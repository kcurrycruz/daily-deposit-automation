"""Opt-in, synthetic read-only checks against an owner-configured test project.

Never use the production workspace. Provisioning and mutation verification are
separate owner-authorized steps documented in the release checklist.
"""
import os
import unittest
from app.ap_shared.models import read_config
from app.ap_shared.repository import create_repository

@unittest.skipUnless(os.getenv('AP_SYNTHETIC_INTEGRATION') == '1',
                     'Deployment blocker: authorized synthetic Supabase project not configured')
class SupabaseIntegrationTests(unittest.TestCase):
    def test_private_bucket_and_server_round_trip(self):
        config=read_config({'ap':{'password':os.environ['AP_TEST_PASSWORD'],
            'supabase_url':os.environ['AP_TEST_URL'],'supabase_secret_key':os.environ['AP_TEST_SECRET_KEY'],
            'workspace_id':os.environ['AP_TEST_WORKSPACE_ID'],'bucket':'hwfc-ap-private'}})
        snapshot=create_repository(config).bootstrap(config.workspace_id)
        self.assertIn('statements',snapshot)
        self.assertIn('activeImport',snapshot)

