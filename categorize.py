"""Transaction categorization: rules (by priority) -> MCC -> fallback.

A rule with a higher priority value overrides the MCC-based category and
weaker rules.
"""

import duckdb

from config import log


def assign_categories(con: duckdb.DuckDBPyConnection, fallback_id: int):
    log("Categorizing transactions...")

    # 1) Base category from MCC
    con.execute("""
        UPDATE transactions AS t
        SET category_id = m.category_id
        FROM mcc_map AS m
        WHERE t.mcc = m.mcc
    """)

    # 2) Unknown MCCs -> fallback
    con.execute(
        "UPDATE transactions SET category_id = ? WHERE category_id IS NULL",
        [fallback_id],
    )

    # 3) User rules override MCC (apply weaker ones first)
    rules = con.execute("""
        SELECT pattern, field, category_id, priority
        FROM categorization_rules
        WHERE category_id IS NOT NULL
        ORDER BY priority ASC
    """).fetchall()

    applied = 0
    for pattern, field, category_id, _ in rules:
        column = "counter_name" if field == "merchant" else "description"
        con.execute(
            f"UPDATE transactions SET category_id = ? "
            f"WHERE {column} ILIKE '%' || ? || '%'",
            [category_id, pattern],
        )
        applied += 1

    if rules:
        log(f"  Rules applied: {applied}")

    counts = con.execute("""
        SELECT c.name, COUNT(*) AS n
        FROM transactions t JOIN categories c ON t.category_id = c.id
        GROUP BY 1 ORDER BY n DESC LIMIT 5
    """).fetchall()
    log(f"  Top categories: {counts}")


def seed_example_rules(con: duckdb.DuckDBPyConnection):
    """Example rules (idempotent). Recognizes common CZ/UA merchants."""
    examples = [
        # (pattern, field, category_name, priority)
        ("ALBERT", "description", "Продукти", 200),
        ("BILLA", "description", "Продукти", 200),
        ("LIDL", "description", "Продукти", 200),
        ("DELIKOMAT", "description", "Фастфуд", 200),
        ("BOLT", "description", "Таксі", 200),
        ("UBER", "description", "Таксі", 200),
        ("NETFLIX", "description", "Підписки", 210),
        ("SPOTIFY", "description", "Підписки", 210),
        ("YOUTUBE", "description", "Підписки", 210),
        ("GOOGLE", "description", "Цифрові товари", 190),
        ("APPLE", "description", "Цифрові товари", 190),
    ]
    existing = {r[0] for r in con.execute(
        "SELECT pattern FROM categorization_rules").fetchall()}
    added = 0
    for pattern, field, cat_name, prio in examples:
        if pattern in existing:
            continue
        row = con.execute(
            "SELECT id FROM categories WHERE name = ?", [cat_name]).fetchone()
        if not row:
            continue
        con.execute(
            "INSERT INTO categorization_rules (pattern, field, category_id, priority) "
            "VALUES (?, ?, ?, ?)",
            [pattern, field, row[0], prio],
        )
        added += 1
    if added:
        log(f"  Example rules added: {added}")
