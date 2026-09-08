from pathlib import Path


def render_need_help_control(ui) -> bool:
    """Render the main-page help button and return whether help is open."""
    state_key = "show_deposit_help"
    if ui.button(
        "❔ Need Help",
        key="need_help_control",
        help="Open or close the Daily Workbook SOP and deposit tips.",
    ):
        ui.session_state[state_key] = not bool(ui.session_state.get(state_key, False))
    return bool(ui.session_state.get(state_key, False))


def render_daily_workbook_sop(ui, *, root: Path, sop_steps: list[dict]) -> None:
    with ui.expander("📘 Daily Workbook SOP", expanded=False):
        ui.markdown(
            """
            ### How to Build the Daily Workbook
            Follow these steps in order for each deposit date. The Daily Deposit template is the master workbook; SMS reports supply the source data that is copied or moved into it.

            **Important:** keep every report on the same deposit date, and do not continue past the Sales check if the totals do not match exactly.
            """
        )

        for index, step in enumerate(sop_steps):
            expanded = index == 0
            with ui.expander(step["title"], expanded=expanded):
                ui.markdown(step["body"])

                if step["title"].startswith("Step 1 ·"):
                    step1_folder_image = root / "assets" / "step1_daily_deposit_folder.png"
                    if step1_folder_image.exists():
                        ui.image(
                            str(step1_folder_image),
                            caption="Step 1 · Daily Deposit folder — open TEMPLATE - SubDept Single Total Report.",
                            use_container_width=True,
                        )
                    else:
                        ui.info(
                            "Step 1 Daily Deposit folder image is not installed. "
                            "Add assets/step1_daily_deposit_folder.png to show it here."
                        )

                if step["title"].startswith("Step 2 ·"):
                    step2a_export_image = root / "assets" / "step2a_sms_sales_export.png"
                    step2a_paste_image = root / "assets" / "step2a_subdept_single_paste.png"

                    if step2a_export_image.exists():
                        ui.image(
                            str(step2a_export_image),
                            caption=(
                                "Step 2 · SMS export: after launching the Sub-department Single Total report, "
                                "export it to Excel and copy the report data from the first sub-department through the final department."
                            ),
                            use_container_width=True,
                        )
                    else:
                        ui.info(
                            "Step 2 SMS export example is not installed. "
                            "Add assets/step2a_sms_sales_export.png to show it here."
                        )

                    if step2a_paste_image.exists():
                        ui.image(
                            str(step2a_paste_image),
                            caption=(
                                "Step 2 · Daily Deposit template: paste the exported sales data starting in cell A1 "
                                "of the SubDept Single tab."
                            ),
                            use_container_width=True,
                        )
                    else:
                        ui.info(
                            "Step 2 paste example is not installed. "
                            "Add assets/step2a_subdept_single_paste.png to show it here."
                        )

                    ui.warning(
                        "**⚠️ Unexpected / Unique Item**\n\n"
                        "The example report contains **23 · Refunded Discounts**. This is not a normal Sales item and "
                        "would ordinarily be expected in the **HASH** process. If an unexpected item appears in the "
                        "Sub-department Single Total report, do not assume it should simply be kept or deleted. "
                        "Drill into the activity in SMS to determine why it appeared, confirm whether it is also represented "
                        "in the HASH report, and ask the Finance team for help if the source is unclear before completing the deposit.",
                        icon="⚠️",
                    )

                if step["title"].startswith("Step 2a"):
                    sales_check_images = [
                        root / "assets" / "sub_department_sales_report.png",
                        root / "assets" / "department_sales_summary_report.png",
                    ]

                    available_sales_check_images = [
                        image_path for image_path in sales_check_images if image_path.exists()
                    ]

                    if available_sales_check_images:
                        ui.caption(
                            "Sales-check example from SMS. "
                            "The source report is shown in multiple images because the report is longer than one screen. "
                            "The highlighted total at the bottom must match the green Sales Total in the Daily Deposit workbook exactly."
                        )

                        image_captions = {
                            "sub_department_sales_report.png":
                                "SMS Sub-department Single Total Report · Part 1",
                            "department_sales_summary_report.png":
                                "SMS Sub-department Single Total Report · Part 2 · Verify the highlighted Total",
                        }

                        for image_path in available_sales_check_images:
                            ui.image(
                                str(image_path),
                                caption=image_captions.get(image_path.name, "SMS Sales-check example"),
                                use_container_width=True,
                            )

                        missing_images = [
                            image_path.name for image_path in sales_check_images if not image_path.exists()
                        ]

                        if missing_images:
                            ui.warning(
                                "One Sales Check example image is missing from the assets folder:\n\n"
                                + "\n".join(f"• {name}" for name in missing_images),
                                icon="⚠️",
                            )
                    else:
                        ui.error(
                            "Sales Check example images could not be found.\n\n"
                            "The app expects these files inside the assets folder:\n\n"
                            "• sub_department_sales_report.png\n\n"
                            "• department_sales_summary_report.png",
                            icon="🚫",
                        )

                if step["title"].startswith("Step 3"):
                    milk_bottle_returns_example = root / "assets" / "milk_bottle_returns_example.png"
                    if milk_bottle_returns_example.exists():
                        ui.caption(
                            "Milk Bottle Returns example from SMS. Add together the highlighted return amounts for all "
                            "Milk Bottle Return items, then enter the combined total into cell M1 on SubDept Sales Report."
                        )
                        ui.image(
                            str(milk_bottle_returns_example),
                            caption=(
                                "Step 3 · Add all highlighted Milk Bottle Return amounts before entering the total in M1."
                            ),
                            use_container_width=True,
                        )
                    else:
                        ui.info(
                            "Milk Bottle Returns example image is not installed. "
                            "Add assets/milk_bottle_returns_example.png to show it here."
                        )

                if step["title"].startswith("Step 4"):
                    step4_discounts_image = root / "assets" / "step4_discounts_move_copy.png"
                    if step4_discounts_image.exists():
                        ui.image(
                            str(step4_discounts_image),
                            caption=(
                                "Step 4 · Move or copy the exported Discounts worksheet into the XXXXXX Discounts "
                                "location, then rename it to the current deposit date."
                            ),
                            use_container_width=True,
                        )
                    else:
                        ui.info(
                            "Step 4 Discounts Move or Copy example is not installed. "
                            "Add assets/step4_discounts_move_copy.png to show it here."
                        )

                if step["title"].startswith("Step 5"):
                    step5_hash_image = root / "assets" / "step5_hash_move_copy.png"
                    if step5_hash_image.exists():
                        ui.image(
                            str(step5_hash_image),
                            caption=(
                                "Step 5 · Move or copy the exported HASH worksheet into the XXXXXX HASH "
                                "location, then rename it to the current deposit date."
                            ),
                            use_container_width=True,
                        )
                    else:
                        ui.info(
                            "Step 5 HASH Move or Copy example is not installed. "
                            "Add assets/step5_hash_move_copy.png to show it here."
                        )

                if step["title"].startswith("Step 6"):
                    step6_bs_image = root / "assets" / "step6_bs_move_copy.png"
                    if step6_bs_image.exists():
                        ui.image(
                            str(step6_bs_image),
                            caption=(
                                "Step 6 · Move or copy the exported Balance Sheet worksheet into the XXXXXX BS "
                                "location, then rename it to the current deposit date."
                            ),
                            use_container_width=True,
                        )
                    else:
                        ui.info(
                            "Step 6 Balance Sheet Move or Copy example is not installed. "
                            "Add assets/step6_bs_move_copy.png to show it here."
                        )

                if step["title"].startswith("Step 7"):
                    daily_workbook_example = root / "assets" / "daily_workbook_example.png"
                    daily_workbook_example_pdf = root / "assets" / "daily_workbook_example.pdf"
                    if daily_workbook_example.exists():
                        ui.image(
                            str(daily_workbook_example),
                            caption="Approved Daily Workbook example",
                            use_container_width=True,
                        )
                    elif daily_workbook_example_pdf.exists():
                        ui.caption("Use the approved PDF in the assets folder for the final visual comparison.")
                        ui.download_button(
                            "Open approved workbook example PDF",
                            data=daily_workbook_example_pdf.read_bytes(),
                            file_name=daily_workbook_example_pdf.name,
                            mime="application/pdf",
                            key="daily_workbook_example_pdf",
                            use_container_width=True,
                        )
                    else:
                        ui.info(
                            "The Daily Workbook example is not installed in the repo assets folder. "
                            "Add assets/daily_workbook_example.png or assets/daily_workbook_example.pdf to show it here."
                        )

        ui.markdown("### Daily Card Settlement Report")
        ui.markdown(
            """
            After the Daily Workbook is complete, prepare the separate **Daily Card Settlement Report** for the same date. The automation uses only the **Processed Net Amount** column for **VISA/MC, Discover, AMEX, Debit Card, and EBT Cash/Food Stamp**.
            """
        )

        with ui.expander("View Daily Card Settlement Example", expanded=False):
            ui.caption(
                "Your Daily Card Settlement Report should look like this. "
                "The automation uses the Processed Net Amount column."
            )
            daily_card_settlement_example = root / "assets" / "daily_card_settlement_example.png"
            if daily_card_settlement_example.exists():
                ui.image(str(daily_card_settlement_example), use_container_width=True)
            else:
                ui.info("Daily Card Settlement example image is not installed in the repo assets folder.")

        ui.markdown(
            """
            ### Before You Run
            Confirm that the Daily Workbook and Daily Card Settlement Report are for the same date, all five required workbook roles are detected, and the settlement report shows as verified. Then select **Validate & Build Deposit**.

            The app compares each card settlement amount with the matching BS tender total. Review any red **✕** before importing the IIF into QuickBooks.
            """
        )


