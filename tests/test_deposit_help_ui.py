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
    def test_sop_renderer_keeps_daily_workbook_and_card_settlement_help(self):
        from app.deposit_help_ui import render_daily_workbook_sop

        ui = RecordingUI()
        render_daily_workbook_sop(
            ui,
            root=Path("tests/nonexistent-help-assets"),
            sop_steps=[],
        )

        expander_labels = [
            event[1] for event in ui.events if event[0] == "expander"
        ]
        rendered_text = " ".join(
            str(event[1][0])
            for event in ui.events
            if event[0] == "markdown" and event[1]
        )
        self.assertIn("📘 Daily Workbook SOP", expander_labels)
        self.assertIn("View Daily Card Settlement Example", expander_labels)
        self.assertIn("How to Build the Daily Workbook", rendered_text)
        self.assertIn("Before You Run", rendered_text)

    def test_known_exceptions_renderer_keeps_operational_disclosures(self):
        from app.deposit_help_ui import render_known_exceptions

        ui = RecordingUI()
        render_known_exceptions(ui)

        expander_labels = [
            event[1] for event in ui.events if event[0] == "expander"
        ]
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
