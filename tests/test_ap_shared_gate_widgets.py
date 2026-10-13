import unittest
from streamlit.testing.v1 import AppTest

SCRIPT='''
import streamlit as st
from datetime import datetime, timezone
from uuid import uuid4
from app.ap_shared.models import ApConfig
from app.ap_statements_ui import render_ap_statements
class Limiter:
    def begin_attempt(self, *args): return str(uuid4())
    def finish_attempt(self, *args): pass
config=ApConfig('SYNTHETIC-PASSWORD','https://synthetic.supabase.co','SYNTHETIC-KEY',
                '00000000-0000-4000-8000-000000000001','hwfc-ap-private')
st.session_state.setdefault('synthetic_calls',0)
def component(**kwargs): st.session_state.synthetic_calls+=1
render_ap_statements(st,config=config,limiter=Limiter(),component_renderer=component)
'''

class GateWidgetTests(unittest.TestCase):
    def test_real_form_wrong_and_correct_password_and_lock(self):
        app=AppTest.from_string(SCRIPT).run(timeout=20)
        self.assertEqual(len(app.exception),0)
        self.assertEqual(app.session_state['synthetic_calls'],0)
        app.text_input(key='_ap_password').set_value('WRONG')
        next(b for b in app.button if b.label=='Open AP Statements').click().run()
        self.assertEqual(len(app.exception),0); self.assertEqual(app.session_state['synthetic_calls'],0)
        app.text_input(key='_ap_password').set_value('SYNTHETIC-PASSWORD')
        next(b for b in app.button if b.label=='Open AP Statements').click().run()
        self.assertEqual(len(app.exception),0); self.assertEqual(app.session_state['synthetic_calls'],1)
        app.button(key='ap_lock_access').click().run()
        self.assertEqual(len(app.exception),0); self.assertEqual(app.session_state['synthetic_calls'],1)
        self.assertEqual(app.text_input(key='_ap_password').value,'')

if __name__=='__main__': unittest.main()
