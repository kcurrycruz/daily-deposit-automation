"""Closeout entry and review show the paper sheet's Actual-first order."""

import ast
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


def _statements_from_assignment(name: str, count: int) -> str:
    tree = ast.parse((ROOT / "streamlit_app.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        for _, value in ast.iter_fields(node):
            if not isinstance(value, list):
                continue
            for index, statement in enumerate(value):
                if (
                    isinstance(statement, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == name
                            for target in statement.targets)
                ):
                    return ast.unparse(ast.Module(
                        body=value[index:index + count], type_ignores=[]
                    ))
    raise AssertionError(f"Could not find the {name} UI block")


def _entry_script() -> str:
    return f'''
import streamlit as st
from app.closeout_reconciliation import STANDARD_CLOSEOUT_ORDER, STANDARD_METADATA
closeout_workbook_key = "order-test"
closeout_baselines = {{field: 0.0 for field in STANDARD_CLOSEOUT_ORDER}}
closeout_baselines["cash"] = 100.0
closeout_defaults = dict(closeout_baselines)
closeout_defaults["cash"] = 90.0
locked_activity_actuals = {{}}
counted_coupon_total = 0.0
inhouse_payload = {{"actual": 0.0}}
closeout_actuals = {{}}
{_statements_from_assignment("header_columns", 3)}
'''


def _review_script() -> str:
    return f'''
import streamlit as st
import pandas as pd
closeout_preview = {{"standard_rows": [{{
    "label": "Cash", "baseline": 100.0, "actual": 90.0, "difference": -10.0,
}}]}}
{_statements_from_assignment("standard_display", 2)}
'''


class CloseoutUiOrderTests(unittest.TestCase):
    def test_entry_grid_shows_actual_before_system_and_keeps_difference_sign(self):
        page = AppTest.from_string(_entry_script()).run(timeout=15)

        self.assertFalse(page.exception)
        self.assertEqual([item.value for item in page.caption][:5], [
            "Category", "Actual", "System / BS", "Difference", "Status",
        ])
        self.assertEqual(page.number_input[0].value, 90.0)
        self.assertIn("-10.00", [item.value for item in page.markdown])

    def test_review_grid_shows_actual_before_system_without_changing_values(self):
        page = AppTest.from_string(_review_script()).run(timeout=15)

        self.assertFalse(page.exception)
        display = page.dataframe[0].value
        self.assertEqual(display.columns.tolist(), [
            "Category", "Actual", "System / BS", "Difference",
        ])
        self.assertEqual(display.iloc[0].tolist(), ["Cash", 90.0, 100.0, -10.0])


if __name__ == "__main__":
    unittest.main()
