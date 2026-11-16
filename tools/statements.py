"""Parse FinVault statement PDFs into normalised JSON.

Extraction is done by pypdf (text layer); this module turns each bank's text into
a common shape:

    {
      "bank": "combank", "card_last4": "8588", "statement_date": "2026-11-10",
      "period_start": ..., "period_end": ..., "opening": ..., "closing": ...,
      "minimum_due": ..., "due_date": ..., "credit_limit": ...,
      "transactions": [{"date","description","amount","direction","type",
                        "category","currency","foreign_amount","notes"}],
      "checks": [...]
    }

Run `python tools/statements.py --report` to parse every PDF and reconcile it.
"""
from __future__ import annotations

import calendar
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from pypdf import PdfReader

INBOX = Path("statements/inbox")

MONEY = r"[\d,]+\.\d{2}"
MONEY_SIGNED = r"-?[\d,]+\.\d{2}"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def read_text(path: Path) -> str:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            pass
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def num(value: str) -> float:
    return float(value.replace(",", "").replace(" ", ""))


def add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------
CATEGORY_RULES = [
    ("Business", ["ALIBABA", "ALIEXPRESS", "DARAZ", "JLCPCB", "VYAPAR", "SWISSFLOW",
                  "FRIMI", "PAYHERE", "MOONSHOT", "JAT HOLDINGS", "GREEN ELECTRIC",
                  "SOVIS LANKA", "LANKA QR MERCHANT", "SHOPIFY", "WOOCOMMERCE"]),
    ("Groceries", ["KEELLS", "CARGILLS", "SPAR", "ARPICO", "GLOMARK", "LAUGFS",
                   "SUPERMARKET", "SUPER CENTRE", "SUPER CENTER", "FOOD CITY", "LANKA SATHOSA",
                   "SATHOSA", "RICHARD STORES", "SAMPATH SUPER", "RANGAMA STORES",
                   "CO-OPERA", "COOP", "MULTI PURPOSE"]),
    ("Dining", ["KFC", "PIZZA", "BURGER", "MCDONALD", "DOMINO", "BARISTA", "COFFEE", "CAFE",
                "RESTAURANT", "REST", "BAKERS", "BAKERY", "FOOD", "HOTEL", "DOSAI", "RICE",
                "CURRY", "STARBUCKS", "SUBWAY", "NOODLE", "DINEMORE", "EAT", "KITCHEN",
                "KOTTU", "TACO", "INDIAN HUT", "ICE CREAM", "SWEET", "MANGOS", "SAYURA",
                "REBEL CHEF", "BING CHUN", "JAYAKIRANA", "RASA VIM", "RANSIRI", "HUT"]),
    ("Fuel", ["FILLING STAT", "FILLING STATION", "FILLIN", "FUEL", "PETROL", "DIESEL",
              "CEYPETCO", "IOC", "SHELL", "SINOPEC", "SERVICE CENTE"]),
    ("Transport", ["UBER", "PICKME", "PICK ME", "TAXI", "THREE WHEELER", "TUK", "BUS",
                   "RAILWAY", "TRAIN", "HIGHWAY", "EXPRESSWAY", "PARKING", "AUTO LIFE",
                   "BRILLIANCE AUTO", "MOTOR", "INTERCHANGE", "DIMO", "TYRE", "DMT-"]),
    ("Healthcare", ["PHARMACY", "HOSPITAL", "MEDICAL", "CLINIC", "LAB", "DENTAL", "OPTICAL",
                    "HEALTH", "SUWAPIYASA", "SUWA PIYASA", "CHEMIST", "NAWALOKA", "ASIRI",
                    "LANKA HOSPITAL", "LANKA HOSPITALS", "UNION CHEMIST", "OSU", "CHANNEL",
                    "ECHANNELLING"]),
    ("Utilities", ["CEB", "ELECTRICITY", "WATER BOARD", "NWSDB", "DIALOG", "MOBITEL",
                   "SLT", "HUTCH", "AIRTEL", "SRI LANKA TELECOM", "BROADBAND", "GAS",
                   "LITRO", "LAUGFS GAS", "INTERNET", "STARLINK"]),
    ("Subscriptions", ["NETFLIX", "SPOTIFY", "YOUTUBE", "GOOGLE", "APPLE", "MICROSOFT",
                       "ADOBE", "CANVA", "CHATGPT", "OPENAI", "ANTHROPIC", "CLAUDE",
                       "GITHUB", "DROPBOX", "ICLOUD", "DISNEY", "AMAZON PRIME",
                       "HOSTINGER", "NAMECHEAP", "GODADDY", "VERCEL", "NOTION",
                       "METAQUOTES", "MQL5", "ENVATO"]),
    ("Education", ["SCHOOL", "COLLEGE", "UNIVERSITY", "TUITION", "ACADEMY", "INSTITUTE",
                   "BOOK", "STATIONERY", "UDEMY", "COURSERA", "INSTITUTION"]),
    ("Shopping", ["FASHION", "CLOTHING", "SHIRT", "SAREE", "SHOE", "NIKE", "ADIDAS",
                  "DAMRO", "ODEL", "NO LIMIT", "COOL PLANET", "SINGER", "ABANS",
                  "SOFTLOGIC", "SAMSUNG", "LG ", "DIGITAL", "MOBILE", "PHONE", "LAPTOP",
                  "ELECTRONIC", "ELECTRIC", "DRESS", "TEXTIL", "MEGA SALE", "STORE",
                  "GARMENT", "DILSARD", "VN PRODUCTS", "IKMAN", "COMPUTER", "TECHNOLOG"]),
    ("Entertainment", ["CINEMA", "MOVIE", "SAVI", "PVR", "NET CAFE", "GAME", "TICKET",
                       "EVENT", "CONCERT"]),
    ("Travel", ["AIRLINE", "AIRWAYS", "SRI LANKAN", "EMIRATES", "QATAR AIR", "BOOKING.COM",
                "AGODA", "AIRBNB", "RESORT", "TRAVEL", "VISA FEE", "IMMIGRATION",
                "AIRPORT"]),
    ("Insurance", ["INSURANCE", "ASSURANCE", "ALLIANZ", "CEYLINCO", "SOFTLOGIC LIFE",
                   "AIA", "SANASA", "UNION ASSURANCE"]),
    ("Personal Care", ["SALON", "BARBER", "SPA", "COSMETIC", "BEAUTY", "HAIR"]),
    ("Fees & Charges", ["STAMP DUTY", "SMS ALERT", "SMS CHARGE", "CARD REPLACEMENT",
                        "ANNUAL FEE", "SERVICE CHARGE", "LATE PAYMENT", "OVER LIMIT",
                        "CHARGES", "FEE", "DUTY"]),
    ("Interest", ["INTEREST"]),
    ("Charity", ["DONATION", "CHARITY", "TEMPLE", "CHURCH", "RED CROSS"]),
    ("Rent", ["RENT"]),
]

