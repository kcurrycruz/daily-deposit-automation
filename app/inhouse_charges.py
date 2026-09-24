"""Domain rules for InHouse charge memos and guided-step payloads."""

from decimal import Decimal, InvalidOperation

from .closeout_reconciliation import normalize_inhouse_charges


END_OF_DAY = "End of Day"
CUSTOM = "Custom"
MEMO_TYPES = (END_OF_DAY, CUSTOM)
END_OF_DAY_PREFIX = "End of Day - "


def compose_inhouse_memo(memo_type: str, value: str) -> str:
    if memo_type not in MEMO_TYPES:
        raise ValueError("Choose End of Day or Custom for the InHouse memo")
    cleaned = str(value or "").strip()
    if not cleaned:
        label = "Initials" if memo_type == END_OF_DAY else "Custom memo"
        raise ValueError(f"{label} is required")
    return END_OF_DAY_PREFIX + cleaned.upper() if memo_type == END_OF_DAY else cleaned


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
    actual = _nonnegative_money(payload.get("actual"), "Charge (House) Actual")
    rows = normalize_inhouse_charges(payload.get("rows", []), actual)
    return {"actual": float(actual), "rows": rows}
