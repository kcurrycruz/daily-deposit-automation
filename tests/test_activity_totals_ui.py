"""Live editor totals and donation defaults, exercised through the real step."""
import ast
from decimal import Decimal
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
DONATION_ACCOUNT = "8506000 · Outreach - Donations"
OTHER_ACCOUNT = "8505000 · Outreach"


def editor_script(category):
    tree = ast.parse((ROOT / "streamlit_app.py").read_text(encoding="utf-8"))
    labels = [node for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id in
                      {"activity_labels", "activity_save_labels"} for target in node.targets)]
    editor = next(node for node in tree.body if isinstance(node, ast.For)
                  and isinstance(node.iter, ast.Call)
                  and getattr(node.iter.func, "id", "") == "activity_workflow_keys"
                  and any(isinstance(item, ast.If) and isinstance(item.test, ast.Compare)
                          and getattr(item.test.left, "id", "") == "active_step"
                          for item in node.body))
    return f'''
import streamlit as st
import streamlit.components.v1 as components
from uuid import uuid4
from app.guided_step_ui import *
from app.activity_breakdowns import *
from app.deposit_workflow import *
from app.guided_deposit_state import save_activity_transition
from app.chart_of_accounts import load_default_chart_of_accounts
try:
    from app.activity_totals_ui import *
except ImportError:
    pass
activity_source_totals = {{"donation": 546.30, "paid_out": 546.30, "paid_in": 546.30}}
activity_detection_valid = True
activity_valid = True
activity_payload = {{}}
active_step = {category!r}
closeout_workbook_key = "totals-test"
step_completions = {{}}
required_steps = ("donation", "paid_out", "paid_in")
workflow_completion_key = "completions"
active_step_content = st.empty()
{ast.unparse(ast.Module(body=labels + [editor], type_ignores=[]))}
'''


class ActivityTotalsUiTests(unittest.TestCase):
    def editor(self, category):
        page = AppTest.from_string(editor_script(category)).run(timeout=15)
        page.radio[0].set_value("Breakdown in app").run(timeout=15)
        self.assertFalse(page.exception)
        return page

    def panel(self, page):
        panels = [item.value for item in page.markdown
                  if 'class="hwfc-activity-totals' in item.value]
        self.assertTrue(panels, "The actual editor must display its live totals panel")
        return panels[0]

    def test_new_donation_rows_default_account_and_preserve_user_override(self):
        page = self.editor("donation")
        self.assertEqual(page.selectbox[0].value, DONATION_ACCOUNT)
        page.selectbox[0].select(OTHER_ACCOUNT).run()
        next(button for button in page.button if button.label == "+ Add Donations item").click().run()
        self.assertFalse(page.exception)
        self.assertEqual([box.value for box in page.selectbox], [OTHER_ACCOUNT, DONATION_ACCOUNT])

    def test_draft_donation_amount_updates_totals_before_required_details(self):
        page = self.editor("donation")
        panel = self.panel(page)
        for amount in ("$546.30", "$100.00", "$446.30"):
            self.assertIn(amount, panel)
        page.number_input[0].set_value(200.25).run()
        panel = self.panel(page)
        self.assertIn("$200.25", panel)
        self.assertIn("$346.05", panel)
        self.assertTrue(any("Given To is required" in item.value for item in page.caption))

    def test_added_and_removed_donation_rows_update_the_visible_total(self):
        page = self.editor("donation")
        next(button for button in page.button if button.label == "+ Add Donations item").click().run()
        self.assertIn("$200.00", self.panel(page))
        next(button for button in page.button if button.label == "×").click().run()
        self.assertIn("$100.00", self.panel(page))
        self.assertIn("$446.30", self.panel(page))

    def test_paid_out_uses_the_same_live_reference_panel(self):
        page = self.editor("paid_out")
        page.number_input[0].set_value(50.25).run()
        self.assertIn("$546.30", self.panel(page))
        self.assertIn("$50.25", self.panel(page))
        self.assertIn("$496.05", self.panel(page))
        self.assertIsNone(page.selectbox[0].value)

    def test_paid_in_pending_amount_is_counted_once_after_add(self):
        page = self.editor("paid_in")
        page.selectbox[0].select(OTHER_ACCOUNT)
        page.text_input[0].set_value("Synthetic paid-in item")
        page.number_input[0].set_value(50.25).run()
        self.assertIn("$50.25", self.panel(page))
        next(button for button in page.button if button.label == "+ Add Paid In item").click().run()
        self.assertFalse(page.exception)
        self.assertIn("$50.25", self.panel(page))
        self.assertIn("$496.05", self.panel(page))
        self.assertEqual(page.number_input[0].value, 0.0)
        page.number_input[0].set_value(10.0).run()
        self.assertIn("$60.25", self.panel(page))

    def test_over_target_and_matching_are_not_item_approval(self):
        page = self.editor("donation")
        page.number_input[0].set_value(600.0).run()
        panel = self.panel(page)
        self.assertIn("Over report total", panel)
        self.assertIn("$53.70", panel)
        page.number_input[0].set_value(546.30).run()
        panel = self.panel(page)
        self.assertIn("Totals match", panel)
        self.assertIn("not saved or approved", panel)
        self.assertTrue(any("Given To is required" in item.value for item in page.caption))

    def test_paid_in_half_cent_preview_agrees_before_and_after_add(self):
        page = self.editor("paid_in")
        page.selectbox[0].select(OTHER_ACCOUNT)
        page.text_input[0].set_value("Synthetic rounding item")
        page.number_input[0].set_value(1.005).run()
        self.assertIn("$1.00", self.panel(page))
        next(button for button in page.button if button.label == "+ Add Paid In item").click().run()
        self.assertIn("$1.00", self.panel(page))
        self.assertIn("$545.30", self.panel(page))


class ActivityEntrySummaryTests(unittest.TestCase):
    def summary(self, source, rows, **kwargs):
        try:
            from app.activity_totals_ui import activity_entry_summary
        except ImportError as exc:
            self.fail(f"Live amount summary is missing: {exc}")
        return activity_entry_summary(source, rows, **kwargs)

    def test_cents_are_exact_and_details_do_not_control_the_amount_preview(self):
        rows = [{"amount": "0.10"}, {"amount": "0.20", "given_to": ""}]
        result = self.summary("546.30", rows)
        self.assertEqual(result["entered"], Decimal("0.30"))
        self.assertEqual(result["remaining"], Decimal("546.00"))
        self.assertEqual(rows, [{"amount": "0.10"}, {"amount": "0.20", "given_to": ""}])

    def test_progress_is_clamped_without_hiding_an_overage(self):
        result = self.summary("546.30", [{"amount": 600}])
        self.assertEqual(result["remaining"], Decimal("-53.70"))
        self.assertEqual(result["percent"], 100)
        self.assertEqual(result["status"], "over")
        self.assertEqual(self.summary(0, [])["percent"], 0)

    def test_extra_decimal_input_matches_existing_accounting_rounding(self):
        result = self.summary(10, [{"amount": "1.005"}, {"amount": "1.015"}])
        self.assertEqual(result["entered"], Decimal("2.02"))
        self.assertEqual(result["remaining"], Decimal("7.98"))

    def test_nonfinite_amounts_are_rejected_instead_of_looking_matched(self):
        for value in (float("nan"), float("inf"), "not money", True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.summary(100, [{"amount": value}])


if __name__ == "__main__":
    unittest.main()
