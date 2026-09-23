from pathlib import Path


SMS_EXPORT_SAVE_DETAILS = {
    "Step 1 · Sales": (5, "MMDDYY Sales", "092126 Sales"),
    "Step 2 · Coupons": (5, "MMDDYY Coupon", "092126 Coupon"),
    "Step 3 · Discounts": (3, "MMDDYY Discount", "092126 Discount"),
    "Step 4 · HASH": (4, "MMDDYY Hash", "092126 Hash"),
    "Step 5 · Balance Sheet": (3, "MMDDYY BS", "092126 BS"),
    "Step 6 · Milk Bottles": (4, "MMDDYY milk bottles", "092126 milk bottles"),
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
                    save_button_instruction, save_dialog_instructions = (
                        save_instruction_parts
                    )
                    ui.markdown(save_button_instruction)

                    if step["title"].startswith("Step 1 · Sales"):
                        save_button_image = (
                            root / "assets" / "sms_save_export_button.png"
                        )
                        if save_button_image.exists():
                            ui.image(
                                str(save_button_image),
                                caption="Step 5: Select the yellow Save/Export button.",
                                use_container_width=True,
                            )
                        else:
                            ui.info("The Step 5 Save/Export reference image is unavailable.")

                    ui.markdown(save_dialog_instructions)

                    if step["title"].startswith("Step 1 · Sales"):
                        save_dialog_image = (
                            root / "assets" / "sms_report_save_dialog.png"
                        )
                        if save_dialog_image.exists():
                            ui.image(
                                str(save_dialog_image),
                                caption=(
                                    "Step 7 reference: confirm the file name, export folder, "
                                    "and Excel File (xls), then select OK."
                                ),
                                use_container_width=True,
                            )
                        else:
                            ui.info("The Step 7 Report save reference image is unavailable.")

                if step["title"].startswith("Step 6 · Milk Bottles"):
                    milk_bottle_returns_example = root / "assets" / "milk_bottle_returns_example.png"
                    if milk_bottle_returns_example.exists():
                        ui.caption(
                            "Milk Bottles report in SMS. The app uses Net Sales from returned Milk Bottle items."
                        )
                        ui.image(
                            str(milk_bottle_returns_example),
                            caption=(
                                "Milk Bottles: export the report after selecting the deposit date and report settings."
                            ),
                            use_container_width=True,
                        )
                    else:
                        ui.info(
                            "Milk Bottle Returns example image is not installed. "
                            "Add assets/milk_bottle_returns_example.png to show it here."
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
                If an item appears in a report where it normally does not belong, investigate the source activity in SMS before changing
                the deposit. For example, if Refunded Discounts appears in the Sales report, confirm whether it is also
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
