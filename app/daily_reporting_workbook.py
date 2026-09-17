from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

from app.sms_deposit_data import SmsDepositData
from app.sms_exports import SmsExport, SmsExportBundle


_CENT = Decimal("0.01")
_REPORT_SHEET = "SubDept Sales Report"
_SOURCE_SHEETS = {
    "sales": "SubDept Single",
    "coupons": "SubDept Coupon (Local Discount)",
}
_DATED_SHEETS = {
    "discounts": "XXXXXX Discounts",
    "bs": "XXXXXX BS",
    "hash": "XXXXXX Hash",
}


def reporting_workbook_name(deposit_date: date) -> str:
    return (
        "SubDept Single Total Report "
        f"{deposit_date.month}-{deposit_date.day}-{deposit_date:%y}.xlsx"
    )


def build_reporting_workbook(
    template_path: Path,
    bundle: SmsExportBundle,
    data: SmsDepositData,
) -> bytes:
    """Build a formula-free daily reporting snapshot from validated SMS data."""
    if bundle.deposit_date != data.deposit_date:
        raise ValueError(
            f"SMS export bundle date {bundle.deposit_date:%m/%d/%Y} does not match "
            f"normalized data date {data.deposit_date:%m/%d/%Y}."
        )

    workbook = load_workbook(Path(template_path))
    for role, sheet_name in _SOURCE_SHEETS.items():
        _write_subdepartment_rows(workbook[sheet_name], bundle.reports[role])

    date_prefix = bundle.deposit_date.strftime("%m%d%y")
    for role, placeholder_name in _DATED_SHEETS.items():
        sheet = workbook[placeholder_name]
        _write_source_grid(sheet, bundle.reports[role])
        sheet.title = f"{date_prefix} {_dated_label(role)}"

    _write_report_values(workbook[_REPORT_SHEET], data)
    workbook.calculation.fullCalcOnLoad = True

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _write_subdepartment_rows(sheet, report: SmsExport) -> None:
    for row in sheet.iter_rows():
        for cell in row:
            cell.value = None

    for row_number, values in enumerate(_subdepartment_rows(report), start=1):
        for column_number, value in enumerate(values, start=1):
            cell = sheet.cell(row=row_number, column=column_number, value=value)
            if column_number == 7 and "0.00" not in cell.number_format:
                cell.number_format = "0.00"


def _subdepartment_rows(report: SmsExport) -> list[tuple[object, ...]]:
    header_index, columns = _subdepartment_columns(report)
    output_rows = []
    for row in report.rows[header_index + 1 :]:
        code = _integer(_cell(row, columns["code"]))
        if code is None:
            continue
        output_rows.append(
            (
                code,
                _cell(row, columns["description"]),
                None,
                None,
                None,
                _number(_cell(row, columns["quantity"])),
                _money_number(_cell(row, columns["amount"])),
            )
        )
    return output_rows


def _subdepartment_columns(report: SmsExport) -> tuple[int, dict[str, int]]:
    for row_index, row in enumerate(report.rows):
        names = {
            _header_name(value): column_index
            for column_index, value in enumerate(row)
            if _header_name(value)
        }
        description = names.get("subdepartment")
        amount = names.get("amount")
        quantity = names.get("qty")
        if description is None or amount is None or quantity is None:
            continue
        code = next(
            (
                names[name]
                for name in ("sdept", "code")
                if name in names
            ),
            description - 1,
        )
        if code < 0:
            break
        columns = {
            "code": code,
            "description": description,
            "quantity": quantity,
            "amount": amount,
        }
        if amount > 0:
            for detail_row in report.rows[row_index + 1 :]:
                if _integer(_cell(detail_row, code)) is None:
                    continue
                declared_amount = _money_number(_cell(detail_row, amount))
                shifted_amount = _money_number(_cell(detail_row, amount - 1))
                if declared_amount is None and shifted_amount is not None:
                    columns["amount"] -= 1
                    columns["quantity"] -= 1
                break
        return row_index, columns
    raise ValueError(f"{report.role.title()} report has no sub-department data header.")


def _write_source_grid(sheet, report: SmsExport) -> None:
    for row in sheet.iter_rows():
        for cell in row:
            cell.value = None
    for row_number, row in enumerate(report.rows, start=1):
        for column_number, value in enumerate(row, start=1):
            sheet.cell(row=row_number, column=column_number, value=value)


def _write_report_values(sheet, data: SmsDepositData) -> None:
    for row_number in range(5, 54):
        code = _integer(sheet.cell(row=row_number, column=1).value)
        sales = data.sales_by_subdept.get(code, Decimal("0.00"))
        coupons = data.coupons_by_subdept.get(code, Decimal("0.00"))
        values = (sales, coupons, Decimal("0.00"), Decimal("0.00"), sales + coupons)
        for column_number, value in enumerate(values, start=3):
            sheet.cell(row=row_number, column=column_number, value=_money_float(value))

    totals = (
        data.sales_total,
        data.coupon_total,
        Decimal("0.00"),
        Decimal("0.00"),
        data.sales_total - data.store_coupons_raw + data.coupon_total,
    )
    for column_number, value in enumerate(totals, start=3):
        sheet.cell(row=54, column=column_number, value=_money_float(value))

    summary = {
        "J1": data.store_coupons_raw,
        "J2": -data.coupon_total,
        "J3": data.sales_total,
        "M1": data.milk_bottle_export_total,
        "M2": data.store_coupons_adjusted,
    }
    for address, value in summary.items():
        sheet[address] = _money_float(value)


def _dated_label(role: str) -> str:
    return {"discounts": "Discounts", "bs": "BS", "hash": "Hash"}[role]


def _header_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold()) if value is not None else ""


def _cell(row: tuple[object, ...], index: int) -> object | None:
    return row[index] if index < len(row) else None


def _integer(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if number != number.to_integral_value():
        return None
    return int(number)


def _number(value: object) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    if number == number.to_integral_value():
        return int(number)
    return float(number)


def _money_number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).replace(",", "").replace("$", ""))
    except (InvalidOperation, ValueError):
        return None
    return _money_float(number)


def _money_float(value: Decimal) -> float:
    return float(value.quantize(_CENT, rounding=ROUND_HALF_UP))
