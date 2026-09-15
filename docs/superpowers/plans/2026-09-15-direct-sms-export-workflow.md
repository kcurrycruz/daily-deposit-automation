# Direct SMS Export Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the assembled Daily Workbook upload with six directly uploaded SMS `.xls` reports and deliver the completed reporting workbook only after the deposit and IIF finish successfully.

**Architecture:** Parse each legacy SMS export into a content-identified, date-validated bundle. Build one deterministic internal Daily Workbook from the normalized rows so the established deposit engine and guided-step readers continue using their proven interfaces. After the engine validates the IIF, expose that workbook as the dated reporting artifact and archive it with the six source reports.

**Tech Stack:** Python 3, Streamlit, `xlrd` for legacy BIFF `.xls`, `openpyxl` for the internal/reporting `.xlsx`, `unittest`, existing subprocess-based IIF engine.

**Spec:** `docs/superpowers/specs/2026-09-15-direct-sms-export-workflow-design.md`

## Global Constraints

- Required SMS roles are exactly Sales, Coupons, Discounts, HASH, Balance Sheet, and Milk Bottles.
- Identify reports from workbook contents; filename text is only a secondary hint.
- All six SMS report dates must match before the user can continue.
- Keep the separate Card Settlement upload and its exact `Processed Net Amount` rule.
- Preserve every existing IIF mapping, guided step, sign rule, and TBA safeguard.
- The 9/14/2026 Milk Bottle control is `$74.00` from the item report plus `$8.00` from BS code 910, producing `-$82.00` in the IIF.
- Offer `SubDept Single Total Report M-D-YY.xlsx` only when the complete deposit and IIF process succeeds.
- Do not stage or delete unrelated `.superpowers`, temporary test directories, or `_sales_mapping_*` artifacts.

---

### Task 1: Legacy SMS workbook reader and content detection

**Files:**
- Create: `app/sms_exports.py`
- Modify: `requirements.txt`
- Create: `tests/test_sms_exports.py`
- Create: `tests/sms_fixture_factory.py`
- Create: `tests/fixtures/sms/minimal_sales.xls`

**Interfaces:**
- Produces: `SMS_ROLE_ORDER`, `SmsExport`, `read_sms_xls(file_bytes)`, `classify_sms_rows(rows)`, `parse_sms_export(filename, file_bytes)`.
- Consumed by: Tasks 2 and 4.

- [ ] **Step 1: Write failing reader and role-detection tests**

```python
def test_classifies_each_report_from_content_instead_of_filename():
    cases = {
        "sales": sms_rows("sales"),
        "coupons": sms_rows("coupons"),
        "discounts": sms_rows("discounts"),
        "hash": sms_rows("hash"),
        "bs": sms_rows("bs"),
        "milk_bottles": sms_rows("milk_bottles"),
    }
    for expected, rows in cases.items():
        assert classify_sms_rows(rows) == expected


def test_reads_committed_biff_xls_fixture():
    report = parse_sms_export(
        "renamed-file.xls",
        Path("tests/fixtures/sms/minimal_sales.xls").read_bytes(),
    )
    assert report.role == "sales"
    assert report.report_date == date(2026, 9, 14)
```

The production mutation caught is choosing a report from its filename or losing support for real BIFF `.xls` bytes.

- [ ] **Step 2: Run the new tests and verify RED**

Run: `python -X utf8 -m unittest tests.test_sms_exports -v`

Expected: import failure for `app.sms_exports`.

- [ ] **Step 3: Add the dependency and minimal parser**

Add `xlrd>=2.0.1,<3` to `requirements.txt`, then implement:

```python
SMS_ROLE_ORDER = ("sales", "coupons", "discounts", "hash", "bs", "milk_bottles")

@dataclass(frozen=True)
class SmsExport:
    role: str
    filename: str
    report_date: date
    rows: tuple[tuple[object, ...], ...]

def read_sms_xls(file_bytes: bytes) -> tuple[tuple[object, ...], ...]:
    book = xlrd.open_workbook(file_contents=file_bytes, on_demand=True)
    sheet = book.sheet_by_index(0)
    return tuple(tuple(sheet.cell_value(r, c) for c in range(sheet.ncols))
                 for r in range(sheet.nrows))
```

