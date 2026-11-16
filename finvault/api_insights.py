"""Dashboard, net worth, analytics, tax, insights and global search."""
from __future__ import annotations

import json
from datetime import date

from . import finance
from .api_base import (
    ApiError, Ctx, as_bool, as_float, as_int, body_dict, clean_text, ensure_person,
    query_person, route,
)
from .db import get_setting, now_iso, q, q1, scalar


# ---------------------------------------------------------------------------
# Dashboard / net worth
# ---------------------------------------------------------------------------

@route("GET", "/api/v1/dashboard")
def dashboard(ctx: Ctx):
    person_id = query_person(ctx)
    month = finance.as_month(ctx.query.get("month"), "month") if ctx.query.get("month") else None
    result = finance.dashboard(ctx.conn, person_id, month)
    _record_snapshot(ctx.conn, person_id)
    return result


def _networth_components(conn, person_id: int | None) -> dict:
    rates = finance.fx_map(conn)
    where = " WHERE person_id = ?" if person_id else ""
    params = [person_id] if person_id else []

    accounts = []
    cash = 0.0
    for account in q(conn, "SELECT * FROM accounts" + where, params):
        balance = finance.account_balance(conn, account["id"])
        rate = rates.get(account["currency"], 1)
        cash += balance * rate
        accounts.append({**account, "balance": finance.money(balance),
                         "balance_base": finance.money(balance * rate)})

    assets = []
    asset_total = 0.0
    for asset in q(conn, "SELECT * FROM assets" + where, params):
        value = finance.to_base(float(asset["value"] or 0), asset["currency"], rates)
        asset_total += value
        assets.append({**asset, "value_base": finance.money(value)})

    cards = []
    card_total = 0.0
    for card in q(conn, "SELECT c.*, p.name AS person_name FROM cards c JOIN persons p ON p.id = c.person_id" +
                  (" WHERE c.person_id = ?" if person_id else ""), params):
        balance = finance.card_balance(conn, card["id"])
        value = finance.to_base(balance, card["currency"], rates)
        card_total += value
        cards.append({**card, "outstanding": finance.money(balance),
                      "outstanding_base": finance.money(value)})

    loans = q(conn, "SELECT l.*, p.name AS person_name FROM loans l JOIN persons p ON p.id = l.person_id" +
              (" WHERE l.person_id = ? AND l.status = 'active'" if person_id else " WHERE l.status = 'active'"),
              params)
    loan_total = sum(finance.to_base(float(loan["outstanding"] or 0), loan["currency"], rates) for loan in loans)
    liabilities = q(conn, "SELECT l.*, p.name AS person_name FROM liabilities l JOIN persons p ON p.id = l.person_id" +
                    where, params)
    liability_total = sum(finance.to_base(float(item["balance"] or 0), item["currency"], rates)
                          for item in liabilities)

    net_worth = cash + asset_total - card_total - loan_total - liability_total
    by_category: dict[str, float] = {}
    for asset in assets:
        by_category[asset["category"]] = by_category.get(asset["category"], 0) + asset["value_base"]
    return {
        "summary": {
            "net_worth": finance.money(net_worth),
            "cash": finance.money(cash),
            "assets": finance.money(asset_total),
            "card_debt": finance.money(card_total),
            "loans": finance.money(loan_total),
            "liabilities": finance.money(liability_total),
            "total_debt": finance.money(card_total + loan_total + liability_total),
            "liquid": finance.money(
                cash + sum(float(a["value_base"] or 0) for a in assets if a["is_liquid"])),
        },
        "accounts": accounts,
        "cards": cards,
        "assets": assets,
        "loans": loans,
        "liabilities": liabilities,
        "assets_by_category": [{"name": k, "amount": finance.money(v)}
                               for k, v in sorted(by_category.items(), key=lambda item: item[1], reverse=True)],
    }


def _record_snapshot(conn, person_id: int | None) -> None:
    components = _networth_components(conn, person_id)
    summary = components["summary"]
    key = person_id or 0
    today = date.today().isoformat()
    conn.execute(
        """INSERT INTO net_worth_snapshots(person_id, date, net_worth, assets, debts, cash, created_at)
           VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(person_id, date) DO UPDATE SET
               net_worth = excluded.net_worth, assets = excluded.assets,
               debts = excluded.debts, cash = excluded.cash""",
        (key, today, summary["net_worth"], summary["assets"], summary["total_debt"],
         summary["cash"], now_iso()),
    )


