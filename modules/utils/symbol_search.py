# modules/utils/symbol_search.py
"""
股票代號搜尋工具
- 台股：TWSE 開放 API（快速、免金鑰）+ FinMind fallback + yfinance fallback
- 美股/全球：Twelve Data symbol_search + yfinance fallback
自動依查詢語言/格式判斷優先來源
"""
from __future__ import annotations

import re
import requests
from typing import List, Dict


# ---------- 判斷是否為台股查詢 ----------

def _is_tw_query(query: str) -> bool:
    """純數字 or 含中文 → 視為台股查詢"""
    q = query.strip()
    if re.fullmatch(r"\d{2,6}", q):
        return True
    if re.search(r"[\u4e00-\u9fff]", q):
        return True
    return False


# ---------- TWSE 開放 API 搜尋（台股主力，免金鑰） ----------

_TWSE_CACHE: List[Dict] = []

def _get_twse_list() -> List[Dict]:
    """取得 TWSE + TPEx 全部上市上櫃股票清單，快取於模組層級。"""
    global _TWSE_CACHE
    if _TWSE_CACHE:
        return _TWSE_CACHE

    results = []
    # 上市
    try:
        r = requests.get(
            "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
            timeout=8,
        )
        r.raise_for_status()
        for item in r.json():
            code = item.get("Code", "")
            name = item.get("Name", "")
            if code and name:
                results.append({"symbol": code, "name": name, "exchange": "TWSE"})
    except Exception:
        pass

    # 上櫃
    try:
        r = requests.get(
            "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
            timeout=8,
        )
        r.raise_for_status()
        for item in r.json():
            code = item.get("SecuritiesCompanyCode", "")
            name = item.get("CompanyName", "")
            if code and name:
                results.append({"symbol": code, "name": name, "exchange": "TPEx"})
    except Exception:
        pass

    _TWSE_CACHE = results
    return results


def _search_twse(query: str, max_results: int = 8) -> List[Dict]:
    """在 TWSE/TPEx 清單中模糊比對代號或名稱。"""
    q = query.strip().lower()
    matched = []
    try:
        for item in _get_twse_list():
            code = item["symbol"].lower()
            name = item["name"].lower()
            if q in code or q in name:
                matched.append({
                    "symbol": item["symbol"],
                    "name": item["name"],
                    "exchange": item["exchange"],
                    "type": "股票",
                    "source": "TWSE/TPEx",
                })
            if len(matched) >= max_results:
                break
    except Exception:
        pass
    return matched


# ---------- FinMind 台股清單搜尋（fallback） ----------

def _search_finmind_tw(query: str, max_results: int = 8) -> List[Dict]:
    try:
        from modules.utils.finmind_client import FinMindClient, has_finmind_token
        if not has_finmind_token():
            return []
        client = FinMindClient()
        resp = requests.get(
            "https://api.finmindtrade.com/api/v4/data",
            params={"dataset": "TaiwanStockInfo", "token": client.token},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        q = query.strip().lower()
        matched = []
        for item in data:
            code = str(item.get("stock_id", "")).lower()
            name = str(item.get("stock_name", "")).lower()
            if q in code or q in name:
                matched.append({
                    "symbol": item.get("stock_id", ""),
                    "name": item.get("stock_name", ""),
                    "exchange": "TWSE/TPEx",
                    "type": "股票",
                    "source": "FinMind",
                })
            if len(matched) >= max_results:
                break
        return matched
    except Exception:
        return []


# ---------- yfinance 搜尋 ----------

def _search_yfinance(query: str, max_results: int = 8) -> List[Dict]:
    try:
        import yfinance as yf
        result = yf.Search(query, max_results=max_results, enable_fuzzy_query=True)
        quotes = result.quotes if hasattr(result, "quotes") else []
        out = []
        for q in quotes:
            symbol = q.get("symbol", "")
            if not symbol:
                continue
            out.append({
                "symbol": symbol,
                "name": q.get("longname") or q.get("shortname") or symbol,
                "exchange": q.get("exchange", ""),
                "type": q.get("quoteType", ""),
                "source": "yfinance",
            })
        return out
    except Exception:
        return []


# ---------- Twelve Data 搜尋 ----------

def _search_twelve(query: str, max_results: int = 8) -> List[Dict]:
    try:
        from modules.utils.twelve_client import TwelveDataClient, has_twelve_data_key
        if not has_twelve_data_key():
            return []
        client = TwelveDataClient()
        raw = client.search_symbol(query, outputsize=max_results)
        out = []
        for item in raw:
            symbol = item.get("symbol", "")
            if not symbol:
                continue
            out.append({
                "symbol": symbol,
                "name": item.get("instrument_name", symbol),
                "exchange": item.get("exchange", ""),
                "type": item.get("instrument_type", ""),
                "source": "TwelveData",
            })
        return out
    except Exception:
        return []


# ---------- 主入口 ----------

def search_symbols(query: str, max_results: int = 8) -> List[Dict]:
    """
    統一搜尋入口。
    - 台股查詢（數字 or 中文）：TWSE/TPEx → FinMind → yfinance
    - 美股/全球查詢：Twelve Data → yfinance
    """
    query = query.strip()
    if not query:
        return []

    results: List[Dict] = []
    seen: set = set()

    def add(items):
        for item in items:
            sym = item["symbol"]
            if sym not in seen:
                seen.add(sym)
                results.append(item)

    if _is_tw_query(query):
        add(_search_twse(query, max_results))
        if len(results) < max_results:
            add(_search_finmind_tw(query, max_results))
        if len(results) < max_results:
            add(_search_yfinance(query, max_results))
    else:
        add(_search_twelve(query, max_results))
        if len(results) < max_results:
            add(_search_yfinance(query, max_results))

    return results[:max_results]
