"""
app.py
------
Flask web app for payment confirmation links.
When a roommate taps the confirmation link in the SMS,
this endpoint auto-marks them as Paid=TRUE in the Google Sheet.
No button click needed — the GET request itself is the confirmation.

Required environment variables (same as reminder.py):
  GOOGLE_CREDENTIALS_JSON
  SPREADSHEET_ID
  APARTMENT_NAME
"""

import os
import sys
import json
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials
from flask import Flask, request


app = Flask(__name__)


# ── Environment variables ─────────────────────────────────────────────────────

def get_env(key: str, default: str = None) -> str:
    value = os.environ.get(key, default)
    if value is None:
        print(f"[ERROR] Missing required environment variable: {key}")
        sys.exit(1)
    return value


GOOGLE_CREDENTIALS = get_env("GOOGLE_CREDENTIALS_JSON")
SPREADSHEET_ID     = get_env("SPREADSHEET_ID")
APARTMENT_NAME     = get_env("APARTMENT_NAME", "your apartment")


# ── Column positions (must match reminder.py) ─────────────────────────────────
COL_ROW_ID   = 1
COL_NAME     = 2
COL_PAID     = 4
COL_VERIFIED = 5


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


def find_row_by_id(sheet, row_id: str):
    """Returns (sheet_row_index, row_data) or (None, None)."""
    all_rows = sheet.get_all_values()
    for i, row in enumerate(all_rows):
        row = row + [""] * max(0, 6 - len(row))
        if row[COL_ROW_ID - 1].strip() == row_id:
            return i + 1, row   # gspread is 1-indexed
    return None, None


# ── HTML responses ────────────────────────────────────────────────────────────

def html_response(emoji: str, heading: str, subtext: str, color: str) -> str:
    """
    Minimal, beautiful mobile-first HTML response page.
    Single-screen, no scrolling, instant feedback.
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0"/>
  <title>{heading}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet"/>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --bg:      #0f0f0f;
      --card:    #1a1a1a;
      --border:  #2a2a2a;
      --accent:  {color};
      --text:    #f0f0f0;
      --muted:   #888;
    }}

    html, body {{
      height: 100%;
      background: var(--bg);
      color: var(--text);
      font-family: 'DM Sans', sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }}

    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 24px;
      padding: 48px 32px;
      max-width: 360px;
      width: 100%;
      text-align: center;
      box-shadow: 0 0 60px rgba(0,0,0,0.6);
      animation: rise 0.4s cubic-bezier(0.16, 1, 0.3, 1) both;
    }}

    @keyframes rise {{
      from {{ opacity: 0; transform: translateY(20px); }}
      to   {{ opacity: 1; transform: translateY(0); }}
    }}

    .emoji {{
      font-size: 56px;
      display: block;
      margin-bottom: 24px;
      animation: pop 0.5s 0.2s cubic-bezier(0.16, 1, 0.3, 1) both;
    }}

    @keyframes pop {{
      from {{ transform: scale(0.5); opacity: 0; }}
      to   {{ transform: scale(1);   opacity: 1; }}
    }}

    h1 {{
      font-family: 'DM Serif Display', serif;
      font-size: 28px;
      line-height: 1.2;
      color: var(--accent);
      margin-bottom: 12px;
    }}

    p {{
      font-size: 15px;
      color: var(--muted);
      line-height: 1.6;
    }}

    .divider {{
      height: 1px;
      background: var(--border);
      margin: 24px 0;
    }}

    .apt-name {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--muted);
    }}
  </style>
</head>
<body>
  <div class="card">
    <span class="emoji">{emoji}</span>
    <h1>{heading}</h1>
    <p>{subtext}</p>
    <div class="divider"></div>
    <span class="apt-name">{APARTMENT_NAME}</span>
  </div>
</body>
</html>"""


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/confirm")
def confirm():
    """
    Called when roommate taps the link in SMS.
    Marks Paid=TRUE in the sheet immediately — no button click needed.
    """
    row_id = request.args.get("id", "").strip()

    if not row_id:
        return html_response(
            "⚠️", "Invalid Link",
            "This confirmation link is missing an ID. Please contact your house manager.",
            "#f59e0b"
        ), 400

    try:
        sheet = get_sheet()
        sheet_row_index, row_data = find_row_by_id(sheet, row_id)

        if sheet_row_index is None:
            return html_response(
                "🔍", "Not Found",
                "We couldn't find your record. Please contact your house manager.",
                "#f59e0b"
            ), 404

        name = row_data[COL_NAME - 1].strip() if row_data else "Roommate"

        # Check if already marked paid
        already_paid = str(row_data[COL_PAID - 1]).strip().upper() == "TRUE"
        if already_paid:
            return html_response(
                "✅", f"Already Confirmed!",
                f"Hi {name}, your payment was already recorded. You're all good!",
                "#22c55e"
            ), 200

        # Mark Paid = TRUE
        sheet.update_cell(sheet_row_index, COL_PAID, "TRUE")
        print(f"[CONFIRMED] {name} (id={row_id}) marked as Paid at {datetime.now()}")

        return html_response(
            "🎉", f"Payment Confirmed!",
            f"Thanks {name}, your rent payment for {APARTMENT_NAME} has been recorded. No more reminders!",
            "#22c55e"
        ), 200

    except Exception as exc:
        print(f"[ERROR] /confirm?id={row_id} — {exc}")
        return html_response(
            "❌", "Something went wrong",
            "We couldn't update your record. Please try again or contact your house manager.",
            "#ef4444"
        ), 500


@app.route("/health")
def health():
    """Simple health check endpoint."""
    return {"status": "ok", "service": f"{APARTMENT_NAME} Rent Reminder"}, 200


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)