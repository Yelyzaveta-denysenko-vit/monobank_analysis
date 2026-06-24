import statistics
from datetime import datetime, timedelta

import duckdb

from config import log


def _cv(values: list[float]) -> float:
    # коефіцієнт варіації (σ/μ); 0 — ідеально стабільно
    if len(values) < 2:
        return 1.0
    m = statistics.mean(values)
    if m == 0:
        return 1.0
    return statistics.pstdev(values) / abs(m)


def detect_recurring(con: duckdb.DuckDBPyConnection, min_occurrences: int = 3):
    log("Analytics: detecting recurring payments...")
    con.execute("DELETE FROM recurring_payments")

    rows = con.execute("""
        SELECT merchant_id, category_id, time, COALESCE(amount_uah, ABS(amount)) AS amt
        FROM transactions
        WHERE merchant_id IS NOT NULL AND amount < 0
        ORDER BY merchant_id, time
    """).fetchall()

    by_merchant: dict[int, list] = {}
    for merchant_id, category_id, t, amt in rows:
        by_merchant.setdefault(merchant_id, []).append((t, abs(amt), category_id))

    found = 0
    for merchant_id, items in by_merchant.items():
        if len(items) < min_occurrences:
            continue
        times = [it[0] for it in items]
        amounts = [it[1] for it in items]
        intervals = [(times[i] - times[i - 1]).days for i in range(1, len(times))]
        intervals = [d for d in intervals if d > 0]
        if len(intervals) < min_occurrences - 1:
            continue

        period = statistics.median(intervals)
        if not (5 <= period <= 45):  # від тижневого до місячного циклу
            continue

        interval_cv = _cv(intervals)
        amount_cv = _cv(amounts)
        if interval_cv > 0.4 or amount_cv > 0.35:
            continue

        # впевненість зростає зі стабільністю інтервалу й суми
        confidence = round(max(0.0, 1 - (interval_cv + amount_cv) / 2), 2)
        last_date = max(times)
        next_expected = last_date + timedelta(days=int(round(period)))

        con.execute("""
            INSERT INTO recurring_payments
            (merchant_id, category_id, typical_amount_uah, period_days,
             occurrences, last_date, next_expected_date, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            merchant_id, items[0][2], round(statistics.median(amounts), 2),
            int(round(period)), len(items), last_date, next_expected, confidence,
        ])
        found += 1

    log(f"  Recurring payments found: {found}")


def detect_anomalies(con: duckdb.DuckDBPyConnection, ratio_threshold: float = 3.0,
                     min_merchant_tx: int = 4, floor_uah: float = 300.0):
    # аномалія = витрата у відомого продавця, помітно більша за медіанну для нього
    # (медіана стійка до викидів, кратність легко пояснити)
    log("Analytics: detecting anomalous spending...")
    con.execute("DELETE FROM anomalies")

    con.execute(f"""
        INSERT INTO anomalies
        (transaction_id, category_id, amount_uah, expected_mean, expected_std, z_score)
        WITH base AS (
            SELECT id, category_id, merchant_id, ABS(amount_uah) AS spend
            FROM transactions
            WHERE amount < 0 AND merchant_id IS NOT NULL AND amount_uah IS NOT NULL
        ),
        med AS (
            SELECT merchant_id, MEDIAN(spend) AS med_spend, COUNT(*) AS n
            FROM base GROUP BY merchant_id
            HAVING COUNT(*) >= {min_merchant_tx}
        )
        SELECT b.id, b.category_id, b.spend,
               m.med_spend, NULL, b.spend / m.med_spend AS ratio
        FROM base b JOIN med m ON b.merchant_id = m.merchant_id
        WHERE b.spend > m.med_spend * {ratio_threshold} AND b.spend > {floor_uah}
    """)

    n = con.execute("SELECT COUNT(*) FROM anomalies").fetchone()[0]
    log(f"  Anomalies found: {n}")


def forecast_and_alert(con: duckdb.DuckDBPyConnection):
    log("Analytics: spend forecast and budget check...")
    row = con.execute("SELECT MAX(time) FROM transactions").fetchone()
    if not row or not row[0]:
        return
    last_dt = row[0]
    month = last_dt.strftime("%Y-%m")
    days_in_month = ((last_dt.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)).day
    day = last_dt.day

    # перекази між власними рахунками не рахуємо як витрати
    spent = con.execute("""
        SELECT COALESCE(SUM(ABS(t.amount_uah)), 0)
        FROM transactions t JOIN categories c ON t.category_id = c.id
        WHERE t.amount < 0 AND c.kind <> 'transfer'
          AND STRFTIME(t.time, '%Y-%m') = ?
    """, [month]).fetchone()[0]
    projected = spent / day * days_in_month if day else spent
    log(f"  {month}: spent {spent:,.0f} UAH in {day}d -> forecast {projected:,.0f} UAH")

    budgets = con.execute("""
        SELECT c.name, b.limit_uah,
               COALESCE((SELECT SUM(ABS(t.amount_uah))
                         FROM transactions t
                         WHERE t.category_id = b.category_id AND t.amount < 0
                           AND STRFTIME(t.time, '%Y-%m') = b.month), 0) AS used
        FROM budgets b JOIN categories c ON b.category_id = c.id
        WHERE b.month = ?
    """, [month]).fetchall()

    for name, limit_uah, used in budgets:
        proj_cat = used / day * days_in_month if day else used
        flag = "OVER" if proj_cat > limit_uah else "ok"
        log(f"  Budget '{name}': {used:,.0f}/{limit_uah:,.0f} (forecast {proj_cat:,.0f}) — {flag}")