@route("GET", "/api/v1/networth")
def networth(ctx: Ctx):
    person_id = query_person(ctx)
    _record_snapshot(ctx.conn, person_id)
    components = _networth_components(ctx.conn, person_id)
    history = q(ctx.conn,
                "SELECT date, net_worth, assets, debts, cash FROM net_worth_snapshots WHERE person_id = ? ORDER BY date DESC LIMIT 24",
                (person_id or 0,))
    components["history"] = list(reversed(history))
    components["person_id"] = person_id
    return components


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@route("GET", "/api/v1/analytics/spending")
def analytics_spending(ctx: Ctx):
    person_id = query_person(ctx)
    start = ctx.query.get("from") or ctx.query.get("start")
    end = ctx.query.get("to") or ctx.query.get("end")
    return finance.spending_analytics(ctx.conn, person_id, start, end)


@route("GET", "/api/v1/insights")
def insights(ctx: Ctx):
    person_id = query_person(ctx)
    month = finance.as_month(ctx.query.get("month"), "month") if ctx.query.get("month") else None
    return finance.build_insights(ctx.conn, person_id, month)


@route("GET", "/api/v1/search")
def search(ctx: Ctx):
    term = clean_text(ctx.query.get("q"), 100)
    if len(term) < 2:
        return {"q": term, "groups": []}
    like = f"%{term}%"
    person_id = query_person(ctx)
    groups = []

    tx_sql = """SELECT t.id, t.date, t.description, t.amount, t.currency, t.direction, t.card_id,
                       c.name AS category_name
                FROM transactions t LEFT JOIN categories c ON c.id = t.category_id
                WHERE t.description LIKE ?"""
    params: list = [like]
    if person_id:
        tx_sql += " AND t.person_id = ?"
        params.append(person_id)
    tx_sql += " ORDER BY t.date DESC LIMIT 8"
    tx = q(ctx.conn, tx_sql, params)
    if tx:
        groups.append({"label": "Transactions", "items": [{
            "type": "transaction", "id": row["id"], "title": row["description"] or "(no description)",
            "subtitle": f"{row['date']} · {row['category_name'] or 'Uncategorized'}",
            "amount": row["amount"], "direction": row["direction"], "page": "transactions",
        } for row in tx]})

    card_rows = q(ctx.conn, "SELECT id, name, last4, credit_limit FROM cards WHERE name LIKE ? OR issuer LIKE ?" +
                  (" AND person_id = ?" if person_id else ""),
                  [like, like] + ([person_id] if person_id else []))
    if card_rows:
        groups.append({"label": "Cards", "items": [{
            "type": "card", "id": row["id"], "title": row["name"],
            "subtitle": f"•••• {row['last4']}" if row["last4"] else "Credit card",
            "amount": row["credit_limit"], "page": "cards",
        } for row in card_rows]})

    accounts = q(ctx.conn, "SELECT id, name, institution FROM accounts WHERE name LIKE ? OR institution LIKE ?" +
                  (" AND person_id = ?" if person_id else ""),
                  [like, like] + ([person_id] if person_id else []))
    if accounts:
        groups.append({"label": "Bank accounts", "items": [{
            "type": "account", "id": row["id"], "title": row["name"],
            "subtitle": row["institution"] or "Bank account", "page": "accounts",
        } for row in accounts]})

    incomes = q(ctx.conn, "SELECT id, date, source, amount FROM incomes WHERE source LIKE ?" +
                 (" AND person_id = ?" if person_id else ""),
                 [like] + ([person_id] if person_id else []))
    if incomes:
        groups.append({"label": "Income", "items": [{
            "type": "income", "id": row["id"], "title": row["source"],
            "subtitle": row["date"], "amount": row["amount"], "page": "income",
        } for row in incomes]})

    assets = q(ctx.conn, "SELECT id, name, category, value FROM assets WHERE name LIKE ?" +
                (" AND person_id = ?" if person_id else ""),
                [like] + ([person_id] if person_id else []))
    if assets:
        groups.append({"label": "Assets", "items": [{
            "type": "asset", "id": row["id"], "title": row["name"],
            "subtitle": row["category"], "amount": row["value"], "page": "networth",
        } for row in assets]})

    loans = q(ctx.conn, "SELECT id, name, lender, outstanding FROM loans WHERE name LIKE ? OR lender LIKE ?" +
               (" AND person_id = ?" if person_id else ""),
               [like, like] + ([person_id] if person_id else []))
    if loans:
        groups.append({"label": "Loans", "items": [{
            "type": "loan", "id": row["id"], "title": row["name"],
            "subtitle": row["lender"] or "Loan", "amount": row["outstanding"], "page": "loans",
        } for row in loans]})
    return {"q": term, "groups": groups}


# ---------------------------------------------------------------------------
# Tax
# ---------------------------------------------------------------------------

def _tax_person(ctx: Ctx) -> int:
    person_id = query_person(ctx)
    if person_id:
        return person_id
    first = q1(ctx.conn, "SELECT id FROM persons ORDER BY is_primary DESC, sort_order, id LIMIT 1")
    if not first:
        raise ApiError("Create a person first")
    return first["id"]


