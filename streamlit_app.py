"""
HWFC Daily Deposit - Streamlit UI
Honest Weight Food Co-op

Drop-in replacement for streamlit_app.py.

Goals:
- Warm Honest Weight / grocery co-op visual identity
- Keep the existing deposit calculation engine as the source of truth
- Show a full post-run reconciliation:
  * Sales
  * Discounts
  * Balance Sheet / tender lines
  * HASH checks
  * IIF debit / credit balance
  * Full QuickBooks IIF preview
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st


# ---------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
ENGINE_PATH = ROOT / "pos_to_quickbooks_v2.py"
INPUT_DIR = ROOT / "input" / "daily_reports"
QB_IMPORT_DIR = ROOT / "output" / "qb_imports"
LOG_DIR = ROOT / "logs"

for folder in (INPUT_DIR, QB_IMPORT_DIR, LOG_DIR):
    folder.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------
# Page / brand
# ---------------------------------------------------------------------

st.set_page_config(
    page_title="HWFC Daily Deposit",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    :root {
        --hwfc-cream: #F6F1E7;
        --hwfc-paper: #FFFDF8;
        --hwfc-forest: #2F5233;
        --hwfc-leaf: #5F7E4A;
        --hwfc-sage: #DDE7D5;
        --hwfc-gold: #C7952B;
        --hwfc-clay: #A95F3B;
        --hwfc-brown: #5D4938;
        --hwfc-ink: #2C3028;
        --hwfc-muted: #6F756A;
        --hwfc-green-soft: #E8F1E3;
        --hwfc-red-soft: #F8E8E3;
        --hwfc-yellow-soft: #FAF2D6;
        --hwfc-border: #DDD5C7;
    }

    .stApp {
        background:
            radial-gradient(circle at 8% 4%, rgba(95,126,74,.10), transparent 22rem),
            linear-gradient(180deg, #F8F4EC 0%, #F3EEE4 100%);
        color: var(--hwfc-ink);
    }

    .block-container {
        max-width: 1180px;
        padding-top: 2rem;
        padding-bottom: 4rem;
    }

    h1, h2, h3 {
        color: var(--hwfc-forest);
        letter-spacing: -0.02em;
    }

    .hwfc-hero {
        background:
            linear-gradient(120deg, rgba(47,82,51,.97), rgba(68,101,57,.96)),
            #2F5233;
        border: 1px solid rgba(255,255,255,.10);
        border-radius: 22px;
        padding: 26px 30px;
        box-shadow: 0 14px 34px rgba(54, 65, 43, .14);
        margin-bottom: 18px;
        position: relative;
        overflow: hidden;
    }

    .hwfc-hero:after {
        content: "🌿";
        position: absolute;
        right: 28px;
        top: 8px;
        font-size: 82px;
        opacity: .11;
        transform: rotate(-12deg);
    }

    .hwfc-kicker {
        color: #DDE7D5;
        font-size: .78rem;
        font-weight: 800;
        letter-spacing: .16em;
        text-transform: uppercase;
        margin-bottom: 6px;
    }

    .hwfc-title {
        color: #FFFDF8;
        font-family: Georgia, 'Times New Roman', serif;
        font-size: 2.15rem;
        font-weight: 700;
        line-height: 1.08;
        margin: 0;
    }

    .hwfc-subtitle {
        color: #E9EEE3;
        margin-top: 8px;
        font-size: .98rem;
    }

    .hwfc-stepbar {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 8px;
        margin: 16px 0 22px;
    }

    .hwfc-step {
        border: 1px solid var(--hwfc-border);
        border-radius: 999px;
        background: rgba(255,253,248,.88);
        padding: 9px 12px;
        text-align: center;
        color: var(--hwfc-brown);
        font-size: .82rem;
        font-weight: 700;
    }

    .hwfc-step.active {
        color: white;
        background: var(--hwfc-forest);
        border-color: var(--hwfc-forest);
    }

    .hwfc-section-label {
        font-size: .75rem;
        color: var(--hwfc-muted);
        font-weight: 800;
        letter-spacing: .12em;
        text-transform: uppercase;
        margin: 8px 0 6px;
    }

    .hwfc-result {
        border-radius: 18px;
        padding: 18px 20px;
        margin: 8px 0 18px;
        border: 1px solid;
    }

    .hwfc-result.good {
        background: var(--hwfc-green-soft);
        border-color: #B9CFAE;
    }

    .hwfc-result.warn {
        background: var(--hwfc-yellow-soft);
        border-color: #E2CC80;
    }

    .hwfc-result.bad {
        background: var(--hwfc-red-soft);
        border-color: #DCAFA0;
    }

    .hwfc-result-title {
        font-size: 1.18rem;
        font-weight: 850;
        margin-bottom: 2px;
        color: var(--hwfc-forest);
    }

    .hwfc-result-sub {
        color: var(--hwfc-muted);
        font-size: .92rem;
    }

    .hwfc-card {
        background: rgba(255,253,248,.92);
        border: 1px solid var(--hwfc-border);
        border-radius: 16px;
        padding: 16px 18px;
        min-height: 118px;
        box-shadow: 0 6px 18px rgba(78, 66, 48, .06);
    }

    .hwfc-card-label {
        font-size: .72rem;
        font-weight: 800;
        letter-spacing: .11em;
        text-transform: uppercase;
        color: var(--hwfc-muted);
        margin-bottom: 8px;
    }

    .hwfc-card-value {
        font-family: Georgia, 'Times New Roman', serif;
        font-size: 1.58rem;
        font-weight: 700;
        color: var(--hwfc-forest);
        line-height: 1.05;
    }

    .hwfc-card-foot {
        color: var(--hwfc-muted);
        font-size: .80rem;
        margin-top: 7px;
    }

    .hwfc-match {
        font-weight: 800;
        color: #3E713D;
    }

    .hwfc-mismatch {
        font-weight: 800;
        color: #A34A32;
    }

    .hwfc-equation {
        padding: 16px 18px;
        border-radius: 14px;
        background: #F1EADC;
        border: 1px solid #D9CDB8;
        font-family: Georgia, 'Times New Roman', serif;
        color: var(--hwfc-brown);
        margin: 10px 0 14px;
    }

    .hwfc-footer {
        margin-top: 32px;
        padding-top: 14px;
        border-top: 1px solid var(--hwfc-border);
        color: var(--hwfc-muted);
        font-size: .8rem;
    }

    div[data-testid="stFileUploader"] {
        background: rgba(255,253,248,.82);
        border: 1px dashed #B7AA94;
        border-radius: 14px;
        padding: 4px 12px;
    }

    div[data-testid="stDateInput"] > div,
    div[data-testid="stFileUploader"] section {
        border-radius: 12px;
    }

    .stButton > button,
    .stDownloadButton > button {
        border-radius: 12px !important;
        font-weight: 800 !important;
        min-height: 44px;
    }

    .stButton > button[kind="primary"] {
        background: var(--hwfc-forest) !important;
        border-color: var(--hwfc-forest) !important;
        color: white !important;
    }

    .stDownloadButton > button {
        background: var(--hwfc-forest) !important;
        border-color: var(--hwfc-forest) !important;
        color: white !important;
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid var(--hwfc-border);
        border-radius: 12px;
        overflow: hidden;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 10px 10px 0 0;
        padding-left: 14px;
        padding-right: 14px;
        font-weight: 750;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

MONEY_RE = r"-?\$?\s*[\(\-]?\s*[\d,]+(?:\.\d{1,2})?\s*\)?"

DISCOUNT_PREFIXES = (
    "8511",
    "8512",
    "8140",
    "8423",
)

TENDER_KEYWORDS = (
    "cash",
    "check",
    "visa",
    "master",
    "amex",
    "american express",
    "discover",
    "debit",
    "ebt",
    "food stamp",
    "snap",
    "gift card",
    "credit card",
)

BALANCE_SHEET_KEYWORDS = (
    "sales tax",
    "bottle",
    "charity",
    "donation",
    "prepaid",
    "coupon",
    "member share",
    "receivable",
    "paid in",
    "paid-in",
    "cash over",
    "cash short",
    "penny",
    "nickel",
    "dufb",
    "double up",
    "outreach",
)


def money(value: Optional[float]) -> str:
    if value is None:
        return "—"
    value = float(value)
    if value < 0:
        return f"(${abs(value):,.2f})"
    return f"${value:,.2f}"


def abs_money(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"${abs(float(value)):,.2f}"


def parse_money(text: str) -> Optional[float]:
    if not text:
        return None
    s = str(text).strip().replace("$", "").replace(",", "").replace(" ", "")
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    try:
        v = float(s)
    except ValueError:
        return None
    return -abs(v) if neg else v


def last_amount_after_label(log_text: str, labels: list[str]) -> Optional[float]:
    for label in labels:
        matches = re.findall(
            rf"{re.escape(label)}\s*:?\s*({MONEY_RE})",
            log_text,
            flags=re.IGNORECASE,
        )
        if matches:
            return parse_money(matches[-1])
    return None


def section_status(log_text: str, section_name: str) -> Optional[bool]:
    upper = log_text.upper()
    start = upper.rfind(section_name.upper())
    if start < 0:
        return None
    chunk = upper[start : start + 1600]
    if "MISMATCH" in chunk or "FAILED" in chunk or "ERROR" in chunk:
        return False
    if "MATCH" in chunk or "OK TO IMPORT" in chunk:
        return True
    return None


def detect_sheet_roles(upload_bytes: bytes) -> dict[str, Optional[str]]:
    """
    Lightweight content-based sheet detector used only for the UI checklist.
    The accounting engine remains the source of truth for the actual run.
    """
    try:
        from io import BytesIO
        import openpyxl

        wb = openpyxl.load_workbook(BytesIO(upload_bytes), read_only=True, data_only=True)
        previews = {}
        for name in wb.sheetnames:
            ws = wb[name]
            parts = []
            for row in ws.iter_rows(
                min_row=1,
                max_row=min(ws.max_row, 30),
                values_only=True,
            ):
                parts.extend(str(v).strip() for v in row if v is not None)
            previews[name] = " ".join(parts).lower()

        detected = {"sales": None, "discounts": None, "bs": None, "hash": None}

        for name, preview in previews.items():
            markers = ("subdept sales report", "sub-department", "sub department", "subdept")
            if sum(m in preview for m in markers) >= 2:
                detected["sales"] = name
                break

        for name, preview in previews.items():
            if name == detected["sales"]:
                continue
            markers = ("member discounts", "shopper level", "discounts by shopper level", "senior", "owner")
            if (
                "member discounts" in preview
                or "discounts by shopper level" in preview
                or sum(m in preview for m in markers) >= 3
            ):
                detected["discounts"] = name
                break

        for name, preview in previews.items():
            if name in detected.values():
                continue
            markers = ("refunded discounts", "pass through donations", "paid-ins", "paid ins")
            if sum(m in preview for m in markers) >= 2:
                detected["hash"] = name
                break

        for name, preview in previews.items():
            if name in detected.values():
                continue
            markers = (
                "taxes",
                "sales tax",
                "charity",
                "visa",
                "mastercard",
                "amex",
                "discover",
                "debit",
                "cash",
                "bottle",
                "nickel round",
                "prepaid",
            )
            if sum(m in preview for m in markers) >= 4:
                detected["bs"] = name
                break

        for name in wb.sheetnames:
            low = name.lower()
            if detected["discounts"] is None and "discount" in low:
                detected["discounts"] = name
            if detected["hash"] is None and "hash" in low:
                detected["hash"] = name
            if detected["bs"] is None and (" bs" in f" {low}" or "balance" in low):
                detected["bs"] = name
            if detected["sales"] is None and ("subdept" in low or "sales report" in low):
                detected["sales"] = name

        return detected
    except Exception:
        return {"sales": None, "discounts": None, "bs": None, "hash": None}


@dataclass
class IIFLine:
    line_type: str
    trns_type: str
    date: str
    account: str
    name: str
    amount: Optional[float]
    memo: str
    qb_class: str


def parse_iif(path: Path) -> tuple[list[IIFLine], pd.DataFrame]:
    lines: list[IIFLine] = []
    headers: dict[str, list[str]] = {}

    with path.open("r", encoding="utf-8-sig", errors="replace") as f:
        for raw in f:
            row = raw.rstrip("\n\r").split("\t")
            if not row:
                continue

            first = row[0].strip()

            if first.startswith("!"):
                headers[first[1:].upper()] = [x.strip().upper() for x in row]
                continue

            line_type = first.upper()
            if line_type not in {"TRNS", "SPL"}:
                continue

            header = headers.get(line_type)
            data = {}

            if header and len(header) == len(row):
                for key, val in zip(header, row):
                    data[key.lstrip("!")] = val
                trns_type = data.get("TRNSTYPE", "")
                dt = data.get("DATE", "")
                account = data.get("ACCNT", "")
                name = data.get("NAME", "")
                amount = parse_money(data.get("AMOUNT", ""))
                memo = data.get("MEMO", "")
                qb_class = data.get("CLASS", "")
            else:
                trns_type = row[1].strip() if len(row) > 1 else ""
                dt = row[2].strip() if len(row) > 2 else ""
                account = row[3].strip() if len(row) > 3 else ""
                name = row[4].strip() if len(row) > 4 else ""
                amount = parse_money(row[5]) if len(row) > 5 else None
                memo = row[6].strip() if len(row) > 6 else ""
                qb_class = row[7].strip() if len(row) > 7 else ""

            lines.append(
                IIFLine(
                    line_type=line_type,
                    trns_type=trns_type,
                    date=dt,
                    account=account,
                    name=name,
                    amount=amount,
                    memo=memo,
                    qb_class=qb_class,
                )
            )

    df = pd.DataFrame(
        [
            {
                "Type": x.line_type,
                "Account": x.account,
                "Memo": x.memo,
                "Amount": x.amount,
                "Name": x.name,
                "Class": x.qb_class,
            }
            for x in lines
        ]
    )
    return lines, df


def account_code(account: str) -> str:
    m = re.match(r"\s*(\d+)", account or "")
    return m.group(1) if m else ""


def classify_line(line: IIFLine) -> str:
    acct = (line.account or "").lower()
    memo = (line.memo or "").lower()
    code = account_code(line.account)

    if line.line_type == "TRNS":
        return "Deposit"

    if code.startswith("711"):
        return "Sales"

    if code.startswith(DISCOUNT_PREFIXES):
        return "Discounts"

    if code == "8515000" or "store coupon" in memo:
        return "Store Coupons"

    combined = f"{acct} {memo}"
    if any(k in combined for k in TENDER_KEYWORDS):
        return "Tenders"

    if any(k in combined for k in BALANCE_SHEET_KEYWORDS):
        return "Balance Sheet"

    return "Other"


def build_detail_df(lines: list[IIFLine], categories: set[str]) -> pd.DataFrame:
    rows = []
    for x in lines:
        cat = classify_line(x)
        if cat not in categories:
            continue
        if x.amount is None and not x.memo and not x.account:
            continue
        rows.append(
            {
                "Category": cat,
                "Account": x.account,
                "Memo": x.memo or "—",
                "Amount": x.amount,
            }
        )
    return pd.DataFrame(rows)


def parse_validation(log_text: str, lines: list[IIFLine]) -> dict:
    sales_ok = section_status(log_text, "SALES CHECK")
    discounts_ok = section_status(log_text, "DISCOUNTS CHECK")
    hash_ok = section_status(log_text, "HASH SALES")

    gross_sales = last_amount_after_label(log_text, ["Gross Sales"])
    store_coupons = last_amount_after_label(log_text, ["Store Coupons"])
    owner_apprec = last_amount_after_label(log_text, ["Owner Apprec", "Owner Appreciation"])
    milk_bottle = last_amount_after_label(log_text, ["Milk Btl", "Milk Bottle Returns", "Milk Bottle Return"])
    script_net = last_amount_after_label(log_text, ["Script Net", "Script Net Sales"])
    excel_sales = last_amount_after_label(log_text, ["Excel Sales", "Excel Sales Total"])

    script_discounts = last_amount_after_label(log_text, ["Script Discounts"])
    excel_discounts = last_amount_after_label(log_text, ["Excel Disc Total", "Excel Discount Total"])

    refunded = last_amount_after_label(log_text, ["Refunded Discounts"])
    pass_through = last_amount_after_label(log_text, ["Pass Thru Donations", "Pass Through Donations"])
    hash_script = last_amount_after_label(log_text, ["Script Total"])
    hash_excel = last_amount_after_label(log_text, ["Hash Sales 6 Total", "HASH Sales 6 Total"])

    trns_amounts = [x.amount for x in lines if x.line_type == "TRNS" and x.amount is not None]
    deposit_total = sum(trns_amounts) if trns_amounts else None

    positive = round(sum(x.amount for x in lines if x.amount is not None and x.amount > 0), 2)
    negative = round(abs(sum(x.amount for x in lines if x.amount is not None and x.amount < 0)), 2)
    iif_difference = round(abs(positive - negative), 2)
    iif_ok = iif_difference < 0.02

    warning_count = sum(
        1
        for ln in log_text.splitlines()
        if "WARNING" in ln.upper() or "MISMATCH" in ln.upper() or "FAILED" in ln.upper()
    )

    checks = [x for x in (sales_ok, discounts_ok, hash_ok, iif_ok) if x is not None]
    all_ok = bool(checks) and all(checks)

    return {
        "sales_ok": sales_ok,
        "discounts_ok": discounts_ok,
        "hash_ok": hash_ok,
        "iif_ok": iif_ok,
        "all_ok": all_ok,
        "warning_count": warning_count,
        "gross_sales": gross_sales,
        "store_coupons": store_coupons,
        "owner_apprec": owner_apprec,
        "milk_bottle": milk_bottle,
        "script_net": script_net,
        "excel_sales": excel_sales,
        "script_discounts": script_discounts,
        "excel_discounts": excel_discounts,
        "refunded": refunded,
        "pass_through": pass_through,
        "hash_script": hash_script,
        "hash_excel": hash_excel,
        "deposit_total": deposit_total,
        "positive_total": positive,
        "negative_total": negative,
        "iif_difference": iif_difference,
    }


def run_engine(uploaded_file, deposit_date: date) -> dict:
    if not ENGINE_PATH.exists():
        raise FileNotFoundError(
            f"Deposit engine not found at {ENGINE_PATH.name}. "
            "Keep streamlit_app.py beside pos_to_quickbooks_v2.py."
        )

    ext = Path(uploaded_file.name).suffix.lower()
    if ext not in {".xlsx", ".xlsm"}:
        raise ValueError("Please upload an .xlsx or .xlsm workbook.")

    # Give the engine a date-explicit filename so it doesn't depend on the
    # user's local workbook naming convention.
    safe_name = f"SubDept Single Total Report {deposit_date.strftime('%m-%d-%y')}{ext}"
    input_path = INPUT_DIR / safe_name
    input_path.write_bytes(uploaded_file.getvalue())

    expected_iif = QB_IMPORT_DIR / f"deposit_{deposit_date.strftime('%Y%m%d')}.iif"
    if expected_iif.exists():
        expected_iif.unlink()

    cmd = [
        sys.executable,
        str(ENGINE_PATH),
        "--date",
        deposit_date.strftime("%m/%d/%y"),
    ]

    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )

    log_text = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")

    # Some versions write the status separately; append it for easier parsing.
    status_candidates = [
        LOG_DIR / "last_run_status.txt",
        QB_IMPORT_DIR / "last_run_status.txt",
    ]
    for status_path in status_candidates:
        if status_path.exists():
            try:
                status_text = status_path.read_text(encoding="utf-8", errors="replace")
                if status_text.strip():
                    log_text += "\n\n--- STATUS SUMMARY ---\n" + status_text
            except Exception:
                pass
            break

    if proc.returncode != 0:
        raise RuntimeError(log_text.strip() or f"Deposit engine exited with code {proc.returncode}.")

    if not expected_iif.exists():
        candidates = sorted(
            QB_IMPORT_DIR.glob("deposit_*.iif"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            expected_iif = candidates[0]

    if not expected_iif.exists():
        raise RuntimeError(
            "The automation finished, but no IIF file was found in output/qb_imports.\n\n"
            + log_text[-4000:]
        )

    lines, iif_df = parse_iif(expected_iif)
    validation = parse_validation(log_text, lines)

    return {
        "input_path": input_path,
        "iif_path": expected_iif,
        "iif_bytes": expected_iif.read_bytes(),
        "lines": lines,
        "iif_df": iif_df,
        "validation": validation,
        "log_text": log_text,
    }


def card(label: str, value: str, foot: str = ""):
    st.markdown(
        f"""
        <div class="hwfc-card">
          <div class="hwfc-card-label">{html.escape(label)}</div>
          <div class="hwfc-card-value">{html.escape(value)}</div>
          <div class="hwfc-card-foot">{foot}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_word(value: Optional[bool]) -> str:
    if value is True:
        return '<span class="hwfc-match">✓ MATCH</span>'
    if value is False:
        return '<span class="hwfc-mismatch">✕ REVIEW</span>'
    return '<span style="color:#777">—</span>'


