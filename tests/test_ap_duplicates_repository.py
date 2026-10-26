import json
import unittest
from uuid import uuid4
import httpx
from test_ap_shared_repository import BackendTransport, make_repository, IMPORT
from test_ap_shared_access import CONFIG
from app.ap_shared.bills.duplicates.contracts import RULE_VERSION


class DuplicateTransport(BackendTransport):
    def __init__(self):
        super().__init__()
        self.scan = dict(id=str(uuid4()), workspace_id=CONFIG.workspace_id, import_id=IMPORT,
                         source_digest='a' * 64, rule_version=RULE_VERSION, state='pending')
        self.error = None

    def respond(self, request):
        path = request.url.path
        if path.endswith('/rpc/ap_duplicate_mutate'):
            self.requests.append(request)
            body = json.loads(request.content)
            assert body['p_workspace'] == CONFIG.workspace_id
            assert body['p_operation'] in ('ensure', 'claim', 'checkpoint', 'restart', 'publish', 'fail', 'reserve', 'review')
            if self.error:
                return httpx.Response(400, json=dict(code='P0001', message=self.error, details=None, hint=None))
            return httpx.Response(200, json=self.scan)
        if path.endswith('/ap_duplicate_scans'):
            self.requests.append(request)
            assert request.url.params['workspace_id'] == 'eq.' + CONFIG.workspace_id
            return httpx.Response(200, json=[self.scan])
        if path.endswith('/ap_duplicate_reviews'):
            self.requests.append(request)
            assert request.url.params['workspace_id'] == 'eq.' + CONFIG.workspace_id
            rows = [dict(key=k * 64, decision='not_duplicate', initials='KC', note='', version=1,
                         at='2026-10-22T12:00:00Z', reviewed_import_id=IMPORT) for k in 'abc']
            after = request.url.params.get('key', 'gt.').removeprefix('gt.')
            return httpx.Response(200, json=[r for r in rows if r['key'] > after][:int(request.url.params['limit'])])
        result = super().respond(request)
        if path.endswith('/ap_workspaces'):
            rows = result.json(); rows[0].update(import_version=1, duplicate_review_revision=4, duplicate_schema_version=1)
            return httpx.Response(200, json=rows)
        if path.endswith('/ap_bill_imports'):
            rows = result.json(); rows[0]['file_hash'] = 'a' * 64
            return httpx.Response(200, json=rows)
        return result


class DuplicateRepositoryTests(unittest.TestCase):
    def setUp(self):
        from app.ap_shared.bills.duplicates.repository import DuplicateRepository
        self.transport = DuplicateTransport()
        self.repo = DuplicateRepository(make_repository(self.transport))

    def test_current_source_and_paged_reviews_are_workspace_scoped(self):
        self.assertEqual(self.repo.current()['importVersion'], 1)
        self.assertEqual(self.repo.current()['sourceDigest'], 'a' * 64)
        self.assertEqual(self.repo.review_revision(), 4)
        first = self.repo.reviews_page(None, 2)
        self.assertEqual([r['key'] for r in first['reviews']], ['a' * 64, 'b' * 64])
        second = self.repo.reviews_page(first['nextCursor'], 2)
        self.assertEqual([r['key'] for r in second['reviews']], ['c' * 64])
        self.assertIsNone(second['nextCursor'])

    def test_rpc_uses_server_workspace_and_unknown_operations_do_not_reach_cloud(self):
        self.assertEqual(self.repo.rpc('ensure', {}, str(uuid4()))['id'], self.transport.scan['id'])
        count = len(self.transport.requests)
        with self.assertRaises(ValueError):
            self.repo.rpc('arbitrary_sql', {}, str(uuid4()))
        self.assertEqual(len(self.transport.requests), count)

    def test_foreign_row_and_cloud_messages_cannot_leak(self):
        self.transport.scan['workspace_id'] = str(uuid4())
        with self.assertRaises(PermissionError):
            self.repo.scan(self.transport.scan['id'])
        self.transport.error = 'SYNTHETIC-SECRET must never leak'
        with self.assertRaises(ValueError) as error:
            self.repo.rpc('claim', {}, str(uuid4()))
        self.assertNotIn('SYNTHETIC-SECRET', str(error.exception))
        self.transport.error = 'duplicate_quota'
        with self.assertRaises(ValueError) as error:
            self.repo.rpc('reserve', {}, str(uuid4()))
        self.assertEqual(error.exception.code, 'duplicate_quota')
