# Large BILL Exports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept the normal full weekly Bills CSV, replace current comparison data without duplicate current entries, and preserve prior statement work.

**Architecture:** Compress the CSV in a browser worker, build a validated SQLite search snapshot on the Python server, and keep immutable compressed artifacts in private Supabase Storage. Postgres stores metadata, concurrency state, and the active pointer rather than another full set of invoice rows each week. Retrieve complete statement-specific candidate sets instead of downloading all historical invoices into the browser.

**Tech Stack:** Existing Streamlit, Supabase, vanilla JavaScript modules and Web Workers; Python 3.12 standard-library csv, gzip, sqlite3, hashlib, and tempfile; existing unittest, Node test runner, and PGlite. No additional hosted service or product dependency.

**Spec:** `docs/superpowers/specs/2026-10-19-large-bill-exports-design.md`, approved for planning October 19, 2026.

## Global Constraints

- Each successful export becomes the current comparison dataset. It replaces the previous active dataset rather than appending another week's copies of the same invoices.
- Preserve existing PDFs, corrections, notes, stated reviewer initials, completed reviews, and historical evidence. No BILL or QuickBooks writes.
- New snapshot limits: 256 MiB original CSV; 32 MiB compressed CSV; 750,000 source rows; 500,000 normalized records; 32 MiB compressed index; 512 MiB expanded index; 128 columns; 1 MiB per CSV field. Reject violations without truncation or activation.
- Keep PDF uploads and their 20 MiB limit unchanged. Keep legacy rows-v1 imports readable and their 100,000-record limit unchanged.
- Retain 256 KiB transport chunks and the existing 1 MiB component envelope. Page comparison records by at most 500 records and the serialized envelope size, whichever is smaller.
- Build steps consume at most 5,000 source rows or 500 invoice groups, with a five-second cooperative time budget. Oversized groups use resumable row iteration.
- Bound simultaneous builds to one per workspace through an expiring server-owned database lease and two per server process. Expire abandoned temporary builds after one hour.
- Enforce a 512 MiB total expanded-index cache budget, reference-counted readers, least-recently-used eviction, and a one-hour idle expiry.
- Reserve staging plus final storage; configured bucket budget defaults to 900,000,000 bytes. Warn at 80%. Do not authorize charges or delete historical data automatically.
- Hash decompressed original bytes for source identity; identical files reuse an import. A previously saved but inactive source needs confirmation before reactivation.
- Preserve current native consolidation and invoice-first matching rules. Equal amount is only a same-vendor suggestion, never a deduplication key or automatic reference substitution.
- Secrets stay server-side. Authorize every operation and cache access, reject arbitrary paths and SQL, and retain immutable-history and optimistic-concurrency checks.
- Development uses synthetic fixtures. The real CSV is read-only local validation input, never a committed fixture or an automatic live upload.
- No implementation until this plan is reviewed and an execution method is selected. No live migration, financial-data replacement, merge, or push is authorized by planning approval alone.

## Review Focus

1. Renaming or recompressing an older export must not create another import or silently restore stale data. Test in Tasks 1 and 5.
2. BOMs, embedded CSV newlines, Unicode whitespace, and reference suffixes must produce the same keys and cents as the JavaScript importer. Test in Task 2.
3. A tab closing, worker failing, or server restarting must not activate partial data or let a late response overwrite newer state. Test in Tasks 5, 6, and 8.
4. Quota failure after some private objects have been saved must preserve the prior active source and all statements. Test in Tasks 4 and 5.
5. A legacy client activating another import during a new build must advance the same version counter and make stale activation fail. Test in Tasks 1 and 8.

## Workspace and verification commands

Use the existing linked worktree `portal-source/.worktrees/deploy-dd-v2`, branch `codex/ap-shared-workspace`. Check branch, tracked changes, and `AGENTS.md` before execution. Do not touch synced `sources/`, ignored QA directories, or unrelated changes. Start from design commit `fac7807` or its descendant containing this plan.

Run commands from the worktree. In the examples below, `python` means the verified project interpreter; on this workstation it is `C:/Users/karlcruz/AppData/Local/Temp/ap-tut-1019/Scripts/python.exe`. If unavailable, resolve a suitable existing runtime before installing anything. Set `PYTHONUTF8=1` for Windows tests. Existing focused commands:

```powershell
python -X utf8 -m unittest discover -s tests -p 'test_ap_shared*.py' -v
node --test --test-isolation=none tests/ap_statements_native_import.test.mjs tests/ap_statements_shared_workspace.test.mjs
```

