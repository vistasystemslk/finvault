"""Financial calculations: balances, dashboard, analytics, tax and insights."""
from __future__ import annotations

import calendar
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from .db import q, q1, scalar

EXPENSE_TYPES = {"purchase", "installment", "fee", "interest", "cash_advance", "expense"}
CARD_DEBT_TYPES = {"purchase", "installment", "fee", "interest", "cash_advance"}
CARD_CREDIT_TYPES = {"payment", "refund", "adjustment"}


# ---------------------------------------------------------------------------
# Dates and money
# ---------------------------------------------------------------------------

def today_iso() -> str:
    return date.today().isoformat()


def as_month(value: str | None, field: str = "month") -> str:
    text = str(value or "").strip()[:7]
    try:
        return datetime.strptime(text, "%Y-%m").strftime("%Y-%m")
    except ValueError:
        return date.today().strftime("%Y-%m")


def month_start(month: str) -> date:
    return datetime.strptime(month + "-01", "%Y-%m-%d").date()


def add_months(d: date, months: int) -> date:
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def month_bounds(month: str) -> tuple[str, str]:
    start = month_start(month)
    end = add_months(start, 1)
    return start.isoformat(), end.isoformat()


def last_months(month: str, count: int) -> list[str]:
    start = month_start(month)
    return [add_months(start, -(count - 1 - i)).strftime("%Y-%m") for i in range(count)]


def next_due_date(day: int, reference: date | None = None) -> str:
    reference = reference or date.today()
    if not day or day < 1:
        return ""
    day = min(day, 28)
    year, month = reference.year, reference.month
    candidate = date(year, month, min(day, calendar.monthrange(year, month)[1]))
    if candidate < reference:
        nxt = add_months(date(year, month, 1), 1)
        candidate = date(nxt.year, nxt.month, min(day, calendar.monthrange(nxt.year, nxt.month)[1]))
    return candidate.isoformat()


def days_until(iso: str) -> int | None:
    if not iso:
        return None
    try:
        return (datetime.strptime(iso, "%Y-%m-%d").date() - date.today()).days
    except ValueError:
        return None


def tax_year_range(year_label: str) -> tuple[str, str]:
    label = (year_label or "").strip()
    try:
        start_year = int(label.split("/")[0])
    except (ValueError, IndexError):
        start_year = date.today().year
        if date.today().month >= 4:
            pass
        else:
            start_year -= 1
    end_year = start_year + 1
    return f"{start_year}-04-01", f"{end_year}-03-31"


def current_tax_year() -> str:
    today = date.today()
    start = today.year if today.month >= 4 else today.year - 1
    return f"{start}/{(start + 1) % 100:02d}"


def fx_map(conn) -> dict[str, float]:
    return {r["currency"]: float(r["rate"] or 1) for r in q(conn, "SELECT currency, rate FROM fx_rates")}


def to_base(amount: float, currency: str | None, rates: dict[str, float], base: str = "LKR") -> float:
    if not currency or currency == base:
        return float(amount or 0)
    rate = rates.get(currency)
    if not rate:
        return float(amount or 0)
    return float(amount or 0) * rate


def money(value: float) -> float:
    return round(float(value or 0) + 1e-9, 2)


def pct(part: float, whole: float, digits: int = 1) -> float:
    if not whole:
        return 0.0
    return round(part / whole * 100.0, digits)


# ---------------------------------------------------------------------------
# Balances
# ---------------------------------------------------------------------------

def card_balance(conn, card_id: int) -> float:
    card = q1(conn, "SELECT opening_balance FROM cards WHERE id = ?", (card_id,))
    if not card:
        return 0.0
    signed = scalar(
        conn,
        """SELECT COALESCE(SUM(CASE WHEN direction = 'in' THEN -amount ELSE amount END), 0)
           FROM transactions WHERE card_id = ?""",
        (card_id,),
    )
    return money(card["opening_balance"] + signed)


def account_balance(conn, account_id: int) -> float:
    account = q1(conn, "SELECT opening_balance FROM accounts WHERE id = ?", (account_id,))
    if not account:
        return 0.0
    signed = scalar(
        conn,
        """SELECT COALESCE(SUM(CASE WHEN direction = 'in' THEN amount ELSE -amount END), 0)
           FROM transactions WHERE account_id = ?""",
        (account_id,),
    )
    return money(account["opening_balance"] + signed)


def loan_total(conn, person_id: int | None = None) -> float:
    sql = "SELECT COALESCE(SUM(outstanding), 0) FROM loans WHERE status = 'active'"
    params: list[Any] = []
    if person_id:
        sql += " AND person_id = ?"
        params.append(person_id)
    return money(scalar(conn, sql, params))


def assets_total(conn, person_id: int | None = None) -> float:
    sql = "SELECT COALESCE(SUM(value), 0) FROM assets"
    params: list[Any] = []
    if person_id:
        sql += " WHERE person_id = ?"
        params.append(person_id)
    return money(scalar(conn, sql, params))


