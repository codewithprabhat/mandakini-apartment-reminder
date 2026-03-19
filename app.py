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
import subprocess
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
ADMIN_KEY          = os.environ.get("ADMIN_KEY", "")

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


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


# ── Admin panel ───────────────────────────────────────────────────────────────

def _check_admin_key():
    """Returns True if ADMIN_KEY is unset or the request provides a matching key."""
    if not ADMIN_KEY:
        return True
    return (
        request.args.get("key", "") == ADMIN_KEY
        or request.headers.get("X-Admin-Key", "") == ADMIN_KEY
    )


@app.route("/admin")
def admin_page():
    if not _check_admin_key():
        return html_response(
            "\U0001f512", "Access Denied",
            "Invalid or missing admin key.", "#ef4444"
        ), 403

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0"/>
  <title>Admin &mdash; {APARTMENT_NAME}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet"/>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --bg:      #0f0f0f;
      --card:    #1a1a1a;
      --border:  #2a2a2a;
      --text:    #f0f0f0;
      --muted:   #888;
      --blue:    #3b82f6;
      --red:     #ef4444;
      --green:   #22c55e;
    }}

    html, body {{
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-family: 'DM Sans', sans-serif;
    }}

    .container {{
      max-width: 600px;
      margin: 0 auto;
      padding: 48px 20px 40px;
      animation: fadeIn 0.4s ease both;
    }}

    @keyframes fadeIn {{
      from {{ opacity: 0; transform: translateY(12px); }}
      to   {{ opacity: 1; transform: translateY(0); }}
    }}

    .header {{
      text-align: center;
      margin-bottom: 36px;
    }}

    .apt-label {{
      display: inline-block;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--muted);
      border: 1px solid var(--border);
      border-radius: 100px;
      padding: 6px 16px;
      margin-bottom: 20px;
    }}

    .header h1 {{
      font-family: 'DM Serif Display', serif;
      font-size: 32px;
      color: var(--text);
      margin-bottom: 8px;
    }}

    .header p {{
      font-size: 14px;
      color: var(--muted);
    }}

    .actions {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-bottom: 32px;
    }}

    @media (max-width: 480px) {{
      .actions {{ grid-template-columns: 1fr; }}
    }}

    .action-btn {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 28px 20px;
      cursor: pointer;
      color: var(--text);
      text-align: center;
      transition: all 0.2s ease;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 10px;
    }}

    .action-btn:hover:not(:disabled) {{
      border-color: #444;
      transform: translateY(-2px);
      box-shadow: 0 8px 30px rgba(0,0,0,0.4);
    }}

    .action-btn:disabled {{
      opacity: 0.5;
      cursor: not-allowed;
      transform: none;
    }}

    .action-btn .icon {{
      font-size: 36px;
    }}

    .action-btn .title {{
      font-family: 'DM Serif Display', serif;
      font-size: 18px;
    }}

    .action-btn .desc {{
      font-size: 12px;
      color: var(--muted);
      line-height: 1.4;
    }}

    .action-btn.reminder .title {{ color: var(--blue); }}
    .action-btn.reset .title {{ color: var(--red); }}

    .console {{
      background: #111;
      border: 1px solid var(--border);
      border-radius: 16px;
      overflow: hidden;
    }}

    .console-bar {{
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 12px 16px;
      background: #161616;
      border-bottom: 1px solid var(--border);
    }}

    .console-dot {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: #333;
    }}
    .console-dot.r {{ background: #ef4444; }}
    .console-dot.y {{ background: #f59e0b; }}
    .console-dot.g {{ background: #22c55e; }}

    .console-title {{
      font-size: 12px;
      color: var(--muted);
      margin-left: 8px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}

    #output {{
      padding: 16px;
      font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
      font-size: 13px;
      line-height: 1.7;
      color: #aaa;
      white-space: pre-wrap;
      word-break: break-word;
      max-height: 340px;
      overflow-y: auto;
      margin: 0;
    }}

    .curl-hint {{
      margin-top: 24px;
      text-align: center;
      font-size: 12px;
      color: #555;
    }}
    .curl-hint code {{
      background: #1a1a1a;
      padding: 2px 8px;
      border-radius: 4px;
      color: #666;
    }}

    .spinner {{
      display: inline-block;
      width: 14px;
      height: 14px;
      border: 2px solid #444;
      border-top-color: var(--text);
      border-radius: 50%;
      animation: spin 0.6s linear infinite;
      vertical-align: middle;
      margin-right: 6px;
    }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <span class="apt-label">{APARTMENT_NAME}</span>
      <h1>Admin Panel</h1>
      <p>Trigger reminders or reset the monthly cycle manually</p>
    </div>

    <div class="actions">
      <button class="action-btn reminder" id="btn-reminder" onclick="trigger('reminder')">
        <span class="icon">\U0001f4e8</span>
        <span class="title">Send Reminders</span>
        <span class="desc">SMS all unpaid roommates now</span>
      </button>
      <button class="action-btn reset" id="btn-reset" onclick="trigger('reset')">
        <span class="icon">\U0001f504</span>
        <span class="title">Reset Monthly</span>
        <span class="desc">Clear Paid &amp; Verified for everyone</span>
      </button>
    </div>

    <div class="console">
      <div class="console-bar">
        <span class="console-dot r"></span>
        <span class="console-dot y"></span>
        <span class="console-dot g"></span>
        <span class="console-title">Output</span>
      </div>
      <pre id="output">Ready. Click a button above to run a job.</pre>
    </div>

    <p class="curl-hint">
      or use curl: <code>curl -X POST /api/trigger-reminder</code>
    </p>
  </div>

  <script>
    var adminKey = new URLSearchParams(window.location.search).get('key') || '';

    function setButtons(disabled) {{
      document.getElementById('btn-reminder').disabled = disabled;
      document.getElementById('btn-reset').disabled = disabled;
    }}

    function trigger(action) {{
      var out = document.getElementById('output');
      setButtons(true);
      out.innerHTML = '<span class="spinner"></span> Running ' + action + '...\\n';

      fetch('/api/trigger-' + action, {{
        method: 'POST',
        headers: {{ 'X-Admin-Key': adminKey }}
      }})
      .then(function(resp) {{ return resp.json(); }})
      .then(function(data) {{
        var text = data.output || '';
        if (data.error) text += '\\n' + data.error;
        if (data.success) text += '\\n\\u2705 Done.';
        else text += '\\n\\u274c Failed.';
        out.textContent = text;
        out.scrollTop = out.scrollHeight;
      }})
      .catch(function(e) {{
        out.textContent = '\\u274c Network error: ' + e.message;
      }})
      .finally(function() {{
        setButtons(false);
      }});
    }}
  </script>
</body>
</html>"""


@app.route("/api/trigger-reminder", methods=["POST"])
def trigger_reminder():
    if not _check_admin_key():
        return {"success": False, "error": "Unauthorized"}, 403

    try:
        result = subprocess.run(
            [sys.executable, os.path.join(_SCRIPT_DIR, "reminder.py")],
            capture_output=True, text=True, timeout=120,
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else "",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "error": "Script timed out (120 s)"}, 504
    except Exception as exc:
        return {"success": False, "output": "", "error": str(exc)}, 500


@app.route("/api/trigger-reset", methods=["POST"])
def trigger_reset():
    if not _check_admin_key():
        return {"success": False, "error": "Unauthorized"}, 403

    try:
        result = subprocess.run(
            [sys.executable, os.path.join(_SCRIPT_DIR, "reset_monthly.py")],
            capture_output=True, text=True, timeout=120,
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr if result.returncode != 0 else "",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "error": "Script timed out (120 s)"}, 504
    except Exception as exc:
        return {"success": False, "output": "", "error": str(exc)}, 500


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)