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
from modules.utils.twelve_client import has_twelve_data_key
from modules.utils.finmind_client import has_finmind_token
from modules.utils.symbol_search import search_symbols

st.set_page_config(page_title="Python 盈再表系統", layout="wide", page_icon="📈")


def _yield_to_price(target_yield: float, etf_data) -> float:
    if target_yield <= 0:
        return 0.0
    div_df = etf_data.dividends
    if div_df.empty:
        return 0.0
    div_df_copy = div_df.copy()
    div_df_copy["date"] = pd.to_datetime(div_df_copy["date"])
    if div_df_copy["date"].dt.tz is not None:
        div_df_copy["date"] = div_df_copy["date"].dt.tz_localize(None)
    cutoff = pd.Timestamp.now().tz_localize(None) - pd.DateOffset(months=12)
    recent = div_df_copy[div_df_copy["date"] >= cutoff]
    if recent.empty:
        return 0.0
    ttm_div = recent["amount"].sum()
    return ttm_div / (target_yield / 100)


@st.cache_data(ttl=3600, show_spinner=False)
def run_stock_pipeline(symbol: str):
    fetcher = UniversalFetcher()
    calculator = FinancialMetricsCalculator()
    valuator = ValueInvestingValuator()
    stock_data = fetcher.fetch(symbol)
    metrics_df = calculator.calculate_metrics(stock_data)
    val_result = valuator.evaluate(stock_data, metrics_df)
    return stock_data, metrics_df, val_result


@st.cache_data(ttl=3600, show_spinner=False)
def run_etf_pipeline(symbol: str):
    fetcher = TwEtfFetcher()
    analyzer = EtfMetricsCalculator()
    etf_data = fetcher.fetch(symbol)
    result = analyzer.analyze(etf_data)
    return etf_data, result


if "symbol" not in st.session_state:
    st.session_state.symbol = "2330"
if "mode" not in st.session_state:
    st.session_state.mode = "自動偵測"
if "clear_search" not in st.session_state:
    st.session_state.clear_search = False

st.sidebar.title("🔍 股票 / ETF 分析設定")
src_bits = []
if has_finmind_token():
    src_bits.append("FinMind(台股)")
if has_twelve_data_key():
    src_bits.append("Twelve Data")
src_bits.append("yfinance")
if has_finmind_token() or has_twelve_data_key():
    st.sidebar.success("資料來源優先序：" + " → ".join(src_bits))
else:
    st.sidebar.warning("未設定 FINMIND_TOKEN / TWELVEDATA_API_KEY，目前僅 yfinance")

mode = st.sidebar.radio(
    "分析模式",
    ["自動偵測", "個股盈再表", "台灣 ETF"],
    index=["自動偵測", "個股盈再表", "台灣 ETF"].index(st.session_state.mode),
    help="自動偵測會根據代號判斷是個股或 ETF",
    key="mode_radio",
)
st.session_state.mode = mode

st.sidebar.divider()

# 單一輸入框：直接輸入代號 or 公司名稱
_input_val = st.session_state.get("_symbol_input_val", st.session_state.symbol)
raw_input = st.sidebar.text_input(
    "🔎 輸入代號或公司名稱",
    value=_input_val,
    placeholder="例：2330 / AAPL / 台積電 / Apple",
    key="unified_input",
).strip()
st.session_state._symbol_input_val = raw_input

# 判斷是否為純代號（純英數或純數字），直接使用；否則做搜尋
import re as _re
_is_direct = bool(_re.fullmatch(r"[A-Za-z0-9\.\-]{1,10}", raw_input))

if raw_input and not _is_direct:
    # 有非代號字元（中文/空白）→ 顯示外部搜尋連結
    import urllib.parse as _up
    _q = _up.quote(raw_input)
    st.sidebar.markdown(
        f"""**🔍 查詢「{raw_input}」的股票代號：**

🇹🇼 台股
- [Goodinfo 台灣股市資訊網](https://goodinfo.tw/tw/StockList.asp?SEARCH_KEY={_q})
- [Yahoo 股市（台股）](https://tw.stock.yahoo.com/q/s?q={_q})

🇺🇸 美股 / 全球
- [Yahoo Finance](https://finance.yahoo.com/search/?q={_q})
- [Finviz](https://finviz.com/search.ashx?q={_q})

查到代號後，貼入上方輸入框即可。""",
        unsafe_allow_html=False,
    )
    symbol_input = st.session_state.symbol  # 維持上一次成功的代號
elif raw_input and _is_direct:
    symbol_input = raw_input.upper()
else:
    symbol_input = st.session_state.symbol

if mode in ["自動偵測", "台灣 ETF"]:
    st.sidebar.divider()
    st.sidebar.subheader("📋 ETF 快速選股")
    categories = get_etf_categories()
    selected_cat = st.sidebar.selectbox("ETF 類別", options=list(categories.keys()), index=0)
    etf_options = categories[selected_cat]
    etf_labels = [f"{e['symbol']} {e['name']} ({e['freq']})" for e in etf_options]
    selected_etf_idx = st.sidebar.selectbox("選擇 ETF", options=range(len(etf_labels)), format_func=lambda i: etf_labels[i], index=0)
    if st.sidebar.button("📌 套用此 ETF", type="secondary"):
        st.session_state.symbol = etf_options[selected_etf_idx]["symbol"]
        st.rerun()

