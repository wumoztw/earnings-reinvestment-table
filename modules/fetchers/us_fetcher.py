# modules/fetchers/us_fetcher.py
"""
通用個股資料抓取器
優先使用 Twelve Data（若有 TWELVEDATA_API_KEY），失敗或無 key 時 fallback 到 yfinance。

支援：
- 台股（數字代號，自動 TWSE / Taiwan）
- 美股（AAPL 等）
"""
from __future__ import annotations

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from typing import Optional, List, Tuple, Dict, Any

from core.interfaces import BaseFetcher
from core.schemas import StockData
from modules.utils.cache import cached
from modules.utils.twelve_client import TwelveDataClient, TwelveDataError, has_twelve_data_key


class UniversalFetcher(BaseFetcher):
    """通用抓取器：優先 Twelve Data，備援 yfinance"""

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

    def _resolve_symbol(self, symbol: str) -> Tuple[str, Optional[str], Optional[str], str]:
        clean = symbol.strip().upper().replace(".TW", "").replace(".TWO", "")
        if clean.isdigit():
            return clean, "TWSE", "Taiwan", "TW"
        return clean, None, None, "US"

    @cached("stock_fetch_v2", ttl=6 * 3600)
    def fetch(self, symbol: str) -> StockData:
        clean, exchange, country, market = self._resolve_symbol(symbol)

        if has_twelve_data_key():
            try:
                return self._fetch_twelve(clean, exchange, country, market)
            except Exception as e:
                print(f"[UniversalFetcher] Twelve Data 失敗 ({clean}): {e} → fallback yfinance")

        return self._fetch_yfinance(clean, market)

    def _fetch_twelve(
        self, clean: str, exchange: Optional[str], country: Optional[str], market: str
    ) -> StockData:
        client = TwelveDataClient()

        inc_raw = client.income_statement(clean, period="annual", outputsize=8, exchange=exchange, country=country)
        bs_raw = client.balance_sheet(clean, period="annual", outputsize=8, exchange=exchange, country=country)

        inc_list = inc_raw.get("income_statement") or []
        bs_list = bs_raw.get("balance_sheet") or []

        if not inc_list or not bs_list:
            raise TwelveDataError(f"{clean} 財報資料為空")

        def _year(item: Dict) -> Optional[int]:
            fd = item.get("fiscal_date") or ""
            try:
                return int(str(fd)[:4])
            except Exception:
                y = item.get("year")
                return int(y) if y else None

        inc_by_year = {_year(x): x for x in inc_list if _year(x)}
        bs_by_year = {_year(x): x for x in bs_list if _year(x)}
        common_years = sorted(set(inc_by_year.keys()) & set(bs_by_year.keys()))

        if len(common_years) < 2:
            raise TwelveDataError(f"{clean} 共同年度財報不足（{len(common_years)} 年）")

        rows = []
        for y in common_years:
            inc = inc_by_year[y]
            bs = bs_by_year[y]

            net_income = self._safe_float(inc.get("net_income"))
            equity = self._safe_float(
                (bs.get("shareholders_equity") or {}).get("total_shareholders_equity")
            )

            non_cur = (bs.get("assets") or {}).get("non_current_assets") or {}
            ppe_parts = [
                non_cur.get("properties"),
                non_cur.get("land_and_improvements"),
                non_cur.get("machinery_furniture_equipment"),
                non_cur.get("construction_in_progress"),
            ]
            ppe_sum = sum(self._safe_float(v) or 0 for v in ppe_parts)
            accum_dep = self._safe_float(non_cur.get("accumulated_depreciation")) or 0
            fixed_assets = ppe_sum - abs(accum_dep) if ppe_sum else self._safe_float(non_cur.get("total_non_current_assets"))

            lti = self._safe_float(non_cur.get("investments_and_advances")) or self._safe_float(non_cur.get("financial_assets")) or 0.0

            rows.append({
                "year": y,
                "net_income": net_income,
                "equity": equity,
                "fixed_assets": fixed_assets,
                "long_term_invest": lti,
            })

        df = pd.DataFrame(rows).set_index("year").sort_index()

        required = ["net_income", "equity", "fixed_assets"]
        missing_ratio = df[required].isna().mean().mean()
        if missing_ratio > 0.5:
            data_quality = "insufficient"
        elif missing_ratio > 0.1:
            data_quality = "partial"
        else:
            data_quality = "ok"

        if pd.isna(df["equity"].iloc[-1]) or pd.isna(df["net_income"].iloc[-1]):
            raise TwelveDataError(f"{clean} 最新一期淨利或股東權益缺失")

        price = 0.0
        try:
            price = client.price(clean, exchange=exchange, country=country)
        except Exception:
            try:
                q = client.quote(clean, exchange=exchange, country=country)
                price = float(q.get("close") or q.get("price") or 0)
            except Exception:
                pass

        name = clean
        book_value_per_share = None
        shares_outstanding = None
        payout_ratio = None
        insider_holding_pct = None
        years_listed = None
        listing_date_str = None
        latest_net_income = float(df["net_income"].iloc[-1]) if not pd.isna(df["net_income"].iloc[-1]) else None

        try:
            prof = client.profile(clean, exchange=exchange, country=country)
            name = prof.get("name") or name
            ipo = prof.get("ipo_date") or prof.get("list_date")
            if ipo:
                listing_date_str = str(ipo)[:10]
                try:
                    dt = datetime.strptime(listing_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    years_listed = round((datetime.now(timezone.utc) - dt).days / 365.25, 1)
                except Exception:
                    pass
        except Exception:
            pass

        try:
            stats = client.statistics(clean, exchange=exchange, country=country)
            val = stats.get("statistics") or stats
            fin = val.get("financials") or {}
            bs_s = fin.get("balance_sheet") or {}
            div_s = val.get("dividends_and_splits") or {}
            stock_s = val.get("stock_statistics") or {}

            bv = bs_s.get("book_value_per_share_mrq") or bs_s.get("book_value_per_share")
            if bv is not None:
                book_value_per_share = float(bv)

            shares = stock_s.get("shares_outstanding") or stock_s.get("float_shares")
            if shares is not None:
                shares_outstanding = float(shares)

            pr = div_s.get("payout_ratio") or div_s.get("payout_ratio_ttm")
            if pr is not None:
                pr_f = float(pr)
                payout_ratio = pr_f * 100 if pr_f <= 1.5 else pr_f

            ins = stock_s.get("percent_held_by_insiders") or stock_s.get("held_percent_insiders")
            if ins is not None:
                ins_f = float(ins)
                insider_holding_pct = ins_f * 100 if ins_f <= 1.5 else ins_f
        except Exception:
            pass

        if book_value_per_share is None and shares_outstanding and shares_outstanding > 0:
            eq = df["equity"].iloc[-1]
            if pd.notna(eq) and eq > 0:
                book_value_per_share = float(eq) / shares_outstanding

        return StockData(
            symbol=clean,
            name=str(name),
            market=market,
            current_price=float(price or 0),
            financials=df,
            book_value_per_share=book_value_per_share,
            shares_outstanding=shares_outstanding,
            data_quality=data_quality,
            payout_ratio=payout_ratio,
            insider_holding_pct=insider_holding_pct,
            years_listed=years_listed,
            latest_net_income=latest_net_income,
            listing_date_str=listing_date_str,
        )

    @staticmethod
    def _safe_float(v: Any) -> Optional[float]:
        if v is None:
            return None
        try:
            f = float(v)
            return f if not np.isnan(f) else None
        except (TypeError, ValueError):
            return None

    def _fetch_yfinance(self, clean: str, market: str) -> StockData:
        ticker_symbol = f"{clean}.TW" if market == "TW" else clean
        ticker = yf.Ticker(ticker_symbol)

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

        def _extract_series(source: pd.DataFrame, year_map: dict, keys: List[str]) -> pd.Series:
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
        df["long_term_invest"] = df["long_term_invest"].fillna(0.0)
        df = df.sort_index(ascending=True)

        required_cols = ["net_income", "equity", "fixed_assets"]
        missing_ratio = df[required_cols].isna().mean().mean()
        if missing_ratio > 0.5:
            data_quality = "insufficient"
        elif missing_ratio > 0.1:
            data_quality = "partial"
        else:
            data_quality = "ok"

        if pd.isna(df["equity"].iloc[-1]) or pd.isna(df["net_income"].iloc[-1]):
            raise ValueError(f"股票 {clean} 最新一期淨利或股東權益缺失，無法進行估值。")

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

        name = info.get("shortName") or info.get("longName") or info.get("symbol") or clean

        book_value_per_share = None
        shares_outstanding = None
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

        payout_ratio = None
        pr = info.get("payoutRatio")
        if pr is not None:
            try:
                pr_f = float(pr)
                payout_ratio = pr_f * 100 if pr_f <= 1.5 else pr_f
            except (TypeError, ValueError):
                pass

        insider_holding_pct = None
        ins = info.get("heldPercentInsiders")
        if ins is not None:
            try:
                ins_f = float(ins)
                insider_holding_pct = ins_f * 100 if ins_f <= 1.5 else ins_f
            except (TypeError, ValueError):
                pass

        years_listed = None
        listing_date_str = None
        ms = info.get("firstTradeDateMilliseconds")
        if ms is not None:
            try:
                listing_dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
                listing_date_str = listing_dt.strftime("%Y-%m-%d")
                delta = datetime.now(timezone.utc) - listing_dt
                years_listed = round(delta.days / 365.25, 1)
            except Exception:
                pass

        latest_net_income = None
        if not pd.isna(df["net_income"].iloc[-1]):
            latest_net_income = float(df["net_income"].iloc[-1])
        else:
            ni = info.get("netIncomeToCommon")
            if ni is not None:
                try:
                    latest_net_income = float(ni)
                except (TypeError, ValueError):
                    pass

        return StockData(
            symbol=clean,
            name=str(name),
            market=market,
            current_price=price,
            financials=df,
            book_value_per_share=book_value_per_share,
            shares_outstanding=shares_outstanding,
            data_quality=data_quality,
            payout_ratio=payout_ratio,
            insider_holding_pct=insider_holding_pct,
            years_listed=years_listed,
            latest_net_income=latest_net_income,
            listing_date_str=listing_date_str,
        )
