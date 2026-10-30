"""Authenticated preparation and atomic publication of shared active coverage."""
import atexit
import threading
import time
from uuid import UUID,uuid5
from ...models import allowed,integer,require_uuid
from ..contracts import SnapshotError,MAX_ARCHIVE_BYTES,canonical_hash
from .archive import WorkingCache
from .registry import WorkingRegistry
from .repository import WorkingRepository
from .protections import ProtectionRepository
from .policy import make_policy
from .contracts import validate_working_manifest,working_digest

_runtimes={}
_lock=threading.RLock()


def create_working_operations(base,bill_ops,config,clock,revalidate,duplicate_members_reader=None):
    repository=WorkingRepository(base)
    key=canonical_hash([config.supabase_url,config.workspace_id,config.bucket,config.supabase_secret_key])
    with _lock:
        if key not in _runtimes:
            from ..duplicates.source import SourcePreparationCache
            registry=WorkingRegistry(bill_ops,SourcePreparationCache(bill_ops.repository));cache=WorkingCache(repository)
            atexit.register(registry.close);atexit.register(cache.close);_runtimes[key]=(registry,cache)
        registry,cache=_runtimes[key]
        if duplicate_members_reader is None:
            from .protection_evidence import FrozenDuplicateEvidence
            from ..duplicates.repository import DuplicateRepository
            if not hasattr(registry,'saved_duplicate_evidence'):
                registry.saved_duplicate_evidence=FrozenDuplicateEvidence(DuplicateRepository(base),source_prepared=registry.source_prepared)
                atexit.register(registry.saved_duplicate_evidence.close)
            duplicate_members_reader=lambda review,auth:registry.saved_duplicate_evidence(review,auth,bill_ops)
    protections=ProtectionRepository(base,bill_ops._check,duplicate_members_reader)
    return WorkingOperations(repository,bill_ops,clock,protections,registry,cache)


