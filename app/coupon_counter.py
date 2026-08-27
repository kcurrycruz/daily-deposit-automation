from decimal import Decimal, InvalidOperation


COUPON_CATEGORIES = ("NCG", "MFG", "VP", "MKTG", "SITKA")
NCG_DENOMINATIONS = (0.25, 0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 3.00, 4.00, 5.00)


def _money(value, label: str) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} must be a valid dollar amount") from None
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{label} must be zero or greater")
    return amount


def summarize_coupon_stacks(stacks: list[dict]) -> dict:
    category_totals = {
        category: Decimal("0.00") for category in COUPON_CATEGORIES
    }
    summarized_stacks = []

    for stack in stacks:
        category = str(stack.get("category", "")).strip().upper()
        if category not in category_totals:
            raise ValueError(f"Unknown coupon category: {category or '(blank)'}")

        subtotal = Decimal("0.00")
        normalized_amounts = []
        for value in stack.get("amounts", []):
            amount = _money(value, f"{category} coupon amount")
            if amount <= 0:
                raise ValueError(f"{category} coupon amounts must be greater than zero")
            subtotal += amount
            normalized_amounts.append(float(amount))
        subtotal = subtotal.quantize(Decimal("0.01"))
        category_totals[category] += subtotal

        raw_expected = stack.get("expected_total")
        expected = (
            None
            if raw_expected in (None, "")
            else _money(raw_expected, f"{category} written stack total")
        )
        difference = (
            None
            if expected is None
            else (subtotal - expected).quantize(Decimal("0.01"))
        )
        summarized_stacks.append({
            "id": stack.get("id"),
            "category": category,
            "label": str(stack.get("label", "")).strip(),
            "expected_total": None if expected is None else float(expected),
            "amounts": normalized_amounts,
            "subtotal": float(subtotal),
            "difference": None if difference is None else float(difference),
            "matches_expected": None if difference is None else difference == 0,
        })

    category_totals = {
        category: total.quantize(Decimal("0.01"))
        for category, total in category_totals.items()
    }
    ncg_total = category_totals["NCG"]
    mfg_total = sum(
        (category_totals[category] for category in ("MFG", "VP", "MKTG", "SITKA")),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))
    overall_total = (ncg_total + mfg_total).quantize(Decimal("0.01"))

    return {
        "category_totals": {
            category: float(total) for category, total in category_totals.items()
        },
        "ncg_total": float(ncg_total),
        "mfg_total": float(mfg_total),
        "overall_total": float(overall_total),
        "stacks": summarized_stacks,
    }


def add_coupon_amount(stacks: list[dict], stack_id: str, amount: float) -> list[dict]:
    normalized_amount = _money(amount, "Coupon amount")
    if normalized_amount <= 0:
        raise ValueError("Coupon amount must be greater than zero")

    updated = []
    found = False
    for stack in stacks:
        copied = dict(stack)
        copied["amounts"] = list(stack.get("amounts", []))
        if stack.get("id") == stack_id:
            copied["amounts"].append(float(normalized_amount))
            found = True
        updated.append(copied)
    if not found:
        raise ValueError("Coupon stack was not found")
    return updated


def remove_coupon_amount(
    stacks: list[dict],
    stack_id: str,
    position: int,
) -> list[dict]:
    updated = []
    found = False
    for stack in stacks:
        copied = dict(stack)
        amounts = list(stack.get("amounts", []))
        if stack.get("id") == stack_id:
            if position < 0 or position >= len(amounts):
                raise IndexError("Coupon position is out of range")
            amounts.pop(position)
            found = True
        copied["amounts"] = amounts
        updated.append(copied)
    if not found:
        raise ValueError("Coupon stack was not found")
    return updated
