"""External API clients: Monobank (accounts, statements) and NBU (FX rates)."""

import time
from datetime import datetime

import requests

from config import MONO_API_BASE, MONO_TOKEN, NBU_API_BASE, log


def _headers() -> dict:
    return {"X-Token": MONO_TOKEN}


def get_client_info() -> dict:
    log("API GET /personal/client-info")
    resp = requests.get(f"{MONO_API_BASE}/personal/client-info", headers=_headers())
    if resp.status_code == 429:
        log("  429 Rate limit — waiting 65s...")
        time.sleep(65)
        resp = requests.get(f"{MONO_API_BASE}/personal/client-info", headers=_headers())
    resp.raise_for_status()
    return resp.json()


def fetch_statement(account_id: str, from_ts: int, to_ts: int) -> list[dict]:
    """Account statement, split into 31-day chunks (API limit)."""
    max_range = 31 * 24 * 60 * 60
    all_txs: list[dict] = []

    chunks = []
    cursor = from_ts
    while cursor < to_ts:
        chunk_to = min(cursor + max_range, to_ts)
        chunks.append((cursor, chunk_to))
        cursor = chunk_to + 1

    for i, (c_from, c_to) in enumerate(chunks, 1):
        d_from = datetime.fromtimestamp(c_from).strftime("%d.%m.%Y")
        d_to = datetime.fromtimestamp(c_to).strftime("%d.%m.%Y")
        log(f"  Chunk {i}/{len(chunks)}: {d_from} — {d_to}")
        path = f"/personal/statement/{account_id}/{c_from}/{c_to}"

        resp = None
        for attempt in range(5):
            try:
                t0 = time.time()
                resp = requests.get(f"{MONO_API_BASE}{path}", headers=_headers())
                if resp.status_code == 429:
                    log(f"    429 (attempt {attempt + 1}/5) — waiting 65s...")
                    time.sleep(65)
                    continue
                resp.raise_for_status()
                break
            except requests.RequestException as e:
                if attempt < 4:
                    log(f"    Error (attempt {attempt + 1}/5): {e} — retry in 10s...")
                    time.sleep(10)
                else:
                    raise

        data = resp.json()
        if isinstance(data, list):
            all_txs.extend(data)
            log(f"    ← {len(data)} transactions in {time.time() - t0:.1f}s (total: {len(all_txs)})")
        else:
            log(f"    ← Unexpected response: {str(data)[:100]}")

    return all_txs


def fetch_nbu_rates(date: datetime) -> list[dict]:
    """NBU rates for a date. Returns a list of {r030, cc, rate} (UAH per unit).

    On weekends/holidays NBU may return an empty list; in that case the rate is
    taken from the nearest previous date during normalization (ASOF join).
    """
    ymd = date.strftime("%Y%m%d")
    resp = requests.get(f"{NBU_API_BASE}/exchange?date={ymd}&json", timeout=30)
    resp.raise_for_status()
    return resp.json()
