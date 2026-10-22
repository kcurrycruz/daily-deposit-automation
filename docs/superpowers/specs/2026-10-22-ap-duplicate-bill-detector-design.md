# AP Statements duplicate bill detector design

Date: October 22, 2026

Status: Approved for implementation planning on October 22, 2026. Product changes require review of the implementation plan and selection of an execution method.

## Purpose and accepted scope

Help the finance team find potentially duplicated bills already present in its saved BILL export, without requiring a vendor statement. Automatically scan all bills in the active dataset after each acknowledged BILL data update. Show explainable findings in a dedicated Duplicate bills sidebar tab, where users can compare evidence and save their review.

The user proposed similar reference numbers combined with equal amounts. The accepted approach combines exact checks with conservative reference similarity, using vendor, original amount, invoice date, and available currency evidence. It favors useful review suggestions over a claim that the software has proven a duplicate.

Weekly exports replace the current comparison source; they do not append to it. Scan one pinned active import, never a union of historical exports. Preserve review decisions across uploads only when the identifying evidence is unchanged.

The detector never deletes, merges, edits, pays, or credits bills in BILL. It never changes statement extraction, invoice matching, confirmed statement matches, completion decisions, or historical revisions. A duplicate finding is not proof of duplicate payment.

## Selected approach

Use a server-side, rules-based scan of the existing verified BILL data, with paginated results and durable review decisions. Exact-only detection would miss suffix differences and transposed digits. Broad fuzzy matching would produce excessive warnings for legitimate recurring purchases and sequential invoice numbers. The selected approach adds only narrowly defined similarity rules.

Keep duplicate detection separate from statement reconciliation, including the Adventure in Food trailing-letter matching rule. A reference that is acceptable for matching a statement to a bill can still warrant a duplicate review when two exported bills share the relevant characteristics. Conversely, a suffix can represent a legitimate adjustment or split bill, so a similarity finding never confirms a duplicate automatically.

## Existing source behavior and boundaries

The current native importer retains invoice reference, invoice date, original amount, currency when supplied, reported payment fields, source rows, and source warnings. It excludes native exports marked Inactive or DraftDeleted. It consolidates line items only when bill-level consistency, line counts, zero-based line order, and amount sums establish a complete bill.

Native normalized IDs are based on export rows, and candidate query IDs are import ID plus ordinal. Neither is an immutable BILL bill identifier across weekly exports. Vendor Id participates in native consolidation but is not retained in normalized records. The normalized source therefore cannot always prove that two identical rows are separate bills or that equal display names identify the same BILL vendor account.

Version one scans normalized records and preserves the existing consolidation rules. It does not modify the parser, existing snapshot manifest, comparison index format, or matching API merely to add detection. It reports its scope as vendor-name based. Missing stable identifiers and unresolved export rows lower the strength of a finding; they must not be disguised as verified identity.

For snapshot-v2, obtain the server-generated SQLite index through the existing authorized, hash-verified cache and open it read-only. For rows-v1, adapt the complete pinned import through bounded server pagination into temporary disk-backed scan tables. Do not rely on the currently viewed statement's candidate subset, export source rows as individual bills, or download the entire history into the browser.

## Eligible records and comparison values

Consider invoice-kind records with a valid positive original amount in integer cents and a nonblank reference and vendor. Exclude credit records, negative amounts, and zero-value records from duplicate-bill suggestions in version one. Retain the import's existing exclusion and warning counts as source context rather than inventing duplicate findings for excluded rows.

Use the existing vendor lookup normalization: case-insensitive trimmed names with repeated whitespace collapsed. Do not fuzzy-match vendor names, merge similarly named vendors, or use statement vendor mappings to combine BILL vendor accounts. Where the export cannot distinguish accounts with the same display name, explain that limitation in the finding.

Use the existing invoice lookup normalization: uppercase reference with whitespace removed. Preserve punctuation, all digits, and leading zeros. Keep original display references visible. Do not globally strip letters, convert references to numbers, or apply arbitrary edit-distance matching.

