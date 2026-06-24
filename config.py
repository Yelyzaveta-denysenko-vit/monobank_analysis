import os
import time
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

MONO_TOKEN = os.getenv("MONO_TOKEN")
MONO_API_BASE = "https://api.monobank.ua"
NBU_API_BASE = "https://bank.gov.ua/NBUStatService/v1/statdirectory"

DB_PATH = os.getenv("DB_PATH", "data/db/mono.duckdb")
PARQUET_DIR = os.getenv("PARQUET_DIR", "data/parquet")
RILL_URL = os.getenv("RILL_URL", "http://localhost:9010")
INITIAL_HISTORY_DAYS = int(os.getenv("INITIAL_HISTORY_DAYS", "365"))

CURRENCY_NAMES = {980: "UAH", 840: "USD", 978: "EUR", 203: "CZK", 826: "GBP", 985: "PLN"}
BASE_CURRENCY_CODE = 980  # гривня — базова валюта звітності

_start_time = time.time()


def currency_name(code: int) -> str:
    return CURRENCY_NAMES.get(code, str(code))


def log(msg: str):
    elapsed = time.time() - _start_time
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts} +{elapsed:6.1f}s] {msg}", flush=True)
