# Two-Stage Daily Deposit Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate report upload and verification from the guided deposit steps so each stage shows only the controls needed for that part of the deposit.

**Architecture:** Add a small page-flow state module that owns stage normalization, readiness, forward navigation, and reset behavior. Keep the existing upload parser and deposit engine unchanged; the Streamlit entry point will select either rendered upload controls or the preserved upload pair, validate those reports, and render exactly one page stage.

**Tech Stack:** Python 3, Streamlit session state, `unittest`, `openpyxl`

**Spec:** `docs/superpowers/specs/2026-09-09-two-stage-deposit-flow-design.md`

## Global Constraints

- New sessions begin on Upload & Verify.
- The app never advances automatically; the user must click **Continue to Deposit Steps**.
- Continue is enabled only when both reports are valid and resolve to the same deposit date.
- Deposit Steps hides upload-stage content and starts with **Today’s Deposit Steps**.
- There is no Edit Uploaded Reports action; **Start Over** is the only return path.
- Portal navigation preserves the current deposit and page stage.
- Missing or invalid preserved reports force a safe fallback to Upload & Verify.
- Deposit calculations, accounting mappings, and IIF output must not change.

Before running any Git step in PowerShell, define the repository's Git executable:

```powershell
$gitExe = "C:\Users\karlcruz\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe"
```

---

### Task 1: Build the Deposit Page-Flow State Model

**Files:**
- Create: `app/deposit_page_flow.py`
- Create: `tests/test_deposit_page_flow.py`

**Interfaces:**
- Consumes: a mutable Streamlit-compatible state mapping plus existing workbook/settlement validation booleans and detected dates.
- Produces: `UPLOAD_STAGE`, `DEPOSIT_STEPS_STAGE`, `DEPOSIT_PAGE_STAGE_KEY`, `selected_deposit_stage(state) -> str`, `reports_ready_for_steps(...) -> bool`, `advance_to_deposit_steps(state, *, reports_ready: bool) -> bool`, `enforce_ready_stage(state, *, reports_ready: bool) -> str`, and `reset_deposit_page(state) -> None`.

- [ ] **Step 1: Write failing state-model tests**

```python
import unittest
from datetime import date

from app.deposit_page_flow import (
    DEPOSIT_PAGE_STAGE_KEY,
    DEPOSIT_STEPS_STAGE,
    UPLOAD_STAGE,
    advance_to_deposit_steps,
    enforce_ready_stage,
    reports_ready_for_steps,
    reset_deposit_page,
    selected_deposit_stage,
)


class DepositPageFlowTests(unittest.TestCase):
    def test_new_and_unknown_stage_values_use_upload(self):
        self.assertEqual(selected_deposit_stage({}), UPLOAD_STAGE)
        self.assertEqual(
            selected_deposit_stage({DEPOSIT_PAGE_STAGE_KEY: "unknown"}),
            UPLOAD_STAGE,
        )

    def test_reports_require_two_valid_files_and_the_same_detected_date(self):
        report_date = date(2026, 9, 8)
        self.assertTrue(reports_ready_for_steps(
            workbook_valid=True,
            settlement_valid=True,
            workbook_date=report_date,
            settlement_date=report_date,
        ))
        self.assertFalse(reports_ready_for_steps(
            workbook_valid=True,
            settlement_valid=True,
            workbook_date=report_date,
            settlement_date=date(2026, 9, 9),
        ))
        self.assertFalse(reports_ready_for_steps(
            workbook_valid=False,
            settlement_valid=True,
            workbook_date=report_date,
            settlement_date=report_date,
        ))

    def test_continue_requires_ready_reports_and_never_advances_automatically(self):
        state = {}
        self.assertFalse(advance_to_deposit_steps(state, reports_ready=False))
        self.assertEqual(selected_deposit_stage(state), UPLOAD_STAGE)
        self.assertTrue(advance_to_deposit_steps(state, reports_ready=True))
        self.assertEqual(selected_deposit_stage(state), DEPOSIT_STEPS_STAGE)

    def test_invalid_preserved_reports_force_upload_stage(self):
        state = {DEPOSIT_PAGE_STAGE_KEY: DEPOSIT_STEPS_STAGE}
        self.assertEqual(
            enforce_ready_stage(state, reports_ready=False),
            UPLOAD_STAGE,
        )
        self.assertEqual(state[DEPOSIT_PAGE_STAGE_KEY], UPLOAD_STAGE)

    def test_reset_returns_to_upload(self):
        state = {DEPOSIT_PAGE_STAGE_KEY: DEPOSIT_STEPS_STAGE}
        reset_deposit_page(state)
        self.assertEqual(selected_deposit_stage(state), UPLOAD_STAGE)
```

