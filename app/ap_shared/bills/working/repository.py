"""Private storage/SQL boundary for immutable active BILL working sets."""
import hashlib
from pathlib import Path
from ...models import require_uuid
from ..contracts import canonical_hash, MAX_ARCHIVE_BYTES, SnapshotError
from .contracts import validate_working_manifest, working_digest


class WorkingRepository:
    def __init__(self, base):
        self.base, self.config = base, base.config

    def home(self):
        self.base._private_bucket()
        return self.base._one(self.base.client.table('ap_workspaces').select('*').eq('id', self.config.workspace_id))

    def source(self, source_id):
        source = self.base.import_info(self.config.workspace_id, require_uuid(source_id))
        if source['state'] != 'ready':
            raise SnapshotError('bill_incomplete')
        return source

    def _row(self, table, ident):
        require_uuid(ident); self.base._private_bucket()
        row = self.base._one(self.base._table(table).eq('id', ident))
        if row['id'] != ident or row['workspace_id'] != self.config.workspace_id:
            raise PermissionError('AP workspace access denied.')
        return row

    def job(self, job_id):
        return self._row('ap_bill_working_jobs', job_id)

    def find_job(self,job_id):
        require_uuid(job_id);self.base._private_bucket()
        rows=self.base._table('ap_bill_working_jobs').eq('id',job_id).limit(1).execute().data
        if type(rows) is not list:raise SnapshotError('bill_incomplete')
        if not rows:return None
        if rows[0]['id']!=job_id or rows[0]['workspace_id']!=self.config.workspace_id:
            raise PermissionError('AP workspace access denied.')
        return rows[0]

    def working_set(self, set_id):
        row = self._row('ap_bill_working_sets', set_id)
        validate_working_manifest(row['manifest'])
        return row

    def rpc(self, operation: str, data: dict, request_id: str) -> dict:
        if operation not in ('begin', 'checkpoint', 'stage', 'activate', 'cancel', 'reserve', 'restart'):
            raise SnapshotError('bill_incomplete')
        require_uuid(request_id); self.base._private_bucket()
        try:
            response = self.base.client.rpc('ap_bill_working_mutate', dict(p_operation=operation,
                p_workspace=self.config.workspace_id, p_request_id=request_id,
                p_payload_hash=canonical_hash(dict(operation=operation, data=data)), p_data=data)).execute().data
        except Exception as error:
            message = getattr(error, 'message', '')
            raise SnapshotError(message if message.startswith('bill_') else 'bill_incomplete') from None
        if type(response) is not dict:
            raise SnapshotError('bill_incomplete')
        return response

    def lookup_digest(self, identity):
        from ..contracts import digest
        digest(identity); self.base._private_bucket()
        rows=self.base._table('ap_bill_working_sets').eq('working_digest',identity).limit(1).execute().data
        if type(rows) is not list:raise SnapshotError('bill_incomplete')
        if not rows:return None
        validate_working_manifest(rows[0]['manifest'])
        return rows[0]

    def put_artifact(self, job_id, name, path):
        if name not in ('index', 'context'):
            raise SnapshotError('bill_incomplete')
        job = self.job(job_id); source = self.source(job['source_import_id'])
        identity = working_digest(dict(importId=source['id'], sourceDigest=source['file_hash'],
                                       recordCount=source['record_count']), job['policy'], job['protection_digest'])
        with open(path, 'rb') as stream:
            raw = stream.read(MAX_ARCHIVE_BYTES + 1)
        if not raw or len(raw) > MAX_ARCHIVE_BYTES:
            raise SnapshotError('bill_limit')
        digest = hashlib.sha256(raw).hexdigest()
        key = f'{self.config.workspace_id}/bill-working/v1/{identity}/{digest}.sqlite.gz'
        self.base.write_bytes(self.config.workspace_id, key, raw, 'application/gzip')
        return dict(key=key, hash=digest, bytes=len(raw))

    def read_artifact(self, manifest, name, target):
        manifest = validate_working_manifest(manifest)
        if name not in ('index', 'context'):
            raise SnapshotError('bill_incomplete')
        info = manifest[name + 'Archive']
        if not info['key'].startswith(self.config.workspace_id + '/'):
            raise PermissionError('AP workspace access denied.')
        raw = self.base.read_bytes(self.config.workspace_id, info['key'])
        if (len(raw) != info['bytes'] or len(raw) > MAX_ARCHIVE_BYTES
                or hashlib.sha256(raw).hexdigest() != info['hash']):
            raise SnapshotError('bill_invalid_archive')
        Path(target).write_bytes(raw)
