# Finance Operations Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a simple Finance Operations Hub that opens before the existing Daily Deposit workflow and presents Credit Card Process and AP Statements as disabled Coming Soon programs.

**Architecture:** Add one focused `app/program_hub_ui.py` module containing program definitions, session-state navigation helpers, and Hub rendering. Gate the existing Daily Deposit screen near its current header so the untouched Daily Deposit workflow runs only after the user selects it; returning to the Hub changes only the program-selection key.

**Tech Stack:** Python 3, Streamlit, HTML/CSS rendered through Streamlit Markdown, `unittest`

**Spec:** `docs/superpowers/specs/2026-09-09-finance-operations-hub-design.md`

## Global Constraints

- A fresh Streamlit browser session opens on the Operations Hub.
- Daily Deposits remains fully available with its current behavior and appearance.
- Credit Card Process and AP Statements remain disabled and display “Coming Soon”.
- Returning to the Hub must preserve all Daily Deposit session data.
- Start Over remains the only action that clears Daily Deposit work and does not return to the Hub.
- The complete Daily Workbook SOP, Tips & Known Exceptions, and collapsed Run History remain in their current Daily Deposit locations.
- Do not change accounting, workbook parsing, mapping, reconciliation, or IIF-generation behavior.
- Do not add dashboards, metrics, authentication, permissions, or new dependencies.

---

## File Structure

- Create `app/program_hub_ui.py`: program registry, safe session-state navigation, Hub card renderer, and All Programs control.
- Create `tests/test_program_hub_ui.py`: behavior tests for registry, navigation, rendering, disabled cards, and data preservation.
- Modify `streamlit_app.py`: import the Hub boundary, add Hub styles, route before the Daily Deposit header, and render All Programs above the existing Daily Deposit hero.
- Modify `tests/test_deposit_help_ui.py`: protect the existing Daily Deposit header/help/history ordering behind the new Hub route.

### Task 1: Program Registry and Safe Navigation State

**Files:**
- Create: `app/program_hub_ui.py`
- Create: `tests/test_program_hub_ui.py`

**Interfaces:**
- Produces: `ACTIVE_PROGRAM_KEY: str`
- Produces: `DAILY_DEPOSITS: str`
- Produces: `ProgramDefinition(key: str, title: str, description: str, enabled: bool)`
- Produces: `PROGRAMS: tuple[ProgramDefinition, ...]`
- Produces: `normalize_program_selection(value: object) -> str | None`
- Produces: `activate_program(state: MutableMapping[str, object], program_key: str) -> bool`
- Produces: `return_to_program_hub(state: MutableMapping[str, object]) -> None`

- [ ] **Step 1: Write failing registry and navigation tests**

```python
import unittest


class ProgramHubStateTests(unittest.TestCase):
    def test_only_daily_deposits_is_enabled(self):
        from app.program_hub_ui import DAILY_DEPOSITS, PROGRAMS

        enabled = [program.key for program in PROGRAMS if program.enabled]
        self.assertEqual(enabled, [DAILY_DEPOSITS])
        self.assertEqual(
            [program.title for program in PROGRAMS],
            ["Daily Deposits", "Credit Card Process", "AP Statements"],
        )

    def test_unknown_and_disabled_programs_normalize_to_hub(self):
        from app.program_hub_ui import normalize_program_selection

        self.assertIsNone(normalize_program_selection(None))
        self.assertIsNone(normalize_program_selection("credit_card_process"))
        self.assertIsNone(normalize_program_selection("not-a-program"))

    def test_daily_deposits_can_be_activated(self):
        from app.program_hub_ui import (
            ACTIVE_PROGRAM_KEY,
            DAILY_DEPOSITS,
            activate_program,
        )

        state = {"membership_payments": [{"amount": 8.45}]}
        self.assertTrue(activate_program(state, DAILY_DEPOSITS))
        self.assertEqual(state[ACTIVE_PROGRAM_KEY], DAILY_DEPOSITS)
        self.assertEqual(state["membership_payments"], [{"amount": 8.45}])

    def test_disabled_program_cannot_be_activated(self):
        from app.program_hub_ui import activate_program

        state = {"daily_workbook": "preserve-me"}
        self.assertFalse(activate_program(state, "ap_statements"))
        self.assertNotIn("active_finance_program", state)
        self.assertEqual(state["daily_workbook"], "preserve-me")

    def test_return_to_hub_removes_only_program_selection(self):
        from app.program_hub_ui import (
            ACTIVE_PROGRAM_KEY,
            DAILY_DEPOSITS,
            return_to_program_hub,
        )

        state = {
            ACTIVE_PROGRAM_KEY: DAILY_DEPOSITS,
            "membership_payments": [{"amount": 8.45}],
            "run_result": {"status": "ready"},
        }
        return_to_program_hub(state)
        self.assertNotIn(ACTIVE_PROGRAM_KEY, state)
        self.assertEqual(state["membership_payments"], [{"amount": 8.45}])
        self.assertEqual(state["run_result"], {"status": "ready"})
```

