from pathlib import Path


def render_need_help_label(ui) -> None:
    """Render the static main-page help label."""
    ui.markdown("### ❔ Need Help")


def render_daily_workbook_sop(ui, *, root: Path, sop_steps: list[dict]) -> None:
    with ui.expander("📘 Export & Upload Guide", expanded=False):
        ui.markdown(
            """
            ### Export the six SMS reports
            For one deposit date, export exactly **Sales, Coupons, Discounts, HASH, Balance Sheet,** and **Milk Bottles** from SMS. Upload all six exports together, then upload the separate **Daily Card Settlement Report**.

            **Date check:** every SMS export and the card settlement report must be for the same date. The app validates the dates before it prepares the IIF.
            """
        )

        for index, step in enumerate(sop_steps):
            expanded = index == 0
            with ui.expander(step["title"], expanded=expanded):
                ui.markdown(step["body"])

                if step["title"].startswith("Step 1 · Sales"):
                    step2a_export_image = root / "assets" / "step2a_sms_sales_export.png"
                    if step2a_export_image.exists():
                        ui.image(
                            str(step2a_export_image),
                            caption=(
                                "Sales report in SMS: select the report date and ranges, select Launch, then export."
                            ),
                            use_container_width=True,
                        )
                    else:
                        ui.info(
                            "Sales SMS export example is not installed. "
                            "Add assets/step2a_sms_sales_export.png to show it here."
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

            The app compares each card settlement amount with the matching Balance Sheet tender total. Review any red **✕** before importing the IIF into QuickBooks. Your dated report is generated after the IIF is complete.
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
