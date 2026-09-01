# Guided Deposit Steps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the detected deposit activities into a stable, numbered workflow that shows only the current unfinished step, preserves completed entries, and always finishes with Closeout Sheet before the IIF can be prepared.

**Architecture:** Add a pure `app.deposit_workflow` state model for required-step discovery, ordering, completion, editing, and final eligibility. Keep accounting payloads in their existing section-specific state, use the workflow model only for orchestration, and update `streamlit_app.py` to reconstruct hidden completed payloads before rendering the one active section.

**Tech Stack:** Python 3, Streamlit session state, `unittest`, existing membership/activity/coupon/Closeout modules.

**Spec:** `docs/superpowers/specs/2026-08-31-guided-deposit-steps-design.md`

## Global Constraints

- Closeout Sheet is always required and always the final numbered step.
- Optional steps appear only when detected, in this order: Member Share Payments, Donations, Paid In, Paid Out, Coupons Receivable, Closeout Sheet.
- Step numbers are gap-free for the current deposit.
- `Finish manually in QuickBooks` completes a step immediately.
- In-app steps complete only after existing validation passes and the employee selects `Save & Continue`; typing alone must not collapse a form.
- Editing an earlier completed step preserves later saved inputs but clears Closeout completion and its saved preview.
- Existing accounts, signs, memos, calculations, IIF ordering, source detection, and manual QuickBooks outputs must not change.
- Workflow and payload state must be scoped to the existing workbook identity key.

---

## File Structure

- Create `app/deposit_workflow.py`: pure required-step and completion-state rules; no Streamlit or accounting imports.
- Create `tests/test_deposit_workflow.py`: exhaustive unit tests for ordering, transitions, editing, and completion eligibility.
- Modify `app/ui_helpers.py`: safe HTML for one compact workflow status card.
- Modify `tests/test_membership_payments.py`: UI helper and Streamlit integration assertions.
- Modify `streamlit_app.py`: source discovery before rendering, workflow summary, one-active-step rendering, payload persistence/reconstruction, Edit behavior, and final gating.

---

### Task 1: Pure Deposit Workflow State Model

**Files:**
- Create: `app/deposit_workflow.py`
- Create: `tests/test_deposit_workflow.py`

**Interfaces:**
- Consumes: numeric source totals already produced by `read_subscription_total`, `read_activity_source_totals`, and `read_coupon_receivable_total`.
- Produces:
  - `STEP_MEMBER_SHARES`, `STEP_DONATION`, `STEP_PAID_IN`, `STEP_PAID_OUT`, `STEP_COUPONS`, `STEP_CLOSEOUT`
  - `STEP_LABELS: dict[str, str]`
  - `required_deposit_steps(subscription_total: float, activity_source_totals: dict, coupon_bs_total: float) -> tuple[str, ...]`
  - `normalize_step_completions(required_steps: tuple[str, ...], completions: dict | None) -> dict[str, str]`
  - `active_deposit_step(required_steps: tuple[str, ...], completions: dict | None) -> str | None`
  - `complete_deposit_step(required_steps: tuple[str, ...], completions: dict | None, step: str, method: str) -> dict[str, str]`
  - `edit_deposit_step(required_steps: tuple[str, ...], completions: dict | None, step: str) -> dict[str, str]`
  - `deposit_workflow_complete(required_steps: tuple[str, ...], completions: dict | None) -> bool`
  - `deposit_step_rows(required_steps: tuple[str, ...], completions: dict | None) -> list[dict]`

- [ ] **Step 1: Write failing required-step discovery tests**

Create `tests/test_deposit_workflow.py` with explicit ordering and zero-value cases:

