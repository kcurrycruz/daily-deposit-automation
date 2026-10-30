# Exact-reference exclusions and digit-typo detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove same-vendor exact-reference noise from AP duplicate alerts and find a substituted digit when vendor, original amount and known invoice date match.

**Architecture:** Keep immutable source/scan/review evidence and apply verified exact-reference exclusions in the shared review projection. Add bounded indexed typo candidates only under new rule versions, retaining the old scanner behavior and compatible artifact readers. Enable new scan versions only after a guarded migration advertises support.

**Tech Stack:** Existing Python/SQLite/Supabase PostgreSQL backend, JavaScript frontend, unittest/Node/PGlite tests; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-30-ap-exact-reference-filter-design.md`

**Execution:** Native, preserving the user's existing execution preference; one independent whole-branch review at the end. Base `e33fc38d9168fa98c521638482d6c09ddd0480e9`, isolated branch `codex/ap-exact-reference-filter`. Existing private artifacts in the reused worktree remain untouched.

## Global Constraints

- Exclude only groups whose every verified member shares the same normalized vendor and invoice reference; preserve zeros, punctuation and suffixes. Existing case/whitespace normalization remains.
- One-digit substitution requires equal vendor and numeric original amount, equal valid invoice dates, no known currency disagreement, and different invoice references. It produces a possible finding, never a confirmed payment duplicate.
- Preserve existing suffix, swap, vendor-format and wrong-vendor behavior. Statement reconciliation amount discrepancies remain unchanged.
- Do not delete or rewrite original data, scans, saved reviews or review events; do not create automatic Not a duplicate decisions.
- Keep 5-second cooperative deadlines, 5,000 input rows, 10,000 probes/step, 512 MiB expanded and 32 MiB compressed result limits unchanged. No vendor-wide all-pairs or unbounded amount-bucket scan.
- No migration application, merge, push, activation or reboot is authorized by this plan approval.

## Review Focus

1. A truncated preview must not hide a mixed-vendor/reference member group; verify every member before excluding it (Task 2).
2. Old scan results must remain interpretable and cannot stand in for a new typo-rule scan (Task 1).
3. A same-day typo can follow the vendor's usual format; format-outlier evidence is not required for this new rule (Task 3).
4. Daily equal-total deliveries on different dates must not satisfy the new rule; neither may ambiguous/unknown dates or currency conflicts (Task 3).
5. Counts, pagination, current-source checks and saved reviews must agree after exclusions and interrupted preparation (Tasks 2 and 4).

---

## Task 1: Versioned rule selection and guarded capability rollout

**Files:** Modify `app/ap_shared/bills/duplicates/{contracts,repository,operations,artifacts,scoped,source}.py`, `app/ap_shared/repository.py`, affected contract/repository/artifact/operation fixtures. Create `supabase/migrations/202610300003_ap_duplicate_near_references.sql`, `tests/test_ap_duplicates_near_schema.py`, `tests/fixtures/ap_shared/duplicate_near_schema_checks.mjs`.

**Interfaces:** Preserve legacy RULE_VERSION v3 and WORKING_RULE_VERSION v4. Add NEAR_RULE_VERSION `bill-duplicates-v5` and NEAR_WORKING_RULE_VERSION `bill-duplicates-v6`. Optional server-owned pin `ruleVersion` selects only the correct full/scoped variant; missing pin field retains old semantics. Add `is_working_rule(rule)` and `rule_for_pin(pin)` dispatch shared by scan/artifact/storage code. Artifact formats remain v2 for full and v3 for scoped, with rule-specific immutable paths. Workspace `duplicate_near_schema_version=1` enables new pins and bootstrap capability `duplicateNearReferences:1`.

- [x] Write failing tests for legacy pins unchanged, valid v5/v6 pins and manifests, mismatched full/scoped versions rejected, old immutable v1-v4 evidence readable on historical paths, and current new scans not reusing old ready results. Test source/session revalidation with the optional field.
- [x] Write PGlite migration tests after all prior migrations: preserve scan/review rows and RLS/ACLs; accept v5/full and v6/scoped lifecycle; reject wrong scope, stale source, epoch or working version; validate manifest format/path and request replay. The additive migration follows the existing 202610300001/2 migrations; never edit shipped migrations. Set the new workspace version only transactionally after guards install. Old workspaces without the migration keep v3/v4 operation.
- [x] Run focused tests RED, implement dispatch and guarded SQL function/constraint updates, then run contract/artifact/repository/operation and schema tests GREEN. Use UTF-8 Python and the existing short-path test environment.
- [x] Commit only Task 1 files and ledger results.

## Task 2: Verified exact-reference exclusions in shared projections

**Files:** Create `app/ap_shared/bills/duplicates/exclusions.py`, `tests/test_ap_duplicates_exclusions.py`; modify `projection.py`, affected projection/operation tests.

**Interfaces:** `ExactReferenceExclusions(source_reader)` cooperatively prepares exact-group exclusions against verified artifact members and current source pin. `advance(projection_db, artifact_db, scan, pin, auth, deadline) -> bool` resumes a finding/member ordinal cursor, verifies member count and original fingerprint/mapping, compares `(vendor_key, invoice_key)` across members, and records an exclusion only after complete proof. A separate projection-local excluded-key table avoids changing immutable artifact schemas or f.* tuple offsets.

- [x] Reproduce Albert-like three repeated rows, same vendor/reference with different amounts/dates, and mixed groups whose first two previews agree but a later member differs. Missing, swapped or partial source/member evidence must remain unavailable and never silently exclude a group.
- [x] Test bounded resume, source/working/review changes, sparse original ordinals, and no repeated full-source download on warm projection work. Any verified differing identity proves a group is not excluded; otherwise consume every member before publication.
- [x] Add the resumable exclusion phase before published counts. Apply exclusions consistently to visible list totals, review filters, pagination and progress counts. Preserve direct saved evidence/review storage; emit a separate `excludedExactReferenceCount` for disclosure, keeping counts keys all/reviewed/unreviewed as visible alerts only. Historical explicit member lookup remains available and verified.
- [x] Run new/projection regressions RED then GREEN with deadline and response-size checks, and commit.

## Task 3: Bounded same-date single-digit candidates

**Files:** Modify `rules.py`, `scan.py`, `vendor_scan.py`; add `tests/test_ap_duplicates_digit_typos.py`, extend scan/rule/working-scope fixtures and scale helper as required.

**Interfaces:** Extend `classify(left,right,*,rule_version=RULE_VERSION)` so legacy callers retain old results. New versions add reason `single_digit_substitution` when equal-length normalized references of at least four characters differ at exactly one position containing two different ASCII digits and other approved conditions hold. The new reason uses classification `possible_duplicate`. Scanner passes its pinned rule version; vendor corroboration uses the same version to avoid duplicate findings.

- [x] Write failing tests for 261398/261399 with equal vendor/amount/date, both fitting normal vendor format; reject differing/unknown dates, differing amounts/vendors, known currency conflicts, unrelated references and multiple substitutions. Preserve leading zeros and punctuation. Test candidates with source warnings remain export-review evidence rather than becoming confirmed bills.
- [x] Generate digit variants lazily/in bounded batches of at most 100 lookup keys and use the existing indexed vendor/reference lookup, equal amount/day and ordinal cursor. Do not run one Python/SQL round trip per variant or build pairwise vendor buckets. Yield between probes and retain stable membership keys across source order/payment-only changes. Preserve old v3/v4 finding sets.
- [x] Add scanner regressions for same-day substitution, daily sequential invoices on different dates, overlapping existing candidate rules, expired deadlines and full/scoped parity. Test long references under existing input limits and small probe budgets.
- [x] Run RED then GREEN focused rules/scan/scope suites. Measure new-version 223,425/500,000 synthetic cases in fresh processes with the existing caps and no artificial limits increase; include a nonzero known typo pair and deterministic repeat keys. Commit.

## Task 4: UI disclosure, release verification and review

**Files:** Modify `app/ap_statements/frontend/{duplicate-bills-ui,duplicate-bills,shared-workspace,guide}.mjs` as needed; extend existing Node UI/controller tests; create `docs/ap-duplicate-near-reference-rollout.md` and `docs/superpowers/verification/2026-10-30-ap-exact-reference-filter.md`.

**Interfaces:** Carry server capability/rule identity through duplicate source adoption so an enabled new rule cannot remain hidden behind a cached legacy result. UI explains exact-reference exclusions and new single-digit reason; it claims same-date digit-typo coverage only for v5/v6 results. Display the excluded-group count separately from actionable alerts. Existing reviewed decisions and conflicts remain unchanged.

- [x] Test accurate filtered empty states/counts, 8-to-9 reason label, old-rule disclosure, capability adoption, source/rule refresh, pagination and preservation of existing review drafts. Run RED then GREEN Node tests and production build.
- [x] Run full backend and all `node --test tests/ap_statements*.test.mjs`, build, and `git diff --check`. Full backend includes old scale tests; new-version scale results must also pass. Investigate failures rather than broad repetition without new evidence.
- [x] Run a read-only local representative-export backtest with aggregate counts only: verify the Albert exact group is excluded, inspect total exclusions and new typo suggestions, preserve source hash, and do not label suggestions as confirmed payments or upload raw data.
- [x] Perform synthetic UI checks when useful; explicitly record unperformed live database/PDF/history tests. Write exact migration order, recovery and capability activation checks; stop before external changes.
- [x] One independent whole-branch review (native execution workflow); re-grade findings, one substantive RED-to-GREEN fix pass, and appropriate full verification. Record all rulings and deferred minors. Commit verification and finish branch without auto-merging/pushing.

## Self-review

The exclusion, typo matching, recurrence safeguard, provenance/versioning, bounded performance, UI/counts and rollout requirements each map to a task. Task 1 provides pinned versions for Task 3 and capability adoption for Task 4; Task 2 supplies consistent visible counts for Task 4. Older scopes and evidence remain intact. Missing deployment authorization and true concurrent Supabase/ACL checks are documented release gates, never claimed as local proof.
