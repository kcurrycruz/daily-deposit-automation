# Vendor-aware duplicate checks

Status: approved by the user on October 28, 2026. Implementation and verification are tracked separately; this document alone does not represent a production merge.

## Intent

Help AP reviewers find mistyped invoice references and bills possibly entered under the wrong vendor. Vendors can legitimately reuse references, change formats, or issue routine purchases with identical totals. Findings must show the supporting imported records and remain suggestions requiring review.

The user requested vendor-aware checks, approved a local backtest, and then requested a merge. The backtest reproduced 223,425 normalized records and all 417 findings of the current v2 detector. In a six-month historical holdout, the narrow format-supported checks found three additional reference-entry candidates and three cross-vendor candidates. These are unlabelled candidates, not confirmed errors or an accuracy estimate. Private source records and examples remain outside the repository.

## Approaches

1. **Broad fuzzy matching:** add similar references whenever amounts and dates are close. Rejected as the default: the three-day experiment produced over 10,000 additional historical pairs and still included routine sequential purchases after simple recurrence filtering.
2. **Manual vendor rules:** require staff to configure each vendor's formats. Useful as a possible future override, but not the requested automatic starting point; it adds ongoing configuration work.
3. **Corroborated vendor-aware warnings (recommended):** learn sufficiently supported formats from earlier data and require a matching counterpart, amount, and nearby dates before generating a new warning. Keep uncertain cases visible without asserting a duplicate or changing BILL.

The merge request is taken as direction to move the recommended approach toward delivery. The exact proposed behavior below remains subject to design approval.

## Goals and limits

- Add reviewable reference-entry and possible-wrong-vendor findings.
- Explain why a reference does or does not fit the observed vendor history.
- Recognize long-separated exact-reference reuse as contextual evidence, not proof of a duplicate.
- Preserve the existing authorization, source pinning, immutable scan history, review conflict handling, and bounded cooperative processing.
- Do not change financial records, automatically select a correct vendor, confirm duplicate payments, or automatically resolve findings.
- Do not publish real export examples, identifiers, or private analysis artifacts in Git.
- Do not add standalone warnings for every format outlier: the backtest found many legitimate changes in invoice-number length.
- Do not bundle startup, PDF, or cold-result-loading fixes into this change.

## Proposed rules

### Shared eligibility

Use the current imported positive original invoice amounts and valid invoice dates. Exclude credits and unusable source transactions as the current detector does. Known differing currencies cannot match; unknown currency remains explicitly disclosed. Incomplete or indistinguishable repeated export rows retain export-quality warnings and cannot become high-priority new claims. Stable vendor normalization stays unchanged.

### Vendor profiles

- A profile for a candidate uses only records dated before the earlier invoice's calendar month, within the preceding 365 days. The month is determined from source invoice dates, not the execution clock; scans must be reproducible from the pinned export.
- Count one vote per distinct normalized reference so repeated line items do not inflate support.
- Preserve literal letters and separators; replace each digit with a digit placeholder. Use whitespace-normalized, case-normalized references and show the original reference in evidence.
- Require at least 20 distinct references. Accept up to the three most common shapes, each supported by at least three distinct references, only when those shapes together cover at least 90% of the profile's references. Resolve equal counts by lexical shape order.
- Accept all qualifying shapes among that top three, rather than stopping as soon as cumulative coverage reaches 90%, so supported secondary formats are retained.
- Recompute month-specific profiles as later source history becomes available. Sparse or unstable vendors have no established profile; absence of a profile is not an anomaly.
- This monthly, historical profile policy is a proposed implementation refinement to the frozen-year backtest. Re-run the real-data comparison before delivery and disclose any changed candidate set; do not promise the exploratory count will remain exactly six.

### Possible reference entry issue

Generate an additional candidate only when:

1. Vendor and positive original amount match; valid dates are no more than three days apart.
2. Compact alphanumeric references differ by one inserted, deleted, or substituted character, one adjacent transposition, or a punctuation/spacing-only variation. Both compact references have at least four characters.
3. Exactly one original reference shape fits the vendor's established historical profile.
4. The pair is not already represented by an existing v2 finding and has no ambiguous source identity.
5. For different invoice dates, downgrade the pair out of this new rule if the vendor/amount has at least ten distinct earlier references on at least six invoice dates in the preceding 90 days. Same-day sequential references with the same shape fail condition 3 and must not create this warning.

