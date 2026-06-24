"""Merchant dimension: name normalization, dedup, aggregates.

The merchant name comes from counter_name (if present), otherwise description.
Normalization collapses case/whitespace so 'Albert' and 'ALBERT ' are one entity.
"""

import duckdb

from config import log


def build_merchants(con: duckdb.DuckDBPyConnection):
    """Create merchant records and assign merchant_id to transactions."""
    log("Building merchant dimension...")

    con.execute(r"""
        CREATE OR REPLACE TEMP VIEW _tx_norm AS
        SELECT
            id,
            upper(trim(regexp_replace(
                coalesce(nullif(counter_name, ''), nullif(description, ''), '(без опису)'),
                '\s+', ' ', 'g'
            ))) AS norm
        FROM transactions
    """)

    con.execute("""
        INSERT INTO merchants (normalized_name)
        SELECT DISTINCT norm FROM _tx_norm
        WHERE norm NOT IN (SELECT normalized_name FROM merchants)
    """)

    con.execute("""
        UPDATE transactions AS t
        SET merchant_id = m.id
        FROM merchants AS m, _tx_norm AS n
        WHERE t.id = n.id AND m.normalized_name = n.norm
    """)

    n = con.execute("SELECT COUNT(*) FROM merchants").fetchone()[0]
    log(f"  Unique merchants: {n}")


def refresh_stats(con: duckdb.DuckDBPyConnection):
    """Recompute merchant aggregates. Call after FX normalization."""
    con.execute("""
        UPDATE merchants AS m
        SET first_seen = s.fs,
            last_seen = s.ls,
            tx_count = s.cnt,
            total_uah = s.tot,
            category_id = s.cat
        FROM (
            SELECT merchant_id,
                   MIN(time) AS fs,
                   MAX(time) AS ls,
                   COUNT(*) AS cnt,
                   SUM(COALESCE(amount_uah, ABS(amount))) AS tot,
                   MODE(category_id) AS cat
            FROM transactions
            WHERE merchant_id IS NOT NULL
            GROUP BY merchant_id
        ) AS s
        WHERE m.id = s.merchant_id
    """)