TYPE_RULES = [
    ("payment", ["PAYMENT RECEIVED", "CEFT PAYMENT", "INTERNET BANKING TRANSACTION",
                 "PAYMENT - THANK YOU", "PAYMENT THANK YOU", "CASH PAYMENT",
                 "PAYMENT FROM", "THANK YOU"]),
    ("interest", ["INTEREST CHARGE", "INTEREST CHARGES", "RETAIL INTEREST", "FINANCE CHARGE",
                  "DEBIT INTEREST"]),
    ("fee", ["STAMP DUTY", "SMS ALERT", "SMS CHARGE", "CARD REPLACEMENT", "ANNUAL FEE",
             "SERVICE CHARGE", "LATE PAYMENT FEE", "OVERLIMIT FEE", "CHARGES", "RENEWAL FEE"]),
    ("cash_advance", ["CASH ADVANCE", "ATM WITHDRAWAL"]),
]

# Leading statement words that carry no merchant information.
LEADING_NOISE = re.compile(
    r"^(PURCHASE|PURCHASES|INSTAL+MENT|PAYMENT|RETURN PURCHASE|DEBIT|CREDIT|RENEWAL FEE|"
    r"STAMP DUTY|DEBIT ADJUSTMNT|PAYMENT-BAL XFR)\s+", re.I)


