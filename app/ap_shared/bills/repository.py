"""Private snapshot Supabase boundary. Object identity is server-generated."""
import hashlib
import json
from pathlib import Path
import re
from ..models import require_uuid, integer
from .contracts import (MAX_ARCHIVE_BYTES, STORAGE_BUDGET, SnapshotError, canonical_hash,
                        digest, validate_manifest)


class BillRepository:
    def __init__(self, base_repository):
        self.base = base_repository
        self.config = base_repository.config

    def job(self, job_id):
        require_uuid(job_id); self.base._private_bucket()
        return self.base._one(self.base._table('ap_bill_jobs').eq('id', job_id))

    def rpc(self, operation, data, request_id):
        if operation not in ('job_begin', 'job_checkpoint', 'job_abandon', 'snapshot_stage', 'snapshot_activate', 'quota_reserve'):
            raise SnapshotError('bill_incomplete')
        require_uuid(request_id); self.base._private_bucket()
        payload = dict(p_workspace=self.config.workspace_id, p_request_id=request_id,
                       p_payload_hash=canonical_hash(dict(operation=operation, data=data)), p_data=data)
        try:
            result = self.base.client.rpc('ap_bill_' + operation, payload).execute().data
            if type(result) is not dict:
                raise SnapshotError('bill_incomplete')
            return result
        except SnapshotError:
            raise
        except Exception as error:
            message = getattr(error, 'message', '')
            raise SnapshotError(message if message.startswith('bill_') else 'bill_incomplete') from None

    def reserve(self, job_id, requested_bytes, request_id):
        job = self.job(job_id)
        integer(requested_bytes, minimum=0, maximum=STORAGE_BUDGET)
        return self.rpc('quota_reserve', dict(job_id=job_id, session_nonce=job['session_nonce'],
                                             bucket=self.config.bucket, requested_bytes=requested_bytes,
                                             budget_bytes=STORAGE_BUDGET), request_id)

    def put_artifact(self, job_id, name, path, request_id):
        job = self.job(job_id)
        if name not in ('original', 'index'):
            raise SnapshotError('bill_incomplete')
        raw_hash = digest(job.get('original_hash', ''))
        with open(path, 'rb') as source:
            data = source.read(MAX_ARCHIVE_BYTES + 1)
        if not data or len(data) > MAX_ARCHIVE_BYTES:
            raise SnapshotError('bill_limit')
        artifact_hash = hashlib.sha256(data).hexdigest()
        extension = 'csv' if name == 'original' else 'sqlite'
        key = f'{self.config.workspace_id}/bills/v2/{raw_hash}/{artifact_hash}.{extension}.gz'
        self.base.write_bytes(self.config.workspace_id, key, data, 'application/gzip')
        return dict(key=key, hash=artifact_hash, bytes=len(data))

    def read_artifact(self, manifest, name, target):
        manifest = validate_manifest(manifest)
        if name not in ('original', 'index'):
            raise SnapshotError('bill_incomplete')
        info = manifest['originalArchive' if name == 'original' else 'indexArchive']
        key = info['key']
        if not key.startswith(self.config.workspace_id + '/'):
            raise PermissionError('AP workspace access denied.')
        data = self.base.read_bytes(self.config.workspace_id, key)
        if len(data) != info['bytes'] or hashlib.sha256(data).hexdigest() != info['hash']:
            raise SnapshotError('bill_invalid_archive')
        Path(target).write_bytes(data)

    def cleanup_acknowledged_chunks(self, job_id):
        job = self.job(job_id)
        if job['state'] not in ('reading', 'grouping', 'packaging', 'prepared', 'activated') or not job.get('original_archive'):
            raise SnapshotError('bill_incomplete')
        digest(job['original_archive']['hash'])
        keys = []
        for position, info in job['chunks'].items():
            if not re.fullmatch('[0-9]{1,3}', position) or not 0 <= int(position) <= 127:
                raise SnapshotError('bill_incomplete')
            part_hash = digest(info['hash'])
            key = f'{self.config.workspace_id}/staging/{job_id}/{position}-{part_hash}.bin'
            self.base._object_key(self.config.workspace_id, key)
            keys.append(key)
        # No prefix deletion: only exact, verified acknowledged upload chunks.
        for key in keys:
            self.base._private_bucket()
            self.base.client.storage.from_(self.config.bucket).remove([key])
