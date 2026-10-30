# AP Active BILL Data Range Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make AP comparisons and duplicate checks use a smaller acknowledged working set, defaulting to the last 12 months while retaining older unsettled and follow-up records and preserving complete saved evidence.

**Architecture:** Preserve every existing immutable full import. Add immutable derived working sets, a shared active-set pointer and compact historical context. Bind preparation, matching, duplicate scans and saved comparisons to the source and working-set identities, publishing a new source/range only after all derived artifacts and protections are verified.

**Tech Stack:** Existing Python, SQLite/gzip artifacts, Supabase PostgreSQL/private Storage, Streamlit custom JavaScript component, unittest, Node test runner and PGlite. No new application dependency.

**Spec:** `docs/superpowers/specs/2026-10-30-ap-active-bill-range-design.md` (user-approved 2026-10-30).

**Execution:** Native implementation in the existing isolated worktree, followed by one independent whole-branch review. Preserve the existing QA/recovery artifacts and old feature branch. Bring the approved documentation into that branch before implementation; do not deploy from an incomplete task.

## Global Constraints

- AP only; no changes to Daily Deposit, BILL or QuickBooks transactions.
- Modes: `last_12_months` (new-update default) and `all`. Existing sources remain full coverage until an acknowledged user action.
- Freeze the server's `America/New_York` date at begin; subtract one calendar year, clamp leap day, include cutoff and future dates. No midnight background purge.
- Keep uncertain/missing-date records, non-invoice transactions, unsettled bills and saved unresolved follow-ups. Exact settlement and protection rules are in the spec; do not substitute status-only retention.
- Preserve original imports, CSVs, full indexes, statement/PDF history and duplicate review evidence. No durable history purge in this release.
- Source caps: 750,000 CSV rows; 500,000 normalized records; 256 MiB original CSV; 32 MiB compressed per artifact; 512 MiB expanded per index. Preserve quota, envelope, per-step and authorization bounds. No limit increases to pass tests.
- New zero-active-record sets are valid; legacy source manifests retain their existing nonempty contract.
- Full export preparation remains a bounded one-time operation. Warm scoped reads/scans must not open the full source merely to filter records or recover training context.
- No production migration, shared range activation, merge/push or app reboot is part of implementation approval. Prepare a concrete rollout after verification.

## Review Focus

1. A renamed/reuploaded identical CSV with a different range/date/protection state must not reuse the wrong subset (Tasks 1, 3, 4).
2. Reopening an old statement or saving follow-up in another session during preparation must not lose its bill or publish stale absence (Tasks 2, 4, 5).
3. A range containing zero bills, but an archived vendor/reference, must display empty coverage and allow explicit archived lookup without claiming missing BILL data (Tasks 5, 6, 7).
4. Archived invoices needed for historical profile/recurrence checks must preserve full-source decisions without becoming active duplicate candidates (Tasks 3, 6).
5. A completed scan prepared under one scope must never be reused, reparsed or reported stalled under another; original/working ordinal confusion must fail verification (Tasks 3, 6, 7).

## Contract decisions shared by all tasks

These choices implement the builder discretion in the spec, not new user requirements.

