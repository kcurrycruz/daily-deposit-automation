import unittest
from types import SimpleNamespace


class UploadIntakeUITests(unittest.TestCase):
    def test_validation_card_shows_six_required_roles_and_progress(self):
        from app.upload_intake_ui import render_sms_validation

        class RecordingUI:
            def __init__(self):
                self.markup = ""

            def markdown(self, body, **kwargs):
                self.markup += body

        ui = RecordingUI()
        render_sms_validation(
            ui,
            reports={"sales": SimpleNamespace(filename="sales.xls")},
            error=None,
        )

        self.assertIn("1 of 6 verified", ui.markup)
        for label in (
            "Sales",
            "Coupon",
            "Discounts",
            "HASH",
            "Balance Sheet",
            "Milk Bottles",
        ):
            self.assertIn(label, ui.markup)
        self.assertIn("sales.xls", ui.markup)

    def test_validation_card_escapes_report_names_and_shows_error(self):
        from app.upload_intake_ui import render_sms_validation

        class RecordingUI:
            def __init__(self):
                self.markup = ""

            def markdown(self, body, **kwargs):
                self.markup += body

        ui = RecordingUI()
        render_sms_validation(
            ui,
            reports={"sales": SimpleNamespace(filename="<sales>.xls")},
            error=ValueError("Missing <HASH> report"),
        )

        self.assertIn("&lt;sales&gt;.xls", ui.markup)
        self.assertIn("Missing &lt;HASH&gt; report", ui.markup)
        self.assertNotIn("<sales>.xls", ui.markup)

    def test_missing_settlement_date_warning_requires_an_otherwise_valid_report(self):
        from app.upload_intake_ui import missing_settlement_date_warning

        warning = missing_settlement_date_warning(
            settlement_file=object(),
            settlement_source_ok=True,
            settlement_date=None,
            settlement_date_error=None,
        )

        self.assertEqual(
            warning,
            "Card Settlement report date not detected—upload a report with its date.",
        )
        for changes in (
            {"settlement_file": None},
            {"settlement_source_ok": False},
            {"settlement_date_error": ValueError("unreadable")},
            {"settlement_date": object()},
        ):
            with self.subTest(changes=changes):
                self.assertIsNone(
                    missing_settlement_date_warning(
                        settlement_file=changes.get("settlement_file", object()),
                        settlement_source_ok=changes.get("settlement_source_ok", True),
                        settlement_date=changes.get("settlement_date"),
                        settlement_date_error=changes.get("settlement_date_error"),
                    )
                )

    def test_upload_row_accepts_multiple_sms_xls_files_and_card_settlement(self):
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
                return ["sms-a", "sms-b"] if "SMS" in label else "settlement"

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
                "Upload SMS reports",
                "Upload Daily Card Settlement Report",
            ],
        )
        self.assertEqual(upload_events[0][2]["key"], "sms_reports_7")
        self.assertEqual(upload_events[1][2]["key"], "card_settlement_7")
        self.assertEqual(upload_events[0][2]["type"], ["xls"])
        self.assertTrue(upload_events[0][2]["accept_multiple_files"])
        self.assertEqual(upload_events[1][2]["type"], ["xlsx", "xlsm"])
        rendered_html = " ".join(
            event[1] for event in ui.events if event[0] == "markdown"
        )
        self.assertIn("Report Date", rendered_html)
        self.assertIn("SMS Reports", rendered_html)
        self.assertIn("Card Settlement", rendered_html)
        self.assertNotIn("Upload deposit reports", rendered_html)
        date_slots = [event[1] for event in ui.events if event[0] == "empty"]
        self.assertEqual(len(date_slots), 1)
        self.assertIs(result.date_slot, date_slots[0])
        self.assertEqual(result.sms_exports, ["sms-a", "sms-b"])
        self.assertEqual(result.card_settlement, "settlement")
        self.assertIsNone(result.daily_workbook)

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

        sms_exports = [object(), object()]
        card_settlement = object()
        state = {
            DAILY_PROGRAM_UPLOADS_KEY: {
                "sms_reports_3": sms_exports,
                "card_settlement_3": card_settlement,
            }
        }

        result = render_upload_inputs(
            EmptyUploaderUI(state),
            uploader_key=3,
        )

        self.assertIs(result.sms_exports, sms_exports)
        self.assertIs(result.card_settlement, card_settlement)

    def test_empty_multi_upload_keeps_sms_reports_through_guided_and_hub_stages(self):
        from app.program_hub_ui import (
            DAILY_DEPOSITS,
            DAILY_PROGRAM_UPLOADS_KEY,
            activate_program,
            preserve_daily_program_state,
            return_to_program_hub,
        )
        from app.upload_intake_ui import render_upload_inputs, retained_upload_pair

        class EmptyMultiUploadUI:
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
                return [] if label == "Upload SMS reports" else None

        sms_exports = [object(), object()]
        state = {
            "active_finance_program": DAILY_DEPOSITS,
            "sms_reports_8": [],
            DAILY_PROGRAM_UPLOADS_KEY: {"sms_reports_8": sms_exports},
        }

        rendered = render_upload_inputs(EmptyMultiUploadUI(state), uploader_key=8)
        self.assertIs(rendered.sms_exports, sms_exports)
        preserve_daily_program_state(state)
        self.assertEqual(retained_upload_pair(state, uploader_key=8)[0], sms_exports)

        return_to_program_hub(state)
        state.pop("sms_reports_8")
        self.assertTrue(activate_program(state, DAILY_DEPOSITS))
        self.assertEqual(
            state[DAILY_PROGRAM_UPLOADS_KEY]["sms_reports_8"],
            sms_exports,
        )

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
            ("sms_reports_4", "card_settlement_4"),
        ):
            self.assertIs(kwargs["on_change"], sync_daily_upload)
            self.assertEqual(kwargs["args"], (ui.session_state, expected_key))

    def test_retained_upload_pair_reads_sms_exports_and_settlement(self):
        from app.program_hub_ui import DAILY_PROGRAM_UPLOADS_KEY
        from app.upload_intake_ui import retained_upload_pair

        sms_exports = [object(), object()]
        settlement = object()
        state = {
            DAILY_PROGRAM_UPLOADS_KEY: {
                "sms_reports_4": sms_exports,
                "card_settlement_4": settlement,
            }
        }

        self.assertEqual(
            retained_upload_pair(state, uploader_key=4),
            (sms_exports, settlement),
        )


if __name__ == "__main__":
    unittest.main()
