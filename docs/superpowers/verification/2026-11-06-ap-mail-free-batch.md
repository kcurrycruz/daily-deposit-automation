# Free AP Gmail batch verification

Status: locally implemented; final regressions/review in progress. No live activation.

## Evidence so far

- Mailbox-scoped SQL/repository read: RED then GREEN, 16/16 scoped read and existing control/schema checks passed.
- Direct GitHub grant storage/shared runtime: RED then GREEN, 31/31 OAuth/runtime/processor/real extraction checks passed.
- Finite coordinator/discovery: RED then GREEN, 21/21 focused checks passed.
- Real synthetic batch: 3 private originals, 3 preliminary drafts, 6 invoice matches; competing invocation, interrupted extraction/comparison and lost publish acknowledgement recovered; prior human history unchanged.
- Complete affected mail suite before final activation-gate change: 112 run, 111 passed, 1 unconfigured live integration skip, 0 failures (326.664 seconds).
- Separate manual/scheduled activation: RED then GREEN, 13/13 batch/workflow tests passed.
- Workflow/deploy/runtime/credential checks: 15/15 passed; worker imports passed using only its hash-locked deployment dependencies.
- AP frontend: 480/480 passed; UI scheduled-copy test RED then GREEN, 17/17 focused UI/controller checks passed.
- Asset build and direct py_compile of changed Python source passed.
- Final affected mail rerun after activation/UI changes: pending.

## 100-PDF backtest

Actual embedded PostgreSQL and shared parser/matcher produced 100 receipts, 100 private objects, 100 awaiting-review drafts and 200 found rows. There were 101 statements including one prior human completion, 1 unchanged completion event, 0 running jobs, 3 recovered attempts, maximum 2 attempts per item, and 1 source-table read. Wall time was 263.988 seconds. These are local digital fixtures, excluding cloud/network latency, real large-export performance and total browser-tree memory.

## Release and external gates

Official GitHub metadata confirms public repository kcurrycruz/daily-deposit-automation and default main. Official v6 action refs were verified: checkout d23441a48e516b6c34aea4fa41551a30e30af803; setup-python ece7cb06caefa5fff74198d8649806c4678c61a1; setup-node 249970729cb0ef3589644e2896645e5dc5ba9c38.

Candidate worker release: 7a8f3356541f5e8234a48eb0b1053afe54f3a2c4. Both scheduler source refs match it; any worker fix requires repinning. Main integration is a minimal separate workflow change; no deployed/default branch was changed.

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
- Ruling: separate AP_MAIL_SCHEDULE_ENABLED from AP_MAIL_BATCH_ENABLED so manual acceptance can run while automatic schedule stays off — resolves contradictory activation steps — one additional false-by-default variable; context/workflow tests RED then GREEN, 13 tests passed. Source pin must advance to this worker fix before final review.

## Fresh review

Pending. No production acceptance or scheduled-run success is claimed.
