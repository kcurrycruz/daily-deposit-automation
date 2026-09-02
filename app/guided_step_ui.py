import html
import json
import re

from app.ui_helpers import deposit_stepper_html


def queue_breakdown_scroll(session_state, choice_key: str, request_key: str) -> None:
    """Queue one form scroll when a handling choice enters app breakdown mode."""
    choice = str(session_state.get(choice_key) or "")
    if choice.startswith("Breakdown in app"):
        session_state[request_key] = True
    else:
        session_state.pop(request_key, None)


def queue_continue_scroll(session_state, request_key: str) -> None:
    """Queue one smooth scroll to the active step's Save & Continue action."""
    session_state[request_key] = True


def render_breakdown_scroll_target(
    ui,
    component_html,
    session_state,
    *,
    target_id: str,
    request_key: str,
) -> None:
    """Render a form anchor and consume a queued smooth-scroll request once."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", target_id):
        raise ValueError("Scroll target id must contain only letters, numbers, _ or -")
    ui.markdown(
        f'<div id="{html.escape(target_id, quote=True)}"></div>',
        unsafe_allow_html=True,
    )
    if not session_state.pop(request_key, False):
        return
    encoded_target = json.dumps(target_id)
    component_html(
        "<script>"
        f"const target = window.parent.document.getElementById({encoded_target});"
        "if (target) { window.setTimeout(() => target.scrollIntoView({"
        "behavior: 'smooth', block: 'start'"
        "}), 0); }"
        "</script>",
        height=0,
        width=0,
    )


def render_deposit_step_panels(
    ui,
    rows,
    *,
    edit_key_prefix: str,
):
    """Render one bubble stepper and reserve the form slot beneath it."""
    rows = tuple(rows)
    edited_step = None
    ui.markdown(deposit_stepper_html(rows), unsafe_allow_html=True)
    edit_columns = ui.columns(len(rows))
    for edit_column, row in zip(edit_columns, rows):
        if row["complete"] and edit_column.button(
            "↶ Edit",
            key=f"{edit_key_prefix}_{row['step']}",
            type="tertiary",
            use_container_width=True,
        ):
            edited_step = row["step"]
    active_slot = ui.empty()
    return active_slot, edited_step


def render_card_settlement_verification(
    ui,
    *,
    source_ok: bool,
    settlement_date,
    deposit_date,
) -> bool:
    """Render settlement verification near workbook validation."""
    if not source_ok:
        ui.error(
            "CARD SETTLEMENT COLUMN MISMATCH — exact headers 'Network' and "
            "'Processed Net Amount' were not found. Gross, Submitted, or other "
            "amount columns will not be substituted.",
            icon="🚫",
        )
    else:
        status = (
            f"💳 Card Settlement · {settlement_date.strftime('%m/%d/%Y')} · ✓ Verified"
            if settlement_date
            else "💳 Card Settlement · ✓ Verified"
        )
        ui.markdown(
            f'<div class="hwfc-source-strip">{html.escape(status)}</div>',
            unsafe_allow_html=True,
        )

    date_mismatch = bool(
        deposit_date and settlement_date and settlement_date != deposit_date
    )
    if date_mismatch:
        ui.warning(
            "**CARD SETTLEMENT DATE MISMATCH**\n\n"
            f"Daily workbook: **{deposit_date.strftime('%m/%d/%Y')}**  \n"
            f"Card settlement: **{settlement_date.strftime('%m/%d/%Y')}**  \n\n"
            "You can still run the deposit, but verify that you uploaded the "
            "intended settlement report.",
            icon="⚠️",
        )
    return date_mismatch


def render_prepare_iif_action(
    ui,
    *,
    visible: bool,
    download_details,
    disabled: bool,
) -> bool:
    """Render the final IIF action only after the guided workflow is complete."""
    if not visible:
        return False
    if download_details is not None:
        ui.download_button(
            "⬇ Download QuickBooks IIF",
            data=download_details["data"],
            file_name=download_details["file_name"],
            mime="text/plain",
            type="primary",
            use_container_width=True,
        )
        return False
    return ui.button(
        "🌿  Validate & Prepare IIF",
        type="primary",
        use_container_width=True,
        disabled=disabled,
    )
