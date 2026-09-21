from __future__ import annotations

import html
from dataclasses import dataclass

from app.sms_exports import SMS_ROLE_ORDER

SMS_ROLE_LABELS = {
    "sales": "Sales",
    "coupons": "Coupon",
    "discounts": "Discounts",
    "hash": "HASH",
    "bs": "Balance Sheet",
    "milk_bottles": "Milk Bottles",
}

# Kept temporarily for the existing app entry point while Task 5 replaces its
# workbook ingestion with the normalized SMS export workflow.
WORKBOOK_ROLE_LABELS = (
    ("sales", "Sales"),
    ("coupons", "Coupons"),
    ("discounts", "Discounts"),
    ("bs", "Balance Sheet"),
    ("hash", "HASH"),
)


def render_sms_validation(ui, reports: dict, error: Exception | None) -> None:
    """Render compact, safe progress for the six required SMS exports."""
    role_count = len(SMS_ROLE_ORDER)
    verified_count = sum(role in reports for role in SMS_ROLE_ORDER)
    checks = "".join(
        '<div class="hwfc-workbook-check">'
        f'<div class="hwfc-workbook-check-label">'
        f'{"✓" if role in reports else "•"} {html.escape(label)}</div>'
        f'<div class="hwfc-workbook-check-sheet">'
        f'{html.escape(str(getattr(reports.get(role), "filename", "Waiting for report")))}</div>'
        "</div>"
        for role in SMS_ROLE_ORDER
        for label in (SMS_ROLE_LABELS[role],)
    )
    validation_message = (
        '<div class="hwfc-sms-validation-message">'
        f'{html.escape(str(error))}</div>'
        if error is not None
        else ""
    )
    ui.markdown(
        '<div class="hwfc-workbook-validation-card">'
        '<div class="hwfc-workbook-validation-title">'
        f'SMS Reports · {verified_count} of {role_count} verified'
        "</div>"
        f'<div class="hwfc-workbook-checks">{checks}</div>'
        f"{validation_message}"
        "</div>",
        unsafe_allow_html=True,
    )


def render_workbook_validation(ui, *, roles: dict, report_date) -> bool:
    """Render one compact workbook box after checking every required role."""
    missing_labels = [
        label for role, label in WORKBOOK_ROLE_LABELS if not roles.get(role)
    ]
    if missing_labels:
        ui.warning(
            "Workbook validation needs attention. Missing required worksheet "
            f"categories: **{', '.join(missing_labels)}**.",
            icon="⚠️",
        )
        return False

    date_label = (
        report_date.strftime("%m/%d/%Y")
        if report_date is not None
        else "Date not detected"
    )
    checks = "".join(
        '<div class="hwfc-workbook-check">'
        f'<div class="hwfc-workbook-check-label">✓ {html.escape(label)}</div>'
        f'<div class="hwfc-workbook-check-sheet">{html.escape(str(roles[role]))}</div>'
        "</div>"
        for role, label in WORKBOOK_ROLE_LABELS
    )
    ui.markdown(
        '<div class="hwfc-workbook-validation-card">'
        '<div class="hwfc-workbook-validation-title">'
        f'📗 Daily Workbook · {html.escape(date_label)} · ✓ Verified'
        "</div>"
        f'<div class="hwfc-workbook-checks">{checks}</div>'
        "</div>",
        unsafe_allow_html=True,
    )
    return True


def missing_settlement_date_warning(
    *,
    settlement_file: object | None,
    settlement_source_ok: bool,
    settlement_date: object | None,
    settlement_date_error: Exception | None,
) -> str | None:
    """Return the upload warning for an otherwise valid report with no date."""
    if (
        settlement_file is not None
        and settlement_source_ok
        and settlement_date is None
        and settlement_date_error is None
    ):
        return "Card Settlement report date not detected—upload a report with its date."
    return None