Compare original bill totals, not outstanding amounts, line amounts, paid amounts, or credits applied. Numeric comparisons use exact cents, with no floating-point or percentage tolerance.

Compare supplied currency codes after trimming and uppercasing, retaining their original display values. Known unequal currencies exclude a pair from amount-based duplicate or discrepancy findings. Equal known currencies support an amount comparison. Missing or invalid currency evidence cannot establish known equal currencies; a reference-based suggestion may still be shown, but it must identify the missing or invalid evidence and cannot receive the strongest warning level. Never assume a missing native currency is USD.

## Detection rules

The following are version-one defaults for review in this specification. The 30-day similarity window and four-digit minimum are conservative design choices, not measured conclusions about the user's data.

| Rule | Required evidence | Result |
| --- | --- | --- |
| Exact reference and amount | Same normalized vendor, exact normalized reference, equal original cents, compatible currency | Duplicate-pattern finding. Same valid invoice date and known equal currency strengthen it. |
| Trailing letter variation | Same vendor and original cents; references share the same numeric stem of at least four digits and differ only by one optional trailing ASCII letter; valid invoice dates within 30 calendar days | Possible duplicate, with both references and date difference shown. A versus B as well as no suffix versus X can qualify. |
| Adjacent digit transposition | Same vendor and original cents; equal-length references of at least four characters differ by swapping exactly two adjacent, unequal digits and otherwise agree; valid invoice dates within 30 calendar days | Possible duplicate, showing the swapped digits. |
| Same reference with different amounts | Same vendor and exact normalized reference; valid, unequal original cents and compatible currency | Separate Same reference, different amounts finding, not a confirmed duplicate or payment discrepancy. |
| Insufficient export identity | A pattern above is present, but repeated source rows, incomplete line evidence, or identical normalized bill identities prevent establishing separate bills | Export needs review. Show the candidate pattern and relevant source rows without counting them as proven separate bills. |

Exact-reference rules examine all eligible dates in the current export. Same-date evidence is stronger; different or missing dates remain explicit and can represent legitimate reference reuse. The amount-difference rule does not conclude that either bill amount is wrong.

Suffix and transposition rules require both valid invoice dates within the inclusive 30-day window. Missing dates do not become zero dates or silently qualify. They remain visible in exact-reference findings where applicable. One-digit numeric differences, nearby sequential numbers, shared endings, equal amounts alone, and general numeric insertion or deletion do not qualify.

If several rules explain the same record pair, show one finding with all reasons and the strongest supported classification. An exact-reference amount difference takes priority over suggestions to substitute some other equal-amount bill. Broad vendor-wide amount searches must not manufacture duplicate findings.

A strong pattern is still a warning, not a verified duplicate. When the export cannot establish separate bills, Export needs review overrides the stronger label. The detector cannot recover two bills that the source has made indistinguishable, and must not promise exhaustive detection from this export.

## Finding structure and review identity

A finding contains its rule version, classification, reasons, pinned import, source evidence, and members. Similarity findings represent direct candidate pairs. Do not treat a chain where A resembles B and B resembles C as proof that A resembles C.

Use one grouped finding for an exact-reference bucket with indistinguishable or ambiguous repeated rows rather than emitting every combination of its rows. Page the group's evidence separately. Grouping is a display and resource safeguard, not permission to declare those rows one bill or several bills. For this ambiguity test, equal normalized vendor, normalized reference, date, currency, and original total establish an indistinguishable identity; differences only in raw reference formatting or import-scoped IDs do not establish separate bills.

Create a versioned canonical bill fingerprint from vendor lookup key, original reference text after trimming, normalized reference, transaction kind, invoice date including explicit missing value, original cents, and normalized currency including explicit missing value. Use unambiguous canonical serialization and a cryptographic hash. Preserve reference case and punctuation changes in review evidence conservatively rather than silently carrying a dismissal across a changed reference.

A finding evidence fingerprint includes sorted member fingerprints with multiplicities, the detector rule version, classification, and source-warning or line-ambiguity evidence affecting the finding. Its workspace-scoped key is independent of export filename, CSV row order, import ID, and source ordinal. Sorting members does not discard repeated occurrences.