- New Python package: `app/ap_shared/bills/working/`; its modules separate policy, protections, persistence, preparation and reads. Keep existing snapshot readers unchanged for historical use.
- Working identity: `workingSetId` UUID plus `workingDigest` SHA-256. Store canonical policy `{version:'ap-active-range-v1', mode, asOfDate, cutoffDate}` and the full source pin `{importId, importVersion, sourceDigest, recordCount}` separately. The set's content identity hashes source ID/hash, policy, semantic protection digest and `trainingVersion:'vendor-history-v1'`; import/working versions are activation CAS values, not content.
- Working artifact format `ap-bill-working-v1`, SQLite user_version 1, private key `<workspace>/bill-working/v1/<workingDigest>/<artifactHash>.sqlite.gz`. Two descriptors: `indexArchive` for active rows/directory/warnings and `contextArchive` for compact historical summaries. Both use existing gzip/hash/size checks.
- Active row schema records contiguous `ordinal`, unique `source_ordinal`, vendor/reference/kind/amount query fields, normalized `record` JSON and ordered `retention_reasons` JSON. Bill IDs presented to statement matching remain `<originalImportId>:<source_ordinal>`.
- PostgreSQL tables: `ap_bill_working_sets` (immutable prepared manifests and source/protection identity) and `ap_bill_working_jobs` (leased cooperative lifecycle). Workspace fields: nullable `active_working_set_id`, `working_set_version` default 0 and `bill_protection_epoch` default 0. Epoch detects source-protection changes; canonical protection digest permits semantic reuse after irrelevant saves.
- Source activation and working activation are one transaction when a newly uploaded full import is selected. Applying a range to the same import increments only working version. Old import activation must clear an incompatible pointer rather than carry a stale subset to another source.
- New authenticated actions: `bill_range_begin`, `bill_range_step`, `bill_range_activate`, `bill_range_cancel`, `bill_archived_candidates_page`. Existing snapshot upload/prepare remains the full-source stage. The frontend waits for range preparation and final atomic activation instead of calling legacy activation first.
- New capability: `billWorkingSets:1`; existing readers continue without it. Do not send new update actions to a server that lacks this capability.
- Scoped duplicate runs use rule `bill-duplicates-v4`, result format `bill-duplicates-v3`, private namespace `bill-duplicates/v3`, SQLite user_version 3. Old formats have explicit read validators, never a relaxed catch-all validator. Add working-set identity/source mapping to v4 pins/results. Extend scan uniqueness to include source/scope digest so repeated ranges do not overwrite a scan.
- Statement revisions gain nullable `working_set_id` provenance, validated with their existing `import_id`. Historical null values continue to mean full-source comparison. Manual review remains explicit and does not invent a working-set comparison.
- Date/protection parsing failures fail closed. An old/full-source frozen revision remains readable even when the current range is unavailable.

## Task 1: Pure retention policy and identity

**Files:** Create `app/ap_shared/bills/working/{__init__,policy,contracts}.py`; test `tests/test_ap_bill_working_policy.py`.

**Interfaces:** `make_policy(mode: str, now: datetime) -> dict`; `retention_reasons(record: dict, policy: dict, *, protected: bool=False) -> list[str]`; `working_digest(source: dict, policy: dict, protection_digest: str) -> str`; `validate_working_manifest(value: dict) -> dict`. Contracts validate counts, exact artifact namespaces/source identity and `activeCount + archivedCount == fullRecordCount`; exception counts are reason counts and can overlap.

- [ ] Write policy tests with a paid, zero-due invoice: `cutoff=2025-10-30`, date `2025-10-29` archives, date `2025-10-30` stays, date `2026-11-13` stays. Assert `make_policy('last_12_months', 2028-02-29 NY)` gives cutoff `2027-02-28` and dates crossing UTC/NY midnight use NY.
- [ ] Add tests for missing/invalid dates, Open/Scheduled/unknown status, positive/nonzero/absent/invalid amount due, valid paid-plus-credit substitute, boolean/noninteger amounts, source issues, non-invoice rows, all mode, protected old rows and zero counts. Assert missing due plus exact paid amount can archive; mismatching paid/credits cannot.
- [ ] Add identity/manifest tests: same complete inputs equal; any source/mode/as-of/protection change differs; invalid namespace/hash/count and cross-workspace descriptors fail.
- [ ] Run `python -X utf8 -m unittest discover -s tests -p 'test_ap_bill_working_policy.py' -v` and observe assertion/import failures before implementation.
- [ ] Implement the four interfaces, run the same tests green, then commit only policy/contracts/tests.

## Task 2: Authoritative protections and private database lifecycle

