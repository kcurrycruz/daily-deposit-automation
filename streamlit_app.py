# HWFC Daily Deposit - Sales Check image fix
#
# Replace the existing Step 2B image-display block in streamlit_app.py
# with this block. It expects the two files already in:
#   assets/sub_department_sales_report.png
#   assets/department_sales_summary_report.png

if step["title"].startswith("Step 2B"):
    # ---------------------------------------------------------
    # SALES CHECK EXAMPLE IMAGES
    # ---------------------------------------------------------

    sales_check_images = [
        ROOT / "assets" / "sub_department_sales_report.png",
        ROOT / "assets" / "department_sales_summary_report.png",
    ]

    available_sales_check_images = [
        image_path
        for image_path in sales_check_images
        if image_path.exists()
    ]

    if available_sales_check_images:
        st.caption(
            "Sales-check example from SMS. "
            "The source report is shown in multiple images because "
            "the report is longer than one screen. "
            "The highlighted total at the bottom must match the "
            "green Sales Total in the Daily Deposit workbook exactly."
        )

        image_captions = {
            "sub_department_sales_report.png":
                "SMS Sub-department Single Total Report · Part 1",
            "department_sales_summary_report.png":
                "SMS Sub-department Single Total Report · Part 2 · Verify the highlighted Total",
        }

        for image_path in available_sales_check_images:
            st.image(
                str(image_path),
                caption=image_captions.get(
                    image_path.name,
                    "SMS Sales-check example",
                ),
                use_container_width=True,
            )

        missing_images = [
            image_path.name
            for image_path in sales_check_images
            if not image_path.exists()
        ]

        if missing_images:
            st.warning(
                "One Sales Check example image is missing from the "
                "assets folder:\n\n"
                + "\n".join(
                    f"• {name}" for name in missing_images
                ),
                icon="⚠️",
            )

    else:
        st.error(
            "Sales Check example images could not be found.\n\n"
            "The app expects these files inside the assets folder:\n\n"
            "• sub_department_sales_report.png\n\n"
            "• department_sales_summary_report.png",
            icon="🚫",
        )
