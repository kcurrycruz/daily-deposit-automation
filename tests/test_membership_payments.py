import unittest


class MembershipPaymentTests(unittest.TestCase):
    def test_coupon_counter_logic_uses_a_separate_deployment_module(self):
        from pathlib import Path

        repository_root = Path(__file__).resolve().parents[1]
        counter_module = repository_root / "app" / "coupon_counter.py"
        self.assertTrue(counter_module.is_file())

        app_source = (repository_root / "streamlit_app.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("from app.coupon_counter import (", app_source)

    def test_coupon_counter_reference_workbook_is_packaged(self):
        from pathlib import Path

        import openpyxl

        workbook_path = (
            Path(__file__).resolve().parents[1]
            / "assets"
            / "NCG-MFG Coupon Counter.xlsx"
        )
        self.assertTrue(workbook_path.is_file())
        workbook = openpyxl.load_workbook(workbook_path, read_only=True, data_only=False)
        try:
            self.assertIn("Template", workbook.sheetnames)
            sheet = workbook["Template"]
            self.assertEqual(
                [sheet.cell(1, column).value for column in range(2, 7)],
                ["NCG", "MFG", "VP", "MKTG", "SITKA"],
            )
        finally:
            workbook.close()

    def test_coupon_stacks_roll_reimbursed_categories_into_mfg(self):
        from app.coupon_counter import summarize_coupon_stacks

        summary = summarize_coupon_stacks([
            {
                "id": "ncg-1",
                "category": "NCG",
                "label": "Labeled stack",
                "expected_total": 10.00,
                "amounts": [0.25, 0.50, 1.25, 3.00, 5.00],
            },
            {
                "id": "mfg-1",
                "category": "MFG",
                "label": "Unlabeled stack",
                "expected_total": None,
                "amounts": [4.99, 5.99],
            },
            {"id": "vp-1", "category": "VP", "amounts": [2.00]},
            {"id": "mktg-1", "category": "MKTG", "amounts": [3.00]},
            {"id": "sitka-1", "category": "SITKA", "amounts": [4.00]},
        ])

        self.assertEqual(summary["category_totals"], {
            "NCG": 10.00,
            "MFG": 10.98,
            "VP": 2.00,
            "MKTG": 3.00,
            "SITKA": 4.00,
        })
        self.assertEqual(summary["ncg_total"], 10.00)
        self.assertEqual(summary["mfg_total"], 19.98)
        self.assertEqual(summary["overall_total"], 29.98)
        self.assertTrue(summary["stacks"][0]["matches_expected"])
        self.assertIsNone(summary["stacks"][1]["matches_expected"])

    def test_coupon_stack_reports_written_total_difference_and_rejects_bad_amounts(self):
        from app.coupon_counter import summarize_coupon_stacks

        summary = summarize_coupon_stacks([
            {
                "id": "mfg-1",
                "category": "MFG",
                "expected_total": 10.00,
                "amounts": [4.99, 5.00],
            }
        ])
        self.assertEqual(summary["stacks"][0]["subtotal"], 9.99)
        self.assertEqual(summary["stacks"][0]["difference"], -0.01)
        self.assertFalse(summary["stacks"][0]["matches_expected"])

        for bad_stack in (
            {"category": "OTHER", "amounts": [1.00]},
            {"category": "NCG", "amounts": [0]},
            {"category": "MFG", "amounts": [-1]},
        ):
            with self.subTest(bad_stack=bad_stack):
                with self.assertRaises(ValueError):
                    summarize_coupon_stacks([bad_stack])

    def test_coupon_stack_entries_can_be_added_and_removed_without_changing_other_stacks(self):
        from app.coupon_counter import (
            add_coupon_amount,
            remove_coupon_amount,
        )

        stacks = [
            {"id": "ncg-1", "category": "NCG", "amounts": [0.25]},
            {"id": "mfg-1", "category": "MFG", "amounts": [4.99]},
        ]
        added = add_coupon_amount(stacks, "mfg-1", 5.99)
        self.assertEqual(added[1]["amounts"], [4.99, 5.99])
        self.assertEqual(added[0]["amounts"], [0.25])

        removed = remove_coupon_amount(added, "mfg-1", 0)
        self.assertEqual(removed[1]["amounts"], [5.99])
        self.assertEqual(stacks[1]["amounts"], [4.99])

    def test_coupon_reconciliation_keeps_legacy_bs_process(self):
        try:
            from app.coupon_reconciliation import reconcile_coupon_receivable
        except ImportError as exc:
            self.fail(f"coupon reconciliation module is missing: {exc}")

        self.assertEqual(
            reconcile_coupon_receivable(181.50, mode="quickbooks"),
            {
                "bs_total": 181.50,
                "closeout_actual_total": None,
                "ncg_total": 181.50,
                "mfg_total": None,
                "difference": None,
            },
        )

    def test_coupon_reconciliation_builds_signed_closeout_differences(self):
        try:
            from app.coupon_reconciliation import reconcile_coupon_receivable
        except ImportError as exc:
            self.fail(f"coupon reconciliation module is missing: {exc}")

        cases = [
            (188.25, 152.25, 36.00, 6.75),
            (175.00, 150.00, 25.00, -6.50),
        ]
        for closeout, ncg, mfg, expected_difference in cases:
            with self.subTest(closeout=closeout):
                result = reconcile_coupon_receivable(
                    181.50,
                    mode="closeout",
                    closeout_actual_total=closeout,
                    ncg_total=ncg,
                    mfg_total=mfg,
                )
                self.assertEqual(result["difference"], expected_difference)
                self.assertEqual(result["ncg_total"], ncg)
                self.assertEqual(result["mfg_total"], mfg)

    def test_coupon_reconciliation_requires_counts_to_match_closeout_actual(self):
        try:
            from app.coupon_reconciliation import reconcile_coupon_receivable
        except ImportError as exc:
            self.fail(f"coupon reconciliation module is missing: {exc}")

        with self.assertRaisesRegex(
            ValueError,
            "NCG Coupons.*MFG Coupons.*Closeout Sheet Coupon Actual Total",
        ):
            reconcile_coupon_receivable(
                181.50,
                mode="closeout",
                closeout_actual_total=188.25,
                ncg_total=150.00,
                mfg_total=36.00,
            )

    def test_coupon_receivable_total_is_read_from_bs_code_908(self):
        from io import BytesIO

        import openpyxl

        try:
            from app.coupon_reconciliation import read_coupon_receivable_total
        except ImportError as exc:
            self.fail(f"coupon BS reader is missing: {exc}")

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "082626 BS"
        sheet.append([908, "Dwr Vendor coupon", None, None, -181.50])
        output = BytesIO()
        workbook.save(output)
        workbook.close()

        self.assertEqual(
            read_coupon_receivable_total(output.getvalue(), "082626 BS"),
            181.50,
        )

    def test_result_actions_stay_outside_more_information_dropdown(self):
        import ast
        from pathlib import Path

        source_path = Path(__file__).parents[1] / "streamlit_app.py"
        source_tree = ast.parse(source_path.read_text(encoding="utf-8"))
        detail_dropdowns = []
        for node in ast.walk(source_tree):
            if not isinstance(node, ast.With) or not node.items:
                continue
            context = node.items[0].context_expr
            if not isinstance(context, ast.Call):
                continue
            function = context.func
            if not (
                isinstance(function, ast.Attribute)
                and function.attr == "expander"
                and context.args
                and isinstance(context.args[0], ast.Constant)
                and context.args[0].value == "More deposit information"
            ):
                continue
            detail_dropdowns.append(node)

        self.assertEqual(len(detail_dropdowns), 1)
        dropdown_source = ast.unparse(detail_dropdowns[0])
        self.assertIn("st.tabs", dropdown_source)
        self.assertNotIn("Download QuickBooks IIF", dropdown_source)
        self.assertNotIn("Run another deposit", dropdown_source)

    def test_coupon_closeout_ui_exposes_required_choice_and_fields(self):
        import ast
        from pathlib import Path

        source = (
            Path(__file__).parents[1] / "streamlit_app.py"
        ).read_text(encoding="utf-8")
        required_labels = (
            "How should Coupons Receivable be handled?",
            "Finish manually in QuickBooks",
            "Breakdown in app using Closeout Sheet",
            "Closeout Sheet Coupon Actual Total",
            "NCG Coupons counted",
            "MFG Coupons counted",
            "How would you like to enter coupon counts?",
            "Count coupon stacks in app",
            "Enter totals directly",
            "Add a stack",
            "Written stack total (optional)",
            "Add coupon",
            "NCG quick amounts",
            "MFG + VP + MKTG + SITKA",
            "Download Excel coupon counter",
        )
        for label in required_labels:
            with self.subTest(label=label):
                self.assertIn(label, source)

        radio_options = {}
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr != "radio":
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            options_keyword = next(
                (keyword for keyword in node.keywords if keyword.arg == "options"),
                None,
            )
            if options_keyword and isinstance(options_keyword.value, ast.List):
                radio_options[node.args[0].value] = [
                    item.value for item in options_keyword.value.elts
                ]

        self.assertEqual(
            radio_options["How should these payments be handled?"],
            [
                "Breakdown in app using the Ownership Payments sheet",
                "Finish manually in QuickBooks",
            ],
        )
        self.assertEqual(
            radio_options["How should Coupons Receivable be handled?"],
            [
                "Breakdown in app using Closeout Sheet",
                "Finish manually in QuickBooks",
            ],
        )

    def test_app_passes_coupon_closeout_values_to_engine(self):
        import ast
        from pathlib import Path

        source_path = Path(__file__).parents[1] / "streamlit_app.py"
        source_tree = ast.parse(source_path.read_text(encoding="utf-8"))
        run_engine_node = next(
            node
            for node in source_tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "run_engine"
        )
        run_engine_source = ast.unparse(run_engine_node)
        for flag in (
            "--coupon-mode",
            "--coupon-closeout-total",
            "--coupon-ncg-total",
            "--coupon-mfg-total",
        ):
            with self.subTest(flag=flag):
                self.assertIn(flag, run_engine_source)

    def test_workbook_validation_ignores_xxxxxx_discount_and_hash_tabs(self):
        import ast
        from io import BytesIO
        from pathlib import Path
        from typing import Optional

        import openpyxl

        source_path = Path(__file__).parents[1] / "streamlit_app.py"
        source_tree = ast.parse(source_path.read_text(encoding="utf-8"))
        function_node = next(
            node
            for node in source_tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "detect_sheet_roles"
        )
        namespace = {"Optional": Optional}
        exec(compile(ast.Module(body=[function_node], type_ignores=[]), str(source_path), "exec"), namespace)

        workbook = openpyxl.Workbook()
        workbook.active.title = "XXXXXX Discounts"
        workbook.create_sheet("XXXXXX Hash")
        discounts = workbook.create_sheet("082626 Discounts")
        discounts.append(["Discounts by Shopper Level"])
        discounts.append([None, None, "Member Discounts"])
        hash_sheet = workbook.create_sheet("082626 Hash")
        hash_sheet.append([None, 23, "Refunded Discounts", None, None, None, 8, 6.96])
        hash_sheet.append([None, 32, "PASS THROUGH DONATIONS", None, None, None, 5, 5.00])
        output = BytesIO()
        workbook.save(output)
        workbook.close()

        roles = namespace["detect_sheet_roles"](output.getvalue())

        self.assertEqual(roles["discounts"], "082626 Discounts")
        self.assertEqual(roles["hash"], "082626 Hash")

    def test_discount_parser_prefers_the_dated_tab_over_xxxxxx_placeholder(self):
        from datetime import date
        from pathlib import Path

        import openpyxl

        from app import pos_to_quickbooks_v2 as engine

        workbook_path = Path(__file__).parent / "_dated_discounts_fixture.xlsx"
        workbook = openpyxl.Workbook()
        placeholder = workbook.active
        placeholder.title = "XXXXXX Discounts"
        dated = workbook.create_sheet("082626 Discounts")
        dated.append(["Discounts by Shopper Level"])
        dated.append(["Date: ", "8/26/2026", "to", "8/26/2026"])
        dated.append(["Target: ", "RAL", "Report all"])
        dated.append([None, None, "Description", None, None, None, None, None, "Qty", "Amount"])
        dated.append(["Shareholder", None, None, 2, None, None, None, 2365, 277.66])
        dated.append(["Senior NonMember", None, None, 3, None, None, None, 3294, 1646.30])
        dated.append(["Senior Share", None, None, 4, None, None, None, 3225, 1547.71])
        dated.append([None, None, "Member Discounts", None, None, None, None, 8814, 3471.67])
        workbook.save(workbook_path)
        workbook.close()
        try:
            discounts, grand_total = engine.parse_excel_discounts(
                workbook_path,
                date(2026, 8, 26),
            )
        finally:
            try:
                workbook_path.unlink()
            except PermissionError:
                pass

        self.assertEqual(grand_total, 3471.67)
        self.assertEqual(discounts["8512001 · Discount 2% - Owners"], 277.66)
        self.assertEqual(discounts["8511002 · Discount 8% - Senior Day"], 3194.01)

    def test_hash_parser_prefers_the_dated_tab_over_xxxxxx_placeholder(self):
        from datetime import date
        from pathlib import Path

        import openpyxl

        from app import pos_to_quickbooks_v2 as engine

        workbook_path = Path(__file__).parent / "_dated_hash_fixture.xlsx"
        workbook = openpyxl.Workbook()
        placeholder = workbook.active
        placeholder.title = "XXXXXX Hash"
        dated = workbook.create_sheet("082626 Hash")
        dated.append(["Sub-department Single Total"])
        dated.append(["Date: ", "8/26/2026", "to", "8/26/2026"])
        dated.append(["S-Dept.  ", 0, "to", 999999])
        dated.append(["Tlz.:", 6, "to", 6])
        dated.append(["Target: ", "RAL", "Report all"])
        dated.append([None, None, "Sub-Department", None, None, None, None, "Qty", "Amount"])
        dated.append([None, 23, "Refunded Discounts", None, None, None, 8, 6.96])
        dated.append([None, 32, "PASS THROUGH DONATIONS", None, None, None, 5, 5.00])
        workbook.save(workbook_path)
        workbook.close()
        try:
            parsed = engine.parse_hash_sheet(workbook_path, date(2026, 8, 26))
        finally:
            try:
                workbook_path.unlink()
            except PermissionError:
                pass

        self.assertEqual(parsed, (6.96, 5.00, 0.0))

    def test_discount_parser_falls_back_to_a_populated_custom_tab(self):
        from datetime import date
        from pathlib import Path

        import openpyxl

        from app import pos_to_quickbooks_v2 as engine

        workbook_path = Path(__file__).parent / "_custom_discounts_fixture.xlsx"
        workbook = openpyxl.Workbook()
        workbook.active.title = "XXXXXX Discounts"
        custom = workbook.create_sheet("Daily Shopper Report")
        custom.append(["Discounts by Shopper Level"])
        custom.append(["Date: ", "8/26/2026", "to", "8/26/2026"])
        custom.append(["Target: ", "RAL", "Report all"])
        custom.append([None, None, "Description", None, None, None, None, None, "Qty", "Amount"])
        custom.append(["Shareholder", None, None, 2, None, None, None, 2365, 277.66])
        custom.append([None, None, "Member Discounts", None, None, None, None, 2365, 277.66])
        workbook.save(workbook_path)
        workbook.close()
        try:
            discounts, total = engine.parse_excel_discounts(
                workbook_path,
                date(2026, 8, 26),
            )
        finally:
            try:
                workbook_path.unlink()
            except PermissionError:
                pass

        self.assertEqual(total, 277.66)
        self.assertEqual(discounts["8512001 · Discount 2% - Owners"], 277.66)

    def test_hash_parser_falls_back_to_a_populated_custom_tab(self):
        from datetime import date
        from pathlib import Path

        import openpyxl

        from app import pos_to_quickbooks_v2 as engine

        workbook_path = Path(__file__).parent / "_custom_hash_fixture.xlsx"
        workbook = openpyxl.Workbook()
        workbook.active.title = "XXXXXX Hash"
        custom = workbook.create_sheet("Daily Special Items")
        custom.append(["Sub-department Single Total"])
        custom.append(["Date: ", "8/26/2026", "to", "8/26/2026"])
        custom.append(["S-Dept.  ", 0, "to", 999999])
        custom.append(["Tlz.:", 6, "to", 6])
        custom.append(["Target: ", "RAL", "Report all"])
        custom.append([None, None, "Sub-Department", None, None, None, None, "Qty", "Amount"])
        custom.append([None, 23, "Refunded Discounts", None, None, None, 8, 6.96])
        custom.append([None, 32, "PASS THROUGH DONATIONS", None, None, None, 5, 5.00])
        workbook.save(workbook_path)
        workbook.close()
        try:
            parsed = engine.parse_hash_sheet(workbook_path, date(2026, 8, 26))
        finally:
            try:
                workbook_path.unlink()
            except PermissionError:
                pass

        self.assertEqual(parsed, (6.96, 5.00, 0.0))

    def test_automatic_split_leaves_new_quickbooks_member_name_blank(self):
        from app.membership_payments import (
            build_membership_lines,
            membership_payment_from_entry,
        )

        try:
            payment = membership_payment_from_entry(
                member_name="This typed value must be ignored",
                member_number_status="No",
                member_number="",
                quickbooks_member_exists=False,
                payment_option="Paid in full — $100",
                amount=100.00,
            )
            lines = build_membership_lines([payment], handling_mode="automatic")
        except ValueError as exc:
            self.fail(f"new QuickBooks member was rejected: {exc}")

        self.assertEqual(payment["member_name"], "")
        self.assertEqual(lines[0]["name"], "")

    def test_member_payment_entry_requires_quickbooks_name_confirmation(self):
        from app.membership_payments import membership_payment_from_entry

        with self.assertRaisesRegex(
            ValueError,
            "Select Yes or No.*QuickBooks",
        ):
            membership_payment_from_entry(
                member_name="Existing Member",
                member_number_status="No",
                member_number="",
                payment_option="Paid in full — $100",
                amount=100.00,
            )

    def test_member_number_question_builds_assigned_and_pending_entries(self):
        try:
            from app.membership_payments import membership_payment_from_entry
        except ImportError as exc:
            self.fail(f"member payment entry builder is missing: {exc}")

        assigned = membership_payment_from_entry(
            member_name="Assigned Member",
            member_number_status="Yes",
            member_number="12345",
            quickbooks_member_exists=True,
            payment_option="Existing plan — 1 year",
            amount=8.45,
        )
        pending = membership_payment_from_entry(
            member_name="Pending Member",
            member_number_status="No",
            member_number="",
            quickbooks_member_exists=True,
            payment_option="New plan — 3 year",
            amount=15.00,
        )

        self.assertEqual(assigned["member_number"], "12345")
        self.assertFalse(assigned["member_number_pending"])
        self.assertEqual(assigned["payment_type"], "Existing plan")
        self.assertEqual(assigned["plan"], "1 year")
        self.assertEqual(pending["member_number"], "")
        self.assertTrue(pending["member_number_pending"])
        self.assertEqual(pending["payment_type"], "New plan")
        self.assertEqual(pending["plan"], "3 year")

    def test_saved_member_payment_can_be_removed_by_position(self):
        try:
            from app.membership_payments import remove_membership_payment
        except ImportError as exc:
            self.fail(f"saved member payment removal is missing: {exc}")

        payments = [
            {"member_name": "Keep First"},
            {"member_name": "Remove"},
            {"member_name": "Keep Last"},
        ]

        self.assertEqual(
            remove_membership_payment(payments, 1),
            [
                {"member_name": "Keep First"},
                {"member_name": "Keep Last"},
            ],
        )

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

    def test_editor_rows_refresh_only_to_autofill_paid_in_full(self):
        try:
            from app.membership_payments import normalize_membership_editor_rows
        except ImportError as exc:
            self.fail(f"membership editor normalization is missing: {exc}")

        ordinary_rows = [{
            "member_name": "Still Typing",
            "payment_option": "Existing plan — 1 year",
            "amount": 8.45,
        }]
        paid_in_full_rows = [{
            "member_name": "Fully Paid Member",
            "payment_option": "Paid in full — $100",
            "amount": None,
        }]

        normalized, refresh_required = normalize_membership_editor_rows(ordinary_rows)
        self.assertEqual(normalized, ordinary_rows)
        self.assertFalse(refresh_required)

        normalized, refresh_required = normalize_membership_editor_rows(paid_in_full_rows)
        self.assertEqual(normalized[0]["amount"], 100.00)
        self.assertTrue(refresh_required)

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
        self.assertEqual(
            membership_mode_from_choice(
                "Breakdown in app using the Ownership Payments sheet"
            ),
            "automatic",
        )
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

    def test_generate_iif_keeps_legacy_coupon_receivable_process(self):
        from datetime import date
        from pathlib import Path

        from app import pos_to_quickbooks_v2 as engine

        temp_dir = Path(__file__).parent / "_legacy_coupon_iif_output"
        temp_dir.mkdir(exist_ok=True)
        old_output_dir = engine.output_dir
        old_log_dir = engine.LOG_DIR
        old_log_disabled = engine.log.disabled
        engine.output_dir = temp_dir
        engine.LOG_DIR = temp_dir
        engine.log.disabled = True
        try:
            iif_path = engine.generate_iif(
                {}, {}, {}, date(2026, 8, 26),
                bs_data={"vendor_coupon": 181.50},
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
            "1250000 · Coupons Receivable\t\t181.50\tNCG Coupons",
            iif_text,
        )
        self.assertIn(
            "1250000 · Coupons Receivable\t\t\tMFG Coupons",
            iif_text,
        )
        self.assertNotIn("Over/Short per Closeout Sheet - Coupon", iif_text)

    def test_iif_omits_empty_calculated_lines_but_keeps_manual_placeholders(self):
        from datetime import date
        from pathlib import Path

        from app import pos_to_quickbooks_v2 as engine

        temp_dir = Path(__file__).parent / "_clean_iif_output"
        temp_dir.mkdir(exist_ok=True)
        old_output_dir = engine.output_dir
        old_log_dir = engine.LOG_DIR
        old_log_disabled = engine.log.disabled
        engine.output_dir = temp_dir
        engine.LOG_DIR = temp_dir
        engine.log.disabled = True
        try:
            empty_path = engine.generate_iif(
                {}, {}, {}, date(2026, 8, 24),
                bs_data={},
            )
            empty_text = empty_path.read_text(encoding="utf-8")
            populated_path = engine.generate_iif(
                {},
                {
                    "8511002 · Discount 8% - Senior Day": 8.00,
                    "8512005 · Discount 8% - College Day": 4.00,
                },
                {},
                date(2026, 8, 26),
                bs_data={"donation": 5.00, "paid_out": 3.00},
                paid_in_total=12.00,
            )
            populated_text = populated_path.read_text(encoding="utf-8")
        finally:
            engine.output_dir = old_output_dir
            engine.LOG_DIR = old_log_dir
            engine.log.disabled = old_log_disabled
            for generated_file in temp_dir.iterdir():
                generated_file.unlink()
            temp_dir.rmdir()

        for conditional_text in (
            "Sales - Frozen Foods",
            "Discount 8% - Senior Day",
            "Discount 8% - College Day",
            "Outreach - Donations",
            "PAID IN:",
            "PAID OUT:",
        ):
            with self.subTest(conditional_text=conditional_text):
                self.assertNotIn(conditional_text, empty_text)

        for placeholder_text in (
            "MFG Coupons",
            "InHouse:",
            "Over/Short per Closeout Sheet",
            "Over/Short per POS (to = POS total)",
        ):
            with self.subTest(placeholder_text=placeholder_text):
                self.assertIn(placeholder_text, empty_text)

        for populated_line in (
            "Discount 8% - Senior Day\t\t8.00\tPdOut -",
            "Discount 8% - College Day\t\t4.00\tPdOut -",
            "Outreach - Donations\t\t5.00\t",
            "TBA Purchases\t\t-12.00\tPAID IN:",
            "TBA Purchases\t\t3.00\tPAID OUT:",
        ):
            with self.subTest(populated_line=populated_line):
                self.assertIn(populated_line, populated_text)

    def test_generate_iif_writes_coupon_closeout_breakdown_and_signed_difference(self):
        from datetime import date
        from pathlib import Path

        from app import pos_to_quickbooks_v2 as engine

        temp_dir = Path(__file__).parent / "_coupon_closeout_iif_output"
        temp_dir.mkdir(exist_ok=True)
        old_output_dir = engine.output_dir
        old_log_dir = engine.LOG_DIR
        old_log_disabled = engine.log.disabled
        engine.output_dir = temp_dir
        engine.LOG_DIR = temp_dir
        engine.log.disabled = True
        try:
            try:
                positive_path = engine.generate_iif(
                    {}, {}, {}, date(2026, 8, 26),
                    bs_data={
                        "vendor_coupon": 181.50,
                        "visa_mc": 100.00,
                        "offline_credit_card": -44.07,
                    },
                    misc_tba_lines=[("Unique unmapped account", 12.34)],
                    settlement_data={"visa_mc": 101.00},
                    coupon_mode="closeout",
                    coupon_closeout_total=188.25,
                    coupon_ncg_total=152.25,
                    coupon_mfg_total=36.00,
                )
                positive_text = positive_path.read_text(encoding="utf-8")
                negative_path = engine.generate_iif(
                    {}, {}, {}, date(2026, 8, 27),
                    bs_data={"vendor_coupon": 181.50},
                    coupon_mode="closeout",
                    coupon_closeout_total=175.00,
                    coupon_ncg_total=150.00,
                    coupon_mfg_total=25.00,
                )
                negative_text = negative_path.read_text(encoding="utf-8")
            except TypeError as exc:
                self.fail(f"coupon closeout IIF integration is missing: {exc}")
        finally:
            engine.output_dir = old_output_dir
            engine.LOG_DIR = old_log_dir
            engine.log.disabled = old_log_disabled
            for generated_file in temp_dir.iterdir():
                generated_file.unlink()
            temp_dir.rmdir()

        self.assertIn(
            "1250000 · Coupons Receivable\t\t152.25\tNCG Coupons",
            positive_text,
        )
        self.assertIn(
            "1250000 · Coupons Receivable\t\t36.00\tMFG Coupons",
            positive_text,
        )
        self.assertIn(
            "8314000 · FE - Cash Over/Shorts\t\t-6.75\t"
            "Over/Short per Closeout Sheet - Coupon\tAdmin",
            positive_text,
        )
        self.assertIn(
            "8314000 · FE - Cash Over/Shorts\t\t6.50\t"
            "Over/Short per Closeout Sheet - Coupon\tAdmin",
            negative_text,
        )
        card_adjustment_position = positive_text.index(
            "VISA/MC - Difference between First Data vs BS"
        )
        coupon_adjustment_position = positive_text.index(
            "Over/Short per Closeout Sheet - Coupon"
        )
        unique_tba_position = positive_text.index("Unique unmapped account")
        offline_tba_position = positive_text.index("Offline Credit Card:")
        self.assertLess(card_adjustment_position, coupon_adjustment_position)
        self.assertLess(coupon_adjustment_position, unique_tba_position)
        self.assertLess(unique_tba_position, offline_tba_position)

    def test_bs_penny_sign_is_preserved_and_offline_credit_is_bottom_tba(self):
        from datetime import date
        from pathlib import Path

        from app import pos_to_quickbooks_v2 as engine

        temp_dir = Path(__file__).parent / "_bs_sign_iif_output"
        temp_dir.mkdir(exist_ok=True)
        old_output_dir = engine.output_dir
        old_log_dir = engine.LOG_DIR
        old_log_disabled = engine.log.disabled
        engine.output_dir = temp_dir
        engine.LOG_DIR = temp_dir
        engine.log.disabled = True
        try:
            negative_path = engine.generate_iif(
                {}, {}, {}, date(2026, 8, 24),
                bs_data={"penny_round": -0.03, "offline_credit_card": -44.07},
            )
            negative_text = negative_path.read_text(encoding="utf-8")
            positive_path = engine.generate_iif(
                {}, {}, {}, date(2026, 8, 25),
                bs_data={"penny_round": 0.03},
            )
            positive_text = positive_path.read_text(encoding="utf-8")
        finally:
            engine.output_dir = old_output_dir
            engine.LOG_DIR = old_log_dir
            engine.log.disabled = old_log_disabled
            for generated_file in temp_dir.iterdir():
                generated_file.unlink()
            temp_dir.rmdir()

        self.assertIn(
            "9107000 · Miscellaneous Income\t\t0.03\t"
            "Penny Round Up for Cash Transactions",
            negative_text,
        )
        self.assertIn(
            "9107000 · Miscellaneous Income\t\t-0.03\t"
            "Penny Round Up for Cash Transactions",
            positive_text,
        )
        offline_line = (
            "4444 · TBA Purchases\t\t44.07\tOffline Credit Card:"
        )
        self.assertIn(offline_line, negative_text)
        generated_splits = [
            line for line in negative_text.splitlines()
            if line.startswith("SPL\t")
        ]
        self.assertIn(
            offline_line,
            generated_splits[-1],
        )

    def test_parse_bs_maps_offline_credit_card_as_a_negative_unique_item(self):
        from datetime import date
        from pathlib import Path

        import openpyxl

        from app import pos_to_quickbooks_v2 as engine

        workbook_path = Path(__file__).parent / "_offline_credit_bs.xlsx"
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "082426 BS"
        sheet.append([1334, "Dwr Offline Credit card", None, None, 44.07, None, "D"])
        workbook.save(workbook_path)
        workbook.close()
        try:
            parsed = engine.parse_bs_sheet(workbook_path, date(2026, 8, 24))
        finally:
            workbook_path.unlink(missing_ok=True)

        self.assertEqual(parsed["offline_credit_card"], -44.07)

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