def liabilities_total(conn, person_id: int | None = None) -> float:
    sql = "SELECT COALESCE(SUM(balance), 0) FROM liabilities"
    params: list[Any] = []
    if person_id:
        sql += " WHERE person_id = ?"
        params.append(person_id)
    return money(scalar(conn, sql, params))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def dashboard(conn, person_id: int | None = None, month: str | None = None) -> dict:
    month = month or date.today().strftime("%Y-%m")
    start, end = month_bounds(month)
    rates = fx_map(conn)
    person_name = ""
    if person_id:
        row = q1(conn, "SELECT name FROM persons WHERE id = ?", (person_id,))
        person_name = row["name"] if row else ""

    card_sql = "SELECT c.*, p.name AS person_name FROM cards c JOIN persons p ON p.id = c.person_id"
    card_params: list[Any] = []
    if person_id:
        card_sql += " WHERE c.person_id = ?"
        card_params.append(person_id)
    card_sql += " ORDER BY c.status, c.id"
    cards = q(conn, card_sql, card_params)

    unpaid_statements = {}
    for st in q(conn, """SELECT * FROM statements WHERE status IN ('unpaid','partial','overdue')
                         ORDER BY due_date ASC"""):
        unpaid_statements.setdefault(st["card_id"], st)

    card_rows = []
    total_outstanding = 0.0
    total_limit = 0.0
    total_available = 0.0
    total_min_due = 0.0
    for card in cards:
        if card["status"] != "active" and card_balance(conn, card["id"]) <= 0:
            continue
        outstanding = card_balance(conn, card["id"])
        limit = float(card["credit_limit"] or 0)
        rate = rates.get(card["currency"], 1)
        outstanding_base = outstanding * rate
        limit_base = limit * rate
        available = max(0.0, limit - outstanding)
        st = unpaid_statements.get(card["id"])
        due_amount = 0.0
        due_date = ""
        minimum = 0.0
        if st:
            due_amount = max(0.0, float(st["closing_balance"]) - float(st["amount_paid"]))
            minimum = max(0.0, float(st["minimum_due"]) - float(st["amount_paid"]))
            due_date = st["due_date"]
        elif outstanding > 0:
            due_amount = outstanding
            minimum = max(0.0, outstanding * 0.05)
            due_date = next_due_date(int(card["due_day"] or 0))
        total_outstanding += outstanding_base
        total_limit += limit_base
        total_available += max(0.0, available * rate)
        total_min_due += minimum * rate
        card_rows.append({
            **card,
            "outstanding": money(outstanding),
            "available": money(available),
            "utilization": pct(outstanding, limit),
            "outstanding_base": money(outstanding_base),
            "due_amount": money(due_amount),
            "minimum_due": money(minimum),
            "due_date": due_date,
            "has_statement": bool(st),
            "days_to_due": days_until(due_date),
        })

    account_sql = "SELECT a.*, p.name AS person_name FROM accounts a JOIN persons p ON p.id = a.person_id"
    account_params: list[Any] = []
    if person_id:
        account_sql += " WHERE a.person_id = ?"
        account_params.append(person_id)
    account_sql += " ORDER BY a.is_active DESC, a.id"
    account_rows = []
    bank_total = 0.0
    for account in q(conn, account_sql, account_params):
        balance = account_balance(conn, account["id"])
        rate = rates.get(account["currency"], 1)
        bank_total += balance * rate
        account_rows.append({**account, "balance": money(balance), "balance_base": money(balance * rate)})

    assets = assets_total(conn, person_id)
    liabilities = liabilities_total(conn, person_id)
    loans = loan_total(conn, person_id)
    net_worth = bank_total + assets - total_outstanding - loans - liabilities

    income_rows = q(conn, "SELECT * FROM incomes WHERE date >= ? AND date < ?" +
                    (" AND person_id = ?" if person_id else ""),
                    [start, end] + ([person_id] if person_id else []))
    income = sum(to_base(r["amount"], r["currency"], rates) for r in income_rows)

    tx_sql = """SELECT t.*, c.name AS category_name, c.color AS category_color, c.icon AS category_icon
                FROM transactions t LEFT JOIN categories c ON c.id = t.category_id
                WHERE t.date >= ? AND t.date < ?"""
    tx_params: list[Any] = [start, end]
    if person_id:
        tx_sql += " AND t.person_id = ?"
        tx_params.append(person_id)
    tx_sql += " ORDER BY t.date DESC, t.id DESC"
    month_tx = q(conn, tx_sql, tx_params)

    expenses = 0.0
    business_spend = 0.0
    personal_spend = 0.0
    tax_deductible = 0.0
    card_payments = 0.0
    loan_payments = 0.0
    for tx in month_tx:
        amount = to_base(tx["amount"], tx["currency"], rates)
        if tx["type"] in EXPENSE_TYPES:
            if tx["direction"] == "in":
                expenses -= amount
                if tx["is_business"]:
                    business_spend -= amount
                else:
                    personal_spend -= amount
            else:
                expenses += amount
                if tx["is_business"]:
                    business_spend += amount
                else:
                    personal_spend += amount
            if tx["tax_deductible"]:
                tax_deductible += amount if tx["direction"] == "out" else -amount
        elif tx["type"] == "refund":
            expenses -= amount
        elif tx["type"] == "payment" and tx["card_id"]:
            card_payments += amount
        elif tx["type"] == "loan_payment" and tx["account_id"]:
            loan_payments += amount

    trend = []
    for m in last_months(month, 6):
        m_start, m_end = month_bounds(m)
        m_income = sum(to_base(r["amount"], r["currency"], rates) for r in q(
            conn,
            "SELECT amount, currency FROM incomes WHERE date >= ? AND date < ?" +
            (" AND person_id = ?" if person_id else ""),
            [m_start, m_end] + ([person_id] if person_id else []),
        ))
        m_expense = 0.0
        for row in q(conn,
                     """SELECT type, direction, amount, currency FROM transactions
                        WHERE date >= ? AND date < ?""" + (" AND person_id = ?" if person_id else ""),
                     [m_start, m_end] + ([person_id] if person_id else [])):
            amt = to_base(row["amount"], row["currency"], rates)
            if row["type"] in EXPENSE_TYPES:
                m_expense += -amt if row["direction"] == "in" else amt
            elif row["type"] == "refund":
                m_expense -= amt
        trend.append({
            "month": m,
            "income": money(m_income),
            "expenses": money(m_expense),
            "net": money(m_income - m_expense),
        })

    category_totals: dict[str, dict] = {}
    for tx in month_tx:
        if tx["type"] not in EXPENSE_TYPES and tx["type"] != "refund":
            continue
        amount = to_base(tx["amount"], tx["currency"], rates)
        if tx["type"] == "refund" or tx["direction"] == "in":
            amount = -amount
        name = tx["category_name"] or "Uncategorized"
        bucket = category_totals.setdefault(name, {
            "name": name,
            "color": tx["category_color"] or "#94a3b8",
            "icon": tx["category_icon"] or "•",
            "amount": 0.0,
        })
        bucket["amount"] += amount
    spend_by_category = sorted(
        [v for v in category_totals.values() if v["amount"] > 0],
        key=lambda item: item["amount"], reverse=True,
    )

    upcoming = _upcoming(conn, person_id, rates)
    insights = build_insights(conn, person_id, month)

    recent_sql = """SELECT t.*, c.name AS category_name, c.icon AS category_icon, c.color AS category_color,
                           cd.name AS card_name, a.name AS account_name
                    FROM transactions t
                    LEFT JOIN categories c ON c.id = t.category_id
                    LEFT JOIN cards cd ON cd.id = t.card_id
                    LEFT JOIN accounts a ON a.id = t.account_id"""
    recent_params: list[Any] = []
    if person_id:
        recent_sql += " WHERE t.person_id = ?"
        recent_params.append(person_id)
    recent_sql += " ORDER BY t.date DESC, t.id DESC LIMIT 8"
    recent = q(conn, recent_sql, recent_params)

    return {
        "month": month,
        "person_id": person_id,
        "person_name": person_name,
        "summary": {
            "net_worth": money(net_worth),
            "total_card_outstanding": money(total_outstanding),
            "total_credit_limit": money(total_limit),
            "total_available_credit": money(total_available),
            "credit_utilization": pct(total_outstanding, total_limit),
            "bank_balance": money(bank_total),
            "assets_value": money(assets),
            "loans_outstanding": money(loans),
            "liabilities_total": money(liabilities),
            "minimum_due": money(total_min_due),
            "month_income": money(income),
            "month_expenses": money(expenses),
            "month_net": money(income - expenses - loan_payments),
            "month_business_spend": money(business_spend),
            "month_personal_spend": money(personal_spend),
            "month_tax_deductible": money(tax_deductible),
            "month_card_payments": money(card_payments),
            "month_loan_payments": money(loan_payments),
            "savings_rate": pct(income - expenses - loan_payments, income),
            "debt_to_assets": pct(total_outstanding + loans + liabilities, bank_total + assets),
        },
        "cards": card_rows,
        "accounts": account_rows,
        "upcoming": upcoming,
        "reminders": reminders(conn, person_id),
        "trend": trend,
        "spend_by_category": spend_by_category,
        "recent": recent,
        "insights": insights,
    }


