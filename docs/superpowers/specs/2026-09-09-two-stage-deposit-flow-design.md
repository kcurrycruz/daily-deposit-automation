# Two-Stage Daily Deposit Flow Design

**Date:** September 9, 2026

## Goal

Reduce page clutter by separating report upload and validation from the guided deposit breakdown. Users should see only the controls needed for their current stage while retaining the verified reports in the background.

## User Flow

### Stage 1: Upload & Verify

The existing Daily Deposit header, Need Help content, operations status, Daily Workbook upload, Card Settlement upload, date detection, and validation feedback remain visible.

A primary **Continue to Deposit Steps** button appears at the end of the upload area. It remains disabled until:

- both reports are uploaded;
- the Daily Workbook contains the required usable content;
- the Card Settlement report is valid;
- both reports resolve to the same deposit date; and
- the existing upload-pair readiness checks pass.

The app never advances automatically. The user must click Continue after reviewing the verified status.

### Stage 2: Deposit Steps

Clicking Continue records that the reports were confirmed and reruns the app in the Deposit Steps stage. The upload controls, Need Help panels, upload validation details, and upload-stage status display are hidden to reduce clutter.

The main content begins with **Today’s Deposit Steps** and retains:

- the existing guided step rail;
- the verified Card Settlement notice in its current location;
- Member Share, activity, coupon, and closeout breakdown behavior;
- smooth scrolling and save-and-continue behavior;
- final validation, IIF preparation, review, and download behavior.

There is no Edit Uploaded Reports control. **Start Over** is the only way to return to the upload stage.

## State and Navigation

The app stores a small session-state value representing either `upload` or `deposit_steps`.

- New sessions begin in `upload`.
- Continue changes the stage to `deposit_steps` only when the current upload pair is ready.
- Normal Streamlit reruns preserve the current stage.
- Returning to the Finance Operations portal through **All Programs** preserves the current stage and deposit, matching the existing preservation behavior.
- Reopening Daily Deposit restores the preserved stage and files.
- **Start Over** clears the current deposit data, upload widgets, guided entries, results, and stage confirmation, then returns to `upload`.
- If the preserved reports are missing or no longer satisfy readiness checks, the app falls back safely to `upload`.

## Component Boundaries

Stage-state rules will live in a small testable helper rather than being embedded throughout the Streamlit page. The main app will use that helper to decide which section to render.

The existing upload renderer, verification logic, guided-step renderer, deposit engine, and portal routing remain the sources of truth. This change reorganizes when existing UI is displayed; it does not change deposit calculations or accounting mappings.

## Error Handling

- Continue is disabled and explains what remains incomplete when either report is missing or invalid.
- Date mismatches keep the user on Upload & Verify with the existing validation message.
- A stale or inconsistent confirmed-stage value cannot bypass readiness checks.
- Start Over remains available from both stages.

## Testing

Automated regression coverage will verify:

- new sessions begin at Upload & Verify;
- Continue remains unavailable until the full upload pair is ready;
- clicking Continue advances to Deposit Steps;
- the Deposit Steps stage hides upload-stage content;
- verified uploads and detected values survive the transition;
- normal reruns and portal navigation preserve the stage;
- invalid or missing preserved uploads fall back to Upload & Verify;
- Start Over clears the stage and returns to Upload & Verify;
- the existing full regression suite still passes.

## Out of Scope

- Changing workbook or Card Settlement validation rules
- Changing accounting mappings or IIF output
- Adding an Edit Uploaded Reports button
- Automatically advancing without user confirmation
- Redesigning the guided deposit steps shown after Continue
