"""Portable, validated checkpoints for an unfinished daily deposit."""

from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import MutableMapping
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

import openpyxl

from app.deposit_page_flow import DEPOSIT_PAGE_STAGE_KEY, DEPOSIT_STEPS_STAGE
from app.deposit_workflow import STEP_CLOSEOUT, STEP_LABELS, COMPLETION_METHODS
from app.program_hub_ui import (
    DAILY_PROGRAM_RECREATED_UPLOADS_KEY,
    DAILY_PROGRAM_UPLOAD_SELECTIONS_KEY,
    DAILY_PROGRAM_UPLOADS_KEY,
)

_MAX_ARCHIVE = 100 * 1024 * 1024
_MAX_ENTRY = 50 * 1024 * 1024
_MAX_TOTAL = 150 * 1024 * 1024
_WORKBOOK_KEY = re.compile(r"^membership_payments_\d+_[0-9a-f]{16}$")
_SCOPED_PREFIXES = (
    "membership_", "activity_", "coupon_", "inhouse_", "closeout_",
    "deposit_step_completions_", "deposit_required_steps_",
)
_ACTIVITY_CATEGORIES = ("donation", "paid_out", "paid_in")


@dataclass(frozen=True)
class RestoredUpload:
    name: str
    data: bytes

    def getvalue(self) -> bytes:
        return self.data


@dataclass(frozen=True)
class DepositDraft:
    deposit_date: date
    old_workbook_key: str
    sms_uploads: tuple[RestoredUpload, ...]
    settlement_upload: RestoredUpload
    state: dict[str, object]


def _allowed_field(key: str, workbook_key: str, row_ids: dict[str, set[str]]) -> bool:
    if workbook_key in key and key.startswith(_SCOPED_PREFIXES):
        return True
    return any(
        key.startswith(f"activity_{category}_{row_id}_")
        for category, ids in row_ids.items()
        for row_id in ids
    )


