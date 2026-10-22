"""Complete current-import reads. No statement-specific candidate subsets."""
import json
from ...models import integer, validate_record
from .contracts import DuplicateError, validate_pin


class DuplicateSource:
    def __init__(self, base_repository, bill_operations):
        self.base, self.ops = base_repository, bill_operations

    def pin(self, authorization):
        self.ops._check(authorization)
        current = self.ops.repository.current()
        if not current['active_import_id']:
            return None
        source = self.ops.repository.source(current['active_import_id'])
        if source['state'] != 'ready':
            raise DuplicateError('duplicate_invalid_source')
        return validate_pin(dict(importId=source['id'], importVersion=current['import_version'],
                                 sourceDigest=source['file_hash'], storageFormat=source.get('storage_format', 'rows-v1'),
                                 recordCount=source['record_count']))

    def _check(self, pin, authorization):
        validate_pin(pin)
        if self.pin(authorization) != pin:
            raise DuplicateError('duplicate_conflict')

    def read_page(self, pin, after, limit, authorization):
        self._check(pin, authorization)
        integer(after, minimum=-1, maximum=pin['recordCount'] - 1)
        integer(limit, minimum=1, maximum=5000)
        if pin['storageFormat'] == 'snapshot-v2':
            with self.ops._index(pin['importId'], authorization) as (index, source):
                rows = [(n, validate_record(json.loads(raw))) for n, raw in index.db.execute(
                    'select ordinal,record from bill_records where ordinal>? order by ordinal limit ?', (after, limit))]
        else:
            limit = min(limit, 500)
            page = self.base.records_page(self.base.config.workspace_id, pin['importId'], after, limit)
            expected_last = min(after + limit, pin['recordCount'] - 1)
            expected_cursor = expected_last if expected_last < pin['recordCount'] - 1 else None
            if page['recordCount'] != pin['recordCount'] or page['importId'] != pin['importId'] or page['nextCursor'] != expected_cursor:
                raise DuplicateError('duplicate_invalid_source')
            rows = []
            for at, raw in enumerate(page['records'], after + 1):
                if raw.get('id') != f'{pin["importId"]}:{at}':
                    raise DuplicateError('duplicate_invalid_source')
                rows.append((at, validate_record(raw)))
        expected = min(limit, pin['recordCount'] - after - 1)
        if len(rows) != expected or any(n != after + i + 1 for i, (n, _) in enumerate(rows)):
            raise DuplicateError('duplicate_invalid_source')
        self._check(pin, authorization)
        last = rows[-1][0] if rows else after
        return dict(records=[dict(ordinal=n, bill=b) for n, b in rows], total=pin['recordCount'],
                    nextOrdinal=last if last + 1 < pin['recordCount'] else None)

    def members(self, pin, ordinals, authorization):
        self._check(pin, authorization)
        if type(ordinals) is not list or not 1 <= len(ordinals) <= 100 or len(set(ordinals)) != len(ordinals):
            raise DuplicateError('duplicate_invalid_source')
        for n in ordinals:
            integer(n, minimum=0, maximum=pin['recordCount'] - 1)
        if pin['storageFormat'] == 'snapshot-v2':
            with self.ops._index(pin['importId'], authorization) as (index, _):
                found = dict(index.db.execute('select ordinal,record from bill_records where ordinal in (' +
                             ','.join('?' for _ in ordinals) + ')', ordinals))
            if len(found) != len(ordinals):
                raise DuplicateError('duplicate_invalid_source')
            output = [dict(ordinal=n, bill={**validate_record(json.loads(found[n])), 'id': f'{pin["importId"]}:{n}'}) for n in ordinals]
        else:
            output = [self.read_page(pin, n - 1, 1, authorization)['records'][0] for n in ordinals]
        self._check(pin, authorization)
        return output
