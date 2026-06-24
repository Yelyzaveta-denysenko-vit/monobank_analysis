-- Actual transactions of recurring-payment merchants, enriched with the
-- subscription's metadata. Unlike the `subscriptions` summary (one row per
-- subscription), this is one row per real charge, so it has a proper time axis
-- for charts and a date filter.
SELECT
    t.id,
    t.time,
    t.amount_uah,
    ABS(t.amount_uah) AS abs_uah,
    COALESCE(m.normalized_name, '(невідомо)') AS merchant,
    COALESCE(c.name, 'Інше') AS category,
    COALESCE(c.group_name, 'Інше') AS category_group,
    rp.period_days,
    rp.confidence,
    rp.next_expected_date
FROM read_parquet('/data/parquet/transactions.parquet') t
JOIN read_parquet('/data/parquet/recurring_payments.parquet') rp ON rp.merchant_id = t.merchant_id
LEFT JOIN read_parquet('/data/parquet/merchants.parquet') m ON m.id = t.merchant_id
LEFT JOIN read_parquet('/data/parquet/categories.parquet') c ON c.id = t.category_id
WHERE t.amount < 0
