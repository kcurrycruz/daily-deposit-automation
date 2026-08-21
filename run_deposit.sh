#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ $# -eq 0 ]; then
  python app/pos_to_quickbooks_v2.py
else
  python app/pos_to_quickbooks_v2.py --date "$1"
fi
