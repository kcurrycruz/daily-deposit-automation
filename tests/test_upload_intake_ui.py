import unittest


class UploadIntakeUITests(unittest.TestCase):
    def test_upload_renderer_uses_compact_horizontal_layout_with_date_detector(self):
        from app.upload_intake_ui import render_upload_inputs

        class RecordingUI:
            def __init__(self):
                self.events = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return None

            def columns(self, widths, **kwargs):
                self.events.append(("columns", widths, kwargs))
                return [self for _ in widths]

            def container(self, **kwargs):
                self.events.append(("container", kwargs))
                return self

            def empty(self):
                slot = object()
                self.events.append(("empty", slot))
                return slot

            def markdown(self, body, **kwargs):
                self.events.append(("markdown", body, kwargs))

            def file_uploader(self, label, **kwargs):
                self.events.append(("file_uploader", label, kwargs))
                return f"selected:{label}"

        ui = RecordingUI()
        result = render_upload_inputs(ui, uploader_key=7)

        self.assertEqual(
            [event for event in ui.events if event[0] == "columns"],
            [("columns", [0.22, 0.39, 0.39], {"gap": "medium"})],
        )
        upload_events = [
            event for event in ui.events if event[0] == "file_uploader"
        ]
        self.assertEqual(
            [event[1] for event in upload_events],
            [
                "Upload completed SubDept workbook",
                "Upload Daily Card Settlement Report",
            ],
        )
        self.assertEqual(upload_events[0][2]["key"], "daily_workbook_7")
        self.assertEqual(upload_events[1][2]["key"], "card_settlement_7")
        self.assertEqual(upload_events[0][2]["type"], ["xlsx", "xlsm"])
        self.assertEqual(upload_events[1][2]["type"], ["xlsx", "xlsm"])
        rendered_html = " ".join(
            event[1] for event in ui.events if event[0] == "markdown"
        )
        self.assertIn("Report date", rendered_html)
        self.assertIn("Daily workbook", rendered_html)
        self.assertIn("Card settlement", rendered_html)
        self.assertNotIn("Upload deposit reports", rendered_html)
        date_slots = [event[1] for event in ui.events if event[0] == "empty"]
        self.assertEqual(len(date_slots), 1)
        self.assertIs(result.date_slot, date_slots[0])
        self.assertEqual(
            result.daily_workbook,
            "selected:Upload completed SubDept workbook",
        )
        self.assertEqual(
            result.card_settlement,
            "selected:Upload Daily Card Settlement Report",
        )


if __name__ == "__main__":
    unittest.main()
