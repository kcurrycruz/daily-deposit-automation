"""Co-op presentation shared by the Daily workspace and its sidebar."""

from base64 import b64encode
from pathlib import Path


def render_daily_brand(ui, *, compact=False):
    logo = Path(__file__).with_name("assets") / "hwfc-logo-simplified.png"
    src = "data:image/png;base64," + b64encode(logo.read_bytes()).decode("ascii")
    note = "Daily Deposits" if compact else "Our co-op. Our workspace."
    ui.markdown(
        '<div class="hwfc-daily-brand">'
        f'<img src="{src}" alt="Honest Weight Food Co-op logo" width="52" height="52"/>'
        '<div><div class="hwfc-daily-brand-name">Honest Weight Food Co-op</div>'
        f'<div class="hwfc-daily-brand-note">{note}</div></div></div>',
        unsafe_allow_html=True,
    )


def render_daily_theme(ui):
    styles = Path(__file__).with_name("daily_workspace.css").read_text(encoding="utf-8")
    ui.markdown(
        f'<style>{styles}</style><span id="hwfc-daily-page" aria-hidden="true"></span>',
        unsafe_allow_html=True,
    )
    render_daily_brand(ui)
