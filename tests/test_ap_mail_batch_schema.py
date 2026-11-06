import subprocess
import shutil
from pathlib import Path
import unittest


class BatchSchemaTests(unittest.TestCase):
    def test_pending_read_is_scoped_due_private_and_read_only(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [shutil.which('node'), str(root/'tests/fixtures/ap_mail/batch_checks.mjs')],
            cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('Mail batch SQL checks passed', result.stdout)
