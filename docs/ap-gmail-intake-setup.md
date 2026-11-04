# Gmail statement intake: owner setup and recovery

Forwarding to the Gmail **AP Statements** label is the first step. The app also needs a separate authenticated background service. Streamlit does not keep this worker alive, and refreshing AP does not run OCR. Nothing in this branch provisions or activates that connection automatically.

## What is ready and what is still gated

The code checks the selected label about every five minutes, saves eligible PDFs privately, and processes one PDF at a time. Its comparison is **preliminary**, using the current saved BILL source and saved vendor mappings. A person still checks PDF reading, vendor choice, exceptions, initials, and completion. Matching does not establish payment settlement. Credits omitted from the Bills CSV cannot be proved present in BILL by this workflow. Continue updating the Bills CSV manually.

The queue survives restarts and uses separate identities for message/MIME part, original hash, processing attempt, and dispatch. Identical statement content links to its saved copy, including completed/archived copies. Different originals are retained. Overlapping statements retain every incoming row and identify new/repeated invoices. Similar statements wait for a user choice. Automatic evidence cannot overwrite a human-edited, confirmed, completed, archived, or reopened head.

Pending range protections do not rebuild or activate a range in the worker. Preliminary reads use the current hash-verified immutable artifact, visibly flag a pending refresh, and keep excluded rows as **Check archived data**. Human saves retain their strict freshness checks. Recompare uses saved extraction, without another Gmail download or OCR.

## 1. Confirm the deployment targets

Record the explicit Google Cloud project, region, Artifact Registry repository, owner principal, Gmail account/label, Supabase URL/workspace UUID, connection UUID, and private bucket. There is no production project default in Terraform. The existing production database is **not** an authorized synthetic acceptance target.

The owner needs permission to deploy Cloud Run, enable the listed APIs, manage the narrow IAM bindings, and authorize the chosen mailbox. Create the existing Supabase server-key Secret Manager secret privately in the cloud console; never put its value in chat, `.tfvars`, a shell argument, Terraform variables, or Git. Use its specific version number. No AP password belongs in the worker.

## 2. Verify locally, then in an authorized synthetic environment

From the repository root, install the app's usual dependencies. Install worker dependencies in a separate Python 3.12 virtual environment with:

```powershell
python -m venv "$env:TEMP\ap-mail-check"
& "$env:TEMP\ap-mail-check\Scripts\python.exe" -m pip install --require-hashes -r workers/ap_mail/requirements.lock
npm ci --prefix app/ap_statements
npm ci --prefix workers/ap_mail
node app/ap_statements/build.mjs
node workers/ap_mail/node_modules/playwright/cli.js install chromium
```

Run Python/AP frontend tests, Terraform formatting/validation, and the offline Linux container command in [deploy/ap_mail/README.md](../deploy/ap_mail/README.md). The real reader must work with Chromium's sandbox enabled. Windows Chrome tests do not substitute for Linux/container or Cloud Run acceptance. Pin the built image by its Artifact Registry SHA-256 digest. Never deploy a floating tag.

The cloud acceptance run must use an owner-approved **synthetic** Supabase workspace/project and test mailbox PDFs. Verify private IAM denial, correct OIDC caller/audience, all database migrations, durable dispatch, crash/lease recovery, private object reuse, and one readable/scanned PDF end to end. Measure queue throughput, peak memory, and foreground AP/database latency before promising any performance improvement. No live consent, Docker/container pass, cloud deployment, or production acceptance is implied by local unit tests.

## 3. Apply the compatible database inventory

Before deployment, preserve recovery definitions and counts for existing functions, constraints, statements, immutable revisions, completion events, scans, and reviews. Store the recovery output privately. Do not erase old rows to make a migration pass. Apply missing migrations in filename order after checking which are already applied:

