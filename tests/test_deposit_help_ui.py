import unittest
from pathlib import Path


class RecordingUI:
    def __init__(self):
        self.events = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def expander(self, label, **kwargs):
        self.events.append(("expander", label, kwargs))
        return self

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.events.append((name, args, kwargs))
            return False

        return record


class DepositHelpUITests(unittest.TestCase):
    def test_hub_stop_boundary_precedes_help_and_start_over(self):
        app_source = (
            Path(__file__).resolve().parents[1] / "streamlit_app.py"
        ).read_text(encoding="utf-8")

        route_marker = "selected_program = normalize_program_selection("
        self.assertIn(route_marker, app_source)
        route_position = app_source.index(route_marker)
        hero_position = app_source.index(
            '<div class="hwfc-title">Daily Deposit Reconciliation</div>'
        )
        hub_stop_position = route_position + app_source[
            route_position:hero_position
        ].index("st.stop()")

        self.assertLess(hub_stop_position, app_source.index("render_need_help_label(st)"))
        self.assertLess(hub_stop_position, app_source.index('"↻ Start Over"'))

    def test_upload_help_status_and_inputs_are_owned_by_upload_stage(self):
        source = self.app_source()
        upload_stage_marker = "if requested_page_stage == UPLOAD_STAGE:"
        continue_marker = "render_upload_continue_action("
        guide_marker = "if deposit_page_stage == DEPOSIT_STEPS_STAGE:"

        self.assertIn(upload_stage_marker, source)
        self.assertIn(continue_marker, source)
        self.assertIn(guide_marker, source)
        self.assertLess(source.index(upload_stage_marker), source.index(continue_marker))
        self.assertLess(source.index(continue_marker), source.index(guide_marker))

    @staticmethod
    def app_source():
        return (
            Path(__file__).resolve().parents[1] / "streamlit_app.py"
        ).read_text(encoding="utf-8")

    def test_help_and_start_over_are_at_the_top_before_the_step_bar(self):
        app_source = (
            Path(__file__).resolve().parents[1] / "streamlit_app.py"
        ).read_text(encoding="utf-8")

        help_position = app_source.index("render_need_help_label(st)")
        start_over_position = app_source.index('"↻ Start Over"')
        sop_position = app_source.index("render_daily_workbook_sop(st")
        tips_position = app_source.index("render_known_exceptions(st)")
        step_bar_position = app_source.index('<div class="hwfc-stepbar">')

        self.assertLess(help_position, step_bar_position)
        self.assertLess(start_over_position, step_bar_position)
        self.assertLess(sop_position, step_bar_position)
        self.assertLess(tips_position, step_bar_position)

    def test_need_help_is_a_static_label(self):
        from app.deposit_help_ui import render_need_help_label

        ui = RecordingUI()
        render_need_help_label(ui)

        self.assertFalse(any(event[0] == "button" for event in ui.events))
        rendered_text = " ".join(
            str(event[1][0])
            for event in ui.events
            if event[0] == "markdown" and event[1]
        )
        self.assertIn("Need Help", rendered_text)

    def test_sop_renderer_keeps_original_steps_and_pictures(self):
        from app.deposit_help_ui import render_daily_workbook_sop

        ui = RecordingUI()
        render_daily_workbook_sop(
            ui,
            root=Path(__file__).resolve().parents[1],
            sop_steps=[
                {"title": "Step 1 · Start", "body": "Open the template."},
                {"title": "Step 2 · Sales", "body": "Paste the sales report."},
            ],
        )

        expander_labels = [event[1] for event in ui.events if event[0] == "expander"]
        image_paths = [str(event[1][0]) for event in ui.events if event[0] == "image"]
        rendered_text = " ".join(
            str(event[1][0])
            for event in ui.events
            if event[0] == "markdown" and event[1]
        )

        self.assertIn("📘 Daily Workbook SOP", expander_labels)
        self.assertIn("Step 1 · Start", expander_labels)
        self.assertIn("Step 2 · Sales", expander_labels)
        self.assertIn("View Daily Card Settlement Example", expander_labels)
        self.assertTrue(any(path.endswith("step1_daily_deposit_folder.png") for path in image_paths))
        self.assertTrue(any(path.endswith("step2a_sms_sales_export.png") for path in image_paths))
        self.assertTrue(any(path.endswith("step2a_subdept_single_paste.png") for path in image_paths))
        self.assertTrue(any(path.endswith("daily_card_settlement_example.png") for path in image_paths))
        self.assertIn("How to Build the Daily Workbook", rendered_text)
        self.assertIn("Before You Run", rendered_text)

    def test_known_exceptions_renderer_keeps_original_operational_guidance(self):
        from app.deposit_help_ui import render_known_exceptions

        ui = RecordingUI()
        render_known_exceptions(ui)

        expander_labels = [event[1] for event in ui.events if event[0] == "expander"]
        rendered_text = " ".join(
            str(event[1][0])
            for event in ui.events
            if event[0] == "markdown" and event[1]
        )
        self.assertIn("💡 Tips & Known Exceptions · WIP", expander_labels)
        self.assertIn("Unique / unrecognized items", rendered_text)
        self.assertIn("Automation Does Not Replace Final Review", rendered_text)
        self.assertIn("Future tips to document", rendered_text)


if __name__ == "__main__":
    unittest.main()
