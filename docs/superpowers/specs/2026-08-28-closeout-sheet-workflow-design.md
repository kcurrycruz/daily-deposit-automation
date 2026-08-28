# Closeout Sheet Reconciliation Workflow Design

Date: 2026-08-28

## Objective

Add an optional, guided Store Closeout reconciliation stage to the Streamlit app. The workflow compares the paper Closeout Sheet actuals with the system control amounts already detected by the deposit engine, replaces the affected QuickBooks detail with the actual amounts, and adds clearly labeled offsetting lines so the transaction remains auditable.

The paper Closeout Sheet varies from day to day, so the feature must support the eight recurring categories, a small set of approved miscellaneous adjustments, and flexible TBA entries without making the Closeout workflow mandatory.

## Workflow choice

When Closeout reconciliation is applicable, the app presents two choices before the deposit is built:

1. `Reconcile using Closeout Sheet`
2. `Finish manually in QuickBooks`

The manual choice preserves the current deposit-generation behavior and adds no new Closeout lines. The in-app choice requires the standard review, final Closeout total, and all validation described below.

## Standard reconciliation table

The table appears in this exact order:

| Order | Category | System baseline | Default Closeout actual |
|---:|---|---|---|
| 1 | Cash | Balance Sheet code 901 | System baseline |
| 2 | Checks | Balance Sheet code 902 | System baseline |
| 3 | Donation | Balance Sheet code 1122 | System baseline |
| 4 | Charge (House) | Balance Sheet code 906 | System baseline |
| 5 | Offline Zon | Balance Sheet code 934 or 1334 | `$0.00` |
| 6 | Vendor Coupons | Balance Sheet code 908 | Existing NCG + MFG actual total |
| 7 | Paid Out | Balance Sheet code 1114 | System baseline |
| 8 | Paid In | Existing HASH code 34 Paid-In total | System baseline |

Paid In intentionally continues to originate from HASH. Its presence in the Closeout table provides a second check against the paper Closeout Sheet; it does not replace HASH as the original source.

Employees enter positive face amounts for all eight standard actuals. The engine continues to own the account-specific QuickBooks direction, including Paid Out reducing the deposit. Baseline values are normalized for positive, human-readable comparison in the UI.

Each row displays:

- System/BS amount
- Closeout Actual
- Difference, calculated as `Actual - System baseline`
- Match or discrepancy status

The employee must confirm `I reviewed these amounts against the paper Closeout Sheet` before continuing.

Offline Zon is expected to be zero on nearly every day. Its actual defaults to zero but remains editable for the rare day when an amount appears.

## Standard QuickBooks posting rules

Cash and Checks are system control amounts but are not separate SPL detail lines in the current IIF. Their signed Closeout differences post directly to `8314000 · FE - Cash Over/Shorts` and therefore change the generated deposit toward the paper Closeout result.

Donation, Charge (House), Offline Zon, Vendor Coupons, Paid Out, and Paid In already have corresponding QuickBooks detail. For these categories, the app replaces that detail with the Closeout Actual and creates an offsetting line on `8314000 · FE - Cash Over/Shorts`. This shows the actual category amount and reclassifies the discrepancy without double-counting it.

The table's human-readable difference remains `Actual - System baseline`. The signed QuickBooks offset for a replacement category is calculated as:

`Baseline QuickBooks effect - Actual QuickBooks effect`

This category-aware calculation is required because employees enter positive face amounts while some categories add to the deposit and others reduce it. The app must not blindly use the raw displayed difference as the IIF sign.

Only nonzero differences create new category-specific adjustment lines.

| Category | Difference memo |
|---|---|
| Cash | `Over/Short per Closeout Sheet - Cash` |
| Checks | `Over/Short per Closeout Sheet - Check` |
| Donation | `Over/Short per Closeout Sheet - Donation` |
| Charge (House) | `Over/Short per Closeout Sheet - Charge (House)` |
| Offline Zon | `Over/Short per Closeout Sheet - Offline Zon` |
| Vendor Coupons | `Over/Short per Closeout Sheet - Coupon` |
| Paid Out | `Over/Short per Closeout Sheet - Paid Out` |
| Paid In | `Over/Short per Closeout Sheet - Paid In` |

Vendor Coupons reuses the existing NCG/MFG counter and reconciliation. The Closeout workflow must not duplicate or replace that calculation. Donation replaces only the Balance Sheet Donation component; the separate HASH Pass Through Donation component remains unchanged.

## Approved miscellaneous adjustments

### Payroll - Check Cashing

- Choices: no adjustment, `+$4,000.00`, or `-$4,000.00`
- Account: `1140000 · Cash Drawers/Safe`
- Memo: `Payroll - Check Cashing`
- QuickBooks effect: exactly the selected signed amount
- No other Payroll amount is accepted

### Safe adjustment

The employee selects no adjustment, Overage, or Shortage and enters a positive magnitude.

- Account: `8314000 · FE - Cash Over/Shorts`
- Overage effect: positive
- Overage memo: `Safe Overage Cash added to deposit`
- Shortage effect: negative
- Shortage memo: `Safe Shortage Cash Taken from Deposit`

