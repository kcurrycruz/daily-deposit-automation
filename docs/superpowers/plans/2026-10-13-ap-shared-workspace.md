# AP Shared Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist BILL imports, original statement PDFs, and completed AP review history in a password-protected shared Supabase workspace, with invoice-first matching and optional notes.

**Architecture:** The browser retains PDF extraction and matching presentation. Authorized Streamlit Python operations validate component requests and access Supabase records and private files; database transactions preserve immutable revisions and prevent overwrites. Completed reviews retain their import, mapping, and matching evidence instead of being recalculated when a newer export arrives.

**Tech Stack:** Existing Python Streamlit app, JavaScript ES modules, bundled PDF.js and Tesseract, Supabase Python SDK, Postgres migrations and transactional RPCs, private Supabase Storage, Python unittest, Node node:test, and browser acceptance checks.

**Spec:** [Approved design](../specs/2026-10-13-ap-shared-workspace-design.md), approved by the user October 13, 2026. Read both documents before execution.

## Global Constraints

- Reviewer initials are required when completing a statement; notes are optional.
- Initials are self-reported labels, not verified identities.
- The password value is never included in source code, this document, tests, logs, or Git history.
- Authorization is session-scoped, expires after eight hours, and has a visible Lock AP action that discards displayed records and ends access.
- Signed links expire after at most five minutes and must not appear in logs or history records.
- Shared state becomes authoritative after unlocking; browser storage is not used as an invisible fallback when Supabase is unavailable.
- Keep monetary values as integer cents and invoice numbers as text. Native BILL exports do not verify settlement, absent currency, outstanding balance, or QuickBooks sync.
- Only an explicit user action migrates existing browser-local records and files into shared storage.
- Keep Daily Deposits and Credit Cards unchanged. Never edit project `sources/` or commit actual financial files.
- Prepare an isolated worktree at execution time using the worktree skill. Do not push, provision a cloud project, run cloud migrations, or upload actual financial data merely because the plan is approved.
- Use synthetic credentials and fixtures in tests; production secrets are entered directly in Streamlit settings. Preserve the existing Python and Node dependency boundaries except for the server-only Supabase SDK.

## Review Focus

- An export exceeds the database's default page size: all records load, in stable order, with no false missing-invoice results. Pin in Task 4.
- A browser retries after a successful write whose acknowledgement was lost: no duplicate statement or completion event appears, and changed payloads cannot reuse that request ID. Pin in Tasks 4 and 5.
- A password rotates or expires while a PDF operation is in progress: later reads and writes are denied, the component locks, and nothing is silently published. Pin in Tasks 3 and 5.
- The PDF saves but extraction fails, or a same-named PDF has different bytes: the original remains available with an unconfirmed draft; filename alone never merges records. Pin in Tasks 4 and 6.
- A colleague saves while another user is editing, or a newer BILL import arrives: conflicting edits are rejected and completed evidence remains tied to the original import. Pin in Tasks 4 and 7.

## Execution conventions and file boundaries

Use `python -m unittest discover -s tests -p 'test_name.py' -v` for targeted Python tests. For Node tests use `node --test tests/exact_name.test.mjs`; for the full Node suite use PowerShell `$apTests = (Get-ChildItem tests -Filter 'ap_statements*.test.mjs').FullName; node --test $apTests`. Resolve installed Node and Python executables before execution if those commands are not on PATH. Do not install dependencies while only reviewing this plan.

New modules each have one responsibility: `app/ap_shared/models.py` validates shared payloads; `access.py` owns authorization; `repository.py` owns Supabase I/O; `service.py` coordinates transactions and file staging; `protocol.py` dispatches component actions. Browser `shared-client.mjs` owns requests, `shared-workspace.mjs` owns synchronization, and `history.mjs` owns previous-work presentation. Keep `app.mjs` as the existing screen coordinator rather than moving unrelated UI code.

Use JSON objects for serialized values and TypedDicts or dataclasses for Python boundaries. Request envelope: `{version: 1, request_id: UUID, action: string, payload: object}`. Response envelope: `{version: 1, request_id: UUID, ok: boolean, data: object|null, error: {code, message}|null}`. Only server-generated responses may report Saved or Completed. Navigation keeps its existing navigation-only message and return boolean.

