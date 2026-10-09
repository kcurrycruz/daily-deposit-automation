"""Program registry and safe navigation state for the finance operations hub."""

from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import MutableMapping


ACTIVE_PROGRAM_KEY = "active_finance_program"
DAILY_DEPOSITS = "daily_deposits"
AP_STATEMENTS = "ap_statements"
SIDEBAR_COLLAPSE_REQUEST_KEY = "_collapse_navigation_sidebar"
DAILY_PROGRAM_SNAPSHOT_KEY = "_daily_program_widget_snapshot"
DAILY_PROGRAM_UPLOADS_KEY = "_daily_program_preserved_uploads"

_DAILY_WIDGET_PREFIXES = (
    "membership_",
    "activity_",
    "coupon_",
    "closeout_",
)
_DAILY_UPLOAD_PREFIXES = ("daily_workbook_", "card_settlement_")
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
        AP_STATEMENTS,
        "AP Statements",
        "Review and reconcile accounts-payable statements.",
        True,
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
        '<svg viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="1.8"'
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
    ui.markdown(
        """
        <div class="hwfc-hub-hero">
          <div class="hwfc-hub-brand">
            <span class="hwfc-hub-emblem" aria-hidden="true">
              <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2" focusable="false">
                <path d="M24 38V23M24 29C9 29 8 17 9 10c13 0 19 9 15 19Zm0-6C23 10 33 7 40 8c0 12-6 18-16 15Z"/>
                <path d="m15 18 9 11m9-15-9 9" stroke-linecap="round"/>
              </svg>
            </span>
            <div><div class="hwfc-hub-kicker">Honest Weight Food Co-op</div>
            <div class="hwfc-hub-brand-note">Our co-op. Our workspace.</div></div>
          </div>
          <div class="hwfc-hub-heading-row">
            <div><h1 class="hwfc-hub-title">Finance Operations</h1>
            <p class="hwfc-hub-subtitle">A little less busywork. More room for good work.</p></div>
            <span class="hwfc-hub-leaf" aria-hidden="true">
              <svg viewBox="0 0 110 110" fill="none" stroke="currentColor" stroke-width="1.4" focusable="false">
                <path d="M24 92C7 40 46 12 93 17c5 49-20 78-69 75Zm0 0 55-60M41 74l-4-23m22 5 24-2m-27 9L53 37"/>
              </svg>
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


def sync_daily_upload(
    state: MutableMapping[str, object], widget_key: str
) -> None:
    """Synchronize a user upload change without writing its read-only widget key."""
    if not widget_key.startswith(_DAILY_UPLOAD_PREFIXES):
        return
    uploads = state.get(DAILY_PROGRAM_UPLOADS_KEY)
    updated_uploads = dict(uploads) if isinstance(uploads, dict) else {}
    selected_upload = state.get(widget_key)
    if selected_upload is None:
        updated_uploads.pop(widget_key, None)
    else:
        updated_uploads[widget_key] = selected_upload
    if updated_uploads:
        state[DAILY_PROGRAM_UPLOADS_KEY] = updated_uploads
    else:
        state.pop(DAILY_PROGRAM_UPLOADS_KEY, None)


def return_to_program_hub(state: MutableMapping[str, object]) -> None:
    """Clear the active program while preserving all other state."""
    state.pop(ACTIVE_PROGRAM_KEY, None)
