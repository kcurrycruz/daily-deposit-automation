"""Pure state transitions for the guided deposit UI."""

from app.deposit_workflow import (
    STEP_LABELS,
    complete_deposit_step,
    edit_deposit_step,
    normalize_step_completions,
)
from app.activity_breakdowns import normalize_activity_section
from app.closeout_reconciliation import (
    STANDARD_CLOSEOUT_ORDER,
    normalize_closeout_payload,
)
from app.membership_payments import (
    build_membership_lines,
    membership_mode_from_choice,
)


AUTOMATIC_MEMBERSHIP_CHOICE = (
    "Breakdown in app using the Ownership Payments sheet"
)
MANUAL_MEMBERSHIP_CHOICE = "Finish manually in QuickBooks"


def reopen_step_for_edit(
    session_state,
    *,
    required_steps,
    completions,
    step: str,
    workbook_key: str,
) -> dict:
    """Reopen a step without allowing its manual radio value to re-complete it."""
    normalized = normalize_step_completions(required_steps, completions)
    if normalized.get(step) == "quickbooks":
        handling_keys = {
            "member_shares": f"membership_handling_{workbook_key}",
            "donation": f"activity_handling_donation_{workbook_key}",
            "paid_in": f"activity_handling_paid_in_{workbook_key}",
            "paid_out": f"activity_handling_paid_out_{workbook_key}",
            "coupons": f"coupon_handling_{workbook_key}",
            "closeout": f"closeout_handling_{workbook_key}",
        }
        handling_key = handling_keys.get(step)
        if handling_key is not None:
            session_state.pop(handling_key, None)
    return edit_deposit_step(required_steps, normalized, step)


def hydrate_reopened_closeout_state(
    session_state,
    *,
    payload_key: str,
    preview_key: str,
    workbook_key: str,
) -> bool:
    """Seed a reopened Closeout form from its canonical payload, never its preview."""
    session_state.pop(preview_key, None)
    session_state.pop(f"closeout_approve_final_{workbook_key}", None)
    try:
        payload = normalize_closeout_payload(session_state[payload_key])
    except (KeyError, TypeError, ValueError):
        return False

    handling_key = f"closeout_handling_{workbook_key}"
    if payload["mode"] == "manual":
        session_state[handling_key] = "Finish manually in QuickBooks"
        return True

    session_state.update(
        {
            handling_key: "Breakdown in app using Closeout Sheet",
            f"closeout_reviewed_{workbook_key}": payload["reviewed"],
            f"closeout_payroll_{workbook_key}": {
                0.0: "None",
                4000.0: "Adds $4,000",
                -4000.0: "Removes $4,000",
            }[payload["payroll"]],
            f"closeout_safe_type_{workbook_key}": payload["safe"]["type"].title(),
            f"closeout_safe_amount_{workbook_key}": payload["safe"]["amount"],
            f"closeout_plants_{workbook_key}": payload["plants_purchase"],
            f"closeout_final_total_{workbook_key}": payload["final_total"],
        }
    )
    for field in STANDARD_CLOSEOUT_ORDER:
        session_state[f"closeout_actual_{field}_{workbook_key}"] = payload["actuals"][
            field
        ]

    custom_ids_key = f"closeout_custom_ids_{workbook_key}"
    custom_next_key = f"closeout_custom_next_{workbook_key}"
    session_state[custom_ids_key] = list(range(len(payload["custom_tba"])))
    session_state[custom_next_key] = len(payload["custom_tba"])
    for custom_id, custom_item in enumerate(payload["custom_tba"]):
        session_state[f"closeout_custom_memo_{workbook_key}_{custom_id}"] = custom_item[
            "memo"
        ]
        session_state[f"closeout_custom_amount_{workbook_key}_{custom_id}"] = custom_item[
            "amount"
        ]
        session_state[
            f"closeout_custom_direction_{workbook_key}_{custom_id}"
        ] = (
            "Adds to deposit"
            if custom_item["direction"] == "adds"
            else "Removes from deposit"
        )
    return True


def _saved_required_steps(value) -> tuple[str, ...] | None:
    if not isinstance(value, (list, tuple)) or not value:
        return None
    steps = tuple(value)
    try:
        valid = len(set(steps)) == len(steps) and all(
            step in STEP_LABELS for step in steps
        )
    except (TypeError, ValueError):
        return None
    if not valid:
        return None
    return steps