st.sidebar.divider()
search_btn = st.sidebar.button("🚀 開始分析", type="primary", use_container_width=True)

if search_btn or (symbol_input and symbol_input != st.session_state.symbol):
    st.session_state.symbol = symbol_input


def determine_mode(symbol: str, user_mode: str) -> str:
    if user_mode == "個股盈再表":
        return "stock"
    elif user_mode == "台灣 ETF":
        return "etf"
    else:
        return "etf" if is_tw_etf(symbol) else "stock"


st.title("📊 盈餘再投資率 & ETF 評估儀表板")
st.caption("基於巴菲特/洪瑞泰價值投資邏輯 + 5點選股原則｜台股 FinMind→Twelve→yf｜美股 Twelve→yf")

current_symbol = st.session_state.symbol

if current_symbol:
    analysis_mode = determine_mode(current_symbol, mode)
    
    if analysis_mode == "etf":
        try:
            with st.spinner(f"正在擷取 ETF {current_symbol} 的歷史資料並分析中..."):
                etf_data, result = run_etf_pipeline(current_symbol)
            etf_info = get_etf_info(current_symbol)
            display_name = etf_data.name or etf_info.get("name", current_symbol)
            st.subheader(f"🏷️ {current_symbol} {display_name}")
            if etf_info:
                st.caption(f"類別: {etf_info.get('category', '—')} ｜ 配息頻率: {etf_info.get('freq', '—')}")
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("目前股價", f"NT${etf_data.current_price:,.2f}")
            col2.metric("近12月殖利率", f"{result.current_yield}%", delta="偏高" if result.current_yield > result.avg_yield else "偏低", delta_color="normal" if result.current_yield >= result.avg_yield else "inverse")
            col3.metric("歷年平均殖利率", f"{result.avg_yield}%")
            col4.metric("連續配息次數", f"{result.dividend_streak} 次")
            col5.metric("歷史最大回撤", f"{result.max_drawdown}%" if result.max_drawdown is not None else "—")
            st.info(f"**投資訊號：** {result.signal}")
        except Exception as e:
            st.error(f"無法取得 ETF `{current_symbol}` 的資料。\n\n**錯誤：** {e}")
    else:
        try:
            with st.spinner("正在擷取歷年財報並運算中..."):
                stock, metrics, val = run_stock_pipeline(current_symbol)
            if stock.data_quality == "partial":
                st.warning("⚠️ 部分財報科目缺失，分析結果僅供參考。")
            elif stock.data_quality == "insufficient":
                st.error("❌ 財報資料嚴重不足，結果可能不可靠。")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("目前股價", f"${stock.current_price:,.2f}")
            col2.metric("最新盈再率", f"{val.reinvest_rate}%", delta="達標 <80%" if val.reinvest_rate < 80 else "偏高", delta_color="normal" if val.reinvest_rate < 80 else "inverse")
            col3.metric("近五年平均 ROE", f"{val.avg_roe}%", delta="達標 >15%" if val.avg_roe > 15 else "偏低")
            col4.subheader(val.signal)
            st.divider()
            st.subheader("✅ 5點選股原則檢查清單")
            if val.all_critical_passed:
                st.success("🎉 所有關鍵條件皆達標！")
            else:
                st.warning("部分關鍵條件未達標或資料不足，建議列入觀察。")
            for c in val.criteria:
                icon = "✅" if c.passed is True else ("❌" if c.passed is False else "⚪")
                cols = st.columns([0.08, 0.35, 0.25, 0.32])
                cols[0].markdown(f"### {icon}")
                cols[1].markdown(f"**{c.name}**")
                cols[2].markdown(f"`{c.value}`")
                cols[3].caption(c.comment)
            st.divider()
            st.subheader("🎯 估值價格區間")
            vcol1, vcol2, vcol3 = st.columns(3)
            vcol1.info(f"🟢 便宜價：**${val.cheap}**")
            vcol2.warning(f"🟡 合理價：**${val.fair}**")
            vcol3.error(f"🔴 昂貴價：**${val.expensive}**")
            st.divider()
            st.subheader("📈 歷年財務趨勢圖")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=metrics.index, y=metrics["roe"], mode="lines+markers", name="ROE (%)", line=dict(color="#00CC96", width=3)))
            fig.add_trace(go.Bar(x=metrics.index, y=metrics["reinvest_rate"], name="盈餘再投資率 (%)", marker_color="#636EFA", opacity=0.6))
            fig.add_hline(y=15, line_dash="dash", line_color="green", annotation_text="ROE 15%")
            fig.add_hline(y=80, line_dash="dash", line_color="orange", annotation_text="盈再 80%")
            fig.update_layout(height=450, hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)
            with st.expander("查看歷年財報"):
                display_cols = [c for c in ["net_income", "equity", "fixed_assets", "long_term_invest", "roe", "reinvest_rate"] if c in metrics.columns]
                st.dataframe(metrics[display_cols].style.format("{:.2f}"), use_container_width=True)
        except Exception as e:
            st.error(f"無法取得股票 `{current_symbol}` 的資料。\n\n**錯誤：** {e}")
            st.info("請確認代號（台股 2330、美股 AAPL），或該標的財報是否已公開。")
else:
    st.info("請在左側輸入股票或 ETF 代號後點擊「開始分析」。")
