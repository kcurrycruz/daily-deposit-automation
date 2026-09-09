# Task 1 Report — Program Registry and Safe Navigation State

## Files changed

- `app/program_hub_ui.py`
- `tests/test_program_hub_ui.py`

## RED

Command:

```text
& 'C:\Users\karlcruz\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_program_hub_ui
```

Output:

```text
EEEEE
======================================================================
ERROR: test_activate_daily_deposits_sets_active_key_and_preserves_state (tests.test_program_hub_ui.ProgramHubStateTests.test_activate_daily_deposits_sets_active_key_and_preserves_state)
----------------------------------------------------------------------
Traceback (most recent call last):
  ...
ModuleNotFoundError: No module named 'app.program_hub_ui'

======================================================================
ERROR: test_activate_disabled_program_does_not_mutate_existing_active_state (tests.test_program_hub_ui.ProgramHubStateTests.test_activate_disabled_program_does_not_mutate_existing_active_state)
----------------------------------------------------------------------
Traceback (most recent call last):
  ...
ModuleNotFoundError: No module named 'app.program_hub_ui'

======================================================================
ERROR: test_daily_deposits_is_only_enabled_program_in_required_order (tests.test_program_hub_ui.ProgramHubStateTests.test_daily_deposits_is_only_enabled_program_in_required_order)
----------------------------------------------------------------------
Traceback (most recent call last):
  ...
ModuleNotFoundError: No module named 'app.program_hub_ui'

======================================================================
ERROR: test_normalize_selection_rejects_missing_disabled_and_unknown_keys (tests.test_program_hub_ui.ProgramHubStateTests.test_normalize_selection_rejects_missing_disabled_and_unknown_keys)
----------------------------------------------------------------------
Traceback (most recent call last):
  ...
ModuleNotFoundError: No module named 'app.program_hub_ui'

======================================================================
ERROR: test_return_to_program_hub_removes_only_active_key (tests.test_program_hub_ui.ProgramHubStateTests.test_return_to_program_hub_removes_only_active_key)
----------------------------------------------------------------------
Traceback (most recent call last):
  ...
ModuleNotFoundError: No module named 'app.program_hub_ui'

----------------------------------------------------------------------
Ran 5 tests in 0.004s

FAILED (errors=5)
```

## GREEN

Command:

```text
& 'C:\Users\karlcruz\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_program_hub_ui
```

Output:

```text
.....
----------------------------------------------------------------------
Ran 5 tests in 0.017s

OK
```

## Self-review

The implementation is limited to the requested immutable registry and three state transitions. Invalid, disabled, and unknown selections return `None`/`False` without mutating state; valid activation and hub return touch only the active-program key. No Streamlit import or new dependency was added.

## Concerns

None.
