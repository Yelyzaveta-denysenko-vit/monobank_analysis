import time
from datetime import datetime

import duckdb

from config import INITIAL_HISTORY_DAYS, currency_name, log
from mono_client import fetch_statement, get_client_info


def sync_accounts(con: duckdb.DuckDBPyConnection) -> list[dict]:
    log("Loading account info...")
    info = get_client_info()
    accounts = info.get("accounts", [])

    for acc in accounts:
        cur = currency_name(acc["currencyCode"])
        bal = acc.get("balance", 0) / 100
        log(f"  Account {acc['id'][:8]}... {cur} balance={bal:,.2f}")
        pans = ",".join(acc.get("maskedPan", []))
        con.execute("""
            INSERT OR REPLACE INTO accounts
            (id, send_id, currency_code, cashback_type, balance, credit_limit,
             masked_pan, type, iban, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, [
            acc["id"], acc.get("sendId", ""), acc.get("currencyCode"),
            acc.get("cashbackType", ""), bal, acc.get("creditLimit", 0) / 100,
            pans, acc.get("type", ""), acc.get("iban", ""),
        ])

    log(f"Accounts found: {len(accounts)}")
    return accounts


def _last_sync_ts(con: duckdb.DuckDBPyConnection, account_id: str) -> int | None:
    row = con.execute(
        "SELECT MAX(time) FROM transactions WHERE account_id = ?", [account_id]
    ).fetchone()
    return int(row[0].timestamp()) if row and row[0] else None


def _save(con: duckdb.DuckDBPyConnection, account_id: str, txs: list[dict]) -> int:
    if not txs:
        return 0
    inserted = 0
    for tx in txs:
        try:
            con.execute("""
                INSERT OR IGNORE INTO transactions
                (id, account_id, time, description, mcc, original_mcc,
                 amount, operation_amount, currency_code, commission_rate,
                 cashback_amount, balance, hold, comment, receipt_id,
                 invoice_id, counter_edrpou, counter_iban, counter_name, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, [
                tx["id"], account_id, datetime.fromtimestamp(tx["time"]),
                tx.get("description", ""), tx.get("mcc", 0), tx.get("originalMcc", 0),
                tx.get("amount", 0) / 100, tx.get("operationAmount", 0) / 100,
                tx.get("currencyCode", 0), tx.get("commissionRate", 0) / 100,
                tx.get("cashbackAmount", 0) / 100, tx.get("balance", 0) / 100,
                tx.get("hold", False), tx.get("comment", ""), tx.get("receiptId", ""),
                tx.get("invoiceId", ""), tx.get("counterEdrpou", ""),
                tx.get("counterIban", ""), tx.get("counterName", ""),
            ])
            inserted += 1
        except Exception:
            pass
    return inserted


def sync_account(con: duckdb.DuckDBPyConnection, account_id: str):
    last_ts = _last_sync_ts(con, account_id)
    now_ts = int(time.time())
    if last_ts:
        from_ts = last_ts
        log(f"Incremental sync from {datetime.fromtimestamp(from_ts).strftime('%d.%m.%Y %H:%M')}")
    else:
        from_ts = now_ts - INITIAL_HISTORY_DAYS * 86400
        log(f"Initial load — last {INITIAL_HISTORY_DAYS} days")

    txs = fetch_statement(account_id, from_ts, now_ts)
    inserted = _save(con, account_id, txs)
    con.execute("""
        INSERT INTO sync_log (account_id, synced_from, synced_to, tx_count, synced_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, [account_id, datetime.fromtimestamp(from_ts), datetime.fromtimestamp(now_ts), inserted])
    log(f"Account total: +{inserted} new of {len(txs)} fetched")
