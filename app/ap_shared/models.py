"""Strict serialization contracts; never include secrets in frontend data."""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Mapping, TypedDict
from urllib.parse import urlparse
from uuid import UUID
import json
import math
import re

JsonObject = dict[str, object]
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_CHUNK_BYTES = 256 * 1024
MAX_ENVELOPE_BYTES = 1024 * 1024
MAX_RECORDS = 100000
PAGE_SIZE = 500
MAX_PDFS = 20
AUTH_SECONDS = 28800
PREVIEW_SECONDS = 300
MAX_SAFE_CENTS = 9007199254740991
RULE_VERSION = 'ap-match-v2'
ACTIONS = frozenset('bootstrap records_page statement history_page pdf_preview upload_begin upload_chunk upload_finish import_begin import_records import_finish save_revision save_mapping complete_revision reopen_statement archive_statement migrate_legacy'.split())
DECISIONS = frozenset(['Follow up with vendor','Request missing invoice','Check payment timing','Check credit application','Investigate amount difference','Reviewed — no action needed'])

class ApValidationError(ValueError):
    """Invalid input, with a safe message that does not repeat the input."""

@dataclass(frozen=True)
class ApConfig:
    password: str = field(repr=False)
    supabase_url: str
    supabase_secret_key: str = field(repr=False)
    workspace_id: str
    bucket: str

@dataclass(frozen=True)
class Authorization:
    workspace_id: str
    session_nonce: str
    expires_at: datetime
    credential_fingerprint: str = field(repr=False)

class SharedSnapshot(TypedDict):
    activeImport: JsonObject | None
    mappings: dict[str, str]
    statements: list[JsonObject]
    nextCursor: str | None

def require_uuid(value: object) -> str:
    if type(value) is not str:
        raise ApValidationError('A valid identifier is required.')
    try:
        parsed = UUID(value)
    except ValueError:
        raise ApValidationError('A valid identifier is required.') from None
    if str(parsed) != value.lower():
        raise ApValidationError('A valid identifier is required.')
    return str(parsed)

def text(value: object, *, maximum: int = 8192, blank: bool = True) -> str:
    if type(value) is not str or len(value.encode('utf-8')) > maximum or (not blank and not value.strip()):
        raise ApValidationError('Text is missing or exceeds the allowed size.')
    return value

def integer(value: object, *, nullable: bool = False, minimum: int = -MAX_SAFE_CENTS, maximum: int = MAX_SAFE_CENTS) -> int | None:
    if nullable and value is None:
        return None
    if type(value) is not int or not minimum <= value <= maximum:
        raise ApValidationError('A valid integer amount or count is required.')
    return value

def date_value(value: object) -> str:
    value = text(value, maximum=10)
    if value:
        try:
            if date.fromisoformat(value).isoformat() != value: raise ValueError
        except ValueError:
            raise ApValidationError('A valid calendar date is required.') from None
    return value

def allowed(value: object, keys: str, required: str = '') -> JsonObject:
    if type(value) is not dict or set(value) - set(keys.split()) or set(required.split()) - set(value):
        raise ApValidationError('Payload fields are missing or unsupported.')
    return dict(value)

def read_config(secrets: Mapping) -> ApConfig:
    try:
        cfg = secrets['ap']
        values = {key: text(cfg[key], maximum=4096, blank=False) for key in ('password','supabase_url','supabase_secret_key','workspace_id','bucket')}
    except (KeyError, TypeError, ApValidationError):
        raise ApValidationError('Shared AP storage is not configured.') from None
    parsed = urlparse(values['supabase_url'])
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        raise ApValidationError('A secure backend URL is required.')
    values['supabase_url'] = values['supabase_url'].rstrip('/')
    values['workspace_id'] = require_uuid(values['workspace_id'])
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,62}',values['bucket']):
        raise ApValidationError('A valid private bucket name is required.')
    return ApConfig(**values)

def normalize_initials(value: str) -> str:
    value = text(value,maximum=40).strip().upper()
    if not re.fullmatch('[A-Z]{1,10}',value):
        raise ApValidationError('Reviewer initials must contain one to ten letters.')
    return value

def validate_request(value: object) -> JsonObject:
    try:
        size = len(json.dumps(value,allow_nan=False,ensure_ascii=False).encode('utf-8'))
    except (ValueError, TypeError, RecursionError):
        raise ApValidationError('A valid JSON payload is required.') from None
    if size > MAX_ENVELOPE_BYTES:
        raise ApValidationError('Request exceeds the size limit.')
    out=allowed(value,'version request_id action payload','version request_id action payload')
    if type(out['version']) is not int or out['version'] != 1 or type(out['action']) is not str or out['action'] not in ACTIONS or type(out['payload']) is not dict:
        raise ApValidationError('Unsupported request.')
    out['request_id']=require_uuid(out['request_id'])
    def reject_secrets(node):
        if isinstance(node,dict):
            for key,child in node.items():
                if key in ('password','supabase_secret_key','workspace_id','originalPath','sql','url','bucket'):
                    raise ApValidationError('Client-supplied credentials or storage targets are prohibited.')
                reject_secrets(child)
        elif isinstance(node,list):
            for child in node: reject_secrets(child)
    reject_secrets(out['payload'])
    return out

