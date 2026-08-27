from decimal import Decimal, InvalidOperation


def read_coupon_receivable_total(
    workbook_bytes: bytes,
    bs_sheet_name: str | None = None,
) -> float:
    from io import BytesIO

    import openpyxl

    workbook = openpyxl.load_workbook(
        BytesIO(workbook_bytes),
        read_only=True,
        data_only=True,
    )
    try:
        if bs_sheet_name:
            if bs_sheet_name not in workbook.sheetnames:
                raise ValueError(f"Balance Sheet tab '{bs_sheet_name}' was not found")
            sheet = workbook[bs_sheet_name]
        else:
            sheet_name = next(
                (
                    name for name in workbook.sheetnames
                    if name.casefold().endswith(" bs")
                    and "xxxxxx" not in name.casefold()
                ),
                None,
            )
            if sheet_name is None:
                raise ValueError("Balance Sheet tab was not found")
            sheet = workbook[sheet_name]

        for row in sheet.iter_rows(values_only=True):
            try:
                code = int(float(row[0]))
            except (TypeError, ValueError):
                continue
            if code != 908:
                continue
            try:
                amount = Decimal(str(row[4]))
                if not amount.is_finite():
                    raise InvalidOperation
                return float(abs(amount).quantize(Decimal("0.01")))
            except (IndexError, InvalidOperation, TypeError, ValueError):
                raise ValueError(
                    "Coupons Receivable (BS code 908) does not contain a valid amount"
                ) from None
        return 0.0
    finally:
        workbook.close()


def _money(value, label: str) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} must be a valid dollar amount") from None
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{label} must be zero or greater")
    return amount


def reconcile_coupon_receivable(
    bs_total: float,
    *,
    mode: str,
    closeout_actual_total: float | None = None,
    ncg_total: float | None = None,
    mfg_total: float | None = None,
) -> dict:
    bs_amount = abs(_money(bs_total, "BS Coupons Receivable total"))
    if mode == "quickbooks":
        return {
            "bs_total": float(bs_amount),
            "closeout_actual_total": None,
            "ncg_total": float(bs_amount),
            "mfg_total": None,
            "difference": None,
        }
    if mode != "closeout":
        raise ValueError("Coupon handling mode must be quickbooks or closeout")

    closeout_amount = _money(
        closeout_actual_total,
        "Closeout Sheet Coupon Actual Total",
    )
    ncg_amount = _money(ncg_total, "NCG Coupons")
    mfg_amount = _money(mfg_total, "MFG Coupons")
    counted_total = (ncg_amount + mfg_amount).quantize(Decimal("0.01"))
    if counted_total != closeout_amount:
        raise ValueError(
            f"NCG Coupons (${ncg_amount:.2f}) + MFG Coupons (${mfg_amount:.2f}) "
            "must equal Closeout Sheet Coupon Actual Total "
            f"(${closeout_amount:.2f})"
        )

    difference = (closeout_amount - bs_amount).quantize(Decimal("0.01"))
    return {
        "bs_total": float(bs_amount),
        "closeout_actual_total": float(closeout_amount),
        "ncg_total": float(ncg_amount),
        "mfg_total": float(mfg_amount),
        "difference": float(difference),
    }