Every task follows red, green, regression verification, and a narrowly staged commit. A red run must fail because the new assertion is unmet, not because the test environment or import path is broken. Do not claim a future behavior passes based only on this plan.

## File structure and shared contracts

Create `app/ap_shared/bills/` with these focused modules:

| File | Responsibility |
| --- | --- |
| `contracts.py` | Limits, manifest validation, bounded query/cursor contracts, safe error codes. |
| `normalization.py` | Exact parity with JavaScript cents, dates, header, vendor, and reference keys. |
| `parser.py` | Stream CSV rows into disk-backed staging and validate individual source rows. |
| `index.py` | Consolidate staged groups, index normalized records, page vendors/warnings/candidates. |
| `archive.py` | Streaming hashes/gzip, verified index cache, private temporary files. |
| `repository.py` | Narrow Supabase snapshot RPCs, object I/O, quota reservation and exact staging cleanup. |
| `builds.py` | Bounded local build generations, checkpoints, expiry, restart, and resource limits. |
| `operations.py` | Authorized BILL action dispatch coordinating these modules. |

New browser modules live beside the existing AP frontend modules: `bill-upload-worker.mjs`, `bill-upload.mjs`, and `comparison-source.mjs`. Keep `core.mjs` matching decisions authoritative; add complete-source guards rather than duplicating the matching algorithm on the server.

All new component actions use the existing version-1 envelope. Their payloads reject unknown fields. Add these actions: `bill_upload_begin`, `bill_upload_chunk`, `bill_upload_finish`, `bill_prepare_step`, `bill_activate`, `bill_vendors_page`, `bill_candidates_page`, and `bill_warnings_page`. New bootstrap capabilities advertise `billSnapshots: 2`; absence disables the new import path with a deployment message, not a partial fallback.

The common `SnapshotManifest` is a validated JSON object with `format: 'snapshot-v2'`, `parserVersion: 'bill-csv-v1'`, `indexVersion: 1`, `originalHash`, `originalBytes`, `originalArchive: {key,hash,bytes}`, `indexArchive: {key,hash,bytes,expandedHash,expandedBytes}`, `recordCount`, `sourceRowCount`, `collapsedRowCount`, `excludedRowCount`, `warningCount`, and `vendorDigest`. All money in indexed records remains integer cents; nullable warning-bearing values follow `validate_record`.

Use JSON-shaped TypedDicts in `contracts.py`, not runtime-only objects across boundaries. Define `IndexArchiveInfo = {hash: str, bytes: int, expandedHash: str, expandedBytes: int}` for a generated index; storage adds the server-generated `key` before manifest validation. Define `BuildProgress` with the exact fields and states in Task 5; checkpoint is an integer incremented after each committed step within one generation, not a raw file offset. The query shape is `{importId, references: [{invoiceKey,kind}], amounts: [{vendorKey,kind,amount}]}`; count references and amounts together against the 100-key limit. The service receives an opaque, validated cursor and translates it to the internal ordinal; the browser cannot supply a file path or database offset as authority. All shortened Python filenames below are relative to `app/ap_shared/bills/`, and shortened browser filenames are relative to `app/ap_statements/frontend/`.

## Task 1: Snapshot contracts and atomic database lifecycle

**Files:** Create `app/ap_shared/bills/__init__.py`, `contracts.py`, `supabase/migrations/202610190001_ap_bill_snapshots.sql`, `tests/test_ap_bill_contracts.py`, `tests/fixtures/ap_shared/snapshot_schema_checks.mjs`, `tests/test_ap_bill_schema.py`. Modify `app/ap_shared/models.py` action allowlist and `tests/test_ap_shared_schema.py` migration loader where needed.

**Interfaces:** `validate_manifest(value: object) -> JsonObject`; `validate_query(value: object) -> JsonObject`; `SnapshotError(code: str)` with safe allowlisted codes. New RPCs `ap_bill_job_begin`, `ap_bill_job_checkpoint`, `ap_bill_job_abandon`, `ap_bill_snapshot_stage`, `ap_bill_snapshot_activate`, and `ap_bill_quota_reserve` use existing `(p_workspace,p_request_id,p_payload_hash,p_data)` arguments and `ap_requests` idempotency. Define their payload field allowlists in `contracts.py` and SQL together.