**Files:** Create `working/protections.py`, `working/repository.py`, `supabase/migrations/202610300001_ap_bill_working_sets.sql`, `tests/test_ap_bill_working_protections.py`, `tests/test_ap_bill_working_schema.py`, `tests/fixtures/ap_shared/working_schema_checks.mjs`. Modify `app/ap_shared/repository.py` only for private object-key capability plumbing required here.

**Interfaces:** `ProtectionRepository.snapshot(source_import_id: str, auth) -> dict` returns server epoch, canonical digest and paginated saved inputs; `ProtectionSet.add_statement(statement: dict, revision: dict, mappings: dict)`, `.add_duplicate(review: dict, members: list[dict])`, `.protects(record: dict) -> bool`, `.digest() -> str`. `WorkingRepository.rpc(operation: str, data: dict, request_id: str) -> dict`, `.job(job_id)`, `.working_set(set_id)`, `.put_artifact(job_id, name, path)`, `.read_artifact(manifest, name, target)` stay workspace scoped.

- [ ] Write protection tests asserting older discrepancies are protected without equal amounts; all plausible vendor/reference records and Adventure aliases survive; explicit follow-ups on completed/archived statements survive; latest resolved revisions release protections; current saved `confirmed_duplicate`/`unreviewed` protect all members and `not_duplicate` does not. Unreviewed findings without a saved decision do not protect arbitrary old history. Missing member evidence must fail, not disappear.
- [ ] Write PGlite lifecycle tests for immutable ready sets, private RLS/service-only RPC permissions, semantic digest reuse, stale source/import/working version/epoch activation rejection, request-ID replay/conflict, session/lease/generation guards, quotas and cancellation. Assert legacy import uniqueness and historical revision/review rows remain unchanged.
- [ ] Add epoch triggers for current statement/revision identity, relevant mapping and duplicate-review changes, locking the workspace row before changing protected state. Test a genuinely interleaved two-session save/activation and trigger rollback, not only sequential stale payloads. Add nullable revision working-set FK and guarded scoped-save validation.
- [ ] Add `ap_bill_working_mutate` service-only dispatcher with operations `begin`, `checkpoint`, `stage`, `activate`, `cancel`, `reserve`; transactionally validate prepared manifest, source and authoritative protection epoch. Stage persists immutable verified metadata; activation alone changes shared pointers/versions. Provide a complete same-source/new-source/legacy-import compatibility fixture.
- [ ] Run the new protection/schema tests red, implement using established pagination/idempotency/error conventions, run them green together with existing bill schema/storage/shared-repository tests, then commit.

## Task 3: Bounded working-index and historical-context builder

**Files:** Create `working/builds.py`, `working/context.py`, `working/archive.py`, `tests/test_ap_bill_working_builds.py`, `tests/test_ap_bill_working_context.py`, `tests/test_ap_bill_working_archive.py`. Reuse normalization, snapshot index and duplicate identity/profile code without changing old artifact semantics.

**Interfaces:** `WorkingBuilder(source_db, output_dir, source: dict, policy: dict, protections: ProtectionSet, monotonic)`; `.step(deadline: float) -> dict`; `.artifacts() -> dict`; `.close()`. `HistoryContext.profile(vendor_key: str, month_ordinal: int) -> dict`; `.recurring(vendor_key: str, amount: int, day: int) -> bool`. `WorkingCache.prepare(manifest, auth, authorize, deadline) -> bool` and `.acquire(manifest, auth, authorize)` yield verified read-only active/context databases.

