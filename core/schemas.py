# core/schemas.py
from pydantic import BaseModel
from typing import Optional
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


# ──────────────────────────────────────────
# ETF 專用資料結構
# ──────────────────────────────────────────

class EtfData(BaseModel):
    """台灣 ETF 原始資料容器"""
    symbol: str
    name: str
    market: str                          # "TW" or "TWO"
    current_price: float
    nav: Optional[float] = None          # 最新淨值
    premium_discount: Optional[float] = None  # 折溢價 (%)
    expense_ratio: Optional[float] = None     # 總費用率 (%)
    aum: Optional[float] = None               # 基金規模 (NTD)
    category: str = ""                   # 類別 (市值型/高股息/債券型 等)
    dividends: pd.DataFrame = pd.DataFrame()   # 配息歷史 (date, amount)
    price_history: pd.DataFrame = pd.DataFrame()  # 歷史價格 (OHLCV)

    class Config:
        arbitrary_types_allowed = True


class EtfAnalysisResult(BaseModel):
    """ETF 分析結果"""
    avg_yield: float              # 近年平均殖利率 (%)
    current_yield: float          # 當前估計殖利率 (%)
    yield_stability: float        # 殖利率穩定度 (變異係數 CV)
    total_return_1y: Optional[float] = None   # 1年含息報酬 (%)
    total_return_3y: Optional[float] = None   # 3年年化含息報酬 (%)
    total_return_5y: Optional[float] = None   # 5年年化含息報酬 (%)
    dividend_streak: int          # 連續配息次數
    max_drawdown: Optional[float] = None      # 最大回撤 (%)
    cheap_yield: float            # 便宜殖利率門檻 (%)
    fair_yield: float             # 合理殖利率門檻 (%)
    expensive_yield: float        # 昂貴殖利率門檻 (%)
    signal: str                   # 投資訊號
    yearly_metrics: pd.DataFrame = pd.DataFrame()  # 年度指標明細

    class Config:
        arbitrary_types_allowed = True
