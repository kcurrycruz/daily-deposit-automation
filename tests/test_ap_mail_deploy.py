from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
class DeploymentTests(unittest.TestCase):
    def test_deploy_private_concurrency_and_dry_run(self):
        main=(ROOT/'deploy/ap_mail/main.tf').read_text();plan=(ROOT/'deploy/ap_mail/plan.ps1').read_text()
        self.assertNotIn('allUsers',main);self.assertNotIn('allAuthenticatedUsers',main)
        self.assertRegex(main,r'max_concurrent_dispatches\s*=\s*1');self.assertRegex(main,r'max_instance_request_concurrency\s*=\s*1')
        self.assertRegex(main,r'max_instance_count\s*=\s*1');self.assertRegex(main,r'timeout\s*=\s*"600s"')
        self.assertRegex(main,r'"cpu"\s*=\s*"2"');self.assertRegex(main,r'"memory"\s*=\s*"4Gi"')
        self.assertRegex(main,r'schedule\s*=\s*"\*/5\s*\*\s*\*\s*\*\s*\*"');self.assertRegex(main,r'paused\s*=\s*true')
        self.assertNotRegex(plan,r'(?im)^\s*(?:&\s*)?terraform\s+apply')
        self.assertNotIn('secret_data',main);self.assertNotIn('supabase_secret_key',main)
        docker=(ROOT/'workers/ap_mail/Dockerfile').read_text()
        self.assertIn('@sha256:',docker);self.assertIn('USER pwuser',docker);self.assertIn('--require-hashes',docker)
        self.assertTrue((ROOT/'workers/ap_mail/requirements.lock').exists())