Source ordinals and row lists locate evidence within an import but do not establish cross-import identity. Changes to amounts, references, vendor, currency, invoice date, evidence multiplicity, relevant source warnings, or detector rules require a new review. A new third candidate does not inherit a decision covering a different pair or group.

Changes only to filename, row ordering, import time, due date, or reported paid and outstanding fields do not reset the duplicate decision. Show current reported payment fields separately; the preserved decision concerns bill duplication, not payment verification. Fingerprints with indistinguishable members remain ambiguity groups, not invented unique bill IDs.

## Scan lifecycle

After an import activation is acknowledged, ensure there is one scan job keyed by workspace, import ID, source digest, and detector version. Reusing the identical active export reuses a complete scan. A restored historical export uses its matching scan only if source and rule versions still agree.

The frontend automatically drives cooperative server steps while the app is open and access remains valid. Bootstrap discovers pending work and resumes it without requiring a statement or a visit to the Duplicate bills tab. This follows Streamlit's request-driven execution model; it is not a promise of a separate worker continuing after every user closes the app.

Use lifecycle states pending, running, ready, failed, superseded, and restart_required. Each step is session-authorized, generation-bound, and idempotent at its expected checkpoint. Persist the job identity, state, progress summary, and lease durably. Intermediate scan databases are process-local derived state. If they expire or the process restarts, rebuild from the verified pinned source under a new generation rather than pretending a lost local cursor survived.

Bound simultaneous scans to one per workspace and two per server process. Use expiring server-owned leases and the existing one-hour temporary-state expiry convention. Do not allow concurrent sessions to produce competing current results.

Check the active import and import version before publishing and before each review mutation. If a new update supersedes a scan, stop publishing it as current. An old response cannot replace a newer source or its results. Previously completed evidence may remain available only with its source and stale status explicit.

A detector failure does not undo an acknowledged BILL import or block statement checks. Display BILL data updated; duplicate scan needs retry with an actionable reason. Never translate pending, incomplete, failed, expired, or superseded work into No duplicates found.

## Processing and storage architecture

Implement a dedicated detection module under app/ap_shared/bills with separate responsibilities for source adaptation, candidate generation, classification, fingerprints, and scan orchestration. Add a frontend module for the Duplicate bills view and service state instead of expanding the statement-matching function.

Build derived lookup tables on temporary disk. Generate candidates within vendor, currency compatibility, and original-amount buckets, and within exact-reference buckets for amount differences. Index numeric stems and bounded transposition variants. Stream bucket members and output; do not compare every bill with every other bill or materialize a large equal-amount bucket in memory.

Cooperative steps process at most 5,000 records or 10,000 candidate probes, with a five-second budget and resumable inner-bucket state. Break and checkpoint long buckets without treating their first page as complete. Bound SQLite execution with its progress handler where a query itself could exceed the cooperative deadline.

Support the existing source limits of 500,000 normalized records and 750,000 source rows. Limit a completed derived result to 100,000 findings, 512 MiB expanded, and 32 MiB compressed. A limit violation produces a specific failed scan with no complete-result claim, not silent truncation. The UI explains that detection could not cover the entire export; the active BILL dataset and statement workflow remain usable.

Keep completed findings and membership locators in a compressed, server-generated derived SQLite artifact in the existing private bucket. Do not copy every bill's full JSON into Postgres or into another historical record table. Resolve evidence against the pinned original index or legacy source using bounded server queries. Store only scan metadata and user review records in Postgres.

Use a detector-specific immutable object namespace, hashes, schema version, and manifest. Reuse the existing private access, size verification, decompression limits, and cache isolation patterns. Do not modify existing immutable comparison artifacts. Account for staging and completed detector artifacts in the configured storage reservation and budget; do not assume that adding derived files is free or unlimited.

Result pages contain at most 100 findings and fit within the existing bridge envelope. Member evidence pages contain at most 100 members and are also byte bounded. Return import ID, scan ID, rule version, stable ordering, total count, and an authenticated cursor bound to query filters and the source. Filtering and sorting run server-side across all results, not merely the downloaded page.