- [ ] **Step 2: Run the state tests and confirm the missing module failure**

Run: `python -m unittest tests.test_program_hub_ui.ProgramHubStateTests`

Expected: FAIL because `app.program_hub_ui` does not exist.

- [ ] **Step 3: Implement the registry and navigation helpers**

```python
from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass


ACTIVE_PROGRAM_KEY = "active_finance_program"
DAILY_DEPOSITS = "daily_deposits"


@dataclass(frozen=True)
class ProgramDefinition:
    key: str
    title: str
    description: str
    enabled: bool


PROGRAMS = (
    ProgramDefinition(
        DAILY_DEPOSITS,
        "Daily Deposits",
        "Reconcile daily reports and prepare the QuickBooks import.",
        True,
    ),
    ProgramDefinition(
        "credit_card_process",
        "Credit Card Process",
        "Process and verify credit-card activity.",
        False,
    ),
    ProgramDefinition(
        "ap_statements",
        "AP Statements",
        "Review and reconcile accounts-payable statements.",
        False,
    ),
)


def normalize_program_selection(value: object) -> str | None:
    enabled_keys = {program.key for program in PROGRAMS if program.enabled}
    return value if isinstance(value, str) and value in enabled_keys else None


def activate_program(state: MutableMapping[str, object], program_key: str) -> bool:
    normalized = normalize_program_selection(program_key)
    if normalized is None:
        return False
    state[ACTIVE_PROGRAM_KEY] = normalized
    return True


def return_to_program_hub(state: MutableMapping[str, object]) -> None:
    state.pop(ACTIVE_PROGRAM_KEY, None)
```

- [ ] **Step 4: Run the state tests and confirm they pass**

Run: `python -m unittest tests.test_program_hub_ui.ProgramHubStateTests`

Expected: 5 tests PASS.

- [ ] **Step 5: Commit the state boundary**

```powershell
git add -- app/program_hub_ui.py tests/test_program_hub_ui.py
git commit -m "feat: add finance program navigation state"
```

### Task 2: Program Cards Home Screen

**Files:**
- Modify: `app/program_hub_ui.py`
- Modify: `tests/test_program_hub_ui.py`

**Interfaces:**
- Consumes: `PROGRAMS: tuple[ProgramDefinition, ...]`
- Produces: `program_card_html(program: ProgramDefinition) -> str`
- Produces: `render_program_hub(ui) -> str | None`
- Produces: `render_all_programs_action(ui) -> bool`

- [ ] **Step 1: Write failing renderer tests with a real recording UI**

```python
class RecordingColumn:
    def __init__(self, ui):
        self.ui = ui

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None


class RecordingUI:
    def __init__(self, clicked_key=None):
        self.clicked_key = clicked_key
        self.events = []

    def markdown(self, body, **kwargs):
        self.events.append(("markdown", body, kwargs))

    def columns(self, count):
        self.events.append(("columns", count, {}))
        return [RecordingColumn(self) for _ in range(count)]

    def button(self, label, **kwargs):
        self.events.append(("button", label, kwargs))
        return kwargs.get("key") == self.clicked_key

    def popover(self, label):
        self.events.append(("popover", label, {}))
        return RecordingColumn(self)

    def caption(self, body):
        self.events.append(("caption", body, {}))


class ProgramHubRendererTests(unittest.TestCase):
    def test_home_renders_three_cards_and_two_disabled_actions(self):
        from app.program_hub_ui import render_program_hub

        ui = RecordingUI()
        selected = render_program_hub(ui)
        buttons = [event for event in ui.events if event[0] == "button"]
        rendered = " ".join(
            event[1] for event in ui.events if event[0] == "markdown"
        )

        self.assertIsNone(selected)
        self.assertIn("What are you working on?", rendered)
        self.assertIn("Daily Deposits", rendered)
        self.assertIn("Credit Card Process", rendered)
        self.assertIn("AP Statements", rendered)
        self.assertEqual(len(buttons), 3)
        self.assertEqual(sum(bool(event[2].get("disabled")) for event in buttons), 2)
        self.assertEqual(buttons[0][1], "Open program →")
        self.assertEqual(buttons[1][1], "Coming Soon")

    def test_daily_card_returns_daily_program_when_clicked(self):
        from app.program_hub_ui import DAILY_DEPOSITS, render_program_hub

        ui = RecordingUI(clicked_key="open_program_daily_deposits")
        self.assertEqual(render_program_hub(ui), DAILY_DEPOSITS)

    def test_card_copy_is_html_escaped(self):
        from app.program_hub_ui import ProgramDefinition, program_card_html

        rendered = program_card_html(
            ProgramDefinition("safe", "<script>x</script>", "A & B", True)
        )
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", rendered)
        self.assertIn("A &amp; B", rendered)
        self.assertNotIn("<script>", rendered)

    def test_all_programs_control_reports_click_without_mutating_state(self):
        from app.program_hub_ui import render_all_programs_action

        ui = RecordingUI(clicked_key="return_to_program_hub")
        self.assertTrue(render_all_programs_action(ui))
```

