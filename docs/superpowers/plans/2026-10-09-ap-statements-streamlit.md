# AP Statements Streamlit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open the existing browser-based Statement Desk through the AP Statements card without changing Daily Deposit behavior or connecting BILL.

**Architecture:** Streamlit hosts a repository-local custom component containing the existing JavaScript application and its PDF and OCR assets. A small Python renderer provides portal navigation; the component retains all financial data in the browser. The existing program router stops before Daily Deposit rendering whenever AP Statements is active.

**Tech Stack:** Existing Streamlit `>=1.37,<2`, Python unittest, browser ES modules, PDF.js `5.4.624`, Tesseract.js `6.0.1`, English data package `1.0.0`, Node test runner, pnpm, and the official Streamlit component library bundled during development.

**Spec:** `docs/superpowers/specs/2026-10-09-ap-statements-streamlit-design.md`

**Execution status:** Implemented on the local feature branch. Final automated checks: 305 Python tests and 24 Node tests pass. Independent review finding fixed. See `docs/ap-statements-validation.txt` for browser evidence and remaining pre-production checks. Integration/deployment awaits user choice.

## Global Constraints

- BILL remains disconnected until the user obtains approval from their boss.
- Credit Card Process remains disabled.
- No vendor PDFs or financial test fixtures may be committed to GitHub.
- The bridge must not return extracted invoices, notes, PDF bytes, or comparison records to Python.
- Streamlit Cloud must not require Node or download OCR data at application startup.
- Returning from AP Statements changes only the active program selection.
- Preserve the existing deployment configuration and audience.
- The separate ChatGPT Site and AP prototype repository remain unchanged.
- Work in an isolated branch/worktree following `superpowers:using-git-worktrees`; preserve the approved design and this plan in that checkout.

## File Structure

- Modify `app/program_hub_ui.py`: AP identifier and availability only.
- Modify `streamlit_app.py`: import and early AP routing only.
- Create `app/ap_statements_ui.py`: Python component declaration, missing-build fallback, exit guidance, and hub return.
- Create `app/ap_statements/frontend/`: copied application modules, HTML, CSS, local vendor assets, and the built Streamlit bridge.
- Create `app/ap_statements/bridge_core.mjs` and `streamlit_bridge.mjs`: testable readiness/height adapter and SDK entrypoint.
- Create `app/ap_statements/frontend/session.mjs`: browser-storage operations, served with the copied frontend app.
- Create `app/ap_statements/package.json`, lockfile, `build.mjs`, `.gitignore`, and `THIRD_PARTY_NOTICES.md`: reproducible local builds, ignored development dependencies, deployable assets, and licenses.
- Create `tests/test_ap_statements_ui.py`, `tests/test_ap_assets.py`, `tests/ap_statements_bridge.test.mjs`, and `tests/ap_statements_session.test.mjs`.
- Create `tests/ap_statements_core.test.mjs` by adapting the existing 14 domain tests; modify `tests/test_program_hub_ui.py` for the additional enabled program.
- Modify `README_WEB_APP`: AP usage, build instructions, privacy limitations, and deployment checklist.

## Review Focus

1. A missing worker or WASM asset must report a document-processing failure, not a match; Task 1 asset checks and Task 4 browser failure checks own this.
2. A Streamlit rerender must not reset an already mounted AP workspace; Task 1 bridge tests and Task 4 browser checks own this.
3. Disabled, corrupt, or full browser storage must not silently claim a successful save; Task 2 storage tests own this.
4. Returning through the hub must preserve Daily uploads, widget values, workflow stage, and results; Task 3 round-trip tests own this.
5. A failed PDF among valid PDFs must leave successful documents available and all actual uploads unverified without BILL records; Task 4 mixed-batch checks own this.

## Task 1 Package the Streamlit Component

**Files:** `app/ap_statements/` build metadata, bridge modules, frontend files, notices; `tests/test_ap_assets.py`, `tests/ap_statements_bridge.test.mjs`, `tests/ap_statements_core.test.mjs`.

**Interfaces:**

- Consumes the existing prototype from `../vendor-statement-app/dist/`, its pinned dependency metadata, and `tests/core.test.mjs`; do not copy `.openai`, credentials, local PDFs, browser sessions, or `.git`.
- Produces `app/ap_statements/frontend/index.html` and all referenced assets.
- Produces `attachStreamlitBridge(sdk, height = 900): void`; its SDK interface is `setComponentReady(): void` and `setFrameHeight(height: number): void`. It calls each once during mount. Streamlit render notifications do not reimport or initialize the application.

- [ ] Write failing bridge tests named `announces_ready_and_height_once` and `never_sends_component_values`: assert one readiness call, one height call with `900`, and no financial-data or component-value calls on mount or repeated render notifications. Use a fake SDK rather than importing browser-only dependencies into Node tests.

  Core assertions: `assert.equal(readyCalls, 1)`, `assert.deepEqual(heightCalls, [900])`, and `assert.equal(valueCalls, 0)` after the initial mount and repeated render notifications.
