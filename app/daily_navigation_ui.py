"""Daily-only confirmation; callers retain ownership of program navigation."""

from pathlib import Path

from app.program_hub_ui import render_all_programs_action

_CONFIRMED_KEY = "_daily_program_return_confirmed"


def render_daily_program_return(ui) -> bool:
    """Request departure only after confirmation, consuming it on a full rerun."""
    if ui.session_state.pop(_CONFIRMED_KEY, False):
        return True
    if not render_all_programs_action(ui):
        return False

    @ui.dialog("Go back to programs?", width="small")
    def confirm_return():
        def request_return():
            ui.session_state[_CONFIRMED_KEY] = True

        styles = Path(__file__).with_name("daily_return_dialog.css").read_text(encoding="utf-8")
        ui.markdown(
            f'<style>{styles}</style><span id="hwfc-daily-return-dialog" aria-hidden="true"></span>',
            unsafe_allow_html=True,
        )
        ui.markdown("Your current deposit work will be kept while you switch programs.")
        ui.caption(
            "Continue where you left off in this session. Use Save draft for a copy "
            "you can resume later; this session is not a backup."
        )
        cancel, confirm = ui.columns(2)
        with cancel:
            if ui.button("Cancel", key="daily_return_cancel", use_container_width=True):
                ui.rerun()
        with confirm:
            if ui.button("Go back to programs", key="daily_return_confirm", type="primary", use_container_width=True, on_click=request_return):
                ui.rerun()

    confirm_return()
    return False
