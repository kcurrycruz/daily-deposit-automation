# Compact Operations UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add a compact operational status summary to the existing daily deposit interface while preserving the horizontal upload row and current guided bubble stepper.

**Architecture:** Add one focused UI module that converts existing upload, validation, workflow, and IIF state into three display values and safe HTML. Reserve its visual location near the top of streamlit_app.py, populate it after the existing workflow state is known, and leave the accounting engine untouched.

**Tech Stack:** Python 3, Streamlit, HTML/CSS through st.markdown, standard-library unittest

**Spec:** docs/superpowers/specs/2026-09-08-compact-operations-ui-design.md

## Global Constraints

- Do not change accounting mappings, transaction-building logic, or IIF output.
- Keep the horizontal Report Date, Daily Workbook, and Card Settlement upload row.
- Keep Need Help, the full SOP pictures and steps, Tips & Known Exceptions, Start Over, and collapsed Run History.
- Show only detected guided activities and keep Closeout Sheet last.
- Keep the horizontal bubble stepper during guided breakdown; do not add a left rail.
- Preserve smooth scrolling, editable defaults, completed-step editing, validation messages, and saved entries.
- Preserve Donation’s editable $100 default; Paid In positive and Paid Out negative handling; and the approved member-plan defaults.
- Preserve Books with Magazines, CDTA Star Pass mapping and memo calculation, and nonstandard or unrecognized amounts routed to TBA.
- Keep Card Settlement verification directly below workbook validation.
- Do not push until the user reviews the working local app.

---

### Task 1: Compact Operations status model and renderer

**Files:**
- Create: app/operations_status_ui.py
- Create: tests/test_operations_status_ui.py

**Interfaces:**
- Consumes: datetime.date or None plus existing upload, validation, workflow-complete, and IIF-generated booleans.
- Produces: OperationsStatus, build_operations_status, operations_status_html, and render_operations_status.

- [ ] **Step 1: Write the failing state tests**

~~~python
import unittest
from datetime import date


class OperationsStatusUITests(unittest.TestCase):
    def test_waiting_state_before_upload(self):
        from app.operations_status_ui import build_operations_status

        status = build_operations_status(
            deposit_date=None,
            daily_uploaded=False,
            settlement_uploaded=False,
            workbook_valid=False,
            settlement_valid=False,
            workflow_complete=False,
            iif_generated=False,
        )
        self.assertEqual(status.deposit_date, "Waiting for workbook")
        self.assertEqual(status.files, "0 of 2 uploaded")
        self.assertEqual(status.iif, "Not ready")

    def test_one_file_names_the_missing_report(self):
        from app.operations_status_ui import build_operations_status

        status = build_operations_status(
            deposit_date=date(2026, 9, 8),
            daily_uploaded=True,
            settlement_uploaded=False,
            workbook_valid=True,
            settlement_valid=False,
            workflow_complete=False,
            iif_generated=False,
        )
        self.assertEqual(status.deposit_date, "09/08/2026")
        self.assertEqual(status.files, "1 of 2 uploaded · Card Settlement needed")

    def test_verified_files_direct_operator_to_guided_steps(self):
        from app.operations_status_ui import build_operations_status

        status = build_operations_status(
            deposit_date=date(2026, 9, 8),
            daily_uploaded=True,
            settlement_uploaded=True,
            workbook_valid=True,
            settlement_valid=True,
            workflow_complete=False,
            iif_generated=False,
        )
        self.assertEqual(status.files, "2 of 2 verified")
        self.assertEqual(status.iif, "Complete guided steps")

    def test_complete_and_generated_states_are_distinct(self):
        from app.operations_status_ui import build_operations_status

        ready = build_operations_status(
            deposit_date=date(2026, 9, 8),
            daily_uploaded=True,
            settlement_uploaded=True,
            workbook_valid=True,
            settlement_valid=True,
            workflow_complete=True,
            iif_generated=False,
        )
        generated = build_operations_status(
            deposit_date=date(2026, 9, 8),
            daily_uploaded=True,
            settlement_uploaded=True,
            workbook_valid=True,
            settlement_valid=True,
            workflow_complete=True,
            iif_generated=True,
        )
        self.assertEqual(ready.iif, "Ready to prepare IIF")
        self.assertEqual(generated.iif, "Ready to download")

    def test_uploaded_invalid_files_need_attention(self):
        from app.operations_status_ui import build_operations_status

        status = build_operations_status(
            deposit_date=None,
            daily_uploaded=True,
            settlement_uploaded=True,
            workbook_valid=False,
            settlement_valid=False,
            workflow_complete=False,
            iif_generated=False,
        )
        self.assertEqual(status.files, "2 of 2 uploaded · Needs attention")
        self.assertEqual(status.iif, "Needs attention")
