from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date
from typing import Iterable


@dataclass(frozen=True)
class UploadIntakeRender:
    """Native uploader values and positioned slots for parsed status details."""

    daily_workbook: object
    card_settlement: object
    progress_slot: object
    daily_details_slot: object
    settlement_details_slot: object
    readiness_slot: object


def render_upload_inputs(ui, *, uploader_key: int) -> UploadIntakeRender:
    """Render both native uploaders in one guided operations panel."""
    ui.markdown(
        '<div class="hwfc-upload-heading">'
        '<div class="hwfc-upload-title">Upload deposit reports</div>'
        '<div class="hwfc-upload-subtitle">Add both reports for today. '
        'We’ll check the dates and contents automatically.</div>'
        "</div>",
        unsafe_allow_html=True,
    )
    with ui.container(border=True):
        progress_slot = ui.empty()

        daily_copy, daily_input = ui.columns([0.46, 0.54], gap="large")
        with daily_copy:
            ui.markdown(
                '<div class="hwfc-upload-card-copy">'
                '<span class="hwfc-upload-card-number">1</span>'
                '<div><strong>Daily Workbook</strong>'
                '<span>Expected workbook contents</span>'
                '<div class="hwfc-upload-expected">'
                '<span>Sales</span><span>Coupons</span><span>Discounts</span>'
                '<span>Balance Sheet</span><span>HASH</span>'
                "</div></div></div>",
                unsafe_allow_html=True,
            )
        with daily_input:
            daily_workbook = ui.file_uploader(
                "Upload completed SubDept workbook",
                type=["xlsx", "xlsm"],
                label_visibility="collapsed",
                help=(
                    "Workbook should contain Sales, Coupons, Discounts, "
                    "BS, and HASH data."
                ),
                key=f"daily_workbook_{uploader_key}",
            )
            daily_details_slot = ui.empty()

        ui.markdown('<div class="hwfc-upload-divider"></div>', unsafe_allow_html=True)

        settlement_copy, settlement_input = ui.columns([0.46, 0.54], gap="large")
        with settlement_copy:
            ui.markdown(
                '<div class="hwfc-upload-card-copy">'
                '<span class="hwfc-upload-card-number">2</span>'
                '<div><strong>Card Settlement</strong>'
                '<span>Processed Net Amount report for the same deposit date.</span>'
                "</div></div>",
                unsafe_allow_html=True,
            )
        with settlement_input:
            card_settlement = ui.file_uploader(
                "Upload Daily Card Settlement Report",
                type=["xlsx", "xlsm"],
                label_visibility="collapsed",
                help=(
                    "Uses ONLY Processed Net Amount for VISA/MC, Discover, "
                    "AMEX, Debit Card, and EBT."
                ),
                key=f"card_settlement_{uploader_key}",
            )
            settlement_details_slot = ui.empty()

        readiness_slot = ui.empty()

    return UploadIntakeRender(
        daily_workbook=daily_workbook,
        card_settlement=card_settlement,
        progress_slot=progress_slot,
        daily_details_slot=daily_details_slot,
        settlement_details_slot=settlement_details_slot,
        readiness_slot=readiness_slot,
    )


def upload_step_rows(
    daily_workbook_ready: bool,
    settlement_ready: bool,
) -> tuple[dict, ...]:
    """Return the visible three-step upload progress state."""
    both_ready = bool(daily_workbook_ready and settlement_ready)
    return (
        {
            "number": 1,
            "label": "Daily Workbook",
            "complete": bool(daily_workbook_ready),
            "current": not daily_workbook_ready,
        },
        {
            "number": 2,
            "label": "Card Settlement",
            "complete": bool(settlement_ready),
            "current": bool(daily_workbook_ready and not settlement_ready),
        },
        {
            "number": 3,
            "label": "Ready",
            "complete": both_ready,
            "current": False,
        },
    )


