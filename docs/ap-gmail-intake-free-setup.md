# AP Gmail imports without paid hosting

Selected route: Gmail **AP Statements** label → a standard GitHub-hosted Linux runner → the existing private AP workspace. Checks target **8:17 AM and 4:17 PM America/New_York**, daily including weekends. GitHub can delay or skip scheduled runs; Streamlit does not need to stay open.

On 2026-11-06, GitHub confirmed `kcurrycruz/daily-deposit-automation` is public and its default branch is `main`. Standard public-repository runners are free independently of private-repository included usage. This workflow uses no paid runners, persistent Actions caches, uploaded artifacts, package/container registry, Cloud Run, Tasks, Scheduler or Secret Manager. Existing Supabase limits still apply; no automatic paid upgrade is authorized. If the repository becomes private, the workflow stops.

Code readiness does not mean Gmail consent, live migrations, Linux acceptance or scheduled imports are already complete.

## 1. Keep Google project hwfc-ap-statements, without billing

Enable **Gmail API** in this project. Configure Google Auth Platform branding/audience/data access and create a **Desktop app** OAuth client. Download its client JSON privately outside Git. Only request `openid`, `email`, and `https://www.googleapis.com/auth/gmail.readonly`.

Confirm the applicable Google verification or exception route before unattended use. Google documents exceptions for limited personal use and internal organization apps; a consumer Gmail account is not automatically a Workspace internal app. External **Testing** generally has a seven-day refresh-token lifetime for these scopes, so it is not durable unattended authorization. The owner completes consent personally. Do not bypass access restrictions/security warnings; stop if Google's required route cannot meet the no-paid-services constraint.

Standard Gmail API usage is currently available at no additional cost. Stay within request limits; no paid quota increase or Google compute resource is needed here. The worker cannot send mail, mark it read, change labels, or alter BILL.

## 2. Review the release and keep activation off

The AP source is on **DD-v2**, but a schedule must live on default branch **main**. Prepare a minimal reviewed main change containing `.github/workflows/ap-mail-batch.yml` only. Its two literal source SHAs must match the tested immutable AP worker commit and be remotely reachable. Repin both after any worker fix. Do not change the default branch, merge the whole newer app into main, or change Streamlit's deployed branch just to install this scheduler.

The connected Chrome account was **KarlHWFC**; the repository owner is **kcurrycruz**. KarlHWFC could access Secrets and variables, but repository options were unavailable. Owner help may be needed for integration/settings; do not change the wrong account's billing.

Configure these repository **Actions variables** with confirmed values:

| Variable | Initial value |
| --- | --- |
| `AP_MAIL_BATCH_ENABLED` | `false` |
| `AP_MAIL_SCHEDULE_ENABLED` | `false` |
| `AP_MAIL_SUPABASE_URL` | Approved existing Supabase HTTPS origin |
| `AP_MAIL_WORKSPACE_ID` | Approved AP workspace UUID |
| `AP_MAIL_CONNECTION_ID` | Approved mail connection UUID |
| `AP_MAIL_BUCKET` | Verified existing private AP bucket |

Both false switches leave imports off. The database connection is a separate pause gate. Runtime also checks the exact public repository, default branch, workflow ref, event, free runner context and source-SHA format.

## 3. Preserve the database before migration

Confirm the exact project/workspace. Historical Supabase reference `uhwpnbntjsopuilouize` is production, not a synthetic test target. Privately preserve existing function/constraint definitions and counts of statements, immutable revisions, completions, duplicate scans/reviews and mail records. Never publish recovery output or financial data.

