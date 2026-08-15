# app.py
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from modules.fetchers.us_fetcher import UniversalFetcher
from modules.fetchers.tw_etf_fetcher import TwEtfFetcher
from modules.fetchers.etf_registry import is_tw_etf, get_etf_categories, get_etf_info
from modules.calculators.metrics import FinancialMetricsCalculator
from modules.calculators.etf_metrics import EtfMetricsCalculator
from modules.valuators.valuation import ValueInvestingValuator

st.set_page_config(page_title="Python 盈再表系統", layout="wide", page_icon="📈")


# ──────────────────────────────────────────
# 工具函式
# ──────────────────────────────────────────

def _yield_to_price(target_yield: float, etf_data) -> float:
    """根據目標殖利率和近 12 月配息推算對應價格"""
    if target_yield <= 0:
        return 0.0
    
    div_df = etf_data.dividends
    if div_df.empty:
        return 0.0
    
    div_df_copy = div_df.copy()
    div_df_copy["date"] = pd.to_datetime(div_df_copy["date"]).dt.tz_localize(None)
    cutoff = pd.Timestamp.now() - pd.DateOffset(months=12)
    recent = div_df_copy[div_df_copy["date"] >= cutoff]
    
    if recent.empty:
        return 0.0
    
    ttm_div = recent["amount"].sum()
    return ttm_div / (target_yield / 100)


# ──────────────────────────────────────────
# 快取分析 Pipeline
# ──────────────────────────────────────────

@st.cache_data(ttl=3600)
def run_stock_pipeline(symbol: str):
    """個股盈再表分析 Pipeline"""
    fetcher = UniversalFetcher()
    calculator = FinancialMetricsCalculator()
    valuator = ValueInvestingValuator()
    
    stock_data = fetcher.fetch(symbol)
    metrics_df = calculator.calculate_metrics(stock_data)
    val_result = valuator.evaluate(stock_data, metrics_df)
    
    return stock_data, metrics_df, val_result


@st.cache_data(ttl=3600)
def run_etf_pipeline(symbol: str):
    """ETF 分析 Pipeline"""
    fetcher = TwEtfFetcher()
    analyzer = EtfMetricsCalculator()
    
    etf_data = fetcher.fetch(symbol)
    result = analyzer.analyze(etf_data)
    
    return etf_data, result


# ──────────────────────────────────────────
# 側邊欄
# ──────────────────────────────────────────

st.sidebar.title("🔍 股票 / ETF 分析設定")

# 分析模式選擇
mode = st.sidebar.radio(
    "分析模式",
    ["自動偵測", "個股盈再表", "台灣 ETF"],
    index=0,
    help="自動偵測會根據代號判斷是個股或 ETF",
)

# 輸入代號
symbol_input = st.sidebar.text_input(
    "輸入代號 (台股: 2330 / 美股: AAPL / ETF: 0050)",
    value="0050",
).strip().upper()

# ETF 快速選股
if mode in ["自動偵測", "台灣 ETF"]:
    st.sidebar.divider()
    st.sidebar.subheader("📋 ETF 快速選股")
    categories = get_etf_categories()
    
    selected_cat = st.sidebar.selectbox(
        "ETF 類別",
        options=list(categories.keys()),
        index=0,
    )
    
    etf_options = categories[selected_cat]
    etf_labels = [f"{e['symbol']} {e['name']} ({e['freq']})" for e in etf_options]
    
    selected_etf_idx = st.sidebar.selectbox(
        "選擇 ETF",
        options=range(len(etf_labels)),
        format_func=lambda i: etf_labels[i],
        index=0,
    )
    
    if st.sidebar.button("📌 套用此 ETF", type="secondary"):
        symbol_input = etf_options[selected_etf_idx]["symbol"]
        st.rerun()

st.sidebar.divider()
search_btn = st.sidebar.button("🚀 開始分析", type="primary", use_container_width=True)


# ──────────────────────────────────────────
# 判斷分析模式
# ──────────────────────────────────────────

def determine_mode(symbol: str, user_mode: str) -> str:
    """判斷要用哪種分析模式"""
    if user_mode == "個股盈再表":
        return "stock"
    elif user_mode == "台灣 ETF":
        return "etf"
    else:  # 自動偵測
        return "etf" if is_tw_etf(symbol) else "stock"


# ──────────────────────────────────────────
# 主畫面
# ──────────────────────────────────────────

st.title("📊 盈餘再投資率 & ETF 評估儀表板")
st.caption("基於巴菲特/洪瑞泰價值投資邏輯的自動化開源分析工具，支援台灣 ETF 殖利率分析")