def merchant_text(description: str) -> str:
    text = LEADING_NOISE.sub("", description.strip())
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def classify_type(description: str, direction: str) -> str:
    upper = description.upper()
    if "SINGER FINANCE" in upper:
        return "loan_payment"
    if "LAST STATEMENT BALANCE" in upper or "UNBILLED BALANCE" in upper:
        return "adjustment"
    if "BALANCE TRANSFER" in upper and direction == "out":
        return "adjustment"
    if direction == "in" and re.search(r"\bCONVERT\b|\bBAL XFR\b|BALANCE TRANSFER", upper):
        return "refund"
    if upper.startswith("PAYMENT") and not upper.startswith("PAYMENT-BAL"):
        return "payment"
    for txn_type, keys in TYPE_RULES:
        if any(k in upper for k in keys):
            return txn_type
    if "INTEREST" in upper and "INTEREST FREE" not in upper and "NO INTEREST" not in upper:
        return "interest"
    if re.search(r"\b(REFUND|RETURN|REVERSAL|CASH BACK|CRDIT|CREDIT ADJUST)\b", upper):
        return "refund"
    if re.search(r"\b(INSTAL+MENT|FLEXIPLAN|EASY PAYMENT PLAN|EQUAL PAYMENT)\b", upper):
        return "installment"
    return "purchase" if direction == "out" else "refund"


def classify_category(description: str, txn_type: str) -> str:
    if txn_type == "payment" or txn_type == "loan_payment":
        return "Card Payment"
    if txn_type == "refund":
        return "Refund"
    if txn_type == "interest":
        return "Interest"
    if txn_type == "fee":
        return "Fees & Charges"
    if txn_type == "adjustment":
        return "Other"
    if txn_type == "installment":
        upper = description.upper()
        if "FLEXIPLAN INS" in upper:
            return "Insurance"
        if "FLEXIPLAN ELE" in upper:
            return "Shopping"
        if "OVERSEAS" in upper:
            return "Travel"
        return "Other"
    upper = merchant_text(description).upper()
    for category, keys in CATEGORY_RULES:
        if any(k in upper for k in keys):
            return category
    return "Other"


def make_txn(raw_date: date, description: str, amount: float, direction: str,
             currency: str = "LKR", foreign_amount: float | None = None,
             note: str = "") -> dict:
    txn_type = classify_type(description, direction)
    return {
        "date": raw_date.isoformat(),
        "description": squash(description),
        "amount": round(amount, 2),
        "direction": direction,
        "type": txn_type,
        "category": classify_category(description, txn_type),
        "currency": currency,
        "foreign_amount": foreign_amount,
        "notes": note,
    }


def signed(txn: dict) -> float:
    return -txn["amount"] if txn["direction"] == "in" else txn["amount"]


# ---------------------------------------------------------------------------
# ComBank
# ---------------------------------------------------------------------------
COMBANK_ROW = re.compile(
    r"^(?P<post>\d{2}/\d{2})\s+(?P<txn>\d{2}/\d{2})\s+(?P<rest>.+?)\s+(?P<amount>" + MONEY + r")(?P<cr>\s+CR)?$"
)
COMBANK_SUBTOTAL = re.compile(
    r"\*\*\s*CARD\s*-\s*(?P<card>\d{8}\*{4}\d{4})\s+SUBTOTAL-?\s+(?P<amount>[\d,]+\.\d{2})(?P<cr>\s+CR)?"
)


