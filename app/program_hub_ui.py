"""Program registry and safe navigation state for the finance operations hub."""

from dataclasses import dataclass
from hashlib import sha256
from html import escape
from typing import MutableMapping


ACTIVE_PROGRAM_KEY = "active_finance_program"
DAILY_DEPOSITS = "daily_deposits"
SIDEBAR_COLLAPSE_REQUEST_KEY = "_collapse_navigation_sidebar"
DAILY_PROGRAM_SNAPSHOT_KEY = "_daily_program_widget_snapshot"
DAILY_PROGRAM_UPLOADS_KEY = "_daily_program_preserved_uploads"
DAILY_PROGRAM_UPLOAD_SELECTIONS_KEY = "_daily_program_upload_widget_selections"
DAILY_PROGRAM_RECREATED_UPLOADS_KEY = "_daily_program_recreated_uploaders"

_DAILY_WIDGET_PREFIXES = (
    "membership_",
    "activity_",
    "coupon_",
    "closeout_",
)
_DAILY_UPLOAD_PREFIXES = ("sms_reports_", "card_settlement_")
_DAILY_ACTION_PREFIXES = (
    "add_activity_",
    "save_activity_",
    "remove_membership_",
    "remove_activity_",
    "delete_activity_",
    "closeout_add_custom_",
    "closeout_remove_custom_",
    "review_closeout_",
)


@dataclass(frozen=True)
class ProgramDefinition:
    key: str
    title: str
    description: str
    enabled: bool


PROGRAMS: tuple[ProgramDefinition, ...] = (
    ProgramDefinition(
        DAILY_DEPOSITS,
        "Daily Deposits",
        "Reconcile daily reports and prepare the QuickBooks import.",
        True,
    ),
    ProgramDefinition(
        "credit_card_process",
        "Credit Card Process",
        "Process and verify credit-card activity.",
        False,
    ),
    ProgramDefinition(
        "ap_statements",
        "AP Statements",
        "Review and reconcile accounts-payable statements.",
        False,
    ),
)


def program_card_html(program: ProgramDefinition) -> str:
    """Return safe, state-aware card markup for a finance program."""
    state_class = "is-available" if program.enabled else "is-coming-soon"
    return (
        f'<section class="hwfc-program-card {state_class}">'
        f'<h2 class="hwfc-program-card-title">{escape(program.title)}</h2>'
        f'<p class="hwfc-program-card-copy">{escape(program.description)}</p>'
        "</section>"
    )


