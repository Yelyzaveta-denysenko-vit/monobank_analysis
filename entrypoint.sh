#!/bin/bash
set -e

# Graceful shutdown — закрываем cron корректно
trap "echo 'Stopping...'; kill $(jobs -p) 2>/dev/null; exit 0" SIGTERM SIGINT

echo "=== Monobank Sync ==="
echo "DB: $DB_PATH"

# Проверяем есть ли уже данные
if [ -f "$DB_PATH" ]; then
    echo "БД найдена, досинк..."
else
    echo "БД не найдена, первая загрузка..."
fi

echo "Запуск синхронизации..."
python3 /app/sync.py

# Запуск cron для периодической синхронизации
echo "Настройка автосинка каждый час..."
echo "0 * * * * cd /app && DB_PATH=$DB_PATH PARQUET_DIR=$PARQUET_DIR MONO_TOKEN=$MONO_TOKEN python3 sync.py >> /var/log/sync.log 2>&1" | crontab -
cron

echo "Синк-сервис запущен. Следующая синхронизация через час."

# Держим контейнер живым
tail -f /var/log/sync.log 2>/dev/null &
wait