~~~

- [ ] **Step 2: Run the new tests**

Run:

~~~powershell
& $pythonExe -m unittest tests.test_operations_status_ui -v
~~~

Expected: FAIL because app.operations_status_ui does not exist.

- [ ] **Step 3: Implement the status rules**

~~~python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import html


@dataclass(frozen=True)
class OperationsStatus:
    deposit_date: str
    files: str
    iif: str
    state: str


def build_operations_status(
    *,
    deposit_date: date | None,
    daily_uploaded: bool,
    settlement_uploaded: bool,
    workbook_valid: bool,
    settlement_valid: bool,
    workflow_complete: bool,
    iif_generated: bool,
) -> OperationsStatus:
    upload_count = int(daily_uploaded) + int(settlement_uploaded)
    date_label = deposit_date.strftime("%m/%d/%Y") if deposit_date else "Waiting for workbook"

    if upload_count == 0:
        files_label = "0 of 2 uploaded"
    elif upload_count == 1:
        missing = "Card Settlement" if daily_uploaded else "Daily Workbook"
        files_label = f"1 of 2 uploaded · {missing} needed"
    elif workbook_valid and settlement_valid:
        files_label = "2 of 2 verified"
    else:
        files_label = "2 of 2 uploaded · Needs attention"

    if iif_generated:
        iif_label, state = "Ready to download", "ready"
    elif upload_count == 2 and (not workbook_valid or not settlement_valid):
        iif_label, state = "Needs attention", "attention"
    elif workflow_complete:
        iif_label, state = "Ready to prepare IIF", "ready"
    elif workbook_valid and settlement_valid:
        iif_label, state = "Complete guided steps", "active"
    else:
        iif_label, state = "Not ready", "waiting"

    return OperationsStatus(date_label, files_label, iif_label, state)
~~~

- [ ] **Step 4: Add escaped HTML and the Streamlit renderer**

~~~python
def operations_status_html(status: OperationsStatus) -> str:
    values = (
        ("Deposit date", status.deposit_date),
        ("Files", status.files),
        ("IIF status", status.iif),
    )
    items = "".join(
        '<div class="hwfc-ops-status-item">'
        f"<span>{html.escape(label)}</span>"
        f"<strong>{html.escape(value)}</strong>"
        "</div>"
        for label, value in values
    )
    return (
        f'<div class="hwfc-ops-status is-{html.escape(status.state)}" '
        'aria-label="Deposit status">'
        f"{items}</div>"
    )


def render_operations_status(ui, status: OperationsStatus) -> None:
    ui.markdown(operations_status_html(status), unsafe_allow_html=True)
~~~

- [ ] **Step 5: Add an HTML safety test**

~~~python
    def test_status_html_is_safe_and_has_three_labels(self):
        from app.operations_status_ui import OperationsStatus, operations_status_html

        markup = operations_status_html(
            OperationsStatus("<date>", "2 of 2 verified", "Complete guided steps", "active")
        )
        self.assertEqual(markup.count("hwfc-ops-status-item"), 3)
        self.assertIn("Deposit date", markup)
        self.assertIn("Files", markup)
        self.assertIn("IIF status", markup)
        self.assertIn("&lt;date&gt;", markup)
        self.assertNotIn("<date>", markup)
~~~

- [ ] **Step 6: Run the focused tests**

Run:

~~~powershell
& $pythonExe -m unittest tests.test_operations_status_ui -v
~~~

Expected: all tests PASS.

- [ ] **Step 7: Create a local checkpoint**

~~~powershell
& $gitExe add -- app/operations_status_ui.py tests/test_operations_status_ui.py
& $gitExe commit -m "ui: add compact deposit operations status"
~~~

Do not push.

---

### Task 2: Integrate status into the existing Streamlit flow

**Files:**
- Modify: streamlit_app.py imports, CSS, header area, upload validation area, and final action area
- Modify: tests/test_deposit_help_ui.py
- Modify: tests/test_membership_payments.py

**Interfaces:**
- Consumes: build_operations_status and render_operations_status from Task 1.
- Produces: one top-page status slot populated from existing application state.

- [ ] **Step 1: Write the failing page-order test**

~~~python
def test_compact_status_is_between_help_and_upload_inputs(self):
    source = (Path(__file__).parents[1] / "streamlit_app.py").read_text(
        encoding="utf-8"
    )
    help_position = source.index("render_known_exceptions(st)")
    slot_position = source.index("operations_status_slot = st.empty()")
    upload_position = source.index("upload_render = render_upload_inputs(")
    self.assertLess(help_position, slot_position)
    self.assertLess(slot_position, upload_position)
