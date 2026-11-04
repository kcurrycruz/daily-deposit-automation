import shutil
import subprocess
from pathlib import Path
import unittest


class MailSchemaTests(unittest.TestCase):
    def test_atomic_cursor_outbox_leases_retry_controls_and_acl(self):
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run([shutil.which('node'), str(root/'tests/fixtures/ap_mail/schema_checks.mjs')],
                              cwd=root,capture_output=True,text=True,encoding='utf-8',timeout=120)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('Mail SQL behavior checks passed',result.stdout)