```python
import unittest


class DepositWorkflowTests(unittest.TestCase):
    def workflow_api(self):
        try:
            from app.deposit_workflow import (
                STEP_CLOSEOUT,
                active_deposit_step,
                complete_deposit_step,
                deposit_step_rows,
                deposit_workflow_complete,
                edit_deposit_step,
                normalize_step_completions,
                required_deposit_steps,
            )
        except ImportError as exc:
            self.fail(f"guided deposit workflow is missing: {exc}")
        return locals()

    def test_required_steps_use_fixed_gap_free_business_order(self):
        api = self.workflow_api()
        steps = api["required_deposit_steps"](
            8.45,
            {"donation": 25, "paid_in": 100, "paid_out": 40},
            18.49,
        )
        self.assertEqual(
            steps,
            (
                "member_shares",
                "donation",
                "paid_in",
                "paid_out",
                "coupons",
                "closeout",
            ),
        )

    def test_only_paid_in_still_ends_with_closeout(self):
        api = self.workflow_api()
        self.assertEqual(
            api["required_deposit_steps"](
                0,
                {"donation": 0, "paid_in": 100, "paid_out": 0},
                0,
            ),
            ("paid_in", "closeout"),
        )

    def test_no_optional_activity_still_requires_closeout(self):
        api = self.workflow_api()
        self.assertEqual(
            api["required_deposit_steps"](
                0,
                {"donation": 0, "paid_in": 0, "paid_out": 0},
                0,
            ),
            ("closeout",),
        )

    def test_every_optional_combination_preserves_business_order(self):
        from itertools import product

        api = self.workflow_api()
        ordered = (
            "member_shares",
            "donation",
            "paid_in",
            "paid_out",
            "coupons",
        )
        for enabled in product((False, True), repeat=len(ordered)):
            with self.subTest(enabled=enabled):
                steps = api["required_deposit_steps"](
                    1 if enabled[0] else 0,
                    {
                        "donation": 1 if enabled[1] else 0,
                        "paid_in": 1 if enabled[2] else 0,
                        "paid_out": 1 if enabled[3] else 0,
                    },
                    1 if enabled[4] else 0,
                )
                self.assertEqual(
                    steps,
                    tuple(
                        step
                        for step, is_enabled in zip(ordered, enabled)
                        if is_enabled
                    )
                    + ("closeout",),
                )
```

- [ ] **Step 2: Run the discovery tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_deposit_workflow.DepositWorkflowTests.test_required_steps_use_fixed_gap_free_business_order tests.test_deposit_workflow.DepositWorkflowTests.test_only_paid_in_still_ends_with_closeout tests.test_deposit_workflow.DepositWorkflowTests.test_no_optional_activity_still_requires_closeout -v
```

Expected: FAIL because `app.deposit_workflow` does not exist.

- [ ] **Step 3: Implement constants and required-step discovery**

Create `app/deposit_workflow.py` with finite-number validation and a Closeout sentinel that is always appended:

```python
from decimal import Decimal, InvalidOperation


STEP_MEMBER_SHARES = "member_shares"
STEP_DONATION = "donation"
STEP_PAID_IN = "paid_in"
STEP_PAID_OUT = "paid_out"
STEP_COUPONS = "coupons"
STEP_CLOSEOUT = "closeout"

STEP_LABELS = {
    STEP_MEMBER_SHARES: "Member Share Payments",
    STEP_DONATION: "Donations",
    STEP_PAID_IN: "Paid In",
    STEP_PAID_OUT: "Paid Out",
    STEP_COUPONS: "Coupons Receivable",
    STEP_CLOSEOUT: "Closeout Sheet",
}

COMPLETION_METHODS = {"app", "quickbooks"}


def _is_nonzero(value, label: str) -> bool:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} must be a valid amount") from None
    if not amount.is_finite():
        raise ValueError(f"{label} must be a valid amount")
    return amount != 0


def required_deposit_steps(
    subscription_total: float,
    activity_source_totals: dict,
    coupon_bs_total: float,
) -> tuple[str, ...]:
    if not isinstance(activity_source_totals, dict):
        raise ValueError("Activity source totals must be an object")
    steps = []
    if _is_nonzero(subscription_total, "Subscription Revenue"):
        steps.append(STEP_MEMBER_SHARES)
    for source_key, step, label in (
        ("donation", STEP_DONATION, "Donation"),
        ("paid_in", STEP_PAID_IN, "Paid In"),
        ("paid_out", STEP_PAID_OUT, "Paid Out"),
    ):
        if _is_nonzero(activity_source_totals.get(source_key, 0), label):
            steps.append(step)
    if _is_nonzero(coupon_bs_total, "Coupons Receivable"):
        steps.append(STEP_COUPONS)
    return (*steps, STEP_CLOSEOUT)
