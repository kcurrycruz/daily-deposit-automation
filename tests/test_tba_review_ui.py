import unittest
from types import SimpleNamespace


class TbaReviewTests(unittest.TestCase):
    def test_review_rows_match_quickbooks_deposit_display(self):
        from app.ui_helpers import tba_quickbooks_rows

        result = {
            "lines": [
                SimpleNamespace(line_type="TRNS", account="1000000 · Bank", amount=25.0, memo="Deposit", qb_class=""),
                SimpleNamespace(line_type="SPL", account="4444 · TBA Purchases", amount=-30.0, memo="Unknown HASH item", qb_class="Admin"),
                SimpleNamespace(line_type="SPL", account="7110110 · Grocery", amount=-5.0, memo="Sales", qb_class=""),
                SimpleNamespace(line_type="SPL", account="4444 · TBA Purchases", amount=5.0, memo="PAID OUT: Correction", qb_class=""),
                SimpleNamespace(line_type="SPL", account="4444 · TBA Purchases", amount=None, memo="", qb_class=""),
            ]
        }

        self.assertEqual(
            tba_quickbooks_rows(result),
            [
                {"Account": "4444 · TBA Purchases", "Memo": "Unknown HASH item", "Class": "Admin", "Amount": "$30.00"},
                {"Account": "4444 · TBA Purchases", "Memo": "PAID OUT: Correction", "Class": "", "Amount": "-$5.00"},
            ],
        )

    def test_final_downloads_show_tba_note_and_lines_when_present(self):
        from app.guided_step_ui import render_prepare_iif_action

        class RecordingUI:
            def __init__(self):
                self.events = []

            def markdown(self, value):
                self.events.append(("markdown", value))

            def success(self, value):
                self.events.append(("success", value))

            def info(self, value):
                self.events.append(("info", value))

            def dataframe(self, value, **kwargs):
                self.events.append(("dataframe", value))

            def download_button(self, label, **kwargs):
                self.events.append(("download", label))

        ui = RecordingUI()
        tba_rows = [{"Account": "4444 · TBA Purchases", "Memo": "Unknown HASH item", "Class": "", "Amount": "$30.00"}]
        render_prepare_iif_action(
            ui,
            visible=True,
            download_details={
                "iif": {"data": b"IIF", "file_name": "deposit.iif"},
                "report": {"data": b"XLSX", "file_name": "report.xlsx"},
            },
            download_status={"kind": "success", "message": "Both files are ready to download."},
            disabled=False,
            tba_rows=tba_rows,
        )

        self.assertEqual([event[0] for event in ui.events if event[0] == "download"], ["download", "download"])
        self.assertTrue(any(event[0] == "info" and "TBA" in event[1] for event in ui.events))
        self.assertEqual([event[1] for event in ui.events if event[0] == "dataframe"], [tba_rows])


if __name__ == "__main__":
    unittest.main()