def _upcoming(conn, person_id: int | None, rates: dict[str, float]) -> list[dict]:
    items: list[dict] = []
    today = date.today()
    horizon = today + timedelta(days=45)
    card_filter = " AND c.person_id = ?" if person_id else ""
    card_params: list[Any] = [person_id] if person_id else []

    statements = q(conn,
                   """SELECT s.*, c.name AS card_name, c.currency
                      FROM statements s JOIN cards c ON c.id = s.card_id
                      WHERE s.status IN ('unpaid','partial','overdue')
                        AND s.due_date >= ? AND s.due_date <= ?""" + card_filter +
                   " ORDER BY s.due_date",
                   [today.isoformat(), horizon.isoformat()] + card_params)
    for st in statements:
        amount = max(0.0, float(st["closing_balance"]) - float(st["amount_paid"]))
        if amount <= 0:
            continue
        items.append({
            "kind": "card_statement",
            "name": f"{st['card_name']} statement",
            "detail": f"Statement due {st['due_date']}",
            "amount": money(amount * rates.get(st["currency"], 1)),
            "due_date": st["due_date"],
            "days_left": days_until(st["due_date"]),
            "card_id": st["card_id"],
        })

    loan_rows = q(conn,
                  "SELECT * FROM loans WHERE status = 'active'" + (" AND person_id = ?" if person_id else ""),
                  [person_id] if person_id else [])
    for loan in loan_rows:
        # Interest-only facilities carry no scheduled instalment until the amount is known.
        if float(loan["monthly_payment"] or 0) <= 0:
            continue
        due = loan["next_due_date"] or next_due_date(int(datetime.strptime(loan["start_date"], "%Y-%m-%d").day)
                                                     if loan["start_date"] else 1)
        if due and due <= horizon.isoformat():
            items.append({
                "kind": "loan",
                "name": f"{loan['name']} payment",
                "detail": loan["lender"] or loan["type"],
                "amount": money(float(loan["monthly_payment"] or 0) * rates.get(loan["currency"], 1)),
                "due_date": due,
                "days_left": days_until(due),
                "loan_id": loan["id"],
            })

    inst = q(conn, """SELECT i.*, c.name AS card_name, c.currency, c.person_id
                      FROM installment_plans i JOIN cards c ON c.id = i.card_id
                      WHERE i.status = 'active'""" + card_filter, card_params)
    for plan in inst:
        due = plan["first_due_date"] or ""
        if not due:
            continue
        # Roll forward to the next monthly due date.
        try:
            due_date = datetime.strptime(due, "%Y-%m-%d").date()
            while due_date < today:
                due_date = add_months(due_date, 1)
            due_iso = due_date.isoformat()
        except ValueError:
            continue
        if due_iso <= horizon.isoformat():
            items.append({
                "kind": "installment",
                "name": plan["description"],
                "detail": f"{plan['card_name']} · {plan['remaining_months']} of {plan['months']} remaining",
                "amount": money(float(plan["monthly_amount"] or 0) * rates.get(plan["currency"], 1)),
                "due_date": due_iso,
                "days_left": days_until(due_iso),
                "card_id": plan["card_id"],
                "installment_id": plan["id"],
            })

    return sorted(items, key=lambda item: item["due_date"])


