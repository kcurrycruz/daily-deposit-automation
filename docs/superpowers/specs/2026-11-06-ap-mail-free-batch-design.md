# AP Gmail intake with no paid hosting

Date: 2026-11-06. Status: proposed; implementation and activation are not approved by this document.

## Intent and agreed constraints

The owner receives fewer than 50 statement PDFs monthly. Outlook forwarding and the Gmail **AP Statements** label already work. The owner cannot obtain a Google Cloud billing account and wants no paid hosting. They selected GitHub Actions checking twice daily, accepting that imports are not immediate.

Reuse the existing Gmail sync, PDF extraction, BILL comparison, duplicate protection, private storage, and preliminary review UI. Keep foreground Streamlit work separate from PDF processing. The previous five-minute Cloud Run rollout is superseded for this owner; no Cloud Run resources have been deployed or Gmail consent granted for it.

No new hosting subscription, payment method, paid model API, container registry, or Google Secret Manager/Tasks/Scheduler dependency is allowed. The repository is already public: standard GitHub-hosted runner compute is free independently of included private-repository usage. Existing platform limits and Supabase storage limits still apply. Imports stop instead of causing a paid upgrade or overage.

## Approaches considered

1. Cloud Run: existing implementation, durable five-minute operation, but requires billing; rejected by the owner.
2. An existing computer: no additional hosting subscription and frequent checks, but requires an awake connected machine; offered but not selected.
3. GitHub Actions twice daily: independent of Streamlit and a personal computer, with free standard runners on the already-public repository and scheduling/platform limitations; selected by the owner.

## Verified current state and open account checks

The design branch codex/ap-mail-free-batch starts from DD-v2 at e6edd3acd5fd809bc2add02b109913ad713dcb32. The prior cloud implementation is merged. MailProcessor already owns renewal, original/extraction reuse, comparison and fenced publication. The database is the durable queue; Cloud Tasks is currently only a dispatch adapter. The mail connection secret_ref is opaque text in SQL; its cloud-specific validation resides in the Cloud Run adapter.

The four 20261104 mail migrations are still required; they have not been applied to the real database. Existing deployment recovery, private storage, history protections and owner consent requirements remain in force.

The GitHub connector is unavailable in this session. On 2026-11-06 the owner signed the connected Work Chrome profile into KarlHWFC. Browser observation verified kcurrycruz/daily-deposit-automation is Public and its root opens main, showing the older d1c59f8 commit. KarlHWFC has access to the repository but its settings page says repository options are unavailable; only Secrets and variables is exposed. Do not confuse KarlHWFC's billing with kcurrycruz's. No owner billing usage/control has been read or changed. Official GitHub documentation confirms standard runners in public repositories are free independently of the private-repository included allowance.

A schedule must live on the actual default branch. Proposed deployment: a narrowly scoped scheduler workflow on main checks out an immutable, reviewed AP release commit from DD-v2 and invokes its batch entry point. Require execution from the reviewed main workflow for schedule/manual events; do not allow arbitrary workflow_dispatch input refs to receive secrets. Advance the pinned AP source SHA only through a reviewed release. Do not change the default branch, merge the whole newer app into main, or switch Streamlit's deployed branch automatically. Confirm the actual default branch from repository metadata before preparing the final integration diff.

## Schedule and bounded resource use

Builder proposal: run daily, including weekends, near 08:17 and 16:17 America/New_York. Use the currently documented timezone-aware schedule; validate syntax against official GitHub documentation. These are target times, not delivery guarantees: GitHub can delay or drop scheduled events. The existing app continues to show the last successful poll; missed runs are caught up from persisted Gmail history next time.

Use one standard Ubuntu-hosted job, a fixed concurrency group with cancel-in-progress false, and a 20-minute whole-job timeout. This bounds a normal 31-day schedule to at most 62 jobs / 1,240 runner-minutes, excluding exceptional owner-triggered runs. Standard public-repository runner compute does not draw from the owner's private-repository allowance. The limits bound resource use and backlog, not a paid allocation.

The coordinator gets a shorter internal deadline (proposed 14 minutes), a maximum of ten PDF processing starts per run, and enough reserved time for the existing 600-second per-PDF limit before starting another PDF. Never shorten the established file protections or disable the Chromium sandbox to fit a run. On a time/item limit, leave remaining jobs durably queued for the next scheduled run. Do not sleep or automatically rerun workflows to exhaust the backlog.

