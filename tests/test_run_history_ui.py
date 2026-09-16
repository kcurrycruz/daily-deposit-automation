import ast
import json
import re
import unittest
from datetime import date, datetime
from importlib.util import find_spec
from pathlib import Path
from uuid import uuid4

from tests.sms_fixture_factory import sms_exports_091426


class Uploaded:
    def __init__(self, name, data):
        self.name = name
        self._data = data

    def getvalue(self):
        return self._data


def uploaded_files_from_sms_rows(exports):
    return [
        Uploaded(report.filename, f"source bytes for {report.role}".encode("utf-8"))
        for report in exports
    ]


def complete_result_091426():
    return {
        "iif_path": Path("deposit_20260914.iif"),
        "iif_bytes": b"IIF body",
        "reporting_workbook_bytes": b"XLSX body",
        "reporting_workbook_name": "SubDept Single Total Report 9-14-26.xlsx",
        "validation": {
            "all_ok": True,
            "sales_ok": True,
            "discounts_ok": True,
            "hash_ok": True,
            "iif_ok": True,
            "card_settlement_ok": True,
        },
    }


class RecordingUI:
    def __init__(self, clicked_keys=()):
        self.events = []
        self.clicked_keys = set(clicked_keys)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def markdown(self, body, **kwargs):
        self.events.append(("markdown", body, kwargs))

    def caption(self, body, **kwargs):
        self.events.append(("caption", body, kwargs))

    def warning(self, body, **kwargs):
        self.events.append(("warning", body, kwargs))

    def selectbox(self, label, **kwargs):
        self.events.append(("selectbox", label, kwargs))
        return kwargs["options"][0]

    def download_button(self, label, **kwargs):
        self.events.append(("download_button", label, kwargs))

    def expander(self, label, **kwargs):
        self.events.append(("expander", label, kwargs))
        return self

    def button(self, label, **kwargs):
        self.events.append(("button", label, kwargs))
        return kwargs.get("key") in self.clicked_keys