```

- [ ] **Step 4: Run the discovery tests and verify they pass**

Run: `python -m unittest tests.test_deposit_workflow -v`

Expected: all four discovery tests PASS.

- [ ] **Step 5: Write failing transition and status-row tests**

Append tests that prove manual/app completion, first-incomplete selection, stale-state removal, Edit invalidation, labels, numbering, and final eligibility:

```python
    def test_completion_methods_advance_to_first_incomplete_step(self):
        api = self.workflow_api()
        steps = ("paid_in", "paid_out", "closeout")
        completed = api["complete_deposit_step"](steps, {}, "paid_in", "quickbooks")
        self.assertEqual(completed, {"paid_in": "quickbooks"})
        self.assertEqual(api["active_deposit_step"](steps, completed), "paid_out")
        completed = api["complete_deposit_step"](steps, completed, "paid_out", "app")
        self.assertEqual(api["active_deposit_step"](steps, completed), "closeout")

    def test_normalization_ignores_stale_and_invalid_completion_entries(self):
        api = self.workflow_api()
        normalized = api["normalize_step_completions"](
            ("paid_in", "closeout"),
            {"donation": "app", "paid_in": "invalid", "closeout": "quickbooks"},
        )
        self.assertEqual(normalized, {"closeout": "quickbooks"})

    def test_edit_preserves_later_activity_but_invalidates_step_and_closeout(self):
        api = self.workflow_api()
        steps = ("donation", "paid_in", "paid_out", "closeout")
        completed = {
            "donation": "app",
            "paid_in": "app",
            "paid_out": "quickbooks",
            "closeout": "app",
        }
        edited = api["edit_deposit_step"](steps, completed, "paid_in")
        self.assertEqual(
            edited,
            {"donation": "app", "paid_out": "quickbooks"},
        )
        self.assertEqual(api["active_deposit_step"](steps, edited), "paid_in")

    def test_rows_are_gap_free_and_expose_user_facing_statuses(self):
        api = self.workflow_api()
        rows = api["deposit_step_rows"](
            ("paid_in", "closeout"),
            {"paid_in": "quickbooks"},
        )
        self.assertEqual(
            rows,
            [
                {
                    "number": 1,
                    "step": "paid_in",
                    "label": "Paid In",
                    "status": "Finish in QuickBooks",
                    "complete": True,
                    "current": False,
                },
                {
                    "number": 2,
                    "step": "closeout",
                    "label": "Closeout Sheet",
                    "status": "Current",
                    "complete": False,
                    "current": True,
                },
            ],
        )

    def test_final_eligibility_requires_every_step(self):
        api = self.workflow_api()
        steps = ("paid_in", "closeout")
        self.assertFalse(api["deposit_workflow_complete"](steps, {"paid_in": "app"}))
        self.assertTrue(
            api["deposit_workflow_complete"](
                steps,
                {"paid_in": "app", "closeout": "quickbooks"},
            )
        )
```

- [ ] **Step 6: Run the transition tests and verify they fail**

Run: `python -m unittest tests.test_deposit_workflow -v`

Expected: FAIL because the transition functions are not implemented.

- [ ] **Step 7: Implement normalization, transitions, row statuses, and eligibility**

Add minimal pure functions. They return new dictionaries and never mutate caller state:

```python
def normalize_step_completions(required_steps, completions):
    source = completions if isinstance(completions, dict) else {}
    return {
        step: source[step]
        for step in required_steps
        if source.get(step) in COMPLETION_METHODS
    }


def active_deposit_step(required_steps, completions):
    normalized = normalize_step_completions(required_steps, completions)
    return next((step for step in required_steps if step not in normalized), None)


def complete_deposit_step(required_steps, completions, step, method):
    if step not in required_steps:
        raise ValueError(f"Deposit step is not required: {step}")
    if method not in COMPLETION_METHODS:
        raise ValueError("Completion method must be app or quickbooks")
    normalized = normalize_step_completions(required_steps, completions)
    normalized[step] = method
    return normalized


def edit_deposit_step(required_steps, completions, step):
    if step not in required_steps:
        raise ValueError(f"Deposit step is not required: {step}")
    normalized = normalize_step_completions(required_steps, completions)
    normalized.pop(step, None)
    if step != STEP_CLOSEOUT:
        normalized.pop(STEP_CLOSEOUT, None)
    return normalized


def deposit_workflow_complete(required_steps, completions):
    normalized = normalize_step_completions(required_steps, completions)
    return all(step in normalized for step in required_steps)


