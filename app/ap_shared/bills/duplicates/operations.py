"""Authorized, cooperative duplicate checks; never mutate the source BILL data."""
import atexit
from datetime import datetime
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from uuid import UUID, uuid5
from ...access import require_access
from ...models import allowed, integer, require_uuid
from .artifacts import DuplicateArtifactCache, DuplicateArtifactWriter
from .contracts import DuplicateError, RULE_VERSION, canonical_hash, validate_review_payload
from .projection import ReviewProjection
from .repository import DuplicateRepository
from .scan import DuplicateScan
from .source import DuplicateSource,SourcePreparationCache


class DuplicateScanRegistry:
    def __init__(self, root=None, monotonic=time.monotonic):
        self.root = tempfile.TemporaryDirectory(prefix='hwfc-duplicate-scans-', dir=root)
        self.clock, self.handles, self.lock = monotonic, {}, threading.RLock()

    def _expire(self):
        for key, handle in list(self.handles.items()):
            if self.clock()-handle['last'] >= 3600:
                self.release(key)

    def claim(self, scan, authorization):
        with self.lock:
            self._expire(); key=scan['id']
            if scan['workspace_id'] != authorization.workspace_id or scan['session_nonce'] != authorization.session_nonce:
                raise PermissionError('AP access is locked.')
            if key in self.handles:
                handle=self.handles[key]
                if handle['generation']!=scan['generation'] or handle['nonce']!=authorization.session_nonce:
                    raise DuplicateError('duplicate_restart')
                return
            if not scan.get('fresh') or scan['checkpoint'] != 0:
                raise DuplicateError('duplicate_restart')
            if len(self.handles)>=2 or any(h['workspace']==scan['workspace_id'] for h in self.handles.values()):
                raise DuplicateError('duplicate_unavailable')
            folder=tempfile.TemporaryDirectory(prefix='scan-',dir=self.root.name)
            db=sqlite3.connect(Path(folder.name)/'working.sqlite',check_same_thread=False)
            try:
                engine=DuplicateScan(db,scan['source_pin'],self.clock)
            except Exception:
                db.close(); folder.cleanup(); raise
            self.handles[key]=dict(folder=folder,db=db,engine=engine,pin=scan['source_pin'],workspace=scan['workspace_id'],
                nonce=authorization.session_nonce,generation=scan['generation'],checkpoint=0,last=self.clock(),
                previous=None,reply=None,phase='reading',writer=None,artifact=None)

    def release_obsolete(self, workspace_id, pin):
        # The caller has verified the current shared pin. Never evict a handle
        # for that same source/version merely because another session requests it.
        with self.lock:
            for key,h in list(self.handles.items()):
                if h['workspace']==workspace_id and h['pin']!=pin:self.release(key)

    def step(self, scan, authorization, authorize,deadline=float('inf')):
        with self.lock:
            authorize(authorization); self._expire()
            self.claim(scan,authorization); h=self.handles[scan['id']]
            expected=scan['checkpoint']; h['last']=self.clock()
            if expected==h['previous']:
                return h['reply']
            if expected!=h['checkpoint']:
                raise DuplicateError('duplicate_restart')
            deadline=min(self.clock()+5,deadline); engine=h['engine']
            if h['phase']=='reading':
                if 'input' not in h and self.clock()<deadline:
                    if not scan['source_reader'].prepare(h['pin'],authorization,deadline=deadline):
                        page=None
                    else:page=scan['source_reader'].read_page(h['pin'],engine.read-1,5000,authorization)
                    if page is not None:h['input']=page['records']
                if 'input' in h:
                    consumed=engine.ingest(h['input'],deadline=deadline)
                    h['input']=h['input'][consumed:]
                    if not h['input']:del h['input']
                if engine.read==h['pin']['recordCount']:
                    engine.finish_input(); h['phase']='candidates'
            elif h['phase']=='candidates':
                result=engine.step(deadline)
                if result['done']:
                    engine.finish(); h['phase']='packaging'
                    h['writer']=DuplicateArtifactWriter(Path(h['folder'].name)/'working.sqlite',Path(h['folder'].name)/'result.gz')
            else:
                packed=h['writer'].step(deadline=deadline)
                if packed['done']:
                    h['artifact']=packed['artifact']
            authorize(authorization)
            reply=dict(phase=h['phase'],progress=dict(recordsRead=engine.read,probes=engine.probes),
                       checkpoint=expected+1,artifact=h['artifact'],path=Path(h['folder'].name)/'result.gz')
            h.update(previous=expected,checkpoint=expected+1,reply=reply,last=self.clock())
            return reply

    def release(self, scan_id):
        with self.lock:
            handle=self.handles.pop(scan_id,None)
            if handle:
                if handle['writer']: handle['writer'].close()
                handle['db'].close(); handle['folder'].cleanup()

    def close(self):
        with self.lock:
            for key in list(self.handles): self.release(key)
            self.root.cleanup()