Implementation limits are explicit and mirrored on server and client: PDF or CSV at most 20 MiB, at most 20 PDFs per upload selection, file chunks at most 256 KiB decoded, any JSON envelope at most 1 MiB encoded, record pages and import batches at most 500 records, one import at most 100,000 normalized records, and statement metadata at most 10,000 rows and 512 KiB of raw source text. Reject oversize work before a partial active import is created. Explain limits in the UI; never silently truncate records or source text. Use signed preview links with a 300-second lifetime and eight-hour authorization measured by server time.

## Task 1 Invoice-first matching and reviewable amount suggestions

**Files:** Modify `app/ap_statements/frontend/core.mjs:235-276`, `app/ap_statements/frontend/app.mjs:173-217`; create `tests/ap_statements_matching.test.mjs`; retain existing core, native import, audit, and scan tests.

**Interfaces:** Consume existing `reconcile(statement, provider, mappings = {})`, `vendorKey`, `invoiceKey`, `groupInvoices`, and `statuses`. Preserve the existing result fields and add `matchMethod: 'reference'|'amount'|null`; statuses `possible` and `vendor` have labels Possible match and Check vendor. Candidates must expose both vendor and reference. Existing exact same-vendor results retain their status and limitations.

Core assertions in `same_vendor_amount_fallback_requires_review`, using the stated Alpha fixture:

```javascript
const [result] = reconcile(statement, provider, {});
assert.equal(result.status, 'possible');
assert.equal(result.matchMethod, 'amount');
assert.deepEqual(result.candidates.map(bill => bill.invoiceNumber), ['00043']);
assert.equal(result.invoiceNumber, '00042');
```

- [ ] Write failing Node tests with synthetic vendor Alpha, reference `00042`, and amount 18400 cents. Assert a unique same-vendor reference uses `matchMethod === 'reference'`; an exact reference under another vendor yields `status === 'vendor'`, not matched. Assert duplicate references across vendors are not silently selected when the statement vendor is unresolved.
- [ ] Add `reference_amount_disagreement_does_not_trigger_fallback`: exact same-vendor `00042` at 18000 and another reference at 18400 returns `amount`, with only the exact-reference evidence. Add `same_vendor_amount_fallback_requires_review`: absent reference plus Alpha/18400 returns `possible` and `matchMethod === 'amount'`; a different-vendor equal amount is excluded. Two Alpha invoices at 18400 return `ambiguous` with both candidates.
- [ ] Add assertions for a credit versus invoice with the same reference, zero-padded references, null or invalid amounts, source warnings, low-confidence or unconfirmed rows, and native exports. Possible candidates never become automatic matches or correct the statement's reference. An unresolved vendor requires mapping before any amount fallback.
- [ ] Run `node --test tests/ap_statements_matching.test.mjs`; expect failures for the new statuses and fallback behavior. Implement the smallest changes to `reconcile` and status definitions. Keep exact reference failures visible rather than replacing them with suggestions.
- [ ] Update `candidateSummary` and `billEvidence` in `app.mjs` to show vendor, reference, original amount, and match method without calling amount-only evidence verified. Test these labels and the report's status and reason. Run the new test and all existing Node tests; expect zero failures.
- [ ] Commit only this tested matching change: `feat: suggest same-vendor amount candidates after invoice lookup`.

## Task 2 Shared data contract and private database schema

**Files:** Create `app/ap_shared/__init__.py`, `app/ap_shared/models.py`, `supabase/migrations/202610130001_ap_shared_workspace.sql`, `tests/test_ap_shared_models.py`, and `tests/test_ap_shared_schema.py`. Create synthetic SQL integration fixtures under `tests/fixtures/ap_shared/` only.

**Interfaces:** Produce `JsonObject`, `ApConfig`, `Authorization`, `SharedSnapshot`, `ApValidationError`, and the constants above. Produce `read_config(secrets: Mapping) -> ApConfig`, `validate_request(value: object) -> JsonObject`, `validate_provider(value: object) -> JsonObject`, `validate_statement(value: object) -> JsonObject`, `validate_resolution(value: object) -> JsonObject`, and `normalize_initials(value: str) -> str`.

