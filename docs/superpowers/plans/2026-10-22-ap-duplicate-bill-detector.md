# AP Statements Duplicate Bill Detector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically scan the saved current BILL dataset for explainable possible duplicates and let the finance team save reviews without changing BILL or statement reconciliation.

**Architecture:** Read the complete pinned import on the Python server, generate narrowly defined candidates in disk-backed tables, and publish a verified immutable result artifact. Postgres holds scan metadata and durable versioned reviews; the browser drives bounded scan steps and loads only paginated findings and evidence. Keep the detector separate from statement matching and preserve reviews using evidence fingerprints rather than import-scoped row IDs.

**Tech Stack:** Existing Python standard-library SQLite, gzip, hashlib, tempfile, and unittest; existing Streamlit and Supabase; vanilla JavaScript modules and Node tests; existing PGlite schema-test runtime. No new product dependency or hosted worker.

**Spec:** `docs/superpowers/specs/2026-10-22-ap-duplicate-bill-detector-design.md`, approved for planning October 22, 2026.

## Global Constraints

- Scan one pinned active import, never a union of historical exports.
- Version one scans normalized records and preserves the existing consolidation rules. Do not change the parser, existing snapshot manifest, comparison index format, matching API, Adventure in Food matching rules, or statement resolutions.
- Compare original bill totals in exact integer cents. Eligible records are invoice-kind, positive, nonblank vendor and reference. Exclude credits, negative amounts, and zero-value records.
- Vendor lookup uses trimmed case-insensitive names with repeated whitespace collapsed. Invoice lookup uses uppercase with whitespace removed; preserve punctuation and leading zeros.
- Suffix similarity requires the same numeric stem of at least four digits and one optional trailing ASCII letter. Transposition swaps exactly two adjacent unequal digits in equal-length references of at least four characters. Both similarity rules require valid invoice dates within the inclusive 30-day window.
- Exact-reference checks cover all eligible dates. Same reference with unequal original amounts is a separate warning. Equal amounts alone, sequential numbers, arbitrary edit distance, and unrelated vendors do not qualify.
- Missing or invalid currency cannot establish known equal currencies. Known unequal currencies exclude amount-based findings. Never assume missing native currency is USD.
- Export ambiguity overrides a stronger label. No automatically confirmed duplicates, invented independent bills, transitive duplicate groups, financial corrections, or claims of duplicate payment.
- Support 500,000 normalized records and 750,000 source rows. Completed results are limited to 100,000 findings, 512 MiB expanded, and 32 MiB compressed. Reject limits explicitly, never truncate and claim completion.
- Cooperative steps process at most 5,000 records or 10,000 candidate probes, with a five-second budget and resumable inner-bucket state.
- Bound simultaneous scans to one per workspace and two per server process. Use expiring server-owned leases and one-hour temporary-state expiry.
- Result and member pages contain at most 100 items and fit the existing bridge envelope. Counts and reviewed filters require a complete review projection at one workspace review revision.
- Review mutations atomically check current import version, ready scan, evidence, and expected review version. Initials are required and self-reported; notes are optional; timestamps are server-owned.
- No source originals, historical snapshots, PDFs, or review events are automatically deleted. Storage reservations include competing imports and detector work under the configured bucket budget.
- No product changes until this plan is reviewed and an execution method selected. No live migration, real upload, merge, push, or production deployment is authorized by planning approval.

## Review Focus

1. Legitimate Adventure in Food suffix bills must remain review suggestions, and a saved Not a duplicate decision must survive weekly changes to reported paid amounts. Pin this in Tasks 1 and 9.
2. The bridge serializes requests: automatic scans must yield between steps so uploads, saves, and statement checks do not sit behind an entire scan. Pin this in Tasks 6 and 7.
3. Legacy exports can omit invoice dates and currencies: do not use a payment date as an invoice date or manufacture a similarity match. Pin this in Tasks 1 and 2.
4. A colleague can review while another user pages Reviewed results: reject stale cursors instead of losing or duplicating rows. Pin this in Tasks 3 and 5.
5. Navigation or a status update must not erase an unsaved duplicate-review note or leave sensitive evidence after access expires. Pin this in Tasks 7 and 8.

## Execution environment and verification

At execution time, use the using-git-worktrees skill and inspect branch, tracked changes, and repository instructions. Prefer the existing linked worktree `portal-source/.worktrees/deploy-dd-v2`, branch `codex/ap-shared-workspace`, containing specification commit `03ab94e` or a descendant. Do not edit synced `sources/`, unrelated user changes, or ignored QA artifacts. Preserve existing preview screenshots.

