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
        # ((當期固定資產 + 當期長期投資) - (4年前固定資產 + 4年前長期投資)) / 近4年淨利總和
        capital_invest = df["fixed_assets"].fillna(0) + df["long_term_invest"].fillna(0)
        delta_invest = capital_invest - capital_invest.shift(4)
        net_income_4y_sum = df["net_income"].rolling(window=4, min_periods=4).sum()

        with np.errstate(divide="ignore", invalid="ignore"):
            reinvest = (delta_invest / net_income_4y_sum) * 100
            reinvest = reinvest.where(net_income_4y_sum.abs() > 1e-3, np.nan)

        df["reinvest_rate"] = reinvest
        df["has_full_reinvest"] = df["reinvest_rate"].notna()

        return df
