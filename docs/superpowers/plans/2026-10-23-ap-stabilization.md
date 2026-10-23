# AP Reliability Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Preserve the user's Native execution choice: implement in this session using executing-plans.

**Goal:** Make existing AP screens stable during background work, make duplicate recovery safe, and replace misleading indefinite loading with useful status.

**Architecture:** Keep the embedded JavaScript workspace and Streamlit request/reply bridge. Separate duplicate-only DOM updates from full workspace updates, coalesce recovery in the duplicate controller, expose safe scan timing metadata, and add an independent startup watchdog. Do not replace the transport or introduce an independent worker.

**Tech Stack:** JavaScript ES modules, Node test runner, Python unittest, Streamlit, private Supabase storage/Postgres, existing esbuild pipeline.

**Spec:** `docs/superpowers/specs/2026-10-23-ap-stabilization-design.md` (approved October 23, 2026).

## Global Constraints

- Keep Streamlit, JavaScript, Python, the private Supabase bucket, existing schema, and server-side authorization.
- No new service, database migration, automatic financial decision, bill/credit mutation, data deletion, or Daily Deposit change.
- Never silently replay a stale review write or steal another session's lease.
- No repeated automatic reloads and no credential handling.
- Expose safe stage/checkpoint/timing diagnostics, not credentials, invoice data, or raw backend exception text.
- Commit locally; merging, pushing, deployment, and any production administrative change require separate user authorization.
- Preserve previously committed re-review/PDF work, the unapplied re-review migration, and untracked QA artifacts. Never edit synced `sources/`.
- Work in the existing `portal-source/.worktrees/deploy-dd-v2` checkout on `codex/ap-shared-workspace`; paths below are relative to that checkout. Stage explicit paths only.

## Review Focus

1. Duplicate updates while typing, selecting text, viewing a PDF, or opening history must preserve the active DOM and user draft (Task 1).
2. Two immediate recovery clicks, including an initial ensure conflict with no scan ID, must issue one safe recovery rather than a stale second restart (Task 2).
3. Source A-to-B-to-A changes or access denial during a pending reply must not restore old evidence or replay a review save (Tasks 1 and 2).
4. All records read, a live lease owned elsewhere, missing timestamps, and clock skew must not falsely imply completion or permit lease theft (Task 3).
5. Missing module/bridge startup, late success, and an existing error must yield bounded, non-destructive startup behavior without reload loops (Task 4).

## File responsibilities

- `frontend/app.mjs`: route workspace changes and patch duplicate-owned DOM only; integrate startup lifecycle signals.
- `frontend/duplicate-bills.mjs`: serialize recovery and track monotonic local scan observations.
- `frontend/duplicate-bills-ui.mjs`: present stages, recovery, and bounded safe diagnostics.
- New `frontend/duplicate-progress.mjs`: pure stage/staleness presentation, separate from financial rules.
- `app/ap_shared/bills/duplicates/operations.py`: add optional safe timing fields to progress responses; no schema change.
- New `frontend/startup-watchdog.js`: dependency-free classic startup guard, runnable even if ES modules fail.
- `frontend/index.html` and `bridge_core.mjs`: load guard before modules and signal bridge attachment.
- Tests listed below cover the actual production functions or real controllers; do not substitute fake implementations for assertions about behavior.

All `frontend/` paths above mean `app/ap_statements/frontend/`.

---

### Task 1: Keep active screens intact during duplicate notifications

**Files:** Modify `app/ap_statements/frontend/app.mjs`; test `tests/ap_statements_preview_updates.test.mjs`; create `tests/ap_statements_background_updates.test.mjs`.

**Interfaces:** Keep `receiveShared(snapshot, change={})` and `change.reason === 'duplicates'`. Add `renderDuplicateUpdate(): void` in app.mjs. Give the duplicate nav item and view stable wrapper IDs, `duplicate-nav-slot` and `duplicate-view-slot`. Only these slots may change on duplicate-only events. Genuine workspace/source/denial updates retain full rendering.