- [ ] **Step 2: Run the state-model tests and verify the missing-module failure**

Run:

```powershell
& "C:\Users\karlcruz\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest tests.test_deposit_page_flow
```

Expected: FAIL because `app.deposit_page_flow` does not exist.

- [ ] **Step 3: Implement the minimal state model**

```python
from __future__ import annotations

from typing import MutableMapping


UPLOAD_STAGE = "upload"
DEPOSIT_STEPS_STAGE = "deposit_steps"
DEPOSIT_PAGE_STAGE_KEY = "daily_deposit_page_stage"


def selected_deposit_stage(state: MutableMapping[str, object]) -> str:
    value = state.get(DEPOSIT_PAGE_STAGE_KEY)
    if value == DEPOSIT_STEPS_STAGE:
        return DEPOSIT_STEPS_STAGE
    return UPLOAD_STAGE


def reports_ready_for_steps(
    *,
    workbook_valid: bool,
    settlement_valid: bool,
    workbook_date,
    settlement_date,
) -> bool:
    return bool(
        workbook_valid
        and settlement_valid
        and workbook_date is not None
        and settlement_date is not None
        and workbook_date == settlement_date
    )


def advance_to_deposit_steps(
    state: MutableMapping[str, object], *, reports_ready: bool
) -> bool:
    if not reports_ready:
        return False
    state[DEPOSIT_PAGE_STAGE_KEY] = DEPOSIT_STEPS_STAGE
    return True


def enforce_ready_stage(
    state: MutableMapping[str, object], *, reports_ready: bool
) -> str:
    stage = selected_deposit_stage(state)
    if stage == DEPOSIT_STEPS_STAGE and not reports_ready:
        state[DEPOSIT_PAGE_STAGE_KEY] = UPLOAD_STAGE
        return UPLOAD_STAGE
    return stage


def reset_deposit_page(state: MutableMapping[str, object]) -> None:
    state.pop(DEPOSIT_PAGE_STAGE_KEY, None)
```

- [ ] **Step 4: Run the state-model tests and verify they pass**

Run the Step 2 command.

Expected: all `DepositPageFlowTests` pass.

- [ ] **Step 5: Commit the state model**

```powershell
& $gitExe add -- app/deposit_page_flow.py tests/test_deposit_page_flow.py
& $gitExe commit -m "feat: add daily deposit page stages"
```

---

### Task 2: Add Preserved-Upload and Continue Controls

**Files:**
- Modify: `app/upload_intake_ui.py`
- Modify: `app/guided_step_ui.py`
- Modify: `tests/test_upload_intake_ui.py`
- Modify: `tests/test_membership_payments.py`

**Interfaces:**
- Consumes: the existing `preserved_daily_upload(state, widget_key)` storage and the readiness result from Task 1.
- Produces: `retained_upload_pair(state, *, uploader_key: int) -> tuple[object | None, object | None]` and `render_upload_continue_action(ui, *, ready: bool) -> bool`.

- [ ] **Step 1: Write failing tests for retained uploads and the Continue action**

Add to `tests/test_upload_intake_ui.py`:

```python
def test_retained_upload_pair_reads_both_preserved_widget_values(self):
    from app.program_hub_ui import DAILY_PROGRAM_UPLOADS_KEY
    from app.upload_intake_ui import retained_upload_pair

    daily = object()
    settlement = object()
    state = {
        DAILY_PROGRAM_UPLOADS_KEY: {
            "daily_workbook_4": daily,
            "card_settlement_4": settlement,
        }
    }

    self.assertEqual(
        retained_upload_pair(state, uploader_key=4),
        (daily, settlement),
    )
```

Add to the guided UI tests in `tests/test_membership_payments.py`:

```python
def test_upload_continue_action_is_disabled_until_reports_are_ready(self):
    from app.guided_step_ui import render_upload_continue_action

    class RecordingUI:
        def __init__(self):
            self.calls = []

        def button(self, label, **kwargs):
            self.calls.append((label, kwargs))
            return True

    ui = RecordingUI()
    self.assertFalse(render_upload_continue_action(ui, ready=False))
    self.assertEqual(ui.calls[0][0], "Continue to Deposit Steps")
    self.assertTrue(ui.calls[0][1]["disabled"])
    self.assertEqual(ui.calls[0][1]["type"], "primary")

    ready_ui = RecordingUI()
    self.assertTrue(render_upload_continue_action(ready_ui, ready=True))
    self.assertFalse(ready_ui.calls[0][1]["disabled"])
```

