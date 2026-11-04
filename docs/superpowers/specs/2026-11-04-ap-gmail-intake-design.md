# Gmail statement intake and background scanning

Date: 2026-11-04. Status: owner approved the written design ("looks good"); implementation plan pending review. Branch: `codex/ap-gmail-intake`, base `1feb83a`. No application code, cloud resources, credentials or database migrations have been created for this feature.

## Intent and agreed approach

The owner has configured Outlook rules for their work mailbox and AP shared mailbox to forward statement emails into a dedicated Gmail account. Gmail labels incoming PDF mail `AP Statements`. They want attachments to appear in the existing AP app, already extracted and compared with saved BILL data, including month-end bursts, without keeping the app open or making its interactive work sluggish.

The owner selected the recommended five-minute mailbox check with one PDF worker. Source files and review history must remain intact. Automatic completion was not selected: the proposed first release creates automatically scanned drafts and preliminary comparison evidence, with final PDF confirmation and completion remaining human actions. This is an explicit proposed default for approval, not an assertion that the owner previously chose it.

## Approaches considered

1. **Five-minute scheduled intake and a single queued worker (selected).** Predictable polling and a durable backlog fit irregular/month-end arrivals. Separate intake from extraction so long PDFs do not prevent subsequent mailbox checks. This requires Google Cloud runtime, a queue and one-time Gmail authorization.
2. **Gmail push notifications.** Lower arrival latency, but adds Pub/Sub delivery, watch renewal and recovery responsibilities. The owner has no near-instant requirement; defer this path.
3. **Intake inside Streamlit or only while a browser is open (rejected).** The existing extraction module depends on browser PDF.js, canvas and Tesseract. Streamlit Community Cloud also hibernates without traffic. This cannot provide the agreed unattended behavior reliably.

## Existing code to reuse

- `frontend/extraction.mjs` reads digital/scanned PDFs using the bundled PDF.js/Tesseract assets and vendor-specific scan recovery.
- `frontend/core.mjs` contains parsing, invoice grouping and reconciliation; `vendor-identity.mjs` and `adventure-reference.mjs` implement existing vendor/reference policies.
- `frontend/statement-duplicates.mjs` assesses exact, overlapping and similar statements. Its interactive `choose` callback cannot be invoked by a background worker.
- `frontend/comparison-source.mjs` prepares scoped candidate data. Python snapshot/working-set queries and archives implement the authoritative BILL source formats.
- `app/ap_shared/service.py`, repository and SQL mutations protect originals, immutable revisions and interactive authorization. They require a human session; automation must not fabricate an `Authorization` or retain the AP password.

## Runtime and boundaries

Proposed builder choices, subject to this design's approval:

- Cloud Scheduler invokes a private **mail intake service** every five minutes. It inventories eligible attachment metadata and commits queue/outbox records; it does not OCR PDFs or load the BILL export.
- A private **PDF processing service** is invoked through Cloud Tasks. Set queue concurrency to one and processor concurrency/maximum instances to one, plus both a workspace-wide processor-slot lease and per-job fencing generations. An active slot belongs to one job; stale attempts lose publication rights and cancel their child process on heartbeat failure. Cloud limits alone do not establish exactly-once work or prevent stale writers.
- The processor copies one original PDF, runs the existing extractor in a credential-free headless Chromium process, queries the saved BILL source and calculates preliminary matches. Streamlit displays the saved outcome.
- Start with Python coordination and a pinned Node/Playwright extraction adapter. Serve only bundled extraction assets over loopback; reuse the modules instead of maintaining a second vendor parser. Browser requests outside those local assets are blocked. Email HTML, links and instructions are data, never executable workflow instructions. No credentials or broad host bindings are exposed to the page/browser process.
- Initial processor budget: two vCPUs, 4 GiB memory, one document per request, ten minutes per document, existing effective 20 MiB file/100-page limits, and a background raster cap of 20 million pixels per page. Oversized/encrypted/unreadable documents retain their original and become manual-review items. Final resource sizing is measured before activation. Cache one pinned active BILL source/working set at a time, with bounded disk/memory use and verified archive hashes; no full export reload per attachment or per UI refresh.

