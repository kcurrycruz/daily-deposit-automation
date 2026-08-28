# Closeout Sheet Reconciliation Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional Closeout Sheet reconciliation stage that compares eight recurring controls, posts approved adjustments with exact QuickBooks mappings, supports flexible miscellaneous activity, and requires an explicit final balancing decision.

**Architecture:** A new pure `app/closeout_reconciliation.py` module owns workbook baseline extraction, payload validation, signed adjustment records, and final balancing. Streamlit collects inputs and performs a dry-run `Review Closeout` engine call; the existing engine revalidates the JSON payload, generates the provisional preview, and applies approved lines at explicit IIF ordering boundaries.

**Tech Stack:** Python 3.12+, `Decimal`, `openpyxl`, Streamlit 1.37+, `unittest`, existing QuickBooks IIF generator

**Spec:** `docs/superpowers/specs/2026-08-28-closeout-sheet-workflow-design.md`

## Global Constraints

- Preserve `Finish manually in QuickBooks`; it must generate the current IIF without new Closeout lines.
- Standard rows must remain ordered: Cash, Checks, Donation, Charge (House), Offline Zon, Vendor Coupons, Paid Out, Paid In.
- Employees enter positive face amounts; the application owns QuickBooks signs.
- Offline Zon actual defaults to `$0.00` but remains editable.
- Paid In baseline remains HASH code 34.
- Vendor Coupons must reuse the existing NCG/MFG reconciliation and must not create a duplicate coupon adjustment.
- Payroll accepts only no adjustment, `+$4,000.00`, or `-$4,000.00`.
- The final POS adjustment is never added without explicit approval.
- Custom Closeout TBA and existing unique-account TBA lines remain last.
- Do not change the approved account names or memo text from the specification.
- Use `Decimal` for dollar arithmetic and quantize every persisted/calculated amount to cents.

## File Structure

- Create `app/closeout_reconciliation.py`: pure baseline reading, defaults, standard reconciliation, miscellaneous adjustment validation, final balancing, JSON persistence.
- Create `tests/test_closeout_reconciliation.py`: focused unit and workbook-fixture coverage for the new module.
- Modify `app/pos_to_quickbooks_v2.py`: CLI payload loading, source replacements, adjustment insertion, preview JSON, and final IIF ordering.
- Modify `streamlit_app.py`: optional workflow, stable form state, dry-run review, preview, final approval, and engine command propagation.
- Modify `tests/test_membership_payments.py`: existing engine/IIF integration regression coverage and Streamlit-to-engine argument coverage.
- Modify `README_WEB_APP`: employee-facing explanation of the optional Closeout stage.

---

### Task 1: Read Closeout baselines and build form defaults

**Files:**
- Create: `app/closeout_reconciliation.py`
- Create: `tests/test_closeout_reconciliation.py`

**Interfaces:**
- Produces: `STANDARD_CLOSEOUT_ORDER: tuple[str, ...]`
- Produces: `read_closeout_baselines(workbook_bytes: bytes, bs_sheet_name: str, hash_sheet_name: str) -> dict[str, float]`
- Produces: `default_closeout_actuals(baselines: dict[str, float], coupon_actual_total: float) -> dict[str, float]`
- Consumes: workbook sheet names already detected by `streamlit_app.detect_sheet_roles`

- [ ] **Step 1: Write failing workbook-reader tests**

```python
from io import BytesIO
import openpyxl

from app.closeout_reconciliation import (
    STANDARD_CLOSEOUT_ORDER,
    default_closeout_actuals,
    read_closeout_baselines,
)


def closeout_workbook_bytes():
    workbook = openpyxl.Workbook()
    bs = workbook.active
    bs.title = "082826 BS"
    for code, label, amount in (
        (901, "Cash", 1250.00),
        (902, "Checks", 75.00),
        (1122, "Donation", 20.00),
        (906, "Charge", 45.00),
        (1334, "Offline Zon", -12.00),
        (908, "Vendor Coupons", 188.25),
        (1114, "Paid Out", 47.06),
    ):
        bs.append([code, label, None, None, amount])
    hash_sheet = workbook.create_sheet("082826 Hash")
    hash_sheet.append(["Code", None, None, "Amount"])
    hash_sheet.append([34, "Paid-Ins", None, 30.00])
    content = BytesIO()
    workbook.save(content)
    return content.getvalue()


class CloseoutBaselineTests(unittest.TestCase):
    def test_reads_standard_baselines_in_approved_order(self):
        baselines = read_closeout_baselines(
            closeout_workbook_bytes(), "082826 BS", "082826 Hash"
        )
        self.assertEqual(
            tuple(baselines),
            ("cash", "checks", "donation", "charge_house", "offline_zon",
             "vendor_coupons", "paid_out", "paid_in"),
        )
        self.assertEqual(baselines["offline_zon"], 12.00)
        self.assertEqual(baselines["paid_in"], 30.00)

    def test_defaults_offline_to_zero_and_coupons_to_counted_actual(self):
        baselines = read_closeout_baselines(
            closeout_workbook_bytes(), "082826 BS", "082826 Hash"
        )
        actuals = default_closeout_actuals(baselines, coupon_actual_total=190.00)
        self.assertEqual(actuals["cash"], 1250.00)
        self.assertEqual(actuals["offline_zon"], 0.00)
        self.assertEqual(actuals["vendor_coupons"], 190.00)
```

