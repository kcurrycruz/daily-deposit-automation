import io
import os
import re
import sys
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "input" / "daily_reports"
IIF_DIR = ROOT / "output" / "qb_imports"
SUMMARY_DIR = ROOT / "output" / "summaries"
LOG_DIR = ROOT / "logs"
ENGINE = ROOT / "app" / "pos_to_quickbooks_v2.py"

for folder in (INPUT_DIR, IIF_DIR, SUMMARY_DIR, LOG_DIR):
    folder.mkdir(parents=True, exist_ok=True)


st.set_page_config(
    page_title="HWFC Daily Deposit",
    page_icon="🌿",
    layout="centered",
)

st.title("🌿 HWFC Daily Deposit")
st.caption("Honest Weight Food Co-op · QuickBooks Deposit Automation")

st.info(
    "Upload the completed daily Excel workbook, select the deposit date, "
    "then run the automation. Review the checks before downloading the IIF."
)

deposit_date = st.date_input(
    "Deposit date",
    value=date.today() - timedelta(days=1),
    format="MM/DD/YYYY",
)

uploaded = st.file_uploader(
    "Daily SubDept Excel workbook",
    type=["xlsx", "xlsm"],
    accept_multiple_files=False,
)

with st.expander("Workbook checklist"):
    st.markdown(
        """
- `SubDept Sales Report`
- Daily `discounts` tab
- Daily `BS` tab
- Daily `hash` tab
- Milk Bottle Return entered in `M1`
- Store Coupons entered in `M2`
- Owner Appreciation entered in `J2` if applicable
- Excel Sales Total available in `J3`
"""
    )


def clear_previous_inputs():
    for p in INPUT_DIR.iterdir():
        if p.is_file() and p.name != ".gitkeep":
            p.unlink()


def extract_validation(log_text: str):
    results = {
        "sales": None,
        "discounts": None,
        "hash_refunded": None,
        "hash_pass": None,
        "hash_paidin": None,
        "charity": None,
    }

    sales_block = re.search(
        r"SALES CHECK.*?RESULT:\s*([^\n]+)",
        log_text,
        flags=re.S,
    )
    if sales_block:
        results["sales"] = sales_block.group(1).strip()

    disc_block = re.search(
        r"DISCOUNTS CHECK.*?RESULT:\s*([^\n]+)",
        log_text,
        flags=re.S,
    )
    if disc_block:
        results["discounts"] = disc_block.group(1).strip()

    patterns = {
        "hash_refunded": r"HASH code 23 Refunded Discounts:\s*\$?([-\d,]+\.\d{2})",
        "hash_pass": r"HASH code 32 Pass Through Donations:\s*\$?([-\d,]+\.\d{2})",
        "hash_paidin": r"HASH code 34 Paid-Ins:\s*\$?([-\d,]+\.\d{2})",
        "charity": r"Charity mapping:.*?=\s*\$?([-\d,]+\.\d{2})",
    }

    for key, pattern in patterns.items():
        m = re.search(pattern, log_text)
        if m:
            results[key] = m.group(1)

    return results


if st.button("▶ Run Deposit Automation", type="primary", use_container_width=True):
    if uploaded is None:
        st.error("Upload the daily Excel workbook first.")
        st.stop()

    clear_previous_inputs()

    uploaded_path = INPUT_DIR / Path(uploaded.name).name
    uploaded_path.write_bytes(uploaded.getvalue())

    date_arg = deposit_date.strftime("%m/%d/%y")
    cmd = [sys.executable, str(ENGINE), "--date", date_arg]

    with st.spinner(f"Running deposit for {deposit_date:%B %d, %Y}..."):
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    full_log = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    st.session_state["last_log"] = full_log
    st.session_state["last_date"] = deposit_date

    if proc.returncode != 0:
        st.error("The automation stopped with an error.")
        st.code(full_log, language="text")
        st.stop()

    results = extract_validation(full_log)

    st.success("Deposit automation completed.")

    c1, c2 = st.columns(2)
    with c1:
        if results["sales"]:
            if "MATCH" in results["sales"] and "MISMATCH" not in results["sales"]:
                st.success(f"Sales: {results['sales']}")
            else:
                st.warning(f"Sales: {results['sales']}")
        else:
            st.warning("Sales check result not found.")

    with c2:
        if results["discounts"]:
            if "MATCH" in results["discounts"] and "MISMATCH" not in results["discounts"]:
                st.success(f"Discounts: {results['discounts']}")
            else:
                st.warning(f"Discounts: {results['discounts']}")
        else:
            st.warning("Discount check result not found.")

    st.subheader("HASH / Deposit Details")
    d1, d2, d3 = st.columns(3)
    d1.metric("Refunded Discounts", f"${results['hash_refunded']}" if results["hash_refunded"] else "Not found")
    d2.metric("Pass Through", f"${results['hash_pass']}" if results["hash_pass"] else "Not found")
    d3.metric("PAID IN", f"${results['hash_paidin']}" if results["hash_paidin"] else "Not found")

    if results["charity"]:
        st.metric("Charity + Pass Through", f"${results['charity']}")

    iif_path = IIF_DIR / f"deposit_{deposit_date.strftime('%Y%m%d')}.iif"
    summary_path = SUMMARY_DIR / f"deposit_summary_{deposit_date.strftime('%Y%m%d')}.xlsx"
    status_path = LOG_DIR / "last_run_status.txt"

    st.subheader("Downloads")

    if iif_path.exists():
        st.download_button(
            "⬇ Download QuickBooks IIF",
            data=iif_path.read_bytes(),
            file_name=iif_path.name,
            mime="text/plain",
            use_container_width=True,
        )
    else:
        st.error("IIF output file was not found.")

    if summary_path.exists():
        st.download_button(
            "⬇ Download Excel Summary",
            data=summary_path.read_bytes(),
            file_name=summary_path.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    if status_path.exists():
        st.download_button(
            "⬇ Download Run Status",
            data=status_path.read_bytes(),
            file_name=status_path.name,
            mime="text/plain",
            use_container_width=True,
        )

if "last_log" in st.session_state:
    with st.expander("View full run log"):
        st.code(st.session_state["last_log"], language="text")

st.divider()
st.caption(
    "Always review the generated deposit in QuickBooks before final posting."
)
