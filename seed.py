"""Demo data for the product tables: budgets and tags.

Needed so the plan/fact budget dashboard and the M:M link (transaction_tags)
are non-empty on real data. Idempotent — re-running duplicates nothing.
"""

import duckdb

from config import log


def _latest_month(con: duckdb.DuckDBPyConnection) -> str | None:
    row = con.execute("SELECT STRFTIME(MAX(time), '%Y-%m') FROM transactions").fetchone()
    return row[0] if row else None


def seed_budgets(con: duckdb.DuckDBPyConnection):
    if con.execute("SELECT COUNT(*) FROM budgets").fetchone()[0] > 0:
        return
    month = _latest_month(con)
    if not month:
        return
    defaults = [
        ("Продукти", 12000),
        ("Ресторани/Кафе", 6000),
        ("Фастфуд", 3000),
        ("Таксі", 2500),
        ("Підписки", 1000),
    ]
    added = 0
    for name, limit_uah in defaults:
        row = con.execute("SELECT id FROM categories WHERE name = ?", [name]).fetchone()
        if not row:
            continue
        con.execute(
            "INSERT INTO budgets (category_id, month, limit_uah) VALUES (?, ?, ?)",
            [row[0], month, limit_uah],
        )
        added += 1
    if added:
        log(f"Seed: budgets for {month}: {added}")


def seed_tags(con: duckdb.DuckDBPyConnection):
    """Create tags and attach them to transactions (demonstrates the M:M link)."""
    for name in ["Підписка", "Валютна операція", "Велика покупка"]:
        con.execute("INSERT INTO tags (name) VALUES (?) ON CONFLICT DO NOTHING", [name])

    tag_id = dict(con.execute("SELECT name, id FROM tags").fetchall())

    # "Підписка" — transactions of merchants from recurring_payments
    con.execute("""
        INSERT INTO transaction_tags (transaction_id, tag_id)
        SELECT DISTINCT t.id, ?
        FROM transactions t
        WHERE t.merchant_id IN (SELECT merchant_id FROM recurring_payments)
          AND t.amount < 0
        ON CONFLICT DO NOTHING
    """, [tag_id["Підписка"]])

    # "Валютна операція" — everything not in hryvnia
    con.execute("""
        INSERT INTO transaction_tags (transaction_id, tag_id)
        SELECT id, ? FROM transactions WHERE currency_code <> 980
        ON CONFLICT DO NOTHING
    """, [tag_id["Валютна операція"]])

    # "Велика покупка" — expense over 5000 UAH
    con.execute("""
        INSERT INTO transaction_tags (transaction_id, tag_id)
        SELECT id, ? FROM transactions
        WHERE amount < 0 AND COALESCE(amount_uah, ABS(amount)) > 5000
        ON CONFLICT DO NOTHING
    """, [tag_id["Велика покупка"]])

    n = con.execute("SELECT COUNT(*) FROM transaction_tags").fetchone()[0]
    log(f"Seed: transaction-tag links: {n}")
