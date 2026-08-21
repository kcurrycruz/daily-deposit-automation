
# HWFC Daily Deposit Automation

## Project layout

```text
daily-deposit-automation/
├── app/
│   ├── HWFC_Deposit_Launcher.pyw
│   └── pos_to_quickbooks_v2.py
├── output/
│   ├── qb_imports/
│   └── summaries/
├── logs/
│   └── last_run_status.txt   # created after a run
├── build/
└── README.md
```

## Generated files

- QuickBooks IIF files: `output/qb_imports/`
- Excel summaries: `output/summaries/`
- Last-run status: `logs/last_run_status.txt`

The folders are resolved relative to the project when running from source,
and relative to `HWFC_Deposit.exe` when running the PyInstaller build.

## Existing source-data locations

This restructure does **not** change the POS and shared-drive source report paths.
Those remain configured inside `app/pos_to_quickbooks_v2.py`.

## Build

Run from the `app` folder:

```bat
C:\Users\karlcruz\AppData\Local\Python\pythoncore-3.14-64\python.exe -m PyInstaller --clean --onedir --windowed --name HWFC_Deposit --add-data "pos_to_quickbooks_v2.py;." HWFC_Deposit_Launcher.pyw
```

After building, the executable will create/use its own:

```text
output\qb_imports
output\summaries
logs
```

next to `HWFC_Deposit.exe`.