- [x] **Write failing regressions.** Extend the real receiveShared/controller harness. Assert that duplicate events leave Vendor input, statement table, history preview, PDF canvas and `.main` node identities unchanged; typing query/caret/scroll persist while duplicate badge changes. In duplicate view, assert focused note value and selection survive a progress update. Assert an untagged statement update still refreshes evidence, and locked/access-denied events clear it.
- [x] **Run RED.** `node --test --test-isolation=none tests/ap_statements_preview_updates.test.mjs tests/ap_statements_background_updates.test.mjs` must fail on the current full-shell rebuild, not a harness exception.
- [x] **Implement scoped routing.** In receiveShared, determine safe duplicate-only status before invoking render. Patch the nav slot and, only if visible, the duplicate view slot. Preserve focused duplicate control ID/selection and current scroll around the smaller replacement; use existing duplicateDrafts for values. Do not call decorateSharedUi, bindDropzone, renderDrawer, or history preview loaders from this path. Fall back to full render when the workspace is not ready, source changes, or access is locked/denied.
- [x] **Run GREEN.** Repeat the two test files and `tests/ap_statements_duplicates_ui.test.mjs`; all must pass, including genuine evidence refresh and denial cases.
- [x] **Commit.** Stage only Task 1 files; commit `Fix AP background updates without rebuilding active screens`.

### Task 2: Coalesce recovery and handle initial conflicts safely

**Files:** Modify `app/ap_statements/frontend/duplicate-bills.mjs`, `app/ap_statements/frontend/duplicate-bills-ui.mjs`; test `tests/ap_statements_duplicates_controller.test.mjs`, `tests/ap_statements_duplicates_ui.test.mjs`.

**Interfaces:** Preserve public `retry(): Promise<object|null>` and existing request IDs for retrying the same failed non-conflict operation. Add a source-token-scoped recovery promise internally; repeated retry calls return that promise. Conflict recovery uses `duplicate_status({scan_id})` only when a scan ID exists, otherwise a fresh `duplicate_ensure({import_id, expected_import_version})`. Never reissue a conflicting review save automatically.

- [x] **Write failing regressions.** Hold the first restart reply, call retry twice synchronously, and assert `strictEqual(first, second)` plus exactly one restart request with the current checkpoint/generation. Reject initial ensure with duplicate_conflict and assert retry sends ensure without dereferencing null. Assert conflicting review save refreshes status but sends no second save; transient same-operation retry preserves its request ID. Repeat with source A-to-B-to-A and denial while recovery is held: late replies must not restore evidence or alter the new source.
- [x] **Run RED.** `node --test --test-isolation=none tests/ap_statements_duplicates_controller.test.mjs tests/ap_statements_duplicates_ui.test.mjs` must expose double restart/null recovery failures.
- [x] **Implement one recovery operation per source token.** Construct recovery payload from current state inside the selected recovery path, coalesce until settlement, and clear the guard on settlement/source replacement/dispose without clearing a newer guard. Keep the existing serialized queue and generation/checkpoint/authorization checks. Disable refresh/retry/restart controls while controller loading is true, preserving drafts and the UI's existing accessible actions. A still-active foreign lease uses status only.
- [x] **Run GREEN.** Repeat the controller/UI tests; verify normal busy pauses, source-token rejection, same-ID transport retry, lost reply, draft retention, and authorization coverage remain passing.
- [x] **Commit.** Stage only Task 2 files; commit `Serialize duplicate recovery and handle missing scan status`.

### Task 3: Show accurate stages, waiting, and interruption

**Files:** Modify `app/ap_shared/bills/duplicates/operations.py`, `app/ap_statements/frontend/duplicate-bills.mjs`, `app/ap_statements/frontend/duplicate-bills-ui.mjs`; create `app/ap_statements/frontend/duplicate-progress.mjs`, `tests/ap_statements_duplicate_progress.test.mjs`; extend `tests/test_ap_duplicates_operations.py` and controller/UI tests.

