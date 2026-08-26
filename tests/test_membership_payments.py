import unittest


class MembershipPaymentTests(unittest.TestCase):
    def test_pending_member_number_rejects_a_typed_number(self):
        from app.membership_payments import build_membership_lines

        with self.assertRaisesRegex(
            ValueError,
            "Enter a member number or select Member # pending, not both",
        ):
            build_membership_lines([{
                "member_name": "New Member",
                "member_number": "12345",
                "member_number_pending": True,
                "payment_type": "Existing plan",
                "plan": "1 year",
                "amount": 8.45,
            }])

    def test_pending_member_number_uses_pending_memo(self):
        from app.membership_payments import build_membership_lines

        try:
            lines = build_membership_lines([{
                "member_name": "New Member",
                "member_number": "",
                "member_number_pending": True,
                "payment_type": "Existing plan",
                "plan": "1 year",
                "amount": 8.45,
            }])
        except ValueError as exc:
            self.fail(f"pending member number was rejected: {exc}")

        self.assertEqual(lines[0]["memo"], "Share Installments - Paid #Pending")
        self.assertEqual(lines[1]["memo"], "Share Installments - Paid #Pending")

    def test_paid_in_full_does_not_require_member_number_or_plan(self):
        from app.membership_payments import build_membership_lines

        try:
            lines = build_membership_lines([{
                "member_name": "Fully Paid Member",
                "member_number": "",
                "payment_type": "Paid in full",
                "plan": "5 year",
                "amount": 100.00,
            }])
        except ValueError as exc:
            self.fail(f"paid-in-full member number should be optional: {exc}")

        self.assertEqual(lines, [{
            "account": "6100000 · Member Shares (Paid-In Equity)",
            "name": "Fully Paid Member",
            "memo": "Member Shares - Paid",
            "class_name": "",
            "amount": 100.00,
        }])

    def test_combined_payment_option_prevents_a_plan_for_paid_in_full(self):
        try:
            from app.membership_payments import payment_fields_from_option
        except ImportError as exc:
            self.fail(f"combined payment option mapping is missing: {exc}")

        self.assertEqual(
            payment_fields_from_option("Paid in full — $100"),
            {"payment_type": "Paid in full", "plan": ""},
        )
        self.assertEqual(
            payment_fields_from_option("New plan — 3 year"),
            {"payment_type": "New plan", "plan": "3 year"},
        )
        self.assertEqual(
            payment_fields_from_option("Existing plan — 5 year"),
            {"payment_type": "Existing plan", "plan": "5 year"},
        )

    def test_blank_dynamic_editor_row_does_not_require_a_payment_option(self):
        from app.membership_payments import prepare_membership_editor_rows

        try:
            prepared = prepare_membership_editor_rows(
                [{"payment_option": float("nan"), "interest_periods": None}],
                allow_interest_override=False,
            )
        except ValueError as exc:
            self.fail(f"blank dynamic editor row was treated as a payment: {exc}")

        self.assertNotIn("payment_type", prepared[0])
        self.assertNotIn("plan", prepared[0])

    def test_selected_membership_editor_rows_can_be_deleted(self):
        try:
            from app.membership_payments import remove_selected_membership_rows
        except ImportError as exc:
            self.fail(f"membership row deletion helper is missing: {exc}")

        rows = [
            {"member_name": "Keep Me", "delete": False},
            {"member_name": "Remove Me", "delete": True},
        ]

        self.assertEqual(
            remove_selected_membership_rows(rows),
            [{"member_name": "Keep Me"}],
        )

    def test_plan_reference_rows_match_the_staff_payment_guide(self):
        try:
            from app.membership_payments import plan_reference_rows
        except ImportError as exc:
            self.fail(f"staff plan reference is missing: {exc}")

        self.assertEqual(plan_reference_rows(), [
            {
                "Plan": "1 year",
                "Deposit": 10.00,
                "Total Paid": 102.95,
                "Payments": 11,
                "Installment": 8.45,
                "Principal": 8.18,
                "Interest": 0.27,
            },
            {
                "Plan": "3 year",
                "Deposit": 15.00,
                "Total Paid": 109.14,
                "Payments": 6,
                "Installment": 15.69,
                "Principal": 14.17,
                "Interest": 1.52,
            },
            {
                "Plan": "5 year",
                "Deposit": 10.00,
                "Total Paid": 115.50,
                "Payments": 10,
                "Installment": 10.55,
                "Principal": 9.00,
                "Interest": 1.55,
            },
        ])

    def test_membership_choice_requires_a_selection_and_maps_to_engine_mode(self):
        try:
            from app.membership_payments import membership_mode_from_choice
        except ImportError as exc:
            self.fail(f"membership workflow choice mapping is missing: {exc}")

        self.assertIsNone(membership_mode_from_choice(None))
        self.assertEqual(membership_mode_from_choice("Split automatically"), "automatic")
        self.assertEqual(
            membership_mode_from_choice("Finish manually in QuickBooks"),
            "manual",
        )

    def test_hidden_payoff_override_is_cleared_before_automatic_split(self):
        try:
            from app.membership_payments import prepare_membership_editor_rows
        except ImportError as exc:
            self.fail(f"membership editor row preparation is missing: {exc}")

        rows = [{
            "member_name": "A Member",
            "member_number": "12345",
            "payment_type": "Existing plan",
            "plan": "1 year",
            "amount": 20.00,
            "interest_periods": 1,
        }]

        self.assertEqual(
            prepare_membership_editor_rows(rows, allow_interest_override=False)[0]["interest_periods"],
            None,
        )
        self.assertEqual(
            prepare_membership_editor_rows(rows, allow_interest_override=True)[0]["interest_periods"],
            1,
        )

    def test_manual_quickbooks_mode_posts_one_balancing_member_share_line(self):
        from app.membership_payments import build_membership_lines

        try:
            lines = build_membership_lines(
                [],
                expected_subscription_total=8.45,
                handling_mode="manual",
            )
        except TypeError as exc:
            self.fail(f"manual QuickBooks handling mode is missing: {exc}")

        self.assertEqual(lines, [{
            "account": "6100000 · Member Shares (Paid-In Equity)",
            "name": "",
            "memo": "Member Shares - Paid",
            "class_name": "",
            "amount": 8.45,
        }])

    def test_automatic_mode_still_requires_member_details(self):
        from app.membership_payments import build_membership_lines

        try:
            with self.assertRaisesRegex(ValueError, "no membership payments were supplied"):
                build_membership_lines(
                    [],
                    expected_subscription_total=8.45,
                    handling_mode="automatic",
                )
        except TypeError as exc:
            self.fail(f"automatic membership handling mode is missing: {exc}")

    def test_subscription_action_status_distinguishes_clear_and_action_required(self):
        try:
            from app.membership_payments import subscription_action_status
        except ImportError as exc:
            self.fail(f"subscription action status helper is missing: {exc}")

        self.assertEqual(
            subscription_action_status(0),
            {
                "needs_action": False,
                "title": "No Subscription Revenue",
                "message": "No member-share action is needed for this deposit.",
            },
        )
        self.assertEqual(
            subscription_action_status(8.45),
            {
                "needs_action": True,
                "title": "Subscription Revenue found: $8.45",
                "message": (
                    "Choose automatic splitting or finish manually in QuickBooks "
                    "before building the deposit."
                ),
            },
        )

    def test_iif_delimiters_are_rejected_in_member_identity(self):
        from app.membership_payments import build_membership_lines

        base = {
            "member_name": "A Member",
            "member_number": "12345",
            "payment_type": "Existing plan",
            "plan": "1 year",
            "amount": 8.45,
        }
        invalid_values = (
            ("member_name", "A\tMember", "tabs or line breaks"),
            ("member_name", "A\nMember", "tabs or line breaks"),
            ("member_number", "12\r345", "tabs or line breaks"),
            ("member_number", "12-345", "digits only"),
            ("member_number", "１２３４５", "digits only"),
        )

        for field, value, message in invalid_values:
            with self.subTest(field=field, value=value):
                payment = dict(base)
                payment[field] = value
                with self.assertRaisesRegex(ValueError, message):
                    build_membership_lines([payment])

    def test_exclusive_run_lock_blocks_overlap_and_releases(self):
        from pathlib import Path

        from app.membership_payments import exclusive_run_lock

        lock_path = Path(__file__).parent / "_deposit_run.lock"
        lock_path.unlink(missing_ok=True)
        try:
            with exclusive_run_lock(lock_path):
                self.assertTrue(lock_path.exists())
                with self.assertRaisesRegex(RuntimeError, "Another deposit is currently running"):
                    with exclusive_run_lock(lock_path):
                        pass
            self.assertTrue(lock_path.exists())
            with exclusive_run_lock(lock_path):
                self.assertTrue(lock_path.exists())
        finally:
            lock_path.unlink(missing_ok=True)

    def test_abandoned_run_lock_is_reusable_and_stale_membership_files_are_cleaned_up(self):
        import os
        from pathlib import Path
        import time

        from app.membership_payments import exclusive_run_lock, write_membership_payments_file

        folder = Path(__file__).parent / "_stale_membership_output"
        folder.mkdir(exist_ok=True)
        lock_path = folder / "deposit.lock"
        stale_json = folder / "membership_payments_stale.json"
        lock_path.write_text("abandoned", encoding="utf-8")
        stale_json.write_text("[]", encoding="utf-8")
        old_time = time.time() - 7200
        os.utime(lock_path, (old_time, old_time))
        os.utime(stale_json, (old_time, old_time))
        created = None
        try:
            with exclusive_run_lock(lock_path, stale_seconds=60):
                self.assertTrue(lock_path.exists())
            created = write_membership_payments_file(folder, [], stale_seconds=60)
            self.assertFalse(stale_json.exists())
            self.assertTrue(created.exists())
        finally:
            lock_path.unlink(missing_ok=True)
            stale_json.unlink(missing_ok=True)
            if created is not None:
                created.unlink(missing_ok=True)
            folder.rmdir()

    def test_two_processes_cannot_both_take_over_an_abandoned_lock_file(self):
        import os
        from pathlib import Path
        import subprocess
        import sys
        import time

        test_folder = Path(__file__).parent
        lock_path = test_folder / "_cross_process_deposit.lock"
        start_path = test_folder / "_cross_process_start"
        release_path = test_folder / "_cross_process_release"
        result_paths = [test_folder / f"_cross_process_result_{index}" for index in range(2)]
        for path in [lock_path, start_path, release_path, *result_paths]:
            path.unlink(missing_ok=True)
        lock_path.write_text("abandoned", encoding="utf-8")
        old_time = time.time() - 7200
        os.utime(lock_path, (old_time, old_time))

        child_code = """
import sys
import time
from pathlib import Path
from app.membership_payments import exclusive_run_lock
lock_path, start_path, release_path, result_path = map(Path, sys.argv[1:])
deadline = time.time() + 10
while not start_path.exists() and time.time() < deadline:
    time.sleep(0.01)
try:
    with exclusive_run_lock(lock_path):
        result_path.write_text('acquired', encoding='utf-8')
        while not release_path.exists() and time.time() < deadline:
            time.sleep(0.01)
except RuntimeError:
    result_path.write_text('blocked', encoding='utf-8')
"""
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", child_code, lock_path, start_path, release_path, result_path],
                cwd=Path(__file__).parents[1],
            )
            for result_path in result_paths
        ]
        try:
            start_path.write_text("start", encoding="utf-8")
            deadline = time.time() + 10
            while not all(path.exists() for path in result_paths) and time.time() < deadline:
                time.sleep(0.02)
            outcomes = [path.read_text(encoding="utf-8") for path in result_paths]
            self.assertCountEqual(outcomes, ["acquired", "blocked"])
        finally:
            release_path.write_text("release", encoding="utf-8")
            for process in processes:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=5)
            for path in [lock_path, start_path, release_path, *result_paths]:
                path.unlink(missing_ok=True)

    def test_nonzero_subscription_total_explains_required_membership_input(self):
        from app.membership_payments import build_membership_lines

        with self.assertRaisesRegex(ValueError, r"--membership-payments-file"):
            build_membership_lines([], expected_subscription_total=10.00)

    def test_one_year_installment_builds_principal_and_interest_lines(self):
        try:
            from app.membership_payments import build_membership_lines
        except ModuleNotFoundError as exc:
            self.fail(f"membership payment feature is missing: {exc}")

        lines = build_membership_lines(
            [
                {
                    "member_name": "Tara Caruso",
                    "member_number": "22206",
                    "payment_type": "Existing plan",
                    "plan": "1 year",
                    "amount": 8.45,
                }
            ]
        )

        self.assertEqual(
            lines,
            [
                {
                    "account": "1260000 · Member Shares Receivable",
                    "name": "Tara Caruso",
                    "memo": "Share Installments - Paid #22206",
                    "class_name": "",
                    "amount": 8.18,
                },
                {
                    "account": "9104000 · Interest Income",
                    "name": "Tara Caruso",
                    "memo": "Share Installments - Paid #22206",
                    "class_name": "Admin",
                    "amount": 0.27,
                },
            ],
        )

    def test_irregular_one_year_payment_charges_only_complete_periods(self):
        from app.membership_payments import build_membership_lines

        lines = build_membership_lines(
            [{
                "member_name": "Tara Caruso",
                "member_number": "#22206",
                "payment_type": "Existing plan",
                "plan": "1 year",
                "amount": 20.00,
            }]
        )

        self.assertEqual(lines[0]["amount"], 19.46)
        self.assertEqual(lines[1]["amount"], 0.54)
        self.assertEqual(lines[0]["memo"], "Share Installments - Paid #22206")


    def test_five_year_installment_uses_five_year_interest(self):
        from app.membership_payments import build_membership_lines

        lines = build_membership_lines([{
            "member_name": "Will Travers",
            "member_number": "21916",
            "payment_type": "Existing plan",
            "plan": "5 year",
            "amount": 10.55,
        }])

        self.assertEqual(lines[0]["amount"], 9.00)
        self.assertEqual(lines[1]["amount"], 1.55)
        self.assertEqual(lines[1]["class_name"], "Admin")


    def test_three_year_installment_uses_three_year_interest(self):
        from app.membership_payments import build_membership_lines

        try:
            lines = build_membership_lines([{
                "member_name": "A Member",
                "member_number": "30001",
                "payment_type": "Existing plan",
                "plan": "3 year",
                "amount": 15.69,
            }])
        except KeyError as exc:
            self.fail(f"3-year plan is missing: {exc}")

        self.assertEqual(lines[0]["amount"], 14.17)
        self.assertEqual(lines[1]["amount"], 1.52)


    def test_interest_period_override_handles_payoff_adjustment(self):
        from app.membership_payments import build_membership_lines

        lines = build_membership_lines([{
            "member_name": "Tara Caruso",
            "member_number": "22206",
            "payment_type": "Existing plan",
            "plan": "1 year",
            "amount": 20.00,
            "interest_periods": 1,
        }])

        self.assertEqual(lines[0]["amount"], 19.73)
        self.assertEqual(lines[1]["amount"], 0.27)


    def test_new_three_year_plan_creates_receivable_and_interest_free_deposit(self):
        from app.membership_payments import build_membership_lines

        lines = build_membership_lines([{
            "member_name": "A New Member",
            "member_number": "30002",
            "payment_type": "New plan",
            "plan": "3 year",
            "amount": 15.00,
        }])

        self.assertEqual(
            lines,
            [
                {
                    "account": "6100000 · Member Shares (Paid-In Equity)",
                    "name": "A New Member",
                    "memo": "Member Shares - Receivable",
                    "class_name": "",
                    "amount": 100.00,
                },
                {
                    "account": "1260000 · Member Shares Receivable",
                    "name": "A New Member",
                    "memo": "Member Shares - Receivable",
                    "class_name": "",
                    "amount": -100.00,
                },
                {
                    "account": "1260000 · Member Shares Receivable",
                    "name": "A New Member",
                    "memo": "Share Installments - Paid #30002",
                    "class_name": "",
                    "amount": 15.00,
                },
            ],
        )


    def test_new_one_and_five_year_plans_create_receivable_with_ten_dollar_deposit(self):
        from app.membership_payments import build_membership_lines

        for plan in ("1 year", "5 year"):
            with self.subTest(plan=plan):
                try:
                    lines = build_membership_lines([{
                        "member_name": "A New Member",
                        "member_number": "40001",
                        "payment_type": "New plan",
                        "plan": plan,
                        "amount": 10.00,
                    }])
                except KeyError as exc:
                    self.fail(f"new {plan} plan is missing its deposit rule: {exc}")

                self.assertEqual([line["amount"] for line in lines], [100.00, -100.00, 10.00])
                self.assertEqual(lines[2]["memo"], "Share Installments - Paid #40001")


    def test_new_plan_can_include_deposit_and_first_installment(self):
        from app.membership_payments import build_membership_lines

        lines = build_membership_lines([{
            "member_name": "A New Member",
            "member_number": "40002",
            "payment_type": "New plan",
            "plan": "1 year",
            "amount": 18.45,
        }])

        self.assertEqual([line["amount"] for line in lines], [100.00, -100.00, 18.18, 0.27])


    def test_paid_in_full_posts_one_hundred_to_member_shares_equity(self):
        from app.membership_payments import build_membership_lines

        try:
            lines = build_membership_lines([{
                "member_name": "Paid Member",
                "member_number": "50001",
                "payment_type": "Paid in full",
                "plan": "",
                "amount": 100.00,
            }])
        except KeyError as exc:
            self.fail(f"paid-in-full path is missing: {exc}")

        self.assertEqual(lines, [{
            "account": "6100000 · Member Shares (Paid-In Equity)",
            "name": "Paid Member",
            "memo": "Member Shares - Paid",
            "class_name": "",
            "amount": 100.00,
        }])


    def test_payment_total_must_match_subscription_revenue(self):
        from app.membership_payments import build_membership_lines

        payment = {
            "member_name": "Tara Caruso",
            "member_number": "22206",
            "payment_type": "Existing plan",
            "plan": "1 year",
            "amount": 8.45,
        }

        try:
            with self.assertRaisesRegex(
                ValueError,
                r"Entered membership payments \(\$8\.45\) must equal Subscription Revenue \(\$10\.00\)",
            ):
                build_membership_lines([payment], expected_subscription_total=10.00)
        except TypeError as exc:
            self.fail(f"subscription reconciliation is missing: {exc}")


    def test_blank_interest_override_uses_automatic_periods(self):
        from app.membership_payments import build_membership_lines

        for blank_value in (None, float("nan")):
            with self.subTest(blank_value=blank_value):
                try:
                    lines = build_membership_lines([{
                        "member_name": "Tara Caruso",
                        "member_number": "22206",
                        "payment_type": "Existing plan",
                        "plan": "1 year",
                        "amount": 16.90,
                        "interest_periods": blank_value,
                    }])
                except (TypeError, ValueError) as exc:
                    self.fail(f"blank interest override should use automatic periods: {exc}")

                self.assertEqual(lines[0]["amount"], 16.36)
                self.assertEqual(lines[1]["amount"], 0.54)


    def test_automatic_interest_periods_are_capped_at_full_plan_schedule(self):
        from app.membership_payments import build_membership_lines

        lines = build_membership_lines([{
            "member_name": "Payoff Member",
            "member_number": "60001",
            "payment_type": "Existing plan",
            "plan": "1 year",
            "amount": 200.00,
        }])

        self.assertEqual(lines[0]["amount"], 197.03)
        self.assertEqual(lines[1]["amount"], 2.97)


    def test_invalid_membership_rows_are_rejected(self):
        from app.membership_payments import build_membership_lines

        base = {
            "member_name": "A Member",
            "member_number": "70001",
            "payment_type": "Existing plan",
            "plan": "1 year",
            "amount": 8.45,
        }
        cases = [
            ({**base, "member_name": ""}, r"Member name is required"),
            ({**base, "member_number": ""}, r"Member number is required"),
            ({**base, "payment_type": "Mystery"}, r"Payment type must be"),
            ({**base, "plan": "2 year"}, r"Plan must be"),
            ({**base, "amount": 0}, r"Amount must be greater than zero"),
            (
                {**base, "payment_type": "Paid in full", "plan": "", "amount": 99},
                r"Paid in full must be exactly \$100\.00",
            ),
            (
                {**base, "payment_type": "New plan", "plan": "3 year", "amount": 10},
                r"New 3 year plan payment must include the \$15\.00 deposit",
            ),
            ({**base, "interest_periods": 12}, r"Interest periods must be between 0 and 11"),
        ]

        for payment, message in cases:
            with self.subTest(payment=payment):
                try:
                    with self.assertRaisesRegex(ValueError, message):
                        build_membership_lines([payment])
                except (KeyError, TypeError) as exc:
                    self.fail(f"invalid input was not validated: {exc}")


    def test_generate_iif_writes_member_principal_and_admin_interest_lines(self):
        from datetime import date
        from pathlib import Path

        from app import pos_to_quickbooks_v2 as engine

        payment = {
            "member_name": "Tara Caruso",
            "member_number": "22206",
            "payment_type": "Existing plan",
            "plan": "1 year",
            "amount": 8.45,
        }

        temp_dir = Path(__file__).parent / "_membership_iif_output"
        temp_dir.mkdir(exist_ok=True)
        old_output_dir = engine.output_dir
        old_log_dir = engine.LOG_DIR
        old_log_disabled = engine.log.disabled
        engine.output_dir = temp_dir
        engine.LOG_DIR = temp_dir
        engine.log.disabled = True
        try:
            try:
                iif_path = engine.generate_iif(
                    {}, {}, {}, date(2026, 8, 24),
                    bs_data={"subscription": 8.45},
                    membership_payments=[payment],
                )
            except TypeError as exc:
                self.fail(f"IIF membership integration is missing: {exc}")
            iif_text = iif_path.read_text(encoding="utf-8")
        finally:
            engine.output_dir = old_output_dir
            engine.LOG_DIR = old_log_dir
            engine.log.disabled = old_log_disabled
            for generated_file in temp_dir.iterdir():
                generated_file.unlink()
            temp_dir.rmdir()

        self.assertIn(
            "SPL\tDEPOSIT\t08/24/2026\t1260000 · Member Shares Receivable\t"
            "Tara Caruso\t-8.18\tShare Installments - Paid #22206\t",
            iif_text,
        )
        self.assertIn(
            "SPL\tDEPOSIT\t08/24/2026\t9104000 · Interest Income\t"
            "Tara Caruso\t-0.27\tShare Installments - Paid #22206\tAdmin",
            iif_text,
        )

    def test_generate_iif_keeps_multiple_members_and_new_plan_offsets_separate(self):
        from datetime import date
        from pathlib import Path

        from app import pos_to_quickbooks_v2 as engine

        payments = [
            {
                "member_name": "Paid Member",
                "member_number": "11111",
                "payment_type": "Paid in full",
                "plan": "",
                "amount": 100.00,
            },
            {
                "member_name": "New Member",
                "member_number": "22222",
                "payment_type": "New plan",
                "plan": "5 year",
                "amount": 10.00,
            },
        ]

        temp_dir = Path(__file__).parent / "_multiple_members_iif_output"
        temp_dir.mkdir(exist_ok=True)
        old_output_dir = engine.output_dir
        old_log_dir = engine.LOG_DIR
        old_log_disabled = engine.log.disabled
        engine.output_dir = temp_dir
        engine.LOG_DIR = temp_dir
        engine.log.disabled = True
        try:
            iif_path = engine.generate_iif(
                {}, {}, {}, date(2026, 8, 24),
                bs_data={"subscription": 110.00},
                membership_payments=payments,
            )
            iif_text = iif_path.read_text(encoding="utf-8")
        finally:
            engine.output_dir = old_output_dir
            engine.LOG_DIR = old_log_dir
            engine.log.disabled = old_log_disabled
            for generated_file in temp_dir.iterdir():
                generated_file.unlink()
            temp_dir.rmdir()

        self.assertIn(
            "6100000 · Member Shares (Paid-In Equity)\tPaid Member\t-100.00\t"
            "Member Shares - Paid",
            iif_text,
        )
        self.assertIn(
            "6100000 · Member Shares (Paid-In Equity)\tNew Member\t-100.00\t"
            "Member Shares - Receivable",
            iif_text,
        )
        self.assertIn(
            "1260000 · Member Shares Receivable\tNew Member\t100.00\t"
            "Member Shares - Receivable",
            iif_text,
        )
        self.assertIn(
            "1260000 · Member Shares Receivable\tNew Member\t-10.00\t"
            "Share Installments - Paid #22222",
            iif_text,
        )

    def test_generate_iif_manual_mode_uses_one_unnamed_equity_line(self):
        from datetime import date
        from pathlib import Path

        from app import pos_to_quickbooks_v2 as engine

        temp_dir = Path(__file__).parent / "_manual_membership_iif_output"
        temp_dir.mkdir(exist_ok=True)
        old_output_dir = engine.output_dir
        old_log_dir = engine.LOG_DIR
        old_log_disabled = engine.log.disabled
        engine.output_dir = temp_dir
        engine.LOG_DIR = temp_dir
        engine.log.disabled = True
        try:
            try:
                iif_path = engine.generate_iif(
                    {}, {}, {}, date(2026, 8, 24),
                    bs_data={"subscription": 8.45},
                    membership_payments=[],
                    membership_mode="manual",
                )
            except TypeError as exc:
                self.fail(f"manual membership IIF mode is missing: {exc}")
            iif_text = iif_path.read_text(encoding="utf-8")
        finally:
            engine.output_dir = old_output_dir
            engine.LOG_DIR = old_log_dir
            engine.log.disabled = old_log_disabled
            for generated_file in temp_dir.iterdir():
                generated_file.unlink()
            temp_dir.rmdir()

        self.assertIn(
            "6100000 · Member Shares (Paid-In Equity)\t\t-8.45\tMember Shares - Paid",
            iif_text,
        )
        self.assertNotIn("1260000 · Member Shares Receivable", iif_text)
        self.assertNotIn("9104000 · Interest Income", iif_text)


    def test_membership_payment_file_loads_manual_app_rows(self):
        import json
        from pathlib import Path

        try:
            from app.membership_payments import load_membership_payments_file
        except ImportError as exc:
            self.fail(f"membership payment file loader is missing: {exc}")

        expected = [{
            "member_name": "Tara Caruso",
            "member_number": "22206",
            "payment_type": "Existing plan",
            "plan": "1 year",
            "amount": 8.45,
            "interest_periods": None,
        }]
        path = Path(__file__).parent / "_membership_rows.json"
        path.write_text(json.dumps(expected), encoding="utf-8")
        try:
            self.assertEqual(load_membership_payments_file(path), expected)
        finally:
            path.unlink(missing_ok=True)


    def test_membership_payment_file_must_contain_a_list(self):
        from pathlib import Path

        from app.membership_payments import load_membership_payments_file

        path = Path(__file__).parent / "_invalid_membership_rows.json"
        path.write_text('{"member_name": "not a list"}', encoding="utf-8")
        try:
            with self.assertRaisesRegex(ValueError, "must contain a list"):
                load_membership_payments_file(path)
        finally:
            path.unlink(missing_ok=True)


    def test_subscription_total_is_read_from_balance_sheet_code_3420(self):
        from io import BytesIO

        import openpyxl

        try:
            from app.membership_payments import read_subscription_total
        except ImportError as exc:
            self.fail(f"subscription total reader is missing: {exc}")

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "082426 BS"
        sheet.append([3420, "Subscription Revenue", None, None, -28.45])
        content = BytesIO()
        workbook.save(content)

        self.assertEqual(read_subscription_total(content.getvalue(), "082426 BS"), 28.45)

    def test_subscription_total_rejects_missing_or_malformed_balance_sheet_data(self):
        from io import BytesIO

        import openpyxl

        from app.membership_payments import read_subscription_total

        missing_bs_workbook = openpyxl.Workbook()
        missing_bs_workbook.active.title = "Sales"
        missing_bs_content = BytesIO()
        missing_bs_workbook.save(missing_bs_content)

        with self.assertRaisesRegex(ValueError, "Balance Sheet"):
            read_subscription_total(missing_bs_content.getvalue())

        for malformed_amount in ("not a dollar amount", "NaN", "Infinity", "-Infinity"):
            with self.subTest(malformed_amount=malformed_amount):
                malformed_workbook = openpyxl.Workbook()
                malformed_sheet = malformed_workbook.active
                malformed_sheet.title = "082426 BS"
                malformed_sheet.append(
                    [3420, "Subscription Revenue", None, None, malformed_amount]
                )
                malformed_content = BytesIO()
                malformed_workbook.save(malformed_content)

                with self.assertRaisesRegex(ValueError, "3420"):
                    read_subscription_total(malformed_content.getvalue(), "082426 BS")

    def test_valid_balance_sheet_without_3420_means_no_subscription_activity(self):
        from io import BytesIO

        import openpyxl

        from app.membership_payments import read_subscription_total

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "082426 BS"
        sheet.append([901, "Cash", None, None, 250.00])
        content = BytesIO()
        workbook.save(content)

        self.assertEqual(read_subscription_total(content.getvalue(), "082426 BS"), 0.0)


    def test_interest_override_cannot_exceed_automatic_period_count(self):
        from app.membership_payments import build_membership_lines

        payment = {
            "member_name": "A Member",
            "member_number": "80001",
            "payment_type": "Existing plan",
            "plan": "1 year",
            "amount": 8.45,
            "interest_periods": 2,
        }
        with self.assertRaisesRegex(ValueError, "automatic count of 1"):
            build_membership_lines([payment])


    def test_membership_payment_files_are_unique_per_app_run(self):
        from pathlib import Path

        try:
            from app.membership_payments import (
                load_membership_payments_file,
                write_membership_payments_file,
            )
        except ImportError as exc:
            self.fail(f"unique membership payment writer is missing: {exc}")

        folder = Path(__file__).parent / "_membership_json_output"
        folder.mkdir(exist_ok=True)
        payments = [{"member_name": "A Member", "amount": 8.45}]
        paths = []
        try:
            paths = [
                write_membership_payments_file(folder, payments),
                write_membership_payments_file(folder, payments),
            ]
            self.assertNotEqual(paths[0], paths[1])
            self.assertEqual(load_membership_payments_file(paths[0]), payments)
            self.assertEqual(load_membership_payments_file(paths[1]), payments)
        finally:
            for path in paths:
                path.unlink(missing_ok=True)
            folder.rmdir()


    def test_membership_editor_key_changes_for_a_different_workbook(self):
        try:
            from app.membership_payments import membership_editor_key
        except ImportError as exc:
            self.fail(f"membership editor key helper is missing: {exc}")

        first = membership_editor_key(b"workbook one", 0)
        same = membership_editor_key(b"workbook one", 0)
        different = membership_editor_key(b"workbook two", 0)
        reset = membership_editor_key(b"workbook one", 1)

        self.assertEqual(first, same)
        self.assertNotEqual(first, different)
        self.assertNotEqual(first, reset)


if __name__ == "__main__":
    unittest.main()
