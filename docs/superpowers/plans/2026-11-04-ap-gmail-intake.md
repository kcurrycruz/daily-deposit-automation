# AP Gmail Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. The owner previously selected native execution; preserve it. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import PDFs from the configured Gmail label every five minutes, scan and compare them outside Streamlit, and present durable unconfirmed drafts or actionable intake issues in AP Statements.

**Architecture:** A private scheduled checker records attachment receipts and a transactional dispatch outbox in Supabase. Cloud Tasks invokes one private PDF processor, protected by a workspace-wide database lease and per-job fencing; a credential-free Chromium child reuses the existing JavaScript scanner. Preliminary comparisons use shared matching code and a machine-authorized read facade; human review and existing history remain authoritative.

**Tech Stack:** Existing Python/Supabase/PostgreSQL and browser ES modules; Node/Playwright/Chromium; isolated worker Python dependencies; Cloud Run, Cloud Scheduler, Cloud Tasks, Secret Manager and Gmail read-only OAuth. Pin compatible dependency/browser/image versions during Task 5 and Task 11, with checked-in lockfiles; do not add worker dependencies to Streamlit's root requirements.

**Spec:** [Approved design](../specs/2026-11-04-ap-gmail-intake-design.md).

## Global Constraints

- "Cloud Scheduler invokes a private **mail intake service** every five minutes."
- "Set queue concurrency to one and processor concurrency/maximum instances to one, plus both a workspace-wide processor-slot lease and per-job fencing generations."
- "Initial processor budget: two vCPUs, 4 GiB memory, one document per request, ten minutes per document, existing effective 20 MiB file/100-page limits, and a background raster cap of 20 million pixels per page."
- "Three real processing attempts per generation is the proposed cap"; duplicate delivery without a claim does not consume one.
- "Intake is budgeted to about one minute of work per request and checkpoints for the next poll."
- "Use OAuth with `gmail.readonly` and identity scopes, offline access, and owner sign-in."
- "Source files and review history must remain intact." No automatic deletion, confirmation, initials, completion, BILL writes, vendor email or fake interactive authorization.
- "Persist discovered work before advancing a history page checkpoint." History IDs are opaque strings; receipt identity includes workspace, account, message and MIME part path.
- "Store preliminary evidence separately from human review results and mark it clearly in the UI. It cannot satisfy completion or count as a reviewed item."
- "The supported source formats are legacy rows, snapshot-v2 and acknowledged working sets." Incomplete reads are errors, and excluded working-range rows remain Check archived data.
- "Refresh only email status/list changes"; preserve open PDFs, selected invoices and unsaved edits. Gmail received time, AP import time and statement date are distinct.
- Capability off/absent must preserve the existing app. Secrets and financial/email payloads never enter logs, task bodies, browser state, Git or test reports.
- Work in the existing `codex/ap-gmail-intake` worktree. Never edit synced `sources/`, old worktree private `artifacts/`, or saved financial datasets. Use synthetic fixtures.
- Cloud account consent, provisioning, production SQL, merge/push and schedule activation require concrete rollout steps after local verification; this plan does not perform them.

## Review Focus

1. A PDF attached at the MIME root, inline base64url PDF, or a second PDF in an existing thread must each produce one receipt (Tasks 1, 3).
2. History expires halfway through a paginated poll while older mail is newly labeled: recover without silently importing unknown historical mail or losing eligible arrivals (Task 3).
3. Worker A loses its lease while worker B takes over, or pause/account generation changes mid-request: stale A must terminate and cannot publish (Tasks 2, 8).
4. A person edits/finishes a statement or changes mapping/BILL range during OCR: preserve their revision and recompare saved extraction only where eligible (Tasks 6, 7, 8).
5. Malformed PDF dimensions or a forged receipt path/cursor/HTML filename must not exhaust the worker, reveal another workspace, or remount the viewer (Tasks 5, 9, 10).

## File map and shared contracts

Keep the connector/coordinator in `app/ap_mail/`, AP interactive controls in `app/ap_shared/mail/`, browser adapters in `workers/ap_mail/`, and schema in additive dated migrations. This is one integrated plan because discovery, leases, publication and UI all share the same receipt protocol; do not ship one as an independently activated subsystem.

