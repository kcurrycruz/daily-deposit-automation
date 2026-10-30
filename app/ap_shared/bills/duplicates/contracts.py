"""Versioned, bounded detector wire contracts."""
import base64
import hashlib
import hmac
import json
import os
import re
from datetime import date,timedelta
from typing import TypedDict
from ...models import allowed, integer, text, require_uuid, normalize_initials, JsonObject

RULE_VERSION = 'bill-duplicates-v3'
ARTIFACT_FORMAT = 'bill-duplicates-v2'
STORAGE_VERSION = 'v2'
WORKING_RULE_VERSION = 'bill-duplicates-v4'
WORKING_ARTIFACT_FORMAT = 'bill-duplicates-v3'
WORKING_STORAGE_VERSION = 'v3'
WORKING_PIN_FIELDS = 'workingSetId workingDigest workingVersion fullSourceDigest fullRecordCount mappingDigest'


def rule_for_pin(pin):
    return WORKING_RULE_VERSION if pin.get('storageFormat')=='working-v1' else RULE_VERSION
CLASSIFICATIONS = ('exact_pattern','possible_duplicate','amount_difference','export_review','reference_entry_issue','possible_wrong_vendor')
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
    evidence: JsonObject


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
    working=type(value) is dict and value.get('storageFormat')=='working-v1'
    fields='importId importVersion sourceDigest storageFormat recordCount'+(' '+WORKING_PIN_FIELDS if working else '')
    out = allowed(value,fields,fields)
    require_uuid(out['importId']); integer(out['importVersion'], minimum=0)
    digest(out['sourceDigest'])
    if out['storageFormat'] not in ('snapshot-v2', 'rows-v1','working-v1'):
        raise DuplicateError('duplicate_invalid_source')
    integer(out['recordCount'], minimum=0 if working else 1, maximum=100000 if out['storageFormat']=='rows-v1' else MAX_RECORDS)
    if working:
        require_uuid(out['workingSetId']);integer(out['workingVersion'],minimum=0)
        for name in ('workingDigest','fullSourceDigest','mappingDigest'):digest(out[name])
        integer(out['fullRecordCount'],minimum=1,maximum=MAX_RECORDS)
        if out['sourceDigest']!=out['workingDigest'] or out['recordCount']>out['fullRecordCount']:
            raise DuplicateError('duplicate_invalid_source')
    return out


def validate_manifest(value,*,historical=False):
    working=type(value) is dict and value.get('format')==WORKING_ARTIFACT_FORMAT
    keys = 'format ruleVersion sourceDigest importId key hash bytes expandedHash expandedBytes findingCount recordCount'+(' '+WORKING_PIN_FIELDS if working else '')
    out = allowed(value, keys, keys)
    supported=(out['format'],out['ruleVersion']) in [(ARTIFACT_FORMAT,RULE_VERSION),*([('bill-duplicates-v1','bill-duplicates-v1'),('bill-duplicates-v1','bill-duplicates-v2')] if historical else []),(WORKING_ARTIFACT_FORMAT,WORKING_RULE_VERSION)]
    if not supported:
        raise DuplicateError('duplicate_invalid_source')
    for name in ('sourceDigest', 'hash', 'expandedHash'):
        digest(out[name])
    require_uuid(out['importId'])
    integer(out['bytes'], minimum=1, maximum=MAX_ARCHIVE_BYTES)
    integer(out['expandedBytes'], minimum=1, maximum=MAX_BYTES)
    integer(out['findingCount'], minimum=0, maximum=MAX_FINDINGS)
    integer(out['recordCount'], minimum=0 if working else 1, maximum=MAX_RECORDS)
    if working:
        validate_pin({k:out[k] for k in ('importId','sourceDigest','recordCount',*WORKING_PIN_FIELDS.split())}|dict(importVersion=0,storageFormat='working-v1'))
    parts = text(out['key'], maximum=1024).split('/')
    version=WORKING_STORAGE_VERSION if working else STORAGE_VERSION if out['format']==ARTIFACT_FORMAT else 'v1'
    if len(parts) != 6 or parts[1:3] != ['bill-duplicates',version] or parts[3] != out['importId'] or parts[4] != out['ruleVersion'] or parts[5] != out['hash'] + '.sqlite.gz':
        raise DuplicateError('duplicate_invalid_source')
    require_uuid(parts[0])
    return out


