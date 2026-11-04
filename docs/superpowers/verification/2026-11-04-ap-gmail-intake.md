# AP Gmail intake verification — 2026-11-04

Implementation branch: `codex/ap-gmail-intake`. Baseline: `1feb83af6e1331751447e07f5a9c3483b38fb7be`. This is a **local implementation and staged rollout package**, not a connected Gmail service or live deployment.

## Verified locally

| Check | Observed result |
|---|---|
| AP frontend `node --test --test-isolation=none tests/ap_statements*.test.mjs` | 473 passed |
| Final mail controls/publication/sources/runtime/OAuth/deploy/integration/browser subset | 29 run, 28 passed, one explicitly unconfigured live integration skipped |
| 100-PDF source-backed burst | Passed; real bundled reader, domain matching, embedded PostgreSQL, synthetic Gmail/Tasks/storage boundaries |
| Real browser UI | Ten real status refreshes preserve canvas, note value/selection/focus/scroll, historical form and a single bootstrap; completed imported statement opens read-only |
| Shared PostgreSQL behavior | Additive migration chain, ACL/RLS, inventory/outbox CAS, lease/slot generations, retry cap, immutable publication, source/head conflicts, replay and controls verified in PGlite |
| Terraform 1.17.1 | Actual `init -backend=false`, `fmt -check`, `validate` passed with locked Google/Google Beta 8.10.0 |
| Worker Python lock | 48 pinned packages, hash-required install in isolated Python 3.12 environment, `pip check` clean |
| Dependency checks | Public OSV batch: zero advisories for the 48 pinned versions; npm audit: zero findings for worker and frontend production dependencies at this check |
| Frontend build | `node app/ap_statements/build.mjs` passed using pinned direct dependencies; frontend and worker npm lockfiles included |
| Offline PDF smoke | Passed with Windows Chrome, Chromium sandbox enabled; no remote assets allowed |

The complete repository Python suite is pending the final review/fix pass. Its previous initial run was 872 tests: six missing-PGlite environment failures, one unconfigured integration skip, and 865 passes. After installing the pinned frontend development dependencies, the exact six schema checks passed. That earlier run is not represented as a final whole-branch pass.

## Source-backed burst and limits of the measurements

100 distinct generated PDFs, 10 discovery retransmissions, a pre-existing completed human statement, and 200 synthetic BILL records went through actual parsing, preliminary comparison and SQL publication. Injected failures covered an expired claim, lost task-enqueue acknowledgements, a lost immutable-upload reply, interruption after copying an original, interruption after saved extraction, and a lost publication acknowledgement. Keyset recompare reuses all saved extractions in batches of at most 50.

| Metric | Local observation |
|---|---:|
| PDF receipts / private originals / preliminary drafts | 100 / 100 / 100 |
| Preliminary invoice rows found | 200 |
| Actual PDF reads / Gmail attachment downloads | 100 / 100 |
| Full synthetic BILL-record table reads | 1 |
| Recovered paths / lost publication acknowledgement | 3 / 1 |
| Maximum real attempts observed in one cycle | 2 (configured cap 3 also tested separately) |
| Pre-existing human revision/history | Unchanged; one prior completion event retained |
| Total harness time including recovery and recompare | 307.787 seconds |
| First PDF read / later median | 1.629 / 1.554 seconds |
| Idle / between-job burst SQL-RPC median | 0.923 / 0.880 milliseconds |
| Embedded SQL child peak RSS | 1,069,984 KiB |

These are small digital fixtures on this Windows computer with an embedded SQL process. The SQL-memory figure includes the PGlite runtime and excludes the complete browser process tree. The latency samples do not establish cloud concurrency, production export performance, total worker peak memory, or a guaranteed lack of AP slowdown. Linux OCR/large-source/cache and actual foreground/cloud latency remain deployment measurements.

The source-backed burst exposed a real legacy-import bug: `snapshot_manifest` can be SQL NULL for row-based imports. A regression test failed with `AttributeError`, then passed after the read facade treated that field as absent metadata. UI tests also caught imported-page adoption and human-completed receipt presentation/navigation; both now pass without writing automated completion decisions.

## Required external acceptance — not passed here

- Docker/Linux container build and sandboxed OCR smoke. Docker is not available in this environment; the supplied CI job is a gate, not a claimed result.
- An explicitly authorized synthetic Supabase/cloud/mailbox round trip: real competing PostgreSQL RPC transactions, private storage, Google IAM/OIDC/Tasks/Gmail, exact synthetic PDF hash and a fresh selected email. The opt-in harness refuses the known production project `uhwpnbntjsopuilouize` before credential/network access. Once enabled, missing prerequisites fail rather than skip.
- Actual cloud region, billing/resource budget, image digest, owner identity and OAuth production/verification choice.
- Recovery copies/counts and migration application to the confirmed live database.
- Owner Gmail consent and one owner-selected end-to-end statement before the five-minute schedule is enabled.

No Cloud Run service, schedule, task, Gmail authorization, secret value or production migration was created/applied during this local work. Terraform configures the queue and schedule paused. No merge or push has been performed for this feature.

## Release inventory and recovery

Use the exact ordered prerequisite/new migration inventory and pause/reconnect/rollback steps in [the setup guide](../../ap-gmail-intake-setup.md). Existing originals, immutable revisions, completion events and earlier duplicate scans/reviews stay in place. Rollback hides/disables the new capability and stops scheduling; it does not delete financial evidence.

The optional `mail-synthetic` workflow requires manual dispatch, the protected `ap-mail-synthetic` environment, explicit test project/workspace allowlists and a workload-identity test runner. It does not apply infrastructure, change queue state, send email, or accept a company/financial PDF: the selected Gmail attachment must exactly hash to `workers.ap_mail.smoke.synthetic_pdf()`.

## Execution rulings

The execution ledger's decisions are copied here at final handoff, including their tradeoffs. Final whole-branch review and full-suite results are still pending.
