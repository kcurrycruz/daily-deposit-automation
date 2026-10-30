from pathlib import Path
import subprocess
import unittest

class DuplicateWorkingSchemaTests(unittest.TestCase):
    def test_scope_bound_duplicate_lifecycle(self):
        root=Path(__file__).resolve().parents[1]
        self.assertTrue((root/'supabase/migrations/202610300002_ap_duplicate_working_scope.sql').exists(),'Scoped duplicate migration is not implemented')
        result=subprocess.run(['node','tests/fixtures/ap_shared/duplicate_working_schema_checks.mjs'],cwd=root,capture_output=True,encoding='utf8',timeout=120)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('Scoped duplicate SQL checks passed',result.stdout)