def parse_combank(path: Path) -> dict:
    text = read_text(path)
    lines = [ln.rstrip() for ln in text.splitlines()]

    opening = None
    for ln in lines:
        m = re.search(r"OPENING BALANCE\s+(" + MONEY + r")", ln)
        if m:
            opening = num(m.group(1))
            break

    statement_date = due_date = None
    card_last4 = None
    credit_limit = None
    minimum_due = None
    for i, ln in enumerate(lines):
        m = re.match(r"^(\d{4}) (\d{4}) \*{4} (\d{4})\s*$", ln.strip())
        if m and card_last4 is None:
            card_last4 = m.group(3)
            credit_limit = num(lines[i - 14]) if i >= 14 else None
            if i + 1 < len(lines) and re.match(r"^\d{2}/\d{2}/\d{2}$", lines[i + 1].strip()):
                statement_date = datetime.strptime(lines[i + 1].strip(), "%d/%m/%y").date()
                due_date = datetime.strptime(lines[i + 2].strip(), "%d/%m/%y").date()
                minimum_due = num(lines[i + 3].strip())
            break

    if statement_date is None:
        raise ValueError("could not find statement date")

    year = statement_date.year
    transactions: list[dict] = []
    pending: list[dict] = []
    subtotals: list[tuple[str, float]] = []
    section_rows: list[float] = []
    section_total = 0.0

    for ln in lines:
        sub = COMBANK_SUBTOTAL.search(ln)
        if sub:
            value = num(sub.group("amount"))
            if sub.group("cr"):
                value = -value
            subtotals.append((sub.group("card"), value))
            if abs(section_total - value) > 0.02:
                raise ValueError(
                    f"subtotal mismatch for {sub.group('card')}: rows {section_total:.2f} vs {value:.2f}")
            section_rows.append(section_total)
            section_card = sub.group("card")[-4:]
            for txn in pending:
                txn["section_card"] = section_card
                if section_card != card_last4:
                    txn["notes"] = f"Supplementary card ending {section_card}"
            transactions.extend(pending)
            pending = []
            section_total = 0.0
            continue
        row = COMBANK_ROW.match(ln.strip())
        if not row:
            continue
        post = row.group("post")
        day, month = (int(x) for x in post.split("/"))
        txn_year = year if month <= statement_date.month else year - 1
        txn_date = date(txn_year, month, day)
        body = row.group("rest")
        currency = "LKR"
        foreign = None
        curm = re.match(r"^(?P<desc>.*?)\s{2,}(?P<cur>LK|US\$|USD|EUR|GBP|AUD|SGD|JPY|INR|CAD)\s*$", body)
        if curm:
            body = curm.group("desc")
            currency = "LKR" if curm.group("cur") == "LK" else curm.group("cur").replace("$", "")
        amount = num(row.group("amount"))
        direction = "in" if row.group("cr") else "out"
        txn = make_txn(txn_date, body, amount, direction, currency, foreign)
        pending.append(txn)
        section_total += signed(txn)

    if abs(section_total - 0.0) > 0.02:
        raise ValueError(f"trailing rows not closed by a subtotal: {section_total:.2f}")

    net = sum(signed(t) for t in transactions)
    closing = round(opening + net, 2)
    return {
        "bank": "combank",
        "file": path.name,
        "card_last4": card_last4,
        "statement_date": statement_date.isoformat(),
        "period_start": add_months(statement_date, -1).isoformat(),
        "period_end": statement_date.isoformat(),
        "opening": opening,
        "closing": closing,
        "minimum_due": minimum_due or 0.0,
        "due_date": due_date.isoformat() if due_date else "",
        "credit_limit": credit_limit,
        "transactions": transactions,
        "checks": {
            "row_net": round(net, 2),
            "subtotal_sum": round(sum(v for _, v in subtotals), 2),
            "sections": len(subtotals),
        },
    }


# ---------------------------------------------------------------------------
# Nations Trust Bank
# ---------------------------------------------------------------------------
NTB_ROW = re.compile(
    r"^(?P<post>\d{2} [A-Z]{3})\s+(?P<txn>\d{2} [A-Z]{3})\s+(?P<desc>.+?)\s+"
    r"(?P<cur>LKR|USD|EUR|GBP|AUD|SGD|JPY|INR|CAD)\s+(?P<amt>" + MONEY + r")\s+"
    r"(?P<lkr>" + MONEY + r")\s+(?P<dr>Dr|Cr)$"
)
NTB_SUMMARY = re.compile(
    r"^(?P<open>" + MONEY + r")\s+(?P<purch>" + MONEY + r")\s+(?P<cash>" + MONEY + r")\s+"
    r"(?P<int>" + MONEY + r")\s+(?P<chg>" + MONEY + r")\s+(?P<pay>" + MONEY + r")\s+"
    r"(?P<other>" + MONEY + r")\s+(?P<close>" + MONEY + r")\s*$"
)