# ---------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------

st.markdown(
    """
    <div class="hwfc-hero">
      <div class="hwfc-kicker">Honest Weight Food Co-op · Finance</div>
      <div class="hwfc-title">Daily Deposit Reconciliation</div>
      <div class="hwfc-subtitle">
        Upload the completed daily workbook, validate the full deposit, then review the QuickBooks entry before import.
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

has_results = "run_result" in st.session_state

st.markdown(
    f"""
    <div class="hwfc-stepbar">
      <div class="hwfc-step {'active' if not has_results else ''}">1 · Upload</div>
      <div class="hwfc-step {'active' if not has_results else ''}">2 · Validate</div>
      <div class="hwfc-step {'active' if has_results else ''}">3 · Review</div>
      <div class="hwfc-step {'active' if has_results else ''}">4 · Download</div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------
# Input area
# ---------------------------------------------------------------------

left, right = st.columns([0.34, 0.66], gap="large")

with left:
    st.markdown('<div class="hwfc-section-label">Deposit setup</div>', unsafe_allow_html=True)

    default_date = date.today() - timedelta(days=1)
    deposit_date = st.date_input(
        "Deposit date",
        value=default_date,
        format="MM/DD/YYYY",
    )

with right:
    st.markdown('<div class="hwfc-section-label">Daily workbook</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader(
        "Upload completed SubDept workbook",
        type=["xlsx", "xlsm"],
        label_visibility="collapsed",
        help="Workbook should contain Sales, Discounts, BS, and HASH data.",
    )

if uploaded:
    roles = detect_sheet_roles(uploaded.getvalue())

    with st.expander("Workbook checklist", expanded=True):
        cols = st.columns(4)
        labels = [
            ("Sales", roles["sales"]),
            ("Discounts", roles["discounts"]),
            ("Balance Sheet", roles["bs"]),
            ("HASH", roles["hash"]),
        ]
        for col, (label, sheet_name) in zip(cols, labels):
            with col:
                if sheet_name:
                    st.success(f"{label}\n\n{sheet_name}", icon="✅")
                else:
                    st.warning(f"{label}\n\nNot detected", icon="⚠️")

    missing_roles = [k for k, v in roles.items() if not v]
else:
    missing_roles = []

run_clicked = st.button(
    "🌿  Validate & Build Deposit",
    type="primary",
    use_container_width=True,
    disabled=uploaded is None,
)

if run_clicked:
    try:
        with st.spinner("Reading workbook, running deposit automation, and reconciling QuickBooks lines..."):
            result = run_engine(uploaded, deposit_date)
            st.session_state["run_result"] = result
            st.session_state["run_date"] = deposit_date
            st.session_state["run_filename"] = uploaded.name
        st.rerun()
    except Exception as exc:
        st.error("The deposit could not be completed.")
        st.code(str(exc), language="text")


# ---------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------

if "run_result" in st.session_state:
    result = st.session_state["run_result"]
    v = result["validation"]
    lines = result["lines"]
    iif_df = result["iif_df"]
    run_date = st.session_state.get("run_date", deposit_date)

    st.markdown("---")

    if v["all_ok"]:
        result_class = "good"
        title = "🟢 Deposit balanced"
        sub = "Core reconciliation checks passed. Review the detail below, then download the IIF."
    elif v["warning_count"] > 0:
        result_class = "warn"
        title = "🟡 Deposit needs review"
        sub = "The file was generated, but one or more checks or warnings need attention before QuickBooks import."
    else:
        result_class = "bad"
        title = "🔴 Deposit does not fully reconcile"
        sub = "Review the validation differences below before importing the IIF."

    st.markdown(
        f"""
        <div class="hwfc-result {result_class}">
          <div class="hwfc-result-title">{title}</div>
          <div class="hwfc-result-sub">
            {run_date.strftime('%A, %B %d, %Y')} · {html.escape(st.session_state.get('run_filename', 'Uploaded workbook'))}
          </div>
          <div class="hwfc-result-sub" style="margin-top:5px">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Summary cards
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        card(
            "Gross sales",
            abs_money(v["gross_sales"]),
            status_word(v["sales_ok"]),
        )
    with c2:
        card(
            "Discounts",
            abs_money(v["script_discounts"]),
            status_word(v["discounts_ok"]),
        )
    with c3:
        card(
            "Net sales",
            abs_money(v["script_net"]),
            status_word(v["sales_ok"]),
        )
    with c4:
        card(
            "Deposit total",
            abs_money(v["deposit_total"]),
            "QuickBooks TRNS amount",
        )

    c5, c6, c7, c8 = st.columns(4)
    with c5:
        card(
            "Excel sales total",
            abs_money(v["excel_sales"]),
            "Workbook J3 comparison",
        )
    with c6:
        card(
            "Excel discount total",
            abs_money(v["excel_discounts"]),
            "Workbook discount report",
        )
    with c7:
        card(
            "HASH Sales 6",
            abs_money(v["hash_excel"]),
            status_word(v["hash_ok"]),
        )
    with c8:
        card(
            "IIF difference",
            money(v["iif_difference"]),
            status_word(v["iif_ok"]),
        )

    # Reconciliation line
    if v["script_net"] is not None and v["excel_sales"] is not None:
        sales_diff = round(abs(abs(v["script_net"]) - abs(v["excel_sales"])), 2)
        st.markdown(
            f"""
            <div class="hwfc-equation">
              <strong>Sales reconciliation:</strong>
              Script Net Sales {abs_money(v['script_net'])}
              &nbsp; vs. &nbsp;
              Excel Sales {abs_money(v['excel_sales'])}
              &nbsp; → &nbsp;
              <strong>Difference {money(sales_diff)}</strong>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Validation checklist
    st.subheader("Validation checks")
    validation_rows = [
        {
            "Check": "Sales total",
            "Source / comparison": "Script Net Sales vs Excel Sales Total",
            "Status": "MATCH" if v["sales_ok"] else ("REVIEW" if v["sales_ok"] is False else "N/A"),
        },
        {
            "Check": "Discount total",
            "Source / comparison": "Script Discounts vs Excel Discount Total",
            "Status": "MATCH" if v["discounts_ok"] else ("REVIEW" if v["discounts_ok"] is False else "N/A"),
        },
        {
            "Check": "HASH sales",
            "Source / comparison": "Script HASH total vs HASH Sales 6",
            "Status": "MATCH" if v["hash_ok"] else ("REVIEW" if v["hash_ok"] is False else "N/A"),
        },
        {
            "Check": "IIF balance",
            "Source / comparison": "Positive vs negative IIF amounts",
            "Status": "MATCH" if v["iif_ok"] else "REVIEW",
        },
    ]
    st.dataframe(
        pd.DataFrame(validation_rows),
        use_container_width=True,
        hide_index=True,
    )

    # Detail tabs
    overview_tab, sales_tab, bs_tab, qb_tab, log_tab = st.tabs(
        [
            "🌿 Overview",
            "🛒 Sales & Discounts",
            "💰 Balance Sheet & Tenders",
            "📘 QuickBooks Preview",
            "🧾 Run Log",
        ]
    )

    with overview_tab:
        st.subheader("Deposit overview")

        o1, o2, o3 = st.columns(3)
        with o1:
            st.metric("Store Coupons", abs_money(v["store_coupons"]))
        with o2:
            st.metric("Owner Appreciation", abs_money(v["owner_apprec"]))
        with o3:
            st.metric("Milk Bottle Returns", abs_money(v["milk_bottle"]))

        h1, h2, h3 = st.columns(3)
        with h1:
            st.metric("Refunded Discounts", abs_money(v["refunded"]))
        with h2:
            st.metric("Pass Through Donations", abs_money(v["pass_through"]))
        with h3:
            st.metric("Warnings found", v["warning_count"])

        st.markdown(
            f"""
            <div class="hwfc-equation">
              <strong>IIF balance:</strong>
              Positive amounts {money(v['positive_total'])}
              &nbsp; | &nbsp;
              Negative amounts {money(v['negative_total'])}
              &nbsp; | &nbsp;
              Difference <strong>{money(v['iif_difference'])}</strong>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with sales_tab:
        sales_df = build_detail_df(lines, {"Sales"})
        disc_df = build_detail_df(lines, {"Discounts", "Store Coupons"})

        st.subheader("Sales")
        if sales_df.empty:
            st.info("No sales lines were detected in the generated IIF.")
        else:
            display = sales_df.copy()
            display["Amount"] = display["Amount"].map(lambda x: f"${abs(x):,.2f}" if pd.notna(x) else "")
            st.dataframe(display, use_container_width=True, hide_index=True)
            sales_total = sales_df["Amount"].dropna().abs().sum()
            st.caption(f"Sales lines shown: {len(sales_df)} · Total: ${sales_total:,.2f}")

        st.subheader("Discounts & Store Coupons")
        if disc_df.empty:
            st.info("No discount lines were detected in the generated IIF.")
        else:
            display = disc_df.copy()
            display["Amount"] = display["Amount"].map(lambda x: money(x) if pd.notna(x) else "")
            st.dataframe(display, use_container_width=True, hide_index=True)

    with bs_tab:
        tender_df = build_detail_df(lines, {"Tenders"})
        bs_df = build_detail_df(lines, {"Balance Sheet", "Other"})

        st.subheader("Tender lines")
        if tender_df.empty:
            st.info("No tender lines were classified from the IIF.")
        else:
            display = tender_df.copy()
            display["Amount"] = display["Amount"].map(lambda x: money(x) if pd.notna(x) else "")
            st.dataframe(display, use_container_width=True, hide_index=True)

        st.subheader("Balance Sheet / supporting lines")
        if bs_df.empty:
            st.info("No additional Balance Sheet lines were detected.")
        else:
            display = bs_df.copy()
            display["Amount"] = display["Amount"].map(lambda x: money(x) if pd.notna(x) else "")
            st.dataframe(display, use_container_width=True, hide_index=True)

    with qb_tab:
        st.subheader("QuickBooks IIF preview")
        st.caption("This is the actual generated transaction detail that will be imported into QuickBooks.")

        if iif_df.empty:
            st.info("No TRNS/SPL lines were found in the IIF.")
        else:
            preview = iif_df.copy()
            preview["Amount"] = preview["Amount"].map(lambda x: money(x) if pd.notna(x) else "")
            st.dataframe(preview, use_container_width=True, hide_index=True, height=520)

        st.download_button(
            "⬇ Download QuickBooks IIF",
            data=result["iif_bytes"],
            file_name=result["iif_path"].name,
            mime="text/plain",
            use_container_width=True,
        )

    with log_tab:
        st.caption("Full engine output for troubleshooting and audit review.")
        st.code(result["log_text"], language="text")

    if st.button("Run another deposit", use_container_width=False):
        st.session_state.pop("run_result", None)
        st.session_state.pop("run_date", None)
        st.session_state.pop("run_filename", None)
        st.rerun()


st.markdown(
    """
    <div class="hwfc-footer">
      Honest Weight Food Co-op · Daily Deposit Automation ·
      Always review the generated deposit in QuickBooks before final posting.
    </div>
    """,
    unsafe_allow_html=True,
)
