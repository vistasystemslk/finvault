# FinVault

**Your personal finance command center — portable, private, and local.**

FinVault is a single Windows application for credit cards, bank accounts, loans, assets,
income and Sri Lankan income tax. It runs a tiny web server on your own computer, opens a
polished browser UI, and keeps every record in a SQLite database stored **next to the app**.
There is no cloud account, no telemetry, and no internet dependency.

---

## Quick start

### Option A — Prebuilt EXE

1. Put `FinVault.exe` in a folder (for example inside your Google Drive).
2. Double-click it. Your browser opens `http://127.0.0.1:8787/`.
3. That folder now contains `FinVault.db` (your data), `backups/`, `exports/` and `finvault.log`.

To stop FinVault, close the browser tab and use **Settings → Quit app**, or run
`FinVault.exe --stop`. Only one copy can run against the same database at a time.

### Option B — From source

Requires Python 3.11+ (3.12 recommended). No third-party packages are needed to run.

```powershell
cd finvault
python -m finvault
```

Useful flags:

```powershell
python -m finvault --no-browser        # start without opening a browser
python -m finvault --port 9000         # use another port
python -m finvault --stop              # stop the running instance
python -m finvault --version
```

---

## What is inside

| Area | What you can do |
| --- | --- |
| Dashboard | Net worth, cash flow, credit health, upcoming payments, insights |
| Credit cards | Multiple cards, limits, balances, utilization, statements, payments |
| Transactions | Purchases, expenses, fees, interest, refunds, business/personal split, CSV import |
| Bank accounts | Savings, current, fixed deposits, cash, wallets, investments; transfers |
| Installments | Monthly plans, remaining months, one-click “log charge” |
| Scheduled | Your own reminders for bills, premiums and instalments; overdue items surface on the dashboard |
| Loans | Personal, vehicle, housing, lease; payments and payoff projection |
| Net worth | Property, vehicles, investments and other assets/liabilities |
| Income | Salary, business, investment, rental; recurring entries and bank deposits |
| Income tax | Sri Lankan personal income tax by year of assessment, editable slabs |
| Insights | Spending patterns, category analysis, merchants, subscriptions, recommendations |
| People | Separate or combined views for you and your wife/partner |
| Settings | Currency, theme, FX rates, backups, exports, API key |
| API | Key-protected JSON REST API on localhost for other apps |

Everything is stored in **one SQLite file**, so backup and portability are trivial.

---

## How the data behaves

- **Credit-card balance** = opening balance + purchases/fees/interest − payments/refunds.
- **Card payment from a bank account** creates two linked transactions (cash out of the bank,
  payment into the card). Transfers are removed as a pair.
- **Statement payment** updates `amount_paid`, marks the statement *paid* or *partial*, and
  records the card payment (plus an optional bank transaction).
- **Business expenses** are excluded from personal spending. `tax_deductible` business
  expenses reduce business income in the tax estimate.
- **Installments** are plans, not transactions. Use **Log charge** each month to add the
  installment charge to the card and reduce the remaining months.
- **Loans** count as debt in net worth. Payments split into interest and principal; blank
  components are calculated from the APR.
- **All-people vs person view** — the picker in the top bar filters every page. “All people”
  shows combined totals; a person shows only their records.

---

## Sri Lankan income tax

Tax is calculated per person and per year of assessment. Open **Income tax** to:

- switch between the seeded years **2024/25**, **2025/26** and **2026/27**;
- edit the progressive slabs, personal relief, rent relief and WHT treatment to match your
  official tax sheet exactly;
- add reliefs (qualifying payments, donations, rent) and credits (APIT, WHT);
- export the current year as CSV for your accountant.

When you share your tax sheet, the slab table and relief labels can be aligned one-to-one
with it — nothing is hard-coded beyond the seeded defaults.

---

## REST API

Base URL: `http://127.0.0.1:8787/api/v1`
Every request needs the key from **Settings → API access**:

```
X-API-Key: <your key>
# or
Authorization: Bearer <your key>
```

