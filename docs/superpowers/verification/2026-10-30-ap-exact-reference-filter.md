# AP exact-reference exclusions and digit typos — verification

Status: release checks and the independent final review are in progress. This is not production acceptance or authorization to deploy.

## Implemented behavior

The approved policy excludes a finding only after all relevant source member identities are verified as the same normalized vendor and invoice reference. Dates and amounts may differ within these excluded groups. Source records, original immutable scan artifacts, saved review decisions and review events remain stored. No automatic Not a duplicate decision is created.

New v5 full/v6 scoped scans add one-digit substitutions for equal vendor/original numeric amount/known invoice date with compatible known currencies. Existing wrong-vendor/suffix/swap/profile behavior remains. Legacy v3/v4 scans keep their previous matching semantics; the UI does not describe those as having checked single-digit typos. Original zeros, punctuation and suffixes remain meaningful.

## Evidence so far

- 50 version/manifest/source/operation/SQL checks passed after missing-feature RED tests.
- 31 initial exclusion/projection/operation/scoped checks passed after RED. Added interrupted-write and batched-read regressions also ran RED to GREEN; the subsequent combined focused suite passed 39 tests.
- 51 rule/scanner/vendor/scoped checks passed, including the new same-date rule and preserved legacy behavior.
- The 12,000-row numeric synthetic smoke produced three raw groups, two exact-reference exclusions and one visible typo; repeat finding keys were stable. Full 223,425/500,000 scale gates remain pending.
- All 457 frontend tests passed. Production frontend asset build passed.
- Backend normal discovery accounts for all discovered tests minus the three independently executed release-scale methods; final results remain pending. The runner's first attempt lacked the repository import path and was replaced after fixing discovery, before interpreting its failures as product defects.

## Saved representative export (read-only)

The saved local normalized index SHA-256 is `3e94e39b975cd68b6ff6f7f47944e5495dcadf030668d5dd82fbb17c344964df`. It contained 223,425 records; source hash before/after matched. Output is aggregate only, with no raw company rows or generated financial artifacts committed.

The first v5 audit produced 799 raw findings, excluded 392 exact-reference groups, and left 407 visible suggestions: 359 possible duplicates, 14 possible wrong-vendor entries and 34 reference-entry issues. Of those, 334 were new single-digit suggestions, not confirmed duplicate bills or payments. The known Albert exact-reference group was excluded. These are results on a saved snapshot, not a live BILL audit or a claim that every suggestion is an error.

The first audit took 56.734 s input, 85.047 s scan and 1.734 s exclusion computation locally, with 799 source-member page calls. The subsequent batching regression reduces 100 small groups to two source calls; a final representative rerun after batching is pending. Local times omit remote network latency and are not Streamlit performance promises.

## Unperformed deployment checks

No database migration/activation, merge, push, shared-app reboot, live financial decision save, or live browser/PDF/history check occurred for this feature. UI verification so far is automated actual-component HTML/controller tests. Local PGlite checks cover serialized lifecycle/ACL definitions; real independent-connection Supabase behavior, deployed ACL enforcement and authorized synthetic storage round trips remain deployment gates.

See [rollout and recovery](../../ap-duplicate-near-reference-rollout.md). All three 20261030 migrations must run in order in an authorized synthetic project before an owner-authorized production rollout. Compatible v1-v6 readers must remain while historical evidence exists.

## Rulings made

Final exhaustive rulings and review findings will be recorded after the independent review and release gates complete.

## Deferred minors

Pending independent review.
