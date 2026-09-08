# Guided Upload Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current three-column upload area with the approved guided **Upload deposit reports** panel while preserving all file parsing, validation, and one-time scrolling behavior.

**Architecture:** Add a small pure UI-state/markup module for upload progress, status summaries, and safely escaped file details. Keep native Streamlit uploaders and all existing parsing in `streamlit_app.py`, but reorganize their presentation into one bordered intake panel. Extract the existing long help sections into a focused renderer so they can appear beneath the intake panel without duplicating or changing their content.

**Tech Stack:** Python 3, Streamlit 1.37+, HTML/CSS rendered through Streamlit Markdown, standard-library `html`, `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-03-guided-upload-intake-design.md`

## Global Constraints

- Preserve all existing workbook parsing, accounting calculations, validation rules, generated IIF behavior, session persistence, and Start Over behavior.
- Keep both XLSX/XLSM upload controls visible and usable at the same time.
- Keep the current 200 MB upload limit and accepted file types.
- Today’s Deposit Steps remain hidden until both files are supplied and receive exactly one smooth scroll when the pair first becomes ready.
- Do not change Donations, Paid In, Paid Out, Coupons Receivable, Member Share Payments, Closeout Sheet, In-House Charges, or QuickBooks/IIF behavior.
- Preserve the existing Daily Workbook SOP and Tips & Known Exceptions content.
- Do not stage `.superpowers/` or existing `tests/_sales_mapping_*` artifacts.

## File Structure

- Create `app/upload_intake_ui.py`: pure upload-step state, escaped status markup, and readiness summary helpers.
- Create `app/deposit_help_ui.py`: render the existing SOP and Known Exceptions content below the upload intake.
- Modify `streamlit_app.py`: import the helpers, add upload-panel CSS, render the new layout, and retain existing parsers/validators.
- Create `tests/test_upload_intake_ui.py`: unit coverage for zero/one/two upload states, output escaping, role badges, and readiness copy.
- Modify `tests/test_membership_payments.py`: source-order and existing one-time-scroll integration regressions.

---

### Task 1: Model and render upload progress safely

**Files:**
- Create: `app/upload_intake_ui.py`
- Create: `tests/test_upload_intake_ui.py`

**Interfaces:**
- Produces: `upload_step_rows(daily_workbook_ready: bool, settlement_ready: bool) -> tuple[dict, ...]`
- Produces: `upload_stepper_html(rows) -> str`
- Produces: `upload_readiness(daily_workbook_ready: bool, settlement_ready: bool) -> dict`
- Produces: `workbook_role_badges_html(role_labels: list[tuple[str, str | None]]) -> str`
- Produces: `uploaded_file_summary_html(filename: str, detected_date: date | None, *, valid: bool, status_text: str) -> str`

- [ ] **Step 1: Write failing state-transition tests**

Create `tests/test_upload_intake_ui.py` with:

```python
import unittest
from datetime import date


class UploadIntakeUITests(unittest.TestCase):
    def test_zero_uploads_marks_daily_current_and_reports_zero_of_two(self):
        from app.upload_intake_ui import upload_readiness, upload_step_rows

        rows = upload_step_rows(False, False)
        self.assertEqual(
            [(row["label"], row["complete"], row["current"]) for row in rows],
            [
                ("Daily Workbook", False, True),
                ("Card Settlement", False, False),
                ("Ready", False, False),
            ],
        )
        self.assertEqual(upload_readiness(False, False)["label"], "0 of 2 reports added")
        self.assertEqual(upload_readiness(False, False)["percent"], 0)

    def test_one_upload_advances_current_state_without_hiding_either_report(self):
        from app.upload_intake_ui import upload_readiness, upload_step_rows

        rows = upload_step_rows(True, False)
        self.assertTrue(rows[0]["complete"])
        self.assertTrue(rows[1]["current"])
        self.assertFalse(rows[2]["complete"])
        self.assertEqual(upload_readiness(True, False)["label"], "1 of 2 reports added")
        self.assertEqual(upload_readiness(True, False)["percent"], 50)

    def test_two_uploads_complete_ready_state(self):
        from app.upload_intake_ui import upload_readiness, upload_step_rows

        rows = upload_step_rows(True, True)
        self.assertTrue(all(row["complete"] for row in rows))
        self.assertEqual(
            upload_readiness(True, True),
            {
                "count": 2,
                "percent": 100,
                "label": "2 of 2 reports added",
                "action": "Ready for Today’s Deposit Steps",
                "ready": True,
            },
        )
```

