# AP Gmail intake verification — 2026-11-04

Implementation branch: `codex/ap-gmail-intake`. Baseline: `1feb83af6e1331751447e07f5a9c3483b38fb7be`. This is a **local implementation and staged rollout package**, not a connected Gmail service or live deployment.

## Verified locally

| Check | Observed result |
|---|---|
| AP frontend `node --test --test-isolation=none tests/ap_statements*.test.mjs` | 479 passed |
| Whole repository `python -m unittest discover -s tests -v` | 960 run in 2,877.133 seconds: 958 passed, two explicitly unconfigured live integrations skipped; zero errors/failures |
| Python compilation `python -m compileall -q app workers streamlit_app.py` | Passed |
| 100-PDF source-backed burst | Passed; real bundled reader, domain matching, embedded PostgreSQL, synthetic Gmail/Tasks/storage boundaries |
| Real browser UI | Ten real status refreshes preserve canvas, note value/selection/focus/scroll, historical form and a single bootstrap; completed imported statement opens read-only; saved preliminary amount differences render, page and clear on lock/close; phone table scrolls within its panel |
| Existing duplicate-rule scale regression | 223,425 and 500,000 records passed repeated v5 scans; stable keys, expected findings, and bounded memory/step work |
| Existing BILL range regression | 223,425-record recent range and 500,000-record full range passed; source unchanged, parity/cache/memory/step limits held |
| Shared PostgreSQL behavior | Additive migration chain, ACL/RLS, inventory/outbox CAS, lease/slot generations, retry cap, immutable publication, source/head conflicts, replay and controls verified in PGlite |
| Terraform 1.17.1 | Actual `init -backend=false`, `fmt -check`, `validate` passed with locked Google/Google Beta 8.10.0 |
| Worker Python lock | 48 pinned packages, hash-required install in isolated Python 3.12 environment, `pip check` clean |
| Dependency checks | Public OSV batch: zero advisories for the 48 pinned versions; npm audit: zero findings for worker and frontend production dependencies at this check |
| Frontend build | `node app/ap_statements/build.mjs` passed using pinned direct dependencies; frontend and worker npm lockfiles included |
| Offline PDF smoke | Passed with Windows Chrome, Chromium sandbox enabled; no remote assets allowed |

The final comprehensive command passed in a separate temporary Python 3.12.14 environment with openpyxl3.1.5, Streamlit1.66.1, xlrd2.0.2, Supabase2.33.0, pandas3.0.1 and complete PyArrow26.0.0. The earlier final attempt had one environment error: an incomplete PyArrow namespace prevented pandas from importing in an existing Daily Deposit test. That error reproduced standalone; no application change was needed. The exact failed test and mail runtime preflight passed (5/5), then the entire 960-test suite passed in the clean environment. The two skips are `test_real_concurrent_claim_and_publish_private_cloud_round_trip` and `test_private_bucket_and_server_round_trip`; neither authorized live test environment is configured.

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
| Total harness time including recovery and recompare | 265.188 seconds |
| First PDF read / later median | 1.632 / 1.550 seconds |
| Idle / between-job burst SQL-RPC median | 1.208 / 0.806 milliseconds |
| Embedded SQL child peak RSS | 1,057,628 KiB |

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

The independent whole-branch review at `c446446` found six Important issues and no Critical or Minor issues. All six entered one regression-test-led fix pass: label-change eligibility, expanded-list freshness, old-account retry fencing, private-preview cleanup at lock, workspace-wide candidate accumulation, and access to saved preliminary rows. All six fixes reproduced their failures before implementation and passed targeted checks, the real browser, all 479 frontend tests and the clean full Python suite (958 passed; two explicit live skips). No second review was dispatched. Deferred minors: none.

| Review finding | Regression evidence in the fix pass |
|---|---|
| Unrelated Gmail label changes could import baseline mail | `test_unrelated_label_changes_never_import_old_baseline_mail`, RED→GREEN; sync suite 12/12 |
| Expanded pages could retain stale statuses/versions | `fresh server versions replace cached head and already-loaded older receipt rows`, RED→GREEN; bounded SQL refresh verifies fixed-workspace IDs |
| Old-account receipts could be retried under a new account | SQL generation/account replacement, forced-gen claim denial and `test_old_account_receipt_is_rejected_before_message_lookup`, RED→GREEN |
| Original PDF could remain open after AP locks | Real-browser denial removes dialog and cancels its timer; all current-generation action denials clear private views, while obsolete denials cannot relock a newly enabled session; re-enable resumes exactly one fresh poll, RED→GREEN |
| Unrelated history filled the semantic matching buffer | Streamed unrelated-vendor and same-vendor/different-reference history plus exact-byte lookup, RED→GREEN |
| Automatic findings were inaccessible | Authorized paginated SQL evidence, found/amount view and late-response/lock tests, RED→GREEN; actual desktop/mobile browser passed |

