# 🏠 Rent Reminder System

Automated monthly rent reminders via SMS (Fast2SMS) with one-tap payment confirmation.

**How it works:**
- Every day (1st–15th of month) at 9 AM IST, an SMS is sent to unpaid roommates
- SMS contains a confirmation link — tapping it instantly marks them as Paid in the sheet
- Reminders stop when both **Paid = TRUE** (self-reported) AND **Verified = TRUE** (you manually set)
- On the 1st of each month, all statuses reset automatically

---

## Project Structure

```
rent-reminder/
├── reminder.py          ← Sends daily SMS reminders
├── app.py               ← Flask web app (confirmation endpoint, deploy on Render)
├── reset_monthly.py     ← Resets Paid/Verified on the 1st of each month
├── requirements.txt
├── Procfile             ← Web process command for hosting platforms
├── .env.example         ← All required environment variables
└── .github/
    └── workflows/
        └── cron.yml     ← GitHub Actions: daily + monthly triggers
```

---

## Google Sheet Format

Create a sheet with this exact header row:

| A      | B    | C     | D    | E        | F             |
|--------|------|-------|------|----------|---------------|
| row_id | Name | Phone | Paid | Verified | Last Reminded |

- **row_id** — unique number per person: 1, 2, 3 ... (you set this once)
- **Name** — first name only, used in SMS greeting
- **Phone** — with country code, no spaces or dashes e.g. `919876543210`
- **Paid** — `FALSE` by default; auto-set to `TRUE` when they tap the link
- **Verified** — `FALSE` by default; **you manually set to `TRUE`** once you confirm receipt
- **Last Reminded** — auto-filled by reminder.py

**Reminders stop only when BOTH Paid = TRUE AND Verified = TRUE.**

---

## Setup Guide

### Step 1 — Google Cloud Service Account

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or use existing)
3. Enable **Google Sheets API** and **Google Drive API**
4. Go to **IAM & Admin → Service Accounts → Create Service Account**
5. Download the JSON key file
6. Convert to single line:
   ```bash
   cat your-key.json | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin)))"
   ```
7. Copy this single-line JSON — you'll use it as `GOOGLE_CREDENTIALS_JSON`
8. **Share your Google Sheet** with the service account email (found in the JSON as `client_email`) — give it **Editor** access

---

### Step 2 — Fast2SMS

1. Sign up at [fast2sms.com](https://www.fast2sms.com)
2. Go to **Dashboard → Dev API** and copy your API key
3. Add credits (₹100 lasts several months for 10–15 people)

---

### Step 3 — Deploy Web App to Render

1. Push this repo to GitHub
2. Go to [render.com](https://render.com) → **New +** → **Web Service**
3. Connect your GitHub account and select this repo
4. Configure the service:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 30`
5. In Render **Environment** tab, add all variables from `.env.example`
6. Deploy the service
7. Copy your Render app URL (e.g. `https://rent-reminder.onrender.com`)
8. Set that as `CONFIRMATION_BASE_URL`

---

### Step 4 — GitHub Actions Secrets

In your GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**

Add all of these:

| Secret Name              | Value                          |
|--------------------------|--------------------------------|
| `FAST2SMS_API_KEY`       | From Fast2SMS dashboard        |
| `GOOGLE_CREDENTIALS_JSON`| Single-line service account JSON |
| `SPREADSHEET_ID`         | From your Google Sheet URL     |
| `CONFIRMATION_BASE_URL`  | Your Render app URL            |
| `APARTMENT_NAME`         | e.g. `Mandakini Garden`        |
| `REMINDER_STOP_DAY`      | e.g. `15`                      |

---

### Step 5 — Test Everything

**Test the confirmation link manually:**
```
https://your-app.onrender.com/confirm?id=1
```
Open this in a browser — it should mark row_id=1 as Paid=TRUE in your sheet.

**Test the reminder script locally:**
```bash
pip install -r requirements.txt
cp .env.example .env   # fill in real values
set -a && source .env && set +a
python reminder.py
```

**Trigger GitHub Actions manually:**
Go to repo → Actions → Rent Reminder → Run workflow → choose `reminder` or `reset`

---

## Deployment (Render)

Deploy the Flask web app to Render so the mark-as-paid confirmation link works in production.

### Prerequisites
- Repo pushed to GitHub
- Google Sheet, Fast2SMS, and service account configured (see Setup Guide above)

### Steps

1. **Create Web Service**
   - Go to [render.com](https://render.com) → **New +** → **Web Service**
   - Connect GitHub and select this repository

2. **Configure Build**
   - **Name:** e.g. `rent-reminder` or `mandakini-apartment-reminder`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 30`

3. **Add Environment Variables**
   - In **Environment** tab, add all variables from `env.example`:
   - `GOOGLE_CREDENTIALS_JSON` — single-line service account JSON
   - `SPREADSHEET_ID` — from your Google Sheet URL
   - `APARTMENT_NAME` — e.g. `Mandakini Garden`
   - `CONFIRMATION_BASE_URL` — leave blank for now (set after deploy)

4. **Deploy**
   - Click **Create Web Service**
   - Wait for build and deploy to finish

5. **Set Confirmation URL**
   - Copy your Render URL (e.g. `https://rent-reminder.onrender.com`)
   - In Render **Environment** tab, set `CONFIRMATION_BASE_URL` to that URL (no trailing slash)
   - In GitHub **Settings → Secrets → Actions**, set `CONFIRMATION_BASE_URL` to the same URL

6. **Verify**
   - Open `https://your-app.onrender.com/health` — should return `{"status":"ok"}`
   - Open `https://your-app.onrender.com/confirm?id=1` — should mark row 1 as Paid in your sheet

---

## Local Dev Testing

Use this before production deployment changes, or whenever you want to validate sheet + confirmation flow safely.

### 1) Prepare local environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in real values
set -a && source .env && set +a
```

### 2) Run and verify the Flask app locally

```bash
python app.py
```

In another terminal, verify health endpoint:

```bash
curl http://localhost:5000/health
```

Expected: JSON with `status: ok`.

### 3) Test confirmation flow locally

Open this URL in browser (use a real `row_id` from your sheet):

```text
http://localhost:5000/confirm?id=1
```

It should set `Paid=TRUE` for that row in your Google Sheet.

### 4) Test reminder and reset scripts locally

```bash
python reminder.py
python reset_monthly.py
```

`reminder.py` should send SMS for rows where BOTH Paid and Verified are not TRUE.
`reset_monthly.py` should reset Paid + Verified to FALSE.

### 5) Recommended safe testing sequence

1. Create one dedicated test row in your sheet.
2. Use your own phone number in that row first.
3. Confirm `/confirm?id=<test_row_id>` behavior before triggering SMS reminders for everyone.
4. Only then run GitHub Actions jobs manually.

---

## SMS Example

```
Hey Prabhat, please pay the Mandakini Garden rent this month.
Tap to confirm payment (one tap marks you as paid):
https://rent-reminder.onrender.com/confirm?id=3
```

---

## Monthly Workflow (What Happens Automatically)

```
1st of month  →  reset_monthly.py resets all Paid + Verified to FALSE
1st–15th      →  reminder.py sends SMS daily at 9 AM IST to unpaid people
Roommate taps link  →  app.py sets Paid = TRUE instantly
You confirm receipt  →  You set Verified = TRUE in sheet manually
Both TRUE  →  No more reminders for that person this month
16th onwards  →  No more reminders sent (REMINDER_STOP_DAY=15)
```
