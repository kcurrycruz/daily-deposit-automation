from __future__ import annotations

import html
import hashlib
import json
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class OperationsStatus:
    deposit_date: str
    files: str
    iif: str
    state: str


def deposit_run_context(daily_bytes: bytes, settlement_bytes: bytes, inputs: dict) -> str:
    """Identify the exact uploaded content and editable inputs used for a run."""
    context = {
        "daily": hashlib.sha256(daily_bytes).hexdigest(),
        "settlement": hashlib.sha256(settlement_bytes).hexdigest(),
        "inputs": inputs,
    }
    encoded = json.dumps(context, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_operations_status(
    *,
    deposit_date: date | None,
    daily_uploaded: bool,
    settlement_uploaded: bool,
    workbook_valid: bool,
    settlement_valid: bool,
    workflow_complete: bool,
    iif_generated: bool,
) -> OperationsStatus:
    uploaded_count = int(daily_uploaded) + int(settlement_uploaded)
    date_text = (
        deposit_date.strftime("%m/%d/%Y")
        if deposit_date and uploaded_count
        else "Waiting for workbook"
    )

    if uploaded_count == 0:
        files_text = "0 of 2 uploaded"
    elif uploaded_count == 1:
        needed = "Card Settlement needed" if daily_uploaded else "Daily Workbook needed"
        files_text = f"1 of 2 uploaded · {needed}"
    elif not (workbook_valid and settlement_valid):
        files_text = "2 of 2 uploaded · Needs attention"
    else:
        files_text = "2 of 2 verified"

    if (iif_generated and uploaded_count == 2 and workbook_valid
            and settlement_valid and workflow_complete):
        iif_text, state = "Ready to download", "ready"
    elif uploaded_count == 2 and not (workbook_valid and settlement_valid):
        iif_text, state = "Needs attention", "attention"
    elif uploaded_count == 2 and workflow_complete:
        iif_text, state = "Ready to prepare IIF", "ready"
    elif uploaded_count == 2 and workbook_valid and settlement_valid:
        iif_text, state = "Complete guided steps", "active"
    else:
        iif_text, state = "Not ready", "waiting"

    return OperationsStatus(date_text, files_text, iif_text, state)


def operations_status_html(status: OperationsStatus) -> str:
    escape = lambda value: html.escape(str(value), quote=True)
    items = (
        ("Deposit date", status.deposit_date),
        ("Files", status.files),
        ("IIF status", status.iif),
    )
    rendered_items = "".join(
        f'<div class="hwfc-ops-status-item"><span class="hwfc-ops-status-label">'
        f"{escape(label)}</span><span class=\"hwfc-ops-status-value\">{escape(value)}</span></div>"
        for label, value in items
    )
    return (
        f'<div class="hwfc-ops-status is-{escape(status.state)}" '
        f'aria-label="Deposit status">{rendered_items}</div>'
    )


def render_operations_status(ui, status: OperationsStatus) -> None:
    ui.markdown(operations_status_html(status), unsafe_allow_html=True)