`ApConfig` fields are `password`, `supabase_url`, `supabase_secret_key`, `workspace_id`, and `bucket`; credential fields are excluded from object representations. `Authorization` fields are `workspace_id`, `session_nonce`, `expires_at`, and `credential_fingerprint`. `SharedSnapshot` fields are `activeImport`, `mappings`, `statements`, and `nextCursor`; bootstrap includes metadata, not an unbounded full dataset. Financial document/record fields retain the current JavaScript names; server routing fields use `statement_id`, `import_id`, `upload_id`, and `expected_version` consistently in both languages.

Core assertions in `test_initials_required_notes_optional`, with `valid_statement` a synthetic current-schema fixture:

```python
self.assertEqual(normalize_initials(' kc '), 'KC')
with self.assertRaises(ApValidationError):
    normalize_initials(' ')
self.assertEqual(validate_statement({**valid_statement, 'notes': ''})['notes'], '')
```

Configuration names under Streamlit Secrets `[ap]` are `password`, `supabase_url`, `supabase_secret_key`, `workspace_id`, and `bucket`. The bucket value for setup is `hwfc-ap-private`; `workspace_id` is one server-selected UUID. Reject missing values, non-HTTPS remote URLs, invalid UUIDs, and an empty password. Inject test configuration in tests instead of reading real secrets.

Tables in `public` are `ap_workspaces`, `ap_bill_imports`, `ap_bill_records`, `ap_statements`, `ap_statement_revisions`, `ap_completion_events`, `ap_vendor_mappings`, `ap_requests`, `ap_uploads`, and `ap_access_limits`. Every financial record belongs to a workspace. Revisions and completion events are immutable; requests have unique `(workspace_id, request_id)` plus a payload hash. Imports have status staging or ready, a unique file hash per workspace, and stable record ordinals. Statements have a unique PDF hash per workspace, archive state, and current revision. Enable RLS and revoke anonymous/authenticated access. RPC execution is granted only to `service_role`, never `PUBLIC`, `anon`, or `authenticated`; privileged routines set a fixed search path and validate workspace and version.

- [ ] Write failing unittest tests with assertions `normalize_initials(' kc ') == 'KC'`, blank initials rejected, more than ten letters rejected, and `validate_statement({...,'notes': ''})['notes'] == ''`. Reject boolean monetary values, floats, unsafe integers, unknown fields, arbitrary file paths, malformed request IDs, and original amounts represented as strings instead of integer cents.
- [ ] Write schema tests asserting each table's RLS, immutable-history constraints, request-ID uniqueness, import/PDF hash uniqueness, and restricted RPC grants. Add synthetic Postgres tests that anonymous roles cannot select records or execute routines and that stale revision updates fail.
- [ ] Run `python -m unittest discover -s tests -p 'test_ap_shared_models.py' -v` and the equivalent schema command; expect missing-module or schema failures. Implement strict allowlists, integer/date validation, and the schema.
- [ ] Define transactional RPCs `ap_activate_import`, `ap_save_revision`, `ap_complete_revision`, `ap_reopen_statement`, and `ap_save_mapping`. Each takes workspace ID, request ID, payload hash, validated operation data, and an expected version where it updates state. Return a stable response for an identical replay, reject a changed payload, and return `conflict` on stale versions. Activation checks exact staged record count before changing the active import. Completion checks confirmed extraction, initials, and decisions for unresolved comparisons; a notes value is never required. Add `ap_begin_access_attempt` and `ap_finish_access_attempt` with row locking so simultaneous sessions cannot bypass cooldown thresholds; these routines touch only the access-attempt store.
- [ ] Run model and schema tests. Run SQL behavior tests against a disposable, explicitly configured local Postgres/Supabase test database, not a production project. If none is available, record the missing integration evidence rather than treating textual schema checks as proof of SQL behavior.
- [ ] Commit `feat: define private AP storage schema and validated payloads`.

## Task 3 Server-side password gate and session lifecycle

**Files:** Create `app/ap_shared/access.py`, `tests/test_ap_shared_access.py`; modify `app/ap_statements_ui.py` and `tests/test_ap_statements_ui.py`. Extend the recording UI test double for forms, password input, and injected configuration.

