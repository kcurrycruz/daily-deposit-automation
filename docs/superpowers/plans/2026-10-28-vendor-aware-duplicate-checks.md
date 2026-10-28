# Vendor-aware duplicate checks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add corroborated invoice-entry and wrong-vendor warnings while keeping repeated references contextual and all financial decisions manual.

**Architecture:** Extend the current disk-backed cooperative detector with historical monthly vendor profiles, indexed compact-reference candidate searches, and recorded profile evidence. Publish immutable v3 scans in a v2 result artifact, preserving prior scans/reviews and applying the additive compatibility migration before deployment.

**Tech Stack:** Python/SQLite, existing Streamlit bridge, native JavaScript modules, PostgreSQL migration/PGlite tests, unittest and node:test.

**Spec:** `docs/superpowers/specs/2026-10-28-vendor-aware-duplicate-checks-design.md` (approved by the user on October 28, 2026).

## Global Constraints

- New rules are suggestions requiring review; never change BILL or auto-resolve findings.
- Profile windows: preceding 365 days before the earlier candidate's calendar month; minimum 20 distinct references; at most three shapes, each supported by at least three references, covering at least 90% together; stable lexical tie order.
- New pairs require equal positive amount, compatible/unknown currency, valid dates within three days, corroborating historical profiles, and unambiguous identities.
- Different-day local candidates with at least ten earlier references on six dates in the preceding 90 days do not produce the new warning.
- Keep v2 rules and history. Annotate exact-reference reuse more than 30 days apart without hiding or resolving it.
- Rule `bill-duplicates-v3`; result format `bill-duplicates-v2`, namespace `bill-duplicates/v2`; preserve v1/v2 owned paths without accepting mismatched versions.
- Existing 5-second cooperative deadline, 5,000 input records/step, 10,000 probes/step, 500,000 records, 100,000 findings, 512 MiB working/artifact size and 32 MiB compressed result limits remain enforced.
- No private source data or financial examples in commits; use synthetic regression data.

## Review Focus

- A supplier changes invoice length: profiles use only earlier months, accept supported secondary formats, and do not create standalone outlier findings (Task 1/2).
- A candidate pair crosses a calendar-month boundary: both profiles use the earlier month's boundary, regardless of input order (Task 2).
- Identical totals and consecutive references occur on the same day: matching shapes cannot create new typo warnings (Task 2).
- Both vendors share a generic numeric format: there is no directional format evidence, so no wrong-vendor warning (Task 2).
- New evidence or migration input is corrupted or its source/session changes: fail closed and preserve immutable history, source data, and unsaved review drafts (Task 3/4).

---

### Task 1: Historical format and recurrence evidence

**Files:** create `app/ap_shared/bills/duplicates/vendor_patterns.py`; create `tests/test_ap_duplicates_vendor_patterns.py`.

**Interfaces:** `reference_shape(reference) -> str`, `compact_reference(reference) -> str`, `edit_kind(left,right) -> str|None`, lazy `reference_variants(reference, shapes) -> iterator[str]`; `VendorPatterns(db)` uses scanner node rows, `advance(vendor, month_start) -> profile|None` processes one bounded batch and caches completed immutable monthly profiles; `recurrence(vendor, amount, earlier_day) -> bool|None` cooperatively checks the 90-day thresholds. None means preparation is incomplete. Profiles contain periodStart, periodEnd, distinctReferences, shapes, established, and per-shape support.

- [x] Write failing tests for the 20-reference floor, secondary formats, 90% coverage, ties, distinct voting, candidate/future-month exclusion, leap/year boundaries, sparse history, and recurrence cutoffs.
- [x] Run `python -m unittest test_ap_duplicates_vendor_patterns -v` with PYTHONPATH=tests; confirm intended missing implementation failures.
- [x] Implement pure normalization/edit helpers plus indexed, 250-row cooperative profile/recurrence preparation. Record no actual bill rows in caches beyond required source locators and derived counts; enforce bounded progress.
- [x] Run these tests and existing rule tests; confirm passing. Commit Task 1.

### Task 2: Indexed scan integration and recorded explanations

**Files:** modify `app/ap_shared/bills/duplicates/scan.py`, `rules.py`; create `tests/test_ap_duplicates_vendor_scan.py`; modify `tests/test_ap_duplicates_scan.py` only for deliberate probe-count changes.

**Interfaces:** scanner node rows gain compact reference and shape with explicit column mapping. Add vendor/day and vendor/amount/compact/day indexes and compact/amount/day cross-vendor lookup. Scanner `step` preserves its existing return contract. New findings use classifications `reference_entry_issue` and `possible_wrong_vendor`; every finding records a versioned evidence JSON object containing date gap and, for new rules, both immutable profile comparisons. Existing `findings` artifact rows gain an evidence column. A transient profile/pair job resumes before scanning continues.

