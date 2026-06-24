"""Multi-currency support: NBU rates and normalization to hryvnia.

Important: in Monobank the `amount` field is already in the ACCOUNT currency
(operation_amount is in the operation currency). So for a hryvnia account the
amount is already in UAH and no conversion is needed; only operations on foreign
accounts (e.g. EUR) need NBU-rate conversion. For weekends/holidays the nearest
rate is taken via an ASOF join.
"""

import time
from datetime import datetime

import duckdb

from config import BASE_CURRENCY_CODE, log
from mono_client import fetch_nbu_rates


def sync_rates(con: duckdb.DuckDBPyConnection):
    """Backfill NBU rates for every date that has non-hryvnia-account operations."""
    dates = con.execute(f"""
        SELECT DISTINCT CAST(t.time AS DATE) AS d
        FROM transactions t JOIN accounts a ON a.id = t.account_id
        WHERE a.currency_code <> {BASE_CURRENCY_CODE}
        ORDER BY d
    """).fetchall()
    if not dates:
        log("FX: no foreign accounts, rates not needed")
        return

    needed = {d[0] for d in dates}
    have = {r[0] for r in con.execute("SELECT DISTINCT rate_date FROM fx_rates").fetchall()}
    to_fetch = sorted(needed - have)

    log(f"FX: {len(needed)} dates total, {len(needed & have)} cached, fetching {len(to_fetch)}")

    fetched = 0
    for d in to_fetch:
        dt = datetime(d.year, d.month, d.day)
        try:
            rows = fetch_nbu_rates(dt)
        except Exception as e:
            log(f"  NBU {d}: error {e}")
            continue
        for r in rows:
            con.execute(
                "INSERT OR REPLACE INTO fx_rates (rate_date, currency_code, rate_uah) "
                "VALUES (?, ?, ?)",
                [d, int(r["r030"]), float(r["rate"])],
            )
        fetched += 1
        time.sleep(0.05)

    total = con.execute("SELECT COUNT(*) FROM fx_rates").fetchone()[0]
    log(f"FX: fetched {fetched} dates, {total} rate rows total")


def normalize_amounts(con: duckdb.DuckDBPyConnection):
    """Fill amount_uah for every transaction."""
    log("FX: normalizing amounts to UAH...")

    # Base-currency accounts — amount is already in UAH
    con.execute(f"""
        UPDATE transactions AS t SET amount_uah = t.amount
        FROM accounts AS a
        WHERE a.id = t.account_id AND a.currency_code = {BASE_CURRENCY_CODE}
    """)

    # Foreign accounts: rate for the ACCOUNT currency on date <= operation date
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _conv AS
        SELECT t.id, t.amount * f.rate_uah AS amt_uah
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        ASOF JOIN fx_rates f
            ON a.currency_code = f.currency_code
            AND CAST(t.time AS DATE) >= f.rate_date
        WHERE a.currency_code <> {BASE_CURRENCY_CODE}
    """)
    con.execute("""
        UPDATE transactions AS t SET amount_uah = c.amt_uah
        FROM _conv AS c WHERE t.id = c.id
    """)

    # Tail (date earlier than the earliest rate) — nearest forward rate
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _conv_fwd AS
        SELECT t.id, t.amount * f.rate_uah AS amt_uah
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        ASOF JOIN fx_rates f
            ON a.currency_code = f.currency_code
            AND CAST(t.time AS DATE) <= f.rate_date
        WHERE a.currency_code <> {BASE_CURRENCY_CODE} AND t.amount_uah IS NULL
    """)
    con.execute("""
        UPDATE transactions AS t SET amount_uah = c.amt_uah
        FROM _conv_fwd AS c WHERE t.id = c.id
    """)

    missing = con.execute(
        "SELECT COUNT(*) FROM transactions WHERE amount_uah IS NULL"
    ).fetchone()[0]
    if missing:
        log(f"  WARNING: {missing} transactions left without a rate")
    else:
        log("  All amounts normalized")