RPC data contracts: job begin `{job_id,session_nonce,filename,compressed_size,as_of,lease_until}` captures the current import version server-side; checkpoint `{job_id,session_nonce,generation,expected_checkpoint,next_checkpoint,state,counts}` requires monotonic progress; abandon `{job_id,session_nonce,generation}` releases only its lease/reservation. Stage `{job_id,session_nonce,generation,manifest,metadata}` validates hashes/counts and reuses the workspace/original-hash import identity. Activate `{job_id,session_nonce,import_id,expected_import_version,confirm_restore}` validates the prepared source and increments the workspace version only on an actual change. Reserve `{job_id,session_nonce,bucket,requested_bytes,budget_bytes}` uses server configuration and counts current private bucket usage plus outstanding reservations under a bucket-level lock. Do not trust a client-supplied lease time, bucket or budget; these RPC fields come from Python.

- [ ] Write contract boundary tests asserting the exact global limits, manifest hash/path requirements, record-count limits by format, maximum query keys of 100, and rejection of unknown fields, booleans as integers, unsafe cents, and forged cursors.
- [ ] Write a separate PGlite fixture that loads the original migration and the new migration, creates synthetic legacy and snapshot imports, and asserts: inactive duplicate hashes are reused, one active pointer, partial activation rejected, expected-version conflict, immutable ready manifests, no invoice rows inserted for snapshot-v2, one build lease per workspace, quota reservations, and anon/authenticated role denial. Preserve the original schema fixture's tests rather than replacing them with new-only assertions.
- [ ] Include direct assertions `assert.equal(activeInvoiceCountAfterSecondImport, 1)`, `assert.equal(oldCompletionEventCount, unchangedCompletionEventCount)`, and `assert.equal(duplicateImportId, originalImportId)`. Mock Supabase's storage metadata table inside the synthetic PGlite fixture so reservation tests exercise actual known-object bytes, not a hard-coded zero.
- [ ] Run `python -m unittest discover -s tests -p 'test_ap_bill_contracts.py' -v` and the corresponding schema test; verify the new assertions fail on missing contracts/RPCs.
- [ ] Implement limits and contracts. Add `storage_format` and `snapshot_manifest` to imports with legacy defaults; add `import_version` to workspaces and `ap_bill_jobs` with lease, session, generation, checkpoint, expected version, and reserved bytes. Use a BEFORE UPDATE trigger to advance `import_version` when `active_import_id` changes through either new or legacy RPCs. New RPCs lock the workspace, check request hashes and lease ownership, and never alter immutable ready imports or completed history. Missing/expired lease acquisition is transactional. Storage reservations count known final objects, upload staging, and other live reservations.
- [ ] Add `legacy_activation_advances_version_and_rejects_stale_snapshot`, `same_hash_reuses_source_but_old_source_requires_confirmation`, and `abandoned_job_cannot_activate`. Assert monotonic versions even after A-to-B-to-A activation.
- [ ] Run the two new Python suites plus `test_ap_shared_schema.py` and `test_ap_shared_models.py`; expect all assertions pass. Stage only Task 1 files and commit `feat: define atomic BILL snapshot contracts`.

## Task 2: Streaming CSV parser with exact native-import parity

**Files:** Create `normalization.py`, `parser.py`, `tests/test_ap_bill_parser.py`, `tests/fixtures/ap_shared/bill_exports.py`, and `tests/fixtures/ap_shared/bill_parser_oracle.mjs`.

**Interfaces:** `vendor_key(value: str) -> str`, `invoice_key(value: str) -> str`, `parse_cents(value: str) -> int | None`, `date_iso(value: str) -> str`, and `header_key(value: str) -> str`. `CsvStage(connection, csv_path: Path)` provides `read_step(max_rows=5000, deadline: float) -> {done,sourceRowCount,checkpoint}` and stages required raw bill fields, row numbers, validated records, issues, counts and orders in SQLite. It does not return a full row array.