Normalize strings only for detection. Preserve numeric cell values in `SmsExport.rows`. Parse `Date:` values in both split-cell and single-cell forms. Raise user-facing `ValueError` messages for unreadable, ambiguous, or undated files.

Create `tests.sms_fixture_factory.sms_rows(role, report_date=date(2026, 9, 14))` with literal tuples matching each supplied SMS header and column layout. The helper returns rows, not expected totals, so assertions remain independently hand-derived.

- [ ] **Step 4: Verify GREEN**

Run: `python -X utf8 -m unittest tests.test_sms_exports -v`

Expected: all Task 1 tests pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add -- requirements.txt app/sms_exports.py tests/test_sms_exports.py tests/sms_fixture_factory.py tests/fixtures/sms/minimal_sales.xls
git commit -m "feat: detect legacy SMS exports"
```

---

### Task 2: Six-report bundle validation and source calculations

**Files:**
- Modify: `app/sms_exports.py`
- Create: `app/sms_deposit_data.py`
- Modify: `tests/test_sms_exports.py`
- Create: `tests/test_sms_deposit_data.py`

**Interfaces:**
- Consumes: `SmsExport`, `SMS_ROLE_ORDER`, and `sms_rows` from Task 1.
- Produces: `SmsExportBundle`, `build_sms_export_bundle(reports)`, `validate_sms_exports(files)`, `SmsDepositData`, `build_sms_deposit_data(bundle)`.
- Consumed by: Tasks 3 and 5.

- [ ] **Step 1: Write failing bundle validation tests**

```python
def test_bundle_accepts_six_reports_in_any_order():
    bundle = build_sms_export_bundle(reversed(sms_exports_091426()))
    assert tuple(bundle.reports) == SMS_ROLE_ORDER
    assert bundle.deposit_date == date(2026, 9, 14)

def test_bundle_names_duplicate_and_missing_roles():
    with self.assertRaisesRegex(ValueError, "Two files were detected as HASH"):
        build_sms_export_bundle(sms_exports_091426(duplicate="hash"))
    with self.assertRaisesRegex(ValueError, "Milk Bottles report is missing"):
        build_sms_export_bundle(sms_exports_091426(omit="milk_bottles"))

def test_bundle_blocks_mismatched_report_dates():
    with self.assertRaisesRegex(ValueError, "Coupon report date 09/13/2026.*Sales report date 09/14/2026"):
        build_sms_export_bundle(sms_exports_091426(coupon_date=date(2026, 9, 13)))
```

The production mutation caught is accepting six files without proving that each required role and date is unique and consistent.

- [ ] **Step 2: Run bundle tests and verify RED**

Run: `python -X utf8 -m unittest tests.test_sms_exports -v`

Expected: missing `SmsExportBundle` and `validate_sms_exports` failures.

- [ ] **Step 3: Implement deterministic bundle validation**

```python
@dataclass(frozen=True)
class SmsExportBundle:
    deposit_date: date
    reports: Mapping[str, SmsExport]

def validate_sms_exports(files: Iterable[object]) -> SmsExportBundle:
    parsed = [parse_sms_export(item.name, item.getvalue()) for item in files]
    return build_sms_export_bundle(parsed)
```

Implement `build_sms_export_bundle` as the pure validation core: reject duplicate roles, list missing roles, require one common date, and return reports ordered by `SMS_ROLE_ORDER`. Extend `tests.sms_fixture_factory` with `sms_exports_091426(omit=None, duplicate=None, coupon_date=None)` returning real `SmsExport` objects built from the literal row fixtures.

- [ ] **Step 4: Write the failing 9/14 calculation backtest**

Use literal row fixtures matching the supplied source layouts and hand-derived expected values:

```python
def test_091426_source_calculations_preserve_unusual_totals():
    data = build_sms_deposit_data(build_sms_export_bundle(sms_exports_091426()))
    assert data.sales_total == Decimal("86502.80")
    assert data.coupon_total == Decimal("61.69")
    assert data.store_coupons_raw == Decimal("-1428.18")
    assert data.milk_bottle_export_total == Decimal("74.00")
    assert data.store_coupons_adjusted == Decimal("-1354.18")
    assert data.bs_data["milk_bottle_return"] == Decimal("8.00")
    assert data.iif_milk_bottle_return == Decimal("-82.00")
    assert data.discount_total == Decimal("3981.21")
    assert data.hash_refunded == Decimal("4.89")
    assert data.hash_pass_through == Decimal("6.00")