- [x] Write failing end-to-end scan tests for missing/extra characters, punctuation, wrong-vendor counterparts, repeated totals, same-day sequential references, common formats, inconsistent currencies, ambiguous source groups, monthly boundary/order reversal, stable rerun keys, complete two-vendor search text/membership, and reused-reference context.
- [x] Run `python -m unittest test_ap_duplicates_vendor_scan -v`; confirm failures on missing v3 behavior.
- [x] Integrate profiles and lazy indexed edit variants. Only outliers under the current/necessary previous-month profiles generate new local edit searches; verify pairs against profiles for the actual earlier month. Cross-vendor matching uses exact compact reference+amount/date and both established profiles. Never enumerate vendor-wide all-pairs.
- [x] Make date gaps/context explicit for existing findings; include all members' vendor names in search text. Keep finding key inputs deterministic and versioned; deduplicate repeated candidate routes on disk.
- [x] Run Task 1/2 tests plus existing rule/scan tests, including bounded one-probe resumption and ambiguous 10,000-row grouping. Commit Task 2.

### Task 3: Artifact, projection and database compatibility

**Files:** modify duplicate `contracts.py`, `artifacts.py`, `repository.py`, `projection.py`; modify `app/ap_shared/repository.py`; add `supabase/migrations/202610280001_ap_duplicate_vendor_rules_v3.sql`; update related artifact/projection/operation/repository/rule/schema tests and SQL fixture.

**Interfaces:** `RULE_VERSION='bill-duplicates-v3'`, `ARTIFACT_FORMAT='bill-duplicates-v2'`, `STORAGE_VERSION='v2'`; `validate_evidence(value)` validates bounded JSON without accepting unsupported versions/profile shapes. Result writer/cache validate the exact expanded v2 schema; projection exposes finding evidence and both new classification filters. RPC actions and review-save payloads stay unchanged.

- [x] Add failing round-trip/corruption tests, private path tests, new-filter tests, and v3 SQL lifecycle tests with rejected mismatched rule/format/path combinations; preserve v1/v2 lifecycle checks and historical-row checksums.
- [x] Run focused Python/SQL tests and confirm expected failures.
- [x] Implement v2 artifact contract and validation, v3 rule identities, exact storage namespace allowlists, and projection evidence. Update test fixtures to use constants where they mean current versions; retain explicit legacy tests.
- [x] Add transactional, retry-safe guarded SQL replacements for the v3 allowlist and rule-dependent manifest format/path. Preserve all lifecycle, source, quota, review, ACL, and immutable-history checks; reject unexpected function shapes.
- [x] Run full duplicate backend suites and PGlite migration tests. Commit Task 3.

### Task 4: Review UI

**Files:** modify `app/ap_statements/frontend/duplicate-bills-ui.mjs`, `styles.css`; extend `tests/ap_statements_duplicates_ui.test.mjs` and relevant controller tests.

**Interfaces:** consume immutable `finding.evidence`; add new pattern labels/filters and reason labels. Wrong-vendor rows and accessible names show both vendors. Detail displays training period, support, expected shapes, fit/outlier, edit type/date gap, and unknown-currency caveat. Existing save/navigation/controller interfaces remain unchanged.

- [x] Add failing rendering/accessibility/escaping tests for both new classifications, multi-vendor rows/search, reused-reference context with amount discrepancies, and sparse/malformed evidence fallback.
- [x] Run focused node tests and confirm intended failures.
- [x] Implement compact list explanations and read-only profile evidence in existing detail view, with no automatic vendor choice or financial resolution.
- [x] Run all frontend node tests and production build. Commit Task 4.

### Task 5: Verification, migration prerequisite and merge

**Files:** update scale fixture for v2 artifact constants; add anonymized profile-heavy scale coverage; create verification record under `docs/superpowers/verification/`. Keep real-export recheck scripts/results in local artifacts only.

- [x] Run full backend/frontend suites and production build. Run the existing 223,425- and 500,000-record complete scale checks and a profile-heavy valid-date case; require bounded steps/memory and stable results.
- [x] Re-run v3 against the locally reconstructed real export with original hash verification; compare classifications/keys to v2 and inspect representative source rows. Report rule refinements' candidate changes without claiming accuracy or automatically changing any review.
- [x] Dispatch a fresh read-only whole-branch reviewer as required by executing-plans. Resolve actionable findings and rerun affected checks; do not rerun unchanged expensive checks without cause.
- [x] In the confirmed AP Supabase project, capture existing definitions/constraints and row/ACL baselines, apply the reviewed v3 migration before deployment, then verify preserved history/access. If user authentication or specific approval is needed, retain the tested branch and present the concrete migration as the final remaining action.
- [x] Squash only the reviewed feature change into DD-v2 after prerequisite completion, verify the resulting source tree and relevant merged checks, and report the merge commit and push/deployment status accurately. Do not publish private analysis data or archive the preserved worktree.

## Execution authorization and self-review

The user already selected native execution earlier in this chat and explicitly approved implementation, testing, and merge with the design. Continue inline using that authorization; do not ask again for the same implementation permission. All spec sections map to Tasks 1–5; all five review-focus cases have named tests above. Internal helper names, evidence fields, and version constants are consistent across tasks.