def _activity_ids(state: dict[str, object], workbook_key: str) -> dict[str, set[str]]:
    result = {}
    for category in _ACTIVITY_CATEGORIES:
        ids = state.get(f"activity_row_ids_{category}_{workbook_key}", [])
        if not isinstance(ids, (list, tuple)) or not all(
            isinstance(i, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", i)
            for i in ids
        ):
            raise ValueError("Draft has invalid activity rows")
        result[category] = set(ids)
    return result


def _validate_saved_state(state: dict[str, object], workbook_key: str) -> None:
    required = state.get(f"deposit_required_steps_{workbook_key}")
    completions = state.get(f"deposit_step_completions_{workbook_key}")
    if (
        not isinstance(required, (tuple, list))
        or not required
        or not all(isinstance(step, str) and step in STEP_LABELS for step in required)
        or required[-1] != STEP_CLOSEOUT
        or len(required) != len(set(required))
        or not isinstance(completions, dict)
        or any(step not in required or method not in COMPLETION_METHODS
               for step, method in completions.items())
    ):
        raise ValueError("Draft guided-step progress is invalid")
    _activity_ids(state, workbook_key)
    for category in _ACTIVITY_CATEGORIES:
        saved_rows = state.get(f"activity_saved_rows_{category}_{workbook_key}", [])
        if not isinstance(saved_rows, list) or not all(isinstance(row, dict) for row in saved_rows):
            raise ValueError("Draft activity rows are invalid")
    inhouse_ids = state.get(f"inhouse_ids_{workbook_key}", [])
    if not isinstance(inhouse_ids, list) or not all(
        isinstance(row_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", row_id)
        for row_id in inhouse_ids
    ):
        raise ValueError("Draft InHouse rows are invalid")
    custom_ids = state.get(f"closeout_custom_ids_{workbook_key}", [])
    if not isinstance(custom_ids, list) or not all(
        isinstance(row_id, int) and not isinstance(row_id, bool) and row_id >= 0
        for row_id in custom_ids
    ):
        raise ValueError("Draft Closeout rows are invalid")
    custom_next = state.get(f"closeout_custom_next_{workbook_key}", 0)
    if not isinstance(custom_next, int) or isinstance(custom_next, bool) or custom_next < 0:
        raise ValueError("Draft Closeout row counter is invalid")
    payments = state.get(f"membership_saved_payments_{workbook_key}", [])
    if not isinstance(payments, list) or not all(isinstance(row, dict) for row in payments):
        raise ValueError("Draft member payments are invalid")
    for prefix in ("closeout_payload_", "coupon_saved_payload_", "inhouse_saved_payload_"):
        value = state.get(f"{prefix}{workbook_key}")
        if value is not None and not isinstance(value, dict):
            raise ValueError("Draft saved section is invalid")


def _encode(value: object) -> object:
    if isinstance(value, date):
        return {"__draft_type__": "date", "value": value.isoformat()}
    if isinstance(value, tuple):
        return {"__draft_type__": "tuple", "value": [_encode(item) for item in value]}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _encode(item) for key, item in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError(f"Draft contains an unsupported value type: {type(value).__name__}")


def _decode(value: object) -> object:
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if isinstance(value, dict):
        tag = value.get("__draft_type__")
        if tag == "date" and set(value) == {"__draft_type__", "value"}:
            return date.fromisoformat(value["value"])
        if tag == "tuple" and set(value) == {"__draft_type__", "value"}:
            return tuple(_decode(item) for item in value["value"])
        if tag is not None:
            raise ValueError("Draft contains an unsupported saved value")
        return {key: _decode(item) for key, item in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError("Draft contains an unsupported saved value")


def _safe_name(name: object) -> str:
    if not isinstance(name, str) or not name or name in (".", "..") or "/" in name or "\\" in name:
        raise ValueError("Draft contains an invalid report filename")
    return name


def validate_draft_settlement(upload: RestoredUpload, deposit_date: date) -> None:
    """Apply the same header/date readiness requirements before replacing work."""
    try:
        workbook = openpyxl.load_workbook(
            io.BytesIO(upload.getvalue()), read_only=True, data_only=True
        )
        try:
            has_header = False
            for sheet in workbook:
                for row in sheet.iter_rows(
                    min_row=1, max_row=min(sheet.max_row, 20), values_only=True
                ):
                    labels = [str(value or "").strip().lower() for value in row]
                    if "network" in labels and "processed net amount" in labels:
                        has_header = True
                        break
                if has_header:
                    break
            sheet = workbook.worksheets[0]
            report_date = None
            for row in sheet.iter_rows(
                min_row=1, max_row=min(sheet.max_row, 12), values_only=True
            ):
                for index, value in enumerate(row):
                    if str(value or "").strip().lower() == "date" and index + 1 < len(row):
                        report_date = row[index + 1]
                        break
                if report_date is not None:
                    break
            if isinstance(report_date, datetime):
                report_date = report_date.date()
            if not has_header or report_date != deposit_date:
                raise ValueError("Saved card settlement is missing its required columns or matching deposit date")
        finally:
            workbook.close()
    except Exception as exc:
        raise ValueError(f"Saved card settlement could not be verified: {exc}") from exc


def _descriptor(path: str, upload: object) -> tuple[dict[str, str], bytes]:
    body = upload.getvalue()
    if not isinstance(body, bytes) or len(body) > _MAX_ENTRY:
        raise ValueError("A source report is too large or invalid for a draft")
    return {
        "path": path,
        "name": _safe_name(upload.name),
        "sha256": hashlib.sha256(body).hexdigest(),
    }, body


def create_deposit_draft(
    sms_uploads: list[object] | tuple[object, ...],
    settlement_upload: object,
    session_state: MutableMapping[str, object],
    *,
    workbook_key: str,
    deposit_date: date,
) -> bytes:
    """Save the six source files and only the guided-step state, never run history."""
    if len(sms_uploads) != 6 or not _WORKBOOK_KEY.fullmatch(workbook_key):
        raise ValueError("A draft needs six verified SMS reports")
    state = dict(session_state)
    row_ids = _activity_ids(state, workbook_key)
    _validate_saved_state(state, workbook_key)
    saved = {
        key: _encode(value)
        for key, value in state.items()
        if isinstance(key, str) and _allowed_field(key, workbook_key, row_ids)
    }
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        sms_descriptors = []
        for index, upload in enumerate(sms_uploads, 1):
            descriptor, body = _descriptor(f"sms/{index:02d}.xls", upload)
            sms_descriptors.append(descriptor)
            archive.writestr(descriptor["path"], body)
        settlement_descriptor, body = _descriptor("card_settlement.xlsx", settlement_upload)
        archive.writestr(settlement_descriptor["path"], body)
        archive.writestr("manifest.json", json.dumps({
            "version": 1,
            "deposit_date": deposit_date.isoformat(),
            "workbook_key": workbook_key,
            "sms": sms_descriptors,
            "settlement": settlement_descriptor,
            "state": saved,
        }, allow_nan=False))
    return output.getvalue()


def _read_upload(archive: ZipFile, descriptor: object, expected_path: str) -> RestoredUpload:
    if not isinstance(descriptor, dict) or descriptor.get("path") != expected_path:
        raise ValueError("Draft report listing is invalid")
    name = _safe_name(descriptor.get("name"))
    body = archive.read(expected_path)
    if hashlib.sha256(body).hexdigest() != descriptor.get("sha256"):
        raise ValueError("A saved report changed or damaged")
    return RestoredUpload(name, body)


def read_deposit_draft(data: bytes) -> DepositDraft:
    """Check structure, sizes, fields, and hashes before any session is changed."""
    if not isinstance(data, bytes) or len(data) > _MAX_ARCHIVE:
        raise ValueError("Draft file is invalid or too large")
    try:
        with ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            expected = {"manifest.json", "card_settlement.xlsx"} | {
                f"sms/{index:02d}.xls" for index in range(1, 7)
            }
            if len(infos) != 8 or {info.filename for info in infos} != expected:
                raise ValueError("Draft must contain exactly six reports and one card settlement")
            if any(info.file_size > _MAX_ENTRY for info in infos) or sum(info.file_size for info in infos) > _MAX_TOTAL:
                raise ValueError("Draft contents are too large")
            manifest = json.loads(archive.read("manifest.json"))
            if not isinstance(manifest, dict) or manifest.get("version") != 1:
                raise ValueError("Draft version is not supported")
            old_key = manifest.get("workbook_key")
            if not isinstance(old_key, str) or not _WORKBOOK_KEY.fullmatch(old_key):
                raise ValueError("Draft workflow identity is invalid")
            deposit_date = date.fromisoformat(manifest["deposit_date"])
            sms_descriptors = manifest.get("sms")
            if not isinstance(sms_descriptors, list) or len(sms_descriptors) != 6:
                raise ValueError("Draft must contain exactly six SMS reports")
            sms = tuple(
                _read_upload(archive, descriptor, f"sms/{index:02d}.xls")
                for index, descriptor in enumerate(sms_descriptors, 1)
            )
            settlement = _read_upload(archive, manifest.get("settlement"), "card_settlement.xlsx")
            raw_state = manifest.get("state")
            if not isinstance(raw_state, dict):
                raise ValueError("Draft guided-step state is invalid")
            row_ids = _activity_ids(raw_state, old_key)
            for key in raw_state:
                if not isinstance(key, str) or not _allowed_field(key, old_key, row_ids):
                    raise ValueError(f"Draft has unexpected saved field: {key}")
            state = {key: _decode(value) for key, value in raw_state.items()}
            _validate_saved_state(state, old_key)
            return DepositDraft(deposit_date, old_key, sms, settlement, state)
    except (BadZipFile, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Draft file is invalid or damaged") from exc


def restore_deposit_draft(
    session_state: MutableMapping[str, object],
    draft: DepositDraft,
    *,
    uploader_key: int,
    workbook_key: str,
) -> None:
    """Restore only after the caller has validated the draft's report contents."""
    if not _WORKBOOK_KEY.fullmatch(workbook_key):
        raise ValueError("Invalid restored workflow identity")
    _validate_saved_state(draft.state, draft.old_workbook_key)
    for key in list(session_state):
        if isinstance(key, str) and (
            key.startswith(_SCOPED_PREFIXES)
            or any(key.startswith(f"activity_{category}_") for category in _ACTIVITY_CATEGORIES)
        ):
            session_state.pop(key, None)
    for key, value in draft.state.items():
        session_state[key.replace(draft.old_workbook_key, workbook_key)] = value
    sms_key = f"sms_reports_{uploader_key}"
    card_key = f"card_settlement_{uploader_key}"
    session_state[DAILY_PROGRAM_UPLOADS_KEY] = {
        sms_key: list(draft.sms_uploads),
        card_key: draft.settlement_upload,
    }
    session_state[DAILY_PROGRAM_RECREATED_UPLOADS_KEY] = (sms_key, card_key)
    session_state.pop(DAILY_PROGRAM_UPLOAD_SELECTIONS_KEY, None)
    session_state["file_uploader_key"] = uploader_key
    session_state[DEPOSIT_PAGE_STAGE_KEY] = DEPOSIT_STEPS_STAGE
