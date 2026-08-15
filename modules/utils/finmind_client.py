# modules/utils/finmind_client.py
"""
FinMind API 薄封裝（台股專用）
- 讀取環境變數 FINMIND_TOKEN（可放 GitHub Secrets）
- 提供財報、資產負債、股利、股價
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests

BASE_URL = "https://api.finmindtrade.com/api/v4/data"


class FinMindError(Exception):
    pass


class FinMindClient:
    def __init__(self, token: Optional[str] = None, timeout: int = 30):
        self.token = (
            token
            or os.getenv("FINMIND_TOKEN")
            or os.getenv("FINMIND_API_TOKEN")
            or os.getenv("FINMIND_API_KEY")
        )
        self.timeout = timeout

    def _get(self, dataset: str, data_id: str, start_date: str, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "dataset": dataset,
            "data_id": data_id,
            "start_date": start_date,
        }
        if end_date:
            params["end_date"] = end_date
        if self.token:
            params["token"] = self.token

        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            resp = requests.get(BASE_URL, params=params, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as e:
            raise FinMindError(f"FinMind 網路錯誤 ({dataset}): {e}") from e

        if isinstance(payload, dict):
            status = payload.get("status")
            msg = payload.get("msg") or payload.get("message")
            if status not in (None, 200, "success", "ok") and msg:
                if not payload.get("data"):
                    raise FinMindError(f"FinMind API 錯誤 ({dataset}): {msg}")
            data = payload.get("data")
            if data is None:
                raise FinMindError(f"FinMind 無資料 ({dataset}): {msg or payload}")
            return data
        raise FinMindError(f"FinMind 回傳格式異常 ({dataset})")

    def financial_statements(self, stock_id: str, start_date: str = "2015-01-01") -> List[Dict]:
        return self._get("TaiwanStockFinancialStatements", stock_id, start_date)

    def balance_sheet(self, stock_id: str, start_date: str = "2015-01-01") -> List[Dict]:
        return self._get("TaiwanStockBalanceSheet", stock_id, start_date)

    def dividend(self, stock_id: str, start_date: str = "2015-01-01") -> List[Dict]:
        return self._get("TaiwanStockDividend", stock_id, start_date)

    def price(self, stock_id: str, start_date: str = "2020-01-01", end_date: Optional[str] = None) -> List[Dict]:
        return self._get("TaiwanStockPrice", stock_id, start_date, end_date)

    def stock_info(self) -> List[Dict]:
        params: Dict[str, Any] = {"dataset": "TaiwanStockInfo"}
        if self.token:
            params["token"] = self.token
            headers = {"Authorization": f"Bearer {self.token}"}
        else:
            headers = {}
        try:
            resp = requests.get(BASE_URL, params=params, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json().get("data") or []
        except Exception as e:
            raise FinMindError(f"FinMind stock_info 失敗: {e}") from e


def has_finmind_token() -> bool:
    return bool(
        os.getenv("FINMIND_TOKEN")
        or os.getenv("FINMIND_API_TOKEN")
        or os.getenv("FINMIND_API_KEY")
    )
