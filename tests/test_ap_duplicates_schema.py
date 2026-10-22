from pathlib import Path
import subprocess
import unittest


class DuplicateSchemaTests(unittest.TestCase):
    def test_atomic_lifecycle_reviews_and_shared_quota(self):
        root = Path(__file__).resolve().parents[1]
        migration = root / 'supabase/migrations/202610220001_ap_duplicate_bills.sql'
        self.assertTrue(migration.exists(), 'Add the additive duplicate detector migration')
        result = subprocess.run(['node', str(root / 'tests/fixtures/ap_shared/duplicate_schema_checks.mjs')],
                                cwd=root, capture_output=True, text=True, encoding='utf8', timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Duplicate bill SQL checks passed', result.stdout)