- [ ] Write failing Python asset tests checking `index.html`, application modules, PDF.js worker, Tesseract worker, English data, at least one complete supported WASM core pair, and license notices. Assert asset URLs are relative and have no reference to `chatgpt.site` or remote OCR services.
- [ ] Run `node --test tests/ap_statements_bridge.test.mjs` and `python -m unittest discover -s tests -p test_ap_assets.py -v`; both should fail because the component files do not exist.
- [ ] Copy the application and adapt the domain-test import to `../app/ap_statements/frontend/core.mjs`. Keep matching behavior unchanged.
- [ ] Implement the bridge core and SDK entrypoint. Use the official SDK, bundle the entrypoint locally, and pin the SDK and bundler versions in the package and lockfile. Load the application only once per frame and keep module/worker URLs relative to the component location.
- [ ] Implement `build.mjs` to prepare the PDF/OCR assets and bridge bundle from pinned dependencies. Include required license notices; exclude source maps and unnecessary package files. Commit deployable runtime assets, but ignore `node_modules`, package stores, logs, and temporary files.
- [ ] Run the build and the asset, bridge, and domain tests. Inspect the build inventory for missing runtime files and GitHub's file-size limit. Expected: all tests pass and every referenced runtime asset exists locally.
- [ ] Commit this independently testable component bundle with a scoped commit message.

## Task 2 Adapt Local Saving and Exit Guidance

**Files:** `app/ap_statements/frontend/session.mjs`, copied `frontend/app.mjs`, `frontend/styles.css`, `tests/ap_statements_session.test.mjs`.

**Interfaces:**

- Produces `loadSession(storage): {session: object | null, error: string | null}` and `saveSession(storage, session): {ok: boolean, error: string | null}`.
- Produces `clearSession(storage): {ok: boolean, error: string | null}`, `loadVendorMappings(storage): {mappings: object, error: string | null}`, and `saveVendorMappings(storage, mappings): {ok: boolean, error: string | null}`.
- Uses dedicated keys `hwfc-ap-statements-session-v1` and `hwfc-ap-statements-vendors-v1`; no Daily Deposit keys or old Site keys are accessed.
- A saved session includes version `1`, statements, provider, and review resolutions, but never `File`, PDF bytes, canvas data, or object URLs.

- [ ] Write failing tests for saved-session round trips, malformed JSON, wrong session versions, denied reads, quota-exceeded writes, and failed deletion. Assert denied/full storage returns an actionable error and cannot report `ok: true`. Assert serialized sessions omit original PDF data.

  Core assertions: `assert.equal(saveSession(fullStorage, fixture).ok, false)`, `assert.ok(loadSession(deniedStorage).error)`, `assert.equal(loadSession(wrongVersionStorage).session, null)`, and `assert.equal(serialized.includes('PDF_BYTES_SENTINEL'), false)` when the input includes an extraneous PDF field. Serialize an explicit metadata allowlist rather than the arbitrary caller object.
- [ ] Run `node --test tests/ap_statements_session.test.mjs`; expect missing-module/function failures.
- [ ] Implement the storage functions and use them in the copied application. Failed Save session, vendor mapping, or Clear workspace actions must report failure while retaining usable in-memory work. Stored vendor mappings are persisted only by explicit user action.
- [ ] Keep Save session visible on narrow screens. Explain that saved rows and notes are browser-local, original PDFs must be selected again after leaving, and saved financial metadata is visible to other users of the same browser profile. Remove externally hosted font imports and use system fallbacks.
- [ ] Retain unavailable-versus-missing labels, explicit simulated comparisons, correction/confirmation, report source labels, HTML escaping, and CSV formula protection.
- [ ] Run session and domain tests. Verify the frontend only stores metadata after a user save and never includes PDF originals. Expected: all tests pass.
- [ ] Commit the local-saving adaptation separately.

## Task 3 Enable Portal Routing Without Daily Regressions

**Files:** `app/program_hub_ui.py`, `app/ap_statements_ui.py`, `streamlit_app.py`, `tests/test_program_hub_ui.py`, `tests/test_ap_statements_ui.py`.

**Interfaces:**

- Produces `AP_STATEMENTS = "ap_statements"` in the existing hub registry; `PROGRAMS` availability becomes `[True, False, True]` in its current order.
- Produces `ap_frontend_path() -> Path` and `render_ap_statements(ui, *, component_renderer=None, frontend_path=None) -> bool`. Return `True` only for confirmed navigation to All Programs, otherwise `False`.
- The default component renderer declares `hwfc_ap_statements` with `path=ap_frontend_path()` and renders with stable key `hwfc_ap_statements_workspace`; it does not accept financial inputs or use returned component values.
- The entrypoint calls `return_to_program_hub(st.session_state)` and `st.rerun()` when the renderer returns `True`; otherwise it calls `st.stop()` for the AP route.

