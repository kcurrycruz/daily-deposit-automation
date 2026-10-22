"""Workspace-scoped cloud boundary for detector metadata and review history."""
from functools import wraps
from ...models import require_uuid, integer
from .contracts import DuplicateError, MESSAGES, canonical_hash, digest, validate_pin

OPERATIONS = frozenset('ensure claim checkpoint restart publish fail reserve review'.split())


def private_operation(method):
    @wraps(method)
    def run(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except (DuplicateError, PermissionError):
            raise
        except Exception as error:
            message = getattr(error, 'message', '')
            code = message if message in MESSAGES else 'duplicate_conflict' if message == 'request_conflict' else 'duplicate_unavailable'
            raise DuplicateError(code) from None
    return run


class DuplicateRepository:
    def __init__(self, base_repository):
        self.base, self.config = base_repository, base_repository.config

    def _home(self):
        self.base._private_bucket()
        return self.base._one(self.base.client.table('ap_workspaces').select('*').eq('id', self.config.workspace_id))

    @private_operation
    def current(self):
        home = self._home()
        if not home['active_import_id']:
            return None
        info = self.base.import_info(self.config.workspace_id, home['active_import_id'])
        if info['state'] != 'ready':
            raise DuplicateError('duplicate_invalid_source')
        return validate_pin(dict(importId=info['id'], importVersion=home['import_version'], sourceDigest=info['file_hash'],
                                 storageFormat=info.get('storage_format', 'rows-v1'), recordCount=info['record_count']))

    @private_operation
    def scan(self, scan_id):
        require_uuid(scan_id); self.base._private_bucket()
        row = self.base._one(self.base._table('ap_duplicate_scans').eq('id', scan_id))
        if row['id'] != scan_id or row['workspace_id'] != self.config.workspace_id:
            raise PermissionError('AP workspace access denied.')
        return row

    @private_operation
    def rpc(self, operation, data, request_id):
        if operation not in OPERATIONS:
            raise DuplicateError('duplicate_invalid_source')
        require_uuid(request_id); self.base._private_bucket()
        payload = dict(p_operation=operation, p_workspace=self.config.workspace_id, p_request_id=request_id,
                       p_payload_hash=canonical_hash(dict(operation=operation, data=data)), p_data=data)
        result = self.base.client.rpc('ap_duplicate_mutate', payload).execute().data
        if type(result) is not dict:
            raise DuplicateError()
        return result

    @private_operation
    def review_revision(self):
        return integer(self._home()['duplicate_review_revision'], minimum=0)

    @private_operation
    def reviews_page(self, after_key=None, limit=500):
        integer(limit, minimum=1, maximum=500); self.base._private_bucket()
        query = self.base._table('ap_duplicate_reviews').order('key').limit(limit + 1)
        if after_key is not None:
            query = query.gt('key', digest(after_key))
        rows = query.execute().data
        if type(rows) is not list or len(rows) > limit + 1:
            raise DuplicateError()
        output = []
        previous = after_key or ''
        for row in rows[:limit]:
            key = digest(row['key'])
            if key <= previous:
                raise DuplicateError('duplicate_invalid_source')
            previous = key
            output.append(dict(key=key, decision=row['decision'], initials=row['initials'], note=row['note'],
                               version=row['version'], at=row['at'], reviewedImportId=row['reviewed_import_id']))
        return dict(reviews=output, nextCursor=output[-1]['key'] if len(rows) > limit else None)