- [ ] Add synthetic native and app-template exports covering every existing native-import test. The Node oracle reads synthetic CSV from stdin, runs `importBillSource`, and returns normalized records and summary. Compare Python staging values and subsequent normalization expectations against that oracle without logging real source data.
- [ ] Add `bom_crlf_and_quoted_newlines_keep_source_record_numbers`, `unicode_whitespace_and_suffix_keys_match_js`, `malformed_money_is_not_zero`, and `same_vendor_reference_different_dates_stays_distinct`. Source row numbers count parsed CSV records, matching the current importer rather than physical embedded newlines.
- [ ] Pin normalization assertions: `assert parse_cents('($138.00)') == -13800`, `assert parse_cents('1.234') is None`, `assert invoice_key(' 00 142-A ') == '00142-A'`, and `assert date_iso('02/30/26') == ''`.
- [ ] Run `python -m unittest discover -s tests -p 'test_ap_bill_parser.py' -v`; verify missing parser behavior fails.
- [ ] Implement CSV parsing with `utf-8-sig`, strict quoting, the exact column and field bounds, and bounded staged inserts. Port existing normalization semantics without stronger Unicode folding or approximate reference correction. Use integer/decimal-safe parsing, not binary-float arithmetic. Preserve all existing warning and exclusion categories. Close streams and rollback the current staging transaction on structural failure.
- [ ] Run the parser suite and `node --test --test-isolation=none tests/ap_statements_native_import.test.mjs`; expect parity, including missing amounts, negative lines, inactive rows, invalid dates and duplicate headers. Commit only Task 2 files as `feat: stream BILL CSV parsing with native parity`.

## Task 3: Indexed snapshot builder and complete candidate queries

**Files:** Create `index.py`, `tests/test_ap_bill_index.py`; extend the synthetic export helper and parser parity suite.

**Interfaces:** `SnapshotIndex(connection).consolidate_step(max_groups=500, deadline: float) -> {done,checkpoint}`; `.finish() -> {counts,vendorDigest}`; `.vendors_page(after: str | None, limit: int) -> JsonObject`; `.warnings_page(after: int, limit: int) -> JsonObject`; `.candidates_page(query: JsonObject, after: int, limit: int, max_bytes: int) -> JsonObject`. Every normalized record has a deterministic zero-based normalized ordinal; the service later exposes `<importId>:<ordinal>` IDs. Candidate query keys are `references: [{invoiceKey,kind}]` and `amounts: [{vendorKey,kind,amount}]`.

- [ ] Write `complete_line_group_collapses_once_without_summing_bill_totals`, `identical_single_line_bills_stay_ambiguous`, `oversized_group_resumes_without_splitting`, `invalid_group_retains_all_source_warnings`, `candidate_page_has_total_digest_and_complete_cursor`, and `candidate_page_respects_bytes_before_row_limit`. Include one reference shared by different vendors and several equal-amount same-vendor references.
- [ ] For a two-line bill whose lines are 10000 and 3800 cents but whose repeated bill total is 13800, assert `counts['recordCount'] == 1` and the stored amount is `13800`, never `27600`. For two independent single-line bills sharing vendor/reference/date, assert two candidate ordinals remain.
- [ ] Run `python -m unittest discover -s tests -p 'test_ap_bill_index.py' -v`; confirm the missing index behavior is red.
- [ ] Implement ordered disk-backed grouping with the current JavaScript consistency/completeness/sum predicates. Preserve group insertion order and within-group source order to make the oracle comparison deterministic. Large groups accumulate bounded state and a resumable checkpoint rather than a full in-memory list. Add parameterized reference/kind and vendor/kind/amount indexes. Include distinct vendors and all source warnings in the derived database.
- [ ] Page the union of matching record ordinals without duplicating a record returned by both a reference and amount key. Bind cursors to import/query digest and return `total`, `afterOrdinal`, `nextCursor`, `queryDigest`, and `records`. Reject a single record larger than the response budget explicitly; never return a shortened candidate as complete.
- [ ] Compare final synthetic records and summaries to the oracle from Task 2; run both parser and index suites. Commit `feat: build indexed BILL comparison snapshots`.

## Task 4: Verified archives, private cache, and narrow storage operations

**Files:** Create `archive.py`, `app/ap_shared/bills/repository.py`, `tests/test_ap_bill_archive.py`, `tests/test_ap_bill_storage.py`. Modify only the original `app/ap_shared/repository.py` object-key allowlist and delegation points required for new immutable artifacts.

