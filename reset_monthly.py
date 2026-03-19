"""
reset_monthly.py
----------------
Resets Paid and Verified columns to FALSE for all roommates
on the 1st of every month, ready for the new rent cycle.

Run via GitHub Actions on the 1st of every month
(see .github/workflows/cron.yml).

Required environment variables:
  GOOGLE_CREDENTIALS_JSON
  SPREADSHEET_ID
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv


# Load local .env for development runs.
_script_dir = Path(__file__).resolve().parent
_env_path = _script_dir / ".env"
load_dotenv(dotenv_path=_env_path, override=False)
if not _env_path.exists():
    load_dotenv(override=False)


def get_env(key: str, default: str = None) -> str:
    value = os.environ.get(key, default)
    if value is None:
        print(f"[ERROR] Missing required environment variable: {key}")
        sys.exit(1)
    return value


GOOGLE_CREDENTIALS = get_env("GOOGLE_CREDENTIALS_JSON")
SPREADSHEET_ID     = get_env("SPREADSHEET_ID")

COL_PAID     = 4
COL_VERIFIED = 5


def get_sheet():
    creds_dict = json.loads(GOOGLE_CREDENTIALS)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds  = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).sheet1


def main():
    print(f"[START] Monthly reset — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    sheet    = get_sheet()
    all_rows = sheet.get_all_values()

    if len(all_rows) < 2:
        print("[INFO] No data rows to reset.")
        return

    data = all_rows[1:]   # skip header
    reset_count = 0

    for i, row in enumerate(data, start=2):
        # Batch update Paid and Verified to FALSE
        sheet.update_cell(i, COL_PAID,     "FALSE")
        sheet.update_cell(i, COL_VERIFIED, "FALSE")
        name = row[1].strip() if len(row) > 1 else f"Row {i}"
        print(f"  Reset: {name}")
        reset_count += 1

    print(f"\n[DONE] Reset {reset_count} roommates for new month.")


if __name__ == "__main__":
    main()