**Interfaces:** Consume Task 2's `ApConfig` and `Authorization`. Produce `attempt_unlock(session: MutableMapping, submitted: str, config: ApConfig, limiter: AccessLimiter, now: datetime) -> bool`, `require_access(session: Mapping, config: ApConfig, now: datetime) -> Authorization`, and `lock_access(session: MutableMapping) -> None`. `AccessLimiter` is a protocol with `begin_attempt(session_nonce: str, now: datetime) -> str|None` and `finish_attempt(ticket: str, succeeded: bool, now: datetime) -> None`; its durable implementation is Task 4. Atomic reservation counts pending attempts against the thresholds; success releases its reservation and failure retains a counted attempt. Unfinished reservations expire after the five-minute window. A trusted server nonce, not a browser-supplied identity, keys per-session attempts.

Core assertions in `test_access_expires_at_eight_hours`, using a synthetic configured session unlocked at `now`:

```python
self.assertEqual(require_access(session, config, now + timedelta(seconds=28799)).workspace_id,
                 config.workspace_id)
with self.assertRaises(PermissionError):
    require_access(session, config, now + timedelta(seconds=28800))
```

- [ ] Write failing tests proving no financial component or repository read is called with missing configuration, a wrong password, or expired access. Use a synthetic password fixture. Assert access at 28,799 seconds and rejection at 28,800 seconds; changing the configured password or backend key invalidates the credential fingerprint. Fingerprints use a server-keyed HMAC and never store the submitted password.
- [ ] Test session cooldown after five failed attempts in five minutes and a global cooldown after 100 failures in five minutes; cooldown duration is five minutes. Both counters are server-side and survive creating a new browser session. A limiter outage fails closed. Do not treat these limits as protection against all distributed denial-of-service attacks.
- [ ] Test that the submitted widget value is cleared after checking, locking clears AP authorization and rendered financial state, and AP back navigation remains usable. Assert Daily Deposit state is untouched. Run `python -m unittest discover -s tests -p 'test_ap_shared_access.py' -v`; expect missing-module failures.
- [ ] Implement access checks with constant-time credential comparison, eight-hour expiry, configuration fingerprint validation, sanitized failure messages, and the gate before the component declaration. Inject a limiter and clock in tests. Until Task 4 is available, production access with unavailable durable limiting fails closed rather than silently using a weaker fallback.
- [ ] Update old UI tests that assumed an unguarded component; authorized tests explicitly inject valid access. Preserve assertions about stable mounting and Daily routing. Run access and AP renderer tests; expect zero failures.
- [ ] Commit `feat: guard AP workspace access on the server`.

## Task 4 Supabase repository and transactional shared operations

**Files:** Create `app/ap_shared/repository.py`, `app/ap_shared/service.py`, `tests/test_ap_shared_repository.py`, `tests/test_ap_shared_service.py`; modify `requirements.txt`. Create `tests/test_ap_shared_integration.py` for opt-in synthetic integration tests. Do not place a secret file in the repository.

**Interfaces:** Produce `create_repository(config: ApConfig) -> ApRepository` using the server-only Supabase SDK, with explicit ten-second query/storage timeouts and no interactive auth. Add `supabase>=2,<3` to requirements and verify the resolved version works with the installed Python/Streamlit versions and the modern secret-key format.

`ApRepository` produces `bootstrap(workspace_id, cursor=None, limit=50) -> SharedSnapshot`, `records_page(workspace_id, import_id, after_ordinal, limit=500) -> JsonObject`, `statement(workspace_id, statement_id, revision=None) -> JsonObject`, `history_page(workspace_id, filters, cursor, limit=50) -> JsonObject`, `signed_pdf(workspace_id, statement_id, expires_in=300) -> JsonObject`, and `transact(operation, workspace_id, request_id, payload_hash, data) -> JsonObject`. It implements `AccessLimiter` using only `ap_access_limits` before authorization. Read queries always filter by the trusted workspace, with deterministic cursors; do not cache user data globally.

