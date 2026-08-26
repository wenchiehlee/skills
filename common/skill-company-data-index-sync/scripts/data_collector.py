try:
    import self_update
except ImportError:
    pass

import os
import pandas as pd
from datetime import datetime


def find_repo_root():
    import os
    curr = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.exists(os.path.join(curr, ".git")) or os.path.exists(os.path.join(curr, "requirements.txt")) or os.path.exists(os.path.join(curr, "CLAUDE.md")):
            return curr
        parent = os.path.dirname(curr)
        if parent == curr:
            return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        curr = parent

# Paths
ROOT = find_repo_root()
DATA_DIR = os.path.join(ROOT, "data")

def refresh_local_metadata():
    """
    Refresh local metadata based on raw_*.csv files ALREADY present in the data folder.
    This repo does NOT access other repositories directly for data IO.
    Data ingestion is handled by upstream push or external sync tools.
    """
    if not os.path.exists(DATA_DIR):
        print(f"Data directory missing: {DATA_DIR}")
        return

    # 1. Update Synchronization Table based on EXISTING files
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sync_rows = []
    
    # Scan only raw_*.csv files in all subdirectories
    for root, dirs, files in os.walk(DATA_DIR):
        for f in files:
            if f.startswith("raw_") and f.endswith(".csv"):
                rel_path = os.path.relpath(os.path.join(root, f), DATA_DIR)
                # Map source based on subdirectory name for metadata purposes
                source = "Unknown"
                if "Python-Actions.GoodInfo.Analyzer" in rel_path: source = "Analyzer"
                elif "GoogleSearch.Factset" in rel_path: source = "Factset"
                elif "ConceptStocks" in rel_path: source = "ConceptStocks"
                elif "Yahoo.Finance" in rel_path: source = "YahooFinance"
                elif "biztrends_raw" in rel_path: source = "BizTrends"
                
                sync_rows.append({
                    "target_file": rel_path, 
                    "source_origin": source,
                    "last_sync_detected": now
                })
    
    pd.DataFrame(sync_rows).to_csv(os.path.join(DATA_DIR, "data_sync_table.csv"), index=False)
    print(f"Updated data_sync_table.csv with {len(sync_rows)} entries found in local data folder.")

    # 2. Refresh Investment Summary (for batch processing)
    generate_summary()

def generate_summary():
    # Use standard preserved names within subdirs
    path_perf = os.path.join(DATA_DIR, "Python-Actions.GoodInfo.Analyzer", "raw_performance1.csv")
    path_inc = os.path.join(DATA_DIR, "ConceptStocks", "raw_conceptstock_company_income.csv")
    
    df_perf = pd.read_csv(path_perf) if os.path.exists(path_perf) else pd.DataFrame()
    df_income = pd.read_csv(path_inc) if os.path.exists(path_inc) else pd.DataFrame()
    
    focus_ids = []
    if not df_perf.empty:
        for id in df_perf["stock_code"].unique():
            focus_ids.append({"id": str(id), "market": "TW"})
    if not df_income.empty:
        for id in df_income["symbol"].unique():
            focus_ids.append({"id": str(id), "market": "US"})
            
    summary_rows = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for item in focus_ids:
        sid = item["id"]
        if sid == "代號" or sid == "stock_code" or sid == "nan": continue
        
        row = {"stock_code": sid, "market": item["market"], "process_timestamp": now}
        
        # Quick metadata for summary purposes
        if item["market"] == "TW" and not df_perf.empty:
            match = df_perf[df_perf["stock_code"].astype(str) == sid].iloc[0:1]
            if not match.empty:
                row["company_name"] = match.iloc[0]["company_name"]
        elif item["market"] == "US" and not df_income.empty:
            match = df_income[df_income["symbol"] == sid].iloc[0:1]
            if not match.empty:
                row["company_name"] = match.iloc[0]["company_name"]

        summary_rows.append(row)
        
    pd.DataFrame(summary_rows).to_csv(os.path.join(DATA_DIR, "raw_investment_summary.csv"), index=False, encoding="utf-8-sig")
    print(f"Generated raw_investment_summary.csv with {len(summary_rows)} items")

if __name__ == "__main__":
    refresh_local_metadata()