**Interfaces:** `verify_csv_archive(source: BinaryIO, target: Path) -> {originalHash,originalBytes,archiveHash,archiveBytes}`; `IndexArchiveWriter(index_path,output_path).step(max_bytes,deadline) -> {done,artifact: IndexArchiveInfo | None}`; `SnapshotCache(repository,clock).acquire(workspace_id, import_id, manifest, authorization, authorize) -> context manager[sqlite3.Connection]`. The acquire call uses the current request's authorization callback; a shared cache must not capture the first user's session callback. `BillRepository(base_repository)` supplies `reserve(job_id, requested_bytes, request_id)`, `put_artifact(job_id, name, path, request_id)`, `read_artifact(manifest, name, target)`, `cleanup_acknowledged_chunks(job_id)`, and `rpc(operation, data, request_id)`. A new BILL job ID also identifies its upload staging prefix; existing PDF ap_uploads state is unchanged. Final paths are `<workspace>/bills/v2/<originalHash>/<archiveHash>.csv.gz` and `<workspace>/bills/v2/<originalHash>/<indexArchiveHash>.sqlite.gz`; hashes must agree on immutable retries. Including artifact hashes avoids overwriting different valid gzip encodings while source identity still uses the decompressed original hash.

- [ ] Test compressed and expanded size boundaries, corrupt/truncated gzip, invalid CSV encoding, distinct compressed bytes with one original hash, incorrect artifact digests, and rejection of caller-supplied SQLite. Verify strict output size even for a high compression-ratio input.
- [ ] Test cache authorization before access, two independently authorized sessions, hash/schema/integrity checks, extension disabling, readonly writes failing, active-reader pinning, LRU eviction and one-hour expiry. Assert no unbounded decompressed buffer and no object URL or credential returned to a browser. Index packing steps process at most 4 MiB of input and honor the cooperative deadline so packaging cannot bypass the bounded job protocol.
- [ ] Test `quota_failure_keeps_original_source_and_prior_objects`, immutable object retries, and exact acknowledged-staging cleanup. Reject workspace mismatches, altered chunk hashes, final artifact keys, and broad path prefixes as deletion targets. Run both new suites and verify red.
- [ ] Assert a staging-cleanup attempt against a final original returns denial and `storage.deleted_keys == []`; after valid cleanup, assert the deleted-key set equals exactly the acknowledged upload's staged-key set.
- [ ] Implement streaming I/O with owned private temporary directories and try/finally cleanup, filesystem-backed gzip, bounded SQLite cache configuration, and exact-key object methods. Stream object downloads to disk where the SDK permits; if the SDK returns compressed bytes, only that bounded archive may occupy memory. Parameterize cache clocks/limits and inject object doubles for tests.
- [ ] Run archive/storage plus existing shared repository tests. Commit `feat: store and cache private BILL snapshot artifacts`.

## Task 5: Recoverable server jobs and authenticated snapshot actions

**Files:** Create `builds.py`, `operations.py`, `tests/test_ap_bill_builds.py`, `tests/test_ap_bill_operations.py`. Modify `app/ap_shared/service.py`, `protocol.py`, `models.py`, and new schema contracts only where integration requires them.

**Interfaces:** `BillOperations(repository, config, clock, revalidate, builds, cache).handle(action, payload, request_id, authorization) -> JsonObject`. `BuildRegistry(root,clock,monotonic).step(job_id, generation, expected_checkpoint, authorization, authorize) -> BuildProgress` runs Task 2/3 work. The registry is process-scoped but authorization callbacks are request-scoped; use a per-job mutex, a process semaphore and locked SQLite access across Streamlit threads. `clock` supplies UTC lease times and `monotonic` supplies cooperative deadlines. Build progress has `state` (`reading`, `grouping`, `packaging`, `prepared`, or `restart_required`), `generation`, `checkpoint`, `sourceRowCount`, `recordCount`, and optional validated manifest/import ID. A lost generation restarts from the durable original, not an acknowledged but missing local offset.

`BuildRegistry.restart(job_id, expected_generation, authorization, authorize) -> BuildProgress` verifies the expected old generation and resets only local derived build state under a new server-generated UUID. The `bill_prepare_step` payload is `{job_id,generation,expected_checkpoint,restart}` with `restart` defaulting to false; true is sent only after the user accepts a restart prompt. A generation mismatch rejects a stale request, rather than restarting someone else's active build.