class WorkingOperations:
    def __init__(self,repository,bill_operations,clock,protections,registry,cache):
        self.repository,self.bill_ops,self.clock=repository,bill_operations,clock
        self.protections,self.registry,self.cache=protections,registry,cache

    def _check(self,auth):self.bill_ops._check(auth)

    def _rpc(self,op,data,request,auth,step):
        self._check(auth)
        result=self.repository.rpc(op,{**data,'session_nonce':auth.session_nonce},str(uuid5(UUID(request),step)))
        self._check(auth);return result

    def _job(self,ident,auth):
        self._check(auth);job=self.repository.job(require_uuid(ident))
        if job['workspace_id']!=self.repository.config.workspace_id or job['session_nonce']!=auth.session_nonce:
            raise PermissionError('This BILL range update belongs to another access session.')
        return job

    def current(self,auth):
        self._check(auth);home=self.repository.home();ident=home['active_import_id']
        if not ident:return dict(importId=None,recordCount=0,metadata={},workingSet=None,importVersion=home['import_version'],workingVersion=home.get('working_set_version',0))
        source=self.repository.source(ident);working=None
        if home.get('active_working_set_id'):
            working=self.repository.working_set(home['active_working_set_id'])['manifest']
            if working['source']['importId']!=ident or working['source']['sourceDigest']!=source['file_hash']:
                raise SnapshotError('bill_conflict')
        self._check(auth)
        return dict(importId=ident,recordCount=source['record_count'],metadata=source['metadata'],storageFormat=source.get('storage_format','rows-v1'),
                    importVersion=home['import_version'],workingVersion=home.get('working_set_version',0),workingSet=working,
                    protectionsCurrent=not working or home.get('working_protection_epoch')==home.get('bill_protection_epoch'))

    def _prepared(self,job,auth):
        self._check(auth);manifest=self.repository.working_set(job['working_set_id'])['manifest']
        return dict(job_id=job['id'],state='prepared',generation=job['generation'],checkpoint=job['checkpoint'],policy=job['policy'],manifest=manifest)

    def _begin(self,data,request,auth):
        home=self.repository.home()
        if home.get('bill_working_schema_version')!=1:raise SnapshotError('bill_incomplete')
        ident=str(uuid5(UUID(auth.session_nonce),request))
        previous=self.repository.find_job(ident)
        if previous and (previous['session_nonce']!=auth.session_nonce or previous['source_import_id']!=data['source_import_id']
                or previous['policy']['mode']!=data['mode'] or previous['expected_import_version']!=data['expected_import_version']
                or previous['expected_working_version']!=data['expected_working_version']):
            raise SnapshotError('bill_conflict')
        if not previous and (home['import_version']!=data['expected_import_version'] or home['working_set_version']!=data['expected_working_version']):
            raise SnapshotError('bill_conflict')
        policy=previous['policy'] if previous else make_policy(data['mode'],self.clock())
        if data.get('refresh',False) and not previous:
            current=self.current(auth)
            if not current['workingSet'] or current['importId']!=data['source_import_id'] or current['workingSet']['policy']['mode']!=data['mode']:
                raise SnapshotError('bill_conflict')
            policy=current['workingSet']['policy']
        snapshot=dict(epoch=previous['protection_epoch'],digest=previous['protection_digest']) if previous else self.protections.snapshot(data['source_import_id'],auth)
        result=self._rpc('begin',dict(job_id=ident,source_import_id=data['source_import_id'],
            expected_import_version=data['expected_import_version'],expected_working_version=data['expected_working_version'],
            protection_epoch=snapshot['epoch'],protection_digest=snapshot['digest'],policy=policy,
            **({'upload_job_id':data['upload_job_id']} if data.get('upload_job_id') else {})),request,auth,'begin')
        job=self._job(ident,auth)
        try:
            self._rpc('reserve',dict(job_id=ident,generation=job['generation'],bucket=self.repository.config.bucket,
                requested_bytes=2*MAX_ARCHIVE_BYTES,budget_bytes=self.repository.config.bill_storage_budget_bytes),request,auth,'reserve')
        except Exception:
            self._rpc('cancel',dict(job_id=ident,generation=job['generation']),request,auth,'cancel-begin')
            raise
        return result

    def _step(self,job,data,request,auth):
        if job['generation']!=data['generation']:raise SnapshotError('bill_conflict')
        if job['state'] in ('prepared','activated'):return self._prepared(job,auth)
        if data.get('restart',False):
            result=self._rpc('restart',dict(job_id=job['id'],generation=job['generation'],expected_checkpoint=data['expected_checkpoint']),request,auth,'restart')
            self.registry.release(job['id']);return result
        deadline=time.monotonic()+5
        try:item=self.registry.entry(job['id'])
        except SnapshotError:
            if job['checkpoint']!=0:
                return dict(job_id=job['id'],state='restart_required',generation=job['generation'],checkpoint=job['checkpoint'],policy=job['policy'])
            snapshot=self.protections.snapshot(job['source_import_id'],auth)
            if snapshot['epoch']!=job['protection_epoch'] or snapshot['digest']!=job['protection_digest']:
                raise SnapshotError('bill_conflict')
            source=self.repository.source(job['source_import_id'])
            identity=working_digest(dict(importId=source['id'],sourceDigest=source['file_hash'],recordCount=source['record_count']),job['policy'],snapshot['digest'])
            reused=self.repository.lookup_digest(identity)
            self.registry.start(job,source,snapshot['protections'],reused['manifest'] if reused else None)
            item=self.registry.entry(job['id'])
        progress=self.registry.step(job,data['expected_checkpoint'],auth,self._check,deadline,bill_operations=self.bill_ops)
        self._rpc('checkpoint',dict(job_id=job['id'],generation=job['generation'],expected_checkpoint=data['expected_checkpoint'],
            next_checkpoint=progress['checkpoint'],state=progress['state'],progress={k:progress[k] for k in ('phase','recordsRead','activeCount')}),request,auth,'checkpoint')
        reply=dict(job_id=job['id'],generation=job['generation'],policy=job['policy'],**progress)
        if not progress['done']:return reply
        if item['manifest'] is None:
            built=item['builder'].artifacts();parts={}
            for name in ('index','context'):
                self._check(auth)
                parts[name+'Archive']={**built[name+'Archive'],**self.repository.put_artifact(job['id'],name,built[name+'ArchivePath'])}
            item['manifest']=validate_working_manifest(dict(**built['summary'],**parts,
                workingSetId=str(uuid5(UUID(self.repository.config.workspace_id),built['summary']['workingDigest']))))
        if not self.cache.prepare(item['manifest'],auth,self._check,deadline):return reply
        staged=self._rpc('stage',dict(job_id=job['id'],generation=job['generation'],expected_checkpoint=progress['checkpoint'],manifest=item['manifest']),request,auth,'stage')
        reply.update(state='prepared',manifest=staged['manifest'])
        # Durable prepared metadata handles a dropped final response; intermediate
        # replies remain in the registry until their checkpoint is acknowledged.
        self.registry.release(job['id'])
        return reply

    def handle(self,action,payload,request_id,authorization):
        require_uuid(request_id);self._check(authorization);auth=authorization
        if action in ('bill_candidates_page','bill_vendors_page','bill_archived_candidates_page'):
            from .queries import WorkingQueries
            return WorkingQueries(self).handle(action,payload,auth)
        if action=='bill_range_begin':
            data=allowed(payload,'source_import_id mode expected_import_version expected_working_version upload_job_id refresh',
                         'source_import_id mode expected_import_version expected_working_version')
            require_uuid(data['source_import_id'])
            if data.get('upload_job_id'):require_uuid(data['upload_job_id'])
            for key in ('expected_import_version','expected_working_version'):integer(data[key],minimum=0)
            if type(data.get('refresh',False)) is not bool:raise SnapshotError('bill_incomplete')
            result=self._begin(data,request_id,auth)
        elif action in ('bill_range_step','bill_range_activate','bill_range_cancel'):
            fields={'bill_range_step':'job_id generation expected_checkpoint restart','bill_range_activate':'job_id expected_import_version expected_working_version','bill_range_cancel':'job_id'}[action]
            required=fields if action=='bill_range_activate' else 'job_id generation expected_checkpoint' if action=='bill_range_step' else 'job_id'
            data=allowed(payload,fields,required);job=self._job(data['job_id'],auth)
            if action=='bill_range_step':
                require_uuid(data['generation']);integer(data['expected_checkpoint'],minimum=0)
                if type(data.get('restart',False)) is not bool:raise SnapshotError('bill_incomplete')
                result=self._step(job,data,request_id,auth)
            elif action=='bill_range_cancel':
                result=self._rpc('cancel',dict(job_id=job['id'],generation=job['generation']),request_id,auth,'cancel')
                self.registry.release(job['id'])
            else:
                for key in ('expected_import_version','expected_working_version'):integer(data[key],minimum=0)
                if job['state']!='activated' and (job['expected_import_version']!=data['expected_import_version'] or job['expected_working_version']!=data['expected_working_version']):
                    raise SnapshotError('bill_conflict')
                self._rpc('activate',dict(job_id=job['id'],generation=job['generation']),request_id,auth,'activate')
                result=self.current(auth)
                result['superseded']=result['importId']!=job['source_import_id'] or not result['workingSet'] or result['workingSet']['workingSetId']!=job['working_set_id']
        else:raise SnapshotError('bill_incomplete')
        self._check(auth);return result
