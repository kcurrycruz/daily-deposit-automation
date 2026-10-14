"""Empty SMS detail amounts must not block otherwise valid daily reports."""

from dataclasses import replace
from decimal import Decimal
import unittest

from app.sms_deposit_data import build_sms_deposit_data
from app.sms_exports import build_sms_export_bundle
from tests.sms_fixture_factory import sms_exports_091426


def bundle_with_blank_detail_amounts():
    blank_rows = {
        "sales": (170, "Adjustments", 0, None, ""),
        "coupons": (142, "Bulk Herbs", 0, None, ""),
        "discounts": (4, "No Discount", ""),
        "hash": (99, "Unused HASH", 0, None, ""),
        "bs": (980, "Rev. Prepaid card/voucher", None),
        "milk_bottles": ("Other Item", None),
    }
    control_rows = {"sales": 1, "coupons": 2, "discounts": 1, "hash": 1,
                    "bs": 0, "milk_bottles": 2}
    reports = []
    for report in sms_exports_091426():
        tail = control_rows[report.role]
        rows = (report.rows[:-tail] + (blank_rows[report.role],) + report.rows[-tail:]
                if tail else report.rows + (blank_rows[report.role],))
        reports.append(replace(report, rows=rows))
    return build_sms_export_bundle(reports)


class BlankDetailAmountTests(unittest.TestCase):
    def test_blank_optional_rows_in_six_reports_do_not_block_valid_totals(self):
        data = build_sms_deposit_data(bundle_with_blank_detail_amounts())

        self.assertEqual(data.sales_total, Decimal("86502.80"))
        self.assertNotIn(170, data.sales_by_subdept)
        self.assertEqual(data.coupon_total, Decimal("61.69"))
        self.assertNotIn(142, data.coupons_by_subdept)
        self.assertEqual(data.discount_total, Decimal("3981.21"))
        self.assertEqual(data.hash_paid_in, Decimal("12.00"))
        self.assertEqual(data.bs_data["prepaid_card"], Decimal("0.00"))
        self.assertEqual(data.milk_bottle_export_total, Decimal("74.00"))


if __name__ == "__main__":
    unittest.main()
