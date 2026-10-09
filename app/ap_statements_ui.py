"""Local AP component and navigation; no accounting data enters Python."""

from pathlib import Path

_EXIT_KEY = "_ap_exit_confirmation"
_COMPONENT_KEY = "hwfc_ap_statements_workspace"


def ap_frontend_path() -> Path:
    return Path(__file__).resolve().parent / "ap_statements" / "frontend"


def render_ap_statements(ui, *, component_renderer=None, frontend_path=None) -> bool:
    """Return True only after the user confirms leaving the AP workspace."""
    ui.title("AP Statements")
    ui.caption(
        "BILL API is disconnected. Sample matches are simulated; CSV matches "
        "depend on export coverage. This does not verify QuickBooks sync."
    )
    ui.caption(
        "Save session keeps extracted rows and notes in this browser profile, "
        "visible to others using it. Original PDFs are not saved: select your "
        "original PDFs again after leaving. Use Save session or export your "
        "report before switching programs."
    )
    if ui.button("← All Programs", key="ap_all_programs"):
        ui.session_state[_EXIT_KEY] = True
    if ui.session_state.get(_EXIT_KEY):
        ui.warning(
            "Before leaving, use Save session and/or export your report in the "
            "workspace below. Unsaved rows and notes will be lost; original "
            "PDFs must be selected again. Browser saving is not a backup."
        )
        if ui.button("Stay in AP Statements", key="ap_stay"):
            ui.session_state.pop(_EXIT_KEY, None)
        if ui.button("Leave for All Programs", key="ap_leave"):
            ui.session_state.pop(_EXIT_KEY, None)
            return True

    path = Path(frontend_path) if frontend_path is not None else ap_frontend_path()
    if not (path / "index.html").is_file():
        ui.error("AP component build is missing. Prepare the local frontend assets before deploying.")
        return False
    if component_renderer is None:
        import streamlit.components.v1 as components

        component_renderer = components.declare_component("hwfc_ap_statements", path=str(path))
    # Intentionally ignore the return value and send no financial props.
    component_renderer(key=_COMPONENT_KEY)
    return False
