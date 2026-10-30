# AP active BILL data range

Status: approved by the user on 2026-10-30; implementation plan pending review. No product code or production data changed.

## Intent and selected approach

Make ordinary AP comparisons and duplicate checks work from a smaller dataset without deleting saved evidence. The user selected an in-app import setting, defaulting to a rolling 12 months, rather than preparing smaller exports manually. Older unpaid bills and unresolved follow-ups remain active. Daily Deposit is outside this change.

Approaches considered:

1. Filter visible lists only. Easy, but leaves the backend reading and scanning all invoices; rejected because it does not address the requested processing reduction.
2. Ask users to export a smaller date range from BILL. Reduces incoming work, but makes users responsible for older unpaid items, follow-ups and historical context; available as an existing manual workflow, not the selected solution.
3. Preserve the complete imported snapshot and derive a smaller, versioned working set. Selected. Adds bounded preparation work at import/apply time, while subsequent routine reads and scans use a smaller index. Retains the original export, historical statements and detector training context.

This is a coordinated backend, database and frontend change, not a cosmetic table filter. It does not promise a particular startup speed or remove the initial cost of uploading and parsing a complete export.

## Evidence and existing constraints

- At local DD-v2 commit `33c6db5`, BILL sources are immutable `rows-v1` or `snapshot-v2` imports. Imports are unique by workspace and original file hash.
- Snapshot manifests bind the original compressed CSV, complete normalized index, counts and vendor digest. Saved statement revisions pin an import and retain saved results and decisions.
- Duplicate source pins, cache entries, pagination, member ordinals and source-digest checks currently assume a complete import. Filtering a reader without updating these contracts would break completeness checks or attach evidence to the wrong bill.
- The current detector learns monthly vendor formats from the preceding 365 days and checks recurring purchases against preceding 90-day history. Simply dropping old rows would change these safeguards.
- Local read-only analysis of the previously supplied normalized export found 223,425 records. Using cutoff 2025-10-30, 18,172 have invoice dates on or after the cutoff; 205,253 are older and marked `PaidInFull`. The source also contains future invoice dates, through 2026-11-13. This is not a live-database audit, does not prove payment settlement, and does not yet account for follow-up protections.
- Applying the stricter retention check below to that local snapshot yields 24,884 active records before saved follow-up protections: 18,172 recent/future records plus 6,712 older exceptions. There are 198,541 archive candidates, approximately 89% of the normalized source. Follow-up protections can increase the active count. These are coverage counts, not measured speed gains.

The required independent builder check reported “nothing important left.” Subsequent local data analysis tightened the paid-data rule and documented the existing duplicate-review decision values; no product changes or production operations were performed.

## User-facing behavior

- Add **Active BILL data** to the BILL upload/update area with choices **Last 12 months** (default for a new update) and **All imported dates**. Do not silently alter existing active sources on deployment.
- Keep the established upload flow. Before activation show the exact cutoff, full imported count, working count, archived count and counts/reasons for retained exceptions. Let the user apply or cancel the prepared update.
- Add **Apply range to saved export** so the existing acknowledged full snapshot can be reused without uploading the same file again. A changed range rebuilds the derived index; it does not rewrite the original source.
- Show the acknowledged range and active count on the BILL data summary and duplicate screen. Distinguish all imported records from records covered by the active scan. Do not imply that archived bills were checked for duplicates.
- **All imported dates** restores full-source working coverage. It is a deliberate action and may take longer. Range changes are shared workspace state, not an unsaved local filter.
- A smaller set is published only when preparation, protection checks and storage verification succeed. Keep the prior acknowledged source/range usable during preparation. Failed or cancelled work must not empty the workspace.
- No new date selector is added to Daily Deposit. No PDFs, statement rows, review decisions or BILL/QuickBooks transactions are deleted or changed.

## Date and inclusion policy

Builder proposal, not an additional user requirement: freeze `asOfDate` to the server's America/New_York calendar date when the user begins an update or applies a range. Freeze it across retry, resume and restart. The optional existing export snapshot date remains metadata and does not choose retention.

For **Last 12 months**, subtract one calendar year, clamping February 29 to February 28 where necessary. Include the cutoff date. There is no upper date bound: future-dated invoices stay included and are not silently discarded. The UI says “Invoice dates on or after [cutoff], plus retained exceptions.”