**Interfaces:** Add optional `updatedAt`, `leaseExpiresAt`, and `serverNow` ISO timestamps to `_progress()` output using existing scan fields and injected server clock. Preserve all current response fields. Extend `createDuplicateBills` options with `now=Date.now`; expose local `observedAt` and `lastAdvanceAt` milliseconds in state, reset on source/generation changes. Export `duplicateProgressPresentation(state, now=Date.now()): {kind, title, message, busy, diagnostics}`; kind is active/waiting/interrupted/paused/ready. Diagnostics contain only phase, checkpoint, and elapsed seconds.

- [x] **Write failing backend metadata test.** Assert exact safe timing values from the fake clock, absent timestamps serialize as null, and response excludes session nonce, source digest, storage paths and raw exceptions. Keep authorization/source-replacement tests in the run.
- [x] **Run backend RED.** Use `C:/Users/karlcruz/AppData/Local/Temp/ap-tut-1019/Scripts/python.exe -X utf8 -m unittest tests.test_ap_duplicates_operations -v`; the new metadata assertion must fail before implementation.
- [x] **Write failing presentation/controller tests.** With an injected clock assert reading, candidates, packaging, and ready-but-projection-pending show distinct text. Packaging at 223425/223425 is not completion. `canStep === false` shows waiting without an active work spinner and offers no restart while lease is live. At 60000 ms without checkpoint/phase/counter advance show interrupted/no-progress status, not finished; newer progress resets it. Missing/invalid timestamps use local observation; server-relative age avoids client clock skew. Failed requests and expired/restart-required scans retain explicit recovery. Unknown phases use neutral checking text. Generic duplicate_conflict says checks could not continue, not that source changed.
- [x] **Run frontend RED.** `node --test --test-isolation=none tests/ap_statements_duplicate_progress.test.mjs tests/ap_statements_duplicates_controller.test.mjs tests/ap_statements_duplicates_ui.test.mjs` must fail on absent presentation/observations or misleading copy.
- [x] **Implement metadata and pure presentation.** Calculate initial age from serverNow minus updatedAt, clamped to nonnegative finite values; thereafter use elapsed local observation time. Use phase/checkpoint/recordsRead/probes/projectionReady as the advancement signature. Choose 60000 ms as a diagnostic warning threshold only, never as permission to restart or change server ownership. Keep current polling/lease rules; show safe details in an expandable diagnostic area. Reuse presentation for sidebar activity and main content. Disable mutation controls while recovery is in flight (Task 2). Do not alter global financial conflict checks or expose raw backend messages in diagnostics.
- [x] **Run GREEN.** Repeat affected backend and frontend tests; include existing expired-lease/foreign-session/source-replacement/publication-safety cases. Missing metadata from an older deployed backend must remain usable.
- [x] **Commit.** Stage only Task 3 files; commit `Show honest duplicate scan stages and interrupted progress`.

### Task 4: Bound component startup and verify the full stabilization pass

**Files:** Create `app/ap_statements/frontend/startup-watchdog.js`; modify `app/ap_statements/frontend/index.html`, `app/ap_statements/frontend/app.mjs`, `app/ap_statements/bridge_core.mjs`; extend `tests/ap_statements_startup.test.mjs`, `tests/ap_statements_bridge.test.mjs`; create `docs/superpowers/verification/2026-10-23-ap-stabilization.md`. Regenerate `frontend/bridge.bundle.mjs` using the existing build.

**Interfaces:** The classic guard installs `window.hwfcStartupWatchdog` with `markAppReady(): void`, `markBridgeReady(): void`, and `dispose(): void`. Load it before both module scripts. App signals after event handlers and initial render are attached; bridge signals after client/RENDER listener installation. A 20000 ms timer waits for both signals, then stops. These are initialization signals, not successful data-loading signals; bootstrap request failure remains owned by the existing shared-client/load-error path.

