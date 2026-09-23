from pathlib import Path


SMS_EXPORT_SAVE_DETAILS = {
    "Step 1 · Sales": (5, "MMDDYY Sales", "092126 Sales"),
    "Step 2 · Coupons": (5, "MMDDYY Coupons", "092126 Coupons"),
    "Step 3 · Discounts": (3, "MMDDYY Discount", "092126 Discount"),
    "Step 4 · HASH": (4, "MMDDYY Hash", "092126 Hash"),
    "Step 5 · Balance Sheet": (3, "MMDDYY BS", "092126 BS"),
    "Step 6 · Milk Bottles": (4, "MMDDYY milk bottles", "092126 milk bottles"),
}

SMS_REPORT_SAVE_IMAGES = {
    "Step 1 · Sales": "sms_report_save_dialog.png",
    "Step 2 · Coupons": "sms_coupon_report_save_dialog.png",
    "Step 3 · Discounts": "sms_discount_report_save_dialog.png",
    "Step 4 · HASH": "sms_hash_report_save_dialog.png",
    "Step 5 · Balance Sheet": "sms_bs_report_save_dialog.png",
    "Step 6 · Milk Bottles": "sms_milk_bottles_report_save_dialog.png",
}


def _sms_export_save_instruction_parts(step_title: str) -> tuple[str, str] | None:
    details = SMS_EXPORT_SAVE_DETAILS.get(step_title)
    if details is None:
        return None

    first_step, filename, example = details
    return (
        f"{first_step}. Select the yellow **Save/Export** button on the report toolbar.",
        f"""
{first_step + 1}. In the **Report save** window, enter:
   - **File name:** `{filename}` (example: `{example}`)
   - **Directory:** `M:\\export\\SMSExport\\`
   - **File type:** **Excel File (xls)**
{first_step + 2}. Select **OK**.
""".strip(),
    )


def render_need_help_label(ui) -> None:
    """Render the static main-page help label."""
    ui.markdown("### ❔ Need Help")


def render_daily_workbook_sop(ui, *, root: Path, sop_steps: list[dict]) -> None:
    with ui.expander("📘 SOP - Export and Upload Guide", expanded=False):
        ui.markdown(
            """
            ### Export the six SMS reports
            For one deposit date, export exactly **Sales, Coupons, Discounts, HASH, Balance Sheet,** and **Milk Bottles** from SMS. Upload all six exports together, then upload the separate **Daily Card Settlement Report**.

            **Date check:** every SMS export and the card settlement report must be for the same date. The app validates the dates before it prepares the IIF.

            **Filename note:** use the naming formats shown in each step. The app identifies each report from its contents, so capitalization differences will not prevent detection, but consistent names make the files easier to organize and review.
            """
        )

        for index, step in enumerate(sop_steps):
            expanded = index == 0
            with ui.expander(step["title"], expanded=expanded):
                ui.markdown(step["body"])
                save_instruction_parts = _sms_export_save_instruction_parts(
                    step["title"]
                )
                if save_instruction_parts is not None:
                    save_step_number = SMS_EXPORT_SAVE_DETAILS[step["title"]][0]
                    save_button_instruction, save_dialog_instructions = (
                        save_instruction_parts
                    )
                    ui.markdown(save_button_instruction)

                    save_button_image = root / "assets" / "sms_save_export_button.png"
                    if save_button_image.exists():
                        ui.image(
                            str(save_button_image),
                            caption=(
                                f"Step {save_step_number}: Select the yellow "
                                "Save/Export button."
                            ),
                            use_container_width=True,
                        )
                    else:
                        ui.info(
                            f"The Step {save_step_number} Save/Export reference "
                            "image is unavailable."
                        )

                    ui.markdown(save_dialog_instructions)

                    save_dialog_filename = SMS_REPORT_SAVE_IMAGES.get(step["title"])
                    if save_dialog_filename is not None:
                        save_dialog_image = root / "assets" / save_dialog_filename
                        if save_dialog_image.exists():
                            ui.image(
                                str(save_dialog_image),
                                caption=(
                                    f"Step {save_step_number + 2} reference: confirm the "
                                    "file name, export folder, "
                                    "and Excel File (xls), then select OK."
                                ),
                                use_container_width=True,
                            )
                        else:
                            ui.info(
                                f"The Step {save_step_number + 2} Report save reference "
                                "image is unavailable."
                            )

        ui.markdown(
            """
            ### Milk Bottles
            The app totals **returned-item Net Sales** from the Milk Bottles export and combines it with **BS code 910** to create the final IIF line.
            """
        )

        ui.markdown("### Daily Card Settlement Report")
        ui.markdown(
            """
            Export and upload the separate **Daily Card Settlement Report** for the same date as the six SMS reports. The automation uses the **Processed Net Amount** column for **VISA/MC, Discover, AMEX, Debit Card, and EBT Cash/Food Stamp**.
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
            Confirm that all six SMS reports and the Daily Card Settlement Report are for the same date. Resolve any date or report-validation message, then select **Validate & Prepare IIF**.

            The app compares each card settlement amount with the matching Balance Sheet tender total. Review any red **✕** before importing the IIF into QuickBooks. Your dated report is downloadable only after a successful IIF.
            """
        )


def render_known_exceptions(ui) -> None:
    with ui.expander("💡 Tips & Known Exceptions", expanded=False):
        ui.caption(
            "Open the topic that matches the situation you are reviewing."
        )

        with ui.expander("Unique / unrecognized items → TBA", expanded=False):
            ui.markdown(
                """
                Any unique item the automation does not recognize is coded as **TBA** in the generated IIF. Review every TBA line and select the correct QuickBooks account before posting. If the correct coding is unclear, research the SMS source report and ask Finance before importing.
                """
            )

        with ui.expander("Unexpected SMS items", expanded=False):
            ui.markdown(
                """
                If an item appears in a report where it normally does not belong, investigate the source activity in SMS before changing the deposit. For example, if Refunded Discounts appears in the Sales report, confirm whether it is also represented in HASH and involve Finance if the reason is unclear.
                """
            )

        with ui.expander("Occasional daily activity", expanded=False):
            ui.markdown(
                """
                **Membership Revenue, Donations, Paid In, and Paid Out** may not appear every day. When one is detected, the app adds the appropriate guided step so you can review the amount, choose how it should be handled, and provide any required member name or QuickBooks account.

                Paid Out reduces the deposit. The other activities follow the transaction direction detected from the source reports. Always confirm the selected account, member information, description, and amount before saving the step.
                """
            )

        with ui.expander("Closeout Sheet reconciliation", expanded=False):
            ui.markdown(
                """
                The app now supports the full Closeout Sheet workflow. Enter the actual Closeout amounts for **Cash, Checks, Donations, Charge (House), Offline ZON, Vendor Coupons, Paid In, and Paid Out**.

                The same workflow also supports **Payroll check cashing, Plants / Market Purchases, Safe overage or shortage,** and **Custom Closeout adjustments**. Enter the required **Final Closeout Sheet Deposit Total**, review the calculated differences, and approve a final POS adjustment only after confirming it against the paper Closeout Sheet.
                """
            )

        with ui.expander("QuickBooks final review", expanded=False):
            ui.markdown(
                """
                Before importing, review all TBA lines, confirm the Sales / Discounts / HASH checks, resolve card-settlement differences, and verify the completed Closeout Sheet reconciliation. Download both the **QuickBooks IIF** and the **SubDept Single Total Report**, import the IIF, and confirm the final deposit is correct before posting.
                """
            )
