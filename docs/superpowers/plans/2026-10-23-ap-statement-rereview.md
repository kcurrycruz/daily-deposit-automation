# AP Statement Re-review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The user's existing execution preference is Native.

**Goal:** Re-review previous statements against latest BILL data or a clearly labeled manual check without overwriting historical evidence.

**Architecture:** Extend the existing statement draft/revision workflow with an atomically persisted review mode. A manual draft uses its pinned saved comparisons; normal drafts use the current scoped comparison source. Manual assertions live in resolution metadata, not matching results.

**Tech Stack:** Existing Python service/repository, private Supabase PostgreSQL RPCs, vanilla JavaScript modules, Node tests and local PGlite.

**Spec:** `docs/superpowers/specs/2026-10-23-ap-statement-rereview-design.md`

## Global Constraints

- "Checked manually in BILL" is a review-method label, never proof of imported invoice presence, payment settlement, credit application or QuickBooks sync.
- Legacy revisions, completed history, original PDFs and prior completion timestamps remain immutable.
- No live SQL, real upload, merge, push, deployment or paid service changes.
- Missing migration disables the new controls without disabling existing statement/history workflows.
- Preserve the existing credit limitation notices and linked Ace credit display.

## Review Focus

1. Another session already reopened or edited the statement: do not replace its draft with the selected historical copy. Task 1 SQL CAS and Task 3 UI tests.
2. Reopen committed but acknowledgement was lost: retry returns the same revision and retains notes. Task 1 SQL idempotency and Task 2 controller tests.
3. A weekly import changes while a manual draft is open or restored: keep its comparison source, results and review metadata pinned. Task 2 load/import/save/completion tests.
4. Financial extraction changes behind a manual result: reject stale evidence and require latest-data mode for corrections. Task 1 validation and Task 3 controls tests.
5. A failed latest comparison or access expiry: retain the prior draft on failure and clear private financial state on expiry. Task 2 failure and disposal tests.

## File responsibilities

- `supabase/migrations/202610230001_ap_statement_rereview.sql`: private atomic reopen, mode/notes preservation, CAS, idempotency and capability marker.
- `app/ap_shared/models.py`, `service.py`, `repository.py`: mode/manual metadata validation, authoritative pinned-evidence checks and capability reporting.
- `app/ap_statements/frontend/manual-review.mjs`: validate and bind manual assertions and render their controls/labels.
- `shared-workspace.mjs`: mode-aware reopen, pinned manual load/save/completion and explicit latest comparison.
- `app.mjs`, `history.mjs`, `history-browser.mjs`, `reference-review.mjs`, `session.mjs`: entry points, mode choice, per-item decisions, display, export and safe session handling.
- Targeted Node/Python tests and `tests/fixtures/ap_shared/rereview_schema_checks.mjs`: synthetic acceptance only.

### Task 1: Private atomic reopen and validated manual evidence

**Files:** Create the migration and `tests/fixtures/ap_shared/rereview_schema_checks.mjs`; modify models/service/repository; add `tests/test_ap_rereview.py` and targeted model/service/repository tests.

**Interfaces:** Mode-aware `reopen_statement` accepts optional `review_mode: 'manual' | 'latest'`. SQL `ap_rereview_statement(p_workspace uuid,p_request_id uuid,p_payload_hash text,p_data jsonb)` returns `{statement_id,version,revision_id}`. Existing `ap_reopen_statement` routes mode-aware calls to it, preserving legacy routing otherwise. Bootstrap adds `capabilities.statementRereview: 1` from `rereview_schema_version=1`.

`validate_statement` accepts optional reviewMode enum. `validate_resolution` accepts optional manualCheck `{vendor,reference,amount,kind,initials}`; initials normalize to one to ten uppercase letters, amount is safe integer cents, kind is invoice/credit/payment/opening. The service checks the marker against that result's vendor/reference/originalAmount/kind and confirms manual financial rows, pinned results, import/mapping/rule match the authoritative current draft.

- [ ] Write SQL tests: manual reopen retains old resolutions/notes and pins evidence; latest reopen keeps notes only; old revision/completion untouched; new revision IDs differ; same request ID/hash returns the same reply; changed payload fails; wrong workspace/version and existing draft cannot be overwritten; anon/authenticated RPC access denied.
- [ ] Run `node tests/fixtures/ap_shared/rereview_schema_checks.mjs`; expect failure before migration exists.
- [ ] Add the additive service-role-only RPC and marker. Lock the statement, verify expected version/completed state, copy current revision once, append a reopened event and update the head in one transaction. Do not rewrite the old migration.
- [ ] Write and run Python tests that reject invalid mode, forged/stale manual metadata, modified frozen financial rows/results/source, unsupported capability and arbitrary fields while accepting optional notes and the exact current pinned evidence.
- [ ] Implement the validation/capability boundary and run `python -X utf8 -m unittest discover -s tests -p 'test_ap*rereview*.py' -v` plus affected model/service/repository suites; expect all pass.
- [ ] Commit Task 1 with an explicit migration-not-applied note in the ledger.

