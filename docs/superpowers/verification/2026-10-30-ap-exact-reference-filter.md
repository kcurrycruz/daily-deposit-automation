# AP exact-reference exclusions and digit typos — verification

Status: local implementation, independent review, its substantive fix pass and required local verification are complete on `codex/ap-exact-reference-filter` (base `e33fc38`). Production acceptance and deployment have not been performed or authorized by this plan.

## Implemented behavior

The approved policy excludes a finding only after all relevant source member identities are verified as the same normalized vendor and invoice reference. Dates and amounts may differ within these excluded groups. Source records, original immutable scan artifacts, saved review decisions and review events remain stored. No automatic Not a duplicate decision is created.

New v5 full/v6 scoped scans add one-digit substitutions for equal vendor/original numeric amount/known invoice date with compatible known currencies. Existing wrong-vendor/suffix/swap/profile behavior remains. Legacy v3/v4 scans keep their previous matching semantics; the UI does not describe those as having checked single-digit typos. Original zeros, punctuation and suffixes remain meaningful.

## Verification evidence

- 50 version/manifest/source/operation/SQL checks passed after missing-feature RED tests.
- 31 initial exclusion/projection/operation/scoped checks passed after RED. Added interrupted-write and batched-read regressions also ran RED to GREEN; the subsequent combined focused suite passed 39 tests.
- 51 rule/scanner/vendor/scoped checks passed, including the new same-date rule and preserved legacy behavior.
- The numeric smoke and both final release sizes produced three raw groups, two exact-reference exclusions and one visible typo, with stable keys after a simulated refreshed import/payment update. Final numeric results are below; earlier failed prototypes are documented separately.
- All 457 frontend tests passed. Production frontend asset build passed.
- Final backend discovery found 862 unique test methods. The existing-index tree's normal run executed 859 in 223.619 seconds: 858 passed and one skipped. The skip is the explicitly gated private-bucket/server round trip because no authorized synthetic Supabase project was configured; it remains a deployment blocker. The remaining three release-scale methods run separately, covering both 223,425 and 500,000 rows. The runner's first attempt lacked the repository import path and was replaced after fixing discovery, before interpreting its failures as product defects.
- Legacy v3 scale passed both sizes: 263.032/643.953 seconds, maximum cooperative step 1.562/1.953 seconds, RSS increases 98,148,352/193,802,240 bytes, stable repeat keys. Each produced two raw exact-reference groups, two exclusions and zero visible alerts.
- Working-range scale passed both sizes in 669.941 seconds combined. The 223,425-row last-12-months case retained 22,567 records, preserved source/context parity, and completed build/cold-cache in 41.469/19.766 seconds. The 500,000-row all-history case retained all records, preserved parity, and completed build/cold-cache in 174.578/402.813 seconds. Maximum steps were 5.172/5.218 seconds; 100 warm reads took 0.172/0.203 seconds without downloads.
- The final existing-index approach passed 56 focused rule/scan/scoped/contract/artifact tests. Full 64-character fingerprints round-trip through v6 scoped artifacts; unrelated and punctuation-different references remain distinct. The earlier signature-index prototype additionally passed forced-collision tests before being removed. The full normal suite and new-rule numeric gates passed after the final production changes. Legacy v3 and working-builder release-size gates preceded these new-rule-only optimizations; their unchanged production paths are also covered by the final normal regression suite. Discovery accounts for 861 passing unique backend methods plus one explicitly skipped integration method.

| Final v5 records | Elapsed seconds | Maximum step (seconds) | Peak RSS increase (bytes) | Expanded / compressed result bytes |
| --- | ---: | ---: | ---: | ---: |
| 223,425 | 352.578 | 1.704 (reading) | 97,939,456 | 970,752 / 117,190 |
| 500,000 | 965.266 | 2.172 (reading) | 193,617,920 | 970,752 / 116,961 |

Both sizes retain the original 1,200-second subprocess timeout, 5-second cooperative deadline plus the existing 1-second test jitter allowance, 5,000 records and 10,000 probes per step, 512 MiB expanded/scratch, 32 MiB compressed and 256 MiB RSS-increase limits. The 223,425-row final run was isolated after the larger run finished; the earlier prototype's 34.547-second outlier did not reproduce. Its exact cause was not established, so this is evidence for the final implementation rather than a claim about the retired prototype or all host conditions.

## Independent review and fixes

One independent whole-branch review reported one Important issue, no Critical issues and no Minor issues. The actual legacy rows-v1 source expanded a 100-record exclusion prefetch into 100 remote calls, defeating cooperative preparation. The failing actual-reader test and SDK HTTP-boundary test now pass after a private workspace/import-bound bulk query. Requests remain capped at 100 records, validate completeness and ordering, and revalidate authorization/source before and after access. No new public API or migration is needed for this fix.

The same fix pass addressed an additional release-scale failure: the initial new-rule 223,425-row run took 898.641 seconds, and the 500,000-row run exceeded the unchanged 512 MiB scratch limit during input. A missing-digit signature-index prototype reduced candidate lookup work but added expensive input writes. Full SHA-256 identities/fingerprints now use binary representation only in new-rule scratch storage; durable artifact fingerprints remain full hexadecimal SHA-256. An early additional covering-index experiment did not improve the profile and was rejected. Original release resource caps were not raised.

