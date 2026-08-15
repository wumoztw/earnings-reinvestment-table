# app.py
import streamlit as st
import plotly.graph_objects as go
from modules.fetchers.us_fetcher import UniversalFetcher
from modules.calculators/metrics import FinancialMetricsCalculator
from modules.valuators.valuation import ValueInvestingValuator

st.set_page_config(page_title="Python 盈再表系統", layout="wide", page_icon="📈")

# 初始化模組積木
@st.cache_data(ttl=3600)  # 快取 1 小時，避免頻繁請求被封鎖
def run_analysis_pipeline(symbol: str):
    fetcher = UniversalFetcher()
    calculator = FinancialMetricsCalculator()
    valuator = ValueInvestingValuator()
    
    stock_data = fetcher.fetch(symbol)
    metrics_df = calculator.calculate_metrics(stock_data)
    val_result = valuator.evaluate(stock_data, metrics_df)
    
    return stock_data, metrics_df, val_result

# 側邊欄
st.sidebar.title("🔍 股票分析設定")
symbol_input = st.sidebar.text_input("輸入代號 (台股: 如 2330 / 美股: 如 AAPL)", value="2330").upper()
search_btn = st.sidebar.button("開始分析", type="primary")

st.title("📊 盈餘再投資率評估儀表板")
st.caption("基於巴菲特/洪瑞泰價值投資邏輯的自動化開源分析工具")

if symbol_input:
    try:
        with st.spinner("正在擷取歷年財報並運算中..."):
            stock, metrics, val = run_analysis_pipeline(symbol_input)
        
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
