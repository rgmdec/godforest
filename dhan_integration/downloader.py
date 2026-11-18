"""Chunked Dhan historical downloads with deduplication and local storage."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import time
from typing import Any

import pandas as pd

from .client import DhanClient


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "dhan"
IST = "Asia/Kolkata"


def effective_five_year_start(requested: date) -> date:
    today = date.today()
    try:
        cutoff = today.replace(year=today.year - 5)
    except ValueError:
        cutoff = today.replace(year=today.year - 5, day=28)
    if requested < cutoff:
        print(f"NOTE: Dhan minute/rolling-options retention is five years. "
              f"Clamping requested start {requested} to {cutoff}.")
        return cutoff
    return requested


def date_chunks(start: date, end_exclusive: date, days: int):
    cursor = start
    while cursor < end_exclusive:
        nxt = min(cursor + timedelta(days=days), end_exclusive)
        yield cursor, nxt
        cursor = nxt


def _response_to_frame(body: dict[str, Any], timestamp_key: str = "timestamp") -> pd.DataFrame:
    # Dhan intraday endpoint returns flat arrays; rolling options nests arrays in data.ce/pe.
    payload = body
    if "data" in body and isinstance(body["data"], dict):
        payload = body["data"]
    keys = ("open", "high", "low", "close", "volume", "timestamp", "oi", "iv", "strike", "spot")
    columns = {k: payload[k] for k in keys if k in payload and isinstance(payload[k], list)}
    if not columns or timestamp_key not in columns:
        return pd.DataFrame()
    lengths = {len(v) for v in columns.values()}
    if len(lengths) != 1:
        raise ValueError(f"API arrays have inconsistent lengths: { {k: len(v) for k,v in columns.items()} }")
    frame = pd.DataFrame(columns)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="s", utc=True).dt.tz_convert(IST)
    return frame


def _save_merge(frame: pd.DataFrame, path: Path) -> int:
    if frame.empty:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            old = pd.read_parquet(path)
        except Exception:
            old = pd.read_csv(path.with_suffix(".csv"), parse_dates=["timestamp"])
        frame = pd.concat([old, frame], ignore_index=True)
    frame = frame.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp")
    try:
        frame.to_parquet(path, index=False)
    except Exception:
        frame.to_csv(path.with_suffix(".csv"), index=False)
    return len(frame)


def download_spot(client: DhanClient, start: date, end_inclusive: date, interval: int = 1):
    start = effective_five_year_start(start)
    start = effective_five_year_start(start)
    end_exclusive = end_inclusive + timedelta(days=1)
    total = 0
    for a, b in date_chunks(start, end_exclusive, 90):
        body = client.intraday(
            "13", "IDX_I", "INDEX",
            a.strftime("%Y-%m-%d 09:15:00"),
            (b - timedelta(days=1)).strftime("%Y-%m-%d 15:30:00"),
            interval=interval, oi=False,
        )
        frame = _response_to_frame(body)
        if not frame.empty:
            frame["instrument"] = "NIFTY_50_SPOT"
            total = _save_merge(frame, DATA_ROOT / "spot" / f"nifty50_{interval}m.parquet")
        print(f"Spot {a} to {b}: {len(frame):,} candles")
        time.sleep(0.15)
    return total


def download_options(
    client: DhanClient, start: date, end_inclusive: date,
    interval: int = 1, expiry_flag: str = "WEEK",
    expiry_code: int | None = None, max_strike_offset: int = 10,
):
    start = effective_five_year_start(start)
    end_exclusive = end_inclusive + timedelta(days=1)
    total_rows = 0
    expiry_codes = (expiry_code,) if expiry_code is not None else (0, 1, 2)
    for a, b in date_chunks(start, end_exclusive, 30):
        from_s, to_s = a.isoformat(), b.isoformat()  # API end date is non-inclusive
        for code in expiry_codes:
          for opt_type in ("CALL", "PUT"):
            for offset in range(-max_strike_offset, max_strike_offset + 1):
                strike = "ATM" if offset == 0 else f"ATM{offset:+d}"
                body = client.rolling_options(
                    from_s, to_s, opt_type, strike, expiry_flag,
                    code, interval,
                )
                data = body.get("data", {}) if isinstance(body, dict) else {}
                side_key = "ce" if opt_type == "CALL" else "pe"
                side = data.get(side_key) if isinstance(data, dict) else None
                if not isinstance(side, dict):
                    print(f"No {opt_type} payload for {a} to {b}, {strike}")
                    continue
                frame = _response_to_frame(side)
                if frame.empty:
                    continue
                frame["option_type"] = opt_type
                frame["expiry_flag"] = expiry_flag
                frame["expiry_code"] = code
                frame["strike_offset"] = offset
                out = DATA_ROOT / "options" / expiry_flag.lower() / f"expiry_{code}" / opt_type.lower() / f"{strike.replace('+','p').replace('-','m')}_{interval}m.parquet"
                total_rows = _save_merge(frame, out)
                print(f"Options {a} to {b}: {opt_type} {strike}, {len(frame):,} candles")
                time.sleep(0.12)
    return total_rows


def download_active_future(
    client: DhanClient, security_id: str, start: date,
    end_inclusive: date, interval: int = 1,
):
    """Download an ACTIVE FUTIDX contract only; expired intraday futures are unsupported."""
    end_exclusive = end_inclusive + timedelta(days=1)
    total = 0
    for a, b in date_chunks(start, end_exclusive, 90):
        body = client.intraday(
            security_id, "NSE_FNO", "FUTIDX",
            a.strftime("%Y-%m-%d 09:15:00"),
            (b - timedelta(days=1)).strftime("%Y-%m-%d 15:30:00"),
            interval=interval, oi=True,
        )
        frame = _response_to_frame(body)
        if not frame.empty:
            frame["security_id"] = str(security_id)
            frame["instrument"] = "NIFTY_FUTIDX_ACTIVE_CONTRACT"
            total = _save_merge(frame, DATA_ROOT / "futures" / f"nifty_fut_{security_id}_{interval}m.parquet")
        print(f"Active future {a} to {b}: {len(frame):,} candles")
        time.sleep(0.15)
    return total
