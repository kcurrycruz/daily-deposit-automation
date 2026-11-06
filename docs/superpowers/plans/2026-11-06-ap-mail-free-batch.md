# Free AP Gmail Batch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. The owner previously selected native execution; preserve that choice. Steps use checkbox syntax for tracking.

**Goal:** Import and preliminarily scan Gmail statement PDFs twice daily through standard free GitHub Actions runners, without a Google Cloud billing account.

**Architecture:** A bounded pull coordinator reuses MailSync, the SQL queue/leases, MailProcessor and private Supabase storage. An owner-run OAuth helper writes the read-only Gmail grant directly to a repository secret. A minimal default-branch scheduler checks out an immutable reviewed AP source commit, while all mail and financial payloads remain outside the public repository/logs.

**Tech Stack:** Python 3.12, Node 24, existing Supabase RPCs, PDF.js/Tesseract/Playwright with Chromium sandbox, standard Ubuntu GitHub Actions, official GitHub CLI for owner authorization.

**Spec:** `docs/superpowers/specs/2026-11-06-ap-mail-free-batch-design.md` (approved in chat 2026-11-06).

## Global Constraints

- No new hosting subscription, payment method, paid model API, container registry, or Google Secret Manager/Tasks/Scheduler dependency is allowed.
- Standard GitHub-hosted Linux runners only, public repository only; no persistent Actions caches or uploaded artifacts.
- Target schedule: 08:17 and 16:17 America/New_York daily, including weekends; timing is not guaranteed.
- One job / fixed concurrency group, cancel-in-progress false, timeout 20 minutes; coordinator 840 seconds and at most 10 PDF starts; reserve at least 600 seconds before a new start.
- Keep existing 20 MiB / 100-page / 20-million-pixel protections, renewable SQL slot/lease, three-attempt cycle and immutable human-history protections.
- No Gmail/BILL/PDF content, credentials, raw exceptions, signed URLs or identifying metadata in public logs/summaries/artifacts.
- Only coordinator receives credentials; browser/domain children stay credential-free, network-blocked and sandboxed.
- Native execution, isolated workspace, RED then GREEN for behavioral changes, focused commits; one whole-branch review at the end.
- Real migrations, persistent Gmail/GitHub access, default-branch integration and activation require reviewed concrete targets and owner setup; no activation follows automatically from implementation approval.

## Review Focus

- A connection is paused or reconfigured between candidate read and claim: no new scan or old-account publication.
- Queued work is deferred, unavailable or repeatedly unclaimable: page progress and deadline prevent spinning/starving other candidates.
- Cancellation after extraction or publication acknowledgement loss: the next run reuses durable state and cannot duplicate or overwrite a human review.
- A public workflow is invoked on an unreviewed ref or the repository becomes private: no secret-bearing execution or switch to paid compute.
- CLI/OAuth/dependency/browser failure contains sensitive text: only allowlisted error codes and aggregate counts reach output.

## File map

- `workers/ap_mail/shared.py`: move reusable Gmail transport/token validation, lazy Gmail and processor construction out of the cloud adapter; preserve old imports.
- `workers/ap_mail/github.py`: fixed-repository grant reference, environment grant store, owner-side GitHub CLI secret writer.
- `workers/ap_mail/batch.py`: validated GitHub execution context, finite discovery/repair/pull/processing loop and redacted CLI result.
- `workers/ap_mail/authorize.py`: inject a grant store; mutually exclusive cloud/GitHub destinations with unchanged consent protections.
- `supabase/migrations/202611060001_ap_mail_batch.sql`: one additive service-only exact-connection pending-jobs read; no table rewrite or mutation behavior changes.
- `app/ap_mail/repository.py`: typed/validated wrapper for that read.
- `.github/workflows/ap-mail-batch.yml`: disabled-by-default guarded schedule/manual entry, immutable AP source ref, ephemeral standard runner setup.
- `app/ap_statements/frontend/mail-imports-ui.mjs`: truthful scheduled-check/retry/history copy without asserting an unknown backend cadence.
- `docs/ap-gmail-intake-free-setup.md`: owner-facing GitHub/Gmail/SQL/activation/recovery guide; existing cloud guide links to it as the owner's selected route.
- New focused Python/SQL/workflow fixtures below; extend existing mail UI/runtime/auth tests where behavior changes.

