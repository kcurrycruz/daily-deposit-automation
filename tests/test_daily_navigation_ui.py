import unittest
from importlib.util import find_spec


# Real Streamlit interactions: opening must not leave, cancel must not clear
# work, and confirmation must use the existing preserve/restore route once.
SCRIPT = '''
import streamlit as st
from app.run_history_ui import render_daily_sidebar
from app.program_hub_ui import (
    ACTIVE_PROGRAM_KEY, DAILY_DEPOSITS, preserve_daily_program_state,
    restore_daily_program_state, return_to_program_hub,
)
if not st.session_state.get("test_initialized"):
    st.session_state[ACTIVE_PROGRAM_KEY] = DAILY_DEPOSITS
    st.session_state["test_initialized"] = True
    st.session_state["run_result"] = {"iif_bytes": b"synthetic IIF", "total": 123.45}
    st.session_state["daily_deposit_page_stage"] = "deposit_steps"
if st.session_state.get(ACTIVE_PROGRAM_KEY) == DAILY_DEPOSITS:
    restore_daily_program_state(st.session_state)
    with st.sidebar:
        leave = render_daily_sidebar(st, records=[], option_labeler=str, run_time_formatter=str)
    if leave:
        preserve_daily_program_state(st.session_state)
        return_to_program_hub(st.session_state)
        st.rerun()
    st.text_input("Review note", key="closeout_test_note")
    st.write("Daily workspace")
else:
    st.write("Programs workspace")
    if st.button("Reopen Daily"):
        st.session_state[ACTIVE_PROGRAM_KEY] = DAILY_DEPOSITS
        st.rerun()
'''


@unittest.skipUnless(find_spec("streamlit"), "Streamlit UI runtime required")
class DailyNavigationTests(unittest.TestCase):
    def setUp(self):
        from streamlit.testing.v1 import AppTest
        self.app = AppTest.from_string(SCRIPT).run()
        self.app.text_input[0].input("Synthetic review note").run()

    def click(self, key):
        self.app.button(key=key).click().run()
        self.assertEqual(len(self.app.exception), 0)

    def assert_work_preserved(self):
        self.assertEqual(self.app.session_state["run_result"], {"iif_bytes": b"synthetic IIF", "total": 123.45})
        self.assertEqual(self.app.session_state["daily_deposit_page_stage"], "deposit_steps")
        self.assertEqual(self.app.text_input[0].value, "Synthetic review note")

    def test_opening_return_dialog_stays_in_daily_and_preserves_work(self):
        self.click("return_to_program_hub")
        self.assertIn("active_finance_program", self.app.session_state)
        self.assertEqual(self.app.session_state["active_finance_program"], "daily_deposits")
        self.assert_work_preserved()
        self.assertIn("Go back to programs", [b.label for b in self.app.button])

    def test_cancel_keeps_daily_work_and_closes_dialog(self):
        self.click("return_to_program_hub")
        self.click("daily_return_cancel")
        self.assertEqual(self.app.session_state["active_finance_program"], "daily_deposits")
        self.assert_work_preserved()
        self.assertNotIn("Go back to programs", [b.label for b in self.app.button])

    def test_confirm_returns_once_and_reentry_restores_review_note(self):
        self.click("return_to_program_hub")
        self.click("daily_return_confirm")
        self.assertNotIn("active_finance_program", self.app.session_state)
        self.app.button[0].click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assert_work_preserved()
        self.app.run()
        self.assertEqual(self.app.session_state["active_finance_program"], "daily_deposits")
        self.assertNotIn("Go back to programs", [b.label for b in self.app.button])


if __name__ == "__main__":
    unittest.main()
