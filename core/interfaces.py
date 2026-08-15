# core/interfaces.py
from abc import ABC, abstractmethod
from core.schemas import StockData, ValuationResult, EtfData, EtfAnalysisResult
import pandas as pd


class BaseFetcher(ABC):
    @abstractmethod
    def fetch(self, symbol: str) -> StockData:
        pass


class BaseCalculator(ABC):
    @abstractmethod
    def calculate_metrics(self, data: StockData) -> pd.DataFrame:
        pass


class BaseValuator(ABC):
    @abstractmethod
    def evaluate(self, data: StockData, metrics_df: pd.DataFrame) -> ValuationResult:
        pass


# ──────────────────────────────────────────
# ETF 專用介面
# ──────────────────────────────────────────

class BaseEtfFetcher(ABC):
    @abstractmethod
    def fetch(self, symbol: str) -> EtfData:
        pass


class BaseEtfAnalyzer(ABC):
    @abstractmethod
    def analyze(self, data: EtfData) -> EtfAnalysisResult:
        pass