- [ ] **Step 2: Run tests and verify the missing-module failure**

Run:

```powershell
python -m unittest tests.test_closeout_reconciliation.CloseoutBaselineTests -v
```

Expected: `ModuleNotFoundError: No module named 'app.closeout_reconciliation'`.

- [ ] **Step 3: Implement the reader and defaults**

Implement these constants and functions in `app/closeout_reconciliation.py`:

```python
from collections import OrderedDict
from decimal import Decimal, InvalidOperation
from io import BytesIO
import openpyxl

STANDARD_CLOSEOUT_ORDER = (
    "cash", "checks", "donation", "charge_house", "offline_zon",
    "vendor_coupons", "paid_out", "paid_in",
)

BS_CODE_TO_KEY = {
    901: "cash",
    902: "checks",
    1122: "donation",
    906: "charge_house",
    934: "offline_zon",
    1334: "offline_zon",
    908: "vendor_coupons",
    1114: "paid_out",
}


def _cents(value, label: str) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} must be a valid dollar amount") from None
    if not amount.is_finite():
        raise ValueError(f"{label} must be a valid dollar amount")
    return amount


def read_closeout_baselines(workbook_bytes, bs_sheet_name, hash_sheet_name):
    workbook = openpyxl.load_workbook(
        BytesIO(workbook_bytes), read_only=True, data_only=True
    )
    try:
        if bs_sheet_name not in workbook.sheetnames:
            raise ValueError(f"Balance Sheet tab '{bs_sheet_name}' was not found")
        if hash_sheet_name not in workbook.sheetnames:
            raise ValueError(f"HASH tab '{hash_sheet_name}' was not found")
        values = {key: Decimal("0.00") for key in STANDARD_CLOSEOUT_ORDER}
        for row in workbook[bs_sheet_name].iter_rows(values_only=True):
            try:
                code = int(float(row[0]))
            except (TypeError, ValueError):
                continue
            key = BS_CODE_TO_KEY.get(code)
            if key:
                values[key] = abs(_cents(row[4], key))
        hash_sheet = workbook[hash_sheet_name]
        amount_column = next(
            (
                index for row in hash_sheet.iter_rows(min_row=1, max_row=20, values_only=True)
                for index, value in enumerate(row)
                if str(value or "").strip().casefold() == "amount"
            ),
            None,
        )
        if amount_column is None:
            raise ValueError("HASH Amount column was not found")
        for row in hash_sheet.iter_rows(values_only=True):
            code = None
            for value in row[:4]:
                try:
                    candidate = int(float(value))
                except (TypeError, ValueError):
                    continue
                if candidate == 34:
                    code = candidate
                    break
            if code == 34:
                values["paid_in"] = abs(_cents(row[amount_column], "Paid In"))
        return OrderedDict((key, float(values[key])) for key in STANDARD_CLOSEOUT_ORDER)
    finally:
        workbook.close()


def default_closeout_actuals(baselines, coupon_actual_total):
    actuals = OrderedDict((key, float(_cents(baselines[key], key))) for key in STANDARD_CLOSEOUT_ORDER)
    actuals["offline_zon"] = 0.0
    actuals["vendor_coupons"] = float(abs(_cents(coupon_actual_total, "Vendor Coupons")))
    return actuals
```