Responses use a consistent envelope:

```json
{ "ok": true, "data": { } }
{ "ok": false, "error": { "message": "…", "field": "…" } }
```

Quick examples (PowerShell):

```powershell
$key = "<your key>"
$h = @{ "X-API-Key" = $key }

# Dashboard
Invoke-RestMethod "http://127.0.0.1:8787/api/v1/dashboard" -Headers $h

# Add a card purchase
$body = @{
  card_id = 1
  type = "purchase"
  date = "2026-11-16"
  description = "Groceries"
  amount = 12500
  direction = "out"
} | ConvertTo-Json

Invoke-RestMethod "http://127.0.0.1:8787/api/v1/transactions" -Method Post `
  -Headers $h -ContentType "application/json" -Body $body
```

cURL equivalent:

```bash
curl -H "X-API-Key: $KEY" http://127.0.0.1:8787/api/v1/dashboard
```

Useful endpoints include `/dashboard`, `/networth`, `/insights`, `/accounts`, `/cards`,
`/transactions`, `/statements`, `/installments`, `/loans`, `/scheduled`, `/reminders`,
`/assets`, `/liabilities`, `/incomes`, `/tax/summary`, `/tax/years`, `/search?q=`,
`/export?format=json|csv`, `/import/csv`, `/admin/backup`, `/admin/restore` and
`/admin/stats`.

### Scheduled transactions and reminders

```powershell
# Create a monthly reminder for a bill you pay by card
$body = @{
  person_id = 1
  name = "Vehicle insurance"
  amount = 12500
  type = "expense"
  frequency = "monthly"        # once | weekly | monthly | quarterly | yearly
  next_due_date = "2026-11-20"
  card_id = 1                  # optional: settle() then records a transaction
  category_id = 8
  installments_left = 0        # optional: stops after N payments
} | ConvertTo-Json
Invoke-RestMethod "http://127.0.0.1:8787/api/v1/scheduled" -Method Post `
  -Headers $h -ContentType "application/json" -Body $body

# Everything overdue or due in the next three weeks
Invoke-RestMethod "http://127.0.0.1:8787/api/v1/reminders?days=21" -Headers $h

# Mark paid: posts the transaction and rolls the date forward
Invoke-RestMethod "http://127.0.0.1:8787/api/v1/scheduled/1/settle" -Method Post `
  -Headers $h -ContentType "application/json" -Body '{"post": true}'
```

`/dashboard` also returns a `reminders` array (overdue first), which is what the
**Needs attention** strip at the top of the dashboard is built from.

### Letting an agent or another app import statements

`POST /api/v1/import/card-statement` is designed to be called by automation, and it is
safe to retry:

```json
{
  "card_id": 14,
  "dry_run": true,
  "strict": true,
  "statement": {
    "statement_date": "2026-11-12",
    "period_start": "2026-10-13",
    "period_end": "2026-11-12",
    "due_date": "2026-12-02",
    "opening_balance": 669866.45,
    "closing_balance": 877452.77,
    "minimum_due": 35098.11
  },
  "transactions": [
    {"date": "2026-10-13", "description": "MIRIGAMA INTERCHANGE", "amount": 300, "direction": "out"}
  ]
}
```

| Flag | Default | Effect |
| --- | --- | --- |
| `dry_run` | false | Validate and preview only; nothing is written |
| `strict` | false | Return HTTP 400 if opening + rows ≠ closing |
| `skip_duplicates` | true | Skip rows that already exist on that card (same date, amount, direction, description) |
| `replace` | false | Delete the existing statement for that date first, then re-import |

The response reports `reconciles` and `difference`, so a caller can verify the arithmetic
before trusting the import. Re-posting the same statement returns
`{"duplicate": true, "inserted": 0}` instead of duplicating data.

For raw lists use `/import/transactions` (pass `skip_duplicates: true`) or
`/import/csv` (already defaults to skipping duplicates).
The in-app **API & docs** page lists the full surface with methods and descriptions.

CORS is enabled for local tools. By default the server binds to `127.0.0.1` only.

---

## Backups and Google Drive

- Automatic backups are written to `backups/` every *N* hours (default 12) and before any
  restore. **Settings → Backup now** creates one immediately.
- **Settings → Export** produces a full JSON snapshot, a transactions CSV, and a tax CSV.
- The database uses `journal_mode=DELETE` and `synchronous=FULL`, which is safer for synced
  folders than WAL.

> **Google Drive caution**
> Do not run the same folder on two computers at the same time while Drive is syncing.
> Close FinVault before moving or renaming the folder. Keep the backups — they are your
> safety net if a sync conflict ever occurs.

---

## Building `FinVault.exe`

```powershell
.\build.ps1
```

or double-click `build.bat`. The build uses PyInstaller:

```powershell
python -m PyInstaller --noconfirm --onefile --windowed `
  --name FinVault --icon assets\FinVault.ico --add-data "web;web" launcher.py
```

