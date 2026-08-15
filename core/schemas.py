# core/schemas.py
from pydantic import BaseModel, Field
from typing import Optional, Dict, List
import pandas as pd


class StockData(BaseModel):
    symbol: str
    name: str
    market: str
    current_price: float
    financials: pd.DataFrame
    book_value_per_share: Optional[float] = None
    shares_outstanding: Optional[float] = None
    data_quality: str = "ok"

    # 5點選股原則所需欄位
    payout_ratio: Optional[float] = None
    insider_holding_pct: Optional[float] = None
    years_listed: Optional[float] = None
    latest_net_income: Optional[float] = None
    listing_date_str: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True


class CriterionResult(BaseModel):
    name: str
    passed: Optional[bool] = None
    value: Optional[str] = None
    threshold: str = ""
    comment: str = ""


class ValuationResult(BaseModel):
    cheap: float
    fair: float
    expensive: float
    reinvest_rate: float
    avg_roe: float
    signal: str
    book_value_used: Optional[float] = None
    base_value_method: str = "roe_adjusted_price"
    criteria: List[CriterionResult] = Field(default_factory=list)
    all_critical_passed: bool = False
    roe_stable: Optional[bool] = None
    min_roe_5y: Optional[float] = None
    roe_cv: Optional[float] = None


class EtfData(BaseModel):
    symbol: str
    name: str
    market: str
    current_price: float
    nav: Optional[float] = None
    premium_discount: Optional[float] = None
    expense_ratio: Optional[float] = None
    aum: Optional[float] = None
    category: str = ""
    dividends: pd.DataFrame = Field(default_factory=pd.DataFrame)
    price_history: pd.DataFrame = Field(default_factory=pd.DataFrame)

    class Config:
        arbitrary_types_allowed = True


class EtfAnalysisResult(BaseModel):
    avg_yield: float
    current_yield: float
    yield_stability: float
    total_return_1y: Optional[float] = None
    total_return_3y: Optional[float] = None
    total_return_5y: Optional[float] = None
    dividend_streak: int
    max_drawdown: Optional[float] = None
    cheap_yield: float
    fair_yield: float
    expensive_yield: float
    signal: str
    yearly_metrics: pd.DataFrame = Field(default_factory=pd.DataFrame)

    class Config:
        arbitrary_types_allowed = True