Run commands from that worktree. In commands below, `python` denotes the verified project interpreter; on this workstation it is `C:/Users/karlcruz/AppData/Local/Temp/ap-tut-1019/Scripts/python.exe`. Resolve a replacement existing runtime if that temporary environment is unavailable. Use `-X utf8` for Python and `--test-isolation=none` for Node in this Windows environment. Obtain appropriate execution permissions for temporary-file tests and esbuild; an environment denial is not a valid red test.

Each task follows failing assertion, verified red run, minimal implementation, green run, and narrow commit. Keep existing tests; do not replace them with detector-only checks. The commands in this plan are future execution steps, not claims that unimplemented tests already pass.

## File structure and common types

New Python modules live in `app/ap_shared/bills/duplicates/`:

| Module | Responsibility |
| --- | --- |
| `contracts.py` | Typed wire objects, rule and artifact versions, limits, validation, safe errors and cursor binding |
| `rules.py` | Eligibility, reference rules, evidence classification and fingerprints |
| `source.py` | Complete pinned snapshot or legacy pages and bounded evidence reads |
| `scan.py` | Disk-backed candidate generation and resumable local scan engine |
| `repository.py` | Narrow Supabase scan and review RPCs, private result storage and review pagination |
| `artifacts.py` | Incremental result packing and independently validated derived-artifact cache |
| `projection.py` | Complete review projection, counts, filtered result pages and member evidence |
| `operations.py` | Authorized lifecycle coordination and detector action dispatch |

Create a small `__init__.py` with no side effects. New frontend modules are `duplicate-bills.mjs` for the controller and `duplicate-bills-ui.mjs` for rendering and review drafts. Existing `app.mjs` only wires navigation, source adoption, view rendering, and event delegation. Do not copy the matching algorithm into the detector.

Python paths abbreviated as `duplicates/` below are relative to `app/ap_shared/bills/`. Existing-file changes are limited to the named integration points; no unrelated refactoring is part of a task.

Define these JSON-shaped TypedDicts in `contracts.py` before later tasks use them:

- `SourcePin = {importId: str, importVersion: int, sourceDigest: str, storageFormat: str, recordCount: int}`. IDs are UUIDs, digest is 64 lowercase hex characters; record count follows the existing format-specific bounds.
- `ScanRecord = {ordinal: int, bill: JsonObject}`. Bill is validated with the existing `validate_record`; ordinal is a locator, not cross-import identity.
- `Finding = {key: str, classification: str, strength: str, reasons: list[str], latestInvoiceDate: str, memberCount: int}`. Classifications are `exact_pattern`, `possible_duplicate`, `amount_difference`, and `export_review`; strength is `strong` or `possible`. The key is the evidence fingerprint.
- `Member = {ordinal: int, fingerprint: str}`. Keep each normalized-record locator individually inspectable. Compute fingerprint multiplicities by counting these members, not by counting raw CSV sourceRows of an already consolidated bill.
- `ScanProgress = {scanId: str, importId: str, importVersion: int, ruleVersion: str, state: str, generation: str, checkpoint: int, phase: str, recordsRead: int, probes: int, findingCount: int | None, counts: JsonObject | None, projectionReady: bool, reviewRevision: int | None, errorCode: str | None}`. State follows the spec; phase is `reading`, `candidates`, `packaging`, or `complete`. A ready artifact can expose its findingCount while its review projection is preparing; counts and projectionReady do not claim reviewed totals until that projection is complete.
- `ResultManifest = {format: 'bill-duplicates-v1', ruleVersion: str, sourceDigest: str, importId: str, key: str, hash: str, bytes: int, expandedHash: str, expandedBytes: int, findingCount: int, recordCount: int}`.
- `Review = {key: str, decision: str, initials: str, note: str, version: int, at: str, reviewedImportId: str}`. Decision values are `confirmed_duplicate`, `not_duplicate`, or `unreviewed`. No row means unreviewed with expected version zero; reopening an existing review increments its version and preserves an event.
- `BillPreview = {ordinal: int, vendor: str, invoiceNumber: str, amount: int, invoiceDate: str, currency: str}`. A finding summary is Finding plus `preview: list[BillPreview]` capped at two, `review: Review | None`, and `priorReview: bool`.
- `FindingPage = {scanId: str, importId: str, ruleVersion: str, reviewRevision: int, total: int, counts: JsonObject, items: list[JsonObject], nextCursor: str | None}`. Each item is a finding summary. Member pages use the same source/revision identity plus `findingKey`, `members: list[ScanRecord]`, `total`, and `nextCursor`. Counts contain `scannedRecords`, `eligibleRecords`, `excludedRecords`, `totalFindings`, `unreviewedFindings`, and `reviewedFindings`; the last two cover the complete current scan, not just the selected filter.

