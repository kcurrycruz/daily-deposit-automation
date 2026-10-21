# AP shared workspace setup

The AP upgrade needs an owner-controlled Supabase project before it can be released. Set up a separate synthetic test project first, run the release checklist, then authorize production setup. Daily Deposits and Credit Cards do not require these credentials.

## Create the private workspace

1. In your Supabase account, create a test project. Keep its database password and secret API key out of chat and Git. Share only the project URL when asking for help.
2. In the SQL Editor, review and apply `supabase/migrations/202610130001_ap_shared_workspace.sql` once to the new project. It creates AP tables, private permissions and transaction functions. Do not apply it over existing tables or remove tables to make it run.
3. Create one workspace using the SQL below. Copy the returned UUID into Streamlit Secrets.

```sql
insert into public.ap_workspaces(id) values(gen_random_uuid()) returning id;
```

4. In Storage, create `hwfc-ap-private` with **Public disabled**. For the large-export release, follow `docs/ap-bill-snapshot-rollout.md`: apply the additive snapshot migration, use a 32 MiB object limit and allow `application/gzip` alongside `application/pdf`, `text/csv`, and `application/octet-stream`. PDFs remain capped at 20 MiB in the app. Do not create anonymous or authenticated Storage policies for this bucket. Check existing broad policies if the project is shared with other apps. [Supabase private bucket access](https://supabase.com/docs/guides/storage/buckets/fundamentals).
5. Verify direct browser-facing requests cannot read AP tables, call AP functions, download private objects or mint signed links. A publishable key must not provide access. The runtime also refuses financial operations if the bucket is public.

## Enter Streamlit Secrets

Open the deployed app's settings and enter the values directly in Secrets. Replace each placeholder; never paste actual credentials into a source file, chat or screenshot. [Streamlit secrets guide](https://docs.streamlit.io/deploy/concepts/secrets).

```toml
[ap]
password = "REPLACE_WITH_A_NEW_TEAM_PASSWORD"
supabase_url = "https://YOUR_PROJECT.supabase.co"
supabase_secret_key = "REPLACE_WITH_SERVER_SECRET_KEY"
workspace_id = "REPLACE_WITH_WORKSPACE_UUID"
bucket = "hwfc-ap-private"
```

Use the server secret key, not a publishable key. Choose a new team password before production use because the earlier value was posted in chat. A password or backend credential change invalidates existing sessions on their next operation. Access expires after eight hours; Lock AP ends access immediately. Previously downloaded files and already-issued five-minute links cannot be recalled.

## First use

Unlock AP, import the original Bills CSV once, then upload statement PDFs. The initial loading screen remains until the saved source, drafts, mappings, and their initial comparisons are ready; a failed load offers Retry instead of an empty dashboard. Up to twenty PDFs may be selected together; each PDF is capped at 20 MiB. The new snapshot importer supports original CSVs up to 256 MiB, subject to 32 MiB compressed artifacts and 500,000 normalized records. Legacy imports keep their earlier limits. Only complete statement-specific candidate sets load before matching. Each weekly export replaces current comparison data; overlapping exports do not append invoice copies. Draft comparisons automatically refresh against current BILL data; completed evidence stays frozen. See `docs/ap-bill-snapshot-rollout.md` for every limit and the required cloud/recovery gates.

Check the extraction, confirm invoice rows, review unresolved comparisons, then mark reviewed with your initials. Notes are optional. Amount-only suggestions and native BILL exports retain their limitations after completion; review does not verify QuickBooks sync. Previous Statements opens frozen review evidence. Reopen starts further work without rewriting earlier completed evidence.

Vendor is its own main sidebar item: type to filter the vendor directory, then open a vendor's previous statements. Previous Statements separately shows all saved reviews, newest completions first. Date, initials and status filters are collapsible. Hover over a statement for a private first-page preview, or choose Quick preview using a keyboard or touchscreen. View revision opens its frozen review and original PDF. PDF thumbnails load only on demand, are cached briefly in memory, and clear when AP closes; they are not stored in browser localStorage.

The upload area supports dragging multiple PDFs or clicking to browse; both paths use the same duplicate checks. Unresolved vendor selection filters as you type and supports arrow keys and Enter. Choosing a search result does not save a mapping: confirm with Use this vendor.

Statement review fills the app width. Click anywhere in an invoice row (or activate its reference button) to open inline details and its PDF source page. A unique native-text reference-and-amount line can be highlighted; ambiguous layouts and scans use the source page and extracted-text fallback. Returning to the list preserves unsaved form values. When the existing comparison supplies a single same-vendor amount suggestion with a different reference, an explicit confirmation can save a review while retaining both original numbers and the original comparison result. Suffixes such as X are never stripped automatically. This does not add new match candidates; a record differing in both reference and amount still uses existing follow-up behavior and cannot be silently accepted.

Statement uploads check current drafts and saved completion history before adding a content-identical copy. Automatic reuse requires the same exact or explicitly mapped vendor, date, invoice references, original amounts, balances, printed total and account activity, with complete and confident extraction. Uncertain scans, changed dates or amounts, and partial statements offer a Similar statement found prompt: cancel, open the saved statement, or keep the upload as a new statement. Repeated invoices plus new invoices are allowed on a later statement, with repeated/new counts shown; prior PDFs and reviews are not merged or overwritten. Same amounts alone never establish a duplicate. These are upload-time browser checks, not a database-atomic content-uniqueness guarantee across simultaneous users; existing server-side identical-file hash handling still applies. No records are created in BILL by these checks.

Use Import old browser work only when you want to migrate existing notes and corrections. It creates unconfirmed drafts, excludes demo data, and leaves browser data intact. Attach each original PDF and confirm it again. Select the original Bills CSV once to store the shared source; browser metadata alone cannot recreate its original bytes. Do not migrate company data until production access and backups have been approved.

## Administrative cleanup

Ordinary reset reloads the local view; archive hides a working statement without deleting its revisions or original. No ordinary user action permanently deletes shared history.

For staging cleanup, first pause uploads and take a backup. List expired `ap_uploads` rows older than an agreed retention period (at least twenty-four hours). Inspect the exact workspace/upload UUIDs and their object manifests. Delete only staging objects under those exact expired upload prefixes, after confirming no live upload uses them. Ready originals under `pdf/` and `csv/` are not staging objects. Never remove a referenced original or completion event automatically. Unreferenced original-file cleanup needs a separate administrator review comparing both statement/import references and upload metadata. Avoid wildcard bucket deletion.

## Back up and restore

Keep an encrypted database backup and a separate encrypted object-file backup with a manifest of object keys, byte counts and SHA-256 hashes. Restrict access to both and keep a copy outside the live project. Database backups do **not** include Storage file bytes. [Supabase backup scope](https://supabase.com/docs/guides/platform/backups).

Before relying on this archive, restore both backups into a separate authorized test project. Preserve UUIDs, revisions, import ordinals and file hashes. Recreate the private bucket, restore object bytes at the manifest keys, restore database contents, and verify anonymous denial, invoice counts, historical revisions and reopened original PDFs. Compare every restored file hash with its manifest. Record the restore date and results. Do not restore over production or disable immutable-history protections as a shortcut.

## Release gate

Follow `docs/ap-shared-workspace-validation.md`. Merge/push, test-project writes, production configuration and financial-data migration are separate approvals. Local unit tests alone do not prove cloud persistence or backup recovery.
