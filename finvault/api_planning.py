"""Installments, loans, assets, liabilities, income, budgets and goals."""
from __future__ import annotations

from datetime import date, datetime

from . import finance
from .api_accounts import create_transaction
from .api_base import (
    ApiError, Ctx, as_bool, as_choice, as_date, as_float, as_int, body_dict, clean_text,
    ensure_account, ensure_card, ensure_category, ensure_person, query_person, route, update_row,
)
from .db import now_iso, q, q1, scalar

TAX_HEADS = {"employment", "business", "investment", "rental", "other"}


# ---------------------------------------------------------------------------
# Installment plans
# ---------------------------------------------------------------------------

def _installment_payload(conn, row: dict) -> dict:
    return {
        **row,
        "paid_months": max(0, int(row["months"] or 0) - int(row["remaining_months"] or 0)),
        "progress": finance.pct(
            max(0, int(row["months"] or 0) - int(row["remaining_months"] or 0)),
            int(row["months"] or 0),
        ),
        "total_payable": finance.money(float(row["monthly_amount"] or 0) * int(row["months"] or 0)),
        "remaining_amount": finance.money(float(row["monthly_amount"] or 0) * int(row["remaining_months"] or 0)),
    }


@route("GET", "/api/v1/installments")
def installments_list(ctx: Ctx):
    person_id = query_person(ctx)
    sql = """SELECT i.*, c.name AS card_name, c.currency, c.person_id, p.name AS person_name
             FROM installment_plans i
             JOIN cards c ON c.id = i.card_id
             JOIN persons p ON p.id = c.person_id"""
    params: list = []
    if person_id:
        sql += " WHERE c.person_id = ?"
        params.append(person_id)
    if ctx.query.get("status"):
        sql += " AND i.status = ?" if person_id else " WHERE i.status = ?"
        params.append(clean_text(ctx.query["status"], 20))
    sql += " ORDER BY i.status, i.id DESC"
    rows = q(ctx.conn, sql, params)
    return [_installment_payload(ctx.conn, row) for row in rows]


@route("GET", "/api/v1/installments/{id}")
def installments_detail(ctx: Ctx):
    plan_id = as_int(ctx.params["id"], "id", required=True)
    row = q1(ctx.conn,
             """SELECT i.*, c.name AS card_name, c.currency, c.person_id, p.name AS person_name
                FROM installment_plans i JOIN cards c ON c.id = i.card_id
                JOIN persons p ON p.id = c.person_id WHERE i.id = ?""", (plan_id,))
    if not row:
        raise ApiError("Installment plan not found", 404)
    return _installment_payload(ctx.conn, row)