## Shared review storage and contracts

Add an additive migration for scan metadata, workspace-scoped duplicate review state, and review events. Do not edit deployed migrations or put detector decisions into statement resolutions.

Scan metadata records the pinned source and version, detector version, lifecycle state, generation, lease, progress, result counts, derived artifact manifest, and server timestamps. Enforce uniqueness for a workspace, source import, and detector version. Publish ready only after all results, counts, and artifact checks succeed.

A review record stores its evidence fingerprint, decision, optional note, required reviewer initials, current version, server timestamp, and the scan evidence used for that decision. Initials are self-reported, consistent with the existing app; they are not a verified employee identity. Append review events when a decision is saved, changed, or reopened.

Allow Confirmed duplicate, Not a duplicate, and Reopen to unreviewed. A confirmed duplicate is the user's classification after inspecting evidence; it does not change BILL. Exact-reference amount differences and export-ambiguity findings use the same manual decisions, with wording that makes clear what is being confirmed.

Expose allowlisted operations for ensuring a scan, advancing a scan, fetching status, paging findings and members, and saving a review. The server derives workspace, fingerprints, membership, artifact paths, and current-source eligibility; it does not accept a client assertion that arbitrary bills belong to a finding.

Review mutations require access revalidation, the current import version, a ready current scan, the evidence fingerprint, expected review version, an idempotent request ID, and a payload hash. Enforce current-import, scan-state, and expected-version checks inside the same database transaction as the review write, not just in an earlier server read. Repeating an acknowledged request returns its acknowledgement. Concurrent edits return a conflict and retain the user's unsaved note for comparison. A lost acknowledgement remains Not saved until the same operation is retried successfully.

Maintain a monotonically increasing workspace review revision. Counts, reviewed filters, and result cursors identify this revision as well as the scan. Create any cached server-side review projection from a complete, boundedly paginated review read, joined to the finding keys; never infer unreviewed status from a partial review page. Invalidate the projection when the revision changes. A stale cursor must request a refresh rather than skip or repeat findings under a changed filter.

Only service-authorized functions may mutate these tables. Preserve row-level protections and private-bucket access; do not grant anonymous or browser clients direct write access or disclose service credentials.

## User experience

Add Duplicate bills as its own left sidebar tab. Its badge counts unreviewed findings from the complete current scan, separately from statement Needs attention. While scanning, show a small progress indicator instead of a misleading zero.

At the top of the view, show the source filename, BILL update time, detector status, last completed scan time, and coverage counts. A clean result says No possible duplicates found by these rules rather than asserting that the dataset contains no duplicates.

Default to unreviewed findings, ordered by supported pattern strength, then most recent member invoice date, then stable finding key. Provide Reviewed and All filters, vendor or reference search, and classifications for duplicate patterns, amount differences, and export review. Use red for strong warnings, amber for possible or export-review findings, and green for completed reviews. Keep text labels and icons so color is never the only signal.

Clicking a finding opens a dedicated detail screen with Back to duplicate list, preserving filters, scroll, and focus. Show original references side by side, original totals, invoice dates, currency or its absence, reported status and payment fields, and source rows. Explain the matching rule in plain language and visibly distinguish differences. Do not imply that a vendor-statement PDF exists for a bill-only scan.

Show Confirmed duplicate and Not a duplicate actions, reviewer initials, and an optional note. Require an explicit save and acknowledgement before the item leaves the unreviewed list. Retain a reviewed item in the Reviewed filter and allow it to be reopened. A new upload that reuses a decision labels it as a prior review with its original review timestamp, not a new review performed today.

Never offer deletion or automatic financial corrections. For amount differences, say Verify the original invoices and follow up outside this app; do not infer an overpayment, underpayment, credit due, or additional bill from equal references alone.

## Security and operational failure

Authorize every scan step, query, artifact read, and review mutation against the current AP workspace and session. Revalidate after long operations before returning financial evidence. Access expiry locks the view and stops automatic progress until the user unlocks it again.

