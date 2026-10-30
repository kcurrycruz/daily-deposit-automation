# AP active BILL range rollout

Status: local implementation and release verification complete; production rollout is gated. See [verification results](superpowers/verification/2026-10-30-ap-active-bill-range.md). Nothing in this document has been run against the shared database or deployed app. Do not activate until the independent-connection, deployed ACL and authorized synthetic Supabase checks below pass.

## User behavior

BILL data offers **Last 12 months** (default for new updates) and **All imported dates**. Existing full sources remain full until an acknowledged change. Preparation shows active/full/archived counts, the frozen New York cutoff, and retention reasons; Apply publishes source and range together. Cancellation/failure retains the acknowledged workspace. The full CSV/index, PDFs, completed revisions, scans, and review events are retained. This feature does not delete 2025 records or reduce durable storage by itself.

Older invoices stay active when unpaid/uncertain, undated/invalid, associated with unresolved saved follow-ups, or non-invoice activity. Paid status alone is insufficient: exclusion requires zero reported due, or missing due plus exact reported paid/credit coverage, with no source issues. Future dates remain active. Found invoices still do not prove payment settlement.

Absent references under limited coverage display **Check archived data**. The invoice detail offers an explicit exact-reference lookup in the full saved export and marks archived matches. Amount-only suggestions never search all archived bills automatically. Credits absent from the Bills export still require checking directly in BILL.

A saved recent/open follow-up has no new retention effect and reuses verified active/context artifacts. A newly protected older excluded reference requires new preparation. Protection collection and cold exact lookups resume across bounded requests; failure is unavailable coverage, never proof of absence. Evidence-identical statement decisions survive protection refresh through startup, invoice preparation, and background refresh. Resolving an older follow-up can move its bill out of the active range; the saved same-export evidence and decision remain visible, explicitly labeled as previously reviewed. A different export, policy, mapping or invoice input still requires evidence comparison or re-review.

## Before deployment

1. Verify the intended Supabase project and workspace with the owner. Earlier project approvals do not authorize these new migrations.
2. Save a recovery copy of the current workspace row, function definitions, relevant constraints/indexes/ACLs, and row counts for imports, statements/revisions/completions, scans/reviews/events. Keep financial rows and recovery files outside git.
3. In a separate disposable synthetic project using the deployed PostgreSQL version, run the migrations and test two independent connections: competing range activation; saved follow-up committed while another range is prepared; duplicate publication after range change; idempotent reply replay after epoch change; lease/session rotation; transaction rollback. Local PGlite checks exercise serialized transactions, not independent connections.
4. Confirm private bucket status and MIME support for gzip/octet-stream; retain existing limits and storage budget. Reservations account for original, active/context, duplicate and staging artifacts. No access grants to anon/authenticated are added.
5. Coordinate a deployment window. No reboot or shared-session interruption has been authorized for this feature.

Recovery-definition query (read-only; save the results privately):

```sql
select p.oid::regprocedure as signature, pg_get_functiondef(p.oid) as definition
from pg_proc p join pg_namespace n on n.oid=p.pronamespace
where n.nspname='public' and p.proname in
 ('ap_bill_mutate','ap_save_revision','ap_storage_reserve','ap_duplicate_mutate');

select c.conrelid::regclass as relation, c.conname,
       pg_get_constraintdef(c.oid) as definition
from pg_constraint c
where c.conrelid in ('public.ap_workspaces'::regclass,
                    'public.ap_duplicate_scans'::regclass,
                    'public.ap_statement_revisions'::regclass);
```

## Migration and application order

Apply these exact files in order, before publishing the feature application:

1. `supabase/migrations/202610300001_ap_bill_working_sets.sql`
2. `supabase/migrations/202610300002_ap_duplicate_working_scope.sql`

The first adds immutable private working sets, resumable jobs, workspace pointers/version/epoch and pinned statement provenance. The second adds scoped v4 scan identities, unique source/scope digest, v3 result namespace and saved review scope. Guarded function rewrites fail rather than guessing if the existing function differs. If either fails, stop and investigate; do not bypass guards or manually delete scans.

Then deploy the verified feature commit from the approved branch. Confirm bootstrap capability `billWorkingSets:1`, then open BILL data and apply Last 12 months to the acknowledged source. Review actual protected counts before Apply. Original import count and current active count must be distinguished. Applying a range to the same import changes working version without changing import version. An unchanged semantic selection can reuse a verified working set while acknowledging the new protection epoch.

Post-migration read-only checks:

```sql
select to_regclass('public.ap_bill_working_sets') is not null as working_sets,
       to_regclass('public.ap_bill_working_jobs') is not null as working_jobs;
select bill_working_schema_version, active_import_id, import_version,
       active_working_set_id, working_set_version,
       bill_protection_epoch, working_protection_epoch
from public.ap_workspaces where id = '<verified-workspace-uuid>'::uuid;
select has_function_privilege('anon',
 'public.ap_bill_working_mutate(text,uuid,uuid,text,jsonb)','execute') as anon_working,
 has_function_privilege('authenticated',
 'public.ap_duplicate_mutate(text,uuid,uuid,text,jsonb)','execute') as authenticated_duplicates;
```

The final two privilege results must be false. Verify RLS on the new tables and service_role execution. Compare pre/post history counts and representative immutable revisions; do not expose record details in shared logs.

## Live acceptance checks

- Initial load displays ready data together; source/range counts are accurate.
- Prepare/cancel leaves the old range usable; approved Apply becomes authoritative across two tabs.
- An older unpaid bill and an older saved amount-discrepancy follow-up remain active.
- Recent follow-up saves do not start a full-source rebuild or discard compatible decisions.
- Archived exact-reference lookup is explicit and disclosed; limited absence is not labeled full-export absence.
- Zero active coverage remains a valid saved import and supports archived lookup.
- Duplicate scans use working identity, original source member IDs, frozen full-history safeguards and meaningful progress. A completed result does not become a stalled scan merely because its timestamp is old.
- Old PDFs, saved read-only revisions and manual re-review remain available.
- Daily Deposit behavior is unchanged.

Do not save fabricated decisions in the live financial workspace for these checks. Use approved synthetic records/project for mutation tests.

## Recovery

Prefer roll-forward. Cancel only a pending update owned by the current session; this does not replace the acknowledged pointer. Restore broad coverage through **All imported dates**, preserving all history.

Once scoped revisions/results exist, retain v4-aware readers even when disabling new range changes. An older application alone cannot interpret all scoped provenance or satisfy the new guards. Do not drop the migrations/tables, rewrite immutable history, or delete scan objects to roll back.

If the UI cannot recover, an owner-authorized guarded transaction can lock the verified workspace row and clear the current working pointer while incrementing working version and disabling range capability; retain the same complete source and v4-aware read code. Compare expected source/version before changing anything, save the previous row first, and verify reads before reopening traffic. This is a recovery procedure requiring separate approval, not an instruction to run it now.
