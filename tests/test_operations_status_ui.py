import unittest
from datetime import date
from pathlib import Path


class OperationsStatusModelTests(unittest.TestCase):
    def test_no_uploads_is_waiting_for_workbook(self):
        from app.operations_status_ui import build_operations_status
        status = build_operations_status(deposit_date=None, daily_uploaded=False, settlement_uploaded=False, workbook_valid=False, settlement_valid=False, workflow_complete=False, iif_generated=False)
        self.assertEqual(status.deposit_date, "Waiting for workbook")
        self.assertEqual(status.files, "0 of 2 uploaded")
        self.assertEqual(status.iif, "Not ready")
        self.assertEqual(status.state, "waiting")
        self.assertEqual(status.deposit_progress, 0)
        self.assertEqual(status.files_progress, 0)
        self.assertEqual(status.iif_progress, 0)

    def test_no_uploads_ignores_non_none_deposit_date(self):
        from app.operations_status_ui import build_operations_status

        status = build_operations_status(
            deposit_date=date(2026, 9, 8),
            daily_uploaded=False,
            settlement_uploaded=False,
            workbook_valid=False,
            settlement_valid=False,
            workflow_complete=False,
            iif_generated=False,
        )

        self.assertEqual(status.deposit_date, "Waiting for workbook")

    def test_daily_only_identifies_card_settlement_as_needed(self):
        from app.operations_status_ui import build_operations_status
        status = build_operations_status(deposit_date=date(2026, 9, 8), daily_uploaded=True, settlement_uploaded=False, workbook_valid=True, settlement_valid=False, workflow_complete=False, iif_generated=False)
        self.assertEqual(status.deposit_date, "09/08/2026")
        self.assertEqual(status.files, "1 of 2 uploaded · Card Settlement needed")
        self.assertEqual(status.iif, "Not ready")
        self.assertEqual(status.state, "waiting")
        self.assertEqual(status.deposit_progress, 100)
        self.assertEqual(status.files_progress, 50)
        self.assertEqual(status.iif_progress, 0)

    def test_settlement_only_identifies_daily_workbook_as_needed(self):
        from app.operations_status_ui import build_operations_status
        status = build_operations_status(deposit_date=date(2026, 9, 8), daily_uploaded=False, settlement_uploaded=True, workbook_valid=False, settlement_valid=True, workflow_complete=False, iif_generated=False)
        self.assertEqual(status.deposit_date, "09/08/2026")
        self.assertEqual(status.files, "1 of 2 uploaded · Daily Workbook needed")
        self.assertEqual(status.iif, "Not ready")
        self.assertEqual(status.state, "waiting")

    def test_both_valid_incomplete_workflow_is_active(self):
        from app.operations_status_ui import build_operations_status
        status = build_operations_status(deposit_date=date(2026, 9, 8), daily_uploaded=True, settlement_uploaded=True, workbook_valid=True, settlement_valid=True, workflow_complete=False, iif_generated=False)
        self.assertEqual(status.files, "2 of 2 verified")
        self.assertEqual(status.iif, "Complete guided steps")
        self.assertEqual(status.state, "active")
        self.assertEqual(status.files_progress, 100)
        self.assertEqual(status.iif_progress, 50)

    def test_complete_workflow_is_ready(self):
        from app.operations_status_ui import build_operations_status
        status = build_operations_status(deposit_date=date(2026, 9, 8), daily_uploaded=True, settlement_uploaded=True, workbook_valid=True, settlement_valid=True, workflow_complete=True, iif_generated=False)
        self.assertEqual(status.iif, "Ready to prepare IIF")
        self.assertEqual(status.state, "ready")
        self.assertEqual(status.iif_progress, 75)

    def test_generated_iif_is_ready_to_download(self):
        from app.operations_status_ui import build_operations_status
        status = build_operations_status(deposit_date=date(2026, 9, 8), daily_uploaded=True, settlement_uploaded=True, workbook_valid=True, settlement_valid=True, workflow_complete=True, iif_generated=True)
        self.assertEqual(status.iif, "Ready to download")
        self.assertEqual(status.state, "ready")
        self.assertEqual(status.iif_progress, 100)

    def test_invalid_uploaded_pair_needs_attention(self):
        from app.operations_status_ui import build_operations_status
        status = build_operations_status(deposit_date=date(2026, 9, 8), daily_uploaded=True, settlement_uploaded=True, workbook_valid=False, settlement_valid=True, workflow_complete=False, iif_generated=False)
        self.assertEqual(status.files, "2 of 2 uploaded · Needs attention")
        self.assertEqual(status.iif, "Needs attention")
        self.assertEqual(status.state, "attention")


class OperationsStatusRendererTests(unittest.TestCase):
    def test_html_has_three_escaped_status_items_and_state_wrapper(self):
        from app.operations_status_ui import OperationsStatus, operations_status_html
        status = OperationsStatus(
            "<script>alert('x')</script>",
            "2 of 2 & verified",
            "Ready to prepare IIF",
            "ready&safe",
            deposit_progress=100,
            files_progress=50,
            iif_progress=75,
        )
        rendered = operations_status_html(status)
        self.assertIn('class="hwfc-ops-status is-ready&amp;safe"', rendered)
        self.assertIn('aria-label="Deposit status"', rendered)
        self.assertEqual(rendered.count("hwfc-ops-status-item"), 3)
        self.assertEqual(rendered.count('role="progressbar"'), 3)
        self.assertIn('aria-label="Deposit date progress"', rendered)
        self.assertIn('aria-valuenow="100"', rendered)
        self.assertIn('style="width: 50%"', rendered)
        self.assertIn('style="width: 75%"', rendered)
        self.assertIn("Deposit date", rendered)
        self.assertIn("Files", rendered)
        self.assertIn("IIF status", rendered)
        self.assertIn("&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;", rendered)
        self.assertIn("2 of 2 &amp; verified", rendered)
        self.assertNotIn("<script>", rendered)

    def test_renderer_passes_html_to_markdown(self):
        from app.operations_status_ui import OperationsStatus, render_operations_status
        class RecordingUI:
            def __init__(self): self.calls = []
            def markdown(self, body, **kwargs): self.calls.append((body, kwargs))
        ui = RecordingUI()
        render_operations_status(ui, OperationsStatus("09/08/2026", "2 of 2 verified", "Not ready", "active"))
        self.assertEqual(len(ui.calls), 1)
        self.assertEqual(ui.calls[0][1], {"unsafe_allow_html": True})
        self.assertIn("Deposit status", ui.calls[0][0])


class OperationsStatusStyleContractTests(unittest.TestCase):
    def test_operations_status_css_supports_compact_ready_and_attention_states(self):
        source = Path(__file__).resolve().parents[1].joinpath("streamlit_app.py").read_text(encoding="utf-8")

        self.assertIn(".hwfc-ops-status {", source)
        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr));", source)
        self.assertIn("@media (max-width: 720px)", source)
        self.assertIn(".hwfc-ops-status.is-attention", source)

    def test_streamlit_app_keeps_the_horizontal_bubble_renderer(self):
        source = Path(__file__).resolve().parents[1].joinpath("streamlit_app.py").read_text(encoding="utf-8")

        self.assertIn("render_deposit_step_panels(", source)
        self.assertNotIn("guided rail", source.lower())


if __name__ == "__main__":
    unittest.main()
