"""External database/object boundary for service tests; SQL is tested in PGlite separately."""
import copy
import hashlib
from uuid import uuid4
from app.ap_shared.bills.contracts import SnapshotError, canonical_hash


class BillStoreDouble:
    def __init__(self, config):
        self.config = config
        self.jobs, self.sources, self.objects, self.requests = {}, {}, {}, {}
        self.active_id, self.version, self.fail_writes = None, 0, False
        self.calls = []

    def job(self, job_id): return copy.deepcopy(self.jobs[job_id])
    def source(self, import_id): return copy.deepcopy(self.sources[import_id])
    def current(self): return dict(active_import_id=self.active_id,import_version=self.version)
    def lookup_hash(self, raw_hash):
        return next((copy.deepcopy(s) for s in self.sources.values() if s['file_hash'] == raw_hash), None)

    def reserve(self, job_id, requested_bytes, request_id):
        if self.fail_writes: raise SnapshotError('bill_quota')
        return dict(used_bytes=0, reserved_bytes=requested_bytes, warning=False)

    def write_chunk(self, job_id, position, data):
        digest = hashlib.sha256(data).hexdigest()
        self.objects[f'{self.config.workspace_id}/staging/{job_id}/{position}-{digest}.bin'] = data
        return dict(hash=digest, size=len(data))

    def read_chunk(self, job_id, position, info):
        return self.objects[f'{self.config.workspace_id}/staging/{job_id}/{position}-{info["hash"]}.bin']

    def put_artifact(self, job_id, name, path, request_id, *, original_hash=None):
        if self.fail_writes: raise SnapshotError('bill_quota')
        data = path.read_bytes(); digest = hashlib.sha256(data).hexdigest()
        raw_hash = original_hash or self.jobs[job_id]['original_hash']
        key = f'{self.config.workspace_id}/bills/v2/{raw_hash}/{digest}.{"csv" if name == "original" else "sqlite"}.gz'
        if key in self.objects and self.objects[key] != data: raise SnapshotError('bill_incomplete')
        self.objects[key] = data
        return dict(key=key, hash=digest, bytes=len(data))

    def read_original(self, job, target): target.write_bytes(self.objects[job['original_archive']['key']])
    def read_artifact(self, manifest, name, target): target.write_bytes(self.objects[manifest['indexArchive' if name == 'index' else 'originalArchive']['key']])
    def cleanup_acknowledged_chunks(self, job_id):
        for key in list(self.objects):
            if key.startswith(f'{self.config.workspace_id}/staging/{job_id}/'): del self.objects[key]

    def rpc(self, operation, data, request_id):
        signature = canonical_hash(dict(operation=operation, data=data))
        if request_id in self.requests:
            old, result = self.requests[request_id]
            if old != signature: raise SnapshotError('bill_conflict')
            return copy.deepcopy(result)
        self.calls.append(operation)
        job_id = data['job_id']
        if operation == 'job_begin':
            if any(j['state'] not in ('activated', 'abandoned') for j in self.jobs.values()): raise SnapshotError('bill_conflict')
            job = dict(id=job_id, workspace_id=self.config.workspace_id, session_nonce=data['session_nonce'],
                       generation=str(uuid4()), expected_import_version=self.version, checkpoint=0,
                       state='uploading', chunks={}, original_hash=None, original_archive=None,
                       metadata=dict(filename=data['filename'], compressed_size=data['compressed_size'], as_of=data.get('as_of', '')))
            self.jobs[job_id] = job
            result = dict(job_id=job_id, generation=job['generation'], expected_import_version=self.version, checkpoint=0, state='uploading')
        else:
            job = self.jobs[job_id]
            if job['session_nonce'] != data['session_nonce'] or job['state'] == 'abandoned': raise SnapshotError('bill_conflict')
            if operation == 'job_chunk':
                job['chunks'][str(data['index'])] = dict(hash=data['chunk_hash'], size=data['size']); result = dict(index=data['index'])
            elif operation == 'job_uploaded':
                job.update(original_hash=data['original_hash'], original_archive=data['original_archive'], state='reading')
                job['metadata']['original_bytes'] = data['original_bytes']; result = dict(state='reading')
            elif operation == 'job_checkpoint':
                if job['generation'] != data['generation'] or job['checkpoint'] != data['expected_checkpoint']: raise SnapshotError('bill_conflict')
                job.update(checkpoint=data['next_checkpoint'], state=data['state']); result = dict(checkpoint=job['checkpoint'])
            elif operation == 'snapshot_stage':
                mf = data['manifest']; source = self.lookup_hash(mf['originalHash'])
                if not source:
                    import_id = str(uuid4())
                    source = dict(id=import_id, file_hash=mf['originalHash'], storage_format='snapshot-v2', state='ready',
                                  record_count=mf['recordCount'], snapshot_manifest=mf, metadata=data['metadata'], original_object_key=mf['originalArchive']['key'])
                    self.sources[import_id] = source
                job.update(state='prepared', import_id=source['id']); result = dict(import_id=source['id'])
            elif operation == 'snapshot_activate':
                if job['state'] != 'prepared' or job['expected_import_version'] != self.version: raise SnapshotError('bill_conflict')
                self.active_id = job['import_id']; self.version += 1; job['state'] = 'activated'
                result = dict(import_id=self.active_id, import_version=self.version)
            elif operation == 'job_abandon': job['state'] = 'abandoned'; result = dict(state='abandoned')
            elif operation == 'job_reuse':
                source = self.lookup_hash(data['original_hash'])
                job.update(import_id=source['id'], original_hash=source['file_hash'], original_archive=source['snapshot_manifest']['originalArchive'],
                           state='activated' if source['id'] == self.active_id else 'prepared')
                result = dict(import_id=source['id'], duplicate=True, alreadyCurrent=source['id'] == self.active_id, confirmationRequired=source['id'] != self.active_id)
            elif operation == 'job_restart':
                if job['generation'] != data['generation']: raise SnapshotError('bill_conflict')
                job.update(generation=str(uuid4()), checkpoint=0, state='reading')
                result = dict(generation=job['generation'], checkpoint=0, state='reading')
            else: raise AssertionError(operation)
        self.requests[request_id] = signature, copy.deepcopy(result)
        return copy.deepcopy(result)
