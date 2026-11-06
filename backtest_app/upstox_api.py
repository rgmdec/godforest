"""Upstox connector boundary. No order-placement methods are provided."""
import os
import requests

class UpstoxClient:
    BASE_URL="https://api.upstox.com"
    def __init__(self,access_token=None):
        self.access_token=access_token or os.getenv("UPSTOX_ACCESS_TOKEN")
        if not self.access_token:
            raise ValueError("Set UPSTOX_ACCESS_TOKEN in Codespaces secrets/environment.")
    def _headers(self):
        return {"Accept":"application/json","Authorization":f"Bearer {self.access_token}"}
    def verify_profile(self):
        response=requests.get(f"{self.BASE_URL}/v2/user/profile",headers=self._headers(),timeout=20)
        response.raise_for_status()
        return response.json()
    def historical_candles(self,*args,**kwargs):
        raise NotImplementedError("Historical V3 endpoint, instrument-key encoding and API date limits must be verified before enabling.")
    def expired_option_candles(self,*args,**kwargs):
        raise NotImplementedError("Verify expired-option endpoint and account entitlement before enabling historical option retrieval.")
    def start_market_data_stream(self,*args,**kwargs):
        raise NotImplementedError("Implement only after verifying current WebSocket V3 authorization, Protobuf schema and feed entitlements.")
