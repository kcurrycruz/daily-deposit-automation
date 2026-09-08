# Guided Upload Intake Design

## Goal

Replace the current scattered upload area with a clear, operations-style intake flow that guides a daily user through adding the Daily Workbook and Card Settlement report before beginning Today’s Deposit Steps.

The redesign is presentation-only. It must preserve all existing workbook parsing, accounting calculations, validation rules, generated IIF behavior, session persistence, and Start Over behavior.

## Approved Direction

The approved layout combines:

- Choice A’s visible numbered guidance and explanation of what belongs in each file.
- Choice B’s compact panel layout and the heading **Upload deposit reports**.
- Both upload controls remain visible at the same time so an experienced user can add the reports in either order without navigating between screens.

## Page Structure

### Heading

The intake begins with:

- Title: **Upload deposit reports**
- Supporting copy: **Add both reports for today. We’ll check the dates and contents automatically.**

The upload flow appears before the long SOP and Known Exceptions content so the routine daily task is the first actionable area.

### Upload progress

A connected three-bubble indicator appears above the upload cards:

1. **Daily Workbook**
2. **Card Settlement**
3. **Ready**

The visual state changes as files are added:

- Pending: muted outline and text.
- Current: green bubble with a soft focus ring.
- Complete: green bubble with a check mark and green connecting line.
- Ready: complete only when both files are present; validation messages may still require the user’s attention before the deposit can be prepared.

The progress indicator describes upload completion only. It must not replace or weaken the existing workbook, date, settlement-header, or final-deposit validations.

### Daily Workbook card

The card contains:

- Numbered Step 1 bubble.
- Title: **Daily Workbook**.
- Expected workbook badges: **Sales**, **Coupons**, **Discounts**, **Balance Sheet**, and **HASH**.
- Existing XLSX/XLSM uploader and 200 MB limit.

Before upload, the card has a neutral/pending appearance. After upload:

- Show the uploaded filename.
- Show the detected report date when available.
- Show each detected workbook role in a compact badge row.
- Use a green completed appearance only when the expected workbook roles are detected and the report date is readable.
- Keep existing warning/error text available inline when dates conflict, roles are missing, or the date cannot be read.
- Let the existing uploader replacement/removal behavior continue to work.

### Card Settlement card

The card contains:

- Numbered Step 2 bubble.
- Title: **Card Settlement**.
- Explanation: **Processed Net Amount report for the same deposit date.**
- Existing XLSX/XLSM uploader and 200 MB limit.

Before upload, the card has a neutral/pending appearance. After upload:

- Show the uploaded filename.
- Show the detected settlement date when available.
- Use a green completed appearance when the exact required settlement headers are found.
- Keep the existing header mismatch and date mismatch messages inline with this card.
- Let the existing uploader replacement/removal behavior continue to work.

### Readiness footer

The bottom of the upload panel shows:

- **0 of 2 reports added**, **1 of 2 reports added**, or **2 of 2 reports added**.
- A compact progress bar.
- A muted **Continue when ready** state until both files are present.
- A green **Ready for Today’s Deposit Steps** state when both files are present.

When the second file is added, preserve the existing one-time smooth scroll to Today’s Deposit Steps. The page must not repeatedly scroll on later Streamlit reruns.

## Help Content

Daily Workbook SOP and Tips & Known Exceptions remain available and their content is unchanged. They move beneath the upload panel under a quieter **Need help?** area so they do not interrupt routine daily entry.

## Responsive Behavior

- Desktop: upload card details and uploader sit side by side in a compact row.
- Narrow screens: each upload card stacks its description above its uploader.
- The three progress bubbles remain connected and horizontally readable.
- Filenames and detected sheet names wrap instead of overflowing.

## Accessibility and Copy

- The stepper uses meaningful labels for pending, current, and completed states.
- Status must not rely on color alone; include text or a check mark.
- Preserve Streamlit’s native file-uploader keyboard and screen-reader behavior.
- Use the user-facing terms **Daily Workbook**, **Card Settlement**, and **Today’s Deposit Steps** consistently.

## Error Handling

- File-specific errors appear with the corresponding upload card.
- Date mismatch warnings retain the two dates and do not block the upload flow unless existing business logic already blocks a later action.
- Missing workbook roles remain explicit; no role is silently treated as valid.
- A rerun must preserve the currently uploaded files and the completed visual state.

## Out of Scope

- Accounting mappings or calculations.
- Changes to Donations, Paid In, Paid Out, Coupons Receivable, Member Share Payments, Closeout Sheet, or In-House Charges.
- Changes to IIF generation or QuickBooks import behavior.
- New file types or a larger upload limit.
- Changing the existing rule that Today’s Deposit Steps appear and receive a one-time smooth scroll after both files are supplied.

## Acceptance Criteria

1. The first routine action visible to the user is the **Upload deposit reports** intake panel.
2. Both required upload controls are visible at once.
3. The three-bubble upload indicator correctly represents zero, one, and two uploaded files.
4. The Daily Workbook card states the five expected workbook roles.
5. Uploaded filenames and detected dates are shown without removing current validation details.
6. SOP and Known Exceptions remain accessible below the intake panel.
7. Today’s Deposit Steps remain hidden until both files are supplied and receive exactly one smooth scroll when the pair first becomes ready.
8. Existing parsing, reconciliation, IIF, and guided-step tests continue to pass.
