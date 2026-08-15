# core/schemas.py
from pydantic import BaseModel
from typing import Dict, Any
import pandas as pd

class StockData(BaseModel):
    symbol: str
    name: str
    market: str
    current_price: float
    # 標準欄位 DataFrame: 索引為年份 (如 2019~2023)
    # 欄位: net_income, equity, fixed_assets, long_term_invest, eps, revenue
    financials: pd.DataFrame

    class Config:
        arbitrary_types_allowed = True

class ValuationResult(BaseModel):
    cheap: float
    fair: float
    expensive: float
    reinvest_rate: float
    avg_roe: float
    signal: str  # "便宜", "合理", "昂貴", "觀望"