- [ ] Test the exact action sequence `bill_upload_begin` (filename, compressed size, optional snapshot date), `bill_upload_chunk` (job ID, index, base64), `bill_upload_finish` (job ID), repeated `bill_prepare_step` (job ID, generation, expected checkpoint), then `bill_activate` (job ID, confirmation flag). Finish computes the original hash; a duplicate returns `duplicate`, `alreadyCurrent`, and `confirmationRequired` without rebuilding or automatically activating old data. No caller supplies a manifest or normalized records to activate.
- [ ] Test chunk index 127, disordered/different chunk retries, duplicate clicks, response loss after activation, expired/revoked access, wrong session, process reset, stale generation, lease expiry, full storage mid-build, and two concurrent source replacements. Assert one source per hash, one active pointer, no ap_bill_records rows for the new format, and unchanged statement/revision/event counts.
- [ ] Record `prior = repo.active_import_id`; fail object storage during packaging and assert `repo.active_import_id == prior`. Replay the successful activation request ID and assert both its reply and completion-event count remain identical.
- [ ] Run both new test modules and verify red. Implement the job state machine, bounded checkpoints and per-process semaphore; use Task 1 transactions and Task 4 artifacts. Revalidate before and after each bounded step and immediately before private file operations or activation. Use the same mutation identity for the same retried operation, but a new generation for rebuilt local state. Do not register a successful build checkpoint until its local transaction commits.
- [ ] Add authenticated `bill_vendors_page`, `bill_candidates_page`, and `bill_warnings_page` dispatch. Validate import format, manifest and cursor; attach import ID/digest/counts. Legacy rows-v1 queries use the existing complete paginated reader to populate a temporary index and return existing import-scoped IDs, preserving the same candidate semantics. New bootstrap metadata includes capabilities and authoritative record counts without large warning strings.
- [ ] Return safe, stage-specific errors through a strict error-code map (`bill_limit`, `bill_quota`, `bill_restart`, `bill_conflict`, `bill_invalid_archive`, `bill_incomplete`), never interpolating CSV values or backend exception strings. Keep existing error handling unchanged for other actions. Run all new BILL tests plus existing shared service, protocol, access, schema and repository suites. Commit `feat: add recoverable authenticated BILL snapshot imports`.

## Task 6: Browser streaming compression and import orchestration

**Files:** Create frontend `bill-upload-worker.mjs`, `bill-upload.mjs`, `tests/ap_statements_bill_upload.test.mjs`. Modify `shared-client.mjs` only for new limits/capability helpers; leave the envelope and PDF path unchanged.

**Interfaces:** `prepareBillUpload(file, {onProgress,signal,workerFactory}) -> Promise<{blob,originalBytes}>`; `importBillSnapshot(client,file,{asOf,onProgress,signal,confirmRestore,confirmRestart}) -> Promise<{importId,metadata,duplicate,alreadyCurrent}>`. Both confirmation callbacks resolve to a boolean and default to false when omitted. Worker messages use operation ID, progress, result, and error; late or unknown operation IDs are ignored. Browser compression uses `File.stream()` piped through `CompressionStream('gzip')` in a module worker.

- [ ] Test with synthetic streams that reject `.text()` and `.arrayBuffer()` on the original file. Assert source size is checked before compression, gzip output is bounded, imported data is never parsed in the UI thread, abort terminates the worker, and unsupported workers/compression produce a compatibility message rather than a whole-file fallback.
- [ ] Test chunk ordering, source snapshot date, duplicate-current no-op, old-source confirmation cancel, build restart prompt, upload-step retries preserving identities, activation acknowledgement loss, and late worker completion after navigation. Run the Node module and verify red.
- [ ] Assert `assert.equal(originalFileTextCalls, 0)`, `assert.equal(originalFileArrayBufferCalls, 0)`, `assert.equal(activateCallsAfterCancel, 0)`, and identical request IDs for a transport retry of the same chunk.
- [ ] Implement the worker and serial orchestrator, keeping only the bounded compressed Blob and current encoded chunk in memory. Preserve request identities for acknowledged/retried steps; a restart requires an explicit new build generation. Re-use the current client timeout for bounded steps, not a multi-minute request. Do not invent a raw-file hash using non-streaming browser crypto; Python returns the verified original identity.
- [ ] Run the new suite plus existing shared client tests. Verify no change to PDF limits, no worker credentials, no external network dependency, and safe disposal. Commit `feat: stream large BILL exports through a browser worker`.

## Task 7: Complete candidate scopes without loading every invoice

**Files:** Create `comparison-source.mjs`, `tests/ap_statements_comparison_source.test.mjs`. Modify `shared-workspace.mjs`, `core.mjs`, `vendor-identity.mjs`, `simple-flow.mjs`, and corresponding existing tests.