class RunHistoryUITests(unittest.TestCase):
    def test_history_archives_six_sources_report_and_iif(self):
        source = Path(__file__).resolve().parents[1] / "streamlit_app.py"
        function_names = {
            "_safe_history_name",
            "load_run_history",
            "save_run_history",
            "archive_run",
        }
        nodes = [
            node
            for node in ast.parse(source.read_text(encoding="utf-8")).body
            if isinstance(node, ast.FunctionDef) and node.name in function_names
        ]
        history_root = Path(__file__).parent / f"_run_history_{uuid4().hex}"
        upload_dir = history_root / "uploads"
        iif_dir = history_root / "iif"
        upload_dir.mkdir(parents=True)
        iif_dir.mkdir()
        try:
            namespace = {
                "Path": Path,
                "date": date,
                "datetime": datetime,
                "json": json,
                "re": re,
                "HISTORY_DIR": history_root,
                "HISTORY_FILE": history_root / "run_history.json",
                "HISTORY_UPLOAD_DIR": upload_dir,
                "HISTORY_IIF_DIR": iif_dir,
            }
            exec(
                compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"),
                namespace,
            )
            uploads = uploaded_files_from_sms_rows(sms_exports_091426())
            expected_names = [upload.name for upload in uploads]
            record = namespace["archive_run"](
                uploads,
                Uploaded("settlement.xlsx", b"settlement workbook"),
                complete_result_091426(),
                date(2026, 9, 14),
                {},
                {},
            )

            self.assertEqual(set(record["sms_source_filenames"]), set(expected_names))
            self.assertEqual(len(record["archived_sms_sources"]), 6)
            for path in record["archived_sms_sources"]:
                self.assertTrue(Path(path).is_file())
            self.assertTrue(Path(record["archived_reporting_workbook"]).is_file())
            self.assertEqual(
                Path(record["archived_reporting_workbook"]).read_bytes(),
                b"XLSX body",
            )
            self.assertTrue(Path(record["archived_settlement"]).is_file())
            self.assertTrue(Path(record["archived_iif"]).is_file())
        finally:
            for path in sorted(history_root.rglob("*"), reverse=True):
                path.unlink() if path.is_file() else path.rmdir()
            history_root.rmdir()

    def test_failed_validation_archives_no_internal_workbook_or_history_download(self):
        import app.run_history_ui as run_history_ui

        source = Path(__file__).resolve().parents[1] / "streamlit_app.py"
        function_names = {
            "_safe_history_name",
            "load_run_history",
            "save_run_history",
            "archive_run",
        }
        nodes = [
            node
            for node in ast.parse(source.read_text(encoding="utf-8")).body
            if isinstance(node, ast.FunctionDef) and node.name in function_names
        ]

        history_root = Path(__file__).parent / f"_run_history_{uuid4().hex}"
        history_root.mkdir()
        try:
            upload_dir = history_root / "uploads"
            iif_dir = history_root / "iif"
            upload_dir.mkdir()
            iif_dir.mkdir()
            namespace = {
                "Path": Path,
                "date": date,
                "datetime": datetime,
                "json": json,
                "re": re,
                "HISTORY_DIR": history_root,
                "HISTORY_FILE": history_root / "run_history.json",
                "HISTORY_UPLOAD_DIR": upload_dir,
                "HISTORY_IIF_DIR": iif_dir,
            }
            exec(
                compile(
                    ast.Module(body=nodes, type_ignores=[]),
                    str(source),
                    "exec",
                ),
                namespace,
            )
            record = namespace["archive_run"](
                [Uploaded("091426-sales.xls", b"sales source")],
                Uploaded("settlement.xlsx", b"settlement workbook"),
                {
                    "iif_path": Path("failed.iif"),
                    "iif_bytes": b"failed validation IIF",
                    "reporting_workbook_bytes": b"internal generated workbook",
                    "reporting_workbook_name": "Internal Working Workbook.xlsx",
                    "validation": {"all_ok": False},
                },
                date(2026, 9, 14),
                {},
                {},
            )

            ui = RecordingUI()
            run_history_ui.render_run_history(
                ui,
                records=[record],
                option_labeler=lambda item: "09/14/2026 · Review",
                run_time_formatter=lambda value, include_date=False: "09/14/2026",
            )
            download_labels = [
                event[1] for event in ui.events if event[0] == "download_button"
            ]
            archived_bytes = [
                path.read_bytes()
                for path in history_root.rglob("*")
                if path.is_file()
            ]
        finally:
            for path in sorted(history_root.rglob("*"), reverse=True):
                path.unlink() if path.is_file() else path.rmdir()
            history_root.rmdir()

        self.assertIsNone(record.get("archived_upload"))
        self.assertIsNone(record.get("archived_reporting_workbook"))
        self.assertNotIn("Download Daily Reporting Workbook", download_labels)
        self.assertNotIn(b"internal generated workbook", archived_bytes)

    def test_sidebar_collapse_request_is_consumed_once_on_program_entry(self):
        from app.program_hub_ui import SIDEBAR_COLLAPSE_REQUEST_KEY
        from app.run_history_ui import render_sidebar_collapse_request

        state = {SIDEBAR_COLLAPSE_REQUEST_KEY: True}
        scripts = []

        def component_html(body, **kwargs):
            scripts.append((body, kwargs))

        self.assertTrue(render_sidebar_collapse_request(component_html, state))
        self.assertNotIn(SIDEBAR_COLLAPSE_REQUEST_KEY, state)
        self.assertEqual(len(scripts), 1)
        self.assertIn("stSidebarCollapseButton", scripts[0][0])
        self.assertIn("click()", scripts[0][0])
        self.assertIn("MutationObserver", scripts[0][0])
        self.assertIn("observer.disconnect()", scripts[0][0])
        self.assertEqual(scripts[0][1], {"height": 0, "width": 0})

        self.assertFalse(render_sidebar_collapse_request(component_html, state))
        self.assertEqual(len(scripts), 1)

    def test_daily_sidebar_places_all_programs_before_collapsed_run_history(self):
        import app.run_history_ui as run_history_ui

        renderer = getattr(run_history_ui, "render_daily_sidebar", None)
        self.assertTrue(callable(renderer), "Daily sidebar renderer is missing")

        ui = RecordingUI({"return_to_program_hub"})
        clicked = renderer(
            ui,
            records=[],
            option_labeler=lambda record: "unused",
            run_time_formatter=lambda value, include_date=False: "unused",
        )

        controls = [
            (event[0], event[1])
            for event in ui.events
            if event[0] in {"button", "expander"}
        ]
        self.assertEqual(
            controls,
            [("button", "← All Programs"), ("expander", "Run History")],
        )
        self.assertTrue(clicked)

    def test_run_history_is_collapsed_by_default(self):
        self.assertIsNotNone(find_spec("app.run_history_ui"))
        import app.run_history_ui as run_history_ui

        ui = RecordingUI()
        run_history_ui.render_run_history(
            ui,
            records=[
                {
                    "id": "run-1",
                    "report_date": "2026-09-04",
                    "run_at": "2026-09-08T12:22:54",
                    "status": "Passed",
                    "sales_status": "MATCH",
                    "discount_status": "MATCH",
                    "hash_status": "MATCH",
                    "iif_status": "MATCH",
                    "card_settlement_status": "MATCH",
                    "uploaded_filename": "daily.xlsx",
                    "settlement_filename": "settlement.xlsx",
                }
            ],
            option_labeler=lambda record: "09/04/2026 · Passed",
            run_time_formatter=lambda value, include_date=False: "09/08/2026 08:22 AM",
        )

        history_expanders = [event for event in ui.events if event[0] == "expander"]
        self.assertEqual(len(history_expanders), 1)
        self.assertEqual(history_expanders[0][1], "Run History")
        self.assertFalse(history_expanders[0][2]["expanded"])
        rendered_text = " ".join(
            str(event[1])
            for event in ui.events
            if event[0] in {"markdown", "caption"}
        )
        self.assertIn("Run details", rendered_text)
        self.assertIn("Files from this run", rendered_text)
        self.assertIn("daily.xlsx", rendered_text)
        self.assertIn("settlement.xlsx", rendered_text)

    def test_legacy_history_workbook_download_and_metadata_render_safely(self):
        import app.run_history_ui as run_history_ui

        history_root = Path(__file__).parent / f"_run_history_{uuid4().hex}"
        history_root.mkdir()
        archived_upload = history_root / "daily.xlsx"
        archived_upload.write_bytes(b"legacy workbook")
        try:
            ui = RecordingUI()
            run_history_ui.render_run_history(
                ui,
                records=[
                    {
                        "id": "legacy-run",
                        "report_date": "2026-09-14",
                        "run_at": "2026-09-14T12:00:00",
                        "status": "Passed",
                        "uploaded_filename": "<script>alert(1)</script>.xlsx",
                        "archived_upload": str(archived_upload),
                    }
                ],
                option_labeler=lambda record: "09/14/2026 · Passed",
                run_time_formatter=lambda value, include_date=False: "09/14/2026",
            )
        finally:
            archived_upload.unlink()
            history_root.rmdir()

        rendered_text = " ".join(
            str(event[1])
            for event in ui.events
            if event[0] in {"markdown", "caption"}
        )
        downloads = [event for event in ui.events if event[0] == "download_button"]
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;.xlsx", rendered_text)
        self.assertNotIn("<script>alert(1)</script>.xlsx", rendered_text)
        self.assertEqual(downloads[0][1], "Download Daily Reporting Workbook")
        self.assertEqual(downloads[0][2]["data"], b"legacy workbook")

    def test_failed_legacy_history_never_exposes_archived_workbook(self):
        import app.run_history_ui as run_history_ui

        history_root = Path(__file__).parent / f"_run_history_{uuid4().hex}"
        history_root.mkdir()
        archived_upload = history_root / "failed-internal.xlsx"
        archived_upload.write_bytes(b"failed internal workbook")
        try:
            ui = RecordingUI()
            run_history_ui.render_run_history(
                ui,
                records=[
                    {
                        "id": "legacy-failed-run",
                        "report_date": "2026-09-14",
                        "run_at": "2026-09-14T12:00:00",
                        "status": "Review",
                        "uploaded_filename": "failed-internal.xlsx",
                        "archived_upload": str(archived_upload),
                    }
                ],
                option_labeler=lambda record: "09/14/2026 · Review",
                run_time_formatter=lambda value, include_date=False: "09/14/2026",
            )
        finally:
            archived_upload.unlink()
            history_root.rmdir()

        downloads = [event for event in ui.events if event[0] == "download_button"]
        self.assertNotIn(
            "Download Daily Reporting Workbook",
            [event[1] for event in downloads],
        )
        self.assertNotIn(
            b"failed internal workbook",
            [event[2].get("data") for event in downloads],
        )


if __name__ == "__main__":
    unittest.main()
