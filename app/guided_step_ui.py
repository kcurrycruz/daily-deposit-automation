from app.ui_helpers import deposit_stepper_html


def render_deposit_step_panels(
    ui,
    rows,
    *,
    edit_key_prefix: str,
):
    """Render one bubble stepper and reserve the form slot beneath it."""
    rows = tuple(rows)
    edited_step = None
    ui.markdown(deposit_stepper_html(rows), unsafe_allow_html=True)
    edit_columns = ui.columns(len(rows))
    for edit_column, row in zip(edit_columns, rows):
        if row["complete"] and edit_column.button(
            "Edit",
            key=f"{edit_key_prefix}_{row['step']}",
        ):
            edited_step = row["step"]
    active_slot = ui.empty()
    return active_slot, edited_step