def deposit_step_rows(required_steps, completions):
    normalized = normalize_step_completions(required_steps, completions)
    active = active_deposit_step(required_steps, normalized)
    rows = []
    for number, step in enumerate(required_steps, start=1):
        method = normalized.get(step)
        status = (
            "Completed in app"
            if method == "app"
            else "Finish in QuickBooks"
            if method == "quickbooks"
            else "Current"
            if step == active
            else "Pending"
        )
        rows.append(
            {
                "number": number,
                "step": step,
                "label": STEP_LABELS[step],
                "status": status,
                "complete": method is not None,
                "current": step == active,
            }
        )
    return rows
```

- [ ] **Step 8: Run workflow tests and commit**

Run:

```powershell
python -m unittest tests.test_deposit_workflow -v
git add app/deposit_workflow.py tests/test_deposit_workflow.py
git commit -m "Add guided deposit workflow state model"
```

Expected: all workflow tests PASS and the commit contains only the pure model and its tests.

---

### Task 2: Compact Today’s Deposit Steps UI

**Files:**
- Modify: `app/ui_helpers.py`
- Modify: `tests/test_membership_payments.py`
- Modify: `streamlit_app.py` near the existing `.hwfc-workflow-heading` CSS and immediately after source-total discovery.

**Interfaces:**
- Consumes: row dictionaries from `deposit_step_rows(...)`.
- Produces: `deposit_step_card_html(row: dict) -> str`, safe status-card markup used by Streamlit; completed-row Edit buttons remain native `st.button` controls.

- [ ] **Step 1: Write failing HTML helper tests**

Add to the existing UI-helper test class in `tests/test_membership_payments.py`:

```python
    def test_deposit_step_card_html_marks_number_status_and_escapes_text(self):
        from app.ui_helpers import deposit_step_card_html

        rendered = deposit_step_card_html(
            {
                "number": 2,
                "label": "Paid <In>",
                "status": "Current",
                "complete": False,
                "current": True,
            }
        )

        self.assertIn('class="hwfc-step-card is-current"', rendered)
        self.assertIn("Step 2", rendered)
        self.assertIn("Paid &lt;In&gt;", rendered)
        self.assertIn("Current", rendered)
        self.assertNotIn("Paid <In>", rendered)
```

- [ ] **Step 2: Run the helper test and verify it fails**

Run: `python -m unittest tests.test_membership_payments.MembershipPaymentTests.test_deposit_step_card_html_marks_number_status_and_escapes_text -v`

Expected: FAIL because `deposit_step_card_html` is missing.

- [ ] **Step 3: Implement the safe card helper**

Add to `app/ui_helpers.py`:

```python
def deposit_step_card_html(row: dict) -> str:
    classes = "hwfc-step-card"
    if row.get("current"):
        classes += " is-current"
    elif row.get("complete"):
        classes += " is-complete"
    return (
        f'<div class="{classes}">'
        '<div class="hwfc-step-number">'
        f'Step {int(row["number"])}</div>'
        '<div class="hwfc-step-copy">'
        f'<strong>{html.escape(str(row["label"]))}</strong>'
        f'<span>{html.escape(str(row["status"]))}</span>'
        "</div></div>"
    )
```

- [ ] **Step 4: Run the helper test and verify it passes**

Run: `python -m unittest tests.test_membership_payments.MembershipPaymentTests.test_deposit_step_card_html_marks_number_status_and_escapes_text -v`

Expected: PASS.

- [ ] **Step 5: Write failing source integration assertions for the summary**

Add one focused source test to `tests/test_membership_payments.py`:

```python
    def test_streamlit_app_renders_guided_step_summary_with_edit_controls(self):
        from pathlib import Path

        source = (Path(__file__).parents[1] / "streamlit_app.py").read_text(
            encoding="utf-8"
        )
        for required_text in (
            "Today’s Deposit Steps",
            "deposit_step_rows",
            "deposit_step_card_html",
            "Edit",
        ):
            with self.subTest(required_text=required_text):
                self.assertIn(required_text, source)
```

- [ ] **Step 6: Run the source test and verify it fails**

Run the exact test added in Step 5. Expected: FAIL because the new summary is not in `streamlit_app.py`.

- [ ] **Step 7: Add status-card styles and render the summary**

Import the Task 1 APIs and `deposit_step_card_html`, add `.hwfc-step-card`, `.is-current`, and `.is-complete` styles beside the existing workflow-heading styles, then render rows with native Edit buttons:

```python
required_steps = required_deposit_steps(
    subscription_total,
    activity_source_totals,
    coupon_bs_total,
)
workflow_completion_key = f"deposit_step_completions_{closeout_workbook_key}"
step_completions = normalize_step_completions(
    required_steps,
    st.session_state.get(workflow_completion_key),
)
st.session_state[workflow_completion_key] = step_completions
active_step = active_deposit_step(required_steps, step_completions)