```

Add a separate test proving that Milk Bottles only sums `Net Sales` lines belonging to item descriptions containing both `milk bottle` and `returned`; coupon promotions and grand totals must not enter the `$74.00` result.

- [ ] **Step 5: Run calculation tests and verify RED**

Run: `python -X utf8 -m unittest tests.test_sms_deposit_data -v`

Expected: import failure for `app.sms_deposit_data`.

- [ ] **Step 6: Implement normalized calculations with `Decimal`**

```python
@dataclass(frozen=True)
class SmsDepositData:
    deposit_date: date
    sales_by_subdept: Mapping[int, Decimal]
    coupons_by_subdept: Mapping[int, Decimal]
    discounts_by_level: Mapping[int, Decimal]
    sales_total: Decimal
    coupon_total: Decimal
    discount_total: Decimal
    store_coupons_raw: Decimal
    milk_bottle_export_total: Decimal
    store_coupons_adjusted: Decimal
    bs_data: Mapping[str, Decimal]
    hash_refunded: Decimal
    hash_pass_through: Decimal
    hash_paid_in: Decimal

    @property
    def iif_milk_bottle_return(self) -> Decimal:
        return -(abs(self.milk_bottle_export_total)
                 + abs(self.bs_data.get("milk_bottle_return", Decimal("0.00"))))
```

Parse the established source columns by report meaning, not by selecting the first nonzero number. Compare Sales, Coupons, Discounts, and HASH detail sums with their report control rows and reject differences greater than `$0.01`.

- [ ] **Step 7: Verify GREEN and commit Task 2**

Run: `python -X utf8 -m unittest tests.test_sms_exports tests.test_sms_deposit_data -v`

```powershell
git add -- app/sms_exports.py app/sms_deposit_data.py tests/test_sms_exports.py tests/test_sms_deposit_data.py tests/sms_fixture_factory.py
git commit -m "feat: normalize six SMS reports"
```

---

### Task 3: Reporting workbook template and deterministic builder

**Files:**
- Create: `assets/SubDept Single Total Report Template.xlsx`
- Create: `app/daily_reporting_workbook.py`
- Create: `tests/test_daily_reporting_workbook.py`

**Interfaces:**
- Consumes: `SmsExportBundle` and `SmsDepositData` from Task 2.
- Produces: `reporting_workbook_name(deposit_date)` and `build_reporting_workbook(template_path, bundle, data) -> bytes`.
- Consumed by: Task 5.

- [ ] **Step 1: Create a sanitized template asset**

Use the supplied `SubDept Single Total Report 9-14-26.xlsx` as the visual baseline. Preserve its tab order, dimensions, fills, borders, fonts, number formats, widths, and labels. Clear date-specific rows from `SubDept Single`, `SubDept Coupon (Local Discount)`, `XXXXXX Discounts`, `XXXXXX BS`, and `XXXXXX Hash`; clear calculated values from `SubDept Sales Report`; retain the empty supporting Maria College tabs and established reference tabs.

- [ ] **Step 2: Write failing workbook output tests**

```python
def test_report_name_uses_no_leading_zero_month_or_day():
    assert reporting_workbook_name(date(2026, 9, 4)) == (
        "SubDept Single Total Report 9-4-26.xlsx"
    )

