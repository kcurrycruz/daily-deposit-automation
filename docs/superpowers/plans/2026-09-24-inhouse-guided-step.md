# InHouse Charges Guided Step Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move account-coded InHouse Charges into a conditional guided step immediately before Closeout Sheet, with End of Day initials and Custom memo modes.

**Architecture:** Add a focused InHouse domain module for memo composition and step-payload validation, extend the existing deposit workflow with a conditional step, and persist the completed step independently from Closeout. Closeout consumes the saved actual and rows; the IIF engine consumes those rows in both in-app and manual Closeout modes.

**Tech Stack:** Python, Streamlit, Decimal currency validation, unittest, QuickBooks IIF.

**Spec:** `docs/superpowers/specs/2026-09-24-inhouse-guided-step-design.md`

## Global Constraints

- The step label is exactly `InHouse Charges` and it appears immediately before `Closeout Sheet`.
- The step is omitted when Balance Sheet Charge (House) is zero.
- Memo Type options are exactly `End of Day` and `Custom`; `End of Day` is the default.
- End of Day memos export as `End of Day - <UPPERCASE INITIALS>`.
- Breakdown Total must equal the editable Charge (House) Actual to the cent.
- Editing InHouse Charges invalidates Closeout completion.
- Completed InHouse splits export even when the remaining Closeout Sheet is finished manually.
- `output/history/` and generated test artifacts must not be committed.

## Review Focus

- A nonzero Charge (House) with missing or malformed InHouse saved state must reopen the InHouse step instead of silently advancing.
- A saved legacy memo of exactly `End of Day` must reopen with blank initials and must not complete until initials are entered.
- A one-cent row-total mismatch must remain visible and block completion.
- Editing InHouse after Closeout completion must invalidate the Closeout preview and completion while preserving earlier steps.
- Manual Closeout must keep real InHouse account lines and must not restore the legacy `InHouse:` TBA placeholders.

---

### Task 1: InHouse memo and payload domain

**Files:**
- Create: `app/inhouse_charges.py`
- Create: `tests/test_inhouse_charges.py`

**Interfaces:**
- Consumes: raw Memo Type/value input and raw `{actual, rows}` step payloads.
- Produces: `compose_inhouse_memo(memo_type: str, value: str) -> str`, `split_inhouse_memo(memo: str) -> tuple[str, str]`, and `normalize_inhouse_step_payload(payload: dict) -> dict`.

- [ ] **Step 1: Write failing memo tests**

```python
def test_end_of_day_memo_trims_and_uppercases_initials(self):
    self.assertEqual(compose_inhouse_memo("End of Day", " bs "), "End of Day - BS")

def test_custom_memo_trims_without_changing_case(self):
    self.assertEqual(compose_inhouse_memo("Custom", "  Board lunch  "), "Board lunch")

def test_blank_or_unknown_memo_input_is_rejected(self):
    for mode, value in (("End of Day", " "), ("Custom", ""), ("Other", "BS")):
        with self.subTest(mode=mode), self.assertRaises(ValueError):
            compose_inhouse_memo(mode, value)

def test_saved_memos_split_back_into_widget_values(self):
    self.assertEqual(split_inhouse_memo("End of Day - BS"), ("End of Day", "BS"))
    self.assertEqual(split_inhouse_memo("End of Day"), ("End of Day", ""))
    self.assertEqual(split_inhouse_memo("Board lunch"), ("Custom", "Board lunch"))
```

- [ ] **Step 2: Run the memo tests and verify they fail**

Run: `python -m unittest tests.test_inhouse_charges -v`

Expected: FAIL because `app.inhouse_charges` does not exist.

- [ ] **Step 3: Implement memo composition and splitting**

```python
END_OF_DAY = "End of Day"
CUSTOM = "Custom"
MEMO_TYPES = (END_OF_DAY, CUSTOM)
END_OF_DAY_PREFIX = "End of Day - "

def compose_inhouse_memo(memo_type: str, value: str) -> str:
    if memo_type not in MEMO_TYPES:
        raise ValueError("Choose End of Day or Custom for the InHouse memo")
    cleaned = str(value or "").strip()
    if not cleaned:
        label = "Initials" if memo_type == END_OF_DAY else "Custom memo"
        raise ValueError(f"{label} is required")
    return END_OF_DAY_PREFIX + cleaned.upper() if memo_type == END_OF_DAY else cleaned

def split_inhouse_memo(memo: str) -> tuple[str, str]:
    cleaned = str(memo or "").strip()
    if cleaned == END_OF_DAY:
        return END_OF_DAY, ""
    if cleaned.startswith(END_OF_DAY_PREFIX):
        return END_OF_DAY, cleaned[len(END_OF_DAY_PREFIX):].strip().upper()
    return CUSTOM, cleaned
```

