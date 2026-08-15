# earnings-reinvestment-table
earnings-reinvestment-table/
├── .github/
│   └── workflows/
│       └── ci.yml              # GitHub Actions 自動測試 API 連線與計算正確性
├── config/
│   └── settings.py             # 全域參數 (預設篩選門檻、折現率、市場代號)
├── core/
│   ├── interfaces.py           # 抽象介面卡榫 (Fetcher, Calculator, Valuator)
│   └── schemas.py              # 資料結構 (Pydantic / Dataclass)
├── modules/
│   ├── fetchers/
│   │   ├── tw_fetcher.py       # 台股資料擷取器 (yfinance / FinMind)
│   │   └── us_fetcher.py       # 美股資料擷取器 (yfinance)
│   ├── calculators/
│   │   └── metrics.py          # 盈再率、ROE、自由現金流計算
│   └── valuators/
│       └── valuation.py        # 便宜價、合理價、昂貴價估值引擎
├── ui/
│   ├── components.py           # Streamlit 警示卡片與表格元件
│   └── charts.py               # Plotly 互動式圖表 (ROE 走勢、盈再率長條圖)
├── tests/
│   └── test_calculators.py     # 單元測試
├── app.py                      # Streamlit 應用程式進入點 (主頁面)
├── requirements.txt            # Python 相依套件清單
├── .gitignore
└── README.md                   # 專案說明與部署指南