- [ ] Write a synthetic interleaved-source fixture: recent and protected old rows get contiguous active ordinals with exact original source ordinals; excluded old rows never become active candidates; reason counts and directory digest are reproducible; source bytes/tables remain unchanged; empty sets produce valid artifacts.
- [ ] Write context parity tests against full-source `VendorPatterns`: preceding-month/365-day boundaries, top-three/tie rules, duplicate/ambiguous source exclusions, 90-day recurring purchases, protected old candidates, two vendors sharing an amount and candidates on different dates. Remove the source connection after build and assert context still returns identical answers.
- [ ] Exercise historical-context key coverage for every possible active candidate's vendor/month and vendor/amount/day (including comparison date used for a pair), not only a sample. Missing keys must be explicit unavailable errors, not false recurrence or a fabricated profile.
- [ ] Write corruption/size tests for swapped artifacts, wrong policy/protection/source, wrong original ordinal, mismatched count/vendor digest, gzip/hash/schema corruption and oversized compact context. Complete validation precedes durable stage publication.
- [ ] Run the three new test modules red; implement cooperative phases (source/protection selection, historical summaries, compact copy/indexes, package/hash) with at most 5,000 source rows or 250 context rows per batch and a five-second cooperative deadline. Persist restart identity and obey quota/storage bounds.
- [ ] Run green plus existing bill archive/build and duplicate profile/scale regressions. Instrument cache preparation to assert warm acquisition never reads/decompresses the full archive. Commit.

## Task 4: Authenticated range orchestration and atomic activation

**Files:** Create `working/operations.py`, `tests/test_ap_bill_working_operations.py`. Modify `app/ap_shared/{models,service,repository}.py`, `bills/{operations,repository}.py` for routing/capabilities and full-import handoff, retaining existing legacy actions.

**Interfaces:** `WorkingOperations.handle(action: str, payload: dict, request_id: str, authorization) -> dict`. Begin payload `{source_import_id, mode, expected_import_version, expected_working_version, upload_job_id?}`; server supplies frozen date/protections and returns `{job_id, generation, checkpoint, policy}`. Step uses `{job_id,generation,expected_checkpoint,restart?}`. Activate uses `{job_id,expected_import_version,expected_working_version}`; returns authoritative source plus working set/version/counts. Cancel uses `{job_id}`. No client credentials, SQL, paths, protection members or cutoff override.

- [ ] Write action tests covering saved-export application, new ready full-import preparation without early activation, identical-source changed range, semantic same-scope reuse, midnight/restart date stability and cancellation after each phase. Assert failed range preparation leaves BOTH old active import and old active set usable.
- [ ] Add malformed/auth-expiry/session-rotation, corrupt protection evidence, missing migration, reservation failure, source/epoch change mid-build, dropped stage/activation reply and replay tests. Recheck authorization before and after storage/network work.
- [ ] Add automatic protection-refresh coordinator: a changed epoch recomputes semantic protections, reuses an unchanged set if equivalent, or prepares a new one before a current comparison/scan is published. It preserves the acknowledged policy/as-of date; does not secretly advance the rolling cutoff. Bound work with the same job protocol and never recalculate on every navigation.
- [ ] Make full snapshot upload completion hand a prepared import to range orchestration rather than publishing it first when the new capability is used. Same raw file detection must still allow a different policy/protection scope. Retain old upload/activation compatibility for unscoped clients and explicitly clear incompatible pointers.
- [ ] Run new orchestration tests red, implement, then run new tests plus existing bill operation/build/upload lifecycle tests green and commit.

## Task 5: Scoped statement reads, provenance and archived lookup

**Files:** Create `working/queries.py`, `tests/test_ap_bill_working_queries.py`. Modify `bills/operations.py`, `app/ap_shared/{service,repository,models}.py`, `app/ap_statements/frontend/{comparison-source,core,shared-workspace}.mjs`. Add `tests/ap_statements_bill_range_source.test.mjs` and extend statement/re-review backend fixtures.

**Interfaces:** `WorkingQueries.candidates_page(set_id, query, cursor, auth) -> dict` returns original bill IDs, original ordinal cursor, complete query digest and scope; `.vendors_page(...)` returns scoped directory and digest; `.archived_references_page(import_id, references, cursor, auth)` accepts at most 100 exact normalized reference/kind keys, no amount-only archive search. `comparison-source.ensure` includes acknowledged working identity in cache/input keys and preserves full-source paths for frozen revisions.