Rule version is `bill-duplicates-v1`, fingerprint format version is `1`, and result SQLite user version is `1`. Detector errors are `duplicate_unavailable`, `duplicate_conflict`, `duplicate_limit`, `duplicate_restart`, `duplicate_quota`, and `duplicate_invalid_source`; map each to safe actionable copy without financial values.

## Task 1 Detection rules and durable evidence identity

**Files:** Create `duplicates/__init__.py`, `duplicates/contracts.py`, `duplicates/rules.py`, `tests/test_ap_duplicates_rules.py`, and `tests/fixtures/ap_shared/duplicate_cases.py`.

**Interfaces:** `eligible(bill: JsonObject) -> bool`; `reference_reasons(left: JsonObject, right: JsonObject) -> list[str]`; `identity_warnings(bill: JsonObject) -> list[str]`; `classify(left: JsonObject, right: JsonObject) -> JsonObject | None`; `bill_fingerprint(bill: JsonObject) -> str`; `finding_key(members: list[tuple[str, int]], classification: str, warnings: list[str], rule_version: str = RULE_VERSION) -> str`. Classification returns classification, strength, and reason codes, not translated UI strings. Contracts also produce `validate_pin(value: object) -> SourcePin`, `validate_manifest(value: object) -> ResultManifest`, `validate_review_payload(value: object) -> JsonObject`, and `DuplicateError(code: str = 'duplicate_unavailable')`.

- [ ] Write table-driven unittest assertions: `271712` versus `271712X` and `271712A` versus `271712B` at 129981 cents qualify at day 30 but not 31; `271712` versus `271721` qualifies as adjacent transposition; `271712` versus `271713` does not. Equal amounts alone, four versus three digit stems, leading-zero removal, differing vendors, known USD versus CAD, and credits do not qualify. Assert missing invoiceDate does not borrow paymentDate. Assert equal normalized vendor/reference/date/currency/total always yields export_review even if IDs or raw formatting differ.
- [ ] Add fingerprint assertions `self.assertEqual(bill_fingerprint(before), bill_fingerprint(payment_updated))`, `self.assertNotEqual(bill_fingerprint(before), bill_fingerprint(amount_updated))`, and multiplicity and third-member key changes. Check reference case or punctuation changes conservatively reopen; sourceRows and ID changes do not. Ignore known payment-only warning text for identity and classification, but preserve unfamiliar or bill-identity warnings. Currency tokens are trimmed and uppercased; a nonempty code is usable only if it is three ASCII letters, without claiming a currency-registry verification.
- [ ] Run `python -X utf8 -m unittest discover -s tests -p 'test_ap_duplicates_rules.py' -v`; confirm an unmet rule assertion or missing new interface causes red, not an interpreter failure.
- [ ] Implement these pure functions using existing vendor/invoice normalization and canonical JSON hashing. Include original trimmed reference in the durable bill fingerprint but use normalized identity separately for ambiguity. A missing or invalid currency lowers confidence; never coerce cents or dates. Define specific reason codes for suffix, transposition, exact reference, unequal total, unknown currency, reused date, and ambiguous source. Do not change existing matching code.
- [ ] Rerun `python -X utf8 -m unittest discover -s tests -p 'test_ap_duplicates_rules.py' -v`, `python -X utf8 -m unittest discover -s tests -p 'test_ap_bill_parser.py' -v`, and `python -X utf8 -m unittest discover -s tests -p 'test_ap_bill_index.py' -v`. Commit the Task 1 files as `feat: define conservative duplicate bill rules`.

## Task 2 Complete source reads and bounded candidate generation

**Files:** Create `duplicates/source.py`, `duplicates/scan.py`, `tests/test_ap_duplicates_scan.py`, and `tests/test_ap_duplicates_source.py`.

**Interfaces:** `DuplicateSource(base_repository, bill_operations)` supplies `pin(authorization) -> SourcePin | None`, `read_page(pin, after: int, limit: int, authorization) -> {records: list[ScanRecord], nextOrdinal: int | None, total: int}`, and `members(pin, ordinals: list[int], authorization) -> list[ScanRecord]`. Snapshot reads use the existing authorized cache through the bill operations object; legacy reads use `records_page` directly and never repeatedly invoke the legacy full-index builder. `DuplicateScan(connection, pin, monotonic)` supplies `ingest(records: list[ScanRecord]) -> None`, `finish_input() -> None`, `step(deadline: float, max_probes: int = 10000) -> JsonObject`, and `finish() -> JsonObject`.