Call it **Possible reference entry issue**, not a confirmed duplicate. Show both original references, amounts, dates, expected shapes, and the edit explanation.

### Possible wrong vendor

Generate a new cross-vendor candidate only when:

1. Normalized vendor identities differ.
2. Compact references match, contain at least six alphanumeric characters, and positive original amounts match.
3. Valid invoice dates are no more than three days apart.
4. Both vendors have established historical profiles; the reference fits one vendor's profile and falls outside the other vendor's profile.
5. Neither source identity is ambiguous. A cross-vendor match with no directional format evidence does not create this new warning.

Call it **Possible wrong vendor**. Show both vendor names prominently, the original reference values and amounts, both dates, and profile evidence. Formats common across many vendors provide weaker context; show that limitation instead of asserting that the matching vendor is correct. The original invoice remains necessary to decide the correct vendor. No automatic reassignment occurs.

### Existing findings and reused references

Retain current v2 matching behavior, including same-day digit-swap safeguards and exact-reference comparisons across dates. For exact-reference findings with valid dates more than 30 days apart, add **Reused reference — check context** information and the date gap. Preserve amount-difference information and review controls. Do not remove or auto-resolve them: a distant date could itself be an input mistake. Keep export-quality findings distinctly labelled.

## Review experience

Extend the existing duplicate list and source-bill detail page. Add pattern filters and clear labels for the two new finding types. Include both vendors in search text and accessible row names for cross-vendor findings. Existing All, Unreviewed, Reviewed, load-more, back navigation, initials, notes, and acknowledged-save behavior stay in place. Evidence explanations must not overflow the table or imply a financial conclusion.

Monthly profile evidence must accompany findings in the immutable result artifact. Review detail should show training period, distinct-reference support, accepted shapes, and how the candidate compares. Profiles used for a finding must never silently change while reviewing that saved scan.

## Processing and storage

Use the existing disk-backed scanner and private result artifacts, with indexed candidate generation for vendor/amount/date and compact-reference/amount/date. Do not scan every vendor against every other vendor or enumerate all bill pairs. Profile construction, candidate lookup, artifact preparation, and review projection must be cooperative and resumable within existing step/probe/memory limits. Index and profile storage count toward the existing limits. If the complete export cannot be checked within supported limits, fail explicitly without publishing partial results.

Bump rules to a new immutable version, `bill-duplicates-v3`. If additional artifact fields require a schema/format change, version that contract explicitly rather than passing new data through a v1 validator. Preserve all v1/v2 scans and reviews; do not silently carry old decisions onto changed finding keys. Extend storage allowlists only for the exact supported namespace/version paths. Keep access and service-role restrictions intact.

Prepare a transactional, retry-safe migration permitting v3 scans and any required immutable evidence fields. Apply it before deploying the v3 application. A separate live database action must use the already confirmed AP project, capture a recovery definition, and verify scans/reviews/permissions are preserved. Never merge/push a deployment that requires a migration before the prerequisite is satisfied. If deployment cannot proceed, keep the tested feature branch intact and clearly report the blocker.

## Validation and completion

- Regression cases for reused references, routine same-price purchases, sequential references, date/currency boundaries, and existing v2 matching.
- Synthetic, anonymized examples of missing digits, extra suffixes, punctuation variants, and incorrect-vendor counterparts; negative cases with common formats, sparse history, and ambiguous rows.
- Historical profile tests excluding candidate-month/future data; month rollover, secondary formats, ties, and changed invoice lengths.
- Stable finding keys and complete cross-vendor membership/search/evidence; source-version changes, authorization denial, review conflicts, and immutable-history preservation.
- Relevant frontend, contract, SQL migration, and backend suites plus production build.
- Existing full-export and 500,000-record scale checks for complete results, bounded steps, memory, and stable reruns.
- Re-run the local real-export comparison with source hashes and row-level example checks. Report candidate-set changes from the exploratory backtest; do not claim accuracy without labelled outcomes.
- Independent code review before merge. Merge only the authorized source changes and anonymized tests/docs; retain private exports, local backtest files, and recovery artifacts outside the commit.

## Builder discretion

Choose internal module boundaries, bounded SQL indexes/cursors, caches, artifact evidence representation, and focused test organization within these contracts. Confirm any necessary source-contract or immutable-artifact schema expansion during planning. The user-facing rules and safeguards above must not be broadened as an implementation shortcut.