st.markdown("## Today’s Deposit Steps")
for row in deposit_step_rows(required_steps, step_completions):
    card_col, action_col = st.columns([6, 1], vertical_alignment="center")
    card_col.markdown(deposit_step_card_html(row), unsafe_allow_html=True)
    if row["complete"] and action_col.button(
        "Edit",
        key=f"edit_deposit_step_{closeout_workbook_key}_{row['step']}",
    ):
        st.session_state[workflow_completion_key] = edit_deposit_step(
            required_steps,
            step_completions,
            row["step"],
        )
        if row["step"] != STEP_CLOSEOUT:
            st.session_state.pop(closeout_preview_key, None)
        st.rerun()
```

Move source-total discovery above this block. Define `closeout_payload_key` and `closeout_preview_key` immediately after `closeout_workbook_key`, before summary Edit controls reference them.

- [ ] **Step 8: Run focused tests and commit**

Run:

```powershell
python -m unittest tests.test_deposit_workflow -v
python -m unittest tests.test_membership_payments -v
git add app/ui_helpers.py streamlit_app.py tests/test_membership_payments.py
git commit -m "Add guided deposit step summary"
```

Expected: workflow and membership/UI tests PASS.

---

### Task 3: Persist and Reconstruct Hidden Activity Payloads

**Files:**
- Modify: `streamlit_app.py` in Member Share Payments, Donations, Paid In, Paid Out, and Coupons Receivable sections.
- Modify: `tests/test_membership_payments.py`
- Modify: `tests/test_activity_breakdowns.py`

**Interfaces:**
- Consumes: `active_step`, `required_steps`, `step_completions`, `complete_deposit_step(...)`, existing membership saved-payment state, `normalize_activity_section(...)`, and `reconcile_coupon_receivable(...)`.
- Produces stable section-state keys:
  - `activity_saved_section_{activity_key}_{workbook_key}` containing a normalized activity section.
  - `coupon_saved_payload_{workbook_key}` containing `mode`, `closeout_total`, `ncg_total`, and `mfg_total`.
  - Existing `membership_saved_payments_{workbook_key}` remains the canonical automatic membership payload.

- [ ] **Step 1: Write failing tests for persistence hooks and one-active-step guards**

Add source-level assertions that require canonical payload keys, Save actions, and active-step guards:

```python
    def test_guided_sections_persist_payloads_and_render_only_when_active(self):
        from pathlib import Path

        source = (Path(__file__).parents[1] / "streamlit_app.py").read_text(
            encoding="utf-8"
        )
        for required_text in (
            "activity_saved_section_",
            "coupon_saved_payload_",
            "Save Member Share Payments & Continue",
            "Save Donations & Continue",
            "Save Paid In & Continue",
            "Save Paid Out & Continue",
            "Save Coupons & Continue",
            "active_step == STEP_MEMBER_SHARES",
            "active_step == STEP_COUPONS",
            'deposit_step_completions_{closeout_workbook_key}',
            "activity_detection_valid",
        ):
            with self.subTest(required_text=required_text):
                self.assertIn(required_text, source)
```

Add an activity regression proving persisted normalized sections can rebuild the overall payload while hidden:

```python
    def test_normalized_saved_sections_rebuild_complete_payload(self):
        api = self.activity_api()
        original = self.complete_payload()
        saved = {
            key: api["normalize_section"](key, original[key])
            for key in ("donation", "paid_in", "paid_out")
        }
        rebuilt = api["normalize"](saved)
        self.assertEqual(api["actuals"](rebuilt), api["actuals"](original))
