from contextlib import contextmanager
import copy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import tempfile
import time
import unittest
from uuid import uuid4
from types import SimpleNamespace
from test_ap_shared_access import CONFIG
from test_ap_shared_service import fixture
from test_ap_bill_working_policy import bill, I
from test_ap_bill_working_builds import source_db
from app.ap_shared.bills.working.protections import ProtectionSet
from app.ap_shared.bills.contracts import SnapshotError

try:
    from app.ap_shared.bills.working.operations import WorkingOperations
    from app.ap_shared.bills.working.registry import WorkingRegistry
except ImportError:
    WorkingOperations = WorkingRegistry = None


class WorkingStore:
    """Metadata/storage boundary; real preparation/cache/policy run in tests."""
    def __init__(self,rows):
        self.config=CONFIG;self.rows=rows;self.jobs={};self.sets={};self.files={};self.requests={};self.quota_fail=False
        self._home=dict(bill_working_schema_version=1,active_import_id=I,import_version=1,
                        active_working_set_id=None,working_set_version=0,bill_protection_epoch=0,working_protection_epoch=None)
    def home(self):return copy.deepcopy(self._home)
    def source(self,ident):return dict(id=ident,file_hash='a'*64,record_count=len(self.rows),state='ready',metadata={'label':'synthetic.csv'},storage_format='snapshot-v2')
    def job(self,ident):return copy.deepcopy(self.jobs[ident])
    def find_job(self,ident):return copy.deepcopy(self.jobs.get(ident))
    def working_set(self,ident):return copy.deepcopy(self.sets[ident])
    def lookup_digest(self,identity):return next((copy.deepcopy(v) for v in self.sets.values() if v['manifest']['workingDigest']==identity),None)
    def put_artifact(self,job,name,path):
        from app.ap_shared.bills.working.contracts import working_digest
        j=self.job(job);identity=working_digest(dict(importId=I,sourceDigest='a'*64,recordCount=len(self.rows)),j['policy'],j['protection_digest'])
        raw=Path(path).read_bytes();sha=hashlib.sha256(raw).hexdigest()
        key=f'{CONFIG.workspace_id}/bill-working/v1/{identity}/{sha}.sqlite.gz';self.files[key]=raw
        return dict(key=key,hash=sha,bytes=len(raw))
    def read_artifact(self,manifest,name,target):Path(target).write_bytes(self.files[manifest[name+'Archive']['key']])
    def rpc(self,op,data,request):
        if op=='begin':self.last_begin_data=copy.deepcopy(data)
        if request in self.requests:return copy.deepcopy(self.requests[request])
        home=self._home
        if op=='begin':
            ident=data['job_id'];job={**data,'id':ident,'workspace_id':CONFIG.workspace_id,'generation':str(uuid4()),'checkpoint':0,'state':'building','working_set_id':None}
            self.jobs[ident]=job
            result=dict(job_id=ident,generation=job['generation'],checkpoint=0,state='building',policy=job['policy'])
        else:
            job=self.jobs[data['job_id']]
            if op=='cancel':job['state']='cancelled';result={'cancelled':True}
            elif op=='reserve':
                if self.quota_fail:raise SnapshotError('bill_quota')
                result={'reserved_bytes':data['requested_bytes']}
            elif op=='checkpoint':
                job.update(checkpoint=data['next_checkpoint'],state=data['state']);result=dict(checkpoint=job['checkpoint'],state=job['state'])
            elif op=='restart':
                job.update(generation=str(uuid4()),checkpoint=0,state='building',working_set_id=None)
                result=dict(job_id=job['id'],generation=job['generation'],checkpoint=0,state='building',policy=job['policy'])
            elif op=='stage':
                mf=copy.deepcopy(data['manifest']);self.sets[mf['workingSetId']]=dict(id=mf['workingSetId'],manifest=mf)
                job.update(state='prepared',working_set_id=mf['workingSetId']);result=dict(working_set_id=mf['workingSetId'],manifest=mf)
            elif op=='activate':
                if home['bill_protection_epoch']!=job['protection_epoch']:raise SnapshotError('bill_conflict')
                if home['active_working_set_id']!=job['working_set_id']:home['working_set_version']+=1
                home.update(active_import_id=job['source_import_id'],active_working_set_id=job['working_set_id'],working_protection_epoch=job['protection_epoch'])
                job['state']='activated';result=dict(working_set_id=job['working_set_id'])
            else:raise AssertionError(op)
        self.requests[request]=copy.deepcopy(result);return result


class WorkingOperationsTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(WorkingOperations,'Authenticated range orchestration is not implemented')
        self.service,_,self.auth,self.session,_=fixture()
        self.rows=[bill(invoiceNumber='OLD'),bill(invoiceNumber='RECENT',invoiceDate='2026-10-01')]
        self.db=source_db(self.rows);self.addCleanup(self.db.close);self.source_reads=0
        self.repo=WorkingStore(self.rows);self.now=[datetime(2026,10,30,16,tzinfo=timezone.utc)]
        self.protected=ProtectionSet()
        class BillOps:
            @contextmanager
            def _index(inner,ident,auth):
                self.source_reads+=1
                yield SimpleNamespace(db=self.db),self.repo.source(ident)
            def _check(inner,auth):self.service._check(auth)
        self.bill_ops=BillOps()
        class Protections:
            def snapshot(inner,ident,auth):return dict(epoch=self.repo._home['bill_protection_epoch'],digest=self.protected.digest(),protections=self.protected)
        self.registry=WorkingRegistry(self.bill_ops);self.addCleanup(self.registry.close)
        from app.ap_shared.bills.working.archive import WorkingCache
        self.cache=WorkingCache(self.repo);self.addCleanup(self.cache.close)
        self.ops=WorkingOperations(self.repo,self.bill_ops,lambda:self.now[0],Protections(),self.registry,self.cache)
    def call(self,action,payload,request=None):return self.ops.handle(action,payload,request or str(uuid4()),self.auth)
    def begin(self,**changes):return self.call('bill_range_begin',dict(source_import_id=I,mode='last_12_months',expected_import_version=self.repo._home['import_version'],expected_working_version=self.repo._home['working_set_version'],**changes))
    def prepare(self,job):
        p=job
        for _ in range(1000):
            if p['state']=='prepared':return p
            p=self.call('bill_range_step',dict(job_id=job['job_id'],generation=p['generation'],expected_checkpoint=p['checkpoint']))
        self.fail('Range did not prepare')
    def activate(self,job):return self.call('bill_range_activate',dict(job_id=job['job_id'],expected_import_version=self.repo._home['import_version'],expected_working_version=self.repo._home['working_set_version']))

    def test_prepare_keeps_full_source_current_until_explicit_atomic_activation(self):
        job=self.begin();p=self.prepare(job)
        self.assertEqual(p['manifest']['activeCount'],1)
        self.assertIsNone(self.repo._home['active_working_set_id'])
        result=self.activate(job)
        self.assertEqual(result['workingSet']['activeCount'],1)
        self.assertEqual(result['recordCount'],2)
        self.assertEqual(result['importId'],I)

    def test_range_changes_same_file_and_frozen_date_survives_restart(self):
        job=self.begin();self.now[0]=datetime(2026,10,31,16,tzinfo=timezone.utc)
        # Simulate loss of process-local derived work without changing durable job.
        self.registry.release(job['job_id'])
        first=self.call('bill_range_step',dict(job_id=job['job_id'],generation=job['generation'],expected_checkpoint=0,restart=True))
        self.assertEqual(first['policy']['asOfDate'],'2026-10-30')
        self.prepare(first);self.activate(first)
        all_job=self.call('bill_range_begin',dict(source_import_id=I,mode='all',expected_import_version=1,expected_working_version=1))
        self.prepare(all_job);result=self.activate(all_job)
        self.assertEqual(result['workingSet']['activeCount'],2)
        self.assertEqual(result['workingSet']['policy']['mode'],'all')

    def test_quota_or_cancellation_does_not_replace_acknowledged_source(self):
        self.repo.quota_fail=True
        with self.assertRaises(ValueError):self.begin()
        self.assertIsNone(self.repo._home['active_working_set_id'])
        self.assertTrue(all(j['state']=='cancelled' for j in self.repo.jobs.values()))
        self.repo.quota_fail=False;job=self.begin()
        self.call('bill_range_cancel',{'job_id':job['job_id']})
        self.assertIsNone(self.repo._home['active_working_set_id'])

    def test_stale_protections_and_malformed_client_policy_fail_closed(self):
        with self.assertRaises(ValueError):self.begin(cutoffDate='2010-01-01')
        job=self.begin();self.prepare(job);self.repo._home['bill_protection_epoch']+=1
        with self.assertRaises(ValueError):self.activate(job)
        self.assertIsNone(self.repo._home['active_working_set_id'])

    def test_authorization_is_checked_again_before_returning_values(self):
        job=self.begin();self.session.pop('_ap_authorization')
        with self.assertRaises(PermissionError):self.prepare(job)

    def test_semantic_same_scope_reuses_verified_index_without_full_source_read(self):
        job=self.begin();self.prepare(job);first=self.activate(job);reads=self.source_reads
        again=self.begin();self.prepare(again);second=self.activate(again)
        self.assertEqual(first['workingSet']['workingDigest'],second['workingSet']['workingDigest'])
        self.assertEqual(self.source_reads,reads)

    def test_protection_refresh_keeps_acknowledged_cutoff_and_retains_new_followup(self):
        job=self.begin();self.prepare(job);first=self.activate(job)
        self.now[0]=datetime(2026,11,1,16,tzinfo=timezone.utc)
        self.protected.add_duplicate({'decision':'unreviewed','memberCount':2},
            [dict(ordinal=0,bill=self.rows[0]),dict(ordinal=1,bill=self.rows[1])])
        self.repo._home['bill_protection_epoch']+=1
        refresh=self.begin(refresh=True);self.prepare(refresh);new=self.activate(refresh)
        self.assertEqual(new['workingSet']['policy'],first['workingSet']['policy'])
        self.assertEqual(new['workingSet']['activeCount'],2)
        self.assertTrue(new['protectionsCurrent'])

    def test_missing_capability_never_begins_a_job(self):
        self.repo._home['bill_working_schema_version']=0
        with self.assertRaises(ValueError):self.begin()
        self.assertEqual(self.repo.jobs,{})

    def test_begin_retry_across_midnight_reuses_durable_frozen_policy(self):
        request=str(uuid4());payload=dict(source_import_id=I,mode='last_12_months',expected_import_version=1,expected_working_version=0)
        first=self.call('bill_range_begin',payload,request)
        self.now[0]=datetime(2026,10,31,16,tzinfo=timezone.utc)
        second=self.call('bill_range_begin',payload,request)
        self.assertEqual(first['policy'],second['policy'])
        self.assertEqual(self.repo.last_begin_data['policy']['asOfDate'],'2026-10-30')

    def test_shared_registry_uses_current_session_reader(self):
        original_reader=self.bill_ops._index
        self.ops.bill_ops=SimpleNamespace(_check=self.bill_ops._check,_index=original_reader)
        @contextmanager
        def old_reader(*args):raise AssertionError('A previous session reader was used');yield
        self.registry.bill_ops._index=old_reader
        job=self.begin();self.assertEqual(self.prepare(job)['manifest']['activeCount'],1)

    def test_validated_service_routes_range_actions_and_scoped_current_read(self):
        from app.ap_shared.models import validate_request
        request=str(uuid4());payload=dict(source_import_id=I,mode='last_12_months',expected_import_version=1,expected_working_version=0)
        validate_request(dict(version=1,request_id=request,action='bill_range_begin',payload=payload))
        self.service.working_operations=self.ops
        self.assertEqual(self.service.handle('bill_range_begin',payload,request,self.auth)['policy']['mode'],'last_12_months')
        self.assertEqual(self.service.handle('bill_current',{'include_working':True},str(uuid4()),self.auth)['importId'],I)


if __name__=='__main__':unittest.main()