~~~

- [ ] **Step 2: Run the placement test**

~~~powershell
& $pythonExe -m unittest tests.test_deposit_help_ui.DepositHelpUITests.test_compact_status_is_between_help_and_upload_inputs -v
~~~

Expected: FAIL because operations_status_slot is absent.

- [ ] **Step 3: Import the status helpers and reserve the top location**

Add the imports:

~~~python
from app.operations_status_ui import (
    build_operations_status,
    render_operations_status,
)
~~~

Immediately after the existing help renderers, add:

~~~python
operations_status_slot = st.empty()
~~~

Keep the four-part workflow bar and horizontal upload row below it.

- [ ] **Step 4: Write the failing wiring test**

~~~python
def test_streamlit_status_uses_existing_validation_and_workflow_state(self):
    source = (Path(__file__).parents[1] / "streamlit_app.py").read_text(
        encoding="utf-8"
    )
    self.assertIn("daily_uploaded=uploaded is not None", source)
    self.assertIn("settlement_uploaded=settlement_file is not None", source)
    self.assertIn("workbook_valid=workbook_status_valid", source)
    self.assertIn("settlement_valid=settlement_status_valid", source)
    self.assertIn("workflow_complete=guided_workflow_ready", source)
    self.assertIn("iif_generated=download_details is not None", source)
~~~

- [ ] **Step 5: Run the wiring test**

~~~powershell
& $pythonExe -m unittest tests.test_membership_payments.MembershipPaymentTests.test_streamlit_status_uses_existing_validation_and_workflow_state -v
~~~

Expected: FAIL because the status variables and builder call are absent.

- [ ] **Step 6: Derive validation booleans from current state**

After workbook roles and settlement headers have been evaluated:

~~~python
workbook_status_valid = bool(
    uploaded is not None
    and deposit_date is not None
    and not missing_roles
)
settlement_status_valid = bool(
    settlement_file is not None
    and settlement_source_ok
)
~~~

Do not turn the existing date mismatch warning into a blocking error.

- [ ] **Step 7: Populate the early slot after workflow state is complete**

Immediately after download_details is created:

~~~python
operations_status = build_operations_status(
    deposit_date=deposit_date,
    daily_uploaded=uploaded is not None,
    settlement_uploaded=settlement_file is not None,
    workbook_valid=workbook_status_valid,
    settlement_valid=settlement_status_valid,
    workflow_complete=guided_workflow_ready,
    iif_generated=download_details is not None,
)
render_operations_status(operations_status_slot, operations_status)
~~~

The late render fills the earlier Streamlit slot, so it appears near the top while using complete current state.

- [ ] **Step 8: Run focused integration tests**

~~~powershell
& $pythonExe -m unittest tests.test_operations_status_ui tests.test_deposit_help_ui tests.test_membership_payments -v
~~~

Expected: all focused tests PASS.

- [ ] **Step 9: Create a local checkpoint**

~~~powershell
& $gitExe add -- streamlit_app.py tests/test_deposit_help_ui.py tests/test_membership_payments.py
& $gitExe commit -m "ui: integrate compact operations status"
~~~

Do not push.

---

### Task 3: Apply Compact Operations styling and protect bubble steps

**Files:**
- Modify: streamlit_app.py CSS section
- Modify: tests/test_operations_status_ui.py
- Modify: tests/test_membership_payments.py
- Verify unchanged: app/upload_intake_ui.py
- Verify unchanged: app/guided_step_ui.py
- Verify unchanged: app/ui_helpers.py

**Interfaces:**
- Consumes: hwfc-ops-status, hwfc-ops-status-item, and is-ready or is-attention classes.
- Produces: responsive compact status styling without new cards or duplicated progress.

- [ ] **Step 1: Write failing CSS-contract and bubble-preservation tests**

~~~python
def test_streamlit_styles_status_as_responsive_three_column_strip(self):
    source = (Path(__file__).parents[1] / "streamlit_app.py").read_text(
        encoding="utf-8"
    )
    self.assertIn(".hwfc-ops-status {", source)
    self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr));", source)
    self.assertIn("@media (max-width: 720px)", source)
    self.assertIn(".hwfc-ops-status.is-attention", source)


def test_guided_workflow_still_uses_horizontal_bubble_renderer(self):
    source = (Path(__file__).parents[1] / "streamlit_app.py").read_text(
        encoding="utf-8"
    )
    self.assertIn("render_deposit_step_panels(", source)
    self.assertNotIn("guided rail", source.lower())
~~~