- [ ] **Step 2: Run renderer tests and confirm the missing function failure**

Run: `python -m unittest tests.test_program_hub_ui.ProgramHubRendererTests`

Expected: FAIL because the Hub renderers are not implemented.

- [ ] **Step 3: Implement escaped card markup and Streamlit controls**

Add to `app/program_hub_ui.py`:

```python
import html


def program_card_html(program: ProgramDefinition) -> str:
    title = html.escape(program.title, quote=True)
    description = html.escape(program.description, quote=True)
    availability = "Available" if program.enabled else "Coming Soon"
    state_class = "is-available" if program.enabled else "is-coming-soon"
    return (
        f'<div class="hwfc-program-card {state_class}">'
        f'<div class="hwfc-program-card-title">{title}</div>'
        f'<div class="hwfc-program-card-copy">{description}</div>'
        f'<div class="hwfc-program-card-status">{availability}</div>'
        "</div>"
    )


def render_program_hub(ui) -> str | None:
    ui.markdown(
        """
        <div class="hwfc-hub-hero">
          <div class="hwfc-hub-kicker">Honest Weight Food Co-op</div>
          <div class="hwfc-hub-title">Finance Operations</div>
        </div>
        <div class="hwfc-hub-prompt">
          <h1>What are you working on?</h1>
          <p>Choose a program to begin.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with ui.popover("❔ Need Help"):
        ui.caption("Choose Daily Deposits to access the Daily Workbook SOP, tips, and run history.")

    selected = None
    columns = ui.columns(len(PROGRAMS))
    for column, program in zip(columns, PROGRAMS):
        with column:
            ui.markdown(program_card_html(program), unsafe_allow_html=True)
            label = "Open program →" if program.enabled else "Coming Soon"
            if ui.button(
                label,
                key=f"open_program_{program.key}",
                disabled=not program.enabled,
                use_container_width=True,
            ):
                selected = program.key
    return selected


def render_all_programs_action(ui) -> bool:
    return ui.button(
        "← All Programs",
        key="return_to_program_hub",
        help="Return to Finance Operations without clearing your Daily Deposit work.",
    )
```

- [ ] **Step 4: Run the complete Hub test module**

Run: `python -m unittest tests.test_program_hub_ui`

Expected: 9 tests PASS.

- [ ] **Step 5: Commit the Home renderer**

```powershell
git add -- app/program_hub_ui.py tests/test_program_hub_ui.py
git commit -m "ui: add finance operations program cards"
```

### Task 3: Route the Existing Daily Deposit Workflow Through the Hub

**Files:**
- Modify: `streamlit_app.py` near imports and immediately before the current `# Header` section
- Modify: `tests/test_program_hub_ui.py`
- Modify: `tests/test_deposit_help_ui.py`

**Interfaces:**
- Consumes: `ACTIVE_PROGRAM_KEY`, `DAILY_DEPOSITS`, `activate_program`, `normalize_program_selection`, `render_all_programs_action`, `render_program_hub`, and `return_to_program_hub`
- Produces: entry-point behavior that stops before Daily Deposit UI on the Hub and continues unchanged when Daily Deposits is active

- [ ] **Step 1: Write failing entry-point contract tests**

Add to `tests/test_program_hub_ui.py`:

```python
from pathlib import Path


class ProgramHubEntryPointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(__file__).resolve().parents[1].joinpath(
            "streamlit_app.py"
        ).read_text(encoding="utf-8")

    def test_router_runs_before_daily_deposit_header(self):
        router = self.source.index("selected_program = normalize_program_selection(")
        daily_header = self.source.index("Daily Deposit Reconciliation")
        self.assertLess(router, daily_header)

    def test_hub_stops_before_daily_workflow_when_no_program_is_selected(self):
        hub_render = self.source.index("render_program_hub(st)")
        stop = self.source.index("st.stop()", hub_render)
        daily_header = self.source.index("Daily Deposit Reconciliation")
        self.assertLess(hub_render, stop)
        self.assertLess(stop, daily_header)

    def test_all_programs_navigation_does_not_call_daily_reset(self):
        start = self.source.index("if render_all_programs_action(st):")
        end = self.source.index("# Header", start)
        navigation_block = self.source[start:end]
        self.assertIn("return_to_program_hub(st.session_state)", navigation_block)
        self.assertIn("st.rerun()", navigation_block)
        self.assertNotIn("reset_current_work()", navigation_block)

    def test_sidebar_remains_after_the_hub_stop_boundary(self):
        stop = self.source.index("st.stop()")
        sidebar = self.source.index("with st.sidebar:")
        self.assertLess(stop, sidebar)
```

Extend `tests/test_deposit_help_ui.py`:

```python
def test_daily_help_and_start_over_remain_inside_daily_program(self):
    app_source = Path(__file__).resolve().parents[1].joinpath(
        "streamlit_app.py"
    ).read_text(encoding="utf-8")

    hub_stop = app_source.index("st.stop()")
    help_position = app_source.index("render_need_help_label(st)")
    start_over_position = app_source.index('"↻ Start Over"')
    self.assertLess(hub_stop, help_position)
    self.assertLess(hub_stop, start_over_position)
```

- [ ] **Step 2: Run entry-point tests and confirm they fail on missing routing**

Run: `python -m unittest tests.test_program_hub_ui.ProgramHubEntryPointTests tests.test_deposit_help_ui.DepositHelpUITests.test_daily_help_and_start_over_remain_inside_daily_program`

Expected: FAIL because `streamlit_app.py` does not yet contain the Hub route.

- [ ] **Step 3: Import Hub interfaces and add the route before the Daily header**

Add to the import section of `streamlit_app.py`:

```python
from app.program_hub_ui import (
    ACTIVE_PROGRAM_KEY,
    DAILY_DEPOSITS,
    activate_program,
    normalize_program_selection,
    render_all_programs_action,
    render_program_hub,
    return_to_program_hub,
)
```

Immediately before the existing `# Header` section, add:

```python
selected_program = normalize_program_selection(
    st.session_state.get(ACTIVE_PROGRAM_KEY)
)

if selected_program is None:
    st.session_state.pop(ACTIVE_PROGRAM_KEY, None)
    requested_program = render_program_hub(st)
    if requested_program and activate_program(
        st.session_state, requested_program
    ):
        st.rerun()
    st.stop()

if selected_program != DAILY_DEPOSITS:
    return_to_program_hub(st.session_state)
    st.rerun()

if render_all_programs_action(st):
    return_to_program_hub(st.session_state)
    st.rerun()
```

Do not move, indent, or rewrite the existing Daily Deposit header, Start Over, SOP, tips, Run History, upload, guided-step, validation, or result code.

- [ ] **Step 4: Run Hub, help, and current-state regression tests**

Run: `python -m unittest tests.test_program_hub_ui tests.test_deposit_help_ui tests.test_current_deposit_state`

Expected: all tests PASS.

- [ ] **Step 5: Compile the entry point**

Run: `python -m py_compile streamlit_app.py app/program_hub_ui.py`

Expected: exit code 0 with no syntax errors.

- [ ] **Step 6: Commit routing integration**

```powershell
git add -- streamlit_app.py app/program_hub_ui.py tests/test_program_hub_ui.py tests/test_deposit_help_ui.py
git commit -m "feat: open daily deposits from operations hub"
```

### Task 4: Responsive Hub Styling and Final Regression

**Files:**
- Modify: `streamlit_app.py` in the existing global CSS block near `.hwfc-ops-status`
- Modify: `tests/test_program_hub_ui.py`

**Interfaces:**
- Consumes: markup classes emitted by `render_program_hub`
- Produces: three-column desktop cards, stacked mobile cards, active Daily Deposit emphasis, and quiet disabled Coming Soon cards

- [ ] **Step 1: Write a failing style and accessibility contract test**

Add to `tests/test_program_hub_ui.py`:

