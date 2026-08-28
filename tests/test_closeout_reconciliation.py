from io import BytesIO

import openpyxl
import unittest


STANDARD_ORDER = (
    "cash",
    "checks",
    "donation",
    "charge_house",
    "offline_zon",
    "vendor_coupons",
    "paid_out",
    "paid_in",
)


BS_VALUES = {
    901: 1250.00,
    902: 75.00,
    1122: 20.00,
    906: 45.00,
    934: -12.00,
    908: 188.25,
    1114: 47.06,
}


def workbook_bytes(
    *, paid_in_column=1, paid_in_amount=30.00, bs_values=None, preceding_amount_like_header=False
):
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    balance_sheet = workbook.create_sheet("Daily BS")
    hash_sheet = workbook.create_sheet("Daily HASH")

    for code, amount in (bs_values or BS_VALUES).items():
        balance_sheet.append([code, None, None, None, amount])

    hash_header = ["Code", "Description", "Notes", "Type", "aMoUnT"]
    if preceding_amount_like_header:
        hash_header[1] = "Net Amount"
    hash_sheet.append(hash_header)
    hash_row = [None] * 5
    hash_row[paid_in_column - 1] = 34
    if preceding_amount_like_header:
        hash_row[1] = 999.99
    hash_row[4] = paid_in_amount
    hash_sheet.append(hash_row)

    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


class CloseoutReconciliationTests(unittest.TestCase):
    def test_read_closeout_baselines_returns_approved_key_order_and_values(self):
        from app.closeout_reconciliation import (
            STANDARD_CLOSEOUT_ORDER,
            read_closeout_baselines,
        )

        result = read_closeout_baselines(
            workbook_bytes(), "Daily BS", "Daily HASH"
        )

        self.assertEqual(STANDARD_CLOSEOUT_ORDER, STANDARD_ORDER)
        self.assertEqual(tuple(result), STANDARD_ORDER)
        self.assertEqual(result["cash"], 1250.00)
        self.assertEqual(result["checks"], 75.00)
        self.assertEqual(result["donation"], 20.00)
        self.assertEqual(result["charge_house"], 45.00)
        self.assertEqual(result["offline_zon"], 12.00)
        self.assertEqual(result["vendor_coupons"], 188.25)
        self.assertEqual(result["paid_out"], 47.06)
        self.assertEqual(result["paid_in"], 30.00)


    def test_default_closeout_actuals_preserve_baselines_except_counted_coupons_and_offline_zon(
        self,
    ):
        from app.closeout_reconciliation import default_closeout_actuals

        baselines = {
            "cash": 1250.00,
            "checks": 75.00,
            "donation": 20.00,
            "charge_house": 45.00,
            "offline_zon": 12.00,
            "vendor_coupons": 188.25,
            "paid_out": 47.06,
            "paid_in": 30.00,
        }

        result = default_closeout_actuals(baselines, 152.25)

        self.assertEqual(tuple(result), STANDARD_ORDER)
        self.assertEqual(result["cash"], 1250.00)
        self.assertEqual(result["offline_zon"], 0.00)
        self.assertEqual(result["vendor_coupons"], 152.25)
        self.assertEqual(baselines["offline_zon"], 12.00)
        self.assertEqual(baselines["vendor_coupons"], 188.25)


    def test_read_closeout_baselines_finds_paid_in_code_in_any_first_four_columns(self):
        from app.closeout_reconciliation import read_closeout_baselines

        for paid_in_column in range(1, 5):
            with self.subTest(paid_in_column=paid_in_column):
                result = read_closeout_baselines(
                    workbook_bytes(paid_in_column=paid_in_column),
                    "Daily BS",
                    "Daily HASH",
                )
                self.assertEqual(result["paid_in"], 30.00)


    def test_read_closeout_baselines_requires_exact_amount_header(self):
        from app.closeout_reconciliation import read_closeout_baselines

        result = read_closeout_baselines(
            workbook_bytes(preceding_amount_like_header=True),
            "Daily BS",
            "Daily HASH",
        )

        self.assertEqual(result["paid_in"], 30.00)


    def test_default_closeout_actuals_rebuilds_canonical_normalized_float_mapping(self):
        from app.closeout_reconciliation import default_closeout_actuals

        baselines = {
            "paid_in": "30.004",
            "paid_out": "47.064",
            "vendor_coupons": "188.254",
            "offline_zon": "12.004",
            "charge_house": "45.004",
            "donation": "20.004",
            "checks": "75.004",
            "cash": "1250.004",
            "extra": "999.999",
        }

        result = default_closeout_actuals(baselines, "-152.256")

        self.assertEqual(tuple(result), STANDARD_ORDER)
        self.assertTrue(all(isinstance(value, float) for value in result.values()))
        self.assertEqual(result["cash"], 1250.00)
        self.assertEqual(result["checks"], 75.00)
        self.assertEqual(result["donation"], 20.00)
        self.assertEqual(result["charge_house"], 45.00)
        self.assertEqual(result["offline_zon"], 0.00)
        self.assertEqual(result["vendor_coupons"], 152.26)
        self.assertEqual(result["paid_out"], 47.06)
        self.assertEqual(result["paid_in"], 30.00)


    def test_read_closeout_baselines_requires_exact_requested_sheet_names(self):
        from app.closeout_reconciliation import read_closeout_baselines

        cases = [
            ("Missing BS", "Daily HASH", "Balance Sheet.*Missing BS"),
            ("Daily BS", "Missing HASH", "HASH.*Missing HASH"),
        ]
        for bs_sheet_name, hash_sheet_name, message in cases:
            with self.subTest(bs_sheet_name=bs_sheet_name), self.assertRaisesRegex(
                ValueError, message
            ):
                read_closeout_baselines(
                    workbook_bytes(), bs_sheet_name, hash_sheet_name
                )


    def test_read_closeout_baselines_rejects_invalid_monetary_data(self):
        from app.closeout_reconciliation import read_closeout_baselines

        invalid_bs_values = dict(BS_VALUES)
        invalid_bs_values[901] = "not money"

        with self.assertRaisesRegex(ValueError, "valid.*amount|monetary"):
            read_closeout_baselines(
                workbook_bytes(bs_values=invalid_bs_values),
                "Daily BS",
                "Daily HASH",
            )

        with self.assertRaisesRegex(ValueError, "valid.*amount|monetary"):
            read_closeout_baselines(
                workbook_bytes(paid_in_amount="NaN"), "Daily BS", "Daily HASH"
            )


    def test_default_closeout_actuals_rejects_invalid_coupon_total(self):
        from app.closeout_reconciliation import default_closeout_actuals

        with self.assertRaisesRegex(ValueError, "valid.*amount|monetary"):
            default_closeout_actuals({"cash": 1.00}, "Infinity")
