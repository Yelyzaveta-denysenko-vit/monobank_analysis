import duckdb

from config import log


def _seq(con, name):
    con.execute(f"CREATE SEQUENCE IF NOT EXISTS {name} START 1")


def init_db(con: duckdb.DuckDBPyConnection):
    log("Initializing DB schema...")

    con.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id VARCHAR PRIMARY KEY,
            account_id VARCHAR NOT NULL,
            time TIMESTAMP NOT NULL,
            description VARCHAR,
            mcc INTEGER,
            original_mcc INTEGER,
            amount DOUBLE,
            operation_amount DOUBLE,
            currency_code INTEGER,
            commission_rate DOUBLE,
            cashback_amount DOUBLE,
            balance DOUBLE,
            hold BOOLEAN,
            comment VARCHAR,
            receipt_id VARCHAR,
            invoice_id VARCHAR,
            counter_edrpou VARCHAR,
            counter_iban VARCHAR,
            counter_name VARCHAR,
            synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # колонки збагачення (додаються сумісно з уже наявною БД)
    for col, typ in [
        ("category_id", "INTEGER"),
        ("merchant_id", "INTEGER"),
        ("amount_uah", "DOUBLE"),
    ]:
        con.execute(f"ALTER TABLE transactions ADD COLUMN IF NOT EXISTS {col} {typ}")

    con.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id VARCHAR PRIMARY KEY,
            send_id VARCHAR,
            currency_code INTEGER,
            cashback_type VARCHAR,
            balance DOUBLE,
            credit_limit DOUBLE,
            masked_pan VARCHAR,
            type VARCHAR,
            iban VARCHAR,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY,
            name VARCHAR NOT NULL,
            group_name VARCHAR NOT NULL,
            kind VARCHAR DEFAULT 'expense'
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS mcc_map (
            mcc INTEGER PRIMARY KEY,
            category_id INTEGER REFERENCES categories(id)
        )
    """)

    _seq(con, "merchants_seq")
    con.execute("""
        CREATE TABLE IF NOT EXISTS merchants (
            id INTEGER PRIMARY KEY DEFAULT nextval('merchants_seq'),
            normalized_name VARCHAR UNIQUE NOT NULL,
            category_id INTEGER REFERENCES categories(id),
            first_seen TIMESTAMP,
            last_seen TIMESTAMP,
            tx_count INTEGER DEFAULT 0,
            total_uah DOUBLE DEFAULT 0
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS fx_rates (
            rate_date DATE NOT NULL,
            currency_code INTEGER NOT NULL,
            rate_uah DOUBLE NOT NULL,
            PRIMARY KEY (rate_date, currency_code)
        )
    """)

    _seq(con, "rules_seq")
    con.execute("""
        CREATE TABLE IF NOT EXISTS categorization_rules (
            id INTEGER PRIMARY KEY DEFAULT nextval('rules_seq'),
            pattern VARCHAR NOT NULL,
            field VARCHAR NOT NULL DEFAULT 'description',
            category_id INTEGER REFERENCES categories(id),
            priority INTEGER DEFAULT 100
        )
    """)

    _seq(con, "budgets_seq")
    con.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY DEFAULT nextval('budgets_seq'),
            category_id INTEGER REFERENCES categories(id),
            month VARCHAR NOT NULL,
            limit_uah DOUBLE NOT NULL
        )
    """)

    _seq(con, "tags_seq")
    con.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY DEFAULT nextval('tags_seq'),
            name VARCHAR UNIQUE NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS transaction_tags (
            transaction_id VARCHAR REFERENCES transactions(id),
            tag_id INTEGER REFERENCES tags(id),
            PRIMARY KEY (transaction_id, tag_id)
        )
    """)

    _seq(con, "recurring_seq")
    con.execute("""
        CREATE TABLE IF NOT EXISTS recurring_payments (
            id INTEGER PRIMARY KEY DEFAULT nextval('recurring_seq'),
            merchant_id INTEGER REFERENCES merchants(id),
            category_id INTEGER REFERENCES categories(id),
            typical_amount_uah DOUBLE,
            period_days INTEGER,
            occurrences INTEGER,
            last_date TIMESTAMP,
            next_expected_date TIMESTAMP,
            confidence DOUBLE
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS anomalies (
            transaction_id VARCHAR PRIMARY KEY REFERENCES transactions(id),
            category_id INTEGER REFERENCES categories(id),
            amount_uah DOUBLE,
            expected_mean DOUBLE,
            expected_std DOUBLE,
            z_score DOUBLE,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    _seq(con, "sync_log_seq")
    con.execute("""
        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY DEFAULT nextval('sync_log_seq'),
            account_id VARCHAR,
            synced_from TIMESTAMP,
            synced_to TIMESTAMP,
            tx_count INTEGER,
            synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    log("Schema ready")
