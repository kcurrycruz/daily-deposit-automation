# AP shared workspace release validation

Production activation is blocked until the remaining cloud and recovery checks below pass. The owner configured a separate test deployment and Supabase workspace directly through Streamlit Secrets. Cloud tests use explicitly labeled synthetic records and PDFs only; no company financial files have been uploaded by this work.

## Local verification

For the large weekly export upgrade also follow `docs/ap-bill-snapshot-rollout.md`. Earlier cloud checks below predate `snapshot-v2` and do not validate its new SQL jobs, gzip artifacts, source-scoped queries or activation/version behavior. These require new authorized synthetic cloud checks before production.

Run Python unittest discovery in the QA environment, the full `tests/ap_statements*.test.mjs` Node suite, `node app/ap_statements/build.mjs`, `git diff --check`, and `python -m pip check`. On restricted Windows runners use Node `--test-isolation=none`; the build needs subprocess permission. SQL behavior tests use PGlite PostgreSQL with synthetic roles and data, not a live Supabase project. The Python SDK tests use HTTPX at the cloud boundary. Their mocks do not demonstrate real cloud access.

`tests/fixtures/ap_shared/browser.html` is a synthetic UI harness served from the repository root. It contains no finance files or credentials and does not test durable cloud storage. Keep it separate from the deployed AP entry point.

`tests/fixtures/ap_shared/streamlit_bridge_app.py` exercises the actual Streamlit component handshake with an injected synthetic service. Run it only locally; `?fail_once=1` injects a temporary bootstrap failure for retry validation. Mutation request IDs stay fixed across retries, while transport attempt numbers distinguish fresh deliveries and acknowledgements. This fixture contains no cloud credentials and does not save financial data.

## Cloud access and persistence checks

- [x] Owner authorizes a separate disposable test project and supplies credentials directly through Streamlit secrets, not chat.
- [ ] Apply the migration and configure a private bucket; verify anon/authenticated table and function access is denied, including existing broad Storage policies.
- [ ] Real server secret key works with the installed SDK. The opt-in `test_ap_shared_integration.py` read-only check runs with `AP_SYNTHETIC_INTEGRATION=1` and the test environment variables documented in that file.
- [ ] Import synthetic CSVs with 1,001 and 5,610 records. All normalized ordinals load exactly once; incomplete imports leave the previous source active.
- [ ] Upload several synthetic PDFs. Identical bytes reuse the statement; different bytes with the same filename remain distinct. An extractor failure retains an original and unconfirmed draft.
- [ ] Two independent unlocked sessions see the same saved source and PDFs without re-upload. Reopen a private PDF; verify its signed link fails after 300 seconds.
- [ ] Wrong password, cooldown, expiry, rotation and Lock AP prevent subsequent financial requests. Password/key values never occur in browser assets, messages or logs.
- [ ] Edit the same revision in two sessions. Stale saves conflict and preserve the unsaved edit. Retry a dropped save/completion acknowledgement with the same request ID; only one event is created.
- [ ] Complete with initials and no notes. Previous statement notes remain. Blank initials cannot complete. New imports/mappings do not change previous revision evidence.
- [ ] Migrate synthetic browser notes explicitly; cancel writes nothing. Demo data is excluded, missing originals are labeled incomplete, and no completion history is invented. Attach an original without erasing prior notes.
- [ ] Responsive layout, keyboard navigation, blur confirmation and AP → programs → Daily round trips work without losing deposit state.

## Recovery checks

- [ ] Back up the synthetic database and original bytes separately, with SHA-256 manifests.
- [ ] Restore into another authorized private test project. Verify record counts, immutable revisions, permissions and every original-file hash.
- [ ] An administrator identifies an expired, unreferenced upload prefix and removes only its staged test objects. Referenced originals and history remain readable.

## Current status

Local verification on October 14, 2026: Python ran 590 tests successfully with one live-integration skip; all 161 Node tests passed, including exact-revision review-date readback, readback-outage retry, concurrent-head protection, and edits made after a readback outage. The native unlock screen was checked at desktop and 390px mobile widths (350px card, no horizontal overflow). Frontend build and whitespace checks passed. Review of the unlock/date fix caught intervening-edit preservation and the Streamlit minimum version; the added regression failed before the preservation guard and passed after it, and the minimum was raised to 1.39 for keyed native containers. The earlier independent branch review identified four cross-layer issues; each received a failing regression followed by a passing fix. A synthetic Streamlit browser session recovered from a temporary bootstrap failure, and Lock AP removed the financial iframe.

Authorized test-cloud checks demonstrated: real server SDK connectivity, a private bucket with no broad object policies, and zero anon/authenticated AP table/function privileges; imports of 1,001 and 5,610 synthetic records; two PDFs uploaded together; invoice lookup past record 1,000 with leading zeros retained; same-vendor amount candidates, amount differences, and missing invoices; corrected fields and private original previews; blank-initial rejection and completion with QA initials and empty notes; duplicate-PDF reuse; and completed evidence retaining the earlier import after a new import. An AP → programs → Daily → programs → AP component remount reloaded the saved source, draft, and history without re-upload. This is single-session persistence evidence, not independent-session validation. Export reported success, but downloaded contents were not verified.

Two independent unlocked cloud-backed browser sessions, expired signed links, live wrong-password/cooldown/rotation checks, dropped-acknowledgement/concurrency tests, migration and recovery checks remain **unverified production-release gates**. Backup restoration has not been performed. The skipped integration test is not a pass. Keep the design's status short of Implemented until those checks and release are complete. Changes are deployed to the feature-branch test portal only; live `DD-v2` is unchanged.