def render_program_hub(ui) -> str | None:
    """Render program choices and return an enabled selected program key."""
    ui.markdown(
        """
        <div class="hwfc-hub-hero">
          <div class="hwfc-hub-kicker">Honest Weight Food Co-op</div>
          <div class="hwfc-hub-title">Finance Operations</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    ui.markdown(
        """
        <section class="hwfc-hub-prompt">
          <h2>What are you working on?</h2>
          <p>Choose a program to begin.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    selected_key = None
    for column, program in zip(ui.columns(len(PROGRAMS)), PROGRAMS):
        with column:
            column.markdown(program_card_html(program), unsafe_allow_html=True)
            if column.button(
                "Open program →" if program.enabled else "Coming Soon",
                key=f"open_program_{program.key}",
                disabled=not program.enabled,
                use_container_width=True,
            ) and program.enabled:
                selected_key = program.key
    return selected_key


def render_all_programs_action(ui) -> bool:
    """Render the hub-return control without changing navigation state."""
    return ui.button(
        "← All Programs",
        key="return_to_program_hub",
        use_container_width=True,
    )


def normalize_program_selection(value: object) -> str | None:
    """Return an enabled program key, or ``None`` for invalid selections."""
    if not isinstance(value, str):
        return None
    for program in PROGRAMS:
        if program.key == value and program.enabled:
            return program.key
    return None


def activate_program(
    state: MutableMapping[str, object], program_key: str
) -> bool:
    """Activate an enabled program without changing unrelated state."""
    normalized_key = normalize_program_selection(program_key)
    if normalized_key is None:
        return False
    state[ACTIVE_PROGRAM_KEY] = normalized_key
    state[SIDEBAR_COLLAPSE_REQUEST_KEY] = True
    return True


def _is_daily_widget_value(key: object) -> bool:
    """Return whether a key is a restorable Daily input rather than an action."""
    if not isinstance(key, str) or not key.startswith(_DAILY_WIDGET_PREFIXES):
        return False
    if key.startswith(_DAILY_ACTION_PREFIXES):
        return False
    return not key.endswith("_add")


def preserve_daily_program_state(state: MutableMapping[str, object]) -> None:
    """Copy Daily widget values outside Streamlit's widget-cleanup lifecycle."""
    preserved_uploads = state.get(DAILY_PROGRAM_UPLOADS_KEY)
    if not isinstance(preserved_uploads, dict):
        preserved_uploads = {}
    state[DAILY_PROGRAM_UPLOADS_KEY] = {
        **preserved_uploads,
        **{
            key: value
            for key, value in state.items()
            if (
                isinstance(key, str)
                and key.startswith(_DAILY_UPLOAD_PREFIXES)
                and value is not None
                and not (key.startswith("sms_reports_") and value == [])
            )
        },
    }
    state[DAILY_PROGRAM_SNAPSHOT_KEY] = {
        key: value for key, value in state.items() if _is_daily_widget_value(key)
    }


def restore_daily_program_state(state: MutableMapping[str, object]) -> None:
    """Restore saved Daily inputs before their widgets render again."""
    snapshot = state.pop(DAILY_PROGRAM_SNAPSHOT_KEY, None)
    if not isinstance(snapshot, dict):
        return
    # Browser file inputs cannot restore their visible selection after the Hub
    # stops rendering them.  Remember which uploaders were recreated until
    # their next real change so that restored widget values do not masquerade
    # as a removable browser selection.
    state.pop(DAILY_PROGRAM_UPLOAD_SELECTIONS_KEY, None)
    uploads = state.get(DAILY_PROGRAM_UPLOADS_KEY)
    recreated_uploads = (
        tuple(
            key
            for key in uploads
            if isinstance(key, str) and key.startswith(_DAILY_UPLOAD_PREFIXES)
        )
        if isinstance(uploads, dict)
        else ()
    )
    if recreated_uploads:
        state[DAILY_PROGRAM_RECREATED_UPLOADS_KEY] = recreated_uploads
    else:
        state.pop(DAILY_PROGRAM_RECREATED_UPLOADS_KEY, None)
    for key, value in snapshot.items():
        if _is_daily_widget_value(key):
            state.setdefault(key, value)


def preserved_daily_upload(
    state: MutableMapping[str, object], widget_key: str
) -> object | None:
    """Return a preserved uploader value without assigning its read-only key."""
    uploads = state.get(DAILY_PROGRAM_UPLOADS_KEY)
    if not isinstance(uploads, dict) or not widget_key.startswith(
        _DAILY_UPLOAD_PREFIXES
    ):
        return None
    return uploads.get(widget_key)


def _daily_upload_identity(upload: object) -> tuple[object, ...]:
    """Return a stable identity for an upload across recreated Streamlit widgets."""
    name = getattr(upload, "name", None)
    try:
        body = upload.getvalue()
    except (AttributeError, OSError, ValueError):
        body = None
    if isinstance(body, bytes):
        return (name, len(body), sha256(body).hexdigest())
    file_id = getattr(upload, "file_id", None)
    size = getattr(upload, "size", None)
    return (name, file_id, size, id(upload))


def reconcile_daily_upload_selection(
    state: MutableMapping[str, object],
    widget_key: str,
    selected_uploads: list[object] | tuple[object, ...] | None,
    *,
    explicit: bool,
) -> list[object] | None:
    """Merge recreated SMS selections while preserving real removal semantics."""
    if not widget_key.startswith("sms_reports_"):
        return selected_uploads

    current = list(selected_uploads or [])
    uploads = state.get(DAILY_PROGRAM_UPLOADS_KEY)
    updated_uploads = dict(uploads) if isinstance(uploads, dict) else {}
    preserved_value = updated_uploads.get(widget_key)
    preserved = (
        list(preserved_value)
        if isinstance(preserved_value, (list, tuple))
        else []
    )
    selections = state.get(DAILY_PROGRAM_UPLOAD_SELECTIONS_KEY)
    updated_selections = dict(selections) if isinstance(selections, dict) else {}
    recreated_value = state.get(DAILY_PROGRAM_RECREATED_UPLOADS_KEY)
    recreated_uploads = (
        set(recreated_value)
        if isinstance(recreated_value, (list, tuple, set))
        else set()
    )
    was_recreated = widget_key in recreated_uploads

    if explicit and not current and was_recreated:
        return (
            preserved_value
            if isinstance(preserved_value, list)
            else preserved or None
        )

    if explicit and not current:
        updated_uploads.pop(widget_key, None)
        updated_selections.pop(widget_key, None)
        recreated_uploads.discard(widget_key)
        if updated_uploads:
            state[DAILY_PROGRAM_UPLOADS_KEY] = updated_uploads
        else:
            state.pop(DAILY_PROGRAM_UPLOADS_KEY, None)
        if updated_selections:
            state[DAILY_PROGRAM_UPLOAD_SELECTIONS_KEY] = updated_selections
        else:
            state.pop(DAILY_PROGRAM_UPLOAD_SELECTIONS_KEY, None)
        if recreated_uploads:
            state[DAILY_PROGRAM_RECREATED_UPLOADS_KEY] = tuple(recreated_uploads)
        else:
            state.pop(DAILY_PROGRAM_RECREATED_UPLOADS_KEY, None)
        return None

    current_ids = tuple(_daily_upload_identity(upload) for upload in current)
    prior_ids = () if was_recreated else updated_selections.get(widget_key)
    updated_selections[widget_key] = current_ids
    state[DAILY_PROGRAM_UPLOAD_SELECTIONS_KEY] = updated_selections
    if explicit and was_recreated:
        recreated_uploads.discard(widget_key)
        if recreated_uploads:
            state[DAILY_PROGRAM_RECREATED_UPLOADS_KEY] = tuple(recreated_uploads)
        else:
            state.pop(DAILY_PROGRAM_RECREATED_UPLOADS_KEY, None)

    if not current:
        return preserved_value if isinstance(preserved_value, list) else preserved or None

    removed_ids = set(prior_ids or ()) - set(current_ids)
    current_by_id = {
        _daily_upload_identity(upload): upload
        for upload in current
    }
    merged: list[object] = []
    merged_ids: set[tuple[object, ...]] = set()
    for upload in preserved:
        upload_id = _daily_upload_identity(upload)
        if upload_id in removed_ids or upload_id in merged_ids:
            continue
        merged.append(current_by_id.get(upload_id, upload))
        merged_ids.add(upload_id)
    for upload in current:
        upload_id = _daily_upload_identity(upload)
        if upload_id not in merged_ids:
            merged.append(upload)
            merged_ids.add(upload_id)

    updated_uploads[widget_key] = merged
    state[DAILY_PROGRAM_UPLOADS_KEY] = updated_uploads
    return merged


def sync_daily_upload(
    state: MutableMapping[str, object], widget_key: str
) -> None:
    """Synchronize a user upload change without writing its read-only widget key."""
    if not widget_key.startswith(_DAILY_UPLOAD_PREFIXES):
        return
    uploads = state.get(DAILY_PROGRAM_UPLOADS_KEY)
    updated_uploads = dict(uploads) if isinstance(uploads, dict) else {}
    selected_upload = state.get(widget_key)
    if widget_key.startswith("sms_reports_") and (
        selected_upload is None or isinstance(selected_upload, (list, tuple))
    ):
        reconcile_daily_upload_selection(
            state,
            widget_key,
            selected_upload,
            explicit=True,
        )
        return
    recreated_value = state.get(DAILY_PROGRAM_RECREATED_UPLOADS_KEY)
    recreated_uploads = (
        set(recreated_value)
        if isinstance(recreated_value, (list, tuple, set))
        else set()
    )
    if widget_key in recreated_uploads and selected_upload is None:
        return
    recreated_uploads.discard(widget_key)
    if recreated_uploads:
        state[DAILY_PROGRAM_RECREATED_UPLOADS_KEY] = tuple(recreated_uploads)
    else:
        state.pop(DAILY_PROGRAM_RECREATED_UPLOADS_KEY, None)
    if selected_upload is None or selected_upload == []:
        updated_uploads.pop(widget_key, None)
    else:
        updated_uploads[widget_key] = selected_upload
    if updated_uploads:
        state[DAILY_PROGRAM_UPLOADS_KEY] = updated_uploads
    else:
        state.pop(DAILY_PROGRAM_UPLOADS_KEY, None)


def clear_daily_uploads(state: MutableMapping[str, object]) -> None:
    """Remove preserved and rendered Daily upload values for Start Over."""
    state.pop(DAILY_PROGRAM_UPLOADS_KEY, None)
    state.pop(DAILY_PROGRAM_UPLOAD_SELECTIONS_KEY, None)
    state.pop(DAILY_PROGRAM_RECREATED_UPLOADS_KEY, None)
    for key in tuple(state):
        if isinstance(key, str) and key.startswith(_DAILY_UPLOAD_PREFIXES):
            state.pop(key, None)


def return_to_program_hub(state: MutableMapping[str, object]) -> None:
    """Clear the active program while preserving all other state."""
    state.pop(ACTIVE_PROGRAM_KEY, None)
