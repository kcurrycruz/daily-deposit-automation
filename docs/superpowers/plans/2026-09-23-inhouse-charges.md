# InHouse Charges Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an account-coded InHouse Charges breakdown that must equal Charge (House) and writes real QuickBooks splits into the IIF.

**Architecture:** Extend the canonical Closeout payload with normalized `inhouse_charges` rows, render those rows inside the existing Closeout form, and have the IIF engine replace legacy TBA placeholders with the normalized splits. Keep reconciliation math centralized in `closeout_reconciliation.py` and session restoration in `guided_deposit_state.py`.

**Tech Stack:** Python, Streamlit, Decimal currency validation, unittest, QuickBooks IIF.

**Spec:** `docs/superpowers/specs/2026-09-23-inhouse-charges.md`

## Global Constraints

- Memo defaults to the exact text `End of Day`.
- The breakdown total must equal Charge (House) to the cent.
- QuickBooks accounts come from the existing searchable Chart of Accounts list.
- Manual Closeout mode and all non-InHouse workflows remain unchanged.
- `output/history/` must never be committed.

## Review Focus

- Charge (House) is positive but rows are missing: reject the form and IIF.
- Row sum differs by one cent: show the remaining amount and block review.
- Account, memo, or amount is invalid: show a clear field-level validation message.
- Reopened Closeout step: restore stable row IDs and every saved value.
- IIF sign and ordering: individual InHouse splits sum to the positive Charge (House) IIF amount and appear before Closeout adjustments.

---

### Task 1: Canonical InHouse validation

**Files:**
- Modify: `app/closeout_reconciliation.py`
- Test: `tests/test_closeout_reconciliation.py`

**Interfaces:**
- Consumes: `actuals["charge_house"]` and raw `inhouse_charges` rows.
- Produces: `normalize_inhouse_charges(rows, expected_total) -> list[dict]` and canonical payload field `inhouse_charges`.

- [ ] **Step 1: Write failing tests** for default-normalized rows, invalid fields, a one-cent mismatch, zero Charge (House), and canonical persistence.
- [ ] **Step 2: Run the focused tests** and confirm they fail because `inhouse_charges` is not normalized.
- [ ] **Step 3: Implement cent-safe normalization** with required account/memo, positive amount, forbidden delimiter checks, and exact total validation.
- [ ] **Step 4: Thread `inhouse_charges` through `build_closeout_form_payload` and `normalize_closeout_payload`** without changing manual mode.
- [ ] **Step 5: Run the focused tests** and confirm they pass.

### Task 2: Closeout form and restoration

**Files:**
- Modify: `streamlit_app.py`
- Modify: `app/guided_deposit_state.py`
- Test: `tests/test_deposit_workflow.py`
- Test: `tests/test_membership_payments.py`

**Interfaces:**
- Consumes: Charge (House) baseline and normalized saved rows.
- Produces: repeatable account/memo/amount UI rows and `inhouse_charges` passed to `build_closeout_form_payload`.

- [ ] **Step 1: Write failing state-restoration and source-contract tests** for row IDs, account, `End of Day` memo, amount, searchable account options, totals, and disabled review on mismatch.
- [ ] **Step 2: Run the focused tests** and confirm the form and hydration keys are absent.
- [ ] **Step 3: Render the InHouse editor** above Other Closeout Sheet activity, beginning with one row when Charge (House) is positive.
- [ ] **Step 4: Lock Charge (House) Actual to the row total** and render Target, Breakdown Total, and Remaining feedback.
- [ ] **Step 5: Restore saved rows when editing** and ensure add/remove actions retain the employee’s other form values.
- [ ] **Step 6: Run the focused tests** and confirm they pass.

### Task 3: IIF account-coded splits

**Files:**
- Modify: `app/pos_to_quickbooks_v2.py`
- Test: `tests/test_membership_payments.py`

**Interfaces:**
- Consumes: canonical `normalized_closeout["inhouse_charges"]`.
- Produces: one IIF SPL per row with selected account, memo, amount, and no reviewed-workflow InHouse TBA placeholders.

- [ ] **Step 1: Write failing IIF tests** for two accounts that sum to Charge (House), exact signs and memos, ordering, and absence of `InHouse:` placeholders.
- [ ] **Step 2: Run the focused tests** and confirm the engine still emits TBA placeholders.
- [ ] **Step 3: Replace the legacy reviewed-workflow InHouse lines** with canonical account-coded splits while preserving the Charge (House) Closeout adjustment.
- [ ] **Step 4: Include InHouse rows in preview totals** so Review Closeout and final POS math use the same amounts as the final IIF.
- [ ] **Step 5: Run the focused tests** and confirm they pass.

### Task 4: End-to-end verification

**Files:**
- Modify tests only if a compatibility expectation legitimately changes.

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: verified Daily Deposit branch ready for user testing.

- [ ] **Step 1: Run all Closeout, workflow, and IIF focused tests.**
- [ ] **Step 2: Run `python -m unittest discover -s tests -q`.**
- [ ] **Step 3: Run syntax compilation and `git diff --check`.**
- [ ] **Step 4: Inspect the final diff** for unrelated files and confirm `output/history/` is excluded.
