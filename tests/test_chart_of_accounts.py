from io import BytesIO
import unittest

import openpyxl


class ChartOfAccountsTests(unittest.TestCase):
    def chart_api(self):
        try:
            from app.chart_of_accounts import load_chart_of_accounts
        except ImportError as exc:
            self.fail(f"Chart of Accounts feature is missing: {exc}")
        return load_chart_of_accounts

    def workbook_bytes(self, rows):
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Account Listing"
        sheet.append(["Report title", None, None, None])
        sheet.append([None, "Account", "Type", "Description"])
        for row in rows:
            sheet.append(row)
        output = BytesIO()
        workbook.save(output)
        workbook.close()
        return output.getvalue()

    def test_loader_returns_only_exact_nonblank_account_values(self):
        load_chart_of_accounts = self.chart_api()
        workbook_bytes = self.workbook_bytes([
            [None, "8504000 · Education", "Expense", "Classes"],
            [None, None, "Expense", "Blank account"],
            [None, "7210420 · Gardening/Plants", "Cost of Goods Sold", None],
        ])

        self.assertEqual(
            load_chart_of_accounts(workbook_bytes),
            (
                "8504000 · Education",
                "7210420 · Gardening/Plants",
            ),
        )

    def test_loader_rejects_a_workbook_without_an_account_column(self):
        load_chart_of_accounts = self.chart_api()
        workbook_bytes = self.workbook_bytes([])
        workbook = openpyxl.load_workbook(BytesIO(workbook_bytes))
        workbook.active["B2"] = "Name"
        output = BytesIO()
        workbook.save(output)
        workbook.close()

        with self.assertRaisesRegex(ValueError, "Account column"):
            load_chart_of_accounts(output.getvalue())


if __name__ == "__main__":
    unittest.main()
