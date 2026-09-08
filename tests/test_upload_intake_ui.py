import unittest
from datetime import date


class UploadIntakeUITests(unittest.TestCase):
    def test_upload_input_renderer_keeps_both_native_uploaders_visible(self):
        from app.upload_intake_ui import render_upload_inputs

        class RecordingUI:
            def __init__(self):
                self.events = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return None

            def container(self, **kwargs):
                self.events.append(("container", kwargs))
                return self

            def columns(self, widths, **kwargs):
                self.events.append(("columns", widths, kwargs))
                return [self, self]

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
        self.assertEqual(
            upload_events[0][2]["key"],
            "daily_workbook_7",
        )
        self.assertEqual(
            upload_events[1][2]["key"],
            "card_settlement_7",
        )
        self.assertEqual(upload_events[0][2]["type"], ["xlsx", "xlsm"])
        self.assertEqual(upload_events[1][2]["type"], ["xlsx", "xlsm"])
        self.assertEqual(
            result.daily_workbook,
            "selected:Upload completed SubDept workbook",
        )
        self.assertEqual(
            result.card_settlement,
            "selected:Upload Daily Card Settlement Report",
        )
        rendered_html = " ".join(
            event[1] for event in ui.events if event[0] == "markdown"
        )
        self.assertIn("Upload deposit reports", rendered_html)
        self.assertIn("Expected workbook contents", rendered_html)
        self.assertIn("Processed Net Amount", rendered_html)
        self.assertNotIn("hwfc-upload-card-number", rendered_html)
        self.assertFalse(hasattr(result, "progress_slot"))
        self.assertEqual(
            len([event for event in ui.events if event[0] == "empty"]),
            3,
        )

    def test_zero_uploads_reports_zero_of_two(self):
        from app.upload_intake_ui import upload_readiness

        self.assertEqual(
            upload_readiness(False, False),
            {
                "count": 0,
                "percent": 0,
                "label": "0 of 2 reports added",
                "action": "Continue when ready",
                "ready": False,
            },
        )

    def test_one_upload_reports_half_complete(self):
        from app.upload_intake_ui import upload_readiness

        self.assertEqual(upload_readiness(True, False)["percent"], 50)
        self.assertEqual(
            upload_readiness(True, False)["label"],
            "1 of 2 reports added",
        )

    def test_settlement_can_be_added_first_without_hiding_daily_workbook(self):
        from app.upload_intake_ui import upload_readiness

        self.assertEqual(upload_readiness(False, True)["count"], 1)

    def test_two_uploads_complete_ready_state(self):
        from app.upload_intake_ui import upload_readiness

        self.assertEqual(
            upload_readiness(True, True),
            {
                "count": 2,
                "percent": 100,
                "label": "2 of 2 reports added",
                "action": "Ready for Today’s Deposit Steps",
                "ready": True,
            },
        )

    def test_role_badges_show_detected_names_and_missing_roles_safely(self):
        from app.upload_intake_ui import workbook_role_badges_html

        markup = workbook_role_badges_html(
            [("Sales", "090326 <Sales>"), ("HASH", None)]
        )

        self.assertIn("Sales · 090326 &lt;Sales&gt;", markup)
        self.assertIn("HASH · Not detected", markup)
        self.assertNotIn("<Sales>", markup)
        self.assertIn("is-missing", markup)

    def test_file_summary_escapes_content_and_omits_unknown_date(self):
        from app.upload_intake_ui import uploaded_file_summary_html

        dated = uploaded_file_summary_html(
            'daily<script>.xlsx',
            date(2026, 9, 3),
            valid=True,
            status_text="Workbook verified",
        )
        undated = uploaded_file_summary_html(
            "settlement.xlsx",
            None,
            valid=False,
            status_text="Needs attention <now>",
        )

        self.assertNotIn("<script>", dated)
        self.assertIn("daily&lt;script&gt;.xlsx", dated)
        self.assertIn("09/03/2026", dated)
        self.assertIn("is-valid", dated)
        self.assertNotIn("Report date", undated)
        self.assertIn("Needs attention &lt;now&gt;", undated)
        self.assertNotIn("is-valid", undated)

    def test_readiness_markup_has_literal_bounded_progress_and_status(self):
        from app.upload_intake_ui import upload_readiness_html

        pending = upload_readiness_html(
            {
                "count": 1,
                "percent": 50,
                "label": "1 of 2 reports added",
                "action": "Continue when ready",
                "ready": False,
            }
        )
        ready = upload_readiness_html(
            {
                "count": 2,
                "percent": 100,
                "label": "2 of 2 reports added",
                "action": "Ready for Today’s Deposit Steps",
                "ready": True,
            }
        )

        self.assertIn("width:50%", pending)
        self.assertIn("Continue when ready", pending)
        self.assertNotIn("is-ready", pending)
        self.assertIn("width:100%", ready)
        self.assertIn("is-ready", ready)
        self.assertIn("Ready for Today’s Deposit Steps", ready)


if __name__ == "__main__":
    unittest.main()
