from decimal import Decimal, InvalidOperation


STEP_MEMBER_SHARES = "member_shares"
STEP_DONATION = "donation"
STEP_PAID_IN = "paid_in"
STEP_PAID_OUT = "paid_out"
STEP_COUPONS = "coupons"
STEP_CLOSEOUT = "closeout"

STEP_LABELS = {
    STEP_MEMBER_SHARES: "Member Share Payments",
    STEP_DONATION: "Donations",
    STEP_PAID_IN: "Paid In",
    STEP_PAID_OUT: "Paid Out",
    STEP_COUPONS: "Coupons Receivable",
    STEP_CLOSEOUT: "Closeout Sheet",
}

COMPLETION_METHODS = {"app", "quickbooks"}


def _is_nonzero(value, label: str) -> bool:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} must be a valid amount") from None
    if not amount.is_finite():
        raise ValueError(f"{label} must be a valid amount")
    return amount != 0


def required_deposit_steps(subscription_total: float, activity_source_totals: dict, coupon_bs_total: float) -> tuple[str, ...]:
    if not isinstance(activity_source_totals, dict):
        raise ValueError("Activity source totals must be an object")
    steps = []
    if _is_nonzero(subscription_total, "Subscription Revenue"):
        steps.append(STEP_MEMBER_SHARES)
    for source_key, step, label in (("donation", STEP_DONATION, "Donation"), ("paid_in", STEP_PAID_IN, "Paid In"), ("paid_out", STEP_PAID_OUT, "Paid Out")):
        if _is_nonzero(activity_source_totals.get(source_key, 0), label):
            steps.append(step)
    if _is_nonzero(coupon_bs_total, "Coupons Receivable"):
        steps.append(STEP_COUPONS)
    return (*steps, STEP_CLOSEOUT)


def normalize_step_completions(required_steps, completions):
    source = completions if isinstance(completions, dict) else {}
    return {step: source[step] for step in required_steps if source.get(step) in COMPLETION_METHODS}


def active_deposit_step(required_steps, completions):
    normalized = normalize_step_completions(required_steps, completions)
    return next((step for step in required_steps if step not in normalized), None)


def complete_deposit_step(required_steps, completions, step, method):
    if step not in required_steps:
        raise ValueError(f"Deposit step is not required: {step}")
    if method not in COMPLETION_METHODS:
        raise ValueError("Completion method must be app or quickbooks")
    normalized = normalize_step_completions(required_steps, completions)
    normalized[step] = method
    return normalized


def edit_deposit_step(required_steps, completions, step):
    if step not in required_steps:
        raise ValueError(f"Deposit step is not required: {step}")
    normalized = normalize_step_completions(required_steps, completions)
    normalized.pop(step, None)
    if step != STEP_CLOSEOUT:
        normalized.pop(STEP_CLOSEOUT, None)
    return normalized


def deposit_workflow_complete(required_steps, completions):
    normalized = normalize_step_completions(required_steps, completions)
    return all(step in normalized for step in required_steps)


def deposit_step_rows(required_steps, completions):
    normalized = normalize_step_completions(required_steps, completions)
    active = active_deposit_step(required_steps, normalized)
    rows = []
    for number, step in enumerate(required_steps, start=1):
        method = normalized.get(step)
        status = ("Completed in app" if method == "app" else "Finish in QuickBooks" if method == "quickbooks" else "Current" if step == active else "Pending")
        rows.append({"number": number, "step": step, "label": STEP_LABELS[step], "status": status, "complete": method is not None, "current": step == active})
    return rows