## Task 1: Service-only connection-scoped pending work

**Files:** create migration above, `tests/fixtures/ap_mail/batch_checks.mjs`, `tests/test_ap_mail_batch_schema.py`; modify repository wrapper and its tests.

**Interfaces:** SQL `ap_mail_batch_pending(p_workspace uuid,p_connection uuid,p_generation bigint,p_cursor uuid default null,p_limit integer default 25) -> jsonb`; Python `MailRepository.batch_pending(generation: int,cursor: str|None=None,limit: int=25) -> dict`. Return `items` (job_id, receipt_id, dispatch_generation, mode only) and `nextCursor` (last UUID or null).

- [x] Write failing SQL behavior checks: two connections in one workspace; another workspace; paused/inactive/stale generation; pending/sent outbox; queued/running/terminal/exhausted/not-yet-due jobs; duplicate dispatch generations; limit 1 pagination. Assert only current, due, pending jobs for the exact connection appear, with no financial fields. Invalid bounds fail. anon/authenticated/public cannot execute; service_role can. Old queued records and immutable history are unchanged.
- [x] Run `python -m unittest discover -s tests -p test_ap_mail_batch_schema.py -v`; expect RED because the new RPC does not exist. Run via the known complete Python environment; fixture uses existing PGlite dependency resolution.
- [x] Implement the additive security-definer read with fixed search_path, explicit limits (1..100), connection/workspace/generation binding and keyset cursor. Filter both job next_retry_at and outbox next_attempt_at. Revoke public/anon/authenticated and grant service_role. The query is read-only and never claims work.
- [x] Add wrapper tests asserting fixed config workspace/connection are passed and caller-supplied target overrides/invalid cursors/limits are rejected; implement `batch_pending` using `_rpc` and existing validators.
- [x] Run new tests plus `test_ap_mail_repository.py`, `test_ap_mail_schema.py` and `test_ap_mail_controls.py`; require GREEN. Commit this independently testable read.

## Task 2: Shared runtime and direct GitHub grant storage

**Files:** create shared.py/github.py and `tests/test_ap_mail_github.py`; modify runtime.py, authorize.py, test_ap_mail_runtime.py and test_ap_mail_authorize.py.

**Interfaces:** shared exports `BoundedTransport`, `DeferredGmail`, `GmailTokens` unchanged and `build_processor(repository,gmail_factory,caches=None) -> (MailProcessor,ReadCaches)`. GitHub exports `grant_reference(repository: str) -> str`, `EnvironmentGrantStore(reference: str,payload: str).read(reference: str) -> dict`, and `GitHubSecretStore(repository: str,run=subprocess.run).validate() -> None`, `.add(reference: str,payload: bytes) -> str`. Secret name is fixed `AP_MAIL_GMAIL_GRANT`; logical reference `github:kcurrycruz/daily-deposit-automation:AP_MAIL_GMAIL_GRANT`.

- [x] Write failing tests for direct secret persistence: gh invoked with argv/no shell, secret bytes only on stdin, exact repository/name, captured/redacted failures, no token file/stdout/argv, wrong repo rejected before owner consent. Include malformed/oversized/extra-account grants and absent CLI/auth. Grant output contains safe identity/reference metadata only.
- [x] Run `python -m unittest discover -s tests -p test_ap_mail_github.py -v`; expect RED for missing adapters. Add refactor regression tests proving cloud OIDC/Secret Manager validation remains unchanged and saved-extraction recompare does not initialize Gmail.
- [x] Extract shared classes without behavioral changes; retain compatible imports in runtime.py. Implement reusable processor construction with fixed repository and reusable ReadCaches; have Runtime.process delegate to it.
- [x] Implement strict reference/environment grant adapters. `GitHubSecretStore.validate` calls official CLI repo metadata before consent and verifies the expected public repository and authenticated CLI access. `.add` uses `gh secret set AP_MAIL_GMAIL_GRANT --repo kcurrycruz/daily-deposit-automation` with stdin, a bounded timeout, no shell and suppressed raw output. Do not acquire/create GitHub tokens in code.
- [x] Extend `authorize(client_path,expected_email,label_name,secret_name,*,store=None)`; validate an injected GitHub store before starting the browser. CLI chooses `--secret` (existing cloud) or `--github-repo` (GitHub); cannot select both. Keep PKCE/state/nonce, exact identity/label, scopes and direct persistence. Existing cloud CLI behavior remains supported.
- [x] Run GitHub/auth/runtime/processor/extraction tests and compile changed modules; require GREEN. Commit shared adapters and direct GitHub destination.