Keep the HASH search compatible with the existing parser by allowing the code to appear in the first four columns and using the detected Amount column. Add a second fixture if necessary rather than simplifying this requirement.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m unittest tests.test_closeout_reconciliation.CloseoutBaselineTests -v
```

Expected: both tests pass.

- [ ] **Step 5: Commit**

```powershell
git add app/closeout_reconciliation.py tests/test_closeout_reconciliation.py
git commit -m "Add Closeout baseline reader"
```

---

### Task 2: Calculate the eight standard reconciliation rows

**Files:**
- Modify: `app/closeout_reconciliation.py`
- Modify: `tests/test_closeout_reconciliation.py`

**Interfaces:**
- Consumes: `STANDARD_CLOSEOUT_ORDER`, `_cents`
- Produces: `build_standard_reconciliation(baselines: dict[str, float], actuals: dict[str, float]) -> list[dict]`
- Each record contains: `key`, `label`, `baseline`, `actual`, `difference`, `detail_qb_effect`, `adjustment_account`, `adjustment_memo`, `adjustment_qb_effect`, `managed_externally`

- [ ] **Step 1: Write failing sign, memo, and ordering tests**

```python
class StandardReconciliationTests(unittest.TestCase):
    def test_builds_rows_in_order_with_category_aware_effects(self):
        baselines = {
            "cash": 100.00, "checks": 50.00, "donation": 20.00,
            "charge_house": 10.00, "offline_zon": 12.00,
            "vendor_coupons": 181.50, "paid_out": 40.00, "paid_in": 30.00,
        }
        actuals = {
            "cash": 105.00, "checks": 45.00, "donation": 25.00,
            "charge_house": 8.00, "offline_zon": 0.00,
            "vendor_coupons": 188.25, "paid_out": 50.00, "paid_in": 35.00,
        }
        rows = build_standard_reconciliation(baselines, actuals)
        self.assertEqual([row["key"] for row in rows], list(STANDARD_CLOSEOUT_ORDER))
        by_key = {row["key"]: row for row in rows}
        self.assertEqual(by_key["cash"]["adjustment_qb_effect"], 5.00)
        self.assertEqual(by_key["donation"]["detail_qb_effect"], -25.00)
        self.assertEqual(by_key["donation"]["adjustment_qb_effect"], 5.00)
        self.assertEqual(by_key["paid_in"]["detail_qb_effect"], 35.00)
        self.assertEqual(by_key["paid_in"]["adjustment_qb_effect"], -5.00)
        self.assertTrue(by_key["vendor_coupons"]["managed_externally"])
        self.assertEqual(
            by_key["checks"]["adjustment_memo"],
            "Over/Short per Closeout Sheet - Check",
        )

    def test_rejects_negative_or_missing_standard_actuals(self):
        baselines = {key: 0 for key in STANDARD_CLOSEOUT_ORDER}
        for key in STANDARD_CLOSEOUT_ORDER:
            bad_actuals = {item: 0 for item in STANDARD_CLOSEOUT_ORDER}
            bad_actuals[key] = -0.01
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, "zero or greater"):
                    build_standard_reconciliation(baselines, bad_actuals)
```

- [ ] **Step 2: Run the tests and verify the missing-function failure**

```powershell
python -m unittest tests.test_closeout_reconciliation.StandardReconciliationTests -v
```

Expected: import failure for `build_standard_reconciliation`.

- [ ] **Step 3: Implement ordered metadata and calculation**

Add exact labels, memos, and detail directions:

```python
STANDARD_METADATA = OrderedDict([
    ("cash", {"label": "Cash", "memo": "Over/Short per Closeout Sheet - Cash", "detail_direction": None}),
    ("checks", {"label": "Checks", "memo": "Over/Short per Closeout Sheet - Check", "detail_direction": None}),
    ("donation", {"label": "Donation", "memo": "Over/Short per Closeout Sheet - Donation", "detail_direction": -1}),
    ("charge_house", {"label": "Charge (House)", "memo": "Over/Short per Closeout Sheet - Charge (House)", "detail_direction": -1}),
    ("offline_zon", {"label": "Offline Zon", "memo": "Over/Short per Closeout Sheet - Offline Zon", "detail_direction": -1}),
    ("vendor_coupons", {"label": "Vendor Coupons", "memo": "Over/Short per Closeout Sheet - Coupon", "detail_direction": -1, "managed_externally": True}),
    ("paid_out", {"label": "Paid Out", "memo": "Over/Short per Closeout Sheet - Paid Out", "detail_direction": -1}),
    ("paid_in", {"label": "Paid In", "memo": "Over/Short per Closeout Sheet - Paid In", "detail_direction": 1}),
])


def build_standard_reconciliation(baselines, actuals):
    rows = []
    for key, metadata in STANDARD_METADATA.items():
        if key not in baselines or key not in actuals:
            raise ValueError(f"Closeout {metadata['label']} is missing")
        baseline = abs(_cents(baselines[key], metadata["label"]))
        actual = _cents(actuals[key], metadata["label"])
        if actual < 0:
            raise ValueError(f"{metadata['label']} must be zero or greater")
        difference = (actual - baseline).quantize(Decimal("0.01"))
        direction = metadata.get("detail_direction")
        detail_effect = None if direction is None else (actual * direction)
        adjustment_effect = (
            difference
            if direction is None
            else (baseline * direction - actual * direction)
        ).quantize(Decimal("0.01"))
        rows.append({
            "key": key,
            "label": metadata["label"],
            "baseline": float(baseline),
            "actual": float(actual),
            "difference": float(difference),
            "detail_qb_effect": None if detail_effect is None else float(detail_effect),
            "adjustment_account": "8314000 · FE - Cash Over/Shorts",
            "adjustment_memo": metadata["memo"],
            "adjustment_qb_effect": float(adjustment_effect),
            "managed_externally": bool(metadata.get("managed_externally")),
        })
    return rows
