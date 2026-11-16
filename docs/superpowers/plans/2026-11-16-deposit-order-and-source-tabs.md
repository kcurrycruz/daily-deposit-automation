# Deposit Order and Source Tabs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let staff reorder InHouse charges, retain all six uploaded SMS inputs as hidden SubDept workbook sheets, and show Closeout Actual left of System / BS.

**Architecture:** Keep the current Streamlit session-state row IDs as the authoritative charge order, and move IDs rather than moving widget values. Extend the existing reporting-workbook builder with hidden raw-value source sheets, without altering its visible report tabs. Swap only the Closeout UI presentation order; accounting calculations remain unchanged.

**Tech Stack:** Python, Streamlit, openpyxl (the existing app workbook builder), unittest.

**Spec:** `docs/superpowers/specs/2026-11-16-deposit-order-and-source-tabs-design.md`

## Global Constraints

- Work on existing `DD-v2`; do not change `main`, push, or deploy without a separate user request.
- Preserve the existing visible SubDept workbook sheets, values, styles, and calculation results.
- Preserve original parsed SMS row/column positions and typed values on six hidden worksheets; original `.xls` binaries and styling are not embedded.
- Preserve InHouse account, memo, initials, signed amount, validation, and IIF sign logic.
- Closeout Difference stays Actual minus System / BS.

## Review Focus

- Moving the first row up or last row down is a no-op; test in Task 1.
- Moving a signed-credit row keeps every field paired and does not change the total; test in Task 1.
- A saved draft and reopened InHouse step preserve row order; test in Task 1.
- A source text cell beginning with `=` stays text, never an executable Excel formula; test in Task 2.
- A hidden input tab must not become the active visible sheet or alter the existing report; test in Task 2.

---

### Task 1: Reorder InHouse charges

**Files:**
- Modify: `app/inhouse_charges.py`
- Modify: `streamlit_app.py` (InHouse charge row loop near `inhouse_ids_key`)
- Test: `tests/test_inhouse_charges.py`
- Test: `tests/test_deposit_draft.py` and `tests/test_deposit_workflow.py`

**Interfaces:**
- Consumes: `st.session_state[inhouse_ids_key]` as ordered `list[str]`.
- Produces: `move_inhouse_row_ids(row_ids: list[str], row_id: str, offset: int) -> list[str]`, where offset is `-1` or `1`; unknown IDs or offsets raise `ValueError`, boundary moves return a copy unchanged.

- [ ] **Step 1: Write failing tests** for up/down/middle/boundary moves, invalid IDs/directions, signed-credit row pairing after UI-state order change, draft ZIP restore order, reopened step order, and resulting IIF order.
- [ ] **Step 2: Run** `python -X utf8 -m unittest tests.test_inhouse_charges tests.test_deposit_draft tests.test_deposit_workflow -q`; confirm new tests fail for missing move behavior.
- [ ] **Step 3: Implement** the pure move helper and compact Up/Down buttons beside Remove in the InHouse row. Move only the selected ID, rerun Streamlit, and let the existing ordered row loop feed save, draft, preview, and IIF.
- [ ] **Step 4: Run** the same targeted command; confirm all tests pass and manually inspect the row alignment.
- [ ] **Step 5: Commit** only Task 1 code/tests plus the approved spec and plan.

### Task 2: Add hidden SMS source tabs to the SubDept download

**Files:**
- Modify: `app/daily_reporting_workbook.py`
- Test: `tests/test_daily_reporting_workbook.py`

**Interfaces:**
- Consumes: `bundle.reports[role].rows` for `sales`, `coupons`, `discounts`, `hash`, `bs`, `milk_bottles`.
- Produces: six extra sheets named `SMS Input - Sales`, `SMS Input - Coupon`, `SMS Input - Discounts`, `SMS Input - HASH`, `SMS Input - BS`, `SMS Input - Milk Bottles`, each with `sheet_state="hidden"` and source grid starting at A1.

- [ ] **Step 1: Write failing tests** asserting exact six hidden sheet names/states and source-grid values (including a formula-looking string preserved as text); assert the existing visible sheets, active sheet, report values, and source input dates are unchanged.
- [ ] **Step 2: Run** `python -X utf8 -m unittest tests.test_daily_reporting_workbook -q`; confirm the hidden-sheet tests fail.
- [ ] **Step 3: Extend** `build_reporting_workbook` to append the hidden sheets after the existing tabs, copy the six parsed grids without changing their positions, and force formula-looking source strings to Excel text.
- [ ] **Step 4: Run** the targeted tests and the six-report-to-IIF workflow tests in `tests.test_deposit_workflow`.
- [ ] **Step 5: Commit** only Task 2 code/tests.

### Task 3: Put Closeout Actual left of System / BS

**Files:**
- Modify: `streamlit_app.py` (Closeout entry grid and review dataframe)
- Test: `tests/test_closeout_ui_order.py` (new focused UI/source-order test)

**Interfaces:**
- Consumes: `closeout_baselines`, `closeout_actuals`, and review `standard_rows` unchanged.
- Produces: entry headings `Category, Actual, System / BS, Difference, Status`; review headings `Category, Actual, System / BS, Difference`.

- [ ] **Step 1: Write failing tests** that inspect the two Closeout display orders and verify a nonzero difference remains Actual minus System / BS.
- [ ] **Step 2: Run** `python -X utf8 -m unittest tests.test_closeout_ui_order -q`; confirm the order assertions fail.
- [ ] **Step 3: Swap** entry-grid column placement and review dataframe column order. Keep widget keys, values, locked breakdowns, difference calculations, and reconciliation payload unchanged.
- [ ] **Step 4: Run** the focused test and `tests.test_deposit_workflow`; inspect the entry/review layout.
- [ ] **Step 5: Commit** only Task 3 code/tests.

### Task 4: Release verification

- [ ] **Step 1: Run** `git diff --check` and `python -X utf8 -m unittest discover -s tests -p 'test_*.py' -q` with the project's test dependency path; require zero failures.
- [ ] **Step 2: Build** one fixture-based SubDept workbook; verify six hidden raw sheets, unchanged visible report totals, and no unexpected formula cells in the hidden inputs.
- [ ] **Step 3: Verify** the final branch status and commit list. Report local results; do not push or deploy unless the user asks.
