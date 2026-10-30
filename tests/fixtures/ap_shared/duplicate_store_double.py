"""Only the external SQL boundary is doubled; rules, source, artifacts and projections remain real."""
from copy import deepcopy
from datetime import datetime, timedelta
from uuid import uuid4
from test_ap_shared_access import NOW
from app.ap_shared.bills.duplicates.repository import DuplicateRepository
from app.ap_shared.bills.duplicates.contracts import DuplicateError, RULE_VERSION, rule_for_pin, canonical_hash


class DuplicateStoreDouble(DuplicateRepository):
    def __init__(self, base, bills):
        super().__init__(base); self.bills=bills
        self.scans={}; self.requests={}; self.saved={}; self.events=[]; self.revision=0
        self.fail_publish=False; self.calls=[]
    def current(self):
        if self.bills.active_id is None: return None
        s=self.bills.source(self.bills.active_id)
        return dict(importId=s['id'],importVersion=self.bills.version,sourceDigest=s['file_hash'],
                    storageFormat=s['storage_format'],recordCount=s['record_count'])
    def scan(self, scan_id):
        if scan_id not in self.scans: raise DuplicateError('duplicate_conflict')
        return deepcopy(self.scans[scan_id])
    def review_revision(self): return self.revision
    def reviews_page(self, after_key=None, limit=500):
        rows=[deepcopy(self.saved[k]) for k in sorted(self.saved) if after_key is None or k>after_key]
        return dict(reviews=rows[:limit],nextCursor=rows[limit-1]['key'] if len(rows)>limit else None)
    def rpc(self, operation, data, request_id):
        signature=canonical_hash([operation,data])
        if request_id in self.requests:
            prior,result=self.requests[request_id]
            if prior!=signature: raise DuplicateError('duplicate_conflict')
            return deepcopy(result)
        self.calls.append(operation); pin=self.current(); sid=data['scan_id']
        if operation=='ensure':
            if data['import_id']!=pin['importId'] or data['expected_import_version']!=pin['importVersion']:
                raise DuplicateError('duplicate_conflict')
            for old in self.scans.values():
                if old['import_id']!=pin['importId'] and old['state'] in ('pending','running','failed','restart_required'):
                    old.update(state='superseded',lease_until=NOW.isoformat())
            if sid not in self.scans:
                self.scans[sid]=dict(id=sid,workspace_id=self.config.workspace_id,import_id=pin['importId'],
                    source_digest=pin['sourceDigest'],rule_version=rule_for_pin(pin),expected_import_version=pin['importVersion'],
                    generation=str(uuid4()),checkpoint=0,state='pending',phase='reading',session_nonce=None,
                    progress=dict(recordsRead=0,probes=0),manifest=None,error_code=None,completed_at=None,lease_until=NOW.isoformat())
            result=self.scan(sid)
        else:
            job=self.scans[sid]
            if job['import_id']!=pin['importId']: raise DuplicateError('duplicate_conflict')
            if operation in ('claim','restart'):
                if job['session_nonce'] not in (None,data['session_nonce']) and datetime.fromisoformat(job['lease_until'].replace('Z','+00:00'))>NOW:
                    raise DuplicateError('duplicate_conflict')
                job.update(state='running',session_nonce=data['session_nonce'],lease_until=(NOW+timedelta(hours=1)).isoformat())
                if operation=='restart':
                    job.update(generation=str(uuid4()),checkpoint=0,phase='reading',progress=dict(recordsRead=0,probes=0))
            elif operation=='reserve':
                result=dict(used_bytes=0,reserved_bytes=data['requested_bytes'],warning=False)
            elif operation=='review':
                old=self.saved.get(data['finding_key'])
                if data['expected_review_version']!=(old['version'] if old else 0) or data['verified_key']!=data['finding_key']:
                    raise DuplicateError('duplicate_conflict')
                self.revision+=1
                review=dict(key=data['finding_key'],decision=data['decision'],initials=data['initials'],note=data['note'],
                            version=1 if old is None else old['version']+1,at='2026-10-22T12:00:00Z',reviewedImportId=pin['importId'])
                self.saved[review['key']]=review; self.events.append(review)
                result=dict(review=review,reviewRevision=self.revision)
            else:
                if job['session_nonce']!=data['session_nonce'] or job['generation']!=data['generation'] or job['checkpoint']!=data['expected_checkpoint']:
                    raise DuplicateError('duplicate_conflict')
                if operation=='checkpoint': job.update(checkpoint=data['next_checkpoint'],phase=data['phase'],progress=data['progress'])
                elif operation=='publish':
                    if self.fail_publish: raise DuplicateError()
                    job.update(state='ready',phase='complete',manifest=data['manifest'],completed_at='2026-10-22T12:00:00Z')
                elif operation=='fail':
                    job.update(state='restart_required' if data['error_code']=='duplicate_restart' else 'failed',error_code=data['error_code'])
                else: raise AssertionError(operation)
            if operation not in ('reserve','review'): result=deepcopy(job)
        self.requests[request_id]=(signature,deepcopy(result))
        return result
