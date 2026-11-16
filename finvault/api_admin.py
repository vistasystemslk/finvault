"""Bulk import, CSV statement import, exports, backups and admin actions."""
from __future__ import annotations

import csv
import io
import json
import threading
from datetime import date, datetime
from pathlib import Path

from . import finance
from .api_accounts import create_transaction
from .api_base import (
    ApiError, Ctx, Raw, as_bool, as_float, as_int, body_dict, clean_text, ensure_card,
    ensure_category, query_person, route,
)
from .config import APP_DIR, APP_VERSION, BACKUP_DIR, DB_PATH, EXPORT_DIR
from .db import (
    backup_database, integrity_check, now_iso, q, q1, restore_backup, scalar,
)

TABLE_EXPORTS = {
    "persons": "SELECT * FROM persons ORDER BY id",
    "cards": "SELECT * FROM cards ORDER BY id",
    "accounts": "SELECT * FROM accounts ORDER BY id",
    "transactions": "SELECT * FROM transactions ORDER BY date, id",
    "statements": "SELECT * FROM statements ORDER BY statement_date, id",
    "installments": "SELECT * FROM installment_plans ORDER BY id",
    "loans": "SELECT * FROM loans ORDER BY id",
    "loan_payments": "SELECT * FROM loan_payments ORDER BY date, id",
    "assets": "SELECT * FROM assets ORDER BY id",
    "liabilities": "SELECT * FROM liabilities ORDER BY id",
    "incomes": "SELECT * FROM incomes ORDER BY date, id",
    "budgets": "SELECT * FROM budgets ORDER BY month, id",
    "goals": "SELECT * FROM goals ORDER BY id",
    "tax_reliefs": "SELECT * FROM tax_reliefs ORDER BY id",
    "tax_credits": "SELECT * FROM tax_credits ORDER BY id",
    "tax_rules": "SELECT * FROM tax_rules ORDER BY year_label",
    "categories": "SELECT * FROM categories ORDER BY sort_order, id",
    "fx_rates": "SELECT * FROM fx_rates ORDER BY currency",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(value: str, day_first: bool = True) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError("missing date")
    text = text.split("T")[0].split(" ")[0]
    formats = ["%Y-%m-%d", "%Y/%m/%d"]
    if day_first:
        formats += ["%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y", "%d.%m.%Y", "%d %b %Y", "%d-%b-%Y"]
    else:
        formats += ["%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%m-%d-%y", "%d %b %Y", "%d-%b-%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date '{value}'")


def _parse_amount(value: str) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace(",", "").replace("Rs.", "").replace("Rs", "")
    text = text.replace("LKR", "").replace("USD", "").replace("$", "").strip()
    if text in {"", "-"}:
        return 0.0
    number = float(text)
    return -number if negative else number


def _detect_delimiter(text: str) -> str:
    sample = text[:5000]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _header_value(row: dict, mapping_value, headers: dict[str, str]) -> str:
    if mapping_value is None or mapping_value == "":
        return ""
    if isinstance(mapping_value, int):
        values = list(row.values())
        return str(values[mapping_value]) if mapping_value < len(values) else ""
    key = str(mapping_value).strip()
    if key in row:
        return str(row.get(key) or "")
    lowered = key.lower()
    if lowered in headers:
        return str(row.get(headers[lowered]) or "")
    return ""


def _resolve_category(conn, item: dict) -> int | None:
    category_id = as_int(item.get("category_id"), "category_id")
    if category_id:
        return category_id
    name = clean_text(item.get("category"), 80)
    if name:
        row = q1(conn, "SELECT id FROM categories WHERE lower(name) = lower(?)", (name,))
        if row:
            return row["id"]
    return None


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

@route("POST", "/api/v1/import/transactions")
def import_transactions(ctx: Ctx):
    body = body_dict(ctx.body)
    items = body.get("items")
    if not isinstance(items, list) or not items:
        raise ApiError("items must be a non-empty list", field="items")
    if len(items) > 5000:
        raise ApiError("Maximum 5,000 transactions per import")
    defaults = body.get("defaults") or {}
    if not isinstance(defaults, dict):
        defaults = {}
    dry_run = as_bool(body.get("dry_run"), False)
    skip_duplicates = as_bool(body.get("skip_duplicates"), False)

    inserted, errors, skipped, preview = [], [], 0, []
    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            errors.append({"index": index, "error": "item must be an object"})
            continue
        item = {**defaults, **raw}
        try:
            item["category_id"] = _resolve_category(ctx.conn, item)
            if skip_duplicates:
                signature = (
                    item.get("card_id"), item.get("account_id"), item.get("date"),
                    round(float(item.get("amount") or 0), 2), item.get("direction"),
                    clean_text(item.get("description"), 300).lower(),
                )
                existing = scalar(ctx.conn,
                                  """SELECT COUNT(*) FROM transactions
                                     WHERE COALESCE(card_id,0) = COALESCE(?,0)
                                       AND COALESCE(account_id,0) = COALESCE(?,0)
                                       AND date = ? AND round(amount,2) = ? AND direction = ?
                                       AND lower(description) = ?""",
                                  (signature[0], signature[1], signature[2], signature[3],
                                   signature[4] or "", signature[5]))
                if existing:
                    skipped += 1
                    continue
            if dry_run:
                preview.append(item)
                continue
            created = create_transaction(ctx.conn, item)
            inserted.append(created["id"])
            if len(preview) < 15:
                preview.append(created)
        except ApiError as error:
            errors.append({"index": index, "error": error.message, "field": error.field})
        except Exception as error:  # noqa: BLE001 - report row-level import issues
            errors.append({"index": index, "error": str(error)})
    return {
        "inserted": len(inserted),
        "skipped": skipped,
        "errors": errors,
        "preview": preview,
        "dry_run": dry_run,
    }


@route("POST", "/api/v1/import/csv")
def import_csv(ctx: Ctx):
    body = body_dict(ctx.body)
    text = body.get("csv_text") or ""
    if not isinstance(text, str) or not text.strip():
        raise ApiError("csv_text is required", field="csv_text")
    card_id = as_int(body.get("card_id"), "card_id")
    account_id = as_int(body.get("account_id"), "account_id")
    if not card_id and not account_id:
        raise ApiError("Choose a card_id or account_id for this import")
    if card_id:
        card = ensure_card(ctx.conn, card_id)
        person_id = card["person_id"]
        destination_currency = card["currency"]
    else:
        from .api_base import ensure_account
        account = ensure_account(ctx.conn, account_id)
        person_id = account["person_id"]
        destination_currency = account["currency"]

    mapping = body.get("mapping") or {}
    if not isinstance(mapping, dict) or not mapping.get("date"):
        raise ApiError("mapping.date is required", field="mapping")
    category_id = as_int(body.get("category_id"), "category_id")
    ensure_category(ctx.conn, category_id)
    default_type = clean_text(body.get("default_type"), 30)
    default_direction = clean_text(body.get("default_direction"), 10) or "out"
    day_first = as_bool(body.get("day_first"), True)
    signed_amount = as_bool(body.get("signed_amount"), True)
    skip_duplicates = as_bool(body.get("skip_duplicates"), True)
    dry_run = as_bool(body.get("dry_run"), False)
    is_business = as_bool(body.get("is_business"), False)
    tax_deductible = as_bool(body.get("tax_deductible"), False)

    delimiter = _detect_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise ApiError("Could not read any columns from the CSV")
    headers = {str(name or "").strip().lower(): name for name in reader.fieldnames}

    rows, errors = [], []
    for line_number, raw in enumerate(reader, start=2):
        if line_number > 5002:
            raise ApiError("Maximum 5,000 rows per import")
        try:
            date_text = _header_value(raw, mapping.get("date"), headers)
            tx_date = _parse_date(date_text, day_first)
            description = _header_value(raw, mapping.get("description"), headers)
            if not description:
                description = clean_text(body.get("default_description"), 300) or "Imported transaction"
            direction = default_direction
            amount = 0.0
            if mapping.get("debit") or mapping.get("credit"):
                debit = _parse_amount(_header_value(raw, mapping.get("debit"), headers)) if mapping.get("debit") else 0
                credit = _parse_amount(_header_value(raw, mapping.get("credit"), headers)) if mapping.get("credit") else 0
                if debit:
                    amount, direction = abs(debit), "out"
                elif credit:
                    amount, direction = abs(credit), "in"
            else:
                raw_amount = _parse_amount(_header_value(raw, mapping.get("amount"), headers))
                amount = abs(raw_amount)
                if signed_amount and raw_amount < 0:
                    direction = "in"
            if amount == 0:
                errors.append({"line": line_number, "error": "zero or missing amount"})
                continue
            if direction == "in":
                tx_type = default_type or ("payment" if card_id else "adjustment")
            else:
                tx_type = default_type or ("purchase" if card_id else "expense")
            rows.append({
                "person_id": person_id, "card_id": card_id, "account_id": account_id,
                "type": tx_type, "date": tx_date, "description": description,
                "category_id": category_id, "amount": amount, "direction": direction,
                "currency": destination_currency, "is_business": is_business,
                "tax_deductible": tax_deductible,
                "notes": clean_text(body.get("notes"), 500),
            })
        except Exception as error:  # noqa: BLE001
            errors.append({"line": line_number, "error": str(error)})

    inserted, skipped = [], 0
    if not dry_run:
        existing_signatures = set()
        if skip_duplicates:
            for row in q(ctx.conn,
                         """SELECT date, round(amount,2) AS amount, direction, lower(description) AS description
                            FROM transactions WHERE COALESCE(card_id,0) = ? AND COALESCE(account_id,0) = ?""",
                         (card_id or 0, account_id or 0)):
                existing_signatures.add((row["date"], row["amount"], row["direction"], row["description"]))
        for item in rows:
            signature = (item["date"], round(item["amount"], 2), item["direction"], item["description"].lower())
            if skip_duplicates and signature in existing_signatures:
                skipped += 1
                continue
            try:
                created = create_transaction(ctx.conn, item)
                inserted.append(created["id"])
                existing_signatures.add(signature)
            except ApiError as error:
                errors.append({"line": None, "error": error.message, "description": item["description"]})
    return {
        "parsed": len(rows),
        "inserted": len(inserted),
        "skipped": skipped,
        "errors": errors[:50],
        "preview": rows[:15],
        "dry_run": dry_run,
        "delimiter": delimiter,
        "columns": list(reader.fieldnames),
    }


@route("POST", "/api/v1/import/card-statement")
def import_card_statement(ctx: Ctx):
    """Import one card statement and its transactions.

    Safe to retry: a statement is identified by (card_id, statement_date), so a
    repeat call returns `duplicate: true` instead of importing twice. Pass
    `replace: true` to re-import, `dry_run: true` to validate only, and
    `strict: true` to reject a statement whose rows do not reconcile.
    """
    body = body_dict(ctx.body)
    card_id = as_int(body.get("card_id"), "card_id", required=True)
    card = ensure_card(ctx.conn, card_id)
    statement = body.get("statement") or {}
    if not isinstance(statement, dict):
        raise ApiError("statement must be an object", field="statement")
    statement_date = statement.get("statement_date") or date.today().isoformat()
    closing = as_float(statement.get("closing_balance"), "closing_balance", default=0)
    opening = as_float(statement.get("opening_balance"), "opening_balance", default=0)
    amount_paid = as_float(statement.get("amount_paid"), "amount_paid", default=0, minimum=0)
    replace = as_bool(body.get("replace"), False)
    skip_duplicates = as_bool(body.get("skip_duplicates"), True)
    strict = as_bool(body.get("strict"), False)
    dry_run = as_bool(body.get("dry_run"), False)
    has_balances = "opening_balance" in statement and "closing_balance" in statement

    existing = q1(ctx.conn,
                  "SELECT id FROM statements WHERE card_id = ? AND statement_date = ?",
                  (card_id, statement_date))
    if existing and not replace:
        return {
            "duplicate": True,
            "statement_id": existing["id"],
            "inserted": 0,
            "skipped": 0,
            "errors": [],
            "message": (f"A statement dated {statement_date} already exists for this card. "
                        "Pass replace=true to re-import it."),
        }

    transactions = body.get("transactions") or []
    if not isinstance(transactions, list):
        raise ApiError("transactions must be a list", field="transactions")

    prepared: list[dict] = []
    errors: list[dict] = []
    for index, raw in enumerate(transactions):
        if not isinstance(raw, dict):
            errors.append({"index": index, "error": "item must be an object"})
            continue
        item = {**raw}
        item.setdefault("person_id", card["person_id"])
        item.setdefault("card_id", card_id)
        item.setdefault("currency", card["currency"])
        item.setdefault("type", "purchase" if (item.get("direction") or "out") == "out" else "payment")
        try:
            item["category_id"] = _resolve_category(ctx.conn, item)
            prepared.append(item)
        except ApiError as error:
            errors.append({"index": index, "error": error.message})

    net = round(sum((-float(i["amount"]) if i.get("direction") == "in" else float(i["amount"]))
                    for i in prepared), 2)
    difference = round(opening + net - closing, 2) if has_balances else 0.0
    reconciles = (not has_balances) or abs(difference) <= 0.01
    if strict and not reconciles:
        raise ApiError(
            f"Statement does not reconcile: opening {opening:,.2f} + rows {net:,.2f} "
            f"= {opening + net:,.2f} but closing is {closing:,.2f} (off by {difference:,.2f})")

    if dry_run:
        return {
            "duplicate": False,
            "dry_run": True,
            "would_insert": len(prepared),
            "errors": errors[:50],
            "net_movement": net,
            "reconciles": reconciles,
            "difference": difference,
            "preview": prepared[:15],
        }

    stamp = now_iso()
    if existing and replace:
        ctx.conn.execute("DELETE FROM transactions WHERE statement_id = ?", (existing["id"],))
        ctx.conn.execute("DELETE FROM statements WHERE id = ?", (existing["id"],))

    cur = ctx.conn.execute(
        """INSERT INTO statements(card_id, period_start, period_end, statement_date, due_date,
               opening_balance, closing_balance, minimum_due, amount_paid, status, notes,
               created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (card_id, clean_text(statement.get("period_start"), 10), clean_text(statement.get("period_end"), 10),
         clean_text(statement_date, 10), clean_text(statement.get("due_date"), 10), opening, closing,
         as_float(statement.get("minimum_due"), "minimum_due", default=0, minimum=0), amount_paid,
         "paid" if amount_paid >= closing and closing > 0 else ("partial" if amount_paid else "unpaid"),
         clean_text(statement.get("notes"), 1000), stamp, stamp),
    )
    statement_id = cur.lastrowid
    if as_bool(body.get("set_card_opening_balance"), False):
        ctx.conn.execute("UPDATE cards SET opening_balance = ?, updated_at = ? WHERE id = ?",
                         (opening, stamp, card_id))

    signatures: set[tuple] = set()
    if skip_duplicates:
        for row in q(ctx.conn,
                     """SELECT date, round(amount, 2) AS amount, direction, lower(description) AS description
                        FROM transactions WHERE card_id = ?""", (card_id,)):
            signatures.add((row["date"], row["amount"], row["direction"], row["description"]))

    inserted, skipped = [], 0
    for item in prepared:
        item["statement_id"] = statement_id
        signature = (item.get("date"), round(float(item.get("amount") or 0), 2),
                     item.get("direction"), clean_text(item.get("description"), 300).lower())
        if skip_duplicates and signature in signatures:
            skipped += 1
            continue
        try:
            created = create_transaction(ctx.conn, item)
            inserted.append(created["id"])
            signatures.add(signature)
        except ApiError as error:
            errors.append({"index": None, "error": error.message,
                           "description": item.get("description", "")})

    return {
        "duplicate": False,
        "statement_id": statement_id,
        "inserted": len(inserted),
        "skipped": skipped,
        "errors": errors[:50],
        "opening_balance": opening,
        "closing_balance": closing,
        "net_movement": net,
        "reconciles": reconciles,
        "difference": difference,
    }


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@route("GET", "/api/v1/export")
def export_data(ctx: Ctx):
    fmt = (ctx.query.get("format") or "json").lower()
    table = ctx.query.get("table") or "transactions"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if fmt == "json":
        data = {}
        for name, sql in TABLE_EXPORTS.items():
            data[name] = q(ctx.conn, sql)
        payload = {
            "meta": {"app": "FinVault", "version": APP_VERSION, "exported_at": now_iso()},
            "data": data,
        }
        return Raw(json.dumps(payload, indent=2, default=str),
                   "application/json",
                   headers={"Content-Disposition": f'attachment; filename="FinVault-export-{stamp}.json"'})
    if fmt == "csv":
        if table == "tax":
            return _tax_csv(ctx, stamp)
        sql = TABLE_EXPORTS.get(table)
        if not sql:
            raise ApiError(f"Unknown table '{table}'. Options: {', '.join(TABLE_EXPORTS)}", 404)
        rows = q(ctx.conn, sql)
        output = io.StringIO()
        if rows:
            writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return Raw(output.getvalue(), "text/csv",
                   headers={"Content-Disposition": f'attachment; filename="FinVault-{table}-{stamp}.csv"'})
    raise ApiError("format must be json or csv", field="format")


def _tax_csv(ctx: Ctx, stamp: str) -> Raw:
    person_id = query_person(ctx) or (q1(ctx.conn, "SELECT id FROM persons ORDER BY is_primary DESC, id LIMIT 1") or {}).get("id")
    if not person_id:
        raise ApiError("No person found")
    year_label = ctx.query.get("year_label") or finance.current_tax_year()
    estimate = finance.tax_estimate(ctx.conn, person_id, year_label)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["FinVault tax summary"])
    writer.writerow(["Person", estimate["person"]["name"]])
    writer.writerow(["TIN", estimate["person"]["tin"]])
    writer.writerow(["Year of assessment", year_label])
    writer.writerow(["Period", estimate["year_range"]["start"], estimate["year_range"]["end"]])
    writer.writerow([])
    writer.writerow(["Income head", "Amount"])
    for head, amount in estimate["heads"].items():
        writer.writerow([head.title(), amount])
    writer.writerow(["Total assessable income", estimate["total_assessable"]])
    writer.writerow([])
    writer.writerow(["Deductions / reliefs", "Amount"])
    writer.writerow(["Rent relief", estimate["deductions"]["rent_relief"]])
    writer.writerow(["Qualifying reliefs", estimate["deductions"]["qualifying_reliefs"]])
    writer.writerow(["Tax-deductible expenses (business)", estimate["deductions"]["used_against_business"]])
    writer.writerow(["Total reliefs", estimate["deductions"]["total"]])
    writer.writerow([])
    writer.writerow(["Taxable income", estimate["taxable_income"]])
    writer.writerow(["Slab", "Rate", "Amount", "Tax"])
    for slab in estimate["slabs"]:
        writer.writerow([f"{slab['from']} - {slab['to'] or 'above'}", f"{slab['rate'] * 100:.0f}%",
                         slab["amount"], slab["tax"]])
    writer.writerow(["Gross tax", estimate["gross_tax"]])
    writer.writerow(["APIT credit", estimate["credits"]["apit"]])
    writer.writerow(["WHT credit", estimate["credits"]["wht"]])
    writer.writerow(["Other credits", estimate["credits"]["other"]])
    writer.writerow(["Tax payable", estimate["tax_payable"]])
    writer.writerow(["Effective rate %", estimate["effective_rate"]])
    return Raw(output.getvalue(), "text/csv",
               headers={"Content-Disposition": f'attachment; filename="FinVault-tax-{year_label.replace("/", "-")}-{stamp}.csv"'})


# ---------------------------------------------------------------------------
# Backups and admin
# ---------------------------------------------------------------------------

@route("GET", "/api/v1/admin/stats")
def admin_stats(ctx: Ctx):
    size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    tables = {}
    for table in ("persons", "cards", "accounts", "transactions", "statements", "installment_plans",
                  "loans", "assets", "liabilities", "incomes"):
        try:
            tables[table] = scalar(ctx.conn, f"SELECT COUNT(*) FROM {table}")
        except Exception:  # noqa: BLE001
            tables[table] = 0
    return {
        "app_version": APP_VERSION,
        "database_path": str(DB_PATH),
        "database_size": size,
        "app_dir": str(APP_DIR),
        "counts": tables,
        "backup_dir": str(BACKUP_DIR),
        "export_dir": str(EXPORT_DIR),
        "integrity": integrity_check(DB_PATH) if DB_PATH.exists() else "missing",
    }


@route("POST", "/api/v1/admin/backup")
def admin_backup(ctx: Ctx):
    target = backup_database(DB_PATH, BACKUP_DIR, reason="manual")
    if not target:
        raise ApiError("Database file not found", 500)
    return {"file": target.name, "path": str(target), "size": target.stat().st_size}


@route("GET", "/api/v1/admin/backups")
def admin_backups(ctx: Ctx):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for path in sorted(BACKUP_DIR.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = path.stat()
        files.append({
            "name": path.name,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        })
    return files


@route("POST", "/api/v1/admin/restore")
def admin_restore(ctx: Ctx):
    body = body_dict(ctx.body)
    name = clean_text(body.get("name"), 200)
    if not name or "/" in name or "\\" in name or ".." in name:
        raise ApiError("Invalid backup name", field="name")
    target = BACKUP_DIR / name
    if not target.exists():
        raise ApiError("Backup not found", 404)
    restore_backup(target, DB_PATH)
    return {"restored": name, "restart_required": False}


@route("POST", "/api/v1/admin/vacuum")
def admin_vacuum(ctx: Ctx):
    ctx.conn.execute("VACUUM")
    return {"ok": True, "size": DB_PATH.stat().st_size if DB_PATH.exists() else 0}


@route("GET", "/api/v1/admin/log")
def admin_log(ctx: Ctx):
    lines = as_int(ctx.query.get("lines"), "lines", default=150, minimum=1, maximum=2000)
    log_path = APP_DIR / "finvault.log"
    if not log_path.exists():
        return {"lines": []}
    content = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"lines": content[-lines:]}


@route("POST", "/api/v1/admin/shutdown")
def admin_shutdown(ctx: Ctx):
    server = ctx.server
    if server:
        threading.Timer(0.6, server.shutdown).start()
    return {"ok": True, "message": "FinVault is shutting down. You can close this tab."}