def parse_ntb(path: Path) -> dict:
    text = read_text(path)
    lines = [ln.strip() for ln in text.splitlines()]

    period = re.search(r"Statement Period:\s*(\d{2}-\w{3}-\d{4})\s*to\s*(\d{2}-\w{3}-\d{4})", text)
    card = re.search(r"Card No:\s*(\d{6})\*{6}(\d{4})", text)
    limit = re.search(r"Credit Limit\s*\n(?:.*\n)*?(" + MONEY + r")", text)
    min_due = re.search(r"Minimum Payment Due\s*\n(?:.*\n)*?(" + MONEY + r")", text)
    total_due = re.search(r"Total Outstanding Due\s*\n(?:.*\n)*?(" + MONEY + r")", text)
    due = re.search(r"Payment Due Date\s*\n(?:.*\n)*?(\d{2}-\w{3}-\d{4})", text)
    summary = next((NTB_SUMMARY.match(ln) for ln in lines if NTB_SUMMARY.match(ln)), None)
    if not (period and card and summary):
        raise ValueError("could not find statement header")

    opening = num(summary.group("open"))
    closing = num(summary.group("close"))
    period_start = datetime.strptime(period.group(1), "%d-%b-%Y").date()
    period_end = datetime.strptime(period.group(2), "%d-%b-%Y").date()

    transactions = []
    for ln in lines:
        m = NTB_ROW.match(ln)
        if not m:
            continue
        txn_date = datetime.strptime(m.group("txn"), "%d %b %Y").date() if False else None
        # dates carry no year in the row; borrow it from the statement period
        day, mon = m.group("post").split()
        year = period_end.year if datetime.strptime(mon, "%b").month <= period_end.month else period_end.year - 1
        d = date(year, datetime.strptime(mon, "%b").month, int(day))
        if d > period_end:
            d = date(year - 1, d.month, d.day)
        lkr = num(m.group("lkr"))
        direction = "in" if m.group("dr") == "Cr" else "out"
        note = ""
        if m.group("cur") != "LKR":
            note = f"{m.group('cur')} {num(m.group('amt')):,.2f}"
        transactions.append(make_txn(d, m.group("desc"), lkr, direction, m.group("cur"), num(m.group("amt")), note))

    net = round(sum(signed(t) for t in transactions), 2)
    expected = round(
        num(summary.group("purch")) + num(summary.group("cash")) + num(summary.group("int"))
        + num(summary.group("chg")) - num(summary.group("pay")) - num(summary.group("other")), 2)
    return {
        "bank": "ntb",
        "file": path.name,
        "card_last4": card.group(2),
        "statement_date": period_end.isoformat(),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "opening": opening,
        "closing": closing,
        "minimum_due": num(min_due.group(1)) if min_due else 0.0,
        "due_date": datetime.strptime(due.group(1), "%d-%b-%Y").date().isoformat() if due else "",
        "credit_limit": num(limit.group(1)) if limit else None,
        "total_due": num(total_due.group(1)) if total_due else closing,
        "transactions": transactions,
        "checks": {"row_net": net, "summary_net": expected, "summary_closes": round(opening + net, 2)},
    }


# ---------------------------------------------------------------------------
# Seylan
# ---------------------------------------------------------------------------
SEYLAN_SUMMARY = re.compile(
    r"LKR (?P<close>" + MONEY_SIGNED + r")\s+(?P<due>\d{4}/\d{2}/\d{2})\s+LKR (?P<min>" + MONEY_SIGNED + r")\s+"
    r"LKR (?P<open>" + MONEY_SIGNED + r")\s+LKR (?P<credit>" + MONEY_SIGNED + r")\s+LKR (?P<debit>" + MONEY_SIGNED + r")"
    r"\s+LKR (?P<fee>" + MONEY_SIGNED + r")"
)
SEYLAN_ROW = re.compile(
    r"^(?P<date>\d{4}/\d{2}/\d{2})\s+(?P<rest>.+?)\s+LKR (?P<amt>" + MONEY + r")\s*$"
)
SEYLAN_CREDIT_PREFIX = re.compile(r"^(PAYMENT\b|PAYMENT-BAL|RETURN PURCHASE|REFUND|REVERSAL)")