def reminders(conn, person_id: int | None = None, horizon_days: int = 21) -> list[dict]:
    """Everything needing attention: overdue first, then the next `horizon_days`."""
    today = date.today()
    horizon_iso = (today + timedelta(days=horizon_days)).isoformat()
    rates = fx_map(conn)
    items: list[dict] = []

    def status_of(due_iso: str) -> str:
        days = days_until(due_iso)
        if days is None:
            return "upcoming"
        if days < 0:
            return "overdue"
        if days == 0:
            return "today"
        if days <= 3:
            return "soon"
        return "upcoming"

    def add(kind: str, name: str, detail: str, amount: float, due_iso: str, **extra) -> None:
        if not due_iso or due_iso > horizon_iso:
            return
        items.append({
            "kind": kind,
            "name": name,
            "detail": detail,
            "amount": money(amount),
            "due_date": due_iso,
            "days_left": days_until(due_iso),
            "status": status_of(due_iso),
            **extra,
        })

    card_filter = " AND c.person_id = ?" if person_id else ""
    card_params: list[Any] = [person_id] if person_id else []

    for st in q(conn,
                """SELECT s.*, c.name AS card_name, c.currency
                   FROM statements s JOIN cards c ON c.id = s.card_id
                   WHERE s.status IN ('unpaid','partial','overdue') AND s.due_date <> ''""" + card_filter,
                card_params):
        remaining = max(0.0, float(st["closing_balance"]) - float(st["amount_paid"]))
        if remaining <= 0:
            continue
        add("card_statement", f"{st['card_name']} statement",
            f"Minimum due Rs {float(st['minimum_due'] or 0):,.0f}",
            remaining * rates.get(st["currency"], 1), st["due_date"], card_id=st["card_id"])

    for loan in q(conn, "SELECT * FROM loans WHERE status = 'active'" +
                  (" AND person_id = ?" if person_id else ""), [person_id] if person_id else []):
        if float(loan["monthly_payment"] or 0) <= 0:
            continue
        due = loan["next_due_date"] or ""
        add("loan", f"{loan['name']} instalment", loan["lender"] or loan["type"],
            float(loan["monthly_payment"]) * rates.get(loan["currency"], 1), due, loan_id=loan["id"])

    for plan in q(conn,
                  """SELECT i.*, c.name AS card_name, c.currency FROM installment_plans i
                     JOIN cards c ON c.id = i.card_id
                     WHERE i.status = 'active' AND i.remaining_months > 0""" + card_filter, card_params):
        due = plan["first_due_date"] or ""
        if not due:
            continue
        try:
            due_date = datetime.strptime(due, "%Y-%m-%d").date()
            while due_date < today:
                due_date = add_months(due_date, 1)
        except ValueError:
            continue
        add("installment", plan["description"],
            f"{plan['card_name']} · {plan['remaining_months']} of {plan['months']} remaining",
            float(plan["monthly_amount"] or 0) * rates.get(plan["currency"], 1),
            due_date.isoformat(), card_id=plan["card_id"], installment_id=plan["id"])

    for row in q(conn, "SELECT * FROM scheduled WHERE is_active = 1" +
                 (" AND person_id = ?" if person_id else ""), [person_id] if person_id else []):
        add("scheduled", row["name"], row["notes"] or row["frequency"],
            float(row["amount"] or 0) * rates.get(row["currency"], 1), row["next_due_date"],
            scheduled_id=row["id"])

    order = {"overdue": 0, "today": 1, "soon": 2, "upcoming": 3}
    return sorted(items, key=lambda item: (order.get(item["status"], 4), item["due_date"], item["name"]))