## Task 3: Finite batch coordinator

**Files:** create batch.py, `tests/test_ap_mail_batch.py`, `tests/fixtures/ap_mail/batch_run_check.py`; reuse existing synthetic processor/source/storage fixtures.

**Interfaces:** frozen `BatchConfig` holds existing `MailConfig`, fixed repository, grant_ref, budget_seconds=840,max_jobs=10. `validate_context(env: Mapping[str,str],event: dict) -> BatchConfig` validates explicit enablement, public exact repository, standard GitHub-hosted runner, allowed event, reviewed workflow/ref and immutable source SHA. `BatchRunner(repository,gmail_factory,process,*,clock=time.monotonic).run(*,budget_seconds=840,max_jobs=10) -> dict` returns only bounded aggregate counters, status and allowlisted reason codes. `main() -> int` assembles dependencies from environment and prints one safe JSON result.

- [x] Write failing context tests for disabled/private/other repository, unreviewed branch/workflow, PR events, self-hosted/custom runner, missing secrets, malformed IDs/source SHA, wrong secret binding and wrong mailbox/label. Assert rejection precedes Gmail/storage calls and raw exceptions/credential sentinels never reach output.
- [x] Write runner tests: empty/baseline/live poll, discovery error versus processing result, pause before read and between read/claim, stale connection generation, due exact-connection jobs, pagination, repeated not_claimed/transient jobs, zero busy waiting, 10-start cap, and no start with <600 seconds left. Preserve attempts and due dates; no Cloud Tasks/Secret Manager/HTTP app calls.
- [x] Run `python -m unittest discover -s tests -p test_ap_mail_batch.py -v`; expect RED for missing batch runner.
- [x] Implement context validation independently of Cloud Run. Load event JSON from the trusted runner file with a small size bound; never emit it. Explicit repo/ref/workflow constants must match the eventual main scheduler. Pass secrets only to this step and consume the fixed grant reference via EnvironmentGrantStore.
- [x] Implement repair -> bounded MailSync -> bounded stale recompare queue -> keyset pending pull -> sequential processor loop. Refresh connection binding/state before new work. Keep per-run seen identities/cursor so one deferred job cannot spin; inspect at most 10 pages of 25 candidates as well as the 10-start cap. Lazy Gmail preserves saved-extraction recompare. Aggregate known results with no payload output; catch unexpected failures as unavailable.
- [x] Run real synthetic fixtures through coordinator composition for interrupted extraction, lost publication acknowledgement and overlapping/manual invocations; verify one draft/link and unchanged completed human statement. Reuse existing SQL/publication tests for atomicity and old-generation denial; do not weaken their assertions.
- [ ] Run new tests and all `test_ap_mail_*.py` targeted tests (live integration remains explicitly skipped without approved targets); require GREEN. Commit the worker source. Record this immutable commit as the candidate AP release for Task 4; no placeholder source SHA may ship.

## Task 4: Guarded free workflow and release integration

**Files:** create `.github/workflows/ap-mail-batch.yml` and `tests/test_ap_mail_batch_workflow.py`; extend validation workflow only where needed to run new tests.

**Interfaces:** workflow env/vars: `AP_MAIL_BATCH_ENABLED`, `AP_MAIL_SUPABASE_URL`, `AP_MAIL_WORKSPACE_ID`, `AP_MAIL_CONNECTION_ID`, `AP_MAIL_BUCKET`; secrets: `AP_MAIL_SUPABASE_KEY`, `AP_MAIL_GMAIL_GRANT`. Literal source ref is Task 3's reviewed immutable 40-hex AP commit; no manual ref input. Runtime validates repository/workflow/main refs independently. Existing Cloud Run env/config stays separate.