def test_generated_091426_report_contains_verified_values_and_dated_tabs():
    bundle = build_sms_export_bundle(sms_exports_091426())
    data = build_sms_deposit_data(bundle)
    output = build_reporting_workbook(TEMPLATE, bundle, data)
    workbook = load_workbook(BytesIO(output), data_only=True)
    assert workbook.sheetnames[-3:] == ["091426 Discounts", "091426 BS", "091426 Hash"]
    report = workbook["SubDept Sales Report"]
    assert report["J3"].value == 86502.80
    assert report["M1"].value == 74.00
    assert report["M2"].value == -1354.18
```

Add assertions that Sales and Coupon source rows land in columns A:G, output money cells are numeric with two-decimal formats, the six input dates are unchanged, and key reference styles match the sanitized template.

The production mutation caught is creating a visually similar workbook with stale formulas, shifted source columns, wrong dated tab names, or text-formatted money.

- [ ] **Step 3: Run workbook tests and verify RED**

Run: `python -X utf8 -m unittest tests.test_daily_reporting_workbook -v`

Expected: import failure for `app.daily_reporting_workbook`.

- [ ] **Step 4: Implement the builder**

```python
def reporting_workbook_name(deposit_date: date) -> str:
    return ("SubDept Single Total Report "
            f"{deposit_date.month}-{deposit_date.day}-{deposit_date:%y}.xlsx")

def build_reporting_workbook(template_path: Path,
                             bundle: SmsExportBundle,
                             data: SmsDepositData) -> bytes:
    workbook = load_workbook(template_path)
    # copy Sales and Coupon B:H data rows to A:G
    # copy full Discounts, BS, and HASH source grids into dated sheets
    # write verified numeric department and summary results
    # set fullCalcOnLoad only as a convenience, never as a validation dependency
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
```

Write fixed, verified numeric results in the dated snapshot. Preserve the template's formatting and do not make the IIF depend on Excel recalculation.

- [ ] **Step 5: Verify GREEN and inspect the workbook**

Run: `python -X utf8 -m unittest tests.test_daily_reporting_workbook -v`

Open a disposable 9/14 output with `data_only=True` and `data_only=False`; verify the same key amounts are available in both views. Render or open the affected sheets and inspect for clipped labels, shifted columns, lost styles, and `####` values.

- [ ] **Step 6: Commit Task 3**

```powershell
git add -- "assets/SubDept Single Total Report Template.xlsx" app/daily_reporting_workbook.py tests/test_daily_reporting_workbook.py
git commit -m "feat: build daily reporting workbook"
```

---

### Task 4: Six-file upload UI, persistence, and progress

**Files:**
- Modify: `app/upload_intake_ui.py`
- Modify: `app/program_hub_ui.py`
- Modify: `app/operations_status_ui.py`
- Modify: `tests/test_upload_intake_ui.py`
- Modify: `tests/test_program_hub_ui.py`
- Modify: `tests/test_operations_status_ui.py`

**Interfaces:**
- Consumes: `SMS_ROLE_ORDER` and bundle validation status.
- Produces: `UploadIntakeRender.sms_exports`, `render_sms_validation(ui, reports, error)`, preserved `sms_reports_<key>` uploader state, and six-report progress text.
- Consumed by: Task 5.

- [ ] **Step 1: Write failing UI contract tests**

```python
def test_upload_row_accepts_multiple_sms_xls_files_and_card_settlement():
    render_upload_inputs(ui, uploader_key=7)
    sms_call, settlement_call = ui.uploader_calls
    assert sms_call.label == "Upload SMS reports"
    assert sms_call.kwargs["type"] == ["xls"]
    assert sms_call.kwargs["accept_multiple_files"] is True
    assert settlement_call.kwargs["type"] == ["xlsx", "xlsm"]

def test_validation_card_shows_six_required_roles_and_progress():
    render_sms_validation(ui, reports={"sales": report}, error=None)
    assert "1 of 6 verified" in ui.markup
    assert "Milk Bottles" in ui.markup
```

Add persistence tests proving a list of uploaded SMS files survives the upload-to-guided-stage transition and returning from All Programs, while Start Over clears it.

- [ ] **Step 2: Run UI tests and verify RED**

Run: `python -X utf8 -m unittest tests.test_upload_intake_ui tests.test_program_hub_ui tests.test_operations_status_ui -v`