`ApService` takes the repository, configuration, and a server clock. Produce `handle(action: str, payload: JsonObject, request_id: str, authorization: Authorization) -> JsonObject`. Allowlisted actions are bootstrap, records_page, statement, history_page, pdf_preview, upload_begin, upload_chunk, upload_finish, import_begin, import_records, import_finish, save_revision, save_mapping, complete_revision, reopen_statement, archive_statement, and migrate_legacy. There is no shared clear/delete action.

Core assertions in `test_completion_retry_is_idempotent`, using an authorized synthetic fixture with confirmed extraction and all necessary review decisions:

```python
first = service.handle('complete_revision', payload, request_id, authorization)
again = service.handle('complete_revision', payload, request_id, authorization)
self.assertEqual(first, again)
self.assertEqual(len(fake_repository.completion_events), 1)
```

- [ ] Write failing fake-repository tests for exactly 1,001 records and 5,610 records, asserting every stable ordinal loads once and the caller detects missing pages instead of concluding invoices are missing. Test mismatched workspace IDs, error sanitization, and rejecting a signed-PDF lookup that does not belong to the workspace. Run targeted repository tests; expect missing modules.
- [ ] Write service tests for identical request replay, changed-payload request replay, a dropped acknowledgement, and conflicts between revisions from two simulated users. Assert one completion event for a retried completion and preservation of the prior active import after an incomplete or invalid import. Assert completion with blank notes succeeds and blank initials fails.
- [ ] Implement repository reads and RPC writes using Task 2 contracts. Store immutable provider metadata, normalized records, comparison snapshots, mapping snapshots, and matching rule version `ap-match-v2`. Server timestamps are UTC. SDK exceptions are mapped to safe codes `validation`, `denied`, `conflict`, `unavailable`, or `not_saved` without exposing credentials or financial values.
- [ ] Implement staged uploads bound to the authorization's server nonce. `upload_begin` accepts kind, filename, byte count, and expected SHA-256, returning a server UUID. Store chunks at generated private staging keys, validate order and byte bounds, and reject a changed chunk retry. Finish verifies byte count, hash, `%PDF-` for PDFs or valid UTF-8 CSV structure for CSV, then stores an immutable original and metadata. Reuse completed hashes; filename collisions remain separate. An OCR failure must still permit an unconfirmed draft linked to the original.
- [ ] Stage import batches under an import ID and only activate using `ap_activate_import` after the original CSV and all validated records exist. Preserve existing browser import semantics, source row details, and warnings; schema validation does not claim an independent re-extraction of the CSV. No original BILL records are inferred from Amount Due when the export omits it.
- [ ] Implement completion, reopening, archiving, and mapping changes through the RPCs. Reject rewriting completed revisions; reopening creates a draft. Ordinary saves never purge prior completion evidence. Expired authorization rejects outstanding upload/chunk requests. Failed finalization leaves non-active staging data for administrative cleanup, not a misleading saved item.
- [ ] Run all new repository/service tests. In an explicitly authorized disposable Supabase test project, verify RLS denial, private object access, 300-second previews, secret-key compatibility, RPC transaction behavior, and round-trip reads. Test files are synthetic. Document skipped integration checks as a deployment blocker, not a pass.
- [ ] Commit `feat: persist AP imports statements and review revisions in Supabase`.

## Task 5 Authorized component protocol and rerun-safe client

**Files:** Create `app/ap_shared/protocol.py`, `app/ap_statements/frontend/shared-client.mjs`, `tests/test_ap_shared_protocol.py`, `tests/ap_statements_shared_client.test.mjs`; modify `app/ap_statements/bridge_core.mjs`, `app/ap_statements/streamlit_bridge.mjs`, `app/ap_statements_ui.py`, and existing bridge tests. Rebuild the committed `frontend/bridge.bundle.mjs` through `app/ap_statements/build.mjs`.

**Interfaces:** Produce Python `dispatch_request(value: object, session: MutableMapping, config: ApConfig, service: ApService, now: datetime) -> JsonObject`. It calls `require_access` before every financial operation. Produce browser `createSharedClient({send, subscribe})` with `request(action, payload, {requestId, signal} = {}) -> Promise<object>` and `dispose() -> void`. `subscribe` consumes server response envelopes from Streamlit render arguments, not arbitrary window messages.

Core assertions in `test_locked_request_never_reaches_service`, with a valid bootstrap envelope and no authorization:

