# AP Statements Integration in the Streamlit Portal

**Date:** October 9, 2026
**Status:** Proposed design for review

## Purpose

Make the existing Statement Desk prototype available through the AP Statements card in the Finance Operations portal. Staff should be able to upload batches of vendor statements, check extraction, review exceptions, and export a report without leaving Streamlit or signing in to the separate ChatGPT Site.

The user approved embedding the existing browser application instead of rewriting its PDF processing in Python. BILL remains disconnected until the user obtains approval from their boss. Matching demonstrations must never be presented as checks against the actual BILL account.

## Scope

- Enable AP Statements and change its action from Coming Soon to Open program.
- Host the existing application and its PDF and OCR dependencies as a local Streamlit custom component.
- Retain multiple PDF uploads, scanned PDF OCR, source previews, extraction corrections, vendor mapping, review decisions, notes, and CSV reports.
- Retain fictional sample records and the optional CSV comparison adapter with explicit source labels.
- Provide an All Programs action and keep Daily Deposits separate.

Live BILL authentication, QuickBooks checks, payments, accounting writes, shared databases, and changes to portal access controls are outside this phase. Credit Card Process remains disabled. No vendor PDFs or financial test fixtures may be committed to GitHub.

## User Experience

The home screen keeps its existing layout. AP Statements becomes available alongside Daily Deposits. Selecting it opens a short portal header, an All Programs control, and the embedded Statement Desk workspace. The workspace keeps its Statements, Exceptions, Vendors, and BILL connection views.

The component initially shows fictional sample statements unless a locally saved session exists. Uploading actual statements leaves their matching results unverified when no comparison records are available. Simulated comparisons require an explicit user action and remain visibly labeled. Low confidence extraction, unreadable scans, unsupported layouts, missing rows, and total discrepancies require review; the integration does not promise automatic support for every vendor layout.

The portal header explains that Save session retains extracted rows, imported comparison records, and review notes in the same browser. Original PDFs remain only in memory. Leaving the AP page or refreshing it releases those PDFs, so original previews require selecting the files again. Unsaved work is not guaranteed to survive navigation. The UI must warn users before leaving to save or export their work; it must not silently save financial data.

## Component Boundaries

The existing `app/program_hub_ui.py` registry remains responsible for program availability and selection. Add a named AP Statements identifier and enable only that additional program.

Add `app/ap_statements_ui.py` as a focused Python renderer. It declares the custom component from a repository-local frontend directory, renders portal navigation and privacy guidance, and checks that the frontend entrypoint exists. It does not receive PDF bytes or invoke the Daily Deposit engine.

The frontend directory contains the existing application modules, styles, and bundled PDF.js and Tesseract assets. A small Streamlit bridge handles component readiness, initial rendering, and frame sizing. Python passes only nonfinancial presentation configuration. The bridge must not return extracted invoices, notes, PDF bytes, or comparison records to Python. Streamlit rerenders must not reinitialize an already mounted workspace.

PDF.js, its worker, the Tesseract worker and WebAssembly files, and English language data must resolve relative to the component URL. No OCR or PDF processing asset may depend on the separate ChatGPT Site. Include reproducible dependency metadata and required third-party license notices. Browser libraries are prepared during development and committed as deployable assets; Streamlit Cloud must not require Node or download OCR data at application startup.

## Routing and Existing Work

In `streamlit_app.py`, route AP Statements before the existing non-Daily guard. Render its page and stop that Streamlit run before Daily Deposit headers, sidebars, workbook processing, or accounting calculations execute.

Returning from AP Statements changes only the active program selection. It must not call Daily Deposit reset logic or alter its saved uploads, widget snapshot, page stage, completion state, or generated results. Reopening Daily Deposits continues to use the existing restoration functions. Invalid program selections still return safely to the hub.

## Data Safety and Failure Handling

All selected files and extraction stay inside the component's browser frame. Do not add a Streamlit file uploader, server OCR, external document service, document telemetry, or financial data in component messages. Render document text as untrusted content and retain HTML escaping and CSV formula protection.

Use AP-specific browser storage keys, separate from Daily Deposit state. Saving is optional, local to the browser, and not protected as a separate user account on a shared computer. Explain that limitation and retain a Clear workspace action. Storage-disabled or quota-exceeded cases must show an actionable message while leaving in-memory work usable.

If the frontend build is missing, show an AP-specific error with working hub navigation rather than crashing Daily Deposits. Asset-loading or OCR failures must identify the failed document and allow other documents to remain usable. Failed extraction must not become a successful match or a missing-invoice conclusion.

## Validation and Release

Update hub tests to expect Daily Deposits and AP Statements enabled, with Credit Card Process still disabled. Test AP activation, return navigation, invalid selections, and an AP-to-hub-to-Daily round trip without changing prior Daily work. Test the AP route's stop boundary and the missing-component fallback.

Run all existing Python regression tests and the prototype's matching-rule tests. In a real browser, verify component readiness, relative asset loading, digital PDF extraction, scanned PDF OCR, correction and confirmation, simulated versus unavailable data labels, CSV import and export, saved-session restoration, and navigation. Use synthetic PDFs and records for repeatable automated checks; supplied financial PDFs stay outside source control and cloud uploads.

Confirm that browser network requests contain no PDF bytes or extracted financial data and that narrow layouts keep upload, save, export, review, and portal navigation controls usable. Check that a saved session restores notes without claiming that its original PDF was retained.

Prepare the change in an isolated development branch and review the diff for unrelated Daily Deposit modifications. Publishing to the configured Streamlit branch should occur only after the regression and browser checks pass. Preserve the existing deployment configuration and audience. The separate ChatGPT Site and AP prototype repository remain unchanged.

If Streamlit serving or iframe behavior prevents the embedded build from functioning, report the concrete compatibility issue before switching to a Python rewrite or external link. Those alternatives change the approved approach.