def parse_seylan(path: Path, debit_total: float | None = None, credit_total: float | None = None) -> dict:
    text = read_text(path)
    lines = [ln.strip() for ln in text.splitlines()]

    summary = SEYLAN_SUMMARY.search(text)
    card = re.search(r"Card Number:\s*(\d{6})[x*]{6}(\d{4})", text)
    asof = re.search(r"as of (\d{4}/\d{2}/\d{2})", text)
    if not (summary and card and asof):
        raise ValueError("could not find statement header")

    statement_date = datetime.strptime(asof.group(1), "%Y/%m/%d").date()
    opening = num(summary.group("open"))
    closing = num(summary.group("close"))
    total_debit = num(summary.group("debit"))
    total_credit = num(summary.group("credit"))

    transactions = []
    for ln in lines:
        m = SEYLAN_ROW.match(ln)
        if not m:
            continue
        d = datetime.strptime(m.group("date"), "%Y/%m/%d").date()
        rest = m.group("rest")
        amount = num(m.group("amt"))
        direction = "in" if SEYLAN_CREDIT_PREFIX.match(rest.upper()) else "out"
        transactions.append(make_txn(d, rest, amount, direction))

    debit_sum = round(sum(t["amount"] for t in transactions if t["direction"] == "out"), 2)
    credit_sum = round(sum(t["amount"] for t in transactions if t["direction"] == "in"), 2)
    finance = round(sum(t["amount"] for t in transactions
                        if t["direction"] == "out" and t["type"] == "interest"), 2)
    fees = round(sum(t["amount"] for t in transactions
                     if t["direction"] == "out" and t["type"] == "fee"), 2)
    return {
        "bank": "seylan",
        "file": path.name,
        "card_last4": card.group(2),
        "statement_date": statement_date.isoformat(),
        "period_start": add_months(statement_date, -1).isoformat(),
        "period_end": statement_date.isoformat(),
        "opening": opening,
        "closing": closing,
        "minimum_due": num(summary.group("min")),
        "due_date": datetime.strptime(summary.group("due"), "%Y/%m/%d").date().isoformat(),
        "credit_limit": None,
        "transactions": transactions,
        "checks": {
            "debit_sum": debit_sum, "debit_statement": total_debit,
            "credit_sum": credit_sum, "credit_statement": total_credit,
            "finance_charges": finance, "fees": fees,
            "closes": round(opening + debit_sum - credit_sum, 2),
        },
    }


# ---------------------------------------------------------------------------
# Union Bank
# ---------------------------------------------------------------------------
UNION_ROW = re.compile(
    r"^(?P<no>\d+)\s+(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<time>\d{2}:\d{2})\s*$"
)
UNION_AMOUNTS = re.compile(
    r"^(?P<credit>[\d,\.\-]+)\s+(?P<debit>[\d,\.\-]+)\s+N/A(?P<balance>[\d,\.\-]+)$"
)


def parse_union(path: Path) -> dict:
    text = read_text(path)
    lines = [ln.strip() for ln in text.splitlines()]

    card = re.search(r"(\d{6})\*{6}(\d{4})", text)
    frm = re.search(r"From Date :\s*\n(?:.*\n)*?(\d{4}-\d{2}-\d{2})", text)
    to = re.search(r"To Date :\s*\n(?:.*\n)*?(\d{4}-\d{2}-\d{2})", text)
    if not card:
        raise ValueError("could not find card number")

    transactions = []
    current = None
    buffer: list[str] = []
    for ln in lines:
        row = UNION_ROW.match(ln)
        if row:
            if current:
                transactions.append(current)
            current = {"date": row.group("date"), "parts": []}
            buffer = []
            continue
        if not current:
            continue
        amounts = UNION_AMOUNTS.match(ln)
        if amounts:
            description = squash(" ".join(current["parts"]))
            direction = "out"
            value = amounts.group("debit")
            if value in ("-", ""):
                direction = "in"
                value = amounts.group("credit")
            amount = num(value) if value not in ("-", "") else 0.0
            transactions.append({**current, "final": (description, amount, direction)})
            current = None
            continue
        if ln and not ln.startswith("Page") and not ln.startswith("This is"):
            current["parts"].append(ln)

    parsed = []
    for t in transactions:
        if "final" not in t:
            continue
        description, amount, direction = t["final"]
        if amount == 0:
            continue
        parsed.append(make_txn(datetime.strptime(t["date"], "%Y-%m-%d").date(), description, amount, direction))

    return {
        "bank": "union",
        "file": path.name,
        "card_last4": card.group(2),
        "statement_date": to.group(1) if to else "",
        "period_start": frm.group(1) if frm else "",
        "period_end": to.group(1) if to else "",
        "opening": None,
        "closing": None,
        "minimum_due": None,
        "due_date": "",
        "credit_limit": None,
        "transactions": parsed,
        "checks": {"debit_total": round(sum(t["amount"] for t in parsed if t["direction"] == "out"), 2)},
    }


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------
PARSERS = {
    "combank": parse_combank,
    "nationstrust bank": parse_ntb,
    "seylan bank": parse_seylan,
    "union bank": parse_union,
}