```

- [ ] **Step 2: Run the new tests and verify the source assertion fails**

Run:

```powershell
python -m unittest tests.test_activity_breakdowns.ActivityBreakdownTests.test_normalized_saved_sections_rebuild_complete_payload -v
python -m unittest tests.test_membership_payments -v
```

Expected: activity normalization PASS; guided source assertion FAIL because persistence hooks and buttons are absent.

- [ ] **Step 3: Guard Member Share Payments and reconstruct hidden membership state**

Keep source-total status messaging above the guide. Wrap the current member workflow block beginning with `if subscription_total > 0:` and ending after its QuickBooks-breakdown validation inside `if active_step == STEP_MEMBER_SHARES:`. Preserve its widgets, payment add/remove behavior, plan guide, and validation unchanged. Insert these completion transitions after the existing mode and reconciliation checks:

```python
if STEP_MEMBER_SHARES in required_steps:
    membership_choice_key = f"membership_handling_{closeout_workbook_key}"
    saved_payments_key = f"membership_saved_payments_{closeout_workbook_key}"
    saved_choice = st.session_state.get(membership_choice_key)
    membership_mode = membership_mode_from_choice(saved_choice)
    membership_payments = list(st.session_state.get(saved_payments_key, []))

if active_step == STEP_MEMBER_SHARES and membership_mode == "manual":
    st.session_state[workflow_completion_key] = complete_deposit_step(
        required_steps, step_completions, STEP_MEMBER_SHARES, "quickbooks"
    )
    st.rerun()

if (
    active_step == STEP_MEMBER_SHARES
    and membership_mode == "automatic"
    and membership_valid
    and st.button("Save Member Share Payments & Continue", type="primary")
):
    st.session_state[workflow_completion_key] = complete_deposit_step(
        required_steps, step_completions, STEP_MEMBER_SHARES, "app"
    )
    st.rerun()

if active_step != STEP_MEMBER_SHARES and STEP_MEMBER_SHARES in step_completions:
    try:
        build_membership_lines(
            membership_payments,
            expected_subscription_total=subscription_total,
            handling_mode=membership_mode,
        )
    except ValueError as exc:
        st.session_state[workflow_completion_key] = edit_deposit_step(
            required_steps, step_completions, STEP_MEMBER_SHARES
        )
        st.error(f"Saved Member Share Payments need review: {exc}", icon="🚫")
        st.rerun()
```

- [ ] **Step 4: Persist each activity section and rebuild hidden activity payloads**

Initialize all three sections to QuickBooks mode, then replace detected completed sections from their canonical saved key:

```python
activity_payload = {
    key: {"mode": "quickbooks", "rows": []}
    for key in ("donation", "paid_in", "paid_out")
}
for activity_key in activity_workflow_keys(activity_source_totals):
    saved_section_key = (
        f"activity_saved_section_{activity_key}_{closeout_workbook_key}"
    )
    if activity_key in step_completions:
        activity_payload[activity_key] = normalize_activity_section(
            activity_key,
            st.session_state[saved_section_key],
        )
