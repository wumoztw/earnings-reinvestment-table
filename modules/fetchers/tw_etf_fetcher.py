# modules/fetchers/tw_etf_fetcher.py
"""台灣 ETF 資料擷取器 - 使用 yfinance

重要修正：
- history(auto_adjust=False) 取得原始價格
- 總報酬計算時明確加上現金配息，避免與 auto_adjust 重複計算
- 磁碟快取 6 小時
"""
import yfinance as yf
import pandas as pd
from core.interfaces import BaseEtfFetcher
from core.schemas import EtfData
from modules.fetchers.etf_registry import (
    get_etf_info, get_yfinance_symbol
)
from modules.utils.cache import cached


class TwEtfFetcher(BaseEtfFetcher):
    """台灣 ETF 資料擷取器
    
    使用 yfinance 取得:
    - 歷史價格 (OHLCV，原始未調整)
    - 配息紀錄 (Dividends)
    - 基本資訊 (Info)
    """

    @cached("etf_fetch", ttl=6*3600)
    def fetch(self, symbol: str) -> EtfData:
        clean_symbol = symbol.upper().strip().replace(".TW", "").replace(".TWO", "")
        yf_symbol = get_yfinance_symbol(clean_symbol)
        
        ticker = yf.Ticker(yf_symbol)

        price_history = ticker.history(period="10y", auto_adjust=False)
        if price_history.empty:
            raise ValueError(f"無法取得 ETF {clean_symbol} 的歷史價格資料，請確認代號是否正確。")
        
        price_history = price_history.dropna(subset=["Close"])

        if price_history.index.tz is not None:
            price_history.index = price_history.index.tz_localize(None)

        dividends = ticker.dividends
        div_df = pd.DataFrame()
        if not dividends.empty:
            div_df = pd.DataFrame({
                "date": dividends.index,
                "amount": dividends.values,
            })
            div_df["date"] = pd.to_datetime(div_df["date"])
            if div_df["date"].dt.tz is not None:
                div_df["date"] = div_df["date"].dt.tz_localize(None)
            div_df = div_df.sort_values("date").reset_index(drop=True)

        try:
            info = ticker.info or {}
        except Exception:
            info = {}

        name = info.get("shortName") or info.get("longName") or ""
        if not name:
            reg = get_etf_info(clean_symbol)
            name = reg.get("name", clean_symbol)

        try:
            current_price = float(ticker.fast_info.last_price or 0.0)
        except Exception:
            current_price = float(price_history["Close"].iloc[-1]) if not price_history.empty else 0.0

        nav = info.get("navPrice", None)
        if nav is not None:
            try:
                nav = float(nav)
            except (TypeError, ValueError):
                nav = None

        premium_discount = None
        if nav and nav > 0 and current_price > 0:
            premium_discount = round((current_price - nav) / nav * 100, 2)

        expense_ratio = info.get("annualReportExpenseRatio", None)
        if expense_ratio and expense_ratio > 0:
            try:
                expense_ratio = round(float(expense_ratio) * 100, 2)
            except (TypeError, ValueError):
                expense_ratio = None

        aum = info.get("totalAssets", None)
        if aum is not None:
            try:
                aum = float(aum)
            except (TypeError, ValueError):
                aum = None

        reg = get_etf_info(clean_symbol)
        category = reg.get("category", "其他")

        market = "TWO" if ".TWO" in yf_symbol else "TW"

        return EtfData(
            symbol=clean_symbol,
            name=name,
            market=market,
            current_price=current_price,
            nav=nav,
            premium_discount=premium_discount,
            expense_ratio=expense_ratio,
            aum=aum,
            category=category,
            dividends=div_df,
            price_history=price_history,
        )
