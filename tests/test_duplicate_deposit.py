import ast
import json
import re
import unittest
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4


class Uploaded:
    def __init__(self, name, data):
        self.name = name
        self.data = data

    def getvalue(self):
        return self.data


class DuplicateDepositTests(unittest.TestCase):
    def test_latest_prior_iif_run_uses_same_date_and_newest_generated_iif(self):
        from app.run_history_ui import latest_prior_iif_run

        records = [
            {"id": "old", "report_date": "2026-09-14", "run_at": "2026-09-14T09:00:00", "archived_iif": "old.iif"},
            {"id": "other-date", "report_date": "2026-09-15", "run_at": "2026-09-15T11:00:00", "archived_iif": "other.iif"},
            {"id": "no-iif", "report_date": "2026-09-14", "run_at": "2026-09-14T12:00:00"},
            {"id": "new", "report_date": "2026-09-14", "run_at": "2026-09-14T10:00:00", "archived_iif": "new.iif"},
        ]

        self.assertEqual(latest_prior_iif_run(records, date(2026, 9, 14))["id"], "new")
        self.assertIsNone(latest_prior_iif_run(records, date(2026, 9, 16)))

    def test_archived_run_stores_deposit_total_for_future_warning(self):
        source = Path(__file__).resolve().parents[1] / "streamlit_app.py"
        names = {"_safe_history_name", "load_run_history", "save_run_history", "archive_run"}
        nodes = [
            node for node in ast.parse(source.read_text(encoding="utf-8")).body
            if isinstance(node, ast.FunctionDef) and node.name in names
        ]
        root = Path(__file__).parent / f"_duplicate_history_{uuid4().hex}"
        root.mkdir()
        try:
            upload_dir = root / "uploads"
            iif_dir = root / "iif"
            upload_dir.mkdir()
            iif_dir.mkdir()
            namespace = {
                "Path": Path, "date": date, "datetime": datetime, "json": json,
                "re": re, "HISTORY_DIR": root, "HISTORY_FILE": root / "run_history.json",
                "HISTORY_UPLOAD_DIR": upload_dir, "HISTORY_IIF_DIR": iif_dir,
            }
            exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), namespace)
            record = namespace["archive_run"](
                [Uploaded("Sales.xls", b"sales")],
                Uploaded("settlement.xlsx", b"settlement"),
                {
                    "iif_path": Path("deposit_20260914.iif"),
                    "iif_bytes": b"IIF",
                    "validation": {"all_ok": True, "deposit_total": 7531.06},
                },
                date(2026, 9, 14), {}, {},
            )

            self.assertEqual(record["deposit_total"], 7531.06)
            self.assertEqual(json.loads((root / "run_history.json").read_text())[0]["deposit_total"], 7531.06)
        finally:
            for path in sorted(root.rglob("*"), reverse=True):
                path.unlink() if path.is_file() else path.rmdir()
            root.rmdir()
