import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class RecordingUi:
    def __init__(self):
        self.session_state = {"active_finance_program": "ap_statements", "run_result": "retained"}
        self.clicked = set()
        self.messages = []
        self.errors = []

    def title(self, text):
        self.messages.append(text)

    def caption(self, text):
        self.messages.append(text)

    def warning(self, text):
        self.messages.append(text)

    def error(self, text):
        self.errors.append(text)

    def button(self, text, **kwargs):
        self.messages.append(text)
        return kwargs.get("key") in self.clicked


class ApRendererTests(unittest.TestCase):
    def test_stable_component_key_and_privacy_guidance_without_financial_inputs(self):
        from app.ap_statements_ui import render_ap_statements
        ui, calls = RecordingUi(), []
        renderer = lambda **kwargs: calls.append(kwargs)
        self.assertFalse(render_ap_statements(ui, component_renderer=renderer))
        self.assertFalse(render_ap_statements(ui, component_renderer=renderer))
        self.assertEqual(calls, [{"key": "hwfc_ap_statements_workspace"}] * 2)
        text = " ".join(ui.messages)
        for phrase in ["AP Statements", "browser profile", "original PDFs", "Save session", "BILL"]:
            self.assertIn(phrase, text)
        self.assertEqual(ui.session_state["run_result"], "retained")

    def test_exit_requires_confirmation_stay_keeps_workspace_leave_returns_true(self):
        from app.ap_statements_ui import render_ap_statements
        ui = RecordingUi()
        renderer = lambda **kwargs: None
        ui.clicked = {"ap_all_programs"}
        self.assertFalse(render_ap_statements(ui, component_renderer=renderer))
        self.assertIn("ap_statements", ui.session_state.values())
        self.assertIn("export", " ".join(ui.messages))
        ui.clicked = {"ap_stay"}
        self.assertFalse(render_ap_statements(ui, component_renderer=renderer))
        ui.clicked = {"ap_all_programs"}
        self.assertFalse(render_ap_statements(ui, component_renderer=renderer))
        ui.clicked = {"ap_leave"}
        self.assertTrue(render_ap_statements(ui, component_renderer=renderer))
        self.assertEqual(ui.session_state["run_result"], "retained")

    def test_missing_build_shows_error_and_navigation_without_rendering_component(self):
        from app.ap_statements_ui import render_ap_statements
        ui, calls = RecordingUi(), []
        with TemporaryDirectory() as folder:
            ui.clicked = {"ap_all_programs"}
            self.assertFalse(render_ap_statements(ui, component_renderer=lambda **kw: calls.append(kw), frontend_path=Path(folder)))
            ui.clicked = {"ap_leave"}
            self.assertTrue(render_ap_statements(ui, component_renderer=lambda **kw: calls.append(kw), frontend_path=Path(folder)))
        self.assertEqual(calls, [])
        self.assertTrue(ui.errors)

    def test_default_component_declaration_uses_local_path(self):
        from app.ap_statements_ui import ap_frontend_path
        self.assertTrue((ap_frontend_path() / "index.html").is_file())

    def test_ap_route_precedes_daily_guard_and_stops_before_daily_ui(self):
        source = (Path(__file__).resolve().parents[1] / "streamlit_app.py").read_text(encoding="utf-8")
        start = source.index("if selected_program == AP_STATEMENTS:")
        end = source.index("if selected_program != DAILY_DEPOSITS:", start)
        route = source[start:end]
        self.assertIn("render_ap_statements(st)", route)
        self.assertIn("return_to_program_hub(st.session_state)", route)
        self.assertIn("st.rerun()", route)
        self.assertTrue(route.strip().endswith("st.stop()"))
        self.assertNotIn("reset", route)
        self.assertNotIn("restore_daily_program_state", route)

    def test_daily_hub_ap_hub_daily_preserves_upload_widgets_stage_and_results(self):
        from app.program_hub_ui import (AP_STATEMENTS, DAILY_DEPOSITS, activate_program,
            preserve_daily_program_state, preserved_daily_upload, restore_daily_program_state, return_to_program_hub)
        from app.deposit_page_flow import DEPOSIT_PAGE_STAGE_KEY, DEPOSIT_STEPS_STAGE
        upload, result = object(), {"rows": 12}
        state = {"active_finance_program": DAILY_DEPOSITS, "daily_workbook_0": upload,
            "membership_example_amount": 8.45, DEPOSIT_PAGE_STAGE_KEY: DEPOSIT_STEPS_STAGE,
            "run_result": result, "daily_completed": True}
        preserve_daily_program_state(state)
        return_to_program_hub(state)
        state.pop("daily_workbook_0")
        state.pop("membership_example_amount")
        self.assertTrue(activate_program(state, AP_STATEMENTS))
        return_to_program_hub(state)
        self.assertTrue(activate_program(state, DAILY_DEPOSITS))
        restore_daily_program_state(state)
        self.assertIs(preserved_daily_upload(state, "daily_workbook_0"), upload)
        self.assertEqual(state["membership_example_amount"], 8.45)
        self.assertEqual(state[DEPOSIT_PAGE_STAGE_KEY], DEPOSIT_STEPS_STAGE)
        self.assertIs(state["run_result"], result)
        self.assertTrue(state["daily_completed"])
