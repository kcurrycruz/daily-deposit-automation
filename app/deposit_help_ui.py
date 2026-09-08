def render_sidebar_help(ui) -> None:
    """Render current deposit guidance in a fixed sidebar help area."""
    ui.markdown("## Need Help?")
    ui.caption("Quick reference for preparing and reviewing today’s deposit.")

    workbook_tab, tips_tab = ui.tabs(["Daily Workbook", "Tips & Exceptions"])

    with workbook_tab:
        ui.markdown(
            """
            #### Build the Daily Workbook

            1. Start with **TEMPLATE - SubDept Single Total Report** from the approved Daily Deposit folder.
            2. Paste the SMS **Sub-department Single Total** sales export into the workbook beginning at the first department row. Confirm the workbook Sales Total matches SMS exactly.
            3. Add the SMS store-coupon report to **SubDept Coupon (Local Discount)**.
            4. Total all Milk Bottle Return items and enter that amount in **M1** on SubDept Sales Report.
            5. Move the exported **Discounts**, **HASH**, and **Balance Sheet (BS)** worksheets into the workbook. Use the deposit date in the tab names. A plain **Hash** tab is also accepted when its contents can be identified safely.
            6. Confirm the workbook contains all five required areas: **Sales, Coupons, Discounts, Balance Sheet, and HASH**.

            #### Card Settlement

            Upload the separate Card Settlement report for the **same deposit date**. The app uses only **Processed Net Amount** for VISA/MC, Discover, AMEX, Debit Card, and EBT.

            #### Before continuing

            Both files must be uploaded. Review any date, missing-sheet, or settlement-column warning before working through Today’s Deposit Steps.
            """
        )

    with tips_tab:
        ui.markdown(
            """
            #### Guided steps

            - The app shows only the activities detected for that deposit. **Closeout Sheet is always last**.
            - For Member Shares, Coupons Receivable, Donations, Paid In, Paid Out, and Closeout activity, choose either **Breakdown in app** or **Finish manually in QuickBooks**.
            - Editing a completed step keeps the entries already supplied. The final IIF action appears only after every required step is complete.
            - If an activity was marked for manual QuickBooks work, finish it there; the app will explain why an in-app review action is unavailable.

            #### Important amount rules

            - **Paid In is always positive. Paid Out is always negative.**
            - Donation rows default to **$100** and remain editable.
            - New member-plan defaults are the plan deposits: **1 year $10, 3 year $15, 5 year $10**. Existing-plan defaults use the normal monthly payment and remain editable.
            - Books are combined with **Magazines** in the sales mapping.

            #### CDTA Star Pass and TBA

            - Department 22 positive multiples of **$30** post to Promotional Sales with a **CDTA Star Pass** memo.
            - Any other Department 22 amount, such as **-$20**, goes to **TBA Purchases** at the bottom instead of stopping the deposit.
            - Other unique or unrecognized items also go to **TBA**. Review every TBA line and assign the correct QuickBooks account before final posting.

            #### Final review

            Confirm the workbook checks, card-settlement comparison, Coupons Receivable, optional activity breakdowns, and final Closeout Sheet total before downloading the IIF. Import the IIF, review the deposit in QuickBooks, and do not post until all remaining manual items are complete.
            """
        )