The checker remains lightweight even when the processing queue is full. Arrival-to-queue target is approximately five minutes plus provider/scheduling delay; completion also includes queue and scan time. No promise that every statement finishes in five minutes, or that shared database/storage load is zero.

## Gmail connection and synchronization

Support one dedicated Gmail account and one label per AP workspace initially. Pin the authorized account identity and selected label ID; label renaming should not break the connection. A deleted label, wrong account, revoked authorization or token failure produces a clear connection error and retains queued work.

Use OAuth with `gmail.readonly` and identity scopes, offline access, and owner sign-in. Read-only authorization is account-wide at Google; the application restricts processing to the configured label. It does not send mail, change read status, move messages, edit labels or delete messages.

A local one-time authorization utility opens Google's consent flow with a loopback redirect, verifies the selected identity/label and stores the resulting credentials directly in Secret Manager. Tokens/client credentials must not be pasted into chat, committed to Git, exposed to Streamlit clients or printed in logs. The account owner performs sign-in and consent. Long-running production must not depend on an External/Testing refresh token that expires after seven days. Determine the applicable verification/exception and publishing requirements before activation; do not assume the single-account use automatically eliminates them.

Start with a metadata-only baseline and an initial history checkpoint captured before the baseline walk. At connection activation show existing labeled-mail counts and offer **new arrivals only** (default) or an explicitly confirmed, bounded existing-mail import. Historical import has its own pagination and does not reset the live cursor. A newly applied AP label after activation is eligible live work, even for an older message.

Poll incremental Gmail history using opaque string history IDs and durable pagination. Recheck that each message still has the selected label and inspect individual PDF MIME parts; thread IDs/read flags are not deduplication keys. Identify parts by stable MIME part path, including a root PDF. Handle bounded MIME depth/part counts and both attachment IDs and inline PDF data. Ignore non-PDF parts; messages that cannot be interpreted become visible attention items.

Persist discovered work before advancing a history page checkpoint. Preserve page progress across budget exhaustion and failure. An expired history checkpoint triggers a paginated label reconciliation, using the receipt ledger to avoid repeated imports. Newly received unknown messages are eligible; old unknown messages whose label-addition time cannot be recovered require an explicit import choice rather than disappearing or causing an unexpected historical import. Gmail deletion or label removal never deletes existing AP statements; a withdrawn/unavailable attachment that has not yet been copied gets a visible skipped/attention state.

## Durable work, retries and source evidence

Add workspace-scoped, RLS-protected mail connection, message/attachment receipt, job/attempt, preliminary-evidence and dispatch-outbox storage. Required identities and fields:

- Unique receipt identity: workspace + Google account identity + Gmail message ID + MIME part path. Store thread ID only for traceability.
- Metadata: bounded sender/subject/filename, MIME/declared size, Gmail received time, discovered/imported times and sanitized error codes. Do not persist full email bodies.
- After copying: verified PDF SHA-256, private object key, parser/build version, linked statement ID, assessment and comparison-source pins.
- Job state/version, dispatch generation, lease generation/expiry, heartbeat, attempt budget, outbox identity and next retry time.

Create the job/outbox atomically before asking Cloud Tasks to dispatch it. Use deterministic task names per receipt/dispatch generation; retries of task creation are safe. Periodic reconciliation repairs unacknowledged outbox entries, expired leases and nonterminal jobs whose task disappeared. Three real processing attempts per generation is the proposed cap; exhausted or deterministic document failures become `Needs attention`, with explicit human retry. Transport duplicate deliveries do not count as successful claims. Never leave abandoned work permanently `Scanning`.

Use database time, renewable leases and fencing tokens on every mutation. Intake is budgeted to about one minute of work per request and checkpoints for the next poll. The worker renews its lease while the child scans; loss of renewal cancels processing. A stale or timed-out attempt cannot register a second draft or overwrite a later result. Tasks contain job identifiers, not PDF bytes or credentials.

The PDF worker fetches/copies bytes one at a time, checks effective file limits, MIME and `%PDF-`, and verifies content hash. Respect the existing shared storage budget. Use the existing workspace/content-addressed private PDF convention; never overwrite a different original. If the email disappears or storage fills, show the reason and preserve the receipt for recovery. No automatic deletion of old financial data.