def render_known_exceptions(ui) -> None:
    with ui.expander("💡 Tips & Known Exceptions · WIP", expanded=False):
        ui.caption(
            "Working guidance for unusual situations. This section will continue to grow as Finance documents more exceptions."
        )

        ui.markdown(
            """
            <div class="hwfc-tip-card attention">
              <div class="hwfc-tip-title">⚠️ Unique / unrecognized items → TBA</div>
              <div class="hwfc-tip-body">
                Any unique item the automation does not recognize is coded as <strong>TBA</strong> at the bottom of the generated IIF.
                Review those lines and change them to the correct QuickBooks account before final posting. If the correct coding is unclear,
                research the SMS/source reports and ask Finance before posting.
              </div>
            </div>

            <div class="hwfc-tip-card info">
              <div class="hwfc-tip-title">🔎 Unexpected SMS items</div>
              <div class="hwfc-tip-body">
                If an item appears in a report where it normally does not belong, investigate the source activity in SMS before manually
                changing the workbook. For example, if Refunded Discounts appears in the Step 2 Sales report, confirm whether it is also
                represented in HASH and involve Finance if the reason is unclear.
              </div>
            </div>

            <div class="hwfc-tip-card info">
              <div class="hwfc-tip-title">💵 Paid Out</div>
              <div class="hwfc-tip-body">
                Paid Out does not appear every day. When it is detected on the <strong>Balance Sheet</strong>, the automation carries that
                amount into the generated IIF, similar to <strong>Paid-Ins</strong> and <strong>Pass Through Donations</strong>.
                Paid Out is treated as a <strong>negative amount</strong>, so it reduces the QuickBooks deposit total.
                <div class="hwfc-tip-example">Example: $47.06 Paid Out → -$47.06 deposit effect</div>
              </div>
            </div>

            <div class="hwfc-tip-card attention">
              <div class="hwfc-tip-title">⚠️ Important Disclosures &amp; Automation Limitations</div>
              <div class="hwfc-tip-body">
                <strong>1. SMS-Based Automation</strong><br>
                The automated IIF is built from <strong>SMS data</strong>. It does not automatically include every actual daily adjustment
                documented on the <strong>Store Closeout</strong> sheet provided by the Front End Manager.<br><br>
                <strong>2. Store Closeout Review Is Required</strong><br>
                Import the generated IIF into <strong>QuickBooks first</strong>, then compare the deposit to the Store Closeout and manually
                adjust the deposit in QuickBooks for Cash Over / Short, additional cash differences, Plants / Dept. Market Purchases,
                Payroll cash activity, Comments / Notes / Issues from Front End, safe overage or shortage, and any other documented amount
                that changes the actual daily deposit.<br><br>
                <strong>3. Automation Does Not Replace Final Review</strong><br>
                A successfully generated and balanced IIF does not necessarily mean the final QuickBooks deposit matches the actual Store
                Closeout. The deposit is not complete until required Store Closeout adjustments are made in QuickBooks and the final deposit
                has been reviewed for accuracy.
              </div>
            </div>

            <div class="hwfc-tip-card success">
              <div class="hwfc-tip-title">✅ QuickBooks final review</div>
              <div class="hwfc-tip-body">
                Review all TBA lines, confirm Sales / Discounts / HASH checks, review card settlement differences, import the IIF, apply the
                Store Closeout adjustments directly in QuickBooks, and confirm the final deposit is correct before posting.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        ui.markdown(
            """
            **Future tips to document**
            - Date mismatch handling
            - When to stop and ask Finance
            - Common TBA mappings once approved
            - QuickBooks pre-post review reminders
            """
        )