This is a rolling window evaluated at each acknowledged import/range application, not a background midnight purge. Display the date it was applied. Ordinary navigation must not rebuild indexes or invalidate an in-progress scan when the clock changes.

Keep a normalized record active if ANY of the following holds:

1. Its valid invoice date is on or after the cutoff.
2. Its invoice date is absent or invalid; retain it with an explicit date-quality warning.
3. It does not pass the settled-for-retention check below. An export's status is a retention signal, not a payment verification.
4. A saved unresolved statement item or duplicate-review follow-up protects it.
5. The record is a credit or other non-invoice transaction. Date-based credit retention is outside this first release; retaining these avoids weakening the app's existing credit limitations.

The settled-for-retention check requires a positive original amount, `PaidInFull` status, no source issues, and either an explicitly reported integer amount due of zero or the following substitute when amount due is absent: reported paid amount is a nonnegative integer and equals the original amount if credits are absent, or paid amount plus a supplied nonnegative integer credit amount equals the original amount. A supplied nonzero/invalid amount due never uses the substitute. Missing or malformed paid/credit data cannot establish the substitute. This choice matters because all 223,425 normalized records in the supplied export have a null `reportedAmountDue`; requiring an explicit zero would retain every record.

Archive only older invoice records that pass this retention check and have no protection. Preserve every source row in the complete original snapshot. All mode includes every normalized record.

## Protecting follow-ups

The backend derives protections from current saved statement revisions and current saved duplicate reviews, including completed or archived statements that still contain a follow-up. It does not trust a client-supplied list of bill IDs. Historical superseded revisions retain their own evidence but do not permanently protect a follow-up that a newer saved revision explicitly resolved.

- Every explicit statement decision other than `Reviewed — no action needed` protects its related records. Unresolved attention items in unfinished saved statements also protect records.
- For duplicate reviews, the existing explicitly saved `confirmed_duplicate` and `unreviewed` decisions protect all finding members; `not_duplicate` does not. The current app has no separate “financial correction completed” state, so a flagged duplicate remains conservatively protected. Unreviewed old findings with no explicit saved review do not force the entire historical dataset to remain active. No review decision is automatically changed.
- Protect confirmed candidate fingerprints and original bill references. Also protect all plausible records for a normalized vendor/reference, including amount differences and the existing Adventure in Food reference alias. Do not require equal amounts to retain a discrepancy.
- If the vendor mapping is ambiguous, retain all records for the protected reference across plausible vendors. Missing or malformed evidence must produce a visible unavailable/protection error rather than silently declaring an old bill disposable.
- Unsaved tab-only edits are not shared protections. Preserve the existing save/cancel requirement before a shared import or range change.
- Freeze a protection digest/version while preparing the working set. Activation must atomically reject changed source, setting or saved-protection state. Refresh and reprepare after a conflict.
- Saving/reopening a statement or changing a follow-up after activation invalidates the protection projection. Before publishing a new live comparison or starting a new duplicate scan, refresh the working set against the acknowledged source and current protections. Preserve the prior saved revision and notes; do not turn stale/incomplete protection into “not found.” Existing scans remain immutable evidence for their pinned scope.

## Storage and identity

Retain the existing complete import and its full index as the archive/evidence source. Add immutable derived working sets in a separate table and private artifact namespace, with a shared acknowledged active-working-set pointer. Do not remove the original import's hash uniqueness or mutate a ready manifest to fit a different range.

Each working set is identified by a server-generated hash over its source import ID/hash, policy version, selected range, frozen as-of/cutoff, protection digest and training-context version. Store and validate the full count, working count, retained-reason counts, archived count, content hashes and explicit original-record mapping. Reapplying an identical source and complete policy identity reuses the verified set; the same file with a different range/date/protection state cannot be mistaken for a no-op.

The smaller index contains active records only, plus compact vendor-directory and historical training context. Its local contiguous ordinals must map unambiguously to the original import ordinals. Statement candidate IDs remain original-import identities. Duplicate result member identity must bind both its working-set ordinal and original source member identity. Never reinterpret an old artifact's ordinal against the new subset.

Extend source pins, query/cache keys, cursors, artifact validators and activation guards to bind the working-set identity. Version any changed artifact/rule contracts rather than loosening old validators. Retain legacy readers for saved revisions and prior duplicate artifacts.

