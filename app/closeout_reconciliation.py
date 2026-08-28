from decimal import Decimal, InvalidOperation
from io import BytesIO


STANDARD_CLOSEOUT_ORDER: tuple[str, ...] = (
    "cash",
    "checks",
    "donation",
    "charge_house",
    "offline_zon",
    "vendor_coupons",
    "paid_out",
    "paid_in",
)

_BS_CODE_TO_FIELD = {
    901: "cash",
    902: "checks",
    1122: "donation",
    906: "charge_house",
    934: "offline_zon",
    1334: "offline_zon",
    908: "vendor_coupons",
    1114: "paid_out",
}


def _money(value, label: str) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} must be a valid monetary amount") from None
    if not amount.is_finite():
        raise ValueError(f"{label} must be a valid monetary amount")
    return amount


def _code(value):
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return None


def read_closeout_baselines(
    workbook_bytes: bytes,
    bs_sheet_name: str,
    hash_sheet_name: str,
) -> dict[str, float]:
    import openpyxl

    workbook = openpyxl.load_workbook(
        BytesIO(workbook_bytes),
        read_only=True,
        data_only=True,
    )
    try:
        if bs_sheet_name not in workbook.sheetnames:
            raise ValueError(f"Balance Sheet tab '{bs_sheet_name}' was not found")
        if hash_sheet_name not in workbook.sheetnames:
            raise ValueError(f"HASH tab '{hash_sheet_name}' was not found")

        baselines = {field: 0.0 for field in STANDARD_CLOSEOUT_ORDER}
        balance_sheet = workbook[bs_sheet_name]
        for row in balance_sheet.iter_rows(values_only=True):
            code = _code(row[0] if row else None)
            field = _BS_CODE_TO_FIELD.get(code)
            if field is None:
                continue
            try:
                amount = abs(_money(row[4], f"BS code {code} amount"))
            except IndexError:
                raise ValueError(
                    f"BS code {code} does not contain a valid monetary amount"
                ) from None
            baselines[field] = float(amount)

        hash_sheet = workbook[hash_sheet_name]
        amount_column = None
        for row in hash_sheet.iter_rows(
            min_row=1,
            max_row=min(hash_sheet.max_row, 20),
            values_only=True,
        ):
            for index, value in enumerate(row):
                label = str(value or "").strip().casefold()
                if "amount" in label and "total" not in label:
                    amount_column = index
                    break
            if amount_column is not None:
                break
        if amount_column is None:
            raise ValueError("HASH Amount header was not found in the first 20 rows")

        for row in hash_sheet.iter_rows(values_only=True):
            paid_in_row = False
            for value in row[:4]:
                if _code(value) == 34:
                    paid_in_row = True
                    break
            if not paid_in_row:
                continue
            try:
                amount = abs(_money(row[amount_column], "HASH code 34 amount"))
            except IndexError:
                raise ValueError(
                    "HASH code 34 does not contain a valid monetary amount"
                ) from None
            baselines["paid_in"] = float(amount)

        return baselines
    finally:
        workbook.close()


def default_closeout_actuals(
    baselines: dict[str, float],
    coupon_actual_total: float,
) -> dict[str, float]:
    counted_coupons = abs(_money(coupon_actual_total, "Vendor Coupons actual total"))
    actuals = dict(baselines)
    actuals["offline_zon"] = 0.0
    actuals["vendor_coupons"] = float(counted_coupons)
    return actuals