- [ ] Write source tests asserting active exact-reference and amount queries see only retained records, preserve original IDs and verify completeness despite sparse original ordinals. Vendor page and empty directory are valid with a zero active set; archived-only vendors remain discoverable for explicit historical lookup without injecting all their invoices into active results.
- [ ] Write outside-range tests: older dated or date-uncertain references absent from active data get `Outside active BILL range — check archived data`, never plain full-source absence. Add explicit archived lookup with pinned source, exact references, original IDs and archived-match labels; errors stay unavailable, and no archived amount-only search occurs.
- [ ] Write current-save/reopen tests: saved scope belongs to saved import; changed active scope/protections rejects stale live saves; manual review remains available; historical null-scope and scoped revisions render original frozen results. Opening a current draft refreshes protections before publishing a comparison.
- [ ] Run Python query/service/re-review tests and new Node source tests red; implement strict source-aware cursor/cache/count validation and provenance, then run new and existing comparison/re-review suites green and commit.

## Task 6: Scope-bound duplicate scans with preserved historical safeguards

**Files:** Modify `bills/duplicates/{contracts,source,repository,operations,scan,vendor_patterns,vendor_scan,artifacts,projection}.py`, `app/ap_shared/repository.py`; create `tests/test_ap_duplicates_working_scope.py`. Add `supabase/migrations/202610300002_ap_duplicate_working_scope.sql`, `tests/fixtures/ap_shared/duplicate_working_schema_checks.mjs`, `tests/test_ap_duplicates_working_schema.py`. Extend duplicate contract/artifact/scan fixtures.

**Interfaces:** V4 pin extends the old source pin with `{workingSetId,workingDigest,workingVersion,fullSourceDigest,fullRecordCount}`; `sourceDigest` is the working digest and `recordCount` the active count. `DuplicateSource.read_page` provides active contiguous ordinals plus verified `sourceOrdinal`; `.members` returns both mappings and original import bill IDs. `VendorPatterns` accepts a verified `HistoryContext` for scoped scans; old/full artifact readers retain their exact old contract.

- [ ] Write tests proving only active member pairs are emitted, profiles/recurrence equal full-source calculations, cross-boundary archived members are not implied checked, empty input completes with zero findings, and original-vs-active ordinal swaps fail prepublication/cache/projection validation.
- [ ] Add SQL ensure/claim/publish/review tests for working pointer/version/digest, unchanged source but changed range, stale protection refresh, scope-keyed uniqueness and result namespace. Validate migration with all prior migrations and preserve existing scan/review/event rows and ACLs. A source/import version check alone is insufficient.
- [ ] Add explicit artifact dispatch for old v1/v2 manifests and new v3; V4 results persist original mapping in members and bind working context identity in scan metadata. Scope changes invalidate only derived current UI/cache views, not immutable stored evidence. Preserve explicit prior-review disclosure; never auto-confirm a duplicate.
- [ ] Add controller/progress tests for completed results under an old scope, local preparation of a completed current scan, interrupted scope refresh and active scan restart. Preserve the completed-scan status fix; no perpetual automatic rescan or false “stalled” warning.
- [ ] Run the new duplicate scope/schema tests red; implement; run all existing duplicate contracts/scans/profile/artifact/projection/SQL tests green plus synthetic scale checks for full coverage. Commit.

## Task 7: Range selector, prepared summary and shared UI acknowledgement

**Files:** Create `app/ap_statements/frontend/bill-range.mjs`, `tests/ap_statements_bill_range_ui.test.mjs`, `tests/ap_statements_bill_range_update.test.mjs`. Modify frontend `app.mjs`, `bill-update-ui.mjs`, `bill-upload.mjs`, `shared-workspace.mjs`, `duplicate-bills.mjs`, `duplicate-bills-ui.mjs`, `styles.css`, `guide.mjs`, `bill-export-guide.mjs`; extend upload/snapshot/comparison/duplicate UI fixtures.

