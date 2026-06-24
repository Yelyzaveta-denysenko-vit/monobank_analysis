"""Export tables to Parquet — the data source for Rill."""

import os

import duckdb

from config import PARQUET_DIR, log

TABLES = [
    "transactions", "accounts", "categories", "merchants",
    "fx_rates", "budgets", "recurring_payments", "anomalies",
    "tags", "transaction_tags",
]


def export_tables(con: duckdb.DuckDBPyConnection, names: list[str]):
    """Export the given tables to Parquet (for targeted updates from the UI)."""
    os.makedirs(PARQUET_DIR, exist_ok=True)
    for table in names:
        path = f"{PARQUET_DIR}/{table}.parquet"
        con.execute(f"COPY {table} TO '{path}' (FORMAT PARQUET, OVERWRITE)")


def export_parquet(con: duckdb.DuckDBPyConnection):
    log("Exporting to Parquet...")
    export_tables(con, TABLES)
    log(f"  Tables exported: {len(TABLES)}")
