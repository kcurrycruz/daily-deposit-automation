from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Mapping

from app.sms_exports import SmsExport, SmsExportBundle


_CENT = Decimal("0.01")
_ZERO = Decimal("0.00")


@dataclass(frozen=True)
class SmsDepositData:
    deposit_date: date
    sales_by_subdept: Mapping[int, Decimal]
    coupons_by_subdept: Mapping[int, Decimal]
    discounts_by_level: Mapping[int, Decimal]
    sales_total: Decimal
    coupon_total: Decimal
    discount_total: Decimal
    store_coupons_raw: Decimal
    milk_bottle_export_total: Decimal
    store_coupons_adjusted: Decimal
    bs_data: Mapping[str, Decimal]
    hash_refunded: Decimal
    hash_pass_through: Decimal
    hash_paid_in: Decimal

    @property
    def iif_milk_bottle_return(self) -> Decimal:
        return -(
            abs(self.milk_bottle_export_total)
            + abs(self.bs_data.get("milk_bottle_return", _ZERO))
        )


_BS_CODE_KEYS = {
    39: "bottle_sales",
    40: "milk_bottle_fee",
    205: "charity",
    207: "penny_round",
    208: "prepaid_increase",
    910: "milk_bottle_return",
    911: "bottle_return",
    901: "cash",
    902: "check",
    903: "debit",
    920: "ebt_cash",
    921: "ebt_food",
    928: "dufb",
    932: "amex",
    933: "discover",
    980: "prepaid_card",
    906: "charge",
    908: "vendor_coupon",
    1114: "paid_out",
    1122: "donation",
    3420: "subscription",
}
_BS_SUMMED_CODES = {930: "visa_mc", 931: "visa_mc", 1117: "prepaid_card"}
_BS_DEFAULT_KEYS = set(_BS_CODE_KEYS.values()) | set(_BS_SUMMED_CODES.values()) | {
    "sales_tax",
    "offline_credit_card",
}


def build_sms_deposit_data(bundle: SmsExportBundle) -> SmsDepositData:
    """Normalize verified SMS rows into the accounting values used by deposits."""
    sales_by_subdept, sales_total = _subdepartment_amounts(
        bundle.reports["sales"],
        control_label="sales total",
        report_label="Sales",
    )
    coupon_rows, _ = _subdepartment_amounts(
        bundle.reports["coupons"],
        control_label="coupon distribution total",
        report_label="Coupon distribution",
        control_total_extractor=lambda amounts: _sum(
            amount for code, amount in amounts.items() if code != 3542
        ),
    )
    coupons_by_subdept = {
        code: amount for code, amount in coupon_rows.items() if code != 3542
    }
    coupon_total = _sum(coupons_by_subdept.values())
    store_coupons_raw = coupon_rows.get(3542, _ZERO)
    _assert_control(
        bundle.reports["coupons"],
        "store coupons total",
        store_coupons_raw,
        "Store Coupons",
    )

    discounts_by_level, discount_total = _discounts(bundle.reports["discounts"])
    hash_refunded, hash_pass_through, hash_paid_in = _hash_amounts(
        bundle.reports["hash"]
    )
    bs_data = _balance_sheet_amounts(bundle.reports["bs"])
    milk_bottle_export_total = _milk_bottle_total(bundle.reports["milk_bottles"])

    return SmsDepositData(
        deposit_date=bundle.deposit_date,
        sales_by_subdept=sales_by_subdept,
        coupons_by_subdept=coupons_by_subdept,
        discounts_by_level=discounts_by_level,
        sales_total=sales_total,
        coupon_total=coupon_total,
        discount_total=discount_total,
        store_coupons_raw=store_coupons_raw,
        milk_bottle_export_total=milk_bottle_export_total,
        store_coupons_adjusted=_money(store_coupons_raw + milk_bottle_export_total),
        bs_data=bs_data,
        hash_refunded=hash_refunded,
        hash_pass_through=hash_pass_through,
        hash_paid_in=hash_paid_in,
    )


def _subdepartment_amounts(
    report: SmsExport,
    *,
    control_label: str,
    report_label: str,
    control_total_extractor=None,
) -> tuple[dict[int, Decimal], Decimal]:
    header_index, columns = _find_subdepartment_header(report.rows, report_label)
    amounts: dict[int, Decimal] = {}
    for row in report.rows[header_index + 1 :]:
        code = _integer(_cell(row, columns["code"]))
        amount = _maybe_money(_cell(row, columns["amount"]))
        if code is None or amount is None:
            continue
        amounts[code] = _money(amounts.get(code, _ZERO) + amount)

    total = _sum(amounts.values())
    control_total = control_total_extractor(amounts) if control_total_extractor else total
    _assert_control(report, control_label, control_total, report_label)
    return amounts, total


def _discounts(report: SmsExport) -> tuple[dict[int, Decimal], Decimal]:
    header_index, columns = _find_header(
        report.rows,
        {"level": ("shopperlevel",), "amount": ("discount",)},
        "Discounts",
    )
    amounts: dict[int, Decimal] = {}
    for row in report.rows[header_index + 1 :]:
        level = _integer(_cell(row, columns["level"]))
        amount = _maybe_money(_cell(row, columns["amount"]))
        if level is None or amount is None:
            continue
        amounts[level] = _money(amounts.get(level, _ZERO) + abs(amount))
    total = _sum(amounts.values())
    _assert_control(report, "discount total", total, "Discount", absolute=True)
    return amounts, total


