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
    import urllib.parse as _up
    import re as _re2

    _has_zh = bool(_re2.search(r"[\u4e00-\u9fff]", raw_input))

    if _has_zh:
        # 中文輸入：台股用原字，美股加「美股 stock ticker」提升精準度
        _q_tw   = _up.quote(raw_input)
        _q_us   = _up.quote(f"{raw_input} 美股 stock ticker")
        _q_google = _up.quote(f"{raw_input} stock ticker symbol")
        st.sidebar.markdown(
            f"""**🔍 查詢「{raw_input}」的股票代號：**

🇹🇼 台股
- [Goodinfo 台灣股市資訊網](https://goodinfo.tw/tw/StockList.asp?SEARCH_KEY={_q_tw})
- [Yahoo 股市（台股）](https://tw.stock.yahoo.com/q/s?q={_q_tw})

🇺🇸 美股 / 全球
- [Google 搜尋](https://www.google.com/search?q={_q_google})
- [Yahoo Finance](https://finance.yahoo.com/search/?q={_up.quote(raw_input)})
- [Finviz](https://finviz.com/search.ashx?q={_up.quote(raw_input)})

查到代號後，貼入上方輸入框即可。""",
            unsafe_allow_html=False,
        )
    else:
        # 英文輸入：直接用原字，加 stock ticker 輔助
        _q      = _up.quote(raw_input)
        _q_full = _up.quote(f"{raw_input} stock ticker")
        st.sidebar.markdown(
            f"""**🔍 查詢「{raw_input}」的股票代號：**

🇺🇸 美股 / 全球
- [Google 搜尋](https://www.google.com/search?q={_q_full})
- [Yahoo Finance](https://finance.yahoo.com/search/?q={_q})
- [Finviz](https://finviz.com/search.ashx?q={_q})

🇹🇼 台股
- [Goodinfo 台灣股市資訊網](https://goodinfo.tw/tw/StockList.asp?SEARCH_KEY={_q})

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


# ── 全域樣式 ──
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.dash-header {
    background: linear-gradient(135deg, #0f1923 0%, #1a2840 100%);
    border: 1px solid #2a3f5f;
    border-radius: 12px;
    padding: 24px 28px 20px;
    margin-bottom: 20px;
}
.dash-symbol { font-size: 13px; font-weight: 600; color: #7b9fc7; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 4px; }
.dash-name   { font-size: 26px; font-weight: 700; color: #e8edf5; margin-bottom: 10px; line-height: 1.2; }
.signal-pill {
    display: inline-block;
    padding: 6px 16px;
    border-radius: 20px;
    font-size: 15px;
    font-weight: 600;
    letter-spacing: 0.3px;
}
.signal-green  { background: rgba(0,200,100,0.15); color: #00c864; border: 1px solid rgba(0,200,100,0.3); }
.signal-yellow { background: rgba(255,190,0,0.15);  color: #ffc107; border: 1px solid rgba(255,190,0,0.3); }
.signal-red    { background: rgba(255,80,80,0.15);  color: #ff6b6b; border: 1px solid rgba(255,80,80,0.3); }
.signal-grey   { background: rgba(150,160,180,0.15); color: #9aa5b8; border: 1px solid rgba(150,160,180,0.3); }

.kpi-card {
    background: #131e2b;
    border: 1px solid #243347;
    border-radius: 10px;
    padding: 16px 18px;
    text-align: center;
}
.kpi-label { font-size: 11px; font-weight: 500; color: #6b80a0; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 6px; }
.kpi-value { font-family: 'JetBrains Mono', monospace; font-size: 24px; font-weight: 600; color: #e2e8f3; }
.kpi-sub   { font-size: 11px; color: #4a6080; margin-top: 3px; }
.kpi-good  { color: #00c864; }
.kpi-warn  { color: #ffc107; }
.kpi-bad   { color: #ff6b6b; }

.criterion-card {
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 8px;
    border-left: 4px solid;
    display: flex;
    align-items: flex-start;
    gap: 12px;
}
.crit-pass { background: rgba(0,200,100,0.06); border-color: #00c864; }
.crit-fail { background: rgba(255,80,80,0.06);  border-color: #ff6b6b; }
.crit-na   { background: rgba(150,160,180,0.06); border-color: #4a6080; }
.crit-icon { font-size: 18px; min-width: 24px; }
.crit-name { font-size: 14px; font-weight: 600; color: #c8d5e8; }
.crit-val  { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #7b9fc7; margin-top: 2px; }
.crit-comment { font-size: 12px; color: #5a7090; margin-top: 2px; }

.valuation-bar-wrap { background: #0f1923; border-radius: 10px; padding: 20px 24px; border: 1px solid #243347; margin: 4px 0; }
.val-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.val-label { font-size: 12px; color: #6b80a0; }
.val-price { font-family: 'JetBrains Mono', monospace; font-size: 15px; font-weight: 600; }
.val-cheap { color: #00c864; }
.val-fair  { color: #ffc107; }
.val-exp   { color: #ff6b6b; }
.price-track { position: relative; height: 8px; background: linear-gradient(to right, #00c864 0%, #ffc107 50%, #ff6b6b 100%); border-radius: 4px; margin: 8px 0 12px; }
.price-needle { position: absolute; top: -4px; width: 4px; height: 16px; background: white; border-radius: 2px; transform: translateX(-50%); box-shadow: 0 0 6px rgba(255,255,255,0.6); }
.price-now { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #e2e8f3; text-align: center; margin-top: 4px; }

.section-title { font-size: 13px; font-weight: 600; color: #4a6080; letter-spacing: 1.5px; text-transform: uppercase; margin: 20px 0 12px; border-bottom: 1px solid #1e2f45; padding-bottom: 8px; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h2 style='color:#c8d5e8;font-size:20px;margin-bottom:4px;'>📊 盈餘再投資率 & ETF 評估儀表板</h2>", unsafe_allow_html=True)
st.caption("基於巴菲特/洪瑞泰價值投資邏輯 ｜ 5點選股原則")

current_symbol = st.session_state.symbol

def _signal_class(signal: str) -> str:
    s = signal.lower()
    if "🟢" in signal or "便宜" in signal: return "signal-green"
    if "🟡" in signal or "合理" in signal: return "signal-yellow"
    if "🔴" in signal or "昂貴" in signal: return "signal-red"
    return "signal-grey"

if current_symbol:
    analysis_mode = determine_mode(current_symbol, mode)

    if analysis_mode == "etf":
        try:
            with st.spinner(f"正在擷取 ETF {current_symbol} 資料..."):
                etf_data, result = run_etf_pipeline(current_symbol)
            etf_info = get_etf_info(current_symbol)
            display_name = etf_data.name or etf_info.get("name", current_symbol)
            sig_cls = _signal_class(result.signal)
            st.markdown(f"""
            <div class="dash-header">
                <div class="dash-symbol">ETF · {etf_info.get("category","—")} · 配息 {etf_info.get("freq","—")}</div>
                <div class="dash-name">{current_symbol} {display_name}</div>
                <span class="signal-pill {sig_cls}">{result.signal}</span>
            </div>""", unsafe_allow_html=True)

            c1,c2,c3,c4,c5 = st.columns(5)
            price_lbl = "NT$" if etf_data.market == "TW" else "$"
            c1.markdown(f'<div class="kpi-card"><div class="kpi-label">目前股價</div><div class="kpi-value">{price_lbl}{etf_data.current_price:,.2f}</div></div>', unsafe_allow_html=True)
            yld_cls = "kpi-good" if result.current_yield >= result.avg_yield else "kpi-bad"
            c2.markdown(f'<div class="kpi-card"><div class="kpi-label">近12月殖利率</div><div class="kpi-value {yld_cls}">{result.current_yield}%</div></div>', unsafe_allow_html=True)
            c3.markdown(f'<div class="kpi-card"><div class="kpi-label">歷年平均殖利率</div><div class="kpi-value">{result.avg_yield}%</div></div>', unsafe_allow_html=True)
            c4.markdown(f'<div class="kpi-card"><div class="kpi-label">連續配息次數</div><div class="kpi-value">{result.dividend_streak}</div><div class="kpi-sub">次</div></div>', unsafe_allow_html=True)
            dd = f"{result.max_drawdown}%" if result.max_drawdown is not None else "—"
            dd_cls = "kpi-bad" if result.max_drawdown and result.max_drawdown < -20 else "kpi-warn"
            c5.markdown(f'<div class="kpi-card"><div class="kpi-label">歷史最大回撤</div><div class="kpi-value {dd_cls}">{dd}</div></div>', unsafe_allow_html=True)

            if not result.yearly_metrics.empty:
                st.markdown('<div class="section-title">配息趨勢</div>', unsafe_allow_html=True)
                fig = go.Figure()
                ym = result.yearly_metrics
                if "yield" in ym.columns:
                    fig.add_trace(go.Bar(x=ym.index, y=ym["yield"], name="年殖利率(%)", marker_color="#3b82f6", opacity=0.8))
                fig.add_hline(y=result.avg_yield, line_dash="dash", line_color="#ffc107", annotation_text=f"平均 {result.avg_yield}%")
                fig.update_layout(height=300, plot_bgcolor="#0f1923", paper_bgcolor="#0f1923",
                                  font_color="#7b9fc7", showlegend=False,
                                  xaxis=dict(gridcolor="#1e2f45"), yaxis=dict(gridcolor="#1e2f45"))
                st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"無法取得 ETF `{current_symbol}` 的資料。\n\n**錯誤：** {e}")

    else:
        try:
            with st.spinner("正在擷取歷年財報並運算中..."):
                stock, metrics, val = run_stock_pipeline(current_symbol)

            if stock.data_quality == "insufficient":
                st.error("❌ 財報資料嚴重不足，結果可能不可靠。")

            # ── Header ──
            sig_cls = _signal_class(val.signal)
            mkt_lbl = "台股" if stock.market in ("TW","TWO") else "美股"
            price_sym = "NT$" if stock.market in ("TW","TWO") else "$"
            st.markdown(f"""
            <div class="dash-header">
                <div class="dash-symbol">{mkt_lbl} · {current_symbol}</div>
                <div class="dash-name">{stock.name}</div>
                <span class="signal-pill {sig_cls}">{val.signal}</span>
            </div>""", unsafe_allow_html=True)

            # ── KPI 列 ──
            c1,c2,c3,c4 = st.columns(4)
            c1.markdown(f'''<div class="kpi-card"><div class="kpi-label">目前股價</div>
                <div class="kpi-value">{price_sym}{stock.current_price:,.2f}</div></div>''', unsafe_allow_html=True)
            rr_cls = "kpi-good" if val.reinvest_rate < 80 else "kpi-bad"
            c2.markdown(f'''<div class="kpi-card"><div class="kpi-label">最新盈再率</div>
                <div class="kpi-value {rr_cls}">{val.reinvest_rate}%</div>
                <div class="kpi-sub">{"✓ 達標 <80%" if val.reinvest_rate < 80 else "✗ 偏高"}</div></div>''', unsafe_allow_html=True)
            roe_cls = "kpi-good" if val.avg_roe > 15 else ("kpi-warn" if val.avg_roe > 10 else "kpi-bad")
            c3.markdown(f'''<div class="kpi-card"><div class="kpi-label">近五年平均 ROE</div>
                <div class="kpi-value {roe_cls}">{val.avg_roe}%</div>
                <div class="kpi-sub">{"✓ 達標 >15%" if val.avg_roe > 15 else "✗ 未達標"}</div></div>''', unsafe_allow_html=True)
            bv = f"{price_sym}{val.book_value_used:,.2f}" if val.book_value_used else "—"
            c4.markdown(f'''<div class="kpi-card"><div class="kpi-label">每股淨值</div>
                <div class="kpi-value">{bv}</div>
                <div class="kpi-sub">{val.base_value_method}</div></div>''', unsafe_allow_html=True)

            # ── 估值區間 ──
            st.markdown('<div class="section-title">估值價格區間</div>', unsafe_allow_html=True)
            price = stock.current_price
            cheap, fair, exp = val.cheap, val.fair, val.expensive
            lo, hi = min(cheap * 0.85, price * 0.85), max(exp * 1.15, price * 1.15)
            rng = hi - lo
            pct_cheap = (cheap - lo) / rng * 100
            pct_fair  = (fair  - lo) / rng * 100
            pct_exp   = (exp   - lo) / rng * 100
            pct_now   = max(0, min(100, (price - lo) / rng * 100))
            st.markdown(f"""
            <div class="valuation-bar-wrap">
                <div class="val-row">
                    <span class="val-label">便宜價</span>
                    <span class="val-price val-cheap">{price_sym}{cheap:,.2f}</span>
                    <span class="val-label">合理價</span>
                    <span class="val-price val-fair">{price_sym}{fair:,.2f}</span>
                    <span class="val-label">昂貴價</span>
                    <span class="val-price val-exp">{price_sym}{exp:,.2f}</span>
                </div>
                <div class="price-track">
                    <div class="price-needle" style="left:{pct_now:.1f}%"></div>
                </div>
                <div class="price-now">▲ 目前股價 {price_sym}{price:,.2f}</div>
            </div>""", unsafe_allow_html=True)

            # ── 5點選股原則 ──
            st.markdown('<div class="section-title">5點選股原則</div>', unsafe_allow_html=True)
            if val.all_critical_passed:
                st.success("🎉 所有關鍵條件皆達標！")
            for c in val.criteria:
                if c.passed is True:
                    cls, icon = "crit-pass", "✅"
                elif c.passed is False:
                    cls, icon = "crit-fail", "❌"
                else:
                    cls, icon = "crit-na", "⚪"
                st.markdown(f"""
                <div class="criterion-card {cls}">
                    <div class="crit-icon">{icon}</div>
                    <div>
                        <div class="crit-name">{c.name}</div>
                        <div class="crit-val">{c.value or "—"} <span style="color:#3a5070">（門檻：{c.threshold}）</span></div>
                        <div class="crit-comment">{c.comment}</div>
                    </div>
                </div>""", unsafe_allow_html=True)

            # ── 趨勢圖 ──
            st.markdown('<div class="section-title">歷年財務趨勢</div>', unsafe_allow_html=True)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=metrics.index, y=metrics["roe"],
                mode="lines+markers", name="ROE (%)",
                line=dict(color="#3b82f6", width=2.5),
                marker=dict(size=6, color="#3b82f6")))
            fig.add_trace(go.Bar(x=metrics.index, y=metrics["reinvest_rate"],
                name="盈再率 (%)", marker_color="#8b5cf6", opacity=0.55, yaxis="y2"))
            fig.add_hline(y=15, line_dash="dot", line_color="#00c864", line_width=1,
                annotation_text="ROE 15%", annotation_font_color="#00c864", annotation_font_size=11)
            fig.add_hline(y=80, line_dash="dot", line_color="#ffc107", line_width=1,
                annotation_text="盈再 80%", annotation_font_color="#ffc107",
                annotation_font_size=11, yref="y2")
            fig.update_layout(
                height=380,
                plot_bgcolor="#0f1923", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#7b9fc7", size=12),
                legend=dict(orientation="h", y=1.08, x=0, font_color="#9aa5b8"),
                hovermode="x unified",
                xaxis=dict(gridcolor="#1e2f45", showgrid=True),
                yaxis=dict(title="ROE %", gridcolor="#1e2f45", showgrid=True),
                yaxis2=dict(title="盈再率 %", overlaying="y", side="right",
                            showgrid=False, range=[0, max(200, metrics["reinvest_rate"].max() * 1.3)]),
                margin=dict(l=10, r=10, t=30, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("📋 查看歷年財報數據"):
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
    <div style="text-align:center;padding:60px 20px;color:#3a5070;">
        <div style="font-size:48px;margin-bottom:16px;">📊</div>
        <div style="font-size:18px;font-weight:600;color:#6b80a0;margin-bottom:8px;">輸入股票代號開始分析</div>
        <div style="font-size:14px;">台股輸入數字代號（如 2330），美股輸入英文代號（如 AAPL）</div>
    </div>""", unsafe_allow_html=True)