```python
reply = dispatch_request(request, {}, config, fake_service, now)
self.assertFalse(reply['ok'])
self.assertEqual(reply['error']['code'], 'denied')
self.assertEqual(fake_service.calls, [])
```

- [ ] Write failing protocol tests asserting denied access never calls `service.handle`; unknown action names, extra fields, arbitrary workspace selectors, malformed IDs, payloads above 1 MiB, and embedded credentials are rejected. A repeated navigation request still does not cause repeated exits. Expired/rotated access returns denied and sends no financial bootstrap data.
- [ ] Write Node tests with fake Streamlit SDK events: one request is sent at a time; only a matching version and request ID resolves it; unrelated or out-of-order replies are ignored; rerenders do not reset unsaved inputs. A timed-out request rejects with a visible retry path, and retrying a write uses the original request ID and payload. Test lock/dispose rejecting pending requests and releasing sensitive references.
- [ ] Run the two new test files; expect missing functions. Implement the explicit request envelope, guarded dispatch, asynchronous queue, and response acknowledgement. Keep request correlation in session state and database idempotency for writes; do not persist signed preview URLs in `ap_requests`. Read requests may regenerate expired links.
- [ ] Replace the old blanket prohibition on financial component values with tests of the authorized allowlist and secret-free responses. Unsupported values never reach a service or trigger navigation. Component keys remain stable for reruns and change on lock/re-unlock so stale component data cannot remain visible.
- [ ] Build with `npm run build` in `app/ap_statements` using the established local dependency runtime; retain OCR/vendor assets and licenses. Run protocol, bridge, asset, and shared-client tests; expect zero failures and no Supabase key or password value in built assets.
- [ ] Commit `feat: add guarded shared AP component requests`.

## Task 6 Automatic shared loading and durable working statements

**Files:** Create `app/ap_statements/frontend/shared-workspace.mjs`, `tests/ap_statements_shared_workspace.test.mjs`; modify `frontend/app.mjs`, `frontend/guide.mjs`, `frontend/styles.css`, and `frontend/session.mjs` only where needed for explicit legacy export. Keep PDF/OCR algorithms in `extraction.mjs` and `core.mjs` unchanged beyond Task 1 matching.

**Interfaces:** Produce `createSharedWorkspace(client, {onState, onSaveState})` with `load()`, `loadProvider(importId)`, `importBills(file, parsedProvider)`, `uploadStatement(file, extract)`, `saveStatement(doc, expectedVersion)`, `saveMapping(mapping, expectedVersion)`, `originalPdf(statementId)`, and `dispose()`. Each returns a Promise; save state is `saving`, `saved`, or `not_saved`. Unsaved local edits are never replaced by an incoming shared snapshot.

Core assertions in `all_import_records_load_before_matching`, using a fake client that serves 5,610 synthetic rows over record pages:

```javascript
const provider = await workspace.loadProvider(importId);
assert.equal(provider.loaded, true);
assert.equal(provider.records.length, 5610);
assert.equal(new Set(provider.records.map(row => row.id)).size, 5610);
```

- [ ] Write failing tests proving startup ignores legacy localStorage data unless migration is selected, bootstrap shows the stored source filename/count/date, and 5,610 records are loaded over multiple pages. Until loading completes, matching is unavailable, not missing. Simulate backend outage and assert no automatic local-only fallback or misleading Saved badge.
- [ ] Test uploading multiple synthetic PDFs, same hash under another filename, different hashes with the same filename, and an extractor exception. Assert the last case has an original file and unconfirmed draft, not a missing-invoice result. A backend upload failure keeps local bytes available for retry and does not display Saved.
- [ ] Test a failed import keeping the prior provider active, and duplicate import reusing its immutable import ID. A new active import invalidates draft comparison decisions while retaining draft notes; it never changes completed revision snapshots. Test Saving/Saved/Not saved changes only on actual acknowledgements. Test `dispose` releasing files, preview buffers, pending promises, and financial state on lock. Run the new test; expect missing module or methods.
- [ ] Implement shared loading and page assembly, following both bootstrap `nextCursor` and import record cursors to completion. Replace implicit browser-local restore as the authority. Route explicit Save corrections, Confirm extracted rows, Save notes, row review decisions, and vendor mapping saves through shared operations. Save edits only after validation; completed revisions remain read-only until explicitly reopened. Retain the existing confirmation boundary and warnings.
- [ ] Save each PDF draft once its original is uploaded, before attempting OCR; update that unconfirmed draft after extraction. `pdfPanel` reopens originals via an authorized 300-second link and PDF.js. Request a fresh link after expiry without making the bucket public. A missing legacy original is labeled Original PDF not attached.
- [ ] Update guidance and navigation to distinguish unsaved edits from acknowledged shared saves. Clear workspace becomes Reset local view, explicitly retaining shared records. Keep the co-op white/green styling, blur transition, keyboard behavior, and guide flow. Do not claim shared saving works while backend errors are visible.
- [ ] Run workspace, guide, navigation, session, scan, core, and native import tests. Expect zero failures. Commit `feat: restore shared AP bills and original statements automatically`.