- [ ] Write fixtures using the real CsvStage and SnapshotIndex for complete multi-line bills, inconsistent duplicate rows, missing dates and currencies, and a deep ordinal past 100,000. Assert every snapshot ordinal is read exactly once, all legacy pages are checked against their stated count, and a missing or repeated page cannot finish. Test source changes between page requests and authorized evidence retrieval from the pinned import.
- [ ] Write scan tests asserting one suffix pair, one transposition pair, one distinct amount-difference pair, and a single grouped export_review finding for 10,000 indistinguishable rows. Assert no A-to-C edge from A-to-B and B-to-C. Use an injected clock and probe budget of two to prove an inner bucket resumes without duplicated findings. A 10,000-record equal-amount bucket with unrelated references must not perform 49,995,000 all-pairs comparisons.
- [ ] Run both new suites and verify red. Implement source readers with strict ordinal/count validation and current pin checks. Build temporary `scan_records`, `reference_keys`, `variant_keys`, `findings`, `members`, and `scan_meta` tables; retain only required detection keys and locators rather than full duplicate copies of bill JSON. Add matching indexes, canonical pair uniqueness, grouped identity multiplicity, and a committed inner-loop checkpoint.
- [ ] Candidate generation uses exact reference buckets for amount differences, numeric stems for suffixes, and bounded adjacent-swap variants for transpositions; amount and vendor are required join keys for similarities. Exclude unequal known currencies and apply date eligibility before emitting. One group represents an ambiguous exact-reference bucket; do not emit its Cartesian row pairs. Exact-reference buckets with distinct reliable identities can use direct pairs up to the explicit finding limit. SQLite progress interrupts must leave a retryable checkpoint, not an apparently finished query.
- [ ] Rerun both suites, assert the 100,001st finding raises duplicate_limit with no complete counts, and verify byte and record limits by lowering constants in focused fixtures. Commit as `feat: scan complete BILL sources without quadratic matching`.

## Task 3 Atomic scan metadata and shared review schema

**Files:** Create `supabase/migrations/202610220001_ap_duplicate_bills.sql`, `duplicates/repository.py`, `tests/test_ap_duplicates_schema.py`, `tests/fixtures/ap_shared/duplicate_schema_checks.mjs`, and `tests/test_ap_duplicates_repository.py`.

**Interfaces:** New tables `ap_duplicate_scans`, `ap_duplicate_reviews`, and `ap_duplicate_review_events`; workspace fields `duplicate_schema_version` default 1 and `duplicate_review_revision` default 0. RPC `ap_duplicate_mutate(p_operation,p_workspace,p_request_id,p_payload_hash,p_data) -> jsonb` supports `ensure`, `claim`, `checkpoint`, `restart`, `publish`, `fail`, `reserve`, and `review`. Python `DuplicateRepository(base_repository)` supplies `current() -> SourcePin | None`, `scan(scan_id) -> JsonObject`, `rpc(operation, data, request_id) -> JsonObject`, `review_revision() -> int`, and `reviews_page(after_key: str | None, limit: int = 500) -> JsonObject`.

RPC payloads are allowlisted in SQL and Python together: ensure `{scan_id,import_id,expected_import_version,source_digest,rule_version}`; claim `{scan_id,session_nonce}`; checkpoint `{scan_id,session_nonce,generation,expected_checkpoint,next_checkpoint,phase,progress}`; restart `{scan_id,session_nonce,expected_generation}`; publish `{scan_id,session_nonce,generation,expected_checkpoint,expected_import_version,manifest}`; fail `{scan_id,session_nonce,generation,expected_checkpoint,error_code}`; reserve `{scan_id,session_nonce,bucket,requested_bytes,budget_bytes}`; review uses the public review payload from Task 6 plus server-derived `verified_key`. Progress contains recordsRead and probes. SQL requires verified_key equals finding_key, but the actual artifact membership verification remains Python's responsibility. A scan ID is deterministic UUID5 from workspace/import/rule; lease times and timestamps are generated by SQL. Restart never mutates an already ready artifact.