def validate_resolution(value: object) -> JsonObject:
    out=allowed(value,'note decision at','note')
    text(out['note'],maximum=16384)
    if 'decision' in out and (type(out['decision']) is not str or out['decision'] not in DECISIONS): raise ApValidationError('Choose a valid review decision.')
    if 'at' in out: text(out['at'],maximum=40)
    return out

def validate_statement(value: object) -> JsonObject:
    keys='id vendor filename layout statementDate declaredTotal openingBalance confirmed demo pageCount ocr notes assignee createdAt fileSize fileModified rawText rows warnings'
    out=allowed(value,keys,'id vendor filename rows warnings confirmed pageCount')
    out['id']=require_uuid(out['id'])
    for key in ('vendor','filename'):
        text(out[key],maximum=1024,blank=False)
    for key in ('layout','notes','assignee','createdAt'):
        if key in out: text(out[key],maximum=16384 if key=='notes' else 256)
    for key in ('statementDate',):
        if key in out: date_value(out[key])
    for key in ('declaredTotal','openingBalance'):
        if key in out: integer(out[key],nullable=True)
    for key in ('confirmed','demo','ocr'):
        if key in out and type(out[key]) is not bool: raise ApValidationError('A valid boolean flag is required.')
    if out.get('demo'): raise ApValidationError('Sample statements cannot be saved as company records.')
    integer(out['pageCount'],minimum=1,maximum=1000)
    for key in ('fileSize','fileModified'):
        if key in out: integer(out[key],minimum=0)
    if 'rawText' in out: text(out['rawText'],maximum=512*1024)
    if type(out['warnings']) is not list or len(out['warnings']) > 10000: raise ApValidationError('Invalid extraction warnings.')
    for warning in out['warnings']: text(warning,maximum=4096)
    if type(out['rows']) is not list or len(out['rows']) > 10000: raise ApValidationError('Statement row limit exceeded.')
    rows=[]
    seen=set()
    for value in out['rows']:
        row=allowed(value,'id invoiceNumber type date dueDate amount balance page source confidence','id invoiceNumber type amount page confidence')
        row['id']=require_uuid(row['id'])
        if row['id'] in seen: raise ApValidationError('Duplicate statement row identifiers.')
        seen.add(row['id'])
        text(row['invoiceNumber'],maximum=256)
        if row['type'] not in ('invoice','credit','payment','opening'): raise ApValidationError('Invalid transaction type.')
        integer(row['amount'])
        if 'balance' in row: integer(row['balance'],nullable=True)
        integer(row['page'],minimum=1,maximum=out['pageCount'])
        if type(row['confidence']) not in (int,float) or not math.isfinite(row['confidence']) or not 0 <= row['confidence'] <= 100:
            raise ApValidationError('A valid confidence score is required.')
        for key in ('date','dueDate'):
            if key in row: date_value(row[key])
        if 'source' in row: text(row['source'],maximum=16384)
        rows.append(row)
    out['rows']=rows
    return out

RECORD_FIELDS='id vendor invoiceNumber amount kind currency clearedPaymentAmount scheduledAmount creditAmount paymentDate status comparisonScope sourceRows sourceIssues invoiceDate reportedPaidAmount reportedAmountDue reportedCreditAmount reportedPaidOn reportedFullPaymentDate'
def validate_record(value: object) -> JsonObject:
    out=allowed(value,RECORD_FIELDS,'vendor invoiceNumber amount')
    for key in ('vendor','invoiceNumber'): text(out[key],maximum=1024,blank=False)
    for key in ('amount','clearedPaymentAmount','scheduledAmount','creditAmount','reportedPaidAmount','reportedAmountDue','reportedCreditAmount'):
        if key in out: integer(out[key],nullable=key!='amount' or bool(out.get('sourceIssues')))
    for key in ('paymentDate','invoiceDate','reportedFullPaymentDate'):
        if key in out: date_value(out[key])
    for key in ('id','kind','currency','status','comparisonScope','sourceRows','sourceIssues','reportedPaidOn'):
        if key in out: text(out[key],maximum=16384 if key in ('sourceRows','sourceIssues') else 1024)
    if out.get('kind','invoice') not in ('invoice','credit'): raise ApValidationError('Invalid BILL record kind.')
    if out.get('comparisonScope') not in (None,'invoice-only'): raise ApValidationError('Invalid comparison scope.')
    return out

def validate_provider(value: object) -> JsonObject:
    keys='loaded simulated label refreshedAt asOf sourceFormat importedRowCount collapsedRowCount excludedRowCount sourceIssueCount importNotes records'
    out=allowed(value,keys,'loaded simulated records')
    if out['loaded'] is not True or out['simulated'] is not False: raise ApValidationError('Only imported company records can be stored.')
    if type(out['records']) is not list or not 1 <= len(out['records']) <= MAX_RECORDS: raise ApValidationError('Import record count is invalid.')
    out['records']=[validate_record(row) for row in out['records']]
    for key in ('label','refreshedAt','sourceFormat','importNotes'):
        if key in out: text(out[key],maximum=512*1024 if key=='importNotes' else 1024)
    if 'asOf' in out: date_value(out['asOf'])
    for key in ('importedRowCount','collapsedRowCount','excludedRowCount','sourceIssueCount'):
        if key in out: integer(out[key],minimum=0)
    return out
