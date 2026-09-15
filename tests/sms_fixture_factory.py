from datetime import date

from app.sms_exports import SmsExport


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


def sms_exports_091426(omit=None, duplicate=None, coupon_date=None):
    """Return literal SMS exports for the 9/14/2026 accounting backtest."""
    report_date = date(2026, 9, 14)
    rows_by_role = {
        "sales": (
            ("Sub-department Single Total",),
            ("Date:", "09/14/2026", "to", "09/14/2026"),
            ("", "Sub-Department", "Qty", "Amount", "g/Weight"),
            (10, "Grocery", 1, "50000.00", "0.00"),
            (20, "Wellness", 1, "36502.80", "0.00"),
            ("Sales Total", "", "", "86502.80", ""),
        ),
        "coupons": (
            ("Sub-department Single Total",),
            ("Date:", "09/14/2026", "to", "09/14/2026"),
            ("", "Sub-Department", "Qty", "Amount", "g/Weight"),
            (10, "Grocery Coupon Distribution", 1, "31.69", "0.00"),
            (20, "Wellness Coupon Distribution", 1, "30.00", "0.00"),
            (3542, "Store Coupons", 1, "-1428.18", "0.00"),
            ("Coupon Distribution Total", "", "", "61.69", ""),
            ("Store Coupons Total", "", "", "-1428.18", ""),
        ),
        "discounts": (
            ("Discounts by Shopper Level",),
            ("Date:", "09/14/2026"),
            ("Shopper Level", "Description", "Discount"),
            (2, "Member Discount", "1200.00"),
            (3, "Senior Discount", "2781.21"),
            ("Discount Total", "", "3981.21"),
        ),
        "hash": (
            ("Sub-department Single Total",),
            ("Date:", "09/14/2026", "to", "09/14/2026"),
            ("", "Sub-Department", "Qty", "Amount", "g/Weight"),
            (23, "Refunded Discounts", 1, "4.89", "0.00"),
            (32, "Pass Through Donations", 1, "6.00", "0.00"),
            (34, "Paid In", 1, "12.00", "0.00"),
            ("HASH Detail Total", "", "", "22.89", ""),
        ),
        "bs": (
            ("Store Balance Sheet",),
            ("Date:", "09/14/2026"),
            ("Code", "Description", "Amount"),
            (910, "Milk Bottle Return", "8.00"),
        ),
        "milk_bottles": (
            ("Item Multi Totals by Sub-department",),
            ("Date:", "09/14/2026"),
            ("Item Description", "Net Sales"),
            ("Milk Bottle Returned - Glass", "20.00"),
            ("Milk Bottle Returned - Plastic", "32.00"),
            ("Milk Bottle Returned - Large", "6.00"),
            ("Milk Bottle Returned - Small", "16.00"),
            ("Store Coupon Promotion", "-1428.18"),
            ("Grand Total", "-1354.18"),
        ),
    }
    exports = []
    for role, rows in rows_by_role.items():
        if role == omit:
            continue
        export_date = coupon_date if role == "coupons" and coupon_date else report_date
        exports.append(
            SmsExport(
                role=role,
                filename=f"091426-{role}.xls",
                report_date=export_date,
                rows=rows,
            )
        )
    if duplicate:
        original = next(report for report in exports if report.role == duplicate)
        exports.append(
            SmsExport(
                role=original.role,
                filename=f"091426-duplicate-{duplicate}.xls",
                report_date=original.report_date,
                rows=original.rows,
            )
        )
    return tuple(exports)