- [ ] Create a separate PGlite fixture loading both deployed migrations followed by the new migration. Assert one scan per workspace/import/rule, one live scan lease per workspace, independent leases across workspaces, unchanged import state, no Postgres copies of normalized bill records, and service-only reads/writes. A missing detector migration must remain distinguishable from a storage outage.
- [ ] Assert atomic review behavior: expected version zero creates version one; same request ID and payload replays the acknowledgement with exactly one event; conflicting payload or stale version fails; server timestamp and normalized required initials are recorded. Changed current import, A-to-B-to-A import version, nonready scan, or mismatched evidence identity cannot save. Reopen increments review and workspace revisions. Another workspace cannot read a review by fingerprint.
- [ ] Run `python -X utf8 -m unittest discover -s tests -p 'test_ap_duplicates_schema.py' -v` and repository boundary tests; verify red. Implement the additive migration, repository allowlists, foreign keys, ready-manifest immutability, generation/checkpoint comparisons, leases, idempotency, and append-only review events. Lock workspace then scan then review consistently to avoid deadlocks. Scan artifact membership is validated by the server before the service-only review RPC; SQL still checks current scan/source/version atomically.
- [ ] Add service-only `ap_storage_reserve(p_owner text,p_workspace uuid,p_job uuid,p_bucket text,p_requested bigint,p_budget bigint) returns jsonb` as the shared reservation helper; owner is strictly bill or duplicate. In this new migration, redefine the existing `ap_bill_mutate` quota-reserve branch to delegate to the helper while preserving all its other operations and signatures. Both reservation paths must use the existing `ap-bill-quota:` bucket advisory-lock namespace and count private storage objects plus all unexpired competing reservations. Accept budgets and bucket identity only from server configuration. Test interleaved bill and duplicate reservations fail rather than overbook; keep existing snapshot schema tests green.
- [ ] Run the new schema/repository suites and existing `test_ap_shared_schema.py` and `test_ap_bill_schema.py`. Verify the fixture prints `Duplicate bill SQL checks passed` and exits zero. Commit as `feat: persist private duplicate scans and review decisions`. Do not apply the migration to a live project.

## Task 4 Verified result artifacts and resource ownership

**Files:** Create `duplicates/artifacts.py` and `tests/test_ap_duplicates_artifacts.py`; extend `duplicates/repository.py` with artifact I/O.

**Interfaces:** `DuplicateArtifactWriter(source_path, target_path)` supplies `step(max_bytes: int = 4194304, deadline: float | None = None) -> JsonObject` and `close()`. `DuplicateArtifactCache(repository, root=None, clock=time.monotonic)` supplies `acquire(workspace_id, scan_id, manifest, authorization, authorize)` as a context manager and `close()`. Repository adds `put_result(scan, path, request_id) -> ResultManifest` and `read_result(manifest, target) -> None`.

- [ ] Write round-trip hash and count assertions for an actual small scan artifact. Verify the allowed tables are exactly findings, members, and scan_meta after staging tables are removed; no bill JSON or credentials are stored in Postgres metadata. Reject arbitrary paths, wrong workspace, wrong source digest, invalid hashes, corrupt SQLite, unexpected schema, wrong counts, and gzip expansion beyond 512 MiB.
- [ ] Run the artifact suite and verify red. First copy only findings, members, and scan_meta into a fresh final SQLite file in bounded steps, then gzip it incrementally; dropping staging tables alone must not leave source keys on the artifact's freelist. Retain only two display previews and normalized vendor/reference search columns per finding, with locators for full evidence. Enforce a 32 MiB compressed limit, immutable namespace `<workspace>/bill-duplicates/v1/<importId>/<ruleVersion>/<hash>.sqlite.gz`, and validated manifest. Reserve up to 64 MiB for a staged plus final compressed result before object writes; release reservations only after acknowledged publication or terminal failure. Quota failure leaves BILL active.
- [ ] Implement a separate derived cache validator; do not weaken SnapshotCache's fixed comparison-schema validation or reuse its manifest as though it accepted detector tables. Use private temporary files, a 512 MiB total derived-cache budget, one-hour idle expiry, reference-counted readers, and read-only SQLite with extension loading disabled and trusted schema off.
- [ ] Add tests for active-reader eviction, lock during download, expired access after decompression, close during a read, exactly 32 MiB versus one byte over, and failures after immutable upload but before publication. Retry reuses identical content-addressed result paths. No broad storage deletions are permitted.
- [ ] Run artifact, repository, and existing bill archive suites, confirming no original source hashes or files change. Commit as `feat: store and verify bounded duplicate result artifacts`.

## Task 5 Complete review projections and filtered evidence pages

**Files:** Create `duplicates/projection.py` and `tests/test_ap_duplicates_projection.py`; extend contract cursor functions in `duplicates/contracts.py`.

