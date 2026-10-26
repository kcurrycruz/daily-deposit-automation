# Recurring-purchase duplicate false positives

## Intent

Avoid flagging separate daily deliveries as duplicates merely because their
invoice references differ by an adjacent digit swap and their amounts repeat.
The reported recurring-delivery pairs reproduce the current classifier's behavior:
same vendor and amount, swapped adjacent digits, different dates within 30 days.

## Approaches

The user selected the recommendation to require the same invoice date for
swapped-digit matches, while retaining exact-reference checks across dates.
A vendor-wide exemption would hide genuine duplicates; keeping the current
30-day swap window would continue the reported false positives. Neither fits.

## Small-change design

- Apply the rule to all vendors, not a hard-coded vendor exception.
- Adjacent-digit swaps require equal original amounts and the same valid
  invoice date, in addition to the existing vendor/currency safeguards.
- Different or missing invoice dates do not produce a swapped-digit finding.
- Exact normalized invoice-reference checks remain unchanged, including
  different-date matches and same-reference amount discrepancies.
- Trailing-letter variations retain their existing equal-amount/30-day rule.
- Enforce the date restriction in classification and scan candidate selection.
- Version the revised rules so completed old scans cannot silently remain the
  current result. The database currently pins rule version v1, so deployment
  also needs a forward migration supporting the new version. Prepare that
  migration; do not apply production SQL as part of implementation.
- Retain old scan/review history. New-version findings are freshly evaluated;
  old review decisions are not silently copied to different-version keys.
- Add regression tests for daily purchases, same-day swaps, exact-reference
  matches across dates, unchanged suffix behavior, and versioned scan selection.

## Boundaries and tradeoff

No changes to bills in BILL, payment status, statement matching, or UI layout.
No automatic confirmation or dismissal of saved reviews. A digit typo paired
with a different invoice date will no longer be suggested by the swap rule;
this is the deliberate precision tradeoff. Keep existing bounded scan work.

## Approval

Approach and short design approved October 26, 2026. Implementation will use
the user's previously selected native execution method.
