import ast
from contextlib import nullcontext
from datetime import date
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import unittest

from app import operations_status_ui
from app.guided_step_ui import update_upload_pair_readiness
from app.ui_helpers import deposit_download_details

SOURCE = Path(__file__).resolve().parents[1].joinpath("streamlit_app.py")


def assignments(*names):
    return [node for node in ast.parse(SOURCE.read_text(encoding="utf-8")).body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id in names
                    for target in node.targets)]


def execute(nodes, namespace):
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), namespace)


class CurrentDepositTests(unittest.TestCase):
    def setUp(self):
        daily = BytesIO(b"daily workbook content")
        daily.name = "daily.xlsx"
        settlement = BytesIO(b"settlement content")
        settlement.name = "settlement.xlsx"
        self.ns = {
            **vars(operations_status_ui),
            "deposit_download_details": deposit_download_details,
            "st": SimpleNamespace(session_state={}),
            "uploaded": daily, "upload_bytes": daily.getvalue(),
            "settlement_file": settlement, "deposit_date": date(2026, 9, 8),
            "workbook_status_valid": True, "settlement_status_valid": True,
            "guided_workflow_ready": True, "membership_valid": True,
            "coupon_valid": True, "activity_valid": True, "closeout_valid": True,
            "membership_mode": "automatic", "membership_payments": [],
            "coupon_mode": "quickbooks", "coupon_closeout_total": 0.0,
            "coupon_ncg_total": 0.0, "coupon_mfg_total": 0.0,
            "activity_payload": {"donation": {"mode": "quickbooks", "rows": []}},
            "closeout_payload": {"mode": "manual"},
            "step_completions": {"closeout": "quickbooks"},
        }
        execute(assignments("current_run_context"), self.ns)
        self.ns["st"].session_state.update({
            "run_context": self.ns.get("current_run_context", "legacy-context"),
            "run_result": {"iif_bytes": b"generated IIF", "iif_path": Path("deposit.iif")},
        })

    def render_state(self):
        execute(assignments("current_run_context", "current_result", "download_details",
                            "operations_status"), self.ns)
        return self.ns["download_details"], self.ns["operations_status"]

    def assert_stale(self):
        download, status = self.render_state()
        self.assertIsNone(download, "Stale generated IIF must not be downloadable")
        self.assertNotEqual(status.iif, "Ready to download")

    def test_unchanged_completed_deposit_remains_downloadable(self):
        download, status = self.render_state()
        self.assertEqual(download, {"data": b"generated IIF", "file_name": "deposit.iif"})
        self.assertEqual(status.iif, "Ready to download")

    def test_removing_either_upload_hides_retained_download(self):
        for field in ("uploaded", "settlement_file"):
            with self.subTest(field=field):
                original = self.ns[field]
                self.ns[field] = None
                self.assert_stale()
                self.ns[field] = original

    def test_replacing_either_file_with_same_filename_hides_retained_download(self):
        for field in ("uploaded", "settlement_file"):
            with self.subTest(field=field):
                original = self.ns[field]
                replacement = BytesIO(b"changed content")
                replacement.name = original.name
                self.ns[field] = replacement
                self.ns["upload_bytes"] = self.ns["uploaded"].getvalue()
                self.assert_stale()
                self.ns[field] = original
                self.ns["upload_bytes"] = self.ns["uploaded"].getvalue()

    def test_reopening_completed_step_hides_retained_download(self):
        from app.guided_deposit_state import reopen_step_for_edit
        from app.deposit_workflow import deposit_workflow_complete

        self.ns["step_completions"] = reopen_step_for_edit(
            self.ns["st"].session_state, required_steps=("closeout",),
            completions=self.ns["step_completions"], step="closeout", workbook_key="daily",
        )
        self.ns["guided_workflow_ready"] = deposit_workflow_complete(
            ("closeout",), self.ns["step_completions"])
        self.assert_stale()

    def test_changed_and_recompleted_editable_inputs_require_new_run(self):
        changes = {
            "membership_mode": "manual", "membership_payments": [{"amount": 100}],
            "coupon_mode": "closeout", "coupon_closeout_total": 20.0,
            "coupon_ncg_total": 10.0, "coupon_mfg_total": 10.0,
            "activity_payload": {"donation": {"mode": "app", "rows": [{"amount": 100}]}},
            "closeout_payload": {"mode": "closeout", "final_total": 100},
            "deposit_date": date(2026, 9, 9),
        }
        for field, changed in changes.items():
            with self.subTest(field=field):
                original = self.ns[field]
                self.ns[field] = changed
                self.assert_stale()
                self.ns[field] = original

    def test_invalid_current_inputs_hide_retained_download(self):
        for field in ("workbook_status_valid", "settlement_status_valid", "membership_valid",
                      "coupon_valid", "activity_valid", "closeout_valid"):
            with self.subTest(field=field):
                self.ns[field] = False
                self.assert_stale()
                self.ns[field] = True

    def test_legacy_result_without_context_is_not_current(self):
        self.ns["st"].session_state.pop("run_context")
        self.assert_stale()

    def test_context_is_stable_for_equivalent_mapping_order(self):
        helper = getattr(operations_status_ui, "deposit_run_context", None)
        self.assertIsNotNone(helper, "Content-based run identity is required")
        self.assertEqual(helper(b"daily", b"settlement", {"a": 1, "b": [2, 3]}),
                         helper(b"daily", b"settlement", {"b": [2, 3], "a": 1}))

    def test_status_does_not_allow_generated_flag_to_override_current_readiness(self):
        for override in ({"daily_uploaded": False}, {"settlement_uploaded": False},
                         {"workbook_valid": False}, {"settlement_valid": False},
                         {"workflow_complete": False}):
            with self.subTest(override=override):
                inputs = dict(deposit_date=date(2026, 9, 8), daily_uploaded=True,
                              settlement_uploaded=True, workbook_valid=True,
                              settlement_valid=True, workflow_complete=True, iif_generated=True)
                status = operations_status_ui.build_operations_status(**(inputs | override))
                self.assertNotEqual(status.iif, "Ready to download")

    def run_action(self, engine):
        self.ns.update(run_clicked=True, run_engine=engine, RUN_LOCK_PATH="unused",
                       exclusive_run_lock=lambda path: nullcontext(), roles={}, date_info={},
                       archive_run=lambda *args: {"id": "history-id"})
        self.ns["st"].spinner = lambda message: nullcontext()
        self.ns["st"].rerun = lambda: None
        self.ns["st"].error = lambda *args: None
        self.ns["st"].code = lambda *args, **kwargs: None
        action = next(node for node in ast.parse(SOURCE.read_text(encoding="utf-8")).body
                      if isinstance(node, ast.If) and isinstance(node.test, ast.Name)
                      and node.test.id == "run_clicked")
        execute([action], self.ns)

    def test_successful_engine_run_stores_current_context_with_result(self):
        self.ns["st"].session_state.pop("run_context")
        new_result = {"iif_bytes": b"new IIF", "iif_path": Path("new.iif")}
        self.run_action(lambda *args, **kwargs: new_result)
        self.assertEqual(self.ns["st"].session_state.get("run_context"),
                         self.ns["current_run_context"])
        self.assertIs(self.ns["st"].session_state["run_result"], new_result)

    def test_failed_engine_run_never_stores_current_context(self):
        self.ns["st"].session_state.pop("run_context")

        def fail(*args, **kwargs):
            raise RuntimeError("Engine failed")

        self.run_action(fail)
        self.assertNotIn("run_context", self.ns["st"].session_state)

    def test_start_over_clears_result_identity(self):
        reset = next(node for node in ast.parse(SOURCE.read_text(encoding="utf-8")).body
                     if isinstance(node, ast.FunctionDef) and node.name == "reset_current_work")
        execute([reset], self.ns)
        self.ns["reset_current_work"]()
        self.assertNotIn("run_context", self.ns["st"].session_state)
        self.assertNotIn("run_result", self.ns["st"].session_state)


