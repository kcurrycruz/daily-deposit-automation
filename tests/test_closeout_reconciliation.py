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
    def test_build_standard_reconciliation_returns_eight_rows_in_approved_order(self):
        from app.closeout_reconciliation import build_standard_reconciliation

        baselines = {
            "cash": 100.00,
            "checks": 50.00,
            "donation": 20.00,
            "charge_house": 10.00,
            "offline_zon": 12.00,
            "vendor_coupons": 181.50,
            "paid_out": 40.00,
            "paid_in": 30.00,
        }
        actuals = {
            "cash": 105.00,
            "checks": 45.00,
            "donation": 25.00,
            "charge_house": 8.00,
            "offline_zon": 0.00,
            "vendor_coupons": 188.25,
            "paid_out": 50.00,
            "paid_in": 35.00,
        }

        result = build_standard_reconciliation(baselines, actuals)

        self.assertEqual([row["key"] for row in result], list(STANDARD_ORDER))
        self.assertEqual(len(result), 8)
        self.assertTrue(
            all(
                set(row)
                == {
                    "key",
                    "label",
                    "baseline",
                    "actual",
                    "difference",
                    "detail_qb_effect",
                    "adjustment_account",
                    "adjustment_memo",
                    "adjustment_qb_effect",
                    "managed_externally",
                }
                for row in result
            )
        )

    def test_build_standard_reconciliation_calculates_fixture_effects_and_metadata(self):
        from app.closeout_reconciliation import build_standard_reconciliation

        baselines = {
            "cash": 100.00,
            "checks": 50.00,
            "donation": 20.00,
            "charge_house": 10.00,
            "offline_zon": 12.00,
            "vendor_coupons": 181.50,
            "paid_out": 40.00,
            "paid_in": 30.00,
        }
        actuals = {
            "cash": 105.00,
            "checks": 45.00,
            "donation": 25.00,
            "charge_house": 8.00,
            "offline_zon": 0.00,
            "vendor_coupons": 188.25,
            "paid_out": 50.00,
            "paid_in": 35.00,
        }

        rows = build_standard_reconciliation(baselines, actuals)
        by_key = {row["key"]: row for row in rows}

        self.assertEqual(by_key["cash"]["difference"], 5.00)
        self.assertIsNone(by_key["cash"]["detail_qb_effect"])
        self.assertEqual(by_key["cash"]["adjustment_qb_effect"], 5.00)
        self.assertEqual(
            by_key["checks"]["adjustment_memo"],
            "Over/Short per Closeout Sheet - Check",
        )
        self.assertEqual(by_key["donation"]["difference"], 5.00)
        self.assertEqual(by_key["donation"]["detail_qb_effect"], -25.00)
        self.assertEqual(by_key["donation"]["adjustment_qb_effect"], 5.00)
        self.assertEqual(by_key["paid_in"]["detail_qb_effect"], 35.00)
        self.assertEqual(by_key["paid_in"]["adjustment_qb_effect"], -5.00)
        self.assertTrue(by_key["vendor_coupons"]["managed_externally"])
        self.assertEqual(
            by_key["vendor_coupons"]["adjustment_memo"],
            "Over/Short per Closeout Sheet - Coupon",
        )

    def test_build_standard_reconciliation_rejects_negative_actual_for_every_category(self):
        from app.closeout_reconciliation import build_standard_reconciliation

        baselines = {key: 1.00 for key in STANDARD_ORDER}
        actuals = {key: 1.00 for key in STANDARD_ORDER}

        for key in STANDARD_ORDER:
            with self.subTest(key=key), self.assertRaisesRegex(
                ValueError, "zero or greater"
            ):
                invalid_actuals = dict(actuals)
                invalid_actuals[key] = -0.01
                build_standard_reconciliation(baselines, invalid_actuals)

    def test_build_standard_reconciliation_rejects_missing_baseline_or_actual_with_label(self):
        from app.closeout_reconciliation import build_standard_reconciliation

        baselines = {key: 1.00 for key in STANDARD_ORDER}
        actuals = {key: 1.00 for key in STANDARD_ORDER}
        labels = {
            "cash": "Cash",
            "checks": "Checks",
            "donation": "Donation",
            "charge_house": "Charge (House)",
            "offline_zon": "Offline Zon",
            "vendor_coupons": "Vendor Coupons",
            "paid_out": "Paid Out",
            "paid_in": "Paid In",
        }

        for key, label in labels.items():
            with self.subTest(mapping="baseline", key=key):
                missing_baseline = dict(baselines)
                missing_baseline.pop(key)
                with self.assertRaises(ValueError) as error:
                    build_standard_reconciliation(missing_baseline, actuals)
                self.assertIn(label, str(error.exception))
            with self.subTest(mapping="actual", key=key):
                missing_actual = dict(actuals)
                missing_actual.pop(key)
                with self.assertRaises(ValueError) as error:
                    build_standard_reconciliation(baselines, missing_actual)
                self.assertIn(label, str(error.exception))

    def test_build_standard_reconciliation_quantizes_decimal_sensitive_values(self):
        from app.closeout_reconciliation import build_standard_reconciliation

        baselines = {key: "0.00" for key in STANDARD_ORDER}
        actuals = {key: "0.00" for key in STANDARD_ORDER}
        baselines["donation"] = "10.009"
        actuals["donation"] = "10.004"

        donation = build_standard_reconciliation(baselines, actuals)[2]

        for field in (
            "baseline",
            "actual",
            "difference",
            "detail_qb_effect",
            "adjustment_qb_effect",
        ):
            self.assertIsInstance(donation[field], float)
        self.assertEqual(donation["baseline"], 10.01)
        self.assertEqual(donation["actual"], 10.00)
        self.assertEqual(donation["difference"], -0.01)
        self.assertEqual(donation["detail_qb_effect"], -10.00)
        self.assertEqual(donation["adjustment_qb_effect"], -0.01)

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
