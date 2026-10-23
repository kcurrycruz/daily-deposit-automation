# Statement re-review rollout

## Deployment prerequisites

This feature is implemented locally; this document does not authorize a production migration, upload, push or deployment. Back up the database and confirm the intended Supabase project before an authorized operator applies SQL. Test first in an authorized non-production project with synthetic data.

Apply existing AP workspace migrations in their established order, then the additive `supabase/migrations/202610230001_ap_statement_rereview.sql`. It adds a workspace capability marker and a service-role-only atomic re-review function. It does not replace or delete completed revisions, history events or original PDFs. Keep the private bucket private and never put service-role credentials in the browser.

Deploy the backend and frontend together. Bootstrap exposes `statementRereview: 1` only when the schema marker is available. Without the migration, new history/vendor Re-review entry points are hidden; existing revision viewing and legacy reopening remain available. Do not enable the marker manually before installing the function.

## User workflow

1. In Previous Statements or Vendor history, choose **Re-review**. This opens the latest statement head, not a replacement made from an older history entry. An existing editable draft is reused; conflicting versions are rejected.
2. Choose **Recheck with latest BILL data** (default) to refresh comparisons. Notes and extraction are retained; old review decisions need a new review.
3. Choose **Review manually** to retain the saved comparison, import, mappings and matching rule. Weekly imports do not silently change this evidence. For an item checked directly in BILL, select the explicit manual-check checkbox, enter initials and save a review decision.
4. Acknowledged manual checks display **Checked manually in BILL**, initials and a server-owned check date (`manualCheck.checkedAt`), separate from the decision's last-save time. Saving statement notes, another item, global changes or completion carries the check date forward. An explicit **Save review decision** with the manual checkbox selected records a fresh check date. Original imported results remain visible. Manual checks do not increase automatic Invoice found counts.
5. To correct financial extraction or use a newer import, explicitly recheck with latest BILL data. If current data cannot be loaded, the prior manual draft is retained. Unsaved edits must be saved before changing modes.
6. Complete the draft again to create another history entry. View revision remains read-only and shows the evidence saved at that time; earlier decisions are not overwritten.

Initials and manual checks are self-reported, not verified identities or proof of payment settlement, credit application or imported invoice presence. A Bills-only export may omit credits that exist in BILL. Linked statement credits remain visible but are not verified merely because an invoice matches. Never treat an amount-only resemblance as credit confirmation.

If the current BILL index is temporarily unavailable, saved pinned manual drafts can still load, save and complete. The app marks current data unavailable and blocks latest-mode saves/completion until the source recovers. **Retry loading BILL data** reloads the source only after dirty edits are saved; an explicit latest recheck also retries source availability. Access denial/expiry remains fatal and clears private state rather than entering this degraded mode.

## Verification and rollback

Local automated coverage includes real PostgreSQL-compatible PGlite execution of the migration, service validation, CAS/idempotent retry, source pinning across import/mapping/save/completion, failed latest recheck restoration, expiry disposal, history controls and CSV provenance. The opt-in live Supabase integration test is not evidence of a live deployment unless separately enabled and passed.

Synthetic browser QA exercised history mode selection, manual decision save/reload, explicit latest recheck with note retention, original read-only history and linked Ace-style credits at narrow and desktop widths. No real records were uploaded. The synthetic preview intentionally does not render a PDF; this walkthrough does not verify real PDF rendering or a live Supabase connection. Screenshots are retained locally in `artifacts/ap-rereview-choice.png`, `artifacts/ap-rereview-manual.png` and `artifacts/ap-rereview-history-wide.png` (not deployment assets).

Final-review regressions additionally exercised a failed current index, manual saves while it is unavailable, successful source retry without switching the pinned comparison, a note-only save retaining the manual-check date, an explicit fresh check receiving a new date, and completion retaining both history entries. Additional local screenshots: `artifacts/ap-rereview-outage.png`, `artifacts/ap-rereview-stable-manual-time.png`, and `artifacts/ap-rereview-history-preserved.png`.

Release verification, October 23, 2026: `python -X utf8 -m unittest discover -s tests -v` ran 734 tests in 808.457 seconds, OK with one opt-in live integration skip. All 390 `ap_statements*.test.mjs` frontend tests passed with `node --test --test-isolation=none`; `node app/ap_statements/build.mjs` and `git diff --check` passed. The backend run includes the real PGlite migration/provenance checks and both 223,425- and 500,000-record duplicate regressions. A fresh whole-branch review found two Important issues (manual check dates restamped by unrelated saves; manual drafts blocked by current-index failure); both were reproduced and fixed in one RED-to-GREEN pass. No Critical or deferred Minor findings. Live migration, production permissions and real PDF rendering remain unverified deployment gates, not passed tests.

If rollback is necessary, disable the feature's UI/capability through a reviewed deployment or return to the previous application version. Do not delete revisions, history or PDFs to roll back. Keep the additive database functions/schema until a separately reviewed data-preserving rollback is prepared. Reopened drafts and their manual provenance must remain recoverable; do not silently relabel them as new automatic matches.
