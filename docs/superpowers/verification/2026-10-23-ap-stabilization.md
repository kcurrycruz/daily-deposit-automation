# AP stabilization verification — October 23, 2026

## Scope and release boundary

Implements the approved reliability design and plan in the existing embedded AP app. No matching/financial rules, schema, credentials, BILL data, saved originals, completion history, or Daily Deposit workflows were changed by this pass. All QA uses synthetic local data. Nothing has been merged, pushed, or deployed.

The earlier statement re-review migration `202610230001_ap_statement_rereview.sql` remains a separate, unapplied release prerequisite for that earlier feature; stabilization adds no migration.

## Automated evidence

- Baseline AP frontend: 393 passing.
- Final complete AP frontend: 421 passing, zero failures; `artifacts/ap-stabilization-frontend-final.log`.
- Affected backend: `PYTHONPATH=tests`, Python `-X utf8 -m unittest test_ap_duplicates_operations -v`: 14 passing, including timing metadata, source replacement, expired/foreign lease ownership, and cross-thread packaging; `artifacts/ap-stabilization-task3-python-green.log`.
- App build succeeds with `node app/ap_statements/build.mjs`. The bridge bundle is regenerated; guard is a static classic script loaded before modules.
- Complete backend suite: 735 tests in 874.560s, zero failures, one optional live integration skip (authorized synthetic Supabase project not configured); `artifacts/ap-stabilization-python.log`. Both 223425- and 500000-record scale checks passed. Final review fixes affect frontend only; backend code is unchanged from this full run.
- RED evidence retained locally for node replacement/focus, concurrent recovery, no-scan conflict, stage/age presentation, metadata, startup guard, diagnostics focus, stalled polling, and denial cleanup (`artifacts/ap-stabilization-*-red.log`).

Python temp-file creation and esbuild subprocess launch need execution outside the sandbox. A diagnostic traceback located the sandbox hang in `tempfile.mkdtemp`; no test or product failure was hidden by changing assertions.

## Browser evidence

Local fixture `artifacts/ap-stabilization-server.mjs` serves the production frontend with synthetic bridge responses and an existing two-page synthetic PDF. Counters are rendered in the page, not read from hidden app state.

- Vendor typing: entered `Syn`, then continued `thetic vendor` across 10 additional duplicate requests. Search focus/query remained intact and main replacement count stayed at 4. Screenshot: `artifacts/ap-stabilization-vendor.png`.
- Vendor history preview: remained visible from poll 47 to 73; exactly one private PDF request; main replacement count stayed at 5.
- Invoice PDF: selected invoice 1001 on page 2. From poll 95 through 117, page/highlight stayed visible with PDF requests fixed at 3 (one history thumbnail plus two intentional source-page displays), canvas insertions fixed at 2, and main replacements fixed at 6. Screenshot: `artifacts/ap-stabilization-pdf.png`.
- Foreign session: displayed “Waiting for the active scan,” without active spinner or a restart action. Screenshot: `artifacts/ap-stabilization-waiting.png`.
- Expired scan: explicit restart disabled all recovery buttons while in flight; exactly one restart recorded, then packaging resumed.
- Initial ensure conflict: showed paused checks with no progress/scan ID; changing fixture to healthy and refreshing resumed packaging without a null-property exception. Conflict copy does not assert that the source changed.
- Stalled scan: old server-relative timestamp produced “No recent scan progress.” Expanded diagnostics remained readable through repeated updates (phase packaging, checkpoint 275); screenshot: `artifacts/ap-stabilization-stalled.png`. A regression then additionally pinned summary keyboard focus and a 1000ms idle interval for usable Refresh.
- Duplicate draft: an unsaved synthetic note survived Refresh and remained editable afterward; no review save was submitted.
- Missing module startup: after 20 seconds, displayed manual “Reload application,” without automatic reload. Screenshot: `artifacts/ap-stabilization-startup-failure.png`.
- Denial cleanup: automated real-workspace/controller test proves shared source/details are cleared and client disposed. Fresh browser verification showed the locked-session instruction without workspace evidence; screenshot `artifacts/ap-stabilization-denied.png`.

## Independent review and final fix pass

One fresh senior reviewer examined the complete pending branch from c9705f3 to 0e2d34c. No critical issue or additional earlier re-review integration defect was found. Two findings were verified and fixed in one RED-to-GREEN pass:

- Important: a delayed findings reply could reset a query typed during the 250ms debounce. A synchronous source-scoped query draft now supplies the displayed value even after focus moves; source replacement/denial cancel the debounce and clear the draft. Regression holds an earlier real-controller findings reply while new input arrives, then verifies the eventual request uses the complete new query.
- Privacy cleanup: reviewer rated retained hidden thumbnail cache Minor. Regraded Important because the agreed lock behavior includes clearing private in-memory evidence, not merely hiding it. Denial now disposes the preview cache, cancels hover work, invalidates pending history loads, removes the preview root, and clears retained focus/query state. The regression uses the real preview controller and verifies it cannot reopen a cached thumbnail after disposal.

All 421 frontend tests pass after the fix pass; no re-review was dispatched. Build and whitespace verification pass. No deferred minor remains.

## Implementation rulings

1. Use native PowerShell bookkeeping instead of unavailable Bash helpers, preserving task boundaries and test/commit evidence; risk is manual bookkeeping drift, checked against history.
2. Use flat-module Python test invocation and escalated local tests/build where the sandbox blocks temp directories or subprocesses; risk is broader local test filesystem access, with synthetic data only and no production connection.
3. Give interrupted requests a 1000ms idle interval instead of 10ms so the offered Refresh is usable; risk is up to 990ms additional delay per interrupted request, with no ownership or automatic-restart change.
4. Production recovery/permissions/migration remain a deployment gate, not inferred from local results; risk is unverified live behavior until an authorized deployment check.
5. Pre-HTML Streamlit hosting failures remain outside the component watchdog's reach; risk is that the outer page can still fail before the guard runs.
6. The reviewer's pending-backend caveat was resolved with the completed 735-test run; one live integration skip still requires the separate deployment check above.
7. Accept the recorded author-run synthetic browser walkthrough alongside fresh code review rather than duplicate it independently; risk is less independent visual coverage, offset by browser evidence and regressions.

## Chosen thresholds and preserved contracts

- Startup watchdog: 20000ms for app-and-bridge initialization only. Bootstrap/data loading retains the existing 30000ms request timeout and retry path. Late initialization never triggers automatic reload or hides an existing error.
- No-progress warning: 60000ms without phase/checkpoint/counter/projection advancement. Initial age uses serverNow minus updatedAt; subsequent elapsed time is local and nonnegative. Missing older-backend metadata remains supported.
- Interrupted requests use the existing 1000ms waiting interval so Refresh is actionable; healthy owned work retains the existing 10ms interval. This changes no lease, generation, checkpoint, or restart authorization.
- Duplicate conflict recovery reads status (or ensures when no scan ID exists), never automatically resubmits a conflicting review. Other transport retries keep their original request identity.
- Access denial terminates the shared client, clears in-memory evidence/previews/drafts, and shows an unlock instruction. No credentials are handled in the component.
- Diagnostics allow only known stage, numeric checkpoint, and elapsed seconds; no invoice values, source digest, storage paths, session nonce, or raw exceptions.

## Remaining live check

Local tests do not establish that the production scan has recovered. Deployment and an unlocked live-session check require separate authorization. The watchdog cannot run when Streamlit never serves the component HTML/outer iframe; that hosting/handshake failure remains distinguishable from in-component startup failure. This pass does not install a durable independent scan worker.
