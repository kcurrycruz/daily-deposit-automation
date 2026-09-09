from __future__ import annotations

from typing import MutableMapping


UPLOAD_STAGE = "upload"
DEPOSIT_STEPS_STAGE = "deposit_steps"
DEPOSIT_PAGE_STAGE_KEY = "daily_deposit_page_stage"


def selected_deposit_stage(state: MutableMapping[str, object]) -> str:
    value = state.get(DEPOSIT_PAGE_STAGE_KEY)
    if value == DEPOSIT_STEPS_STAGE:
        return DEPOSIT_STEPS_STAGE
    return UPLOAD_STAGE


def reports_ready_for_steps(
    *,
    workbook_valid: bool,
    settlement_valid: bool,
    workbook_date,
    settlement_date,
) -> bool:
    return bool(
        workbook_valid
        and settlement_valid
        and workbook_date is not None
        and settlement_date is not None
        and workbook_date == settlement_date
    )


def advance_to_deposit_steps(
    state: MutableMapping[str, object], *, reports_ready: bool
) -> bool:
    if not reports_ready:
        return False
    state[DEPOSIT_PAGE_STAGE_KEY] = DEPOSIT_STEPS_STAGE
    return True


def enforce_ready_stage(
    state: MutableMapping[str, object], *, reports_ready: bool
) -> str:
    stage = selected_deposit_stage(state)
    if stage == DEPOSIT_STEPS_STAGE and not reports_ready:
        state[DEPOSIT_PAGE_STAGE_KEY] = UPLOAD_STAGE
        return UPLOAD_STAGE
    return stage


def reset_deposit_page(state: MutableMapping[str, object]) -> None:
    state.pop(DEPOSIT_PAGE_STAGE_KEY, None)