- [ ] **Step 2: Run the tests and confirm the new contract fails**

~~~powershell
& $pythonExe -m unittest tests.test_operations_status_ui tests.test_membership_payments -v
~~~

Expected: the responsive CSS test FAILS because the status-strip styles are absent.

- [ ] **Step 3: Add restrained responsive CSS**

~~~css
.hwfc-ops-status {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px;
    margin: 18px 0 20px;
}

.hwfc-ops-status-item {
    min-width: 0;
    padding: 5px 10px 10px;
    border-bottom: 2px solid var(--hwfc-border);
}

.hwfc-ops-status-item span {
    display: block;
    color: var(--hwfc-muted);
    font-size: .78rem;
    margin-bottom: 5px;
}

.hwfc-ops-status-item strong {
    display: block;
    color: #FFFDF8;
    font-weight: 750;
    overflow-wrap: anywhere;
}

.hwfc-ops-status.is-ready .hwfc-ops-status-item:last-child {
    border-bottom-color: #78A85B;
}

.hwfc-ops-status.is-attention .hwfc-ops-status-item:last-child {
    border-bottom-color: #D7A84B;
}

@media (max-width: 720px) {
    .hwfc-ops-status {
        grid-template-columns: 1fr;
    }
}
~~~

Do not add card backgrounds, shadows, new badges, or another progress system.

- [ ] **Step 4: Verify the approved components remain unchanged**

Keep these calls:

~~~python
upload_render = render_upload_inputs(
    st,
    uploader_key=st.session_state["file_uploader_key"],
)

active_step_content, edited_step = render_deposit_step_panels(
    st,
    deposit_step_rows(required_steps, step_completions),
    edit_key_prefix=f"edit_deposit_step_{closeout_workbook_key}",
)
~~~

- [ ] **Step 5: Run all focused UI and workflow tests**

~~~powershell
& $pythonExe -m unittest tests.test_operations_status_ui tests.test_upload_intake_ui tests.test_deposit_workflow tests.test_membership_payments tests.test_deposit_help_ui tests.test_run_history_ui -v
~~~

Expected: all tests PASS.

- [ ] **Step 6: Create a local checkpoint**

~~~powershell
& $gitExe add -- streamlit_app.py app/operations_status_ui.py tests/test_operations_status_ui.py tests/test_membership_payments.py
& $gitExe commit -m "ui: polish compact operations workflow"
~~~

Do not push.

---

### Task 4: Full regression and local user review

**Files:**
- Verify: streamlit_app.py
- Verify: app/operations_status_ui.py
- Verify: app/upload_intake_ui.py
- Verify: app/guided_step_ui.py
- Verify: app/ui_helpers.py
- Verify: all tests

**Interfaces:**
- Consumes: Tasks 1 through 3.
- Produces: a verified local app for user review, with no remote push.

- [ ] **Step 1: Run the complete suite**

~~~powershell
$env:PYTHONIOENCODING = "utf-8"
& $pythonExe -m unittest discover -s tests -p "test_*.py"
~~~

Expected: PASS with zero failures and errors.

- [ ] **Step 2: Run syntax checks**

~~~powershell
& $pythonExe -m py_compile streamlit_app.py app/operations_status_ui.py app/upload_intake_ui.py app/guided_step_ui.py app/ui_helpers.py
~~~

Expected: exit code 0.

- [ ] **Step 3: Check whitespace and repository state**

~~~powershell
& $gitExe diff --check
& $gitExe status --short
~~~

Expected: no whitespace errors. Do not stage unrelated temporary test folders.

- [ ] **Step 4: Review desktop behavior at about 1024 pixels**

Confirm:

- Need Help, full SOP, Tips, and Start Over remain at the top.
- Compact Operations appears as one quiet three-part row.
- Upload inputs remain horizontal.
- Card Settlement verification remains below workbook validation.
- Guided breakdown uses horizontal bubble steps.
- Closeout Sheet remains last.

- [ ] **Step 5: Review narrow behavior at about 360 pixels**

Confirm:

- Status values stack without horizontal overflow.
- Upload controls remain usable.
- Bubble labels remain readable.
- Essential actions do not depend on hover.

- [ ] **Step 6: Show the local app to the user**

Ask the user to review the upload state and one guided-breakdown state. Do not push.

- [ ] **Step 7: Report exact local Git state**

~~~powershell
& $gitExe status --short
& $gitExe log -4 --oneline
~~~

Report tracked feature files separately from unrelated untracked test artifacts.

- [ ] **Step 8: Wait for explicit push approval**

Only after the user approves the running interface should the implementation commits be pushed to origin/main or copied to a requested backup branch.