**Interfaces:** `ReviewProjection(repository, artifact_cache, source_reader, clock)` supplies `prepare(scan, authorization, deadline: float) -> {ready: bool, reviewRevision: int}`, `findings_page(scan, filters, cursor, limit, authorization) -> FindingPage`, `members_page(scan, finding_key, cursor, limit, authorization) -> JsonObject`, `invalidate(workspace_id) -> None`, and `close()`. Filters are `{review: 'unreviewed' | 'reviewed' | 'all', classification: str | null, search: str}`; search is literal text, capped at 256 UTF-8 bytes.

Contracts add `encode_cursor(binding: JsonObject, position: JsonObject) -> str` and `decode_cursor(token: str | None, binding: JsonObject) -> JsonObject | None`. Bind to workspace, scan, import, detector version, review revision, filters, and page kind. A server restart may invalidate process-signed cursors and request a fresh first page; it must not accept an unverifiable position.

- [ ] Write tests with more than 500 saved reviews and more than 100 findings. Assert Reviewed/Unreviewed totals reflect all review pages, not the first page; no complete counts appear during projection preparation. Change the review revision mid-build and mid-pagination and require duplicate_conflict plus a refresh, never skipped/repeated rows.
- [ ] Test ordering by strength descending, latest invoice date descending with missing dates last, then finding key; literal vendor/reference search including percent, underscore, quotes, and non-ASCII text must not become SQL or wildcard injection. Assert source and rule mismatches, forged cursors, and an unrelated finding key cannot expose members.
- [ ] Run the projection suite and verify red. Stream reviews into a temporary SQLite projection joined on evidence key at a pinned revision, checking revision before and after completion. Use bounded pagination and cooperative preparation so projection work also respects five-second steps. Cache only complete projections by workspace/scan/reviewRevision. Generate signed opaque cursors bound to that identity, filters, and ordering.
- [ ] Implement byte-bounded pages of at most 100 findings or 100 members. Resolve current evidence from Task 2 without a source-wide re-download for each detail. Confirm counts, total, import ID, rule version, scan ID, and review revision in each page. Unsaved or unavailable review data must not default to unreviewed.
- [ ] Rerun tests with an oversized source warning and a group containing 10,000 members; assert bounded pages and complete eventual membership. Commit as `feat: page duplicate findings with consistent shared review filters`.

## Task 6 Authorized lifecycle and component service integration

**Files:** Create `duplicates/operations.py`, `tests/test_ap_duplicates_operations.py`, and `tests/test_ap_duplicates_service.py`. Modify `app/ap_shared/models.py`, `service.py`, `protocol.py`, and `repository.py` only at action dispatch, safe errors, and bootstrap capability points.

**Interfaces:** `create_duplicate_operations(base_repository, bill_operations, config, clock, revalidate) -> DuplicateOperations`; `DuplicateOperations.handle(action, payload, request_id, authorization) -> JsonObject`. Registry `DuplicateScanRegistry(root=None, monotonic=time.monotonic)` in operations.py supplies `claim(scan, authorization)`, `step(scan, authorization, authorize) -> ScanProgress`, `release(scan_id)`, and `close()`. Registry handles are process-local and never treated as durable checkpoints after loss.

Add these public version-1 component actions:

- `duplicate_ensure`: `{import_id, expected_import_version}` -> ScanProgress or explicit no-source status.
- `duplicate_status`: `{scan_id}` -> ScanProgress, advancing projection preparation within the five-second budget when the artifact is ready but its current review projection is not.
- `duplicate_step`: `{scan_id, generation, expected_checkpoint, restart: bool}` -> ScanProgress.
- `duplicate_findings_page`: `{scan_id, filters, cursor: str | null, limit: int}` -> FindingPage.
- `duplicate_members_page`: `{scan_id, finding_key, cursor: str | null, limit: int}` -> member page.
- `duplicate_review_save`: `{scan_id, import_id, expected_import_version, finding_key, expected_review_version, decision, initials, note}` -> `{review: Review, reviewRevision: int}`.

- [ ] Write end-to-end service tests through dispatch_request for access expiry, rotation, cross-workspace IDs, malformed booleans and integers, forged keys, unknown fields, stale source, and unauthorized artifact paths. Start with a current verified import and no statements; assert ensure/steps produce a complete scan without invoking statement matching.
- [ ] Test scan recovery: lost step acknowledgement replays once; process-local loss returns restart_required and rebuilds under a new generation; a second session cannot steal an unexpired lease; one workspace/two process scans are enforced; newer import publication supersedes old work. Scan failure after a successful BILL activation must not mark that BILL import unsaved or erase provider state.
- [ ] Run the operations/service suites and verify red. Implement the state coordinator over Tasks 2–5 with current-source checks and authorization before and after long reads. Register DuplicateError safe messages in protocol.py and add detector actions separately from BILL_ACTIONS. Bootstrap advertises `duplicateBills: 1` only when `duplicate_schema_version == 1`; missing schema disables only this feature.
- [ ] Tie artifact readiness to a verified result manifest and atomic publication. Keep reviewed/unreviewed counts null until projection preparation completes. duplicate_status may advance this derived read preparation without changing the immutable scan checkpoint. Review saves load server-side finding evidence, derive the fingerprint themselves, validate initials with existing normalization, and transact using the immutable request identity. After saving, invalidate the affected projection and return its new revision. Server requests drive bounded work, not an unbounded background thread.
- [ ] Run the new suites plus existing shared access, service, protocol, snapshot operations, and schema suites. Assert no detector operations call save_revision, complete_revision, BILL write APIs, or QuickBooks APIs. Commit as `feat: coordinate authenticated recoverable duplicate scans`.

