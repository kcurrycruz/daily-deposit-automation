from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

import xlrd


SMS_ROLE_ORDER = ("sales", "coupons", "discounts", "hash", "bs", "milk_bottles")


@dataclass(frozen=True)
class SmsExport:
    role: str
    filename: str
    report_date: date
    rows: tuple[tuple[object, ...], ...]


def read_sms_xls(file_bytes: bytes) -> tuple[tuple[object, ...], ...]:
    """Read the first worksheet from a legacy BIFF SMS export."""
    try:
        book = xlrd.open_workbook(file_contents=file_bytes, on_demand=True)
        sheet = book.sheet_by_index(0)
        rows = tuple(
            tuple(sheet.cell_value(row_index, column_index) for column_index in range(sheet.ncols))
            for row_index in range(sheet.nrows)
        )
    except (OSError, ValueError, xlrd.biffh.XLRDError) as error:
        raise ValueError(
            "This SMS report could not be read. Upload a legacy .xls export."
        ) from error
    finally:
        if "book" in locals():
            book.release_resources()
    return rows


def classify_sms_rows(rows: tuple[tuple[object, ...], ...]) -> str:
    """Return the sole SMS report role recognized from its contents."""
    text_rows = tuple(tuple(_detection_text(cell) for cell in row) for row in rows)
    report_text = "\n".join(" | ".join(row) for row in text_rows)
    candidates: set[str] = set()

    if "discounts by shopper level" in report_text:
        candidates.add("discounts")
    if "store balance sheet" in report_text:
        candidates.add("bs")
    if "item multi totals by sub-department" in report_text:
        candidates.add("milk_bottles")

    if "sub-department single total" in report_text:
        if _has_totalizer_values(text_rows, {"3", "4"}):
            candidates.add("sales")
        if _has_totalizer_values(text_rows, {"3542"}):
            candidates.add("coupons")
        if _has_totalizer_values(text_rows, {"6"}) or _has_hash_activity_markers(report_text):
            candidates.add("hash")

    if len(candidates) == 1:
        return candidates.pop()
    if candidates:
        raise ValueError("This SMS report has ambiguous content and cannot be identified.")
    raise ValueError("This SMS report layout is not recognized.")


def parse_sms_export(filename: str, file_bytes: bytes) -> SmsExport:
    """Read and identify one uploaded SMS export without relying on its filename."""
    rows = read_sms_xls(file_bytes)
    role = classify_sms_rows(rows)
    report_date = _parse_report_date(rows)
    return SmsExport(role=role, filename=filename, report_date=report_date, rows=rows)


def _detection_text(value: object) -> str:
    if isinstance(value, str):
        return " ".join(value.split()).casefold()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip().casefold()


def _has_totalizer_values(
    text_rows: tuple[tuple[str, ...], ...], expected_values: set[str]
) -> bool:
    for row in text_rows:
        if not row or not re.match(
            r"(?:tlz\.?|totalizer)\s*:?(?:\s|$)", row[0]
        ):
            continue
        joined_row = " ".join(row)
        values = set(re.findall(r"\b\d+\b", joined_row))
        if expected_values <= values:
            return True
    return False


def _has_hash_activity_markers(report_text: str) -> bool:
    return any(
        marker in report_text
        for marker in ("refunded discounts", "pass through donations", "paid in")
    )


def _parse_report_date(rows: tuple[tuple[object, ...], ...]) -> date:
    dates: set[date] = set()
    for row in rows:
        for index, value in enumerate(row):
            if not isinstance(value, str):
                continue
            inline_match = re.search(r"\bdate\s*:\s*(.+)", value, flags=re.IGNORECASE)
            if inline_match:
                dates.update(_parse_dates_in_value(inline_match.group(1)))
            if re.fullmatch(r"\s*date\s*:\s*", value, flags=re.IGNORECASE):
                for following_value in row[index + 1 :]:
                    dates.update(_parse_dates_in_value(following_value))

    if len(dates) == 1:
        return dates.pop()
    if len(dates) > 1:
        raise ValueError("This SMS report has ambiguous report dates.")
    raise ValueError("This SMS report does not contain a report date.")


def _parse_dates_in_value(value: object) -> tuple[date, ...]:
    if not isinstance(value, str):
        return ()
    parsed_dates = []
    for date_text in re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", value):
        for date_format in ("%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y"):
            try:
                parsed_dates.append(datetime.strptime(date_text, date_format).date())
                break
            except ValueError:
                continue
    return tuple(parsed_dates)