Expected: old Daily Workbook uploader labels and two-file status fail.

- [ ] **Step 3: Implement the compact upload presentation**

Keep the current horizontal layout: Report Date, SMS Reports, Card Settlement. Replace the workbook uploader with the multi-file `.xls` uploader. Render six small role statuses in the existing verified-card style and show actionable validation text beneath the uploader.

Update `_DAILY_UPLOAD_PREFIXES` to preserve `sms_reports_` and `card_settlement_`. Update Operations Status so the file line distinguishes SMS progress from settlement readiness, for example `6 of 6 SMS verified · Card Settlement needed` and `All reports verified`.

- [ ] **Step 4: Verify GREEN and commit Task 4**

Run: `python -X utf8 -m unittest tests.test_upload_intake_ui tests.test_program_hub_ui tests.test_operations_status_ui -v`

```powershell
git add -- app/upload_intake_ui.py app/program_hub_ui.py app/operations_status_ui.py tests/test_upload_intake_ui.py tests/test_program_hub_ui.py tests/test_operations_status_ui.py
git commit -m "feat: upload six SMS reports"
```

---

### Task 5: Connect normalized SMS inputs to the existing deposit workflow

**Files:**
- Modify: `streamlit_app.py`
- Modify: `app/operations_status_ui.py`
- Modify: `tests/test_current_deposit_state.py`
- Modify: `tests/test_deposit_workflow.py`
- Modify: `tests/test_membership_payments.py`

**Interfaces:**
- Consumes: `validate_sms_exports`, `build_sms_deposit_data`, `build_reporting_workbook`.
- Produces: an internal generated workbook object with `.name` and `.getvalue()` compatible with the existing `run_engine` interface; result keys `reporting_workbook_bytes` and `reporting_workbook_name` only after successful engine completion.
- Consumed by: Tasks 6 and 7.

- [ ] **Step 1: Write failing workflow identity and gating tests**

```python
def test_run_context_changes_when_any_sms_source_changes():
    source_bytes = {role: role.encode("ascii") for role in SMS_ROLE_ORDER}
    first = sms_run_context(source_bytes, b"settlement", inputs={})
    changed = source_bytes | {"hash": b"changed hash"}
    assert sms_run_context(changed, b"settlement", inputs={}) != first

def test_report_workbook_is_not_downloadable_before_success():
    assert deposit_download_details({"working_workbook_bytes": b"internal"}) is None

def test_successful_engine_result_receives_completed_reporting_workbook():
    bundle = build_sms_export_bundle(sms_exports_091426())
    data = build_sms_deposit_data(bundle)
    engine_result = {
        "iif_bytes": b"IIF body",
        "iif_path": Path("deposit_20260914.iif"),
        "validation": {"all_ok": True},
    }
    result = complete_sms_run(engine_result, bundle, data)
    assert result["reporting_workbook_name"] == (
        "SubDept Single Total Report 9-14-26.xlsx"
    )
    assert result["reporting_workbook_bytes"]
```

The production mutation caught is reusing a stale IIF after one source file changes or exposing the workbook before successful completion.

- [ ] **Step 2: Run integration tests and verify RED**

Run: `python -X utf8 -m unittest tests.test_current_deposit_state tests.test_deposit_workflow tests.test_membership_payments -v`

Expected: missing six-source run context and reporting result fields.

- [ ] **Step 3: Replace workbook ingestion on the upload page**

In `streamlit_app.py`:

1. Parse the multi-upload list and show partial role progress even before the bundle is complete.
2. Build a validated bundle only when all six roles are present and dates match.
3. Build `SmsDepositData` and the deterministic internal workbook bytes.
4. Feed those internal workbook bytes through the current workbook role detection and guided-step extraction functions.
5. Keep the existing Card Settlement validation.
6. Hash all six original source byte streams in role order for `current_run_context`.
7. Pass the internal workbook object to the existing `run_engine` only after all guided work is complete.
8. Attach the reporting bytes and dated filename to the result only after `run_engine` returns a fully validated IIF result.

Use a narrow compatibility wrapper:

```python
@dataclass(frozen=True)
class GeneratedWorkbookUpload:
    name: str
    data: bytes

    def getvalue(self) -> bytes:
        return self.data
```

- [ ] **Step 4: Add the explicit Milk Bottle end-to-end assertion**

Run the 9/14 internal workbook through the existing engine parsing path and assert that the IIF contains one `Milk Bottle Return` SPL for account `1311100` with amount `-82.00`. Also assert that the workbook summary retains `M1=74.00`, ensuring the BS `$8.00` is added only at the IIF stage.

- [ ] **Step 5: Verify GREEN and commit Task 5**

Run: `python -X utf8 -m unittest tests.test_current_deposit_state tests.test_deposit_workflow tests.test_membership_payments tests.test_sms_exports tests.test_sms_deposit_data tests.test_daily_reporting_workbook -v`

```powershell
git add -- streamlit_app.py app/operations_status_ui.py tests/test_current_deposit_state.py tests/test_deposit_workflow.py tests/test_membership_payments.py
git commit -m "feat: run deposits from SMS exports"
```

---

### Task 6: Final downloads and Run History archive

**Files:**
- Modify: `app/ui_helpers.py`
- Modify: `app/guided_step_ui.py`
- Modify: `app/run_history_ui.py`
- Modify: `streamlit_app.py`
- Modify: `tests/test_current_deposit_state.py`
- Modify: `tests/test_run_history_ui.py`
- Modify: `tests/test_membership_payments.py`

**Interfaces:**
- Consumes: successful result fields from Task 5.
- Produces: paired IIF/report download details and Run History records containing six source filenames plus the archived reporting workbook.

- [ ] **Step 1: Write failing paired-download and archive tests**

```python
def test_completed_result_offers_iif_and_reporting_workbook():
    result = {
        "iif_bytes": b"IIF body",
        "iif_path": Path("deposit_20260914.iif"),
        "reporting_workbook_bytes": b"XLSX body",
        "reporting_workbook_name": "SubDept Single Total Report 9-14-26.xlsx",
    }
    details = deposit_download_details(result)
    assert details["iif"]["file_name"] == "deposit_20260914.iif"
    assert details["report"]["file_name"] == (
        "SubDept Single Total Report 9-14-26.xlsx"
    )

def test_history_archives_six_sources_report_and_iif():
    uploads = uploaded_files_from_sms_rows(sms_exports_091426())
    result = complete_result_091426()
    record = archive_run(uploads, settlement, result, date(2026, 9, 14), roles, date_info)
    assert set(record["sms_source_filenames"]) == set(expected_six_names)
    assert Path(record["archived_reporting_workbook"]).is_file()
```

Define `uploaded_files_from_sms_rows` and `complete_result_091426` in `tests/test_run_history_ui.py` as local test helpers that return full file-like source objects and the complete real result shape, respectively. Do not mock filesystem writes; use the existing temporary history directories used by the Run History tests.

- [ ] **Step 2: Run download/history tests and verify RED**

Run: `python -X utf8 -m unittest tests.test_current_deposit_state tests.test_run_history_ui tests.test_membership_payments -v`

Expected: the old single-IIF download shape and single-workbook history schema fail.

- [ ] **Step 3: Implement paired downloads and backward-compatible history**

Render `Download QuickBooks IIF` and `Download Daily Reporting Workbook` together only when both successful result artifacts exist. Archive each SMS source under the run stamp, archive the generated reporting workbook, and retain compatibility when rendering older history records that contain only `uploaded_filename` and `archived_upload`.

- [ ] **Step 4: Verify GREEN and commit Task 6**

Run: `python -X utf8 -m unittest tests.test_current_deposit_state tests.test_run_history_ui tests.test_membership_payments -v`

```powershell
git add -- app/ui_helpers.py app/guided_step_ui.py app/run_history_ui.py streamlit_app.py tests/test_current_deposit_state.py tests/test_run_history_ui.py tests/test_membership_payments.py
git commit -m "feat: download and archive daily report"
```

---

### Task 7: Replace the obsolete workbook-building help text

