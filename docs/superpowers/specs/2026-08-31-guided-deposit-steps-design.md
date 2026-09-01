# Guided Deposit Steps Design

Date: 2026-08-31

## Objective

Replace the current stack of independent breakdown sections with a guided, numbered workflow. After the Daily Workbook is uploaded, the app tells the employee exactly which activities require attention for that deposit, shows only the current unfinished activity in full, and always ends with the Closeout Sheet.

This is a presentation and workflow-state change only. Existing accounting calculations, QuickBooks accounts, memos, signs, reconciliation rules, IIF ordering, workbook detection, and manual QuickBooks behavior remain unchanged.

## Required-step detection and order

The app builds the step list from the uploaded workbook in this fixed business order:

1. Member Share Payments, when Subscription Revenue is nonzero.
2. Donations, when the Balance Sheet Donation total is nonzero.
3. Paid In, when the HASH Paid-In total is nonzero.
4. Paid Out, when the Balance Sheet Paid Out total is nonzero.
5. Coupons Receivable, when the detected Balance Sheet Coupons Receivable total is nonzero.
6. Closeout Sheet, always included and always last.

Only required activities receive step numbers. Numbers close gaps automatically. For example, a deposit with only Paid In becomes:

1. Paid In
2. Closeout Sheet

The workbook and card-settlement upload controls remain outside the numbered workflow. Existing validation errors that prevent reliable detection appear before the steps and keep the final build action unavailable.

## Today’s Deposit Steps summary

After source totals are read, the app displays a compact `Today’s Deposit Steps` summary above the forms. Each required step shows one of four statuses:

- `Current` — the only step whose full controls are visible.
- `Pending` — waiting for an earlier step.
- `Completed in app` — valid data was entered and saved in the app.
- `Finish in QuickBooks` — the employee explicitly chose the existing manual workflow.

Completed steps include an `Edit` control. The summary is the employee’s main orientation point; employees should not need to scroll through unopened forms to discover what is required.

## Guided progression

The active step is the first required step that is not complete. Only that step renders its full existing controls. Later steps remain compact and cannot be opened until preceding steps are complete.

A step becomes complete when either:

- its in-app inputs satisfy the section’s existing validation and reconciliation rules and the employee selects `Save & Continue`; or
- the employee selects `Finish manually in QuickBooks`.

Selecting the manual option counts as completion immediately because the employee has made the required handling decision. The next step opens on the following Streamlit rerun.

Every in-app section has one clear `Save & Continue` action at its bottom. Invalid inputs keep the section open and display the existing specific validation message. Merely typing a value never collapses the current section.

The Closeout Sheet cannot become the active step until every preceding required activity has a completed handling decision. This preserves the current rule that app-based Closeout reconciliation depends on valid in-app activity and coupon data.

The final `Validate & Prepare IIF` action stays outside the guided step panels. It is enabled only when all required steps, including Closeout Sheet, are complete and the existing workbook and card-settlement checks pass.

## Editing completed steps

Selecting `Edit` on a completed step reopens that step with its previously saved choice and values. Data saved in later steps is preserved, but the Closeout Sheet is marked pending because its reconciliation may depend on the edited values.

If the employee edits Closeout Sheet itself, only Closeout completion is cleared. If the employee changes an earlier activity from in-app to manual or changes an amount, later activity entries remain stored and can be reviewed again without retyping them.

After the edited step is valid again, the workflow returns to the first incomplete step. If all intermediate steps were already complete, Closeout Sheet becomes current so the employee can review and reconfirm it.

## Workflow state model

Add a focused workflow-state module, separate from Streamlit rendering and accounting logic. It owns step discovery, ordering, status, active-step selection, completion, and invalidation. It does not calculate accounting entries.

The module exposes small, testable operations equivalent to:

- build required steps from detected source totals and the existing coupon requirement;
- return the first incomplete or explicitly edited step;
- mark a step complete with either `app` or `quickbooks` handling;
- reopen a completed step for editing;
- invalidate Closeout completion after an earlier step is edited;
- report whether the final IIF action is eligible.

Each workflow is scoped to the existing workbook identity key so data from one deposit cannot appear in another deposit. Streamlit session state stores:

- the required step identifiers;
- completion status and completion method per step;
- the currently edited step, when applicable;
- the existing section-specific saved payloads and widget state.

The workflow coordinator references the existing saved payloads rather than duplicating accounting data. Hidden completed sections reconstruct their engine inputs from their saved payloads or saved handling choice. This is required so hiding a widget does not cause its values to disappear during a Streamlit rerun.

## Section completion rules

### Member Share Payments

- Required when Subscription Revenue is nonzero.
- `Finish manually in QuickBooks` completes the step using the existing unnamed Member Shares behavior.
- In-app mode completes only when the saved member payments reconcile to Subscription Revenue under the existing membership validation.

### Donations, Paid In, and Paid Out

- Each is required only when its existing source detector returns a nonzero total.
- `Finish manually in QuickBooks` completes the corresponding step.
- In-app mode completes only when the section payload passes the existing normalization and validation rules.
- Existing rows, account choices, memos, signs, and totals are unchanged.

### Coupons Receivable

- Required when the detected Balance Sheet Coupons Receivable total is nonzero.
- `Finish manually in QuickBooks` completes the step using the existing behavior.
- In-app mode completes only when NCG plus MFG equals the entered Closeout Sheet Coupon Actual total and existing coupon validation passes.
- When the coupon total is zero, the step is omitted. An in-app Closeout uses a zero Vendor Coupons actual without inserting a new earlier step.

### Closeout Sheet

- Always required and always last.
- `Finish manually in QuickBooks` completes the step using the existing manual Closeout payload.
- In-app mode completes only when the existing Closeout review, reconciliation, confirmations, and final-total rules pass.
- Editing any preceding step clears the saved Closeout preview and completion marker but preserves the employee’s Closeout inputs where safe. The employee must review and confirm Closeout again before building the IIF.

## Streamlit integration

The existing section renderers are retained but placed behind the active-step decision. The monolithic page should use focused rendering helpers for the guided summary and each activity panel where practical; the change must not refactor unrelated deposit or IIF code.

The integration sequence is:

1. Read workbook roles and source totals using the existing readers.
2. Build the required ordered step list.
3. Load workflow status for the workbook identity.
4. Render `Today’s Deposit Steps`.
5. Render only the active step’s full controls.
6. Reconstruct all completed section payloads from saved state for validation and IIF generation.
7. Gate Closeout and `Validate & Prepare IIF` on workflow completion plus existing validations.

Status changes trigger a controlled Streamlit rerun so the newly current step appears immediately. The app must not automatically mark an in-app step complete merely because default values happen to be valid; `Save & Continue` or the existing Closeout review confirmation is required.

## Error handling

- If a source total cannot be read reliably, the existing error or warning remains visible and the app does not silently omit a potentially required step.
- If saved workflow state references a step that is no longer required for the current workbook identity, that stale status is ignored.
- If a saved payload no longer passes current validation, its step returns to `Current` rather than allowing the IIF to build.
- Hidden-section payload reconstruction errors identify the affected step and reopen it for correction.
- Changing or removing an uploaded workbook isolates or clears the visible workflow through the existing workbook-key mechanism.

## Testing strategy

Add pure workflow-state tests for:

- all combinations of detected optional steps;
- fixed business ordering and gap-free numbering;
- Closeout Sheet always present and always last;
- first-incomplete active-step selection;
- manual QuickBooks selection counting as completion;
- valid in-app selection counting as completion;
- reopening a completed step;
- preserving later payloads while invalidating Closeout completion;
- rejecting a stale or invalid saved payload;
- isolating workflow state by workbook identity;
- final IIF eligibility only after all steps complete.

Add focused Streamlit integration tests or source-level assertions for:

- the `Today’s Deposit Steps` summary and statuses;
- rendering only the active step’s full controls;
- the `Edit` action;
- Closeout gating and final button gating;
- reconstruction of hidden membership, activity, coupon, and Closeout payloads.

Run the full existing test suite to prove accounting behavior and current workflows remain intact.

## Out of scope

- Changes to account mappings, signs, memos, or IIF ordering.
- New breakdown categories.
- OCR or automatic reading of paper forms.
- A general-purpose wizard framework outside this deposit page.
- Persisting unfinished workflows outside the current Streamlit session.