def _hash_amounts(report: SmsExport) -> tuple[Decimal, Decimal, Decimal]:
    header_index, columns = _find_subdepartment_header(report.rows, "HASH")
    amounts: dict[int, Decimal] = {}
    for row in report.rows[header_index + 1 :]:
        code = _integer(_cell(row, columns["code"]))
        amount = _maybe_money(_cell(row, columns["amount"]))
        if code is None or amount is None:
            continue
        amounts[code] = _money(amounts.get(code, _ZERO) + abs(amount))
    _assert_control(
        report, "hash detail total", _sum(amounts.values()), "HASH detail", absolute=True
    )
    return (
        amounts.get(23, _ZERO),
        amounts.get(32, _ZERO),
        amounts.get(34, _ZERO),
    )


def _balance_sheet_amounts(report: SmsExport) -> dict[str, Decimal]:
    header_index, columns = _find_header(
        report.rows,
        {"code": ("code",), "amount": ("amount",)},
        "Balance Sheet",
    )
    data = {key: _ZERO for key in _BS_DEFAULT_KEYS}
    for row in report.rows[header_index + 1 :]:
        code = _integer(_cell(row, columns["code"]))
        amount = _maybe_money(_cell(row, columns["amount"]))
        if code is None or amount is None:
            continue
        if code in _BS_CODE_KEYS:
            data[_BS_CODE_KEYS[code]] = amount
        elif code in _BS_SUMMED_CODES:
            key = _BS_SUMMED_CODES[code]
            data[key] = _money(data[key] + amount)
        elif code == 934:
            data["offline_credit_card"] = -abs(amount)
        elif code == 1334:
            data["offline_credit_card"] = -abs(amount)
    return data


def _milk_bottle_total(report: SmsExport) -> Decimal:
    header_index, columns = _find_header(
        report.rows,
        {
            "description": ("itemdescription", "item"),
            "amount": ("netsales",),
        },
        "Milk Bottles",
    )
    total = _ZERO
    for row in report.rows[header_index + 1 :]:
        description = _cell(row, columns["description"])
        amount = _maybe_money(_cell(row, columns["amount"]))
        if not isinstance(description, str) or amount is None:
            continue
        normalized_description = " ".join(description.casefold().split())
        if "milk bottle" in normalized_description and "returned" in normalized_description:
            total = _money(total + amount)
    return total


def _find_header(
    rows: tuple[tuple[object, ...], ...],
    required: Mapping[str, tuple[str, ...]],
    report_label: str,
) -> tuple[int, dict[str, int]]:
    for row_index, row in enumerate(rows):
        by_name = {
            _header_name(value): column_index
            for column_index, value in enumerate(row)
            if _header_name(value)
        }
        columns = {
            field: next(
                (by_name[alias] for alias in aliases if alias in by_name), None
            )
            for field, aliases in required.items()
        }
        if all(column is not None for column in columns.values()):
            return row_index, columns
    required_names = ", ".join(required)
    raise ValueError(f"{report_label} report is missing required {required_names} columns.")


def _find_subdepartment_header(
    rows: tuple[tuple[object, ...], ...], report_label: str
) -> tuple[int, dict[str, int]]:
    """Find SMS's unlabeled leading department-code column and Amount column."""
    header_index, columns = _find_header(
        rows,
        {"description": ("subdepartment",), "amount": ("amount",)},
        report_label,
    )
    header = rows[header_index]
    named_code_column = next(
        (
            column_index
            for column_index, value in enumerate(header)
            if _header_name(value) in {"sdept", "code"}
        ),
        None,
    )
    columns["code"] = (
        named_code_column
        if named_code_column is not None
        else columns["description"] - 1
    )
    if columns["code"] < 0:
        raise ValueError(f"{report_label} report is missing its sub-department code column.")
    return header_index, columns


def _assert_control(
    report: SmsExport,
    control_label: str,
    actual: Decimal,
    report_label: str,
    *,
    absolute: bool = False,
) -> None:
    expected = _control_total(report.rows, control_label)
    if expected is None:
        raise ValueError(f"{report_label} report is missing its {control_label} control row.")
    if absolute:
        actual = abs(actual)
        expected = abs(expected)
    if abs(actual - expected) > _CENT:
        raise ValueError(
            f"{report_label} detail total {_format_money(actual)} does not match "
            f"its control total {_format_money(expected)}."
        )


def _control_total(
    rows: tuple[tuple[object, ...], ...], control_label: str
) -> Decimal | None:
    label = " ".join(control_label.casefold().split())
    for row in rows:
        text = " ".join(
            " ".join(value.casefold().split()) for value in row if isinstance(value, str)
        )
        if label not in text:
            continue
        for value in reversed(row):
            amount = _maybe_money(value)
            if amount is not None:
                return amount
    return None


def _header_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold()) if value is not None else ""


def _cell(row: tuple[object, ...], index: int) -> object | None:
    return row[index] if index < len(row) else None


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if decimal != decimal.to_integral_value():
        return None
    return int(decimal)


def _maybe_money(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return _money(Decimal(str(value).replace(",", "").replace("$", "")))
    except (InvalidOperation, ValueError):
        return None


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _sum(values) -> Decimal:
    return _money(sum(values, _ZERO))


def _format_money(value: Decimal) -> str:
    return f"${value:,.2f}"