```

- [ ] **Step 4: Run focused tests**

```powershell
python -m unittest tests.test_closeout_reconciliation.StandardReconciliationTests -v
```

Expected: all standard reconciliation tests pass.

- [ ] **Step 5: Commit**

```powershell
git add app/closeout_reconciliation.py tests/test_closeout_reconciliation.py
git commit -m "Calculate Closeout standard differences"
```

---

### Task 3: Validate miscellaneous adjustments, JSON payloads, and final balancing

**Files:**
- Modify: `app/closeout_reconciliation.py`
- Modify: `tests/test_closeout_reconciliation.py`

**Interfaces:**
- Produces: `normalize_closeout_payload(payload: dict) -> dict`
- Produces: `build_misc_adjustments(payload: dict) -> list[dict]`
- Produces: `calculate_final_pos_adjustment(provisional_total: float, final_total: float, approved: bool) -> dict`
- Produces: `write_closeout_payload_file(folder: Path, payload: dict) -> Path`
- Produces: `load_closeout_payload_file(path: str | Path) -> dict`
- Adjustment records contain: `kind`, `account`, `memo`, `qb_effect`, `iif_amount`

- [ ] **Step 1: Write failing preset, TBA, balance, and persistence tests**

```python
class CloseoutAdjustmentTests(unittest.TestCase):
    def test_builds_exact_approved_misc_adjustments(self):
        payload = {
            "payroll": -4000,
            "safe": {"type": "overage", "amount": 25},
            "plants_purchase": 60,
            "custom_tba": [
                {"memo": "Unusual Closeout item", "amount": 12, "direction": "removes"}
            ],
        }
        rows = build_misc_adjustments(payload)
        self.assertEqual(
            [(row["account"], row["memo"], row["qb_effect"]) for row in rows],
            [
                ("1140000 · Cash Drawers/Safe", "Payroll - Check Cashing", -4000.00),
                ("8314000 · FE - Cash Over/Shorts", "Safe Overage Cash added to deposit", 25.00),
                ("1130000 · Petty Cash", "Plants Dept - Market Purchases", -60.00),
                ("4444 · TBA Purchases", "Unusual Closeout item", -12.00),
            ],
        )
        self.assertEqual([row["iif_amount"] for row in rows], [4000.0, -25.0, 60.0, 12.0])

    def test_rejects_unapproved_payroll_and_incomplete_custom_tba(self):
        with self.assertRaisesRegex(ValueError, "Payroll"):
            build_misc_adjustments({"payroll": 3999, "custom_tba": []})
        with self.assertRaisesRegex(ValueError, "memo"):
            build_misc_adjustments({
                "payroll": 0,
                "custom_tba": [{"memo": "", "amount": 5, "direction": "adds"}],
            })

    def test_final_difference_requires_explicit_approval(self):
        preview = calculate_final_pos_adjustment(1000, 1025, approved=False)
        self.assertEqual(preview["remaining"], 25.00)
        self.assertIsNone(preview["line"])
        approved = calculate_final_pos_adjustment(1000, 1025, approved=True)
        self.assertEqual(approved["line"]["qb_effect"], 25.00)
        self.assertEqual(approved["line"]["iif_amount"], -25.00)
        self.assertEqual(
            approved["line"]["memo"], "Over/Short per POS (to = POS total)"
        )

    def test_payload_round_trips_through_unique_json_file(self):
        payload = {
            "mode": "closeout",
            "reviewed": True,
            "actuals": {key: 10 for key in STANDARD_CLOSEOUT_ORDER},
            "payroll": 0,
            "safe": {"type": "none", "amount": 0},
            "plants_purchase": 0,
            "custom_tba": [],
            "final_total": 1000,
            "approve_final_pos": False,
        }
        with tempfile.TemporaryDirectory() as folder:
            path = write_closeout_payload_file(Path(folder), payload)
            self.assertEqual(load_closeout_payload_file(path), normalize_closeout_payload(payload))
```

- [ ] **Step 2: Run focused tests and verify missing functions**

```powershell
python -m unittest tests.test_closeout_reconciliation.CloseoutAdjustmentTests -v
```

Expected: import failures for the new adjustment functions.

- [ ] **Step 3: Implement exact mappings and validation**

Implement `build_misc_adjustments` with these immutable mappings:

```python
PAYROLL_VALUES = {Decimal("-4000.00"), Decimal("0.00"), Decimal("4000.00")}


def _adjustment(kind, account, memo, qb_effect):
    effect = _cents(qb_effect, memo)
    return {
        "kind": kind,
        "account": account,
        "memo": memo,
        "qb_effect": float(effect),
        "iif_amount": float(-effect),
    }
