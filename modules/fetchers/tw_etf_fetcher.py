# modules/fetchers/tw_etf_fetcher.py
"""台灣 ETF 資料擷取器 - 使用 yfinance"""
import yfinance as yf
import pandas as pd
from core.interfaces import BaseEtfFetcher
from core.schemas import EtfData
from modules.fetchers.etf_registry import (
    get_etf_info, get_yfinance_symbol, is_tw_etf
)


class TwEtfFetcher(BaseEtfFetcher):
    """台灣 ETF 資料擷取器
    
    使用 yfinance 取得:
    - 歷史價格 (OHLCV)
    - 配息紀錄 (Dividends)
    - 基本資訊 (Info)
    """

    def fetch(self, symbol: str) -> EtfData:
        clean_symbol = symbol.upper().strip().replace(".TW", "").replace(".TWO", "")
        yf_symbol = get_yfinance_symbol(clean_symbol)
        
        ticker = yf.Ticker(yf_symbol)

        # 1. 取得歷史價格 (最多 10 年)
        price_history = ticker.history(period="10y", auto_adjust=True)
        if price_history.empty:
            raise ValueError(f"無法取得 ETF {clean_symbol} 的歷史價格資料，請確認代號是否正確。")
        
        # 移除收盤價為 NaN 的不完整交易日 (如盤中未結算)
        price_history = price_history.dropna(subset=["Close"])

        # 2. 取得配息歷史
        dividends = ticker.dividends
        div_df = pd.DataFrame()
        if not dividends.empty:
            div_df = pd.DataFrame({
                "date": dividends.index,
                "amount": dividends.values,
            })
            div_df["date"] = pd.to_datetime(div_df["date"])
            div_df = div_df.sort_values("date").reset_index(drop=True)

        # 3. 取得基本資訊
        try:
            info = ticker.info
        except Exception:
            info = {}

        name = info.get("shortName") or info.get("longName") or ""
        # 若 yfinance 沒有名稱，從清單取
        if not name:
            reg = get_etf_info(clean_symbol)
            name = reg.get("name", clean_symbol)

        # 目前價格
        try:
            current_price = ticker.fast_info.last_price or 0.0
        except Exception:
            current_price = price_history["Close"].iloc[-1] if not price_history.empty else 0.0

        # NAV (yfinance 對台灣 ETF 通常無法取得)
        nav = info.get("navPrice", None)

        # 折溢價 (若有 NAV 才能計算)
        premium_discount = None
        if nav and nav > 0 and current_price > 0:
            premium_discount = round((current_price - nav) / nav * 100, 2)

        # 總費用率
        expense_ratio = info.get("annualReportExpenseRatio", None)
        if expense_ratio and expense_ratio > 0:
            expense_ratio = round(expense_ratio * 100, 2)  # 轉為百分比

        # 基金規模
        aum = info.get("totalAssets", None)

        # 類別
        reg = get_etf_info(clean_symbol)
        category = reg.get("category", "其他")

        # 市場判斷
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