Saved preliminary evidence is authorized before and after IO, paged to 50 rows and a bounded reply, and pinned to the receipt version. Polling marks open evidence stale when that version changes. These rows remain separate from human resolutions/completion history. A read-only evidence panel labels its export and comparison time, shows findings/candidates/amount differences, and explains freshness/range/credit coverage.

The following decisions were made in order, with their tradeoffs:

1. skill shell helpers require Bash, which is unavailable in the installed Windows Git runtime — use equivalent plan-scoped Python brief/test-ledger commands — costs extra maintenance of execution bookkeeping, not product behavior.

2. processing attempts persist across dispatch repair; only explicit retry starts a fresh attempt budget — otherwise task-name generation recovery would reset the cap indefinitely — cost if wrong is manual retry needed sooner, not silent unbounded scans.

3. malformed/withdrawn or uncertain historical emails have message-level attention records instead of fabricated PDF receipts — there may be no verified PDF identity/size to store — cost if wrong is an additional message-attention row/control in Email imports; originals and valid attachments remain available. Email imports lists these records and provides retry/skip controls.

4. extend outbox_page with a pending/sent state filter and persist a separate dispatch cursor — otherwise a stable first page starves later queued or missing tasks — cost if wrong is extra metadata and a recovery cycle delay, not duplicate financial documents.

5. the current interactive reader returns no rows for the synthetic fragmented dot-matrix fixture — retain it as a negative quality-parity test and route automatic reading to Needs attention rather than changing vendor parser rules in this feature — cost if wrong is manual review of some visually legible scans; no false empty success. Existing dot-matrix recovery unit tests remain green.

6. cap comparison IPC/results at 1MiB, matching work at 1,000,000 row-record pairs and candidate appearances at 2,000 — overly broad results fail to Needs attention instead of truncating evidence into Missing — cost if wrong is manual review for unusually ambiguous statements.

7. preliminary-only machine reads may use the hash-verified current immutable working artifact while protection refresh is pending, pinning the live epoch and exposing rangeRefreshPending; human APIs stay strict — automatic draft inserts otherwise block every later unattended comparison — cost if wrong is preliminary coverage needing human refresh; excluded records stay archive review, never Missing.

8. a new stale-source comparison after a successfully completed cycle gets three fresh attempts; dispatch repair and retries within a failed cycle keep their budget — otherwise a valid draft becomes permanently unrefreshable after three successful source updates — cost if wrong is extra bounded comparisons across legitimate source/protection changes, with no repeat OCR.

9. use fixed project-specific custom Cloud Run audiences with pinned caller identities, while task URLs remain private run.app origins — avoids a Terraform service depending on its own not-yet-created URI — cost if wrong is denied invocation until matching audiences are configured, not a public bypass.

10. Docker/daemon is unavailable here; keep Linux/container and authorized synthetic Cloud Run/database acceptance as explicit rollout gates, with offline smoke and CI jobs supplied, rather than disabling Chromium sandbox or claiming a Windows result covers Linux — cost if wrong is additional environment work before activation; no live schedule enabled. Portable checksum-verified Terraform was obtained and its real fmt/validate ran successfully.

11. run the expensive whole-repository regression after the independent review/fix pass, with focused suites and the full 100-PDF source-backed burst green before review — ensures the approximately 45-minute scale suite sees the final code and avoids routinely repeating it for review fixes — cost if wrong is discovering an unrelated regression later; it still blocks handoff until resolved.

12. history-wide semantic matching must not accumulate unrelated statements — stream every candidate page, retain only shared-vendor/shared-reference candidates through the existing browser-domain rules, and perform exact-byte lookup separately — cost if wrong is manual attention for genuinely oversized relevant evidence, with complete pages and source/mapping fences still required.

13. the reviewer set aside actual Linux/Cloud Run/IAM/OAuth/storage/database acceptance — keep all of it as mandatory external rollout gates; the branch stays local and scheduling stays paused — cost if wrong is additional setup/testing time before real emails can import, rather than claiming an untested live service.
