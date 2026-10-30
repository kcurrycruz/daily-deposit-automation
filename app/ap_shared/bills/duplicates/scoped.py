"""One authoritative scope-pin constructor shared by scan metadata and readers."""
from .contracts import DuplicateError,validate_pin
from ..working.contracts import validate_working_manifest


def working_pin(home,source,manifest):
    manifest=validate_working_manifest(manifest)
    if (home.get('working_protection_epoch')!=home.get('bill_protection_epoch')
            or home['active_working_set_id']!=manifest['workingSetId'] or source['id']!=manifest['source']['importId']
            or source['file_hash']!=manifest['source']['sourceDigest'] or source['record_count']!=manifest['fullRecordCount']):
        raise DuplicateError('duplicate_conflict')
    return validate_pin(dict(importId=source['id'],importVersion=home['import_version'],sourceDigest=manifest['workingDigest'],
        storageFormat='working-v1',recordCount=manifest['activeCount'],workingSetId=manifest['workingSetId'],
        workingDigest=manifest['workingDigest'],workingVersion=home['working_set_version'],
        fullSourceDigest=source['file_hash'],fullRecordCount=source['record_count'],mappingDigest=manifest['mappingDigest']))