# ---------------------------------------------------------------------------
# Spending analytics
# ---------------------------------------------------------------------------

def spending_analytics(conn, person_id: int | None = None, start: str | None = None,
                       end: str | None = None) -> dict:
    rates = fx_map(conn)
    if not start:
        start = (date.today().replace(day=1) - timedelta(days=180)).isoformat()
    if not end:
        end = today_iso()
    sql = """SELECT t.*, c.name AS category_name, c.color AS category_color,
                    cd.name AS card_name, a.name AS account_name
             FROM transactions t
             LEFT JOIN categories c ON c.id = t.category_id
             LEFT JOIN cards cd ON cd.id = t.card_id
             LEFT JOIN accounts a ON a.id = t.account_id
             WHERE t.date >= ? AND t.date <= ?"""
    params: list[Any] = [start, end]
    if person_id:
        sql += " AND t.person_id = ?"
        params.append(person_id)
    rows = q(conn, sql, params)

    categories: dict[str, dict] = {}
    merchants: dict[str, float] = {}
    cards: dict[str, float] = {}
    monthly: dict[str, dict] = defaultdict(lambda: {"income": 0.0, "expenses": 0.0})
    business = 0.0
    personal = 0.0
    deductible = 0.0
    total_spend = 0.0
    biggest = []
    for tx in rows:
        amount = to_base(tx["amount"], tx["currency"], rates)
        if tx["type"] in EXPENSE_TYPES:
            if tx["direction"] == "in":
                amount = -amount
            total_spend += amount
            if tx["is_business"]:
                business += amount
            else:
                personal += amount
            if tx["tax_deductible"]:
                deductible += amount
            name = tx["category_name"] or "Uncategorized"
            bucket = categories.setdefault(name, {
                "name": name, "color": tx["category_color"] or "#94a3b8", "amount": 0.0,
            })
            bucket["amount"] += amount
            merchant = (tx["description"] or "Unknown").strip()
            merchants[merchant] = merchants.get(merchant, 0) + amount
            card_key = tx["card_name"] or tx["account_name"] or "Other"
            cards[card_key] = cards.get(card_key, 0) + amount
            monthly[tx["date"][:7]]["expenses"] += amount
            biggest.append({
                "date": tx["date"], "description": merchant, "amount": money(amount),
                "category": name, "card_id": tx["card_id"], "id": tx["id"],
            })
        elif tx["type"] == "refund":
            total_spend -= amount
            if tx["is_business"]:
                business -= amount
            else:
                personal -= amount
            monthly[tx["date"][:7]]["expenses"] -= amount

    income_sql = "SELECT date, amount, currency FROM incomes WHERE date >= ? AND date <= ?"
    income_params: list[Any] = [start, end]
    if person_id:
        income_sql += " AND person_id = ?"
        income_params.append(person_id)
    for row in q(conn, income_sql, income_params):
        monthly[row["date"][:7]]["income"] += to_base(row["amount"], row["currency"], rates)

    return {
        "range": {"start": start, "end": end},
        "total_spend": money(total_spend),
        "business_spend": money(business),
        "personal_spend": money(personal),
        "tax_deductible": money(deductible),
        "categories": sorted(categories.values(), key=lambda item: item["amount"], reverse=True),
        "merchants": [{"name": k, "amount": money(v)} for k, v in
                      sorted(merchants.items(), key=lambda item: item[1], reverse=True)[:15]],
        "cards": [{"name": k, "amount": money(v)} for k, v in
                  sorted(cards.items(), key=lambda item: item[1], reverse=True)],
        "monthly": [{"month": k, **{kk: money(vv) for kk, vv in v.items()}}
                    for k, v in sorted(monthly.items())],
        "biggest": sorted(biggest, key=lambda item: item["amount"], reverse=True)[:10],
        "subscriptions": detect_subscriptions(conn, person_id, rates),
    }


