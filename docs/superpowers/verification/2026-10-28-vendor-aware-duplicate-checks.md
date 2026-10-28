# Vendor-aware duplicate checks — release verification

## Scope and identity

Approved design: `../specs/2026-10-28-vendor-aware-duplicate-checks-design.md`.
Implementation plan: `../plans/2026-10-28-vendor-aware-duplicate-checks.md`.
Feature branch: `codex/ap-shared-workspace`; target: `DD-v2`.
Runtime source frozen at `00b75cf` (evidence correction `40462ae`).

The detector adds format-supported reference-entry and wrong-vendor warnings.
It retains existing findings and amount differences. It does not identify a
correct vendor, confirm duplicate payment, or change BILL records. Exact
reference reuse more than 30 days apart is contextualized rather than hidden.

Profiles use the 365 days before the earlier candidate's calendar month: at
least 20 distinct references, up to three supported shapes covering at least
90% of history, and at least three references per shape. New candidates require
equal positive totals, compatible currency, valid dates within three days, and
one format fit and one outlier. Routine different-day same-amount purchases
with sufficient prior recurrence do not create the new reference-entry warning.

## Verification gates

- Three new focused modules independently passed 20 tests during code review.
- Review corrections passed 33 focused scan/contract/artifact/projection tests.
- Full frontend: 425 passed; no failures or skips.
- Production frontend build: passed, with local PDF/OCR/bridge assets prepared.
- Browser visual check: synthetic wrong-vendor list and dedicated detail view,
  recorded profiles/support, both vendors, and return-to-list navigation passed.
  Private local screenshots are retained outside the committed change.
- Full backend: 770 tests in 872.964 seconds, OK with one unconfigured external
  integration skip (769 passed). Both complete scale checks passed:

| Records | End-to-end seconds | Largest step | Peak RSS increase | Refresh keys stable |
| --- | ---: | ---: | ---: | --- |
| 223,425 | 202.578 | 1.234 s | 98,136,064 bytes | Yes |
| 500,000 | 470.797 | 1.329 s | 193,740,800 bytes | Yes |

Both runs preserved the 5,000-record and 10,000-probe step limits. Each produced
the expected two synthetic findings and a 970,752-byte expanded artifact; the
compressed sizes were 116,694 and 116,692 bytes. The 2,000-reference dated
profile case also passed with a 25-probe step budget.

The final read-only real-export recheck covered 223,425 normalized records:
223,388 eligible and 37 excluded. It preserved all 417 v2 classification/member
sets and produced 465 findings: 117 amount differences, 49 exact patterns, 226
export reviews, 25 existing possible duplicates, 34 reference-entry issues and
14 possible wrong-vendor pairs. Finding keys deliberately change with the rule
version; immutable old scans/reviews remain stored.

The final run took 136.891 seconds; its largest candidate step was 0.750 seconds.
The compressed result was 144,588 bytes, expanded 548,864 bytes. All new pairs'
96 source records were checked against their original CSV rows for vendor,
reference, amount and invoice date, with the original file hash unchanged.
There are 71 reused-reference annotations; all 417 older findings remain.

Using the earlier analysis's recent holdout boundary, 2026-04-22, the monthly
profiles yield two new reference-entry issues and three wrong-vendor pairs.
The earlier exploratory fixed-window result had three reference-entry pairs;
monthly historical profiles intentionally change the candidate set. There are
no new Cider Belly warnings in that recent period, but two historical warnings
remain (one cross-vendor counterpart and one same-day format/reference issue).
Original invoices are still needed: these are unlabelled candidate counts,
not measured precision, recall, confirmed duplicates, or guaranteed savings.

## Independent review and correction

A fresh read-only reviewer examined `4a132d4..09f3fe4`. No Critical issues or
actionable Minor issues were reported. Two Important gaps were reproduced and
fixed in one correction pass:

1. Oversized evidence could previously become an immutable ready artifact that
   subsequently failed to load. Generation and cooperative packaging now reject
   invalid/oversized evidence before publication.
2. Internally plausible profile evidence was not bound to its finding pair.
   A shared validator now checks vendor/reference association, equal amount,
   currency compatibility, actual date gap, earlier-month training cutoff, and
   complete pair membership during publication/preparation/projection.

RED/GREEN regressions cover oversized valid-input generation and corrupted
vendor, future training window, reference, amount, currency and member identity.
Both full and cooperative cache loading reject semantically corrupt profiles.
Existing source/session, object hash, quota, lease and review checks remain.

The first full run exposed a separate scale regression: at 500,000 records,
the four added date-based indexes unnecessarily indexed undated nodes and
exceeded the unchanged 512 MiB working limit. The new indexes are partial,
excluding NULL dates that none of the new rules can use. Sixty-four focused
tests passed after that correction; a distinct 500,000-record ingestion used
503,197,696 bytes, below 536,870,912. The complete release suite is rerun rather
than accepting the earlier failed scale result.

One optional external Supabase round-trip test is unconfigured because no
dedicated authorized synthetic project is provided. It is reported as a skip,
not a pass. Local repository and PGlite SQL tests are exercised separately;
the production project is used only for the approved schema migration/audit.

The reviewer declined to judge a historical v1/v2 UI browser, which is outside
the approved scope. Historical database scans and reviews are preserved.

## Database prerequisite

Migration `202610280001_ap_duplicate_vendor_rules_v3.sql` introduces rule v3 and
artifact format/namespace v2 while preserving historical v1/v2 acceptance.
The function change is limited to three guarded substitutions. Fixture tests
exercise retry, mismatched manifests, access restrictions and transactional
rollback on unsupported definitions. No review or source rows are rewritten.

Confirmed project: HWFC Finance Programs Test, main (PRODUCTION),
`uhwpnbntjsopuilouize`. A read-only preflight captured the function, constraint,
owner/ACL and complete scan/review/event row checksums. The local recovery SQL
was verified against the database function hash, preserving its original line
endings. This is schema recovery, not a full database or storage backup; once
v3 scans exist, a rollback must retain v3 compatibility.

Live migration applied successfully on 2026-10-28 after all verification gates.
The postflight matched the exact three-substitution function hash, enabled
v1/v2/v3 compatibility, and preserved complete row counts and checksums for
two scans, ten reviews and twelve review events. Function owner and ACL were
identical: postgres and service_role execution only, with anon/authenticated
execution denied. No source or review records were changed. Recovery SQL and
before/after audit data remain local and uncommitted.

## Execution rulings

Native Windows task bookkeeping replaced unavailable Bash helpers, retaining
per-task bases, RED/GREEN logs, review and completion gates. The risk was an
omitted gate; the explicit ledger and plan checklist provide the audit.

The independent review ran against a frozen implementation while full checks
ran. Its two findings triggered fresh verification of the correction, avoiding
divergence between reviewed and tested code. No findings were deferred.

The preserved worktree remains available with its earlier QA/recovery files.
Only the approved feature delta will be squash-merged; the newer DD-v2 release
notes from the prior deployment will be retained. Private source exports,
derived real-data analysis, recovery SQL and browser captures are not committed.

The resolved squash-merge runtime, migration and test trees match the reviewed
feature tree exactly. Version/path conflicts from the earlier squash history
were resolved with those tested files; prior DD-v2 deployment notes were
preserved. On the merged tree, 102 focused backend/private-storage/SQL tests,
all 425 frontend tests and the production build passed again. The identical
long scale checks were not repeated after integration; their source identity
was verified against the completed 770-test release run.

Merge status: squash-merged locally into DD-v2. Not pushed or deployed. No shared
Streamlit reboot was performed, and the new live app UI is not claimed verified.
