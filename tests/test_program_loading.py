"""Exercise the production routing block with Streamlit's callback lifecycle."""
from pathlib import Path
import unittest


class ProgramLoadingTests(unittest.TestCase):
    def test_callbacks_open_each_program_without_rendering_the_hub_again(self):
        from streamlit.testing.v1 import AppTest
        from app.program_hub_ui import ACTIVE_PROGRAM_KEY

        source = (Path(__file__).resolve().parents[1] / 'streamlit_app.py').read_text(encoding='utf-8')
        route = source[source.index('selected_program = normalize_program_selection('):
                       source.index('restore_daily_program_state(st.session_state)')]
        setup = '''
import streamlit as st
from app.program_hub_ui import (
    ACTIVE_PROGRAM_KEY, DAILY_DEPOSITS, AP_STATEMENTS, activate_program,
    normalize_program_selection, render_program_transition, return_to_program_hub,
    render_program_hub as actual_hub,
)
st.set_page_config(page_title='Program routing test')
render_program_transition(st)
st.session_state.setdefault('retained_work', {'amount': 123})
def render_program_hub(ui):
    ui.session_state.hub_renders = ui.session_state.get('hub_renders', 0) + 1
    return actual_hub(ui)
def render_ap_statements(ui):
    ui.title('AP password screen')
    return ui.button('Back to programs', key='test_back_ap')
'''
        daily = '''
st.title('Daily Deposits ready')
st.button('Back to programs', key='test_back_daily', on_click=return_to_program_hub, args=(st.session_state,))
'''
        for key, title in [('daily_deposits', 'Daily Deposits ready'), ('ap_statements', 'AP password screen')]:
            with self.subTest(program=key):
                app = AppTest.from_string(setup + route + daily).run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state['hub_renders'], 1)
                app.button(key='open_program_' + key).click().run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state[ACTIVE_PROGRAM_KEY], key)
                self.assertEqual(app.session_state['hub_renders'], 1)
                self.assertIn(title, [node.value for node in app.title])
                self.assertEqual(app.session_state['retained_work'], {'amount': 123})
                loading = [node.value for node in app.markdown if 'id="hwfc-program-loader"' in node.value]
                self.assertEqual(len(loading), 1)
                self.assertIn('data-program-opening="true"', loading[0])
                app.run()
                loading = [node.value for node in app.markdown if 'id="hwfc-program-loader"' in node.value]
                self.assertNotIn('data-program-opening="true"', loading[0])
                app.button(key='test_back_' + ('ap' if key == 'ap_statements' else 'daily')).click().run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state['hub_renders'], 2)
                self.assertEqual(app.session_state['retained_work'], {'amount': 123})


if __name__ == '__main__':
    unittest.main()
