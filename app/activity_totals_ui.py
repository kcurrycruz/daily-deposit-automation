"""Read-only entry progress; never authorizes or changes accounting totals."""
import html
from decimal import Decimal, InvalidOperation


def _preview_money(value):
    try:
        if isinstance(value, bool):
            raise ValueError
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0:
            raise ValueError
        # Match activity_breakdowns._money rather than invent a preview policy.
        return amount.quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Entry totals require a finite, nonnegative amount.") from None


def activity_entry_summary(source_total, rows, *, pending_amount=0):
    """Count draft amounts even when their descriptions are still unfinished."""
    source = _preview_money(source_total)
    entered = sum((_preview_money(row["amount"]) for row in rows), Decimal("0.00"))
    entered += _preview_money(pending_amount)
    remaining = source - entered
    percent = float(min(Decimal(100), entered / source * 100)) if source else 0
    return {"source": source, "entered": entered, "remaining": remaining,
            "percent": percent,
            "status": "over" if remaining < 0 else "matched" if remaining == 0 else "remaining"}


def render_activity_totals(ui, *, title, source_label, source_total, rows, pending_amount=0):
    summary = activity_entry_summary(source_total, rows, pending_amount=pending_amount)
    status = summary["status"]
    difference_label = "Over report total" if status == "over" else "Remaining"
    status_label = {"over": "Over report total — review your entries",
                    "matched": "Totals match", "remaining": "Keep adding your items"}[status]
    values = (("Report total", summary["source"], "report"),
              ("Entered so far", summary["entered"], "entered"),
              (difference_label, abs(summary["remaining"]), "difference"))
    cells = "".join(
        f'<div class="hwfc-activity-total-cell {key}"><dt>{label}</dt>'
        f'<dd>${amount:,.2f}</dd></div>' for label, amount, key in values
    )
    ui.markdown(
        f'<section class="hwfc-activity-totals is-{status}" aria-label="{html.escape(title)} entry totals">'
        f'<div class="hwfc-activity-total-heading">{html.escape(title)} · Entry totals</div>'
        f'<div class="hwfc-activity-total-source">{html.escape(source_label)}</div>'
        f'<dl class="hwfc-activity-total-grid">{cells}</dl>'
        f'<div class="hwfc-activity-total-progress" role="progressbar" aria-label="Amount entered toward report total" '
        f'aria-valuemin="0" aria-valuemax="100" aria-valuenow="{summary["percent"]:.2f}">'
        f'<span style="width:{summary["percent"]:.2f}%"></span></div>'
        f'<div class="hwfc-activity-total-status">{status_label}</div>'
        '<div class="hwfc-activity-total-note">Includes amounts in unfinished items; not saved or approved.</div>'
        '</section>', unsafe_allow_html=True,
    )
