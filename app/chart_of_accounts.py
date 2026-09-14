from functools import lru_cache
from io import BytesIO
from pathlib import Path


DEFAULT_CHART_OF_ACCOUNTS_PATH = (
    Path(__file__).resolve().parents[1] / "assets" / "HWFC COA Mappings.xlsx"
)


def load_chart_of_accounts(workbook_source: bytes | str | Path) -> tuple[str, ...]:
    """Return the exact, nonblank values beneath the workbook's Account header."""
    import openpyxl

    source = (
        BytesIO(workbook_source)
        if isinstance(workbook_source, bytes)
        else workbook_source
    )
    workbook = openpyxl.load_workbook(source, read_only=True, data_only=True)
    try:
        for sheet in workbook.worksheets:
            account_column = None
            header_row = None
            for row_number, row in enumerate(
                sheet.iter_rows(
                    min_row=1,
                    max_row=min(sheet.max_row, 50),
                    values_only=True,
                ),
                start=1,
            ):
                for column_number, value in enumerate(row, start=1):
                    if str(value or "").strip().casefold() == "account":
                        account_column = column_number
                        header_row = row_number
                        break
                if account_column is not None:
                    break
            if account_column is None:
                continue

            accounts = []
            seen = set()
            for (value,) in sheet.iter_rows(
                min_row=header_row + 1,
                min_col=account_column,
                max_col=account_column,
                values_only=True,
            ):
                account = str(value or "").strip()
                if not account or account in seen:
                    continue
                seen.add(account)
                accounts.append(account)
            if accounts:
                return tuple(accounts)
    finally:
        workbook.close()

    raise ValueError("Chart of Accounts workbook is missing a populated Account column")


@lru_cache(maxsize=1)
def load_default_chart_of_accounts() -> tuple[str, ...]:
    return load_chart_of_accounts(DEFAULT_CHART_OF_ACCOUNTS_PATH)
