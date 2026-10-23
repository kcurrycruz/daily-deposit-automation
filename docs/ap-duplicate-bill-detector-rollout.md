# Duplicate bill checks: rollout and recovery

This feature reads the current saved BILL export and flags patterns for manual review. It never deletes, pays, creates, or changes a bill in BILL. Statement reconciliation and historical statement evidence are unchanged.

## Enablement order

1. Obtain deployment and database-change approval. No live migration was applied during development.
2. Confirm the existing AP shared-workspace and BILL snapshot migrations are installed, including the functions used by the snapshot import migration. Back up the database using the team's existing process.
3. Apply `supabase/migrations/202610220001_ap_duplicate_bills.sql` after the existing migrations. It adds private scan/review tables and rewrites only the existing quota reservation branch to share its storage accounting. It fails rather than guessing if that branch has an unexpected structure.
4. Keep the configured storage bucket private. Preserve existing PDF, CSV and octet-stream MIME types and permit `application/gzip` for compressed BILL snapshots and duplicate results. The bucket must accept 32 MiB objects; a 50 MB bucket limit within the existing global allowance is sufficient. Do not make the bucket public or change its access policies.
5. Deploy the reviewed code and rebuilt component assets. Bootstrap advertises `duplicateBills: 1` only when `duplicate_schema_version` is 1. A missing migration disables the new tab without disabling statement checks.
6. Open an already saved import. The app starts checking it automatically; users do not need to reupload a statement or BILL export to start the first scan.

## Rules and limits

- One active source, not a union of weekly exports. New exports replace the source used by this detector.
- Same normalized vendor and original integer-cent bill totals. Equal amount alone is never a duplicate finding.
- Exact references, a numeric reference plus an optional trailing letter, or an adjacent digit swap. Similar-reference checks need invoice dates within 30 days. Payment dates are not invoice dates.
- Exact references with different original totals produce an amount-difference finding, not an automatic correction.
- Negative amounts, zero amounts and credit-kind records are excluded. Missing currency is displayed as missing. Known unequal currencies are not treated as matching amounts.
- Identical economic identities or ambiguous export rows are labeled **Export needs review**. Import row IDs and differing payment fields do not prove independent bills exist.
- 500,000 normalized records and 750,000 CSV source rows, with explicit failure rather than partial success. Results are bounded to 100,000 findings, 512 MiB expanded and 32 MiB compressed.
- Requests ingest at most 5,000 records or perform at most 10,000 candidate probes. Cooperative work has a five-second budget. The browser yields between requests so foreground work can enter the serialized bridge queue.
- This is a cooperative work budget, not a remote-network latency guarantee. Network latency or operating-system scheduling can extend wall-clock time; a slow publication does not grant the same request a second work budget.
- Source decompression, result verification and review projection preparation resume across requests. Warm private caches reuse hash-verified immutable files; they do not repeat a whole-database check for each page. Complete source ordinal/record validation still happens before a scan can finish. SQLite progress handlers bound potentially long reads.
- At most one scan per workspace and two scan handles per server process. Temporary handles expire after one hour. Ready result artifacts are immutable.

## Review behavior

The default list is Unreviewed. Reviewed and All filters and literal vendor/reference search operate on a complete shared review projection. Counts remain unavailable until that projection is complete. A review-revision change invalidates old cursors and requires a refresh.

Whole-row click or Enter/Space opens a dedicated side-by-side source-bill detail. Back restores the list position. Unknown currency and source warnings remain visible. Reported payment data is not verified settlement evidence.

Initials are required and self-reported. Notes are optional. Acknowledged reviews have server timestamps and immutable events. A retry retains its operation identity. Concurrent changes retain the user's draft and show the current saved review before another save. Navigation and progress updates preserve unsaved notes; access lock/pagehide clears financial evidence and drafts.

An unchanged identifying fingerprint carries a prior decision into a new export. Payment-status or paid-amount changes alone do not reset it. Changes to vendor, reference, original amount, invoice date, currency, relevant identity warnings, member multiplicity or detector rule version require a new review. Legitimate Adventure in Food suffix bills can be marked Not a duplicate without changing statement matching.

## Storage and recovery

Duplicate artifacts use only the private content-addressed namespace:

`<workspace>/bill-duplicates/v1/<importId>/bill-duplicates-v1/<hash>.sqlite.gz`

Before result writes, reserve up to 64 MiB under the configured BILL bucket budget. Import jobs and duplicate scans use the same advisory lock and reservation accounting. A storage-limit or scan failure does not undo a successful BILL activation.

