import unittest
from decimal import Decimal

from app.sms_deposit_data import build_sms_deposit_data
from app.sms_exports import SmsExport, build_sms_export_bundle
from tests.sms_fixture_factory import sms_exports_091426


class SmsDepositDataTests(unittest.TestCase):
    def test_091426_source_calculations_preserve_unusual_totals(self):
        data = build_sms_deposit_data(
            build_sms_export_bundle(sms_exports_091426())
        )

        self.assertEqual(data.sales_total, Decimal("86502.80"))
        self.assertEqual(data.coupon_total, Decimal("61.69"))
        self.assertEqual(data.store_coupons_raw, Decimal("-1428.18"))
        self.assertEqual(data.milk_bottle_export_total, Decimal("74.00"))
        self.assertEqual(data.store_coupons_adjusted, Decimal("-1354.18"))
        self.assertEqual(data.bs_data["milk_bottle_return"], Decimal("8.00"))
        self.assertEqual(data.iif_milk_bottle_return, Decimal("-82.00"))
        self.assertEqual(data.discount_total, Decimal("3981.21"))
        self.assertEqual(data.hash_refunded, Decimal("4.89"))
        self.assertEqual(data.hash_pass_through, Decimal("6.00"))

    def test_milk_bottles_only_sums_returned_item_net_sales(self):
        data = build_sms_deposit_data(
            build_sms_export_bundle(sms_exports_091426())
        )

        self.assertEqual(data.milk_bottle_export_total, Decimal("74.00"))

    def test_rejects_sales_detail_that_disagrees_with_its_control_total(self):
        reports = list(sms_exports_091426())
        sales_index = next(
            index for index, report in enumerate(reports) if report.role == "sales"
        )
        sales = reports[sales_index]
        reports[sales_index] = SmsExport(
            role=sales.role,
            filename=sales.filename,
            report_date=sales.report_date,
            rows=sales.rows[:-1] + (("Sales Total", "", "", "86500.00"),),
        )

        with self.assertRaisesRegex(ValueError, "Sales detail total"):
            build_sms_deposit_data(build_sms_export_bundle(reports))


if __name__ == "__main__":
    unittest.main()