- `app/ap_mail/contracts.py`: immutable config, source/claim pins, strict DTO validation, safe error codes and deterministic identities.
- `app/ap_mail/repository.py`: fixed-workspace Supabase mail RPC/storage adapter, no interactive authorization.
- `app/ap_mail/gmail.py`, `sync.py`, `dispatch.py`: HTTP Gmail adapter, checkpointed inventory, task outbox recovery.
- `app/ap_mail/extraction.py`, `sources.py`, `publication.py`, `processor.py`: child supervision, read-only BILL facade, duplicate/draft publication and coordinator.
- `app/ap_shared/mail/service.py`: human-authorized list/control/preview operations. Existing service owns session checks.
- `workers/ap_mail/browser.mjs`, `page.mjs`, `page.html`, `domain.mjs`: local Chromium extraction and pure shared comparison/duplicate calculations; never use the interactive app bundle as a worker.
- `workers/ap_mail/http.py`, `authorize.py`, `Dockerfile`, package/dependency lockfiles: IAM-only endpoints and local owner OAuth setup.
- `app/ap_statements/frontend/mail-imports.mjs`, `mail-imports-ui.mjs`: isolated controller/DOM section; integration in existing app/workspace modules.
- `supabase/migrations/202611040001_ap_mail_intake.sql`: queue/connection/control schema and capability. `202611040002_ap_mail_publication.sql`: atomic publication and narrow publication rights.
- `tests/test_ap_mail_*.py`, `tests/ap_statements_mail*.test.mjs`, `tests/fixtures/ap_mail/`: synthetic unit, schema, browser, integration, burst and recovery fixtures.
- `deploy/ap_mail/`: reviewed infrastructure configuration and Windows-friendly dry-run/setup/recovery tools. `docs/ap-gmail-intake-setup.md`: owner runbook.

Contract names below are authoritative; implementation may split internals without changing these interfaces:

- `MailConfig`: backend URL/secret reference, fixed workspace and private bucket, Gmail connection ID, runtime role, limits; no AP password. Secret values excluded from repr.
- `SourcePin`: `import_id`, `import_version`, `source_digest`, `working_set_id`, `working_version`, `protection_epoch`, `working_digest`, `mapping_digest`, `mapping_versions`, `rule_version`; nullable source fields only for Waiting for BILL data.
- `Claim`: `job_id`, `receipt_id`, `connection_generation`, `dispatch_generation`, `lease_generation`, `slot_generation`, `lease_until`, `mode` (extract/recompare); server-issued values only.
- `ReceiptKey`: workspace/account/message/part_path. `attachment_parts(message: dict) -> list[AttachmentPart]` yields bounded filename/MIME/declared size and attachment ID or inline bytes, never email body text.
- `ExtractedDocument`: existing `validate_statement` shape, `confirmed=False`, deterministic document/row UUIDs, source hash and parser build stored alongside it. No new fields smuggled into existing strict DTOs.
- `MailEvidence`: validated preliminary rows plus SourcePin/parser version, extraction digest and created time; separate table/response key from revision `results` and `resolutions`.
- UI statuses: `queued`, `scanning`, `awaiting_review`, `needs_attention`, `already_imported`, `skipped`; additional reason codes distinguish waiting source, similarity, auth, quota and stale source. No success status for unreadable/zero-row documents.
- Queue RPC operations: `claim`, `heartbeat`, `record_original`, `save_extraction`, `needs_attention`, `finish`, `requeue`, `reconcile`. Every attempt mutation requires all Claim generations and database time checks. Publication uses its own RPC from Task 7.
- Human actions: `mail_status`, `mail_receipts_page`, `mail_pause`, `mail_retry`, `mail_import_history`, `mail_resolve_similar`, `mail_original_preview`; client may pass only validated IDs, cursors, bounded import options and expected versions, never account/storage/credential targets.

### Task 1: Strict mail contracts, MIME parsing and identities

**Files:** Create `app/ap_mail/{__init__,contracts,gmail}.py`; test `tests/test_ap_mail_contracts.py`, `tests/test_ap_mail_gmail.py`; fixtures `tests/fixtures/ap_mail/messages.py`.

**Interfaces:** Consume existing UUID/statement/record validators. Produce MailConfig, SourcePin, Claim, ReceiptKey, `attachment_parts(message)`, `receipt_id(key) -> str`, `normalize_extraction(doc, receipt_id, sha256) -> dict`, and `GmailClient.profile/labels/message/history/messages/attachment` adapter methods returning validated provider DTOs. Inject transport/token provider; do not log raw provider exceptions.

- [ ] **Step 1: Write failing tests.** `test_same_receipt_stable_across_delivery_and_thread_change`, `test_root_inline_and_nested_pdf_parts`, `test_non_pdf_and_mime_bombs`, `test_opaque_history_id`, `test_secret_redaction_and_fixed_workspace` assert: stable receipt IDs; root path `0` and indexed child paths remain distinct; two same-thread messages differ; depth > 20 or > 200 MIME parts becomes attention; invalid base64url/declared > 20 MiB rejected; huge string history IDs unchanged; config repr contains no token/password. Normalize preserves reference/cent/page values and makes `confirmed=False` with stable row IDs.
- [ ] **Step 2: Run** `python -m unittest discover -s tests -p test_ap_mail_contracts.py -v` and equivalent Gmail test file; expect missing-module/function failures before implementation.
- [ ] **Step 3: Implement** the interfaces and bounded Google response adapter. Pin account identity using authenticated user identity, label ID rather than label name; reject wrong identity, malformed/missing profile data and mutation requests. Normalize error codes for 401/403/404/429/transient server failures without copying payload text.
- [ ] **Step 4: Rerun both files**; all pass including forward-compatible MIME metadata handling and fixture redaction checks.
- [ ] **Step 5: Commit** only Task 1 files with message `feat(ap): define Gmail intake identities and read-only adapter`.

