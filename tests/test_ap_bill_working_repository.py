import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import httpx
from test_ap_shared_repository import BackendTransport, make_repository
from test_ap_shared_access import CONFIG
import test_ap_bill_working_policy as policy_fixtures
from test_ap_bill_working_policy import bill, I, S

try:
    from app.ap_shared.bills.working.repository import WorkingRepository
    from app.ap_shared.bills.working.protections import ProtectionRepository
except ImportError:
    WorkingRepository = ProtectionRepository = None


class WorkingTransport(BackendTransport):
    def __init__(self):
        super().__init__()
        self.epoch = 4
        self.job = dict(id=S, workspace_id=CONFIG.workspace_id, source_import_id=I,
                        session_nonce=S, policy=dict(version='ap-active-range-v1', mode='all',
                                                    asOfDate='2026-10-30', cutoffDate=''),
                        protection_digest='b'*64)

    def respond(self, request):
        table = request.url.path.rsplit('/', 1)[-1]
        if request.url.path.startswith('/rest/v1/') and '/rpc/' not in request.url.path:
            self.requests.append(request)
            key = 'id' if table == 'ap_workspaces' else 'workspace_id'
            assert request.url.params[key] == 'eq.'+CONFIG.workspace_id
            rows = {'ap_workspaces': [dict(id=CONFIG.workspace_id, bill_protection_epoch=self.epoch)],
                    'ap_bill_working_jobs': [self.job], 'ap_bill_working_sets': [],
                    'ap_bill_imports': [dict(id=I, state='ready', file_hash='a'*64, record_count=2)],
                    'ap_statements': [], 'ap_duplicate_reviews': [], 'ap_vendor_mappings': []}
            return httpx.Response(200, json=rows[table])
        if request.url.path.endswith('/rpc/ap_bill_working_mutate'):
            self.requests.append(request)
            payload = json.loads(request.content)
            assert payload['p_workspace'] == CONFIG.workspace_id
            assert payload['p_operation'] == 'cancel'
            return httpx.Response(200, json={'cancelled': True})
        return super().respond(request)


class WorkingRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(WorkingRepository, 'The private working-set repository is not implemented')
        self.transport = WorkingTransport()
        self.base = make_repository(self.transport)
        self.repo = WorkingRepository(self.base)

    def test_workspace_scoping_and_private_rpc(self):
        self.assertEqual(self.repo.job(S)['id'], S)
        self.assertEqual(self.repo.rpc('cancel', {'job_id':S}, I), {'cancelled':True})
        with self.assertRaises(ValueError):
            self.repo.rpc('sql', {}, I)
        self.transport.public = True
        with self.assertRaises(Exception):
            self.repo.job(S)

    def test_only_exact_working_artifact_namespaces_allowed(self):
        key = f'{CONFIG.workspace_id}/bill-working/v1/{"a"*64}/{"b"*64}.sqlite.gz'
        self.base._object_key(CONFIG.workspace_id, key)
        for bad in [key.replace('/v1/', '/v2/'), key.replace('/bill-working/', '/other/'),
                    key.replace('.sqlite.gz','.csv.gz'), '../'+key]:
            with self.subTest(key=bad), self.assertRaises(Exception):
                self.base._object_key(CONFIG.workspace_id, bad)

    def test_artifact_write_and_verified_read_roundtrip(self):
        raw = b'synthetic immutable artifact'
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'index.gz';path.write_bytes(raw)
            info=self.repo.put_artifact(S,'index',path)
            self.assertEqual(info['hash'],hashlib.sha256(raw).hexdigest())
            self.assertTrue(info['key'].startswith(CONFIG.workspace_id+'/bill-working/v1/'))
            fixture=policy_fixtures.WorkingManifestTests();fixture.setUp();mf=fixture.manifest
            # This job's policy differs from the policy fixture; bind a complete
            # manifest with a descriptor actually stored through the private SDK.
            mf['source']=dict(importId=I,sourceDigest='a'*64,recordCount=2)
            mf['policy']=self.transport.job['policy']
            from app.ap_shared.bills.working.contracts import working_digest
            mf['workingDigest']=working_digest(mf['source'],mf['policy'],mf['protectionDigest'])
            for name in ('indexArchive','contextArchive'):
                mf[name]={**info, 'expandedHash':'e'*64,'expandedBytes':1000}
            target=Path(folder)/'read.gz'
            self.repo.read_artifact(mf,'index',target)
            self.assertEqual(target.read_bytes(),raw)
            self.transport.files[info['key']]=b'corrupted'
            with self.assertRaises(ValueError):self.repo.read_artifact(mf,'index',target)

    def test_authoritative_protection_snapshot_rechecks_epoch_and_authorization(self):
        self.assertIsNotNone(ProtectionRepository)
        checked=[]
        repo=ProtectionRepository(self.base,lambda auth:checked.append(auth))
        snapshot=repo.snapshot(I,'synthetic-authorization')
        self.assertEqual(snapshot['epoch'],4)
        self.assertEqual(snapshot['digest'],snapshot['protections'].digest())
        self.assertFalse(snapshot['protections'].protects(bill()))
        self.assertGreaterEqual(len(checked),5)
        def change(auth):self.transport.epoch+=1
        with self.assertRaises(ValueError):ProtectionRepository(self.base,change).snapshot(I,'synthetic')


if __name__=='__main__':unittest.main()
