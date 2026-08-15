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
from modules.utils.symbol_search import search_symbols, get_tw_stock_list_debug

st.set_page_config(page_title="盈再分析", layout="wide", page_icon="📈", initial_sidebar_state="expanded")

# 最優先注入：隱藏 sidebar 頂部的 keyboard_double 文字
st.markdown("""
<style>
[data-testid="stSidebarCollapseButton"] { visibility: hidden; height: 0; overflow: hidden; }
[data-testid="stSidebarCollapseButton"] * { display: none !important; }
button[data-testid="baseButton-header"] { display: none !important; }
/* Streamlit 1.x 的收合按鈕選法 */
.st-emotion-cache-yfhhig { display: none !important; }
.st-emotion-cache-1f3w014 { display: none !important; }
/* 通殺：sidebar 頂部第一個按鈕 */
section[data-testid="stSidebar"] > div > div:first-child button {
    visibility: hidden !important;
    height: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
}
</style>
""", unsafe_allow_html=True)


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


# ── session state ──
if "symbol" not in st.session_state:
    st.session_state.symbol = "2330"
if "mode" not in st.session_state:
    st.session_state.mode = "自動偵測"
if "clear_search" not in st.session_state:
    st.session_state.clear_search = False

# ══════════════════════════════════════════
#  Sidebar
# ══════════════════════════════════════════
st.sidebar.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;700&family=DM+Mono:wght@400;500&display=swap');
section[data-testid="stSidebar"] { background: #F2EFE9; border-right: 1px solid #DDD8CF; }
section[data-testid="stSidebar"] * { font-family: 'Noto Sans JP', sans-serif !important; }
section[data-testid="stSidebar"] .stButton button {
    background: #1C1C1E; color: #F7F5F0; border: none;
    border-radius: 4px; font-weight: 500; letter-spacing: 0.5px;
}
section[data-testid="stSidebar"] > div:first-child { padding-top: 16px !important; }
.sb-label { font-size: 10px; letter-spacing: 2px; color: #8C8579; text-transform: uppercase; margin-bottom: 4px; }

/* 重新設計原生收合按鈕 */
[data-testid="stSidebarCollapseButton"] button {
    background: #EDEAE4 !important;
    border: 1px solid #DDD8CF !important;
    border-radius: 4px !important;
    width: 28px !important;
    height: 28px !important;
    padding: 0 !important;
    color: #5A5A5A !important;
}
[data-testid="stSidebarCollapseButton"] button:hover {
    background: #DDD8CF !important;
    color: #1C1C1E !important;
}
[data-testid="stSidebarCollapseButton"] button svg {
    width: 14px !important;
    height: 14px !important;
}
/* 展開時的浮動按鈕也一起美化 */
[data-testid="collapsedControl"] button {
    background: #F2EFE9 !important;
    border: 1px solid #DDD8CF !important;
    border-radius: 4px !important;
    color: #5A5A5A !important;
}
</style>
""", unsafe_allow_html=True)

st.sidebar.markdown('<p style="font-size:18px;font-weight:700;color:#1C1C1E;margin:0;letter-spacing:1px;">盈再分析</p>', unsafe_allow_html=True)
st.sidebar.markdown('<p style="font-size:10px;color:#8C8579;letter-spacing:2px;margin-top:2px;">EARNINGS REINVESTMENT ANALYZER</p>', unsafe_allow_html=True)
st.sidebar.divider()

src_bits = []
if has_finmind_token():
    src_bits.append("FinMind")
if has_twelve_data_key():
    src_bits.append("Twelve Data")
src_bits.append("yfinance")
if has_finmind_token() or has_twelve_data_key():
    st.sidebar.success("資料來源：" + " → ".join(src_bits))
else:
    st.sidebar.warning("未設定 API Key，僅使用 yfinance")

mode = st.sidebar.radio(
    "分析模式",
    ["自動偵測", "個股盈再表", "台灣 ETF"],
    index=["自動偵測", "個股盈再表", "台灣 ETF"].index(st.session_state.mode),
    key="mode_radio",
)
st.session_state.mode = mode

st.sidebar.divider()

import re as _re
_input_val = st.session_state.get("_symbol_input_val", st.session_state.symbol)
raw_input = st.sidebar.text_input(
    "代號 / 公司名稱",
    value=_input_val,
    placeholder="2330 · AAPL · 台積電",
    key="unified_input",
).strip()
st.session_state._symbol_input_val = raw_input

_is_direct = bool(_re.fullmatch(r"[A-Za-z0-9\.\-]{1,10}", raw_input))

if raw_input and not _is_direct:
    import urllib.parse as _up
    _has_zh = bool(_re.search(r"[\u4e00-\u9fff]", raw_input))
    if _has_zh:
        _q_tw = _up.quote(raw_input)
        _q_g  = _up.quote(f"{raw_input} stock ticker symbol")
        st.sidebar.markdown(f"""**查詢「{raw_input}」代號：**

🇹🇼 [Goodinfo]( https://goodinfo.tw/tw/StockList.asp?SEARCH_KEY={_q_tw}) · [Yahoo台股](https://tw.stock.yahoo.com/q/s?q={_q_tw})
🇺🇸 [Google]( https://www.google.com/search?q={_q_g}) · [Yahoo Finance](https://finance.yahoo.com/search/?q={_up.quote(raw_input)})

查到後貼入上方框即可。""")
    else:
        _q = _up.quote(raw_input)
        _qf = _up.quote(f"{raw_input} stock ticker")
        st.sidebar.markdown(f"""**查詢「{raw_input}」代號：**

🇺🇸 [Google](https://www.google.com/search?q={_qf}) · [Yahoo Finance](https://finance.yahoo.com/search/?q={_q}) · [Finviz](https://finviz.com/search.ashx?q={_q})
🇹🇼 [Goodinfo](https://goodinfo.tw/tw/StockList.asp?SEARCH_KEY={_q})

查到後貼入上方框即可。""")
    symbol_input = st.session_state.symbol
elif raw_input and _is_direct:
    symbol_input = raw_input.upper()
else:
    symbol_input = st.session_state.symbol

if mode in ["自動偵測", "台灣 ETF"]:
    st.sidebar.divider()
    st.sidebar.markdown('<p class="sb-label">ETF 快速選股</p>', unsafe_allow_html=True)
    categories = get_etf_categories()
    selected_cat = st.sidebar.selectbox("類別", options=list(categories.keys()), index=0, label_visibility="collapsed")
    etf_options = categories[selected_cat]
    etf_labels = [f"{e['symbol']} {e['name']} ({e['freq']})" for e in etf_options]
    selected_etf_idx = st.sidebar.selectbox("ETF", options=range(len(etf_labels)), format_func=lambda i: etf_labels[i], index=0, label_visibility="collapsed")
    if st.sidebar.button("套用此 ETF", type="secondary"):
        st.session_state.symbol = etf_options[selected_etf_idx]["symbol"]
        st.rerun()

st.sidebar.divider()
search_btn = st.sidebar.button("開始分析", type="primary", use_container_width=True)

if search_btn or (symbol_input and symbol_input != st.session_state.symbol):
    st.session_state.symbol = symbol_input


# ══════════════════════════════════════════
#  Global CSS
# ══════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;700&family=DM+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans JP', sans-serif;
    background: #F7F5F0;
    color: #1C1C1E;
}

/* ── 通用 section label ── */
.sec-label {
    font-size: 10px;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: #8C8579;
    border-bottom: 1px solid #DDD8CF;
    padding-bottom: 6px;
    margin: 32px 0 16px;
}

/* ── Header ── */
.stock-header {
    border-left: 3px solid #1C1C1E;
    padding: 4px 0 4px 16px;
    margin-bottom: 24px;
}
.stock-eyebrow { font-size: 11px; letter-spacing: 2px; color: #8C8579; }
.stock-name    { font-size: 28px; font-weight: 700; color: #1C1C1E; line-height: 1.2; margin: 4px 0; }
.signal-tag {
    display: inline-block;
    font-size: 13px;
    font-weight: 500;
    padding: 4px 14px;
    border-radius: 2px;
    letter-spacing: 0.5px;
}
.sig-green  { background: #E8F5ED; color: #1A7A40; }
.sig-yellow { background: #FEF8E7; color: #8A6A00; }
.sig-red    { background: #FDECEA; color: #B02020; }
.sig-grey   { background: #EFEFEF; color: #5A5A5A; }

/* ── KPI ── */
.kpi-wrap {
    border-top: 2px solid #1C1C1E;
    border-bottom: 1px solid #DDD8CF;
    padding: 16px 0;
    text-align: center;
}
.kpi-lbl { font-size: 10px; letter-spacing: 2px; color: #8C8579; margin-bottom: 6px; }
.kpi-val {
    font-family: 'DM Mono', monospace;
    font-size: 26px;
    font-weight: 500;
    color: #1C1C1E;
    line-height: 1;
}
.kpi-sub { font-size: 11px; color: #8C8579; margin-top: 4px; }
.c-green  { color: #1A7A40; }
.c-amber  { color: #8A6A00; }
.c-red    { color: #B02020; }

/* ── 估值竹節尺 ── */
.val-ruler {
    background: #EFECE6;
    border: 1px solid #DDD8CF;
    border-radius: 4px;
    padding: 20px 24px 16px;
}
.ruler-labels {
    display: flex;
    justify-content: space-between;
    margin-bottom: 6px;
}
.ruler-lbl { font-size: 10px; letter-spacing: 1px; color: #8C8579; }
.ruler-price {
    font-family: 'DM Mono', monospace;
    font-size: 15px;
    font-weight: 500;
}
.r-green { color: #1A7A40; }
.r-amber { color: #8A6A00; }
.r-red   { color: #B02020; }
.ruler-track {
    position: relative;
    height: 10px;
    border-radius: 2px;
    background: linear-gradient(to right, #A8D5B5 0%, #EAC96A 50%, #E8908A 100%);
    margin: 4px 0 10px;
}
.ruler-mark {
    position: absolute;
    top: -4px;
    width: 3px;
    height: 18px;
    background: #1C1C1E;
    border-radius: 1px;
    transform: translateX(-50%);
}
.ruler-now {
    font-family: 'DM Mono', monospace;
    font-size: 12px;
    color: #1C1C1E;
    text-align: center;
    font-weight: 500;
}
.ruler-ticks {
    display: flex;
    justify-content: space-between;
    margin: 0;
    padding: 0;
}
.ruler-tick { font-size: 9px; color: #C0BAB0; }

/* ── 選股原則表格 ── */
.criteria-table { width: 100%; border-collapse: collapse; }
.criteria-table tr { border-bottom: 1px solid #EDEAE4; }
.criteria-table tr:last-child { border-bottom: none; }
.criteria-table td { padding: 10px 8px; vertical-align: top; font-size: 13px; }
.crit-icon-cell { width: 28px; font-size: 14px; padding-top: 11px; }
.crit-name-cell { font-weight: 500; color: #1C1C1E; white-space: nowrap; }
.crit-val-cell  { font-family: 'DM Mono', monospace; font-size: 12px; color: #5A5A5A; }
.crit-thr-cell  { font-size: 11px; color: #8C8579; }
.crit-cmt-cell  { font-size: 11px; color: #8C8579; font-style: italic; }
.pass-row td { background: transparent; }
.fail-row td { background: #FEF8F8; }
.na-row   td { background: transparent; opacity: 0.7; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════
#  Main
# ══════════════════════════════════════════
def determine_mode(symbol: str, user_mode: str) -> str:
    if user_mode == "個股盈再表":
        return "stock"
    if user_mode == "台灣 ETF":
        return "etf"
    return "etf" if is_tw_etf(symbol) else "stock"


def _sig_cls(signal: str) -> str:
    if "🟢" in signal or "便宜" in signal: return "sig-green"
    if "🟡" in signal or "合理" in signal: return "sig-yellow"
    if "🔴" in signal or "昂貴" in signal: return "sig-red"
    return "sig-grey"


# 頁首
st.markdown("""
<div style="display:flex;align-items:baseline;gap:12px;margin-bottom:4px;">
  <span style="font-size:22px;font-weight:700;letter-spacing:1px;color:#1C1C1E;">盈再分析</span>
  <span style="font-size:11px;letter-spacing:3px;color:#8C8579;">EARNINGS REINVESTMENT ANALYZER</span>
</div>
<div style="font-size:12px;color:#8C8579;border-bottom:1px solid #DDD8CF;padding-bottom:12px;margin-bottom:24px;">
  基於巴菲特 · 洪瑞泰價值投資邏輯 · 五點選股原則
</div>
""", unsafe_allow_html=True)

current_symbol = st.session_state.symbol

if current_symbol:
    analysis_mode = determine_mode(current_symbol, mode)

    # ─── ETF ───────────────────────────────────────
    if analysis_mode == "etf":
        try:
            with st.spinner("資料擷取中…"):
                etf_data, result = run_etf_pipeline(current_symbol)
            etf_info = get_etf_info(current_symbol)
            display_name = etf_data.name or etf_info.get("name", current_symbol)
            price_sym = "NT$" if etf_data.market == "TW" else "$"

            # Header
            cls = _sig_cls(result.signal)
            st.markdown(f"""
            <div class="stock-header">
              <div class="stock-eyebrow">ETF · {etf_info.get("category","—")} · 配息 {etf_info.get("freq","—")}</div>
              <div class="stock-name">{current_symbol} &nbsp;<span style="font-weight:300;">{display_name}</span></div>
              <span class="signal-tag {cls}">{result.signal}</span>
            </div>""", unsafe_allow_html=True)

            # KPI
            c1,c2,c3,c4,c5 = st.columns(5)
            c1.markdown(f'<div class="kpi-wrap"><div class="kpi-lbl">目前股價</div><div class="kpi-val">{price_sym}{etf_data.current_price:,.2f}</div></div>', unsafe_allow_html=True)
            yc = "c-green" if result.current_yield >= result.avg_yield else "c-red"
            c2.markdown(f'<div class="kpi-wrap"><div class="kpi-lbl">近12月殖利率</div><div class="kpi-val {yc}">{result.current_yield}%</div></div>', unsafe_allow_html=True)
            c3.markdown(f'<div class="kpi-wrap"><div class="kpi-lbl">歷年平均殖利率</div><div class="kpi-val">{result.avg_yield}%</div></div>', unsafe_allow_html=True)
            c4.markdown(f'<div class="kpi-wrap"><div class="kpi-lbl">連續配息</div><div class="kpi-val">{result.dividend_streak}</div><div class="kpi-sub">次</div></div>', unsafe_allow_html=True)
            dd = f"{result.max_drawdown}%" if result.max_drawdown is not None else "—"
            dc = "c-red" if result.max_drawdown and result.max_drawdown < -20 else "c-amber"
            c5.markdown(f'<div class="kpi-wrap"><div class="kpi-lbl">最大回撤</div><div class="kpi-val {dc}">{dd}</div></div>', unsafe_allow_html=True)

            # 配息趨勢圖
            if not result.yearly_metrics.empty:
                st.markdown('<div class="sec-label">配息趨勢</div>', unsafe_allow_html=True)
                ym = result.yearly_metrics
                fig = go.Figure()
                if "yield" in ym.columns:
                    fig.add_trace(go.Bar(x=ym.index, y=ym["yield"], name="年殖利率(%)",
                        marker_color="#6B9E7A", opacity=0.75))
                fig.add_hline(y=result.avg_yield, line_dash="dot", line_color="#8A6A00",
                    annotation_text=f"平均 {result.avg_yield}%", annotation_font_color="#8A6A00")
                fig.update_layout(height=280, plot_bgcolor="#F7F5F0", paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#5A5A5A", size=11, family="Noto Sans JP"),
                    showlegend=False, margin=dict(l=0,r=0,t=16,b=0),
                    xaxis=dict(gridcolor="#EDEAE4"), yaxis=dict(gridcolor="#EDEAE4"))
                st.plotly_chart(fig, use_container_width=True)

        except Exception as e:
            st.error(f"無法取得 ETF `{current_symbol}` 的資料。\n\n**錯誤：** {e}")

    # ─── 個股 ──────────────────────────────────────
    else:
        try:
            with st.spinner("財報擷取中…"):
                stock, metrics, val = run_stock_pipeline(current_symbol)

            if stock.data_quality == "insufficient":
                st.warning("財報資料不足，分析結果僅供參考。")

            mkt_lbl  = "台股" if stock.market in ("TW","TWO") else "美股"
            price_sym = "NT$" if stock.market in ("TW","TWO") else "$"

            # ── Header ──
            cls = _sig_cls(val.signal)
            st.markdown(f"""
            <div class="stock-header">
              <div class="stock-eyebrow">{mkt_lbl} · {current_symbol}</div>
              <div class="stock-name">{stock.name}</div>
              <span class="signal-tag {cls}">{val.signal}</span>
            </div>""", unsafe_allow_html=True)

            # ── KPI ──
            c1,c2,c3,c4 = st.columns(4)
            c1.markdown(f'<div class="kpi-wrap"><div class="kpi-lbl">目前股價</div><div class="kpi-val">{price_sym}{stock.current_price:,.2f}</div></div>', unsafe_allow_html=True)
            rc = "c-green" if val.reinvest_rate < 80 else "c-red"
            rs = "達標" if val.reinvest_rate < 80 else "偏高"
            c2.markdown(f'<div class="kpi-wrap"><div class="kpi-lbl">最新盈再率</div><div class="kpi-val {rc}">{val.reinvest_rate}%</div><div class="kpi-sub">{rs}</div></div>', unsafe_allow_html=True)
            oc = "c-green" if val.avg_roe > 15 else ("c-amber" if val.avg_roe > 10 else "c-red")
            os_ = "達標" if val.avg_roe > 15 else "未達標"
            c3.markdown(f'<div class="kpi-wrap"><div class="kpi-lbl">五年平均 ROE</div><div class="kpi-val {oc}">{val.avg_roe}%</div><div class="kpi-sub">{os_}</div></div>', unsafe_allow_html=True)
            bv = f"{price_sym}{val.book_value_used:,.2f}" if val.book_value_used else "—"
            c4.markdown(f'<div class="kpi-wrap"><div class="kpi-lbl">每股淨值</div><div class="kpi-val">{bv}</div></div>', unsafe_allow_html=True)

            # ── 估值竹節尺 ──
            st.markdown('<div class="sec-label">估值價格區間</div>', unsafe_allow_html=True)
            price = stock.current_price
            cheap, fair, exp = val.cheap, val.fair, val.expensive
            lo = min(cheap * 0.82, price * 0.82)
            hi = max(exp * 1.18, price * 1.18)
            rng = hi - lo or 1
            pct_now = max(1, min(99, (price - lo) / rng * 100))
            st.markdown(f"""
            <div class="val-ruler">
              <div class="ruler-labels">
                <div><div class="ruler-lbl">便宜價</div><div class="ruler-price r-green">{price_sym}{cheap:,.2f}</div></div>
                <div style="text-align:center;"><div class="ruler-lbl">合理價</div><div class="ruler-price r-amber">{price_sym}{fair:,.2f}</div></div>
                <div style="text-align:right;"><div class="ruler-lbl">昂貴價</div><div class="ruler-price r-red">{price_sym}{exp:,.2f}</div></div>
              </div>
              <div class="ruler-track">
                <div class="ruler-mark" style="left:{pct_now:.1f}%"></div>
              </div>
              <div class="ruler-now">▲ &nbsp;目前股價 &nbsp;{price_sym}{price:,.2f}</div>
            </div>""", unsafe_allow_html=True)

            # ── 五點選股原則 ──
            st.markdown('<div class="sec-label">五點選股原則</div>', unsafe_allow_html=True)
            if val.all_critical_passed:
                st.success("すべての条件達成 — 所有關鍵條件皆達標")
            rows_html = ""
            for c in val.criteria:
                if c.passed is True:
                    row_cls, icon = "pass-row", "✅"
                elif c.passed is False:
                    row_cls, icon = "fail-row", "❌"
                else:
                    row_cls, icon = "na-row", "　"
                rows_html += f"""
                <tr class="{row_cls}">
                  <td class="crit-icon-cell">{icon}</td>
                  <td class="crit-name-cell">{c.name}</td>
                  <td class="crit-val-cell">{c.value or "—"}</td>
                  <td class="crit-thr-cell">{c.threshold}</td>
                  <td class="crit-cmt-cell">{c.comment}</td>
                </tr>"""
            st.markdown(f"""
            <table class="criteria-table">
              <thead><tr style="border-bottom:2px solid #1C1C1E;">
                <th style="width:28px;"></th>
                <th style="text-align:left;font-size:10px;letter-spacing:2px;color:#8C8579;font-weight:500;padding:6px 8px;">項目</th>
                <th style="text-align:left;font-size:10px;letter-spacing:2px;color:#8C8579;font-weight:500;padding:6px 8px;">數值</th>
                <th style="text-align:left;font-size:10px;letter-spacing:2px;color:#8C8579;font-weight:500;padding:6px 8px;">門檻</th>
                <th style="text-align:left;font-size:10px;letter-spacing:2px;color:#8C8579;font-weight:500;padding:6px 8px;">備註</th>
              </tr></thead>
              <tbody>{rows_html}</tbody>
            </table>""", unsafe_allow_html=True)

            # ── 趨勢圖 ──
            st.markdown('<div class="sec-label">歷年財務趨勢</div>', unsafe_allow_html=True)
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=metrics.index, y=metrics["roe"],
                mode="lines+markers", name="ROE (%)",
                line=dict(color="#2D6A4F", width=2),
                marker=dict(size=5, color="#2D6A4F", symbol="circle")))
            fig.add_trace(go.Bar(
                x=metrics.index, y=metrics["reinvest_rate"],
                name="盈再率 (%)", marker_color="#C0392B", opacity=0.25, yaxis="y2"))
            fig.add_hline(y=15, line_dash="dot", line_color="#2D6A4F", line_width=1,
                annotation_text="ROE 15%", annotation_font_color="#2D6A4F", annotation_font_size=10)
            fig.add_hline(y=80, line_dash="dot", line_color="#C0392B", line_width=1,
                annotation_text="盈再 80%", annotation_font_color="#C0392B",
                annotation_font_size=10, yref="y2")
            fig.update_layout(
                height=340,
                plot_bgcolor="#F7F5F0", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#8C8579", size=11, family="Noto Sans JP"),
                legend=dict(orientation="h", y=1.06, x=0, bgcolor="rgba(0,0,0,0)"),
                hovermode="x unified",
                xaxis=dict(gridcolor="#EDEAE4", showgrid=True, zeroline=False),
                yaxis=dict(title="ROE %", gridcolor="#EDEAE4", showgrid=True, zeroline=False),
                yaxis2=dict(title="盈再率 %", overlaying="y", side="right",
                            showgrid=False, range=[0, max(200, metrics["reinvest_rate"].max() * 1.3)]),
                margin=dict(l=0, r=0, t=30, b=0),
            )
            st.plotly_chart(fig, use_container_width=True)

            # ── 財報明細 ──
            with st.expander("財報明細"):
                col_rename = {"net_income":"淨利","equity":"股東權益",
                              "fixed_assets":"固定資產","long_term_invest":"長期投資",
                              "roe":"ROE(%)","reinvest_rate":"盈再率(%)"}
                display_cols = [c for c in col_rename if c in metrics.columns]
                df_show = metrics[display_cols].rename(columns=col_rename)
                st.dataframe(df_show.style.format("{:.2f}"), use_container_width=True)

        except Exception as e:
            st.error(f"無法取得股票 `{current_symbol}` 的資料。\n\n**錯誤：** {e}")
            st.info("請確認代號（台股 2330、美股 AAPL），或該標的財報是否已公開。")

else:
    st.markdown("""
    <div style="padding:80px 0;text-align:center;">
      <div style="font-size:13px;letter-spacing:4px;color:#C0BAB0;margin-bottom:12px;">ENTER A SYMBOL TO BEGIN</div>
      <div style="font-size:36px;font-weight:700;color:#DDD8CF;">—</div>
    </div>""", unsafe_allow_html=True)
