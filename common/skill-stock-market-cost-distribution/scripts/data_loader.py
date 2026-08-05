import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional

class DataLoader:
    """
    DataLoader handles reading and aligning stock historical daily prices,
    company share capital, and dividend schedule from the synced local CSVs.
    """
    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            # Default to the data/ folder inside the repository root
            self.data_dir = Path(__file__).resolve().parent.parent / "data"
        else:
            self.data_dir = Path(data_dir)
            
        self.yahoo_dir = self.data_dir / "Yahoo.Finance"
        self.goodinfo_dir = self.data_dir / "Python-Actions.GoodInfo.Analyzer"

    def load_daily_prices(self, stock_code: str) -> pd.DataFrame:
        """
        Loads the daily OHLCV price series for a given stock code from Yahoo Finance CSV.
        """
        csv_path = self.yahoo_dir / "raw_yahoo_finance_daily_price.csv"
        if not csv_path.exists():
            raise FileNotFoundError(f"Yahoo daily price CSV not found at {csv_path}")

        # Columns in Yahoo Finance CSV:
        # stock_code,company_name,market,yahoo_symbol,交易_日期,開盤價,最高價,最低價,收盤價,volume,download_timestamp
        # Standardize stock code matching (ensure string comparison)
        stock_code_str = str(stock_code).strip()
        
        # Read the file chunk-by-chunk or directly (it's around 42MB, direct load is fast enough)
        df = pd.read_csv(csv_path, dtype={"stock_code": str}, encoding="utf-8-sig")
        df = df[df["stock_code"] == stock_code_str].copy()
        
        if df.empty:
            raise ValueError(f"No daily price data found for stock code: {stock_code_str}")

        # Rename columns to standard English fields
        rename_map = {
            "交易_日期": "Date",
            "開盤價": "Open",
            "最高價": "High",
            "最低價": "Low",
            "收盤價": "Close",
            "volume": "Volume"
        }
        df = df.rename(columns=rename_map)
        
        # Select and sort by date
        df = df[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date").reset_index(drop=True)
        
        # Fill missing values if any
        df = df.dropna(subset=["Date", "Close"])
        
        return df

    def load_shares_outstanding(self, stock_code: str) -> float:
        """
        Retrieves the latest share capital (in shares) from GoodInfo performance CSV.
        In Taiwan, par value is typically 10 NTD. Total shares = Share Capital (億元) * 10,000,000.
        """
        csv_path = self.goodinfo_dir / "cleaned_performance.csv"
        if not csv_path.exists():
            raise FileNotFoundError(f"GoodInfo performance CSV not found at {csv_path}")

        stock_code_str = str(stock_code).strip()
        df = pd.read_csv(csv_path, dtype={"stock_code": str}, encoding="utf-8-sig")
        df = df[df["stock_code"] == stock_code_str].copy()
        
        if df.empty:
            # Fallback default value (e.g. 1 billion shares)
            print(f"[Warning] No performance capital data found for {stock_code_str}. Using default 100M shares.")
            return 100_000_000.0

        # Sort by year/quarter to get the latest (usually first or last depending on order)
        # Performance rows have '年度' column.
        # Let's sort to find the latest non-empty '股本_億'
        df = df.dropna(subset=["股本_億"])
        if df.empty:
            return 100_000_000.0
            
        # Get the latest row (usually row with max year/quarter, or first row)
        # Let's just find the max value under '年度' or the first row in file order
        latest_capital_100m = df.iloc[0]["股本_億"]
        
        # Convert 億元 (100 million NTD) to shares (each share is 10 NTD par value)
        # Shares = capital_100m * 10^8 / 10 = capital_100m * 10,000,000
        shares_outstanding = float(latest_capital_100m) * 10_000_000.0
        return shares_outstanding

    def load_corporate_actions(self, stock_code: str) -> List[Dict]:
        """
        Loads ex-dividend and ex-rights events from the GoodInfo dividend schedule CSV.
        Returns a sorted list of dicts:
        [
           {"Date": Timestamp, "Cash_Dividend": float, "Stock_Dividend_Ratio": float},
           ...
        ]
        Note: Stock_Dividend_Ratio is expressed as a multiplier increase in shares.
              In Taiwan, a stock dividend of 2.0 (元) means 2 NTD face value per share,
              which distributes 2/10 = 0.2 shares per share. The share multiplier is 1.2x.
              So Stock_Dividend_Ratio here represents the share increase ratio (0.2 in this case).
        """
        csv_path = self.goodinfo_dir / "cleaned_dividend_schedule.csv"
        if not csv_path.exists():
            print(f"[Warning] Dividend schedule CSV not found at {csv_path}. Corporate actions will be disabled.")
            return []

        stock_code_str = str(stock_code).strip()
        df = pd.read_csv(csv_path, dtype={"stock_code": str}, encoding="utf-8-sig")
        df = df[df["stock_code"] == stock_code_str].copy()
        
        if df.empty:
            return []

        actions = []
        
        for _, row in df.iterrows():
            # Ex-dividend date: '除息_交易日'
            # Ex-rights date: '除權_交易日'
            # Cash dividend: '現金股利_合計'
            # Stock dividend: '股票股利_合計'
            
            ex_div_date_raw = row.get("除息_交易日")
            ex_right_date_raw = row.get("除權_交易日")
            
            cash_div = row.get("現金股利_合計")
            stock_div = row.get("股票股利_合計")
            
            # Parse cash dividend event
            if pd.notna(ex_div_date_raw) and ex_div_date_raw != "-" and ex_div_date_raw != "":
                try:
                    date = pd.to_datetime(ex_div_date_raw.strip())
                    val = float(cash_div) if pd.notna(cash_div) else 0.0
                    if val > 0:
                        actions.append({
                            "Date": date,
                            "Type": "Cash",
                            "Value": val
                        })
                except Exception:
                    pass

            # Parse stock dividend event
            if pd.notna(ex_right_date_raw) and ex_right_date_raw != "-" and ex_right_date_raw != "":
                try:
                    date = pd.to_datetime(ex_right_date_raw.strip())
                    val = float(stock_div) if pd.notna(stock_div) else 0.0
                    if val > 0:
                        # Stock dividend ratio = shares received per existing share
                        # In TW, 2.0 NTD dividend = 2.0 / 10.0 = 0.2 ratio
                        ratio = val / 10.0
                        actions.append({
                            "Date": date,
                            "Type": "Stock",
                            "Value": ratio
                        })
                except Exception:
                    pass
                    
        # Group by Date because sometimes Ex-dividend and Ex-rights occur on the same day!
        # Merge them into combined action dicts
        grouped_actions = {}
        for act in actions:
            date = act["Date"]
            if date not in grouped_actions:
                grouped_actions[date] = {"Date": date, "Cash_Dividend": 0.0, "Stock_Dividend_Ratio": 0.0}
            
            if act["Type"] == "Cash":
                grouped_actions[date]["Cash_Dividend"] += act["Value"]
            elif act["Type"] == "Stock":
                grouped_actions[date]["Stock_Dividend_Ratio"] += act["Value"]
                
        # Filter out actions that do nothing
        final_actions = []
        for act in grouped_actions.values():
            if act["Cash_Dividend"] > 0 or act["Stock_Dividend_Ratio"] > 0:
                final_actions.append(act)
                
        # Sort chronologically
        final_actions.sort(key=lambda x: x["Date"])
        return final_actions

    def load_weekly_shareholder_concentration(self, stock_code: str) -> pd.DataFrame:
        """
        Loads the weekly shareholder concentration history for a given stock.
        Returns a DataFrame containing:
        - Date: Timestamp (weekly date)
        - Core_Fraction: float (proportion of shares held by holders of > 1000 shares)
        - Active_Fraction: float (1.0 - Core_Fraction)
        """
        csv_path = self.goodinfo_dir / "raw_equity_class_his.csv"
        if not csv_path.exists():
            return pd.DataFrame(columns=["Date", "Core_Fraction", "Active_Fraction"])
            
        stock_code_str = str(stock_code).strip()
        df = pd.read_csv(csv_path, dtype={"stock_code": str}, encoding="utf-8-sig")
        df = df[df["stock_code"] == stock_code_str].copy()
        
        if df.empty:
            return pd.DataFrame(columns=["Date", "Core_Fraction", "Active_Fraction"])
            
        # Filter out rows where Date or weekly class is "-"
        df = df[(df["統計_日期"] != "-") & (df["統計_日期"].notna())].copy()
        df = df[df["週別"].str.len() >= 2].copy()
        
        if df.empty:
            return pd.DataFrame(columns=["Date", "Core_Fraction", "Active_Fraction"])
            
        # Reconstruct the full date: 20YY-MM-DD
        df["Year"] = "20" + df["週別"].str[:2]
        df["Full_Date"] = df["Year"] + "-" + df["統計_日期"].str.replace("/", "-")
        df["Date"] = pd.to_datetime(df["Full_Date"], errors="coerce")
        df = df.dropna(subset=["Date"])
        
        # Calculate Core_Fraction based on '持股_大於1千張_pct'
        large_holder_col = "持股_大於1千張_pct"
        if large_holder_col in df.columns:
            df["Core_Fraction"] = pd.to_numeric(df[large_holder_col], errors="coerce").fillna(60.0) / 100.0
        else:
            df["Core_Fraction"] = 0.60
            
        # Ensure it stays in a sane range [0.10, 0.90]
        df["Core_Fraction"] = df["Core_Fraction"].clip(0.10, 0.90)
        df["Active_Fraction"] = 1.0 - df["Core_Fraction"]
        
        # Keep only required columns and sort chronologically
        df = df[["Date", "Core_Fraction", "Active_Fraction"]].sort_values("Date").reset_index(drop=True)
        return df
