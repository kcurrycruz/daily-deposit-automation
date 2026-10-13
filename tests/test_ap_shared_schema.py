import os
from pathlib import Path
import shutil
import subprocess
import unittest

class SharedSchemaTests(unittest.TestCase):
    def test_postgres_private_roles_history_and_transactions(self):
        root=Path(__file__).resolve().parents[1]
        node=shutil.which('node')
        self.assertIsNotNone(node,'Install the documented Node development runtime first')
        result=subprocess.run([node,str(root/'tests/fixtures/ap_shared/schema_checks.mjs')],cwd=root,
                              capture_output=True,text=True,encoding='utf-8',timeout=90)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('SQL behavior checks passed:',result.stdout)

if __name__ == '__main__': unittest.main()
