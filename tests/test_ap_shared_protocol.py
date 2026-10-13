import unittest
from datetime import timedelta
from uuid import uuid4
from test_ap_shared_service import fixture
from test_ap_shared_access import CONFIG,NOW

class ProtocolTests(unittest.TestCase):
    def dispatch(self,value,state=None):
        from app.ap_shared.protocol import dispatch_request
        _,_,_,authorized,_=fixture()
        class Service:
            calls=[]
            def handle(self,*args): self.calls.append(args); return {'statements':[]}
        service=Service()
        reply=dispatch_request(value,authorized if state is None else state,CONFIG,service,NOW)
        return reply,service.calls

    def request(self,**changes):
        return {'version':1,'request_id':str(uuid4()),'action':'bootstrap','payload':{},**changes}

    def test_locked_request_never_reaches_service(self):
        reply,calls=self.dispatch(self.request(),{})
        self.assertFalse(reply['ok']); self.assertEqual(reply['error']['code'],'denied'); self.assertEqual(calls,[])

    def test_bad_requests_do_not_reach_service(self):
        for request in [self.request(action='delete_all'),self.request(extra=True),self.request(request_id='bad'),
                        self.request(payload={'workspace_id':str(uuid4())}),self.request(payload={'password':'synthetic'}),
                        self.request(payload={'note':'x'*1048576})]:
            reply,calls=self.dispatch(request)
            self.assertFalse(reply['ok']); self.assertEqual(calls,[])

    def test_valid_request_returns_correlated_secret_free_reply(self):
        request=self.request(); reply,calls=self.dispatch(request)
        self.assertTrue(reply['ok']); self.assertEqual(reply['request_id'],request['request_id']); self.assertEqual(len(calls),1)
        self.assertNotIn(CONFIG.password,str(reply)); self.assertNotIn(CONFIG.supabase_secret_key,str(reply))

    def test_expiry_rejects_before_service(self):
        _,_,_,state,_=fixture()
        from app.ap_shared.protocol import dispatch_request
        class Service:
            def handle(self,*args): raise AssertionError('Unauthorized call')
        reply=dispatch_request(self.request(),state,CONFIG,Service(),NOW+timedelta(hours=8))
        self.assertEqual(reply['error']['code'],'denied')
    def test_transport_retry_can_dispatch_without_automatic_rerun_loop(self):
        from app.ap_statements_ui import render_ap_statements
        from test_ap_shared_gate import GateUi
        from app.ap_shared.access import attempt_unlock
        from test_ap_shared_access import TestLimiter
        from app.ap_shared.repository import ApStoreError
        ui=GateUi();attempt_unlock(ui.session_state,CONFIG.password,CONFIG,TestLimiter(),NOW)
        class Service:
            calls=0
            def handle(self,*args):
                self.calls+=1
                if self.calls==1:raise ApStoreError('unavailable')
                return {'statements':[]}
        service=Service();request=self.request()
        args={'config':CONFIG,'now':NOW,'service':service}
        render_ap_statements(ui,component_renderer=lambda **kw:request,**args)
        render_ap_statements(ui,component_renderer=lambda **kw:request,**args)
        self.assertEqual(service.calls,1)
        retry={**request,'attempt':1}
        render_ap_statements(ui,component_renderer=lambda **kw:retry,**args)
        self.assertEqual(service.calls,2)
        self.assertTrue(ui.session_state['_ap_shared_reply']['ok'])
        self.assertEqual(ui.session_state['_ap_shared_reply']['attempt'],1)

