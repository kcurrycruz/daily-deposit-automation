import html
from pathlib import Path
import re


def parse_engine_status_summary(log_text: str) -> dict:
    """Read authoritative pass controls from the engine's concise status file."""
    def amount(label: str):
        match = re.search(
            rf"^\s*{label}:\s*[^\r\n]*?\$([0-9,]+(?:\.[0-9]+)?)",
            log_text or "",
            flags=re.IGNORECASE | re.MULTILINE,
        )
        return float(match.group(1).replace(",", "")) if match else None

    return {
        "sales": amount("SALES"),
        "discounts": amount("DISCOUNTS"),
        "hash_sales": amount("HASH SALES"),
        "all_ok": bool(
            re.search(r"ALL\s+CHECKS\s+PASSED", log_text or "", re.IGNORECASE)
        ),
    }


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
    """Return generated downloads when the IIF is structurally balanced."""
    if not isinstance(result, dict):
        return None
    validation = result.get("validation")
    if not isinstance(validation, dict):
        return None
    iif_ok = validation.get("iif_ok", validation.get("all_ok"))
    if iif_ok is not True:
        return None
    iif_data = result.get("iif_bytes")
    iif_path = result.get("iif_path")
    report_data = result.get("reporting_workbook_bytes")
    report_name = result.get("reporting_workbook_name")
    if (
        not isinstance(iif_data, bytes)
        or not iif_data
        or iif_path is None
        or not isinstance(report_data, bytes)
        or not report_data
        or not isinstance(report_name, str)
        or not report_name.strip()
    ):
        return None
    return {
        "iif": {
            "file_name": Path(iif_path).name,
            "data": iif_data,
        },
        "report": {
            "file_name": Path(report_name).name,
            "data": report_data,
        },
    }


def deposit_download_status(result: dict | None) -> dict | None:
    """Describe final-download readiness without exposing engine details."""
    if not isinstance(result, dict):
        return None
    validation = result.get("validation")
    if not isinstance(validation, dict):
        return {
            "kind": "error",
            "message": "Downloads are not ready because validation is incomplete.",
        }
    iif_ok = validation.get("iif_ok", validation.get("all_ok"))
    if iif_ok is not True:
        return {
            "kind": "error",
            "message": (
                "Downloads are not ready because the QuickBooks IIF is not "
                "balanced. Review the validation results below."
            ),
        }
    if deposit_download_details(result) is None:
        return {
            "kind": "error",
            "message": (
                "Downloads are not ready because one or more files could not be "
                "generated. Select Validate & Prepare IIF again."
            ),
        }
    if validation.get("all_ok") is True:
        return {
            "kind": "success",
            "message": "Both files are ready to download.",
        }
    return {
        "kind": "warning",
        "message": (
            "Both files are ready. Review the highlighted warnings "
            "before importing into QuickBooks."
        ),
    }


def tba_quickbooks_rows(result: dict | None) -> list[dict[str, str]]:
    """Show posted TBA splits using QuickBooks deposit amount signs."""
    if not isinstance(result, dict):
        return []
    rows = []
    for line in result.get("lines") or []:
        account = str(line.account or "")
        if (
            line.line_type != "SPL"
            or account.split("·", 1)[0].strip() != "4444"
            or line.amount is None
        ):
            continue
        quickbooks_amount = -float(line.amount)
        formatted_amount = (
            f"-${abs(quickbooks_amount):,.2f}"
            if quickbooks_amount < 0
            else f"${quickbooks_amount:,.2f}"
        )
        rows.append({
            "Account": account,
            "Memo": str(line.memo or ""),
            "Class": str(line.qb_class or ""),
            "Amount": formatted_amount,
        })
    return rows
