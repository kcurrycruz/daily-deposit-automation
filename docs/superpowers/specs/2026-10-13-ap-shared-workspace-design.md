# AP Statements Shared Storage and Review History Design

**Date:** October 13, 2026

**Status:** Approved for implementation planning on October 13, 2026

## Purpose and agreed requirements

Give the HWFC finance team one shared AP workspace. Imported BILL records and uploaded statement PDFs must be available on later visits and other computers without uploading them again. Previous work must show what was reviewed, the stated reviewer initials, and the completion date.

The user selected Supabase for shared storage and a shared AP password instead of individual accounts. Reviewer initials are required when completing a statement; notes are optional. The portal remains publicly accessible, but its saved AP records must not be accessible without the password. The password value is never included in source code, this document, tests, logs, or Git history.

The user also approved searching BILL by invoice number first, followed by an amount search within the same vendor when the number is absent. Amount-only results require review, and repeated amounts produce multiple candidates rather than a chosen invoice.

## Selected approach

Use Supabase Postgres for BILL imports, statement records, vendor mappings, and review history. Use a private Supabase Storage bucket for original PDFs and imported CSV files. Streamlit Python is the only application layer allowed to use the Supabase secret key.

Browser-only saving cannot meet the shared-history requirement. Separate database and object-storage vendors would work but introduce two services to administer. The selected Supabase approach keeps both services in one project while retaining separate permissions for records and files.

This design supersedes the October 9 browser-only integration boundary for AP storage: authorized financial payloads will now pass through the Streamlit component bridge to Python. PDF parsing and OCR still run in the browser. Daily Deposits, Credit Cards, BILL API access, QuickBooks verification, and accounting writes are unchanged and outside this work.

## Access and secrets

Show a password prompt when AP Statements opens. Validate the password on the server before declaring the financial component, reading records, serving PDFs, or processing any storage action. The browser must not receive the expected password or Supabase secret key. Missing credentials or storage configuration fail closed with working navigation back to programs.

Read the configured password and backend credentials from Streamlit Secrets. Do not create a committed secrets file or store credentials in browser storage. Compare credentials without logging them, clear the submitted password after validation, and enforce server-side limits on failed attempts across sessions with a cooldown. A separate access-attempt store may be used before unlocking; it contains no financial records. Detailed error messages must not reveal whether storage contains a particular vendor or statement.

Authorization is session-scoped, expires after eight hours, and has a visible Lock AP action that discards displayed records and ends access. Revalidate authorization before every operation, including requests replayed through component messages. A password change invalidates existing authorization on the next server operation. Clear unlocked component state when access ends; previously viewed or downloaded files cannot be revoked from a user's computer.

All authorized users share the same permissions in this phase. Initials are self-reported labels, not verified identities. Anyone given the password can access the workspace. No individual accounts, verified user audit, or MFA are promised. Changing the password before production use is recommended because its initial value was supplied in chat.

Enable row-level security on AP tables and deny direct access to browser-facing anonymous and authenticated roles. Do not expose a financial-data API using a publishable key. Supabase secret keys bypass row-level security, so every Python operation must perform its own access and input checks. PDFs and CSV files have no permanent public URLs; previews receive short-lived signed links only after authorization. Signed links expire after at most five minutes and must not appear in logs or history records.

## Stored records

Use one server-configured HWFC workspace; a client cannot select an arbitrary workspace identifier.

| Record | Contents and purpose |
| --- | --- |
| BILL imports | Immutable import ID, filename, file hash, import timestamp, optional snapshot date, source format, row counts, warnings, and original CSV object reference. |
| BILL records | Normalized records keyed to one import, preserving invoice numbers as text, monetary values as integer cents, vendor name, source rows, and native-export comparison limitations. |
| Statements | Stable ID, PDF hash and object reference, filename, vendor, statement date, extraction fields, current revision, and workflow status. |
| Statement revisions | Immutable corrections, confirmed rows, notes, row review decisions, comparison import ID, mapping snapshot, matching rule version, and result snapshot. |
| Completion history | Statement revision, reviewer initials, server timestamp, completion or reopening event, and optional note. |
| Vendor mappings | Statement vendor to BILL vendor mapping, revision, and update timestamp. |

The schema uses database transactions, uniqueness constraints, and version checks for consistent changes. PDF and CSV object keys are generated by the server and cannot be supplied as arbitrary paths by the browser.

Original files and prior completed work are retained until an authorized administrator follows a separately documented deletion procedure. Ordinary users can archive a statement, not permanently delete shared history. The existing Clear workspace action becomes a local-view reset and must never wipe shared records.

## Upload and import workflow

After unlocking AP, load the latest successful BILL import metadata and active statement list automatically. Load full invoice datasets and PDFs as needed, with pagination that does not stop at a service default row limit. Clearly show the active import filename, record count, snapshot date when supplied, and import date. A stored CSV is a snapshot, not a live BILL connection.

Import a new Bills CSV through the existing browser importer, preserving line-item consolidation and warnings. Save its original file and validated normalized records as a new immutable import. Only switch the active import after every required write succeeds. A malformed or partially saved import leaves the previous import active. An identical file hash reuses the existing import rather than duplicating it. This phase treats each import as a complete comparison snapshot, not an incremental merge with older exports.

Support multiple statement PDFs in one upload. After a successful private file upload, save an unconfirmed draft and its extraction. If OCR fails, retain the PDF as a draft with the failure visible so the user can reopen and correct it. Confirming extraction remains a separate action. Never classify a failed extraction as a missing invoice.