```python
class ProgramHubStyleContractTests(unittest.TestCase):
    def test_hub_has_responsive_three_card_layout_and_visible_states(self):
        source = Path(__file__).resolve().parents[1].joinpath(
            "streamlit_app.py"
        ).read_text(encoding="utf-8")

        self.assertIn(".hwfc-program-card {", source)
        self.assertIn(".hwfc-program-card.is-available", source)
        self.assertIn(".hwfc-program-card.is-coming-soon", source)
        self.assertIn("@media (max-width: 720px)", source)
        self.assertIn(".hwfc-hub-prompt", source)

    def test_hub_renderer_uses_accessible_program_actions(self):
        from app.program_hub_ui import render_program_hub

        ui = RecordingUI()
        render_program_hub(ui)
        buttons = [event for event in ui.events if event[0] == "button"]
        self.assertTrue(all(event[2].get("use_container_width") for event in buttons))
        self.assertTrue(buttons[1][2]["disabled"])
        self.assertTrue(buttons[2][2]["disabled"])
```

- [ ] **Step 2: Run the style test and confirm missing CSS failure**

Run: `python -m unittest tests.test_program_hub_ui.ProgramHubStyleContractTests`

Expected: FAIL because the Hub CSS selectors are missing.

- [ ] **Step 3: Add scoped Hub styles to the existing CSS block**

Add styles using the established HWFC palette and existing CSS variables:

```css
.hwfc-hub-hero {
    background: linear-gradient(100deg, #315F3A, #3D6739);
    border-radius: 0 0 22px 22px;
    color: #FFFDF8;
    margin-bottom: 26px;
    padding: 24px 30px;
}

.hwfc-hub-kicker {
    font-size: .78rem;
    font-weight: 800;
    letter-spacing: .14em;
    text-transform: uppercase;
}

.hwfc-hub-title {
    font-family: Georgia, "Times New Roman", serif;
    font-size: clamp(2rem, 4vw, 3.1rem);
    font-weight: 800;
}

.hwfc-hub-prompt {
    margin: 12px 0 22px;
}

.hwfc-hub-prompt p {
    color: var(--hwfc-muted);
}

.hwfc-program-card {
    background: var(--hwfc-paper);
    border: 1px solid var(--hwfc-border);
    border-radius: 14px;
    min-height: 190px;
    padding: 22px;
}

.hwfc-program-card.is-available {
    border-color: #78A85B;
    box-shadow: inset 0 3px 0 rgba(120, 168, 91, .65);
}

.hwfc-program-card.is-coming-soon {
    opacity: .72;
}

.hwfc-program-card-title {
    color: #FFFDF8;
    font-size: 1.15rem;
    font-weight: 800;
    margin-bottom: 8px;
}

.hwfc-program-card-copy {
    color: var(--hwfc-muted);
    min-height: 70px;
}

.hwfc-program-card-status {
    color: #78A85B;
    font-weight: 750;
    margin-top: 18px;
}

@media (max-width: 720px) {
    .hwfc-program-card {
        min-height: 0;
    }
}
```

- [ ] **Step 4: Run focused Hub and existing UI tests**

Run: `python -m unittest tests.test_program_hub_ui tests.test_deposit_help_ui tests.test_operations_status_ui tests.test_upload_intake_ui`

Expected: all tests PASS.

- [ ] **Step 5: Run the complete regression suite**

Run: `python -m unittest discover -s tests -p "test_*.py"`

Expected: all tests PASS with no failures or errors. Existing Windows console Unicode logging notices may appear; they are unrelated only when the test runner still ends with `OK`.

- [ ] **Step 6: Compile and inspect the final diff**

Run: `python -m py_compile streamlit_app.py app/program_hub_ui.py`

Run: `git diff --check`

Run: `git status --short`

Expected: compilation and diff checks exit 0; only the Hub implementation, tests, design, and plan files are intended for staging. Do not stage `.superpowers/`, `tests/_sales_mapping_*`, or `tests/tmp*` artifacts.

- [ ] **Step 7: Commit the completed Hub**

```powershell
git add -- streamlit_app.py app/program_hub_ui.py tests/test_program_hub_ui.py tests/test_deposit_help_ui.py docs/superpowers/specs/2026-09-09-finance-operations-hub-design.md docs/superpowers/plans/2026-09-09-finance-operations-hub.md
git commit -m "feat: add finance operations hub"
```

- [ ] **Step 8: Present the local Hub for user review before pushing**

Launch the Streamlit app using the project’s configured runtime. Verify at desktop and narrow widths that the Hub opens first, only Daily Deposits is active, All Programs preserves Daily Deposit inputs, Start Over still clears Daily Deposit work, and the existing guided workflow still renders. Do not push until the user approves the visible result.
