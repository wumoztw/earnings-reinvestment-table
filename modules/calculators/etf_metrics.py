# modules/calculators/etf_metrics.py
"""ETF 專屬指標計算器"""
import pandas as pd
import numpy as np
from core.interfaces import BaseEtfAnalyzer
from core.schemas import EtfData, EtfAnalysisResult


class EtfMetricsCalculator(BaseEtfAnalyzer):
    """計算 ETF 專屬分析指標
    
    包含:
    - 各年度殖利率
    - 年度含息報酬率
    - 殖利率穩定度 (變異係數)
    - 最大回撤
    - 連續配息次數
    - 基於殖利率歷史區間的買進建議
    """

    def analyze(self, data: EtfData) -> EtfAnalysisResult:
        yearly = self._build_yearly_metrics(data)
        
        # ── 殖利率統計 ──
        valid_yields = yearly["yield"].dropna()
        valid_yields = valid_yields[valid_yields > 0]
        
        avg_yield = round(valid_yields.mean(), 2) if len(valid_yields) > 0 else 0.0
        yield_std = valid_yields.std() if len(valid_yields) > 1 else 0.0
        yield_cv = round(yield_std / avg_yield, 2) if avg_yield > 0 else 0.0
        
        # 當前估計殖利率 (最近 12 個月配息 / 當前價格)
        current_yield = self._calc_trailing_yield(data)
        
        # ── 年度含息報酬率 ──
        total_return_1y = self._calc_total_return(data, years=1)
        total_return_3y = self._calc_total_return(data, years=3)
        total_return_5y = self._calc_total_return(data, years=5)
        
        # ── 連續配息次數 ──
        dividend_streak = self._calc_dividend_streak(data)
        
        # ── 最大回撤 ──
        max_drawdown = self._calc_max_drawdown(data)
        
        # ── 殖利率區間估值 (均值 ± 1σ) ──
        cheap_yield = round(avg_yield + yield_std, 2) if yield_std > 0 else round(avg_yield * 1.2, 2)
        fair_yield = avg_yield
        expensive_yield = round(avg_yield - yield_std, 2) if yield_std > 0 else round(avg_yield * 0.8, 2)
        expensive_yield = max(expensive_yield, 0.0)  # 殖利率不為負
        
        # ── 投資訊號 ──
        signal = self._generate_signal(current_yield, cheap_yield, fair_yield, expensive_yield)
        
        return EtfAnalysisResult(
            avg_yield=avg_yield,
            current_yield=round(current_yield, 2),
            yield_stability=yield_cv,
            total_return_1y=total_return_1y,
            total_return_3y=total_return_3y,
            total_return_5y=total_return_5y,
            dividend_streak=dividend_streak,
            max_drawdown=max_drawdown,
            cheap_yield=cheap_yield,
            fair_yield=fair_yield,
            expensive_yield=expensive_yield,
            signal=signal,
            yearly_metrics=yearly,
        )

    def _build_yearly_metrics(self, data: EtfData) -> pd.DataFrame:
        """建構年度指標 DataFrame"""
        price_df = data.price_history
        div_df = data.dividends
        
        if price_df.empty:
            return pd.DataFrame()
        
        # 確保索引為 DatetimeIndex
        if not isinstance(price_df.index, pd.DatetimeIndex):
            price_df.index = pd.to_datetime(price_df.index)
        
        years = sorted(price_df.index.year.unique())
        records = []
        
        for year in years:
            year_prices = price_df[price_df.index.year == year]
            if year_prices.empty:
                continue
            
            open_price = year_prices["Close"].iloc[0]
            close_price = year_prices["Close"].iloc[-1]
            high_price = year_prices["High"].max() if "High" in year_prices else close_price
            low_price = year_prices["Low"].min() if "Low" in year_prices else close_price
            
            # 年度配息總額
            year_div = 0.0
            if not div_df.empty and "date" in div_df.columns:
                year_divs = div_df[pd.to_datetime(div_df["date"]).dt.year == year]
                year_div = year_divs["amount"].sum() if not year_divs.empty else 0.0
            
            # 年殖利率 = 年度配息 / 年初價格
            div_yield = (year_div / open_price * 100) if open_price > 0 else 0.0
            
            # 價格報酬率
            price_return = ((close_price - open_price) / open_price * 100) if open_price > 0 else 0.0
            
            # 含息總報酬率
            total_return = (((close_price + year_div) - open_price) / open_price * 100) if open_price > 0 else 0.0
            
            records.append({
                "year": year,
                "open": round(open_price, 2),
                "close": round(close_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "dividend": round(year_div, 2),
                "yield": round(div_yield, 2),
                "price_return": round(price_return, 2),
                "total_return": round(total_return, 2),
            })
        
        df = pd.DataFrame(records)
        if not df.empty:
            df = df.set_index("year")
        return df

    def _calc_trailing_yield(self, data: EtfData) -> float:
        """計算最近 12 個月追蹤殖利率"""
        if data.dividends.empty or data.current_price <= 0:
            return 0.0
        
        div_df = data.dividends.copy()
        div_df["date"] = pd.to_datetime(div_df["date"]).dt.tz_localize(None)
        
        cutoff = pd.Timestamp.now() - pd.DateOffset(months=12)
        recent = div_df[div_df["date"] >= cutoff]
        
        if recent.empty:
            return 0.0
        
        ttm_div = recent["amount"].sum()
        return (ttm_div / data.current_price) * 100

    def _calc_total_return(self, data: EtfData, years: int) -> float | None:
        """計算 N 年含息年化報酬率"""
        price_df = data.price_history
        div_df = data.dividends
        
        if price_df.empty:
            return None
        
        price_idx = price_df.index
        if isinstance(price_idx, pd.DatetimeIndex) and price_idx.tz is not None:
            price_idx = price_idx.tz_localize(None)
            price_df = price_df.copy()
            price_df.index = price_idx
        
        end_date = price_df.index[-1]
        start_date = end_date - pd.DateOffset(years=years)
        
        # 確保有足夠歷史資料
        if price_df.index[0] > start_date:
            return None
        
        # 找最接近 start_date 的交易日
        mask = price_df.index >= start_date
        if not mask.any():
            return None
        
        start_price = price_df.loc[mask, "Close"].iloc[0]
        end_price = price_df["Close"].iloc[-1]
        
        # 期間配息總和
        total_div = 0.0
        if not div_df.empty and "date" in div_df.columns:
            div_dates = pd.to_datetime(div_df["date"]).dt.tz_localize(None)
            period_divs = div_df[(div_dates >= start_date) & (div_dates <= end_date)]
            total_div = period_divs["amount"].sum() if not period_divs.empty else 0.0
        
        # 總報酬
        total_return = (end_price + total_div - start_price) / start_price
        
        # 年化
        if years > 1:
            annualized = (1 + total_return) ** (1 / years) - 1
        else:
            annualized = total_return
        
        return round(annualized * 100, 2)

    def _calc_dividend_streak(self, data: EtfData) -> int:
        """計算連續配息次數 (從最近一次往回數)"""
        if data.dividends.empty:
            return 0
        
        div_df = data.dividends.copy()
        div_df["date"] = pd.to_datetime(div_df["date"])
        div_df = div_df.sort_values("date", ascending=False)
        
        streak = 0
        for _, row in div_df.iterrows():
            if row["amount"] > 0:
                streak += 1
            else:
                break
        return streak

    def _calc_max_drawdown(self, data: EtfData) -> float | None:
        """計算歷史最大回撤"""
        if data.price_history.empty:
            return None
        
        close = data.price_history["Close"]
        cummax = close.cummax()
        drawdown = (close - cummax) / cummax
        max_dd = drawdown.min()
        
        return round(max_dd * 100, 2)

    def _generate_signal(
        self,
        current_yield: float,
        cheap_yield: float,
        fair_yield: float,
        expensive_yield: float,
    ) -> str:
        """根據殖利率位置產生投資訊號"""
        if current_yield <= 0:
            return "⚪ 資料不足 (無近期配息紀錄)"
        
        if current_yield >= cheap_yield:
            return "🟢 便宜區間 (殖利率高於歷史均值+1σ，可考慮分批買進)"
        elif current_yield >= fair_yield:
            return "🟡 合理區間 (殖利率接近歷史均值，持有或觀望)"
        elif current_yield >= expensive_yield:
            return "🟠 偏貴區間 (殖利率低於均值，宜謹慎)"
        else:
            return "🔴 昂貴區間 (殖利率遠低於歷史均值-1σ，不宜追高)"
