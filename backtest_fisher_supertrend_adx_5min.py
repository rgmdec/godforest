#!/usr/bin/env python3
"""
Nifty 50 Supertrend + Fisher Transform + ADX option-buying backtest.

Inputs (defaults):
  data/nifty50_1min.csv
  data/nifty_atm_otm_itm_220_280_selected_1min.csv

The strategy indicators and breakout/stop/exit decisions use Nifty 50 underlying
prices. Options are used only for entry/exit fills and P&L. This is a research
backtest only: it never places broker orders.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import numpy as np
import pandas as pd

IST = "Asia/Kolkata"

ALIASES = {
    "timestamp": ["timestamp", "datetime", "date_time", "time", "ts"],
    "open": ["open", "o"],
    "high": ["high", "h"],
    "low": ["low", "l"],
    "close": ["close", "c", "ltp"],
    "instrument_key": ["instrument_key", "instrument", "symbol", "tradingsymbol", "ticker"],
    "strike": ["strike", "strike_price", "strikeprice"],
    "option_type": ["option_type", "instrument_type", "right", "optiontype", "type"],
    "expiry": ["expiry", "expiry_date", "expiry_datetime"],
}


def resolve_columns(columns, required, label):
    lower = {str(c).strip().lower(): c for c in columns}
    found = {}
    for key in required:
        for alias in ALIASES.get(key, [key]):
            if alias in lower:
                found[key] = lower[alias]
                break
    missing = [k for k in required if k not in found]
    if missing:
        raise ValueError(
            f"{label} is missing required columns {missing}. "
            f"Available columns: {list(columns)}"
        )
    return found


def read_ohlc(path, required, label):
    # Read only required fields; avoids retaining unrelated columns from large CSVs.
    header = pd.read_csv(path, nrows=0).columns
    cols = resolve_columns(header, required, label)
    usecols = list(dict.fromkeys(cols.values()))
    df = pd.read_csv(path, usecols=usecols, low_memory=False)
    rename = {v: k for k, v in cols.items()}
    df = df.rename(columns=rename)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize(IST, ambiguous="NaT", nonexistent="shift_forward")
    else:
        df["timestamp"] = df["timestamp"].dt.tz_convert(IST)
    for c in ["open", "high", "low", "close", "strike"]:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"])
    return df.sort_values("timestamp").reset_index(drop=True)


def wilder(series, period):
    return series.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def add_supertrend(df, period=10, multiplier=2.0):
    h, l, c = df["high"], df["low"], df["close"]
    prev_close = c.shift(1)
    tr = pd.concat([(h-l), (h-prev_close).abs(), (l-prev_close).abs()], axis=1).max(axis=1)
    atr = wilder(tr, period)
    mid = (h + l) / 2.0
    upper = mid + multiplier * atr
    lower = mid - multiplier * atr
    final_upper = upper.copy()
    final_lower = lower.copy()
    st = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=int)
    for i in range(len(df)):
        if i == 0 or pd.isna(atr.iat[i]):
            continue
        if i == 1 or pd.isna(final_upper.iat[i-1]):
            final_upper.iat[i] = upper.iat[i]
            final_lower.iat[i] = lower.iat[i]
        else:
            final_upper.iat[i] = (
                upper.iat[i] if upper.iat[i] < final_upper.iat[i-1]
                or c.iat[i-1] > final_upper.iat[i-1] else final_upper.iat[i-1]
            )
            final_lower.iat[i] = (
                lower.iat[i] if lower.iat[i] > final_lower.iat[i-1]
                or c.iat[i-1] < final_lower.iat[i-1] else final_lower.iat[i-1]
            )
        if i == 1 or pd.isna(st.iat[i-1]):
            direction.iat[i] = 1 if c.iat[i] >= mid.iat[i] else -1
        elif st.iat[i-1] == final_upper.iat[i-1]:
            direction.iat[i] = 1 if c.iat[i] > final_upper.iat[i] else -1
        else:
            direction.iat[i] = -1 if c.iat[i] < final_lower.iat[i] else 1
        st.iat[i] = final_lower.iat[i] if direction.iat[i] == 1 else final_upper.iat[i]
    df["supertrend"] = st
    df["st_dir"] = direction
    return df


def add_fisher(df, period=9):
    # Ehlers-style Fisher Transform with recursive smoothing.
    high_n = df["high"].rolling(period, min_periods=period).max()
    low_n = df["low"].rolling(period, min_periods=period).min()
    value = pd.Series(0.0, index=df.index)
    fisher = pd.Series(0.0, index=df.index)
    for i in range(len(df)):
        if pd.isna(high_n.iat[i]) or pd.isna(low_n.iat[i]):
            value.iat[i] = 0.0 if i == 0 else value.iat[i-1]
            fisher.iat[i] = 0.0 if i == 0 else fisher.iat[i-1]
            continue
        span = high_n.iat[i] - low_n.iat[i]
        raw = 0.0 if span == 0 else 2.0 * ((df["close"].iat[i] - low_n.iat[i]) / span - 0.5)
        prior = 0.0 if i == 0 else value.iat[i-1]
        value.iat[i] = np.clip(0.33 * raw + 0.67 * prior, -0.999, 0.999)
        p_f = 0.0 if i == 0 else fisher.iat[i-1]
        fisher.iat[i] = 0.5 * np.log((1 + value.iat[i]) / (1 - value.iat[i])) + 0.5 * p_f
    df["fisher"] = fisher
    df["fisher_signal"] = fisher.shift(1)
    return df


def add_adx(df, period=14):
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs()
    ], axis=1).max(axis=1)
    atr = wilder(tr, period)
    plus_di = 100 * wilder(plus_dm, period) / atr.replace(0, np.nan)
    minus_di = 100 * wilder(minus_dm, period) / atr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df["adx"] = wilder(dx, period)
    return df


def prepare_underlying(path, args):
    one = read_ohlc(path, ["timestamp", "open", "high", "low", "close"], "Underlying CSV")
    one = one.set_index("timestamp")
    bars = one.resample("5min", label="right", closed="right").agg({
        "open": "first", "high": "max", "low": "min", "close": "last"
    }).dropna().reset_index()
    bars = add_supertrend(bars, args.st_period, args.st_multiplier)
    bars = add_fisher(bars, args.fisher_period)
    bars = add_adx(bars, args.adx_period)
    return one.reset_index(), bars


def normalise_option_type(value):
    s = str(value).strip().upper()
    if s in {"CE", "CALL", "C"} or "CALL" in s:
        return "CE"
    if s in {"PE", "PUT", "P"} or "PUT" in s:
        return "PE"
    return s


def load_options(path):
    header = pd.read_csv(path, nrows=0).columns
    cols = resolve_columns(header, ["timestamp", "open", "high", "low", "close", "instrument_key", "strike", "option_type"], "Options CSV")
    df = pd.read_csv(path, usecols=list(dict.fromkeys(cols.values())), low_memory=False)
    df = df.rename(columns={v: k for k, v in cols.items()})
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize(IST, ambiguous="NaT", nonexistent="shift_forward")
    else:
        df["timestamp"] = df["timestamp"].dt.tz_convert(IST)
    for c in ["open", "high", "low", "close", "strike"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["option_type"] = df["option_type"].map(normalise_option_type)
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close", "strike", "instrument_key"])
    return df.sort_values("timestamp").reset_index(drop=True)


def option_at_entry(options, timestamp, spot, side, args):
    # Exact minute first; allow the next available minute only when exact timestamp is absent.
    rows = options[(options["timestamp"] == timestamp) & (options["option_type"] == side)].copy()
    if rows.empty:
        later = options[(options["timestamp"] > timestamp) &
                        (options["timestamp"] <= timestamp + pd.Timedelta(minutes=args.option_fill_wait)) &
                        (options["option_type"] == side)]
        if later.empty:
            return None
        first_ts = later["timestamp"].min()
        rows = later[later["timestamp"] == first_ts].copy()
    rows["strike_gap"] = (rows["strike"] - spot).abs()
    rows["premium_gap"] = (rows["open"] - args.target_premium).abs()
    # Keep the requested premium band; prefer nearest ATM strike, then premium nearest target.
    band = rows[rows["open"].between(args.premium_min, args.premium_max)]
    if band.empty:
        return None
    band = band.sort_values(["strike_gap", "premium_gap"])
    chosen = band.iloc[0]
    return chosen


def run_backtest(underlying_1m, bars, options, args):
    trades = []
    pending = None
    active = None
    one = underlying_1m.set_index("timestamp")
    bars = bars.reset_index(drop=True)

    for i in range(1, len(bars)):
        b = bars.iloc[i]
        prev = bars.iloc[i-1]
        if pd.isna(b["supertrend"]) or pd.isna(b["adx"]) or pd.isna(b["fisher"]):
            continue
        ts = b["timestamp"]

        # Evaluate an open position at each completed underlying 5-minute bar.
        if active is not None:
            side = active["side"]
            # Check the underlying stop on every 1-minute candle since option entry.
            stop_window = one[(one.index >= active["entry_time"]) & (one.index <= ts)]
            stop_hit = False
            stop_ts = None
            if side == "CE":
                hit_rows = stop_window[stop_window["low"] <= active["underlying_stop"]]
            else:
                hit_rows = stop_window[stop_window["high"] >= active["underlying_stop"]]
            if not hit_rows.empty:
                stop_hit = True
                stop_ts = hit_rows.index[0]

            reversed_trend = (b["st_dir"] < 0) if side == "CE" else (b["st_dir"] > 0)
            st_change = abs(b["supertrend"] - prev["supertrend"])
            flat = st_change <= max(abs(b["close"]) * args.flat_st_pct / 100.0, args.flat_st_points)
            exit_reason = "UNDERLYING_SIGNAL_CANDLE_SL" if stop_hit else (
                "SUPERTREND_REVERSAL" if reversed_trend else ("SUPERTREND_FLAT" if flat else None)
            )
            if exit_reason:
                exit_after = stop_ts if stop_hit else ts
                exit_rows = options[(options["instrument_key"] == active["instrument_key"]) &
                                    (options["timestamp"] >= exit_after)]
                if not exit_rows.empty:
                    ex = exit_rows.iloc[0]
                    active["exit_time"] = ex["timestamp"]
                    active["exit_price"] = float(ex["open"])
                    active["exit_reason"] = exit_reason
                    active["pnl_points"] = active["exit_price"] - active["entry_price"]
                    active["pnl_pct"] = active["pnl_points"] / active["entry_price"] * 100
                    trades.append(active)
                    active = None
                    pending = None
                    continue

        # One pending signal at a time; check subsequent 1-minute bars for breakout.
        if pending is not None and active is None:
            sig_ts = pending["signal_time"]
            window = one[(one.index > sig_ts) & (one.index <= sig_ts + pd.Timedelta(minutes=args.breakout_wait))]
            triggered = None
            for minute_ts, m in window.iterrows():
                if pending["side"] == "CE" and m["high"] > pending["trigger"]:
                    triggered = (minute_ts, m)
                    break
                if pending["side"] == "PE" and m["low"] < pending["trigger"]:
                    triggered = (minute_ts, m)
                    break
            if triggered:
                entry_ts, minute = triggered
                opt = option_at_entry(options, entry_ts, float(minute["close"]), pending["side"], args)
                if opt is not None:
                    active = {
                        "side": pending["side"], "signal_time": sig_ts, "entry_time": opt["timestamp"],
                        "entry_price": float(opt["open"]), "instrument_key": str(opt["instrument_key"]),
                        "strike": float(opt["strike"]), "spot_at_entry": float(minute["close"]),
                        "signal_high": pending["signal_high"], "signal_low": pending["signal_low"],
                        "underlying_stop": pending["stop"], "exit_time": None, "exit_price": None,
                        "exit_reason": None, "pnl_points": None, "pnl_pct": None
                    }
                pending = None

        if active is None and pending is None:
            fisher_cross_up = b["fisher"] > b["fisher_signal"] and prev["fisher"] <= prev["fisher_signal"]
            fisher_cross_dn = b["fisher"] < b["fisher_signal"] and prev["fisher"] >= prev["fisher_signal"]
            fisher_moving = abs(b["fisher"] - prev["fisher"]) >= args.fisher_min_move
            adx_rising = b["adx"] > prev["adx"] and (b["adx"] - prev["adx"]) >= args.adx_min_rise
            if not (fisher_moving and adx_rising):
                continue
            if b["st_dir"] > 0 and b["close"] > b["supertrend"] and fisher_cross_up and b["fisher"] >= -args.fisher_zero_band:
                pending = {"side": "CE", "signal_time": ts, "trigger": float(b["high"]),
                           "stop": float(b["low"]), "signal_high": float(b["high"]), "signal_low": float(b["low"])}
            elif b["st_dir"] < 0 and b["close"] < b["supertrend"] and fisher_cross_dn and b["fisher"] <= args.fisher_zero_band:
                pending = {"side": "PE", "signal_time": ts, "trigger": float(b["low"]),
                           "stop": float(b["high"]), "signal_high": float(b["high"]), "signal_low": float(b["low"])}

    # Force-close any remaining position at the final available option close.
    if active is not None:
        last = options[options["instrument_key"] == active["instrument_key"]]
        if not last.empty:
            ex = last.iloc[-1]
            active["exit_time"] = ex["timestamp"]
            active["exit_price"] = float(ex["close"])
            active["exit_reason"] = "END_OF_DATA"
            active["pnl_points"] = active["exit_price"] - active["entry_price"]
            active["pnl_pct"] = active["pnl_points"] / active["entry_price"] * 100
            trades.append(active)
    return pd.DataFrame(trades)


def main():
    p = argparse.ArgumentParser(description="Nifty 5m Supertrend + Fisher + ADX ATM CE/PE backtest")
    p.add_argument("--underlying", default="data/nifty50_1min.csv")
    p.add_argument("--options", default="data/nifty_atm_otm_itm_220_280_selected_1min.csv")
    p.add_argument("--out", default="results/fisher_supertrend_adx_5min")
    p.add_argument("--start", default=None, help="Inclusive date, e.g. 2025-01-01")
    p.add_argument("--end", default=None, help="Inclusive date, e.g. 2025-12-31")
    p.add_argument("--st-period", type=int, default=10)
    p.add_argument("--st-multiplier", type=float, default=2.0)
    p.add_argument("--fisher-period", type=int, default=9)
    p.add_argument("--fisher-zero-band", type=float, default=0.20)
    p.add_argument("--fisher-min-move", type=float, default=0.02)
    p.add_argument("--adx-period", type=int, default=14)
    p.add_argument("--adx-min-rise", type=float, default=0.0)
    p.add_argument("--target-premium", type=float, default=250.0)
    p.add_argument("--premium-min", type=float, default=220.0)
    p.add_argument("--premium-max", type=float, default=280.0)
    p.add_argument("--breakout-wait", type=int, default=30, help="Minutes after signal candle")
    p.add_argument("--option-fill-wait", type=int, default=2, help="Minutes to wait for option candle")
    p.add_argument("--flat-st-points", type=float, default=0.5)
    p.add_argument("--flat-st-pct", type=float, default=0.005)
    args = p.parse_args()

    for f in [args.underlying, args.options]:
        if not Path(f).exists():
            sys.exit(f"ERROR: file not found: {f}")

    print("Loading Nifty 50 underlying 1-minute data...")
    underlying, bars = prepare_underlying(args.underlying, args)
    print(f"Built {len(bars):,} completed 5-minute candles.")
    if args.start:
        start = pd.Timestamp(args.start, tz=IST)
        bars = bars[bars["timestamp"] >= start]
        underlying = underlying[underlying["timestamp"] >= start - pd.Timedelta(days=2)]
    if args.end:
        end = pd.Timestamp(args.end, tz=IST) + pd.Timedelta(days=1)
        bars = bars[bars["timestamp"] < end]
        underlying = underlying[underlying["timestamp"] < end]

    print("Loading selected CE/PE option 1-minute data (large CSV; memory use may be high)...")
    options = load_options(args.options)
    if args.start:
        options = options[options["timestamp"] >= pd.Timestamp(args.start, tz=IST)]
    if args.end:
        options = options[options["timestamp"] < pd.Timestamp(args.end, tz=IST) + pd.Timedelta(days=1)]

    print("Running paper backtest...")
    trades = run_backtest(underlying, bars, options, args)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    trades.to_csv(out / "trades.csv", index=False)

    if trades.empty:
        print("No trades found. Check the option CSV schema, premium coverage, and strategy filters.")
        return
    wins = int((trades["pnl_points"] > 0).sum())
    losses = int((trades["pnl_points"] <= 0).sum())
    summary = pd.DataFrame([{
        "trades": len(trades), "wins": wins, "losses": losses,
        "win_rate_pct": round(wins / len(trades) * 100, 2),
        "gross_pnl_option_points": round(trades["pnl_points"].sum(), 2),
        "avg_pnl_points": round(trades["pnl_points"].mean(), 2),
        "ce_trades": int((trades["side"] == "CE").sum()),
        "pe_trades": int((trades["side"] == "PE").sum()),
        "target_premium": args.target_premium,
        "premium_band": f"{args.premium_min}-{args.premium_max}",
        "timeframe": "5min underlying"
    }])
    summary.to_csv(out / "summary.csv", index=False)
    print("\nBACKTEST SUMMARY")
    print(summary.to_string(index=False))
    print(f"\nSaved: {out / 'trades.csv'}")
    print(f"Saved: {out / 'summary.csv'}")
    print("Note: P&L is option premium points per unit; brokerage, taxes, slippage, lot size,")
    print("and contract multiplier are not included. Review assumptions before paper trading.")


if __name__ == "__main__":
    main()
