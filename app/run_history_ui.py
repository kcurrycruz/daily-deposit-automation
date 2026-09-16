from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from app.program_hub_ui import (
    SIDEBAR_COLLAPSE_REQUEST_KEY,
    render_all_programs_action,
)


def render_sidebar_collapse_request(component_html, state) -> bool:
    """Consume one program-entry request and collapse an expanded sidebar."""
    if not state.pop(SIDEBAR_COLLAPSE_REQUEST_KEY, False):
        return False
    component_html(
        """
        <script>
        const doc = window.parent.document;
        const collapseSidebar = () => {
          const collapseControl = doc.querySelector(
            '[data-testid="stSidebarCollapseButton"]'
          );
          if (!collapseControl) return false;

          const button = collapseControl.matches('button')
            ? collapseControl
            : collapseControl.querySelector('button');
          if (!button) return false;

          button.click();
          return true;
        };

        if (!collapseSidebar()) {
          const observer = new MutationObserver(() => {
            if (collapseSidebar()) observer.disconnect();
          });
          observer.observe(doc.body, { childList: true, subtree: true });
          window.setTimeout(() => observer.disconnect(), 3000);
        }
        </script>
        """,
        height=0,
        width=0,
    )
    return True


def render_daily_sidebar(
    ui,
    *,
    records: list[dict],
    option_labeler,
    run_time_formatter,
) -> bool:
    """Render Daily Deposit navigation followed by collapsed Run History."""
    ui.markdown("## 🌿 HWFC Daily Deposit")
    return_to_hub = render_all_programs_action(ui)
    render_run_history(
        ui,
        records=records,
        option_labeler=option_labeler,
        run_time_formatter=run_time_formatter,
    )
    return return_to_hub


def render_run_history(
    ui,
    *,
    records: list[dict],
    option_labeler,
    run_time_formatter,
) -> None:
    """Render Run History in a collapsed sidebar section."""
    with ui.expander("Run History", expanded=False):
        _render_run_history_content(
            ui,
            records=records,
            option_labeler=option_labeler,
            run_time_formatter=run_time_formatter,
        )


def _render_run_history_content(
    ui,
    *,
    records: list[dict],
    option_labeler,
    run_time_formatter,
) -> None:
    ui.caption("Prior deposit records")

    if not records:
        ui.caption("No completed runs yet.")
        return

    selectable_history = records[:25]
    history_ids = [
        record.get("id", str(index))
        for index, record in enumerate(selectable_history)
    ]
    history_by_id = dict(zip(history_ids, selectable_history))
    selected_history_id = ui.selectbox(
        "Prior deposit",
        options=history_ids,
        format_func=lambda record_id: option_labeler(history_by_id[record_id]),
        key="run_history_selection",
    )
    record = history_by_id[selected_history_id]

    try:
        report_label = datetime.fromisoformat(
            record.get("report_date", "")
        ).strftime("%m/%d/%Y")
    except Exception:
        report_label = record.get("report_date", "—") or "—"
    run_label = run_time_formatter(
        record.get("run_at", ""),
        include_date=True,
    )

    status_icon = "✓" if record.get("status") == "Passed" else "⚠"
    ui.markdown(
        f"**{status_icon} {html.escape(str(report_label))} · "
        f"{html.escape(str(record.get('status', '—')))}**"
    )
    ui.caption(f"Run {html.escape(str(run_label))}")

    history_checks = [
        ("Sales", record.get("sales_status", "N/A")),
        ("Discounts", record.get("discount_status", "N/A")),
        ("HASH", record.get("hash_status", "N/A")),
        ("IIF", record.get("iif_status", "N/A")),
        ("Card Settlement", record.get("card_settlement_status", "N/A")),
    ]
    status_text = []
    for label, status in history_checks:
        icon = "✓" if status == "MATCH" else ("⚠" if status == "REVIEW" else "—")
        status_text.append(f"{icon} {label}")
    ui.caption("  ·  ".join(status_text))

    ui.markdown("#### Run details")
    reporting_name = record.get(
        "reporting_workbook_filename",
        record.get("uploaded_filename", "—"),
    )
    ui.caption(
        f"Daily Reporting Workbook: {html.escape(str(reporting_name or '—'))}"
    )
    source_names = record.get("sms_source_filenames", [])
    if isinstance(source_names, list) and source_names:
        ui.caption(
            "SMS Sources: "
            + ", ".join(html.escape(str(name)) for name in source_names)
        )
    ui.caption(
        "Card Settlement: "
        f"{html.escape(str(record.get('settlement_filename') or '—'))}"
    )
    if record.get("date_mismatch"):
        ui.warning("This run had a workbook date mismatch warning.", icon="⚠️")

    ui.markdown("#### Files from this run")
    reporting_archive = (
        record.get(
            "archived_reporting_workbook",
            record.get("archived_upload"),
        )
        if record.get("status") == "Passed"
        else None
    )
    archived_files = [
        (
            "Download Daily Reporting Workbook",
            reporting_archive,
            reporting_name,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"history_upload_{selected_history_id}",
        ),
        (
            "Download Card Settlement",
            record.get("archived_settlement"),
            record.get("settlement_filename"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"history_settlement_{selected_history_id}",
        ),
        (
            "Download IIF",
            record.get("archived_iif"),
            record.get("iif_filename"),
            "text/plain",
            f"history_iif_{selected_history_id}",
        ),
    ]
    source_paths = record.get("archived_sms_sources", [])
    if isinstance(source_names, list) and isinstance(source_paths, list):
        archived_files.extend(
            (
                f"Download SMS Source {index}",
                source_path,
                source_name,
                "application/vnd.ms-excel",
                f"history_sms_{selected_history_id}_{index}",
            )
            for index, (source_name, source_path) in enumerate(
                zip(source_names, source_paths), start=1
            )
        )
    available_file = False
    for label, path_value, filename, mime, key in archived_files:
        if not path_value:
            continue
        path = Path(path_value)
        if not path.is_file():
            continue
        available_file = True
        ui.download_button(
            label,
            data=path.read_bytes(),
            file_name=filename or path.name,
            mime=mime,
            key=key,
            use_container_width=True,
        )
    if not available_file:
        ui.caption("Archived files are not available for this run.")
