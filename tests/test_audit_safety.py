"""Regressions for financial-file privacy and fail-closed orchestration."""

import ast
import json
import os
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "streamlit_app.py"


def definitions(names, namespace):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace


class AuditSafetyTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="_audit_safety_", dir=ROOT / "tests")
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def test_financial_history_and_secrets_are_ignored_by_git(self):
        paths = ["output/history/run_history.json", "output/history/uploads/report.xls",
                 "output/history/iif/deposit.iif", ".streamlit/secrets.toml"]
        result = subprocess.run(["git", "check-ignore", "--stdin"], cwd=ROOT,
                                input=("\n".join(paths) + "\n").encode(), capture_output=True)
        self.assertEqual(set(result.stdout.decode().splitlines()), set(paths))

    def history(self):
        return definitions({"load_run_history", "save_run_history"}, {
            "Path": Path, "json": json, "HISTORY_DIR": self.root,
            "HISTORY_FILE": self.root / "run_history.json",
        })

    def test_interrupted_history_replacement_retains_previous_records(self):
        history = self.history()
        old = [{"id": "old", "run_at": "2026-10-01T09:00:00"}]
        history["HISTORY_FILE"].write_text(json.dumps(old), encoding="utf-8")
        with patch("os.replace", side_effect=OSError("synthetic interruption")):
            with self.assertRaises(OSError):
                history["save_run_history"]([{"id": "new"}])
        self.assertEqual(history["load_run_history"](), old)
        self.assertEqual([p.name for p in self.root.iterdir()], ["run_history.json"])

    def test_history_reader_never_sees_a_partial_replacement(self):
        history = self.history()
        old, new = [{"id": "old"}], [{"id": "new"}]
        history["HISTORY_FILE"].write_text(json.dumps(old), encoding="utf-8")
        observed = []
        replace = os.replace

        def observe_before_replace(source, destination):
            observed.append(history["load_run_history"]())
            replace(source, destination)

        with patch("os.replace", side_effect=observe_before_replace):
            history["save_run_history"](new)
        self.assertEqual(observed, [old])
        self.assertEqual(history["load_run_history"](), new)

    def test_bad_history_entry_does_not_hide_good_records(self):
        history = self.history()
        valid = {"id": "valid", "run_at": "2026-10-01T09:00:00"}
        history["HISTORY_FILE"].write_text(json.dumps([None, valid, "invalid"]), encoding="utf-8")
        self.assertEqual(history["load_run_history"](), [valid])

    def test_damaged_history_is_not_silently_overwritten(self):
        history = self.history()
        damaged = "{interrupted historical JSON"
        history["HISTORY_FILE"].write_text(damaged, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Run History"):
            history["save_run_history"]([{"id": "new"}])
        self.assertEqual(history["HISTORY_FILE"].read_text(encoding="utf-8"), damaged)

    def test_missing_current_iif_never_returns_another_dates_file(self):
        from app.membership_payments import write_membership_payments_file

        for name in ("input", "iif", "logs", "tmp"):
            (self.root / name).mkdir()
        engine = self.root / "engine.py"
        engine.write_text("# synthetic process boundary", encoding="utf-8")
        prior = self.root / "iif" / "deposit_20260913.iif"
        prior.write_bytes(b"synthetic prior IIF")
        namespace = definitions({"run_engine"}, {
            "Path": Path, "date": date, "ROOT": self.root, "ENGINE_PATH": engine,
            "INPUT_DIR": self.root / "input", "QB_IMPORT_DIR": self.root / "iif",
            "LOG_DIR": self.root / "logs", "RUNTIME_TEMP_DIR": self.root / "tmp",
            "write_membership_payments_file": write_membership_payments_file,
            "build_engine_command": lambda **kwargs: ["synthetic-engine"],
            # Only the external process is simulated: it reports success but fails
            # to create today's expected artifact. File selection remains real.
            "subprocess": SimpleNamespace(run=lambda *args, **kwargs: SimpleNamespace(
                returncode=0, stdout="Synthetic successful process without output", stderr="")),
            "parse_iif": lambda path: ([], None),
            "parse_validation": lambda *args: {"all_ok": True},
        })
        upload = SimpleNamespace(name="report.xlsx", getvalue=lambda: b"synthetic input")
        with self.assertRaisesRegex(RuntimeError, "IIF"):
            namespace["run_engine"](upload, upload, date(2026, 9, 14), [], "automatic", "quickbooks", None, None, None)
        self.assertEqual(prior.read_bytes(), b"synthetic prior IIF")


if __name__ == "__main__":
    unittest.main()