- [ ] Write failing workflow tests asserting schedule `17 8,16 * * *` plus America/New_York; manual dispatch only; no push/PR trigger; reviewed main/public/enable guards; ubuntu-24.04 standard runner; timeout 20; fixed concurrency/cancel false; contents:read and no id-token/write permission; checkout credential persistence false; literal SHA ref; secrets only on processing step; no caches/artifacts/registry/paid services.
- [ ] Run new tests to observe RED. Verify actual repository default branch through available authenticated metadata/official API before constructing the main integration proposal; no branch change. Resolve official action commit SHAs from primary repositories and pin actions, not mutable tags.
- [ ] Implement workflow: validate trusted context, checkout reviewed AP SHA, install Python 3.12/Node 24/hash-locked dependencies and pinned npm dependencies, build bundled frontend assets, install matching Chromium with OS dependencies, and run sandboxed synthetic smoke BEFORE adding real secrets to the coordinator step. Never enable shell tracing of credentials or dump env/event. Whole job remains bounded at 20 minutes.
- [ ] Set processing step to `python -m workers.ap_mail.batch`; explicit enabled variable and connection pause remain independent gates. Do not enable either. Workflow is inactive until the minimal default-branch scheduler change is reviewed/applied separately.
- [ ] Run workflow/adapter tests; validate actual Linux/sandbox/OCR acceptance on standard Actions without financial credentials after a reviewed code push. If unavailable locally, report Linux acceptance pending and prepare the exact synthetic run; never substitute Windows results or --no-sandbox. Commit the disabled workflow. If worker fixes follow, update its pinned source commit before final release.

## Task 5: Truthful UI, setup and complete verification

**Files:** modify mail-imports-ui.mjs, `tests/ap_statements_mail_ui.test.mjs`, docs/ap-gmail-intake-setup.md; create docs/ap-gmail-intake-free-setup.md and `docs/superpowers/verification/2026-11-06-ap-mail-free-batch.md`.

**Interfaces:** keep existing UI/API data shapes. Replace five-minute claim with backend-neutral copy: new mail and queued requests run on the configured schedule; Last successful check remains authoritative. Free-route guide gives the exact twice-daily schedule and both pause/enable gates.

- [ ] Write a failing UI test rejecting the unconditional five-minute claim and requiring scheduled retry/history guidance while retaining last-success, pause, preliminary and credit-limit copy. Run `node --test --test-isolation=none tests/ap_statements_mail_ui.test.mjs` to confirm RED.
- [ ] Make only the necessary UI copy change, run mail UI/controller tests, and rebuild the frontend. Keep the optional cloud guide accurate and link the selected free route rather than describing every deployment as twice daily.
- [ ] Write complete owner setup for current public repository/main/DD-v2 split, official CLI owner login, Gmail API/Desktop OAuth without compute billing, applicable production/exemption consent route (Testing refresh tokens are not durable), direct grant secret writer, private Supabase key, connection/workspace IDs, recovery copy and ordered migrations including 202611060001, paused connection, default-branch scheduler pointer, one synthetic then one selected real PDF, activation and rollback. No placeholders may be executed; no secrets pasted into chat/files/clipboard.
- [ ] Run targeted mail Python tests, all AP Node tests, build, compilation and migration fixtures. Run the full Python suite once in the known complete environment if shared refactors/regressions justify it; never use the broken PyArrow environment. Record exact pass/skip counts and evidence limits, including pending live setup/Linux acceptance where applicable. Do not label manual/disabled deployment as automated production success.
- [ ] Run one whole-branch native review using the requesting-code-review skill; cover every Review Focus item and the immutable source pointer. Address findings with focused RED/GREEN tests, rerunning affected checks. No task-by-task review agents.
- [ ] Save verification evidence and commit. Update plan checkboxes accurately. Present ready code and any required owner setup; do not merge/push, grant new access, apply live migrations or enable imports without the corresponding authorized next step.

## Plan self-review

All spec sections map to Tasks 1-5; existing human review/history behavior is reused rather than reimplemented. Task 1 owns exact-connection due work; Task 2 owns OAuth/cloud compatibility and credential sinks; Task 3 owns budgets/recovery/redaction; Task 4 owns public/default-branch/ref/runner boundaries; Task 5 owns UI/rollout/regression evidence. Signatures and secret names above are the shared contracts. Live authority/consent, migrations and scheduled-run acceptance are explicit unfinished rollout work, not automatically satisfied by unit tests.