def parse_all() -> list[dict]:
    out: list[dict] = []
    seen: dict[tuple[str, str], dict] = {}
    for bank_dir, parser in PARSERS.items():
        folder = INBOX / bank_dir
        if not folder.exists():
            continue
        for pdf in sorted(folder.glob("*.pdf")):
            try:
                statement = parser(pdf)
            except Exception as exc:
                out.append({"bank": bank_dir, "file": pdf.name, "error": str(exc), "transactions": []})
                continue
            key = (statement["bank"], statement["statement_date"])
            previous = seen.get(key)
            if previous is not None:
                statement["duplicate_of"] = previous["file"]
                if len(statement["transactions"]) > len(previous["transactions"]):
                    out = [s for s in out if s is not previous]
                    out.append(statement)
                    seen[key] = statement
                continue
            seen[key] = statement
            out.append(statement)
    return out


def diff(a: float, b: float) -> float:
    return round(a - b, 2)


def main() -> int:
    statements = parse_all()
    dest = Path("statements/parsed")
    dest.mkdir(parents=True, exist_ok=True)
    report = []
    for st in statements:
        name = f"{st['bank']}-{st.get('statement_date') or st['file']}".replace(" ", "_")
        (dest / f"{name}.json").write_text(json.dumps(st, indent=2), encoding="utf-8")
        if st.get("error"):
            report.append(f"FAIL {st['bank']}/{st['file']}: {st['error']}")
            continue
        checks = st["checks"]
        problems = []
        if st["closing"] is not None and st["opening"] is not None:
            if checks.get("summary_closes") is not None:
                d = diff(checks["summary_closes"], st["closing"])
                if abs(d) > 0.02:
                    problems.append(f"closes off {d}")
            if st["bank"] == "seylan":
                row_debits = round(checks["debit_sum"] - checks["finance_charges"], 2)
                if abs(diff(row_debits, checks["debit_statement"])) > 0.02:
                    problems.append(f"debits {diff(row_debits, checks['debit_statement'])}")
                if abs(diff(checks["credit_sum"], checks["credit_statement"])) > 0.02:
                    problems.append(f"credits {diff(checks['credit_sum'], checks['credit_statement'])}")
                if abs(diff(checks["closes"], st["closing"])) > 0.02:
                    problems.append(f"balance off {diff(checks['closes'], st['closing'])}")
        if st["bank"] == "combank":
            if abs(diff(checks["row_net"], checks["subtotal_sum"])) > 0.02:
                problems.append("subtotal mismatch")
        status = "OK  " if not problems else "WARN"
        opening = f"{st['opening']:>12,.2f}" if st["opening"] is not None else " " * 12
        closing = f"{st['closing']:>12,.2f}" if st["closing"] is not None else " " * 12
        report.append(
            f"{status} {st['bank']:<18} {st['card_last4']:<6} {st['statement_date']:<11} "
            f"{len(st['transactions']):>3} txns  open {opening} close {closing}  {'; '.join(problems)}"
        )
    print("\n".join(report))

    total = sum(len(s["transactions"]) for s in statements)
    print(f"\n{len(statements)} statements, {total} transactions")
    print(f"JSON written to {dest}")

    dupes = {}
    for st in statements:
        key = (st["bank"], st.get("statement_date"), st.get("file"))
        dupes.setdefault(key, 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
