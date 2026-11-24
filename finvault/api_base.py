"""Shared API plumbing, validation helpers and core endpoints."""
from __future__ import annotations

import math
import re
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable

from .config import APP_NAME, APP_TAGLINE, APP_VERSION, IDLE_QUIT_DEFAULT_MINUTES
from .db import get_setting, now_iso, q, q1, scalar, set_setting

ROUTES: list[tuple[str, re.Pattern, Callable]] = []


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.field = field


class Raw:
    """A non-JSON response (file download)."""

    def __init__(self, body: bytes | str, content_type: str = "application/octet-stream",
                 status: int = 200, headers: dict | None = None):
        self.body = body.encode("utf-8") if isinstance(body, str) else body
        self.content_type = content_type
        self.status = status
        self.headers = headers or {}


@dataclass
class Ctx:
    conn: Any
    query: dict[str, str] = field(default_factory=dict)
    body: dict = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    method: str = "GET"
    path: str = ""
    server: Any = None


def route(method: str, path: str):
    regex = re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", path) + "$")

    def decorator(fn: Callable):
        ROUTES.append((method.upper(), regex, fn))
        return fn

    return decorator


def resolve(method: str, path: str):
    for route_method, regex, fn in ROUTES:
        if route_method != method.upper():
            continue
        match = regex.match(path)
        if match:
            return fn, match.groupdict()
    return None, None


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def clean_text(value: Any, max_len: int = 500) -> str:
    if value is None:
        return ""
    return str(value).strip()[:max_len]


def as_int(value: Any, field: str, required: bool = False, minimum: int | None = None,
           maximum: int | None = None, default: int | None = None) -> int | None:
    if value is None or value == "":
        if required:
            raise ApiError(f"{field} is required", field=field)
        return default
    try:
        number = int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        raise ApiError(f"{field} must be a whole number", field=field)
    if minimum is not None and number < minimum:
        raise ApiError(f"{field} must be at least {minimum}", field=field)
    if maximum is not None and number > maximum:
        raise ApiError(f"{field} must be at most {maximum}", field=field)
    return number


def as_float(value: Any, field: str, required: bool = False, minimum: float | None = None,
             default: float | None = None) -> float | None:
    if value is None or value == "":
        if required:
            raise ApiError(f"{field} is required", field=field)
        return default
    try:
        number = float(str(value).replace(",", "").replace("Rs", "").strip())
    except (TypeError, ValueError):
        raise ApiError(f"{field} must be a number", field=field)
    if math.isnan(number) or math.isinf(number):
        raise ApiError(f"{field} must be a valid number", field=field)
    if minimum is not None and number < minimum:
        raise ApiError(f"{field} must be at least {minimum}", field=field)
    return number


def as_bool(value: Any, default: bool = False) -> int:
    if value is None or value == "":
        return 1 if default else 0
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if value else 0
    return 1 if str(value).strip().lower() in {"1", "true", "yes", "y", "on"} else 0


