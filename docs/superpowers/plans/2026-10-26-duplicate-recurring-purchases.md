# Recurring-purchase Duplicate Checks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop different-day digit-swap false positives without disabling genuine duplicate checks.

**Architecture:** Keep the existing classifier and bounded SQLite scan. Restrict swap candidates to the same invoice day, then introduce `bill-duplicates-v2` as a rule version (not a new artifact format) to trigger fresh scans. A forward SQL migration enables both rule versions without rewriting historical scans/reviews.

**Tech Stack:** Python/unittest, SQLite, PostgreSQL/PLpgSQL, Node/PGlite.

**Spec:** `docs/superpowers/specs/2026-10-26-duplicate-recurring-purchases-design.md`

## Global Constraints

- Apply the rule to all vendors, not a hard-coded vendor exception.
- Exact normalized invoice-reference checks remain unchanged.
- Trailing-letter variations retain their existing equal-amount/30-day rule.
- Retain old scan/review history; do not copy decisions to new-version keys.
- Do not apply production SQL, change BILL records, merge, or push.
- Reuse the existing isolated worktree and preserve its QA artifacts; do not edit `sources/`.

## Review Focus

- A missing/invalid date must never become a same-day swap match: Task 1 classifier test.
- Normalized exact references with different dates remain visible: Task 1 classifier/scan tests.
- Repeated equal totals across daily deliveries must remain bounded: Task 1 scan test.
- A ready v1 result and its reviews must survive the upgrade: Task 2 PGlite upgrade test.
- Overlapping old/new app versions must select separate scans and reject unsupported versions: Task 2 SQL and operations tests.

## Task 1: Restrict digit-swap classification and candidates

**Files:** Modify `app/ap_shared/bills/duplicates/rules.py`, `scan.py`; test `tests/test_ap_duplicates_rules.py`, `tests/test_ap_duplicates_scan.py`.

**Interfaces:** `classify(left: dict, right: dict) -> dict | None` stays unchanged. `DuplicateScan._next_pair()` retains its resumable ordinal/probe contract.

- [x] Add failing `test_digit_swaps_require_same_valid_invoice_day`: equal-total pairs (published as synthetic `990000-R-1303`/`990000-R-1330`) produce `None` on different, missing, or invalid dates; same valid date returns `possible_duplicate` with `digit_transposition`. Repeat for an unrelated vendor and reversed input order.
- [x] Add `test_exact_reference_checks_survive_different_dates`: normalized-equal references across dates still return `exact_pattern`, and different amounts return `amount_difference`. Retain the existing suffix 30-day boundary test unchanged.
- [x] Add scan regressions: different-day recurring swap pairs yield zero findings; same-day swaps yield one; exact-reference/different-date pairs remain findings. Assert the swap query does not fetch different-day candidates (probe count or classifier spy), and per-step `max_probes` remains honored.
- [x] Run `python -m unittest test_ap_duplicates_rules test_ap_duplicates_scan -v` with `PYTHONPATH=tests`; confirm the new different-date swap assertions fail against current code.
- [x] In `classify`, reject `digit_transposition` unless both invoice days are valid and equal; preserve existing vendor/currency/amount/eligibility checks and suffix behavior. In `_next_pair`, give swap queries an equal-day filter while leaving exact/stem queries unchanged.
- [x] Rerun those modules: all pass. Run `git diff --check`, inspect the scoped diff, and commit the rule, scan, and tests.

## Task 2: Version revised results and prepare a safe upgrade

**Files:** Modify `app/ap_shared/bills/duplicates/contracts.py`; create `supabase/migrations/202610260001_ap_duplicate_rules_v2.sql`; modify `tests/fixtures/ap_shared/duplicate_schema_checks.mjs`, `duplicate_store_double.py`, `duplicate_scale_check.py`, and affected `tests/test_ap_duplicates_{rules,artifacts,projection,repository,operations}.py` fixtures/tests. Update deployment guidance in the spec or verification note.

**Interfaces:** Current `RULE_VERSION` becomes `bill-duplicates-v2`. Artifact `format='bill-duplicates-v1'` and directory `bill-duplicates/v1` stay unchanged. Existing deterministic `duplicate_ensure` scan IDs bind to the new rule version; manifest validation accepts only the runtime's current rule version.

- [x] Add failing tests for current rule v2, v1 manifest rejection, and ensuring a distinct v2 scan when a ready v1 scan exists, with old reviews retained and no implicit decision transfer. Make current-version test fixtures use `RULE_VERSION`; keep explicit v1 upgrade fixtures literal.
- [x] Extend PGlite coverage to create a ready v1 scan with a saved review before applying the new migration. Assert v1 scan/review/event values are unchanged afterward, v2 ensure/publish/review works, v1 ensure still selects v1, unknown/null versions fail, and service-role-only execute permissions remain. Apply the forward migration twice to test safe retry.
- [x] Run the targeted new tests and `node tests/fixtures/ap_shared/duplicate_schema_checks.mjs`; confirm expected failures before adding migration/version support.
- [x] Set `RULE_VERSION` to v2. Add a transactional forward migration expanding the scan rule constraint to v1/v2 and updating only version selection in `ap_duplicate_mutate` (ensure allowlist, inserted version, selected version). Use guarded function-definition replacement like the existing quota migration; allow an already-upgraded definition and reject unexpected definitions. Preserve all session, lease, source, idempotency, publish, review, and permission checks.
- [x] Run all `test_ap_duplicates*.py` modules, all AP frontend Node tests, and the frontend build. Use the established escalated Python runtime and existing dependencies; no dependency installation. Run the existing 223,425/500,000-record scale checks through their test module to catch hard-coded rule versions and bounded-work regressions.
- [x] Record actual verification results and deployment order: migration first, application deployment second, then fresh duplicate scan; prior reviews remain historical and new-version findings need review. Do not apply live SQL during implementation.
- [x] Run `git diff --check`, inspect the whole change, and obtain the required fresh final review using native execution's review gate. Fix actionable findings, rerun relevant checks, and commit. Report local completion separately from deployment; no merge/push without a new user request.

## Plan self-review

The two tasks cover every design requirement. Rule and artifact-format versions are deliberately separate; all five review risks have explicit tests. No frontend layout changes or production data access is needed. SQL behavior must be executed in local PGlite, not merely string-checked.

## Follow-up deployment authorization

After implementation, the user asked to continue the listed verification,
migration, merge/push and refresh steps. They separately confirmed the AP
Supabase project/production branch and explicitly authorized saving a schema
recovery copy before applying this migration after all tests passed. That
follow-up supersedes the implementation-only deployment exclusions above.
