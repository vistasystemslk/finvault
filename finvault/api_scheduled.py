"""Scheduled transactions (reminders) and the due/overdue reminder feed."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from . import finance
from .api_accounts import create_transaction
from .api_base import (
    ApiError, Ctx, as_bool, as_choice, as_date, as_float, as_int, body_dict, clean_text,
    ensure_account, ensure_card, ensure_category, ensure_person, query_person, route, update_row,
)
from .db import now_iso, q, q1

FREQUENCIES = {"once", "weekly", "monthly", "quarterly", "yearly"}
SCHEDULE_TYPES = {"expense", "income", "card_payment", "transfer", "loan_payment"}
EDITABLE = {"person_id", "name", "amount", "currency", "type", "frequency", "next_due_date",
            "end_date", "account_id", "card_id", "category_id", "installments_left",
            "auto_post", "is_active", "notes"}


def _advance(due: str, frequency: str) -> str:
    current = datetime.strptime(due, "%Y-%m-%d").date()
    if frequency == "weekly":
        nxt = current + timedelta(days=7)
    elif frequency == "monthly":
        nxt = finance.add_months(current, 1)
    elif frequency == "quarterly":
        nxt = finance.add_months(current, 3)
    elif frequency == "yearly":
        nxt = finance.add_months(current, 12)
    else:
        return ""
    return nxt.isoformat()


def _status(due: str, active: int) -> str:
    if not active:
        return "paused"
    if not due:
        return "done"
    days = finance.days_until(due)
    if days is None:
        return "upcoming"
    if days < 0:
        return "overdue"
    if days == 0:
        return "today"
    if days <= 3:
        return "soon"
    return "upcoming"


def _payload(conn, row) -> dict:
    data = dict(row) if not isinstance(row, dict) else dict(row)
    data["days_left"] = finance.days_until(data.get("next_due_date") or "")
    data["status"] = _status(data.get("next_due_date") or "", int(data.get("is_active") or 0))
    data["account_name"] = ""
    data["card_name"] = ""
    data["category_name"] = ""
    if data.get("account_id"):
        acc = q1(conn, "SELECT name FROM accounts WHERE id = ?", (data["account_id"],))
        data["account_name"] = acc["name"] if acc else ""
    if data.get("card_id"):
        card = q1(conn, "SELECT name FROM cards WHERE id = ?", (data["card_id"],))
        data["card_name"] = card["name"] if card else ""
    if data.get("category_id"):
        cat = q1(conn, "SELECT name FROM categories WHERE id = ?", (data["category_id"],))
        data["category_name"] = cat["name"] if cat else ""
    return data


def _validate(conn, body: dict, existing: dict | None = None) -> dict:
    """Normalise and check a scheduled-transaction payload."""
    out: dict[str, Any] = {}
    if "person_id" in body or existing is None:
        person_id = as_int(body.get("person_id"), "person_id", required=existing is None)
        if person_id:
            ensure_person(conn, person_id)
            out["person_id"] = person_id
    if "name" in body or existing is None:
        name = clean_text(body.get("name"), 120)
        if not name:
            raise ApiError("Name is required", field="name")
        out["name"] = name
    for field_name in ("account_id", "card_id", "category_id"):
        if field_name in body or existing is None:
            value = as_int(body.get(field_name), field_name)
            if value:
                if field_name == "account_id":
                    ensure_account(conn, value)
                elif field_name == "card_id":
                    ensure_card(conn, value)
                else:
                    ensure_category(conn, value)
            out[field_name] = value or None
    if out.get("account_id") and out.get("card_id"):
        raise ApiError("Pick either a card or a bank account, not both", field="card_id")
    if "amount" in body or existing is None:
        out["amount"] = as_float(body.get("amount"), "amount", default=0.0, minimum=0)
    if "currency" in body or existing is None:
        out["currency"] = (clean_text(body.get("currency"), 8).upper() or
                           (conn.execute("SELECT value FROM settings WHERE key='base_currency'")
                            .fetchone() or ["LKR"])[0])
    if "type" in body or existing is None:
        out["type"] = as_choice(body.get("type"), "type", SCHEDULE_TYPES, "expense")
    if "frequency" in body or existing is None:
        out["frequency"] = as_choice(body.get("frequency"), "frequency", FREQUENCIES, "monthly")
    if "next_due_date" in body or existing is None:
        out["next_due_date"] = as_date(body.get("next_due_date"), "next_due_date")
    if "end_date" in body:
        out["end_date"] = as_date(body.get("end_date"), "end_date", False) if body.get("end_date") else ""
    if "installments_left" in body:
        out["installments_left"] = as_int(body.get("installments_left"), "installments_left",
                                          default=0, minimum=0)
    if "auto_post" in body:
        out["auto_post"] = as_bool(body.get("auto_post"))
    if "is_active" in body:
        out["is_active"] = 1 if as_bool(body.get("is_active"), True) else 0
    if "notes" in body:
        out["notes"] = clean_text(body.get("notes"), 1000)
    if out.get("installments_left", (existing or {}).get("installments_left", 0)) and out.get("frequency") in (None, "once"):
        out["frequency"] = "monthly"
    return out


@route("GET", "/api/v1/scheduled")
def scheduled_list(ctx: Ctx):
    person_id = query_person(ctx)
    sql = "SELECT * FROM scheduled"
    params: list[Any] = []
    if person_id:
        sql += " WHERE person_id = ?"
        params.append(person_id)
    if ctx.query.get("status") == "active":
        sql += (" AND" if person_id else " WHERE") + " is_active = 1"
    sql += " ORDER BY is_active DESC, next_due_date, name"
    return [_payload(ctx.conn, row) for row in q(ctx.conn, sql, params)]


@route("GET", "/api/v1/scheduled/{id}")
def scheduled_detail(ctx: Ctx):
    row = q1(ctx.conn, "SELECT * FROM scheduled WHERE id = ?", (as_int(ctx.params["id"], "id"),))
    if not row:
        raise ApiError("Reminder not found", 404)
    return _payload(ctx.conn, row)


@route("POST", "/api/v1/scheduled")
def scheduled_create(ctx: Ctx):
    data = _validate(ctx.conn, body_dict(ctx.body))
    stamp = now_iso()
    columns = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    cur = ctx.conn.execute(
        f"INSERT INTO scheduled({columns}, created_at, updated_at) VALUES({marks}, ?, ?)",
        list(data.values()) + [stamp, stamp])
    return _payload(ctx.conn, q1(ctx.conn, "SELECT * FROM scheduled WHERE id = ?", (cur.lastrowid,)))


@route("PUT", "/api/v1/scheduled/{id}")
def scheduled_update(ctx: Ctx):
    schedule_id = as_int(ctx.params["id"], "id")
    existing = q1(ctx.conn, "SELECT * FROM scheduled WHERE id = ?", (schedule_id,))
    if not existing:
        raise ApiError("Reminder not found", 404)
    data = _validate(ctx.conn, body_dict(ctx.body), existing)
    data = {k: v for k, v in data.items() if k in EDITABLE}
    if data:
        data["updated_at"] = now_iso()
        assignments = ", ".join(f"{key} = ?" for key in data)
        ctx.conn.execute(f"UPDATE scheduled SET {assignments} WHERE id = ?",
                         list(data.values()) + [schedule_id])
    return _payload(ctx.conn, q1(ctx.conn, "SELECT * FROM scheduled WHERE id = ?", (schedule_id,)))


@route("DELETE", "/api/v1/scheduled/{id}")
def scheduled_delete(ctx: Ctx):
    schedule_id = as_int(ctx.params["id"], "id")
    if not q1(ctx.conn, "SELECT id FROM scheduled WHERE id = ?", (schedule_id,)):
        raise ApiError("Reminder not found", 404)
    ctx.conn.execute("DELETE FROM scheduled WHERE id = ?", (schedule_id,))
    return {"deleted": schedule_id}


@route("POST", "/api/v1/scheduled/{id}/settle")
def scheduled_settle(ctx: Ctx):
    """Mark this occurrence paid, optionally posting the matching transaction."""
    schedule_id = as_int(ctx.params["id"], "id")
    row = q1(ctx.conn, "SELECT * FROM scheduled WHERE id = ?", (schedule_id,))
    if not row:
        raise ApiError("Reminder not found", 404)
    body = body_dict(ctx.body)
    paid_on = as_date(body.get("date") or date.today().isoformat(), "date")
    post = as_bool(body.get("post"), True)
    posted_id = None

    if post and float(row["amount"] or 0) > 0 and (row["card_id"] or row["account_id"]):
        txn = {
            "person_id": row["person_id"],
            "date": paid_on,
            "description": clean_text(body.get("description") or row["name"], 300),
            "amount": float(row["amount"]),
            "currency": row["currency"],
            "category_id": row["category_id"],
        }
        if row["type"] == "income":
            txn.update({"type": "income_deposit", "direction": "in", "account_id": row["account_id"]})
        else:
            txn["type"] = "expense"
            txn["direction"] = "out"
            if row["card_id"]:
                txn["card_id"] = row["card_id"]
            else:
                txn["account_id"] = row["account_id"]
        posted_id = create_transaction(ctx.conn, txn)["id"]

    frequency = row["frequency"] or "once"
    remaining = int(row["installments_left"] or 0)
    next_due = _advance(row["next_due_date"], frequency) if frequency != "once" else ""
    still_active = 1
    if remaining > 0:
        remaining -= 1
        if remaining == 0:
            next_due = ""
            still_active = 0
    if not next_due and frequency == "once":
        still_active = 0
    if row["end_date"] and next_due and next_due > row["end_date"]:
        next_due = ""
        still_active = 0

    ctx.conn.execute(
        """UPDATE scheduled SET next_due_date = ?, installments_left = ?, is_active = ?,
               last_paid_date = ?, updated_at = ? WHERE id = ?""",
        (next_due or row["next_due_date"], remaining, still_active, paid_on, now_iso(), schedule_id))
    return {
        "reminder": _payload(ctx.conn, q1(ctx.conn, "SELECT * FROM scheduled WHERE id = ?", (schedule_id,))),
        "transaction_id": posted_id,
        "posted": post and posted_id is not None,
    }


@route("GET", "/api/v1/reminders")
def reminders_list(ctx: Ctx):
    person_id = query_person(ctx)
    try:
        horizon = max(1, min(365, int(ctx.query.get("days", "21"))))
    except ValueError:
        horizon = 21
    return finance.reminders(ctx.conn, person_id, horizon)
