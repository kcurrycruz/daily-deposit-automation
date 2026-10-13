import unittest
from pathlib import Path


class RecordingUi:
    def __init__(self):
        self.session_state = {"active_finance_program": "ap_statements", "run_result": "retained"}
        self.clicked = set()
        self.messages = []
        self.errors = []
        self.blocks = []
        self.button_calls = []
        from datetime import datetime, timezone
        from dataclasses import asdict
        from test_ap_shared_access import CONFIG, TestLimiter
        from app.ap_shared.access import attempt_unlock
        self.secrets = {"ap": asdict(CONFIG)}
        attempt_unlock(self.session_state, CONFIG.password, CONFIG, TestLimiter(), datetime.now(timezone.utc))

    def container(self):
        self.blocks.append("confirmation")
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def title(self, text):
        self.messages.append(text)

    def caption(self, text):
        self.messages.append(text)

    def markdown(self, text, **kwargs):
        self.messages.append(text)

    def warning(self, text):
        self.messages.append(text)

    def error(self, text):
        self.errors.append(text)

    def button(self, text, **kwargs):
        self.button_calls.append(kwargs)
        self.messages.append(text)
        return kwargs.get("key") in self.clicked


class ApRendererTests(unittest.TestCase):
    def test_confirmation_always_has_a_reserved_block_before_component(self):
        from app.ap_statements_ui import render_ap_statements
        ui, positions = RecordingUi(), []
        def component(**kwargs):
            positions.append(tuple(ui.blocks))
        render_ap_statements(ui, component_renderer=component)
        ui.blocks = []
        ui.session_state["_ap_exit_confirmation"] = True
        render_ap_statements(ui, component_renderer=component)
        self.assertEqual(positions, [("confirmation",), ("confirmation",)])

    def test_stable_component_key_and_privacy_guidance_without_financial_inputs(self):
        from app.ap_statements_ui import render_ap_statements
        ui, calls = RecordingUi(), []
        renderer = lambda **kwargs: calls.append(kwargs)
        self.assertFalse(render_ap_statements(ui, component_renderer=renderer))
        self.assertFalse(render_ap_statements(ui, component_renderer=renderer))
        self.assertEqual(calls, [{"key": "hwfc_ap_statements_workspace"}] * 2)
        text = " ".join(ui.messages)
        for phrase in ["browser profile", "original PDFs", "Save session", "BILL"]:
            self.assertIn(phrase, text)
        self.assertEqual(ui.session_state["run_result"], "retained")
        self.assertEqual([call['key'] for call in ui.button_calls], ['ap_lock_access', 'ap_lock_access'])
        self.assertNotIn("AP Statements", ui.messages)

    def test_confirmed_sidebar_exit_returns_to_hub_without_changing_daily_results(self):
        from app.ap_statements_ui import render_ap_statements
        ui = RecordingUi()
        request = {"action": "return_to_programs", "request_id": "00000000-0000-4000-8000-000000000001"}
        self.assertTrue(render_ap_statements(ui, component_renderer=lambda **kw: request))
        self.assertEqual(ui.session_state["run_result"], "retained")

    def test_consumed_sidebar_request_does_not_exit_reopened_ap(self):
        from app.ap_statements_ui import render_ap_statements
        ui = RecordingUi()
        request = {"action": "return_to_programs", "request_id": "00000000-0000-4000-8000-000000000001"}
        self.assertTrue(render_ap_statements(ui, component_renderer=lambda **kw: request))
        self.assertFalse(render_ap_statements(ui, component_renderer=lambda **kw: request))
        next_request = {"action": "return_to_programs", "request_id": "00000000-0000-4000-8000-000000000002"}
        self.assertTrue(render_ap_statements(ui, component_renderer=lambda **kw: next_request))

    def test_component_financial_or_unknown_values_cannot_navigate(self):
        from app.ap_statements_ui import render_ap_statements
        for value in (None, True, "unknown", "return_to_programs",
                      {"action": "return_to_programs", "invoices": []},
                      {"action": "return_to_programs", "request_id": "invoice-data"},
                      {"action": "return_to_programs", "request_id": "00000000-0000-4000-8000-000000000001", "invoices": []}):
            with self.subTest(value=value):
                ui = RecordingUi()
                self.assertFalse(render_ap_statements(ui, component_renderer=lambda **kw: value))
                self.assertEqual(ui.session_state["active_finance_program"], "ap_statements")

    def test_exit_requires_confirmation_stay_keeps_workspace_leave_returns_true(self):
        from app.ap_statements_ui import render_ap_statements
        ui = RecordingUi()
        missing_path = Path(__file__).resolve().parent / "nonexistent-ap-build"
        renderer = lambda **kwargs: None
        ui.clicked = {"ap_all_programs"}
        self.assertFalse(render_ap_statements(ui, component_renderer=renderer, frontend_path=missing_path))
        self.assertIn("ap_statements", ui.session_state.values())
        self.assertIn("export", " ".join(ui.messages))
        ui.clicked = {"ap_stay"}
        self.assertFalse(render_ap_statements(ui, component_renderer=renderer, frontend_path=missing_path))
        ui.clicked = {"ap_all_programs"}
        self.assertFalse(render_ap_statements(ui, component_renderer=renderer, frontend_path=missing_path))
        ui.clicked = {"ap_leave"}
        self.assertTrue(render_ap_statements(ui, component_renderer=renderer, frontend_path=missing_path))
        self.assertEqual(ui.session_state["run_result"], "retained")

    def test_missing_build_shows_error_and_navigation_without_rendering_component(self):
        from app.ap_statements_ui import render_ap_statements
        ui, calls = RecordingUi(), []
        missing_path = Path(__file__).resolve().parent / "nonexistent-ap-build"
        self.assertFalse(missing_path.exists())
        ui.clicked = {"ap_all_programs"}
        self.assertFalse(render_ap_statements(ui, component_renderer=lambda **kw: calls.append(kw), frontend_path=missing_path))
        ui.clicked = {"ap_leave"}
        self.assertTrue(render_ap_statements(ui, component_renderer=lambda **kw: calls.append(kw), frontend_path=missing_path))
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
        uploads, settlement, result = [object(), object()], object(), {"rows": 12}
        state = {"active_finance_program": DAILY_DEPOSITS, "sms_reports_0": uploads,
            "card_settlement_0": settlement,
            "membership_example_amount": 8.45, DEPOSIT_PAGE_STAGE_KEY: DEPOSIT_STEPS_STAGE,
            "run_result": result, "daily_completed": True}
        preserve_daily_program_state(state)
        return_to_program_hub(state)
        state.pop("sms_reports_0")
        state.pop("card_settlement_0")
        state.pop("membership_example_amount")
        self.assertTrue(activate_program(state, AP_STATEMENTS))
        return_to_program_hub(state)
        self.assertTrue(activate_program(state, DAILY_DEPOSITS))
        restore_daily_program_state(state)
        self.assertIs(preserved_daily_upload(state, "sms_reports_0"), uploads)
        self.assertIs(preserved_daily_upload(state, "card_settlement_0"), settlement)
        self.assertEqual(state["membership_example_amount"], 8.45)
        self.assertEqual(state[DEPOSIT_PAGE_STAGE_KEY], DEPOSIT_STEPS_STAGE)
        self.assertIs(state["run_result"], result)
        self.assertTrue(state["daily_completed"])