@route("GET", "/api/v1/tax/estimate")
def tax_estimate(ctx: Ctx):
    person_id = _tax_person(ctx)
    year_label = clean_text(ctx.query.get("year_label"), 20) or finance.current_tax_year()
    return finance.tax_estimate(ctx.conn, person_id, year_label)


@route("GET", "/api/v1/tax/years")
def tax_years(ctx: Ctx):
    rules = q(ctx.conn, "SELECT * FROM tax_rules ORDER BY year_label DESC")
    for rule in rules:
        rule["slabs"] = json.loads(rule["slabs_json"] or "[]")
    data_years = {row["year_label"] for row in q(ctx.conn, "SELECT DISTINCT year_label FROM tax_reliefs")}
    data_years |= {row["year_label"] for row in q(ctx.conn, "SELECT DISTINCT year_label FROM tax_credits")}
    return {"years": rules, "current": finance.current_tax_year(), "with_data": sorted(data_years)}


@route("PUT", "/api/v1/tax/rules/{year_label}")
def tax_rules_update(ctx: Ctx):
    year_label = clean_text(ctx.params["year_label"], 20)
    if not year_label:
        raise ApiError("Year label is required")
    existing = q1(ctx.conn, "SELECT * FROM tax_rules WHERE year_label = ?", (year_label,))
    body = body_dict(ctx.body)
    slabs = body.get("slabs")
    if slabs is not None:
        if not isinstance(slabs, list) or not slabs:
            raise ApiError("slabs must be a non-empty list", field="slabs")
        cleaned = []
        for index, slab in enumerate(slabs):
            upto = slab.get("upto")
            if upto in (None, "", 0):
                upto = None
            else:
                upto = as_float(upto, f"slab {index + 1} upto", required=True, minimum=0)
            rate = as_float(slab.get("rate"), f"slab {index + 1} rate", required=True, minimum=0)
            if rate > 1:
                rate = rate / 100.0
            cleaned.append({"upto": upto, "rate": rate})
        slabs_json = json.dumps(cleaned)
    else:
        slabs_json = existing["slabs_json"] if existing else "[]"
    personal_relief = as_float(body.get("personal_relief"), "personal_relief",
                               default=float(existing["personal_relief"]) if existing else 0, minimum=0)
    rent_pct = as_float(body.get("rent_relief_pct"), "rent_relief_pct",
                        default=float(existing["rent_relief_pct"]) if existing else 0, minimum=0, maximum=100)
    rent_cap = as_float(body.get("rent_relief_cap"), "rent_relief_cap",
                        default=float(existing["rent_relief_cap"]) if existing else 0, minimum=0)
    label = clean_text(body.get("label"), 120) or (existing["label"] if existing else f"Sri Lanka Y/A {year_label}")
    notes = clean_text(body.get("notes"), 2000) if "notes" in body else (existing["notes"] if existing else "")
    wht_final = as_bool(body.get("wht_is_final"), bool(existing["wht_is_final"]) if existing else False)
    stamp = now_iso()
    ctx.conn.execute(
        """INSERT INTO tax_rules(year_label, label, personal_relief, slabs_json, rent_relief_pct,
               rent_relief_cap, wht_is_final, notes, updated_at)
           VALUES(?,?,?,?,?,?,?,?,?)
           ON CONFLICT(year_label) DO UPDATE SET label = excluded.label,
               personal_relief = excluded.personal_relief, slabs_json = excluded.slabs_json,
               rent_relief_pct = excluded.rent_relief_pct, rent_relief_cap = excluded.rent_relief_cap,
               wht_is_final = excluded.wht_is_final, notes = excluded.notes, updated_at = excluded.updated_at""",
        (year_label, label, personal_relief, slabs_json, rent_pct, rent_cap, wht_final, notes, stamp),
    )
    row = q1(ctx.conn, "SELECT * FROM tax_rules WHERE year_label = ?", (year_label,))
    row["slabs"] = json.loads(row["slabs_json"] or "[]")
    return row


@route("GET", "/api/v1/tax/reliefs")
def tax_reliefs_list(ctx: Ctx):
    person_id = _tax_person(ctx)
    year_label = clean_text(ctx.query.get("year_label"), 20) or finance.current_tax_year()
    return q(ctx.conn, "SELECT * FROM tax_reliefs WHERE person_id = ? AND year_label = ? ORDER BY id",
             (person_id, year_label))


