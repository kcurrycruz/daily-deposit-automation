import base64
import gzip
import importlib
from pathlib import Path
import tempfile
import time
import unittest
from uuid import uuid4
from fixtures.ap_shared.bill_exports import export
from fixtures.ap_shared.bill_store_double import BillStoreDouble
from app.ap_shared.bills.archive import SnapshotCache
from app.ap_shared.bills.builds import BuildRegistry
from test_ap_shared_access import CONFIG, NOW
from test_ap_shared_service import fixture


class BillOperationsTests(unittest.TestCase):
    def setUp(self):
        try:
            self.api = importlib.import_module('app.ap_shared.bills.operations')
        except ModuleNotFoundError:
            self.fail('Authenticated BILL snapshot operations have not been implemented')
        self.service, _, self.auth, self.session, _ = fixture()
        self.repo = BillStoreDouble(CONFIG)
        self.tmp = tempfile.TemporaryDirectory(prefix='ap-bill-op-'); self.addCleanup(self.tmp.cleanup)
        self.builds = BuildRegistry(Path(self.tmp.name), lambda: NOW, time.monotonic); self.addCleanup(self.builds.close)
        self.cache = SnapshotCache(self.repo); self.addCleanup(self.cache.close)
        self.ops = self.api.BillOperations(self.repo, CONFIG, lambda: NOW, self.service.revalidate, self.builds, self.cache)
        self.service.bill_operations = self.ops

    def call(self, action, payload, request_id=None):
        return self.ops.handle(action, payload, request_id or str(uuid4()), self.auth)

    def upload(self, source, filename='synthetic.csv', mtime=0):
        payload = gzip.compress(source.encode(), mtime=mtime)
        job = self.call('bill_upload_begin', dict(filename=filename, compressed_size=len(payload), as_of=''))
        for at in range(0, len(payload), 262144):
            self.call('bill_upload_chunk', dict(job_id=job['job_id'], index=at // 262144, data=base64.b64encode(payload[at:at+262144]).decode()))
        result = self.call('bill_upload_finish', dict(job_id=job['job_id']))
        return job, result

    def finish(self, job, progress):
        while progress.get('state') != 'prepared':
            progress = self.call('bill_prepare_step', dict(job_id=job['job_id'], generation=progress['generation'], expected_checkpoint=progress['checkpoint']))
        return self.call('bill_activate', dict(job_id=job['job_id'], confirm_restore=False))

    def test_weekly_replacement_and_duplicate_reupload_do_not_append_invoices(self):
        job, p = self.upload(export([{}])); first = self.finish(job, p)
        duplicate, same = self.upload(export([{}]), filename='renamed.csv', mtime=5)
        self.assertTrue(same['alreadyCurrent']); self.assertEqual(len(self.repo.sources), 1)
        self.assertEqual(same['importId'], first['importId'])
        new, p = self.upload(export([{}, {'Invoice #': 'NEW-1'}])); second = self.finish(new, p)
        self.assertEqual(second['recordCount'], 2)
        self.assertEqual(self.repo.active_id, second['importId'])
        self.assertEqual(self.repo.source(first['importId'])['record_count'], 1)

    def test_queries_find_exact_reference_and_all_equal_amount_candidates(self):
        job, p = self.upload(export([{'Invoice #': 'A'}, {'Invoice #': 'B'}])); saved = self.finish(job, p)
        query = dict(importId=saved['importId'], references=[dict(invoiceKey='A', kind='invoice')],
                     amounts=[dict(vendorKey='synthetic & co.', kind='invoice', amount=13800)])
        page = self.call('bill_candidates_page', dict(query=query))
        self.assertEqual(page['total'], 2)
        self.assertEqual([r['invoiceNumber'] for r in page['records']], ['A', 'B'])
        vendors = self.call('bill_vendors_page', dict(import_id=saved['importId']))
        self.assertEqual(vendors['vendors'], [dict(vendor='Synthetic & Co.')])

    def test_storage_failure_does_not_replace_active_data(self):
        job, p = self.upload(export([{}])); first = self.finish(job, p)
        self.repo.fail_writes = True
        with self.assertRaises(ValueError): self.upload(export([{'Invoice #': 'NEW-1'}]))
        self.assertEqual(self.repo.active_id, first['importId'])

    def test_missing_process_state_requires_explicit_restart(self):
        job, p = self.upload(export([{}]))
        self.builds.release(job['job_id'])
        request = dict(job_id=job['job_id'], generation=p['generation'], expected_checkpoint=p['checkpoint'])
        lost = self.call('bill_prepare_step', request)
        self.assertEqual(lost['state'], 'restart_required')
        restarted = self.call('bill_prepare_step', {**request, 'restart': True})
        self.assertNotEqual(restarted['generation'], p['generation'])
        saved = self.finish(job, restarted)
        self.assertEqual(saved['recordCount'], 1)

    def test_replayed_activation_has_one_effect_and_old_source_cancel_keeps_current(self):
        job, p = self.upload(export([{}]))
        while p['state'] != 'prepared': p = self.call('bill_prepare_step', dict(job_id=job['job_id'], generation=p['generation'], expected_checkpoint=p['checkpoint']))
        request_id = str(uuid4()); payload = dict(job_id=job['job_id'], confirm_restore=False)
        first = self.call('bill_activate', payload, request_id)
        self.assertEqual(self.call('bill_activate', payload, request_id)['importId'], first['importId'])
        self.assertEqual(self.repo.version, 1)
        newer, p = self.upload(export([{'Invoice #': 'NEW'}])); second = self.finish(newer, p)
        old, restored = self.upload(export([{}])); self.assertTrue(restored['confirmationRequired'])
        cancelled = self.call('bill_activate', dict(job_id=old['job_id'], confirm_restore=False))
        self.assertTrue(cancelled['cancelled']); self.assertEqual(self.repo.active_id, second['importId'])

    def test_actions_reject_unknown_fields_and_wrong_sessions(self):
        with self.assertRaises(ValueError): self.call('bill_upload_begin', dict(filename='x.csv', compressed_size=1, sql='bad'))
        job, _ = self.upload(export([{}]))
        self.repo.jobs[job['job_id']]['session_nonce'] = str(uuid4())
        with self.assertRaises(PermissionError): self.call('bill_prepare_step', dict(job_id=job['job_id'], generation=job['generation'], expected_checkpoint=0))

    def test_service_and_protocol_route_snapshot_actions_and_report_safe_quota_error(self):
        from app.ap_shared.protocol import dispatch_request
        self.repo.fail_writes = True
        request = dict(version=1, request_id=str(uuid4()), action='bill_upload_begin',
                       payload=dict(filename='synthetic.csv', compressed_size=20))
        reply = dispatch_request(request, self.session, CONFIG, self.service, NOW)
        self.assertFalse(reply['ok'])
        self.assertEqual(reply['error']['code'], 'bill_quota')
        self.assertIsNone(reply['data'])
        self.assertNotIn(CONFIG.supabase_secret_key, str(reply))

    def test_rejected_quota_does_not_leave_a_blocking_unseen_update_job(self):
        self.repo.fail_writes = True
        with self.assertRaises(ValueError):
            self.call('bill_upload_begin', dict(filename='synthetic.csv', compressed_size=20))
        self.repo.fail_writes = False
        next_job = self.call('bill_upload_begin', dict(filename='smaller.csv', compressed_size=10))
        self.assertEqual(next_job['state'], 'uploading')