def detect_subscriptions(conn, person_id: int | None = None, rates: dict | None = None) -> list[dict]:
    rates = rates or fx_map(conn)
    sql = """SELECT t.description, t.date, t.amount, t.currency, c.name AS category
             FROM transactions t LEFT JOIN categories c ON c.id = t.category_id
             WHERE t.type IN ('purchase','installment','expense') AND t.direction = 'out'
               AND t.date >= ?"""
    params: list[Any] = [(date.today() - timedelta(days=240)).isoformat()]
    if person_id:
        sql += " AND t.person_id = ?"
        params.append(person_id)
    groups: dict[str, list[dict]] = defaultdict(list)
    skip_categories = {"Transport", "Fuel", "Groceries", "Dining", "Healthcare", "Shopping"}
    for row in q(conn, sql, params):
        if row["category"] in skip_categories:
            continue
        key = " ".join((row["description"] or "").upper().split())[:60]
        if not key:
            continue
        groups[key].append({
            "month": row["date"][:7],
            "amount": to_base(row["amount"], row["currency"], rates),
        })
    found = []
    for key, rows in groups.items():
        months = {r["month"] for r in rows}
        if len(months) < 3:
            continue
        # A subscription bills once (occasionally twice) a month; tolls and fuel do not.
        if len(rows) > len(months) * 2:
            continue
        amounts = [r["amount"] for r in rows]
        avg = sum(amounts) / len(amounts)
        if avg <= 0:
            continue
        similar = all(abs(a - avg) <= max(avg * 0.08, 5) for a in amounts)
        if similar:
            found.append({
                "name": key.title(),
                "average": money(avg),
                "months": len(months),
                "annual_cost": money(avg * 12),
            })
    return sorted(found, key=lambda item: item["annual_cost"], reverse=True)[:10]


# ---------------------------------------------------------------------------
# Tax
# ---------------------------------------------------------------------------

def get_tax_rules(conn, year_label: str) -> dict | None:
    row = q1(conn, "SELECT * FROM tax_rules WHERE year_label = ?", (year_label,))
    if not row:
        row = q1(conn, "SELECT * FROM tax_rules ORDER BY year_label DESC LIMIT 1")
    if not row:
        return None
    row["slabs"] = json.loads(row["slabs_json"] or "[]")
    return row


def _slab_calc(taxable: float, slabs: list[dict]) -> tuple[float, list[dict], float]:
    tax = 0.0
    breakdown = []
    previous = 0.0
    marginal = 0.0
    for slab in slabs:
        upper = slab.get("upto")
        rate = float(slab.get("rate") or 0)
        top = float(upper) if upper not in (None, "", 0) else None
        band_top = top if top is not None else taxable
        amount = max(0.0, min(taxable, band_top) - previous)
        if top is not None and taxable > previous:
            marginal = rate
        if amount > 0:
            tax += amount * rate
            breakdown.append({
                "from": money(previous),
                "to": money(top) if top is not None else None,
                "rate": rate,
                "amount": money(amount),
                "tax": money(amount * rate),
            })
        if top is not None:
            previous = top
        if top is not None and taxable <= top:
            break
    return money(tax), breakdown, marginal


