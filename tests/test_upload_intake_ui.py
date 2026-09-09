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

    def test_preserved_uploads_are_used_without_assigning_uploader_widget_keys(self):
        from app.upload_intake_ui import render_upload_inputs
        from app.program_hub_ui import DAILY_PROGRAM_UPLOADS_KEY

        class EmptyUploaderUI:
            def __init__(self, state):
                self.session_state = state

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return None

            def columns(self, widths, **kwargs):
                return [self for _ in widths]

            def empty(self):
                return object()

            def markdown(self, body, **kwargs):
                return None

            def file_uploader(self, label, **kwargs):
                return None

        daily_workbook = object()
        card_settlement = object()
        state = {
            DAILY_PROGRAM_UPLOADS_KEY: {
                "daily_workbook_3": daily_workbook,
                "card_settlement_3": card_settlement,
            }
        }

        result = render_upload_inputs(
            EmptyUploaderUI(state),
            uploader_key=3,
        )

        self.assertIs(result.daily_workbook, daily_workbook)
        self.assertIs(result.card_settlement, card_settlement)

    def test_uploaders_wire_change_callback_with_their_own_widget_keys(self):
        from app.upload_intake_ui import render_upload_inputs
        from app.program_hub_ui import sync_daily_upload

        class CallbackRecordingUI:
            def __init__(self):
                self.uploader_calls = []
                self.session_state = {}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return None

            def columns(self, widths, **kwargs):
                return [self for _ in widths]

            def empty(self):
                return object()

            def markdown(self, body, **kwargs):
                return None

            def file_uploader(self, label, **kwargs):
                self.uploader_calls.append((label, kwargs))
                return None

        ui = CallbackRecordingUI()
        render_upload_inputs(
            ui,
            uploader_key=4,
        )

        self.assertEqual(len(ui.uploader_calls), 2)
        for (_, kwargs), expected_key in zip(
            ui.uploader_calls,
            ("daily_workbook_4", "card_settlement_4"),
        ):
            self.assertIs(kwargs["on_change"], sync_daily_upload)
            self.assertEqual(kwargs["args"], (ui.session_state, expected_key))

    def test_retained_upload_pair_reads_both_preserved_widget_values(self):
        from app.program_hub_ui import DAILY_PROGRAM_UPLOADS_KEY
        from app.upload_intake_ui import retained_upload_pair

        daily = object()
        settlement = object()
        state = {
            DAILY_PROGRAM_UPLOADS_KEY: {
                "daily_workbook_4": daily,
                "card_settlement_4": settlement,
            }
        }

        self.assertEqual(
            retained_upload_pair(state, uploader_key=4),
            (daily, settlement),
        )


if __name__ == "__main__":
    unittest.main()
