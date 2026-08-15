import os
import requests
import pandas as pd
from typing import Optional, Dict, Any

try:
    import streamlit as st
except ImportError:
    st = None


def _get_finmind_token() -> Optional[str]:
    """
    依序嘗試由環境變數 (os.getenv) 與 Streamlit secrets (st.secrets)
    讀取 FinMind Token，支援以下 key 名稱（按優先順序）：
    1. FINMIND_TOKEN
    2. FINMIND_API_TOKEN
    3. FINMIND_API_KEY
    """
    keys = ["FINMIND_TOKEN", "FINMIND_API_TOKEN", "FINMIND_API_KEY"]

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


def has_finmind_token() -> bool:
    """檢查是否存在可用的 FinMind Token"""
    return _get_finmind_token() is not None


class FinMindClient:
    def __init__(self, token: Optional[str] = None):
        self.token = token or _get_finmind_token()
        self.base_url = "https://api.finmindtrade.com/api/v4/data"

    def get_data(self, dataset: str, data_id: str, start_date: str, end_date: Optional[str] = None) -> pd.DataFrame:
        params: Dict[str, Any] = {
            "dataset": dataset,
            "data_id": data_id,
            "start_date": start_date,
        }
        if end_date:
            params["end_date"] = end_date
        if self.token:
            params["token"] = self.token

        response = requests.get(self.base_url, params=params)
        response.raise_for_status()
        data = response.json()

        if data.get("status") == 200 and "data" in data:
            return pd.DataFrame(data["data"])
        return pd.DataFrame()
