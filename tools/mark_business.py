"""Flag transactions as business/personal (and optionally tax-deductible) in bulk.

    python tools/mark_business.py --list
    python tools/mark_business.py --merchant "ALIBABA" --merchant "JLCPCB"
    python tools/mark_business.py --merchant "ALIBABA" --business 0      # undo
    python tools/mark_business.py --merchant "STARLINK" --deductible 1

Matches are case-insensitive substrings of the transaction description, over the
whole history. Figures are printed before anything changes.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finvault import db as fvdb  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(fvdb.DB_PATH))
    ap.add_argument("--merchant", action="append", default=[], help="description substring")
    ap.add_argument("--business", type=int, choices=[0, 1])
    ap.add_argument("--deductible", type=int, choices=[0, 1])
    ap.add_argument("--list", action="store_true", help="Show merchants over 20,000 with flags")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = fvdb.get_connection(Path(args.db))
    conn.row_factory = None

    if args.list or not args.merchant:
        print(f"{'total':>14}  {'rows':>4}  {'biz':>3}  merchant")
        for desc, total, rows, biz in conn.execute(
                """SELECT description, SUM(amount) s, COUNT(*), SUM(is_business)
                   FROM transactions WHERE direction = 'out'
                   GROUP BY description HAVING s > 20000 ORDER BY s DESC"""):
            print(f"{total:>14,.2f}  {rows:>4}  {biz:>3}  {desc[:62]}")
        return 0

    if args.business is None and args.deductible is None:
        print("Nothing to change: pass --business 0/1 or --deductible 0/1")
        return 2

    sets, params = [], []
    if args.business is not None:
        sets.append("is_business = ?")
        params.append(args.business)
    if args.deductible is not None:
        sets.append("tax_deductible = ?")
        params.append(args.deductible)
    sets.append("updated_at = ?")
    params.append(datetime.now().replace(microsecond=0).isoformat())

    where = " OR ".join("UPPER(description) LIKE ?" for _ in args.merchant)
    like_params = [f"%{m.upper()}%" for m in args.merchant]
    matched = conn.execute(
        f"SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM transactions WHERE ({where})",
        like_params).fetchone()
    print(f"Matched {matched[0]} transactions worth {matched[1]:,.2f}")

    if args.dry_run:
        print("Dry run: nothing changed.")
        return 0

    conn.execute(f"UPDATE transactions SET {', '.join(sets)} WHERE ({where})",
                 params + like_params)
    conn.commit()
    print(f"Updated {matched[0]} transactions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