- [ ] **Step 2: Run the focused tests and verify the module is missing**

Run: `python -m unittest tests.test_upload_intake_ui.UploadIntakeUITests -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.upload_intake_ui'`.

- [ ] **Step 3: Implement the minimal state helpers**

Create `app/upload_intake_ui.py` with this state contract:

```python
from __future__ import annotations

import html
from datetime import date


def upload_step_rows(daily_workbook_ready: bool, settlement_ready: bool) -> tuple[dict, ...]:
    both_ready = bool(daily_workbook_ready and settlement_ready)
    return (
        {
            "number": 1,
            "label": "Daily Workbook",
            "complete": bool(daily_workbook_ready),
            "current": not daily_workbook_ready,
        },
        {
            "number": 2,
            "label": "Card Settlement",
            "complete": bool(settlement_ready),
            "current": bool(daily_workbook_ready and not settlement_ready),
        },
        {
            "number": 3,
            "label": "Ready",
            "complete": both_ready,
            "current": False,
        },
    )


def upload_readiness(daily_workbook_ready: bool, settlement_ready: bool) -> dict:
    count = int(bool(daily_workbook_ready)) + int(bool(settlement_ready))
    ready = count == 2
    return {
        "count": count,
        "percent": count * 50,
        "label": f"{count} of 2 reports added",
        "action": "Ready for Today’s Deposit Steps" if ready else "Continue when ready",
        "ready": ready,
    }
```

- [ ] **Step 4: Add failing markup and escaping tests**

Append these tests to `UploadIntakeUITests`:

```python
    def test_stepper_has_upload_specific_accessible_label_and_three_bubbles(self):
        from app.upload_intake_ui import upload_step_rows, upload_stepper_html

        markup = upload_stepper_html(upload_step_rows(True, False))
        self.assertIn('aria-label="Upload deposit reports progress"', markup)
        self.assertEqual(markup.count('class="hwfc-upload-stepper-bubble"'), 3)
        self.assertIn("✓", markup)
        self.assertIn("Card Settlement", markup)

    def test_role_badges_and_file_summary_escape_workbook_content(self):
        from app.upload_intake_ui import (
            uploaded_file_summary_html,
            workbook_role_badges_html,
        )

        badges = workbook_role_badges_html(
            [("Sales", "090326 <Sales>"), ("HASH", None)]
        )
        summary = uploaded_file_summary_html(
            'daily<script>.xlsx',
            date(2026, 9, 3),
            valid=True,
            status_text="Workbook verified",
        )
        self.assertIn("090326 &lt;Sales&gt;", badges)
        self.assertIn("HASH · Not detected", badges)
        self.assertNotIn("<script>", summary)
        self.assertIn("daily&lt;script&gt;.xlsx", summary)
        self.assertIn("09/03/2026", summary)
```

- [ ] **Step 5: Implement the markup helpers**

Implement markup using `html.escape` on every filename, label, sheet name, and status string. Use these exact CSS hooks so `streamlit_app.py` can style them without parsing text:

```python
def upload_stepper_html(rows) -> str:
    items = []
    for row in rows:
        state = "is-complete" if row["complete"] else "is-current" if row["current"] else "is-pending"
        bubble = "✓" if row["complete"] else str(int(row["number"]))
        items.append(
            f'<div class="hwfc-upload-stepper-item {state}" role="listitem">'
            '<div class="hwfc-upload-stepper-track">'
            f'<span class="hwfc-upload-stepper-bubble">{bubble}</span>'
            '</div><div class="hwfc-upload-stepper-label">'
            f'<span>Step {int(row["number"])}</span>'
            f'<strong>{html.escape(str(row["label"]))}</strong>'
            '</div></div>'
        )
    return (
        '<div class="hwfc-upload-stepper" role="list" '
        'aria-label="Upload deposit reports progress">'
        + "".join(items)
        + "</div>"
    )
```

`workbook_role_badges_html` must emit one `.hwfc-upload-role` element per `(label, sheet_name)` pair, include the detected sheet name when present, and include `Not detected` when absent. `uploaded_file_summary_html` must emit `.hwfc-upload-file-summary`, add `is-valid` only when `valid` is true, and omit the date line when `detected_date` is `None`.

- [ ] **Step 6: Run the new helper suite**

