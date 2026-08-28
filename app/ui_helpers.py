import html


def workflow_heading_html(title: str, description: str) -> str:
    """Return safe, consistent markup for a deposit workflow heading."""
    return (
        '<div class="hwfc-workflow-heading">'
        f'<div class="hwfc-workflow-heading-title">{html.escape(str(title))}</div>'
        f'<div class="hwfc-workflow-heading-sub">{html.escape(str(description))}</div>'
        "</div>"
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