_lock=threading.RLock()
_registry=None
_runtimes={}


def create_duplicate_operations(base_repository, bill_operations, config, clock, revalidate):
    global _registry
    repository=DuplicateRepository(base_repository); source=DuplicateSource(base_repository,bill_operations)
    key=canonical_hash([config.supabase_url,config.workspace_id,config.bucket,config.supabase_secret_key])
    with _lock:
        if _registry is None:
            _registry=DuplicateScanRegistry(); atexit.register(_registry.close)
        if key not in _runtimes:
            cache=DuplicateArtifactCache(repository)
            projection=ReviewProjection(repository,cache,source,time.monotonic)
            atexit.register(cache.close); atexit.register(projection.close)
            source_cache=SourcePreparationCache(bill_operations.repository);atexit.register(source_cache.close)
            _runtimes[key]=cache,projection,source_cache
        cache,projection,source_cache=_runtimes[key]
        source.prepared=source_cache
    return DuplicateOperations(repository,source,_registry,cache,projection,config,clock,revalidate)


class DuplicateOperations:
    def __init__(self, repository, source, registry, cache, projection, config, clock, revalidate):
        self.repository,self.source,self.registry,self.cache,self.projection=repository,source,registry,cache,projection
        self.config,self.clock,self.revalidate=config,clock,revalidate
        self.deadline=float('inf')

    def _check(self, auth):
        current=self.revalidate()
        if current!=auth: raise PermissionError('AP access is locked.')
        require_access({'_ap_authorization':current,'_ap_session_nonce':current.session_nonce},self.config,self.clock())

    def _rpc(self, operation, data, request_id, auth, step):
        self._check(auth)
        return self.repository.rpc(operation,data,str(uuid5(UUID(request_id),step)))

    def _scan(self, scan_id, auth):
        self._check(auth); scan=self.repository.scan(require_uuid(scan_id)); pin=self.repository.current()
        if (pin is None or scan['workspace_id']!=self.config.workspace_id or scan['import_id']!=pin['importId'] or
            scan['source_digest']!=pin['sourceDigest'] or scan['rule_version']!=RULE_VERSION):
            raise DuplicateError('duplicate_conflict')
        scan['source_pin']=pin; scan['source_reader']=self.source
        return scan

    def _progress(self, scan, auth):
        self._check(auth); current=self._scan(scan['id'],auth); prepared=dict(ready=False,reviewRevision=None,counts=None)
        if current['state']=='ready' and time.monotonic()<self.deadline:
            deadline=min(self.deadline,time.monotonic()+5)
            if self.source.prepare(current['source_pin'],auth,deadline) and self.cache.prepare(
                self.config.workspace_id,current['id'],current['manifest'],auth,self._check,deadline):
                prepared=self.projection.prepare(current,auth,deadline)
        self._check(auth)
        expired=self._lease_expired(current)
        restart=current['state']=='superseded' or current['state']=='running' and (
            current['expected_import_version']!=current['source_pin']['importVersion'] or expired)
        return dict(scanId=current['id'],importId=current['import_id'],importVersion=current['source_pin']['importVersion'],
            ruleVersion=RULE_VERSION,state='restart_required' if restart else current['state'],phase=current['phase'],generation=current['generation'],
            checkpoint=current['checkpoint'],recordsRead=current['progress']['recordsRead'],probes=current['progress']['probes'],
            totalRecords=current['source_pin']['recordCount'],projectionReady=prepared['ready'],
            findingCount=current['manifest']['findingCount'] if current['state']=='ready' else None,
            counts=prepared['counts'],reviewRevision=prepared['reviewRevision'],completedAt=current.get('completed_at'),
            updatedAt=current.get('updated_at'),leaseExpiresAt=current.get('lease_until'),serverNow=self.clock().isoformat(),
            canStep=current.get('session_nonce')==auth.session_nonce or expired,error='duplicate_restart' if restart else current.get('error_code'),
            errorCode='duplicate_restart' if restart else current.get('error_code'))

    def _lease_expired(self, scan):
        try:
            return datetime.fromisoformat(scan['lease_until'].replace('Z','+00:00'))<=self.clock()
        except (KeyError,ValueError,TypeError):
            return False

    def _fail(self, scan, code, request_id, auth):
        try:
            return self._rpc('fail',dict(scan_id=scan['id'],session_nonce=auth.session_nonce,generation=scan['generation'],
                expected_checkpoint=scan['checkpoint'],error_code=code),request_id,auth,'fail:'+code)
        finally:
            self.registry.release(scan['id'])

    def _step(self, scan, data, request_id, auth):
        if scan['state']=='ready': return self._progress(scan,auth)
        if scan.get('session_nonce') not in (None,auth.session_nonce) and not (data['restart'] and self._lease_expired(scan)):
            raise PermissionError('This duplicate check belongs to another access session.')
        if data['generation']!=scan['generation']:
            raise DuplicateError('duplicate_conflict')
        if data['restart']:
            self.registry.release(scan['id'])
            scan=self._rpc('restart',dict(scan_id=scan['id'],session_nonce=auth.session_nonce,expected_generation=scan['generation']),request_id,auth,'restart')
            scan=self._scan(scan['id'],auth); scan['fresh']=True; self.registry.claim(scan,auth)
            return self._progress(scan,auth)
        if scan['state'] in ('failed','restart_required'):
            return self._progress(scan,auth)
        expected=data['expected_checkpoint']
        if scan['checkpoint']==expected+1:
            return self._progress(scan,auth)
        if scan['checkpoint']!=expected:
            raise DuplicateError('duplicate_conflict')
        try:
            result=self.registry.step(scan,auth,self._check,self.deadline)
            self.source._check(scan['source_pin'],auth)
            row=self._rpc('checkpoint',dict(scan_id=scan['id'],session_nonce=auth.session_nonce,generation=scan['generation'],
                expected_checkpoint=expected,next_checkpoint=result['checkpoint'],phase=result['phase'],progress=result['progress']),
                request_id,auth,'checkpoint')
            if result['artifact']:
                self._rpc('reserve',dict(scan_id=scan['id'],session_nonce=auth.session_nonce,bucket=self.config.bucket,
                    requested_bytes=64*1024*1024,budget_bytes=self.config.bill_storage_budget_bytes),request_id,auth,'reserve')
                self._check(auth)
                manifest=self.repository.put_result({**row,'result_info':result['artifact']},result['path'],request_id)
                self.source._check(scan['source_pin'],auth)
                self._rpc('publish',dict(scan_id=scan['id'],session_nonce=auth.session_nonce,generation=scan['generation'],
                    expected_checkpoint=row['checkpoint'],expected_import_version=scan['source_pin']['importVersion'],manifest=manifest),request_id,auth,'publish')
                self.registry.release(scan['id'])
            return self._progress(scan,auth)
        except DuplicateError as error:
            if error.code in ('duplicate_restart','duplicate_limit','duplicate_quota','duplicate_invalid_source'):
                latest=self._scan(scan['id'],auth)
                self._fail(latest,error.code,request_id,auth)
                return self._progress(scan,auth)
            raise

    def handle(self, action, payload, request_id, authorization):
        require_uuid(request_id); self._check(authorization)
        # A shared projection is rebound only while holding its lock. A fresh
        # request's session validator must govern every source/cache read.
        with self.projection.lock:
            self.deadline=time.monotonic()+5;self.projection.deadline=self.deadline
            self.projection.source=self.source
            try:result=self._handle(action,payload,request_id,authorization)
            except sqlite3.OperationalError as error:
                if 'interrupted' in str(error):raise DuplicateError('duplicate_unavailable') from None
                raise
            self._check(authorization)
            return result

    def _handle(self, action, payload, request_id, auth):
        if action=='duplicate_ensure':
            data=allowed(payload,'import_id expected_import_version','import_id expected_import_version')
            require_uuid(data['import_id']); integer(data['expected_import_version'],minimum=0)
            pin=self.repository.current()
            if pin is None: return dict(state='no_source',counts=None,projectionReady=False)
            if pin['importId']!=data['import_id'] or pin['importVersion']!=data['expected_import_version']:
                raise DuplicateError('duplicate_conflict')
            self.registry.release_obsolete(self.config.workspace_id,pin)
            sid=str(uuid5(UUID(self.config.workspace_id),pin['importId']+':'+RULE_VERSION))
            scan=self._rpc('ensure',dict(scan_id=sid,**data,source_digest=pin['sourceDigest'],rule_version=RULE_VERSION),request_id,auth,'ensure')
            if scan['state']=='pending':
                scan=self._rpc('claim',dict(scan_id=sid,session_nonce=auth.session_nonce),request_id,auth,'claim')
                scan=self._scan(sid,auth); scan['fresh']=True
                try: self.registry.claim(scan,auth)
                except DuplicateError as error:
                    self._fail(scan,error.code,request_id,auth)
            return self._progress(scan,auth)
        if action=='duplicate_review_save':
            data=validate_review_payload(payload); scan=self._scan(data['scan_id'],auth)
            if data['import_id']!=scan['import_id'] or data['expected_import_version']!=scan['source_pin']['importVersion'] or scan['state']!='ready':
                raise DuplicateError('duplicate_conflict')
            with self.cache.acquire(self.config.workspace_id,scan['id'],scan['manifest'],auth,self._check,prepared_only=True) as artifact:
                found=artifact.execute('select key from findings where key=?',(data['finding_key'],)).fetchone()
            if found is None: raise DuplicateError('duplicate_conflict')
            self.source._check(scan['source_pin'],auth)
            result=self._rpc('review',{**data,'verified_key':found[0]},request_id,auth,'review')
            self.projection.invalidate(self.config.workspace_id)
            return result
        fields={
            'duplicate_status':'scan_id',
            'duplicate_step':'scan_id generation expected_checkpoint restart',
            'duplicate_findings_page':'scan_id filters cursor limit',
            'duplicate_members_page':'scan_id finding_key cursor limit',
        }
        if action not in fields: raise DuplicateError('duplicate_invalid_source')
        keys=fields[action]; data=allowed(payload,keys,keys); scan=self._scan(data['scan_id'],auth)
        if action=='duplicate_status': return self._progress(scan,auth)
        if action=='duplicate_step':
            require_uuid(data['generation']); integer(data['expected_checkpoint'],minimum=0)
            if type(data['restart']) is not bool: raise DuplicateError('duplicate_invalid_source')
            return self._step(scan,data,request_id,auth)
        if scan['state']!='ready': raise DuplicateError('duplicate_conflict')
        if action=='duplicate_findings_page':
            return self.projection.findings_page(scan,data['filters'],data['cursor'],data['limit'],auth)
        return self.projection.members_page(scan,data['finding_key'],data['cursor'],data['limit'],auth)
