# AP exact-reference exclusions and digit-typo rollout

Status: local implementation, independent-review fixes and local release checks are complete. Both numeric release sizes passed their original limits. No production migration, activation, merge, push or reboot has been performed for this change. See the [verification record](superpowers/verification/2026-10-30-ap-exact-reference-filter.md) for the exact evidence and remaining rollout gates.

## Approved behavior

Duplicate alerts exclude groups whose every verified member has the same normalized vendor and invoice number, regardless of amounts, dates or repeated export rows. Case/whitespace normalization remains; zeros, punctuation and letter suffixes remain meaningful. This follows the owner's BILL entry workflow assumption; it does not prove payment uniqueness or automatically save Not a duplicate decisions. Original records, immutable scan results, reviews and events remain stored.

The new single-digit rule finds different equal-length invoice references (at least four characters) with one ASCII digit substituted when vendor, numeric original amount and valid invoice date agree. Known conflicting currencies reject the candidate. Unknown dates and different dates do not satisfy this rule, protecting routine daily deliveries. Other suffix/swap/format/wrong-vendor rules remain in place. Statement reconciliation amount discrepancies remain independent.

## Database and application order

Confirm the intended project/workspace and obtain authorization before any external mutation. The preceding range migrations were pushed but were not applied in this task. Save private recovery definitions for ap_duplicate_mutate, constraints/ACLs and workspace version/pointers, plus scan/review/event counts. Keep recovery financial data outside git.

In a disposable authorized synthetic Supabase project, apply all prior migrations, including these in order:

1. `202610300001_ap_bill_working_sets.sql`
2. `202610300002_ap_duplicate_working_scope.sql`
3. `202610300003_ap_duplicate_near_references.sql`

The third migration adds duplicate_near_schema_version=1, allows v5 full/v6 working scans, and preserves immutable old scans and reviews. Guarded function rewrites reject an unexpected database function rather than guessing. Do not bypass a guard or edit an already deployed migration. Confirm independent-connection source/range/review interleavings and deployed ACLs; local PGlite tests are sequential and cannot prove those behaviors.

Before deploying, verify the release record and all gates. Coordinate migration/application rollout: old application code may request legacy scan versions after the new database flag activates and receive a conflict until the compatible application loads. Existing statements and BILL data remain unchanged. No shared-app reboot has been authorized.

Deploy the approved commit, then reload AP sessions to refresh bootstrap capability `duplicateNearReferences:1`. Existing full sources select bill-duplicates-v5; acknowledged working ranges select bill-duplicates-v6. Old workspaces without the migration retain v3/v4 behavior. New rule versions generate new scan identities and finding keys; prior reviews remain stored and are not automatically applied as decisions to new-rule findings.

Exact-reference filtering is a projection policy and applies to saved legacy scans without rewriting them. The list, badge and pagination show visible alert counts; excluded exact-reference groups are disclosed separately. An older saved scan is explicitly labeled as not including single-digit typo checks. Old immutable evidence remains readable through compatible historical paths.

## Acceptance and recovery

Verify the Albert-like exact group is excluded; a synthetic 8-to-9 typo with equal vendor/amount/date appears; changed dates/amounts and daily sequential purchases do not satisfy the new rule; wrong-vendor findings remain; source/scope conflicts, interrupted preparation and review drafts recover. Do not save fabricated decisions in the live finance workspace. Compare preserved original/history counts before/after.

Read-only checks after authorized migration:

```sql
select id,duplicate_schema_version,duplicate_near_schema_version,
       active_import_id,active_working_set_id
from public.ap_workspaces where id='<confirmed-workspace-uuid>'::uuid;
select rule_version,state,count(*) from public.ap_duplicate_scans
where workspace_id='<confirmed-workspace-uuid>'::uuid group by rule_version,state;
select has_function_privilege('anon','public.ap_duplicate_mutate(text,uuid,uuid,text,jsonb)','execute') as anon_can_mutate,
       has_function_privilege('authenticated','public.ap_duplicate_mutate(text,uuid,uuid,text,jsonb)','execute') as authenticated_can_mutate;
```

Both privilege results must be false; confirm service_role access and existing RLS. Do not drop migrations or delete historical artifacts to roll back. Prefer roll-forward. If an owner-authorized recovery is needed, lock the confirmed workspace and disable duplicate_near_schema_version while retaining compatible v1-v6 readers; new sessions return to v3/v4 current scans and new v5/v6 evidence remains stored. Preserve the previous workspace row first. This procedure is not authorization to run it.