def as_date(value: Any, field: str, required: bool = True, default: str | None = None) -> str:
    if value is None or value == "":
        if required:
            raise ApiError(f"{field} is required", field=field)
        return default or ""
    text = str(value).strip()[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
    except ValueError:
        raise ApiError(f"{field} must be a date (YYYY-MM-DD)", field=field)


def as_month(value: Any, field: str = "month") -> str:
    text = str(value or "").strip()[:7]
    try:
        return datetime.strptime(text, "%Y-%m").strftime("%Y-%m")
    except ValueError:
        return date.today().strftime("%Y-%m")


def as_choice(value: Any, field: str, choices: set[str], default: str) -> str:
    text = str(value or default).strip().lower()
    if text not in choices:
        raise ApiError(f"{field} must be one of: {', '.join(sorted(choices))}", field=field)
    return text


def body_dict(body: Any) -> dict:
    if body is None:
        return {}
    if not isinstance(body, dict):
        raise ApiError("Request body must be a JSON object")
    return body


def query_person(ctx: Ctx) -> int | None:
    raw = ctx.query.get("person_id") or ""
    if raw in ("", "all", "0", "null", "None"):
        return None
    return as_int(raw, "person_id", minimum=1)


def ensure_person(conn, person_id: int) -> dict:
    person = q1(conn, "SELECT * FROM persons WHERE id = ?", (person_id,))
    if not person:
        raise ApiError("Person not found", 404, "person_id")
    return person


def ensure_card(conn, card_id: int) -> dict:
    card = q1(conn, "SELECT * FROM cards WHERE id = ?", (card_id,))
    if not card:
        raise ApiError("Card not found", 404, "card_id")
    return card


def ensure_account(conn, account_id: int) -> dict:
    account = q1(conn, "SELECT * FROM accounts WHERE id = ?", (account_id,))
    if not account:
        raise ApiError("Account not found", 404, "account_id")
    return account


def ensure_category(conn, category_id: int | None) -> dict | None:
    if not category_id:
        return None
    category = q1(conn, "SELECT * FROM categories WHERE id = ?", (category_id,))
    if not category:
        raise ApiError("Category not found", 404, "category_id")
    return category


def update_row(conn, table: str, row_id: int, body: dict, allowed: set[str],
               required: set[str] | None = None) -> None:
    sets = ["updated_at = ?"]
    values: list[Any] = [now_iso()]
    for key in allowed:
        if key in body:
            sets.append(f"{key} = ?")
            values.append(body[key])
    if required:
        for key in required:
            if key in body and (body[key] is None or body[key] == ""):
                raise ApiError(f"{key} cannot be empty", field=key)
    values.append(row_id)
    conn.execute(f"UPDATE {table} SET {', '.join(sets)} WHERE id = ?", values)


# ---------------------------------------------------------------------------
# Bootstrap and settings
# ---------------------------------------------------------------------------

@route("GET", "/api/health")
def health(ctx: Ctx):
    return {
        "app": "finvault",
        "name": APP_NAME,
        "version": APP_VERSION,
        "ok": True,
        "database": str(ctx.conn.execute("PRAGMA database_list").fetchone()[2]),
        "time": now_iso(),
    }


@route("GET", "/api/v1/bootstrap")
def bootstrap(ctx: Ctx):
    persons = q(ctx.conn, "SELECT * FROM persons ORDER BY sort_order, id")
    categories = q(ctx.conn, "SELECT * FROM categories ORDER BY kind, sort_order, name")
    fx = q(ctx.conn, "SELECT * FROM fx_rates ORDER BY currency")
    settings = {
        "base_currency": get_setting(ctx.conn, "base_currency", "LKR"),
        "theme": get_setting(ctx.conn, "theme", "dark"),
        "onboarded": get_setting(ctx.conn, "onboarded", "0"),
        "backup_interval_hours": get_setting(ctx.conn, "backup_interval_hours", "12"),
        "default_person_id": get_setting(ctx.conn, "default_person_id", ""),
        "fiscal_year_start_month": get_setting(ctx.conn, "fiscal_year_start_month", "4"),
        "idle_quit_minutes": get_setting(
            ctx.conn, "idle_quit_minutes", str(IDLE_QUIT_DEFAULT_MINUTES)
        ),
        "api_key": get_setting(ctx.conn, "api_key", ""),
    }
    counts = {
        "cards": scalar(ctx.conn, "SELECT COUNT(*) FROM cards"),
        "accounts": scalar(ctx.conn, "SELECT COUNT(*) FROM accounts"),
        "transactions": scalar(ctx.conn, "SELECT COUNT(*) FROM transactions"),
        "incomes": scalar(ctx.conn, "SELECT COUNT(*) FROM incomes"),
        "assets": scalar(ctx.conn, "SELECT COUNT(*) FROM assets"),
        "liabilities": scalar(ctx.conn, "SELECT COUNT(*) FROM liabilities"),
        "loans": scalar(ctx.conn, "SELECT COUNT(*) FROM loans"),
    }
    return {
        "app": {"name": APP_NAME, "tagline": APP_TAGLINE, "version": APP_VERSION},
        "persons": persons,
        "categories": categories,
        "fx": fx,
        "settings": settings,
        "counts": counts,
        "today": date.today().isoformat(),
    }


@route("GET", "/api/v1/settings")
def get_settings(ctx: Ctx):
    rows = q(ctx.conn, "SELECT key, value FROM settings ORDER BY key")
    return {"settings": {row["key"]: row["value"] for row in rows}}


@route("PUT", "/api/v1/settings")
def put_settings(ctx: Ctx):
    allowed = {"base_currency", "theme", "backup_interval_hours", "onboarded",
               "fiscal_year_start_month", "default_person_id", "idle_quit_minutes"}
    body = body_dict(ctx.body)
    payload = body.get("settings", body)
    if not isinstance(payload, dict):
        raise ApiError("settings must be an object", field="settings")
    changed = {}
    for key, value in payload.items():
        if key not in allowed:
            continue
        if key == "idle_quit_minutes":
            try:
                minutes = int(str(value).strip())
            except (TypeError, ValueError):
                raise ApiError(
                    "idle_quit_minutes must be a whole number of minutes",
                    field=key,
                )
            if minutes < 0 or minutes > 1440:
                raise ApiError(
                    "idle_quit_minutes must be between 0 and 1440 minutes",
                    field=key,
                )
            value = minutes
        set_setting(ctx.conn, key, str(value))
        changed[key] = str(value)
    return {"updated": changed}


@route("POST", "/api/v1/settings/rotate-key")
def rotate_key(ctx: Ctx):
    key = secrets.token_urlsafe(32)
    set_setting(ctx.conn, "api_key", key)
    return {"api_key": key}


@route("GET", "/api/v1/fx")
def fx_list(ctx: Ctx):
    return q(ctx.conn, "SELECT * FROM fx_rates ORDER BY currency")


@route("PUT", "/api/v1/fx")
def fx_update(ctx: Ctx):
    body = body_dict(ctx.body)
    rates = body.get("rates", body)
    if not isinstance(rates, dict):
        raise ApiError("rates must be an object", field="rates")
    stamp = now_iso()
    for currency, rate in rates.items():
        code = clean_text(currency, 8).upper()
        value = as_float(rate, f"rate for {code}", required=True, minimum=0.000001)
        ctx.conn.execute(
            """INSERT INTO fx_rates(currency, rate, updated_at) VALUES(?,?,?)
               ON CONFLICT(currency) DO UPDATE SET rate = excluded.rate, updated_at = excluded.updated_at""",
            (code, value, stamp),
        )
    return q(ctx.conn, "SELECT * FROM fx_rates ORDER BY currency")


# ---------------------------------------------------------------------------
# Persons
# ---------------------------------------------------------------------------

@route("GET", "/api/v1/persons")
def persons_list(ctx: Ctx):
    persons = q(ctx.conn, "SELECT * FROM persons ORDER BY sort_order, id")
    for person in persons:
        person["card_count"] = scalar(ctx.conn, "SELECT COUNT(*) FROM cards WHERE person_id = ?", (person["id"],))
        person["account_count"] = scalar(ctx.conn, "SELECT COUNT(*) FROM accounts WHERE person_id = ?", (person["id"],))
    return persons


@route("POST", "/api/v1/persons")
def persons_create(ctx: Ctx):
    body = body_dict(ctx.body)
    name = clean_text(body.get("name"), 80)
    if not name:
        raise ApiError("Name is required", field="name")
    stamp = now_iso()
    is_primary = as_bool(body.get("is_primary"), False)
    if is_primary:
        ctx.conn.execute("UPDATE persons SET is_primary = 0")
    sort_order = as_int(body.get("sort_order"), "sort_order", default=0)
    cur = ctx.conn.execute(
        """INSERT INTO persons(name, relationship, color, email, phone, tin, date_of_birth,
               is_primary, sort_order, created_at, updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (name, clean_text(body.get("relationship"), 40), clean_text(body.get("color"), 20) or "#6366f1",
         clean_text(body.get("email"), 120), clean_text(body.get("phone"), 40),
         clean_text(body.get("tin"), 40), as_date(body.get("date_of_birth"), "date_of_birth", False),
         is_primary, sort_order, stamp, stamp),
    )
    if scalar(ctx.conn, "SELECT COUNT(*) FROM persons") == 1:
        set_setting(ctx.conn, "default_person_id", str(cur.lastrowid))
    return q1(ctx.conn, "SELECT * FROM persons WHERE id = ?", (cur.lastrowid,))


@route("PUT", "/api/v1/persons/{id}")
def persons_update(ctx: Ctx):
    person_id = as_int(ctx.params["id"], "id", required=True)
    ensure_person(ctx.conn, person_id)
    body = body_dict(ctx.body)
    if "name" in body:
        body["name"] = clean_text(body["name"], 80)
        if not body["name"]:
            raise ApiError("Name cannot be empty", field="name")
    if as_bool(body.get("is_primary"), False):
        ctx.conn.execute("UPDATE persons SET is_primary = 0")
        body["is_primary"] = 1
    if "date_of_birth" in body:
        body["date_of_birth"] = as_date(body["date_of_birth"], "date_of_birth", False)
    update_row(ctx.conn, "persons", person_id, body,
               {"name", "relationship", "color", "email", "phone", "tin", "date_of_birth",
                "is_primary", "sort_order"})
    return q1(ctx.conn, "SELECT * FROM persons WHERE id = ?", (person_id,))


@route("DELETE", "/api/v1/persons/{id}")
def persons_delete(ctx: Ctx):
    person_id = as_int(ctx.params["id"], "id", required=True)
    ensure_person(ctx.conn, person_id)
    remaining = scalar(ctx.conn, "SELECT COUNT(*) FROM persons")
    if remaining <= 1:
        raise ApiError("You need at least one person. Create another person first.", 409)
    ctx.conn.execute("DELETE FROM persons WHERE id = ?", (person_id,))
    if get_setting(ctx.conn, "default_person_id") == str(person_id):
        first = q1(ctx.conn, "SELECT id FROM persons ORDER BY sort_order, id LIMIT 1")
        set_setting(ctx.conn, "default_person_id", str(first["id"]) if first else "")
    return {"deleted": person_id}


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

@route("GET", "/api/v1/categories")
def categories_list(ctx: Ctx):
    return q(ctx.conn, "SELECT * FROM categories ORDER BY kind, sort_order, name")


@route("POST", "/api/v1/categories")
def categories_create(ctx: Ctx):
    body = body_dict(ctx.body)
    name = clean_text(body.get("name"), 60)
    if not name:
        raise ApiError("Name is required", field="name")
    kind = as_choice(body.get("kind"), "kind", {"expense", "income", "transfer"}, "expense")
    cur = ctx.conn.execute(
        """INSERT INTO categories(name, kind, icon, color, is_system, sort_order)
           VALUES(?,?,?,?,0,?)""",
        (name, kind, clean_text(body.get("icon"), 8) or "•", clean_text(body.get("color"), 20) or "#64748b",
         as_int(body.get("sort_order"), "sort_order", default=100)),
    )
    return q1(ctx.conn, "SELECT * FROM categories WHERE id = ?", (cur.lastrowid,))


@route("PUT", "/api/v1/categories/{id}")
def categories_update(ctx: Ctx):
    category_id = as_int(ctx.params["id"], "id", required=True)
    if not q1(ctx.conn, "SELECT id FROM categories WHERE id = ?", (category_id,)):
        raise ApiError("Category not found", 404)
    body = body_dict(ctx.body)
    if "kind" in body:
        body["kind"] = as_choice(body["kind"], "kind", {"expense", "income", "transfer"}, "expense")
    update_row(ctx.conn, "categories", category_id, body, {"name", "kind", "icon", "color", "sort_order"})
    return q1(ctx.conn, "SELECT * FROM categories WHERE id = ?", (category_id,))


@route("DELETE", "/api/v1/categories/{id}")
def categories_delete(ctx: Ctx):
    category_id = as_int(ctx.params["id"], "id", required=True)
    row = q1(ctx.conn, "SELECT * FROM categories WHERE id = ?", (category_id,))
    if not row:
        raise ApiError("Category not found", 404)
    if row["is_system"] and not as_bool(ctx.query.get("force")):
        raise ApiError("Built-in categories cannot be deleted. You can rename them instead.", 409)
    used = scalar(ctx.conn, "SELECT COUNT(*) FROM transactions WHERE category_id = ?", (category_id,))
    if used and not as_bool(ctx.query.get("force")):
        raise ApiError(f"This category is used by {used} transaction(s). Set force=1 to delete anyway.", 409)
    ctx.conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    return {"deleted": category_id}
