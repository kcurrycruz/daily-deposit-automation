"""Exercise the actual InHouse row controls in a small Streamlit harness."""

import ast
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


def _inhouse_editor_script() -> str:
    tree = ast.parse((ROOT / "streamlit_app.py").read_text(encoding="utf-8"))
    editor = next(
        node for node in tree.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.BoolOp)
        and any(
            isinstance(part, ast.Compare)
            and getattr(part.left, "id", "") == "active_step"
            and getattr(part.comparators[0], "id", "") == "STEP_INHOUSE"
            for part in node.test.values
        )
    )
    return f'''
import streamlit as st
import streamlit.components.v1 as components
from uuid import uuid4
from app.chart_of_accounts import load_default_chart_of_accounts
from app.deposit_workflow import STEP_INHOUSE
from app.guided_deposit_state import save_inhouse_transition
from app.guided_step_ui import prepare_closeout_after_inhouse_save, queue_continue_scroll, render_breakdown_scroll_target
from app.inhouse_charges import compose_inhouse_memo, describe_inhouse_memo_draft, move_inhouse_row_ids, normalize_inhouse_step_payload
from app.step_totals_ui import render_step_totals
uploaded = True
active_step = STEP_INHOUSE
closeout_workbook_key = "order-test"
charge_house_total = 30.0
required_steps = (STEP_INHOUSE, "closeout")
step_completions = {{}}
workflow_completion_key = "completion"
active_step_content = st.empty()
if "inhouse_ids_order-test" not in st.session_state:
    st.session_state["inhouse_ids_order-test"] = ["row-a", "row-b"]
    for row_id, account, initials, amount in (
        ("row-a", "8320000 · Store Supplies", "BS", 20.0),
        ("row-b", "8504000 · Education", "KC", 10.0),
    ):
        st.session_state[f"inhouse_account_order-test_{{row_id}}"] = account
        st.session_state[f"inhouse_memo_type_order-test_{{row_id}}"] = "End of Day"
        st.session_state[f"inhouse_initials_order-test_{{row_id}}"] = initials
        st.session_state[f"inhouse_amount_order-test_{{row_id}}"] = amount
{ast.unparse(editor)}
'''


class InhouseOrderUiTests(unittest.TestCase):
    def test_move_buttons_reorder_complete_rows_and_keep_totals(self):
        page = AppTest.from_string(_inhouse_editor_script()).run(timeout=15)
        self.assertFalse(page.exception)
        self.assertEqual([box.value for box in page.selectbox], [
            "8320000 · Store Supplies", "8504000 · Education",
        ])
        buttons = [button for button in page.button if button.label == "↑"]
        self.assertEqual(len(buttons), 2)
        buttons[1].click().run(timeout=15)

        self.assertFalse(page.exception)
        self.assertEqual([box.value for box in page.selectbox], [
            "8504000 · Education", "8320000 · Store Supplies",
        ])
        self.assertEqual([box.value for box in page.text_input], ["KC", "BS"])
        self.assertEqual([box.value for box in page.number_input], [10.0, 20.0])
        self.assertTrue(any("match the System / BS total" in item.value for item in page.success))
        next(button for button in page.button
             if button.label == "Save InHouse Charges & Continue").click().run(timeout=15)
        self.assertFalse(page.exception)
        self.assertEqual(
            page.session_state["inhouse_saved_payload_order-test"]["rows"],
            [
                {"account": "8504000 · Education", "memo": "End of Day - KC", "amount": 10.0},
                {"account": "8320000 · Store Supplies", "memo": "End of Day - BS", "amount": 20.0},
            ],
        )


if __name__ == "__main__":
    unittest.main()
