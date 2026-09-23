# InHouse Charges Design

## Goal

Replace the generic Charge (House) QuickBooks placeholder with an employee-entered breakdown of searchable QuickBooks accounts, memos, and positive amounts.

## Employee workflow

- The Closeout Sheet step displays an **InHouse Charges** section whenever the Charge (House) system amount is greater than zero.
- Each row contains, from left to right, a searchable QuickBooks account, a memo defaulted to `End of Day`, a positive amount, and a remove action.
- The section starts with one row and supports adding and removing rows.
- A summary shows the Charge (House) target, breakdown total, and remaining amount.
- The Charge (House) Actual in the reconciliation table is locked to the breakdown total and labeled `(breakdown)`.
- Review Closeout remains unavailable until the breakdown total exactly equals the Charge (House) system amount.
- When Charge (House) is zero, no breakdown rows are required and no InHouse IIF lines are produced.
- Reopening the Closeout step restores every saved row.

## QuickBooks behavior

- Each breakdown row becomes its own deposit split using the selected account, entered memo, and positive IIF amount.
- The previous `4444 · TBA Purchases` InHouse line and its five blank placeholder rows are omitted when the reviewed Closeout workflow is active.
- The existing `Over/Short per Closeout Sheet - Charge (House)` calculation remains unchanged.
- The sum of InHouse split amounts must equal the Closeout Charge (House) actual before an IIF can be reviewed or generated.

## Validation

- Account is required and must not contain IIF delimiters.
- Memo is required, defaults to `End of Day`, and must not contain tabs or line breaks.
- Amount must be greater than zero.
- Duplicate accounts are allowed because separate source charges may need separate memos.
- Currency comparisons are performed to the cent.

## Compatibility

- Manual Closeout mode remains unchanged.
- Donation, Paid In, Paid Out, Coupons, final POS approval, and the reporting workbook remain unchanged.
- Existing historical payloads without an InHouse breakdown reopen for employee review instead of silently producing TBA placeholders.