- **Connection failure:** Retry the same operation. The immutable result path is reused; a lost publication acknowledgement does not require reuploading the CSV.
- **Server restart/temporary-state loss:** Choose Restart from saved BILL data. A new generation replays the source from the beginning. Process-local SQLite cursors are not durable checkpoints.
- **Another access session is checking:** It may be polled, but an unexpired lease cannot be stolen. After expiry, a newly authorized session can explicitly restart it.
- **New weekly source arrives:** Old in-progress work cannot publish against the new import/version. New checks use the saved current source. Ready older evidence remains immutable.
- **Access expires during a read:** No financial result is returned. Unlock AP again; do not restore private evidence from browser storage.
- **Result verification fails:** Display an unavailable/error state, not zero duplicates. Hashes, sizes, source pin, allowed SQLite schema, counts and member locators are verified independently.

No automatic cleanup deletes original CSVs, PDFs, historical snapshots or review events. Temporary local directories belong only to the creating cache/scan handle. Ready private objects are retained under the team's normal retention policy.

Scratch scan/copy SQLite databases use memory journals and no synchronous durability waits. They are not durable checkpoints: losing a process requires an explicit restart, and only a fully packed, hash-verified private artifact can become ready. Original exports and durable SQL reviews do not use this scratch setting.

## Acceptance before production enablement

Run the full Python suite, all `tests/ap_statements*.test.mjs`, the component build, and `git diff --check`. The release scale test runs both specified counts in fresh processes, including an equal-amount unrelated-reference bucket, a 10,000-member ambiguous group, an exact-reference amount difference, and a repeated scan with payment-only changes.

Verify two authorized sessions: first owns a running scan, second polls but cannot steal its lease; simultaneous review saves with the same expected version cannot overwrite one another. Verify page refresh after a colleague reviews, recovery after losing the server process, quota contention with an import, source replacement, and a stored prior review on a new weekly source.

Browser QA uses synthetic values only and includes pending scans, suffix suggestions, ambiguous identities, amount differences, acknowledged reviews, failed-save retries, source replacement and narrow/wide layouts. Read-only local CSV backtests do not upload data or claim confirmed duplicates.

## Disable without deleting evidence

If rollback is required, deploy the previous UI or set the capability marker to a non-enabled value under approved database administration. Leave stored evidence and review history intact. Do not drop tables or reverse private bucket protections. Existing statement workflows do not depend on duplicate scan readiness.

## Release measurements

The read-only local export backtest covered 155,585,995 source bytes, 284,365 CSV rows and 223,425 normalized records. The detector included 223,388 positive invoice records and excluded 37 credit/zero/negative records. It produced 1,479 review groups: 49 exact-reference/amount patterns, 1,085 reference-similarity suggestions, 117 same-reference amount differences and 228 export-identity ambiguity groups. Repeating with payment-only changes retained the same finding keys. None is a confirmed duplicate or duplicate payment.

Representative review patterns included equal amounts with adjacent digits transposed, exact references reused on different invoice dates, and indistinguishable repeated export identities. These can be legitimate separate bills or export repetition. Missing currency remains unknown. Record-level examples are deliberately absent from this committed document.

That pre-fix backtest used the earlier scan-only timing harness: 36,823,040 bytes peak RSS growth, 1,396,736 expanded result bytes and 426,400 compressed bytes. It took 1,307.641 seconds under concurrent local disk load and exposed a 49.563-second work step. Those timings were a failed cooperative-budget baseline, not release acceptance. The corrected release harness measures source preparation, actual registry steps, result verification and complete review projection, in fresh processes without competing scale runs. The final results below passed on October 23, 2026; the step test allows one second of scheduler/I/O jitter around the five-second cooperative deadline. Its 1,200-second per-fixture timeout is more than 2.5 times the observed maximum fixture time.

| Synthetic normalized records | Total seconds, including index preparation and two scans | Peak RSS growth (bytes) | Longest measured work step (seconds) | Expanded result (bytes) | Gzip result (bytes) |
| --- | --- | --- | --- | --- | --- |
| 223,425 | 183.265 | 98,082,816 | 1.016 | 970,752 | 116,620 |
| 500,000 | 468.781 | 193,757,184 | 1.500 | 970,752 | 116,621 |

The synthetic source deliberately has only two planted groups: one amount difference and one 10,000-member export-ambiguity group. Every unrelated same-amount reference is still scanned. Both scans must retain the same finding keys; these counts are fixture expectations, not counts from the user's export.

Final verification: 722 Python tests ran in 803.552 seconds, with no failures and one opt-in integration skip; all 348 frontend tests passed; the component build and patch whitespace check succeeded. The skipped `test_private_bucket_and_server_round_trip` has no authorized synthetic Supabase project configured. It remains a deployment gate, not a passed live-integration check. Local PGlite schema, private-role, concurrency, quota and restoration checks did run and pass. No live migration, real upload, merge, push or production enablement occurred.