class ValidatedUploadWiringTests(unittest.TestCase):
    def readiness(self, state, **changes):
        ns = dict(st=SimpleNamespace(session_state=state), uploaded=object(),
                  settlement_file=object(), workbook_status_valid=True,
                  settlement_status_valid=True, upload_pair_readiness_key="ready",
                  deposit_steps_scroll_key="scroll", settlement_date_mismatch=True,
                  update_upload_pair_readiness=update_upload_pair_readiness)
        ns.update(changes)
        execute(assignments("uploads_ready"), ns)
        return ns["uploads_ready"]

    def test_invalid_workbook_or_settlement_never_unlocks_or_queues_scroll(self):
        for field in ("workbook_status_valid", "settlement_status_valid"):
            with self.subTest(field=field):
                state = {}
                self.assertFalse(self.readiness(state, **{field: False}))
                self.assertNotIn("scroll", state)

    def test_invalid_to_valid_queues_once_and_date_mismatch_does_not_block(self):
        state = {}
        self.assertFalse(self.readiness(state, workbook_status_valid=False))
        self.assertTrue(self.readiness(state))
        self.assertTrue(state.pop("scroll"))
        self.assertTrue(self.readiness(state))
        self.assertNotIn("scroll", state)

    def test_upload_gate_runs_after_both_validation_phases_before_guide(self):
        nodes = assignments("uploads_ready", "workbook_status_valid", "settlement_status_valid")
        positions = {node.targets[0].id: node.lineno for node in nodes}
        self.assertGreater(positions["uploads_ready"], positions["workbook_status_valid"])
        self.assertGreater(positions["uploads_ready"], positions["settlement_status_valid"])
        guide = next(node for node in ast.parse(SOURCE.read_text(encoding="utf-8")).body
                     if isinstance(node, ast.If) and isinstance(node.test, ast.Name)
                     and node.test.id == "uploads_ready")
        self.assertLess(positions["uploads_ready"], guide.lineno)

    def test_missing_workbook_date_or_roles_and_bad_settlement_header_block_guide(self):
        for changes in ({"deposit_date": None}, {"missing_roles": ["hash"]},
                        {"settlement_source_ok": False}):
            with self.subTest(changes=changes):
                ns = dict(st=SimpleNamespace(session_state={}), uploaded=object(),
                          settlement_file=object(), deposit_date=date(2026, 9, 8),
                          missing_roles=[], settlement_source_ok=True,
                          upload_pair_readiness_key="ready", deposit_steps_scroll_key="scroll",
                          update_upload_pair_readiness=update_upload_pair_readiness)
                ns.update(changes)
                execute(assignments("workbook_status_valid", "settlement_status_valid",
                                    "uploads_ready"), ns)
                self.assertFalse(ns["uploads_ready"])
                self.assertNotIn("scroll", ns["st"].session_state)


if __name__ == "__main__":
    unittest.main()
