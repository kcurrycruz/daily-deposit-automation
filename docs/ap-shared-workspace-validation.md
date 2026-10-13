# AP shared workspace release validation

Production activation is blocked until an authorized synthetic Supabase project passes the cloud and recovery checks below. The current implementation has local automated coverage, but no project credentials have been configured and no company data has been uploaded by this work.

## Local verification

Run Python unittest discovery in the QA environment, the full `tests/ap_statements*.test.mjs` Node suite, `node app/ap_statements/build.mjs`, `git diff --check`, and `python -m pip check`. On restricted Windows runners use Node `--test-isolation=none`; the build needs subprocess permission. SQL behavior tests use PGlite PostgreSQL with synthetic roles and data, not a live Supabase project. The Python SDK tests use HTTPX at the cloud boundary. Their mocks do not demonstrate real cloud access.

`tests/fixtures/ap_shared/browser.html` is a synthetic UI harness served from the repository root. It contains no finance files or credentials and does not test durable cloud storage. Keep it separate from the deployed AP entry point.

## Cloud access and persistence checks

- [ ] Owner authorizes a separate disposable test project and supplies credentials directly through local or Streamlit secrets, not chat.
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

Cloud Storage access, real credential compatibility, two independent cloud-backed browser sessions, expired live links and backup restoration remain **unverified deployment blockers**. The skipped integration test is not a pass. Keep the design's status short of Implemented until those checks and release are complete.