Run: `python -m unittest tests.test_upload_intake_ui -v`

Expected: all tests PASS.

- [ ] **Step 7: Commit the pure upload UI model**

```powershell
git add app/upload_intake_ui.py tests/test_upload_intake_ui.py
git commit -m "feat: add guided upload intake states"
```

---

### Task 2: Move help content beneath the routine upload flow

**Files:**
- Create: `app/deposit_help_ui.py`
- Modify: `streamlit_app.py`
- Modify: `tests/test_membership_payments.py`

**Interfaces:**
- Produces: `render_daily_workbook_sop(ui, *, root: Path, sop_steps: list[dict]) -> None`
- Produces: `render_known_exceptions(ui) -> None`
- Consumes: existing `ROOT`, `SOP_STEPS`, Streamlit API, and current image asset paths.

- [ ] **Step 1: Add a failing source-order regression test**

Add to `MembershipPaymentTests`:

```python
    def test_upload_intake_appears_before_optional_help_content(self):
        source = (Path(__file__).parents[1] / "streamlit_app.py").read_text(
            encoding="utf-8"
        )
        upload_heading = source.index('"Upload deposit reports"')
        daily_uploader = source.index('"Upload completed SubDept workbook"')
        settlement_uploader = source.index('"Upload Daily Card Settlement Report"')
        sop_call = source.index("render_daily_workbook_sop(")
        exceptions_call = source.index("render_known_exceptions(")
        self.assertLess(upload_heading, daily_uploader)
        self.assertLess(daily_uploader, settlement_uploader)
        self.assertLess(settlement_uploader, sop_call)
        self.assertLess(sop_call, exceptions_call)
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `python -m unittest tests.test_membership_payments.MembershipPaymentTests.test_upload_intake_appears_before_optional_help_content -v`

Expected: FAIL because the new heading and renderer calls do not exist.

- [ ] **Step 3: Extract the current help renderers without changing copy**

Create `app/deposit_help_ui.py` with `from pathlib import Path`. Mechanically move the complete body of the current `with st.expander("📘 Daily Workbook SOP", expanded=False):` block into a function with this exact signature and outer statement: `def render_daily_workbook_sop(ui, *, root: Path, sop_steps: list[dict]) -> None:` followed by `with ui.expander("📘 Daily Workbook SOP", expanded=False):`. Within the moved body, replace `ROOT` with `root`, `SOP_STEPS` with `sop_steps`, and every Streamlit receiver `st` with the injected `ui` receiver. The resulting function must retain every current markdown paragraph, nested step expander, asset filename, image caption, warning, download button, and missing-asset message.

Mechanically move the complete body of the current `with st.expander("💡 Tips & Known Exceptions · WIP", expanded=False):` block into `def render_known_exceptions(ui) -> None:` followed by `with ui.expander("💡 Tips & Known Exceptions · WIP", expanded=False):`. Replace every Streamlit receiver `st` with `ui` and retain every existing tip card, disclosure, QuickBooks reminder, and future-tip line verbatim. Do not rewrite or shorten user guidance while moving it.

- [ ] **Step 4: Import the renderers but call them only below the complete upload panel**

Add:

```python
from app.deposit_help_ui import (
    render_daily_workbook_sop,
    render_known_exceptions,
)
```

Remove the original top-level expander blocks. After the upload panel, its validation messages, and readiness footer, render:

```python
st.markdown('<div class="hwfc-upload-help-label">Need help?</div>', unsafe_allow_html=True)
render_daily_workbook_sop(st, root=ROOT, sop_steps=SOP_STEPS)
render_known_exceptions(st)
```

- [ ] **Step 5: Run the source-order and import checks**

Run:

```powershell
python -m unittest tests.test_membership_payments.MembershipPaymentTests.test_upload_intake_appears_before_optional_help_content -v
python -m py_compile app/deposit_help_ui.py streamlit_app.py
```

Expected: test PASS and compilation exits successfully.

- [ ] **Step 6: Commit the help-content move**

```powershell
git add app/deposit_help_ui.py streamlit_app.py tests/test_membership_payments.py
git commit -m "refactor: place deposit help after uploads"
```

---

### Task 3: Build the approved Streamlit upload panel

**Files:**
- Modify: `streamlit_app.py`
- Modify: `tests/test_membership_payments.py`

**Interfaces:**
- Consumes: all helpers from `app.upload_intake_ui`.
- Preserves: `update_upload_pair_readiness(...)` and `deposit_steps_scroll_key` behavior.
- Preserves: `render_card_settlement_verification(...)` semantics and existing workbook-role/date detection.

- [ ] **Step 1: Add failing integration assertions for the approved layout**

Add to `MembershipPaymentTests`:

```python
    def test_streamlit_app_uses_guided_upload_panel_without_changing_readiness_gate(self):
        source = (Path(__file__).parents[1] / "streamlit_app.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("Upload deposit reports", source)
        self.assertIn("Add both reports for today. We’ll check the dates and contents automatically.", source)
        self.assertIn("upload_stepper_html(", source)
        self.assertIn("workbook_role_badges_html(", source)
        self.assertIn("uploaded_file_summary_html(", source)
        self.assertIn("upload_readiness(", source)
        self.assertEqual(source.count("update_upload_pair_readiness("), 1)
        self.assertIn("daily_workbook_ready=uploaded is not None", source)
        self.assertIn("settlement_ready=settlement_file is not None", source)

    def test_both_native_uploaders_remain_visible_in_the_same_intake_block(self):
        source = (Path(__file__).parents[1] / "streamlit_app.py").read_text(
            encoding="utf-8"
        )
        panel_start = source.index("upload_progress_placeholder = st.empty()")
        panel_end = source.index("upload_pair_readiness_key =", panel_start)
        panel = source[panel_start:panel_end]
        self.assertIn('"Upload completed SubDept workbook"', panel)
        self.assertIn('"Upload Daily Card Settlement Report"', panel)
```

- [ ] **Step 2: Run the two integration tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_membership_payments.MembershipPaymentTests.test_streamlit_app_uses_guided_upload_panel_without_changing_readiness_gate tests.test_membership_payments.MembershipPaymentTests.test_both_native_uploaders_remain_visible_in_the_same_intake_block -v
```

Expected: both tests FAIL because the old three-column input block is still present.

- [ ] **Step 3: Import the upload helpers**

Add:

```python
from app.upload_intake_ui import (
    upload_readiness,
    upload_step_rows,
    upload_stepper_html,
    uploaded_file_summary_html,
    workbook_role_badges_html,
)
```

- [ ] **Step 4: Replace the old report-date/workbook/settlement columns with one intake panel**

Render the heading first:

```python
st.markdown(
    '<div class="hwfc-upload-heading">'
    '<div class="hwfc-upload-title">Upload deposit reports</div>'
    '<div class="hwfc-upload-subtitle">Add both reports for today. '
    'We’ll check the dates and contents automatically.</div>'
    '</div>',
    unsafe_allow_html=True,
)
```

Inside one `st.container(border=True)`, create `upload_progress_placeholder = st.empty()`, then two rows with `st.columns([0.46, 0.54], gap="large")`. The left side of each row contains its numbered label and explanatory copy; the right side contains the existing native `st.file_uploader` call with its current key, file types, and help text. Do not conditionally hide either uploader.

After parsing the files, fill `upload_progress_placeholder` with:

```python
upload_progress_placeholder.markdown(
    upload_stepper_html(
        upload_step_rows(uploaded is not None, settlement_file is not None)
    ),
    unsafe_allow_html=True,
)
```

For the Daily Workbook row, render role badges for:

```python
[
    ("Sales", roles.get("sales")),
    ("Coupons", roles.get("coupons")),
    ("Discounts", roles.get("discounts")),
    ("Balance Sheet", roles.get("bs")),
    ("HASH", roles.get("hash")),
]
```

Its green summary condition is `deposit_date is not None and all(roles.get(key) for key in ("sales", "coupons", "discounts", "bs", "hash"))`. For Card Settlement, use `settlement_source_ok` as the green summary condition. Keep date mismatch, missing role, unreadable date, and exact-header messages adjacent to the corresponding row.

- [ ] **Step 5: Render the readiness footer without changing the existing scroll gate**

After both uploader values are known, call the existing `update_upload_pair_readiness` exactly once with presence checks. Render the result of `upload_readiness(uploaded is not None, settlement_file is not None)` as `.hwfc-upload-readiness`, including `.hwfc-upload-progress-fill` with an inline width restricted to `0`, `50`, or `100` percent and action text **Continue when ready** or **Ready for Today’s Deposit Steps**.

Do not add a second Continue button. The existing automatic one-time smooth scroll remains the transition.

- [ ] **Step 6: Add panel, stepper, status, and responsive CSS**

Add CSS hooks under the existing theme variables:

- `.hwfc-upload-heading`, `.hwfc-upload-title`, `.hwfc-upload-subtitle`
- `.hwfc-upload-stepper`, `.hwfc-upload-stepper-item`, `.hwfc-upload-stepper-track`, `.hwfc-upload-stepper-bubble`, `.hwfc-upload-stepper-label`
- `.hwfc-upload-card-copy`, `.hwfc-upload-role-list`, `.hwfc-upload-role`
- `.hwfc-upload-file-summary`, `.hwfc-upload-file-summary.is-valid`
- `.hwfc-upload-readiness`, `.hwfc-upload-progress`, `.hwfc-upload-progress-fill`, `.hwfc-upload-ready-action`
- `.hwfc-upload-help-label`

Use the existing colors `#0E1117`, `#161B22`, `#30363D`, `#315F3A`, `#78A85B`, `#A7B0A3`, and `#F4F1E8`. At `max-width: 700px`, reduce label sizes, allow the stepper items to use `min-width: 96px`, and make upload detail text wrap with `overflow-wrap: anywhere`. Do not hide status text at narrow widths.

- [ ] **Step 7: Run the focused UI and scrolling tests**

Run:

```powershell
python -m unittest tests.test_upload_intake_ui -v
python -m unittest tests.test_membership_payments.MembershipPaymentTests.test_streamlit_app_uses_guided_upload_panel_without_changing_readiness_gate tests.test_membership_payments.MembershipPaymentTests.test_both_native_uploaders_remain_visible_in_the_same_intake_block tests.test_membership_payments.MembershipPaymentTests.test_deposit_steps_unlock_and_scroll_once_when_both_uploads_are_ready tests.test_membership_payments.MembershipPaymentTests.test_card_settlement_verification_is_rendered_before_guided_steps -v
python -m py_compile streamlit_app.py
```

Expected: all tests PASS and compilation exits successfully.

- [ ] **Step 8: Commit the approved upload panel**

```powershell
git add streamlit_app.py tests/test_membership_payments.py
git commit -m "feat: guide daily deposit report uploads"
```

---

### Task 4: Run full regression and visual acceptance checks

**Files:**
- Modify: only a file with a demonstrated regression; otherwise no source changes.

**Interfaces:**
- Consumes: completed Tasks 1–3.
- Produces: verified upload UI ready for backup/push.

- [ ] **Step 1: Run the complete automated suite**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Expected: all tests PASS. If a test cannot create an existing repository temp directory because of local filesystem permissions, rerun using a writable temporary directory and confirm the failure is environmental before changing code.

- [ ] **Step 2: Perform empty-state visual verification**

Launch the app with `streamlit run streamlit_app.py`. Confirm:

- **Upload deposit reports** is the first routine action.
- Both uploaders are visible.
- Daily Workbook is current, Card Settlement and Ready are pending.
- Footer reads **0 of 2 reports added** and **Continue when ready**.
- SOP and Known Exceptions appear below the upload panel.

- [ ] **Step 3: Perform one-file visual verification**

Upload a valid Daily Workbook only. Confirm its filename, detected date, and five workbook-role badges appear; the Daily Workbook step completes; Card Settlement becomes current; footer reads **1 of 2 reports added**; and no scroll to Today’s Deposit Steps occurs.

- [ ] **Step 4: Perform two-file and error-state visual verification**

Upload a valid Card Settlement for the same date. Confirm the second file shows its filename/date, the footer reads **2 of 2 reports added**, and the page smooth-scrolls exactly once to Today’s Deposit Steps. Replace one file with a wrong-date or wrong-header sample and confirm the existing explicit warning stays adjacent to that report and no accounting output changes.

- [ ] **Step 5: Review the final diff for scope**

Run:

```powershell
git diff --check
git status --short
git diff --stat HEAD~3..HEAD
```

Confirm only the planned UI, help-renderer, tests, spec, and plan files are tracked. Confirm `.superpowers/` and `tests/_sales_mapping_*` remain untracked.

- [ ] **Step 6: Record any verification-only adjustment**

If visual or regression verification required a source correction, stage only the affected planned file and its regression test, then run:

```powershell
git commit -m "fix: polish guided upload intake"
```

If no correction was needed, do not create an empty commit.
