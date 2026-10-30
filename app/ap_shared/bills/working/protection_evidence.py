"""Frozen saved-review member proofs, independent of the current active source.

Only full member identities are read. Legacy artifacts do not acquire invented
modern classification/profile evidence. Cold private archives yield for retry.
"""
from collections import OrderedDict
from contextlib import closing,ExitStack
import json
from pathlib import Path
import tempfile
import threading
import time
from ...models import require_uuid,validate_record
from ..contracts import SnapshotError
from ..duplicates.contracts import validate_manifest,validate_pin,canonical_hash,MAX_BYTES
from ..duplicates.preparation import Unpack,connect,stamp,bounded
from ..duplicates.rules import bill_fingerprint


class FrozenDuplicateEvidence:
    def __init__(self,repository,bill_ops=None,source_prepared=None):
        self.repo,self.bill_ops,self.source_prepared=repository,bill_ops,source_prepared
        self.root=tempfile.TemporaryDirectory(prefix='hwfc-saved-duplicate-evidence-')
        self.entries=OrderedDict();self.lock=threading.RLock()

    def __call__(self,review,auth,bill_ops=None,*,deadline=None,after=-1):
        ops=bill_ops or self.bill_ops
        ops._check(auth);deadline=min(time.monotonic()+5,deadline if deadline is not None else float('inf'))
        scan=self.repo.scan(require_uuid(review['scan_id']))
        mf=validate_manifest(scan['manifest'],historical=True)
        if (scan['state']!='ready' or scan['workspace_id']!=self.repo.config.workspace_id or
            scan['import_id']!=review['reviewed_import_id'] or mf['importId']!=scan['import_id'] or
            mf['ruleVersion']!=scan['rule_version'] or mf['sourceDigest']!=scan['source_digest']):raise SnapshotError('bill_incomplete')
        identity=canonical_hash(mf)
        with self.lock:
            if identity not in self.entries:
                for key,item in list(self.entries.items()):
                    if sum(i['size'] for i in self.entries.values())+mf['expandedBytes']<=MAX_BYTES:break
                    item['unpack'].close();del self.entries[key]
                if sum(i['size'] for i in self.entries.values())+mf['expandedBytes']>MAX_BYTES:raise SnapshotError('bill_limit')
                self.entries[identity]=dict(unpack=Unpack(self.root.name,lambda p:self.repo.read_result(mf,p,historical=True),mf),size=mf['expandedBytes'],stamp=None)
            item=self.entries[identity];unpack=item['unpack']
            if not unpack.step(deadline):raise SnapshotError('bill_range_loading')
            if item['stamp'] is not None and stamp(unpack.path)!=item['stamp']:raise SnapshotError('bill_incomplete')
            item['stamp']=stamp(unpack.path);self.entries.move_to_end(identity)
            with closing(connect(unpack.path)) as result:
                bounded(result,deadline)
                version={'bill-duplicates-v1':1,'bill-duplicates-v2':2,'bill-duplicates-v3':3}[mf['format']]
                expected={'findings','members','scan_meta'}|({'source_map'} if version==3 else set())
                if result.execute('pragma user_version').fetchone()[0]!=version:raise SnapshotError('bill_incomplete')
                schema=result.execute("select type,name from sqlite_master where name not like 'sqlite_%'").fetchall()
                if {name for kind,name in schema if kind=='table'}!=expected or any(kind in ('view','trigger') for kind,_ in schema):raise SnapshotError('bill_incomplete')
                columns={'findings':'id key classification strength reasons latest_date member_count preview search'+(' evidence' if version>1 else ''),'members':'finding_id ordinal fp','scan_meta':'key value'}
                if version==3:columns['source_map']='ordinal source_ordinal fp'
                if any([r[1] for r in result.execute('pragma table_info('+table+')')]!=names.split() for table,names in columns.items()):raise SnapshotError('bill_incomplete')
                meta={k:json.loads(v) for k,v in result.execute('select key,value from scan_meta')};pin=validate_pin(meta['pin'])
                if pin['importId']!=mf['importId'] or pin['sourceDigest']!=mf['sourceDigest'] or pin['recordCount']!=mf['recordCount']:raise SnapshotError('bill_incomplete')
                row=result.execute('select id,member_count from findings where key=?',(review['key'],)).fetchone()
                if row is None or not 2<=row[1]<=500000:raise SnapshotError('bill_incomplete')
                if result.execute('select count(*) from members where finding_id=?',(row[0],)).fetchone()[0]!=row[1]:raise SnapshotError('bill_incomplete')
                selected=result.execute('select ordinal,fp from members where finding_id=? and ordinal>? order by ordinal limit 251',(row[0],after)).fetchall()
                more=len(selected)>250;selected=selected[:250]
                if not selected:raise SnapshotError('bill_incomplete')
                mapped=[]
                for n,fp in selected:
                    if type(n) is not int or not 0<=n<mf['recordCount']:raise SnapshotError('bill_incomplete')
                    if version==3:
                        original=result.execute('select source_ordinal,fp from source_map where ordinal=?',(n,)).fetchone()
                        if original is None or original[1]!=fp or type(original[0]) is not int or not 0<=original[0]<mf['fullRecordCount']:raise SnapshotError('bill_incomplete')
                        mapped.append((n,original[0],fp))
                    else:mapped.append((n,n,fp))
            with ExitStack() as stack:
                if self.source_prepared is not None:
                    info=ops.repository.source(mf['importId'])
                    full_pin=dict(importId=mf['importId'],importVersion=0,sourceDigest=mf.get('fullSourceDigest',mf['sourceDigest']),recordCount=mf.get('fullRecordCount',mf['recordCount']),storageFormat=info.get('storage_format','rows-v1'))
                    if info['state']!='ready' or info['file_hash']!=full_pin['sourceDigest'] or info['record_count']!=full_pin['recordCount']:raise SnapshotError('bill_incomplete')
                    if full_pin['storageFormat']=='snapshot-v2':
                        if not self.source_prepared.prepare(full_pin,info['snapshot_manifest'],auth,ops._check,deadline):raise SnapshotError('bill_range_loading')
                        db=stack.enter_context(self.source_prepared.acquire(full_pin,auth,ops._check))
                    else:db=stack.enter_context(ops._index(mf['importId'],auth))[0].db
                else:db=stack.enter_context(ops._index(mf['importId'],auth))[0].db
                output=[]
                for n,original,fp in mapped:
                    ops._check(auth)
                    raw=db.execute('select record from bill_records where ordinal=?',(original,)).fetchone()
                    if raw is None:raise SnapshotError('bill_incomplete')
                    bill=validate_record(json.loads(raw[0]))
                    if bill_fingerprint(bill)!=fp:raise SnapshotError('bill_incomplete')
                    output.append(dict(ordinal=n,sourceOrdinal=original,bill={**bill,'id':f'{mf["importId"]}:{original}'}))
            ops._check(auth);return dict(memberCount=row[1],members=output,nextCursor=output[-1]['ordinal'] if more else None)

    def close(self):
        with self.lock:
            for item in self.entries.values():item['unpack'].close()
            self.entries.clear();self.root.cleanup()
