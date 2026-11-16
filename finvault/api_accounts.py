"""Cards, bank accounts, transactions, transfers and statements."""
from __future__ import annotations

import uuid
from datetime import date

from . import finance
from .api_base import (
    ApiError, Ctx, as_bool, as_choice, as_date, as_float, as_int, body_dict,
    clean_text, ensure_account, ensure_card, ensure_category, ensure_person,
    query_person, route, update_row,
)
from .db import get_setting, now_iso, q, q1, scalar

TX_TYPES = {"purchase", "installment", "fee", "interest", "cash_advance", "expense",
            "payment", "card_payment", "refund", "transfer", "income_deposit",
            "loan_payment", "adjustment"}
DIRECTION_IN_TYPES = {"payment", "refund", "income_deposit"}


def _base_currency(conn) -> str:
    return get_setting(conn, "base_currency", "LKR")


def _card_payload(conn, card: dict) -> dict:
    balance = finance.card_balance(conn, card["id"])
    limit = float(card["credit_limit"] or 0)
    st = q1(conn,
            """SELECT * FROM statements
               WHERE card_id = ? AND status IN ('unpaid','partial','overdue')
               ORDER BY due_date ASC LIMIT 1""",
            (card["id"],))
    if st:
        due_amount = max(0.0, float(st["closing_balance"] or 0) - float(st["amount_paid"] or 0))
        minimum = max(0.0, float(st["minimum_due"] or 0) - float(st["amount_paid"] or 0))
        due_date = st["due_date"] or ""
        has_statement = True
    else:
        due_amount = max(0.0, balance)
        minimum = max(0.0, balance * 0.05)
        due_date = finance.next_due_date(int(card["due_day"] or 0)) if balance > 0 else ""
        has_statement = False
    return {
        **card,
        "outstanding": balance,
        "available": round(max(0.0, limit - balance), 2),
        "utilization": finance.pct(balance, limit),
        "due_amount": finance.money(due_amount),
        "minimum_due": finance.money(minimum),
        "due_date": due_date,
        "has_statement": has_statement,
        "days_to_due": finance.days_until(due_date),
        "person_name": card.get("person_name") or "",
    }


def _account_payload(conn, account: dict) -> dict:
    balance = finance.account_balance(conn, account["id"])
    rates = finance.fx_map(conn)
    base = finance.to_base(balance, account.get("currency"), rates)
    return {**account, "balance": balance, "balance_base": finance.money(base)}


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------

@route("GET", "/api/v1/cards")
def cards_list(ctx: Ctx):
    person_id = query_person(ctx)
    sql = "SELECT c.*, p.name AS person_name FROM cards c JOIN persons p ON p.id = c.person_id"
    params: list = []
    if person_id:
        sql += " WHERE c.person_id = ?"
        params.append(person_id)
    if ctx.query.get("status") and ctx.query["status"] in {"active", "closed"}:
        sql += " AND c.status = ?" if person_id else " WHERE c.status = ?"
        params.append(ctx.query["status"])
    sql += " ORDER BY c.status, c.id"
    return [_card_payload(ctx.conn, row) for row in q(ctx.conn, sql, params)]