```

Rules:

- Omit zero/disabled presets.
- Map Safe `overage` to positive and `shortage` to negative.
- Require Safe/Plants/custom magnitudes greater than zero when enabled.
- Require custom direction exactly `adds` or `removes`.
- Strip custom memos and reject blank memos.
- Preserve custom TBA input order.

Implement final balancing exactly as:

```python
def calculate_final_pos_adjustment(provisional_total, final_total, approved):
    provisional = _cents(provisional_total, "Generated deposit")
    final = _cents(final_total, "Final Closeout Sheet Deposit Total")
    if final <= 0:
        raise ValueError("Final Closeout Sheet Deposit Total must be greater than zero")
    remaining = (final - provisional).quantize(Decimal("0.01"))
    line = None
    if remaining and approved:
        line = _adjustment(
            "final_pos",
            "8314000 · FE - Cash Over/Shorts",
            "Over/Short per POS (to = POS total)",
            remaining,
        )
    return {"provisional_total": float(provisional), "final_total": float(final),
            "remaining": float(remaining), "line": line,
            "requires_approval": bool(remaining and not approved)}
```

`normalize_closeout_payload` must return mode `manual` unchanged or validate in-app mode fields: `reviewed is True`, all eight actuals present, valid presets/custom rows, positive final total, and boolean `approve_final_pos`.

Persistence uses `json.dumps(payload, indent=2)` and a UUID filename `closeout_<uuid>.json`; write only inside the supplied runtime folder.

- [ ] **Step 4: Run focused tests**

```powershell
python -m unittest tests.test_closeout_reconciliation.CloseoutAdjustmentTests -v
```

Expected: all adjustment tests pass.

- [ ] **Step 5: Commit**

```powershell
git add app/closeout_reconciliation.py tests/test_closeout_reconciliation.py
git commit -m "Validate Closeout adjustments and balancing"
```

---

### Task 4: Integrate Closeout records into IIF generation

**Files:**
- Modify: `app/pos_to_quickbooks_v2.py:1019-1380`
- Modify: `tests/test_membership_payments.py`

**Interfaces:**
- Consumes: `normalize_closeout_payload`, `build_standard_reconciliation`, `build_misc_adjustments`, `calculate_final_pos_adjustment`
- Extends the existing `generate_iif` signature with `closeout_payload: dict | None = None` and `closeout_preview_path: Path | None = None`; its return type remains `Path`.
- Produces preview JSON: `standard_rows`, `misc_rows`, `provisional_total`, `final_total`, `remaining`, `requires_approval`, `final_pos_line`

- [ ] **Step 1: Write failing IIF integration tests**

Add a new test beside the existing coupon integration test. Use a hand-calculated fixture:

```python
def test_generate_iif_applies_closeout_actuals_memos_signs_and_order(self):
    payload = {
        "mode": "closeout",
        "reviewed": True,
        "actuals": {
            "cash": 110, "checks": 45, "donation": 25, "charge_house": 8,
            "offline_zon": 0, "vendor_coupons": 188.25,
            "paid_out": 50, "paid_in": 35,
        },
        "payroll": -4000,
        "safe": {"type": "shortage", "amount": 10},
        "plants_purchase": 20,
        "custom_tba": [{"memo": "Other paper item", "amount": 5, "direction": "adds"}],
        "final_total": 5000,
        "approve_final_pos": True,
    }
    # Generate with BS cash=100, check=50, donation=20, charge=10,
    # offline=12, coupons=181.50, paid_out=40, HASH paid_in=30.
    text, preview = generate_closeout_fixture(payload)
    self.assertIn("Over/Short per Closeout Sheet - Cash", text)
    self.assertIn("Over/Short per Closeout Sheet - Check", text)
    self.assertIn("Over/Short per Closeout Sheet - Donation", text)
    self.assertIn("Over/Short per Closeout Sheet - Charge (House)", text)
    self.assertIn("Over/Short per Closeout Sheet - Offline Zon", text)
    self.assertEqual(text.count("Over/Short per Closeout Sheet - Coupon"), 1)
    self.assertIn("Over/Short per Closeout Sheet - Paid Out", text)
    self.assertIn("Over/Short per Closeout Sheet - Paid In", text)
    self.assertIn("1140000 · Cash Drawers/Safe", text)
    self.assertIn("1130000 · Petty Cash", text)
    self.assertLess(text.index("Over/Short per POS"), text.index("Other paper item"))
    self.assertEqual(preview["remaining_after_approval"], 0.0)


def test_generate_iif_manual_closeout_mode_is_byte_equivalent_to_legacy(self):
    legacy = generate_closeout_fixture(None)[0]
    manual = generate_closeout_fixture({"mode": "manual"})[0]
    self.assertEqual(manual, legacy)
```

The helper must call the real `generate_iif` with a temporary output directory and read the real preview JSON; do not mock `spl` or IIF generation.

- [ ] **Step 2: Run the two integration tests and verify failure**

```powershell
python -m unittest \
  tests.test_membership_payments.MembershipPaymentTests.test_generate_iif_applies_closeout_actuals_memos_signs_and_order \
  tests.test_membership_payments.MembershipPaymentTests.test_generate_iif_manual_closeout_mode_is_byte_equivalent_to_legacy -v
