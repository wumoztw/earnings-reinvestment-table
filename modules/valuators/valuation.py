# modules/valuators/valuation.py
import pandas as pd
from core.interfaces import BaseValuator
from core.schemas import StockData, ValuationResult

class ValueInvestingValuator(BaseValuator):
    def evaluate(self, data: StockData, metrics_df: pd.DataFrame) -> ValuationResult:
        latest_metrics = metrics_df.dropna(subset=['reinvest_rate'])
        
        # 取得最近一期指標與 5 年平均 ROE
        latest_reinvest = latest_metrics['reinvest_rate'].iloc[-1] if not latest_metrics.empty else 0.0
        avg_roe = metrics_df['roe'].tail(5).mean()
        
        # 簡易內在價值折現模型（以 ROE 及目前淨值估算基準價值）
        latest_equity = data.financials['equity'].iloc[-1]
        base_value = data.current_price * (avg_roe / 15.0) if avg_roe > 0 else data.current_price
        
        cheap = round(base_value * 0.8, 2)
        fair = round(base_value * 1.0, 2)
        expensive = round(base_value * 1.3, 2)
        
        # 買進訊號決策
        price = data.current_price
        if latest_reinvest < 40 and avg_roe > 15:
            if price <= cheap:
                signal = "🟢 便宜價 (極佳買點)"
            elif price <= fair:
                signal = "🟡 合理價 (可分批佈局)"
            else:
                signal = "🔴 昂貴價 (暫不追高)"
        else:
            signal = "⚪ 觀察中 (體質未達標：ROE低於15% 或 盈再率高於40%)"

        return ValuationResult(
            cheap=cheap,
            fair=fair,
            expensive=expensive,
            reinvest_rate=round(latest_reinvest, 2),
            avg_roe=round(avg_roe, 2),
            signal=signal
        )
