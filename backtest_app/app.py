from __future__ import annotations
import io
from datetime import time
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from backtest_engine import run_ce_backtest
from indicators import add_ce_indicators
from strategy_config import DEFAULT_CE_CONFIG

st.set_page_config(page_title="Nifty Backtest Pro", page_icon="📈", layout="wide")
st.markdown("<style>.block-container{padding-top:1.4rem}[data-testid='stMetric']{background:rgba(120,120,120,.08);padding:14px;border-radius:12px}</style>", unsafe_allow_html=True)
st.title("NIFTY BACKTEST PRO")
st.caption("Strategy research • Upstox data integration • PAPER TRADING ONLY")

with st.sidebar:
    st.header("Workspace")
    mode = st.radio("Data mode", ["Historical backtest", "Live paper trading"])
    st.divider()
    st.subheader("CE_STGY BUILDER – Positional")
    premium_low = st.number_input("Premium minimum (₹)", min_value=0.0, value=220.0, step=5.0)
    premium_high = st.number_input("Premium maximum (₹)", min_value=0.0, value=280.0, step=5.0)
    units = st.number_input("Quantity / units", min_value=1, value=1, step=1)
    brokerage = st.number_input("Estimated costs per completed trade (₹)", min_value=0.0, value=0.0, step=5.0)
    force_exit_enabled = st.checkbox("Enable optional daily force-exit", value=False)
    force_exit_time = st.time_input("Force-exit time (IST)", value=time(15, 15))
    st.caption("No live orders are sent by this application.")

if mode == "Live paper trading":
    st.subheader("Live paper-trading connection")
    st.warning("Live WebSocket streaming is not implemented in this initial build. No live subscription or order request is sent.")
    st.info("The next integration stage must verify your Upstox market-data entitlement, authorization flow, subscription limits and Protobuf schema.")
    st.stop()

st.subheader("1. Market data")
st.write("Upload one selected Nifty CE contract's OHLC candles. All strategy indicators are calculated on this option premium series.")
uploaded = st.file_uploader("Upload option candle CSV", type=["csv"])
with st.expander("Expected CSV format"):
    st.code("timestamp,open,high,low,close,volume\n2025-01-01 09:15:00+05:30,245,251,242,249,1200")
    st.caption("Required: timestamp, open, high, low, close. Optional: volume, instrument_key, symbol.")

if uploaded is None:
    st.info("Upload an option CSV. Synthetic demo data is only for checking the interface and engine wiring.")
    if st.button("Load synthetic demo data"):
        idx = pd.date_range("2025-01-02 09:15", periods=500, freq="1min", tz="Asia/Kolkata")
        close = 248 + 10*np.sin(np.arange(len(idx))/13) + .018*np.arange(len(idx))
        demo = pd.DataFrame({"timestamp":idx,"open":pd.Series(close).shift(1).fillna(close[0]),"high":close+2.2,"low":close-2.2,"close":close,"volume":1000})
        st.session_state["demo_csv"] = demo.to_csv(index=False)
    if "demo_csv" not in st.session_state:
        st.stop()
    raw = pd.read_csv(io.StringIO(st.session_state["demo_csv"]))
else:
    raw = pd.read_csv(uploaded)

st.subheader("2. Entry-condition builder")
a,b,c = st.columns(3)
with a:
    use_supertrend = st.checkbox("Supertrend 1 bullish", True)
    st_length = st.number_input("Entry ST length", 1, 100, 10)
    st_factor = st.number_input("Entry ST factor", .1, 10.0, 2.0)
with b:
    use_rsi = st.checkbox("RSI above threshold", True)
    rsi_length = st.number_input("RSI length", 2, 100, 14)
    rsi_level = st.number_input("RSI threshold", 1.0, 99.0, 70.0)
with c:
    use_adx = st.checkbox("ADX below threshold", True)
    adx_length = st.number_input("ADX length", 2, 100, 12)
    adx_max = st.number_input("ADX maximum", 1.0, 100.0, 35.0)

d,e,f = st.columns(3)
with d:
    use_bollinger = st.checkbox("Close above BB upper", True)
    bb_length = st.number_input("Bollinger length", 2, 200, 20)
    bb_factor = st.number_input("Bollinger factor", .1, 5.0, 2.0)