## Task 7 Completion initials and Previous Statements history

**Files:** Create `app/ap_statements/frontend/history.mjs`, `tests/ap_statements_history.test.mjs`; modify `frontend/app.mjs`, `frontend/shared-workspace.mjs`, and `frontend/styles.css`.

**Interfaces:** Produce `completionPayload({doc, resolutions, initials, notes, importId, mappingSnapshot, expectedVersion}) -> object`, `historyFilters({vendor, statementDate, initials, status, completedFrom, completedTo}) -> object`, and `historyView(page) -> string`. Add workspace methods `completeStatement(payload)`, `history(filters, cursor)`, `reopenStatement(id, expectedVersion)`, and `archiveStatement(id, expectedVersion)`, which call Task 4 operations through Task 5.

Core assertions in `completion_allows_blank_notes`, using a saved confirmed synthetic statement with no unresolved comparisons:

```javascript
const payload = completionPayload({...fixture, initials: 'kc', notes: ''});
assert.equal(payload.initials, 'KC');
assert.equal(payload.notes, '');
assert.throws(() => completionPayload({...fixture, initials: ''}), /initials/i);
```

- [ ] Write failing Node assertions: initials `kc` become `KC`; blank/invalid initials prevent completion; empty notes are accepted; unconfirmed extraction cannot complete; unresolved comparisons require a review decision. A reviewed follow-up status is distinct from fully reconciled. Initials are labeled Reviewer initials, not authenticated reviewer.
- [ ] Test history filters and server timestamps displayed in `America/New_York`, including daylight-saving boundaries. Test viewing the original revision after a new import/mapping/rule change and assert its snapshot and import ID stay unchanged. Test that only explicit Reopen creates a new editable draft.
- [ ] Test stale save responses: display Conflict, preserve unsaved edits, and offer Reload latest without an automatic overwrite. A lost completion acknowledgement retries the same request ID and shows one event. Test all displayed notes/filenames/initials are HTML-escaped and exported rows retain formula protection.
- [ ] Run `node --test tests/ap_statements_history.test.mjs`; expect missing module or behavior. Implement Mark reviewed and Previous Statements, with vendor/date/initials/status/completion-date filters and paginated results. Completed revisions open read-only; an explicit reopen starts further work. Notes fields remain optional everywhere.
- [ ] Preserve provenance in reports: import filename/ID, comparison rule version, stated initials, server completion timestamp, and original matching reasons. Do not label an amount-only candidate or native export as a verified balance after a user marks the work reviewed.
- [ ] Run new history and prior Node tests; expect zero failures. Commit `feat: show completed AP statement history with reviewer initials`.

## Task 8 Explicit migration setup and release verification

**Files:** Create `docs/ap-shared-workspace-setup.md`, `docs/ap-shared-workspace-validation.md`, `tests/test_ap_shared_migration.py`, `tests/ap_statements_migration.test.mjs`; modify `frontend/shared-workspace.mjs`, `frontend/app.mjs`, and `app/ap_shared/service.py` for explicit migration only. Update the design's status to Implemented only after the feature is actually verified and released.

**Interfaces:** Produce `legacyMigrationPreview(session, mappings) -> object` in `shared-workspace.mjs`, listing real statement count, original-file availability, import metadata, and review notes. `migrate_legacy` creates new shared drafts and historical notes without inventing reviewer initials or completion events. Missing originals remain incomplete. Request-level replay and file hashes deduplicate subsequent attachments.

