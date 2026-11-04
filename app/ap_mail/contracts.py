"""Strict, log-safe contracts for the fixed-workspace mail coordinator."""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import re
from urllib.parse import urlparse
from uuid import UUID, uuid5

from app.ap_shared.models import MAX_FILE_BYTES, RULE_VERSION, validate_statement

CODES = frozenset('invalid auth denied wrong_account label_missing not_found quota unavailable '
                  'limit unreadable conflict stale_source stale_claim paused exhausted storage '
                  'similar waiting_source not_configured withdrawn'.split())
IDENTITY_NAMESPACE = UUID('e1057c17-c04a-5a8f-b60c-521a8da51377')


class MailError(RuntimeError):
    def __init__(self, code):
        if code not in CODES: raise ValueError('Unknown mail error code.')
        self.code = code
        super().__init__(code)


def bounded_text(value, maximum=1024, *, blank=False):
    if (type(value) is not str or len(value.encode('utf-8')) > maximum or
            (not blank and not value.strip()) or any(ord(c) < 32 for c in value)):
        raise MailError('invalid')
    return value


def identifier(value):
    try:
        if type(value) is not str or str(UUID(value)) != value: raise ValueError
        return value
    except (ValueError, TypeError, AttributeError): raise MailError('invalid') from None


def natural(value, minimum=0, maximum=9007199254740991):
    if type(value) is not int or not minimum <= value <= maximum: raise MailError('invalid')
    return value


def digest(value):
    if type(value) is not str or not re.fullmatch('[a-f0-9]{64}', value): raise MailError('invalid')
    return value


def canonical(value):
    try: return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError, RecursionError): raise MailError('invalid') from None


def payload_digest(value): return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class MailConfig:
    supabase_url: str
    supabase_secret_key: str = field(repr=False)
    workspace_id: str
    bucket: str
    connection_id: str
    role: str
    max_file_bytes: int = MAX_FILE_BYTES
    storage_budget_bytes: int = 900000000

    def __post_init__(self):
        url = urlparse(bounded_text(self.supabase_url, 4096))
        if (url.scheme != 'https' or not url.hostname or url.username or url.password or
                url.query or url.fragment or url.path not in ('', '/')): raise MailError('invalid')
        bounded_text(self.supabase_secret_key, 8192)
        identifier(self.workspace_id); identifier(self.connection_id)
        if not re.fullmatch('[a-z0-9][a-z0-9-]{2,62}', self.bucket): raise MailError('invalid')
        if self.role not in ('checker', 'processor'): raise MailError('invalid')
        natural(self.max_file_bytes, 1, MAX_FILE_BYTES)
        natural(self.storage_budget_bytes, 1, 9000000000)


@dataclass(frozen=True)
class ReceiptKey:
    workspace_id: str
    account_id: str
    message_id: str
    part_path: str

    def __post_init__(self):
        identifier(self.workspace_id)
        bounded_text(self.account_id, 256); bounded_text(self.message_id, 256)
        if type(self.part_path) is not str or not re.fullmatch(r'0(?:\.[0-9]{1,3}){0,20}', self.part_path):
            raise MailError('invalid')


def receipt_id(key: ReceiptKey):
    return str(uuid5(IDENTITY_NAMESPACE, canonical([key.workspace_id, key.account_id, key.message_id, key.part_path])))


@dataclass(frozen=True)
class Claim:
    job_id: str
    receipt_id: str
    connection_generation: int
    dispatch_generation: int
    lease_generation: int
    slot_generation: int
    lease_until: str
    mode: str

    def __post_init__(self):
        identifier(self.job_id); identifier(self.receipt_id)
        for value in (self.connection_generation, self.dispatch_generation, self.lease_generation, self.slot_generation):
            natural(value, 1)
        try:
            if datetime.fromisoformat(self.lease_until).utcoffset() is None: raise ValueError
        except (TypeError, ValueError): raise MailError('invalid') from None
        if self.mode not in ('extract', 'recompare'): raise MailError('invalid')


@dataclass(frozen=True)
class SourcePin:
    import_id: str | None
    import_version: int
    source_digest: str | None
    working_set_id: str | None
    working_version: int
    protection_epoch: int
    working_digest: str | None
    mapping_digest: str
    mapping_versions: dict
    rule_version: str

    def __post_init__(self):
        for value in (self.import_version, self.working_version, self.protection_epoch): natural(value)
        if self.import_id is not None: identifier(self.import_id); digest(self.source_digest)
        elif self.source_digest is not None or self.working_set_id is not None: raise MailError('invalid')
        if self.working_set_id is not None: identifier(self.working_set_id); digest(self.working_digest)
        elif self.working_digest is not None: raise MailError('invalid')
        digest(self.mapping_digest)
        if type(self.mapping_versions) is not dict or len(self.mapping_versions) > 100000: raise MailError('invalid')
        for key, value in self.mapping_versions.items(): bounded_text(key); natural(value, 1)
        if self.rule_version != RULE_VERSION: raise MailError('invalid')


def normalize_extraction(doc, receipt, sha256):
    """Replace parser-generated IDs; never manufacture confirmation or review."""
    identifier(receipt); digest(sha256)
    result = deepcopy(doc)
    try:
        result['id'] = str(uuid5(UUID(receipt), 'statement:' + sha256))
        result['confirmed'] = False
        result['reviewMode'] = 'latest'
        if not result['rows']: raise MailError('unreadable')
        for index, row in enumerate(result['rows']):
            row['id'] = str(uuid5(UUID(result['id']), 'row:' + str(index)))
        return validate_statement(result)
    except MailError: raise
    except (ValueError, TypeError, KeyError): raise MailError('unreadable') from None
