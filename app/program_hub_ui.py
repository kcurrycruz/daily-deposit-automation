"""Program registry and safe navigation state for the finance operations hub."""

from dataclasses import dataclass
from hashlib import sha256
from base64 import b64encode
from html import escape
from pathlib import Path
from typing import MutableMapping


ACTIVE_PROGRAM_KEY = "active_finance_program"
PROGRAM_OPENING_KEY = "_finance_program_opening"
DAILY_DEPOSITS = "daily_deposits"
AP_STATEMENTS = "ap_statements"
SIDEBAR_COLLAPSE_REQUEST_KEY = "_collapse_navigation_sidebar"
DAILY_PROGRAM_SNAPSHOT_KEY = "_daily_program_widget_snapshot"
DAILY_PROGRAM_UPLOADS_KEY = "_daily_program_preserved_uploads"
DAILY_PROGRAM_UPLOAD_SELECTIONS_KEY = "_daily_program_upload_widget_selections"
DAILY_PROGRAM_RECREATED_UPLOADS_KEY = "_daily_program_recreated_uploaders"
DAILY_PROGRAM_SMS_SIBLING_CALLBACK_KEY = "_daily_program_sms_sibling_callback"

_DAILY_WIDGET_PREFIXES = (
    "membership_",
    "activity_",
    "coupon_",
    "inhouse_",
    "closeout_",
)
_DAILY_UPLOAD_PREFIXES = ("sms_reports_", "card_settlement_")
_DAILY_ACTION_PREFIXES = (
    "add_activity_",
    "save_activity_",
    "remove_membership_",
    "remove_activity_",
    "delete_activity_",
    "inhouse_add_",
    "inhouse_remove_",
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
        AP_STATEMENTS,
        "AP Statements",
        "Review and reconcile accounts-payable statements.",
        True,
    ),
    ProgramDefinition(
        "credit_card_process",
        "Credit Card Process",
        "Process and verify credit-card activity.",
        False,
    ),
)


def program_card_html(program: ProgramDefinition) -> str:
    """Return safe, state-aware card markup for a finance program."""
    state_class = "is-available" if program.enabled else "is-coming-soon"
    icon_path = {
        DAILY_DEPOSITS: '<rect x="5" y="8" width="30" height="25" rx="5"/><path d="M5 15h30M12 23h7m-7 5h12M12 8V5m16 3V5"/><circle cx="29" cy="27" r="7"/><path d="m26 27 2 2 4-4"/>',
        "credit_card_process": '<rect x="4" y="9" width="32" height="23" rx="5"/><path d="M4 17h32M10 25h8m5 0h5"/>',
        AP_STATEMENTS: '<path d="M12 5h14l7 7v23H9V8a3 3 0 0 1 3-3Z"/><path d="M26 5v8h7M15 19h12M15 25h8M15 30h10"/>',
    }.get(program.key, '<path d="M9 31C4 12 18 5 33 7c1 17-8 25-24 24Zm0 0L26 14"/>')
    tone = {
        DAILY_DEPOSITS: "sage",
        "credit_card_process": "honey",
        AP_STATEMENTS: "mist",
    }.get(program.key, "sage")
    status = "Ready to open" if program.enabled else "Planned"
    return (
        f'<section class="hwfc-program-card {state_class}">'
        f'<div class="hwfc-program-card-top"><span class="hwfc-program-icon tone-{tone}">'
        '<svg width="34" height="34" viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="1.8"'
        f' stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">{icon_path}</svg>'
        f'</span><span class="hwfc-program-status">{status}</span></div>'
        f'<h2 class="hwfc-program-card-title">{escape(program.title)}</h2>'
        f'<p class="hwfc-program-card-copy">{escape(program.description)}</p>'
        "</section>"
    )