@route("POST", "/api/v1/cards")
def cards_create(ctx: Ctx):
    body = body_dict(ctx.body)
    person_id = as_int(body.get("person_id"), "person_id", required=True)
    ensure_person(ctx.conn, person_id)
    name = clean_text(body.get("name"), 80)
    if not name:
        raise ApiError("Card name is required", field="name")
    stamp = now_iso()
    cur = ctx.conn.execute(
        """INSERT INTO cards(person_id, name, issuer, network, last4, currency, credit_limit,
               opening_balance, apr, statement_day, due_day, annual_fee, purpose, color_from,
               color_to, status, notes, created_at, updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (person_id, name, clean_text(body.get("issuer"), 80), clean_text(body.get("network"), 40),
         clean_text(body.get("last4"), 8), clean_text(body.get("currency"), 8).upper() or _base_currency(ctx.conn),
         as_float(body.get("credit_limit"), "credit_limit", default=0, minimum=0),
         as_float(body.get("opening_balance"), "opening_balance", default=0),
         as_float(body.get("apr"), "apr", default=0, minimum=0),
         as_int(body.get("statement_day"), "statement_day", default=0, minimum=0, maximum=31),
         as_int(body.get("due_day"), "due_day", default=0, minimum=0, maximum=31),
         as_float(body.get("annual_fee"), "annual_fee", default=0, minimum=0),
         as_choice(body.get("purpose"), "purpose", {"personal", "business", "mixed"}, "personal"),
         clean_text(body.get("color_from"), 20) or "#4f46e5",
         clean_text(body.get("color_to"), 20) or "#0ea5e9",
         as_choice(body.get("status"), "status", {"active", "closed"}, "active"),
         clean_text(body.get("notes"), 1000), stamp, stamp),
    )
    return _card_payload(ctx.conn, q1(ctx.conn, "SELECT * FROM cards WHERE id = ?", (cur.lastrowid,)))


@route("GET", "/api/v1/cards/{id}")
def cards_detail(ctx: Ctx):
    card_id = as_int(ctx.params["id"], "id", required=True)
    card = ensure_card(ctx.conn, card_id)
    payload = _card_payload(ctx.conn, card)
    person = q1(ctx.conn, "SELECT name FROM persons WHERE id = ?", (card["person_id"],))
    payload["person_name"] = person["name"] if person else ""
    payload["recent_transactions"] = q(
        ctx.conn,
        """SELECT t.*, c.name AS category_name, c.icon AS category_icon, c.color AS category_color
           FROM transactions t LEFT JOIN categories c ON c.id = t.category_id
           WHERE t.card_id = ? ORDER BY t.date DESC, t.id DESC LIMIT 25""",
        (card_id,),
    )
    statement_rows = q(
        ctx.conn, "SELECT * FROM statements WHERE card_id = ? ORDER BY statement_date DESC LIMIT 24",
        (card_id,),
    )
    for row in statement_rows:
        row["remaining"] = finance.money(
            max(0.0, float(row["closing_balance"] or 0) - float(row["amount_paid"] or 0)))
        row["effective_status"] = _statement_status(row)
    payload["statements"] = statement_rows
    payload["installment_plans"] = q(
        ctx.conn, "SELECT * FROM installment_plans WHERE card_id = ? ORDER BY id DESC", (card_id,),
    )
    rates = finance.fx_map(ctx.conn)
    payload["outstanding_base"] = finance.money(
        payload["outstanding"] * rates.get(card["currency"], 1))
    payload["limit_base"] = finance.money(
        float(card["credit_limit"] or 0) * rates.get(card["currency"], 1))
    return payload


@route("PUT", "/api/v1/cards/{id}")
def cards_update(ctx: Ctx):
    card_id = as_int(ctx.params["id"], "id", required=True)
    ensure_card(ctx.conn, card_id)
    body = body_dict(ctx.body)
    if "person_id" in body:
        body["person_id"] = as_int(body["person_id"], "person_id", required=True)
        ensure_person(ctx.conn, body["person_id"])
    for field_name in ("credit_limit", "opening_balance", "annual_fee", "apr"):
        if field_name in body:
            body[field_name] = as_float(body[field_name], field_name, default=0,
                                        minimum=0 if field_name != "opening_balance" else None)
    for field_name in ("statement_day", "due_day"):
        if field_name in body:
            body[field_name] = as_int(body[field_name], field_name, default=0, minimum=0, maximum=31)
    if "currency" in body:
        body["currency"] = clean_text(body["currency"], 8).upper() or _base_currency(ctx.conn)
    if "status" in body:
        body["status"] = as_choice(body["status"], "status", {"active", "closed"}, "active")
    if "purpose" in body:
        body["purpose"] = as_choice(body["purpose"], "purpose", {"personal", "business", "mixed"}, "personal")
    update_row(ctx.conn, "cards", card_id, body,
               {"person_id", "name", "issuer", "network", "last4", "currency", "credit_limit",
                "opening_balance", "apr", "statement_day", "due_day", "annual_fee", "purpose",
                "color_from", "color_to", "status", "notes"})
    return _card_payload(ctx.conn, q1(ctx.conn, "SELECT * FROM cards WHERE id = ?", (card_id,)))


@route("DELETE", "/api/v1/cards/{id}")
def cards_delete(ctx: Ctx):
    card_id = as_int(ctx.params["id"], "id", required=True)
    ensure_card(ctx.conn, card_id)
    tx_count = scalar(ctx.conn, "SELECT COUNT(*) FROM transactions WHERE card_id = ?", (card_id,))
    if tx_count and not as_bool(ctx.query.get("force")):
        raise ApiError(
            f"This card has {tx_count} transaction(s). Set status to closed instead, or pass force=1 to delete everything.",
            409,
        )
    ctx.conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))
    return {"deleted": card_id}


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

@route("GET", "/api/v1/accounts")
def accounts_list(ctx: Ctx):
    person_id = query_person(ctx)
    sql = "SELECT a.*, p.name AS person_name FROM accounts a JOIN persons p ON p.id = a.person_id"
    params: list = []
    if person_id:
        sql += " WHERE a.person_id = ?"
        params.append(person_id)
    sql += " ORDER BY a.is_active DESC, a.id"
    return [_account_payload(ctx.conn, row) for row in q(ctx.conn, sql, params)]


@route("GET", "/api/v1/accounts/{id}")
def accounts_detail(ctx: Ctx):
    account_id = as_int(ctx.params["id"], "id", required=True)
    account = ensure_account(ctx.conn, account_id)
    payload = _account_payload(ctx.conn, account)
    person = q1(ctx.conn, "SELECT name FROM persons WHERE id = ?", (account["person_id"],))
    payload["person_name"] = person["name"] if person else ""
    payload["recent_transactions"] = q(
        ctx.conn,
        """SELECT t.*, c.name AS category_name, c.icon AS category_icon, c.color AS category_color
           FROM transactions t LEFT JOIN categories c ON c.id = t.category_id
           WHERE t.account_id = ? ORDER BY t.date DESC, t.id DESC LIMIT 25""",
        (account_id,),
    )
    return payload


@route("POST", "/api/v1/accounts")
def accounts_create(ctx: Ctx):
    body = body_dict(ctx.body)
    person_id = as_int(body.get("person_id"), "person_id", required=True)
    ensure_person(ctx.conn, person_id)
    name = clean_text(body.get("name"), 80)
    if not name:
        raise ApiError("Account name is required", field="name")
    stamp = now_iso()
    cur = ctx.conn.execute(
        """INSERT INTO accounts(person_id, name, institution, type, account_number, currency,
               opening_balance, is_active, notes, created_at, updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (person_id, name, clean_text(body.get("institution"), 80),
         as_choice(body.get("type"), "type",
                   {"savings", "current", "fixed", "wallet", "cash", "investment", "other"}, "savings"),
         clean_text(body.get("account_number"), 60),
         clean_text(body.get("currency"), 8).upper() or _base_currency(ctx.conn),
         as_float(body.get("opening_balance"), "opening_balance", default=0),
         as_bool(body.get("is_active"), True), clean_text(body.get("notes"), 1000), stamp, stamp),
    )
    return _account_payload(ctx.conn, q1(ctx.conn, "SELECT * FROM accounts WHERE id = ?", (cur.lastrowid,)))


@route("PUT", "/api/v1/accounts/{id}")
def accounts_update(ctx: Ctx):
    account_id = as_int(ctx.params["id"], "id", required=True)
    ensure_account(ctx.conn, account_id)
    body = body_dict(ctx.body)
    if "person_id" in body:
        body["person_id"] = as_int(body["person_id"], "person_id", required=True)
        ensure_person(ctx.conn, body["person_id"])
    if "opening_balance" in body:
        body["opening_balance"] = as_float(body["opening_balance"], "opening_balance", default=0)
    if "is_active" in body:
        body["is_active"] = as_bool(body["is_active"], True)
    if "type" in body:
        body["type"] = as_choice(body["type"], "type",
                                 {"savings", "current", "fixed", "wallet", "cash", "investment", "other"},
                                 "savings")
    if "currency" in body:
        body["currency"] = clean_text(body["currency"], 8).upper() or _base_currency(ctx.conn)
    update_row(ctx.conn, "accounts", account_id, body,
               {"person_id", "name", "institution", "type", "account_number", "currency",
                "opening_balance", "is_active", "notes"})
    return _account_payload(ctx.conn, q1(ctx.conn, "SELECT * FROM accounts WHERE id = ?", (account_id,)))


@route("DELETE", "/api/v1/accounts/{id}")
def accounts_delete(ctx: Ctx):
    account_id = as_int(ctx.params["id"], "id", required=True)
    ensure_account(ctx.conn, account_id)
    tx_count = scalar(ctx.conn, "SELECT COUNT(*) FROM transactions WHERE account_id = ?", (account_id,))
    if tx_count and not as_bool(ctx.query.get("force")):
        raise ApiError(f"This account has {tx_count} transaction(s). Pass force=1 to delete it all.", 409)
    ctx.conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    return {"deleted": account_id}


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

def create_transaction(conn, body: dict) -> dict:
    """Validate and insert one transaction. Shared with bulk import."""
    card_id = as_int(body.get("card_id"), "card_id")
    account_id = as_int(body.get("account_id"), "account_id")
    card = ensure_card(conn, card_id) if card_id else None
    account = ensure_account(conn, account_id) if account_id else None
    if card and account:
        raise ApiError("A transaction belongs to either a card or a bank account, not both", field="card_id")

    person_id = as_int(body.get("person_id"), "person_id")
    if card:
        person_id = card["person_id"]
    elif account:
        person_id = account["person_id"]
    if not person_id:
        raise ApiError("person_id, card_id or account_id is required", field="person_id")
    ensure_person(conn, person_id)

    tx_type = as_choice(body.get("type"), "type", TX_TYPES, "purchase")
    direction = str(body.get("direction") or "").strip().lower()
    if direction not in {"in", "out"}:
        direction = "in" if tx_type in DIRECTION_IN_TYPES else "out"
    amount = as_float(body.get("amount"), "amount", required=True, minimum=0)
    tx_date = as_date(body.get("date"), "date")
    category_id = as_int(body.get("category_id"), "category_id")
    ensure_category(conn, category_id)
    currency = clean_text(body.get("currency"), 8).upper()
    if not currency:
        currency = (card or account or {}).get("currency") or _base_currency(conn)
    statement_id = as_int(body.get("statement_id"), "statement_id")
    if statement_id and (not card or not q1(conn, "SELECT id FROM statements WHERE id = ? AND card_id = ?",
                                             (statement_id, card_id))):
        raise ApiError("Statement does not belong to this card", field="statement_id")
    installment_id = as_int(body.get("installment_id"), "installment_id")
    income_id = as_int(body.get("income_id"), "income_id")
    stamp = now_iso()
    cur = conn.execute(
        """INSERT INTO transactions(person_id, card_id, account_id, type, date, description,
               category_id, amount, direction, currency, is_business, tax_deductible, notes,
               tags, statement_id, installment_id, income_id, transfer_group, created_at, updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (person_id, card_id, account_id, tx_type, tx_date, clean_text(body.get("description"), 300),
         category_id, amount, direction, currency, as_bool(body.get("is_business")),
         as_bool(body.get("tax_deductible")), clean_text(body.get("notes"), 1000),
         clean_text(body.get("tags"), 300), statement_id, installment_id, income_id,
         clean_text(body.get("transfer_group"), 40), stamp, stamp),
    )
    return q1(conn, "SELECT * FROM transactions WHERE id = ?", (cur.lastrowid,))


@route("GET", "/api/v1/transactions")
def transactions_list(ctx: Ctx):
    where: list[str] = []
    params: list = []
    person_id = query_person(ctx)
    if person_id:
        where.append("t.person_id = ?")
        params.append(person_id)
    if ctx.query.get("card_id"):
        where.append("t.card_id = ?")
        params.append(as_int(ctx.query["card_id"], "card_id"))
    if ctx.query.get("account_id"):
        where.append("t.account_id = ?")
        params.append(as_int(ctx.query["account_id"], "account_id"))
    if ctx.query.get("category_id"):
        where.append("t.category_id = ?")
        params.append(as_int(ctx.query["category_id"], "category_id"))
    if ctx.query.get("type"):
        where.append("t.type = ?")
        params.append(clean_text(ctx.query["type"], 30))
    if ctx.query.get("business") is not None and ctx.query.get("business") != "":
        where.append("t.is_business = ?")
        params.append(as_bool(ctx.query["business"]))
    if ctx.query.get("deductible") is not None and ctx.query.get("deductible") != "":
        where.append("t.tax_deductible = ?")
        params.append(as_bool(ctx.query["deductible"]))
    if ctx.query.get("month"):
        start, end = finance.month_bounds(finance.as_month(ctx.query["month"], "month"))
        where.append("t.date >= ? AND t.date < ?")
        params.extend([start, end])
    if ctx.query.get("from"):
        where.append("t.date >= ?")
        params.append(as_date(ctx.query["from"], "from", False))
    if ctx.query.get("to"):
        where.append("t.date <= ?")
        params.append(as_date(ctx.query["to"], "to", False))
    if ctx.query.get("q"):
        where.append("(t.description LIKE ? OR t.notes LIKE ? OR t.tags LIKE ?)")
        like = f"%{clean_text(ctx.query['q'], 100)}%"
        params.extend([like, like, like])
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    total = scalar(ctx.conn, f"SELECT COUNT(*) FROM transactions t{clause}", params)
    limit = as_int(ctx.query.get("limit"), "limit", default=100, minimum=1, maximum=1000)
    offset = as_int(ctx.query.get("offset"), "offset", default=0, minimum=0)
    rows = q(ctx.conn,
             f"""SELECT t.*, c.name AS category_name, c.icon AS category_icon, c.color AS category_color,
                        cd.name AS card_name, a.name AS account_name, p.name AS person_name
                 FROM transactions t
                 LEFT JOIN categories c ON c.id = t.category_id
                 LEFT JOIN cards cd ON cd.id = t.card_id
                 LEFT JOIN accounts a ON a.id = t.account_id
                 JOIN persons p ON p.id = t.person_id
                 {clause}
                 ORDER BY t.date DESC, t.id DESC LIMIT ? OFFSET ?""",
             params + [limit, offset])

    sum_rows = q(ctx.conn,
                 f"""SELECT t.direction, t.amount, t.currency FROM transactions t{clause}""", params)
    rates = finance.fx_map(ctx.conn)
    total_in = sum(finance.to_base(r["amount"], r["currency"], rates) for r in sum_rows if r["direction"] == "in")
    total_out = sum(finance.to_base(r["amount"], r["currency"], rates) for r in sum_rows if r["direction"] == "out")
    return {
        "items": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
        "summary": {"in": finance.money(total_in), "out": finance.money(total_out),
                    "net": finance.money(total_in - total_out)},
    }


@route("GET", "/api/v1/transactions/{id}")
def transactions_detail(ctx: Ctx):
    tx_id = as_int(ctx.params["id"], "id", required=True)
    row = q1(ctx.conn,
             """SELECT t.*, c.name AS category_name, c.icon AS category_icon, c.color AS category_color,
                       cd.name AS card_name, a.name AS account_name, p.name AS person_name
                FROM transactions t
                LEFT JOIN categories c ON c.id = t.category_id
                LEFT JOIN cards cd ON cd.id = t.card_id
                LEFT JOIN accounts a ON a.id = t.account_id
                JOIN persons p ON p.id = t.person_id
                WHERE t.id = ?""", (tx_id,))
    if not row:
        raise ApiError("Transaction not found", 404)
    return row


@route("POST", "/api/v1/transactions")
def transactions_create(ctx: Ctx):
    return create_transaction(ctx.conn, body_dict(ctx.body))


@route("PUT", "/api/v1/transactions/{id}")
def transactions_update(ctx: Ctx):
    tx_id = as_int(ctx.params["id"], "id", required=True)
    existing = q1(ctx.conn, "SELECT * FROM transactions WHERE id = ?", (tx_id,))
    if not existing:
        raise ApiError("Transaction not found", 404)
    body = body_dict(ctx.body)
    allowed = {"person_id", "card_id", "account_id", "type", "date", "description", "category_id",
               "amount", "direction", "currency", "is_business", "tax_deductible", "notes", "tags",
               "statement_id", "installment_id", "transfer_group"}
    merged = {**existing, **{k: body[k] for k in body if k in allowed}}

    # Re-derive ownership/currency from the selected card or account.
    if "card_id" in body or "account_id" in body:
        card_id = as_int(merged.get("card_id"), "card_id")
        account_id = as_int(merged.get("account_id"), "account_id")
        if card_id and account_id:
            raise ApiError("A transaction belongs to either a card or a bank account, not both")
        if card_id:
            card = ensure_card(ctx.conn, card_id)
            merged["person_id"] = card["person_id"]
            if "currency" not in body:
                merged["currency"] = card["currency"]
        elif account_id:
            account = ensure_account(ctx.conn, account_id)
            merged["person_id"] = account["person_id"]
            if "currency" not in body:
                merged["currency"] = account["currency"]

    if "type" in body:
        merged["type"] = as_choice(body["type"], "type", TX_TYPES, existing["type"])
    if "direction" in body:
        merged["direction"] = as_choice(body["direction"], "direction", {"in", "out"}, existing["direction"])
    if "amount" in body:
        merged["amount"] = as_float(body["amount"], "amount", required=True, minimum=0)
    if "date" in body:
        merged["date"] = as_date(body["date"], "date")
    if "person_id" in body and "card_id" not in body and "account_id" not in body:
        merged["person_id"] = as_int(body["person_id"], "person_id", required=True)
        ensure_person(ctx.conn, merged["person_id"])
    if "category_id" in body:
        merged["category_id"] = as_int(body["category_id"], "category_id")
        ensure_category(ctx.conn, merged["category_id"])
    for flag in ("is_business", "tax_deductible"):
        if flag in body:
            merged[flag] = as_bool(body[flag])
    for text_field in ("description", "notes", "tags"):
        if text_field in body:
            merged[text_field] = clean_text(body[text_field], 1000 if text_field == "notes" else 300)
    if "currency" in body:
        merged["currency"] = clean_text(body["currency"], 8).upper() or existing["currency"]

    update_row(ctx.conn, "transactions", tx_id, merged,
               {"person_id", "card_id", "account_id", "type", "date", "description", "category_id",
                "amount", "direction", "currency", "is_business", "tax_deductible", "notes", "tags",
                "statement_id", "installment_id", "transfer_group"})
    return q1(ctx.conn, "SELECT * FROM transactions WHERE id = ?", (tx_id,))


@route("DELETE", "/api/v1/transactions/{id}")
def transactions_delete(ctx: Ctx):
    tx_id = as_int(ctx.params["id"], "id", required=True)
    existing = q1(ctx.conn, "SELECT * FROM transactions WHERE id = ?", (tx_id,))
    if not existing:
        raise ApiError("Transaction not found", 404)
    group = existing.get("transfer_group")
    if group and as_bool(ctx.query.get("group"), True):
        ctx.conn.execute("DELETE FROM transactions WHERE transfer_group = ?", (group,))
    else:
        ctx.conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    return {"deleted": tx_id}


# ---------------------------------------------------------------------------
# Transfers and payments
# ---------------------------------------------------------------------------

def record_transfer(conn, body: dict) -> dict:
    from_account_id = as_int(body.get("from_account_id"), "from_account_id")
    from_card_id = as_int(body.get("from_card_id"), "from_card_id")
    to_account_id = as_int(body.get("to_account_id"), "to_account_id")
    to_card_id = as_int(body.get("to_card_id"), "to_card_id")
    if bool(from_account_id) == bool(from_card_id):
        raise ApiError("Choose exactly one source: from_account_id or from_card_id")
    if bool(to_account_id) == bool(to_card_id):
        raise ApiError("Choose exactly one destination: to_account_id or to_card_id")
    if from_account_id == to_account_id and from_account_id:
        raise ApiError("Source and destination accounts are the same")
    amount = as_float(body.get("amount"), "amount", required=True, minimum=0.01)
    tx_date = as_date(body.get("date") or date.today().isoformat(), "date")
    description = clean_text(body.get("description"), 300)
    group = uuid.uuid4().hex

    source = ensure_account(conn, from_account_id) if from_account_id else ensure_card(conn, from_card_id)
    target = ensure_account(conn, to_account_id) if to_account_id else ensure_card(conn, to_card_id)
    person_id = source["person_id"]
    if target["person_id"] != person_id:
        raise ApiError("Transfer source and destination belong to different people")

    if from_account_id and to_account_id:
        out_type, in_type = "transfer", "transfer"
        out_desc = description or f"Transfer to {target['name']}"
        in_desc = description or f"Transfer from {source['name']}"
    elif from_account_id and to_card_id:
        out_type, in_type = "card_payment", "payment"
        out_desc = description or f"Payment to {target['name']}"
        in_desc = description or f"Payment from {source['name']}"
    elif from_card_id and to_account_id:
        out_type, in_type = "cash_advance", "transfer"
        out_desc = description or f"Cash advance to {target['name']}"
        in_desc = description or f"Cash advance from {source['name']}"
    else:
        raise ApiError("Card-to-card transfers are not supported")

    out_tx = create_transaction(conn, {
        "person_id": person_id, "account_id": from_account_id, "card_id": from_card_id,
        "type": out_type, "date": tx_date, "description": out_desc, "amount": amount,
        "direction": "out", "currency": source["currency"], "transfer_group": group,
        "notes": clean_text(body.get("notes"), 1000),
    })
    in_tx = create_transaction(conn, {
        "person_id": person_id, "account_id": to_account_id, "card_id": to_card_id,
        "type": in_type, "date": tx_date, "description": in_desc, "amount": amount,
        "direction": "in", "currency": target["currency"], "transfer_group": group,
        "notes": clean_text(body.get("notes"), 1000),
    })
    return {"group": group, "out": out_tx, "in": in_tx}


@route("POST", "/api/v1/transfers")
def transfers_create(ctx: Ctx):
    return record_transfer(ctx.conn, body_dict(ctx.body))


@route("POST", "/api/v1/cards/{id}/payments")
def cards_payment(ctx: Ctx):
    card_id = as_int(ctx.params["id"], "id", required=True)
    card = ensure_card(ctx.conn, card_id)
    body = body_dict(ctx.body)
    amount = as_float(body.get("amount"), "amount", required=True, minimum=0.01)
    pay_date = as_date(body.get("date") or date.today().isoformat(), "date")
    account_id = as_int(body.get("account_id"), "account_id")
    statement_id = as_int(body.get("statement_id"), "statement_id")
    description = clean_text(body.get("description"), 300) or f"Payment to {card['name']}"
    group = uuid.uuid4().hex

    if account_id:
        account = ensure_account(ctx.conn, account_id)
        if account["person_id"] != card["person_id"]:
            raise ApiError("Card and bank account belong to different people")
        create_transaction(ctx.conn, {
            "person_id": card["person_id"], "account_id": account_id, "type": "card_payment",
            "date": pay_date, "description": description, "amount": amount, "direction": "out",
            "currency": account["currency"], "transfer_group": group,
        })
    payment = create_transaction(ctx.conn, {
        "person_id": card["person_id"], "card_id": card_id, "type": "payment",
        "date": pay_date, "description": description, "amount": amount, "direction": "in",
        "currency": card["currency"], "transfer_group": group,
    })
    if statement_id:
        st = q1(ctx.conn, "SELECT * FROM statements WHERE id = ? AND card_id = ?", (statement_id, card_id))
        if st:
            paid = float(st["amount_paid"] or 0) + amount
            status = "paid" if paid >= float(st["closing_balance"] or 0) else "partial"
            ctx.conn.execute(
                "UPDATE statements SET amount_paid = ?, status = ?, paid_date = ?, updated_at = ? WHERE id = ?",
                (paid, status, pay_date, now_iso(), statement_id),
            )
    return {"payment": payment, "statement_id": statement_id}


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------

def _statement_status(row: dict) -> str:
    paid = float(row.get("amount_paid") or 0)
    closing = float(row.get("closing_balance") or 0)
    due = row.get("due_date") or ""
    if paid >= closing and closing > 0:
        return "paid"
    if paid > 0:
        return "partial"
    if due and due < date.today().isoformat():
        return "overdue"
    return "unpaid"


@route("GET", "/api/v1/statements")
def statements_list(ctx: Ctx):
    where, params = [], []
    person_id = query_person(ctx)
    if person_id:
        where.append("c.person_id = ?")
        params.append(person_id)
    if ctx.query.get("card_id"):
        where.append("s.card_id = ?")
        params.append(as_int(ctx.query["card_id"], "card_id"))
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    rows = q(ctx.conn,
             f"""SELECT s.*, c.name AS card_name, c.currency, c.person_id
                 FROM statements s JOIN cards c ON c.id = s.card_id{clause}
                 ORDER BY s.statement_date DESC, s.id DESC""", params)
    for row in rows:
        row["remaining"] = finance.money(max(0.0, float(row["closing_balance"]) - float(row["amount_paid"])))
        row["effective_status"] = _statement_status(row)
    return rows


@route("POST", "/api/v1/statements")
def statements_create(ctx: Ctx):
    body = body_dict(ctx.body)
    card_id = as_int(body.get("card_id"), "card_id", required=True)
    card = ensure_card(ctx.conn, card_id)
    statement_date = as_date(body.get("statement_date"), "statement_date")
    closing = as_float(body.get("closing_balance"), "closing_balance", default=0)
    amount_paid = as_float(body.get("amount_paid"), "amount_paid", default=0, minimum=0)
    stamp = now_iso()
    status = body.get("status") or ("paid" if amount_paid >= closing and closing > 0 else
                                    ("partial" if amount_paid > 0 else "unpaid"))
    cur = ctx.conn.execute(
        """INSERT INTO statements(card_id, period_start, period_end, statement_date, due_date,
               opening_balance, closing_balance, minimum_due, amount_paid, paid_date, status, notes,
               created_at, updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (card_id, as_date(body.get("period_start"), "period_start", False),
         as_date(body.get("period_end"), "period_end", False), statement_date,
         as_date(body.get("due_date"), "due_date", False),
         as_float(body.get("opening_balance"), "opening_balance", default=0), closing,
         as_float(body.get("minimum_due"), "minimum_due", default=0, minimum=0), amount_paid,
         as_date(body.get("paid_date"), "paid_date", False), status,
         clean_text(body.get("notes"), 1000), stamp, stamp),
    )
    row = q1(ctx.conn, "SELECT * FROM statements WHERE id = ?", (cur.lastrowid,))
    row["remaining"] = finance.money(max(0.0, closing - amount_paid))
    row["effective_status"] = _statement_status(row)
    row["card_name"] = card["name"]
    return row


@route("PUT", "/api/v1/statements/{id}")
def statements_update(ctx: Ctx):
    statement_id = as_int(ctx.params["id"], "id", required=True)
    existing = q1(ctx.conn, "SELECT * FROM statements WHERE id = ?", (statement_id,))
    if not existing:
        raise ApiError("Statement not found", 404)
    body = body_dict(ctx.body)
    for field_name in ("statement_date", "due_date", "period_start", "period_end", "paid_date"):
        if field_name in body:
            body[field_name] = as_date(body[field_name], field_name, False)
    for field_name in ("opening_balance", "closing_balance"):
        if field_name in body:
            body[field_name] = as_float(body[field_name], field_name, default=0)
    for field_name in ("minimum_due", "amount_paid"):
        if field_name in body:
            body[field_name] = as_float(body[field_name], field_name, default=0, minimum=0)
    if "card_id" in body:
        ensure_card(ctx.conn, as_int(body["card_id"], "card_id", required=True))
    update_row(ctx.conn, "statements", statement_id, body,
               {"card_id", "period_start", "period_end", "statement_date", "due_date",
                "opening_balance", "closing_balance", "minimum_due", "amount_paid", "paid_date",
                "status", "notes"})
    row = q1(ctx.conn, "SELECT * FROM statements WHERE id = ?", (statement_id,))
    effective = _statement_status(row)
    if row.get("status") != effective:
        ctx.conn.execute("UPDATE statements SET status = ?, updated_at = ? WHERE id = ?",
                         (effective, now_iso(), statement_id))
        row["status"] = effective
    row["remaining"] = finance.money(max(0.0, float(row["closing_balance"]) - float(row["amount_paid"])))
    row["effective_status"] = effective
    return row


@route("DELETE", "/api/v1/statements/{id}")
def statements_delete(ctx: Ctx):
    statement_id = as_int(ctx.params["id"], "id", required=True)
    if not q1(ctx.conn, "SELECT id FROM statements WHERE id = ?", (statement_id,)):
        raise ApiError("Statement not found", 404)
    ctx.conn.execute("DELETE FROM statements WHERE id = ?", (statement_id,))
    return {"deleted": statement_id}


@route("POST", "/api/v1/statements/{id}/pay")
def statements_pay(ctx: Ctx):
    statement_id = as_int(ctx.params["id"], "id", required=True)
    st = q1(ctx.conn, "SELECT * FROM statements WHERE id = ?", (statement_id,))
    if not st:
        raise ApiError("Statement not found", 404)
    body = body_dict(ctx.body)
    remaining = max(0.0, float(st["closing_balance"]) - float(st["amount_paid"]))
    amount = as_float(body.get("amount"), "amount", default=remaining, minimum=0.01)
    payment_ctx = Ctx(
        conn=ctx.conn,
        query=ctx.query,
        body={**body, "amount": amount, "statement_id": statement_id},
        params={"id": str(st["card_id"])},
        headers=ctx.headers,
        method="POST",
        path=ctx.path,
    )
    return cards_payment(payment_ctx)
