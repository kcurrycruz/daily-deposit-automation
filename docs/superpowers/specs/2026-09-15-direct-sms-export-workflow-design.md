# Direct SMS Export Workflow Design

## Goal

Replace the manually assembled Daily Workbook upload with one upload area for six raw SMS Excel exports while preserving every existing Daily Deposit calculation, guided step, QuickBooks mapping, and safety check. After the entire deposit and IIF process succeeds, also produce the completed reporting workbook named `SubDept Single Total Report M-D-YY.xlsx`.

## User Workflow

The Upload and Verify page keeps the separate Card Settlement uploader and replaces the Daily Workbook uploader with one multi-file SMS Reports uploader. The user can drag these six `.xls` exports into that uploader in any order:

1. Sales
2. Coupons
3. Discounts
4. HASH
5. Balance Sheet
6. Milk Bottles

The app identifies each report from its contents, not only its filename. A compact checklist shows which of the six report types are present and displays progress such as `4 of 6 verified`. The user can add missing files without losing files already accepted.

The current two-stage flow remains intact. The user cannot continue to the guided deposit steps until all six SMS reports and the Card Settlement report pass validation.

## Input Detection and Validation

The app reads the legacy SMS `.xls` files with `xlrd`. Each file must match exactly one report role:

- Sales: `Sub-department Single Total` with Totalizer range 3 through 4.
- Coupons: `Sub-department Single Total` with Totalizer 3542.
- Discounts: `Discounts by Shopper Level`.
- HASH: `Sub-department Single Total` with Totalizer 6, or content containing the established HASH activity markers.
- Balance Sheet: `Store Balance Sheet`.
- Milk Bottles: `Item Multi Totals by Sub-department` with returned milk-bottle items.

Every report must contain one readable deposit date, and all six dates must match. The Card Settlement date must also match when its date is present. Missing roles, duplicate roles, unreadable files, ambiguous content, or mismatched dates block continuation and identify the specific file or role that needs attention.

Filename keywords are secondary hints only. A renamed file must still work when its contents are valid.

## Normalized Data and Calculation Rules

Each parser produces a small normalized result containing the report date, role, source rows needed for the reporting workbook, totals, and any role-specific details. Financial calculations use decimal arithmetic rounded to cents at established business boundaries.

The new direct-export route must feed the same normalized values used by the existing IIF generator. All current rules remain in force, including department-to-account mappings, Books combined with Magazines, Coop Scoop/CDTA Star Pass handling, In-House breakdowns, member shares, Paid In, Paid Out, Donations, coupons, Closeout, card adjustments, unknown-item TBA handling, and all signed debit/credit behavior.

The reporting calculations reproduce the supplied workbook rather than using a generic sum:

- Department result equals Sales plus Coupon distribution. The sanitized Maria College supporting tabs remain in the reporting template and contribute zero because they are not among the six supplied SMS exports.
- Store Coupons remain separate from the department sales total.
- Coupon distribution is allocated to departments and offset in the established summary calculation so it does not inflate the final SMS Sales total.
- Milk Bottle export parsing finds each item description containing both `Milk Bottle` and `Returned`, then reads that item's `Net Sales` amount. It must not sum the report's store-coupon or grand-total rows.
- The Milk Bottles result populates the reporting workbook's Milk Bottle Returns value.
- The final IIF Milk Bottle Return combines the raw Milk Bottles result with Balance Sheet code 910 and applies the established negative sign.

For the supplied 9/14/2026 backtest, the required control values are:

- Raw SMS Sales total: `$86,502.80`.
- Coupon distribution total: `$61.69`.
- Raw Store Coupons: `-$1,428.18`.
- Milk Bottles report: `$20 + $32 + $6 + $16 = $74.00`.
- Reporting workbook adjusted Store Coupons: `-$1,428.18 + $74.00 = -$1,354.18`.
- Balance Sheet code 910: `$8.00`.
- Final IIF Milk Bottle Return: `-($74.00 + $8.00) = -$82.00`.
- Discounts total: `$3,981.21`.
- HASH Refunded Discounts: `$4.89`.
- HASH Pass Through Donations: `$6.00`.

The app must compare independently calculated control totals with the corresponding report totals to the cent. Any disagreement greater than `$0.01` blocks the IIF instead of silently substituting a value.

## Reporting Workbook

The repository contains a sanitized reporting template based on the supplied `SubDept Single Total Report 9-14-26.xlsx`. The generated file preserves the familiar tab order, labels, layout, formatting, and reporting sections while replacing date-specific source data and results.

The generator:

- fills `SubDept Single` from the Sales export;
- fills `SubDept Coupon (Local Discount)` from the Coupons export;
- fills the calculated `SubDept Sales Report` values, including Milk Bottle Returns and adjusted Store Coupons;
- replaces and date-renames the Discounts, BS, and HASH placeholder tabs using `MMDDYY Discounts`, `MMDDYY BS`, and `MMDDYY Hash`;
- preserves the established supporting tabs and formatting;
- stores currency as numeric values with two-decimal display formatting; and
- names the output `SubDept Single Total Report M-D-YY.xlsx`, matching the supplied no-leading-zero example.

The workbook is a dated reporting snapshot. The generator writes the verified calculated results as numeric values while preserving the reference workbook's labels, styles, number formats, and layout. The app does not rely on Excel formula recalculation to build the workbook or validate the IIF, which avoids stale formula caches in Streamlit Cloud. The server-side normalized calculations are the source of truth.

## Completion Gate and Downloads

The reporting workbook is generated only after the complete deposit workflow succeeds, including upload verification, guided steps, closeout requirements, IIF generation, and final IIF validation. It is not offered immediately after the six SMS exports are uploaded.

The final Download section offers the completed IIF and `SubDept Single Total Report M-D-YY.xlsx` together. A failed or incomplete run produces neither a newly approved IIF nor a completed reporting workbook. Run History retains the six source filenames and the generated reporting workbook so the completed run can be reviewed later.

## Error Handling

Errors use report-role language that an operations user can act on. Examples include `Milk Bottles report is missing`, `Two files were detected as HASH`, and `Coupon report date 09/13/2026 does not match Sales report date 09/14/2026`.

An unreadable `.xls` file or an unexpected SMS layout must not be guessed into a role. Unknown sub-departments and existing business exceptions continue through the current review and TBA safeguards after the source reports themselves have been validated.

## Testing and Backtesting

Tests cover content-based role detection, same-date validation, duplicate and missing roles, legacy `.xls` reading, report-specific parsing, Milk Bottle item association, unusual blank/zero rows, and output filename formatting.

Calculation tests use hand-derived expected amounts. They protect the unusual 9/14 relationships, especially `$74 + $8 = -$82`, coupon distribution offsets, adjusted Store Coupons, and the raw Sales control total.

An integration backtest runs the supplied 9/14 source layouts through the direct-export pipeline and compares its normalized data and IIF-relevant outputs with the existing completed workbook. Workbook tests reopen the generated file and verify its sheet order, dated tab names, key cells, numeric types, formulas or fixed results as designed, and formatting in the affected ranges. The existing full regression suite must remain green.

## Out of Scope

- Changing QuickBooks account mappings or guided deposit decisions.
- Changing the Card Settlement source or its `Processed Net Amount` rule.
- Changing coupon recommendation behavior beyond preserving the current workflow.
- Importing directly from the mapped SMS export folder without a user upload.
- Producing the reporting workbook before the complete deposit and IIF process succeeds.
