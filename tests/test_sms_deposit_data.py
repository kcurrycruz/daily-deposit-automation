import unittest
from datetime import date
from decimal import Decimal

from app.sms_deposit_data import build_sms_deposit_data
from app.sms_exports import SmsExport, build_sms_export_bundle
from tests.sms_fixture_factory import sms_exports_091426


class SmsDepositDataTests(unittest.TestCase):
    def test_real_sms_layouts_preserve_091426_controls(self):
        report_date = date(2026, 9, 14)
        reports = (
            SmsExport(
                role="sales",
                filename="091426 Sales.xls",
                report_date=report_date,
                rows=(
                    (("Sub-department Single Total",) + ("",) * 11),
                    (("Date: ", "9/14/2026", "to", "9/14/2026") + ("",) * 8),
                    (("", "", "Sub-Department", "", "", "", "", "Qty", "Amount", "Pkg/Weight") + ("",) * 2),
                    (("", 27, "Store coupons", "", "", "", None, -1428.18, "", "") + ("",) * 2),
                    (("", 110, "Grocery Non-Tax", "", "", "", 1, 87930.98, "", "") + ("",) * 2),
                    (("", "", "", "", "Total", "", 1, "", 86502.80, 4519.652) + ("",) * 2),
                ),
            ),
            SmsExport(
                role="coupons",
                filename="091426 Coupon.xls",
                report_date=report_date,
                rows=(
                    (("Sub-department Single Total",) + ("",) * 11),
                    (("Date: ", "9/14/2026", "to", "9/14/2026") + ("",) * 8),
                    (("", "", "Sub-Department", "", "", "", "", "Qty", "Amount", "Pkg/Weight") + ("",) * 2),
                    (("", 110, "Grocery Non-Tax", "", "", "", 1, 61.69, "", "") + ("",) * 2),
                    (("", "", "", "", "Total", "", 1, "", 61.69, "") + ("",) * 2),
                ),
            ),
            SmsExport(
                role="discounts",
                filename="091426 Discount.xls",
                report_date=report_date,
                rows=(
                    (("Discounts by Shopper Level",) + ("",) * 11),
                    (("", "", "Description", "", "", "", "", "", "Qty", "Amount", "Other", "")),
                    (("Shareholder", "", "", 2, "", "", "", 1, 1200.00, "", "", "")),
                    (("Senior Share", "", "", 4, "", "", "", 1, 2781.21, "", "", "")),
                    (("", "", "Grand Total", "", "", "", "", "", "", "", "", "")),
                    (("", "", "Member Discounts", "", "", "", "", 2, 3981.21, "", "", "")),
                ),
            ),
            SmsExport(
                role="hash",
                filename="091426 Hash.xls",
                report_date=report_date,
                rows=(
                    (("Sub-department Single Total",) + ("",) * 11),
                    (("", "", "Sub-Department", "", "", "", "", "Qty", "Amount", "Pkg/Weight") + ("",) * 2),
                    (("", 23, "Refunded Discounts", "", "", "", 8, 4.89, "", "") + ("",) * 2),
                    (("", 32, "PASS THROUGH DONATIONS", "", "", "", 6, 6.00, "", "") + ("",) * 2),
                    (("", "", "", "", "Total", "", 14, "", 10.89, "") + ("",) * 2),
                ),
            ),
            SmsExport(
                role="bs",
                filename="091426 BS.xls",
                report_date=report_date,
                rows=(
                    (("Store Balance Sheet",) + ("",) * 11),
                    (("", "", "Description", "", "", "Amount", "", "Balance", "", "Debit", "Credit", "")),
                    ((120, "STORE COUPONS", "", 0, -1428.18, "", "C", "", "", "", -1428.18, "")),
                    ((910, "Milk Bottle Return", "", "", 8.00, "", "", "", "", "", "", "")),
                ),
            ),
            SmsExport(
                role="milk_bottles",
                filename="91426 milk bottles.xls",
                report_date=report_date,
                rows=(
                    (("Item Multi Totals by Sub-department",) + ("",) * 11),
                    (("", "Code", "", "", "", "Description", "", "Qty/Weight", "", "Amount", "", "Units")),
                    ((111251, "", "MILK BOTTLE - 1 - RETURNED $2", "", "", "", "", "", "", "", "", "")),
                    (("", "", "Net Sales", "", "", "", "", "", -20.00, "", "", "")),
                    ((111252, "", "MILK BOTTLES - 2 - RETURNED $4", "", "", "", "", "", "", "", "", "")),
                    (("", "", "Net Sales", "", "", "", "", "", -32.00, "", "", "")),
                    ((111253, "", "MILK BOTTLES - 3 - RETURNED $6", "", "", "", "", "", "", "", "", "")),
                    (("", "", "Net Sales", "", "", "", "", "", -6.00, "", "", "")),
                    ((111254, "", "MILK BOTTLES - 4 - RETURNED $8", "", "", "", "", "", "", "", "", "")),
                    (("", "", "Net Sales", "", "", "", "", "", -16.00, "", "", "")),
                    (("", "", "Grand Total", "", "", "", "", "", "", "", "", "")),
                    (("", "", "", "Net Sales", "", "", "", "", -1408.18, "", "", "")),
                ),
            ),
        )

        data = build_sms_deposit_data(build_sms_export_bundle(reports))

        self.assertEqual(data.sales_total, Decimal("86502.80"))
        self.assertEqual(data.coupon_total, Decimal("61.69"))
        self.assertEqual(data.store_coupons_raw, Decimal("-1428.18"))
        self.assertEqual(data.milk_bottle_export_total, Decimal("74.00"))
        self.assertEqual(data.bs_data["milk_bottle_return"], Decimal("8.00"))
        self.assertEqual(data.iif_milk_bottle_return, Decimal("-82.00"))
        self.assertEqual(data.discount_total, Decimal("3981.21"))
        self.assertEqual(data.hash_refunded, Decimal("4.89"))
        self.assertEqual(data.hash_pass_through, Decimal("6.00"))

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

    def test_hash_uses_printed_amount_total_when_paid_in_adds_a_right_hand_value(self):
        reports = list(sms_exports_091426())
        hash_index = next(
            index for index, report in enumerate(reports) if report.role == "hash"
        )
        hash_report = reports[hash_index]
        reports[hash_index] = SmsExport(
            role=hash_report.role,
            filename="090226 Hash.xls",
            report_date=hash_report.report_date,
            rows=(
                (("Sub-department Single Total",) + ("",) * 11),
                (("", "", "Sub-Department", "", "", "", "", "Qty", "Amount", "Pkg/Weight") + ("",) * 2),
                (("", 23, "Refunded Discounts", "", "", "", 1, 1.00, "", "") + ("",) * 2),
                (("", 32, "PASS THROUGH DONATIONS", "", "", "", 1, 1.00, "", "") + ("",) * 2),
                (("", 34, "PAID-INS", "", "", "", 1, 13.98, "", 13.98) + ("",) * 2),
                (("", "", "", "", "Total", "", 3, "", 15.98, 13.98) + ("",) * 2),
            ),
        )

        data = build_sms_deposit_data(build_sms_export_bundle(reports))

        self.assertEqual(data.hash_refunded, Decimal("1.00"))
        self.assertEqual(data.hash_pass_through, Decimal("1.00"))
        self.assertEqual(data.hash_paid_in, Decimal("13.98"))

    def test_hash_preserves_signed_detail_amounts_for_control_validation(self):
        reports = list(sms_exports_091426())
        hash_index = next(
            index for index, report in enumerate(reports) if report.role == "hash"
        )
        hash_report = reports[hash_index]
        reports[hash_index] = SmsExport(
            role=hash_report.role,
            filename="082326 Hash.xls",
            report_date=hash_report.report_date,
            rows=(
                (("Sub-department Single Total",) + ("",) * 11),
                (("", "", "Sub-Department", "", "", "", "", "Qty", "Amount", "Pkg/Weight") + ("",) * 2),
                (("", 23, "Refunded Discounts", "", "", "", "", -70.06, "", "") + ("",) * 2),
                (("", 32, "PASS THROUGH DONATIONS", "", "", "", 1, 1.00, "", "") + ("",) * 2),
                (("", "", "", "", "Total", "", 1, "", -69.06, "") + ("",) * 2),
            ),
        )

        data = build_sms_deposit_data(build_sms_export_bundle(reports))

        self.assertEqual(data.hash_refunded, Decimal("-70.06"))
        self.assertEqual(data.hash_pass_through, Decimal("1.00"))

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