if symbol_input:
    analysis_mode = determine_mode(symbol_input, mode)
    
    if analysis_mode == "etf":
        # ════════════════════════════════════════
        # ETF 分析模式
        # ════════════════════════════════════════
        try:
            with st.spinner(f"正在擷取 ETF {symbol_input} 的歷史資料並分析中..."):
                etf_data, result = run_etf_pipeline(symbol_input)
            
            # 標題
            etf_info = get_etf_info(symbol_input)
            display_name = etf_data.name or etf_info.get("name", symbol_input)
            st.subheader(f"🏷️ {symbol_input} {display_name}")
            if etf_info:
                st.caption(f"類別: {etf_info.get('category', '—')} ｜ 配息頻率: {etf_info.get('freq', '—')}")
            
            # 1. KPI 卡片
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("目前股價", f"NT${etf_data.current_price:,.2f}")
            col2.metric(
                "近12月殖利率",
                f"{result.current_yield}%",
                delta="偏高" if result.current_yield > result.avg_yield else "偏低",
                delta_color="normal" if result.current_yield >= result.avg_yield else "inverse",
            )
            col3.metric("歷年平均殖利率", f"{result.avg_yield}%")
            col4.metric("連續配息次數", f"{result.dividend_streak} 次")
            
            if result.max_drawdown is not None:
                col5.metric("歷史最大回撤", f"{result.max_drawdown}%")
            else:
                col5.metric("歷史最大回撤", "—")
            
            # 投資訊號
            st.info(f"**投資訊號：** {result.signal}")
            
            # 2. 報酬率摘要
            st.divider()
            st.subheader("💰 含息報酬率")
            rcol1, rcol2, rcol3 = st.columns(3)
            rcol1.metric("1 年報酬", f"{result.total_return_1y}%" if result.total_return_1y is not None else "—")
            rcol2.metric("3 年年化", f"{result.total_return_3y}%" if result.total_return_3y is not None else "—")
            rcol3.metric("5 年年化", f"{result.total_return_5y}%" if result.total_return_5y is not None else "—")
            
            # 3. 殖利率區間
            st.divider()
            st.subheader("🎯 殖利率估值區間")
            ycol1, ycol2, ycol3 = st.columns(3)
            ycol1.success(f"🟢 便宜殖利率：**{result.cheap_yield}%**\n\n(對應價格約 NT${_yield_to_price(result.cheap_yield, etf_data):,.1f})" if result.cheap_yield > 0 else "🟢 便宜殖利率：—")
            ycol2.warning(f"🟡 合理殖利率：**{result.fair_yield}%**\n\n(對應價格約 NT${_yield_to_price(result.fair_yield, etf_data):,.1f})" if result.fair_yield > 0 else "🟡 合理殖利率：—")
            ycol3.error(f"🔴 昂貴殖利率：**{result.expensive_yield}%**\n\n(對應價格約 NT${_yield_to_price(result.expensive_yield, etf_data):,.1f})" if result.expensive_yield > 0 else "🔴 昂貴殖利率：—")
            
            # 4. 殖利率與報酬率趨勢圖
            yearly = result.yearly_metrics
            if not yearly.empty:
                st.divider()
                st.subheader("📈 歷年趨勢圖")
                
                tab1, tab2, tab3 = st.tabs(["殖利率趨勢", "年度報酬率", "配息歷史"])
                
                with tab1:
                    fig_yield = go.Figure()
                    fig_yield.add_trace(go.Scatter(
                        x=yearly.index, y=yearly["yield"],
                        mode="lines+markers", name="年殖利率 (%)",
                        line=dict(color="#00CC96", width=3),
                        marker=dict(size=8),
                    ))
                    # 歷史均值線
                    fig_yield.add_hline(
                        y=result.avg_yield, line_dash="dash", line_color="blue",
                        annotation_text=f"均值 {result.avg_yield}%",
                    )
                    # 便宜 / 昂貴區間
                    fig_yield.add_hline(
                        y=result.cheap_yield, line_dash="dot", line_color="green",
                        annotation_text=f"便宜 {result.cheap_yield}%",
                    )
                    fig_yield.add_hline(
                        y=result.expensive_yield, line_dash="dot", line_color="red",
                        annotation_text=f"昂貴 {result.expensive_yield}%",
                    )
                    fig_yield.update_layout(
                        height=420, yaxis_title="殖利率 (%)",
                        hovermode="x unified",
                        legend=dict(orientation="h", y=1.08, x=0),
                    )
                    st.plotly_chart(fig_yield, use_container_width=True)
                
                with tab2:
                    fig_return = go.Figure()
                    colors = ["#00CC96" if v >= 0 else "#EF553B" for v in yearly["total_return"]]
                    fig_return.add_trace(go.Bar(
                        x=yearly.index, y=yearly["total_return"],
                        name="含息總報酬 (%)", marker_color=colors,
                    ))
                    fig_return.add_trace(go.Scatter(
                        x=yearly.index, y=yearly["price_return"],
                        mode="lines+markers", name="純價格報酬 (%)",
                        line=dict(color="#636EFA", width=2, dash="dash"),
                    ))
                    fig_return.add_hline(y=0, line_color="gray", line_width=1)
                    fig_return.update_layout(
                        height=420, yaxis_title="報酬率 (%)",
                        hovermode="x unified",
                        legend=dict(orientation="h", y=1.08, x=0),
                    )
                    st.plotly_chart(fig_return, use_container_width=True)
                
                with tab3:
                    fig_div = go.Figure()
                    fig_div.add_trace(go.Bar(
                        x=yearly.index, y=yearly["dividend"],
                        name="年度配息 (NTD)", marker_color="#AB63FA",
                    ))
                    fig_div.update_layout(
                        height=400, yaxis_title="每股配息 (NTD)",
                        hovermode="x unified",
                    )
                    st.plotly_chart(fig_div, use_container_width=True)
            
            # 5. 額外資訊
            if etf_data.nav or etf_data.expense_ratio or etf_data.aum:
                st.divider()
                st.subheader("ℹ️ 基金資訊")
                icol1, icol2, icol3 = st.columns(3)
                if etf_data.nav:
                    icol1.metric("淨值 (NAV)", f"NT${etf_data.nav:,.2f}")
                if etf_data.premium_discount is not None:
                    icol2.metric("折溢價", f"{etf_data.premium_discount:+.2f}%")
                if etf_data.expense_ratio:
                    icol3.metric("總費用率", f"{etf_data.expense_ratio}%")
                if etf_data.aum:
                    st.metric("基金規模 (AUM)", f"NT${etf_data.aum:,.0f}")
            
            # 6. 原始數據表格
            if not yearly.empty:
                with st.expander("📋 查看歷年指標數據表"):
                    display_df = yearly.copy()
                    display_df.columns = [
                        "年初價", "年末價", "最高價", "最低價",
                        "年度配息", "殖利率(%)", "價格報酬(%)", "含息報酬(%)",
                    ]
                    st.dataframe(
                        display_df.style.format("{:.2f}"),
                        use_container_width=True,
                    )
            
            if not etf_data.dividends.empty:
                with st.expander("📋 查看完整配息紀錄"):
                    div_display = etf_data.dividends.copy()
                    div_display.columns = ["除息日", "每股配息 (NTD)"]
                    div_display["除息日"] = pd.to_datetime(div_display["除息日"]).dt.strftime("%Y-%m-%d")
                    div_display = div_display.sort_values("除息日", ascending=False)
                    st.dataframe(div_display, use_container_width=True, hide_index=True)
        
        except Exception as e:
            st.error(f"無法取得 ETF `{symbol_input}` 的資料，請確認代號是否正確或稍後再試。\n\n錯誤訊息: {e}")
    
    else:
        # ════════════════════════════════════════
        # 個股盈再表分析模式 (原始邏輯)
        # ════════════════════════════════════════
        try:
            with st.spinner("正在擷取歷年財報並運算中..."):
                stock, metrics, val = run_stock_pipeline(symbol_input)
            
            # 1. 頂部 KPI 卡片
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("目前股價", f"${stock.current_price:,.2f}")
            col2.metric("最新盈再率", f"{val.reinvest_rate}%", delta="標準 < 40%" if val.reinvest_rate < 40 else "偏高", delta_color="normal" if val.reinvest_rate < 40 else "inverse")
            col3.metric("近五年平均 ROE", f"{val.avg_roe}%", delta="標準 > 15%" if val.avg_roe > 15 else "偏低")
            col4.subheader(val.signal)

            # 2. 估值區間卡片
            st.divider()
            st.subheader("🎯 估值價格區間")
            vcol1, vcol2, vcol3 = st.columns(3)
            vcol1.info(f"🟢 便宜價：**${val.cheap}**")
            vcol2.warning(f"🟡 合理價：**${val.fair}**")
            vcol3.error(f"🔴 昂貴價：**${val.expensive}**")

            # 3. 視覺化圖表
            st.divider()
            st.subheader("📈 歷年財務趨勢圖")
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=metrics.index, y=metrics['roe'], mode='lines+markers', name='ROE (%)', line=dict(color='#00CC96', width=3)))
            fig.add_trace(go.Bar(x=metrics.index, y=metrics['reinvest_rate'], name='盈餘再投資率 (%)', marker_color='#636EFA', opacity=0.6))
            
            # 標記安全門檻線
            fig.add_hline(y=15, line_dash="dash", line_color="green", annotation_text="ROE 15% 門檻")
            fig.add_hline(y=40, line_dash="dash", line_color="red", annotation_text="盈再率 40% 警戒線")
            
            fig.update_layout(height=450, hovermode="x unified", legend=dict(orientation="h", y=1.1, x=0))
            st.plotly_chart(fig, use_container_width=True)

            # 4. 原始數據表格
            with st.expander("查看歷年標準化財報數據表"):
                st.dataframe(metrics.style.format("{:.2f}"), use_container_width=True)

        except Exception as e:
            st.error(f"無法取得股票 `{symbol_input}` 的資料，請確認代號是否正確或稍後再試。錯誤訊息: {e}")