**Interfaces:** `comparisonInputKey(doc,mappings)` exported by core returns a deterministic key for grouped references, original amounts, kinds, vendor, mappings and rule version. `createComparisonSource(client,{onChange})` provides `loadDirectory(importInfo)`, `ensure(doc,mappings)`, `invalidate(statementId)`, and `dispose()`. Provider state contains `importId`, `recordCount`, `vendorDirectory`, `directoryComplete`, and `scopes[statementId] = {inputKey,queryDigest,complete,records,error}`. Legacy standalone test providers with `records` keep working; shared v1/v2 imports use scopes.

- [ ] Write `metadata_count_is_not_candidate_count`, `bootstrap_never_downloads_all_snapshot_records`, `partial_vendor_directory_cannot_resolve_uniquely`, `last_candidate_page_must_arrive_before_unique_match`, `missing_page_is_unverified_not_missing`, and `reference_amount_conflict_keeps_exact_reference`. Compare scoped results with `reconcile` over a full synthetic provider for the same inputs.
- [ ] Add overlapping in-flight query tests: edit vendor/reference/amount while requests are pending, then deliver responses in reverse order. The newer scope must survive; changing mappings invalidates affected scopes. Empty or opening/payment-only statement queries complete without fabricating invoice matches. Run the new suite and verify red.
- [ ] Add `query_keys_above_100_are_batched_without_losing_candidates`: split 101 reference keys into two bounded queries, deduplicate the combined results by stable record ID, and mark the scope complete only after all their pages arrive. Assert `assert.equal(scope.complete, false)` while the last page is pending and `assert.equal(result.status, 'unverified')`, never `missing` or a unique match.
- [ ] Implement complete directory/candidate loading with pinned import ID, counts/digests, strict cursors and duplicate-ID detection. `reconcile` resolves vendors from the complete directory and fails closed for stale/incomplete scopes. `confirmVendor` validates directory membership rather than relying on a full records array; `billDataSummary` reads authoritative `recordCount` with standalone fallback.
- [ ] Integrate shared workspace loading with metadata plus directory; prefetch active statements' required candidates with at most two concurrent queries outside render functions. Saving and completing await the relevant scope and verify its input key has not changed. Keep historical `results` read-only and never recompute them. Expose explicit `refreshComparisons(statementId)` for an older editable draft, retaining notes and a prior saved revision while invalidating new-source decisions.
- [ ] Run new scope tests and existing native, vendor, evidence, shared workspace, simple-flow and history test suites. Replace obsolete full-dataset boot assertions with complete-scope assertions rather than removing completeness coverage. Commit `feat: query complete statement-specific BILL candidates`.

## Task 8: Integrate the simplified update UI and preserved review workflow

**Files:** Modify frontend `app.mjs`, `simple-flow-view.mjs`, `styles.css`, `app/ap_statements/build.mjs` only if module assets need packaging, `tests/ap_statements_shared_ui.test.mjs`, `tests/ap_statements_real_only.test.mjs`, and `tests/fixtures/ap_shared/streamlit_bridge_app.py`. Create `tests/ap_statements_bill_snapshot_ui.test.mjs`.

**Interfaces:** Existing file selection calls `importBillSnapshot` instead of `importBillSource(await file.text())`. Shared workspace adopts new metadata only after authoritative activation/readback. UI uses `refreshComparisons(statementId)` from Task 7 and reads candidate scopes through existing comparison helpers, not direct RPC calls inside render.

- [ ] Write UI tests for Preparing file, Uploading, Checking records, Saving, duplicate-current, explicit old-source confirmation, actionable restart, and failure keeping the old source label/count. Preserve the screenshot tutorial, selected statement, list scroll position, optional notes, initials validation, PDF progress and sidebar navigation.
- [ ] Test updating with an unsaved draft, a saved older draft, and a completed statement. Unsaved work requires save/cancel before update; a saved draft keeps corrections/notes and shows an explicit compare-with-current action; completed results remain frozen. Test a legacy client changing the active import while this tab prepares another update, and stale async responses after returning to programs.
- [ ] With a completed fixture, retain its serialized results before import; assert `assert.deepEqual(history.results, frozenResults)` afterward and `assert.equal(currentProvider.recordCount, 223425)`, even if the displayed statement has only two candidates.
- [ ] Run the new UI suite and verify red. Integrate the upload and comparison controllers, cancellation, disabled controls, sanitized messages, and count/warning details. Required success copy is `BILL data updated. Previous invoices were refreshed, not added again.` Do not show Saved on worker completion or before server activation. Missing server capability blocks only new-format import with a deployment message.
- [ ] Add synthetic fixture routes for successful large-snapshot metadata, duplicate-current, failed update, partial candidate loading, and historical review. Browser-check desktop and narrow viewports through the computer-use workflow, including page-bottom scrolling and keyboard focus. Build the actual component with `node app/ap_statements/build.mjs`; retain generated changes only when required by changed entrypoints.
- [ ] Run new/existing UI, guide, evidence and navigation suites plus the built-component tests. Commit `feat: integrate safe weekly BILL data replacement`.