```

Wrap the current per-activity form body inside `if active_step == activity_key:`. Keep its exact Donation, Paid In, and Paid Out widgets. A manual choice stores `{"mode": "quickbooks", "rows": []}`, completes with method `quickbooks`, and reruns. A valid in-app form displays the exact category-specific label from `f"Save {activity_title} & Continue"`; clicking it stores the normalized section, completes with method `app`, and reruns.

If a completed section key is missing or invalid, call `edit_deposit_step(...)`, display `Saved <label> details need to be reviewed again`, and rerun instead of silently reverting to QuickBooks mode.

Set `activity_detection_valid = True` before `read_activity_source_totals(...)`. In its exception handler, set it to `False` in addition to showing the existing warning. Do not mark any activity step complete from zero defaults after a detection failure.

- [ ] **Step 5: Persist Coupons and handle zero-coupon Closeout days**

Render the existing coupon form only when `active_step == STEP_COUPONS`. Store a canonical payload after validation:

```python
coupon_saved_key = f"coupon_saved_payload_{closeout_workbook_key}"
coupon_payload = {
    "mode": coupon_mode,
    "closeout_total": float(coupon_closeout_total),
    "ncg_total": float(coupon_ncg_total),
    "mfg_total": float(coupon_mfg_total),
}
```

A manual choice stores QuickBooks mode, completes immediately, and reruns. Valid in-app values expose `Save Coupons & Continue`; clicking saves the payload, marks method `app`, and reruns. Hidden completion reconstructs the four local coupon variables from this payload and reruns `reconcile_coupon_receivable(...)` to prove freshness.

When `STEP_COUPONS` is not required, set QuickBooks-compatible zero defaults for standalone IIF arguments and let the later Closeout integration treat Vendor Coupons actual as zero. Do not call the old `coupon_workflow_is_required(...)` with the employee’s later Closeout choice because the guided list must remain stable.

- [ ] **Step 6: Run focused tests and commit**

Run:

```powershell
python -m unittest tests.test_deposit_workflow tests.test_activity_breakdowns tests.test_membership_payments -v
git add streamlit_app.py tests/test_activity_breakdowns.py tests/test_membership_payments.py
git commit -m "Guide and persist deposit breakdown steps"
```

Expected: all focused tests PASS; no accounting module output tests change.

---

### Task 4: Closeout Completion, Edit Invalidation, and Final IIF Gate

**Files:**
- Modify: `streamlit_app.py` in Closeout Sheet rendering and final `Validate & Prepare IIF` button.
- Modify: `tests/test_membership_payments.py`
- Modify: `tests/test_deposit_workflow.py`

**Interfaces:**
- Consumes: hidden reconstructed `membership_payments`, `membership_mode`, `activity_payload`, coupon values, `activity_detection_valid`, existing `closeout_payload_key`, existing `closeout_preview_key`, and `deposit_workflow_complete(...)`.
- Produces: Closeout completion method in `deposit_step_completions_{workbook_key}` and a final `guided_workflow_ready` boolean used by the existing IIF button.

- [ ] **Step 1: Write failing Closeout and final-gate source tests**

Add assertions for the required active-step guard, manual completion, preview invalidation, and final gate:

```python
    def test_closeout_is_final_guided_step_and_final_button_uses_workflow_gate(self):
        from pathlib import Path

        source = (Path(__file__).parents[1] / "streamlit_app.py").read_text(
            encoding="utf-8"
        )
        for required_text in (
            "active_step == STEP_CLOSEOUT",
            "deposit_workflow_complete",
            "guided_workflow_ready",
            "st.session_state.pop(closeout_preview_key, None)",
        ):
            with self.subTest(required_text=required_text):
                self.assertIn(required_text, source)
        self.assertIn("or not guided_workflow_ready", source)
```

Extend `tests/test_deposit_workflow.py` to prove editing Closeout clears only Closeout:

```python
    def test_editing_closeout_preserves_every_earlier_completion(self):
        api = self.workflow_api()
        steps = ("paid_in", "paid_out", "closeout")
        completed = {
            "paid_in": "app",
            "paid_out": "quickbooks",
            "closeout": "app",
        }
        self.assertEqual(
            api["edit_deposit_step"](steps, completed, "closeout"),
            {"paid_in": "app", "paid_out": "quickbooks"},
        )
```

- [ ] **Step 2: Run the new tests and verify the source test fails**

Run the two exact tests from Step 1. Expected: pure transition test PASS after Task 1; Streamlit source test FAIL.

- [ ] **Step 3: Render Closeout only when active and complete manual mode immediately**

Replace the unconditional Closeout section with an active-step guard:

```python
if uploaded and active_step == STEP_CLOSEOUT:
    closeout_choice = st.radio(
        "How should the Closeout Sheet be handled?",
        options=[
            "Breakdown in app using Closeout Sheet",
            "Finish manually in QuickBooks",
        ],
        horizontal=True,
        index=None,
        key=f"closeout_handling_{closeout_workbook_key}",
    )
    if closeout_choice == "Finish manually in QuickBooks":
        closeout_payload = {"mode": "manual"}
        st.session_state[closeout_payload_key] = closeout_payload
        st.session_state[workflow_completion_key] = complete_deposit_step(
            required_steps,
            step_completions,
            STEP_CLOSEOUT,
            "quickbooks",
        )
        st.rerun()
```

Indent the current in-app Closeout reconciliation block under `closeout_choice == "Breakdown in app using Closeout Sheet"`; do not alter its field definitions or calculations.

When Closeout is already complete and hidden, reconstruct `closeout_payload` from `closeout_payload_key`. If missing or invalid, clear only Closeout completion and reopen the step.

- [ ] **Step 4: Mark a reviewed in-app Closeout complete without changing reconciliation**

After the existing review path sets `closeout_valid = True` and stores the normalized payload and fresh preview, expose one explicit final action:

```python
if closeout_valid and st.button(
    "Save Closeout Sheet & Continue",
    type="primary",
    use_container_width=True,
):
    st.session_state[workflow_completion_key] = complete_deposit_step(
        required_steps,
        step_completions,
        STEP_CLOSEOUT,
        "app",
    )
    st.rerun()
