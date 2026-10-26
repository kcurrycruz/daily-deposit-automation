# Recurring-purchase duplicate rules: verification and deployment

## Behavior

Rule version `bill-duplicates-v2` requires the same valid invoice date for
adjacent-digit-swap suggestions. Same vendor, equal original amounts and
existing currency safeguards still apply. Different-day deliveries are not
suggested by this rule. Exact normalized references still compare across
dates; trailing-letter variants still use the existing 30-day window.

Artifact format and storage directory remain `bill-duplicates-v1` and
`bill-duplicates/v1`; the rule-version segment distinguishes new results.
Old scans and reviews remain stored unchanged. New-version findings need
fresh review; decisions are not silently carried across different rules.

## Verification record

- Baseline classifier/scan tests: 23 passed.
- New classifier/scan regressions: observed different-day failures, then 29 passed.
- New manifest/scan-selection/SQL-upgrade regressions: three expected failures,
  then the 34-test targeted run passed.
- Private storage regression: v2 publication initially rejected, then both
  supported versions round-tripped and invalid/foreign paths remained rejected.
- All detector/private-repository tests excluding the long scale module: 82 passed.
- Local PGlite exercised a populated v1 upgrade, migration retry, v2
  publication/review, old history retention, invalid versions, restricted
  execution permissions, and rollback on an unexpected function definition.
- AP frontend tests: 421 passed. Production build: passed.
- Publication preparation anonymized the example vendor/reference/amount
  fixtures; all 30 classifier/scan tests passed again. Runtime and migration
  code remain identical to the independently reviewed/full-suite-tested tree.
- Full backend discovery completed with exit code 0: 744 tests in 871.371s,
  no failures, one optional live integration skip (no authorized synthetic
  Supabase project configured). Prior interrupted runs were not counted as
  completed suite results.
- The full run included both 223,425- and 500,000-record checks. Repeat keys
  stayed stable; maximum steps were 1.297s and 2.562s respectively, below the
  6s test ceiling. The larger run used at most 5,000 records/9,998 probes per
  step and approximately 185 MiB additional peak RSS, within existing bounds.
- Fresh independent whole-change review (`100970a..6f7a115`): no critical,
  important or minor issues, and no declined judgments. The reviewer also
  reran PGlite SQL checks and the diff check successfully. Its pending full-suite
  condition is now satisfied. No product-code fix pass was needed.

## Deployment order

1. Review a database backup and confirm the intended AP Supabase project.
   Test the upgrade on a non-production copy first.
2. Apply `supabase/migrations/202610260001_ap_duplicate_rules_v2.sql` before
   deploying the v2 application. It requires the existing shared-workspace,
   BILL snapshot and duplicate-detector migrations. It is independent of the
   optional statement re-review migration.
3. The migration permits v1 and v2 scans together, preserving old application
   compatibility and immutable history. A successful retry is safe; an
   unexpected deployed function definition causes transaction rollback.
4. Deploy the application, reload AP, and open Duplicate bills. The current
   saved export receives a new v2 scan automatically; no BILL reupload or
   deletion of old scan rows is needed.
5. Verify different-day recurring purchases disappear from the new results,
   same-day suspicious swaps remain, and exact-reference checks still work.

## Authorized deployment record

The user subsequently asked to continue the listed deployment steps, selected
connected-browser execution, and confirmed the AP production project. After
all tests passed, migration `202610260001` ran successfully in that project.

Before applying it, a read-only query captured the exact existing function and
constraint as local recovery SQL. The recovered function's checksum matched
the database. This is a schema recovery copy, not a full database/storage backup;
it is kept locally with the preflight/postflight audit, not committed to Git.
Its v1-only constraint restoration is intended before v2 scans are created;
after deployment, rollback planning must retain compatibility with v2 history.

The postflight verified the exact three-expression function change, v1/v2
constraint support, unchanged complete scan/review/event row checksums and
counts, and identical function access permissions. No BILL records changed.
The squash-merged DD-v2 tree was checked against the reviewed runtime/migration
tree (identical) and final source tests (identical except anonymized fixtures).
All 82 detector/private-repository tests, all 421 frontend tests and the
production build passed again on that merged tree. The long scale checks were
not repeated after integration because their implementation and dependencies
were unchanged; the complete 744-test run above covers that runtime.

After publishing DD-v2, reload the live application to trigger its new scan.

## Execution decisions

- Native PowerShell bookkeeping replaced unavailable Bash helpers; the same
  ledger, tests and review gates were retained.
- The private-storage allowlist also needed rule-v2 compatibility, otherwise
  the new results could not publish. Workspace and version restrictions remain.
- Read-only final review ran alongside full verification on frozen code;
  completion waited for both, so neither was treated as a substitute.
- Publication uses synthetic regression examples and a squash merge, keeping
  intermediate supplied examples out of pushed history while preserving the
  original local branch and QA artifacts.
- Integration used exact runtime/migration identity plus fresh targeted,
  frontend and build checks instead of repeating identical long scale work.
  An unrelated path-specific issue outside those checks is the residual risk.