### Statement duplicate behavior

- Identical bytes already registered: link the receipt to the saved statement; do not reopen or modify it, including completed/archived statements.
- A confident semantic duplicate under the existing same-vendor/date/invoice/amount/activity/total rules: link to the existing statement and retain the incoming original/receipt evidence.
- An overlapping statement with added invoices: retain the complete incoming statement and all activity, identify repeated/new items and permit the new draft. Do not silently discard carried-forward invoices or credits.
- A similar or uncertain statement: retain original/extraction evidence as a mail attention item, with explicit **View existing** / **Import separately** choices. No headless substitute for the existing user's similarity prompt.

Candidate-head revisions and mapping/source versions are checked again atomically at publication. Conflicts cause reassessment rather than overwriting human work. Use deterministic statement/row identities for accepted attempts and idempotent publication. Automation may create its own unconfirmed draft, or update only its own unchanged unconfirmed revision with an expected-head guard. Any human edit, PDF confirmation, completion, archive, reopen or incompatible head change blocks automated document writes.

## Comparison and human review

Current `reconcile` intentionally returns extraction-review statuses until a person confirms the PDF. Preserve this contract. Factor its common matching calculation for a new **preliminary** comparison entry point, rather than setting `confirmed=true` or fabricating reviewer decisions. Store preliminary evidence separately from human review results and mark it clearly in the UI. It cannot satisfy completion or count as a reviewed item.

Reuse the exact existing vendor/reference/amount, Adventure trailing-letter, currency, warning, credit, balance and range policies. Source reads use an explicit machine-authorized, read-only facade over the existing validated snapshot/working-set queries; do not invoke the interactive API with a fake session. The supported source formats are legacy rows, snapshot-v2 and acknowledged working sets. Incomplete directories/candidate pages are not successful comparisons. Working-range exclusions remain `Check archived data`, not `Missing`.

Pin import ID/version, active working set/version/protection epoch, mapping revision/digest and matching/parser version. Revalidate before publishing. A changed source retries comparison using the saved extraction rather than repeating OCR. The checker also discovers stale preliminary comparisons on untouched, unconfirmed mail drafts and queues a bounded recompare. It never rewrites completed/manual/human-edited review history. Preserve explicit human notes and decisions.

Missing BILL data produces a saved `Waiting for BILL data` draft. Freshness displays the actual saved export label/upload time; a proposed seven-day upload-age warning reflects the existing weekly-export workflow, not proof of live BILL freshness. Standalone credits absent from Bills exports remain a manual limitation. Low-confidence rows, unknown vendors, source warnings, unrecognized documents and comparison discrepancies stay visible for review. No automatic final completion, reviewer initials, paid confirmation, BILL writes or vendor emails in this release.

## App experience

Add a small Email imports section/card with connection status, selected mailbox/label, last completed check, queued/scanning/attention counts and rows linking to the original or saved statement. Each item shows Gmail received time separately from app import time and statement date, rendered in the app's existing New York convention. States cover Queued, Scanning, Automatically scanned/Awaiting review, Needs attention, Already imported and explicitly skipped work.

Provide authenticated pause/resume, retry and bounded historical-import controls. Pause prevents new discovery/claims; an already running document may finish safely and the UI says it is finishing. Changing account/label requires a new connection generation and preserves old receipt/history evidence. Existing drafts/manual uploads remain usable if email intake is disconnected.

Refresh only email status/list changes, at a modest interval while visible. Do not rerender the whole app or remount the PDF viewer, discard unsaved edits, or unexpectedly replace the active document. New statements appear in normal vendor views after publication; mail attention items have explicit actions. Receipt-original previews use an AP-authorized endpoint that validates workspace ownership and the saved object hash/path before issuing a short-lived private URL; a caller cannot supply an arbitrary storage key. Require a schema capability flag and keep old workspaces functional before migration.

## Machine access and deployment

