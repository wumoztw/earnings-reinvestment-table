# modules/fetchers/etf_registry.py
"""台灣 ETF 清單與分類註冊表"""

# 台灣熱門 ETF 清單，用於 UI 快速選股與代號識別
# 資料結構: symbol -> {name, category, freq}
TW_ETF_REGISTRY = {
    # ── 市值型 ──
    "0050":   {"name": "元大台灣50",         "category": "市值型",   "freq": "半年配"},
    "006208": {"name": "富邦台50",           "category": "市值型",   "freq": "半年配"},
    "00692":  {"name": "富邦公司治理",       "category": "市值型",   "freq": "半年配"},
    "00922":  {"name": "國泰台灣領袖50",     "category": "市值型",   "freq": "季配"},
    "0051":   {"name": "元大中型100",        "category": "市值型",   "freq": "年配"},

    # ── 高股息型 ──
    "0056":   {"name": "元大高股息",         "category": "高股息",   "freq": "季配"},
    "00878":  {"name": "國泰永續高股息",     "category": "高股息",   "freq": "季配"},
    "00919":  {"name": "群益台灣精選高息",   "category": "高股息",   "freq": "季配"},
    "00713":  {"name": "元大台灣高息低波",   "category": "高股息",   "freq": "季配"},
    "00929":  {"name": "復華台灣科技優息",   "category": "高股息",   "freq": "月配"},
    "00940":  {"name": "元大台灣價值高息",   "category": "高股息",   "freq": "月配"},
    "00915":  {"name": "凱基優選高股息30",   "category": "高股息",   "freq": "季配"},

    # ── 科技/產業型 ──
    "00881":  {"name": "國泰台灣5G+",       "category": "科技產業", "freq": "季配"},
    "00891":  {"name": "中信關鍵半導體",     "category": "科技產業", "freq": "季配"},
    "00892":  {"name": "富邦台灣半導體",     "category": "科技產業", "freq": "季配"},
    "0052":   {"name": "富邦科技",           "category": "科技產業", "freq": "年配"},

    # ── 海外股票型 ──
    "00646":  {"name": "元大S&P500",         "category": "海外股票", "freq": "年配"},
    "00662":  {"name": "富邦NASDAQ",         "category": "海外股票", "freq": "年配"},
    "00757":  {"name": "統一FANG+",          "category": "海外股票", "freq": "不配息"},
    "00830":  {"name": "國泰費城半導體",     "category": "海外股票", "freq": "年配"},

    # ── 債券型 (上櫃, 需加 .TWO) ──
    "00679B": {"name": "元大美債20年",       "category": "債券型",   "freq": "季配"},
    "00687B": {"name": "國泰20年美債",       "category": "債券型",   "freq": "季配"},
    "00720B": {"name": "元大投資級公司債",   "category": "債券型",   "freq": "季配"},
}

# 債券型 ETF 代號集合 (需要 .TWO 後綴)
BOND_ETF_SYMBOLS = {s for s, v in TW_ETF_REGISTRY.items() if v["category"] == "債券型"}

# 所有已知 ETF 代號集合
ALL_ETF_SYMBOLS = set(TW_ETF_REGISTRY.keys())


def is_tw_etf(symbol: str) -> bool:
    """判斷代號是否為台灣 ETF
    
    判斷規則：
    1. 在已知清單中 → 是 ETF
    2. 4~6 碼純數字且以 00 開頭 → 高度可能為 ETF (00xxx 系列)
    3. 代號含 B 後綴 (如 00679B) → 債券 ETF
    """
    symbol = symbol.upper().strip()
    
    # 已在清單中
    if symbol in ALL_ETF_SYMBOLS:
        return True
    
    # 移除可能的 .TW / .TWO 後綴
    clean = symbol.replace(".TW", "").replace(".TWO", "")
    if clean in ALL_ETF_SYMBOLS:
        return True
    
    # 00 開頭的 4~6 碼數字代號 (ETF 命名規則)
    digits_only = clean.rstrip("BbLlRrUu")
    if digits_only.isdigit() and digits_only.startswith("00") and 4 <= len(digits_only) <= 6:
        return True
    
    # 代號含 B 後綴 (債券 ETF)
    if clean.endswith("B") and clean[:-1].isdigit():
        return True
    
    return False


def get_etf_info(symbol: str) -> dict:
    """取得 ETF 註冊資訊，若不在清單中回傳空 dict"""
    clean = symbol.upper().strip().replace(".TW", "").replace(".TWO", "")
    return TW_ETF_REGISTRY.get(clean, {})


def get_yfinance_symbol(symbol: str) -> str:
    """將台灣 ETF 代號轉換為 yfinance 格式
    
    上市 ETF → {symbol}.TW
    上櫃債券 ETF → {symbol}.TWO
    """
    clean = symbol.upper().strip().replace(".TW", "").replace(".TWO", "")
    if clean in BOND_ETF_SYMBOLS:
        return f"{clean}.TWO"
    return f"{clean}.TW"


def get_etf_categories() -> dict:
    """按類別分組回傳 ETF 清單，用於 UI 選單"""
    categories = {}
    for symbol, info in TW_ETF_REGISTRY.items():
        cat = info["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append({"symbol": symbol, **info})
    return categories
