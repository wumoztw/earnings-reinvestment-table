# modules/fetchers/tw_etf_fetcher.py
"""
台灣 ETF 資料擷取器
優先 Twelve Data，失敗則 fallback yfinance。

重要：
- 歷史價格使用未調整（adjust=none / auto_adjust=False）
- 總報酬計算時明確加上現金配息
"""
from __future__ import annotations

import yfinance as yf
import pandas as pd
from typing import Optional

from core.interfaces import BaseEtfFetcher
from core.schemas import EtfData
from modules.fetchers.etf_registry import get_etf_info, get_yfinance_symbol
from modules.utils.cache import cached
from modules.utils.twelve_client import TwelveDataClient, has_twelve_data_key


class TwEtfFetcher(BaseEtfFetcher):
    @cached("etf_fetch_v2", ttl=6 * 3600)
    def fetch(self, symbol: str) -> EtfData:
        clean = symbol.upper().strip().replace(".TW", "").replace(".TWO", "")

        if has_twelve_data_key():
            try:
                return self._fetch_twelve(clean)
            except Exception as e:
                print(f"[TwEtfFetcher] Twelve Data 失敗 ({clean}): {e} → fallback yfinance")

        return self._fetch_yfinance(clean)

    def _fetch_twelve(self, clean: str) -> EtfData:
        client = TwelveDataClient()
        exchange, country = "TWSE", "Taiwan"

        ts = client.time_series(
            clean,
            interval="1day",
            outputsize=3000,
            exchange=exchange,
            country=country,
            adjust="none",
        )
        values = ts.get("values") or []
        if not values:
            raise ValueError(f"Twelve Data 無 {clean} 價格資料")

        rows = []
        for v in values:
            rows.append({
                "Date": pd.to_datetime(v["datetime"]),
                "Open": float(v.get("open") or 0),
                "High": float(v.get("high") or 0),
                "Low": float(v.get("low") or 0),
                "Close": float(v.get("close") or 0),
                "Volume": float(v.get("volume") or 0),
            })
        price_history = pd.DataFrame(rows).set_index("Date").sort_index()
        price_history = price_history.dropna(subset=["Close"])

        div_df = pd.DataFrame()
        try:
            div_raw = client.dividends(clean, exchange=exchange, country=country, range_="full")
            divs = div_raw.get("dividends") or []
            if divs:
                div_df = pd.DataFrame([
                    {"date": pd.to_datetime(d["ex_date"]), "amount": float(d["amount"])}
                    for d in divs if d.get("ex_date") and d.get("amount") is not None
                ]).sort_values("date").reset_index(drop=True)
        except Exception:
            pass

        current_price = float(price_history["Close"].iloc[-1]) if not price_history.empty else 0.0
        try:
            current_price = client.price(clean, exchange=exchange, country=country) or current_price
        except Exception:
            pass

        reg = get_etf_info(clean)
        name = reg.get("name", clean)
        try:
            prof = client.profile(clean, exchange=exchange, country=country)
            name = prof.get("name") or name
        except Exception:
            pass

        return EtfData(
            symbol=clean,
            name=name,
            market="TW",
            current_price=current_price,
            nav=None,
            premium_discount=None,
            expense_ratio=None,
            aum=None,
            category=reg.get("category", "其他"),
            dividends=div_df,
            price_history=price_history,
        )

    def _fetch_yfinance(self, clean: str) -> EtfData:
        yf_symbol = get_yfinance_symbol(clean)
        ticker = yf.Ticker(yf_symbol)

        price_history = ticker.history(period="10y", auto_adjust=False)
        if price_history.empty:
            raise ValueError(f"無法取得 ETF {clean} 的歷史價格資料，請確認代號是否正確。")

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
            reg = get_etf_info(clean)
            name = reg.get("name", clean)

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

        reg = get_etf_info(clean)
        category = reg.get("category", "其他")
        market = "TWO" if ".TWO" in yf_symbol else "TW"

        return EtfData(
            symbol=clean,
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