Check the [ordered prerequisites](ap-gmail-intake-setup.md#3-apply-the-compatible-database-inventory), then apply missing mail migrations in filename order:

1. `202611040001_ap_mail_intake.sql`
2. `202611040002_ap_mail_publication.sql`
3. `202611040003_ap_mail_processing.sql`
4. `202611040004_ap_mail_controls.sql`
5. `202611060001_ap_mail_batch.sql`

The last file adds only a service-role read of due jobs for one exact mailbox. Verify ACLs and old-workspace behavior; never delete records to make migration succeed. Keep the real connection paused.

## 4. Configure private access

Use the official GitHub CLI, authenticated by the owner through its normal login flow, with permission to set repository Actions secrets. No token belongs in chat or a script argument.

Create **AP_MAIL_SUPABASE_KEY** directly in GitHub's private Actions secret entry or an owner-controlled secure flow. This existing server credential is broad: never put it in an Actions variable, Git, logs, screenshots, chat, or a command argument.

Install the worker's existing hash-locked dependencies in an isolated Python 3.12 environment. The owner authorization helper writes the Gmail refresh grant directly to **AP_MAIL_GMAIL_GRANT** through CLI standard input. Replace the template email/path with confirmed values before running:

```powershell
python -m workers.ap_mail.authorize `
  --client-json 'C:\private\desktop-oauth-client.json' `
  --expected-email 'CONFIRMED-GMAIL-ADDRESS' `
  --label 'AP Statements' `
  --github-repo 'kcurrycruz/daily-deposit-automation'
```

The helper checks exact repository/public visibility/write access before consent, then verifies the Google account, label and scopes. The owner completes Google sign-in/consent. The refresh grant is never printed, placed in argv, saved to a token file, or copied to the clipboard. Output contains safe identity/label IDs and a destination reference only. A failed secret write means setup is incomplete; fix it and repeat owner authorization.

Review this persistent access at setup time: GitHub will hold the read-only Gmail grant and AP server credential as encrypted Actions secrets. The downloaded desktop client JSON remains private.

With the verified identity/label IDs, prepare a reviewed **paused** connection row for the exact workspace/connection UUID. Its `secret_ref` is the literal binding:

`github:kcurrycruz/daily-deposit-automation:AP_MAIL_GMAIL_GRANT`

This is not a token or endpoint. If an old connection exists, perform a reviewed paused transition preserving receipts, cursor and history. Never reset them or create a second active connection for the same workspace. The worker does not need an AP password.

## 5. Verify Linux, then accept one statement

After an authorized reviewed-code push, run **Validate Application** on that revision. Ubuntu mail tests, synthetic batch recovery, real PDF/OCR tests and the offline container smoke must pass with Chromium's sandbox enabled. The validation job installs `tests/requirements-ap-mail.txt`; its YAML parser is test-only, not a deployed dependency. The optional protected synthetic-cloud job is for Cloud Run and does not require provisioning paid Google resources for this route.

Windows results do not substitute for Linux acceptance. If setup/runtime cannot fit the 20-minute job, leave activation off and resolve it. Never disable the sandbox as a workaround.

Keep `AP_MAIL_SCHEDULE_ENABLED=false`. After migration/access checks, deliberately resume the matching app connection and set `AP_MAIL_BATCH_ENABLED=true` for manual acceptance. Use **Actions → Import AP statements twice daily → Run workflow → main**.

The first successful check inventories existing labeled mail and anchors history without importing an unexpected backlog. Use the app's explicit bounded **Import earlier emails** control for older mail.

Complete approved synthetic acceptance first, then test the approved real connection. With an empty queue, forward one owner-selected statement into the Gmail label and manually run again. Review other new arrivals if any came during that interval: a run may process up to ten PDFs and safely leave excess work queued. Never send real financial PDFs to a synthetic target.

Verify the correct mailbox/label, advanced last-success time, private original, one draft/saved-copy link, correct vendor/rows/amounts/BILL source, unchanged human decisions/history, and public logs containing aggregate counts/reason codes only. An import remains **Awaiting review**, never completed automatically.

Only after acceptance set `AP_MAIL_SCHEDULE_ENABLED=true`. Both switches must be true and the connection resumed for scheduled operation. Observe one successful scheduled run; a manual or skipped run does not prove the scheduler is active.

## Operating and recovery

The app's last successful check is authoritative. New mail, retries, earlier-mail requests and untouched-draft comparisons run on a later scheduled check. Work is sequential and finite. Interrupted attempts are reclaimed by SQL leases; saved originals/extraction are reused. A pause stops new scans while an active scan may finish; expired Scanning entries can still be repaired.

Stop unattended checks with `AP_MAIL_SCHEDULE_ENABLED=false`, then pause the connection as appropriate. Set `AP_MAIL_BATCH_ENABLED=false` to block manual runs too, or disable the workflow. Fix the cause and resume the same connection; do not delete queues, reset cursors, or recreate connections as a repair.

An old last-success time can mean scheduling delay, disabled workflow, access trouble or platform limits. Inspect GitHub run status; the app does not invent a billing diagnosis. Private-repository conversion requires a separately reviewed no-paid-usage setup.

Continue uploading current BILL CSV data manually. Credits omitted from that export require manual checking in BILL, and invoice presence does not establish payment settlement.

Rollback disables both switches, pauses the connection and restores a compatible app/release. Preserve additive mail tables, originals, queue and audit/history; no financial-data deletion.

Primary references: [free public runners](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [schedules](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule), [Gmail usage](https://developers.google.com/workspace/gmail/api/reference/quota), [verification exceptions](https://support.google.com/cloud/answer/13464323), [restricted scopes](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification), [token expiration](https://developers.google.com/identity/protocols/oauth2#expiration), [CLI secret input](https://cli.github.com/manual/gh_secret_set).