`build.ps1` clears `build\` and the previous `dist\FinVault.exe` before packaging, tolerating
files that OneDrive or antivirus may lock, then verifies the EXE was produced. Exit code is 0
only on success, so `build.bat` reports failures correctly.

Output: `dist\FinVault.exe`.

Copy that single file anywhere. On first launch it creates `FinVault.db` beside itself.
The web UI is bundled inside the EXE, so no extra files are required.

To regenerate the icon:

```powershell
python tools\make_icon.py
```

---

## Importing credit-card statements (PDF)

Drop statement PDFs into `statements/inbox/<bank>/`, then:

```powershell
python tools/statements.py                    # parse + reconcile every PDF
python tools/load_statements.py --dry-run     # show what would be imported
python tools/load_statements.py --reset       # import (--db dist\FinVault.db for the EXE)
```

`tools/statements.py` writes normalised JSON to `statements/parsed/` and refuses to
proceed unless every statement reconciles: each statement's opening balance must equal
the previous statement's closing balance, and each card's computed balance must equal
the latest statement's closing balance.

Supported layouts: Commercial Bank (incl. supplementary cards), Nations Trust Bank,
Seylan (online banking export) and Union Bank. PDFs need a text layer; scanned images
are not supported. Requires `pip install pypdf`.

Bank rows that are not spending (balance transfers, plan conversions, loan repayments,
card payments) are classified so they never inflate spending totals:

| Row | Type | Effect |
| --- | --- | --- |
| `CONVERT / BAL XFR / RETURN PURCHASE ... EASY PAYMENT PLAN` | refund | nets the original purchase, which then counts as installments |
| `HSBC LAST/UNBILLED STATEMENT BALANCE` | adjustment | moves debt, not spending |
| `SINGER FINANCE` | loan_payment | loan repayment |
| `CASH PAYMENT` | payment | money paid into the card |

---

## Project layout

```
finvault/
  finvault/            Python package (config, db, finance, API modules, server)
  web/                 Offline browser UI (HTML, CSS, ES modules)
  tests/smoke_api.py   End-to-end API regression test
  tools/make_icon.py   Icon generator
  assets/              FinVault.ico / .png
  launcher.py          PyInstaller entry point
  build.ps1 / build.bat
  README.md
```

Run the regression test with the server stopped:

```powershell
python tests\smoke_api.py
```

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Browser shows “can’t connect” | The app may have exited. Start `FinVault.exe` again. |
| “Another instance is already running” | Use the open window, or run `FinVault.exe --stop` first. |
| Port 8787 is busy | Start with `FinVault.exe --port 8788` (or set the flag in a shortcut). |
| Data looks stale after restoring a backup | Refresh the browser tab. |
| Want a clean start | Close the app, rename `FinVault.db`, relaunch. A fresh seeded database is created. |
| Lost the API key | Settings → API access → Rotate key. Update any external scripts. |

---

*FinVault 1.0.0 — built for one household, not for a data centre.*