def render_program_hub(ui) -> str | None:
    """Render program choices and return an enabled selected program key."""
    hub_css = Path(__file__).with_name("program_hub.css").read_text(encoding="utf-8")
    ui.markdown(f"<style>{hub_css}</style>", unsafe_allow_html=True)
    leaf_path = Path(__file__).with_name("assets") / "hwfc-leaf-modern.png"
    leaf_src = "data:image/png;base64," + b64encode(leaf_path.read_bytes()).decode("ascii")
    logo_path = Path(__file__).with_name("assets") / "hwfc-logo-simplified.png"
    logo_src = "data:image/png;base64," + b64encode(logo_path.read_bytes()).decode("ascii")
    ui.markdown(
        f"""
        <div class="hwfc-hub-hero">
          <div class="hwfc-hub-brand">
            <span class="hwfc-hub-emblem" aria-hidden="true">
              <img src="{logo_src}" alt="" width="64" height="64"/>
            </span>
            <div><div class="hwfc-hub-kicker">Honest Weight Food Co-op</div>
            <div class="hwfc-hub-brand-note">Our co-op. Our workspace.</div></div>
          </div>
          <div class="hwfc-hub-heading-row">
            <div><h1 class="hwfc-hub-title">Finance Operations</h1>
            <p class="hwfc-hub-subtitle">A little less busywork. More room for good work.</p></div>
            <span class="hwfc-hub-leaf" aria-hidden="true">
              <img src="{leaf_src}" alt="" width="126" height="84"/>
            </span>
          </div>
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
                on_click=activate_program if program.enabled else None,
                args=(ui.session_state, program.key) if program.enabled else None,
            ) and program.enabled:
                selected_key = program.key
    ui.markdown(
        '<div class="hwfc-hub-footer"><span>Rooted in community. Built for the everyday.</span>'
        '<span>Honest Weight · Finance</span></div>',
        unsafe_allow_html=True,
    )
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
    state[PROGRAM_OPENING_KEY] = normalized_key
    state[SIDEBAR_COLLAPSE_REQUEST_KEY] = True
    return True


def render_program_transition(ui) -> None:
    """Mask only menu-to-program runs; never leave a mask over a stopped app."""
    requested = normalize_program_selection(ui.session_state.pop(PROGRAM_OPENING_KEY, None))
    active = normalize_program_selection(ui.session_state.get(ACTIVE_PROGRAM_KEY))
    opening = ' data-program-opening="true"' if requested and requested == active else ''
    styles = Path(__file__).with_name('program_transition.css').read_text(encoding='utf-8')
    ui.markdown(
        f'<style>{styles}</style><span id="hwfc-program-loader" role="status"{opening}>'
        'Loading application</span>', unsafe_allow_html=True,
    )


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
        # Streamlit invokes callbacks before the app reruns.  Remember a
        # non-empty SMS change only through that callback batch so its
        # recreated, empty settlement sibling cannot look like a user clear.
        if selected_upload:
            state[DAILY_PROGRAM_SMS_SIBLING_CALLBACK_KEY] = widget_key
        else:
            state.pop(DAILY_PROGRAM_SMS_SIBLING_CALLBACK_KEY, None)
        return
    recreated_value = state.get(DAILY_PROGRAM_RECREATED_UPLOADS_KEY)
    recreated_uploads = (
        set(recreated_value)
        if isinstance(recreated_value, (list, tuple, set))
        else set()
    )
    if (
        widget_key.startswith("card_settlement_")
        and selected_upload is None
        and state.pop(DAILY_PROGRAM_SMS_SIBLING_CALLBACK_KEY, None)
    ):
        recreated_uploads.discard(widget_key)
        if recreated_uploads:
            state[DAILY_PROGRAM_RECREATED_UPLOADS_KEY] = tuple(recreated_uploads)
        else:
            state.pop(DAILY_PROGRAM_RECREATED_UPLOADS_KEY, None)
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


def finish_daily_upload_callback_batch(state: MutableMapping[str, object]) -> None:
    """Expire the SMS sibling signal after Streamlit has completed its rerun."""
    state.pop(DAILY_PROGRAM_SMS_SIBLING_CALLBACK_KEY, None)


def clear_daily_uploads(state: MutableMapping[str, object]) -> None:
    """Remove preserved and rendered Daily upload values for Start Over."""
    state.pop(DAILY_PROGRAM_UPLOADS_KEY, None)
    state.pop(DAILY_PROGRAM_UPLOAD_SELECTIONS_KEY, None)
    state.pop(DAILY_PROGRAM_RECREATED_UPLOADS_KEY, None)
    state.pop(DAILY_PROGRAM_SMS_SIBLING_CALLBACK_KEY, None)
    for key in tuple(state):
        if isinstance(key, str) and key.startswith(_DAILY_UPLOAD_PREFIXES):
            state.pop(key, None)


def return_to_program_hub(state: MutableMapping[str, object]) -> None:
    """Clear the active program while preserving all other state."""
    state.pop(ACTIVE_PROGRAM_KEY, None)
    state.pop(PROGRAM_OPENING_KEY, None)
