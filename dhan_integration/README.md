# Dhan historical-data integration (paper research only)

This module downloads historical market data from DhanHQ into local Parquet files. It contains **no order-placement code**.

## Coverage and important limitations

- Dhan's intraday historical API supports 1, 5, 15, 25 and 60-minute bars, up to the latest five years, with a maximum 90-day range per request.
- Dhan's rolling expired-options API supports 1, 5, 15, 25 and 60-minute data, up to the latest five years, with a maximum 30-day range per request. It returns rolling ATM-relative strikes (index options up to ATM +/- 10 near expiry).
- The requested period 2021-01-01 through 2026-11-18 is wider than a rolling five-year window. The API cannot be assumed to return all of 2021; the downloader records actual returned coverage.
- **Expired futures intraday history is not available** through Dhan's intraday API. It returns active contracts only. To backtest old futures contracts, obtain a separate historical source or use daily continuous futures where appropriate.
- Rolling ATM-relative options are not a permanent-contract archive. They are useful for research but do not guarantee every historical strike/expiry or exact contract continuity.

Official docs:
- https://dhanhq.co/docs/v2/authentication/
- https://dhanhq.co/docs/v2/historical-data/
- https://dhanhq.co/docs/v2/expired-options-data/
- https://dhanhq.co/docs/v2/instruments/

## 1. Configure secrets in Codespaces

Add a Codespaces secret named `DHAN_ACCESS_TOKEN` containing the token generated in Dhan Web. Restart/reload the Codespace after adding a secret.

For local testing only, you may create a root `.env` file (never commit it). The client reads environment variables; it does not print or persist tokens. Dhan access tokens generated from Dhan Web are valid for 24 hours. The module validates tokens using the read-only GET /profile endpoint. Renew a still-active Web-generated token using Dhan's RenewToken API if desired, or generate a new token and update the Codespaces secret. The profile response also reports dataPlan and dataValidity.

The data endpoints require the Dhan Data APIs entitlement. Check the Data APIs subscription in your Dhan account.

## 2. Install

```bash
pip install -r dhan_integration/requirements.txt
```

## 3. Test authentication

```bash
python -m dhan_integration.cli --test-auth
```

## 4. Download Nifty 50 spot (minute bars)

```bash
python -m dhan_integration.cli spot --from 2021-01-01 --to 2026-11-18 --interval 1
```

Nifty 50 index mapping is configured as security ID 13 / IDX_I / INDEX. Verify against the latest Dhan instrument/security list if Dhan changes its mapping.

## 5. Download rolling expired Nifty options

Example for weekly ATM and ATM +/- 1 through +/- 10, calls and puts:

```bash
python -m dhan_integration.cli options --from 2021-01-01 --to 2026-11-18 --interval 1 --expiry-flag WEEK --expiry-code 1 --max-strike-offset 10
```

Run monthly separately if required:

```bash
python -m dhan_integration.cli options --from 2021-01-01 --to 2026-11-18 --interval 1 --expiry-flag MONTH --expiry-code 1 --max-strike-offset 10
```

Each request is split into non-overlapping 30-day windows. Both CALL and PUT are downloaded. Data is partitioned by instrument, option type, expiry flag/code and strike offset. The `strike` column returned by Dhan is the actual strike price; `strike_offset` is the ATM-relative request.

## 6. Download active Nifty futures only

First obtain the current contract's security ID from Dhan's instrument list. Then:

```bash
python -m dhan_integration.cli futures --security-id YOUR_ACTIVE_FUTIDX_SECURITY_ID --from 2026-08-20 --to 2026-11-18 --interval 1
```

This is **not** an expired-futures downloader. Dhan states intraday historical data is available only for active contracts; expired futures intraday history is not provided.

## Output

Files are written under `data/dhan/` in Parquet format, with CSV fallback if Parquet support is unavailable. Raw API payloads are not stored. Re-running a date range replaces duplicate timestamps during merge.

## Safety

- No Dhan order endpoints are implemented or called.
- Do not put credentials in source files, command-line arguments, notebooks, screenshots or Git.
- Do not commit downloaded market data unless you have checked your data-provider licence.