### Task 2: Durable receipts, outbox, leases and human controls schema

**Files:** Create migration `202611040001_ap_mail_intake.sql`, `app/ap_mail/repository.py`, `tests/test_ap_mail_schema.py`, `tests/test_ap_mail_repository.py`, `tests/fixtures/ap_mail/schema_checks.mjs`, `store_double.py`; modify repository bootstrap capability detection only.

**Interfaces:** `MailRepository(config, client)` implements `connection()`, `inventory_commit(expected_cursor, messages, receipts, next_cursor)`, `mutate(operation, payload, request_id)`, `outbox_page(cursor, limit)`, `status()`, `receipts_page(filters, cursor, limit)`, `private_original(receipt_id)`. SQL service-role-only `ap_mail_mutate(operation, workspace, request_id, payload_hash, data)` and read RPCs use fixed workspace, idempotent request ledger and strict operation payloads. All tables have RLS, denied anon/authenticated access, immutable receipt uniqueness and no user-controlled SQL identifiers.

- [ ] **Step 1: Write failing behavior tests.** `test_atomic_cursor_receipt_outbox`, `test_one_workspace_slot_and_stale_fence`, `test_claim_budget_and_expiry`, `test_pause_generation_and_control_replay`, `test_acl_and_cross_workspace` assert: rollback leaves cursor unchanged; duplicate receipt yields one job/outbox; concurrent jobs cannot both claim slot; heartbeat uses database time; stale slot/job generations cannot write; duplicate task delivery consumes no attempt; third failed claim exhausts budget; pause blocks new claims; retry creates one new dispatch generation; old connection jobs do not attach to a new account; all cross-workspace/unauthorized calls denied. No schema capability before install; after install `mailIntake=1`.
- [ ] **Step 2: Run** `python -m unittest discover -s tests -p test_ap_mail_schema.py -v` and repository file; expect absent migration/module failure.
- [ ] **Step 3: Implement** connection/message/receipt/job/attempt/outbox/preliminary tables plus global slot table, indexes and capability version. Lease interval 60 seconds, renew every 15 seconds; reject writes after lease expiry and require generation matches even when a lease is renewed. Keep immutable original/extraction references and append-only attempt facts; add no financial retention cleanup. Reconcile at most 100 outbox/jobs per call with keyset cursor.
- [ ] **Step 4: Run** both test files and existing `test_ap_shared_repository.py`; execute real SQL functions in PGlite via schema harness. Test PostgreSQL-specific concurrency separately in Task 12, not by declaring PGlite a concurrent deployment test.
- [ ] **Step 5: Commit** Task 2 files with message `feat(ap): persist mail intake queue and fenced processor leases`.

### Task 3: Checkpointed baseline, incremental sync and historical recovery

**Files:** Create `app/ap_mail/sync.py`, `tests/test_ap_mail_sync.py`, `tests/fixtures/ap_mail/history.py`.

**Interfaces:** `MailSync(gmail, repository, clock, monotonic).poll(connection_id, budget_seconds=60) -> PollSummary`; `begin_baseline(mode='new_only', history_bounds=None)`; `PollSummary` contains counts, safe status and next-work flag only. Use Task 2 inventory transaction; cursor stores phase, history anchor, page token, pending message IDs and current within-page progress.

- [ ] **Step 1: Write failing tests.** `test_baseline_history_bridge`, `test_checkpoint_after_each_discovered_page`, `test_history_expiry_reconcile_and_old_unknown`, `test_historical_import_separate_cursor`, `test_label_removed_or_message_deleted`, `test_thousand_message_budget_resume` assert: anchor captured before baseline; new-only marks baseline metadata without importing old PDFs; newly added label eligible despite old received date; failure/budget expiry resumes uncommitted message work; history 404 triggers bounded reconcile; unknown old messages require explicit import choice; new receives import; live cursor never reset by historical work; removed/deleted mail never deletes copied AP data.
- [ ] **Step 2: Run** `python -m unittest discover -s tests -p test_ap_mail_sync.py -v`; expect missing implementation.
- [ ] **Step 3: Implement** baseline/live/recovery/historical phases with opaque cursors and version-guarded page commits. Re-fetch individual message label membership before inventory. Preserve lightweight message metadata only, deduplicate change events within a page, and stop safely at the monotonic one-minute deadline. Count/status only after a page checkpoint is durable; bound historical request to explicit received-date interval and count cap (maximum 1,000 messages/request, resumable).
- [ ] **Step 4: Rerun tests** including root/inline/multiple attachment fixtures from Task 1. No Gmail request changes read flags or labels.
- [ ] **Step 5: Commit** with message `feat(ap): synchronize labeled Gmail PDFs with durable cursors`.