Both Cloud Run services require IAM authentication, with separate scheduler/dispatcher/runtime identities and least-needed Cloud roles. Configure queue/task OIDC audiences and authorized callers explicitly. Coordinator secrets stay in Secret Manager; the extraction child has no Gmail/Supabase credentials or external network access. Reuse the project's private Supabase backend credential only server-side, with fixed configured workspace/bucket and narrow, service-role-only mail RPC operations. The browser receives no service credentials. The interactive mail controls retain existing AP session authorization. Do not weaken `require_access` or allow a machine caller to complete reviews, change mappings, activate BILL imports or archive statements.

This is a project-sized change: worker, connector, private persistence/protocol, app status and deployment tooling. This design authorizes planning only. Implementation starts after design approval. External account authorization, billing/resource provisioning, production SQL application, merge/push and activation remain separate concrete rollout steps; no such action has occurred here.

Deliver local code/tests and Windows-friendly setup/deploy instructions. Before live activation: confirm the target cloud project/region and existing AP workspace, resolve Gmail production authorization requirements, present measured resource/cost expectations, test all required migrations on an authorized synthetic project, preserve recovery definitions/counts, deploy IAM-protected services, authorize Gmail, and run one owner-selected statement end to end. Let the owner choose new-only versus historical import, then enable the five-minute schedule. Existing merged AP changes/pending migrations must be included in that rollout inventory.

## Acceptance and recovery

- A labeled incoming statement reaches the durable queue with the app/browser closed. Repeated polls, same-thread new attachments, duplicate deliveries and identical/semantic repeated statements do not create duplicate drafts.
- Digital/scanned/dot-matrix/credit/overlap fixtures have parity with the existing parser and matching rules, including exact amounts, row/page/source references and the effective limits. Unknown or failed reading never appears as a clean zero-invoice success.
- A simulated month-end burst (at least 100 PDFs) preserves every receipt across pagination, retries, restarts, history expiry, lost enqueue replies and lease takeover, with at most one active processing claim. No secret/raw email/PDF/financial payload appears in logs.
- Wrong caller/workspace, stale generation/source/head, incomplete archives/pages, replayed publication and human-edit races fail safely. SQL ACL/RLS, storage paths and authenticated controls are verified locally and in an authorized synthetic cloud/database round trip before production acceptance.
- UI polling preserves open PDFs, selected invoices and unsaved drafts. Existing AP/Daily Deposit tests remain green. Measure scan/queue throughput, cache peak memory and interactive app/database latency; do not promise no slowdown from architecture alone.
- Pausing the scheduler/connection/queue stops new work without deleting originals or review evidence. Recovery is resume/retry/reconnect, not resetting history or erasing imported statements. Keep compatible readers and disable the new capability on rollback.

## Decisions left to the builder

Module/table names, exact test fixtures, pinned compatible browser/library versions, safe cache eviction and deployment script mechanics may be settled during implementation without changing the approved behavior. The numerical runtime/retry/resource defaults above are proposals to verify and document; changes that alter user-visible import, confirmation or retention policy return for approval.

## Primary references

- [Gmail synchronization and history recovery](https://developers.google.com/workspace/gmail/api/guides/sync)
- [Gmail read scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [OAuth desktop authorization](https://developers.google.com/identity/protocols/oauth2/native-app)
- [OAuth refresh-token lifetime in Testing](https://developers.google.com/identity/protocols/oauth2)
- [Restricted-scope verification and exceptions](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)
- [Scheduled Cloud Run requests](https://docs.cloud.google.com/run/docs/triggering/using-scheduler)
- [Cloud Tasks with Cloud Run](https://docs.cloud.google.com/run/docs/triggering/using-tasks)
- [Queue concurrency and retry controls](https://docs.cloud.google.com/tasks/docs/configuring-queues)
- [Streamlit Community Cloud hibernation](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app)

## Design check record

A fresh independent builder check read this design and reported **nothing important left**. The author then made the processor-slot scope and authorized receipt-preview boundary explicit; these clarify the existing one-worker/private-original requirements. Baseline Node tests for core parsing, statement duplicates and shared workspace passed **46/46** on the isolated checkout. The first sandboxed attempt was prevented from spawning test processes; the permitted run passed. No dependencies were installed and no product or deployment code was changed during design preparation.
