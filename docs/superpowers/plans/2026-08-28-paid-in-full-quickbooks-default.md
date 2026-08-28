# Paid-in-Full QuickBooks Default Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When an employee changes the membership Payment Option to `Paid in full — $100`, default the QuickBooks-name answer to `No`, clear and disable the name field, and preserve the employee's ability to deliberately change the answer to `Yes` and enter the exact QuickBooks name.

**Architecture:** Add one pure transition helper to `app/membership_payments.py` and invoke it before Streamlit instantiates the QuickBooks-name widgets. Track the prior Payment Option in the existing workbook- and entry-version-scoped session-state namespace so the default runs once on entry into paid-in-full, not on every Streamlit rerun.

**Tech Stack:** Python 3.12+, Streamlit 1.37+, `unittest`

**Related spec:** `docs/superpowers/specs/2026-08-28-closeout-sheet-workflow-design.md` (separate approved UI refinement recorded in the specification's scope notes)

## Constraints

- The Paid-in-Full amount remains locked at `$100.00` and Member # remains not required.
- Entering Paid-in-Full from another option sets `In QuickBooks?` to `No` and clears any stale name.
- Rerunning while Paid-in-Full remains selected must not overwrite a deliberate change to `Yes` or erase the exact name.
- Leaving Paid-in-Full for another Payment Option resets the paid-in-full default to no answer and a blank name.
- Existing membership validation and generated QuickBooks lines must remain unchanged.

---

### Task 1: Add and test the Payment Option transition helper

**Files:**
- Modify: `app/membership_payments.py:40-90`
- Modify: `tests/test_membership_payments.py:400-610`

**Interfaces:**
- Produces: `quickbooks_name_state_for_payment_option(payment_option: str, previous_option: str | None, current_status: str | None, current_name: str) -> tuple[str | None, str]`
- Consumes: exact `Paid in full — $100` key from `PAYMENT_OPTIONS`

- [ ] **Step 1: Write failing transition tests**

Add these focused tests alongside the existing Payment Option tests:

```python
def test_entering_paid_in_full_defaults_quickbooks_name_to_no(self):
    self.assertEqual(
        quickbooks_name_state_for_payment_option(
            payment_option="Paid in full — $100",
            previous_option="Existing plan — 1 year",
            current_status="Yes",
            current_name="Karl Chester Cruz",
        ),
        ("No", ""),
    )


def test_paid_in_full_rerun_preserves_deliberate_yes_and_name(self):
    self.assertEqual(
        quickbooks_name_state_for_payment_option(
            payment_option="Paid in full — $100",
            previous_option="Paid in full — $100",
            current_status="Yes",
            current_name="Karl Chester Cruz",
        ),
        ("Yes", "Karl Chester Cruz"),
    )


def test_non_paid_in_full_option_does_not_apply_a_quickbooks_default(self):
    self.assertEqual(
        quickbooks_name_state_for_payment_option(
            payment_option="Existing plan — 1 year",
            previous_option="Existing plan — 1 year",
            current_status=None,
            current_name="",
        ),
        (None, ""),
    )


def test_leaving_paid_in_full_clears_its_new_member_default(self):
    self.assertEqual(
        quickbooks_name_state_for_payment_option(
            payment_option="Existing plan — 1 year",
            previous_option="Paid in full — $100",
            current_status="No",
            current_name="",
        ),
        (None, ""),
    )
```

- [ ] **Step 2: Run the tests and verify the missing-helper failure**

```powershell
python -m unittest \
  tests.test_membership_payments.MembershipPaymentTests.test_entering_paid_in_full_defaults_quickbooks_name_to_no \
  tests.test_membership_payments.MembershipPaymentTests.test_paid_in_full_rerun_preserves_deliberate_yes_and_name \
  tests.test_membership_payments.MembershipPaymentTests.test_non_paid_in_full_option_does_not_apply_a_quickbooks_default \
  tests.test_membership_payments.MembershipPaymentTests.test_leaving_paid_in_full_clears_its_new_member_default -v
```

Expected: import failure for `quickbooks_name_state_for_payment_option`.

- [ ] **Step 3: Implement the minimal pure helper**

Add this directly after `payment_fields_from_option`:

```python
def quickbooks_name_state_for_payment_option(
    payment_option: str,
    previous_option: str | None,
    current_status: str | None,
    current_name: str,
) -> tuple[str | None, str]:
    payment_fields_from_option(payment_option)
    if (
        payment_option == "Paid in full — $100"
        and previous_option != payment_option
    ):
        return "No", ""
    if (
        payment_option != "Paid in full — $100"
        and previous_option == "Paid in full — $100"
    ):
        return None, ""
    return current_status, str(current_name or "").strip()
```

Calling `payment_fields_from_option` keeps unknown-option validation aligned with the rest of the membership module.

- [ ] **Step 4: Run focused tests**

```powershell
python -m unittest \
  tests.test_membership_payments.MembershipPaymentTests.test_entering_paid_in_full_defaults_quickbooks_name_to_no \
  tests.test_membership_payments.MembershipPaymentTests.test_paid_in_full_rerun_preserves_deliberate_yes_and_name \
  tests.test_membership_payments.MembershipPaymentTests.test_non_paid_in_full_option_does_not_apply_a_quickbooks_default \
  tests.test_membership_payments.MembershipPaymentTests.test_leaving_paid_in_full_clears_its_new_member_default -v
```

Expected: all four tests pass.

- [ ] **Step 5: Commit**

```powershell
git add app/membership_payments.py tests/test_membership_payments.py
git commit -m "Default paid-in-full names to new members"
```

---

### Task 2: Apply the one-time default before Streamlit creates the widgets

**Files:**
- Modify: `streamlit_app.py:2055-2105`
- Modify: `tests/test_membership_payments.py`

**Interfaces:**
- Consumes: `quickbooks_name_state_for_payment_option`
- Uses session keys: `<entry_key>_previous_payment_option`, `<entry_key>_quickbooks_name_status`, `<entry_key>_member_name`

- [ ] **Step 1: Add a failing source-wiring regression test**

Use the existing source-based Streamlit regression style in `tests/test_membership_payments.py` and assert that:

```python
source = Path("streamlit_app.py").read_text(encoding="utf-8")
helper_call = source.index("quickbooks_name_status, saved_quickbooks_name = (")
radio_call = source.index('"Does this member already exist in QuickBooks?"')
self.assertLess(helper_call, radio_call)
self.assertIn('f"{entry_key}_previous_payment_option"', source)
```

This protects the Streamlit rule that widget state must be updated before the widget with that key is instantiated.

- [ ] **Step 2: Run the wiring test and verify failure**

```powershell
python -m unittest tests.test_membership_payments.MembershipPaymentTests.test_paid_in_full_default_is_applied_before_quickbooks_widget -v
```

Expected: failure because the helper is not wired into `streamlit_app.py`.

- [ ] **Step 3: Wire the helper into the entry form**

Import `quickbooks_name_state_for_payment_option` with the existing membership helpers. Immediately after the Payment Option selectbox and before the QuickBooks radio/text widgets:

```python
previous_option_key = f"{entry_key}_previous_payment_option"
quickbooks_status_key = f"{entry_key}_quickbooks_name_status"
quickbooks_name_key = f"{entry_key}_member_name"
quickbooks_name_status, saved_quickbooks_name = (
    quickbooks_name_state_for_payment_option(
        payment_option=payment_option,
        previous_option=st.session_state.get(previous_option_key),
        current_status=st.session_state.get(quickbooks_status_key),
        current_name=st.session_state.get(quickbooks_name_key, ""),
    )
)
st.session_state[quickbooks_status_key] = quickbooks_name_status
st.session_state[quickbooks_name_key] = saved_quickbooks_name
st.session_state[previous_option_key] = payment_option
```

Then retain the existing popover behavior:

- `No` shows the new-member caption, does not instantiate the name text input, and passes a blank QuickBooks NAME.
- `Yes` enables the exact-name text input.
- A non-paid-in-full option with no previous answer still shows neither choice selected.

Do not write to either widget key after its widget has been instantiated in the current rerun.

- [ ] **Step 4: Run focused membership tests and compile**

```powershell
python -m unittest \
  tests.test_membership_payments.MembershipPaymentTests.test_paid_in_full_default_is_applied_before_quickbooks_widget \
  tests.test_membership_payments.MembershipPaymentTests.test_entering_paid_in_full_defaults_quickbooks_name_to_no \
  tests.test_membership_payments.MembershipPaymentTests.test_paid_in_full_rerun_preserves_deliberate_yes_and_name \
  tests.test_membership_payments.MembershipPaymentTests.test_combined_payment_option_prevents_a_plan_for_paid_in_full -v
python -m py_compile streamlit_app.py app/membership_payments.py
git diff --check
```

Expected: all tests pass; compilation and diff check exit zero.

- [ ] **Step 5: Run the full regression suite**

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

Expected: all tests pass with zero failures/errors.

- [ ] **Step 6: Commit**

```powershell
git add streamlit_app.py tests/test_membership_payments.py
git commit -m "Apply paid-in-full QuickBooks default in UI"
```
