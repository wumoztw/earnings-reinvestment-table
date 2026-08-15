# modules/utils/twelve_client.py
"""
Twelve Data API 薄封裝
- 從環境變數讀取 TWELVEDATA_API_KEY（對應 GitHub Secrets）
- 提供 time_series、quote、profile、statistics、dividends、
  income_statement、balance_sheet 等常用端點
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests

BASE_URL = "https://api.twelvedata.com"


class TwelveDataError(Exception):
    pass


class TwelveDataClient:
    def __init__(self, apikey: Optional[str] = None, timeout: int = 20):
        self.apikey = apikey or os.getenv("TWELVEDATA_API_KEY") or os.getenv("TWELVE_DATA_API_KEY")
        self.timeout = timeout
        if not self.apikey:
            raise TwelveDataError(
                "找不到 TWELVEDATA_API_KEY。請設定環境變數或 GitHub Secret。"
            )

    def _get(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        params = {k: v for k, v in params.items() if v is not None}
        params["apikey"] = self.apikey
        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise TwelveDataError(f"Twelve Data 網路錯誤 ({endpoint}): {e}") from e

        if isinstance(data, dict):
            status = data.get("status")
            code = data.get("code")
            msg = data.get("message") or data.get("status")
            if status == "error" or (code and int(code) >= 400):
                raise TwelveDataError(f"Twelve Data API 錯誤 ({endpoint}): {msg or data}")
        return data

    def quote(self, symbol: str, exchange: Optional[str] = None, country: Optional[str] = None) -> Dict:
        return self._get("quote", {"symbol": symbol, "exchange": exchange, "country": country})

    def price(self, symbol: str, exchange: Optional[str] = None, country: Optional[str] = None) -> float:
        data = self._get("price", {"symbol": symbol, "exchange": exchange, "country": country})
        return float(data.get("price", 0) or 0)

    def time_series(
        self,
        symbol: str,
        interval: str = "1day",
        outputsize: int = 5000,
        exchange: Optional[str] = None,
        country: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        adjust: str = "none",
    ) -> Dict:
        return self._get(
            "time_series",
            {
                "symbol": symbol,
                "interval": interval,
                "outputsize": outputsize,
                "exchange": exchange,
                "country": country,
                "start_date": start_date,
                "end_date": end_date,
                "adjust": adjust,
            },
        )

    def profile(self, symbol: str, exchange: Optional[str] = None, country: Optional[str] = None) -> Dict:
        return self._get("profile", {"symbol": symbol, "exchange": exchange, "country": country})

    def statistics(self, symbol: str, exchange: Optional[str] = None, country: Optional[str] = None) -> Dict:
        return self._get("statistics", {"symbol": symbol, "exchange": exchange, "country": country})

    def dividends(
        self,
        symbol: str,
        exchange: Optional[str] = None,
        country: Optional[str] = None,
        range_: str = "full",
    ) -> Dict:
        return self._get(
            "dividends",
            {"symbol": symbol, "exchange": exchange, "country": country, "range": range_},
        )

    def income_statement(
        self,
        symbol: str,
        period: str = "annual",
        outputsize: int = 8,
        exchange: Optional[str] = None,
        country: Optional[str] = None,
    ) -> Dict:
        return self._get(
            "income_statement",
            {
                "symbol": symbol,
                "period": period,
                "outputsize": outputsize,
                "exchange": exchange,
                "country": country,
            },
        )

    def balance_sheet(
        self,
        symbol: str,
        period: str = "annual",
        outputsize: int = 8,
        exchange: Optional[str] = None,
        country: Optional[str] = None,
    ) -> Dict:
        return self._get(
            "balance_sheet",
            {
                "symbol": symbol,
                "period": period,
                "outputsize": outputsize,
                "exchange": exchange,
                "country": country,
            },
        )


def has_twelve_data_key() -> bool:
    return bool(os.getenv("TWELVEDATA_API_KEY") or os.getenv("TWELVE_DATA_API_KEY"))