with e:
    use_williams = st.checkbox("Williams %R above threshold", True)
    williams_length = st.number_input("Williams %R length", 2, 100, 14)
    williams_level = st.number_input("Williams %R threshold", -100.0, 0.0, -8.0)
with f:
    st.markdown("**Entry combination**")
    st.info("All enabled entry conditions are combined with AND.")
    st.markdown("**Initial defaults**")
    st.caption("ST 10,2 • RSI 14 > 70 • ADX 12 < 35 • BB 20,2 • Williams %R 14 > -8")

st.subheader("3. Exit configuration")
x,y = st.columns(2)
with x:
    exit_st_length = st.number_input("Exit Supertrend length", 1, 100, 10)
with y:
    exit_st_factor = st.number_input("Exit Supertrend factor", .1, 10.0, 2.0)

st.subheader("4. Run")
st.caption("Entry is simulated at the next candle open. Exit is simulated at the close of a candle closing below exit Supertrend. Daily force-exit is optional and disabled by default for positional testing.")
if st.button("Run CE backtest", type="primary", use_container_width=True):
    if premium_low >= premium_high:
        st.error("Premium minimum must be lower than premium maximum.")
        st.stop()
    config = {"premium_low":premium_low,"premium_high":premium_high,"units":int(units),
      "estimated_cost_per_trade":brokerage,"force_exit_enabled":force_exit_enabled,
      "force_exit_time":force_exit_time.strftime("%H:%M"),
      "entry":{"use_supertrend":use_supertrend,"use_rsi":use_rsi,"use_adx":use_adx,
      "use_bollinger":use_bollinger,"use_williams":use_williams,"rsi_length":int(rsi_length),
      "rsi_level":rsi_level,"adx_length":int(adx_length),"adx_max":adx_max,
      "williams_length":int(williams_length),"williams_level":williams_level,
      "supertrend_length":int(st_length),"supertrend_factor":float(st_factor),
      "bb_length":int(bb_length),"bb_factor":float(bb_factor)},
      "exit":{"supertrend_length":int(exit_st_length),"supertrend_factor":float(exit_st_factor)}}
    try:
        data = add_ce_indicators(raw, config)
        result = run_ce_backtest(data, config)
    except Exception as exc:
        st.exception(exc)
        st.stop()
    s = result["summary"]
    m1,m2,m3,m4,m5 = st.columns(5)
    m1.metric("Trades",s["trades"])
    m2.metric("Win rate",f'{s["win_rate_pct"]:.2f}%')
    m3.metric("Net P&L",f'₹{s["net_pnl_rupees"]:.2f}')
    m4.metric("Average / trade",f'₹{s["avg_pnl_rupees"]:.2f}')
    m5.metric("Max drawdown",f'₹{s["max_drawdown_rupees"]:.2f}')
    cd = result["data"].tail(500)
    fig = go.Figure([go.Candlestick(x=cd.timestamp,open=cd.open,high=cd.high,low=cd.low,close=cd.close,name="CE premium")])
    fig.add_trace(go.Scatter(x=cd.timestamp,y=cd.entry_supertrend,name="Entry ST"))
    fig.add_trace(go.Scatter(x=cd.timestamp,y=cd.exit_supertrend,name="Exit ST"))
    fig.update_layout(height=540,xaxis_rangeslider_visible=False,template="plotly_dark",margin=dict(l=10,r=10,t=25,b=10))
    st.plotly_chart(fig,use_container_width=True)
    trades = result["trades"]
    st.subheader("5. Trade log")
    if trades.empty:
        st.info("No trades met all enabled conditions and premium filters.")
    else:
        st.dataframe(trades,use_container_width=True,hide_index=True)
        st.download_button("Download trade log CSV",trades.to_csv(index=False).encode(),"ce_positional_trade_log.csv","text/csv")
    st.download_button("Download indicator data CSV",result["data"].to_csv(index=False).encode(),"ce_indicator_data.csv","text/csv")
st.divider()
st.caption("Candle-based simulated fills are estimates, not guaranteed executable prices. No broker orders are placed.")
