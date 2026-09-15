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

    def test_reads_committed_biff_xls_fixture(self):
        report = parse_sms_export(
            "renamed-file.xls",
            Path("tests/fixtures/sms/minimal_sales.xls").read_bytes(),
        )

        self.assertEqual(report.role, "sales")
        self.assertEqual(report.report_date, date(2026, 9, 14))


if __name__ == "__main__":
    unittest.main()
