"""AP component and navigation, protected by server-side shared access."""

from pathlib import Path
from base64 import b64encode
from re import fullmatch
from datetime import datetime, timezone
from app.ap_shared.models import read_config
from app.ap_shared.access import require_access, attempt_unlock, lock_access

_EXIT_KEY = "_ap_exit_confirmation"
_COMPONENT_KEY = "hwfc_ap_statements_workspace"
_LAST_EXIT_REQUEST_KEY = "_ap_last_exit_request"


def ap_frontend_path() -> Path:
    return Path(__file__).resolve().parent / "ap_statements" / "frontend"


def render_ap_statements(ui, *, component_renderer=None, frontend_path=None, config=None, limiter=None, now=None, service=None) -> bool:
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
        authorization = require_access(ui.session_state, config, now)
    except PermissionError:
        if "_ap_authorization" in ui.session_state:
            lock_access(ui.session_state)
        with ui.container(key="ap_unlock_card"):
            logo = Path(__file__).with_name("assets") / "hwfc-logo-simplified.png"
            src = "data:image/png;base64," + b64encode(logo.read_bytes()).decode("ascii")
            ui.markdown(
                '<div id="hwfc-ap-gate" class="ap-gate-brand">'
                f'<img src="{src}" alt="Honest Weight Food Co-op logo" width="52" height="52"/>'
                '<div><strong>Honest Weight Food Co-op</strong><span>Our co-op. Our workspace.</span></div></div>',
                unsafe_allow_html=True,
            )
            ui.title("Unlock AP Statements")
            ui.markdown("Enter the finance team password to open your shared statement workspace.")
            with ui.form("ap_unlock", clear_on_submit=True):
                submitted = ui.text_input("Finance team password", type="password", key="_ap_password")
                clicked = ui.form_submit_button("Open AP Statements", type="primary", use_container_width=True)
            if ui.button("← Back to programs", key="ap_gate_back"):
                return True
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
                "Before leaving, save your changes and/or export your report. "
                "Unacknowledged edits are not saved. Shared originals and saved revisions remain available."
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
    # Stable during reruns; a fresh unlock mounts a fresh financial component.
    value = component_renderer(key=f'{_COMPONENT_KEY}_{authorization.session_nonce}',
                               shared_reply=ui.session_state.get('_ap_shared_reply'))
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
    elif type(value) is dict and 'version' in value:
        import hashlib
        import json
        from app.ap_shared.protocol import dispatch_request
        from app.ap_shared.models import validate_request, ApValidationError
        try:
            validate_request(value)
            fingerprint=hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
        except (ApValidationError,TypeError,ValueError):
            fingerprint='invalid'
        if fingerprint != ui.session_state.get('_ap_shared_last_request'):
            if service is None:
                try:
                    from app.ap_shared.repository import create_repository
                    from app.ap_shared.service import ApService
                    clock=lambda:datetime.now(timezone.utc)
                    service=ApService(create_repository(config),config,clock,
                        lambda:require_access(ui.session_state,config,clock()))
                except Exception:
                    service=None
            ui.session_state['_ap_shared_reply']=dispatch_request(value,ui.session_state,config,service,now)
            ui.session_state['_ap_shared_last_request']=fingerprint
            ui.rerun()
    ui.caption(
        "BILL API is disconnected. Comparisons use imported CSV records and "
        "depend on export coverage. This does not verify QuickBooks sync."
    )
    ui.caption(
        "Shared AP records and original PDFs are private. Save acknowledgements confirm storage; "
        "unsaved edits remain in this browser tab only. Reviewer initials are self-reported."
    )
    return False
