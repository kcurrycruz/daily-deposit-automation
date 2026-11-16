# Deposit charge order and source tabs

## Intent

Make the Daily Deposit workflow easier to review against the paper Closeout Sheet and retain the six SMS inputs inside the downloadable SubDept workbook. Keep the existing deposit calculations and visible workbook layout intact.

## Agreed behavior

- InHouse Charges: add compact Up and Down controls beside each charge. Moving a row reorders the whole charge (account, memo, initials, signed amount), not its individual fields. Boundary controls are disabled or omitted. The order survives Streamlit reruns, saved drafts, and reopening the step, and is the order of the resulting InHouse IIF and preview lines. Totals and validation remain unchanged.
- SubDept workbook: append six hidden `SMS Input - <role>` worksheets (Sales, Coupon, Discounts, HASH, BS, Milk Bottles) that a user can unhide for review. Copy each uploaded export's parsed cell grid to its own hidden sheet, retaining the original row and column positions and values. These are supporting inputs, not new calculation sources. Existing visible report and supporting tabs remain in their current order and retain their current values, formatting, and formulas. The original binary `.xls` files and their exact source styling are not embedded.
- Closeout Sheet: show `Category | Actual | System / BS | Difference | Status` in the entry grid and `Category | Actual | System / BS | Difference` in the review grid. The actual field stays editable where it is now; only its display position changes. Difference continues to mean Actual minus System / BS. No accounting or IIF sign logic changes.

## Approaches considered

- Chosen: native Streamlit Up/Down buttons; six extra hidden raw-value tabs. This uses the app's current session-state row order and existing workbook builder, with no new UI dependency or visible workbook redesign.
- Not chosen: drag-and-drop charge ordering. It would need a custom component and complicate keyboard use and saved-state handling.
- Not chosen: repurpose or hide the current five supporting tabs. Those tabs contain transformed data and are part of the existing workbook layout; doing so would change the report beyond the request and still not preserve all six original inputs.

## Verification

- Test first, middle, and last charge moves; ensure account, memo, initials, and signed amount remain paired, the total is unchanged, and saved/restored/IIF order matches.
- Build a SubDept workbook from six fixture exports; verify all six hidden input tabs preserve source grids, the visible sheet list/layout remains intact, and the generated report and IIF totals are unchanged.
- Verify both Closeout grids show Actual on the left of System / BS while differences retain their existing values.

## Scope

This changes the Daily Deposit app and its generated workbook. It does not change SMS parsing, QuickBooks accounts, deposit math, or the user's original uploaded files. No deployment or push is implied until separately requested.
