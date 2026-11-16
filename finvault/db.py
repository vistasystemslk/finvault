"""SQLite schema, connections, seed data and backup helpers."""
from __future__ import annotations

import json
import secrets
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from .config import APP_VERSION, BASE_CURRENCY, DB_PATH, BACKUP_DIR

SCHEMA_VERSION = 1

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS persons (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    relationship  TEXT DEFAULT '',
    color         TEXT DEFAULT '#6366f1',
    email         TEXT DEFAULT '',
    phone         TEXT DEFAULT '',
    tin           TEXT DEFAULT '',
    date_of_birth TEXT DEFAULT '',
    is_primary    INTEGER NOT NULL DEFAULT 0,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fx_rates (
    currency   TEXT PRIMARY KEY,
    rate       REAL NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'expense',
    icon       TEXT DEFAULT '•',
    color      TEXT DEFAULT '#64748b',
    is_system  INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cards (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id       INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    issuer          TEXT DEFAULT '',
    network         TEXT DEFAULT '',
    last4           TEXT DEFAULT '',
    currency        TEXT NOT NULL DEFAULT 'LKR',
    credit_limit    REAL NOT NULL DEFAULT 0,
    opening_balance REAL NOT NULL DEFAULT 0,
    apr             REAL NOT NULL DEFAULT 0,
    statement_day   INTEGER DEFAULT 0,
    due_day         INTEGER DEFAULT 0,
    annual_fee      REAL DEFAULT 0,
    purpose         TEXT DEFAULT 'personal',
    color_from      TEXT DEFAULT '#4f46e5',
    color_to        TEXT DEFAULT '#0ea5e9',
    status          TEXT NOT NULL DEFAULT 'active',
    notes           TEXT DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id       INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    institution     TEXT DEFAULT '',
    type            TEXT DEFAULT 'savings',
    account_number  TEXT DEFAULT '',
    currency        TEXT NOT NULL DEFAULT 'LKR',
    opening_balance REAL NOT NULL DEFAULT 0,
    is_active       INTEGER NOT NULL DEFAULT 1,
    notes           TEXT DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id        INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    card_id          INTEGER REFERENCES cards(id) ON DELETE CASCADE,
    account_id       INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
    type             TEXT NOT NULL DEFAULT 'purchase',
    date             TEXT NOT NULL,
    description      TEXT NOT NULL DEFAULT '',
    category_id      INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    amount           REAL NOT NULL DEFAULT 0,
    direction        TEXT NOT NULL DEFAULT 'out',
    currency         TEXT NOT NULL DEFAULT 'LKR',
    is_business      INTEGER NOT NULL DEFAULT 0,
    tax_deductible   INTEGER NOT NULL DEFAULT 0,
    notes            TEXT DEFAULT '',
    tags             TEXT DEFAULT '',
    statement_id     INTEGER REFERENCES statements(id) ON DELETE SET NULL,
    installment_id   INTEGER REFERENCES installment_plans(id) ON DELETE SET NULL,
    income_id        INTEGER REFERENCES incomes(id) ON DELETE SET NULL,
    transfer_group   TEXT DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS statements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id         INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    period_start    TEXT DEFAULT '',
    period_end      TEXT DEFAULT '',
    statement_date  TEXT NOT NULL,
    due_date        TEXT DEFAULT '',
    opening_balance REAL NOT NULL DEFAULT 0,
    closing_balance REAL NOT NULL DEFAULT 0,
    minimum_due     REAL NOT NULL DEFAULT 0,
    amount_paid     REAL NOT NULL DEFAULT 0,
    paid_date       TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'unpaid',
    notes           TEXT DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS installment_plans (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id          INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    description      TEXT NOT NULL,
    principal        REAL NOT NULL DEFAULT 0,
    months           INTEGER NOT NULL DEFAULT 1,
    monthly_amount   REAL NOT NULL DEFAULT 0,
    interest_rate    REAL NOT NULL DEFAULT 0,
    start_date       TEXT DEFAULT '',
    first_due_date   TEXT DEFAULT '',
    remaining_months INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'active',
    notes            TEXT DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS loans (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id      INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    lender         TEXT DEFAULT '',
    type           TEXT DEFAULT 'personal',
    principal      REAL NOT NULL DEFAULT 0,
    outstanding    REAL NOT NULL DEFAULT 0,
    currency       TEXT NOT NULL DEFAULT 'LKR',
    annual_rate    REAL NOT NULL DEFAULT 0,
    monthly_payment REAL NOT NULL DEFAULT 0,
    start_date     TEXT DEFAULT '',
    term_months    INTEGER NOT NULL DEFAULT 0,
    next_due_date  TEXT DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'active',
    notes          TEXT DEFAULT '',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS loan_payments (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    loan_id            INTEGER NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
    date               TEXT NOT NULL,
    amount             REAL NOT NULL DEFAULT 0,
    principal_component REAL NOT NULL DEFAULT 0,
    interest_component REAL NOT NULL DEFAULT 0,
    notes              TEXT DEFAULT '',
    created_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id    INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    category     TEXT DEFAULT 'other',
    value        REAL NOT NULL DEFAULT 0,
    currency     TEXT NOT NULL DEFAULT 'LKR',
    acquired_date TEXT DEFAULT '',
    is_liquid    INTEGER NOT NULL DEFAULT 0,
    notes        TEXT DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS liabilities (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id      INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    category       TEXT DEFAULT 'other',
    balance        REAL NOT NULL DEFAULT 0,
    currency       TEXT NOT NULL DEFAULT 'LKR',
    annual_rate    REAL NOT NULL DEFAULT 0,
    monthly_payment REAL NOT NULL DEFAULT 0,
    notes          TEXT DEFAULT '',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS incomes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id    INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    date         TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT '',
    category_id  INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    amount       REAL NOT NULL DEFAULT 0,
    currency     TEXT NOT NULL DEFAULT 'LKR',
    frequency    TEXT NOT NULL DEFAULT 'one_time',
    is_taxable   INTEGER NOT NULL DEFAULT 1,
    tax_head     TEXT NOT NULL DEFAULT 'other',
    account_id   INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
    notes        TEXT DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budgets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id   INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    month       TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    amount      REAL NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS goals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id     INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    target_amount REAL NOT NULL DEFAULT 0,
    saved_amount  REAL NOT NULL DEFAULT 0,
    target_date   TEXT DEFAULT '',
    notes         TEXT DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tax_rules (
    year_label        TEXT PRIMARY KEY,
    label             TEXT NOT NULL DEFAULT '',
    personal_relief   REAL NOT NULL DEFAULT 0,
    slabs_json        TEXT NOT NULL DEFAULT '[]',
    rent_relief_pct   REAL NOT NULL DEFAULT 0,
    rent_relief_cap   REAL NOT NULL DEFAULT 0,
    wht_is_final      INTEGER NOT NULL DEFAULT 0,
    notes             TEXT DEFAULT '',
    updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tax_reliefs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id  INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    year_label TEXT NOT NULL,
    name       TEXT NOT NULL,
    amount     REAL NOT NULL DEFAULT 0,
    kind       TEXT NOT NULL DEFAULT 'qualifying',
    notes      TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tax_credits (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id  INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    year_label TEXT NOT NULL,
    name       TEXT NOT NULL,
    amount     REAL NOT NULL DEFAULT 0,
    kind       TEXT NOT NULL DEFAULT 'apit',
    notes      TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tax_profiles (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id  INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    year_label TEXT NOT NULL,
    notes      TEXT DEFAULT '',
    updated_at TEXT NOT NULL,
    UNIQUE(person_id, year_label)
);

CREATE TABLE IF NOT EXISTS net_worth_snapshots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id  INTEGER NOT NULL DEFAULT 0,
    date       TEXT NOT NULL,
    net_worth  REAL NOT NULL DEFAULT 0,
    assets     REAL NOT NULL DEFAULT 0,
    debts      REAL NOT NULL DEFAULT 0,
    cash       REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(person_id, date)
);

CREATE TABLE IF NOT EXISTS scheduled (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id      INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    amount         REAL NOT NULL DEFAULT 0,
    currency       TEXT NOT NULL DEFAULT 'LKR',
    type           TEXT NOT NULL DEFAULT 'expense',
    frequency      TEXT NOT NULL DEFAULT 'monthly',
    next_due_date  TEXT NOT NULL,
    end_date       TEXT DEFAULT '',
    account_id     INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
    card_id        INTEGER REFERENCES cards(id) ON DELETE SET NULL,
    category_id    INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    installments_left INTEGER NOT NULL DEFAULT 0,
    auto_post      INTEGER NOT NULL DEFAULT 0,
    is_active      INTEGER NOT NULL DEFAULT 1,
    last_paid_date TEXT DEFAULT '',
    notes          TEXT DEFAULT '',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tx_person_date ON transactions(person_id, date);
CREATE INDEX IF NOT EXISTS idx_tx_card_date ON transactions(card_id, date);
CREATE INDEX IF NOT EXISTS idx_tx_account_date ON transactions(account_id, date);
CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category_id);
CREATE INDEX IF NOT EXISTS idx_income_person_date ON incomes(person_id, date);
CREATE INDEX IF NOT EXISTS idx_cards_person ON cards(person_id);
CREATE INDEX IF NOT EXISTS idx_accounts_person ON accounts(person_id);
CREATE INDEX IF NOT EXISTS idx_assets_person ON assets(person_id);
CREATE INDEX IF NOT EXISTS idx_liabilities_person ON liabilities(person_id);
CREATE INDEX IF NOT EXISTS idx_loans_person ON loans(person_id);
CREATE INDEX IF NOT EXISTS idx_statements_card ON statements(card_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_person ON scheduled(person_id, next_due_date);
"""

DEFAULT_CATEGORIES = [
    # (name, kind, icon, color)
    ("Groceries", "expense", "🛒", "#10b981"),
    ("Dining", "expense", "🍽️", "#f59e0b"),
    ("Transport", "expense", "🚕", "#0ea5e9"),
    ("Fuel", "expense", "⛽", "#ef4444"),
    ("Utilities", "expense", "💡", "#eab308"),
    ("Rent", "expense", "🏠", "#8b5cf6"),
    ("Housing", "expense", "🔧", "#a855f7"),
    ("Insurance", "expense", "🛡️", "#06b6d4"),
    ("Healthcare", "expense", "🩺", "#f43f5e"),
    ("Education", "expense", "🎓", "#3b82f6"),
    ("Shopping", "expense", "🛍️", "#ec4899"),
    ("Entertainment", "expense", "🎬", "#d946ef"),
    ("Travel", "expense", "✈️", "#14b8a6"),
    ("Subscriptions", "expense", "🔁", "#6366f1"),
    ("Fees & Charges", "expense", "🏦", "#64748b"),
    ("Interest", "expense", "📈", "#dc2626"),
    ("Taxes", "expense", "🧾", "#78716c"),
    ("Business", "expense", "💼", "#0f766e"),
    ("Investments", "expense", "📊", "#22c55e"),
    ("Charity", "expense", "❤️", "#f97316"),
    ("Personal Care", "expense", "💅", "#fb7185"),
    ("Other", "expense", "•", "#94a3b8"),
    ("Salary", "income", "💵", "#10b981"),
    ("Business Income", "income", "💼", "#0f766e"),
    ("Freelance", "income", "🧑‍💻", "#06b6d4"),
    ("Rental Income", "income", "🏘️", "#8b5cf6"),
    ("Interest Income", "income", "🏦", "#0ea5e9"),
    ("Dividends", "income", "📈", "#22c55e"),
    ("Capital Gains", "income", "📊", "#84cc16"),
    ("Gift", "income", "🎁", "#f472b6"),
    ("Refund", "income", "↩️", "#a3e635"),
    ("Other Income", "income", "•", "#64748b"),
    ("Transfer", "transfer", "⇄", "#64748b"),
    ("Card Payment", "transfer", "💳", "#6366f1"),
    ("Loan Payment", "transfer", "🏦", "#f59e0b"),
]

DEFAULT_FX = [
    ("LKR", 1.0),
    ("USD", 300.0),
    ("EUR", 325.0),
    ("GBP", 385.0),
    ("INR", 3.6),
    ("AUD", 198.0),
    ("CAD", 220.0),
    ("AED", 82.0),
    ("SGD", 225.0),
    ("JPY", 2.0),
    ("CNY", 42.0),
]

DEFAULT_TAX_RULES = {
    "2024/25": {
        "label": "Sri Lanka Y/A 2024/25",
        "personal_relief": 1_200_000,
        "slabs": [
            {"upto": 1_200_000, "rate": 0.0},
            {"upto": 1_700_000, "rate": 0.06},
            {"upto": 2_200_000, "rate": 0.12},
            {"upto": 2_700_000, "rate": 0.18},
            {"upto": 3_200_000, "rate": 0.24},
            {"upto": 3_700_000, "rate": 0.30},
            {"upto": None, "rate": 0.36},
        ],
        "rent_relief_pct": 25.0,
        "rent_relief_cap": 600_000,
        "wht_is_final": 0,
        "notes": "Personal income tax slabs effective 1 April 2023. Edit if the Inland Revenue rules change.",
    },
    "2025/26": {
        "label": "Sri Lanka Y/A 2025/26",
        "personal_relief": 1_800_000,
        "slabs": [
            {"upto": 1_800_000, "rate": 0.0},
            {"upto": 2_800_000, "rate": 0.06},
            {"upto": 3_800_000, "rate": 0.18},
            {"upto": 4_800_000, "rate": 0.24},
            {"upto": 5_800_000, "rate": 0.30},
            {"upto": None, "rate": 0.36},
        ],
        "rent_relief_pct": 25.0,
        "rent_relief_cap": 600_000,
        "wht_is_final": 0,
        "notes": "Rates announced for Y/A 2025/26. Verify against your tax sheet and update if needed.",
    },
    "2026/27": {
        "label": "Sri Lanka Y/A 2026/27",
        "personal_relief": 1_800_000,
        "slabs": [
            {"upto": 1_800_000, "rate": 0.0},
            {"upto": 2_800_000, "rate": 0.06},
            {"upto": 3_800_000, "rate": 0.18},
            {"upto": 4_800_000, "rate": 0.24},
            {"upto": 5_800_000, "rate": 0.30},
            {"upto": None, "rate": 0.36},
        ],
        "rent_relief_pct": 25.0,
        "rent_relief_cap": 600_000,
        "wht_is_final": 0,
        "notes": "Placeholder copied from 2025/26. Update with the official 2026/27 rules.",
    },
}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def get_connection(path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # DELETE journal keeps the folder clean for cloud-sync (no -wal/-shm files).
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.execute("PRAGMA synchronous = FULL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


@contextmanager
def database(path: Path | str = DB_PATH) -> Iterator[sqlite3.Connection]:
    conn = get_connection(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def q(conn: sqlite3.Connection, sql: str, params: tuple | list = ()) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def q1(conn: sqlite3.Connection, sql: str, params: tuple | list = ()) -> dict | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def scalar(conn: sqlite3.Connection, sql: str, params: tuple | list = (), default: Any = 0) -> Any:
    row = conn.execute(sql, params).fetchone()
    if row is None or row[0] is None:
        return default
    return row[0]


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )


def all_settings(conn: sqlite3.Connection) -> dict[str, str]:
    return {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM settings")}


def init_db(path: Path | str = DB_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(path)
    try:
        conn.executescript(SCHEMA)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        _seed(conn)
        conn.commit()
    finally:
        conn.close()


def _seed(conn: sqlite3.Connection) -> None:
    if scalar(conn, "SELECT COUNT(*) FROM settings", default=0) == 0:
        settings = {
            "base_currency": BASE_CURRENCY,
            "api_key": secrets.token_urlsafe(32),
            "theme": "dark",
            "backup_interval_hours": "12",
            "last_backup_at": "",
            "onboarded": "0",
            "app_version": APP_VERSION,
            "fiscal_year_start_month": "4",
        }
        for key, value in settings.items():
            set_setting(conn, key, value)

    if scalar(conn, "SELECT COUNT(*) FROM categories", default=0) == 0:
        for index, (name, kind, icon, color) in enumerate(DEFAULT_CATEGORIES):
            conn.execute(
                "INSERT INTO categories(name, kind, icon, color, is_system, sort_order) VALUES(?,?,?,?,1,?)",
                (name, kind, icon, color, index),
            )

    if scalar(conn, "SELECT COUNT(*) FROM fx_rates", default=0) == 0:
        stamp = now_iso()
        for currency, rate in DEFAULT_FX:
            conn.execute(
                "INSERT INTO fx_rates(currency, rate, updated_at) VALUES(?,?,?)",
                (currency, rate, stamp),
            )

    if scalar(conn, "SELECT COUNT(*) FROM tax_rules", default=0) == 0:
        stamp = now_iso()
        for year_label, rule in DEFAULT_TAX_RULES.items():
            conn.execute(
                """INSERT INTO tax_rules(year_label, label, personal_relief, slabs_json,
                       rent_relief_pct, rent_relief_cap, wht_is_final, notes, updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    year_label,
                    rule["label"],
                    rule["personal_relief"],
                    json.dumps(rule["slabs"]),
                    rule["rent_relief_pct"],
                    rule["rent_relief_cap"],
                    rule["wht_is_final"],
                    rule["notes"],
                    stamp,
                ),
            )

    if scalar(conn, "SELECT COUNT(*) FROM persons", default=0) == 0:
        stamp = now_iso()
        conn.execute(
            """INSERT INTO persons(name, relationship, color, is_primary, sort_order, created_at, updated_at)
               VALUES(?,?,?,?,?,?,?)""",
            ("Me", "self", "#6366f1", 1, 0, stamp, stamp),
        )
        set_setting(conn, "default_person_id", "1")


def backup_database(path: Path | str = DB_PATH, dest_dir: Path | str = BACKUP_DIR,
                    reason: str = "auto", keep: int = 40) -> Path | None:
    """Create a consistent snapshot using SQLite's online backup API."""
    path = Path(path)
    if not path.exists():
        return None
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = dest_dir / f"FinVault-{reason}-{stamp}.db"
    source = sqlite3.connect(str(path))
    try:
        dest = sqlite3.connect(str(target))
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()

    # Prune only automatic backups, newest first.
    if keep > 0:
        autos = sorted(dest_dir.glob("FinVault-auto-*.db"), reverse=True)
        for old in autos[keep:]:
            try:
                old.unlink()
            except OSError:
                pass
    return target


def maybe_auto_backup(conn: sqlite3.Connection, path: Path | str = DB_PATH) -> Path | None:
    interval_hours = float(get_setting(conn, "backup_interval_hours", "12") or 12)
    last = get_setting(conn, "last_backup_at", "")
    if last:
        try:
            last_dt = datetime.fromisoformat(last)
            if datetime.now() - last_dt < timedelta(hours=interval_hours):
                return None
        except ValueError:
            pass
    target = backup_database(path, reason="auto")
    if target:
        set_setting(conn, "last_backup_at", now_iso())
        conn.commit()
    return target


def restore_backup(backup_file: Path, db_path: Path | str = DB_PATH) -> None:
    """Safely replace the live DB with a backup, keeping a pre-restore copy."""
    backup_file = Path(backup_file)
    db_path = Path(db_path)
    if not backup_file.exists():
        raise FileNotFoundError(str(backup_file))
    if db_path.exists():
        backup_database(db_path, reason="pre-restore")
    shutil.copy2(backup_file, db_path)


def integrity_check(path: Path | str = DB_PATH) -> str:
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()


def parse_json(value: str, default: Any = None) -> Any:
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default