def upload_readiness(
    daily_workbook_ready: bool,
    settlement_ready: bool,
) -> dict:
    """Summarize upload completion without changing validation rules."""
    count = int(bool(daily_workbook_ready)) + int(bool(settlement_ready))
    ready = count == 2
    return {
        "count": count,
        "percent": count * 50,
        "label": f"{count} of 2 reports added",
        "action": (
            "Ready for Today’s Deposit Steps"
            if ready
            else "Continue when ready"
        ),
        "ready": ready,
    }


def upload_stepper_html(rows: Iterable[dict]) -> str:
    """Render a safe, accessible three-bubble upload progress indicator."""
    items = []
    for row in rows:
        label = str(row["label"])
        if row["complete"]:
            state = "is-complete"
            state_label = "completed"
            bubble = "✓"
        elif row["current"]:
            state = "is-current"
            state_label = "current"
            bubble = str(int(row["number"]))
        else:
            state = "is-pending"
            state_label = "pending"
            bubble = str(int(row["number"]))
        safe_label = html.escape(label)
        items.append(
            f'<div class="hwfc-upload-stepper-item {state}" role="listitem">'
            '<div class="hwfc-upload-stepper-track">'
            '<span class="hwfc-upload-stepper-bubble" '
            f'aria-label="{safe_label} {state_label}">{bubble}</span>'
            "</div>"
            '<div class="hwfc-upload-stepper-label">'
            f'<span>Step {int(row["number"])}</span>'
            f"<strong>{safe_label}</strong>"
            "</div>"
            "</div>"
        )
    return (
        '<div class="hwfc-upload-stepper" role="list" '
        'aria-label="Upload deposit reports progress">'
        + "".join(items)
        + "</div>"
    )


def workbook_role_badges_html(
    role_labels: Iterable[tuple[str, str | None]],
) -> str:
    """Render detected and missing Daily Workbook roles without trusting names."""
    badges = []
    for label, sheet_name in role_labels:
        safe_label = html.escape(str(label))
        if sheet_name:
            text = f"{safe_label} · {html.escape(str(sheet_name))}"
            css_class = "hwfc-upload-role"
        else:
            text = f"{safe_label} · Not detected"
            css_class = "hwfc-upload-role is-missing"
        badges.append(f'<span class="{css_class}">{text}</span>')
    return f'<div class="hwfc-upload-role-list">{"".join(badges)}</div>'


def uploaded_file_summary_html(
    filename: str,
    detected_date: date | None,
    *,
    valid: bool,
    status_text: str,
) -> str:
    """Render an uploaded-file summary with optional detected date."""
    css_class = "hwfc-upload-file-summary is-valid" if valid else "hwfc-upload-file-summary"
    date_markup = (
        '<span class="hwfc-upload-file-date">'
        f"Report date · {detected_date.strftime('%m/%d/%Y')}"
        "</span>"
        if detected_date is not None
        else ""
    )
    return (
        f'<div class="{css_class}">'
        '<span class="hwfc-upload-file-name">'
        f"{html.escape(str(filename))}</span>"
        f"{date_markup}"
        '<span class="hwfc-upload-file-status">'
        f"{html.escape(str(status_text))}</span>"
        "</div>"
    )


def upload_readiness_html(readiness: dict) -> str:
    """Render the bounded report count, progress bar, and next-state label."""
    percent = int(readiness["percent"])
    if percent not in (0, 50, 100):
        raise ValueError("Upload readiness percent must be 0, 50, or 100")
    ready_class = " is-ready" if readiness["ready"] else ""
    return (
        f'<div class="hwfc-upload-readiness{ready_class}">'
        '<div class="hwfc-upload-readiness-progress">'
        f'<span>{html.escape(str(readiness["label"]))}</span>'
        '<div class="hwfc-upload-progress">'
        f'<div class="hwfc-upload-progress-fill" style="width:{percent}%"></div>'
        "</div>"
        "</div>"
        '<div class="hwfc-upload-ready-action">'
        f'{html.escape(str(readiness["action"]))}'
        "</div>"
        "</div>"
    )
