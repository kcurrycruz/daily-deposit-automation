"""Versioned, bounded detector wire contracts."""
import base64
import hashlib
import hmac
import json
import os
import re
from typing import TypedDict
from ...models import allowed, integer, text, require_uuid, normalize_initials, JsonObject

RULE_VERSION = 'bill-duplicates-v2'
MAX_RECORDS = 500000
MAX_FINDINGS = 100000
MAX_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
PAGE_SIZE = 100
RESPONSE_BYTES = 1024 * 1024 - 8192
MESSAGES = {
    'duplicate_unavailable': 'Duplicate checks are unavailable. Your saved BILL data and statements are unchanged. Retry loading.',
    'duplicate_conflict': 'The source or shared review changed. Refresh duplicate checks before saving.',
    'duplicate_limit': 'Duplicate checks could not cover this entire export within the supported limits. Statement checks remain available.',
    'duplicate_restart': 'Duplicate checking needs to restart from the saved BILL data. No reupload is needed.',
    'duplicate_quota': 'There is not enough private storage for duplicate checks. Your saved BILL data is unchanged.',
    'duplicate_invalid_source': 'The saved duplicate evidence could not be verified. Retry loading or contact your administrator.',
}
_CURSOR_KEY = os.urandom(32)


class SourcePin(TypedDict):
    importId: str
    importVersion: int
    sourceDigest: str
    storageFormat: str
    recordCount: int


class ScanRecord(TypedDict):
    ordinal: int
    bill: JsonObject


class Finding(TypedDict):
    key: str
    classification: str
    strength: str
    reasons: list[str]
    latestInvoiceDate: str
    memberCount: int


class Member(TypedDict):
    ordinal: int
    fingerprint: str


class Review(TypedDict):
    key: str
    decision: str
    initials: str
    note: str
    version: int
    at: str
    reviewedImportId: str


class BillPreview(TypedDict):
    ordinal: int
    vendor: str
    invoiceNumber: str
    amount: int
    invoiceDate: str
    currency: str


class FindingSummary(Finding):
    preview: list[BillPreview]
    review: Review | None
    priorReview: bool


class ResultManifest(TypedDict):
    format: str
    ruleVersion: str
    sourceDigest: str
    importId: str
    key: str
    hash: str
    bytes: int
    expandedHash: str
    expandedBytes: int
    findingCount: int
    recordCount: int


class ScanProgress(TypedDict):
    scanId: str
    importId: str
    importVersion: int
    ruleVersion: str
    state: str
    generation: str
    checkpoint: int
    phase: str
    recordsRead: int
    probes: int
    findingCount: int | None
    counts: JsonObject | None
    projectionReady: bool
    reviewRevision: int | None
    errorCode: str | None


class FindingPage(TypedDict):
    scanId: str
    importId: str
    ruleVersion: str
    reviewRevision: int
    findings: list[FindingSummary]
    total: int
    counts: JsonObject
    nextCursor: str | None


class DuplicateError(ValueError):
    def __init__(self, code='duplicate_unavailable'):
        self.code = code if code in MESSAGES else 'duplicate_unavailable'
        super().__init__(MESSAGES[self.code])


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise DuplicateError('duplicate_invalid_source')
    return value


def canonical_hash(value):
    return hashlib.sha256(encoded(value).encode('utf8')).hexdigest()


def validate_pin(value):
    out = allowed(value, 'importId importVersion sourceDigest storageFormat recordCount',
                  'importId importVersion sourceDigest storageFormat recordCount')
    require_uuid(out['importId']); integer(out['importVersion'], minimum=0)
    digest(out['sourceDigest'])
    if out['storageFormat'] not in ('snapshot-v2', 'rows-v1'):
        raise DuplicateError('duplicate_invalid_source')
    integer(out['recordCount'], minimum=1, maximum=MAX_RECORDS if out['storageFormat'] == 'snapshot-v2' else 100000)
    return out


def validate_manifest(value):
    keys = 'format ruleVersion sourceDigest importId key hash bytes expandedHash expandedBytes findingCount recordCount'
    out = allowed(value, keys, keys)
    if out['format'] != 'bill-duplicates-v1' or out['ruleVersion'] != RULE_VERSION:
        raise DuplicateError('duplicate_invalid_source')
    for name in ('sourceDigest', 'hash', 'expandedHash'):
        digest(out[name])
    require_uuid(out['importId'])
    integer(out['bytes'], minimum=1, maximum=MAX_ARCHIVE_BYTES)
    integer(out['expandedBytes'], minimum=1, maximum=MAX_BYTES)
    integer(out['findingCount'], minimum=0, maximum=MAX_FINDINGS)
    integer(out['recordCount'], minimum=1, maximum=MAX_RECORDS)
    parts = text(out['key'], maximum=1024).split('/')
    if len(parts) != 6 or parts[1:3] != ['bill-duplicates', 'v1'] or parts[3] != out['importId'] or parts[4] != RULE_VERSION or parts[5] != out['hash'] + '.sqlite.gz':
        raise DuplicateError('duplicate_invalid_source')
    require_uuid(parts[0])
    return out


def validate_review_payload(value):
    keys = 'scan_id import_id expected_import_version finding_key expected_review_version decision initials note'
    out = allowed(value, keys, keys)
    require_uuid(out['scan_id']); require_uuid(out['import_id']); digest(out['finding_key'])
    integer(out['expected_import_version'], minimum=0); integer(out['expected_review_version'], minimum=0)
    if out['decision'] not in ('confirmed_duplicate', 'not_duplicate', 'unreviewed'):
        raise DuplicateError('duplicate_conflict')
    out['initials'] = normalize_initials(out['initials'])
    text(out['note'], maximum=16384)
    return out


def encode_cursor(binding, position):
    raw = encoded([canonical_hash(binding), position]).encode()
    return base64.urlsafe_b64encode(raw + hmac.digest(_CURSOR_KEY, raw, 'sha256')).decode()


def decode_cursor(token, binding):
    if token is None:
        return None
    try:
        raw = base64.b64decode(text(token, maximum=2048), altchars=b'-_', validate=True)
        body, signature = raw[:-32], raw[-32:]
        if not hmac.compare_digest(signature, hmac.digest(_CURSOR_KEY, body, 'sha256')):
            raise ValueError
        source, position = json.loads(body)
        if source != canonical_hash(binding) or type(position) is not dict:
            raise ValueError
        return position
    except (ValueError, TypeError, UnicodeError):
        raise DuplicateError('duplicate_conflict') from None
