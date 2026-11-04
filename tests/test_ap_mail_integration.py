"""Live acceptance is explicit and synthetic-only; never infer deployment success."""
import os
import unittest

class IntegrationGateTests(unittest.TestCase):
    def test_production_ref_is_refused_before_any_network_or_secret_access(self):
        from fixtures.ap_mail.integration_check import integration_target
        from app.ap_mail.contracts import MailError
        env=dict(AP_MAIL_SYNTHETIC_INTEGRATION='1',AP_MAIL_SYNTHETIC_ATTESTATION='synthetic-only',
            AP_MAIL_ALLOW_TEST_PROJECT='uhwpnbntjsopuilouize',AP_MAIL_SUPABASE_URL='https://uhwpnbntjsopuilouize.supabase.co',
            AP_MAIL_ALLOW_TEST_WORKSPACE='00000000-0000-4000-8000-000000000001',AP_MAIL_WORKSPACE_ID='00000000-0000-4000-8000-000000000001')
        with self.assertRaises(MailError):integration_target(env)
        self.assertIsNone(integration_target({}))

class SyntheticIntegrationTests(unittest.TestCase):
    def test_real_concurrent_claim_and_publish_private_cloud_round_trip(self):
        if os.environ.get('AP_MAIL_SYNTHETIC_INTEGRATION')!='1':
            self.skipTest('Deployment blocker: owner-authorized synthetic SQL/storage/IAM/Tasks/Gmail environment not configured.')
        from fixtures.ap_mail.integration_check import run_integration
        report=run_integration(os.environ)
        self.assertLessEqual(report['concurrent_claims'],1)
        self.assertTrue(report['private_storage_verified'])
        self.assertTrue(report['unsigned_call_denied'])
        self.assertEqual(report['status'],'awaiting_review')
