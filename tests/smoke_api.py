"""End-to-end smoke test for the FinVault API (no UI required)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TEST_DB = Path(tempfile.gettempdir()) / "finvault-smoke.db"
os.environ["FINVAULT_DB"] = str(TEST_DB)
if TEST_DB.exists():
    TEST_DB.unlink()

from finvault.db import database, get_setting, init_db  # noqa: E402
from finvault.server import FinVaultHandler, FinVaultServer  # noqa: E402

init_db(TEST_DB)
with database(TEST_DB) as conn:
    KEY = get_setting(conn, "api_key")

server = FinVaultServer(("127.0.0.1", 0), FinVaultHandler)
FinVaultHandler.api_key = KEY
PORT = server.server_address[1]
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
BASE = f"http://127.0.0.1:{PORT}/api/v1"


def call(method: str, path: str, body=None, expect=200):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, method=method, data=data,
                                 headers={"Content-Type": "application/json", "X-API-Key": KEY})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            status = response.status
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        status = error.code
        payload = json.loads(error.read().decode())
    if status != expect:
        raise AssertionError(f"{method} {path} -> {status}: {payload}")
    return payload.get("data") if isinstance(payload, dict) and "data" in payload else payload


def check(label: str, condition: bool, detail=""):
    print(("PASS " if condition else "FAIL ") + label + ((" " + detail) if detail else ""))
    if not condition:
        raise SystemExit(1)


# --- bootstrap -------------------------------------------------------------
boot = call("GET", "/bootstrap")
check("bootstrap", boot["app"]["name"] == "FinVault" and len(boot["persons"]) == 1)
person_id = boot["persons"][0]["id"]
categories = boot["categories"]
cat = {row["name"]: row["id"] for row in categories}

# --- card / account --------------------------------------------------------
card = call("POST", "/cards", {
    "person_id": person_id, "name": "HNB Visa", "issuer": "HNB", "last4": "1234",
    "credit_limit": 500000, "apr": 28, "statement_day": 25, "due_day": 15,
    "purpose": "business", "currency": "LKR",
})
check("create card", card["id"] > 0 and card["outstanding"] == 0)
account = call("POST", "/accounts", {
    "person_id": person_id, "name": "Commercial Bank", "institution": "ComBank",
    "type": "savings", "opening_balance": 250000,
})
check("create account", account["id"] > 0 and account["balance"] == 250000)

# --- transactions ----------------------------------------------------------
tx1 = call("POST", "/transactions", {
    "card_id": card["id"], "type": "purchase", "date": "2026-11-02",
    "description": "Office chairs", "category_id": cat["Business"], "amount": 85000,
    "is_business": True, "tax_deductible": True,
})
tx2 = call("POST", "/transactions", {
    "card_id": card["id"], "type": "purchase", "date": "2026-11-05",
    "description": "Groceries", "category_id": cat["Groceries"], "amount": 18500,
})
check("create card tx", tx1["id"] > 0 and tx2["id"] > 0)
card_after = call("GET", f"/cards/{card['id']}")
check("card outstanding", abs(card_after["outstanding"] - 103500) < 0.01, str(card_after["outstanding"]))

payment = call("POST", f"/cards/{card['id']}/payments", {
    "amount": 50000, "account_id": account["id"], "date": "2026-11-10",
})
check("card payment", payment["payment"]["type"] == "payment")
card_after = call("GET", f"/cards/{card['id']}")
check("outstanding after payment", abs(card_after["outstanding"] - 53500) < 0.01, str(card_after["outstanding"]))
account_after = call("GET", f"/accounts/{account['id']}")
check("bank balance after payment", abs(account_after["balance"] - 200000) < 0.01, str(account_after["balance"]))

transfer = call("POST", "/transfers", {
    "from_account_id": account["id"], "to_account_id": account["id"],
    "amount": 100, "date": "2026-11-10",
}, expect=400)
check("transfer validation", True)

# --- statement -------------------------------------------------------------
statement = call("POST", "/statements", {
    "card_id": card["id"], "statement_date": "2026-11-25", "due_date": "2026-12-15",
    "opening_balance": 0, "closing_balance": 53500, "minimum_due": 2675,
})
check("create statement", statement["id"] > 0 and statement["effective_status"] == "unpaid")
statement = call("POST", f"/statements/{statement['id']}/pay", {"amount": 20000, "account_id": account["id"]})
check("statement partial payment", statement["statement_id"] > 0)
statements = call("GET", f"/statements?card_id={card['id']}")
check("statement status partial", statements[0]["effective_status"] == "partial",
      statements[0]["effective_status"])

# --- installment -----------------------------------------------------------
plan = call("POST", "/installments", {
    "card_id": card["id"], "description": "Laptop 12 months", "months": 12,
    "monthly_amount": 10000, "principal": 120000, "first_due_date": "2026-11-20",
})
check("installment plan", plan["remaining_months"] == 12 and plan["paid_months"] == 0)
posted = call("POST", f"/installments/{plan['id']}/post", {"date": "2026-11-20"})
check("post installment", posted["remaining_months"] == 11 and posted["transaction"]["type"] == "installment")

# --- scheduled reminders ---------------------------------------------------
reminder = call("POST", "/scheduled", {
    "person_id": person_id, "name": "Vehicle insurance", "amount": 12500,
    "type": "expense", "frequency": "monthly", "next_due_date": "2026-11-20",
    "card_id": card["id"], "installments_left": 2,
})
check("create reminder", reminder["id"] > 0 and reminder["status"] in ("upcoming", "soon", "today"))
check("reminder links card", reminder["card_name"] == card["name"])
settled = call("POST", f"/scheduled/{reminder['id']}/settle", {"post": True, "date": "2026-11-20"})
check("settle reminder", settled["posted"] and settled["reminder"]["next_due_date"] == "2026-12-20"
      and settled["reminder"]["installments_left"] == 1)
feed = call("GET", "/reminders?days=60")
check("reminder feed", any(item["scheduled_id"] == reminder["id"] for item in feed if item["kind"] == "scheduled"))
call("DELETE", f"/scheduled/{reminder['id']}")
check("delete reminder", all(item["id"] != reminder["id"] for item in call("GET", "/scheduled")))

# --- loan ----------------------------------------------------------------
loan = call("POST", "/loans", {
    "person_id": person_id, "name": "Personal loan", "lender": "NDB", "principal": 1000000,
    "outstanding": 800000, "annual_rate": 14, "monthly_payment": 30000,
    "next_due_date": "2026-11-20",
})
check("create loan", loan["id"] > 0 and loan["projection_months"] > 0)
loan_payment = call("POST", f"/loans/{loan['id']}/payments", {
    "amount": 30000, "date": "2026-11-20", "account_id": account["id"],
})
check("loan payment", abs(loan_payment["loan"]["outstanding"] - 779333.33) < 1,
      str(loan_payment["loan"]["outstanding"]))
loan_detail = call("GET", f"/loans/{loan['id']}")
check("loan detail amortization", len(loan_detail["amortization"]["schedule"]) > 10)

# --- assets / liabilities / income ---------------------------------------
asset = call("POST", "/assets", {"person_id": person_id, "name": "Apartment", "category": "property", "value": 15000000})
liability = call("POST", "/liabilities", {"person_id": person_id, "name": "Furniture loan", "balance": 150000, "monthly_payment": 15000})
income = call("POST", "/incomes", {
    "person_id": person_id, "date": "2026-11-01", "source": "Salary", "category_id": cat["Salary"],
    "amount": 450000, "frequency": "monthly", "tax_head": "employment", "account_id": account["id"],
})
check("asset/liability/income", asset["id"] > 0 and liability["id"] > 0 and income["id"] > 0)
check("income deposit linked", income["deposit_transaction_id"] is not None)
account_after = call("GET", f"/accounts/{account['id']}")
check("bank balance after income", abs(account_after["balance"] - 600000) < 0.01, str(account_after["balance"]))

# --- dashboard / net worth / analytics -----------------------------------
dash = call("GET", f"/dashboard?person_id={person_id}&month=2026-11")
check("dashboard cards", len(dash["cards"]) == 1)
check("dashboard summary", dash["summary"]["bank_balance"] == 600000)
check("dashboard income", abs(dash["summary"]["month_income"] - 450000) < 0.01)
check("dashboard expenses", abs(dash["summary"]["month_expenses"] - 126000) < 1,
      str(dash["summary"]["month_expenses"]))  # 113,500 + 12,500 posted by the settled reminder
check("dashboard insights", len(dash["insights"]) > 0)

networth = call("GET", f"/networth?person_id={person_id}")
check("net worth", networth["summary"]["net_worth"] > 0 and len(networth["history"]) >= 1,
      str(networth["summary"]["net_worth"]))
spending = call("GET", f"/analytics/spending?person_id={person_id}&from=2026-11-01&to=2026-11-30")
check("spending categories", len(spending["categories"]) >= 2)
check("business split", spending["business_spend"] == 85000)

# --- tax -----------------------------------------------------------------
relief = call("POST", "/tax/reliefs", {
    "person_id": person_id, "year_label": "2026/27", "name": "Solar panels", "amount": 500000,
})
credit = call("POST", "/tax/credits", {
    "person_id": person_id, "year_label": "2026/27", "name": "APIT", "amount": 250000, "kind": "apit",
})
call("POST", "/incomes", {
    "person_id": person_id, "date": "2026-06-15", "source": "Consulting project",
    "amount": 3000000, "frequency": "one_time", "tax_head": "business",
})
tax = call("GET", f"/tax/estimate?person_id={person_id}&year_label=2026/27")
check("tax estimate", tax["total_assessable"] > 0 and tax["gross_tax"] > 0, json.dumps(tax["heads"]))
check("tax business head net of deductions", tax["heads"]["business"] == 2915000, json.dumps(tax["heads"]))
check("tax credits", tax["credits"]["apit"] == 250000)
check("tax reliefs", tax["deductions"]["qualifying_reliefs"] == 500000)
check("tax effective rate", 0 < tax["effective_rate"] < 40, str(tax["effective_rate"]))

# --- CSV import ----------------------------------------------------------
csv_text = "Date,Description,Amount\n01/11/2026,Coffee shop,1200\n02/11/2026,Book store,3500\n06/11/2026,Refund,-500\n"
preview = call("POST", "/import/csv", {
    "csv_text": csv_text, "card_id": card["id"],
    "mapping": {"date": "Date", "description": "Description", "amount": "Amount"},
    "day_first": True, "dry_run": True, "category_id": cat["Other"],
})
check("csv preview", preview["parsed"] == 3 and preview["inserted"] == 0)
imported = call("POST", "/import/csv", {
    "csv_text": csv_text, "card_id": card["id"],
    "mapping": {"date": "Date", "description": "Description", "amount": "Amount"},
    "day_first": True, "category_id": cat["Other"], "skip_duplicates": True,
})
check("csv import", imported["inserted"] == 3, json.dumps(imported["errors"]))
again = call("POST", "/import/csv", {
    "csv_text": csv_text, "card_id": card["id"],
    "mapping": {"date": "Date", "description": "Description", "amount": "Amount"},
    "day_first": True, "category_id": cat["Other"], "skip_duplicates": True,
})
check("csv duplicate skip", again["skipped"] == 3, json.dumps(again))

# --- bulk import / statement import -------------------------------------
bulk = call("POST", "/import/transactions", {"items": [
    {"card_id": card["id"], "date": "2026-11-07", "description": "Bulk A", "amount": 100, "type": "purchase", "category": "Other"},
    {"card_id": card["id"], "date": "2026-11-08", "description": "Bulk B", "amount": 200, "type": "purchase"},
], "skip_duplicates": True})
check("bulk import", bulk["inserted"] == 2, json.dumps(bulk["errors"]))

stmt_import = call("POST", "/import/card-statement", {
    "card_id": card["id"],
    "statement": {"statement_date": "2026-12-25", "due_date": "2027-01-15", "opening_balance": 0, "closing_balance": 10000},
    "transactions": [
        {"date": "2026-12-01", "description": "Statement item", "amount": 10000, "type": "purchase"},
    ],
})
check("statement import", stmt_import["inserted"] == 1)
check("statement reconciles", stmt_import["reconciles"] is True and stmt_import["difference"] == 0)

repeat = call("POST", "/import/card-statement", {
    "card_id": card["id"],
    "statement": {"statement_date": "2026-12-25", "closing_balance": 10000},
    "transactions": [{"date": "2026-12-01", "description": "Statement item", "amount": 10000}],
})
check("statement import is idempotent", repeat["duplicate"] is True and repeat["inserted"] == 0)

dry = call("POST", "/import/card-statement", {
    "card_id": card["id"], "dry_run": True,
    "statement": {"statement_date": "2027-01-25", "opening_balance": 10000, "closing_balance": 15000},
    "transactions": [{"date": "2027-01-05", "description": "Dry item", "amount": 5000}],
})
check("statement dry run", dry["would_insert"] == 1 and dry["reconciles"] is True)

call("POST", "/import/card-statement", {
    "card_id": card["id"], "strict": True, "expect_error": False,
    "statement": {"statement_date": "2027-02-25", "opening_balance": 0, "closing_balance": 999},
    "transactions": [{"date": "2027-02-05", "description": "Mismatch", "amount": 500}],
}, expect=400)

# --- export / backup -----------------------------------------------------
with urllib.request.urlopen(urllib.request.Request(f"{BASE}/export?format=csv&table=transactions",
                                                  headers={"X-API-Key": KEY})) as response:
    csv_out = response.read().decode()
check("csv export", "Office chairs" in csv_out)
backup = call("POST", "/admin/backup")
check("backup", Path(backup["path"]).exists())
stats = call("GET", "/admin/stats")
check("admin stats", stats["integrity"] == "ok")

print("\nAll smoke tests passed.")
server.shutdown()
server.server_close()