### Task 4: Reliable dispatch and lost-delivery reconciliation

**Files:** Create `app/ap_mail/dispatch.py`, `tests/test_ap_mail_dispatch.py`.

**Interfaces:** `TaskDispatcher(repository, tasks_client, config).drain(limit=100) -> DispatchSummary`; `.reconcile(limit=100) -> DispatchSummary`. Task name is a deterministic hash of fixed workspace/job/dispatch generation; JSON body contains job ID and dispatch generation only. Target URL and OIDC service account/audience come only from server configuration.

- [ ] **Step 1: Write failing tests.** `test_enqueue_ack_lost`, `test_outbox_commit_precedes_task`, `test_task_missing_lease_expired_repair`, `test_backoff_and_pause` assert: retry after successful creation/timeout accepts AlreadyExists without duplicate job; unknown create outcome never discards outbox; 404 task plus expired/nonexistent lease produces one recoverable dispatch generation; active lease is not replaced; quota failure applies bounded delay; paused connection dispatch cannot make a new claim.
- [ ] **Step 2: Run** `python -m unittest discover -s tests -p test_ap_mail_dispatch.py -v`; expect missing module failure.
- [ ] **Step 3: Implement** TaskDispatcher with bounded retries, deterministic deduplication, generation guards and safe request logging. Verify task name/generation matches pending work before acknowledging it. Retained task names never force resetting receipt history; database generation remains the authority.
- [ ] **Step 4: Rerun tests** with timeout-before-send, timeout-after-create, duplicate delivery and process-restart fault injection.
- [ ] **Step 5: Commit** with message `feat(ap): dispatch and recover queued statement scans`.

### Task 5: Isolated headless extraction using the existing scanner

**Files:** Create `workers/ap_mail/{package.json,package-lock.json,browser.mjs,page.mjs,page.html}`, `app/ap_mail/extraction.py`, `tests/test_ap_mail_extraction.py`, `tests/ap_statements_mail_extraction.test.mjs`, synthetic PDF fixtures/generator under `tests/fixtures/ap_mail/`; modify `frontend/extraction.mjs` only to accept explicit bounded rendering options.

**Interfaces:** Preserve `extractPDF(file, onProgress)` defaults; add optional third options object with `maxRasterPixels` applied to every OCR/retry canvas. `extract_private_pdf(path, filename, timeout_seconds=600, heartbeat) -> ExtractedDocument` owns child lifecycle; child exchanges bounded JSON over stdin/stdout, no inherited credential environment. `browser.mjs` serves allowlisted assets on `127.0.0.1` ephemeral port, allows only its own origin/blob workers, runs Chromium with sandbox enabled and closes all child resources.

- [ ] **Step 1: Write failing tests.** `test_extractor_parity_digital_scan_dotmatrix_credit`, `test_twenty_mib_hundred_pages_and_raster_cap`, `test_no_external_requests_or_secrets`, `test_timeout_heartbeat_loss_and_zero_rows` assert: same synthetic document gives identical normalized references/cents/pages/source text as interactive scanner; > 20 MiB or > 100 pages becomes attention; every retry canvas <= 20,000,000 pixels; malicious dimensions, encryption and malformed PDF fail boundedly; browser fetch outside allowlist blocked; inherited secret sentinel absent; lost heartbeat kills process; zero usable rows is never clean success.
- [ ] **Step 2: Run** Python/Node new extraction test files; expect missing adapter/unsupported raster option failure. Generate only synthetic fixtures; never upload real backtest PDFs.
- [ ] **Step 3: Implement** adapter and limits. Resolve and pin Playwright/browser versions compatible with Node 24, bundled PDF.js 5.4.624/Tesseract 6.0.1 and Linux sandbox; lock dependency graph. Use private temp directory, tight permissions and cleanup on every exit; bounded progress messages expose stage/page counts only, not filename/text/rows. Clamp initial/retry/dot-matrix raster creation before allocation, preserving normal-size OCR behavior.
- [ ] **Step 4: Rerun** new tests plus `ap_statements_scan.test.mjs`, `ap_statements_source_highlight.test.mjs`, `ap_statements_core.test.mjs`; run Linux image smoke test in Task 11 because Windows-only browser success is insufficient.
- [ ] **Step 5: Commit** with message `feat(ap): run shared PDF extraction in an isolated worker`.

