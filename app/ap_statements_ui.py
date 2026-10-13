"""AP component and navigation, protected by server-side shared access."""

from pathlib import Path
from re import fullmatch
from datetime import datetime, timezone
from app.ap_shared.models import read_config
from app.ap_shared.access import require_access, attempt_unlock, lock_access

_EXIT_KEY = "_ap_exit_confirmation"
_COMPONENT_KEY = "hwfc_ap_statements_workspace"
_LAST_EXIT_REQUEST_KEY = "_ap_last_exit_request"


def ap_frontend_path() -> Path:
    return Path(__file__).resolve().parent / "ap_statements" / "frontend"


def render_ap_statements(ui, *, component_renderer=None, frontend_path=None, config=None, limiter=None, now=None) -> bool:
    """Return True only after the user confirms leaving the AP workspace."""
    styles = Path(__file__).with_name("ap_statements.css").read_text(encoding="utf-8")
    ui.markdown(f'<style>{styles}</style><span id="hwfc-ap-page" aria-hidden="true"></span>', unsafe_allow_html=True)
    now = now or datetime.now(timezone.utc)
    try:
        config = config or read_config(ui.secrets)
    except Exception:
        ui.title("AP Statements")
        ui.error("Shared AP storage is not configured. Ask the app owner to finish the private Supabase and Streamlit Secrets setup.")
        return ui.button("← All Programs", key="ap_gate_back", type="primary")
    try:
        require_access(ui.session_state, config, now)
    except PermissionError:
        if "_ap_authorization" in ui.session_state:
            lock_access(ui.session_state)
        ui.title("Unlock AP Statements")
        if ui.button("← All Programs", key="ap_gate_back"):
            return True
        with ui.form("ap_unlock", clear_on_submit=True):
            submitted = ui.text_input("Finance team password", type="password", key="_ap_password")
            clicked = ui.form_submit_button("Open AP Statements")
        if clicked:
            if limiter is None:
                try:
                    from app.ap_shared.repository import create_repository
                    limiter = create_repository(config)
                except Exception:
                    limiter = None
            if limiter is not None and attempt_unlock(ui.session_state, submitted, config, limiter, now):
                ui.rerun()
            else:
                ui.session_state.pop("_ap_password", None)
                ui.warning("Unable to unlock AP. Check the password and try again later if access is temporarily limited or unavailable.")
        return False
    if ui.button("Lock AP", key="ap_lock_access"):
        lock_access(ui.session_state)
        ui.rerun()
        return False
    path = Path(frontend_path) if frontend_path is not None else ap_frontend_path()
    missing_build = not (path / "index.html").is_file()
    if missing_build:
        ui.title("AP Statements")
        if ui.button("← All Programs", key="ap_all_programs", type="primary"):
            ui.session_state[_EXIT_KEY] = True
    # Reserve one stable block so conditional guidance cannot move/remount
    # the component and discard its browser-only state on a rerun.
    with ui.container():
        if ui.session_state.get(_EXIT_KEY):
            ui.warning(
                "Before leaving, use Save session and/or export your report in the "
                "workspace below. Unsaved rows and notes will be lost; original "
                "PDFs must be selected again. Browser saving is not a backup."
            )
            if ui.button("Stay in AP Statements", key="ap_stay", type="primary"):
                ui.session_state.pop(_EXIT_KEY, None)
            if ui.button("Leave for All Programs", key="ap_leave", type="primary"):
                ui.session_state.pop(_EXIT_KEY, None)
                return True

    if missing_build:
        ui.error("AP component build is missing. Prepare the local frontend assets before deploying.")
        return False
    if component_renderer is None:
        import streamlit.components.v1 as components

        component_renderer = components.declare_component("hwfc_ap_statements", path=str(path))
    # Only a new, navigation-only request may return to the hub.
    # No financial props are sent to or returned from the component.
    value = component_renderer(key=_COMPONENT_KEY)
    if (
        type(value) is dict
        and value.keys() == {"action", "request_id"}
        and value["action"] == "return_to_programs"
        and type(value["request_id"]) is str
        and fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", value["request_id"])
    ):
        request_id = value["request_id"]
        if request_id != ui.session_state.get(_LAST_EXIT_REQUEST_KEY):
            ui.session_state[_LAST_EXIT_REQUEST_KEY] = request_id
            ui.session_state.pop(_EXIT_KEY, None)
            return True
    ui.caption(
        "BILL API is disconnected. Comparisons use imported CSV records and "
        "depend on export coverage. This does not verify QuickBooks sync."
    )
    ui.caption(
        "Save session keeps extracted rows and notes in this browser profile, "
        "visible to others using it. Original PDFs are not saved: select your "
        "original PDFs again after leaving. Use Save session or export your "
        "report before switching programs."
    )
    return False
