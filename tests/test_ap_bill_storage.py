import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4
import httpx
from test_ap_shared_repository import BackendTransport, make_repository
from test_ap_shared_access import CONFIG


class BillTransport(BackendTransport):
    def __init__(self):
        super().__init__()
        self.job = dict(id=str(uuid4()), workspace_id=CONFIG.workspace_id, session_nonce=str(uuid4()),
                        state='reading', original_hash='a' * 64, original_archive={'hash': 'b' * 64}, chunks={})
        self.deleted = []
        self.quota = False

    def respond(self, request):
        if request.url.path.endswith('/ap_bill_jobs'):
            self.requests.append(request)
            assert request.url.params['workspace_id'] == 'eq.' + CONFIG.workspace_id
            return httpx.Response(200, json=[self.job])
        if request.url.path.endswith('/rpc/ap_bill_quota_reserve'):
            self.requests.append(request)
            if self.quota: return httpx.Response(400, json={'code': 'P0001', 'message': 'bill_quota', 'details': None, 'hint': None})
            return httpx.Response(200, json={'used_bytes': 20, 'reserved_bytes': 30, 'warning': False})
        if request.method == 'DELETE' and '/storage/v1/object/' in request.url.path:
            self.requests.append(request)
            self.deleted.extend(json.loads(request.content)['prefixes'])
            return httpx.Response(200, json=[])
        return super().respond(request)


class BillStorageTests(unittest.TestCase):
    def setUp(self):
        try:
            self.api = importlib.import_module('app.ap_shared.bills.repository')
        except ModuleNotFoundError:
            self.fail('Private snapshot object operations have not been implemented')
        self.transport = BillTransport()
        self.repo = self.api.BillRepository(make_repository(self.transport))

    def test_acknowledged_chunk_cleanup_uses_one_bounded_exact_key_request(self):
        self.transport.job['chunks']={str(i):dict(hash='c'*64,size=1) for i in range(128)}
        self.repo.cleanup_acknowledged_chunks(self.transport.job['id'])
        deletes=[r for r in self.transport.requests if r.method=='DELETE']
        self.assertEqual(len(deletes),1)
        self.assertEqual(len(self.transport.deleted),128)
        self.assertTrue(all('/staging/'+self.transport.job['id']+'/' in key for key in self.transport.deleted))

    def test_content_addressed_artifact_retries_do_not_overwrite(self):
        with tempfile.TemporaryDirectory(prefix='ap-bill-store-') as root:
            path = Path(root) / 'index.gz'; path.write_bytes(b'synthetic compressed fixture')
            first = self.repo.put_artifact(self.transport.job['id'], 'index', path, str(uuid4()))
            second = self.repo.put_artifact(self.transport.job['id'], 'index', path, str(uuid4()))
            self.assertEqual(first, second)
            self.assertEqual(len(self.transport.files), 1)
            self.assertEqual(first['hash'], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertTrue(first['key'].endswith(first['hash'] + '.sqlite.gz'))

    def test_quota_failure_is_safe_and_keeps_existing_objects(self):
        self.transport.files['keep'] = b'existing source'
        self.transport.quota = True
        with self.assertRaises(ValueError) as error:
            self.repo.reserve(self.transport.job['id'], 30, str(uuid4()))
        self.assertEqual(error.exception.code, 'bill_quota')
        self.assertEqual(self.transport.files, {'keep': b'existing source'})
        self.assertNotIn(CONFIG.supabase_secret_key, str(error.exception))

    def test_only_exact_acknowledged_job_chunks_are_deleted(self):
        job = self.transport.job
        job['chunks'] = {'127': {'hash': 'c' * 64, 'size': 1}}
        self.repo.cleanup_acknowledged_chunks(job['id'])
        self.assertEqual(self.transport.deleted, [f'{CONFIG.workspace_id}/staging/{job["id"]}/127-' + 'c' * 64 + '.bin'])
        self.assertFalse(any('/bills/' in key for key in self.transport.deleted))

    def test_unverified_original_cannot_trigger_cleanup(self):
        self.transport.job['original_archive'] = None
        with self.assertRaises(ValueError): self.repo.cleanup_acknowledged_chunks(self.transport.job['id'])
        self.assertEqual(self.transport.deleted, [])
