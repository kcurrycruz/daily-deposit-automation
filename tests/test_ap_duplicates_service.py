import unittest
from datetime import timedelta
from uuid import uuid4
from test_ap_duplicates_operations import setup_detector
from test_ap_shared_access import CONFIG,NOW


class DuplicateServiceTests(unittest.TestCase):
    def test_dispatch_validates_and_checks_expiry_without_affecting_statements(self):
        from app.ap_shared.protocol import dispatch_request
        h,ops,repo=setup_detector(self); pin=repo.current()
        request=dict(version=1,request_id=str(uuid4()),action='duplicate_ensure',
                     payload=dict(import_id=pin['importId'],expected_import_version=pin['importVersion']))
        reply=dispatch_request(request,h.session,CONFIG,h.service,NOW)
        self.assertTrue(reply['ok'],reply)
        for payload in [dict(request['payload'],extra=True),dict(request['payload'],expected_import_version=True)]:
            invalid=dispatch_request({**request,'request_id':str(uuid4()),'payload':payload},h.session,CONFIG,h.service,NOW)
            self.assertEqual(invalid['error']['code'],'validation')
        expired=dispatch_request(request,h.session,CONFIG,h.service,NOW+timedelta(hours=9))
        self.assertEqual(expired['error']['code'],'denied'); self.assertIsNone(expired['data'])
        self.assertFalse(h.service.repository.completion_events)
    def test_bootstrap_capability_is_additive_and_schema_gated(self):
        from test_ap_duplicates_repository import DuplicateTransport
        from test_ap_shared_repository import make_repository,IMPORT,BackendTransport
        self.assertEqual(make_repository(DuplicateTransport()).bootstrap(CONFIG.workspace_id)['capabilities']['duplicateBills'],1)
        self.assertNotIn('duplicateBills',make_repository(BackendTransport()).bootstrap(CONFIG.workspace_id)['capabilities'])

    def test_access_rotation_during_source_read_returns_no_financial_evidence(self):
        from app.ap_shared.protocol import dispatch_request
        h,ops,repo=setup_detector(self); pin=repo.current()
        started=ops.handle('duplicate_ensure',dict(import_id=pin['importId'],expected_import_version=pin['importVersion']),str(uuid4()),h.auth)
        original=ops.source.read_page
        def rotating(*args):
            result=original(*args)
            h.session.clear()
            return result
        ops.source.read_page=rotating
        request=dict(version=1,request_id=str(uuid4()),action='duplicate_step',payload=dict(scan_id=started['scanId'],
            generation=started['generation'],expected_checkpoint=0,restart=False))
        reply=dispatch_request(request,h.session,CONFIG,h.service,NOW)
        self.assertEqual(reply['error']['code'],'denied'); self.assertIsNone(reply['data'])
        self.assertEqual(h.repo.active_id,pin['importId'])
