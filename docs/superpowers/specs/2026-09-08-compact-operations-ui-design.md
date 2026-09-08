# Compact Operations UI Design

**Date:** September 8, 2026  
**Status:** Approved visual direction; implementation pending user review  
**Reference:** Compact Operations with Guided Bubble Steps mockup

## Goal

Make the daily deposit workflow feel simpler, faster, and more polished for an operator completing the process every day. Improve visual hierarchy and progress awareness without changing accounting logic, mappings, validation rules, or the guided workflow behavior already approved.

## Design Direction

Use **Compact Operations** as the primary page layout. At the top of the working area, show a quiet three-part status strip:

1. **Deposit date** — detected from the uploaded Daily Workbook.
2. **Files** — progress and validation state for the Daily Workbook and Card Settlement.
3. **IIF status** — what the operator must do next or whether the IIF is ready.

The status strip uses compact text and subtle separators instead of additional cards. Its values update as the operator moves through the workflow.

## Main Page Structure

The page remains in this order:

1. Existing HWFC Finance header.
2. Existing static **Need Help** label and original expandable Daily Workbook SOP and Tips & Known Exceptions.
3. Existing **Start Over** action.
4. Compact Operations status strip.
5. Current workflow content.
6. Existing footer.

The collapsed Run History remains in the sidebar.

## Upload and Validation

Keep the existing horizontal upload arrangement:

- Report Date detector
- Daily Workbook upload
- Card Settlement upload

The guided deposit workflow must not appear until both required files have been uploaded and validated. When both files validate, preserve the existing automatic scroll into Today’s Deposit Steps.

The Card Settlement verification message remains directly below workbook validation.

## Guided Breakdown

When guided breakdown begins, retain the existing horizontal bubble stepper:

- Show only activities detected for the current deposit.
- Display completed steps with checkmarks.
- Clearly distinguish the current step.
- Display pending steps without excessive emphasis.
- Keep **Closeout Sheet** as the final step every time.
- Do not add a left progress rail during guided breakdown; it would duplicate the bubble stepper.

Each current breakdown section continues using the established behavior:

- Choose **Breakdown in app** or **Finish manually in QuickBooks**.
- Preserve entries when returning to edit a completed step.
- Smooth-scroll to the active form after choosing in-app breakdown.
- Smooth-scroll toward **Save & Continue** when adding another item.
- Show the final Validate/Prepare IIF action only after all required steps are complete.

## Existing Features That Must Remain Unchanged

- Member Share payment options and editable defaults
- Donation default of $100
- Paid In positive and Paid Out negative rules
- Matching Paid In/Paid Out account dropdowns and required memos
- Coupons Receivable workflow
- Closeout Sheet reconciliation and required final total
- Card Settlement verification
- HASH/BS/date detection
- Books combined with Magazines
- CDTA Star Pass mapping and memo calculation
- Unrecognized and nonstandard amounts routed to TBA
- Existing QuickBooks IIF generation and download behavior
- Existing validation, error messages, edit behavior, and scrolling

## Responsive Behavior

On desktop, the compact status strip remains one horizontal row. On narrow screens, it stacks cleanly without horizontal scrolling. The horizontal bubble stepper may compress or wrap as needed, but labels and the current step must remain readable.

## Error and Readiness States

The status strip must use plain operational language:

- Before upload: **Waiting for workbook**, **0 of 2 uploaded**, **Not ready**
- One file uploaded: identify which required file is missing
- Files validated: show the detected date, **2 of 2 verified**, and **Complete guided steps**
- Guided steps complete: show **Ready to prepare IIF**
- Validation problem: show **Needs attention** and keep the existing detailed error message near the affected input

Color supports status but never carries meaning alone.

## Implementation Boundaries

This is a presentation-focused change. The accounting engine and transaction-building logic must not be refactored as part of this work. UI code may be extracted into focused rendering helpers when needed for clear testing, but behavior and data contracts remain unchanged.

## Verification

Before the user reviews the working app:

1. Add tests for status-strip values and transitions.
2. Add tests protecting the horizontal upload layout and bubble-step behavior.
3. Run the complete automated test suite.
4. Run syntax checks on all changed Python files.
5. Check the interface at desktop and narrow widths.
6. Confirm no tracked changes are pushed.

The user will review the working local app before any commit or push instructions are provided.
