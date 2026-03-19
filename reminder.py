"""
reminder.py
-----------
Reads the Google Sheet and sends SMS reminders via Fast2SMS
to all roommates who have NOT completed both Paid + Verified.

Stops sending when BOTH Paid=TRUE AND Verified=TRUE for a person.
Either one alone is not enough.

Run daily via GitHub Actions cron (see .github/workflows/cron.yml).

Required GitHub Secrets (environment variables):
  FAST2SMS_API_KEY        - Your Fast2SMS API key
  GOOGLE_CREDENTIALS_JSON - Full service account JSON as a single-line string
  SPREADSHEET_ID          - Google Sheet ID (from its URL)
  CONFIRMATION_BASE_URL   - e.g. https://your-app.onrender.com
  APARTMENT_NAME          - e.g. Mandakini Garden
  REMINDER_STOP_DAY       - Day of month after which reminders stop (default: 15)
"""

import os
import sys
import json
import requests
from datetime import datetime
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv


# ── Environment variables ─────────────────────────────────────────────────────

# Load local .env for development runs.
# In CI/production, real environment variables are still used.
_script_dir = Path(__file__).resolve().parent
_env_path = _script_dir / ".env"
load_dotenv(dotenv_path=_env_path, override=False)
if not _env_path.exists():
    load_dotenv(override=False)  # fallback: current working directory

def get_env(key: str, default: str = None) -> str:
    value = os.environ.get(key, default)
    if value is None:
        print(f"[ERROR] Missing required environment variable: {key}")
        sys.exit(1)
    return value


FAST2SMS_API_KEY      = get_env("FAST2SMS_API_KEY")
GOOGLE_CREDENTIALS    = get_env("GOOGLE_CREDENTIALS_JSON")
SPREADSHEET_ID        = get_env("SPREADSHEET_ID")
CONFIRMATION_BASE_URL = get_env("CONFIRMATION_BASE_URL").rstrip("/")
APARTMENT_NAME        = get_env("APARTMENT_NAME", "your apartment")
REMINDER_STOP_DAY     = int(get_env("REMINDER_STOP_DAY", "15"))


# ── Google Sheet column positions (1-indexed) ─────────────────────────────────
#
#  A        B      C       D      E          F
#  row_id | Name | Phone | Paid | Verified | Last Reminded
#
COL_ROW_ID        = 1
COL_NAME          = 2
COL_PHONE         = 3
COL_PAID          = 4
COL_VERIFIED      = 5
COL_LAST_REMINDED = 6


# ── Sheets client ─────────────────────────────────────────────────────────────

def get_sheet():
    creds_dict = json.loads(GOOGLE_CREDENTIALS)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds  = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).sheet1


# ── Helpers ───────────────────────────────────────────────────────────────────

def pad_row(row: list, length: int = 6) -> list:
    return row + [""] * max(0, length - len(row))


def should_run_today() -> bool:
    today = datetime.now().day
    if today > REMINDER_STOP_DAY:
        print(f"[INFO] Day {today} > stop day {REMINDER_STOP_DAY}. No reminders today.")
        return False
    return True


def is_fully_done(row: list) -> bool:
    """Stop reminders only when BOTH Paid AND Verified are TRUE."""
    paid     = str(row[COL_PAID - 1]).strip().upper()     == "TRUE"
    verified = str(row[COL_VERIFIED - 1]).strip().upper() == "TRUE"
    return paid and verified


# ── SMS ───────────────────────────────────────────────────────────────────────

def send_sms(phone: str, name: str, row_id: str) -> dict:
    confirmation_url = f"{CONFIRMATION_BASE_URL}/confirm?id={row_id}"
    message = (
        f"Hey {name}, please pay the {APARTMENT_NAME} rent this month. "
        f"Once paid, tap this link to confirm (one tap marks you as paid): "
        f"{confirmation_url}"
    )
    headers = {
        "authorization": FAST2SMS_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "message":       message,
        "language":      "english",
        "route":         "q",
        "numbers":       phone,
    }
    try:
        resp = requests.post(
            "https://www.fast2sms.com/dev/bulkV2",
            headers=headers,
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        return {"return": False, "message": str(exc)}


def update_last_reminded(sheet, row_index: int):
    sheet.update_cell(row_index, COL_LAST_REMINDED, datetime.now().strftime("%Y-%m-%d %H:%M"))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not should_run_today():
        return

    print(f"[START] {datetime.now().strftime('%Y-%m-%d %H:%M')} — Rent reminder job")
    sheet    = get_sheet()
    all_rows = sheet.get_all_values()

    if len(all_rows) < 2:
        print("[INFO] No data rows found in sheet.")
        return

    data          = all_rows[1:]   # row 0 is header
    sent          = 0
    skipped       = 0
    errors        = 0

    for i, raw_row in enumerate(data, start=2):  # sheet rows start at 1; row 1 = header
        row    = pad_row(raw_row)
        row_id = row[COL_ROW_ID - 1].strip()
        name   = row[COL_NAME - 1].strip()
        phone  = row[COL_PHONE - 1].strip()

        if not all([row_id, name, phone]):
            print(f"[SKIP] Row {i} — incomplete data.")
            continue

        if is_fully_done(row):
            print(f"[SKIP] {name} — Paid ✅  Verified ✅")
            skipped += 1
            continue

        print(f"[SEND] {name} ({phone})")
        result = send_sms(phone, name, row_id)

        if result.get("return") is True:
            update_last_reminded(sheet, i)
            print(f"       ✅ Sent.")
            sent += 1
        else:
            print(f"       ❌ Error: {result.get('message', result)}")
            errors += 1

    print(f"\n[DONE] Sent={sent}  Skipped={skipped}  Errors={errors}")


if __name__ == "__main__":
    main()