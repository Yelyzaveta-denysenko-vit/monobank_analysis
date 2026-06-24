-- Transactions mart: raw data enriched with categories, merchants, UAH amounts,
-- subscription/anomaly flags and tags. Categories come from the reference table
-- (this used to be a large CASE here). Displayed values are in Ukrainian.
SELECT
    t.id,
    t.account_id,
    CASE
        WHEN a.currency_code = 980 THEN 'UAH'
        WHEN a.currency_code = 840 THEN 'USD'
        WHEN a.currency_code = 978 THEN 'EUR'
        ELSE CAST(a.currency_code AS VARCHAR)
    END || ' ' || COALESCE(a.type, '') ||
    CASE
        WHEN a.masked_pan IS NOT NULL AND a.masked_pan != ''
        THEN ' *' || RIGHT(REPLACE(a.masked_pan, ',', '/'), 4)
        ELSE ''
    END AS account_name,
    t.time,
    t.description,
    t.mcc,
    t.amount,
    t.amount_uah,
    ABS(t.amount_uah) AS abs_uah,
    t.operation_amount,
    t.cashback_amount,
    t.balance,
    t.hold,
    t.comment,
    -- Category and group from the reference table
    COALESCE(cat.name, 'Інше') AS category,
    COALESCE(cat.group_name, 'Інше') AS category_group,
    COALESCE(cat.kind, 'expense') AS category_kind,
    -- Merchant from the dimension table
    COALESCE(m.normalized_name, '(без опису)') AS merchant,
    CASE WHEN t.amount < 0 THEN 'Витрата' ELSE 'Дохід' END AS tx_type,
    -- Operation currency (may differ from the account currency)
    CASE
        WHEN t.currency_code = 980 THEN 'UAH'
        WHEN t.currency_code = 840 THEN 'USD'
        WHEN t.currency_code = 978 THEN 'EUR'
        WHEN t.currency_code = 203 THEN 'CZK'
        ELSE CAST(t.currency_code AS VARCHAR)
    END AS op_currency,
    -- Analytics flags
    CASE WHEN an.transaction_id IS NOT NULL THEN 'Аномалія' ELSE 'Звичайна' END AS anomaly_flag,
    CASE WHEN rp.merchant_id IS NOT NULL THEN 'Регулярний' ELSE 'Разовий' END AS recurring_flag,
    COALESCE(tags_agg.tags, '') AS tags,
    CASE DAYOFWEEK(t.time)
        WHEN 0 THEN '7 Нд' WHEN 1 THEN '1 Пн' WHEN 2 THEN '2 Вт'
        WHEN 3 THEN '3 Ср' WHEN 4 THEN '4 Чт' WHEN 5 THEN '5 Пт' WHEN 6 THEN '6 Сб'
    END AS day_of_week,
    STRFTIME(t.time, '%Y-%m') AS month
FROM read_parquet('/data/parquet/transactions.parquet') t
LEFT JOIN read_parquet('/data/parquet/accounts.parquet') a ON t.account_id = a.id
LEFT JOIN read_parquet('/data/parquet/categories.parquet') cat ON t.category_id = cat.id
LEFT JOIN read_parquet('/data/parquet/merchants.parquet') m ON t.merchant_id = m.id
LEFT JOIN read_parquet('/data/parquet/anomalies.parquet') an ON an.transaction_id = t.id
LEFT JOIN (
    SELECT DISTINCT merchant_id FROM read_parquet('/data/parquet/recurring_payments.parquet')
) rp ON rp.merchant_id = t.merchant_id
LEFT JOIN (
    SELECT tt.transaction_id, STRING_AGG(tg.name, ', ') AS tags
    FROM read_parquet('/data/parquet/transaction_tags.parquet') tt
    JOIN read_parquet('/data/parquet/tags.parquet') tg ON tg.id = tt.tag_id
    GROUP BY 1
) tags_agg ON tags_agg.transaction_id = t.id