def validate_evidence(value,classification):
    """Strict, bounded immutable explanations; never trust stored format claims."""
    from .vendor_patterns import reference_shape
    if classification not in CLASSIFICATIONS:raise DuplicateError('duplicate_invalid_source')
    out=allowed(value,'version dateGapDays referenceReuse profiles edit','version dateGapDays referenceReuse profiles')
    if type(out['version']) is not int or out['version']!=1 or type(out['referenceReuse']) is not bool:
        raise DuplicateError('duplicate_invalid_source')
    integer(out['dateGapDays'],nullable=True,minimum=0,maximum=3652058)
    profiles=out['profiles'];new=classification in ('reference_entry_issue','possible_wrong_vendor')
    if type(profiles) is not list or len(profiles)!=(2 if new else 0):raise DuplicateError('duplicate_invalid_source')
    if out['referenceReuse'] and (new or out['dateGapDays'] is None or out['dateGapDays']<=30):raise DuplicateError('duplicate_invalid_source')
    if new and (out['dateGapDays'] is None or out['dateGapDays']>3):raise DuplicateError('duplicate_invalid_source')
    for profile in profiles:
        p=allowed(profile,'periodStart periodEnd distinctReferences shapes established vendor invoiceNumber matches',
                  'periodStart periodEnd distinctReferences shapes established vendor invoiceNumber matches')
        text(p['vendor'],maximum=1024,blank=False);text(p['invoiceNumber'],maximum=1024,blank=False)
        if p['established'] is not True or type(p['matches']) is not bool:raise DuplicateError('duplicate_invalid_source')
        integer(p['distinctReferences'],minimum=20,maximum=MAX_RECORDS)
        try:
            start=date.fromisoformat(p['periodStart']);end=date.fromisoformat(p['periodEnd'])
            cutoff=end+timedelta(days=1)
            expected_start=date.fromordinal(max(1,cutoff.toordinal()-365))
            if len(p['periodStart'])!=10 or len(p['periodEnd'])!=10 or cutoff.day!=1 or start!=expected_start:raise ValueError
        except (ValueError,TypeError,OverflowError):raise DuplicateError('duplicate_invalid_source') from None
        if type(p['shapes']) is not list or not 1<=len(p['shapes'])<=3:raise DuplicateError('duplicate_invalid_source')
        seen=set();total=0;order=[]
        for shape in p['shapes']:
            v=allowed(shape,'shape references','shape references');text(v['shape'],maximum=2048,blank=False)
            n=integer(v['references'],minimum=3,maximum=p['distinctReferences'])
            if v['shape'] in seen:raise DuplicateError('duplicate_invalid_source')
            seen.add(v['shape']);total+=n;order.append((-n,v['shape']))
        if total>p['distinctReferences'] or total*10<p['distinctReferences']*9 or order!=sorted(order):raise DuplicateError('duplicate_invalid_source')
        if p['matches']!=(reference_shape(p['invoiceNumber']) in seen):raise DuplicateError('duplicate_invalid_source')
    if new and (profiles[0]['matches']==profiles[1]['matches'] or profiles[0]['periodStart']!=profiles[1]['periodStart'] or profiles[0]['periodEnd']!=profiles[1]['periodEnd']):
        raise DuplicateError('duplicate_invalid_source')
    if classification=='reference_entry_issue':
        from ..normalization import vendor_key
        from .vendor_patterns import compact_reference,edit_kind
        if vendor_key(profiles[0]['vendor'])!=vendor_key(profiles[1]['vendor']):raise DuplicateError('duplicate_invalid_source')
        actual=edit_kind(*(compact_reference(p['invoiceNumber']) for p in profiles))
        if actual is None or out.get('edit')!=actual:raise DuplicateError('duplicate_invalid_source')
    elif 'edit' in out:raise DuplicateError('duplicate_invalid_source')
    elif classification=='possible_wrong_vendor':
        from ..normalization import vendor_key
        from .vendor_patterns import compact_reference
        if vendor_key(profiles[0]['vendor'])==vendor_key(profiles[1]['vendor']) or compact_reference(profiles[0]['invoiceNumber'])!=compact_reference(profiles[1]['invoiceNumber']):
            raise DuplicateError('duplicate_invalid_source')
    if len(encoded(out).encode('utf8'))>16384:raise DuplicateError('duplicate_limit')
    return out


def validate_finding_evidence(value,classification,previews,member_count,member_ordinals=None):
    """Bind vendor-format explanations to the complete immutable invoice pair."""
    out=validate_evidence(value,classification)
    if classification not in ('reference_entry_issue','possible_wrong_vendor'):return out
    if type(previews) is not list or len(previews)!=2 or member_count!=2:
        raise DuplicateError('duplicate_invalid_source')
    identities=[];days=[];ordinals=[];amounts=[];currencies=[]
    try:
        for p in previews:
            text(p['vendor'],maximum=1024,blank=False);text(p['invoiceNumber'],maximum=1024,blank=False)
            ordinals.append(integer(p['ordinal'],minimum=0,maximum=MAX_RECORDS-1))
            identities.append((p['vendor'],p['invoiceNumber']))
            day=date.fromisoformat(p['invoiceDate'])
            if len(p['invoiceDate'])!=10:raise ValueError
            days.append(day)
            amounts.append(integer(p['amount'],minimum=1))
            currency=text(p['currency'],maximum=1024).strip().upper()
            currencies.append(currency if re.fullmatch('[A-Z]{3}',currency) else '')
        cutoff=min(days).replace(day=1)
        if len(set(ordinals))!=2 or amounts[0]!=amounts[1] or (all(currencies) and currencies[0]!=currencies[1]):raise ValueError
        if out['dateGapDays']!=abs((days[0]-days[1]).days):raise ValueError
        if sorted(identities)!=sorted((p['vendor'],p['invoiceNumber']) for p in out['profiles']):raise ValueError
        if any(date.fromisoformat(p['periodEnd'])+timedelta(days=1)!=cutoff for p in out['profiles']):raise ValueError
        if member_ordinals is not None and sorted(ordinals)!=sorted(member_ordinals):raise ValueError
    except (KeyError,TypeError,ValueError,OverflowError):
        raise DuplicateError('duplicate_invalid_source') from None
    return out


def validate_review_payload(value):
    keys = 'scan_id import_id expected_import_version finding_key expected_review_version decision initials note'
    out = allowed(value, keys+' working_set_id expected_working_version', keys)
    if 'working_set_id' in out or 'expected_working_version' in out:
        require_uuid(out.get('working_set_id'));integer(out.get('expected_working_version'),minimum=0)
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