- [ ] Update hub tests to expect enabled AP selection and one disabled Credit Card action. Change the old disabled-program mutation test to use `credit_card_process`. Add AP activation and a Daily-to-hub-to-AP-to-hub-to-Daily test that preserves the exact Daily snapshot, upload object, page stage, completion state, and generated result.

  Core assertions: `self.assertEqual([p.enabled for p in PROGRAMS], [True, False, True])`, `self.assertTrue(activate_program(state, AP_STATEMENTS))`, `self.assertIs(preserved_daily_upload(state, upload_key), uploaded_workbook)`, and `self.assertEqual(state[DEPOSIT_PAGE_STAGE_KEY], DEPOSIT_STEPS_STAGE)` after the round trip.
- [ ] Add recording-UI renderer tests for title, privacy/exit guidance, stable component key, and a missing `index.html`. Assert missing builds show an error without invoking the component and still allow returning to the hub.
- [ ] Test an exit confirmation: the initial All Programs click shows a save/export reminder without changing the active program; Stay keeps AP open; Leave returns `True`. This confirmation is UI state only and never sends AP financial data to Python.
- [ ] Add an entrypoint test proving the AP route precedes the non-Daily guard and ends with `st.stop()` before Daily Deposit rendering. Assert the route never calls Daily reset or accounting functions.
- [ ] Run `python -m unittest discover -s tests -p test_program_hub_ui.py -v` and the AP renderer tests. Expect failures for the disabled AP registry and missing renderer.
- [ ] Implement only the registry change, isolated renderer, and early entrypoint route. Keep existing Daily state preservation/restoration logic and Credit Card behavior unchanged. Use the exit-confirmation sequence above to prevent accidental departure.
- [ ] Run the targeted tests and `python -m unittest discover -s tests -v`. Expected: the new tests and all existing Python regressions pass.
- [ ] Commit the portal routing change separately.

## Task 4 Validate and Prepare Release

**Files:** `README_WEB_APP`; temporary synthetic fixtures and evidence outside tracked source.

**Interfaces:** Consumes the bundled frontend, renderer, and route from Tasks 1–3. Produces a tested branch and user-facing release summary; no change to BILL or the separate Site.

- [ ] Document how to open AP Statements, distinguish sample/CSV/unavailable data, save/export work before leaving, restore metadata and select originals again, and clear browser-local data. Add the exact local component build command and note that Node is unnecessary on Streamlit Cloud.
- [ ] Run `python -m unittest discover -s tests -v`, `node --test tests/ap_statements_core.test.mjs tests/ap_statements_bridge.test.mjs tests/ap_statements_session.test.mjs`, and `git diff --check`. Expected: zero failures and no whitespace errors.
- [ ] Start `python -m streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501` for browser QA. Open AP from the actual hub; verify readiness, relative worker/WASM/language assets, and no separate ChatGPT login.
- [ ] Generate clearly fictional digital and image-only PDF fixtures outside tracked source. Upload a mixed batch including an invalid PDF; assert valid documents remain available, the invalid file is reported, and actual uploads show unavailable BILL data rather than verified matches or missing invoices. Deliberately fail a worker asset in a local-only test and confirm it cannot clear a document as matched.
- [ ] Confirm extraction corrections, row confirmation, simulated comparisons, CSV import, report downloads, saved notes, and restoring a session without its originals. Trigger a benign Streamlit rerender and verify the mounted AP workspace is not reset.
- [ ] Verify narrow layouts expose upload, save, export, review, and navigation. Exercise Stay and Leave in the exit confirmation, then reopen Daily Deposits and verify prior work is intact. Capture a screenshot using fictional data.
- [ ] Check requests using an available browser network/log inspection surface or a local diagnostic request log. No selected PDF bytes, extracted records, or notes may be transmitted to Streamlit or an external service. If inspection is unavailable, explicitly report this verification gap; do not claim it passed.
- [ ] Review the entire diff for unrelated Daily changes, credentials, customer data, missing licenses, oversized assets, and build completeness. Use `superpowers:requesting-code-review` and `superpowers:verification-before-completion` before release claims.
- [ ] Follow `superpowers:finishing-a-development-branch` to offer the tested integration choices. Do not force-push or change portal access settings. If authorized integration reaches Streamlit's configured `main`, check the live portal for the enabled AP card and working component before saying the portal is updated.

## Self Review

All design requirements map to Tasks 1–4. The five review-focus conditions have explicit owning tests or browser checks. Function names, component key, storage keys, and routing return values are consistent. Inline implementation and local validation are complete; live deployment remains deferred. Network-payload capture, actual download retrieval, full Daily workbook browser retention and missing-WASM fault injection remain explicitly unverified.
