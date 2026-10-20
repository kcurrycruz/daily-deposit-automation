# Large weekly BILL export rollout

This release is an isolated implementation, not permission to change production. It adds a `snapshot-v2` source alongside existing `rows-v1` imports. A successful weekly full export replaces the active comparison source; it does not append another copy of historical invoices. Previous import versions remain archived for statement evidence.

## Owner-approved rollout order

1. Back up the AP database **and** private Storage object bytes separately. Include workspace/import UUIDs, object keys, sizes and SHA-256 hashes. Test restoration into a separate approved project; do not assume a database backup includes Storage files.
2. In a disposable authorized test project, apply the existing AP migrations in filename order, then `supabase/migrations/202610190001_ap_bill_snapshots.sql`. On an existing project apply only migrations not already applied. Do not drop/recreate tables or remove old imports. The additive migration introduces snapshot manifests, resumable jobs and the monotonic active-import version guard, including legacy writers.
3. Keep the bucket private. Raise its per-object limit to **32 MiB** and allow `application/gzip`, keeping `application/pdf`, `text/csv` and `application/octet-stream`. The application still caps each PDF at **20 MiB**. Do not add public, anon or authenticated Storage policies.
4. Deploy compatible server actions and UI together to the test portal. Bootstrap advertises `capabilities.billSnapshots = 2` only after the migration. Without that capability the UI can read existing data, but new uploads show a migration/deployment message; it never falls back to reading the full CSV in the main UI thread.
5. Run the checks below with synthetic data. Obtain separate approval before production migration/deploy and before importing the actual company export. Keep the prior application version available, subject to the rollback restriction below.

## Limits and capacity

| Resource | Limit |
| --- | --- |
| Original CSV / compressed CSV | 256 MiB / 32 MiB |
| Source rows / normalized records | 750,000 / 500,000 |
| Compressed / expanded SQLite index | 32 MiB / 512 MiB |
| CSV columns / UTF-8 bytes per field | 128 / 1 MiB |
| Transport chunk / message envelope | 256 KiB / 1 MiB |
| Candidate page / query keys | 500 records, also byte bounded / 100 |
| Build step | 5,000 source rows or 500 groups, cooperative 5-second deadline |
| Builds | One leased job per workspace; two per server process |
| Expanded-index cache | 512 MiB total; pinned readers, LRU, one-hour idle expiry |

Legacy imports retain their 20 MiB / 100,000-record limits. Their full original records remain readable through compatible server queries. No source is truncated to fit a limit.

Optional server-side Streamlit Secrets setting, inside `[ap]`:

```toml
bill_storage_budget_bytes = 900000000
```

The default is 900,000,000 bytes. The value must be an integer from 1 through 9,000,000,000. This is an **application reservation budget, not a billing limit or a plan upgrade**. Do not raise it without checking the account's actual included capacity and approving any costs. Capacity checks count all existing objects in the configured bucket plus active job reservations, reserve staging and final artifacts, and warn at 80%. An insufficient reservation leaves the prior source current. Historical imports and statements are not automatically deleted.

## Verification before production

Local supplied-export measurement (October 20, 2026): 284,365 source rows → 223,425 records; 59,592 line rows consolidated, 1,348 excluded and 1,784 warnings. Original bytes: 155,585,995; compressed CSV: 14,006,851; compressed index: 15,704,647; expanded index: 146,219,008. Raw-byte hash round trip agreed; finalized freelist was empty. Additional peak builder RSS: 21,258,240 bytes. Total local check: 113.031 seconds across 539 steps; maximum source batch: 5,000. Longest step: 6.953 seconds, because cooperative deadlines cannot interrupt an atomic SQLite index/finalization call. This is not a hard five-second real-time guarantee. No company file was uploaded.

- Run Python discovery, all `ap_statements*.test.mjs` Node tests, component build and `git diff --check`. SQL transaction tests use PGlite; SDK boundary tests do not prove live Supabase behavior.
- Run `tests/fixtures/ap_shared/bill_scale_check.py --synthetic-records 223425`. It uses only temporary local files and a synthetic storage boundary. Record counts, archive sizes, peak RSS increase, maximum build-step duration and hash parity. The representative target is less than 256 MiB additional RSS. A failed target blocks rollout; do not silently raise the limits.
- Local-only real-file checking is explicit: `bill_scale_check.py --source <local CSV>`. It prints only sanitized counts, sizes, hashes and timing; it never uploads. Expected supplied export: 284,365 source rows, 223,425 normalized records, 59,592 consolidated line rows and 1,348 exclusions. Parser warning details still require review; a comparison does not verify settled payment, outstanding balance or QuickBooks sync.
- In an explicitly approved synthetic Supabase workspace, upload a source, reupload its identical bytes under another name, then upload an overlapping full export with a changed invoice, a new invoice and an omitted invoice. The active count must equal the latest snapshot alone; changed values replace old current values and omitted invoices are not retained in current matching. The old import remains available to saved statements.
- Recompressing or renaming identical raw bytes reuses the import. An already-current export is a no-op. Restoring an older source requires explicit confirmation. Equal amounts do not establish duplicate invoice identity or choose another reference.
- Use two independent sessions. A legacy import changing the active pointer during a new build must make stale activation conflict. Dropped chunk/activation acknowledgements must replay with the same request identity and have one effect. Restart the server mid-build; require explicit restart from the saved original, not a partial activation.
- Test a cold cache, expiry/credential rotation, private PDF links, final candidate-page failure, and an unavailable vendor-directory page. Incomplete results must say unavailable/unverified, never uniquely matched or missing. All pages must arrive before matching.
- Preserve a dirty draft, saved older draft and completed statement during import. Dirty edits require save/cancel. The saved draft keeps its source until **Compare with current BILL data** is chosen; notes and corrections stay, refreshed decisions need review. Completed results remain frozen. Notes remain optional; initials remain required.
- Browser QA: current metadata count, progress stages, duplicate no-op, old-source confirmation, restart, failure retaining prior data, tutorial snippets, keyboard focus, sidebar return, desktop/narrow bottom scrolling and worker cancellation after navigation. The initial local file-chooser check stalled; it is not end-to-end upload evidence. Retry this in the authorized test deployment before production.

## Cleanup and rollback

Ordinary successful upload cleanup removes only exact acknowledged staging chunk keys from that job after its verified original is durable. It never removes `bills/v2/`, PDFs or completed history. Failed/abandoned uploads can leave reserved or unreferenced objects. Leases expire after one hour; do not interpret expiry as permission to remove arbitrary objects. Administrative cleanup requires a backup, an exact job/object manifest, proof the job is no longer live, and a separate reviewed deletion. Never delete broad workspace/bucket prefixes automatically.

Temporary process directories are derived and private. A restart loses them safely; the durable original is the recovery source. Hash-verified server-generated indexes open read-only. Arbitrary uploaded SQLite databases, paths and SQL are not accepted.

Once a v2 source is active, **do not roll back to old full-reader code**: it cannot load the new snapshot as legacy rows. Use a compatible patched release, or explicitly restore an approved legacy source using compatible code before switching versions. Back up and verify frozen statement references before any restoration. Source restoration does not authorize rewriting historical evidence.

No part of this workflow posts accounting entries to BILL or QuickBooks.