```

Expected: `TypeError` because `generate_iif` does not accept `closeout_payload`.

- [ ] **Step 3: Apply actual values to existing source lines**

Inside `generate_iif`:

1. Normalize the payload; default missing/`manual` to legacy behavior.
2. Build standard rows from BS/HASH baselines and payload actuals.
3. Override only the relevant sources in in-app mode:
   - Donation: `actual donation + unchanged HASH pass-through`
   - Charge House: Closeout actual
   - Offline Zon: Closeout actual
   - Vendor Coupons: leave existing NCG/MFG detail unchanged and require its total equals Closeout Vendor Coupon actual
   - Paid Out: Closeout actual
   - Paid In: Closeout actual
4. Cash and Checks remain difference-only because they have no separate SPL detail lines.

Use a lookup such as:

```python
closeout_rows_by_key = {row["key"]: row for row in closeout_rows}

def closeout_actual(key, legacy_value):
    row = closeout_rows_by_key.get(key)
    return row["actual"] if row else legacy_value
```

- [ ] **Step 4: Insert standard and preset lines without duplicating Coupon**

Replace the standalone coupon-difference append block with one ordered loop over standard records. When `managed_externally` is true for Vendor Coupons, use the already calculated coupon reconciliation line at that position instead of creating a second line.

For every nonzero `adjustment_qb_effect`, append:

```python
iif_amount = -row["adjustment_qb_effect"]
spl_total += iif_amount
spls.append(spl(date_str, row["adjustment_account"], "", iif_amount,
                row["adjustment_memo"], "Admin"))
```

Append Payroll, Safe, and Plants records next. Hold custom Closeout TBA records and existing miscellaneous/unique TBA records in a pending list instead of appending them immediately.

- [ ] **Step 5: Calculate the provisional total and explicit final POS line**

Calculate the provisional deposit including the pending TBA effects even though those lines will be appended last:

```python
pending_tba_iif_total = sum(Decimal(str(row["iif_amount"])) for row in pending_tba_rows)
provisional_total = -(
    Decimal(str(spl_total)) + pending_tba_iif_total
).quantize(Decimal("0.01"))
final_balance = calculate_final_pos_adjustment(
    provisional_total,
    closeout_payload["final_total"],
    closeout_payload["approve_final_pos"],
)
```

Append the approved final POS line before appending pending TBA lines. If a nonzero remaining difference is not approved, omit the line, set `requires_approval=True` in preview JSON, and allow preview generation to finish; final UI validation will prevent download/archive.

Write preview JSON atomically to `closeout_preview_path` when supplied.

- [ ] **Step 6: Run integration tests**

```powershell
python -m unittest \
  tests.test_membership_payments.MembershipPaymentTests.test_generate_iif_applies_closeout_actuals_memos_signs_and_order \
  tests.test_membership_payments.MembershipPaymentTests.test_generate_iif_manual_closeout_mode_is_byte_equivalent_to_legacy \
  tests.test_membership_payments.MembershipPaymentTests.test_generate_iif_writes_coupon_closeout_breakdown_and_signed_difference -v
```

Expected: all three pass, proving new behavior and coupon compatibility.

- [ ] **Step 7: Commit**

```powershell
git add app/pos_to_quickbooks_v2.py tests/test_membership_payments.py
git commit -m "Apply Closeout reconciliation to IIF"
```

---

### Task 5: Add Closeout JSON CLI and dry-run preview transport

**Files:**
- Modify: `app/pos_to_quickbooks_v2.py:1588-1760`
- Modify: `streamlit_app.py:1273-1345`
- Modify: `tests/test_membership_payments.py`

**Interfaces:**
- CLI consumes: `--closeout-file <json path>` and `--closeout-preview-output <json path>`
- Extends the existing `run_engine` signature with `closeout_payload: dict | None` and `preview_only: bool = False`; its return type remains `dict`.
- Result adds: `closeout_preview: dict | None`, `preview_only: bool`

- [ ] **Step 1: Write failing command-propagation tests**

Add a pure command builder in `streamlit_app.py` so command construction can be tested without mocking subprocess:

```python
def test_build_engine_command_passes_closeout_files(self):
    command = build_engine_command(
        engine_path=Path("engine.py"),
        deposit_date=date(2026, 8, 28),
        membership_path=Path("members.json"),
        membership_mode="automatic",
        coupon_mode="closeout",
        coupon_closeout_total=188.25,
        coupon_ncg_total=152.25,
        coupon_mfg_total=36.00,
        closeout_path=Path("closeout.json"),
        closeout_preview_path=Path("preview.json"),
    )
    self.assertIn("--closeout-file", command)
    self.assertIn("closeout.json", command)
    self.assertIn("--closeout-preview-output", command)
    self.assertIn("preview.json", command)