### Task 6: Preliminary matching and machine-authorized source reads

**Files:** Modify `frontend/core.mjs`; create `workers/ap_mail/domain.mjs`, `app/ap_mail/sources.py`, `app/ap_shared/bills/reads.py`; refactor read-only branches in existing bill/working operations and `working/queries.py`; create `tests/ap_statements_mail_comparison.test.mjs`, `tests/test_ap_mail_sources.py`, `tests/test_ap_bill_reads.py`.

**Interfaces:** `preliminaryReconcile(statement, provider, mappings={}) -> rows` shares the internal matching calculation with `reconcile`; skips only the human-confirmation requirement, retaining confidence/duplicate/source guards. `BillReadAPI(repository, authorize, caches)` exposes `pin() -> SourcePin`, `vendors_page(pin, cursor)`, `candidates_page(pin, query, cursor)`, `archived_references_page(pin, references, cursor)`, `assert_current(pin)`. Human adapters retain `_check`; machine facade uses fixed workspace/claim validation callbacks and never creates Authorization. `MailSources.prepare(doc, claim) -> {provider, mappings, pin}` drains complete validated vendor/candidate pages using the existing comparison query rules; `assert_current(pin, claim)` revalidates source and mappings.

- [ ] **Step 1: Write failing tests.** `test_preliminary_does_not_confirm_or_resolve`, `test_preview_parity_all_existing_rules`, `test_rows_snapshot_working_parity`, `test_incomplete_page_corrupt_archive_and_stale_pin`, `test_source_cache_reuse_and_bounded_eviction` assert: `reconcile` on unconfirmed input still yields extraction; preliminary differs only by that gate and carries explicit preliminary metadata outside saved results; Adventure suffix/amount discrepancy, credit, vendor ambiguity, currency/source warnings and range exclusion match current behavior; truncated cursor pages/corrupt hashes never produce Missing; any import/version/range/protection/mapping change invalidates pin; only one prepared source/working pair retained, reused across attachments. Authorization callback runs before/after reads and cache access.
- [ ] **Step 2: Run** new Python/Node files; expect absent entrypoint/read API failures.
- [ ] **Step 3: Implement** shared pure matching helper and read-only query factoring without changing write operations or accepting fake sessions. Reuse SnapshotIndex, archive validation and WorkingCache queries; build rows-v1 via existing validated readers. Directory and candidate pagination counts/digests must complete; source unavailable saves Waiting for BILL data. Seven-day freshness flag uses actual saved import upload time, independent of as-of dates. Domain adapter also exports `assessIncoming(doc, candidates, mappings)` delegating to existing `assessStatement`.
- [ ] **Step 4: Run** new tests plus existing matching/Adventure/comparison-source tests and Python bill operations/working queries/archive tests. Prove human auth remains enforced and machine surface has no import activation/completion/mapping mutation methods.
- [ ] **Step 5: Commit** with message `feat(ap): calculate preliminary matches with pinned read-only BILL sources`.

### Task 7: Atomic duplicate linking and human-safe draft publication

**Files:** Create `app/ap_mail/publication.py`, `supabase/migrations/202611040002_ap_mail_publication.sql`, `tests/test_ap_mail_publication.py`, `tests/fixtures/ap_mail/publication_checks.mjs`; extend mail repository/schema tests.

**Interfaces:** `MailPublication(repository, domain).assess(extracted, claim, pin) -> Assessment` loads paginated current candidate heads and saved mappings, including completed/archived originals. `.publish(extracted, assessment, evidence, claim, pin) -> PublicationResult`; service-role-only `ap_mail_publish(workspace, request_id, payload_hash, data)` checks Claim, source/mapping pins and candidate-head revisions in one transaction. `PublicationResult` gives receipt status, statement ID/version or similarity reason, no browser credential.

- [ ] **Step 1: Write failing tests.** `test_byte_duplicate_completed_and_archived`, `test_semantic_duplicate_and_overlap`, `test_similarity_requires_human_choice`, `test_publish_replay_after_lost_response`, `test_human_head_and_source_race` assert: repeated bytes/semantic match links only; incoming distinct original retained; overlap adds whole statement with new/repeated counts; similarity publishes no new statement; concurrent identical receipts yield one draft; replay identical payload returns same publication; changed payload/request rejected; any human touch, confirmation, completion, archive/reopen or incompatible head leaves revision unchanged; stale pins/candidate heads force reassessment. Draft resolutions/results remain empty; preliminary evidence is separate.
- [ ] **Step 2: Run** publication/schema tests; expect absent function/module failures.
- [ ] **Step 3: Implement** deterministic statement/row identities, original ownership/hash validation and publication transaction. Record automation-owned revision ID/digest; only that unchanged, unconfirmed revision may be updated. Duplicate candidate collection must include revision/version proof and an inventory/version guard preventing a concurrent new candidate from bypassing assessment. Existing `save_revision`/complete authorization stays intact. Recompare updates preliminary table only where document/head remains untouched, not revision review history.
- [ ] **Step 4: Run** new checks plus `test_ap_shared_schema.py`, `test_ap_rereview.py`, existing statement duplicate/shared-workspace tests. Verify old revision rows and completion-event counts unchanged by automated duplicate linking.
- [ ] **Step 5: Commit** with message `feat(ap): publish scanned drafts without overwriting human review`.