Accept no client SQL, database paths, object keys, arbitrary URLs, or workspace selectors. Verify artifact provenance and hashes before reading; open final indexes read-only with extensions disabled. Sanitize logs to operation identifiers, counts, durations, and byte sizes, without vendor names, invoice numbers, amounts, notes, or credentials.

Display specific states for unavailable storage, insufficient storage budget, corrupt artifacts, unsupported versions, scan limits, stale sources, and conflicts. Provide retry or restart only when appropriate. Preserve imported originals, PDFs, prior snapshots, completed statement reviews, and duplicate review history. No automatic retention deletion, paid-plan change, or live migration is authorized by this specification.

## Acceptance tests and rollout

The implementation must demonstrate:

- Exact references and totals produce the intended pattern; currency and date qualifications remain visible.
- Optional trailing letters and a single adjacent digit transposition qualify only under the stated amount, vendor, date, and reference constraints. Removing leading zeros, comparing short references through similarity, sequential numbers, equal amounts alone, unrelated vendors, and different known currencies do not qualify. Exact short-reference checks remain supported.
- Credits, negative values, zero-value records, and existing source exclusions stay outside the bill detector. Paid bills remain eligible based on their original totals.
- Exact-reference amount differences stay separate and do not substitute another equal-amount bill or imply a payment correction.
- Complete multi-line bills remain one bill. Repeated incomplete or inconsistent source rows produce Export needs review, not fabricated independent bills. Large ambiguity groups do not create quadratic output.
- Weekly reordering, renamed files, changed payment fields, identical uploads, and retried requests do not duplicate findings or reset unchanged decisions. Changes to identifying evidence, multiplicity, or rule version require review.
- A third candidate does not inherit a pair's dismissal; candidate chains do not become unsupported all-member duplicate claims.
- No source mixing occurs during replacement or historical restore. Stale pages, cursors, scan completions, and review saves cannot affect the current scan.
- Both snapshot-v2 and rows-v1 use complete datasets. Pagination, missing pages, interrupted steps, process restarts, expired leases, and concurrent sessions cannot produce a false complete or empty scan.
- Review saves require initials and server acknowledgement, retain optional notes, handle conflicts, and record server timestamps and review events.
- A synthetic 223,425-record export and a maximum-supported 500,000-record fixture exercise time slicing, large equal-amount buckets, pagination, and resource limits. Target peak server RSS growth below 256 MiB; browser memory must depend on displayed pages rather than dataset size. Record actual timings and memory measurements, not estimated performance claims.
- Authentication, expiry, cross-workspace isolation, forged fingerprints, arbitrary paths, corrupt artifacts, decompression limits, quota failures, and sanitized logs are covered.
- Existing Python and frontend regression suites and the AP production build pass. Statement matching, Adventure in Food rules, source highlighting, history, and invoice-detail navigation remain unchanged.

After implementation, backtest against the user's locally available saved export without altering it or uploading it to a new destination. Present representative candidates and false positives for rule calibration; do not present those candidates as established duplicate bills. Any change to the specified rules receives a new detector version and updated tests.

Apply the additive migration only in an explicitly approved environment. Validate synthetic data, two-session review conflicts, interrupted scans, and a server restart before production enablement. Expose the feature through a capability check so missing schema leaves existing AP functionality intact. An already active dataset should be scanned automatically on first use after enablement, without requiring a redundant weekly reupload.

This approval stage covers the design specification only. Implementation planning follows user review; coding, merge and push, live schema changes, and production deployment remain later actions.

## Repository references

- Existing source behavior: app/ap_shared/bills/parser.py, normalization.py, index.py, and contracts.py.
- Import lifecycle and verified cache: app/ap_shared/bills/operations.py, builds.py, repository.py, and archive.py.
- Authorization and validation: app/ap_shared/protocol.py, service.py, models.py, and repository.py.
- Existing interface and service state: app/ap_statements/frontend/app.mjs and shared-workspace.mjs.
- Snapshot architecture: docs/superpowers/specs/2026-10-19-large-bill-exports-design.md.
- Existing additive migrations: supabase/migrations/202610130001_ap_shared_workspace.sql and 202610190001_ap_bill_snapshots.sql.
