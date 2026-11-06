# Free AP Gmail batch verification

Status: implementation and final local verification complete. One fresh review finding fixed. No shared push or live activation.

## Verified evidence

- Mailbox-scoped SQL/repository read: RED then GREEN, 16/16 scoped read and existing control/schema checks passed.
- Direct GitHub grant storage/shared runtime: RED then GREEN, 31/31 OAuth/runtime/processor/real extraction checks passed.
- Finite coordinator/discovery: RED then GREEN, 21/21 focused checks passed.
- Real synthetic batch: 3 private originals, 3 preliminary drafts, 6 invoice matches; competing invocation, interrupted extraction/comparison and lost publish acknowledgement recovered; prior human history unchanged.
- Complete affected mail suite before final activation-gate change: 112 run, 111 passed, 1 unconfigured live integration skip, 0 failures (326.664 seconds).
- Separate manual/scheduled activation: RED then GREEN, 13/13 batch/workflow tests passed.
- Workflow/deploy/runtime/credential checks: 15/15 passed; worker imports passed using only its hash-locked deployment dependencies.
- AP frontend: 480/480 passed; UI scheduled-copy test RED then GREEN, 17/17 focused UI/controller checks passed.
- Asset build and direct py_compile of changed Python source passed.
- Final affected mail suite after the review fix and final source repin: 117 run, 116 passed, 1 explicitly unconfigured live integration skip, 0 failures (326.339 seconds). Command: python -m unittest discover -s tests -p test_ap_mail_*.py -v, using sandboxed installed Chrome.
- Final AP frontend rerun: 480/480 passed, 0 skipped or failed (865.745 ms).
- Git diff whitespace checks passed; the final worker source is f78eaae29bfd4c595b7a81a08dff8e0b74902275.

## 100-PDF backtest

Actual embedded PostgreSQL and shared parser/matcher produced 100 receipts, 100 private objects, 100 awaiting-review drafts and 200 found rows. There were 101 statements including one prior human completion, 1 unchanged completion event, 0 running jobs, 3 recovered attempts, maximum 2 attempts per item, and 1 source-table read. Wall time was 263.988 seconds. These are local digital fixtures, excluding cloud/network latency, real large-export performance and total browser-tree memory.

## Release and external gates

Official GitHub metadata confirms public repository kcurrycruz/daily-deposit-automation and default main. Official v6 action refs were verified: checkout d23441a48e516b6c34aea4fa41551a30e30af803; setup-python ece7cb06caefa5fff74198d8649806c4678c61a1; setup-node 249970729cb0ef3589644e2896645e5dc5ba9c38.

Candidate worker release: f78eaae29bfd4c595b7a81a08dff8e0b74902275. Both scheduler source refs match it; any worker fix requires repinning. Main integration is a minimal separate workflow change; no deployed/default branch was changed.

No shared push, main integration, live migration, secret/variable setup, Gmail consent or schedule activation has occurred. Linux/Docker acceptance is pending an authorized reviewed-code push and the Ubuntu validation/container workflow. Sandboxed Windows Chrome proves local behavior only. The affected mail suite and all AP frontend tests cover this isolated worker/copy change; unrelated deposit and large duplicate tests were not rerun.

## Execution rulings

- Ruling: retain native execution and proceed under explicit implementation approval instead of requesting another permission for the expanded task plan — scope is unchanged — owner can correct the documented defaults before live activation.
- Ruling: managed worktree call was unresponsive, stopped and verified unregistered; use native Git fallback in ignored .worktrees/mail-free — protects DD-v2 without waiting indefinitely — any later managed attachment must be inspected before reuse.
- Ruling: bash is unavailable; reproduce workspace/task brief/ledger bookkeeping with Python on Windows — same identity and per-task records — script conveniences need manual parity checks.
- Ruling: npm executable is absent; pnpm import reproduced the existing npm lock, frozen install used identical playwright 1.62.1 and integrity, transient pnpm lock removed — no dependency/product changes — Linux workflow still uses npm ci.
- Ruling: MailSync previously queued its own stale page; add default-true queue_stale option and let batch pass false then queue exactly one page of 50 even after discovery failure — avoids double scheduling and permits saved-extraction recompare when Gmail is unavailable — cloud behavior remains unchanged and both paths are tested.
- Ruling: paused runs still reconcile expired leases, while claiming/discovery/stale queue stay stopped — preserves prior recovery semantics — cleanup may update an expired queued attempt but cannot complete a human review.
- Ruling: add pinned PyYAML 6.0.3 as a test-only dependency and install it in validation CI — semantic workflow checks need a real parser, none existed in the test environment — adds test setup only, no Streamlit/worker dependency or hosting cost.
- Ruling: no Linux/Docker environment is available locally and a shared push has not been authorized for this new feature; Linux sandbox/OCR acceptance remains explicitly pending the reviewed code push and Validate Application workflow — Windows evidence is not presented as Linux acceptance — deployment remains disabled.
- Ruling: separate AP_MAIL_SCHEDULE_ENABLED from AP_MAIL_BATCH_ENABLED so manual acceptance can run while automatic schedule stays off — resolves contradictory activation steps — one additional false-by-default variable; context/workflow tests RED then GREEN, 13 tests passed. Both immutable source refs were advanced after the verified fixes.

