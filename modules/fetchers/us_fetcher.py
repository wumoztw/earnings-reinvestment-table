# modules/fetchers/us_fetcher.py
"""
通用個股資料抓取器（台股自動補 .TW，美股直接使用）
強化重點：
- 多組可能的 yfinance 標籤容錯
- 年份對齊（balance_sheet 與 income statement 取交集）
- 避免標量/陣列混用
- 明確處理資料不足情況
- 額外抓取 bookValue / sharesOutstanding 支援淨值估值
"""
import yfinance as yf
import pandas as pd
import numpy as np
from typing import Optional, List
from core.interfaces import BaseFetcher
from core.schemas import StockData


class UniversalFetcher(BaseFetcher):
    """通用抓取器：美股直接輸入 (如 AAPL)，台股自動補綴 .TW (如 2330.TW)"""

    # 可能的科目標籤（依優先順序）
    NET_INCOME_KEYS = [
        "Net Income",
        "Net Income Common Stockholders",
        "Net Income Including Noncontrolling Interests",
        "Net Income Continuous Operations",
    ]
    EQUITY_KEYS = [
        "Stockholders Equity",
        "Total Equity Gross Minority Interest",
        "Common Stock Equity",
        "Total Stockholder Equity",
        "Shareholders Equity",
    ]
    PPE_KEYS = [
        "Net PPE",
        "Gross PPE",
        "Property Plant And Equipment Net",
        "Net Property Plant And Equipment",
        "Property Plant Equipment",
    ]
    LONG_TERM_INVEST_KEYS = [
        "Investments And Advances",
        "Long Term Equity Investment",
        "Long Term Investments",
        "Investment In Financial Assets",
        "Other Long Term Investments",
    ]

    def fetch(self, symbol: str) -> StockData:
        clean = symbol.strip().upper()
        ticker_symbol = f"{clean}.TW" if clean.isdigit() else clean
        ticker = yf.Ticker(ticker_symbol)

        # ── 1. 取得財報 ──
        try:
            bs = ticker.balance_sheet
            inc = ticker.financials
        except Exception as e:
            raise ValueError(f"無法取得 {clean} 的財報資料：{e}")

        if bs is None or bs.empty or inc is None or inc.empty:
            raise ValueError(
                f"股票 {clean} 的資產負債表或損益表為空，可能是代號錯誤、資料尚未公開，"
                "或 yfinance 暫不支援該標的。"
            )

        # ── 2. 對齊共同年份 ──
        bs_years = {col.year: col for col in bs.columns if hasattr(col, "year")}
        inc_years = {col.year: col for col in inc.columns if hasattr(col, "year")}
        common_years = sorted(set(bs_years.keys()) & set(inc_years.keys()))

        if len(common_years) < 2:
            raise ValueError(
                f"股票 {clean} 可用的共同年度財報不足（僅 {len(common_years)} 年），"
                "無法可靠計算盈再率與 ROE 趨勢。"
            )

        years = common_years
        df = pd.DataFrame(index=years)

        # ── 3. 安全提取各科目（多標籤容錯 + 對齊年份） ──
        def _extract_series(source: pd.DataFrame, year_map: dict, keys: List[str]) -> pd.Series:
            """從 source 依優先 keys 取出，並對齊到 common years"""
            for key in keys:
                if key in source.index:
                    raw = source.loc[key]
                    values = []
                    for y in years:
                        col = year_map.get(y)
                        if col is not None and col in raw.index:
                            val = raw[col]
                            values.append(float(val) if pd.notna(val) else np.nan)
                        else:
                            values.append(np.nan)
                    return pd.Series(values, index=years)
            return pd.Series([np.nan] * len(years), index=years)

        df["net_income"] = _extract_series(inc, inc_years, self.NET_INCOME_KEYS)
        df["equity"] = _extract_series(bs, bs_years, self.EQUITY_KEYS)
        df["fixed_assets"] = _extract_series(bs, bs_years, self.PPE_KEYS)
        df["long_term_invest"] = _extract_series(bs, bs_years, self.LONG_TERM_INVEST_KEYS)

        # 填補長期投資缺失為 0（很多公司沒有或很少）
        df["long_term_invest"] = df["long_term_invest"].fillna(0.0)

        df = df.sort_index(ascending=True)

        # ── 4. 資料品質判斷 ──
        required_cols = ["net_income", "equity", "fixed_assets"]
        missing_ratio = df[required_cols].isna().mean().mean()
        if missing_ratio > 0.5:
            data_quality = "insufficient"
        elif missing_ratio > 0.1:
            data_quality = "partial"
        else:
            data_quality = "ok"

        # 至少需要最新一期有 equity 與 net_income
        if pd.isna(df["equity"].iloc[-1]) or pd.isna(df["net_income"].iloc[-1]):
            raise ValueError(
                f"股票 {clean} 最新一期淨利或股東權益缺失，無法進行估值。"
            )

        # ── 5. 價格與名稱、每股淨值 ──
        try:
            info = ticker.info or {}
        except Exception:
            info = {}

        try:
            fast = ticker.fast_info
            price = float(getattr(fast, "last_price", None) or 0.0)
        except Exception:
            price = 0.0
            try:
                hist = ticker.history(period="5d")
                if not hist.empty:
                    price = float(hist["Close"].iloc[-1])
            except Exception:
                pass

        name = (
            info.get("shortName")
            or info.get("longName")
            or info.get("symbol")
            or clean
        )

        book_value_per_share: Optional[float] = None
        shares_outstanding: Optional[float] = None

        bv = info.get("bookValue")
        if bv is not None and bv > 0:
            book_value_per_share = float(bv)

        shares = info.get("sharesOutstanding") or info.get("floatShares")
        if shares is not None and shares > 0:
            shares_outstanding = float(shares)

        if book_value_per_share is None and shares_outstanding and shares_outstanding > 0:
            latest_equity = df["equity"].iloc[-1]
            if pd.notna(latest_equity) and latest_equity > 0:
                book_value_per_share = float(latest_equity) / shares_outstanding

        market = "TW" if clean.isdigit() else "US"

        return StockData(
            symbol=clean,
            name=str(name),
            market=market,
            current_price=price,
            financials=df,
            book_value_per_share=book_value_per_share,
            shares_outstanding=shares_outstanding,
            data_quality=data_quality,
        )
