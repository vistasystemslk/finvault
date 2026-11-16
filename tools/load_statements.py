"""Load parsed statements into FinVault.db.

    python tools/load_statements.py --dry-run   # show what would happen
    python tools/load_statements.py             # back up, then import

Every statement is reconciled by tools/statements.py before import: the previous
statement's closing balance must equal the next one's opening balance.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finvault import db as fvdb  # noqa: E402
from tools import statements as P  # noqa: E402

CARD_SPECS = {
    "combank": {
        "name": "ComBank Visa Platinum",
        "issuer": "Commercial Bank of Ceylon",
        "network": "Visa",
        "last4": "8588",
        "credit_limit": 600000.0,
        "apr": 28.0,
        "statement_day": 10,
        "due_day": 1,
        "color_from": "#6d28d9",
        "color_to": "#2563eb",
        "notes": "Account 235761. Includes supplementary card ending 9170 until Feb 2026.",
    },
    "ntb": {
        "name": "Nations Trust World Mastercard",
        "issuer": "Nations Trust Bank",
        "network": "Mastercard",
        "last4": "6810",
        "credit_limit": 900000.0,
        "apr": 0.0,
        "statement_day": 12,
        "due_day": 2,
        "color_from": "#0f766e",
        "color_to": "#0ea5e9",
        "notes": "Account 112578580347784. Business card: every transaction is a business expense.",
        "purpose": "business",
        "business": True,
    },
    "seylan": {
        "name": "Seylan Visa",
        "issuer": "Seylan Bank",
        "network": "Visa",
        "last4": "3394",
        "credit_limit": 0.0,
        "apr": 0.0,
        "statement_day": 6,
        "due_day": 26,
        "color_from": "#b91c1c",
        "color_to": "#f97316",
        "notes": "Credit limit not printed on statements.",
    },
    "union": {
        "name": "Union Bank Platinum",
        "issuer": "Union Bank",
        "network": "Visa",
        "last4": "9005",
        "credit_limit": 225000.0,
        "apr": 0.0,
        "statement_day": 23,
        "due_day": 12,
        "color_from": "#1d4ed8",
        "color_to": "#0891b2",
        "notes": "Account 0560201000043385.",
    },
}

# Union Bank's PDF has no balances; these come from the bank app screenshot.
UNION_STATEMENT = {
    "statement_date": "2026-10-23",
    "period_start": "2026-09-23",
    "period_end": "2026-11-12",
    "closing": 22292.80,
    "minimum_due": 1000.00,
    "due_date": "2026-11-12",
}
UNION_ADJUSTMENT = {
    "date": "2026-10-12",
    "description": "Union Bank balance adjustment (PDF rows 26,913.80 vs billed 22,292.80)",
    "amount": 4621.00,
    "direction": "in",
    "type": "adjustment",
    "category": "Other",
    "notes": "Imported so the card matches the bank app's utilised balance; review and delete if wrong.",
}

INSTALLMENT_RE = re.compile(r"^(?P<label>.*?)\s*(?P<current>\d{1,3})\s+of\s+(?P<total>\d{1,3})\s*$")


def now() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def month_shift(d: date, months: int) -> date:
    return P.add_months(d, months)


def card_balance(conn: sqlite3.Connection, card_id: int) -> float:
    opening = conn.execute("SELECT opening_balance FROM cards WHERE id = ?", (card_id,)).fetchone()[0]
    signed = conn.execute(
        """SELECT COALESCE(SUM(CASE WHEN direction = 'in' THEN -amount ELSE amount END), 0)
           FROM transactions WHERE card_id = ?""", (card_id,)).fetchone()[0]
    return round(float(opening) + float(signed), 2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(fvdb.DB_PATH))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reset", action="store_true",
                    help="Delete imported cards/statements/transactions first")
    args = ap.parse_args()

    parsed = P.parse_all()
    errors = [s for s in parsed if s.get("error")]
    if errors:
        for s in errors:
            print(f"FAIL {s['bank']}/{s['file']}: {s['error']}")
        print("Refusing to import while statements fail to parse.")
        return 1

    by_bank: dict[str, list[dict]] = {}
    for st in parsed:
        by_bank.setdefault(st["bank"], []).append(st)
    for bank in by_bank:
        by_bank[bank].sort(key=lambda s: s["statement_date"])

    # Rolling-balance proof: each statement must open where the previous one closed.
    chain_problems = []
    for bank, items in by_bank.items():
        for prev, cur in zip(items, items[1:]):
            if abs(float(cur["opening"]) - float(prev["closing"])) > 0.01:
                chain_problems.append(
                    f"{bank}: {prev['statement_date']} closes {prev['closing']:,.2f} "
                    f"but {cur['statement_date']} opens {cur['opening']:,.2f}")
    if chain_problems:
        print("Balance chain broken:")
        for p in chain_problems:
            print("  " + p)
        return 1
    print("Balance chain verified: every statement opens at the previous closing balance.")

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return 1

    conn = fvdb.get_connection(db_path)
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    existing_cards = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    existing_txns = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    if (existing_cards or existing_txns) and not args.dry_run:
        if not args.reset:
            print(f"Database already has {existing_cards} cards and {existing_txns} transactions.")
            print("Use --reset to replace them, or point --db at a clean database.")
            return 1

    person = conn.execute("SELECT id FROM persons ORDER BY is_primary DESC, id LIMIT 1").fetchone()
    if not person:
        print("No person row found; run the app once to seed the database.")
        return 1
    person_id = int(person[0])

    categories = {row["name"]: int(row["id"])
                  for row in conn.execute("SELECT id, name FROM categories")}

    total_txns = 0
    total_statements = 0
    plan_count = 0
    summary: list[str] = []

    if not args.dry_run:
        backup_dir = Path(fvdb.BACKUP_DIR)
        backup_dir.mkdir(parents=True, exist_ok=True)
        dest = backup_dir / f"FinVault-before-statement-import-{datetime.now():%Y%m%d-%H%M%S}.db"
        shutil.copy2(db_path, dest)
        print(f"Backup written: {dest}")

    stamp = now()
    try:
        conn.execute("BEGIN")
        if args.reset:
            for table in ("transactions", "statements", "installment_plans", "cards"):
                conn.execute(f"DELETE FROM {table}")
            print("Cleared previous cards, statements and transactions.")
        for bank, items in by_bank.items():
            spec = CARD_SPECS[bank]
            opening = float(items[0]["opening"] or 0.0)
            cur = conn.execute(
                """INSERT INTO cards(person_id, name, issuer, network, last4, currency, credit_limit,
                        opening_balance, apr, statement_day, due_day, annual_fee, purpose,
                        color_from, color_to, status, notes, created_at, updated_at)
                   VALUES (?,?,?,?,?,'LKR',?,?,?,?,?,0,?,?,?,'active',?,?,?)""",
                (person_id, spec["name"], spec["issuer"], spec["network"], spec["last4"],
                 spec["credit_limit"], opening, spec["apr"], spec["statement_day"],
                 spec["due_day"], spec.get("purpose", "personal"),
                 spec["color_from"], spec["color_to"], spec["notes"], stamp, stamp))
            card_id = int(cur.lastrowid)
            is_business = 1 if spec.get("business") else 0

            latest = items[-1]
            statement_ids: dict[str, int] = {}
            if bank == "union":
                # The PDF has no balances; header values come from the bank app screenshot.
                cur = conn.execute(
                    """INSERT INTO statements(card_id, period_start, period_end, statement_date,
                            due_date, opening_balance, closing_balance, minimum_due, amount_paid,
                            paid_date, status, notes, created_at, updated_at)
                       VALUES (?,?,?,?,?,0,?,?,0,'','unpaid',?,?,?)""",
                    (card_id, UNION_STATEMENT["period_start"], UNION_STATEMENT["period_end"],
                     UNION_STATEMENT["statement_date"], UNION_STATEMENT["due_date"],
                     UNION_STATEMENT["closing"], UNION_STATEMENT["minimum_due"],
                     "Header from the Union Bank app (PDF carries no balances); "
                     "closing matches the app's utilised balance.", stamp, stamp))
                statement_ids[latest["file"]] = int(cur.lastrowid)
                total_statements += 1
            else:
                for st in items:
                    is_latest = st is latest
                    closing = float(st["closing"])
                    status = "unpaid" if is_latest else "paid"
                    amount_paid = 0.0 if is_latest else max(0.0, closing)
                    paid_date = "" if is_latest else (st["due_date"] or st["statement_date"])
                    note = f"Imported from {st['file']}"
                    if not is_latest:
                        note += " (historical; balance rolled forward)"
                    cur = conn.execute(
                        """INSERT INTO statements(card_id, period_start, period_end, statement_date,
                                due_date, opening_balance, closing_balance, minimum_due, amount_paid,
                                paid_date, status, notes, created_at, updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (card_id, st["period_start"], st["period_end"], st["statement_date"],
                         st["due_date"], float(st["opening"]), closing, float(st["minimum_due"] or 0),
                         amount_paid, paid_date, status, note, stamp, stamp))
                    statement_ids[st["file"]] = int(cur.lastrowid)
                    total_statements += 1

            for st in items:
                statement_id = statement_ids[st["file"]]
                for txn in st["transactions"]:
                    conn.execute(
                        """INSERT INTO transactions(person_id, card_id, account_id, type, date,
                                description, category_id, amount, direction, currency,
                                is_business, tax_deductible, notes, tags, statement_id,
                                created_at, updated_at)
                           VALUES (?,?,NULL,?,?,?,?,?,?,'LKR',?,0,?,'',?,?,?)""",
                        (person_id, card_id, txn["type"], txn["date"], txn["description"],
                         categories.get(txn["category"], categories.get("Other")),
                         float(txn["amount"]), txn["direction"], is_business,
                         (txn.get("notes") or ""), statement_id, stamp, stamp))
                    total_txns += 1

            # Active installment plans, taken from the newest statement only.
            if bank != "union":
                for txn in latest["transactions"]:
                    m = INSTALLMENT_RE.match(txn["description"])
                    if not m or txn["type"] != "installment":
                        continue
                    current, total_months = int(m.group("current")), int(m.group("total"))
                    if current > total_months:
                        continue
                    remaining = total_months - current + 1
                    due = date.fromisoformat(txn["date"])
                    first_due = month_shift(due, 1)
                    label = re.sub(r"\s+", " ", m.group("label")).strip() or "Installment"
                    conn.execute(
                        """INSERT INTO installment_plans(card_id, description, principal, months,
                                monthly_amount, interest_rate, start_date, first_due_date,
                                remaining_months, status, notes, created_at, updated_at)
                           VALUES (?,?,?,?,?,0,?,?,?, 'active', ?,?,?)""",
                        (card_id, label, round(float(txn["amount"]) * remaining, 2), total_months,
                         float(txn["amount"]), month_shift(first_due, -total_months).isoformat(),
                         first_due.isoformat(), remaining,
                         f"Imported from statement {latest['statement_date']} ({current} of {total_months})",
                         stamp, stamp))
                    plan_count += 1

            if bank == "union":
                adj = UNION_ADJUSTMENT
                conn.execute(
                    """INSERT INTO transactions(person_id, card_id, account_id, type, date,
                            description, category_id, amount, direction, currency,
                            is_business, tax_deductible, notes, tags, statement_id,
                            created_at, updated_at)
                       VALUES (?,?,NULL,?,?,?,?,?,?,'LKR',0,0,?,'',?,?,?)""",
                    (person_id, card_id, adj["type"], adj["date"], adj["description"],
                     categories.get(adj["category"], categories.get("Other")),
                     adj["amount"], adj["direction"], adj["notes"],
                     statement_ids[latest["file"]], stamp, stamp))
                total_txns += 1

            expected = float(UNION_STATEMENT["closing"]) if bank == "union" else float(latest["closing"])
            actual = card_balance(conn, card_id)
            if abs(expected - actual) > 0.01:
                raise SystemExit(
                    f"{bank}: card balance {actual:,.2f} does not match statement closing {expected:,.2f}")
            summary.append(f"{spec['name']:<36} {len(items):>2} statements  "
                           f"{sum(len(s['transactions']) for s in items):>3} transactions  "
                           f"balance {actual:>12,.2f}")

        if args.dry_run:
            conn.rollback()
            print("\n".join(summary))
            print(f"\nDry run: {total_statements} statements, {total_txns} transactions, "
                  f"{plan_count} installment plans would be imported. Nothing saved.")
            return 0
        conn.commit()
    except SystemExit:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise

    print("\n".join(summary))
    print(f"\nImported {total_statements} statements, {total_txns} transactions, {plan_count} installment plans.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