## Task 7 Automatic frontend scan controller without blocking app readiness

**Files:** Create `app/ap_statements/frontend/duplicate-bills.mjs` and `tests/ap_statements_duplicates_controller.test.mjs`. Modify `shared-workspace.mjs` at successful load/adopt/dispose hooks; modify `app.mjs` at startup and BILL update scheduling hooks.

**Interfaces:** `createDuplicateBills(client, {onChange, schedule, cancelSchedule})` returns `{state, adoptSource({importId, importVersion, capability}), setBusy(busy), load({filters, more}), open(key), loadMembers({more}), save({decision, initials, note, expectedVersion}), retry(), dispose()}`. Default scheduling uses timers between requests, not a tight promise loop. State stores current source, progress, projection readiness, pages, selection, reviewRevision, and detector-specific error/retry; it must not reuse shared statement saveState.

- [ ] Write mock-client tests holding a duplicate step unresolved while normal workspace load completes. Assert shared readiness is true, existing comparison counts remain valid, and a detector failure does not populate the global Not saved banner for a successfully acknowledged BILL update. No capability means no detector requests; no current import means a clear no-data state without calling ensure with null identifiers.
- [ ] Test automatic start for an existing source on first load, acknowledged weekly adoption, identical source reuse, and restart after reopening. Use a manual scheduler and assert at most one step request is outstanding. When upload/save/comparison work marks the controller busy, it schedules no new duplicate step; the already-sent step is allowed to finish within its bounded budget, not cancelled as though it could undo server work.
- [ ] Run `node --test --test-isolation=none tests/ap_statements_duplicates_controller.test.mjs` and verify red. Implement generation/source tokens, visible pending counts, detector-local errors, retries retaining request IDs, and invalidation on changed import/review revision. Once state is ready, poll duplicate_status until projectionReady instead of sending more scan steps. Do not await scan completion as part of shared.load or provider adoption. Duplicate scheduling yields after each reply so ordinary client work can enter the existing serialized bridge queue.
- [ ] Add disposal and stale-response assertions: pagehide, lock, source A-to-B-to-A with differing import versions, and a delayed old list response clear or preserve state appropriately without rendering old financial evidence. Controller disposal does not dispose the shared client owned by the workspace. Assert saved decisions remain server-backed and are not written into localStorage or statement resolutions.
- [ ] Run the controller suite and all existing `tests/ap_statements*.test.mjs`; verify no startup-loading or statement-confirmation regressions. Commit as `feat: scan BILL updates automatically without blocking statement checks`.

## Task 8 Duplicate bills list and dedicated review detail

**Files:** Create `app/ap_statements/frontend/duplicate-bills-ui.mjs` and `tests/ap_statements_duplicates_ui.test.mjs`. Modify `app.mjs` only for view routing and delegated events and `styles.css` for scoped duplicate-view classes.

**Interfaces:** `duplicateSidebarHTML(state, {active}) -> string`; `duplicateViewHTML(state) -> string`; `createDuplicateReviewDrafts()` returns `{get(key), update(key, changes), acknowledge(key, review), hasUnsaved(key), clear()}`. UI receives escaped display values and plain controller state; drafts remain separate from DOM rerenders and server-acknowledged Review objects.

