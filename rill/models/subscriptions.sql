-- Recurring payments / subscriptions found by the detect_recurring algorithm.
-- monthly_cost_uah scales each payment to a monthly cost based on its period.
SELECT
    rp.id,
    COALESCE(m.normalized_name, '(невідомо)') AS merchant,
    COALESCE(c.name, 'Інше') AS category,
    COALESCE(c.group_name, 'Інше') AS category_group,
    rp.typical_amount_uah,
    rp.period_days,
    rp.occurrences,
    rp.last_date,
    rp.next_expected_date,
    rp.confidence,
    rp.typical_amount_uah * (30.0 / NULLIF(rp.period_days, 0)) AS monthly_cost_uah
FROM read_parquet('/data/parquet/recurring_payments.parquet') rp
LEFT JOIN read_parquet('/data/parquet/merchants.parquet') m ON m.id = rp.merchant_id
LEFT JOIN read_parquet('/data/parquet/categories.parquet') c ON c.id = rp.category_id
