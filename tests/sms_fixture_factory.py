from datetime import date


def sms_rows(role: str, report_date: date = date(2026, 9, 14)):
    """Return representative SMS export rows for one report role."""
    date_text = report_date.strftime("%m/%d/%Y")
    rows_by_role = {
        "sales": (
            ("Sub-department Single Total",),
            ("Date:", date_text, "to", date_text),
            ("S-Dept.", 0, "to", 999999),
            ("Tlz.:", 3, "to", 4),
            ("Target:", "RAL", "Report all"),
            ("", "Sub-Department", "Qty", "Amount", "g/Weight"),
            (6, "Ordinary Sales Department", 1, 100.0, 0.0),
        ),
        "coupons": (
            ("Sub-department Single Total",),
            ("Date:", date_text, "to", date_text),
            ("S-Dept.", 0, "to", 999999),
            ("Tlz.:", 3542, "to", 3542),
            ("Target:", "RAL", "Report all"),
            ("", "Sub-Department", "Qty", "Amount", "g/Weight"),
            (3542, "Store Coupons", 1, -12.5, 0.0),
        ),
        "discounts": (
            ("Discounts by Shopper Level",),
            (f"Date: {date_text}",),
            ("Shopper Level", "Discount"),
            ("Member", 12.5),
        ),
        "hash": (
            ("Sub-department Single Total",),
            ("Date:", date_text, "to", date_text),
            ("S-Dept.", 0, "to", 999999),
            ("Tlz.:", 6, "to", 6),
            ("Target:", "RAL", "Report all"),
            ("", "Sub-Department", "Qty", "Amount", "g/Weight"),
            (23, "Refunded Discounts", 1, -4.89, 0.0),
        ),
        "bs": (
            ("Store Balance Sheet",),
            (f"Date: {date_text}",),
            ("Code", "Description", "Amount"),
            (910, "Milk Bottle Return", 8.0),
        ),
        "milk_bottles": (
            ("Item Multi Totals by Sub-department",),
            ("Date:", date_text),
            ("Item", "Net Sales"),
            ("Milk Bottle Returned", 20.0),
        ),
    }
    try:
        return rows_by_role[role]
    except KeyError as error:
        raise ValueError(f"Unknown SMS fixture role: {role}") from error
