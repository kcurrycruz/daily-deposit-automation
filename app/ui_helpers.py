import html
from pathlib import Path


def workflow_heading_html(title: str, description: str) -> str:
    """Return safe, consistent markup for a deposit workflow heading."""
    return (
        '<div class="hwfc-workflow-heading">'
        f'<div class="hwfc-workflow-heading-title">{html.escape(str(title))}</div>'
        f'<div class="hwfc-workflow-heading-sub">{html.escape(str(description))}</div>'
        "</div>"
    )


def deposit_stepper_html(rows) -> str:
    """Render safe connected bubbles for the guided deposit workflow."""
    items = []
    for row in rows:
        number = int(row["number"])
        if row.get("complete"):
            state = "is-complete"
            bubble = "✓"
            bubble_label = "Completed"
        elif row.get("current"):
            state = "is-current"
            bubble = str(number)
            bubble_label = f"Current step {number}"
        else:
            state = "is-pending"
            bubble = str(number)
            bubble_label = f"Pending step {number}"
        items.append(
            f'<div class="hwfc-stepper-item {state}" role="listitem">'
            '<div class="hwfc-stepper-track">'
            f'<span class="hwfc-stepper-bubble" aria-label="{bubble_label}">'
            f"{bubble}</span>"
            "</div>"
            '<div class="hwfc-stepper-label">'
            f'<span>Step {number}</span>'
            f'<strong>{html.escape(str(row["label"]))}</strong>'
            "</div></div>"
        )
    return (
        '<div class="hwfc-deposit-stepper" role="list" '
        'aria-label="Today’s Deposit Steps">'
        f'{"".join(items)}</div>'
    )


def plan_guide_html(rows: list[dict]) -> str:
    """Render membership plan details as responsive, easy-to-scan cards."""
    cards = []
    for row in rows:
        plan = str(row["Plan"]).strip().replace(" year", "-Year").title()
        details = (
            ("Deposit", f'${float(row["Deposit"]):,.2f}'),
            ("Regular payment", f'${float(row["Installment"]):,.2f}'),
            ("Principal", f'${float(row["Principal"]):,.2f}'),
            ("Interest", f'${float(row["Interest"]):,.2f}'),
            ("Number of payments", str(int(row["Payments"]))),
            ("Total paid", f'${float(row["Total Paid"]):,.2f}'),
        )
        detail_rows = "".join(
            '<div class="hwfc-plan-card-row">'
            f"<span>{html.escape(label)}</span>"
            f"<strong>{html.escape(value)}</strong>"
            "</div>"
            for label, value in details
        )
        cards.append(
            '<div class="hwfc-plan-card">'
            f'<div class="hwfc-plan-card-title">{html.escape(plan)} Plan</div>'
            f"{detail_rows}"
            "</div>"
        )
    return f'<div class="hwfc-plan-guide-grid">{"".join(cards)}</div>'


def deposit_download_details(result: dict | None) -> dict | None:
    """Return browser-download data only for a complete generated IIF result."""
    if not isinstance(result, dict):
        return None
    data = result.get("iif_bytes")
    path = result.get("iif_path")
    if not isinstance(data, bytes) or not data or path is None:
        return None
    return {
        "file_name": Path(path).name,
        "data": data,
    }