### Plants Department market purchases

- Employee enters a positive magnitude
- Account: `1130000 · Petty Cash`
- Memo: `Plants Dept - Market Purchases`
- QuickBooks effect: always negative

### Other miscellaneous items

The app allows add/remove rows containing:

- Required memo
- Positive magnitude
- Direction: `Adds to deposit` or `Removes from deposit`

These rows post to `4444 · TBA Purchases`. They remain at the bottom of the generated IIF for the employee to correct in QuickBooks.

## Final Closeout balancing

The employee enters a positive `Final Closeout Sheet Deposit Total`.

After standard replacements and all approved miscellaneous adjustments, the app calculates:

`Remaining difference = Final Closeout Sheet Deposit Total - Generated deposit`

If the remaining difference is zero, the Closeout workflow is reconciled. If it is nonzero, the app displays the exact signed difference and offers an explicit `Add final POS adjustment` confirmation.

When approved, the final difference posts to:

- Account: `8314000 · FE - Cash Over/Shorts`
- Memo: `Over/Short per POS (to = POS total)`
- Effect: exact signed remaining difference

The app must never add this last-resort line silently.

## Validation and error handling

The app blocks `Validate & Build Deposit` until all applicable requirements pass:

- A Closeout handling choice is selected.
- The paper Closeout review confirmation is checked in in-app mode.
- All eight actuals are nonnegative numbers.
- NCG + MFG equals the Vendor Coupon actual.
- Payroll is absent or exactly positive/negative `$4,000.00`.
- Safe and Plants adjustments have valid positive magnitudes when enabled.
- Every custom TBA row has a memo, positive magnitude, and direction.
- A positive Final Closeout Sheet Deposit Total is entered.
- The generated deposit equals the final Closeout total.
- Any final POS adjustment was explicitly approved.

Validation messages identify the specific row or adjustment that requires attention. Switching to manual QuickBooks mode bypasses only the new Closeout inputs; it does not bypass existing workbook, membership, coupon, or card-settlement validation.

## Review UI

Before the deposit is built, the app shows:

1. The eight-row reconciliation table with System/BS, Actual, Difference, and Status.
2. A preview of each generated Closeout line with account, memo, and signed QuickBooks effect.
3. The deposit total before Closeout changes, the total after approved adjustments, the Final Closeout total, and remaining difference.
4. A distinct warning and confirmation for the last-resort POS adjustment.

The UI uses positive entry fields plus explicit direction controls wherever possible so employees do not have to reason about IIF sign inversion.

## IIF ordering

Generated lines appear in this order:

1. Existing normal deposit lines
2. Standard Closeout difference lines in the approved eight-category order
3. Payroll, Safe, and Plants Department adjustments
4. Final POS balancing line, when approved
5. Custom Closeout TBA entries and all existing unique-account TBA lines last

Zero standard differences do not add category-specific adjustment lines. Existing intentional MFG/TBA/Cash Over-Short template placeholders remain governed by the current IIF cleanup rules.

## Architecture

Closeout logic is isolated from Streamlit rendering and the existing engine:

- A new Closeout reconciliation module owns normalization, difference calculation, validation, miscellaneous mappings, final balancing, and preview records.
- Streamlit owns input widgets and session state, then passes a validated Closeout payload to the engine.
- The command-line engine accepts the Closeout payload through a temporary JSON file, following the established member-share pattern.
- IIF generation consumes the validated records and inserts them at the defined ordering boundary.
- Manual QuickBooks mode sends no Closeout payload and preserves existing behavior.

The JSON payload records the handling mode, eight actuals, review confirmation, preset adjustments, custom TBA rows, final Closeout total, and final POS approval. The engine revalidates the payload rather than trusting UI validation.

## Testing strategy

Automated tests cover:

- Baseline normalization and all eight differences
- Offline Zon default-zero behavior
- Paid In comparison against HASH code 34
- Vendor Coupons integration without duplicate coupon adjustment lines
- Exact accounts, memos, signs, and allowed Payroll values
- Safe, Plants, and custom TBA validation
- Final total and explicit last-resort approval
- Manual mode preserving the current IIF
- Required IIF ordering, with TBA entries last
- Streamlit-to-engine payload propagation

Representative positive and negative discrepancy scenarios are derived by hand so tests verify the accounting effect rather than mirror implementation calculations.

## Companion bounded member-share change

When `Paid in full — $100` is selected in the member-share form:

- `In QuickBooks?` defaults to `No`.
- Member Name is cleared and disabled.
- Amount remains locked/defaulted to `$100.00`.
- The payment is treated as an unnamed Member Shares line for completion by creating the new member in QuickBooks.
- The employee may change `In QuickBooks?` to `Yes`; doing so enables the exact QuickBooks Member Name field.

This change is logically separate from Closeout reconciliation and must have its own focused tests.

## Out of scope

- OCR or automatic ingestion of the paper Closeout Sheet
- Automatically choosing an account for custom miscellaneous items
- Accepting arbitrary Payroll amounts
- Silently forcing a deposit to balance
- Removing the existing manual QuickBooks workflow