The next 500,000-row run reached the unchanged 1,200-second timeout, so the same fix pass remained open. An end-to-end 30,000-row synthetic profile identified repeated individual swap queries and vendor/month profile reads. Batching indexed candidates (each branch returns at most its next ordinal) and memoizing at most 128 immutable profiles reduced that profile from 85.093 to 56.828 seconds with identical findings. Direct integer ordinal keys avoid an extra scratch-node lookup. The signature-index 223,425-row run then took 667.719 seconds with stable expected results, but failed a 34.547-second step outlier; its parallel 500,000-row run timed out again. Phase diagnostics showed 437.047 seconds for its first input and 293.782 seconds for repeat input, before candidate processing. This justified removing the signature index rather than increasing limits.

The final approach reuses the existing covering vendor/amount/compact-reference/date index, batching at most 100 swap/substitution reference variants per branch. Compaction is only a candidate lookup: full normalized references and all vendor/amount/date/currency rules are checked before emitting a finding. The SQL-call regression failed at 9,345 calls for 1,000 unique synthetic bills, then passed below 4,500. The self-added absolute VM diagnostic is replaced by a 1,000-to-2,000 input linear-growth check (less than 2.3x), because this approach deliberately trades more index reads for fewer writes; the original release time/storage/RSS/step/probe/row caps remain unchanged. Pair-set equivalence covers exact reference/amount differences, suffixes, swaps, typos, unknown/different dates, punctuation and currency conflicts. Scoped history takes precedence over memoized profiles; eviction remains bounded. The final 30,000-row instrumented profile took 65.484 seconds and produced the same three raw/two excluded/one visible findings and stable repeat keys; this small profile alone does not establish the large-data tradeoff.

## Saved representative export (read-only)

The saved local normalized index SHA-256 is `3e94e39b975cd68b6ff6f7f47944e5495dcadf030668d5dd82fbb17c344964df`. It contained 223,425 records; source hash before/after matched. Output is aggregate only, with no raw company rows or generated financial artifacts committed.

The first v5 audit produced 799 raw findings, excluded 392 exact-reference groups, and left 407 visible suggestions: 359 possible duplicates, 14 possible wrong-vendor entries and 34 reference-entry issues. Of those, 334 were new single-digit suggestions, not confirmed duplicate bills or payments. The known Albert exact-reference group was excluded. These are results on a saved snapshot, not a live BILL audit or a claim that every suggestion is an error.

The final existing-index audit reproduced those counts and the unchanged hash. It took 61.031 seconds input, 86.391 seconds scan and 3.562 seconds exclusion preparation, 150.984 seconds total, with 16 source-member page calls rather than the initial 799. Maximum scan step was 0.890 seconds; peak RSS increase was 80,502,784 bytes. The prior signature-index audit took 240.375 seconds and used 114,352,128 additional RSS bytes. These local concurrent-test timings omit remote network latency and are not Streamlit performance promises.

## Unperformed deployment checks

No database migration/activation, merge, push, shared-app reboot, live financial decision save, or live browser/PDF/history check occurred for this feature. UI verification so far is automated actual-component HTML/controller tests. Local PGlite checks cover serialized lifecycle/ACL definitions; real independent-connection Supabase behavior, deployed ACL enforcement and authorized synthetic storage round trips remain deployment gates.

See [rollout and recovery](../../ap-duplicate-near-reference-rollout.md). All three 20261030 migrations must run in order in an authorized synthetic project before an owner-authorized production rollout. Compatible v1-v6 readers must remain while historical evidence exists.

## Rulings made

1. Use PowerShell/Python bookkeeping in place of Bash helpers, preserving per-task briefs, bases, RED/GREEN logs and commits. Cost if wrong: an omitted gate; explicit ledger and release records mitigate it.
2. Consolidate old/new release-scale runs with Task 4 instead of repeating them in Task 3. Cost: later discovery of scale failures; both sizes must pass before completion.
3. Enrich normalized synthetic generic-template rows with a known invoice date because that importer intentionally ignores invoiceDate. Cost: this is a normalized scan benchmark, not native-import end-to-end proof; the saved native export was checked separately read-only.
4. Run the three release-scale methods in separate fresh processes beside the normal discovered suite; run the two numeric sizes independently while retaining their default unittest coverage. Cost: contention-sensitive timings; all original per-process caps remain unchanged and discovery accounts for every method.
5. Keep deployed concurrency/ACL and live browser/PDF/history acceptance as unperformed rollout gates. Cost: local serialized tests cannot establish live behavior; owner-authorized deployment checks remain necessary.
6. Keep private representative inputs out of the independent review; the author performs the read-only aggregate backtest and verifies the source hash. Cost: company-specific counts are author-verified, not independently audited.
7. Prototype 128-bit indexed digit-mask keys followed by full-value classification, with full binary SHA-256 scratch identities/fingerprints only for new rules. Cost: an additional index and representation; collision/provenance tests covered correctness, but scale tests later rejected that extra index. Binary full fingerprints remain in the final implementation.
8. Batch new-rule indexed candidates, cache at most 128 immutable vendor/month profiles with scoped contexts taking precedence, use direct integer ordinal scratch keys and initially share hash prefixes. Cost: additional internal query/cache machinery; mixed-rule equivalence, bounded-cache/context, SQL-work, deadline/probe, provenance and full-size gates cover it. Hash signatures were subsequently removed; legacy v3/v4 behavior remains unchanged.
9. Reject the signature index after its scale failures; reuse the existing covering index with bounded reference variants and strict full-reference classification. Replace the self-added absolute VM diagnostic with a linear-growth check while retaining the SQL-call regression and all original release caps. Cost: broader lookup candidates and more per-query CPU, which require punctuation-sensitive equivalence and real full-size gate verification.

## Deferred minors

None.