- [ ] **Step 2: Run both focused test modules and verify missing-interface failures**

Run:

```powershell
& "C:\Users\karlcruz\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest tests.test_upload_intake_ui tests.test_membership_payments
```

Expected: FAIL because `retained_upload_pair` and `render_upload_continue_action` are not defined.

- [ ] **Step 3: Implement retained upload lookup**

Add to `app/upload_intake_ui.py`:

```python
def retained_upload_pair(
    state, *, uploader_key: int
) -> tuple[object | None, object | None]:
    """Return the upload pair while its widgets are hidden on Deposit Steps."""
    from app.program_hub_ui import preserved_daily_upload

    return (
        preserved_daily_upload(state, f"daily_workbook_{uploader_key}"),
        preserved_daily_upload(state, f"card_settlement_{uploader_key}"),
    )
```

- [ ] **Step 4: Implement the Continue renderer**

Add to `app/guided_step_ui.py`:

```python
def render_upload_continue_action(ui, *, ready: bool) -> bool:
    """Render the explicit handoff from verified reports to guided steps."""
    clicked = ui.button(
        "Continue to Deposit Steps",
        type="primary",
        use_container_width=True,
        disabled=not ready,
        help=(
            "Continue after both reports are verified and their dates match."
            if not ready
            else "Open Today’s Deposit Steps."
        ),
    )
    return bool(clicked and ready)
```

- [ ] **Step 5: Run the focused tests and verify they pass**

Run the Step 2 command.

Expected: both test modules pass.

- [ ] **Step 6: Commit the UI boundaries**

```powershell
& $gitExe add -- app/upload_intake_ui.py app/guided_step_ui.py tests/test_upload_intake_ui.py tests/test_membership_payments.py
& $gitExe commit -m "feat: add verified report continue action"
```

---

### Task 3: Wire the Two Exclusive Page Stages

**Files:**
- Modify: `streamlit_app.py:100-140`
- Modify: `streamlit_app.py:1448-1452`
- Modify: `streamlit_app.py:1950-2335`
- Modify: `tests/test_current_deposit_state.py`
- Modify: `tests/test_deposit_help_ui.py`
- Modify: `tests/test_program_hub_ui.py`

**Interfaces:**
- Consumes: all Task 1 page-flow functions, Task 2 `retained_upload_pair`, Task 2 `render_upload_continue_action`, existing `render_upload_inputs`, existing upload validation functions, and existing guided-step rendering.
- Produces: an exclusive Upload & Verify page and Deposit Steps page in the Streamlit entry point.

- [ ] **Step 1: Write failing wiring tests**

Add behavior-oriented page-flow coverage to `tests/test_current_deposit_state.py`:

```python
def test_start_over_resets_the_page_stage(self):
    from app.deposit_page_flow import (
        DEPOSIT_PAGE_STAGE_KEY,
        DEPOSIT_STEPS_STAGE,
        reset_deposit_page,
    )

    self.ns["st"].session_state[DEPOSIT_PAGE_STAGE_KEY] = DEPOSIT_STEPS_STAGE
    reset = next(
        node for node in ast.parse(SOURCE.read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef) and node.name == "reset_current_work"
    )
    self.ns["reset_deposit_page"] = reset_deposit_page
    execute([reset], self.ns)
    self.ns["reset_current_work"]()
    self.assertNotIn(DEPOSIT_PAGE_STAGE_KEY, self.ns["st"].session_state)

def test_page_stage_is_enforced_after_report_validation(self):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    assignments_by_name = {
        target.id: node.lineno
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    self.assertLess(
        assignments_by_name["reports_ready"],
        assignments_by_name["deposit_page_stage"],
    )
```

Replace the old assertion that the operations-status slot always precedes upload inputs in `tests/test_deposit_help_ui.py` with stage-specific expectations:

```python
def test_upload_help_status_and_inputs_are_owned_by_upload_stage(self):
    source = self.app_source()
    upload_stage_marker = "if requested_page_stage == UPLOAD_STAGE:"
    continue_marker = "render_upload_continue_action("
    guide_marker = "if deposit_page_stage == DEPOSIT_STEPS_STAGE:"

    self.assertIn(upload_stage_marker, source)
    self.assertIn(continue_marker, source)
    self.assertIn(guide_marker, source)
    self.assertLess(source.index(upload_stage_marker), source.index(continue_marker))
    self.assertLess(source.index(continue_marker), source.index(guide_marker))
```

Add an explicit portal-preservation check to `tests/test_program_hub_ui.py`:

```python
def test_portal_round_trip_preserves_daily_deposit_page_stage(self):
    from app.deposit_page_flow import DEPOSIT_PAGE_STAGE_KEY, DEPOSIT_STEPS_STAGE
    from app.program_hub_ui import (
        DAILY_DEPOSITS,
        activate_program,
        preserve_daily_program_state,
        restore_daily_program_state,
        return_to_program_hub,
    )

    state = {DEPOSIT_PAGE_STAGE_KEY: DEPOSIT_STEPS_STAGE}
    activate_program(state, DAILY_DEPOSITS)
    preserve_daily_program_state(state)
    return_to_program_hub(state)
    activate_program(state, DAILY_DEPOSITS)
    restore_daily_program_state(state)

    self.assertEqual(state[DEPOSIT_PAGE_STAGE_KEY], DEPOSIT_STEPS_STAGE)
```

- [ ] **Step 2: Run the two wiring test modules and verify they fail for missing stage wiring**

Run:

```powershell
& "C:\Users\karlcruz\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest tests.test_current_deposit_state tests.test_deposit_help_ui tests.test_program_hub_ui
```

Expected: FAIL because `streamlit_app.py` does not yet use the page-flow interfaces.

- [ ] **Step 3: Import the new page-flow interfaces**

Add these imports near the existing guided workflow imports:

```python
from app.deposit_page_flow import (
    DEPOSIT_STEPS_STAGE,
    UPLOAD_STAGE,
    advance_to_deposit_steps,
    enforce_ready_stage,
    reports_ready_for_steps,
    reset_deposit_page,
    selected_deposit_stage,
)
from app.upload_intake_ui import render_upload_inputs, retained_upload_pair
```

Also import `render_upload_continue_action` from `app.guided_step_ui`.

- [ ] **Step 4: Make Start Over clear the page stage**

Append this call to `reset_current_work()` after clearing the current result identity:

```python
reset_deposit_page(st.session_state)
```

Keep the existing uploader-key increment so the old upload widgets and preserved file keys cannot reappear after reset.

- [ ] **Step 5: Select rendered or retained uploads based on the requested stage**

Before the existing main-page upload area, set:

```python
requested_page_stage = selected_deposit_stage(st.session_state)
```

Render the hero, Need Help, upload progress strip, upload step bar, and `render_upload_inputs(...)` only inside:

```python
if requested_page_stage == UPLOAD_STAGE:
    # existing upload-stage presentation
    upload_render = render_upload_inputs(
        st,
        uploader_key=st.session_state["file_uploader_key"],
    )
    uploaded = upload_render.daily_workbook
    settlement_file = upload_render.card_settlement
else:
    uploaded, settlement_file = retained_upload_pair(
        st.session_state,
        uploader_key=st.session_state["file_uploader_key"],
    )
```

Keep the sidebar outside this condition so **All Programs** and Run History remain available in both stages. Render a compact right-aligned **Start Over** action above Today’s Deposit Steps when `requested_page_stage == DEPOSIT_STEPS_STAGE`.

- [ ] **Step 6: Keep validation calculations in both stages but upload feedback only on Upload & Verify**

Continue computing `deposit_date`, detected roles, missing roles, settlement source validity, and settlement date for both rendered and retained uploads. Wrap upload-only presentation calls—date card, workbook validation expander, mismatch detail, upload warnings, and upload-stage operations status—with:

```python
if requested_page_stage == UPLOAD_STAGE:
    # existing upload feedback call
```

On Deposit Steps, call the existing Card Settlement verification renderer with the verified strip enabled immediately before Today’s Deposit Steps. Do not render upload controls or Need Help there.

- [ ] **Step 7: Enforce date-matched readiness and render the explicit Continue action**

Replace the guide-unlock decision with:

```python
reports_ready = reports_ready_for_steps(
    workbook_valid=workbook_status_valid,
    settlement_valid=settlement_status_valid,
    workbook_date=deposit_date,
    settlement_date=settlement_date_info,
)
deposit_page_stage = enforce_ready_stage(
    st.session_state,
    reports_ready=reports_ready,
)

if requested_page_stage == DEPOSIT_STEPS_STAGE and deposit_page_stage == UPLOAD_STAGE:
    st.rerun()

if deposit_page_stage == UPLOAD_STAGE:
    render_operations_status(
        operations_status_slot,
        build_operations_status(
            deposit_date=deposit_date,
            daily_uploaded=uploaded is not None,
            settlement_uploaded=settlement_file is not None,
            workbook_valid=workbook_status_valid,
            settlement_valid=settlement_status_valid,
            workflow_complete=False,
            iif_generated=False,
        ),
    )
    if render_upload_continue_action(st, ready=reports_ready):
        if advance_to_deposit_steps(
            st.session_state,
            reports_ready=reports_ready,
        ):
            st.rerun()
    st.stop()
```

Update the settlement date-mismatch message so it tells the user to upload the matching report before continuing; remove the old statement that the deposit can still run with mismatched dates.

- [ ] **Step 8: Render the existing guided workflow only in Deposit Steps**

Guard the existing workbook-derived totals, required-step detection, `render_deposit_step_panels`, active forms, final IIF action, and results with the confirmed stage. The controlling condition must be:

```python
if deposit_page_stage == DEPOSIT_STEPS_STAGE:
    st.markdown("## Today’s Deposit Steps")
    # existing guided workflow, final action, and results
```

Remove the old automatic `deposit_steps_scroll_key` handoff from upload readiness. Preserve every per-step scroll request already used inside the guided workflow.

- [ ] **Step 9: Run the focused wiring and existing guided-flow tests**

Run:

```powershell
& "C:\Users\karlcruz\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest tests.test_current_deposit_state tests.test_deposit_help_ui tests.test_program_hub_ui tests.test_membership_payments
```

Expected: all selected tests pass, including portal preservation, Start Over, verified Card Settlement placement, and guided-step behavior.

- [ ] **Step 10: Commit the integrated two-stage page**

```powershell
& $gitExe add -- streamlit_app.py tests/test_current_deposit_state.py tests/test_deposit_help_ui.py tests/test_program_hub_ui.py
& $gitExe commit -m "feat: separate upload and deposit step pages"
```

---

### Task 4: Full Regression and User-Flow Verification

**Files:**
- Modify only if a regression exposes a defect in a file changed by Tasks 1–3.
- Verify: all `tests/test_*.py`

**Interfaces:**
- Consumes: the completed two-stage workflow.
- Produces: regression evidence and a deploy-ready commit series without modifying unrelated untracked backup/test artifacts.

- [ ] **Step 1: Run the complete automated suite**

Run:

```powershell
& "C:\Users\karlcruz\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest discover -s tests -p "test_*.py"
```

Expected: all tests pass with zero failures or errors. Existing Windows console encoding warnings may appear in legacy engine logging, but the test process must exit with code `0`.

- [ ] **Step 2: Check the final diff for whitespace and scope**

Run:

```powershell
& $gitExe diff --check
& $gitExe status --short
```

Expected: no whitespace errors; only files named in this plan are modified. Leave `.superpowers/` and existing `_sales_mapping_*` artifacts untouched.

- [ ] **Step 3: Verify the app’s two user paths locally**

Run:

```powershell
& "C:\Users\karlcruz\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m streamlit run streamlit_app.py
```

Verify in the browser:

1. Daily Deposit opens with the taskbar collapsed and the Upload & Verify page visible.
2. One report alone leaves Continue disabled.
3. Two valid same-date reports enable Continue.
4. Clicking Continue hides the upload page and starts at Today’s Deposit Steps.
5. A normal rerun keeps Deposit Steps visible.
6. All Programs and reopening Daily Deposit preserve the current stage and files.
7. Start Over clears the deposit and returns to Upload & Verify.
8. Mismatched report dates cannot continue.

- [ ] **Step 4: Commit any test-driven integration correction**

If Step 1 or Step 3 required a correction, stage only its directly related files and commit:

```powershell
& $gitExe add -- app/deposit_page_flow.py app/upload_intake_ui.py app/guided_step_ui.py streamlit_app.py tests/test_deposit_page_flow.py tests/test_upload_intake_ui.py tests/test_membership_payments.py tests/test_current_deposit_state.py tests/test_deposit_help_ui.py
& $gitExe commit -m "fix: complete two-stage deposit navigation"
```

If no correction was required, do not create an empty commit.