```

Retain all existing review confirmation, coupon/activity link readiness, fingerprint freshness, final POS approval, and validation messages.

- [ ] **Step 5: Invalidate Closeout preview on every earlier Edit and gate the IIF button**

In the summary Edit handler, always clear the selected completion. For any step other than Closeout, additionally execute:

```python
st.session_state.pop(closeout_preview_key, None)
```

Keep the Closeout payload inputs stored, but require its preview and completion to be recreated. Before the settlement/IIF controls calculate the disabled state, compute:

```python
step_completions = normalize_step_completions(
    required_steps,
    st.session_state.get(workflow_completion_key),
)
guided_workflow_ready = deposit_workflow_complete(
    required_steps,
    step_completions,
) and activity_detection_valid
```

Add `or not guided_workflow_ready` to the existing disabled expression. Preserve every existing membership, coupon, activity, Closeout, workbook, and card-settlement condition as defense in depth.

- [ ] **Step 6: Add a completion summary after all steps are done**

When `guided_workflow_ready` is true, show one compact success message immediately below the step summary:

```python
st.success(
    "All deposit steps are complete. Validate and prepare the QuickBooks IIF below.",
    icon="✅",
)
```

Do not automatically run or download the IIF.

- [ ] **Step 7: Run focused tests and commit**

Run:

```powershell
python -m unittest tests.test_deposit_workflow tests.test_activity_breakdowns tests.test_membership_payments tests.test_closeout_reconciliation -v
git add streamlit_app.py tests/test_deposit_workflow.py tests/test_membership_payments.py
git commit -m "Complete guided Closeout and IIF gating"
```

Expected: all focused tests PASS.

---

### Task 5: Full Regression and Guided Workflow Smoke Verification

**Files:**
- Modify only if a failing regression identifies a defect in files already named above.
- Test: entire `tests/` suite.

**Interfaces:**
- Consumes: completed implementation from Tasks 1–4.
- Produces: verified app behavior without accounting-output regressions.

- [ ] **Step 1: Run syntax and import checks**

Run:

```powershell
python -m py_compile streamlit_app.py app/deposit_workflow.py app/ui_helpers.py
python -c "import app.deposit_workflow; import app.ui_helpers"
```

Expected: exit code 0 and no output.

- [ ] **Step 2: Run the complete automated suite**

Run:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Expected: all existing and new tests PASS. Do not accept changed account, memo, sign, source-total, or IIF-order expectations merely to make tests green.

- [ ] **Step 3: Smoke-test a deposit with no optional activities**

Run the app with a representative workbook whose Subscription Revenue, Donations, Paid In, Paid Out, and Coupons Receivable totals are zero. Verify:

```text
Today’s Deposit Steps
Step 1  Closeout Sheet  Current
```

Choose `Finish manually in QuickBooks`; verify the step becomes `Finish in QuickBooks` and the final IIF action unlocks only when card settlement and existing validations pass.

- [ ] **Step 4: Smoke-test a deposit with multiple optional activities**

Use a representative workbook containing Member Shares, Paid In, Coupons Receivable, and no Donations/Paid Out. Verify this exact visible order:

```text
Step 1  Member Share Payments
Step 2  Paid In
Step 3  Coupons Receivable
Step 4  Closeout Sheet
```

Verify only Step 1 initially shows full controls, `Finish manually in QuickBooks` advances immediately, valid in-app steps require `Save & Continue`, and later saved data survives an Edit of Step 1.

- [ ] **Step 5: Smoke-test Closeout invalidation**

Complete all steps in app, then select Edit on Paid In. Verify:

```text
Paid In       Current
Closeout Sheet Pending
```

Confirm the prior Paid In rows remain visible, the prior Closeout inputs remain available, the old Closeout preview is gone, and `Validate & Prepare IIF` stays disabled until Paid In and Closeout are saved again.

- [ ] **Step 6: Review the final diff for scope and commit any verification fix**

Run:

```powershell
git diff --check
git status --short
git diff --stat
```

Expected: no whitespace errors, no unrelated files, and no accounting-engine changes. If smoke testing required a correction, rerun Steps 1–5, then commit only that correction:

```powershell
git add app/deposit_workflow.py app/ui_helpers.py streamlit_app.py tests/test_deposit_workflow.py tests/test_activity_breakdowns.py tests/test_membership_payments.py
git commit -m "Fix guided deposit workflow regression"
```
