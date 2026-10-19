import importlib
from pathlib import Path
import tempfile
import time
import unittest
from uuid import uuid4
from test_ap_shared_access import CONFIG, NOW
from test_ap_shared_service import fixture
from fixtures.ap_shared.bill_exports import export


class BillBuildTests(unittest.TestCase):
    def setUp(self):
        try:
            self.api = importlib.import_module('app.ap_shared.bills.builds')
        except ModuleNotFoundError:
            self.fail('Recoverable bounded BILL build registry is not implemented')
        self.tmp = tempfile.TemporaryDirectory(prefix='ap-bill-build-')
        self.addCleanup(self.tmp.cleanup)
        self.registry = self.api.BuildRegistry(Path(self.tmp.name), lambda: NOW, time.monotonic)
        self.addCleanup(self.registry.close)
        _, _, self.auth, _, _ = fixture()
        self.job = dict(id=str(uuid4()), workspace_id=CONFIG.workspace_id,
                        session_nonce=self.auth.session_nonce, generation=str(uuid4()))

    def prepare(self):
        paths = self.registry.paths(self.job['id'])
        paths['csv'].write_text(export([{}, {'Invoice #': '00043'}]), encoding='utf8', newline='')
        self.registry.start(self.job)

    def test_build_completes_in_steps_and_repeated_checkpoint_does_not_duplicate(self):
        self.prepare()
        first = self.registry.step(self.job['id'], self.job['generation'], 0, self.auth, lambda a: None)
        repeated = self.registry.step(self.job['id'], self.job['generation'], 0, self.auth, lambda a: None)
        self.assertEqual(first, repeated)
        result = first
        while result['state'] != 'prepared':
            result = self.registry.step(self.job['id'], self.job['generation'], result['checkpoint'], self.auth, lambda a: None)
        self.assertEqual(result['recordCount'], 2)
        artifacts = self.registry.artifacts(self.job['id'])
        self.assertTrue(artifacts['indexArchivePath'].is_file())
        self.assertEqual(artifacts['summary']['counts']['recordCount'], 2)

    def test_missing_local_build_requires_restart_not_a_false_resume(self):
        result = self.registry.step(self.job['id'], self.job['generation'], 20, self.auth, lambda a: None)
        self.assertEqual(result['state'], 'restart_required')
        self.assertNotEqual(result.get('state'), 'prepared')

    def test_wrong_session_and_stale_generation_are_rejected(self):
        self.prepare()
        with self.assertRaises(ValueError):
            self.registry.step(self.job['id'], str(uuid4()), 0, self.auth, lambda a: None)
        from dataclasses import replace
        with self.assertRaises(PermissionError):
            self.registry.step(self.job['id'], self.job['generation'], 0,
                               replace(self.auth, session_nonce=str(uuid4())), lambda a: None)

    def test_expired_authorization_cannot_read_even_a_cached_step_reply(self):
        self.prepare()
        self.registry.step(self.job['id'], self.job['generation'], 0, self.auth, lambda a: None)
        def deny(auth): raise PermissionError('locked')
        with self.assertRaises(PermissionError):
            self.registry.step(self.job['id'], self.job['generation'], 0, self.auth, deny)
