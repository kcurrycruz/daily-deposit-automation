import io
import json
import unittest
from datetime import date
from types import SimpleNamespace
from zipfile import ZipFile

from openpyxl import Workbook

from app.deposit_page_flow import DEPOSIT_STEPS_STAGE, DEPOSIT_PAGE_STAGE_KEY
from app.deposit_workflow import active_deposit_step
from app.program_hub_ui import DAILY_PROGRAM_UPLOADS_KEY


class DepositDraftTests(unittest.TestCase):
    def setUp(self):
        self.old_key = "membership_payments_0_0123456789abcdef"
        self.sms = [
            SimpleNamespace(name=f"092526 {role}.xls", getvalue=lambda role=role: role.encode())
            for role in ("Sales", "Coupon", "Discount", "Hash", "BS", "milk bottles")
        ]
        self.settlement = SimpleNamespace(
            name="092526 Card Settlement.xlsx", getvalue=lambda: b"settlement"
        )
        self.state = {
            f"deposit_required_steps_{self.old_key}": ("inhouse_charges", "closeout"),
            f"deposit_step_completions_{self.old_key}": {"inhouse_charges": "app"},
            f"inhouse_ids_{self.old_key}": ["row-a", "row-b"],
            f"inhouse_account_{self.old_key}_row-a": "8504000 · Education",
            f"inhouse_memo_type_{self.old_key}_row-a": "Custom",
            f"inhouse_memo_value_{self.old_key}_row-a": "Staff class",
            f"inhouse_amount_{self.old_key}_row-a": 4.75,
            f"activity_row_ids_donation_{self.old_key}": ["donation-a"],
            f"activity_row_ids_paid_out_{self.old_key}": ["row-z"],
            "activity_donation_donation-a_given_to": "Food Pantry",
            "activity_paid_out_row-z_date": date(2026, 9, 20),
            "run_result": {"should_not": "be saved"},
        }

    def make_draft(self):
        from app.deposit_draft import create_deposit_draft

        return create_deposit_draft(
            self.sms,
            self.settlement,
            self.state,
            workbook_key=self.old_key,
            deposit_date=date(2026, 9, 25),
        )

    def test_round_trip_preserves_sources_completed_steps_and_unsaved_rows(self):
        from app.deposit_draft import read_deposit_draft

        draft = read_deposit_draft(self.make_draft())

        self.assertEqual(draft.deposit_date, date(2026, 9, 25))
        self.assertEqual([upload.name for upload in draft.sms_uploads], [upload.name for upload in self.sms])
        self.assertEqual([upload.getvalue() for upload in draft.sms_uploads], [upload.getvalue() for upload in self.sms])
        self.assertEqual(draft.settlement_upload.getvalue(), b"settlement")
        self.assertEqual(draft.state[f"inhouse_memo_value_{self.old_key}_row-a"], "Staff class")
        self.assertEqual(draft.state[f"deposit_required_steps_{self.old_key}"], ("inhouse_charges", "closeout"))
        self.assertEqual(draft.state["activity_paid_out_row-z_date"], date(2026, 9, 20))
        self.assertNotIn("run_result", draft.state)

    def test_restore_rekeys_workbook_and_reopens_active_step(self):
        from app.deposit_draft import read_deposit_draft, restore_deposit_draft

        draft = read_deposit_draft(self.make_draft())
        new_key = "membership_payments_3_0123456789abcdef"
        session = {"file_uploader_key": 3, f"inhouse_ids_{self.old_key}": ["stale"]}

        restore_deposit_draft(session, draft, uploader_key=3, workbook_key=new_key)

        self.assertEqual(session[DEPOSIT_PAGE_STAGE_KEY], DEPOSIT_STEPS_STAGE)
        self.assertEqual(session[f"inhouse_ids_{new_key}"], ["row-a", "row-b"])
        self.assertEqual(session[f"inhouse_amount_{new_key}_row-a"], 4.75)
        self.assertEqual(
            active_deposit_step(
                session[f"deposit_required_steps_{new_key}"],
                session[f"deposit_step_completions_{new_key}"],
            ),
            "closeout",
        )
        self.assertEqual(session["activity_donation_donation-a_given_to"], "Food Pantry")
        self.assertNotIn(f"inhouse_ids_{self.old_key}", session)
        preserved = session[DAILY_PROGRAM_UPLOADS_KEY]
        self.assertEqual(len(preserved["sms_reports_3"]), 6)
        self.assertEqual(preserved["card_settlement_3"].getvalue(), b"settlement")

    def test_corrupt_source_is_rejected_before_restoring_state(self):
        from app.deposit_draft import read_deposit_draft

        source = self.make_draft()
        output = io.BytesIO()
        with ZipFile(io.BytesIO(source)) as original, ZipFile(output, "w") as altered:
            for name in original.namelist():
                body = original.read(name)
                altered.writestr(name, b"changed" if name == "sms/01.xls" else body)

        with self.assertRaisesRegex(ValueError, "changed or damaged"):
            read_deposit_draft(output.getvalue())

    def test_unexpected_session_key_is_rejected(self):
        from app.deposit_draft import read_deposit_draft

        output = io.BytesIO()
        with ZipFile(io.BytesIO(self.make_draft())) as original, ZipFile(output, "w") as altered:
            for name in original.namelist():
                body = original.read(name)
                if name == "manifest.json":
                    manifest = json.loads(body)
                    manifest["state"]["active_finance_program"] = "credit_card_process"
                    body = json.dumps(manifest).encode()
                altered.writestr(name, body)

        with self.assertRaisesRegex(ValueError, "unexpected saved field"):
            read_deposit_draft(output.getvalue())

    def test_malformed_saved_rows_are_rejected_before_session_change(self):
        from app.deposit_draft import read_deposit_draft

        output = io.BytesIO()
        with ZipFile(io.BytesIO(self.make_draft())) as original, ZipFile(output, "w") as altered:
            for name in original.namelist():
                body = original.read(name)
                if name == "manifest.json":
                    manifest = json.loads(body)
                    manifest["state"][f"inhouse_ids_{self.old_key}"] = "not a row list"
                    body = json.dumps(manifest).encode()
                altered.writestr(name, body)
        existing_session = {"current_work": "unchanged"}

        with self.assertRaisesRegex(ValueError, "InHouse rows"):
            read_deposit_draft(output.getvalue())
        self.assertEqual(existing_session, {"current_work": "unchanged"})

    def test_card_settlement_must_match_deposit_before_resume(self):
        from app.deposit_draft import RestoredUpload, validate_draft_settlement

        def settlement_bytes(report_date):
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(["Date", report_date])
            sheet.append(["Network", "Processed Net Amount"])
            output = io.BytesIO()
            workbook.save(output)
            return output.getvalue()

        matching = RestoredUpload("card.xlsx", settlement_bytes(date(2026, 9, 25)))
        validate_draft_settlement(matching, date(2026, 9, 25))
        mismatched = RestoredUpload("card.xlsx", settlement_bytes(date(2026, 9, 24)))
        with self.assertRaisesRegex(ValueError, "matching deposit date"):
            validate_draft_settlement(mismatched, date(2026, 9, 25))
        with self.assertRaisesRegex(ValueError, "could not be verified"):
            validate_draft_settlement(RestoredUpload("card.xlsx", b"broken"), date(2026, 9, 25))


if __name__ == "__main__":
    unittest.main()
