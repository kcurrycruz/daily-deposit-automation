# Final fix report — Card Settlement date-not-detected upload warning

## Scope

Implemented the final-review correction only: a Card Settlement upload with valid
source headers, no parsing exception, and no detected date now displays:

`Card Settlement report date not detected—upload a report with its date.`

The existing `settlement_status_valid` condition still requires a detected date, so
Continue remains disabled. No calculation, mapping, IIF, page-stage, or navigation
logic changed.

## Root cause

`streamlit_app.py` previously rendered a specific date warning only when settlement
date parsing raised an exception. A parsed workbook with no `Date` value produced no
exception and therefore fell through to the generic operations status.

## Test-driven evidence

1. Added `test_missing_settlement_date_warning_requires_an_otherwise_valid_report`.
   It asserts the message for a present, valid-source report with no detected date
   and no exception; it asserts no message for an absent report, invalid source,
   parser exception, or detected date.
2. RED: `python -m unittest tests.test_upload_intake_ui` failed with the expected
   `ImportError` because `missing_settlement_date_warning` did not yet exist.
3. GREEN: after the minimal helper and upload-stage renderer call were added,
   `python -m unittest tests.test_upload_intake_ui tests.test_current_deposit_state`
   ran 25 tests successfully.

## Implementation

- Added `missing_settlement_date_warning` to `app/upload_intake_ui.py`.
- Called it only in the existing settlement-file branch and rendered its result only
  while `requested_page_stage == UPLOAD_STAGE`.
- The helper requires all four conditions: present file, valid source headers, no
  detected date, and no parse exception. This avoids duplicating the exception
  warning and prevents the new warning for absent or invalid-source files.

## Verification

- Focused/related: 25 tests passed.
- Full suite: `python -m unittest discover -s tests` ran 275 tests successfully.
- The first full-suite attempt was blocked by sandbox write restrictions on existing
  tests' temporary fixtures (37 permission errors); after restricted write access to
  this worktree was granted, the same discover command passed.
- The full run emitted pre-existing Windows `cp1252` logging encoding tracebacks for
  arrow characters, but exited zero and all 275 tests passed.
- Self-review confirmed the new message is upload-stage-only and is gated by the
  requested four conditions; readiness still requires `settlement_date_info is not None`.

## Files changed

- `app/upload_intake_ui.py`
- `streamlit_app.py`
- `tests/test_upload_intake_ui.py`
