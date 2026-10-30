from pathlib import Path
import subprocess
import unittest
class NearSchemaTests(unittest.TestCase):
 def test_near_reference_lifecycle_preserves_scoped_guards(self):
  self.assertTrue(Path('supabase/migrations/202610300003_ap_duplicate_near_references.sql').is_file(),'Near-reference migration missing')
  result=subprocess.run(['node','tests/fixtures/ap_shared/duplicate_near_schema_checks.mjs'],capture_output=True,encoding='utf8',timeout=120)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
  self.assertIn('Near-reference duplicate SQL checks passed',result.stdout)
