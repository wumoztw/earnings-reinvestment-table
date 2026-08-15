# modules/calculators/metrics.py
import pandas as pd
from core.interfaces import BaseCalculator
from core.schemas import StockData

class FinancialMetricsCalculator(BaseCalculator):
    def calculate_metrics(self, data: StockData) -> pd.DataFrame:
        df = data.financials.copy()
        
        # 1. 計算 ROE = 當期淨利 / 當期股東權益
        df['roe'] = (df['net_income'] / df['equity']) * 100
        
        # 2. 計算 盈餘再投資率 (Reinvestment Rate)
        # 公式：((當期固定資產 + 當期長期投資) - (4年前固定資產 + 4年前長期投資)) / 近4年淨利總和
        capital_invest = df['fixed_assets'] + df['long_term_invest']
        delta_invest = capital_invest - capital_invest.shift(4)
        net_income_4y_sum = df['net_income'].rolling(window=4).sum()
        
        df['reinvest_rate'] = (delta_invest / net_income_4y_sum) * 100
        return df
