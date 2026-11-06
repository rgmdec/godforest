# Nifty Backtest Pro

Streamlit/Python research dashboard for Nifty option strategy development.

## First-build scope

- CE_STGY BUILDER – Positional.
- All entry indicators calculated on selected CE option OHLC candles.
- Entry: Supertrend (10,2) bullish; RSI(14) > 70; ADX(12) < 35;
  close above Bollinger upper band (20,2); Williams %R(14) > -8.
- Exit: option candle closes below Supertrend (10,2).
- Paper-only simulation; no order placement.
- CSV input for validating calculations before Upstox integration.

## Run in Codespaces

From repository root:

    cd backtest_app
    pip install -r requirements.txt
    streamlit run app.py --server.address 0.0.0.0

## CSV columns

Required: timestamp, open, high, low, close
Optional: volume, instrument_key, symbol

Upload one selected CE contract at a time. Do not combine multiple strikes/contracts in one CSV; automatic historical contract selection is a later integration step.

## Upstox integration status

upstox_api.py provides a token-profile verification method and explicit placeholders for historical candles, expired options and WebSocket V3. Those market-data features are not operational in this first build. Verify API entitlement and current official endpoint/schema before enabling them.

Set UPSTOX_ACCESS_TOKEN as a Codespaces secret or environment variable. Never commit access tokens, client secrets or .env files.

## Fill assumptions

- Signal on completed candle.
- Entry at next candle open.
- Exit at close of candle that closes below exit Supertrend.
- If data ends with an open position, close at final candle.
- Candle-based fills are estimates. Slippage, spread, lot size, taxes and exact historical contract selection still need modelling.
