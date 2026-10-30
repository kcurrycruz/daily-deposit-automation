"""Strict working-set identities and artifact contracts, separate from full imports."""
from ...models import allowed, integer, require_uuid
from ..contracts import canonical_hash, digest, MAX_RECORDS, MAX_INDEX_BYTES, MAX_ARCHIVE_BYTES
from .policy import validate_policy, REASONS

FORMAT = 'ap-bill-working-v1'
TRAINING_VERSION = 'vendor-history-v1'


def validate_source(value):
    source = allowed(value, 'importId sourceDigest recordCount', 'importId sourceDigest recordCount')
    require_uuid(source['importId']); digest(source['sourceDigest'])
    integer(source['recordCount'], minimum=1, maximum=MAX_RECORDS)
    return source


def working_digest(source: dict, policy: dict, protection_digest: str) -> str:
    return canonical_hash(dict(source=validate_source(source), policy=validate_policy(policy),
                               protectionDigest=digest(protection_digest), trainingVersion=TRAINING_VERSION))


def validate_working_manifest(value: dict) -> dict:
    fields = ('format workingSetId workingDigest source policy protectionDigest trainingVersion '
              'fullRecordCount activeCount archivedCount retainedReasonCounts vendorDigest indexArchive contextArchive')
    out = allowed(value, fields, fields)
    if out['format'] != FORMAT or out['trainingVersion'] != TRAINING_VERSION:
        raise ValueError('Unsupported active BILL artifact.')
    require_uuid(out['workingSetId']); digest(out['workingDigest']); digest(out['vendorDigest'])
    out['source'] = validate_source(out['source']); out['policy'] = validate_policy(out['policy'])
    if out['workingDigest'] != working_digest(out['source'], out['policy'], out['protectionDigest']):
        raise ValueError('Active BILL identity does not match its source and policy.')
    for name in ('fullRecordCount', 'activeCount', 'archivedCount'):
        integer(out[name], minimum=0, maximum=MAX_RECORDS)
    if (out['fullRecordCount'] != out['source']['recordCount']
            or out['activeCount'] + out['archivedCount'] != out['fullRecordCount']):
        raise ValueError('Active BILL coverage counts do not agree.')
    reasons = out['retainedReasonCounts']
    if type(reasons) is not dict or set(reasons) - set(REASONS):
        raise ValueError('Invalid active BILL retention reasons.')
    for count in reasons.values():
        integer(count, minimum=1, maximum=out['activeCount'])
    if sum(reasons.values()) < out['activeCount']:
        raise ValueError('Active BILL retention reasons do not cover the working set.')
    workspace = None
    for name in ('indexArchive', 'contextArchive'):
        fields = 'key hash bytes expandedHash expandedBytes'
        part = allowed(out[name], fields, fields)
        digest(part['hash']); digest(part['expandedHash'])
        integer(part['bytes'], minimum=1, maximum=MAX_ARCHIVE_BYTES)
        integer(part['expandedBytes'], minimum=1, maximum=MAX_INDEX_BYTES)
        key = part['key']
        if type(key) is not str:
            raise ValueError('Invalid active BILL artifact key.')
        parts = key.split('/')
        if (len(parts) != 5 or parts[1:3] != ['bill-working', 'v1']
                or parts[3] != out['workingDigest'] or parts[4] != part['hash'] + '.sqlite.gz'):
            raise ValueError('Active BILL artifact key does not match its identity.')
        require_uuid(parts[0])
        if workspace is not None and workspace != parts[0]:
            raise ValueError('Active BILL artifacts belong to different workspaces.')
        workspace = parts[0]; out[name] = part
    return out
