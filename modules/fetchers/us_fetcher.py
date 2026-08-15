# modules/fetchers/us_fetcher.py
import yfinance as yf
import pandas as pd
from core.interfaces import BaseFetcher
from core.schemas import StockData

class UniversalFetcher(BaseFetcher):
    """通用抓取器：美股直接輸入 (如 AAPL)，台股自動補綴 .TW (如 2330.TW)"""
    def fetch(self, symbol: str) -> StockData:
        ticker_symbol = f"{symbol}.TW" if symbol.isdigit() else symbol
        ticker = yf.Ticker(ticker_symbol)
        
        bs = ticker.balance_sheet
        inc = ticker.financials
        
        # 轉換為以年為單位的標準欄位
        years = [col.year for col in bs.columns]
        df = pd.DataFrame(index=years)
        
        # 提取核心科目（支援 yfinance 標準標籤與容錯）
        df['net_income'] = inc.loc['Net Income'].values if 'Net Income' in inc.index else 0
        df['equity'] = bs.loc['Stockholders Equity'].values if 'Stockholders Equity' in bs.index else 1
        
        # 固定資產 (Net PPE)
        ppe_key = 'Net PPE' if 'Net PPE' in bs.index else 'Gross PPE'
        df['fixed_assets'] = bs.loc[ppe_key].values if ppe_key in bs.index else 0
        
        # 長期投資 (Investments And Advances)
        inv_key = 'Investments And Advances' if 'Investments And Advances' in bs.index else 'Long Term Equity Investment'
        df['long_term_invest'] = bs.loc[inv_key].values if inv_key in bs.index else 0
        
        # 排序時間由舊到新
        df = df.sort_index(ascending=True)
        
        info = ticker.fast_info
        price = info.last_price or 0.0
        name = ticker.info.get('shortName', symbol)
        market = "TW" if symbol.isdigit() else "US"

        return StockData(
            symbol=symbol,
            name=name,
            market=market,
            current_price=price,
            financials=df
        )
