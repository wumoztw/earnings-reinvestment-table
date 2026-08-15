# modules/valuators/valuation.py
"""
價值投資估值引擎 + 5點選股原則檢查

選股條件：
1. 五年ROE穩定（至少4年資料、平均>15%、最低>=10%、變異係數<0.45）
2. 五年ROE平均 >15%
3. 盈再率 <80%
4. 配息率 >40%
5. 公司淨利 >5億（台股以TWD計；美股以USD計，門檻調整為5,000萬）
6. 公司上市超過2年
7. 董監/內部人持股 ≥10%（資料來自 yfinance heldPercentInsiders，台股可能估低）
"""
import pandas as pd
import numpy as np
from typing import List, Optional
from core.interfaces import BaseValuator
from core.schemas import StockData, ValuationResult, CriterionResult


class ValueInvestingValuator(BaseValuator):
    def evaluate(self, data: StockData, metrics_df: pd.DataFrame) -> ValuationResult:
        # ── 基本指標 ──
        latest_metrics = metrics_df.dropna(subset=["reinvest_rate"])
        latest_reinvest = (
            float(latest_metrics["reinvest_rate"].iloc[-1])
            if not latest_metrics.empty
            else np.nan
        )

        roe_series = metrics_df["roe"].tail(5).dropna()
        avg_roe = float(roe_series.mean()) if len(roe_series) > 0 else 0.0
        min_roe = float(roe_series.min()) if len(roe_series) > 0 else None
        roe_std = float(roe_series.std()) if len(roe_series) > 1 else 0.0
        roe_cv = (roe_std / avg_roe) if avg_roe > 0 else None

        # ── 估值（維持原邏輯） ──
        book = data.book_value_per_share
        price = data.current_price

        if book is not None and book > 0 and avg_roe > 0:
            base_value = book * (avg_roe / 15.0)
            method = "book_value_x_roe_multiple"
            book_used = book
        else:
            base_value = price * (avg_roe / 15.0) if avg_roe > 0 else price
            method = "price_x_roe_adjusted (no book value)"
            book_used = None

        cheap = round(base_value * 0.8, 2)
        fair = round(base_value * 1.0, 2)
        expensive = round(base_value * 1.3, 2)

        # ── 5點選股原則檢查 ──
        criteria: List[CriterionResult] = []

        # 1 & 2. 五年ROE穩定 + 平均>15%
        roe_stable = None
        if len(roe_series) >= 4 and avg_roe > 0:
            stable_cond = (
                avg_roe > 15
                and (min_roe is not None and min_roe >= 10)
                and (roe_cv is None or roe_cv < 0.45)
            )
            roe_stable = bool(stable_cond)
            criteria.append(CriterionResult(
                name="五年ROE穩定且>15%",
                passed=roe_stable,
                value=f"平均 {avg_roe:.1f}%｜最低 {min_roe:.1f}%｜CV {roe_cv:.2f}" if roe_cv is not None else f"平均 {avg_roe:.1f}%｜最低 {min_roe:.1f}%",
                threshold="平均>15% 且 最低≥10% 且 CV<0.45（至少4年資料）",
                comment="ROE 穩定高檔" if roe_stable else "ROE 不夠穩定或不足15%",
            ))
        else:
            criteria.append(CriterionResult(
                name="五年ROE穩定且>15%",
                passed=None,
                value=f"僅有 {len(roe_series)} 年有效資料",
                threshold="至少4年資料 + 平均>15% + 最低≥10%",
                comment="資料不足，無法判斷穩定性",
            ))

        # 3. 盈再率 <80%
        if not np.isnan(latest_reinvest):
            reinvest_ok = latest_reinvest < 80
            criteria.append(CriterionResult(
                name="盈餘再投資率 <80%",
                passed=reinvest_ok,
                value=f"{latest_reinvest:.1f}%",
                threshold="< 80%",
                comment="再投資需求不高，較易配得出現金" if reinvest_ok else "再投資率偏高，需注意擴張風險",
            ))
        else:
            criteria.append(CriterionResult(
                name="盈餘再投資率 <80%",
                passed=None,
                value="無法計算",
                threshold="< 80%",
                comment="缺少足夠歷史資本支出資料",
            ))

        # 4. 配息率 >40%
        if data.payout_ratio is not None:
            payout_ok = data.payout_ratio > 40
            criteria.append(CriterionResult(
                name="配息率 >40%",
                passed=payout_ok,
                value=f"{data.payout_ratio:.1f}%",
                threshold="> 40%",
                comment="有實際配出現金給股東" if payout_ok else "配息率偏低",
            ))
        else:
            criteria.append(CriterionResult(
                name="配息率 >40%",
                passed=None,
                value="無資料",
                threshold="> 40%",
                comment="yfinance 未提供 payoutRatio",
            ))

        # 5. 公司淨利 >5億
        if data.latest_net_income is not None:
            if data.market == "TW":
                threshold = 5e8
                threshold_str = "5億元（TWD）"
                size_ok = data.latest_net_income > threshold
                display_val = f"{data.latest_net_income/1e8:.2f} 億元"
            else:
                threshold = 5e7
                threshold_str = "5,000萬（USD）"
                size_ok = data.latest_net_income > threshold
                display_val = f"{data.latest_net_income/1e6:.1f} 百萬USD"
            criteria.append(CriterionResult(
                name="公司淨利夠大",
                passed=size_ok,
                value=display_val,
                threshold=f"> {threshold_str}",
                comment="規模足夠" if size_ok else "淨利規模偏小",
            ))
        else:
            criteria.append(CriterionResult(
                name="公司淨利夠大",
                passed=None,
                value="無資料",
                threshold=">5億（台）/ >5千萬USD（美）",
                comment="無法取得最新淨利",
            ))

        # 6. 上市超過2年
        if data.years_listed is not None:
            years_ok = data.years_listed > 2
            criteria.append(CriterionResult(
                name="上市櫃超過2年",
                passed=years_ok,
                value=f"{data.years_listed:.1f} 年" + (f"（{data.listing_date_str}）" if data.listing_date_str else ""),
                threshold="> 2 年",
                comment="已有足夠公開歷史" if years_ok else "上市時間過短",
            ))
        else:
            criteria.append(CriterionResult(
                name="上市櫃超過2年",
                passed=None,
                value="無資料",
                threshold="> 2 年",
                comment="無法取得上市日期",
            ))

        # 7. 董監/內部人持股 ≥10%
        if data.insider_holding_pct is not None:
            insider_ok = data.insider_holding_pct >= 10
            criteria.append(CriterionResult(
                name="董監/內部人持股 ≥10%",
                passed=insider_ok,
                value=f"{data.insider_holding_pct:.2f}%",
                threshold="≥ 10%",
                comment="持股比例達標（注意：台股 yfinance 資料可能估低實際董監持股）" if insider_ok else "內部人持股偏低或資料不完整",
            ))
        else:
            criteria.append(CriterionResult(
                name="董監/內部人持股 ≥10%",
                passed=None,
                value="無資料",
                threshold="≥ 10%",
                comment="yfinance 未提供 heldPercentInsiders（台股常見）",
            ))

        # ── 綜合判斷 ──
        critical_names = {
            "五年ROE穩定且>15%",
            "盈餘再投資率 <80%",
            "配息率 >40%",
            "公司淨利夠大",
            "上市櫃超過2年",
        }

        critical_results = [c for c in criteria if c.name in critical_names]
        all_critical_passed = all(c.passed is True for c in critical_results)

        if all_critical_passed:
            if price <= cheap:
                signal = "🟢 便宜價 (極佳買點)｜5點原則全數達標"
            elif price <= fair:
                signal = "🟡 合理價 (可分批佈局)｜5點原則全數達標"
            else:
                signal = "🔴 昂貴價 (暫不追高)｜體質達標但股價偏貴"
        else:
            failed = [c.name for c in critical_results if c.passed is not True]
            signal = f"⚪ 觀察中 (未達標：{'、'.join(failed[:3])}{'…' if len(failed)>3 else ''})"

        return ValuationResult(
            cheap=cheap,
            fair=fair,
            expensive=expensive,
            reinvest_rate=round(latest_reinvest, 2) if not np.isnan(latest_reinvest) else 0.0,
            avg_roe=round(avg_roe, 2),
            signal=signal,
            book_value_used=round(book_used, 2) if book_used is not None else None,
            base_value_method=method,
            criteria=criteria,
            all_critical_passed=all_critical_passed,
            roe_stable=roe_stable,
            min_roe_5y=round(min_roe, 2) if min_roe is not None else None,
            roe_cv=round(roe_cv, 3) if roe_cv is not None else None,
        )
