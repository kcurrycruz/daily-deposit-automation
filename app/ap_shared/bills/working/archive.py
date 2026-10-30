"""Bounded immutable active/context cache. Never fall back to a full import."""
from collections import OrderedDict,Counter
from contextlib import contextmanager, closing
import hashlib
import json
import sqlite3
import tempfile
import threading
import time
from ...models import validate_record
from ..contracts import MAX_INDEX_BYTES, SnapshotError
from ..parser import encoded
from ..normalization import vendor_key, invoice_key
from ..duplicates.rules import eligible, invoice_day, bill_fingerprint
from ..duplicates.preparation import Unpack, connect, stamp
from ..duplicates.contracts import DuplicateError
from .builds import INDEX_SCHEMA, CONTEXT_SCHEMA
from .contracts import validate_working_manifest,MappingDigest
from .policy import retention_reasons
from .context import HistoryContext, context_keys


class WorkingCache:
    def __init__(self, repository):
        self.repository=repository
        self.root=tempfile.TemporaryDirectory(prefix='hwfc-active-bills-')
        self.entries=OrderedDict();self.lock=threading.RLock();self.closed=False

    def _remove(self,key):
        item=self.entries[key]
        if item['refs']:return False
        for unpack in item['unpack'].values():unpack.close()
        del self.entries[key];return True

    def _schema(self,db,expected,table,scope):
        if db.execute('pragma user_version').fetchone()[0]!=1:
            raise SnapshotError('bill_invalid_archive')
        schema=db.execute("select type,name from sqlite_master where name not like 'sqlite_%'").fetchall()
        if {name for kind,name in schema if kind=='table'}!=set(expected) or any(kind in ('view','trigger') for kind,_ in schema):
            raise SnapshotError('bill_invalid_archive')
        meta={k:json.loads(v) for k,v in db.execute('select key,value from '+table)}
        if meta!={'scope':scope}:raise SnapshotError('bill_invalid_archive')

    def _validate_rows(self,item,manifest,db,history):
        after=item['after'];rows=db.execute('select * from working_records where ordinal>? order by ordinal limit 250',(after,)).fetchall()
        for ordinal,original,vendor,reference,kind,amount,raw,reason_raw in rows:
            if (type(ordinal) is not int or ordinal!=item['count'] or type(original) is not int
                    or not item['original']<original<manifest['fullRecordCount']):
                raise SnapshotError('bill_invalid_archive')
            record=validate_record(json.loads(raw));reasons=json.loads(reason_raw)
            if (type(reasons) is not list or not reasons or record.get('id')!=f'{manifest["source"]["importId"]}:{original}'
                    or reasons!=retention_reasons(record,manifest['policy'],protected='follow_up' in reasons)
                    or vendor!=vendor_key(record['vendor']) or reference!=invoice_key(record['invoiceNumber'])
                    or kind!=record.get('kind','invoice') or amount!=record['amount']):
                raise SnapshotError('bill_invalid_archive')
            day=invoice_day(record)
            if eligible(record) and day is not None:
                profiles,recurrences=context_keys(vendor,amount,day)
                for args in profiles:history.profile(*args)
                for args in recurrences:history.recurring(*args)
            item['count']+=1;item['after']=ordinal;item['original']=original
            item['mapping'].add(ordinal,original,bill_fingerprint(record));item['reasons'].update(reasons)
        if len(rows)<250:
            if item['count']!=manifest['activeCount'] or item['mapping'].hexdigest()!=manifest['mappingDigest'] or dict(item['reasons'])!=manifest['retainedReasonCounts']:
                raise SnapshotError('bill_invalid_archive')
            item['phase']='profiles';item['profile_after']=('',0)

    def _validate(self,item,manifest,deadline):
        scope={k:v for k,v in manifest.items() if k not in ('workingSetId','indexArchive','contextArchive')}
        with closing(connect(item['unpack']['index'].path)) as index,closing(connect(item['unpack']['context'].path)) as context_db:
            history=HistoryContext(context_db)
            if item['phase']=='schema':
                self._schema(index,INDEX_SCHEMA,'working_meta',scope)
                self._schema(context_db,CONTEXT_SCHEMA,'context_meta',scope)
                item['phase']='rows'
            while time.monotonic()<deadline:
                if item['phase']=='rows':self._validate_rows(item,manifest,index,history)
                elif item['phase']=='profiles':
                    rows=context_db.execute('select vendor,month from profiles where (vendor,month)>(?,?) order by vendor,month limit 250',item['profile_after']).fetchall()
                    for key in rows:history.profile(*key);item['profile_after']=key
                    if len(rows)<250:item['phase']='recurrences';item['recurrence_after']=('',-1,0)
                elif item['phase']=='recurrences':
                    rows=context_db.execute('select vendor,amount,day from recurrences where (vendor,amount,day)>(?,?,?) order by vendor,amount,day limit 250',item['recurrence_after']).fetchall()
                    for key in rows:history.recurring(*key);item['recurrence_after']=key
                    if len(rows)<250:item['phase']='vendors';item['vendor_table']='working_vendors';item['vendor_digest']='vendorDigest';item['vendor_after']=-1;item['vendor_hash']=hashlib.sha256(b'[');item['vendor_count']=0
                elif item['phase']=='vendors':
                    rows=index.execute('select ordinal,vendor from '+item['vendor_table']+' where ordinal>? order by ordinal limit 250',(item['vendor_after'],)).fetchall()
                    for ordinal,vendor in rows:
                        if item['vendor_count']:item['vendor_hash'].update(b',')
                        item['vendor_hash'].update(encoded(dict(vendor=vendor)).encode('utf8'))
                        item['vendor_count']+=1;item['vendor_after']=ordinal
                    if len(rows)<250:
                        item['vendor_hash'].update(b']')
                        if item['vendor_hash'].hexdigest()!=manifest[item['vendor_digest']]:raise SnapshotError('bill_invalid_archive')
                        if item['vendor_table']=='working_vendors':
                            item.update(vendor_table='archive_vendors',vendor_digest='archiveVendorDigest',vendor_after=-1,vendor_hash=hashlib.sha256(b'['),vendor_count=0)
                            continue
                        item['phase']='done';return True
                else:return True
        return False

    def prepare(self,manifest,auth,authorize,deadline):
        authorize(auth);manifest=validate_working_manifest(manifest);key=manifest['workingDigest']
        with self.lock:
            if self.closed:raise SnapshotError('bill_incomplete')
            if key in self.entries and self.entries[key]['ready']:
                item=self.entries[key]
                if item['manifest']!=manifest or any(stamp(u.path)!=item['stamps'][n] for n,u in item['unpack'].items()):
                    raise SnapshotError('bill_invalid_archive')
                item['last']=time.monotonic();authorize(auth);return True
            if time.monotonic()>=deadline:return False
            if key not in self.entries:
                size=sum(manifest[n+'Archive']['expandedBytes'] for n in ('index','context'))
                for old in list(self.entries):
                    if sum(e['size'] for e in self.entries.values())+size<=MAX_INDEX_BYTES:break
                    self._remove(old)
                if sum(e['size'] for e in self.entries.values())+size>MAX_INDEX_BYTES:
                    raise SnapshotError('bill_limit')
                item=dict(manifest=manifest,unpack={},size=size,refs=0,last=time.monotonic(),ready=False,
                          phase='schema',after=-1,original=-1,count=0,mapping=MappingDigest(),reasons=Counter())
                self.entries[key]=item
                for name in ('index','context'):
                    item['unpack'][name]=Unpack(self.root.name,
                        lambda target,n=name:self.repository.read_artifact(manifest,n,target),manifest[name+'Archive'])
            item=self.entries[key]
            try:
                for unpack in item['unpack'].values():
                    if not unpack.step(deadline):authorize(auth);return False
                if not self._validate(item,manifest,deadline):authorize(auth);return False
                authorize(auth);item['ready']=True;item['stamps']={n:stamp(u.path) for n,u in item['unpack'].items()}
                item['last']=time.monotonic();return True
            except Exception as error:
                self._remove(key)
                if isinstance(error,DuplicateError):raise SnapshotError('bill_invalid_archive') from None
                if isinstance(error,(sqlite3.Error,KeyError,TypeError,json.JSONDecodeError)):
                    raise SnapshotError('bill_invalid_archive') from None
                raise

    @contextmanager
    def acquire(self,manifest,auth,authorize):
        authorize(auth);manifest=validate_working_manifest(manifest);key=manifest['workingDigest']
        with self.lock:
            item=self.entries.get(key)
            if not item or not item['ready'] or item['manifest']!=manifest:
                raise SnapshotError('bill_incomplete')
            if any(stamp(u.path)!=item['stamps'][n] for n,u in item['unpack'].items()):
                raise SnapshotError('bill_invalid_archive')
            item['refs']+=1;self.entries.move_to_end(key)
        index=context_db=None
        try:
            index=connect(item['unpack']['index'].path);context_db=connect(item['unpack']['context'].path)
            authorize(auth);yield index,HistoryContext(context_db);authorize(auth)
        finally:
            if index:index.close()
            if context_db:context_db.close()
            with self.lock:item['refs']-=1;item['last']=time.monotonic()

    def close(self):
        with self.lock:
            self.closed=True
            for key in list(self.entries):self._remove(key)
            if not self.entries:self.root.cleanup()