## Fresh review

One fresh whole-branch review covered e6edd3a..1d50a90, including the plan, approved design, execution rulings and Review Focus inputs. It found 0 Critical, 1 Important and 0 Minor findings.

Important: inherited GH_HOST could redirect owner CLI repository validation and secret storage away from github.com. The reproducing test test_inherited_enterprise_host_cannot_redirect_the_gmail_grant failed first; _call now forces GH_HOST=github.com for every subprocess. GitHub adapter tests then passed 8/8, direct compilation passed, and the full affected mail and AP frontend suites above passed. Fix commit: f78eaae. Both immutable workflow source refs were advanced to it. No second review was dispatched.

Deferred minors: none. No production acceptance or scheduled-run success is claimed.

The reviewer declined to judge four external or out-of-range areas; rulings on each follow.

1. Linux sandbox/OCR and setup duration: require the prepared Ubuntu synthetic workflow before credentials or activation. Windows results do not establish Linux acceptance. Cost if wrong: deployment must be revised while imports remain disabled.
2. Real Gmail/Supabase and scheduled success: require confirmed targets, owner consent, migrations, a selected real-PDF acceptance run and an observed scheduled run. Cost if wrong: live setup may need correction; no automatic success is asserted.
3. Generated vendor/bridge files: restore build-only line-ending drift after the asset build, because there was no substantive change. Final regressions used committed assets. Cost if wrong: a necessary generated asset would need a separate reviewed update.
4. Unrelated deposit/large-duplicate suites: rely on unchanged code, existing baseline evidence and fresh complete affected-mail/AP suites; avoid an unrelated 48-minute rerun. Cost if wrong: a latent cross-area regression would remain outside fresh coverage.

## Preserved execution ledger

The complete local ledger is preserved below before plan-only scratch cleanup. This also records environment substitutions and their limitations.

# SDD ledger — plan: docs/superpowers/plans/2026-11-06-ap-mail-free-batch.md



BASE: 3bdc8b139445196b9e29da62747f2d4ed09a31c0

Execution: native; design and implementation authorized by owner.

Pre-flight 1->3: batch_pending exact connection/generation/cursor -> runner; aligned.

Pre-flight 2->3: shared construction and environment grant -> runner; aligned.

Pre-flight 3->4: reviewed immutable worker commit -> literal checkout SHA; aligned.

Pre-flight 4->5: disabled main scheduler -> explicit owner activation; aligned.

Ruling: retain native execution and proceed under explicit implementation approval instead of requesting another permission for the expanded task plan — scope is unchanged — owner can correct the documented defaults before live activation.

Ruling: managed worktree call was unresponsive, stopped and verified unregistered; use native Git fallback in ignored .worktrees/mail-free — protects DD-v2 without waiting indefinitely — any later managed attachment must be inspected before reuse.

Ruling: bash is unavailable; reproduce workspace/task brief/ledger bookkeeping with Python on Windows — same identity and per-task records — script conveniences need manual parity checks.

Baseline: repository tests 5/5 in complete ap-mail-final Python environment.

Task 1: in progress; BASE 3bdc8b139445196b9e29da62747f2d4ed09a31c0

Task 1: complete (commits 3bdc8b1..837ae04, tests: repository + batch SQL + existing SQL + mail controls, 16/16 passed). New wrapper and SQL read observed RED then GREEN. Synthetic fixture parameter type corrected before valid RED.

Task 2: in progress; BASE 837ae042a1330a5ed18e783c3cff49a5d84f442f

Task 2: complete (commits 837ae04..23e2992, tests: GitHub + OAuth + runtime + processor + real extraction 31/31 passed in 31.463s; compile passed). New adapter assertions observed RED then GREEN.

Ruling: npm executable is absent; pnpm import reproduced the existing npm lock, frozen install used identical playwright 1.62.1 and integrity, transient pnpm lock removed — no dependency/product changes — Linux workflow still uses npm ci.

Task 2 environment: first broad run 29 passed / 2 extraction failures from missing Playwright; installed locked worker packages, built assets and set AP_MAIL_BROWSER_BINARY to existing sandboxed Chrome; complete rerun 31/31 green. No application patch for those failures.

Task 3: in progress; BASE 23e299273ba555c2f6a4d0344d3a742aad5a923e

Task 3: RED batch context/coordinator assertions 8 failures; new MailSync queue_stale option RED then GREEN; 21 coordinator/sync tests passed.

Task 3: real SQL/PDF synthetic batch integration passed (3 private originals, 3 drafts, 6 matches, overlapping invocation, interrupted extraction/comparison, lost publish acknowledgement, existing completed history preserved). All affected mail suite now running.

