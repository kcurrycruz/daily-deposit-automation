# InHouse Charges Guided Step Design

## Goal

Move the InHouse Charges breakdown out of the Closeout Sheet page and into its own guided step immediately before Closeout Sheet. Make repetitive memo entry faster while preserving explicit account coding and the existing Closeout over/short behavior.

## Workflow

- Add a guided step named **InHouse Charges**.
- Insert it immediately before **Closeout Sheet** in the fixed business order.
- Include the step only when the Balance Sheet Charge (House) amount is greater than zero.
- When Charge (House) is zero, omit the step entirely; the employee does not need to confirm an empty screen.
- Completing or editing an earlier step invalidates Closeout Sheet completion through the existing workflow rules.
- Editing InHouse Charges specifically reopens Closeout Sheet for review.

## InHouse Step

The step displays:

1. The Charge (House) System / BS amount for reference.
2. An editable **Charge (House) Actual**, defaulted to the System / BS amount.
3. One or more breakdown rows.
4. Actual, Breakdown Total, and Remaining summary values.

Each breakdown row contains, from left to right:

- searchable QuickBooks account;
- Memo Type dropdown;
- initials or custom memo input, depending on Memo Type;
- positive amount;
- remove action.

The employee can add or remove rows. At least one row is present while the step is required.

## Memo Behavior

The Memo Type dropdown contains exactly:

- **End of Day** — the default;
- **Custom**.

For **End of Day**:

- show an Initials field;
- trim whitespace and convert the initials to uppercase;
- require at least one non-whitespace character;
- save and export the final memo as `End of Day - <INITIALS>`, for example `End of Day - BS`.

For **Custom**:

- show a free-text Memo field;
- trim surrounding whitespace;
- require non-empty text;
- save and export the entered memo unchanged apart from surrounding whitespace.

The canonical saved row and IIF continue to contain only the final composed memo. UI-only fields do not alter the IIF payload format.

## Validation and Completion

- QuickBooks account is required.
- Initials or custom memo is required according to the selected Memo Type.
- Amount must be greater than zero.
- Breakdown Total must equal Charge (House) Actual to the cent.
- The step cannot be completed while any rule fails.
- Show clear inline feedback for missing row fields and a Remaining amount for total mismatches.

On completion, save the canonical rows and Charge (House) Actual, then advance to Closeout Sheet.

## Closeout Handoff

- Remove the editable InHouse row editor from the Closeout Sheet page.
- Populate Closeout Sheet Charge (House) Actual from the completed InHouse step.
- Display Charge (House) Actual as a locked breakdown-derived value on Closeout Sheet.
- Preserve the difference between System / BS and Actual in the reconciliation table.
- Preserve the existing `Over/Short per Closeout Sheet - Charge (House)` IIF calculation.
- If InHouse data is edited, the employee must review Closeout Sheet again before preparing the IIF.

## Save and Resume

- Reopening InHouse Charges restores every account, memo, amount, and Charge (House) Actual.
- A saved memo beginning with `End of Day - ` reopens as Memo Type **End of Day** with the suffix restored to Initials.
- Any other saved memo reopens as Memo Type **Custom** with the full memo restored.
- The legacy exact memo `End of Day` reopens as **End of Day** with blank Initials and requires initials before the step can be completed again.
- Row identifiers remain stable during add/remove reruns.

## Compatibility

- The canonical closeout payload remains account, memo, and amount based, so existing IIF generation does not need a new memo schema.
- Manual Closeout mode remains unchanged.
- Historical reviewed deposits containing valid InHouse rows remain readable.
- Existing dynamic steps and their ordering remain unchanged except for insertion of InHouse Charges before Closeout Sheet when required.

## Verification

Automated coverage will verify:

- dynamic step inclusion and zero-value omission;
- fixed placement immediately before Closeout Sheet;
- edit invalidation of Closeout Sheet;
- memo composition and validation for both modes;
- save/resume reconstruction of End of Day and Custom rows;
- Actual/total matching and one-cent mismatch rejection;
- Closeout handoff and over/short preservation;
- final IIF account, memo, amount, and ordering;
- unchanged manual workflow and full regression suite.
