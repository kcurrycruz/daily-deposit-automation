[README.md](https://github.com/user-attachments/files/31309520/README.md)
# HWFC Daily Deposit Automation — Codespaces Edition

This version is designed to run away from the HWFC local Windows machine.

## Daily workflow

1. Open this repository in GitHub.
2. Choose **Code → Codespaces → Create codespace on main**.
3. In the Codespace file explorer, upload the day's source files into:

   `input/daily_reports/`

4. Open the terminal.
5. Run the deposit for a specific date:

   ```bash
   ./run_deposit.sh 08/20/26
   ```

   Or run without a date to use yesterday:

   ```bash
   ./run_deposit.sh
   ```

6. Review the terminal validation results.
7. Download the generated files from:

   - `output/qb_imports/` — QuickBooks IIF
   - `output/summaries/` — Excel summary
   - `logs/last_run_status.txt` — run status

8. Import the IIF into QuickBooks on the HWFC computer.

## Important privacy rule

Do **not** commit daily sales, discount, credit-card, or deposit output files.

The repository `.gitignore` is configured so the contents of:

- `input/daily_reports/`
- `output/qb_imports/`
- `output/summaries/`
- `logs/`

are ignored by Git.

For real financial data, make the GitHub repository **private**.

## What changed from the Windows version

The cloud version no longer depends on:

- `C:\POS_Reports\Daily`
- mapped `S:` drives
- local Python
- Tkinter launcher
- PyInstaller
- Xcitium/Comodo allowing Python file writes

Everything the engine reads and writes lives inside the remote Codespace.

## Input files

Upload the normal daily Excel workbook and any applicable CSV exports into one folder:

`input/daily_reports/`

The engine detects Excel, discounts, coupons, and Commerce Control Center CSV files from there.

## Codespaces setup

The `.devcontainer/devcontainer.json` file automatically provides Python 3.12 and installs `openpyxl`.

## Validation

GitHub Actions runs a lightweight syntax check whenever the Python engine changes. It does not process financial data.
