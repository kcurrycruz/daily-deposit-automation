from collections import OrderedDict
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


STANDARD_METADATA = OrderedDict(
    [
        (
            "cash",
            {
                "label": "Cash",
                "memo": "Over/Short per Closeout Sheet - Cash",
                "detail_direction": None,
            },
        ),
        (
            "checks",
            {
                "label": "Checks",
                "memo": "Over/Short per Closeout Sheet - Check",
                "detail_direction": None,
            },
        ),
        (
            "donation",
            {
                "label": "Donation",
                "memo": "Over/Short per Closeout Sheet - Donation",
                "detail_direction": -1,
            },
        ),
        (
            "charge_house",
            {
                "label": "Charge (House)",
                "memo": "Over/Short per Closeout Sheet - Charge (House)",
                "detail_direction": -1,
            },
        ),
        (
            "offline_zon",
            {
                "label": "Offline Zon",
                "memo": "Over/Short per Closeout Sheet - Offline Zon",
                "detail_direction": -1,
            },
        ),
        (
            "vendor_coupons",
            {
                "label": "Vendor Coupons",
                "memo": "Over/Short per Closeout Sheet - Coupon",
                "detail_direction": -1,
                "managed_externally": True,
            },
        ),
        (
            "paid_out",
            {
                "label": "Paid Out",
                "memo": "Over/Short per Closeout Sheet - Paid Out",
                "detail_direction": -1,
            },
        ),
        (
            "paid_in",
            {
                "label": "Paid In",
                "memo": "Over/Short per Closeout Sheet - Paid In",
                "detail_direction": 1,
            },
        ),
    ]
)

_STANDARD_ADJUSTMENT_ACCOUNT = "8314000 · FE - Cash Over/Shorts"


def _money(value, label: str) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} must be a valid monetary amount") from None
    if not amount.is_finite():
        raise ValueError(f"{label} must be a valid monetary amount")
    return amount


def build_standard_reconciliation(
    baselines: dict[str, float],
    actuals: dict[str, float],
) -> list[dict]:
    """Build the approved closeout reconciliation rows in canonical order."""
    normalized_baselines = {}
    normalized_actuals = {}
    for key in STANDARD_CLOSEOUT_ORDER:
        metadata = STANDARD_METADATA[key]
        label = metadata["label"]
        if key not in baselines:
            raise ValueError(f"Closeout {label} is missing")
        if key not in actuals:
            raise ValueError(f"Closeout {label} is missing")

        normalized_baselines[key] = abs(_money(baselines[key], f"{label} baseline"))
        try:
            raw_actual = Decimal(str(actuals[key]))
        except (InvalidOperation, TypeError, ValueError):
            raw_actual = None
        if raw_actual is not None and raw_actual.is_finite() and raw_actual < 0:
            raise ValueError(f"{label} must be zero or greater")
        actual = _money(actuals[key], f"{label} actual")
        if actual < 0:
            raise ValueError(f"{label} must be zero or greater")
        normalized_actuals[key] = actual

    rows = []
    for key in STANDARD_CLOSEOUT_ORDER:
        metadata = STANDARD_METADATA[key]
        label = metadata["label"]
        memo = metadata["memo"]
        detail_direction = metadata.get("detail_direction")
        baseline = normalized_baselines[key]
        actual = normalized_actuals[key]
        difference = (actual - baseline).quantize(Decimal("0.01"))
        if detail_direction is None:
            detail_qb_effect = None
            adjustment_qb_effect = difference
        else:
            detail_qb_effect = (actual * detail_direction).quantize(Decimal("0.01"))
            adjustment_qb_effect = (
                (baseline * detail_direction) - (actual * detail_direction)
            ).quantize(Decimal("0.01"))

        rows.append(
            {
                "key": key,
                "label": label,
                "baseline": float(baseline),
                "actual": float(actual),
                "difference": float(difference),
                "detail_qb_effect": (
                    None if detail_qb_effect is None else float(detail_qb_effect)
                ),
                "adjustment_account": _STANDARD_ADJUSTMENT_ACCOUNT,
                "adjustment_memo": memo,
                "adjustment_qb_effect": float(adjustment_qb_effect),
                "managed_externally": bool(metadata.get("managed_externally")),
            }
        )
    return rows


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
                if label == "amount":
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
    actuals = {
        field: float(
            _money(baselines.get(field, 0.0), f"{field} baseline")
        )
        for field in STANDARD_CLOSEOUT_ORDER
    }
    actuals["offline_zon"] = 0.0
    actuals["vendor_coupons"] = float(counted_coupons)
    return actuals
