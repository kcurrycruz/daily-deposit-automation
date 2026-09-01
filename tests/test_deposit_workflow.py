import unittest


class DepositWorkflowTests(unittest.TestCase):
    def workflow_api(self):
        try:
            from app.deposit_workflow import (
                STEP_CLOSEOUT,
                active_deposit_step,
                complete_deposit_step,
                deposit_step_rows,
                deposit_workflow_complete,
                edit_deposit_step,
                normalize_step_completions,
                required_deposit_steps,
            )
        except ImportError as exc:
            self.fail(f"guided deposit workflow is missing: {exc}")
        return locals()

    def test_required_steps_use_fixed_gap_free_business_order(self):
        api = self.workflow_api()
        steps = api["required_deposit_steps"](8.45, {"donation": 25, "paid_in": 100, "paid_out": 40}, 18.49)
        self.assertEqual(steps, ("member_shares", "donation", "paid_in", "paid_out", "coupons", "closeout"))

    def test_only_paid_in_still_ends_with_closeout(self):
        api = self.workflow_api()
        self.assertEqual(api["required_deposit_steps"](0, {"donation": 0, "paid_in": 100, "paid_out": 0}, 0), ("paid_in", "closeout"))

    def test_no_optional_activity_still_requires_closeout(self):
        api = self.workflow_api()
        self.assertEqual(api["required_deposit_steps"](0, {"donation": 0, "paid_in": 0, "paid_out": 0}, 0), ("closeout",))

    def test_every_optional_combination_preserves_business_order(self):
        from itertools import product
        api = self.workflow_api()
        ordered = ("member_shares", "donation", "paid_in", "paid_out", "coupons")
        for enabled in product((False, True), repeat=len(ordered)):
            with self.subTest(enabled=enabled):
                steps = api["required_deposit_steps"](1 if enabled[0] else 0, {"donation": 1 if enabled[1] else 0, "paid_in": 1 if enabled[2] else 0, "paid_out": 1 if enabled[3] else 0}, 1 if enabled[4] else 0)
                self.assertEqual(steps, tuple(step for step, is_enabled in zip(ordered, enabled) if is_enabled) + ("closeout",))

    def test_completion_methods_advance_to_first_incomplete_step(self):
        api = self.workflow_api(); steps = ("paid_in", "paid_out", "closeout")
        completed = api["complete_deposit_step"](steps, {}, "paid_in", "quickbooks")
        self.assertEqual(completed, {"paid_in": "quickbooks"})
        self.assertEqual(api["active_deposit_step"](steps, completed), "paid_out")
        completed = api["complete_deposit_step"](steps, completed, "paid_out", "app")
        self.assertEqual(api["active_deposit_step"](steps, completed), "closeout")

    def test_normalization_ignores_stale_and_invalid_completion_entries(self):
        api = self.workflow_api()
        normalized = api["normalize_step_completions"](("paid_in", "closeout"), {"donation": "app", "paid_in": "invalid", "closeout": "quickbooks"})
        self.assertEqual(normalized, {"closeout": "quickbooks"})

    def test_edit_preserves_later_activity_but_invalidates_step_and_closeout(self):
        api = self.workflow_api(); steps = ("donation", "paid_in", "paid_out", "closeout")
        completed = {"donation": "app", "paid_in": "app", "paid_out": "quickbooks", "closeout": "app"}
        edited = api["edit_deposit_step"](steps, completed, "paid_in")
        self.assertEqual(edited, {"donation": "app", "paid_out": "quickbooks"})
        self.assertEqual(api["active_deposit_step"](steps, edited), "paid_in")

    def test_editing_closeout_preserves_every_earlier_completion(self):
        api = self.workflow_api()
        steps = ("paid_in", "paid_out", "closeout")
        completed = {
            "paid_in": "app",
            "paid_out": "quickbooks",
            "closeout": "app",
        }
        self.assertEqual(
            api["edit_deposit_step"](steps, completed, "closeout"),
            {"paid_in": "app", "paid_out": "quickbooks"},
        )

    def test_reopened_closeout_hydrates_canonical_form_and_drops_preview(self):
        from app.closeout_reconciliation import STANDARD_CLOSEOUT_ORDER
        from app.guided_deposit_state import hydrate_reopened_closeout_state

        workbook_key = "workbook-123"
        payload_key = f"closeout_payload_{workbook_key}"
        preview_key = f"closeout_preview_{workbook_key}"
        session_state = {
            payload_key: {
                "mode": "closeout",
                "reviewed": True,
                "actuals": {
                    field: float(index + 10)
                    for index, field in enumerate(STANDARD_CLOSEOUT_ORDER)
                },
                "payroll": -4000.0,
                "safe": {"type": "overage", "amount": 7.5},
                "plants_purchase": 12.34,
                "custom_tba": [
                    {
                        "memo": "Printer repair",
                        "amount": 45.67,
                        "direction": "adds",
                    }
                ],
                "final_total": 1000.0,
                "approve_final_pos": True,
            },
            preview_key: {"input_fingerprint": "stale", "preview": {}},
        }

        hydrated = hydrate_reopened_closeout_state(
            session_state,
            payload_key=payload_key,
            preview_key=preview_key,
            workbook_key=workbook_key,
        )

        self.assertTrue(hydrated)
        self.assertNotIn(preview_key, session_state)
        self.assertEqual(
            session_state[f"closeout_handling_{workbook_key}"],
            "Breakdown in app using Closeout Sheet",
        )
        self.assertTrue(session_state[f"closeout_reviewed_{workbook_key}"])
        self.assertEqual(
            session_state[f"closeout_actual_cash_{workbook_key}"],
            10.0,
        )
        self.assertEqual(
            session_state[f"closeout_payroll_{workbook_key}"],
            "Removes $4,000",
        )
        self.assertEqual(
            session_state[f"closeout_safe_type_{workbook_key}"], "Overage")
        self.assertEqual(
            session_state[f"closeout_safe_amount_{workbook_key}"], 7.5
        )
        self.assertEqual(
            session_state[f"closeout_plants_{workbook_key}"], 12.34)
        self.assertEqual(session_state[f"closeout_custom_ids_{workbook_key}"], [0])
        self.assertEqual(
            session_state[f"closeout_custom_memo_{workbook_key}_0"],
            "Printer repair",
        )
        self.assertEqual(
            session_state[f"closeout_custom_direction_{workbook_key}_0"],
            "Adds to deposit",
        )
        self.assertEqual(
            session_state[f"closeout_final_total_{workbook_key}"], 1000.0)
        self.assertNotIn(
            f"closeout_approve_final_{workbook_key}",
            session_state,
        )

    def test_rows_are_gap_free_and_expose_user_facing_statuses(self):
        api = self.workflow_api()
        rows = api["deposit_step_rows"](("paid_in", "closeout"), {"paid_in": "quickbooks"})
        self.assertEqual(rows, [{"number": 1, "step": "paid_in", "label": "Paid In", "status": "Finish in QuickBooks", "complete": True, "current": False}, {"number": 2, "step": "closeout", "label": "Closeout Sheet", "status": "Current", "complete": False, "current": True}])

    def test_final_eligibility_requires_every_step(self):
        api = self.workflow_api(); steps = ("paid_in", "closeout")
        self.assertFalse(api["deposit_workflow_complete"](steps, {"paid_in": "app"}))
        self.assertTrue(api["deposit_workflow_complete"](steps, {"paid_in": "app", "closeout": "quickbooks"}))