- [ ] **Step 4: Write failing canonical payload tests**

```python
def test_step_payload_normalizes_rows_against_editable_actual(self):
    payload = normalize_inhouse_step_payload({
        "actual": "140.82",
        "rows": [
            {"account": "8320000 · Store Supplies", "memo": "End of Day - BS", "amount": "100.82"},
            {"account": "8504000 · Education", "memo": "Class materials", "amount": "40"},
        ],
    })
    self.assertEqual(payload["actual"], 140.82)
    self.assertEqual(sum(row["amount"] for row in payload["rows"]), 140.82)

def test_step_payload_rejects_one_cent_mismatch(self):
    with self.assertRaisesRegex(ValueError, "must equal Charge \\(House\\)"):
        normalize_inhouse_step_payload({
            "actual": 140.82,
            "rows": [{"account": "8320000 · Store Supplies", "memo": "End of Day - BS", "amount": 140.81}],
        })
```

- [ ] **Step 5: Implement canonical payload normalization**

Use `Decimal("0.01")` for the Actual and delegate row validation to `normalize_inhouse_charges(rows, actual)` from `app.closeout_reconciliation`:

```python
def _nonnegative_money(value, label: str) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} must be a valid amount") from None
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{label} must be a nonnegative amount")
    return amount

def normalize_inhouse_step_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("InHouse payload must be an object")
    actual = _nonnegative_money(payload.get("actual"), "Charge (House) Actual")
    rows = normalize_inhouse_charges(payload.get("rows", []), actual)
    return {"actual": float(actual), "rows": rows}
```

- [ ] **Step 6: Run the domain tests**

Run: `python -m unittest tests.test_inhouse_charges -v`

Expected: PASS.

- [ ] **Step 7: Commit the domain layer**

```bash
git add app/inhouse_charges.py tests/test_inhouse_charges.py
git commit -m "feat: add inhouse memo and payload rules"
```

### Task 2: Conditional guided-step workflow and persistence

**Files:**
- Modify: `app/closeout_reconciliation.py`
- Modify: `app/deposit_workflow.py`
- Modify: `app/guided_deposit_state.py`
- Modify: `streamlit_app.py`
- Modify: `tests/test_closeout_reconciliation.py`
- Modify: `tests/test_deposit_workflow.py`

**Interfaces:**
- Consumes: Balance Sheet code 906 Charge (House), canonical InHouse payload from Task 1.
- Produces: `read_charge_house_total(workbook_bytes, bs_sheet_name) -> float`, `STEP_INHOUSE`, and `save_inhouse_transition(...) -> dict`.

- [ ] **Step 1: Write failing Charge (House) reader tests**

Add workbook fixtures with code 906 and assert positive normalization, zero fallback, and a clear invalid-money error.

```python
self.assertEqual(read_charge_house_total(workbook_bytes, "BS"), 140.82)
```

- [ ] **Step 2: Implement the focused Balance Sheet reader**

Read only the named Balance Sheet and code 906. Do not require the HASH sheet merely to determine whether the step exists.

- [ ] **Step 3: Write failing workflow-order tests**

Update the workflow test helper to import `STEP_INHOUSE`, then pin both conditions:

```python
self.assertEqual(
    required_deposit_steps(0, {"donation": 0, "paid_in": 0, "paid_out": 0}, 18.49, 140.82),
    ("coupons", "inhouse_charges", "closeout"),
)
self.assertEqual(
    required_deposit_steps(0, {"donation": 0, "paid_in": 0, "paid_out": 0}, 0, 0),
    ("closeout",),
)
```

- [ ] **Step 4: Add the workflow constant and condition**