```

Also add a CLI parser integration test that calls the real engine module with a malformed Closeout file and asserts the specific validation error is emitted rather than silently ignored.

- [ ] **Step 2: Run tests and verify missing interface failures**

```powershell
python -m unittest \
  tests.test_membership_payments.MembershipPaymentTests.test_build_engine_command_passes_closeout_files \
  tests.test_membership_payments.MembershipPaymentTests.test_engine_rejects_malformed_closeout_payload -v
```

Expected: missing `build_engine_command`/CLI arguments.

- [ ] **Step 3: Implement CLI loading and propagation**

Add arguments:

```python
parser.add_argument("--closeout-file", help="Validated Closeout Sheet JSON payload")
parser.add_argument("--closeout-preview-output", help="Path for Closeout preview JSON")
```

Load with `load_closeout_payload_file`, pass the payload and preview path into `generate_iif`, and preserve `None` when no file is supplied.

Extract `build_engine_command` from `run_engine`; it must retain all current membership and coupon flags and append Closeout flags only when paths are supplied.

- [ ] **Step 4: Implement Streamlit runtime file lifecycle**

`run_engine` writes a unique normalized Closeout payload using `write_closeout_payload_file`, allocates `RUNTIME_TEMP_DIR / f"closeout_preview_{uuid4().hex}.json"`, executes the engine, reads preview JSON, and deletes both temporary files in `finally`.

For `preview_only=True`, return the preview and logs but do not archive the run or expose the IIF download. For final execution, require preview `remaining_after_approval == 0.0` and `requires_approval is False`; otherwise raise a clear `ValueError`.

- [ ] **Step 5: Run transport tests**

```powershell
python -m unittest \
  tests.test_membership_payments.MembershipPaymentTests.test_build_engine_command_passes_closeout_files \
  tests.test_membership_payments.MembershipPaymentTests.test_engine_rejects_malformed_closeout_payload -v
```

Expected: both pass.

- [ ] **Step 6: Commit**

```powershell
git add app/pos_to_quickbooks_v2.py streamlit_app.py tests/test_membership_payments.py
git commit -m "Transport Closeout payload through engine"
```

---

### Task 6: Build the guided Streamlit Closeout workflow

**Files:**
- Modify: `streamlit_app.py:1945-2450`
- Modify: `tests/test_membership_payments.py`

**Interfaces:**
- Consumes: `read_closeout_baselines`, `default_closeout_actuals`, `normalize_closeout_payload`
- Consumes the extended `run_engine` with the Closeout payload and `preview_only=True`.
- Produces session state: `closeout_payload_<workbook key>`, `closeout_preview_<workbook key>`

- [ ] **Step 1: Write failing form-state and validation tests**

Test a pure helper `build_closeout_form_payload` rather than Streamlit widgets:

```python
def test_closeout_form_payload_preserves_order_defaults_and_confirmation(self):
    payload = build_closeout_form_payload(
        baselines={key: 10 for key in STANDARD_CLOSEOUT_ORDER},
        actuals={**{key: 10 for key in STANDARD_CLOSEOUT_ORDER}, "offline_zon": 0},
        reviewed=True,
        payroll=-4000,
        safe_type="shortage",
        safe_amount=25,
        plants_purchase=40,
        custom_tba=[{"memo": "Other", "amount": 3, "direction": "adds"}],
        final_total=1000,
        approve_final_pos=False,
    )
    self.assertEqual(list(payload["actuals"]), list(STANDARD_CLOSEOUT_ORDER))
    self.assertEqual(payload["payroll"], -4000.0)
    self.assertEqual(payload["safe"], {"type": "shortage", "amount": 25.0})


def test_closeout_form_requires_paper_review_confirmation(self):
    with self.assertRaisesRegex(ValueError, "paper Closeout Sheet"):
        build_closeout_form_payload(
            baselines={key: 10 for key in STANDARD_CLOSEOUT_ORDER},
            actuals={key: 10 for key in STANDARD_CLOSEOUT_ORDER},
            reviewed=False,
            payroll=0,
            safe_type="none",
            safe_amount=0,
            plants_purchase=0,
            custom_tba=[],
            final_total=1000,
            approve_final_pos=False,
        )
```

- [ ] **Step 2: Run tests and verify missing-helper failure**

```powershell
python -m unittest \
  tests.test_membership_payments.MembershipPaymentTests.test_closeout_form_payload_preserves_order_defaults_and_confirmation \
  tests.test_membership_payments.MembershipPaymentTests.test_closeout_form_requires_paper_review_confirmation -v
