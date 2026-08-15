# modules/valuators/valuation.py
"""
價值投資估值引擎
依據洪瑞泰 / 巴菲特班邏輯：
- 以近 5 年平均 ROE 與每股淨值估算合理價值
- 便宜 / 合理 / 昂貴 = 0.8x / 1.0x / 1.3x 合理價
"""
import pandas as pd
import numpy as np
from core.interfaces import BaseValuator
from core.schemas import StockData, ValuationResult


class ValueInvestingValuator(BaseValuator):
    def evaluate(self, data: StockData, metrics_df: pd.DataFrame) -> ValuationResult:
        # 取得最近一期有效的再投資率
        latest_metrics = metrics_df.dropna(subset=["reinvest_rate"])
        latest_reinvest = (
            float(latest_metrics["reinvest_rate"].iloc[-1])
            if not latest_metrics.empty
            else 0.0
        )

        # 近 5 年平均 ROE（忽略 NaN）
        roe_series = metrics_df["roe"].tail(5).dropna()
        avg_roe = float(roe_series.mean()) if len(roe_series) > 0 else 0.0

        # ── 核心估值邏輯（真正使用每股淨值） ──
        book = data.book_value_per_share
        price = data.current_price

        if book is not None and book > 0 and avg_roe > 0:
            # 方法：以「合理本益比 ≈ ROE / 要求報酬率」概念
            # 簡化實作：假設市場對 15% ROE 的企業給 1 倍淨值（合理）
            # 因此合理價 = 每股淨值 × (avg_roe / 15)
            # 這與 README 描述一致，且使用真實淨值
            base_value = book * (avg_roe / 15.0)
            method = "book_value_x_roe_multiple"
            book_used = book
        else:
            # Fallback：若無淨值資料，退回用當前股價相對調整（舊邏輯）
            base_value = price * (avg_roe / 15.0) if avg_roe > 0 else price
            method = "price_x_roe_adjusted (no book value)"
            book_used = None

        cheap = round(base_value * 0.8, 2)
        fair = round(base_value * 1.0, 2)
        expensive = round(base_value * 1.3, 2)

        # ── 買進訊號決策 ──
        if latest_reinvest < 40 and avg_roe > 15:
            if price <= cheap:
                signal = "🟢 便宜價 (極佳買點)"
            elif price <= fair:
                signal = "🟡 合理價 (可分批佈局)"
            else:
                signal = "🔴 昂貴價 (暫不追高)"
        else:
            reason = []
            if avg_roe <= 15:
                reason.append("ROE ≤ 15%")
            if latest_reinvest >= 40:
                reason.append("盈再率 ≥ 40%")
            signal = f"⚪ 觀察中 (體質未達標：{'、'.join(reason)})"

        return ValuationResult(
            cheap=cheap,
            fair=fair,
            expensive=expensive,
            reinvest_rate=round(latest_reinvest, 2),
            avg_roe=round(avg_roe, 2),
            signal=signal,
            book_value_used=round(book_used, 2) if book_used is not None else None,
            base_value_method=method,
        )