## Task 9: Scale validation and deployment documentation

**Files:** Create `tests/test_ap_bill_large_export.py`, `tests/fixtures/ap_shared/bill_scale_check.py`, and `docs/ap-bill-snapshot-rollout.md`. Modify `docs/ap-shared-workspace-setup.md`, `docs/ap-shared-workspace-validation.md`, and integration fixture configuration where needed.

**Interfaces:** `bill_scale_check.py --synthetic-records 223425` prints sanitized counts, peak process memory, archive/index sizes, timing and hash parity. `--source <local CSV path>` is a separately invoked, local-only mode and never writes to Supabase. Do not make a user's filesystem path part of test discovery or a committed fixture.

- [ ] Write synthetic tests above 100,000 records and at 223,425 records. Assert bounded builder steps, final exact count, once-only active invoice entries after repeated full export, old/new/changed/omitted invoice behavior, deep candidate pagination, archive round-trip hashes, and explicit rejection at each spec limit. Use a subprocess for memory measurement to distinguish builder RSS from the test runner.
- [ ] Assert `recordCount == 223425`, `activeRecordCountAfterRepeat == 223425`, `originalHash == decompressedArchiveHash`, and `peakRssIncreaseBytes < 256 * 1024 * 1024`. On Windows measure process working set with the standard-library ctypes process-memory API; on Unix normalize resource peak-RSS units before comparison.
- [ ] Run the new suite and verify red where integration behavior remains unmet. Resolve only failures in the approved scope, with focused regression tests. Require measured RSS increase below 256 MiB for the representative fixture and no main-thread whole-file parser. A failed scale target stops rollout; do not silently raise limits or weaken assertions.
- [ ] Run local-only validation against the supplied real CSV. Verify 284,365 source rows, 223,425 normalized records, 59,592 collapsed rows, and 1,348 exclusions, plus hashes, query samples, memory and actual artifact sizes. Do not log vendor/reference/amount rows or upload the file. If parity differs, investigate before classifying the export as successfully supported.
- [ ] Document the additive migration order, version/capability compatibility, gzip MIME and 32 MiB bucket limit while keeping PDF's app limit 20 MiB, quota checks including existing files, private access verification, backup of database and object files, and exact acknowledged-staging cleanup. Legacy code must remain able to read its own imports, but rollback after a snapshot becomes active requires an approved compatible release or explicit source restoration, not pointing old full-reader code at v2.
- [ ] Run the complete suites and build, capture exit codes and totals, and inspect `git diff --check`:

```powershell
python -X utf8 -m unittest discover -s tests -q
$apNodeTests = (Get-ChildItem -LiteralPath tests -Filter 'ap_statements*.test.mjs').FullName
node --test --test-isolation=none $apNodeTests
node app/ap_statements/build.mjs
git diff --check
```

- [ ] Perform a fresh whole-branch code review after the complete test/build pass. Test synthetic data in an explicitly approved isolated Supabase test workspace, two sessions, a cold cache/server restart, upload interruption and final-page query failure. An unconfigured live integration test is a rollout blocker, not a deployment success. No production setup or real-data import in this step without separate authority.
- [ ] Commit the validation/documentation changes as `test: validate large BILL exports and document rollout`. Report measured limits and outstanding rollout actions. Do not merge/push or activate production merely because implementation tests pass.

## Plan review and execution handoff

This is one dependent subsystem change, not independent projects: the artifact contract feeds the builder, service, browser import, and comparison source. Keep the tasks sequential in the existing isolated worktree.

After the user reviews this plan, ask them to select native execution or subagent-driven execution. Native execution means implementing these tasks in this session, followed by a fresh whole-branch review; subagent-driven execution uses a fresh implementer and reviewer per task. Recommend native execution here because these modules share tightly coupled source-identity, paging and state contracts; the final independent review and strict failure tests remain mandatory. Do not spawn implementers before the method is selected.