def tax_estimate(conn, person_id: int, year_label: str | None = None) -> dict:
    year_label = year_label or current_tax_year()
    rules = get_tax_rules(conn, year_label)
    if not rules:
        raise ValueError("No tax rules configured")
    start, end = tax_year_range(year_label)
    rates = fx_map(conn)

    person = q1(conn, "SELECT * FROM persons WHERE id = ?", (person_id,))
    if not person:
        raise ValueError("Person not found")

    heads = {"employment": 0.0, "business": 0.0, "investment": 0.0, "rental": 0.0, "other": 0.0}
    income_rows = q(conn,
                    """SELECT * FROM incomes WHERE person_id = ? AND is_taxable = 1
                       AND date >= ? AND date <= ?""",
                    (person_id, start, end))
    for row in income_rows:
        head = row["tax_head"] if row["tax_head"] in heads else "other"
        heads[head] += to_base(row["amount"], row["currency"], rates)

    # Tax-deductible business expenses recorded against cards/accounts.
    deductible = 0.0
    for tx in q(conn,
                """SELECT amount, currency, direction FROM transactions
                   WHERE person_id = ? AND tax_deductible = 1 AND date >= ? AND date <= ?
                     AND type IN ('purchase','installment','fee','interest','cash_advance','expense')""",
                (person_id, start, end)):
        amount = to_base(tx["amount"], tx["currency"], rates)
        deductible += -amount if tx["direction"] == "in" else amount
    used_deduction = min(deductible, heads["business"])
    heads["business"] = max(0.0, heads["business"] - used_deduction)

    relief_rows = q(conn, "SELECT * FROM tax_reliefs WHERE person_id = ? AND year_label = ?",
                    (person_id, year_label))
    qualifying = sum(float(r["amount"] or 0) for r in relief_rows)
    rent_pct = float(rules["rent_relief_pct"] or 0)
    rent_cap = float(rules["rent_relief_cap"] or 0)
    rent_relief = heads["rental"] * rent_pct / 100.0
    if rent_cap > 0:
        rent_relief = min(rent_relief, rent_cap)

    total_assessable = sum(heads.values())
    total_reliefs = qualifying + rent_relief
    taxable = max(0.0, total_assessable - total_reliefs)
    gross_tax, breakdown, marginal = _slab_calc(taxable, rules["slabs"])

    credit_rows = q(conn, "SELECT * FROM tax_credits WHERE person_id = ? AND year_label = ?",
                    (person_id, year_label))
    credits = {"apit": 0.0, "wht": 0.0, "other": 0.0}
    for row in credit_rows:
        kind = row["kind"] if row["kind"] in credits else "other"
        credits[kind] += float(row["amount"] or 0)
    total_credits = sum(credits.values())
    payable = gross_tax - total_credits

    return {
        "year_label": year_label,
        "year_range": {"start": start, "end": end},
        "rules": rules,
        "person": {"id": person["id"], "name": person["name"], "tin": person["tin"]},
        "heads": {k: money(v) for k, v in heads.items()},
        "total_assessable": money(total_assessable),
        "deductions": {
            "tax_deductible_expenses": money(deductible),
            "used_against_business": money(used_deduction),
            "unused": money(max(0.0, deductible - used_deduction)),
            "rent_relief": money(rent_relief),
            "qualifying_reliefs": money(qualifying),
            "total": money(total_reliefs),
        },
        "taxable_income": money(taxable),
        "gross_tax": money(gross_tax),
        "slabs": breakdown,
        "credits": {**{k: money(v) for k, v in credits.items()}, "total": money(total_credits)},
        "tax_payable": money(payable),
        "refund_due": money(max(0.0, -payable)),
        "effective_rate": pct(gross_tax, total_assessable),
        "marginal_rate": marginal,
        "monthly_estimate": money(payable / 12 if payable > 0 else 0),
        "reliefs": relief_rows,
        "credit_items": credit_rows,
        "incomes": income_rows,
        "rules_note": rules["notes"],
    }


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------

