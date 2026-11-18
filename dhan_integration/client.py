"""Minimal, data-only DhanHQ v2 REST client."""
from __future__ import annotations

import os
from typing import Any

import requests


BASE_URL = "https://api.dhan.co/v2"


class DhanAPIError(RuntimeError):
    """Raised when Dhan returns an HTTP or API error."""


class DhanClient:
    def __init__(self, access_token: str | None = None, timeout: int = 60):
        token = access_token or os.getenv("DHAN_ACCESS_TOKEN")
        if not token:
            raise ValueError(
                "DHAN_ACCESS_TOKEN is not set. Add it as a Codespaces secret "
                "or environment variable; never hard-code it."
            )
        self._session = requests.Session()
        self._session.headers.update({
            "access-token": token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        self.timeout = timeout

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        # Only data endpoints are intentionally exposed in this client.
        if endpoint not in {"/charts/intraday", "/charts/rollingoption"}:
            raise ValueError("This client permits data endpoints only.")
        response = self._session.post(
            BASE_URL + endpoint, json=payload, timeout=self.timeout
        )
        if response.status_code in (401, 403):
            raise DhanAPIError(
                f"Dhan authentication/permission failed ({response.status_code}). "
                "Renew the access token and verify the Data APIs subscription."
            )
        if not response.ok:
            detail = response.text[:1000]
            raise DhanAPIError(f"Dhan HTTP {response.status_code}: {detail}")
        try:
            body = response.json()
        except ValueError as exc:
            raise DhanAPIError("Dhan returned a non-JSON response.") from exc
        if isinstance(body, dict) and str(body.get("status", "")).lower() in {
            "failure", "failed", "error"
        }:
            raise DhanAPIError(f"Dhan API error: {body.get('remarks', body)}")
        return body

    def test_auth(self) -> bool:
        # A small, bounded data request verifies token + data permission.
        from datetime import date, timedelta
        end = date.today()
        start = end - timedelta(days=2)
        payload = {
            "securityId": "13",
            "exchangeSegment": "IDX_I",
            "instrument": "INDEX",
            "interval": "1",
            "oi": False,
            "fromDate": start.strftime("%Y-%m-%d 09:15:00"),
            "toDate": end.strftime("%Y-%m-%d 15:30:00"),
        }
        self._post("/charts/intraday", payload)
        return True

    def intraday(
        self, security_id: str, exchange_segment: str, instrument: str,
        start: str, end: str, interval: int = 1, oi: bool = False,
    ) -> dict[str, Any]:
        if interval not in (1, 5, 15, 25, 60):
            raise ValueError("interval must be one of 1, 5, 15, 25, 60")
        payload = {
            "securityId": str(security_id),
            "exchangeSegment": exchange_segment,
            "instrument": instrument,
            "interval": str(interval),
            "oi": bool(oi),
            "fromDate": start,
            "toDate": end,
        }
        return self._post("/charts/intraday", payload)

    def rolling_options(
        self, start: str, end: str, option_type: str, strike: str,
        expiry_flag: str, expiry_code: int, interval: int = 1,
    ) -> dict[str, Any]:
        if option_type not in ("CALL", "PUT"):
            raise ValueError("option_type must be CALL or PUT")
        if expiry_flag not in ("WEEK", "MONTH"):
            raise ValueError("expiry_flag must be WEEK or MONTH")
        if interval not in (1, 5, 15, 25, 60):
            raise ValueError("interval must be one of 1, 5, 15, 25, 60")
        if expiry_code not in (0, 1, 2, 3):
            raise ValueError("expiry_code must be 0, 1, 2 or 3")
        payload = {
            "exchangeSegment": "NSE_FNO",
            "interval": str(interval),
            "securityId": "13",
            "instrument": "OPTIDX",
            "expiryFlag": expiry_flag,
            "expiryCode": expiry_code,
            "strike": strike,
            "drvOptionType": option_type,
            "requiredData": [
                "open", "high", "low", "close", "volume",
                "oi", "iv", "strike", "spot"
            ],
            "fromDate": start,
            "toDate": end,
        }
        return self._post("/charts/rollingoption", payload)