| Existing prerequisites | Purpose |
|---|---|
| `202610130001_ap_shared_workspace.sql` | Private shared workspace/history |
| `202610190001_ap_bill_snapshots.sql` | Large BILL imports |
| `202610220001_ap_duplicate_bills.sql` | Duplicate scans/private quota |
| `202610230001_ap_statement_rereview.sql` | Safe re-review |
| `202610260001_ap_duplicate_rules_v2.sql` | Duplicate scan rules |
| `202610280001_ap_duplicate_vendor_rules_v3.sql` | Vendor rules |
| `202610300001_ap_bill_working_sets.sql` | Active range/protection epochs |
| `202610300002_ap_duplicate_working_scope.sql` | Scoped duplicate scans |
| `202610300003_ap_duplicate_near_references.sql` | Near-reference rules |
| New mail migrations | Purpose |
| `202611040001_ap_mail_intake.sql` | Private receipts, jobs, cursor/outbox/slot |
| `202611040002_ap_mail_publication.sql` | Atomic draft/link publication |
| `202611040003_ap_mail_processing.sql` | Shared quota and bounded recompare |
| `202611040004_ap_mail_controls.sql` | Authorized human controls |

All four new migrations and pending prerequisite code must be included in the same rollout inventory. The additions preserve existing originals and financial history; no new function permits public/anonymous/authenticated table access. Run the old-workspace and migration acceptance checks before deployment.

## 4. Plan the paused services

Create a private, ignored variables file with the required fields in `deploy/ap_mail/variables.tf`, using only the confirmed target IDs and secret names. Run:

```powershell
.\deploy\ap_mail\plan.ps1 -VariablesFile 'C:\private\ap-mail.tfvars'
```

Review its concrete resource/IAM plan before applying. No script applies infrastructure for you. Resources are a checker, a processor, a one-dispatch PDF queue, one paused five-minute schedule, distinct runtime/scheduler/task identities, and the empty Gmail secret container. The processor is request-scoped, one instance/concurrent request, 2 vCPU/4 GiB, 600-second timeout. Checker work is budgeted and lighter. Both services require IAM, internal ingress, and the pinned caller/audience inside the application. Cloud Tasks/Scheduler in the same project invoke the actual `run.app` URLs; laptop access is not an acceptance route through internal ingress.

The Gmail and database secrets are readable only by the two runtime accounts. The owner receives permission to add a Gmail secret version, not a token-download endpoint. The checker can create/get tasks on its one queue and act as its one task signer. It cannot invoke a generic database operation through HTTP.

## 5. Authorize the dedicated Gmail account

In the selected Google Cloud project, enable Gmail API and configure the OAuth consent screen. Create a **Desktop app** OAuth client and privately download its client JSON. Request only `openid`, `email`, and Gmail read-only. Decide the production authorization/verification route before enabling unattended imports. Gmail read-only is a restricted scope; verification/security-assessment requirements and exemptions depend on the app's use and data handling. An External app in Testing can have a seven-day refresh-token lifetime for these scopes, so Testing is not durable unattended authorization. Do not bypass Google's consent or verification requirements.

Sign in to the cloud owner account with Application Default Credentials using the normal Google CLI flow; avoid service account key files. Run the owner tool locally from the repo root (the arguments below are public IDs/paths, not token values):

```powershell
& "$env:TEMP\ap-mail-check\Scripts\python.exe" -m workers.ap_mail.authorize `
  --client-json 'C:\private\desktop-oauth-client.json' `
  --expected-email 'YOUR-DEDICATED-GMAIL-ADDRESS' `
  --label 'AP Statements' `
  --secret 'projects/YOUR-PROJECT/secrets/YOUR-GMAIL-SECRET'
```

Complete Google's sign-in/consent yourself. The script binds a temporary loopback callback with PKCE/state/nonce, checks the exact account and label ID, requires a refresh token and the exact scopes, and writes the refresh grant directly to Secret Manager. It does not write Gmail tokens to a file or print them. Output contains only account/email/label IDs and the secret version reference. The original downloaded client JSON remains private; Google's normal ADC credentials are separate from the Gmail refresh grant.

Use those safe identifiers to create the connection row **paused**, with the same workspace/connection UUID supplied to Terraform. `secret_ref` is the `projects/.../secrets/...` reference, without `/versions/...`, and must match the configured Gmail secret. A reviewed SQL insert has these columns:

```sql
insert into public.ap_mail_connections
 (id, workspace_id, account_id, email, label_id, label_name, secret_ref, paused)
values
 ('CONNECTION-UUID', 'WORKSPACE-UUID', 'GOOGLE-SUB', 'GMAIL-ADDRESS',
  'LABEL-ID', 'AP Statements', 'projects/PROJECT/secrets/SECRET', true);
```

Do not run placeholders or paste secret contents. If a label is renamed its pinned ID still works; deleting/recreating it needs a deliberate reconnect. Switching account/label requires a new connection generation and compatible runtime configuration. Deactivate/fence the prior connection, preserve its receipts/history, and test the replacement while paused. Never reset receipts or history cursors to reconnect.

## 6. Accept one PDF, then enable the schedule

Open AP → **Email imports**. Check the displayed account/label. Default behavior is **new arrivals only**: the first successful check inventories existing labeled mail and anchors Gmail history without importing an unexpected backlog. Use the bounded date/count **Import earlier emails** control only for owner-selected older mail.

Keep the schedule paused. Resume the connection deliberately, run the scheduler job manually to establish the baseline, and test one selected newly forwarded statement (or explicitly requested earlier email). Resume the task queue for that test. Verify one private original, one preliminary draft/link, correct vendor/rows/amounts, and unchanged human history. Pause it again if anything fails. Only after acceptance, resume the five-minute scheduler. The native app exposes private receipt previews and manual retry/skip/similarity choices; it never edits Gmail labels/read state or sends email.

A baseline recovery after Gmail history expiry reconciles labeled mail by pages, queues known/new eligible messages, and holds uncertain older mail for review. Message-level failures remain actionable even when no verified PDF receipt could be created.

## Monitoring, limits and recovery

Inspect last successful poll, queued/scanning/attention counts, receipt reasons, and attempt metadata. Use Cloud Run request/error counts and duration metrics without enabling raw HTTP/OAuth/PDF debug logs. One successful import remains **Awaiting review**, not completed. Received time, imported time, and the extracted statement date are distinct; the UI renders email times in New York time.

Files are capped at 20 MiB/100 pages and OCR canvases at 20 million pixels before allocation. A processing cycle has three fenced attempts and a renewable 60-second slot, with 15-second heartbeat and bounded child lifetime. A new comparison after a completed cycle gets a new bounded attempt budget; dispatch repair never resets a failed cycle. At most 50 untouched stale drafts are queued per poll. Broad candidate inventories/results fail to attention instead of becoming a truncated Missing result.

For a monthly processor duration of **S seconds**, the configured upper allocation is approximately `2 × S` vCPU-seconds and `4 × S` GiB-seconds, plus checker time, task calls, secret access, storage, and logs. This is a resource model, not a price quote or measured throughput. Budget alerts and the owner-approved region's current pricing belong in the deployment review. Measure scanned, digital, and large exports separately. The architecture isolates OCR from Streamlit, but shared database/hosting load still needs measurement.

Pause in this order when recovering: scheduler, connection, queue. An active scan may safely finish; the next reconciler reclaims expired leases. Fix the displayed cause and use Retry or reconnect; no reset/delete is required. Keep originals and revisions. A crash after extraction resumes from saved extraction. A lost immutable-upload acknowledgement is verified by hash. Stale source/head conflicts trigger reassessment; a human-touched draft is never overwritten.

Rollback disables the schedule/queue, keeps the connection paused, restores the previous compatible app image, and sets the workspace's `mail_schema_version` capability marker to `0` if the new UI must be hidden. Preserve the additive mail tables, private originals, and audit/history; do not reverse migrations by deleting financial data. Confirm all users saved before any shared Streamlit reboot.

Primary references: [Gmail synchronization](https://developers.google.com/workspace/gmail/api/guides/sync), [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes), [desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app), [token expiration](https://developers.google.com/identity/protocols/oauth2#expiration), [Cloud Run service authentication](https://cloud.google.com/run/docs/authenticating/service-to-service), [HTTP Cloud Tasks](https://cloud.google.com/tasks/docs/creating-http-target-tasks).
