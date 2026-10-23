# AP statement re-review

## Approved intent

The user approved a direct Re-review action for previous statements, with a choice to compare against the latest saved BILL export or update decisions after checking BILL manually. Manual checks must be labeled "Checked manually in BILL", not presented as automatic invoice matches. Existing saved reviews remain unchanged.

## Approach

Extend the existing draft/revision workflow. Do not edit immutable completed revisions, duplicate the statement/PDF, or build a parallel review store. A new editable revision is the one approach consistent with the existing audit model. Reusing today's reopen unchanged would discard decisions and immediately switch sources, so it cannot implement manual re-review safely.

The existing reopen RPC will accept an optional review_mode, guarded by a new schema capability. An additive migration will provide an atomic, private, idempotent re-review operation and route mode-aware reopen calls to it. Legacy reopen calls remain compatible. No live migration is authorized by this implementation request.

## Required behavior

- Add Re-review beside View revision, including vendor-filtered previous statements. View revision remains read-only.
- Offer Recheck with latest BILL data and Review manually. State that the latest revision of the statement will be reopened; selecting an older history event must not overwrite later work.
- Recheck uses current BILL data, preserves statement/PDF corrections and all notes, and clears superseded review decisions and confirmation metadata before reviewing again.
- Manual re-review retains the prior comparison results, import identity, mapping snapshot, rule version, notes and decisions. A weekly upload, page refresh, opening the draft or completion must not silently recompare this mode.
- An already editable draft is opened without overwriting local or colleague edits. A concurrent version change fails closed and invites loading the current draft.
- A manual check is explicit per invoice/account item: checkbox, required self-reported initials of one to ten letters, existing review decision, optional note. The server stamps the saved decision time.
- Bind manual-check metadata to the exact statement vendor, reference, original integer-cent amount and transaction kind. Stale metadata cannot give a changed item a manual-check label.
- "Checked manually in BILL" is a review-method label, never proof of imported invoice presence, payment settlement, credit application or QuickBooks sync. Keep original comparison results/candidates visible and unchanged. Automatic Invoices found counts and filters are not inflated by a manual assertion.
- Manual mode permits decisions and notes, not silent changes to the extracted financial rows behind frozen evidence. Offer an explicit switch to latest-data review before changing those rows.
- Completing a re-review uses the existing initials/timestamp/history flow and creates a new completion entry. The prior completion remains available.
- Preserve retries, request identity, CAS/version checks, private access boundaries, dirty drafts and access-expiry clearing.
- Export the review method, manual initials and saved time alongside the original comparison result.

## Implementation calls

These are builder choices supporting the approved intent:

- Persist doc.reviewMode as manual or latest. Absence means the existing latest-data behavior.
- Store a manualCheck object in the existing resolution JSON, with vendor, reference, amount, kind and initials. Reuse the server-owned resolution at timestamp.
- Advertise statementRereview: 1 only after the additive migration's capability marker exists. Missing setup disables the new controls without breaking existing statement/history workflows.
- Use the latest authoritative statement head when reopening; never restore an arbitrarily old history revision over newer evidence.

## Non-goals

No BILL/QuickBooks writes, automatic settlement claims, changes to duplicate detection or credit matching, deletion of history, real-data uploads, deployment, merge, push, live database updates or paid services. Previously implemented credit notices and linked Ace credit display must remain intact.

## Acceptance

Synthetic tests cover immutable history, retained notes, source pinning across reload/import changes, manual-marker validation and invalidation, concurrent reopens, retry acknowledgement loss, dirty drafts, failed comparisons, CSV evidence and capability fallback. Run all frontend tests, backend tests, local SQL checks, the component build and whitespace checks before handoff. Live Supabase validation remains a separately authorized deployment gate.
