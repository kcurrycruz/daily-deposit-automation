# Exact vendor/reference exclusions from AP duplicate alerts

## Intent

Reduce recurring noise such as Albert's Organics N2609-61636. The user reports that their BILL workflow already catches entering the same invoice number for the same vendor. This is the user's workflow assumption, not an independently verified universal guarantee about BILL.

## Proposed rules — approval pending

For the duplicate-alert queue, exclude a finding when every member has the same normalized vendor and exact normalized invoice reference, regardless of invoice date, amount or export-row multiplicity. Preserve leading zeros, punctuation and letter suffixes: do not use fuzzy matching to exclude candidates. Existing normalization ignores case and whitespace.

Do not automatically create a Not a duplicate review or claim that payment uniqueness was verified. Retain immutable scan artifacts, saved reviews and original source records. Statement-to-BILL amount discrepancy checks remain independent and unchanged.

The user clarified that a core target is a near-identical reference with one wrongly entered digit, for example an 8 changed to a 9. Add a same-vendor, equal-original-amount, one-digit-substitution candidate rule even when both references fit the vendor's normal format. The existing format-outlier rule does not cover ordinary same-format digit substitutions.

Builder proposal, not yet user approved: require matching known invoice dates for this new substitution rule, and suppress known-currency disagreements. This limits routine daily deliveries with sequential numbers and equal totals, as in the earlier Cider Belly case. Unknown dates do not satisfy this new rule. These are Possible duplicate suggestions requiring review, never automatic confirmations.

Keep existing same-vendor different-reference candidates (including suffixes, digit swaps and corroborated reference-entry errors) and different-vendor candidates visible. A vendor is never globally exempted.

## Approaches

1. Hide only identical vendor/reference/date/amount export rows: originally proposed, but the user rejected the date/amount conditions because the intended exclusion follows the vendor/reference entry rule.
2. Remember each manually reviewed case: retains repetitive manual work; not the user's requested automatic filter.
3. Exclude exact vendor/reference groups from duplicate alerts while preserving evidence: selected by the user's correction. Different-reference and wrong-vendor checks remain useful under their workflow.

## Presentation and implementation boundaries

Apply the exclusion in the verified shared review projection so existing saved scans benefit without a detector rerun or rewriting versioned artifacts. Compute the exclusion from every member's verified source identity, not a potentially truncated preview. Use bounded preparation with visible eligible counts, pagination and empty-state text that agree with the filter. Explain in the duplicate view that same-vendor exact-reference groups are excluded under this workspace rule. Preserve the current review/source revision and cursor checks.

The new substitution rule also changes candidate generation: use bounded indexed reference lookups, not vendor-wide all-pairs or equal-amount bucket scans. Newly generated scan identities must distinguish the changed rules; preserve readers and immutable historical results for older scan versions. Determine the compatible rule-version/migration rollout in the implementation plan before modifying product code.

This changes duplicate-alert visibility and near-reference candidate generation, not imported data, payment processing, statement reconciliation, historical training semantics or BILL itself. No merge, push, migration or production mutation is authorized by design approval alone.

## Verification

Regression cases: single-digit substitution with equal vendor/amount/date is a candidate; different dates, unequal amounts, unknown dates, known-currency conflicts, unrelated references and routine sequential daily invoices do not satisfy the new rule; source identity/order and bounded scale behavior remain stable. Albert-like three identical export rows; same vendor/reference with different dates or amounts; missing/partial member evidence fails closed; same vendor with trailing-letter or digit-swap differences remains visible; different vendors with the same reference remain visible; leading-zero and punctuation distinctions remain visible when otherwise candidates. Confirm counts and pagination after exclusion, reviewed history preservation, source/scope conflicts, and existing frontend behavior. Run affected backend/projection and frontend gates plus build. The prior full suite on the unchanged baseline is recorded separately; broaden only when the implementation's scope justifies it.
