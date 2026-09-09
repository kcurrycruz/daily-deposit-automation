from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UploadIntakeRender:
    """Values and date slot from the compact horizontal upload row."""

    daily_workbook: object
    card_settlement: object
    date_slot: object


def render_upload_inputs(
    ui,
    *,
    uploader_key: int,
) -> UploadIntakeRender:
    """Render the original date/workbook/settlement row with native uploaders."""
    from app.program_hub_ui import preserved_daily_upload, sync_daily_upload

    upload_change_state = getattr(ui, "session_state", None)
    date_col, workbook_col, settlement_col = ui.columns(
        [0.22, 0.39, 0.39],
        gap="medium",
    )

    with date_col:
        ui.markdown(
            '<div class="hwfc-section-label">Report date</div>',
            unsafe_allow_html=True,
        )
        date_slot = ui.empty()

    with workbook_col:
        ui.markdown(
            '<div class="hwfc-section-label">Daily workbook</div>',
            unsafe_allow_html=True,
        )
        daily_workbook_key = f"daily_workbook_{uploader_key}"
        preserved_daily_workbook = (
            preserved_daily_upload(upload_change_state, daily_workbook_key)
            if upload_change_state is not None
            else None
        )
        daily_change_kwargs = (
            {
                "on_change": sync_daily_upload,
                "args": (upload_change_state, daily_workbook_key),
            }
            if upload_change_state is not None
            else {}
        )
        selected_daily_workbook = ui.file_uploader(
            "Upload completed SubDept workbook",
            type=["xlsx", "xlsm"],
            label_visibility="collapsed",
            help=(
                "Workbook should contain Sales, Coupons, Discounts, "
                "BS, and HASH data."
            ),
            key=daily_workbook_key,
            **daily_change_kwargs,
        )
        daily_workbook = (
            selected_daily_workbook
            if selected_daily_workbook is not None
            else preserved_daily_workbook
        )

    with settlement_col:
        ui.markdown(
            '<div class="hwfc-section-label">Card settlement</div>',
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

    return UploadIntakeRender(
        daily_workbook=daily_workbook,
        card_settlement=card_settlement,
        date_slot=date_slot,
    )