- [ ] Write rendered/DOM tests asserting a distinct Duplicate bills sidebar tab; unreviewed badge only after complete current counts; loading/error/limit states never claim zero duplicates; exact clean copy is No possible duplicates found by these rules. Assert red/amber/green indicators have text and icons, reviewed labels retain original timestamps, and missing currency/source ambiguity remain visible.
- [ ] Test whole-row and keyboard activation into a dedicated detail view, Back restoring filters/scroll/focus, source fields shown side by side, optional note, required initials, explicit save acknowledgement, concurrent save conflict retaining the draft, and reopening a prior review. A progress update and a search/filter change must not silently discard a note; preserve the draft or ask before abandoning it.
- [ ] Run the UI suite and verify red. Implement the scoped list/detail renderer with default Unreviewed, Reviewed/All filters, classification filter, literal vendor/reference search, result pagination, and grouped member pagination. Expose only server-supported manual review actions; never add delete, pay, credit, or automatic correction controls. Show reported payment data as reported, not verified.
- [ ] Wire app events to the controller and drafts. On access expiry or pagehide, clear drafts, evidence, timers, and selection; status rerenders preserve focus and dirty text while access is valid. Use New York date/time display consistent with the app, accessible form labels and focus states, and responsive single-column detail layout on narrow viewports. Do not imply a bill-only finding has a statement PDF.
- [ ] Run the UI/controller and full frontend suites, then `node app/ap_statements/build.mjs`. Inspect synthetic browser states using the computer-use skill: pending scan, exact-pattern ambiguity, suffix suggestion, amount difference, completed review, failed save, source replacement, and narrow viewport. Save a screenshot of the final list and detail; do not enter real financial data into a new destination. Commit as `feat: add duplicate bill review workspace`.

## Task 9 Scale validation and rollout handoff

**Files:** Create `tests/test_ap_duplicates_scale.py`, `tests/fixtures/ap_shared/duplicate_scale_check.py`, and `docs/ap-duplicate-bill-detector-rollout.md`. Extend detector tests with cross-layer regressions exposed by the backtest; product fixes remain narrowly scoped to their owning modules.

**Interfaces:** The scale helper CLI accepts `--records 223425` or `--records 500000` and emits only a sanitized JSON report `{recordCount, findingCount, peakRssIncreaseBytes, maxRecordsPerStep, maxProbesPerStep, expandedBytes, compressedBytes, elapsedSeconds}`. Optional `--source PATH` reads a local export through the existing parser/index without modifying it; keep record-level candidate examples out of committed fixtures and logs.

- [ ] Write scale unittest assertions for both specified counts in fresh processes: source record coverage equals input count; maxRecordsPerStep <= 5000; maxProbesPerStep <= 10000; peakRssIncreaseBytes < 268435456; expandedBytes <= 536870912; compressedBytes <= 33554432. Assert completing a repeated-source scan produces the same finding keys without duplicate review events. Use a resource-bounded timeout justified by measured fixture timing; do not silently skip the maximum-size case in the release check.
- [ ] Run these tests and verify any new assertion's red before the owning minimal implementation. Include pathological equal-amount and ambiguous-source buckets, multi-page reviews, missing dates/currencies, legitimate Adventure suffix bills marked Not a duplicate, weekly payment-field changes, and simultaneous snapshot/duplicate storage reservations.
- [ ] Run full verification on the final tree: `python -X utf8 -m unittest discover -s tests -v`; `node --test --test-isolation=none tests/ap_statements*.test.mjs`; `node app/ap_statements/build.mjs`; `git diff --check`. Confirm actual exit status and failed-test counts. A single known opt-in integration skip is not a substitute for running detector schema and synthetic lifecycle tests.
- [ ] Read-only backtest the locally available user export if still present, reporting source size/counts, rule counts, representative candidates, and likely false positives to the user without claiming confirmed duplicates. Do not tune approved thresholds silently. Document migration order, capability gating, private artifact MIME/size needs, reservations, two-session checks, restart recovery, scan-on-existing-import, and disabling the UI without dropping stored evidence.
- [ ] Commit tests and rollout notes as `test: validate duplicate detector scale and weekly review continuity`. Obtain the selected execution method's final whole-branch review, address findings with verified tests, and use the finishing skill for the integration decision. No merge, push, live schema application, account upgrade, or production enablement occurs without the applicable user authority.

## Coverage and handoff

Rules and normalization map to Task 1; complete sources, grouping, and bounded candidate generation to Task 2; atomic leases/reviews/quotas to Task 3; storage integrity and cleanup boundaries to Task 4; complete reviewed filtering and evidence pages to Task 5; authorization, publication, recovery, and capabilities to Task 6; automatic scheduling and source replacement to Task 7; review UX to Task 8; large-source and cross-layer acceptance plus rollout to Task 9.

Implementation must not start before the user reviews this plan and selects an execution method. Native execution is recommended because the nine tasks share contracts, source identities, and lifecycle interfaces; one implementer can maintain that continuity with less repeated context. It still requires a fresh whole-branch reviewer before integration. Subagent-driven execution adds a fresh implementer and reviewer per task at higher context cost.