An identical PDF hash opens the existing statement instead of creating duplicate completed work. Different PDFs remain distinct even if their names match. Saving an original is not a reason to automatically trust its extracted rows.

Saving corrections, notes, review decisions, and mappings writes shared state and shows Saving, Saved, or Not saved. An error retains the local edit and offers retry. Do not show a saved or completed state before the server acknowledges it. Existing browser sessions are offered as an explicit migration after unlocking; they are not silently uploaded. Legacy statement records without original files remain visibly incomplete until their PDFs are attached.

## Matching behavior

Keep extraction confirmation, duplicate-row checks, source warnings, and currency limitations ahead of matching conclusions.

1. Search for the invoice reference and transaction kind first, retaining its leading zeros and meaningful suffixes. Prefer candidates from the mapped vendor. An exact reference found only under another or unresolved vendor is shown for vendor verification, not automatically accepted as a same-vendor match. Repeated references across vendors are not silently resolved.
2. For a unique same-vendor reference, retain current amount, credit, payment timing, and comparison-scope checks. An amount disagreement on an exact reference remains an amount exception; do not hide it by switching to another invoice with the expected amount.
3. Only when the reference is absent from BILL, search for the same original invoice amount and transaction kind within the mapped vendor. Compare individual invoice amounts, not the overall statement total or a running balance. If the vendor cannot be established, request a mapping rather than searching amounts across vendors.
4. Show a unique amount candidate as Possible match with both references and the reason for the suggestion. Multiple same-vendor equal amounts stay ambiguous and all candidates remain visible. No automatic reference correction, combining invoices, or reuse of one candidate as an accepted match for several statement rows is allowed.

Native BILL exports continue to establish invoice presence and original numeric amount only. They do not verify outstanding balances, payment settlement, currency when absent, or QuickBooks sync. A review decision records a user's conclusion without changing the original matching evidence.

## Completion and previous work

Add Mark reviewed with a required initials field, normalized to uppercase and limited to one to ten letters. Notes remain optional. Completion requires confirmed extraction and an explicit review decision for unresolved comparisons; it does not require every invoice to be a successful match. A statement can be reviewed with follow-up items and must display that distinction rather than calling it fully reconciled.

Save completion as a new immutable revision and completion event. Show Previous Statements with filters for vendor, statement date, initials, status, and completion date. Reopening retrieves the original PDF, corrections, notes, comparison evidence, and completion history. A completed revision retains its original BILL import and mapping snapshot even after new imports or rule changes.

Reopening for further work creates a new draft revision. Comparing it with a newer import is an explicit action. Prior completed results remain available. Two users editing the same revision cannot silently overwrite one another: stale saves produce a conflict and offer reload while preserving the unsaved local edit.

Use server-generated UTC timestamps for history and display them in America/New_York. User-supplied statement dates remain calendar dates, not timestamps.

## Component and server responsibilities

Extend the existing bridge with a narrow, versioned request and response envelope. Actions are allowlisted, assigned unique request IDs, validated for size and schema, and acknowledged once. Reruns and retries must not create duplicate imports, statements, revisions, or completion events. Arbitrary client paths, SQL, URLs, and credentials are rejected.

Python owns authorization, Supabase access, server timestamps, file validation, revision transactions, and idempotent request handling. Browser modules retain extraction, input editing, and presentation. Shared state becomes authoritative after unlocking; browser storage is not used as an invisible fallback when Supabase is unavailable.

Validate uploaded PDF signatures, CSV content, allowed types, bounded payload sizes, and maximum batch sizes. Support files through bounded chunks if needed rather than transferring an unbounded base64 payload in one component message. Handle file and database writes in stages so failed operations do not create usable partial records. Provide an administrative cleanup procedure for orphaned staged files; never delete referenced originals automatically.

Escape untrusted filenames, vendor names, source text, and notes. Retain spreadsheet formula protection in report exports. Logs contain operation IDs and sanitized errors, not passwords, API keys, invoice payloads, original file bytes, or signed links.

## Validation and rollout

Use synthetic fixtures for automated tests. Verify password rejection, cooldowns, expiry, locking, password rotation, missing configuration, and forged component actions. Confirm unauthenticated browser and direct Supabase requests cannot read financial records or files, and that frontend assets contain no secrets.

Test record pagination beyond the Supabase default limit, duplicate uploads and request retries, complete imports, partial failure recovery, concurrent edits, optional notes, required initials, and preserved completion history. Test invoice-first matching, vendor conflicts, missing mappings, equal-amount ambiguity, exact-reference amount discrepancies, and native-export limitations.

In two independent authorized browser sessions, verify a saved import and statement become available without re-upload, reopen their original PDFs, and confirm a conflict instead of an overwrite during concurrent editing. Test returning to programs and Daily Deposits without changing existing deposit state. Run the complete Python and Node regression suites.

Prepare schema migrations and setup instructions without provisioning an external project or uploading financial files automatically. Activation requires a user-controlled Supabase project, the private bucket and schema, and credentials entered directly in Streamlit Secrets. Test with synthetic data before the user explicitly migrates existing financial data. Establish and test database and file backup and recovery procedures before relying on the archive; retention in a live bucket is not a backup.

Application implementation, external setup, migration, merging, and pushing are separate later steps. This design was approved for implementation planning; approval does not mean shared storage is deployed.

## Technical references

- [Streamlit secret handling](https://docs.streamlit.io/deploy/concepts/secrets)
- [Supabase server and browser key separation](https://supabase.com/docs/guides/getting-started/api-keys)
- [Supabase row level security](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [Supabase private storage access](https://supabase.com/docs/guides/storage/buckets/fundamentals)
