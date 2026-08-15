import os
import requests
import pandas as pd
from typing import Optional, Dict, Any

try:
    import streamlit as st
except ImportError:
    st = None


class TwelveDataError(Exception):
    pass


def _get_twelve_key() -> Optional[str]:
    """
    依序嘗試由環境變數 (os.getenv) 與 Streamlit secrets (st.secrets)
    讀取 Twelve Data API Key，支援以下 key 名稱（按優先順序）：
    1. TWELVEDATA_API_KEY
    2. TWELVE_DATA_API_KEY
    """
    keys = ["TWELVEDATA_API_KEY", "TWELVE_DATA_API_KEY"]

    # 1. 嘗試從環境變數讀取
    for key in keys:
        val = os.getenv(key)
        if val:
            return val

    # 2. 嘗試從 st.secrets 讀取 (避免非 Streamlit 環境報錯)
    if st is not None:
        try:
            for key in keys:
                if key in st.secrets:
                    val = st.secrets[key]
                    if val:
                        return str(val)
        except Exception:
            pass

    return None


def has_twelve_data_key() -> bool:
    """檢查是否存在可用的 Twelve Data API Key"""
    return _get_twelve_key() is not None


class TwelveDataClient:
    def __init__(self, apikey: Optional[str] = None):
        self.apikey = apikey or _get_twelve_key()
        self.base_url = "https://api.twelvedata.com"

    def get_time_series(self, symbol: str, interval: str = "1day", outputsize: int = 30) -> pd.DataFrame:
        url = f"{self.base_url}/time_series"
        params: Dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
        }
        if self.apikey:
            params["apikey"] = self.apikey

        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if "values" in data:
            df = pd.DataFrame(data["values"])
            return df
        return pd.DataFrame()

    def _fetch_financials(self, endpoint: str, symbol: str, period: str = "annual",
                          outputsize: int = 8, exchange: Optional[str] = None,
                          country: Optional[str] = None) -> Dict[str, Any]:
        """通用財報請求，回傳原始 JSON dict。"""
        url = f"{self.base_url}/{endpoint}"
        params: Dict[str, Any] = {
            "symbol": symbol,
            "period": period,
            "outputsize": outputsize,
        }
        if exchange:
            params["exchange"] = exchange
        if country:
            params["country"] = country
        if self.apikey:
            params["apikey"] = self.apikey

        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()

        if data.get("status") == "error":
            raise TwelveDataError(f"Twelve Data [{endpoint}] 錯誤：{data.get('message', data)}")
        return data

    def income_statement(self, symbol: str, period: str = "annual",
                         outputsize: int = 8, exchange: Optional[str] = None,
                         country: Optional[str] = None) -> Dict[str, Any]:
        """取得損益表，回傳含 income_statement list 的 dict。"""
        return self._fetch_financials("income_statement", symbol, period, outputsize, exchange, country)

    def balance_sheet(self, symbol: str, period: str = "annual",
                      outputsize: int = 8, exchange: Optional[str] = None,
                      country: Optional[str] = None) -> Dict[str, Any]:
        """取得資產負債表，回傳含 balance_sheet list 的 dict。"""
        return self._fetch_financials("balance_sheet", symbol, period, outputsize, exchange, country)

    def search_symbol(self, query: str, outputsize: int = 10) -> list:
        """
        搜尋股票代號，回傳 list of dict，每筆含：
        symbol, instrument_name, exchange, country, type
        """
        url = f"{self.base_url}/symbol_search"
        params: Dict[str, Any] = {"symbol": query, "outputsize": outputsize}
        if self.apikey:
            params["apikey"] = self.apikey
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("status") == "error":
                return []
            return data.get("data", [])
        except Exception:
            return []
