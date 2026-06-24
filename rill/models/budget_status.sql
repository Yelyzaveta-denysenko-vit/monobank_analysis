SELECT
    b.month,
    c.name AS category,
    c.group_name AS category_group,
    b.limit_uah,
    COALESCE(spent.used_uah, 0) AS used_uah,
    b.limit_uah - COALESCE(spent.used_uah, 0) AS remaining_uah,
    COALESCE(spent.used_uah, 0) / NULLIF(b.limit_uah, 0) AS utilization,
    CASE WHEN COALESCE(spent.used_uah, 0) > b.limit_uah THEN 'Перевищено' ELSE 'В нормі' END AS status
FROM read_parquet('/data/parquet/budgets.parquet') b
JOIN read_parquet('/data/parquet/categories.parquet') c ON c.id = b.category_id
LEFT JOIN (
    SELECT category_id, STRFTIME(time, '%Y-%m') AS m, SUM(ABS(amount_uah)) AS used_uah
    FROM read_parquet('/data/parquet/transactions.parquet')
    WHERE amount < 0
    GROUP BY 1, 2
) spent ON spent.category_id = b.category_id AND spent.m = b.month