### Task 8: Processor orchestration, private originals and stale-source recompare

**Files:** Create `app/ap_mail/processor.py`, `tests/test_ap_mail_processor.py`; extend sync stale-evidence inventory and repository bounded recompare query.

**Interfaces:** `MailProcessor(repository, gmail, extractor, sources, publication, clock).run(job_id, dispatch_generation) -> ProcessReply` returns ack/retry disposition with safe code. Claim precedes attachment I/O; `record_original` precedes extraction. `MailSync` queues at most 50 stale-source untouched drafts per poll using a keyset cursor and Task 2 outbox. Recompare mode reuses persisted extraction, not Gmail download/OCR.

- [ ] **Step 1: Write failing tests.** `test_full_pipeline_and_waiting_bill`, `test_private_copy_hash_and_budget`, `test_timeout_slot_takeover`, `test_pause_and_connection_change`, `test_source_update_recompare_no_ocr`, `test_retry_cap_classification` assert: one copied original/draft after repeated deliveries; bytes stream bounded before allocation/hash; hash collision/path mismatch cannot overwrite; storage full leaves actionable receipt; no credentials in extraction child; heartbeat failure stops publication; old connection generation cannot publish into new connection; source update reuses extraction and only untouched drafts; deterministic invalid PDF does not spin; transient errors stop after three real claims; no abandoned Scanning state after reconciliation.
- [ ] **Step 2: Run** `python -m unittest discover -s tests -p test_ap_mail_processor.py -v`; expect missing coordinator.
- [ ] **Step 3: Implement** original copy and state machine with 60-second renewable fenced leases, 15-second heartbeat, 600-second processing deadline and bounded download/child/candidate budgets. Use existing workspace `/pdf/<sha256>.pdf` convention with verified existing-object reuse; never delete another receipt's original. Persist extraction before source work. On pin drift enqueue recompare against saved extraction; finish/attention writes require the current global slot and job fence. Pause stops new claims but safely finishing the already active job is allowed; revoked/wrong account fails visibly.
- [ ] **Step 4: Rerun** processor, dispatch and sync tests with each boundary failure (copy, parse, candidate read, assessment, commit acknowledgement) and assert idempotent recovery.
- [ ] **Step 5: Commit** with message `feat(ap): coordinate resilient automatic statement scans`.

### Task 9: Authenticated mail controls and private previews

**Files:** Create `app/ap_shared/mail/{__init__,service}.py`, `tests/test_ap_mail_controls.py`; modify `app/ap_shared/{models,service,protocol,repository}.py` and relevant contract tests.

**Interfaces:** `MailService(repository, config, clock, check).handle(action, payload, request_id, authorization)`. Existing `ApService.handle` dispatches only validated MAIL_ACTIONS after `_check`; new typed errors map to safe messages. Status/list include capability, connection generation/version, last successful poll, counts, receipt reason/times, linked statement ID and preliminary evidence availability. Preview receives receipt ID only and returns a <= 300-second signed URL after fixed-workspace/hash/path validation.

- [ ] **Step 1: Write failing tests.** `test_controls_locked_expired_and_mid_request`, `test_pause_retry_history_bounds_and_replay`, `test_similarity_choice_stale_head`, `test_receipt_preview_ownership_path_and_host`, `test_no_secrets_in_responses` assert every action requires current human session before/after I/O; absent capability returns unavailable safely; pause/retry/history choices use expected version/idempotency; similarity import resolves through fresh assessment, not stale candidate; completed/archived existing link remains read-only; forged workspace/path/host rejected; allowed object hash and private URL only. New-only remains default unless explicit historical options supplied.
- [ ] **Step 2: Run** controls tests and existing model/protocol tests; expect unsupported actions/no MailService failures.
- [ ] **Step 3: Implement** list/status/pause/resume/retry/history/similarity/preview operations using dedicated mail transactions. Similarity actions record the human choice with expected receipt/candidate versions and enqueue reassessment; the human endpoint never fabricates a worker Claim. Apply existing envelope/text/UUID limits; 50-row lists and opaque validated cursors. Never return OAuth tokens, secret references, raw provider errors, full email bodies or machine configuration. History request verifies bounded count/date range; replay does not create extra work.
- [ ] **Step 4: Run** new tests plus shared access/gate/protocol/service tests. Verify mail capability absence leaves old app bootstrap and manual upload functional.
- [ ] **Step 5: Commit** with message `feat(ap): expose authorized email intake controls and previews`.