```python
STEP_INHOUSE = "inhouse_charges"
STEP_LABELS[STEP_INHOUSE] = "InHouse Charges"

def required_deposit_steps(subscription_total, activity_source_totals, coupon_bs_total, charge_house_total):
    ...
    if _is_nonzero(charge_house_total, "Charge (House)"):
        steps.append(STEP_INHOUSE)
    return (*steps, STEP_CLOSEOUT)
```

Update every call and combination test so InHouse is always immediately before Closeout when enabled.

- [ ] **Step 5: Write failing save/reopen tests**

Test an app completion saved under `inhouse_saved_payload_<workbook_key>`, restoration of `actual`, row IDs, account, Memo Type, memo value, and amount, plus the legacy exact `End of Day` case. Also pass a malformed saved payload and assert that reopening returns `False` and does not mark InHouse complete.

```python
transition = save_inhouse_transition(
    ("inhouse_charges", "closeout"), {}, saved_key,
    {"actual": 8, "rows": [{"account": account, "memo": "End of Day - BS", "amount": 8}]},
)
self.assertEqual(transition["completions"], {"inhouse_charges": "app"})
```

- [ ] **Step 6: Implement save and reopen state transitions**

Add `save_inhouse_transition` using `_save_payload_transition`. Extend `_hydrate_reopened_app_step` to normalize the saved payload, restore `inhouse_actual_*`, stable row IDs, account, memo type/value from `split_inhouse_memo`, and amount.

- [ ] **Step 7: Read Charge (House) during workflow detection**

In `streamlit_app.py`, read `charge_house_total` alongside subscription and coupon totals. If it cannot be read, mark workflow detection invalid and show a specific message. Pass the total into `required_deposit_steps`.

- [ ] **Step 8: Run focused workflow tests**

Run: `python -m unittest tests.test_closeout_reconciliation tests.test_deposit_workflow -v`

Expected: PASS.

- [ ] **Step 9: Commit workflow and state support**

```bash
git add app/closeout_reconciliation.py app/deposit_workflow.py app/guided_deposit_state.py streamlit_app.py tests/test_closeout_reconciliation.py tests/test_deposit_workflow.py
git commit -m "feat: add conditional inhouse guided step"
```

### Task 3: InHouse step UI and Closeout handoff

**Files:**
- Modify: `streamlit_app.py`
- Modify: `app/guided_step_ui.py`
- Modify: `tests/test_membership_payments.py`
- Modify: `tests/test_deposit_workflow.py`

**Interfaces:**
- Consumes: `STEP_INHOUSE`, memo helpers, canonical saved payload, Chart of Accounts options.
- Produces: completed `inhouse_saved_payload_<workbook_key>` and a Closeout form whose Charge (House) Actual/rows are derived from that payload.

- [ ] **Step 1: Write failing UI source-contract tests**

Assert the source contains the dedicated active-step branch, Memo Type options, Initials and Custom Memo fields, save label, and no InHouse editor inside the Closeout block.

```python
self.assertIn("active_step == STEP_INHOUSE", source)
self.assertIn('options=["End of Day", "Custom"]', source)
self.assertIn('"Save InHouse Charges & Continue"', source)
self.assertLess(source.index("active_step == STEP_INHOUSE"), source.index("active_step == STEP_CLOSEOUT"))
```

- [ ] **Step 2: Render the dedicated InHouse step**

Before the Closeout branch, render System / BS, editable Actual, repeatable rows, and Actual/Breakdown/Remaining summary. Use the existing searchable Chart of Accounts selector. For each row, compose the canonical memo with `compose_inhouse_memo`; display its validation error next to the affected field.

- [ ] **Step 3: Implement atomic save and advancement**

On `Save InHouse Charges & Continue`, normalize `{actual, rows}`, call `save_inhouse_transition`, write both saved payload and workflow completions, clear stale Closeout preview state, queue the existing continue scroll, and rerun.

- [ ] **Step 4: Write failing Closeout-handoff tests**

Pin that the saved Actual becomes the locked Closeout Charge (House) Actual and saved rows are passed to `build_closeout_form_payload`. Test a BS amount of 10, saved Actual/rows of 8, and expect the existing +2 Charge (House) over/short adjustment.

- [ ] **Step 5: Remove the duplicate Closeout editor**

