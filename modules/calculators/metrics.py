# modules/calculators/metrics.py
"""
個股財務指標計算器
- ROE
- 盈餘再投資率（含邊界保護）
"""
import pandas as pd
import numpy as np
from core.interfaces import BaseCalculator
from core.schemas import StockData


class FinancialMetricsCalculator(BaseCalculator):
    def calculate_metrics(self, data: StockData) -> pd.DataFrame:
        df = data.financials.copy()

        # 1. ROE = 當期淨利 / 當期股東權益
        equity_safe = df["equity"].replace(0, np.nan)
        df["roe"] = (df["net_income"] / equity_safe) * 100

        # 2. 盈餘再投資率
        # 標準 4 年：((當期固定資產 + 當期長期投資) - (4年前固定資產 + 4年前長期投資)) / 近4年淨利總和
        capital_invest = df["fixed_assets"].fillna(0) + df["long_term_invest"].fillna(0)
        delta_invest_4y = capital_invest - capital_invest.shift(4)
        net_income_4y_sum = df["net_income"].rolling(window=4, min_periods=4).sum()

        with np.errstate(divide="ignore", invalid="ignore"):
            reinvest_4y = (delta_invest_4y / net_income_4y_sum) * 100
            reinvest_4y = reinvest_4y.where(net_income_4y_sum.abs() > 1e-3, np.nan)

        # 彈性累積：若某年因歷史資料不足 4 年而為空，則採用可用年數 (k=1..3年) 計算累積盈再率
        reinvest = reinvest_4y.copy()
        for i in range(len(df)):
            if pd.isna(reinvest.iloc[i]) and i > 0:
                k = min(4, i)
                delta_k = capital_invest.iloc[i] - capital_invest.iloc[i - k]
                ni_k = df["net_income"].iloc[i - k + 1 : i + 1].sum()
                if abs(ni_k) > 1e-3:
                    reinvest.iloc[i] = (delta_k / ni_k) * 100

        df["reinvest_rate"] = reinvest
        df["has_full_reinvest"] = reinvest_4y.notna()

        return df