### Task 10: Stable Email imports UI and preliminary evidence presentation

**Files:** Create `app/ap_statements/frontend/{mail-imports,mail-imports-ui}.mjs`, `tests/ap_statements_mail_controller.test.mjs`, `tests/ap_statements_mail_ui.test.mjs`, `tests/fixtures/ap_mail/ui.browser.mjs`; modify `app/ap_statements/frontend/{app,shared-workspace}.mjs` and `app/ap_statements/frontend/styles.css`.

**Interfaces:** `createMailImports(client, {onChange, hasUnsaved, visible, clock})` exposes `load`, `pause`, `retry`, `importHistory`, `resolveSimilar`, `previewOriginal`, `dispose`; `mailImportsHTML(snapshot)` renders escaped isolated section. `patchMailImports(root, snapshot)` updates only that region. Normal vendor lists refresh by explicit incremental adoption of new server documents without replacing dirty/current details; `mail_status` polling must never call whole-workspace `load()` or `renderDrawer()`.

- [ ] **Step 1: Write failing tests.** `test_status_poll_preserves_pdf_and_dirty_dom`, `test_imported_draft_normal_list_visibility`, `test_stale_responses_and_dispose`, `test_preliminary_never_resolves_or_completes`, `test_accessible_controls_xss_and_dates` assert: selected invoice/canvas DOM identity, scroll, focused note input/value unchanged across ten polls; new receipt links new draft into list; stale connection/reply ignored; pagehide/lock stops timer and clears sensitive data; preliminary found/amount discrepancies clearly labeled Awaiting review and don't change reviewed totals/completion; subject/filename safely escaped; NY received/imported timestamps separately labeled, statement date unaffected. Capability absent means no network poll or empty-state flicker.
- [ ] **Step 2: Run** new Node tests; expect missing controller/UI. Add real browser DOM assertions with synthetic client, not just source-string checks.
- [ ] **Step 3: Implement** compact section on Statements plus detailed list view, selected label/status/last successful check, queued/scanning/attention counts and original/statement links. Visible-only polling every 30 seconds with one in-flight request and backoff; pause text explains an active scan may finish. Historical import shows scope/count confirmation; similarity offers View existing / Import separately. Keep operational configuration out of review flow; show waiting/stale BILL/credits limitations in context. Existing invoice details remain human decisions.
- [ ] **Step 4: Run** new browser tests and existing background updates, preview updates, navigation, shared UI/workspace and re-review tests; verify viewport/keyboard behavior and no viewer remount while typing.
- [ ] **Step 5: Commit** with message `feat(ap): display email imports without disrupting statement review`.

### Task 11: Private runtime, owner authorization and deployment tooling

**Files:** Create `workers/ap_mail/{http,authorize}.py`, `workers/ap_mail/{requirements.in,requirements.lock,Dockerfile,.dockerignore}`, `deploy/ap_mail/{main.tf,variables.tf,outputs.tf,.terraform.lock.hcl,plan.ps1,README.md}`, `docs/ap-gmail-intake-setup.md`, `tests/test_ap_mail_runtime.py`, `tests/test_ap_mail_authorize.py`, `tests/test_ap_mail_deploy.py`; adjust CI path filters for worker/deploy changes.

**Interfaces:** IAM-only HTTP `/poll`, `/dispatch-reconcile` on checker; `/process` on processor. Runtime role disables unrelated endpoints. `authorize.py` local owner flow uses installed-app OAuth, PKCE/state, loopback redirect, `openid email gmail.readonly`, refresh token and direct Secret Manager write; outputs only safe identity/label/secret version identifiers. Deployment inputs explicitly require project, region, AP workspace/bucket, service/secret identities and connection ID; no default production target.