- [x] **Write failing tests.** Run the guard in a VM with fake timers/DOM. Missing either startup signal at 20000 ms must replace only the initial startup spinner with an actionable message and manual Reload button. Both signals before deadline cancel the timer. The guard must not replace an existing workspace/error, late signals must not auto-reload, and pagehide disposes its timer. Bridge attachment signals readiness once; existing bridge navigation still never forwards event detail. Preserve the current circle-only initial loading assertions and bootstrap failure/retry tests.
- [x] **Run RED.** `node --test --test-isolation=none tests/ap_statements_startup.test.mjs tests/ap_statements_bridge.test.mjs` must fail for absent watchdog behavior.
- [x] **Implement the dependency-free guard.** Limit takeover to the original startup node, with no data or authentication access. Explain that the connection did not initialize and offer user-triggered reload only. Do not add reload intervals or replace the 30000 ms shared-client timeout. Document that this guard cannot execute if Streamlit never serves the component HTML (the observed outer-frame hosting failure remains a separate live check).
- [x] **Run GREEN and build.** Run startup/bridge/client tests, then `node app/ap_statements/build.mjs`; confirm the bridge bundle includes readiness signaling and static guard is packaged with index.html.
- [x] **Run full frontend verification.** In PowerShell: `$apTestFiles=@(Get-ChildItem tests -Filter 'ap_statements*.test.mjs' | ForEach-Object {$_.FullName}); node --test --test-isolation=none @apTestFiles`. Expected zero failures. Record current counts rather than assuming previous totals.
- [x] **Run synthetic browser QA.** Use the computer-use skill and local fixtures, not production financial edits. While duplicate progress runs, type continuously in Vendor search, navigate statements/history, open a preview, select invoices across PDF pages, and verify highlights/canvas remain stable. Exercise rapid recovery clicks, initial conflict, expired lease, foreign active lease, no-progress warning and blocked module startup. Check duplicate note/caret preservation and access-denial cleanup. Record screenshots and observed request counts in local artifacts; do not commit source financial data.
- [x] **Run backend and whitespace release checks.** Run the complete Python suite once (previous duration about 14 minutes), no concurrent scale-test jobs; use `-X utf8 -m unittest discover -s tests -v`. Run `git diff --check`. Expected zero unexpected failures; document any genuine optional/live skips. Existing broader suite includes prior re-review work.
- [x] **Record evidence and remaining boundaries.** In the verification doc record commands/results, 20000 ms startup and 60000 ms warning choices, synthetic evidence, preserved source/lease/auth contracts, and the distinction between local verification and unverified live scan recovery. List any pre-existing pending migration/release step separately. Request final whole-branch review per requesting-code-review; resolve findings and re-run affected tests before any completion claim.
- [x] **Commit.** Stage only Task 4 code, generated bridge, tests and verification doc; commit `Bound AP startup failures and verify reliability stabilization`. Do not merge, push, apply migrations, or reboot production without separate authorization.

## Plan self-review

- Spec coverage: stable views (Task 1), serialized recovery (Task 2), honest stages/safe diagnostics (Task 3), bounded startup (Task 4); all have RED/GREEN verification.
- Cross-task interfaces: duplicate slots belong to Task 1; recovery stays retry() in Task 2; optional metadata and pure presentation belong to Task 3; startup signals remain independent of workspace readiness in Task 4.
- All five Review Focus cases are assigned to explicit regressions; production ownership/authorization remain unchanged.
- Scope boundary: this pass fixes confirmed rendering/recovery defects and improves diagnosis. It does not claim a proven root cause for every live conflict or guarantee Streamlit uptime.
- Execution: Native completed after user approval. Final verification: 421 frontend tests; 735 backend tests with one optional live integration skip; build and whitespace checks pass. Independent review findings fixed in one regression-tested pass.
