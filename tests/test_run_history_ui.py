import unittest
from importlib.util import find_spec


class RecordingUI:
    def __init__(self):
        self.events = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def markdown(self, body, **kwargs):
        self.events.append(("markdown", body, kwargs))

    def caption(self, body, **kwargs):
        self.events.append(("caption", body, kwargs))

    def warning(self, body, **kwargs):
        self.events.append(("warning", body, kwargs))

    def selectbox(self, label, **kwargs):
        self.events.append(("selectbox", label, kwargs))
        return kwargs["options"][0]

    def download_button(self, label, **kwargs):
        self.events.append(("download_button", label, kwargs))

    def expander(self, label, **kwargs):
        self.events.append(("expander", label, kwargs))
        return self


class RunHistoryUITests(unittest.TestCase):
    def test_run_history_is_collapsed_by_default(self):
        self.assertIsNotNone(find_spec("app.run_history_ui"))
        import app.run_history_ui as run_history_ui

        ui = RecordingUI()
        run_history_ui.render_run_history(
            ui,
            records=[
                {
                    "id": "run-1",
                    "report_date": "2026-09-04",
                    "run_at": "2026-09-08T12:22:54",
                    "status": "Passed",
                    "sales_status": "MATCH",
                    "discount_status": "MATCH",
                    "hash_status": "MATCH",
                    "iif_status": "MATCH",
                    "card_settlement_status": "MATCH",
                    "uploaded_filename": "daily.xlsx",
                    "settlement_filename": "settlement.xlsx",
                }
            ],
            option_labeler=lambda record: "09/04/2026 · Passed",
            run_time_formatter=lambda value, include_date=False: "09/08/2026 08:22 AM",
        )

        history_expanders = [event for event in ui.events if event[0] == "expander"]
        self.assertEqual(len(history_expanders), 1)
        self.assertEqual(history_expanders[0][1], "Run History")
        self.assertFalse(history_expanders[0][2]["expanded"])
        rendered_text = " ".join(
            str(event[1])
            for event in ui.events
            if event[0] in {"markdown", "caption"}
        )
        self.assertIn("Run details", rendered_text)
        self.assertIn("Files from this run", rendered_text)
        self.assertIn("daily.xlsx", rendered_text)
        self.assertIn("settlement.xlsx", rendered_text)


if __name__ == "__main__":
    unittest.main()
