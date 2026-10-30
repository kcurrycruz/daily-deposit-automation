"""Retention effects, rather than irrelevant recent follow-ups, identify a subset."""
from collections import OrderedDict
from contextlib import contextmanager
import json
import threading
import time
from ...models import validate_record
from ..contracts import SnapshotError,canonical_hash
from ..normalization import vendor_key,invoice_key
from .policy import retention_reasons
from .protections import ProtectionSet


class EffectiveProtections:
    def __init__(self,source_prepared=None):
        self.source_prepared=source_prepared;self.entries=OrderedDict();self.lock=threading.RLock()

    @contextmanager
    def _source(self,source,ops,auth,deadline):
        pin=dict(importId=source['id'],importVersion=0,sourceDigest=source['file_hash'],recordCount=source['record_count'],storageFormat=source.get('storage_format','rows-v1'))
        if self.source_prepared is not None and pin['storageFormat']=='snapshot-v2':
            if not self.source_prepared.prepare(pin,source['snapshot_manifest'],auth,ops._check,deadline):raise SnapshotError('bill_range_loading')
            with self.source_prepared.acquire(pin,auth,ops._check) as db:yield db
        else:
            with ops._index(source['id'],auth) as (index,_):yield index.db

    def derive(self,snapshot,source,policy,ops,auth,deadline):
        ops._check(auth)
        raw=snapshot['protections'];identity=canonical_hash([source['id'],source['file_hash'],source['record_count'],policy,snapshot['digest']])
        with self.lock:
            if identity not in self.entries:
                while len(self.entries)>=2:self.entries.popitem(last=False)
                self.entries[identity]=dict(keys=sorted(raw.keys,key=lambda k:(k[0] or '',k[1],k[2])),at=0,after=-1,protections=ProtectionSet(),done=False)
            entry=self.entries[identity];self.entries.move_to_end(identity)
            if policy['mode']=='all' or not entry['keys']:entry['done']=True
            if not entry['done']:
                with self._source(source,ops,auth,deadline) as db:
                    while time.monotonic()<deadline and entry['at']<len(entry['keys']):
                        vendor,reference,kind=entry['keys'][entry['at']]
                        params=[reference,kind,entry['after']]
                        where='reference_key=? and kind=? and ordinal>?'
                        if vendor is not None:where+=' and vendor_key=?';params.append(vendor)
                        rows=db.execute('select ordinal,record from bill_records where '+where+' order by ordinal limit 250',params).fetchall()
                        for n,raw_record in rows:
                            record=validate_record(json.loads(raw_record))
                            if invoice_key(record['invoiceNumber'])!=reference or record.get('kind','invoice')!=kind or vendor is not None and vendor_key(record['vendor'])!=vendor:raise SnapshotError('bill_incomplete')
                            if not retention_reasons(record,policy,protected=False):
                                # Actual source namespaces bind the effect. Unknown vendor
                                # mappings and Adventure aliases already expanded the query.
                                entry['protections']._add(record['vendor'],record['invoiceNumber'],kind)
                            entry['after']=n
                        if len(rows)<250:entry['at']+=1;entry['after']=-1
                    entry['done']=entry['at']==len(entry['keys'])
            ops._check(auth)
            if not entry['done']:raise SnapshotError('bill_range_loading')
            effective=entry['protections']
            return dict(epoch=snapshot['epoch'],digest=effective.digest(),protections=effective)