Before activation, verify the repository remains public and only standard free GitHub-hosted Linux runners are selected. Fail closed before credential exposure if the repository becomes private, the event/repository binding differs, or a paid/custom runner is selected. A private-repository deployment is not implicitly authorized; it needs separately verified allowance and effective paid-usage blocking. Do not add artifact/cache/package storage to this workflow. Do not change any repository visibility or account-wide spending settings. If platform limits prevent runs, delayed imports are acceptable. The public repository must contain code only: keep financial data in private Supabase storage and suppress all identifying PDF/Gmail/BILL content in public workflow logs and summaries.

Avoid persistent Actions caches, uploaded artifacts, container images and paid runners in this intake workflow. Install pinned runtime dependencies on each ephemeral runner. Bound setup as part of the same timeout and measure its actual overhead. Dependency installation/build happens before sensitive credentials are exposed to the processing step.

## Execution architecture

A new finite batch entry point composes the existing domain components directly. It does not start the Cloud Run HTTP server, create public endpoints, or simulate Google OIDC/Cloud Tasks.

1. Validate fixed repository/workspace/connection configuration and explicit enablement. Resolve the configured credential reference; check exact Gmail account and label against the stored connection. Cloud Run's existing adapter remains strict and unchanged in behavior.
2. Repair expired SQL leases using the existing reconciler; this is recovery, not a reason to reset attempts or completed records. Respect connection active/paused state and generation fences.
3. Execute a bounded MailSync poll, preserving baseline-new-arrivals behavior and all durable pagination/history/retry cursors. Keep discovery failures actionable and distinguish discovery success from processing completion.
4. Queue bounded stale untouched comparisons using the existing source protections. Read pending work for the exact configured connection, generation and workspace through a service-only, connection-scoped read (a small additive RPC if needed). The current general workspace outbox must not allow this runner to process another connection's jobs.
5. Run MailProcessor sequentially against ready pending jobs. Its existing SQL claim/heartbeat/workspace slot remains authoritative, even if a manual run races another worker. No synthetic Cloud Task acknowledgement is necessary: jobs remain pull candidates only while queued and due; terminal job state removes them from eligibility. Preserve pending outbox identities for retries and audit.
6. Preserve originals/extraction and resume from durable state following termination or lost acknowledgement. Transient failures use the existing fenced retry budget and due times. Do not spin on an unclaimable or deferred job; advance the bounded page/cursor and leave it for the next run.
7. Emit aggregate counts and allowlisted reason codes only. Never log subjects, senders, invoice numbers/amounts, PDFs, source data, tokens, signed URLs or raw SDK exceptions.

A GitHub-specific credential adapter and coordinator are distinct from the Cloud Run runtime. Shared Gmail token verification and processor construction may be extracted only where behavior stays covered for both adapters. Do not add bypasses to Cloud Run identity checks.

Use a logical secret reference such as github:OWNER/REPOSITORY:AP_MAIL_GMAIL_GRANT for the connection. Treat it as a binding, never as an arbitrary secret selector or network URL. The runner must match it against the pinned GITHUB_REPOSITORY and configured secret name. Backend switching requires a deliberate paused reconfiguration and preserves all receipts/cursors/history. Never run Cloud Run dispatch and GitHub pull processing as an intended dual-backend deployment.

## Gmail authorization and credential handling

Retain Google project hwfc-ap-statements for Gmail API / desktop OAuth configuration. No paid Google compute APIs or billing link are required for this architecture. Confirm Gmail API's current requirements and the applicable restricted-scope production authorization/verification or exemption route before unattended activation. External Testing's short-lived refresh grant is not a durable production solution.

Reuse owner-run loopback PKCE/state/nonce, exact-account/label checks, read-only scopes and verification of the ID token. Add a GitHub destination to the authorization helper. Proposed implementation: official GitHub CLI, authenticated by the owner, writes the grant directly to the exact repository Actions secret through stdin. It must not print tokens, include them in process arguments, or save them in a project/temporary file or clipboard. No Google Secret Manager is used. Validate the repository destination before owner consent; report only safe identity/reference metadata on success.

The owner personally completes sign-in, consent and any credential creation/entry. GitHub receives the Gmail refresh grant and Supabase server credential as private Actions secrets; this persistent access must be reviewed explicitly at setup time. Do not ask the owner to paste credentials into chat. Keep the server credential confined to the fixed-workspace worker operations; acknowledge that it remains a broad Supabase service credential.

Workflow permissions are contents:read except for the owner's separate local secret-writing session. No id-token:write is needed in the batch workflow. Use schedule and deliberate manual dispatch only; never run a secret-bearing job from pull_request or pull_request_target. Read-only Gmail access cannot send mail, change labels, mark messages read, or alter BILL.

Only the coordinator process gets secrets. Existing PDF/browser/domain children retain a credential-free environment and blocked external network. Continue ephemeral private originals, hash checks, file/page/canvas limits, browser sandbox, private bucket and signed-preview restrictions. The runner's workspace, logs, caches and artifacts must not retain financial payloads or grants after the job.

