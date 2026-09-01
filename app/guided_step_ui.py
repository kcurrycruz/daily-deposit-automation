from app.ui_helpers import deposit_step_card_html


def render_deposit_step_panels(
    ui,
    rows,
    *,
    edit_key_prefix: str,
):
    """Render compressed step cards and reserve an inline slot for the current step."""
    active_slot = None
    edited_step = None
    for row in rows:
        with ui.container():
            card_col, action_col = ui.columns(
                [6, 1],
                vertical_alignment="center",
            )
            card_col.markdown(
                deposit_step_card_html(row),
                unsafe_allow_html=True,
            )
            if row["complete"] and action_col.button(
                "Edit",
                key=f"{edit_key_prefix}_{row['step']}",
            ):
                edited_step = row["step"]
            if row["current"]:
                active_slot = ui.empty()
    return active_slot, edited_step
