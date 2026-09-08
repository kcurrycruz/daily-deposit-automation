import unittest


class RecordingUI:
    def __init__(self):
        self.events = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def tabs(self, labels):
        self.events.append(("tabs", labels))
        return [self for _ in labels]

    def expander(self, label, **kwargs):
        self.events.append(("expander", label, kwargs))
        return self

    def markdown(self, body, **kwargs):
        self.events.append(("markdown", body, kwargs))

    def caption(self, body, **kwargs):
        self.events.append(("caption", body, kwargs))


class DepositHelpUITests(unittest.TestCase):
    def test_sidebar_help_is_static_and_documents_current_workflow(self):
        import app.deposit_help_ui as deposit_help_ui

        renderer = getattr(deposit_help_ui, "render_sidebar_help", None)
        self.assertIsNotNone(renderer)

        ui = RecordingUI()
        renderer(ui)

        self.assertEqual(
            [event[1] for event in ui.events if event[0] == "tabs"],
            [["Daily Workbook", "Tips & Exceptions"]],
        )
        self.assertFalse(any(event[0] == "expander" for event in ui.events))
        rendered_text = " ".join(
            str(event[1])
            for event in ui.events
            if event[0] in {"markdown", "caption"}
        )
        self.assertIn("Need Help?", rendered_text)
        self.assertIn("Processed Net Amount", rendered_text)
        self.assertIn("HASH", rendered_text)
        self.assertIn("Books", rendered_text)
        self.assertIn("CDTA Star Pass", rendered_text)
        self.assertIn("TBA", rendered_text)
        self.assertIn("Paid In", rendered_text)
        self.assertIn("Paid Out", rendered_text)
        self.assertIn("Closeout Sheet", rendered_text)


if __name__ == "__main__":
    unittest.main()