Core assertions in `migration_does_not_invent_completion`, using an explicitly confirmed migration of synthetic legacy notes without original PDFs:

```python
result = service.handle('migrate_legacy', payload, request_id, authorization)
self.assertEqual(result['migrated_count'], 1)
self.assertEqual(fake_repository.completion_events, [])
self.assertIsNone(result['statements'][0]['original_object_id'])
```

- [ ] Write failing tests proving browser-local data never migrates on startup, cancel sends nothing, confirmed migration excludes old demo/simulated records, and no completion is fabricated from legacy review decisions. Assert a missing PDF is visible and prior browser data stays intact after a failed migration. Test duplicate IDs in a legacy payload cannot overwrite shared records.
- [ ] Run migration tests, implement explicit preview and confirmation, then rerun them; expect zero failures. Do not migrate the user's current browser session or actual supplied PDFs as a test.
- [ ] Write setup instructions for creating a user-controlled Supabase project, applying the supplied migration, configuring a private `hwfc-ap-private` bucket with the file-size limit, checking denied anonymous access, and entering the `[ap]` secret values directly in Streamlit. Include no actual password or API key. Provide synthetic examples and explain that changing the password locks existing sessions on their next operation.
- [ ] Document staged-object cleanup limited to expired, unreferenced upload IDs, plus separate database and object-file backup/restore procedures. Retain referenced originals and immutable review events. Verify a synthetic backup restoration before depending on the archive; do not promise a platform backup includes file bytes automatically.
- [ ] Run `python -m unittest discover -s tests -v`, the full Node suite, the frontend build, and `git diff --check`. Capture current counts and actual output rather than repeating historical test totals. Review dependency installation with `python -m pip check` in the isolated test environment.
- [ ] With explicit authorization for a synthetic test project, run SQL/Supabase integration tests and browser checks: two independent unlocked sessions see the same stored CSV and PDFs; locking prevents subsequent data requests; concurrent editing conflicts; a fresh session shows preserved completed history after importing newer records. Verify denied direct database/file access, no secrets in browser assets/messages, expired PDF links, failed save recovery, responsive layout, and AP-to-hub-to-Daily round trips.
- [ ] Use a fresh code review focused on authorization bypass, data loss, mutation replay, cross-vendor matches, and frozen history. Address confirmed findings with failing tests before claiming completion. Record any live verification blocked by missing project credentials as incomplete; offline tests alone do not prove durable shared storage.
- [ ] Commit `docs: document AP shared storage setup migration and validation`. Stop for the user's merge/push and live-setup direction. Do not change production settings or upload company financial data without the corresponding authority.

## Self-review and execution handoff

The matching task is independently testable; storage, authorization, protocol, and shared UI are kept in one plan because their access checks and data contracts must agree. Task 8 cannot be claimed complete until SQL, storage access, and two-browser persistence are exercised against an authorized synthetic environment.

Coverage: matching is Task 1; private schema and validation are Task 2; password lifecycle is Task 3; records/files/history transactions are Task 4; component access and replay are Task 5; saved imports/PDFs and save-state UI are Task 6; initials/optional notes/previous work are Task 7; migration, recovery, regression, and activation are Task 8. Each Review Focus item has a named owning task and assertion. Exact credential values remain outside all artifacts.

After the user reviews this plan, choose execution before implementation. Native execution keeps the tightly coupled storage and bridge interfaces in one implementer's context, followed by an independent whole-branch review. Subagent-driven execution gives each task its own implementer and reviewer, with more handoffs and context cost. Neither method authorizes external provisioning or production uploads.

## Technical references

- [Supabase Python client initialization and timeouts](https://supabase.com/docs/reference/python/initializing)
- [Supabase Python reads and pagination](https://supabase.com/docs/reference/python/select)
- [Supabase private storage](https://supabase.com/docs/guides/storage/buckets/fundamentals)
- [Supabase server-only secret keys](https://supabase.com/docs/guides/getting-started/api-keys)
- [Streamlit secret handling](https://docs.streamlit.io/deploy/concepts/secrets)
