"""Synthetic accounting regressions: signs, authoritative zeroes, and corrupt inputs."""

from datetime import date
from decimal import Decimal
import gc
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import openpyxl

from app import pos_to_quickbooks_v2 as engine
from app.sms_deposit_data import build_sms_deposit_data
from app.sms_exports import SmsExport, build_sms_export_bundle


DAY = date(2026, 10, 10)


def synthetic_bundle(role=None, rows=None):
    source_rows = {
        "sales": (("Code", "Sub-Department", "Qty", "Amount"),
                  (110, "Grocery", 1, 300), (27, "Store Coupons", 1, -100),
                  ("Sales Total", "", "", 200)),
        "coupons": (("Code", "Sub-Department", "Qty", "Amount"),
                    (3542, "Store Coupons", 1, -100),
                    ("Coupon Distribution Total", "", "", 0),
                    ("Store Coupons Total", "", "", -100)),
        "discounts": (("Shopper Level", "Discount"), (2, 0), ("Discount Total", 0)),
        "hash": (("Code", "Sub-Department", "Qty", "Amount"),
                 (23, "Refunded Discounts", 0, 0), ("HASH Detail Total", "", "", 0)),
        "bs": (("Code", "Description", "Amount"), (901, "Cash", 200)),
        "milk_bottles": (("Item", "Net Sales"), ("Milk Bottle Returned", 0)),
    }
    if role is not None:
        source_rows[role] = rows
    return build_sms_export_bundle(
        SmsExport(key, f"synthetic-{key}.xls", DAY, value)
        for key, value in source_rows.items()
    )


class AccountingAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="accounting-audit-")
        self.folder = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        # Older read-only parsers can leave ZipFile cycles until collection.
        self.addCleanup(gc.collect)
        self.patches = [patch.object(engine, "output_dir", self.folder),
                        patch.object(engine, "LOG_DIR", self.folder),
                        patch.object(engine, "SUMMARY_DIR", self.folder),
                        patch.dict(engine.CONFIG, pos_export_folder=str(self.folder)),
                        patch.object(engine.log, "disabled", True)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def generate(self, sales=None, **kwargs):
        path = engine.generate_iif(
            sales or {}, {}, {}, DAY, hash_sales_total=0, **kwargs
        )
        rows = [line.split("\t") for line in path.read_text(encoding="utf-8").splitlines()
                if line.startswith(("SPL\t", "TRNS\t"))]
        return rows, (self.folder / "last_run_status.txt").read_text(encoding="utf-8")

    def workbook(self, title, rows, name="synthetic.xlsx"):
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = title
        for row in rows:
            sheet.append(row)
        path = self.folder / name
        workbook.save(path)
        workbook.close()
        return path

    def test_net_refunds_reduce_revenue_and_pass_signed_sales_control(self):
        sales = {engine.SUBDEPT_TO_QB[110]: 100,
                 engine.SUBDEPT_TO_QB[120]: -25,
                 engine.SUBDEPT_TO_QB[230]: -5,
                 engine.SUBDEPT_TO_QB[38]: -2}
        rows, status = self.generate(sales, excel_sales_total=68)
        self.assertEqual(Decimal(rows[0][5]), Decimal("68.00"))
        expected = {engine.SUBDEPT_TO_QB[120]: Decimal("25.00"),
                    engine.SUBDEPT_TO_QB[38]: Decimal("2.00")}
        for account, amount in expected.items():
            self.assertEqual(next(Decimal(row[5]) for row in rows[1:] if row[3] == account), amount)
        catering = next(row for row in rows[1:] if row[6] == "Catering")
        self.assertEqual(Decimal(catering[5]), Decimal("5.00"))
        self.assertIn("ALL CHECKS PASSED", status)

    def test_milk_return_reclassification_conserves_signed_coupon_total(self):
        sales = {engine.SUBDEPT_TO_QB[110]: 300, engine.SUBDEPT_TO_QB[27]: -100}
        for adjusted, returned, expected_coupon in ((0, -100, None), (100, -200, "-100.00"),
                                                     (-60, -40, "60.00")):
            with self.subTest(adjusted=adjusted):
                rows, status = self.generate(sales, store_coupons_xl=adjusted,
                                             milk_bottle_return=returned, excel_sales_total=200)
                self.assertEqual(Decimal(rows[0][5]), Decimal("200.00"))
                coupons = [row for row in rows[1:] if row[6] == "Store Coupons"]
                if expected_coupon is None:
                    self.assertEqual(coupons, [])
                else:
                    self.assertEqual(Decimal(coupons[0][5]), Decimal(expected_coupon))
                self.assertIn("ALL CHECKS PASSED", status)

    def test_missing_adjusted_coupon_cell_uses_raw_coupon_amount(self):
        rows, _ = self.generate({engine.SUBDEPT_TO_QB[110]: 300,
                                 engine.SUBDEPT_TO_QB[27]: -100})
        self.assertEqual(Decimal(rows[0][5]), Decimal("200.00"))

    def test_sales_control_excludes_inhouse_expense_using_same_sales_account(self):
        rows, status = self.generate(
            {engine.SUBDEPT_TO_QB[110]: 100, engine.SUBDEPT_TO_QB[28]: 10},
            excel_sales_total=110,
            bs_data={"charge": 7},
            closeout_payload={"mode": "manual", "charge_house_actual": 7,
                              "inhouse_charges": [{"account": engine.SUBDEPT_TO_QB[28],
                                                   "memo": "End of Day", "amount": 7}]},
        )
        self.assertEqual(Decimal(rows[0][5]), Decimal("103.00"))
        self.assertIn("ALL CHECKS PASSED", status)

    def test_excel_parser_distinguishes_present_zero_from_missing_coupon_cell(self):
        for value in (None, 0):
            with self.subTest(value=value):
                path = self.workbook("SubDept Sales Report", [[], [None] * 12 + [value], []])
                self.assertEqual(engine.parse_excel_report(path, DAY)[3], value)

    def test_sms_rejects_corrupt_recognized_balance_sheet_amounts(self):
        for amount in ("not money", "NaN", "Infinity", None):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                build_sms_deposit_data(synthetic_bundle("bs", (
                    ("Code", "Description", "Amount"), (930, "Visa", amount))))

    def test_sms_rejects_corrupt_returned_milk_bottle_amounts(self):
        for amount in ("not money", "NaN", "Infinity", None):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                build_sms_deposit_data(synthetic_bundle("milk_bottles", (
                    ("Item", "Net Sales"), ("Milk Bottle Returned", amount))))

    def test_sms_rejects_returned_item_without_valid_hierarchical_net_sales(self):
        for detail in (("", "Net Sales", "not money"), ("", "Net Sales", "NaN"),
                       ("Grand Total", 0)):
            with self.subTest(detail=detail), self.assertRaises(ValueError):
                build_sms_deposit_data(synthetic_bundle("milk_bottles", (
                    ("Item Multi Totals by Sub-department",),
                    (111251, "Milk Bottle Returned"), detail)))

    def test_sms_rejects_occupied_corrupt_milk_amount_before_later_numeric_cell(self):
        for amount in ("bad amount", "NaN", "Infinity"):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                build_sms_deposit_data(synthetic_bundle("milk_bottles", (
                    ("Item Multi Totals by Sub-department",),
                    (111251, "Milk Bottle Returned"), ("", "Net Sales", amount, 0))))

    def test_named_code_header_never_uses_quantity_for_missing_sales_amount(self):
        with self.assertRaises(ValueError):
            build_sms_deposit_data(synthetic_bundle("sales", (
                ("Code", "Sub-Department", "Qty", "Amount"),
                (110, "Grocery", 200, None), ("Sales Total", "", 200, None))))

    def test_named_code_header_requires_its_declared_control_amount(self):
        with self.assertRaises(ValueError):
            build_sms_deposit_data(synthetic_bundle("sales", (
                ("Code", "Sub-Department", "Qty", "Amount"),
                (110, "Grocery", 1, 200), ("Sales Total", "", 200, None))))

    def test_named_coupon_header_requires_declared_store_coupon_control_amount(self):
        with self.assertRaises(ValueError):
            build_sms_deposit_data(synthetic_bundle("coupons", (
                ("Code", "Sub-Department", "Qty", "Amount"),
                (3542, "Store Coupons", 1, -100),
                ("Coupon Distribution Total", "", "", 0),
                ("Store Coupons Total", "", -100, None))))

    def test_sms_rejects_invalid_sales_detail_even_when_zero_control_matches(self):
        with self.assertRaises(ValueError):
            build_sms_deposit_data(synthetic_bundle("sales", (
                ("Code", "Sub-Department", "Qty", "Amount"),
                (110, "Grocery", 0, "not money"), ("Sales Total", "", "", 0))))

    def test_sms_rejects_corrupt_declared_control_instead_of_using_other_numeric_cell(self):
        for amount in ("not money", "NaN", "Infinity"):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                build_sms_deposit_data(synthetic_bundle("sales", (
                    ("Code", "Sub-Department", "Qty", "Amount"),
                    (110, "Grocery", 0, 0), ("Sales Total", "", 0, amount, 0))))

    def test_engine_rejects_corrupt_recognized_balance_sheet_amounts(self):
        for amount in ("not money", "NaN", "Infinity", None):
            with self.subTest(amount=amount):
                path = self.workbook("101026 BS", [[930, "Visa", None, None, amount]])
                with self.assertRaises(ValueError):
                    engine.parse_bs_sheet(path, DAY)

    def test_engine_rejects_corrupt_sales_detail_amounts(self):
        for amount in ("not money", "NaN", "Infinity", None):
            with self.subTest(amount=amount):
                path = self.workbook("SubDept Sales Report", [[], [], [],
                    [110, "Grocery", None, None, None, None, amount]])
                with self.assertRaises(ValueError):
                    engine.parse_excel_report(path, DAY)

    def test_sales_parser_ignores_unrelated_supplementary_notes(self):
        for row_number in range(3):
            with self.subTest(row_number=row_number):
                rows = [[None] * 16 for _ in range(3)]
                rows[row_number][14:16] = ["Notes", "Unrelated text"]
                path = self.workbook("SubDept Sales Report", rows)
                try:
                    parsed = engine.parse_excel_report(path, DAY)
                except ValueError as error:
                    self.fail(f"Unrelated supplementary notes must be ignored: {error}")
                self.assertEqual(parsed[0], {})

    def test_engine_rejects_corrupt_hash_amount_instead_of_using_quantity(self):
        for amount in ("not money", "NaN", "Infinity", None):
            with self.subTest(amount=amount):
                path = self.workbook("101026 Hash", [["Code", "Description", "Qty", "Amount"],
                                                     [34, "Paid In", 50, amount]])
                with self.assertRaises(ValueError):
                    engine.parse_hash_sheet_details(path, DAY)

    def test_engine_rejects_corrupt_hash_control_instead_of_using_quantity(self):
        for amount in ("not money", "NaN", "Infinity"):
            with self.subTest(amount=amount):
                path = self.workbook("101026 Hash", [["Code", "Description", "Qty", "Amount"],
                                                     ["", "Total", 0, amount, 0]])
                workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
                try:
                    with self.assertRaises(ValueError):
                        engine._hash_control_total(workbook, DAY)
                finally:
                    workbook.close()

    def test_engine_rejects_corrupt_discount_detail_amounts(self):
        for amount in ("not money", "NaN", "Infinity"):
            with self.subTest(amount=amount):
                path = self.workbook("101026 Discounts", [
                    ["Discounts by Shopper Level", None, None, None, None, None, None, None, None],
                    [None, None, "Shopper", 2, None, None, None, 1, amount]])
                with self.assertRaises(ValueError):
                    engine.parse_excel_discounts(path, DAY)

    def test_engine_rejects_corrupt_known_settlement_network_amounts(self):
        for amount in ("not money", "NaN", "Infinity", None):
            with self.subTest(amount=amount):
                path = self.workbook("Settlement", [["Date", DAY],
                    ["Network", "Processed Net Amount"], ["VISA", amount]])
                with self.assertRaises(ValueError):
                    engine.parse_card_settlement_report(path)

    def test_iif_rejects_delimiters_in_source_memos_before_writing_artifact(self):
        for delimiter in ("\t", "\r", "\n"):
            with self.subTest(delimiter=delimiter), self.assertRaises(ValueError):
                self.generate({engine.SUBDEPT_TO_QB[110]: 100},
                              hash_misc_lines=[(f"HASH 777 Source{delimiter}Injected", 5)])
        self.assertFalse((self.folder / "deposit_20261010.iif").exists())

    def test_iif_rejects_delimiters_in_transaction_account(self):
        with patch.dict(engine.CONFIG, deposit_account="Operating\nENDTRNS"):
            with self.assertRaises(ValueError):
                self.generate({engine.SUBDEPT_TO_QB[110]: 100})
        self.assertFalse((self.folder / "deposit_20261010.iif").exists())

    def test_iif_rejects_nonfinite_money_instead_of_emitting_nan(self):
        with self.assertRaises(ValueError):
            self.generate({engine.SUBDEPT_TO_QB[110]: 100}, bs_data={"visa_mc": float("nan")})
        self.assertFalse((self.folder / "deposit_20261010.iif").exists())

    def test_csv_only_main_retains_sales_in_generated_deposit(self):
        csv_path = self.folder / "SMS_101026.csv"
        csv_path.write_text(
            "Sub-department Single Total\n,Sub-Department\n"
            "110,Grocery,,,,,,100\nDiscounts by Shopper Level\nDescription\n"
            "2,Owner,,,,,,,5\n", encoding="utf-8"
        )
        with patch("sys.argv", ["engine", "--date", "10/10/26"]):
            engine.main()
        rows = [line.split("\t") for line in (self.folder / "deposit_20261010.iif")
                .read_text(encoding="utf-8").splitlines() if line.startswith("TRNS\t")]
        self.assertEqual(Decimal(rows[0][5]), Decimal("95.00"))

    def test_finder_does_not_select_other_day_when_requested_date_is_absent(self):
        for filename in ("Report 10-09-26.xlsx", "Report 100926.xlsx", "Report 2026-10-09.xlsx"):
            with self.subTest(filename=filename):
                path = self.workbook("SubDept Sales Report", [[]], filename)
                try:
                    with self.assertRaises(FileNotFoundError):
                        engine.find_todays_files(DAY)
                finally:
                    gc.collect()
                    path.unlink()

    def test_finder_rejects_multiple_matching_accounting_workbooks(self):
        self.workbook("SubDept Sales Report", [[]], "Report 101026.xlsx")
        self.workbook("SubDept Sales Report", [[]], "Report 101026.xlsm")
        with self.assertRaises(ValueError):
            engine.find_todays_files(DAY)

    def test_finder_rejects_multiple_settlements_with_matching_content_date(self):
        rows = [["Date", DAY], ["Network", "Processed Net Amount"], ["VISA", 100]]
        self.workbook("Settlement", rows, "Daily Card Settlement A.xlsx")
        self.workbook("Settlement", rows, "Daily Card Settlement B.xlsx")
        with self.assertRaises(ValueError):
            engine.find_todays_files(DAY)

    def test_finder_preserves_undated_supported_workbook_filename(self):
        path = self.workbook("SubDept Sales Report", [[]], "daily.xlsx")
        self.assertEqual(engine.find_todays_files(DAY)[3], [path])

    def test_balance_sheet_rejects_dated_sheet_for_other_deposit_day(self):
        for sheet_name in ("100926 BS", "90926 BS"):
            with self.subTest(sheet_name=sheet_name):
                path = self.workbook(sheet_name, [[930, "Visa", None, None, 123]])
                with self.assertRaises(ValueError):
                    engine.parse_bs_sheet(path, DAY)

    def test_balance_sheet_accepts_supported_undated_sheet(self):
        path = self.workbook("Daily BS", [[930, "Visa", None, None, 123]])
        self.assertEqual(engine.parse_bs_sheet(path, DAY)["visa_mc"], 123)

    def test_main_rejects_mismatched_settlement_date_before_iif_generation(self):
        self.workbook("SubDept Sales Report", [[], [], [],
            [110, "Grocery", None, None, None, None, 100]], "Report 101026.xlsx")
        self.workbook("Settlement", [["Date", date(2026, 10, 9)],
            ["Network", "Processed Net Amount"], ["VISA", 10]], "Daily Card Settlement.xlsx")
        with patch("sys.argv", ["engine", "--date", "10/10/26"]), \
                patch.object(engine.log, "disabled", False), \
                self.assertLogs(engine.log, level="ERROR") as recorded:
            with self.assertRaises(SystemExit) as exited:
                engine.main()
        self.assertEqual(exited.exception.code, 1)
        self.assertRegex("\n".join(recorded.output),
                         r"Card settlement date 10/09/2026.*deposit date 10/10/2026")
        self.assertFalse((self.folder / "deposit_20261010.iif").exists())


if __name__ == "__main__":
    unittest.main()
