import unittest
from datetime import date
from pathlib import Path

from app.sms_exports import classify_sms_rows, parse_sms_export
from tests.sms_fixture_factory import sms_rows


class SmsExportTests(unittest.TestCase):
    def test_classifies_each_report_from_content_instead_of_filename(self):
        cases = {
            "sales": sms_rows("sales"),
            "coupons": sms_rows("coupons"),
            "discounts": sms_rows("discounts"),
            "hash": sms_rows("hash"),
            "bs": sms_rows("bs"),
            "milk_bottles": sms_rows("milk_bottles"),
        }

        for expected, rows in cases.items():
            with self.subTest(role=expected):
                self.assertEqual(classify_sms_rows(rows), expected)

    def test_classifies_sales_when_data_contains_hash_totalizer_number(self):
        self.assertEqual(classify_sms_rows(sms_rows("sales")), "sales")

    def test_ignores_totalizer_words_in_non_header_rows(self):
        rows = sms_rows("sales") + (("Totalizer Adjustment", 6),)

        self.assertEqual(classify_sms_rows(rows), "sales")

    def test_reads_committed_biff_xls_fixture(self):
        report = parse_sms_export(
            "renamed-file.xls",
            Path("tests/fixtures/sms/minimal_sales.xls").read_bytes(),
        )

        self.assertEqual(report.role, "sales")
        self.assertEqual(report.report_date, date(2026, 9, 14))

    def test_reads_single_cell_date_and_preserves_numeric_cells(self):
        report = parse_sms_export(
            "single-date.xls",
            Path("tests/fixtures/sms/minimal_single_sales.xls").read_bytes(),
        )

        self.assertEqual(report.report_date, date(2026, 9, 14))
        self.assertEqual(report.rows[3][1], 3.0)
        self.assertIsInstance(report.rows[3][1], float)

    def test_rejects_conflicting_split_cell_dates(self):
        with self.assertRaisesRegex(ValueError, "ambiguous report dates"):
            parse_sms_export(
                "conflicting-dates.xls",
                Path("tests/fixtures/sms/minimal_conflicting_sales.xls").read_bytes(),
            )

    def test_rejects_conflicting_single_cell_dates(self):
        with self.assertRaisesRegex(ValueError, "ambiguous report dates"):
            parse_sms_export(
                "conflicting-inline-dates.xls",
                Path(
                    "tests/fixtures/sms/minimal_conflicting_inline_sales.xls"
                ).read_bytes(),
            )

    def test_rejects_undated_report(self):
        with self.assertRaisesRegex(ValueError, "does not contain a report date"):
            parse_sms_export(
                "undated.xls",
                Path("tests/fixtures/sms/minimal_undated_sales.xls").read_bytes(),
            )

    def test_rejects_unreadable_file_with_user_facing_message(self):
        with self.assertRaisesRegex(ValueError, "could not be read"):
            parse_sms_export("not-a-workbook.xls", b"not a workbook")

    def test_rejects_ambiguous_report_content(self):
        ambiguous_rows = sms_rows("sales") + (("Tlz.:", 3542, "to", 3542),)

        with self.assertRaisesRegex(ValueError, "ambiguous content"):
            classify_sms_rows(ambiguous_rows)


if __name__ == "__main__":
    unittest.main()
