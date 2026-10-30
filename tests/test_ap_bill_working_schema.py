from pathlib import Path
import subprocess
import unittest


class WorkingSchemaTests(unittest.TestCase):
    def test_private_versioned_working_set_transactions(self):
        root = Path(__file__).resolve().parents[1]
        self.assertTrue((root / 'supabase/migrations/202610300001_ap_bill_working_sets.sql').exists(),
                        'The additive private working-set lifecycle has not been implemented')
        result = subprocess.run(['node', 'tests/fixtures/ap_shared/working_schema_checks.mjs'], cwd=root,
                                capture_output=True, encoding='utf8', timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Working-set SQL checks passed', result.stdout)
