"""Read-only guided-step totals; no accounting, persistence, or approval effects."""
import html
from decimal import Decimal, InvalidOperation


def _money(value):
    try:
        if isinstance(value, bool):
            raise ValueError
        amount = Decimal(str(value))
        if not amount.is_finite():
            raise ValueError
        return amount.quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Step totals require a finite monetary amount.") from None


def entry_amount_total(rows, *, pending_amount=0):
    return sum((_money(row["amount"]) for row in rows), _money(pending_amount))


def step_total_summary(target_total, entered_total):
    target = _money(target_total)
    if target < 0:
        raise ValueError("Step target must be nonnegative.")
    if entered_total is None:
        return {"target": target, "entered": None, "remaining": None,
                "percent": 0, "status": "pending"}
    entered = _money(entered_total)
    remaining = target - entered
    percent = float(max(Decimal(0), min(Decimal(100), entered / target * 100))) if target else 0
    return {"target": target, "entered": entered, "remaining": remaining,
            "percent": percent, "status": "over" if remaining < 0 else "matched" if remaining == 0 else "remaining"}


def render_step_totals(ui, *, title, target_label, target_total, entered_label,
                       entered_total, reference_label=None, reference_total=None,
                       note="Includes draft amounts; not saved or approved."):
    summary = step_total_summary(target_total, entered_total)
    status = summary["status"]
    difference_label = "Over target" if status == "over" else "Remaining"
    status_label = {"pending": "Review required — run Review Closeout to calculate the deposit",
                    "matched": "Totals match", "remaining": "Amount still remaining",
                    "over": "Over target — review the difference"}[status]
    values = ((target_label, summary["target"], "report"),
              (entered_label, summary["entered"], "entered"),
              (difference_label, None if summary["remaining"] is None else abs(summary["remaining"]), "difference"))
    cells = "".join(
        f'<div class="hwfc-activity-total-cell {key}"><dt>{html.escape(label)}</dt>'
        f'<dd>{"—" if amount is None else ("-$" if amount < 0 else "$") + f"{abs(amount):,.2f}"}</dd></div>'
        for label, amount, key in values
    )
    reference = ""
    if reference_total is not None:
        reference_amount = _money(reference_total)
        difference = summary["target"] - reference_amount
        reference = (f'<div class="hwfc-activity-total-source">{html.escape(reference_label or "Reference total")}: '
                     f'${reference_amount:,.2f} · Target minus reference: '
                     f'{"+" if difference >= 0 else "-"}${abs(difference):,.2f}</div>')
    progress = "" if status == "pending" else (
        '<div class="hwfc-activity-total-progress" role="progressbar" '
        'aria-label="Amount toward step target" aria-valuemin="0" aria-valuemax="100" '
        f'aria-valuenow="{summary["percent"]:.2f}"><span style="width:{summary["percent"]:.2f}%"></span></div>'
    )
    ui.markdown(
        f'<section class="hwfc-activity-totals hwfc-step-totals is-{status}" aria-label="{html.escape(title)} entry totals">'
        f'<div class="hwfc-activity-total-heading">{html.escape(title)} · Entry totals</div>'
        f'<dl class="hwfc-activity-total-grid">{cells}</dl>{reference}{progress}'
        f'<div class="hwfc-activity-total-status">{status_label}</div>'
        f'<div class="hwfc-activity-total-note">{html.escape(note)}</div></section>',
        unsafe_allow_html=True,
    )
