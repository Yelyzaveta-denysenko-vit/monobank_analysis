#!/bin/bash
set -e

trap "echo 'Зупинка...'; kill $(jobs -p) 2>/dev/null; exit 0" SIGTERM SIGINT

echo "=== Monobank Sync ==="
echo "DB: $DB_PATH"

if [ -f "$DB_PATH" ]; then
    echo "БД знайдено, дооновлення..."
else
    echo "БД не знайдено, перше завантаження..."
fi

echo "Запуск синхронізації..."
python3 /app/sync.py

# автоматична синхронізація щогодини через cron
echo "Налаштування автосинхронізації щогодини..."
echo "0 * * * * cd /app && DB_PATH=$DB_PATH PARQUET_DIR=$PARQUET_DIR MONO_TOKEN=$MONO_TOKEN python3 sync.py >> /var/log/sync.log 2>&1" | crontab -
cron

echo "Сервіс синхронізації запущено. Наступна синхронізація — за годину."

tail -f /var/log/sync.log 2>/dev/null &
wait
