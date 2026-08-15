# modules/utils/symbol_search.py
"""
股票代號搜尋工具
- 台股：FinMind 股票清單 + yfinance fallback
- 美股/全球：Twelve Data symbol_search + yfinance fallback
自動依查詢語言/格式判斷優先來源
"""
from __future__ import annotations

import re
from typing import List, Dict

# ---------- 判斷是否為台股查詢 ----------

def _is_tw_query(query: str) -> bool:
    """純數字 or 含中文 → 視為台股查詢"""
    q = query.strip()
    if re.fullmatch(r"\d{4,6}", q):
        return True
    if re.search(r"[\u4e00-\u9fff]", q):
        return True
    return False


# ---------- yfinance 搜尋 ----------

def _search_yfinance(query: str, max_results: int = 8) -> List[Dict]:
    """
    使用 yfinance.Search 搜尋，回傳標準化 dict list。
    每筆: {symbol, name, exchange, type, source}
    """
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
    """使用 TwelveDataClient.search_symbol，回傳標準化 dict list。"""
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


# ---------- FinMind 台股清單搜尋 ----------

def _search_finmind_tw(query: str, max_results: int = 8) -> List[Dict]:
    """
    呼叫 FinMind /taiwan_stock_info 取得台股清單，
    依代號或公司名稱模糊比對。
    """
    try:
        from modules.utils.finmind_client import FinMindClient, has_finmind_token
        if not has_finmind_token():
            return []
        client = FinMindClient()
        token = client.token
        import requests
        resp = requests.get(
            "https://api.finmindtrade.com/api/v4/data",
            params={
                "dataset": "TaiwanStockInfo",
                "token": token,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        q = query.strip().lower()
        matched = []
        for item in data:
            code = str(item.get("stock_id", ""))
            name = str(item.get("stock_name", ""))
            if q in code.lower() or q in name.lower():
                matched.append({
                    "symbol": code,
                    "name": name,
                    "exchange": "TWSE/TPEx",
                    "type": "股票",
                    "source": "FinMind",
                })
            if len(matched) >= max_results:
                break
        return matched
    except Exception:
        return []


# ---------- 主入口 ----------

def search_symbols(query: str, max_results: int = 8) -> List[Dict]:
    """
    統一搜尋入口。
    - 台股查詢（數字 or 中文）：FinMind → yfinance
    - 美股/全球查詢：Twelve Data → yfinance
    去重後回傳，欄位統一為 {symbol, name, exchange, type, source}
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
        add(_search_finmind_tw(query, max_results))
        if len(results) < max_results:
            add(_search_yfinance(query, max_results))
    else:
        add(_search_twelve(query, max_results))
        if len(results) < max_results:
            add(_search_yfinance(query, max_results))

    return results[:max_results]