An additive migration introduces only the needed working-set/job/pointer state and guarded service-role RPCs. Maintain the existing private bucket, server-generated keys, workspace authorization, request idempotency, leases, quota reservations and source-version conflict protection. Expose capability gating so an older database can still read existing sources without accepting the new update flow.

## Historical context and archived lookups

Prepare compact, source-bound profile and recurrence summaries from the complete normalized source at import/apply time. Use the same eligibility, ambiguity exclusion, distinct-reference counting, monthly preceding-365-day window, preceding-90-day recurrence policy and deterministic tie rules as the current detector. Only active records may form duplicate candidate/member pairs; archived records support context, not additional reported pairs.

Preparation may temporarily use the full server-side index. Normal statement navigation and warm duplicate checks must not decompress or scan that full index just to recover profiles. Persist hash-verified compact context with the working set. Verify that profiles/recurrence decisions for retained candidates match full-source computation; insufficient context produces disclosed reduced coverage, never an invented established profile.

An older statement reopened against current data can request an explicit archived exact-reference lookup. It uses the acknowledged full source, on demand and with existing authorization/limits, not an automatic full-file scan for every missing candidate. Mark archived matches as such. If a reference is outside active coverage, show **Outside active BILL range — check archived data** rather than implying it does not exist in the full export. Scope/date uncertainty must likewise remain unverified. Amount-only matching must never silently search all archived bills.

## Bounds, empty sets and publication

Preserve the existing source and archive caps (750,000 CSV rows, 500,000 normalized bills, 256 MiB original CSV, 32 MiB compressed per artifact, 512 MiB expanded per index), cooperative five-second steps and current access/transport limits. Do not raise budgets to pass tests. Account for full archive, derived artifacts, compact context and staging in reservation checks.

Allow a valid zero-record working set with an explicit “No bills in this range” result. Zero active bills does not mean the original import is missing or incomplete. Update vendors/scan/progress validation accordingly. Do not publish a fake one-row import to satisfy legacy nonempty checks.

Storage cleanup may remove only acknowledged temporary objects owned by a job. This release does not purge older originals, historical imports or saved results and therefore does not promise reduced durable storage usage.

## Verification and release gates

1. Policy tests: inclusive boundary, calendar/leap dates, frozen New York date across midnight/retry, future dates, missing/invalid dates, unknown status, zero/nonzero/absent due amounts, exact paid coverage when due is absent, mismatching/invalid paid or credit amounts, source issues, credits, all mode and empty active set.
2. Protection tests: amount discrepancies, ambiguous vendors, Adventure aliases, explicit follow-ups on completed/archived statements, unresolved drafts, resolved newer revisions, duplicate member pairs, unsaved drafts and stale/malformed protection data.
3. Identity tests: same bytes/different scope; same scope reused; differing protection digests; original/local ordinal mapping; result/member hash validation; cursor and cache isolation; old imports/revisions/artifacts still readable.
4. Lifecycle/SQL tests: service-only access, additive rollback, request retry, same-source range changes, two-session conflicts, protection changes during build, lost acknowledgements, restart, quota failure, corrupt artifacts and cancellation preserving the acknowledged working set.
5. Frontend tests: range selection/defaults, preparation counts and exceptions, acknowledgement before publication, empty state, unavailable migration, outside-range/archived lookup labels, settings shared across sessions, no false missing results and no repeated full-source warm reads.
6. Read-only representative-export comparison: recompute the stricter settlement/protection counts; compare active pair/profile/recurrence results to a full-source baseline; measure expanded/compressed sizes, bounded step duration and peak memory. The earlier 18,172 count is an estimate before exceptions, not a release target.
7. Full relevant backend/frontend regression suites, production frontend build and independent final review. Measure startup/navigation/scan timings before claiming a speed improvement.
8. Prepare a concrete migration/recovery and rollout record. Applying this new migration, activating the production range and publishing the feature are separate external steps requiring their own reviewed rollout; prior migration approvals do not authorize this new migration.

## Implementation discretion

The builder chooses focused module boundaries, exact new table/RPC names, artifact version numbers and the private compact context representation. They may not change inclusion rules, provenance, immutable-history guarantees or the visible scope contract to simplify implementation. Use the existing Python/Supabase/custom frontend stack and the previously selected native execution workflow.
