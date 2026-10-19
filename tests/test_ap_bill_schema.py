from pathlib import Path
import subprocess
import unittest


class BillSchemaTests(unittest.TestCase):
    def test_snapshot_transactions_and_private_permissions(self):
        root = Path(__file__).resolve().parents[1]
        self.assertTrue((root / 'supabase/migrations/202610190001_ap_bill_snapshots.sql').exists(),
                        'Additive snapshot migration has not been implemented')
        result = subprocess.run(['node', str(root / 'tests/fixtures/ap_shared/snapshot_schema_checks.mjs')],
                                cwd=root, capture_output=True, encoding='utf8', timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('BILL snapshot SQL checks passed', result.stdout)