@route("POST", "/api/v1/installments")
def installments_create(ctx: Ctx):
    body = body_dict(ctx.body)
    card_id = as_int(body.get("card_id"), "card_id", required=True)
    ensure_card(ctx.conn, card_id)
    description = clean_text(body.get("description"), 120)
    if not description:
        raise ApiError("Description is required", field="description")
    months = as_int(body.get("months"), "months", required=True, minimum=1, maximum=360)
    monthly = as_float(body.get("monthly_amount"), "monthly_amount", default=0, minimum=0)
    principal = as_float(body.get("principal"), "principal", default=monthly * months, minimum=0)
    stamp = now_iso()
    first_due = as_date(body.get("first_due_date") or body.get("start_date") or date.today().isoformat(),
                        "first_due_date", False)
    cur = ctx.conn.execute(
        """INSERT INTO installment_plans(card_id, description, principal, months, monthly_amount,
               interest_rate, start_date, first_due_date, remaining_months, status, notes,
               created_at, updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (card_id, description, principal, months, monthly,
         as_float(body.get("interest_rate"), "interest_rate", default=0, minimum=0),
         as_date(body.get("start_date") or date.today().isoformat(), "start_date", False),
         first_due, months, as_choice(body.get("status"), "status",
                                      {"active", "completed", "cancelled"}, "active"),
         clean_text(body.get("notes"), 1000), stamp, stamp),
    )
    row = q1(ctx.conn,
             """SELECT i.*, c.name AS card_name, c.currency, c.person_id, p.name AS person_name
                FROM installment_plans i JOIN cards c ON c.id = i.card_id
                JOIN persons p ON p.id = c.person_id WHERE i.id = ?""", (cur.lastrowid,))
    return _installment_payload(ctx.conn, row)


@route("PUT", "/api/v1/installments/{id}")
def installments_update(ctx: Ctx):
    plan_id = as_int(ctx.params["id"], "id", required=True)
    existing = q1(ctx.conn, "SELECT * FROM installment_plans WHERE id = ?", (plan_id,))
    if not existing:
        raise ApiError("Installment plan not found", 404)
    body = body_dict(ctx.body)
    if "card_id" in body:
        ensure_card(ctx.conn, as_int(body["card_id"], "card_id", required=True))
    for field_name in ("principal", "monthly_amount"):
        if field_name in body:
            body[field_name] = as_float(body[field_name], field_name, default=0, minimum=0)
    for field_name in ("months", "remaining_months"):
        if field_name in body:
            body[field_name] = as_int(body[field_name], field_name, default=0, minimum=0, maximum=360)
    if "interest_rate" in body:
        body["interest_rate"] = as_float(body["interest_rate"], "interest_rate", default=0, minimum=0)
    if "first_due_date" in body:
        body["first_due_date"] = as_date(body["first_due_date"], "first_due_date", False)
    if "start_date" in body:
        body["start_date"] = as_date(body["start_date"], "start_date", False)
    if "status" in body:
        body["status"] = as_choice(body["status"], "status",
                                   {"active", "completed", "cancelled"}, "active")
    update_row(ctx.conn, "installment_plans", plan_id, body,
               {"card_id", "description", "principal", "months", "monthly_amount", "interest_rate",
                "start_date", "first_due_date", "remaining_months", "status", "notes"})
    row = q1(ctx.conn,
             """SELECT i.*, c.name AS card_name, c.currency, c.person_id, p.name AS person_name
                FROM installment_plans i JOIN cards c ON c.id = i.card_id
                JOIN persons p ON p.id = c.person_id WHERE i.id = ?""", (plan_id,))
    return _installment_payload(ctx.conn, row)


@route("DELETE", "/api/v1/installments/{id}")
def installments_delete(ctx: Ctx):
    plan_id = as_int(ctx.params["id"], "id", required=True)
    if not q1(ctx.conn, "SELECT id FROM installment_plans WHERE id = ?", (plan_id,)):
        raise ApiError("Installment plan not found", 404)
    ctx.conn.execute("DELETE FROM installment_plans WHERE id = ?", (plan_id,))
    return {"deleted": plan_id}


@route("POST", "/api/v1/installments/{id}/post")
def installments_post(ctx: Ctx):
    plan_id = as_int(ctx.params["id"], "id", required=True)
    plan = q1(ctx.conn, "SELECT * FROM installment_plans WHERE id = ?", (plan_id,))
    if not plan:
        raise ApiError("Installment plan not found", 404)
    if plan["status"] != "active" or int(plan["remaining_months"] or 0) <= 0:
        raise ApiError("This installment plan has no remaining months", 409)
    body = body_dict(ctx.body)
    amount = as_float(body.get("amount"), "amount", default=float(plan["monthly_amount"]), minimum=0.01)
    tx = create_transaction(ctx.conn, {
        "person_id": q1(ctx.conn, "SELECT person_id FROM cards WHERE id = ?", (plan["card_id"],))["person_id"],
        "card_id": plan["card_id"],
        "type": "installment",
        "date": as_date(body.get("date") or date.today().isoformat(), "date"),
        "description": body.get("description") or f"Installment {plan['description']}",
        "amount": amount,
        "direction": "out",
        "category_id": as_int(body.get("category_id"), "category_id"),
        "installment_id": plan_id,
        "notes": clean_text(body.get("notes"), 1000),
    })
    remaining = max(0, int(plan["remaining_months"] or 0) - 1)
    status = "completed" if remaining == 0 else "active"
    ctx.conn.execute(
        "UPDATE installment_plans SET remaining_months = ?, status = ?, updated_at = ? WHERE id = ?",
        (remaining, status, now_iso(), plan_id),
    )
    return {"transaction": tx, "remaining_months": remaining, "status": status}


# ---------------------------------------------------------------------------
# Loans
# ---------------------------------------------------------------------------

def amortization_schedule(outstanding: float, annual_rate: float, payment: float,
                          max_months: int = 360) -> dict:
    schedule = []
    balance = float(outstanding)
    monthly_rate = float(annual_rate or 0) / 100.0 / 12.0
    total_interest = 0.0
    month = 0
    if payment <= 0:
        return {"schedule": [], "months": 0, "total_interest": 0,
                "warning": "Monthly payment is zero, so no payoff projection is possible."}
    while balance > 0.01 and month < max_months:
        month += 1
        interest = balance * monthly_rate
        principal = payment - interest
        if principal <= 0:
            return {"schedule": schedule, "months": None, "total_interest": finance.money(total_interest),
                    "warning": "The monthly payment does not cover interest. Increase the payment."}
        if principal > balance:
            principal = balance
            payment_this = principal + interest
        else:
            payment_this = payment
        schedule.append({
            "month": month,
            "payment": finance.money(payment_this),
            "interest": finance.money(interest),
            "principal": finance.money(principal),
            "balance": finance.money(balance - principal),
        })
        total_interest += interest
        balance -= principal
        if len(schedule) >= max_months and balance > 0.01:
            break
    return {"schedule": schedule, "months": len(schedule), "total_interest": finance.money(total_interest)}


def _loan_payload(conn, loan: dict) -> dict:
    paid = scalar(conn, "SELECT COALESCE(SUM(amount),0) FROM loan_payments WHERE loan_id = ?", (loan["id"],))
    projection = amortization_schedule(float(loan["outstanding"] or 0), float(loan["annual_rate"] or 0),
                                       float(loan["monthly_payment"] or 0))
    return {
        **loan,
        "total_paid": finance.money(paid),
        "projection_months": projection["months"],
        "projection_interest": projection["total_interest"],
        "projection_warning": projection.get("warning"),
    }


@route("GET", "/api/v1/loans")
def loans_list(ctx: Ctx):
    person_id = query_person(ctx)
    sql = "SELECT l.*, p.name AS person_name FROM loans l JOIN persons p ON p.id = l.person_id"
    params: list = []
    if person_id:
        sql += " WHERE l.person_id = ?"
        params.append(person_id)
    sql += " ORDER BY l.status, l.id"
    return [_loan_payload(ctx.conn, row) for row in q(ctx.conn, sql, params)]


@route("POST", "/api/v1/loans")
def loans_create(ctx: Ctx):
    body = body_dict(ctx.body)
    person_id = as_int(body.get("person_id"), "person_id", required=True)
    ensure_person(ctx.conn, person_id)
    name = clean_text(body.get("name"), 80)
    if not name:
        raise ApiError("Loan name is required", field="name")
    principal = as_float(body.get("principal"), "principal", default=0, minimum=0)
    outstanding = as_float(body.get("outstanding"), "outstanding", default=principal, minimum=0)
    stamp = now_iso()
    cur = ctx.conn.execute(
        """INSERT INTO loans(person_id, name, lender, type, principal, outstanding, currency,
               annual_rate, monthly_payment, start_date, term_months, next_due_date, status, notes,
               created_at, updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (person_id, name, clean_text(body.get("lender"), 80),
         as_choice(body.get("type"), "type",
                   {"personal", "vehicle", "housing", "lease", "education", "business", "other"}, "personal"),
         principal, outstanding, clean_text(body.get("currency"), 8).upper() or "LKR",
         as_float(body.get("annual_rate"), "annual_rate", default=0, minimum=0),
         as_float(body.get("monthly_payment"), "monthly_payment", default=0, minimum=0),
         as_date(body.get("start_date"), "start_date", False),
         as_int(body.get("term_months"), "term_months", default=0, minimum=0, maximum=600),
         as_date(body.get("next_due_date"), "next_due_date", False),
         as_choice(body.get("status"), "status", {"active", "paid", "closed"}, "active"),
         clean_text(body.get("notes"), 1000), stamp, stamp),
    )
    return _loan_payload(ctx.conn, q1(ctx.conn, "SELECT * FROM loans WHERE id = ?", (cur.lastrowid,)))


@route("GET", "/api/v1/loans/{id}")
def loans_detail(ctx: Ctx):
    loan_id = as_int(ctx.params["id"], "id", required=True)
    loan = q1(ctx.conn, """SELECT l.*, p.name AS person_name FROM loans l
                           JOIN persons p ON p.id = l.person_id WHERE l.id = ?""", (loan_id,))
    if not loan:
        raise ApiError("Loan not found", 404)
    payload = _loan_payload(ctx.conn, loan)
    payload["payments"] = q(ctx.conn, "SELECT * FROM loan_payments WHERE loan_id = ? ORDER BY date DESC, id DESC",
                            (loan_id,))
    payload["amortization"] = amortization_schedule(
        float(loan["outstanding"] or 0), float(loan["annual_rate"] or 0),
        float(loan["monthly_payment"] or 0),
    )
    return payload


@route("PUT", "/api/v1/loans/{id}")
def loans_update(ctx: Ctx):
    loan_id = as_int(ctx.params["id"], "id", required=True)
    if not q1(ctx.conn, "SELECT id FROM loans WHERE id = ?", (loan_id,)):
        raise ApiError("Loan not found", 404)
    body = body_dict(ctx.body)
    if "person_id" in body:
        body["person_id"] = as_int(body["person_id"], "person_id", required=True)
        ensure_person(ctx.conn, body["person_id"])
    for field_name in ("principal", "outstanding", "annual_rate", "monthly_payment"):
        if field_name in body:
            body[field_name] = as_float(body[field_name], field_name, default=0, minimum=0)
    if "term_months" in body:
        body["term_months"] = as_int(body["term_months"], "term_months", default=0, minimum=0, maximum=600)
    for field_name in ("start_date", "next_due_date"):
        if field_name in body:
            body[field_name] = as_date(body[field_name], field_name, False)
    if "status" in body:
        body["status"] = as_choice(body["status"], "status", {"active", "paid", "closed"}, "active")
    update_row(ctx.conn, "loans", loan_id, body,
               {"person_id", "name", "lender", "type", "principal", "outstanding", "currency",
                "annual_rate", "monthly_payment", "start_date", "term_months", "next_due_date",
                "status", "notes"})
    return _loan_payload(ctx.conn, q1(ctx.conn, "SELECT * FROM loans WHERE id = ?", (loan_id,)))


@route("DELETE", "/api/v1/loans/{id}")
def loans_delete(ctx: Ctx):
    loan_id = as_int(ctx.params["id"], "id", required=True)
    if not q1(ctx.conn, "SELECT id FROM loans WHERE id = ?", (loan_id,)):
        raise ApiError("Loan not found", 404)
    ctx.conn.execute("DELETE FROM loans WHERE id = ?", (loan_id,))
    return {"deleted": loan_id}


@route("POST", "/api/v1/loans/{id}/payments")
def loans_payment(ctx: Ctx):
    loan_id = as_int(ctx.params["id"], "id", required=True)
    loan = q1(ctx.conn, "SELECT * FROM loans WHERE id = ?", (loan_id,))
    if not loan:
        raise ApiError("Loan not found", 404)
    body = body_dict(ctx.body)
    amount = as_float(body.get("amount"), "amount", required=True, minimum=0.01)
    pay_date = as_date(body.get("date") or date.today().isoformat(), "date")
    monthly_rate = float(loan["annual_rate"] or 0) / 100.0 / 12.0
    interest = as_float(body.get("interest_component"), "interest_component",
                        default=finance.money(float(loan["outstanding"] or 0) * monthly_rate))
    principal = as_float(body.get("principal_component"), "principal_component",
                         default=max(0.0, amount - interest), minimum=0)
    if principal + interest <= 0:
        raise ApiError("Principal and interest cannot both be zero")
    new_outstanding = max(0.0, float(loan["outstanding"] or 0) - principal)
    status = "paid" if new_outstanding <= 0.01 else loan["status"]
    ctx.conn.execute(
        """INSERT INTO loan_payments(loan_id, date, amount, principal_component, interest_component,
               notes, created_at) VALUES(?,?,?,?,?,?,?)""",
        (loan_id, pay_date, amount, principal, interest, clean_text(body.get("notes"), 1000), now_iso()),
    )
    next_due = finance.add_months(datetime.strptime(pay_date, "%Y-%m-%d").date(), 1).isoformat()
    ctx.conn.execute(
        "UPDATE loans SET outstanding = ?, status = ?, next_due_date = ?, updated_at = ? WHERE id = ?",
        (new_outstanding, status, next_due, now_iso(), loan_id),
    )
    account_id = as_int(body.get("account_id"), "account_id")
    transaction = None
    if account_id:
        account = ensure_account(ctx.conn, account_id)
        if account["person_id"] != loan["person_id"]:
            raise ApiError("Loan and bank account belong to different people")
        transaction = create_transaction(ctx.conn, {
            "person_id": loan["person_id"], "account_id": account_id, "type": "loan_payment",
            "date": pay_date, "description": clean_text(body.get("description"), 300) or f"{loan['name']} payment",
            "amount": amount, "direction": "out", "currency": account["currency"],
            "notes": clean_text(body.get("notes"), 1000),
        })
    return {
        "loan": _loan_payload(ctx.conn, q1(ctx.conn, "SELECT * FROM loans WHERE id = ?", (loan_id,))),
        "transaction": transaction,
    }


# ---------------------------------------------------------------------------
# Assets and liabilities
# ---------------------------------------------------------------------------

@route("GET", "/api/v1/assets")
def assets_list(ctx: Ctx):
    person_id = query_person(ctx)
    sql = "SELECT a.*, p.name AS person_name FROM assets a JOIN persons p ON p.id = a.person_id"
    params: list = []
    if person_id:
        sql += " WHERE a.person_id = ?"
        params.append(person_id)
    sql += " ORDER BY a.value DESC, a.id"
    return q(ctx.conn, sql, params)


@route("GET", "/api/v1/assets/{id}")
def assets_detail(ctx: Ctx):
    asset_id = as_int(ctx.params["id"], "id", required=True)
    row = q1(ctx.conn, "SELECT * FROM assets WHERE id = ?", (asset_id,))
    if not row:
        raise ApiError("Asset not found", 404)
    return row


@route("POST", "/api/v1/assets")
def assets_create(ctx: Ctx):
    body = body_dict(ctx.body)
    person_id = as_int(body.get("person_id"), "person_id", required=True)
    ensure_person(ctx.conn, person_id)
    name = clean_text(body.get("name"), 80)
    if not name:
        raise ApiError("Asset name is required", field="name")
    stamp = now_iso()
    cur = ctx.conn.execute(
        """INSERT INTO assets(person_id, name, category, value, currency, acquired_date, is_liquid,
               notes, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (person_id, name, clean_text(body.get("category"), 40) or "other",
         as_float(body.get("value"), "value", default=0, minimum=0),
         clean_text(body.get("currency"), 8).upper() or "LKR",
         as_date(body.get("acquired_date"), "acquired_date", False),
         as_bool(body.get("is_liquid")), clean_text(body.get("notes"), 1000), stamp, stamp),
    )
    return q1(ctx.conn, "SELECT * FROM assets WHERE id = ?", (cur.lastrowid,))


@route("PUT", "/api/v1/assets/{id}")
def assets_update(ctx: Ctx):
    asset_id = as_int(ctx.params["id"], "id", required=True)
    if not q1(ctx.conn, "SELECT id FROM assets WHERE id = ?", (asset_id,)):
        raise ApiError("Asset not found", 404)
    body = body_dict(ctx.body)
    if "value" in body:
        body["value"] = as_float(body["value"], "value", default=0, minimum=0)
    if "acquired_date" in body:
        body["acquired_date"] = as_date(body["acquired_date"], "acquired_date", False)
    if "is_liquid" in body:
        body["is_liquid"] = as_bool(body["is_liquid"])
    update_row(ctx.conn, "assets", asset_id, body,
               {"person_id", "name", "category", "value", "currency", "acquired_date", "is_liquid", "notes"})
    return q1(ctx.conn, "SELECT * FROM assets WHERE id = ?", (asset_id,))


@route("DELETE", "/api/v1/assets/{id}")
def assets_delete(ctx: Ctx):
    asset_id = as_int(ctx.params["id"], "id", required=True)
    ctx.conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
    return {"deleted": asset_id}


@route("GET", "/api/v1/liabilities")
def liabilities_list(ctx: Ctx):
    person_id = query_person(ctx)
    sql = "SELECT l.*, p.name AS person_name FROM liabilities l JOIN persons p ON p.id = l.person_id"
    params: list = []
    if person_id:
        sql += " WHERE l.person_id = ?"
        params.append(person_id)
    sql += " ORDER BY l.balance DESC, l.id"
    return q(ctx.conn, sql, params)


@route("GET", "/api/v1/liabilities/{id}")
def liabilities_detail(ctx: Ctx):
    liability_id = as_int(ctx.params["id"], "id", required=True)
    row = q1(ctx.conn, "SELECT * FROM liabilities WHERE id = ?", (liability_id,))
    if not row:
        raise ApiError("Liability not found", 404)
    return row


@route("POST", "/api/v1/liabilities")
def liabilities_create(ctx: Ctx):
    body = body_dict(ctx.body)
    person_id = as_int(body.get("person_id"), "person_id", required=True)
    ensure_person(ctx.conn, person_id)
    name = clean_text(body.get("name"), 80)
    if not name:
        raise ApiError("Liability name is required", field="name")
    stamp = now_iso()
    cur = ctx.conn.execute(
        """INSERT INTO liabilities(person_id, name, category, balance, currency, annual_rate,
               monthly_payment, notes, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (person_id, name, clean_text(body.get("category"), 40) or "other",
         as_float(body.get("balance"), "balance", default=0, minimum=0),
         clean_text(body.get("currency"), 8).upper() or "LKR",
         as_float(body.get("annual_rate"), "annual_rate", default=0, minimum=0),
         as_float(body.get("monthly_payment"), "monthly_payment", default=0, minimum=0),
         clean_text(body.get("notes"), 1000), stamp, stamp),
    )
    return q1(ctx.conn, "SELECT * FROM liabilities WHERE id = ?", (cur.lastrowid,))


@route("PUT", "/api/v1/liabilities/{id}")
def liabilities_update(ctx: Ctx):
    liability_id = as_int(ctx.params["id"], "id", required=True)
    if not q1(ctx.conn, "SELECT id FROM liabilities WHERE id = ?", (liability_id,)):
        raise ApiError("Liability not found", 404)
    body = body_dict(ctx.body)
    for field_name in ("balance", "annual_rate", "monthly_payment"):
        if field_name in body:
            body[field_name] = as_float(body[field_name], field_name, default=0, minimum=0)
    update_row(ctx.conn, "liabilities", liability_id, body,
               {"person_id", "name", "category", "balance", "currency", "annual_rate",
                "monthly_payment", "notes"})
    return q1(ctx.conn, "SELECT * FROM liabilities WHERE id = ?", (liability_id,))


@route("DELETE", "/api/v1/liabilities/{id}")
def liabilities_delete(ctx: Ctx):
    liability_id = as_int(ctx.params["id"], "id", required=True)
    ctx.conn.execute("DELETE FROM liabilities WHERE id = ?", (liability_id,))
    return {"deleted": liability_id}


# ---------------------------------------------------------------------------
# Income
# ---------------------------------------------------------------------------

def _income_payload(conn, row: dict) -> dict:
    tx = q1(conn, "SELECT id, account_id FROM transactions WHERE income_id = ? LIMIT 1", (row["id"],))
    return {**row, "deposit_transaction_id": tx["id"] if tx else None,
            "deposit_account_id": tx["account_id"] if tx else None}


@route("GET", "/api/v1/incomes")
def incomes_list(ctx: Ctx):
    person_id = query_person(ctx)
    sql = """SELECT i.*, p.name AS person_name, c.name AS category_name, c.icon AS category_icon,
                    a.name AS account_name
             FROM incomes i JOIN persons p ON p.id = i.person_id
             LEFT JOIN categories c ON c.id = i.category_id
             LEFT JOIN accounts a ON a.id = i.account_id"""
    params: list = []
    if person_id:
        sql += " WHERE i.person_id = ?"
        params.append(person_id)
    if ctx.query.get("year_label"):
        start, end = finance.tax_year_range(ctx.query["year_label"])
        sql += " AND i.date >= ? AND i.date <= ?" if person_id else " WHERE i.date >= ? AND i.date <= ?"
        params.extend([start, end])
    if ctx.query.get("month"):
        start, end = finance.month_bounds(finance.as_month(ctx.query["month"]))
        sql += " AND i.date >= ? AND i.date < ?" if (person_id or ctx.query.get("year_label")) else " WHERE i.date >= ? AND i.date < ?"
        params.extend([start, end])
    sql += " ORDER BY i.date DESC, i.id DESC"
    return [_income_payload(ctx.conn, row) for row in q(ctx.conn, sql, params)]


@route("GET", "/api/v1/incomes/{id}")
def incomes_detail(ctx: Ctx):
    income_id = as_int(ctx.params["id"], "id", required=True)
    row = q1(ctx.conn, "SELECT * FROM incomes WHERE id = ?", (income_id,))
    if not row:
        raise ApiError("Income not found", 404)
    return _income_payload(ctx.conn, row)


@route("POST", "/api/v1/incomes")
def incomes_create(ctx: Ctx):
    body = body_dict(ctx.body)
    person_id = as_int(body.get("person_id"), "person_id", required=True)
    ensure_person(ctx.conn, person_id)
    amount = as_float(body.get("amount"), "amount", required=True, minimum=0)
    source = clean_text(body.get("source"), 120)
    if not source:
        raise ApiError("Income source is required", field="source")
    income_date = as_date(body.get("date") or date.today().isoformat(), "date")
    category_id = as_int(body.get("category_id"), "category_id")
    ensure_category(ctx.conn, category_id)
    account_id = as_int(body.get("account_id"), "account_id")
    if account_id:
        ensure_account(ctx.conn, account_id)
    stamp = now_iso()
    cur = ctx.conn.execute(
        """INSERT INTO incomes(person_id, date, source, category_id, amount, currency, frequency,
               is_taxable, tax_head, account_id, notes, created_at, updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (person_id, income_date, source, category_id, amount,
         clean_text(body.get("currency"), 8).upper() or "LKR",
         as_choice(body.get("frequency"), "frequency",
                   {"one_time", "monthly", "quarterly", "annual"}, "one_time"),
         as_bool(body.get("is_taxable"), True),
         as_choice(body.get("tax_head"), "tax_head", TAX_HEADS, "other"),
         account_id, clean_text(body.get("notes"), 1000), stamp, stamp),
    )
    income = q1(ctx.conn, "SELECT * FROM incomes WHERE id = ?", (cur.lastrowid,))
    if account_id and as_bool(body.get("deposit"), True):
        account = ensure_account(ctx.conn, account_id)
        create_transaction(ctx.conn, {
            "person_id": person_id, "account_id": account_id, "type": "income_deposit",
            "date": income_date, "description": source, "category_id": category_id,
            "amount": amount, "direction": "in", "currency": account["currency"],
            "income_id": income["id"], "notes": clean_text(body.get("notes"), 1000),
        })
    return _income_payload(ctx.conn, income)


@route("PUT", "/api/v1/incomes/{id}")
def incomes_update(ctx: Ctx):
    income_id = as_int(ctx.params["id"], "id", required=True)
    existing = q1(ctx.conn, "SELECT * FROM incomes WHERE id = ?", (income_id,))
    if not existing:
        raise ApiError("Income not found", 404)
    body = body_dict(ctx.body)
    if "person_id" in body:
        body["person_id"] = as_int(body["person_id"], "person_id", required=True)
        ensure_person(ctx.conn, body["person_id"])
    if "amount" in body:
        body["amount"] = as_float(body["amount"], "amount", required=True, minimum=0)
    if "date" in body:
        body["date"] = as_date(body["date"], "date")
    if "category_id" in body:
        body["category_id"] = as_int(body["category_id"], "category_id")
        ensure_category(ctx.conn, body["category_id"])
    if "account_id" in body:
        body["account_id"] = as_int(body["account_id"], "account_id")
        if body["account_id"]:
            ensure_account(ctx.conn, body["account_id"])
    if "tax_head" in body:
        body["tax_head"] = as_choice(body["tax_head"], "tax_head", TAX_HEADS, "other")
    if "is_taxable" in body:
        body["is_taxable"] = as_bool(body["is_taxable"], True)
    if "frequency" in body:
        body["frequency"] = as_choice(body["frequency"], "frequency",
                                      {"one_time", "monthly", "quarterly", "annual"}, "one_time")
    update_row(ctx.conn, "incomes", income_id, body,
               {"person_id", "date", "source", "category_id", "amount", "currency", "frequency",
                "is_taxable", "tax_head", "account_id", "notes"})
    # Keep an automatically-created deposit transaction in sync.
    linked = q1(ctx.conn, "SELECT * FROM transactions WHERE income_id = ? LIMIT 1", (income_id,))
    if linked:
        sets, values = [], []
        if "amount" in body:
            sets.append("amount = ?")
            values.append(body["amount"])
        if "date" in body:
            sets.append("date = ?")
            values.append(body["date"])
        if "source" in body:
            sets.append("description = ?")
            values.append(clean_text(body["source"], 300))
        if "category_id" in body:
            sets.append("category_id = ?")
            values.append(body["category_id"])
        if sets:
            sets.append("updated_at = ?")
            values.append(now_iso())
            values.append(linked["id"])
            ctx.conn.execute(f"UPDATE transactions SET {', '.join(sets)} WHERE id = ?", values)
    return _income_payload(ctx.conn, q1(ctx.conn, "SELECT * FROM incomes WHERE id = ?", (income_id,)))


@route("DELETE", "/api/v1/incomes/{id}")
def incomes_delete(ctx: Ctx):
    income_id = as_int(ctx.params["id"], "id", required=True)
    if not q1(ctx.conn, "SELECT id FROM incomes WHERE id = ?", (income_id,)):
        raise ApiError("Income not found", 404)
    ctx.conn.execute("DELETE FROM transactions WHERE income_id = ?", (income_id,))
    ctx.conn.execute("DELETE FROM incomes WHERE id = ?", (income_id,))
    return {"deleted": income_id}


@route("POST", "/api/v1/incomes/{id}/repeat")
def incomes_repeat(ctx: Ctx):
    income_id = as_int(ctx.params["id"], "id", required=True)
    income = q1(ctx.conn, "SELECT * FROM incomes WHERE id = ?", (income_id,))
    if not income:
        raise ApiError("Income not found", 404)
    body = body_dict(ctx.body)
    months = as_int(body.get("months"), "months", default=11, minimum=1, maximum=120)
    interval = {"monthly": 1, "quarterly": 3, "annual": 12, "one_time": 1}.get(income["frequency"], 1)
    start = datetime.strptime(income["date"], "%Y-%m-%d").date()
    created = []
    for index in range(1, months + 1):
        next_date = finance.add_months(start, interval * index)
        stamp = now_iso()
        cur = ctx.conn.execute(
            """INSERT INTO incomes(person_id, date, source, category_id, amount, currency, frequency,
                   is_taxable, tax_head, account_id, notes, created_at, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (income["person_id"], next_date.isoformat(), income["source"], income["category_id"],
             income["amount"], income["currency"], income["frequency"], income["is_taxable"],
             income["tax_head"], income["account_id"], income["notes"], stamp, stamp),
        )
        created.append(cur.lastrowid)
        if income["account_id"] and as_bool(body.get("deposit"), True):
            account = ensure_account(ctx.conn, income["account_id"])
            create_transaction(ctx.conn, {
                "person_id": income["person_id"], "account_id": income["account_id"],
                "type": "income_deposit", "date": next_date.isoformat(),
                "description": income["source"], "category_id": income["category_id"],
                "amount": income["amount"], "direction": "in",
                "currency": account["currency"], "income_id": cur.lastrowid,
            })
    return {"created": created, "count": len(created)}


# ---------------------------------------------------------------------------
# Budgets and goals
# ---------------------------------------------------------------------------

@route("GET", "/api/v1/budgets")
def budgets_list(ctx: Ctx):
    month = finance.as_month(ctx.query.get("month"), "month")
    person_id = query_person(ctx)
    sql = """SELECT b.*, c.name AS category_name, c.icon AS category_icon, c.color AS category_color
             FROM budgets b JOIN categories c ON c.id = b.category_id WHERE b.month = ?"""
    params: list = [month]
    if person_id:
        sql += " AND b.person_id = ?"
        params.append(person_id)
    rows = q(ctx.conn, sql, params)
    start, end = finance.month_bounds(month)
    for row in rows:
        spent = 0.0
        for tx in q(ctx.conn,
                    """SELECT amount, direction FROM transactions
                       WHERE category_id = ? AND date >= ? AND date < ? AND type IN
                       ('purchase','installment','fee','interest','cash_advance','expense')""",
                    (row["category_id"], start, end)):
            spent += -tx["amount"] if tx["direction"] == "in" else tx["amount"]
        row["spent"] = finance.money(spent)
        row["remaining"] = finance.money(float(row["amount"]) - spent)
        row["utilization"] = finance.pct(spent, float(row["amount"]))
    return rows


@route("POST", "/api/v1/budgets")
def budgets_create(ctx: Ctx):
    body = body_dict(ctx.body)
    person_id = as_int(body.get("person_id"), "person_id", required=True)
    ensure_person(ctx.conn, person_id)
    category_id = as_int(body.get("category_id"), "category_id", required=True)
    ensure_category(ctx.conn, category_id)
    month = finance.as_month(body.get("month"), "month")
    amount = as_float(body.get("amount"), "amount", required=True, minimum=0)
    existing = q1(ctx.conn, "SELECT id FROM budgets WHERE person_id = ? AND month = ? AND category_id = ?",
                  (person_id, month, category_id))
    if existing:
        ctx.conn.execute("UPDATE budgets SET amount = ? WHERE id = ?", (amount, existing["id"]))
        budget_id = existing["id"]
    else:
        cur = ctx.conn.execute(
            "INSERT INTO budgets(person_id, month, category_id, amount, created_at) VALUES(?,?,?,?,?)",
            (person_id, month, category_id, amount, now_iso()),
        )
        budget_id = cur.lastrowid
    return q1(ctx.conn, "SELECT * FROM budgets WHERE id = ?", (budget_id,))


@route("DELETE", "/api/v1/budgets/{id}")
def budgets_delete(ctx: Ctx):
    budget_id = as_int(ctx.params["id"], "id", required=True)
    ctx.conn.execute("DELETE FROM budgets WHERE id = ?", (budget_id,))
    return {"deleted": budget_id}


@route("GET", "/api/v1/goals")
def goals_list(ctx: Ctx):
    person_id = query_person(ctx)
    sql = "SELECT g.*, p.name AS person_name FROM goals g JOIN persons p ON p.id = g.person_id"
    params: list = []
    if person_id:
        sql += " WHERE g.person_id = ?"
        params.append(person_id)
    sql += " ORDER BY g.id"
    rows = q(ctx.conn, sql, params)
    for row in rows:
        row["progress"] = finance.pct(float(row["saved_amount"]), float(row["target_amount"]))
    return rows


@route("POST", "/api/v1/goals")
def goals_create(ctx: Ctx):
    body = body_dict(ctx.body)
    person_id = as_int(body.get("person_id"), "person_id", required=True)
    ensure_person(ctx.conn, person_id)
    name = clean_text(body.get("name"), 80)
    if not name:
        raise ApiError("Goal name is required", field="name")
    stamp = now_iso()
    cur = ctx.conn.execute(
        """INSERT INTO goals(person_id, name, target_amount, saved_amount, target_date, notes,
               created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)""",
        (person_id, name, as_float(body.get("target_amount"), "target_amount", default=0, minimum=0),
         as_float(body.get("saved_amount"), "saved_amount", default=0, minimum=0),
         as_date(body.get("target_date"), "target_date", False), clean_text(body.get("notes"), 1000),
         stamp, stamp),
    )
    return q1(ctx.conn, "SELECT * FROM goals WHERE id = ?", (cur.lastrowid,))


@route("PUT", "/api/v1/goals/{id}")
def goals_update(ctx: Ctx):
    goal_id = as_int(ctx.params["id"], "id", required=True)
    if not q1(ctx.conn, "SELECT id FROM goals WHERE id = ?", (goal_id,)):
        raise ApiError("Goal not found", 404)
    body = body_dict(ctx.body)
    for field_name in ("target_amount", "saved_amount"):
        if field_name in body:
            body[field_name] = as_float(body[field_name], field_name, default=0, minimum=0)
    if "target_date" in body:
        body["target_date"] = as_date(body["target_date"], "target_date", False)
    update_row(ctx.conn, "goals", goal_id, body,
               {"person_id", "name", "target_amount", "saved_amount", "target_date", "notes"})
    return q1(ctx.conn, "SELECT * FROM goals WHERE id = ?", (goal_id,))


@route("DELETE", "/api/v1/goals/{id}")
def goals_delete(ctx: Ctx):
    goal_id = as_int(ctx.params["id"], "id", required=True)
    ctx.conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
    return {"deleted": goal_id}
