"""Presentation-only totals for the remaining guided steps."""
import ast
from decimal import Decimal
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


class StepTotalsSummaryTests(unittest.TestCase):
    def summary(self, target, entered):
        try:
            from app.step_totals_ui import step_total_summary
        except ImportError:
            self.fail("Shared guided-step totals summary is missing")
        return step_total_summary(target, entered)

    def test_signed_inhouse_credit_reduces_entered_total(self):
        result = self.summary("100.00", "-25.50")
        self.assertEqual(result["remaining"], Decimal("125.50"))
        self.assertEqual(result["percent"], 0)
        self.assertEqual(result["status"], "remaining")

    def test_unreviewed_closeout_cannot_look_matched(self):
        result = self.summary("100.00", None)
        self.assertIsNone(result["remaining"])
        self.assertEqual(result["status"], "pending")

    def test_overage_is_visible_and_progress_does_not_overflow(self):
        result = self.summary("100.00", "125.50")
        self.assertEqual(result["remaining"], Decimal("-25.50"))
        self.assertEqual(result["percent"], 100)
        self.assertEqual(result["status"], "over")

    def test_valid_zero_target_is_distinct_from_unreviewed(self):
        self.assertEqual(self.summary(0, 0)["status"], "matched")
        self.assertEqual(self.summary(0, None)["status"], "pending")

    def test_invalid_amounts_never_look_reconciled(self):
        for value in (True, "bad", "NaN", "Infinity"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.summary(100, value)


class GuidedStepTotalsTests(unittest.TestCase):
    def page(self, title):
        tree = ast.parse((ROOT / "streamlit_app.py").read_text(encoding="utf-8"))
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and getattr(node.func, "id", "") == "render_step_totals"
                 and any(kw.arg == "title" and isinstance(kw.value, ast.Constant)
                         and kw.value.value == title for kw in node.keywords)]
        self.assertEqual(len(calls), 1, f"The actual {title} step must render its totals")
        # Execute the production call with changing widgets and hand-derived
        # source/review data. No account or save rules are substituted.
        script = '''
import streamlit as st
from app.step_totals_ui import *
subscription_total = 150.00
membership_payments = [{"amount": 50.00}]
amount = st.number_input("Current payment", value=50.00)
coupon_bs_total = 148.25
coupon_closeout_total = st.number_input("Coupon target", value=164.25)
coupon_ncg_total = st.number_input("NCG counted", value=100.00)
coupon_mfg_total = st.number_input("MFG counted", value=64.25)
charge_house_total = 100.00
inhouse_rows = [{"amount": st.number_input("Charge", value=100.00)},
                {"amount": st.number_input("Credit", value=-25.50)}]
inhouse_total = round(sum(row["amount"] for row in inhouse_rows), 2)
final_closeout_total = st.number_input("Paper deposit total", value=500.00)
preview_is_fresh = st.checkbox("Current review", value=False)
saved_closeout_preview = {"preview": {"provisional_total": 480.00}}
membership_totals_slot = coupon_totals_slot = inhouse_totals_slot = closeout_totals_slot = st.empty()
'''
        page = AppTest.from_string(script + ast.unparse(calls[0])).run(timeout=15)
        self.assertFalse(page.exception)
        return page

    def panel(self, page):
        panels = [item.value for item in page.markdown if 'hwfc-step-totals' in item.value]
        self.assertEqual(len(panels), 1)
        return panels[0]

    def test_member_pending_amount_is_included_without_approving_it(self):
        page = self.page("Member Shares")
        self.assertIn("$150.00", self.panel(page))
        self.assertIn("$100.00", self.panel(page))
        page.number_input[0].set_value(100.00).run()
        self.assertIn("Totals match", self.panel(page))
        self.assertIn("not saved or approved", self.panel(page))

    def test_coupons_match_closeout_target_not_balance_sheet_reference(self):
        page = self.page("Coupons Receivable")
        panel = self.panel(page)
        self.assertIn("Totals match", panel)
        self.assertIn("$164.25", panel)
        self.assertIn("$148.25", panel)
        self.assertIn("+$16.00", panel)
        next(item for item in page.number_input if item.label == "MFG counted").set_value(14.25).run()
        panel = self.panel(page)
        self.assertIn("$114.25", panel)
        self.assertIn("$50.00", panel)
        self.assertNotIn("Totals match", panel)

    def test_inhouse_panel_preserves_signed_credits(self):
        page = self.page("InHouse Charges")
        self.assertIn("$74.50", self.panel(page))
        self.assertIn("$25.50", self.panel(page))
        next(item for item in page.number_input if item.label == "Credit").set_value(-100.00).run()
        self.assertIn("$0.00", self.panel(page))
        self.assertIn("$100.00", self.panel(page))

    def test_closeout_requires_current_review_and_does_not_hide_differences(self):
        page = self.page("Closeout Sheet")
        panel = self.panel(page)
        self.assertIn("$500.00", panel)
        self.assertIn("Review required", panel)
        self.assertNotIn("Totals match", panel)
        page.checkbox[0].check().run()
        self.assertIn("$480.00", self.panel(page))
        self.assertIn("$20.00", self.panel(page))
        page.checkbox[0].uncheck().run()
        self.assertIn("Review required", self.panel(page))
        self.assertNotIn("$480.00", self.panel(page))


if __name__ == "__main__":
    unittest.main()