@route("POST", "/api/v1/tax/reliefs")
def tax_reliefs_create(ctx: Ctx):
    body = body_dict(ctx.body)
    person_id = as_int(body.get("person_id"), "person_id") or _tax_person(ctx)
    ensure_person(ctx.conn, person_id)
    year_label = clean_text(body.get("year_label"), 20) or finance.current_tax_year()
    name = clean_text(body.get("name"), 120)
    if not name:
        raise ApiError("Relief name is required", field="name")
    cur = ctx.conn.execute(
        """INSERT INTO tax_reliefs(person_id, year_label, name, amount, kind, notes, created_at)
           VALUES(?,?,?,?,?,?,?)""",
        (person_id, year_label, name,
         as_float(body.get("amount"), "amount", default=0, minimum=0),
         clean_text(body.get("kind"), 40) or "qualifying", clean_text(body.get("notes"), 500), now_iso()),
    )
    return q1(ctx.conn, "SELECT * FROM tax_reliefs WHERE id = ?", (cur.lastrowid,))


@route("PUT", "/api/v1/tax/reliefs/{id}")
def tax_reliefs_update(ctx: Ctx):
    relief_id = as_int(ctx.params["id"], "id", required=True)
    if not q1(ctx.conn, "SELECT id FROM tax_reliefs WHERE id = ?", (relief_id,)):
        raise ApiError("Relief not found", 404)
    body = body_dict(ctx.body)
    if "amount" in body:
        body["amount"] = as_float(body["amount"], "amount", default=0, minimum=0)
    from .api_base import update_row
    update_row(ctx.conn, "tax_reliefs", relief_id, body, {"name", "amount", "kind", "notes", "year_label"})
    return q1(ctx.conn, "SELECT * FROM tax_reliefs WHERE id = ?", (relief_id,))


@route("DELETE", "/api/v1/tax/reliefs/{id}")
def tax_reliefs_delete(ctx: Ctx):
    relief_id = as_int(ctx.params["id"], "id", required=True)
    ctx.conn.execute("DELETE FROM tax_reliefs WHERE id = ?", (relief_id,))
    return {"deleted": relief_id}


@route("GET", "/api/v1/tax/credits")
def tax_credits_list(ctx: Ctx):
    person_id = _tax_person(ctx)
    year_label = clean_text(ctx.query.get("year_label"), 20) or finance.current_tax_year()
    return q(ctx.conn, "SELECT * FROM tax_credits WHERE person_id = ? AND year_label = ? ORDER BY id",
             (person_id, year_label))


@route("POST", "/api/v1/tax/credits")
def tax_credits_create(ctx: Ctx):
    body = body_dict(ctx.body)
    person_id = as_int(body.get("person_id"), "person_id") or _tax_person(ctx)
    ensure_person(ctx.conn, person_id)
    year_label = clean_text(body.get("year_label"), 20) or finance.current_tax_year()
    name = clean_text(body.get("name"), 120)
    if not name:
        raise ApiError("Credit name is required", field="name")
    cur = ctx.conn.execute(
        """INSERT INTO tax_credits(person_id, year_label, name, amount, kind, notes, created_at)
           VALUES(?,?,?,?,?,?,?)""",
        (person_id, year_label, name,
         as_float(body.get("amount"), "amount", default=0, minimum=0),
         clean_text(body.get("kind"), 40) or "apit", clean_text(body.get("notes"), 500), now_iso()),
    )
    return q1(ctx.conn, "SELECT * FROM tax_credits WHERE id = ?", (cur.lastrowid,))


@route("PUT", "/api/v1/tax/credits/{id}")
def tax_credits_update(ctx: Ctx):
    credit_id = as_int(ctx.params["id"], "id", required=True)
    if not q1(ctx.conn, "SELECT id FROM tax_credits WHERE id = ?", (credit_id,)):
        raise ApiError("Tax credit not found", 404)
    body = body_dict(ctx.body)
    if "amount" in body:
        body["amount"] = as_float(body["amount"], "amount", default=0, minimum=0)
    from .api_base import update_row
    update_row(ctx.conn, "tax_credits", credit_id, body, {"name", "amount", "kind", "notes", "year_label"})
    return q1(ctx.conn, "SELECT * FROM tax_credits WHERE id = ?", (credit_id,))


@route("DELETE", "/api/v1/tax/credits/{id}")
def tax_credits_delete(ctx: Ctx):
    credit_id = as_int(ctx.params["id"], "id", required=True)
    ctx.conn.execute("DELETE FROM tax_credits WHERE id = ?", (credit_id,))
    return {"deleted": credit_id}


@route("GET", "/api/v1/tax/summary")
def tax_summary(ctx: Ctx):
    person_id = _tax_person(ctx)
    year_label = clean_text(ctx.query.get("year_label"), 20) or finance.current_tax_year()
    estimate = finance.tax_estimate(ctx.conn, person_id, year_label)
    estimate["reliefs"] = q(ctx.conn,
                            "SELECT * FROM tax_reliefs WHERE person_id = ? AND year_label = ?",
                            (person_id, year_label))
    estimate["credit_items"] = q(ctx.conn,
                                 "SELECT * FROM tax_credits WHERE person_id = ? AND year_label = ?",
                                 (person_id, year_label))
    return estimate
