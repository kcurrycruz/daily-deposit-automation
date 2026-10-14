import unittest
from datetime import timedelta
from test_ap_statements_ui import RecordingUi
from test_ap_shared_access import CONFIG, NOW, TestLimiter

class GateUi(RecordingUi):
    def __init__(self):
        super().__init__(); self.submitted=False; self.password=''; self.reran=False
        self.form_calls=[]; self.submit_calls=[]; self.container_calls=[]
        self.secrets={}
        self.session_state.pop('_ap_authorization',None)
    def container(self,**kwargs): self.container_calls.append(kwargs); return self
    def form(self,*args,**kwargs): self.form_calls.append((args,kwargs)); return self
    def text_input(self,*args,**kwargs): return self.password
    def form_submit_button(self,*args,**kwargs): self.submit_calls.append((args,kwargs)); return self.submitted
    def rerun(self): self.reran=True

class GateTests(unittest.TestCase):
    def test_locked_gate_is_branded_and_has_native_full_width_primary_form(self):
        from app.ap_statements_ui import render_ap_statements
        ui=GateUi(); calls=[]
        render_ap_statements(ui,component_renderer=lambda **kw:calls.append(kw),config=CONFIG,now=NOW)
        self.assertIn({'key':'ap_unlock_card'},ui.container_calls)
        self.assertIn('alt="Honest Weight Food Co-op logo"',' '.join(ui.messages))
        self.assertIn('Unlock AP Statements',ui.messages)
        self.assertEqual(ui.submit_calls[0][1],{'type':'primary','use_container_width':True})
        self.assertEqual(ui.form_calls[0],(('ap_unlock',),{'clear_on_submit':True}))
        self.assertIn('← Back to programs',ui.messages)
        self.assertEqual(calls,[])

    def test_locked_gate_back_does_not_attempt_unlock_or_touch_daily_results(self):
        from app.ap_statements_ui import render_ap_statements
        ui=GateUi(); ui.clicked={'ap_gate_back'}
        self.assertTrue(render_ap_statements(ui,config=CONFIG,now=NOW))
        self.assertEqual(ui.session_state['run_result'],'retained')
        self.assertNotIn('_ap_authorization',ui.session_state)

    def test_missing_configuration_never_declares_financial_component(self):
        from app.ap_statements_ui import render_ap_statements
        ui=GateUi(); calls=[]
        render_ap_statements(ui,component_renderer=lambda **kw:calls.append(kw))
        self.assertEqual(calls,[]); self.assertTrue(ui.errors)
        self.assertEqual(ui.session_state['run_result'],'retained')

    def test_locked_or_wrong_password_cannot_render_financial_component(self):
        from app.ap_statements_ui import render_ap_statements
        ui=GateUi(); calls=[]; ui.submitted=True; ui.password='WRONG'
        render_ap_statements(ui,component_renderer=lambda **kw:calls.append(kw),config=CONFIG,limiter=TestLimiter(),now=NOW)
        self.assertEqual(calls,[]); self.assertNotIn('_ap_authorization',ui.session_state)

    def test_gate_back_navigation_preserves_daily(self):
        from app.ap_statements_ui import render_ap_statements
        ui=GateUi(); ui.clicked={'ap_gate_back'}
        self.assertTrue(render_ap_statements(ui,component_renderer=lambda **kw:None))
        self.assertEqual(ui.session_state['run_result'],'retained')

    def test_correct_password_requires_new_authorized_render_and_lock_ends_access(self):
        from app.ap_statements_ui import render_ap_statements
        ui=GateUi(); ui.password=CONFIG.password; ui.submitted=True; calls=[]
        kwargs={'component_renderer':lambda **kw:calls.append(kw),'config':CONFIG,'limiter':TestLimiter(),'now':NOW}
        render_ap_statements(ui,**kwargs)
        self.assertEqual(calls,[]); self.assertTrue(ui.reran)
        ui.submitted=False; render_ap_statements(ui,**kwargs); self.assertEqual(len(calls),1)
        ui.clicked={'ap_lock_access'}; render_ap_statements(ui,**kwargs)
        self.assertEqual(len(calls),1); self.assertNotIn('_ap_authorization',ui.session_state)

    def test_expired_session_is_locked_before_rendering(self):
        from app.ap_shared.access import attempt_unlock
        from app.ap_statements_ui import render_ap_statements
        ui=GateUi(); attempt_unlock(ui.session_state,CONFIG.password,CONFIG,TestLimiter(),NOW); calls=[]
        render_ap_statements(ui,component_renderer=lambda **kw:calls.append(kw),config=CONFIG,limiter=TestLimiter(),now=NOW+timedelta(hours=8))
        self.assertEqual(calls,[])

if __name__=='__main__': unittest.main()