def build_insights(conn, person_id: int | None = None, month: str | None = None) -> list[dict]:
    month = month or date.today().strftime("%Y-%m")
    start, end = month_bounds(month)
    rates = fx_map(conn)
    insights: list[dict] = []
    filter_sql = " AND person_id = ?" if person_id else ""
    filter_params: list[Any] = [person_id] if person_id else []

    cards = q(conn, "SELECT * FROM cards WHERE status = 'active'" + filter_sql, filter_params)
    for card in cards:
        outstanding = card_balance(conn, card["id"])
        limit = float(card["credit_limit"] or 0)
        util = pct(outstanding, limit)
        if util >= 75:
            insights.append({
                "severity": "critical",
                "title": f"{card['name']} utilization is {util:.0f}%",
                "message": "High utilization hurts your credit score and signals over-reliance on credit. Prioritise a payment.",
                "action": "View card", "page": "cards", "entity_id": card["id"],
                "metric": f"{util:.0f}%",
            })
        elif util >= 30:
            insights.append({
                "severity": "warning",
                "title": f"{card['name']} utilization is {util:.0f}%",
                "message": "Keeping utilization below 30% is healthier. Consider paying down part of this balance.",
                "action": "View card", "page": "cards", "entity_id": card["id"],
                "metric": f"{util:.0f}%",
            })
        if outstanding > 0 and float(card["apr"] or 0) >= 24:
            insights.append({
                "severity": "warning",
                "title": f"{card['name']} carries a {float(card['apr']):.0f}% APR",
                "message": "Revolving this balance is expensive. Clearing it should come before low-return saving.",
                "action": "Plan payoff", "page": "cards", "entity_id": card["id"],
                "metric": f"Rs {outstanding:,.0f}",
            })

    income_rows = q(conn, "SELECT amount, currency FROM incomes WHERE date >= ? AND date < ?" +
                    filter_sql, [start, end] + filter_params)
    month_income = sum(to_base(r["amount"], r["currency"], rates) for r in income_rows)
    expense_rows = q(conn,
                     """SELECT type, direction, amount, currency, is_business FROM transactions
                        WHERE date >= ? AND date < ?""" + filter_sql,
                     [start, end] + filter_params)
    month_expense = 0.0
    for tx in expense_rows:
        amount = to_base(tx["amount"], tx["currency"], rates)
        if tx["type"] in EXPENSE_TYPES:
            month_expense += -amount if tx["direction"] == "in" else amount
        elif tx["type"] == "refund":
            month_expense -= amount

    if month_income > 0 and month_expense > month_income:
        insights.append({
            "severity": "critical",
            "title": "Spending exceeded income this month",
            "message": f"Expenses are Rs {month_expense - month_income:,.0f} above income. Review the biggest categories.",
            "action": "See spending", "page": "insights",
            "metric": f"Rs {month_expense - month_income:,.0f} over",
        })
    elif month_income > 0:
        savings_rate = (month_income - month_expense) / month_income * 100
        if savings_rate < 20:
            insights.append({
                "severity": "warning" if savings_rate < 0 else "info",
                "title": f"Savings rate is {savings_rate:.0f}%",
                "message": "A 20%+ savings rate builds a buffer. Try trimming the top two discretionary categories.",
                "action": "See spending", "page": "insights",
                "metric": f"{savings_rate:.0f}%",
            })

    active_installments = q(conn, """SELECT i.monthly_amount, c.currency FROM installment_plans i
                                     JOIN cards c ON c.id = i.card_id
                                     WHERE i.status = 'active'""" +
                            (" AND c.person_id = ?" if person_id else ""),
                            filter_params)
    installment_total = sum(to_base(r["monthly_amount"], r["currency"], rates) for r in active_installments)
    if month_income > 0 and installment_total > month_income * 0.2:
        insights.append({
            "severity": "warning",
            "title": "Installment commitments are heavy",
            "message": f"Rs {installment_total:,.0f}/month of installments is over 20% of this month's income.",
            "action": "View installments", "page": "installments",
            "metric": f"Rs {installment_total:,.0f}/mo",
        })

    uncategorized = scalar(conn,
                           """SELECT COUNT(*) FROM transactions
                              WHERE category_id IS NULL
                                AND type IN ('purchase','installment','fee','interest','cash_advance','expense')
                                AND date >= ?""" + filter_sql,
                           [start] + filter_params)
    if uncategorized:
        insights.append({
            "severity": "info",
            "title": f"{uncategorized} uncategorized transaction(s)",
            "message": "Categorising them makes your spending analysis and tax deductions far more accurate.",
            "action": "Review transactions", "page": "transactions",
            "metric": str(uncategorized),
        })

    untagged_business = scalar(conn,
                               """SELECT COUNT(*) FROM transactions t JOIN cards c ON c.id = t.card_id
                                  WHERE c.purpose = 'business' AND t.is_business = 0
                                    AND t.date >= ?""" + (" AND t.person_id = ?" if person_id else ""),
                               [start] + filter_params)
    if untagged_business:
        insights.append({
            "severity": "info",
            "title": f"{untagged_business} business-card spend(s) not tagged",
            "message": "Mark them as business so your business/personal split and deductions stay clean.",
            "action": "Review transactions", "page": "transactions",
            "metric": str(untagged_business),
        })

    subs = detect_subscriptions(conn, person_id, rates)
    if subs:
        top = subs[0]
        insights.append({
            "severity": "info",
            "title": "Recurring subscriptions detected",
            "message": f"{len(subs)} repeating charges found. Largest is {top['name']} at about Rs {top['annual_cost']:,.0f}/year.",
            "action": "Review subscriptions", "page": "insights",
            "metric": f"Rs {sum(s['annual_cost'] for s in subs):,.0f}/yr",
        })

    bank_total = 0.0
    accounts = q(conn, "SELECT id, currency FROM accounts WHERE is_active = 1" + filter_sql, filter_params)
    for account in accounts:
        bank_total += account_balance(conn, account["id"]) * rates.get(account["currency"], 1)
    liquid_assets = sum(
        to_base(row["value"], row["currency"], rates)
        for row in q(conn, "SELECT value, currency FROM assets WHERE is_liquid = 1" + filter_sql, filter_params)
    )
    runway = bank_total + liquid_assets
    monthly_burn = month_expense if month_expense > 0 else 0
    if monthly_burn > 0 and runway < monthly_burn * 3:
        insights.append({
            "severity": "warning" if runway < monthly_burn * 2 else "info",
            "title": "Emergency fund looks thin",
            "message": f"Liquid funds cover about {runway / monthly_burn:.1f} months of spending. Aim for 3–6 months.",
            "action": "View net worth", "page": "networth",
            "metric": f"{runway / monthly_burn:.1f} months",
        })

    if not insights:
        insights.append({
            "severity": "success",
            "title": "Everything looks healthy",
            "message": "No urgent issues detected. Add more data for sharper recommendations.",
            "action": "View dashboard", "page": "dashboard", "metric": "✓",
        })
    return insights[:12]
