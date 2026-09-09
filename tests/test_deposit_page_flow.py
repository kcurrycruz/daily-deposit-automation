import unittest
from datetime import date

from app.deposit_page_flow import (
    DEPOSIT_PAGE_STAGE_KEY,
    DEPOSIT_STEPS_STAGE,
    UPLOAD_STAGE,
    advance_to_deposit_steps,
    enforce_ready_stage,
    reports_ready_for_steps,
    reset_deposit_page,
    selected_deposit_stage,
)


class DepositPageFlowTests(unittest.TestCase):
    def test_new_and_unknown_stage_values_use_upload(self):
        self.assertEqual(selected_deposit_stage({}), UPLOAD_STAGE)
        self.assertEqual(
            selected_deposit_stage({DEPOSIT_PAGE_STAGE_KEY: "unknown"}),
            UPLOAD_STAGE,
        )

    def test_reports_require_two_valid_files_and_the_same_detected_date(self):
        report_date = date(2026, 9, 8)
        self.assertTrue(reports_ready_for_steps(
            workbook_valid=True,
            settlement_valid=True,
            workbook_date=report_date,
            settlement_date=report_date,
        ))
        self.assertFalse(reports_ready_for_steps(
            workbook_valid=True,
            settlement_valid=True,
            workbook_date=report_date,
            settlement_date=date(2026, 9, 9),
        ))
        self.assertFalse(reports_ready_for_steps(
            workbook_valid=False,
            settlement_valid=True,
            workbook_date=report_date,
            settlement_date=report_date,
        ))

    def test_continue_requires_ready_reports_and_never_advances_automatically(self):
        state = {}
        self.assertFalse(advance_to_deposit_steps(state, reports_ready=False))
        self.assertEqual(selected_deposit_stage(state), UPLOAD_STAGE)
        self.assertTrue(advance_to_deposit_steps(state, reports_ready=True))
        self.assertEqual(selected_deposit_stage(state), DEPOSIT_STEPS_STAGE)

    def test_invalid_preserved_reports_force_upload_stage(self):
        state = {DEPOSIT_PAGE_STAGE_KEY: DEPOSIT_STEPS_STAGE}
        self.assertEqual(
            enforce_ready_stage(state, reports_ready=False),
            UPLOAD_STAGE,
        )
        self.assertEqual(state[DEPOSIT_PAGE_STAGE_KEY], UPLOAD_STAGE)

    def test_reset_returns_to_upload(self):
        state = {DEPOSIT_PAGE_STAGE_KEY: DEPOSIT_STEPS_STAGE}
        reset_deposit_page(state)
        self.assertEqual(selected_deposit_stage(state), UPLOAD_STAGE)