Ruling: MailSync previously queued its own stale page; add default-true queue_stale option and let batch pass false then queue exactly one page of 50 even after discovery failure — avoids double scheduling and permits saved-extraction recompare when Gmail is unavailable — cloud behavior remains unchanged and both paths are tested.

Ruling: paused runs still reconcile expired leases, while claiming/discovery/stale queue stay stopped — preserves prior recovery semantics — cleanup may update an expired queued attempt but cannot complete a human review.

Task 2 verification clarification: compileall traversed node_modules and warned about a long dependency path; direct py_compile of every changed Python source passed without warnings.

Task 4 preflight research: official GitHub REST repository metadata confirms public=true/default_branch=main. Official action v6 refs verified via git ls-remote: checkout d23441a48e516b6c34aea4fa41551a30e30af803, setup-python ece7cb06caefa5fff74198d8649806c4678c61a1, setup-node 249970729cb0ef3589644e2896645e5dc5ba9c38. No deployment/integration performed.

Task 3: complete (commits 23e2992..6082e71, tests: all mail 112 run / 111 passed / 1 unconfigured live skip, 0 failures, 326.664s; 100-PDF backtest passed). Candidate immutable source 6082e711c700876324a7734fec07a229ca4a165b.

Task 4: in progress; BASE 6082e711c700876324a7734fec07a229ca4a165b

Task 4: complete locally (commits 6082e71..ea84c36, workflow/deploy/runtime/GitHub regression tests 15/15 passed; worker imports passed in hash-locked runtime-only environment). Default main verified; source pinned 6082e711c700876324a7734fec07a229ca4a165b; no push/main integration or activation.

Ruling: add pinned PyYAML 6.0.3 as a test-only dependency and install it in validation CI — semantic workflow checks need a real parser, none existed in the test environment — adds test setup only, no Streamlit/worker dependency or hosting cost.

Ruling: no Linux/Docker environment is available locally and a shared push has not been authorized for this new feature; Linux sandbox/OCR acceptance remains explicitly pending the reviewed code push and Validate Application workflow — Windows evidence is not presented as Linux acceptance — deployment remains disabled.

Task 5: in progress; BASE ea84c365c25a4657466ca791057396d31ed06a6c

Task 5: UI scheduled-copy test observed RED then GREEN, 17 UI/controller tests passed.

Ruling: separate AP_MAIL_SCHEDULE_ENABLED from AP_MAIL_BATCH_ENABLED so manual acceptance can run while automatic schedule stays off — resolves contradictory activation steps — one additional false-by-default variable; context/workflow tests RED then GREEN, 13 tests passed. Source pin must advance to this worker fix before final review.

Task 5: candidate worker source advanced after activation fix to 7a8f3356541f5e8234a48eb0b1053afe54f3a2c4; both workflow refs repinned.

Main integration proposal: origin/main d1c59f878915fa3f13796f43767818f58b48f406 lacks the intake workflow; main-scheduler.patch contains only the added scheduler. No main mutation or push performed.
Fresh final review at 1d50a90: 0 Critical, 1 Important, 0 Minor. Important GH_HOST destination binding reproduced RED; forced GH_HOST=github.com for every CLI subprocess; GitHub tests 8/8 GREEN and py_compile passed. Fix source f78eaae29bfd4c595b7a81a08dff8e0b74902275; both workflow refs repinned. Complete affected suite and AP Node rerun pending.
Final: Ruling: Linux and live acceptance remain rollout gates, not claimed local completion — no Linux host or real consent/targets configured — imports stay disabled until authorized checks.
Final: Ruling: restore only generated vendor/bridge line-ending drift from our clean worktree after build verification — no meaningful content diff and none belongs in this feature — final regressions use the actual committed assets.
Final: Ruling: unrelated deposit/large duplicate suites were not rerun because runtime changes are mail-only and all AP frontend plus mail/source/schema regressions cover impacted behavior — avoids an unrelated 48-minute rerun — unrelated areas retain earlier baseline evidence rather than fresh coverage.

Task 5: complete locally; final affected mail suite 117 run / 116 passed / 1 unconfigured live skip / 0 failures in 326.339s; final AP Node suite 480/480 in 865.745ms. Asset build and changed Python compilation passed.
Final: fixed inherited GH_HOST secret destination — test_inherited_enterprise_host_cannot_redirect_the_gmail_grant RED then GREEN, adapters 8/8; complete affected mail and AP frontend suites green.
Final: minor (deferred): none.
Final: Ruling: Linux acceptance remains an explicit gate — local Windows tests cannot prove Linux sandbox/OCR/setup duration — deployment may require correction before credentials or activation.
Final: Ruling: real Gmail/Supabase and scheduled success remain unverified — no live setup or new consent performed — owner-selected acceptance and an observed scheduled run are required before claiming live success.