Delete the InHouse add/remove widgets from the Closeout branch. Require a valid saved InHouse payload when `STEP_INHOUSE` is present. Render Charge (House) Actual as `$<amount> (breakdown)` and pass the saved rows to the closeout payload builder.

- [ ] **Step 6: Preserve historical payload restoration**

When the new saved key is absent but a historical Closeout payload has `inhouse_charges`, seed the new step from `actuals["charge_house"]` and those rows. Do not auto-complete it; legacy `End of Day` rows require initials before completion.

- [ ] **Step 7: Run focused UI and handoff tests**

Run: `python -m unittest tests.test_deposit_workflow tests.test_membership_payments -v`

Expected: PASS.

- [ ] **Step 8: Commit the guided UI**

```bash
git add streamlit_app.py app/guided_step_ui.py tests/test_membership_payments.py tests/test_deposit_workflow.py
git commit -m "feat: move inhouse charges before closeout"
```

### Task 4: Manual Closeout IIF compatibility and end-to-end verification

**Files:**
- Modify: `app/closeout_reconciliation.py`
- Modify: `app/pos_to_quickbooks_v2.py`
- Modify: `streamlit_app.py`
- Modify: `tests/test_closeout_reconciliation.py`
- Modify: `tests/test_membership_payments.py`

**Interfaces:**
- Consumes: canonical saved InHouse Actual and rows in either Closeout mode.
- Produces: real IIF SPL rows for InHouse Charges without legacy placeholders.

- [ ] **Step 1: Write failing manual-mode payload tests**

Pin that manual Closeout can carry canonical `charge_house_actual` and `inhouse_charges` while still rejecting mismatched rows.

```python
normalized = normalize_closeout_payload({
    "mode": "manual",
    "charge_house_actual": 8,
    "inhouse_charges": [{"account": account, "memo": "End of Day - BS", "amount": 8}],
})
self.assertEqual(normalized["mode"], "manual")
self.assertEqual(normalized["charge_house_actual"], 8.0)
```

- [ ] **Step 2: Preserve InHouse data in manual Closeout payloads**

When the employee selects manual Closeout, build `{mode, charge_house_actual, inhouse_charges}` from the completed step. Extend `normalize_closeout_payload` to normalize those optional fields; retain `{"mode": "manual"}` compatibility when Charge (House) is zero.

- [ ] **Step 3: Write failing IIF tests for manual Closeout**

Generate an IIF with manual Closeout plus two InHouse rows. Assert both selected accounts and composed memos are present, their amounts sum to Charge (House) Actual, and `InHouse:` plus its five blank TBA rows are absent.

- [ ] **Step 4: Use canonical InHouse rows independently of Closeout reconciliation mode**

Keep `normalized_closeout` reserved for full Closeout adjustments, but derive `inhouse_rows` from `candidate_closeout` in both modes. Build `inhouse_entries` from those rows whenever present; use legacy placeholders only when no canonical InHouse rows were supplied.

- [ ] **Step 5: Run all InHouse, workflow, Closeout, and IIF tests**

Run: `python -m unittest tests.test_inhouse_charges tests.test_deposit_workflow tests.test_closeout_reconciliation tests.test_membership_payments -v`

Expected: PASS.

- [ ] **Step 6: Run the complete regression suite and static checks**

Run: `python -m unittest discover -s tests -q`

Run: `python -m py_compile app/inhouse_charges.py app/deposit_workflow.py app/guided_deposit_state.py app/closeout_reconciliation.py app/pos_to_quickbooks_v2.py streamlit_app.py`

Run: `git diff --check`

Expected: all tests pass, compilation succeeds, and no whitespace errors are reported.

- [ ] **Step 7: Inspect scope and commit**

Confirm `git status --short` contains only intended source, tests, and documentation; exclude `output/history/` and generated test folders.

```bash
git add app/inhouse_charges.py app/deposit_workflow.py app/guided_deposit_state.py app/closeout_reconciliation.py app/pos_to_quickbooks_v2.py streamlit_app.py tests/test_inhouse_charges.py tests/test_deposit_workflow.py tests/test_closeout_reconciliation.py tests/test_membership_payments.py docs/superpowers/specs/2026-09-24-inhouse-guided-step-design.md docs/superpowers/plans/2026-09-24-inhouse-guided-step.md
git commit -m "feat: complete inhouse guided workflow"
```