### Task 2: Source-pinned drafts and explicit review methods

**Files:** Create `manual-review.mjs`; modify shared-workspace/session/reference-review; test `ap_statements_rereview.test.mjs` and existing workspace/matching tests.

**Interfaces:** `createManualCheck(doc,row,{initials,decision,note},prior={})` returns a resolution without changing row candidates/status. `manualCheckFor(row,resolution)` returns valid bound metadata or null, requiring an acknowledged at timestamp for a displayed saved label. `invoiceResult` adds checkedManually without turning a missing item into found.

`workspace.reopenStatement(id,expectedVersion,{mode}={})` forwards review_mode only when supported and reads back the exact acknowledged revision. Existing signatures remain compatible. Manual doc.reviewMode makes prepare/ensure skip source replacement; saveData/complete use its pinned results/import/mapping/rule. `refreshComparisons(id)` explicitly switches to latest data, keeps notes, clears superseded decisions and restores the manual draft on failure.

- [ ] Add failing tests for manual-marker binding/initials, no automatic found-count inflation, notes-only latest reopening, stable retry identities/readback, concurrent head changes and reuse of an existing draft.
- [ ] Add failing tests for manual mode across startup, prepare, weekly import adoption, save and completion, including a different current mapping/import and unavailable current source. Assert pinned evidence is unchanged.
- [ ] Add failing tests for failed explicit refresh restoring mode/source/decisions, dirty local changes not being replaced, and access expiry clearing private state.
- [ ] Implement the smallest mode-aware paths and manual helpers. Keep saved financial rows unchanged in manual mode and existing compare behavior for absent/latest mode.
- [ ] Run `node --test --test-isolation=none tests/ap_statements_rereview.test.mjs tests/ap_statements_shared_workspace.test.mjs tests/ap_statements_confirmed_match.test.mjs`; expect all pass.
- [ ] Commit Task 2.

### Task 3: Direct history actions and editable manual decisions

**Files:** Modify app/history/history-browser/reference-review/manual-review and relevant UI/export tests.

**Interfaces:** History adds `history-rereview` carrying the existing event ID. A mode-choice dialog offers latest and manual, explicitly starts from the latest head and retains View revision. The existing read-only reopen control opens this same choice when supported. Mode banners display the pinned import and explain manual assertions. Manual checkbox/initials controls use IDs `review-manual-check` and `review-manual-initials`; the existing resolve action remains the only per-item save path.

- [ ] Write failing rendered/action tests for both history views, capability missing, preserved read-only View revision, safe existing/dirty draft reuse and a colleague's newer revision.
- [ ] Write failing tests for checkbox+initials validation, saved "Checked manually in BILL" distinct from automatic Invoice found, follow-up versus no-action colors, optional notes and unchanged raw matching evidence.
- [ ] Write failing tests that manual mode disables financial extraction edits but permits notes/decisions, explicit recheck uses Task 2, and export includes review method/manual initials/server time plus original comparison.
- [ ] Implement the direct entry point, choice dialog, banners, controls, labels and CSV columns using existing styles and save/initials conventions. No BILL financial actions or external credential handling.
- [ ] Run all `tests/ap_statements*.test.mjs` with `--test-isolation=none`; expect zero failures.
- [ ] Commit Task 3.

### Task 4: Release evidence and one final review

**Files:** Add `docs/ap-statement-rereview-rollout.md` and complete release tests where needed.

**Interfaces:** Consumes the schema capability, mode-aware reopen, pinned draft controller and manual UI. Produces documented deployment order and verified local release evidence, not production enablement.

- [ ] Document backup/test-project prerequisites, additive migration order, missing-capability behavior, preserving immutable history, manual self-report limitations and rollback without deleting evidence.
- [ ] Verify synthetic UI wide/narrow layouts, history entry to each mode, manual decision save/reload, explicit latest recheck and the linked Ace credit display. Preserve a synthetic screenshot outside temporary plan scratch.
- [ ] Run `python -X utf8 -m unittest discover -s tests -v`, all frontend tests, `node app/ap_statements/build.mjs`, and `git diff --check`. Record exact counts, skips and any blockers. Do not claim skipped live integration passed.
- [ ] Commit Task 4, then request one fresh whole-branch review using Native execution's final review requirements. Fix Critical/Important findings in one RED-to-GREEN pass, rerun affected/full suites, record all rulings and deferred minors, and do not dispatch a second reviewer.
- [ ] Preserve existing worktrees/ignored user history; clean only this plan's validated scratch after completion. Hand off locally without merging, pushing or applying SQL unless separately requested.
