"""Wire contracts. Never accept client paths, SQL or credentials."""
import base64
import hashlib
import hmac
import json
import os
import re
from ..models import allowed, integer, text, require_uuid

MIB = 1024 * 1024
MAX_SOURCE_BYTES = 256 * MIB
MAX_ARCHIVE_BYTES = 32 * MIB
MAX_INDEX_BYTES = 512 * MIB
MAX_SOURCE_ROWS = 750000
MAX_RECORDS = 500000
MAX_COLUMNS = 128
MAX_FIELD_BYTES = MIB
MAX_QUERY_KEYS = 100
PAGE_SIZE = 500
CHUNK_BYTES = 256 * 1024
RESPONSE_BYTES = MIB - 4096
STORAGE_BUDGET = 900000000
LEASE_SECONDS = 3600
_CURSOR_KEY = os.urandom(32)

MESSAGES = {
    'bill_limit': 'This BILL export exceeds the supported size. The previous data is still current.',
    'bill_quota': 'There is not enough private storage for this update. The previous data is still current.',
    'bill_restart': 'The temporary BILL build expired. Restart processing the saved export.',
    'bill_conflict': 'The BILL data or update session changed. The previous operation was not overwritten.',
    'bill_invalid_archive': 'The BILL export could not be read or verified. Select the original CSV again.',
    'bill_incomplete': 'The BILL comparison source is incomplete or unavailable. Retry before reviewing.',
}


class SnapshotError(ValueError):
    def __init__(self, code='bill_incomplete'):
        self.code = code if code in MESSAGES else 'bill_incomplete'
        super().__init__(MESSAGES[self.code])


def digest(value):
    if not re.fullmatch('[0-9a-f]{64}', text(value, maximum=64)):
        raise SnapshotError('bill_invalid_archive')
    return value


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def validate_manifest(value):
    keys = ('format parserVersion indexVersion originalHash originalBytes originalArchive indexArchive '
            'recordCount sourceRowCount collapsedRowCount excludedRowCount warningCount vendorDigest')
    out = allowed(value, keys, keys)
    if out['format'] != 'snapshot-v2' or out['parserVersion'] != 'bill-csv-v1' or type(out['indexVersion']) is not int or out['indexVersion'] != 1:
        raise SnapshotError('bill_invalid_archive')
    digest(out['originalHash']); digest(out['vendorDigest'])
    integer(out['originalBytes'], minimum=1, maximum=MAX_SOURCE_BYTES)
    for field, limit in [('recordCount', MAX_RECORDS), ('sourceRowCount', MAX_SOURCE_ROWS),
                         ('collapsedRowCount', MAX_SOURCE_ROWS), ('excludedRowCount', MAX_SOURCE_ROWS),
                         ('warningCount', MAX_SOURCE_ROWS)]:
        integer(out[field], minimum=1 if field in ('recordCount', 'sourceRowCount') else 0, maximum=limit)
    if out['recordCount'] + out['collapsedRowCount'] + out['excludedRowCount'] != out['sourceRowCount']:
        raise SnapshotError('bill_incomplete')
    workspace = None
    for field, extension in [('originalArchive', 'csv'), ('indexArchive', 'sqlite')]:
        fields = 'key hash bytes' + (' expandedHash expandedBytes' if field == 'indexArchive' else '')
        archive = allowed(out[field], fields, fields)
        digest(archive['hash']); integer(archive['bytes'], minimum=1, maximum=MAX_ARCHIVE_BYTES)
        parts = text(archive['key'], maximum=1024).split('/')
        if len(parts) != 5 or parts[1:3] != ['bills', 'v2'] or parts[3] != out['originalHash'] or parts[4] != archive['hash'] + '.' + extension + '.gz':
            raise SnapshotError('bill_invalid_archive')
        require_uuid(parts[0])
        if workspace and workspace != parts[0]:
            raise SnapshotError('bill_invalid_archive')
        workspace = parts[0]
        if field == 'indexArchive':
            digest(archive['expandedHash']); integer(archive['expandedBytes'], minimum=1, maximum=MAX_INDEX_BYTES)
        out[field] = archive
    return out


def validate_query(value):
    out = allowed(value, 'importId references amounts', 'importId references amounts')
    require_uuid(out['importId'])
    if type(out['references']) is not list or type(out['amounts']) is not list or len(out['references']) + len(out['amounts']) > MAX_QUERY_KEYS:
        raise SnapshotError('bill_limit')
    for key, fields in [('references', 'invoiceKey kind'), ('amounts', 'vendorKey kind amount')]:
        items = []
        for raw in out[key]:
            item = allowed(raw, fields, fields)
            if item['kind'] not in ('invoice', 'credit'):
                raise SnapshotError('bill_incomplete')
            text(item['invoiceKey'] if key == 'references' else item['vendorKey'], maximum=4096, blank=False)
            if key == 'amounts':
                integer(item['amount'])
            items.append(item)
        out[key] = items
    return out


def encode_cursor(import_id, query_hash, ordinal):
    require_uuid(import_id); digest(query_hash); integer(ordinal, minimum=-1, maximum=MAX_SOURCE_ROWS)
    raw = json.dumps([import_id, query_hash, ordinal], separators=(',', ':')).encode()
    return base64.urlsafe_b64encode(raw + hmac.digest(_CURSOR_KEY, raw, 'sha256')).decode()


def decode_cursor(token, import_id, query_hash):
    if token is None:
        return -1
    try:
        raw = base64.b64decode(text(token, maximum=2048), altchars=b'-_', validate=True)
        value, signature = raw[:-32], raw[-32:]
        if not hmac.compare_digest(signature, hmac.digest(_CURSOR_KEY, value, 'sha256')):
            raise ValueError
        source, query, after = json.loads(value)
        if source != import_id or query != query_hash:
            raise ValueError
        integer(after, minimum=-1, maximum=MAX_SOURCE_ROWS)
        return after
    except (ValueError, TypeError):
        raise SnapshotError('bill_incomplete') from None
