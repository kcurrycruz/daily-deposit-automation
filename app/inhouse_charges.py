"""Domain rules for InHouse charge memos and guided-step payloads."""

from decimal import Decimal, InvalidOperation

from .closeout_reconciliation import normalize_inhouse_charges


END_OF_DAY = "End of Day"
CUSTOM = "Custom"
MEMO_TYPES = (END_OF_DAY, CUSTOM)
END_OF_DAY_PREFIX = "End of Day - "


def compose_inhouse_memo(
    memo_type: str,
    value: str = "",
    initials: str = "",
) -> str:
    if memo_type not in MEMO_TYPES:
        raise ValueError("Choose End of Day or Custom for the InHouse memo")
    cleaned_value = str(value or "").strip()
    cleaned_initials = str(initials or "").strip().upper()
    if memo_type == END_OF_DAY:
        # Keep the previous two-argument call compatible with saved sessions.
        suffix = cleaned_initials or cleaned_value.upper()
        return END_OF_DAY_PREFIX + suffix if suffix else END_OF_DAY
    if not cleaned_value:
        raise ValueError("Custom memo is required")
    return (
        f"{cleaned_value} - {cleaned_initials}"
        if cleaned_initials
        else cleaned_value
    )


def split_inhouse_memo(memo: str) -> tuple[str, str]:
    cleaned = str(memo or "").strip()
    if cleaned == END_OF_DAY:
        return END_OF_DAY, ""
    if cleaned.startswith(END_OF_DAY_PREFIX):
        return END_OF_DAY, cleaned[len(END_OF_DAY_PREFIX):].strip().upper()
    return CUSTOM, cleaned


def _nonnegative_money(value, label: str) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} must be a valid amount") from None
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{label} must be a nonnegative amount")
    return amount


def normalize_inhouse_step_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("InHouse payload must be an object")
    raw_rows = payload.get("rows", [])
    if not isinstance(raw_rows, list):
        raise ValueError("InHouse charges must be a list")
    if not raw_rows:
        raise ValueError("Add at least one InHouse charge")
    actual = Decimal("0.00")
    for row in raw_rows:
        if not isinstance(row, dict):
            raise ValueError("InHouse row must be an object")
        actual += _nonnegative_money(row.get("amount"), "InHouse amount")
    actual = actual.quantize(Decimal("0.01"))
    rows = normalize_inhouse_charges(raw_rows, actual)
    return {"actual": float(actual), "rows": rows}
