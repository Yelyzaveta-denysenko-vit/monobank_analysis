#!/usr/bin/env python3
"""Monobank BI pipeline orchestrator.

Stages: raw ingestion -> categorization -> merchants -> rates/normalization ->
aggregates -> analytics -> tags -> Parquet export.

Supports a --enrich-only flag: skip the Monobank API and rebuild only the
derived data on top of already-loaded transactions.
"""

import os
import sys

import duckdb

import analytics
import categorize
import fx
import merchants
import seed
from config import DB_PATH, MONO_TOKEN, PARQUET_DIR, currency_name, log
from db import init_db
from export import export_parquet
from ingest import sync_account, sync_accounts
from taxonomy import seed_taxonomy


def enrich(con: duckdb.DuckDBPyConnection):
    """All derived steps on top of the raw transactions."""
    fallback_id = seed_taxonomy(con)
    categorize.seed_example_rules(con)
    categorize.assign_categories(con, fallback_id)

    merchants.build_merchants(con)

    fx.sync_rates(con)
    fx.normalize_amounts(con)

    # Clear derived tables that reference merchants (FK) — otherwise DuckDB
    # forbids UPDATE-ing merchant rows that are still referenced.
    con.execute("DELETE FROM recurring_payments")
    merchants.refresh_stats(con)

    seed.seed_budgets(con)
    analytics.detect_recurring(con)
    analytics.detect_anomalies(con)
    analytics.forecast_and_alert(con)
    seed.seed_tags(con)


def main():
    enrich_only = "--enrich-only" in sys.argv

    log("=" * 50)
    log("MONOBANK BI SYNC" + (" (enrich-only)" if enrich_only else ""))
    log("=" * 50)
    log(f"DB: {DB_PATH}")
    log(f"Parquet: {PARQUET_DIR}")

    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    con = duckdb.connect(DB_PATH)
    init_db(con)

    if not enrich_only:
        if not MONO_TOKEN:
            log("ERROR: MONO_TOKEN is not set!")
            sys.exit(1)
        accounts = sync_accounts(con)
        for i, acc in enumerate(accounts, 1):
            log("")
            log(f"--- Account {i}/{len(accounts)}: {acc['id'][:8]}... "
                f"({currency_name(acc['currencyCode'])}) ---")
            try:
                sync_account(con, acc["id"])
            except Exception as e:
                log(f"ERROR: {e}")

    total = con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    log("")
    log(f"Transactions in DB: {total}")

    log("")
    log("--- Enrichment ---")
    enrich(con)

    export_parquet(con)
    con.close()

    log("")
    log("SYNC DONE")
    log("=" * 50)


if __name__ == "__main__":
    main()