**Interfaces:** `createBillRangeUI({client,shared,hasUnsaved,onProgress,confirmApply})` exposes `.applySaved(mode)`, `.prepareUploaded(importResult,mode)`, `.refreshProtections()`, `.dispose()`. `rangeSummaryHTML(prepared)` renders full/active/archived/reason counts and cutoff. `createBillUpdateUI.update(file,{asOf,mode='last_12_months'})` uses full upload preparation, range preparation, explicit prepared-summary acceptance and atomic activation/readback before publishing local source state.

- [ ] Write selector/default tests asserting new updates choose Last 12 months, existing sources retain acknowledged full coverage, both modes are keyboard accessible, and changing an unsaved selection alone changes no shared source or scan.
- [ ] Write apply/cancel/error tests: show exact cutoff/counts/reasons; retain prior workspace during prepare; publish only after activation and authoritative directory/scope readback; same CSV/different range is not an early no-op; concurrent source change adopts the authoritative result; interrupted navigation aborts pending work and leaves no stale callback publication.
- [ ] Write shared-session and guard tests: unsaved edits block update/refresh; invalidated protections show progress/unavailable rather than false matches; legacy capability hides/disables unsupported action with useful copy; all-mode restoration, zero set and archived lookup work; completed saved revisions remain readable.
- [ ] Run new UI/update tests red; implement a compact field/summary in the existing BILL area, show range/active count on duplicate summary, update help copy, run all `ap_statements*.test.mjs` green and build with `node app/ap_statements/build.mjs`. Commit.

## Task 8: Representative verification, review and concrete rollout package

**Files:** Add synthetic runner `tests/fixtures/ap_shared/bill_working_scale_check.py`, `tests/test_ap_bill_working_scale.py`, `docs/ap-bill-working-range-rollout.md`, `docs/superpowers/verification/2026-10-30-ap-active-bill-range.md`. Keep raw company records, artifacts and timings outside tracked docs except sanitized summaries.

- [ ] Add scale/parity regression tests for 223,425 and 500,000 synthetic records, all mode, empty mode, many retained exceptions and many historical profile keys. Assert existing bounds, original-byte/table immutability, complete active/context coverage, deterministic repeated identity/artifacts and no full-archive warm reads.
- [ ] Run read-only company-export analysis using the saved local source index, recording its provenance hash. Compare policy counts to the previous 24,884 preliminary result, explain any saved-protection additions and compare each active candidate's profile/recurrence against full-source computation. Do not upload company records or label candidates as confirmed duplicates.
- [ ] Measure import/apply, cold/warm comparison reads and active duplicate scans on the same machine; report actual timing and resource differences, not “89% faster.” Preserve error/progress correctness and distinguish initial full-export work from routine operation.
- [ ] Run full backend with `$env:PYTHONPATH='tests'; python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v`, full frontend with `node --test tests/ap_statements*.test.mjs`, production build with `node app/ap_statements/build.mjs`, and `git diff --check`. Use the verified short-path Python environment or provision an equivalent task environment if it is unavailable. Investigate failures before broad repetition.
- [ ] Perform synthetic local browser checks of selector, prepared counts, cancel/failure, active-empty, archived lookup, original PDF/history and back navigation. Do not save live financial decisions or reboot the shared app. Record any unperformed live checks explicitly.
- [ ] Request one independent whole-branch review using the native execution workflow; reproduce substantive findings with tests, correct and rerun affected/full gates as needed. No review loop merely to obtain approval.
- [ ] Write exact migrations/ACL/recovery checks and production activation steps in the rollout package, including how to keep v4-aware readers after scoped artifacts exist. Stop before external mutation/publication and present the verified result and remaining rollout actions for review.

## Self-review record

The plan maps every spec section to policy/protection, derived storage/context, orchestration, scoped reads, duplicate adaptation, UI or rollout tasks. Review Focus cases are explicitly tested in their owning tasks. Interface names and wire keys are defined once above; no task may treat a partial working set as a legacy complete import. Optional external production actions remain outside implementation and all actual speed claims require measured results.