- [ ] **Step 1: Write failing tests.** `test_wrong_oidc_caller_audience_role`, `test_bounded_body_and_log_redaction`, `test_oauth_state_identity_and_missing_refresh`, `test_no_token_disk_or_stdout`, `test_deploy_private_concurrency_and_dry_run` assert: wrong IAM principal/audience/role denied; unsigned or forged task headers grant nothing; task body <= 4 KiB IDs only; request exceptions redact payloads; OAuth wrong state/account aborts, no refresh token means not activated; Secret Manager failure does not dump token; cloud service/private invoker bindings explicit; scheduler `*/5 * * * *`, queue concurrency=1, processor max instances/concurrency=1, 600-second timeout/2 vCPU/4 GiB; plan.ps1 is read-only and never auto applies or echoes secrets.
- [ ] **Step 2: Run** new runtime/OAuth/deploy tests; expect missing infrastructure/runtime files.
- [ ] **Step 3: Implement** isolated locked runtime and IAM token validation in addition to platform private ingress/invocation controls. Pin audited dependency/browser/image versions and record notices. Build single code image with checker/processor role selection; browser child strips credential env and blocks remote egress. Terraform creates separate scheduler, task invoker and runtime principals, narrow Secret Manager access, private Cloud Run services, queue and scheduler initially paused. Keep passwords out of config; service-role DB key server-only with fixed workspace, no generic RPC endpoint. Supply PowerShell setup/recovery commands, no secret command arguments or automatic production apply.
- [ ] **Step 4: Verify** locked dependency install, container build and Linux headless PDF/OCR smoke; run tests. Run `terraform fmt -check`/`validate` when Terraform available, otherwise document missing prerequisite rather than claim validated. No cloud apply/consent here. Runbook covers OAuth External/Testing seven-day refresh expiration, verification/publishing decision, cost/resource measurements, private bucket limits, migration inventory/recovery copy and capability rollback.
- [ ] **Step 5: Commit** with message `feat(ap): package private Gmail intake services and owner setup tools`.

### Task 12: Whole-system burst/recovery verification and release handoff

**Files:** Create `tests/test_ap_mail_burst.py`, `test_ap_mail_integration.py`, `tests/fixtures/ap_mail/burst_check.py`, `docs/superpowers/verification/2026-11-04-ap-gmail-intake.md`; finalize setup/recovery runbook and plan checkbox status; modify `.github/workflows/validate.yml` to run new local checks without secrets and use a separate opt-in integration job.

**Interfaces:** Integration requires `AP_MAIL_SYNTHETIC_INTEGRATION=1` plus explicit test project/workspace allowlist and refuses known production project `uhwpnbntjsopuilouize`. It exercises real SQL/storage/IAM/Tasks/Gmail with owner-authorized synthetic fixtures, never personal/financial backtest files. Offline harness has injected Gmail, Tasks and clock, actual parser fixtures, real SQL harness and crash boundaries.

- [ ] **Step 1: Write failing tests.** `test_hundred_pdf_burst_no_loss`, `test_crash_every_boundary`, `test_real_concurrent_claim_and_publish` assert 100 distinct PDFs plus retransmissions produce 100 receipts and correct unique/new/overlap/attention outcomes; <= 1 valid workspace claim; cursor always reconciles; max three real failed attempts/generation; lost task/SQL ack/expired lease recover; human edits/history survive. PostgreSQL integration uses competing connections for fencing; missing authorized environment explicitly skips with deployment blocker, never reports live acceptance.
- [ ] **Step 2: Run** the new harness before adding recovery glue; identify genuine missing behavior, not artificial failing expectations. Repair only failures demonstrated by these tests and rerun affected earlier task checks.
- [ ] **Step 3: Execute final local verification:** `python -m compileall -q app workers streamlit_app.py`; `python -m unittest discover -s tests -v`; `node --test --test-isolation=none tests/ap_statements*.test.mjs`; locked frontend build; Linux container smoke; schema harness; 100-PDF synthetic burst. Measure warm/cold scan throughput, peak memory/cache size, queue latency, and UI/backend latency under burst versus idle. Do not repeat unaffected checks after a passing final suite unless code changes.
- [ ] **Step 4: Record** actual commands/counts/results, baseline comparison and skipped/environment-blocked checks. Inventory prior pending working-set/duplicate migrations plus new mail migrations in exact order. Request one fresh independent whole-branch review per native execution workflow after tests pass; fix meaningful findings and rerun relevant checks. No claim that Gmail is connected or live if consent/integration remain pending.
- [ ] **Step 5: Commit** verification/runbook updates. Present concrete rollout package: target project/region/billing/cost expectations, migration recovery definitions/counts, OAuth verification/publishing status, private services/IAM, synthetic cloud round-trip result and one owner-selected sample. Obtain needed external-action authorization at that stage; preserve earlier approvals only for their original actions. New-only vs explicit historical import is selected at activation. Leave scheduler paused until authorized end-to-end sample passes. Merge/push only when requested.

## Self-review and execution status

All approved design sections map to tasks: runtime/limits (5, 8, 11), Gmail/account/OAuth (1, 3, 11), durable work/fencing/outbox (2, 4, 8), statement duplicates and immutable human work (7), preliminary source parity/refresh (6, 8), stable UI and controls (9, 10), machine boundaries/rollout/recovery (11, 12). Each Review Focus condition has explicit assertions in its owning tasks. Interfaces use the names defined above; numeric resource/retry defaults remain the approved proposals to verify before activation.

Status: plan written and self-reviewed; awaiting owner review. No implementation tasks started. Native execution preference preserved. The existing baseline is 46 passing core/statement-duplicate/shared-workspace Node tests, not mail feature verification.