**Files:**
- Modify: `streamlit_app.py`
- Modify: `app/deposit_help_ui.py`
- Modify: `tests/test_deposit_help_ui.py`

**Interfaces:**
- Consumes: the final six-report workflow.
- Produces: current SOP and exception guidance with no instruction to manually copy or move worksheets.

- [ ] **Step 1: Write failing help-content behavior tests**

```python
def test_sop_lists_six_sms_exports_and_generated_report():
    render_daily_workbook_sop(ui, root=ROOT, sop_steps=SOP_STEPS)
    text = ui.rendered_text
    for label in ("Sales", "Coupons", "Discounts", "HASH", "Balance Sheet", "Milk Bottles"):
        assert label in text
    assert "generated after the IIF is complete" in text
    assert "Move or Copy" not in text
```

- [ ] **Step 2: Run help tests and verify RED**

Run: `python -X utf8 -m unittest tests.test_deposit_help_ui -v`

Expected: current manual template-building instructions remain and fail the new behavior.

- [ ] **Step 3: Update SOP and known exceptions**

Replace the seven manual workbook-building steps with concise instructions for exporting and uploading the six SMS reports. Include the Milk Bottle rule in plain language: the app totals returned-item Net Sales, then combines it with BS code 910 for the final IIF line. Keep the supplied screenshots only where they still explain how to launch the correct SMS reports; remove captions that instruct the user to paste or move worksheet tabs.

- [ ] **Step 4: Verify GREEN and commit Task 7**

Run: `python -X utf8 -m unittest tests.test_deposit_help_ui -v`

```powershell
git add -- streamlit_app.py app/deposit_help_ui.py tests/test_deposit_help_ui.py
git commit -m "docs: update direct SMS upload guidance"
```

---

### Task 8: Full backtest, visual regression, and release readiness

**Files:**
- Modify only files required to correct failures introduced by Tasks 1-7.

**Interfaces:**
- Verifies all preceding interfaces together.

- [ ] **Step 1: Run focused 9/14 end-to-end backtest**

Run the six supplied 9/14 SMS exports through the local app pipeline with a controlled matching Card Settlement fixture. Confirm:

```text
SMS date                 09/14/2026
Sales control            86502.80
Coupon distribution         61.69
Milk Bottles                74.00
BS code 910                  8.00
IIF Milk Bottle Return     -82.00
Discount control          3981.21
HASH Refunded                4.89
HASH Pass Through            6.00
Report filename  SubDept Single Total Report 9-14-26.xlsx
```

- [ ] **Step 2: Run the complete automated regression suite**

Run: `python -X utf8 -m unittest discover -s tests -p 'test_*.py'`

Expected: all tests pass with exit code 0.

- [ ] **Step 3: Perform workbook verification**

Reopen the generated 9/14 report and inspect all sheets. Verify key values and formats, scan formulas for `#REF!`, `#VALUE!`, `#NAME?`, and `#N/A`, and visually inspect `SubDept Sales Report`, `SubDept Single`, `SubDept Coupon (Local Discount)`, and the three dated source tabs. Confirm no clipped labels, `####`, lost fills, or shifted data.

- [ ] **Step 4: Perform browser workflow verification**

In the local Streamlit app, verify these user paths:

1. Upload one valid file and see `1 of 6 verified`.
2. Upload files in a different order and receive the same role assignments.
3. Upload a duplicate HASH and receive an actionable duplicate message.
4. Upload one wrong-date file and remain blocked.
5. Upload all six correct files plus Card Settlement and continue to guided steps.
6. Complete the guided steps and prepare the IIF.
7. Confirm both final downloads appear only after success.
8. Confirm Start Over clears current uploads and Run History remains collapsed.

- [ ] **Step 5: Check the exact staged scope**

Run:

```powershell
git diff --check
git status --short
```

Do not stage unrelated untracked files or inaccessible temporary test folders.

- [ ] **Step 6: Commit final verification corrections**

If verification required corrections, stage only their exact files and commit:

```powershell
git commit -m "fix: complete direct SMS deposit workflow"
```

If no corrections were needed, do not create an empty commit. Stop for user approval before pushing.