```

Expected: import failure for `build_closeout_form_payload`.

- [ ] **Step 3: Implement the pure form-payload helper**

Add the helper to `app/closeout_reconciliation.py`. It assembles the exact normalized payload keys and delegates final validation to `normalize_closeout_payload`; it contains no Streamlit imports.

- [ ] **Step 4: Add optional handling choice and eight-row UI**

In `streamlit_app.py`, after the coupon workflow and before card settlement validation:

1. Display `Reconcile using Closeout Sheet` and `Finish manually in QuickBooks` with no default selection.
2. In manual mode, set `closeout_payload={"mode": "manual"}` and preserve current behavior.
3. In in-app mode, read baselines from uploaded workbook roles.
4. Render positive number inputs in `STANDARD_CLOSEOUT_ORDER` with System/BS, Actual, Difference, and Matched/Review status.
5. Lock Vendor Coupon actual to the existing `coupon_ncg_total + coupon_mfg_total` result.
6. Default Offline Zon to zero and other actuals as defined by `default_closeout_actuals`.
7. Require the paper-review checkbox.

Use a workbook-derived stable key so uploading another workbook or selecting Run Another Deposit clears stale Closeout inputs.

- [ ] **Step 5: Add preset and custom adjustment UI**

Render:

- Payroll selectbox: `None`, `+$4,000`, `-$4,000`.
- Safe type selectbox and positive amount enabled only for Overage/Shortage.
- Positive Plants purchase input.
- Add/remove custom TBA rows with memo, amount, and Adds/Removes direction.
- Positive Final Closeout Sheet Deposit Total.

The UI must never expose raw IIF signs.

- [ ] **Step 6: Add Review Closeout dry run and final approval**

Add a distinct secondary `Review Closeout` button. It runs the extended `run_engine` with `preview_only=True`, stores the returned preview, and displays:

- Eight standard rows
- Generated account/memo/effect rows
- Provisional deposit total
- Final Closeout total
- Remaining difference

If the remaining amount is nonzero, render `Add final POS adjustment` unchecked. Changing any Closeout input invalidates the saved preview. The primary `Validate & Build Deposit` button is enabled only when a fresh preview exists, all validation passes, and either remaining is zero or explicit final approval is checked.

- [ ] **Step 7: Run focused tests and compile**

```powershell
python -m unittest \
  tests.test_membership_payments.MembershipPaymentTests.test_closeout_form_payload_preserves_order_defaults_and_confirmation \
  tests.test_membership_payments.MembershipPaymentTests.test_closeout_form_requires_paper_review_confirmation \
  tests.test_membership_payments.MembershipPaymentTests.test_app_passes_coupon_closeout_values_to_engine -v
python -m py_compile streamlit_app.py app/closeout_reconciliation.py
```

Expected: tests pass and compilation exits zero.

- [ ] **Step 8: Perform local visual smoke test**

Run:

```powershell
python -m streamlit run streamlit_app.py
```

Verify with a fixture workbook:

- Exact eight-row order
- Offline Zon starts at zero
- Vendor Coupons is linked to NCG/MFG
- Positive-only standard inputs
- Preset signs are described in plain language
- Review Closeout reveals exact remaining amount
- Final build stays disabled until approval
- Manual mode hides all new inputs

- [ ] **Step 9: Commit**

```powershell
git add app/closeout_reconciliation.py streamlit_app.py tests/test_membership_payments.py
git commit -m "Add guided Closeout Sheet workflow"
```

---

### Task 7: Complete regression, documentation, and deployment checks

**Files:**
- Modify: `README_WEB_APP`
- Modify: `tests/test_membership_payments.py` only if a real uncovered regression is found

**Interfaces:**
- Consumes all prior interfaces
- Produces no new runtime interface

- [ ] **Step 1: Add employee-facing documentation**

Document:

- The optional workflow choice
- Positive actual-entry rule
- Eight recurring categories
- Payroll/Safe/Plants presets
- TBA correction requirement
- Review Closeout dry run
- Explicit last-resort approval
- Manual QuickBooks fallback

- [ ] **Step 2: Run the full suite**

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

Expected: all tests pass with zero failures/errors.

- [ ] **Step 3: Run syntax and diff verification**

```powershell
python -m py_compile streamlit_app.py app/closeout_reconciliation.py app/pos_to_quickbooks_v2.py
git diff --check
git status --short
```

Expected: compilation and diff check exit zero; status contains only intended files.

- [ ] **Step 4: Verify manual-mode compatibility and ordering fixtures again**

```powershell
python -m unittest \
  tests.test_membership_payments.MembershipPaymentTests.test_generate_iif_manual_closeout_mode_is_byte_equivalent_to_legacy \
  tests.test_membership_payments.MembershipPaymentTests.test_generate_iif_applies_closeout_actuals_memos_signs_and_order \
  tests.test_membership_payments.MembershipPaymentTests.test_generate_iif_writes_coupon_closeout_breakdown_and_signed_difference -v
```

Expected: all compatibility and ordering tests pass.

- [ ] **Step 5: Commit final documentation or regression changes**

```powershell
git add README_WEB_APP tests/test_membership_payments.py
git commit -m "Document Closeout reconciliation workflow"
```

Skip this commit only when Task 7 produces no file changes; do not create an empty commit.
