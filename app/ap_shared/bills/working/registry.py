"""Owned process-local derived builds; durable job policy survives their loss."""
from pathlib import Path
import tempfile
import threading
import time
from ..contracts import SnapshotError
from .builds import WorkingBuilder


class WorkingRegistry:
    def __init__(self,bill_operations,source_prepared=None):
        self.bill_ops=bill_operations;self.source_prepared=source_prepared
        self.root=tempfile.TemporaryDirectory(prefix='hwfc-bill-ranges-')
        self.entries={};self.lock=threading.RLock()

    def start(self,job,source,protections,reused_manifest=None):
        with self.lock:
            if job['id'] in self.entries:return
            for ident,item in list(self.entries.items()):
                if time.monotonic()-item['last']>=3600:self.release(ident)
            if len(self.entries)>=2:raise SnapshotError('bill_conflict')
            folder=tempfile.TemporaryDirectory(prefix='range-',dir=self.root.name)
            try:
                builder=None if reused_manifest else WorkingBuilder(None,folder.name,dict(importId=source['id'],sourceDigest=source['file_hash'],
                    recordCount=source['record_count']),job['policy'],protections,time.monotonic)
            except Exception:folder.cleanup();raise
            self.entries[job['id']]=dict(builder=builder,folder=folder,generation=job['generation'],nonce=job['session_nonce'],
                source=source,last=time.monotonic(),previous=None,reply=None,checkpoint=0,manifest=reused_manifest)

    def step(self,job,expected,auth,authorize,deadline,bill_operations=None):
        with self.lock:
            authorize(auth);item=self.entries.get(job['id'])
            if item is None:return dict(state='restart_required',checkpoint=job['checkpoint'],done=False)
            if item['generation']!=job['generation'] or item['nonce']!=auth.session_nonce:
                raise SnapshotError('bill_conflict')
            if expected==item['previous']:return item['reply']
            if expected!=item['checkpoint']:raise SnapshotError('bill_conflict')
            builder=item['builder'];item['last']=time.monotonic()
            if builder is None:
                progress=dict(done=True,phase='reusing',recordsRead=item['source']['record_count'],activeCount=item['manifest']['activeCount'])
            elif builder.phase=='reading':
                source=item['source']
                pin=dict(importId=source['id'],importVersion=job['expected_import_version'],sourceDigest=source['file_hash'],
                         recordCount=source['record_count'],storageFormat=source.get('storage_format','rows-v1'))
                if self.source_prepared is not None and pin['storageFormat']=='snapshot-v2':
                    if not self.source_prepared.prepare(pin,source['snapshot_manifest'],auth,authorize,deadline):
                        progress=dict(done=False,phase='reading',recordsRead=builder.history.read,activeCount=builder.active)
                    else:
                        with self.source_prepared.acquire(pin,auth,authorize) as db:
                            builder.source_db=db
                            try:progress=builder.step(deadline)
                            finally:builder.source_db=None
                else:
                    with (bill_operations or self.bill_ops)._index(source['id'],auth) as (index,_):
                        builder.source_db=index.db
                        try:progress=builder.step(deadline)
                        finally:builder.source_db=None
            else:progress=builder.step(deadline)
            authorize(auth)
            reply=dict(**progress,state='packaging' if progress['done'] else 'building',checkpoint=expected+1)
            item.update(previous=expected,reply=reply,checkpoint=expected+1,last=time.monotonic())
            return reply

    def entry(self,job_id):
        with self.lock:
            if job_id not in self.entries:raise SnapshotError('bill_restart')
            return self.entries[job_id]

    def release(self,job_id):
        with self.lock:
            item=self.entries.pop(job_id,None)
            if item:
                if item['builder']:item['builder'].close()
                Path(item['folder'].name).resolve().relative_to(Path(self.root.name).resolve())
                item['folder'].cleanup()

    def close(self):
        with self.lock:
            for key in list(self.entries):self.release(key)
            self.root.cleanup()
            if self.source_prepared:self.source_prepared.close()