def retained_upload_pair(
    state, *, uploader_key: int
) -> tuple[list[object] | None, object | None]:
    """Return the upload pair while its widgets are hidden on Deposit Steps."""
    from app.program_hub_ui import preserved_daily_upload

    return (
        preserved_daily_upload(state, f"sms_reports_{uploader_key}"),
        preserved_daily_upload(state, f"card_settlement_{uploader_key}"),
    )


@dataclass(frozen=True)
class UploadIntakeRender:
    """Values and date slot from the compact horizontal upload row."""

    sms_exports: list[object] | None
    card_settlement: object
    date_slot: object

    @property
    def daily_workbook(self) -> None:
        """Keep the pre-SMS app entry point inert until its Task 5 migration."""
        return None


def render_upload_inputs(
    ui,
    *,
    uploader_key: int,
) -> UploadIntakeRender:
    """Render the date, multi-SMS-report, and settlement upload row."""
    from app.program_hub_ui import (
        finish_daily_upload_callback_batch,
        preserved_daily_upload,
        reconcile_daily_upload_selection,
        sync_daily_upload,
    )

    upload_change_state = getattr(ui, "session_state", None)
    date_col, sms_col, settlement_col = ui.columns(
        [0.22, 0.39, 0.39],
        gap="medium",
    )

    with date_col:
        ui.markdown(
            '<div class="hwfc-section-label">Report Date</div>',
            unsafe_allow_html=True,
        )
        date_slot = ui.empty()

    with sms_col:
        ui.markdown(
            '<div class="hwfc-section-label">SMS Reports</div>',
            unsafe_allow_html=True,
        )
        sms_reports_key = f"sms_reports_{uploader_key}"
        preserved_sms_reports = (
            preserved_daily_upload(upload_change_state, sms_reports_key)
            if upload_change_state is not None
            else None
        )
        sms_change_kwargs = (
            {
                "on_change": sync_daily_upload,
                "args": (upload_change_state, sms_reports_key),
            }
            if upload_change_state is not None
            else {}
        )
        selected_sms_reports = ui.file_uploader(
            "Upload SMS reports",
            type=["xls"],
            accept_multiple_files=True,
            label_visibility="collapsed",
            help="Upload the six legacy .xls SMS exports for the deposit date.",
            key=sms_reports_key,
            **sms_change_kwargs,
        )
        sms_exports = (
            reconcile_daily_upload_selection(
                upload_change_state,
                sms_reports_key,
                selected_sms_reports,
                explicit=False,
            )
            if upload_change_state is not None
            else (
                selected_sms_reports
                if selected_sms_reports or not preserved_sms_reports
                else preserved_sms_reports
            )
        )

    with settlement_col:
        ui.markdown(
            '<div class="hwfc-section-label">Card Settlement</div>',
            unsafe_allow_html=True,
        )
        card_settlement_key = f"card_settlement_{uploader_key}"
        preserved_card_settlement = (
            preserved_daily_upload(upload_change_state, card_settlement_key)
            if upload_change_state is not None
            else None
        )
        settlement_change_kwargs = (
            {
                "on_change": sync_daily_upload,
                "args": (upload_change_state, card_settlement_key),
            }
            if upload_change_state is not None
            else {}
        )
        selected_card_settlement = ui.file_uploader(
            "Upload Daily Card Settlement Report",
            type=["xlsx", "xlsm"],
            label_visibility="collapsed",
            help=(
                "Uses ONLY Processed Net Amount for VISA/MC, Discover, "
                "AMEX, Debit Card, and EBT."
            ),
            key=card_settlement_key,
            **settlement_change_kwargs,
        )
        card_settlement = (
            selected_card_settlement
            if selected_card_settlement is not None
            else preserved_card_settlement
        )

    if upload_change_state is not None:
        finish_daily_upload_callback_batch(upload_change_state)

    return UploadIntakeRender(
        sms_exports=sms_exports,
        card_settlement=card_settlement,
        date_slot=date_slot,
    )