def resolve_activity_detection_workflow(
    *,
    detection_valid: bool,
    detected_required_steps,
    saved_required_steps,
    saved_completions,
) -> dict:
    """Keep a proven workflow on activity-detection failure, or block safely."""
    if detection_valid:
        required_steps = tuple(detected_required_steps)
        return {
            "blocked": False,
            "required_steps": required_steps,
            "completions": normalize_step_completions(
                required_steps, saved_completions
            ),
        }

    required_steps = _saved_required_steps(saved_required_steps)
    if required_steps is None:
        return {"blocked": True, "required_steps": (), "completions": {}}
    return {
        # Preserve the last known state for the next successful rerun, but do
        # not render or advance the guide while the current workbook is not
        # reliably detected.  The zero-valued fallback is untrusted.
        "blocked": True,
        "required_steps": required_steps,
        "completions": normalize_step_completions(required_steps, saved_completions),
    }


def validated_activity_save_payload(category: str, section: dict) -> dict:
    """Return the canonical activity section saved by the guided UI."""
    return normalize_activity_section(category, section)


def validated_membership_save_payload(
    payments,
    subscription_total: float,
) -> list[dict]:
    """Return a copied automatic-membership payload only after validation."""
    if not isinstance(payments, list):
        raise ValueError("Saved Member Share Payments must be a list")
    if any(not isinstance(payment, dict) for payment in payments):
        raise ValueError("Saved Member Share Payments must contain payment rows")
    copied_payments = [dict(payment) for payment in payments]
    build_membership_lines(
        copied_payments,
        expected_subscription_total=subscription_total,
        handling_mode="automatic",
    )
    return copied_payments


def _save_payload_transition(
    required_steps,
    completions,
    step: str,
    saved_key: str,
    payload,
) -> dict:
    """Build the atomic session writes for a guided Save action."""
    return {
        "saved_payload": {saved_key: payload},
        "completions": complete_deposit_step(
            required_steps, completions, step, "app"
        ),
    }


def save_member_share_transition(
    required_steps,
    completions,
    saved_key: str,
    payments,
    *,
    subscription_total: float,
) -> dict:
    """Validate Member Shares, then produce its payload/completion together."""
    payload = validated_membership_save_payload(payments, subscription_total)
    transition = _save_payload_transition(
        required_steps, completions, "member_shares", saved_key, payload
    )
    saved_choice_key = saved_key.replace(
        "membership_saved_payments_",
        "membership_saved_choice_",
        1,
    )
    transition["saved_payload"][saved_choice_key] = AUTOMATIC_MEMBERSHIP_CHOICE
    return transition


def save_manual_member_share_transition(
    required_steps,
    completions,
    saved_choice_key: str,
) -> dict:
    """Persist manual handling independently from Streamlit's radio widget."""
    return {
        "saved_payload": {saved_choice_key: MANUAL_MEMBERSHIP_CHOICE},
        "completions": complete_deposit_step(
            required_steps,
            completions,
            "member_shares",
            "quickbooks",
        ),
    }


def save_activity_transition(
    required_steps,
    completions,
    category: str,
    saved_key: str,
    section: dict,
) -> dict:
    """Normalize an activity section, then produce its payload/completion together."""
    payload = validated_activity_save_payload(category, section)
    return _save_payload_transition(
        required_steps, completions, category, saved_key, payload
    )


def recover_completed_membership_state(
    required_steps,
    completions,
    saved_choice,
    saved_payments,
    *,
    subscription_total: float,
) -> dict:
    """Validate hidden membership state and reopen its step on any bad payload."""
    try:
        membership_mode = membership_mode_from_choice(saved_choice)
        if membership_mode not in {"automatic", "manual"}:
            raise ValueError("Choose how to handle Member Share Payments")
        if not isinstance(saved_payments, list):
            raise ValueError("Saved Member Share Payments must be a list")
        if any(not isinstance(payment, dict) for payment in saved_payments):
            raise ValueError("Saved Member Share Payments must contain payment rows")
        membership_payments = [dict(payment) for payment in saved_payments]
        build_membership_lines(
            membership_payments,
            expected_subscription_total=subscription_total,
            handling_mode=membership_mode,
        )
    except Exception as exc:
        return {
            "needs_review": True,
            "membership_mode": None,
            "membership_payments": [],
            "completions": edit_deposit_step(
                required_steps, completions, "member_shares"
            ),
            "error": f"Saved Member Share Payments need review: {exc}",
        }
    return {
        "needs_review": False,
        "membership_mode": membership_mode,
        "membership_payments": membership_payments,
        "completions": normalize_step_completions(required_steps, completions),
        "error": None,
    }