## App behavior

Keep the existing Email imports list, private previews, source evidence, retry/skip/similarity choices, upload time and preliminary status. All automatic results remain Awaiting review. Never set human initials, confirmation, a review decision, or completion.

Any visible text claiming a five-minute interval must become compatible with twice-daily processing. Explain that retry/history/recompare requests are picked up on a later scheduled check. If quota exhaustion prevents a runner from starting, the app can truthfully show an old last-success time; it must not invent a confirmed GitHub billing diagnosis without data. A manual workflow run remains subject to the same allowance, budgets and limits.

Original baseline behavior remains new arrivals only. Explicit bounded Import earlier emails is the only way to ingest selected existing labeled mail. Reused/corrected vendor mappings and newer BILL sources recompare untouched drafts using saved extraction; human-touched and historical records remain protected. Missing credit data remains a comparison limitation.

## Delivery and activation

1. Approve this revised design; implement in an isolated codex/ branch with a task plan.
2. Add the batch adapter/entry point, direct secret destination, guarded twice-daily workflow, any minimal additive SQL read and truthful setup/UI documentation. Preserve the cloud deployment as an optional tested backend.
3. Run targeted unit/integration tests and relevant regressions. Test the actual Ubuntu browser/OCR environment with sandbox enabled and synthetic PDFs. Do not claim Linux acceptance from Windows-only verification.
4. Verify GitHub deployment authority, public visibility, actual default branch, standard free runner selection, no persistent workflow artifact/cache storage, and private financial-data handling. Prepare a minimal reviewed default-branch scheduler diff pinned to the tested AP release. No repository visibility or default-branch change is automatic. If the repository is private by activation time, stop and revisit the design and no-paid-usage controls.
5. Inventory/privately back up the approved database definitions and counts. Apply missing migrations in order only after the real target and recovery copy are reviewed. Preserve all existing financial records.
6. Configure the Gmail API/OAuth client; obtain owner consent with direct private secret storage. Configure only public IDs as variables and private values as secrets. Keep the workflow enable flag off and the database connection paused until readiness checks pass.
7. Test a synthetic PDF end to end, then one owner-selected real statement while the twice-daily schedule is still disabled. Verify private original, one draft/link, correct extracted rows and BILL source, and unchanged human history. Measure runtime and foreground impact against the actual allowance.
8. Review readiness, enable the twice-daily workflow, and confirm a successful scheduled run. The owner may pause imports in the app or disable the workflow. Nothing in this design activates live access by itself.

Recovery disables the workflow/connection, preserves all SQL queues/receipts and originals, and resumes from persisted extraction/history after the fault is fixed. If a job is interrupted, the next authorized run reclaims expired leases. Rollback restores the previous compatible app version and keeps new mail additions private and additive; no financial-data deletion.

## Acceptance evidence

- Exact repository/account/label/workspace/connection binding; paused/missing/wrong-account paths fail closed.
- Empty mailbox, baseline, pagination, label-only changes, history expiry and source-missing paths.
- Only due jobs from the fixed connection; one processor; no busy loop; bounded backlog and retries.
- Overlap/manual races, expired lease, cancellation after download/extraction/publication, ambiguous acknowledgement, generation mismatch, exhausted attempts and retry on a later run.
- Existing exact/semantic duplicate links, overlapping invoices, similarity choices and human-history protections.
- No Cloud Run/Tasks/Secret Manager calls in the batch path; no secrets in child environments, output, temp payloads or artifacts.
- Workflow default-branch semantics, explicit enablement, timezone, pinned trusted actions/dependencies, read-only permissions, no PR secret execution, timeout and storage policy.
- Public-repository/free-runner eligibility verified separately from automated code tests; a visibility change fails closed; measured setup/runtime fits the bounded job.

## Builder discretion

Choose internal class/module boundaries, an efficient dependency subset, and the smallest additive read RPC needed for exact-connection work. Follow the existing Python/Node adapters and test fixtures rather than introducing a second parser/matcher. The schedule and runtime caps above are proposed defaults for owner review. Do not substitute a different hosting platform, weaken privacy protections, broaden Gmail scopes, or promise unlimited free availability.

## Primary references

- https://docs.github.com/en/billing/concepts/product-billing/github-actions
- https://docs.github.com/en/billing/how-tos/set-up-budgets
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- https://developers.google.com/workspace/gmail/api/auth/scopes
- https://developers.google.com/identity/protocols/oauth2#expiration
- https://docs.cloud.google.com/free/docs/free-cloud-features
