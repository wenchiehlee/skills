import os
import re
import csv
import sys
import datetime
import numpy as np
import pandas as pd
import matplotlib
# If in CI environment, use Agg backend
if os.environ.get("CI"):
    matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from PIL import Image

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

# Setup Chinese font support for Windows and Linux
if os.name == "posix":
    for font_path in [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansTC-Regular.otf",
        "/usr/share/truetype/noto/NotoSansCJK-Regular.ttc",
    ]:
        if os.path.exists(font_path):
            fm.fontManager.addfont(font_path)

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = [
    "Microsoft JhengHei",
    "Noto Sans CJK JP",
    "Noto Sans CJK TC",
    "Noto Sans TC",
    "Heiti TC",
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False

# Paths
# Resolve the biztrends.TW repo root regardless of whether this script is run from
# biztrends.TW/scripts/ (2 levels up) or biztrends.TW/skills/*/scripts/ (4 levels up).
def _find_repo_root(start: str) -> str:
    """Walk upward until we find a directory that contains both 'data' and 'output'."""
    current = os.path.abspath(start)
    for _ in range(6):  # Search at most 6 levels up
        if os.path.isdir(os.path.join(current, "data")) and os.path.isdir(os.path.join(current, "output")):
            return current
        parent = os.path.dirname(current)
        if parent == current:  # Reached filesystem root
            break
        current = parent
    # Fallback: 2 levels up from script (original behaviour)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ROOT = _find_repo_root(os.path.dirname(os.path.abspath(__file__)))
RAW_PERFORMANCE_CSV = os.path.join(ROOT, "data", "Python-Actions.GoodInfo.Analyzer", "raw_performance1.csv")
CYCLE_WEIGHTS_CSV = os.path.join(ROOT, "data", "company_major_cycle_weights.csv")
CYCLE_MAPPING_CSV = os.path.join(ROOT, "data", "company_cycle_mapping.csv")
OUTPUT_DIR = os.path.join(ROOT, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ----------------------------------------------------
# 10 Models Implementation (Quarterly version, Period = 4)
# ----------------------------------------------------
PERIOD = 4

def model_seasonal_naive(train, steps, train_quarters=None):
    predictions = []
    for k in range(steps):
        predictions.append(train[-4 + (k % 4)])
    return predictions

def model_yoy_growth_adjusted(train, steps, train_quarters=None):
    yoy_list = []
    n = len(train)
    for i in range(max(4, n - 4), n):
        if i - 4 >= 0 and train[i-4] > 0:
            yoy = (train[i] - train[i-4]) / train[i-4]
            yoy_list.append(yoy)
    avg_yoy = np.mean(yoy_list) if yoy_list else 0.0
    
    predictions = []
    for k in range(steps):
        base_val = train[-4 + (k % 4)]
        predictions.append(base_val * (1.0 + avg_yoy))
    return predictions

def model_linear_trend(train, steps, train_quarters=None):
    n = len(train)
    x = np.arange(n)
    y = np.array(train)
    a, b = np.polyfit(x, y, 1)
    predictions = [a * (n + k) + b for k in range(steps)]
    return predictions

def model_ar1(train, steps, train_quarters=None):
    n = len(train)
    y = np.array(train)
    x = y[:-1]
    target = y[1:]
    a, b = np.polyfit(x, target, 1) # a is phi_1, b is c
    
    predictions = []
    last_val = train[-1]
    for k in range(steps):
        next_val = a * last_val + b
        predictions.append(next_val)
        last_val = next_val
    return predictions

def model_seasonal_decomposition(train, steps, train_quarters=None):
    n = len(train)
    if n < 4:
        return model_linear_trend(train, steps)
        
    quarterly_vals = {i: [] for i in range(1, 5)}
    for idx in range(n):
        q = (idx % 4) + 1
        quarterly_vals[q].append(train[idx])
        
    quarterly_avgs = {q: np.mean(vals) for q, vals in quarterly_vals.items()}
    overall_mean = np.mean(train)
    
    S = {q: (quarterly_avgs[q] / overall_mean if overall_mean > 0 else 1.0) for q in range(1, 5)}
    train_adj = [train[idx] / S[(idx % 4) + 1] for idx in range(n)]
    
    a, b = np.polyfit(np.arange(n), np.array(train_adj), 1)
    
    predictions = []
    for k in range(steps):
        t_val = n + k
        s_val = S[(t_val % 4) + 1]
        predictions.append((a * t_val + b) * s_val)
    return predictions

def model_holt_linear(train, steps, train_quarters=None, alpha=0.2, beta=0.2):
    n = len(train)
    if n < 2:
        return [train[-1]] * steps
    L = [0.0] * n
    T = [0.0] * n
    
    L[0] = train[0]
    T[0] = train[1] - train[0]
    
    for t in range(1, n):
        L[t] = alpha * train[t] + (1 - alpha) * (L[t-1] + T[t-1])
        T[t] = beta * (L[t] - L[t-1]) + (1 - beta) * T[t-1]
        
    predictions = [L[-1] + (k + 1) * T[-1] for k in range(steps)]
    return predictions

def model_holt_winters_multiplicative(train, steps, train_quarters=None, alpha=0.2, beta=0.2, gamma=0.2):
    n = len(train)
    if n < 12:
        return model_seasonal_decomposition(train, steps)
        
    L_init = np.mean(train[:4])
    S = list(np.array(train[:4]) / L_init if L_init > 0 else [1.0]*4)
    
    L = [0.0] * n
    T = [0.0] * n
    
    L[3] = L_init
    T[3] = (np.mean(train[4:8]) - np.mean(train[:4])) / 4.0
    
    S_full = S + [1.0] * (n - 4)
    
    for t in range(4, n):
        S_prev_seasonal = S_full[t-4]
        L[t] = alpha * (train[t] / S_prev_seasonal if S_prev_seasonal > 0 else train[t]) + (1 - alpha) * (L[t-1] + T[t-1])
        T[t] = beta * (L[t] - L[t-1]) + (1 - beta) * T[t-1]
        S_full[t] = gamma * (train[t] / L[t] if L[t] > 0 else 1.0) + (1 - gamma) * S_prev_seasonal
        
    predictions = []
    for k in range(steps):
        s_factor = S_full[-4 + (k % 4)]
        predictions.append((L[-1] + (k + 1) * T[-1]) * s_factor)
    return predictions

def model_wma_3(train, steps, train_quarters=None):
    n = len(train)
    if n < 3:
        return [train[-1]] * steps
    predictions = []
    history = list(train)
    for k in range(steps):
        next_val = (3 * history[-1] + 2 * history[-2] + 1 * history[-3]) / 6.0
        predictions.append(next_val)
        history.append(next_val)
    return predictions

def model_fourier_seasonal(train, steps, train_quarters=None):
    n = len(train)
    if n < 4:
        return model_linear_trend(train, steps)
    t = np.arange(n)
    X = np.column_stack([
        np.ones(n),
        t,
        np.cos(2 * np.pi * t / 4),
        np.sin(2 * np.pi * t / 4)
    ])
    y = np.array(train)
    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    
    predictions = []
    for k in range(steps):
        t_fut = n + k
        x_fut = np.array([
            1.0,
            t_fut,
            np.cos(2 * np.pi * t_fut / 4),
            np.sin(2 * np.pi * t_fut / 4)
        ])
        predictions.append(np.dot(x_fut, beta))
    return predictions

def model_ar2(train, steps, train_quarters=None):
    n = len(train)
    if n < 4:
        return model_ar1(train, steps)
    y = np.array(train)
    x1 = y[1:-1]
    x2 = y[:-2]
    X = np.column_stack([x1, x2, np.ones(n - 2)])
    target = y[2:]
    beta, _, _, _ = np.linalg.lstsq(X, target, rcond=None)
    
    predictions = []
    history = list(train)
    for k in range(steps):
        next_val = beta[0] * history[-1] + beta[1] * history[-2] + beta[2]
        predictions.append(next_val)
        history.append(next_val)
    return predictions

# ----------------------------------------------------
# Analyst Consensus Integration Helpers
# ----------------------------------------------------
YAHOO_HISTORY_CSV = os.path.join(ROOT, "data", "Yahoo.Finance", "raw_yahoo_finance_consensus_history.csv")
FACTSET_DETAILED_CSV = os.path.join(ROOT, "data", "GoogleSearch.Factset", "raw_factset_detailed_report.csv")

def get_approx_announcement_date(q_str):
    m = re.match(r"(\d{4})/Q(\d)", q_str)
    if not m:
        return None
    year = int(m.group(1))
    q = int(m.group(2))
    if q == 1:
        return f"{year}-05-15"
    elif q == 2:
        return f"{year}-08-15"
    elif q == 3:
        return f"{year}-11-15"
    elif q == 4:
        return f"{year+1}-03-31"
    return None

def load_all_consensus_data(stock_code, latest_capital_billion, oprofit_to_netincome_ratio, quarters_list, future_quarters):
    yahoo_map = {}
    factset_map = {}
    
    shares_billion = float(latest_capital_billion) / 10.0 if latest_capital_billion else 0.0
    
    import datetime
    def get_q0_q1_from_date(d):
        y = d.year
        if datetime.date(y, 3, 31) <= d <= datetime.date(y, 5, 15):
            return f"{y}/Q1", f"{y}/Q2"
        elif datetime.date(y, 5, 16) <= d <= datetime.date(y, 8, 15):
            return f"{y}/Q2", f"{y}/Q3"
        elif datetime.date(y, 8, 16) <= d <= datetime.date(y, 11, 15):
            return f"{y}/Q3", f"{y}/Q4"
        else:
            if d < datetime.date(y, 3, 31):
                return f"{y-1}/Q4", f"{y}/Q1"
            else:
                return f"{y}/Q4", f"{y+1}/Q1"

    # 1. Load Yahoo Finance consensus history
    if os.path.exists(YAHOO_HISTORY_CSV):
        try:
            df = pd.read_csv(YAHOO_HISTORY_CSV, encoding="utf-8")
            df.columns = df.columns.str.strip()
            df_stock = df[df["stock_code"].astype(str).str.strip() == str(stock_code)].copy()
            
            for _, row in df_stock.iterrows():
                dt_str = str(row["forecast_asof_date"]).split(" ")[0]
                dt = pd.to_datetime(dt_str).date()
                q0, q1 = get_q0_q1_from_date(dt)
                
                # Q0 mapping
                if "revenue_0q_avg" in row and not pd.isna(row["revenue_0q_avg"]):
                    rev_val = float(row["revenue_0q_avg"]) / 1e8
                    eps_val = float(row["earnings_0q_avg"]) if ("earnings_0q_avg" in row and not pd.isna(row["earnings_0q_avg"])) else None
                    prof_val = eps_val * shares_billion * oprofit_to_netincome_ratio if (eps_val is not None and shares_billion > 0) else None
                    yahoo_map.setdefault(q0, []).append((dt, rev_val, prof_val))
                    
                # Q1 mapping
                if "revenue_1q_avg" in row and not pd.isna(row["revenue_1q_avg"]):
                    rev_val = float(row["revenue_1q_avg"]) / 1e8
                    eps_val = float(row["earnings_1q_avg"]) if ("earnings_1q_avg" in row and not pd.isna(row["earnings_1q_avg"])) else None
                    prof_val = eps_val * shares_billion * oprofit_to_netincome_ratio if (eps_val is not None and shares_billion > 0) else None
                    yahoo_map.setdefault(q1, []).append((dt, rev_val, prof_val))
        except Exception as e:
            print(f"Error loading Yahoo consensus map: {e}")
            
    # 2. Load FactSet consensus detailed report
    if os.path.exists(FACTSET_DETAILED_CSV):
        try:
            df = pd.read_csv(FACTSET_DETAILED_CSV, encoding="utf-8")
            df.columns = df.columns.str.strip()
            code_col = "代號" if "代號" in df.columns else "股票代號"
            df_stock = df[df[code_col].astype(str).str.strip().str.replace("-TW", "").str.replace(".TW", "") == str(stock_code)].copy()
            
            for _, row in df_stock.iterrows():
                dt_str = str(row["MD日期"]).split(" ")[0]
                dt = pd.to_datetime(dt_str).date()
                q0, q1 = get_q0_q1_from_date(dt)
                
                for q_key in [q0, q1]:
                    q_year = q_key.split("/")[0]
                    rev_col = f"{q_year}營收平均值"
                    eps_col = f"{q_year}EPS平均值"
                    
                    if rev_col in row and not pd.isna(row[rev_col]) and eps_col in row and not pd.isna(row[eps_col]):
                        annual_rev = float(row[rev_col])
                        scale = 1.0
                        if annual_rev > 1e11:
                            scale = 1e-8
                        elif annual_rev > 1e8:
                            scale = 1e-5
                        else:
                            scale = 1.0
                            
                        rev_val_annual = annual_rev * scale
                        eps_val_annual = float(row[eps_col])
                        
                        rev_val = rev_val_annual * 0.25
                        prof_val = eps_val_annual * shares_billion * oprofit_to_netincome_ratio * 0.25 if (shares_billion > 0) else None
                        
                        if q_key == q0:
                            factset_map.setdefault(q0, []).append((dt, rev_val, prof_val))
                        else:
                            factset_map.setdefault(q1, []).append((dt, rev_val, prof_val))
        except Exception as e:
            print(f"Error loading FactSet consensus map: {e}")
            
    for q in yahoo_map:
        yahoo_map[q] = sorted(yahoo_map[q], key=lambda x: x[0])
    for q in factset_map:
        factset_map[q] = sorted(factset_map[q], key=lambda x: x[0])
        
    return yahoo_map, factset_map

def query_consensus_for_quarter(q, consensus_map, target_date_str=None):
    if q not in consensus_map or not consensus_map[q]:
        return None, None
    records = consensus_map[q]
    if not target_date_str:
        return records[-1][1], records[-1][2]
        
    import datetime
    t_date = pd.to_datetime(target_date_str).date()
    matched = [r for r in records if r[0] <= t_date]
    if not matched:
        return None, None
    return matched[-1][1], matched[-1][2]

# ----------------------------------------------------
# Helper Functions
# ----------------------------------------------------
def parse_quarter(q_str):
    m = re.match(r"(\d{4})Q(\d)", str(q_str))
    if m:
        return int(m.group(1)), int(m.group(2))
    return None

def get_next_quarters(q_str, steps=4):
    m = re.match(r"(\d{4})/Q(\d)", q_str)
    if not m:
        return []
    year = int(m.group(1))
    q = int(m.group(2))
    
    next_qs = []
    for _ in range(steps):
        q += 1
        if q > 4:
            q = 1
            year += 1
        next_qs.append(f"{year}/Q{q}")
    return next_qs

def load_company_cycle_weights(stock_code):
    # 1. Try company_major_cycle_weights.csv
    if os.path.exists(CYCLE_WEIGHTS_CSV):
        try:
            df = pd.read_csv(CYCLE_WEIGHTS_CSV, encoding="utf-8")
            df.columns = df.columns.str.strip()
            df_row = df[df["代號"].astype(str).str.strip() == str(stock_code)]
            if not df_row.empty:
                cycles = ["AI_Compute_Infra", "AI_Compute", "Memory", "Smartphone", "PC_Consumer", 
                          "EV_Automotive", "Network_Infra", "Software_SaaS", "Consumer_IoT", "Other"]
                weights = {}
                for c in cycles:
                    if c in df_row.columns:
                        weights[c] = float(df_row[c].iloc[0]) / 100.0
                    else:
                        weights[c] = 0.0
                return weights
        except Exception as e:
            print(f"Error reading major company cycle weights: {e}")

    # 2. Try company_cycle_mapping.csv
    if os.path.exists(CYCLE_MAPPING_CSV):
        try:
            df = pd.read_csv(CYCLE_MAPPING_CSV, encoding="utf-8")
            df.columns = df.columns.str.strip()
            df_row = df[df["stock_code"].astype(str).str.strip() == str(stock_code)]
            if not df_row.empty and "canonical_cycle" in df_row.columns:
                cycle_name = str(df_row["canonical_cycle"].iloc[0]).strip()
                weights = {c: 0.0 for c in ["AI_Compute_Infra", "AI_Compute", "Memory", "Smartphone", "PC_Consumer", 
                                           "EV_Automotive", "Network_Infra", "Software_SaaS", "Consumer_IoT", "Other"]}
                if cycle_name in weights:
                    weights[cycle_name] = 1.0
                else:
                    weights["Other"] = 1.0
                return weights
        except Exception as e:
            print(f"Error reading company cycle mapping: {e}")

    # 3. Default fallback
    print(f"No weights or mapping found for {stock_code}. Fallback to Other: 100%")
    return {"Other": 1.0}

def get_historical_and_future_weights(stock_code, quarters_list, future_quarters, latest_weights):
    all_qs = list(quarters_list) + list(future_quarters)
    weights_timeline = {q: {} for q in all_qs}
    true_source_flags = {q: False for q in all_qs}
    known_points = {}
    
    if os.path.exists(CYCLE_WEIGHTS_CSV):
        try:
            df = pd.read_csv(CYCLE_WEIGHTS_CSV, encoding="utf-8")
            df.columns = df.columns.str.strip()
            df_row = df[df["代號"].astype(str).str.strip() == str(stock_code)]
            if not df_row.empty:
                period_str = str(df_row["期間"].iloc[0]).strip()
                m = re.match(r"(\d{4})-Q(\d)", period_str)
                if m:
                    q_key = f"{m.group(1)}/Q{m.group(2)}"
                    known_points[q_key] = latest_weights.copy()
                m_fy = re.match(r"(\d{4})-FY", period_str)
                if m_fy:
                    year = m_fy.group(1)
                    for q in ["Q1", "Q2", "Q3", "Q4"]:
                        known_points[f"{year}/{q}"] = latest_weights.copy()
        except Exception as e:
            print(f"Error loading major weights period: {e}")
            
    if str(stock_code) == "2330" and os.path.exists(os.path.join(ROOT, "data", "tsm_platform_revenue.csv")):
        try:
            df_tsm = pd.read_csv(os.path.join(ROOT, "data", "tsm_platform_revenue.csv"), encoding="utf-8")
            for _, row in df_tsm.iterrows():
                p = str(row["period"]).strip()
                m = re.match(r"(\d{4})-Q(\d)", p)
                if m:
                    q_key = f"{m.group(1)}/Q{m.group(2)}"
                    col_map = {
                        "HPC": "AI_Compute_Infra",
                        "Smartphone": "Smartphone",
                        "IoT": "Consumer_IoT",
                        "Automotive": "EV_Automotive",
                        "DCE": "PC_Consumer",
                        "Others": "Other"
                    }
                    w_dict = {c: 0.0 for c in latest_weights}
                    valid = True
                    for csv_col, cycle_col in col_map.items():
                        if csv_col in row and not pd.isna(row[csv_col]):
                            try:
                                w_dict[cycle_col] = float(row[csv_col]) / 100.0
                            except:
                                valid = False
                        else:
                            valid = False
                    if valid:
                        known_points[q_key] = w_dict
        except Exception as e:
            print(f"Error loading TSMC platform weights: {e}")
            
    if not known_points:
        for q in all_qs:
            weights_timeline[q] = latest_weights.copy()
        return weights_timeline, true_source_flags
        
    for q in all_qs:
        if q in known_points:
            true_source_flags[q] = True
            
    sorted_all_qs = sorted(all_qs, key=lambda x: (int(x.split("/")[0]), int(x.split("/")[1][1])))
    known_indices = []
    known_weights_list = []
    for q in sorted_all_qs:
        if q in known_points:
            known_indices.append(sorted_all_qs.index(q))
            known_weights_list.append(known_points[q])
            
    for idx, q in enumerate(sorted_all_qs):
        if q in known_points:
            weights_timeline[q] = known_points[q].copy()
        else:
            before_idx = [i for i in known_indices if i < idx]
            after_idx = [i for i in known_indices if i > idx]
            
            if not before_idx:
                weights_timeline[q] = known_weights_list[0].copy()
            elif not after_idx:
                weights_timeline[q] = known_weights_list[-1].copy()
            else:
                b_i = before_idx[-1]
                a_i = after_idx[0]
                b_w = known_points[sorted_all_qs[b_i]]
                a_w = known_points[sorted_all_qs[a_i]]
                factor = (idx - b_i) / (a_i - b_i)
                interpolated_w = {}
                for c in latest_weights:
                    interpolated_w[c] = b_w[c] + factor * (a_w[c] - b_w[c])
                weights_timeline[q] = interpolated_w
                
    return weights_timeline, true_source_flags

# Industry Multipliers (Solution C)
CYCLE_MULTIPLIERS = {
    "AI_Compute_Infra": 1.25, # High growth AI server infrastructure
    "AI_Compute": 1.25,
    "PC_Consumer": 0.98,      # Mature consumer PC market
    "Smartphone": 1.01,
    "EV_Automotive": 1.05,
    "Consumer_IoT": 1.02,
    "Software_SaaS": 1.10,
    "Memory": 1.08,
    "Network_Infra": 1.03,
    "Other": 1.00
}

# Segment Model Overrides for specific stocks/segments to resolve:
# 1. 2382 flattening (WMA-3)
# 2. 2357 growth rates synchronized (identical YoY growth)
SEGMENT_MODEL_OVERRIDES = {
    "2382": {
        "revenue": {
            "AI_Compute_Infra": "YoY Growth Adjusted",
            "PC_Consumer": "WMA-3",
            "Network_Infra": "WMA-3",
            "Other": "WMA-3"
        },
        "expense": {
            "AI_Compute_Infra": "YoY Growth Adjusted",
            "PC_Consumer": "WMA-3",
            "Network_Infra": "WMA-3",
            "Other": "WMA-3"
        }
    },
    "2357": {
        "revenue": {
            "AI_Compute_Infra": "YoY Growth Adjusted",
            "PC_Consumer": "WMA-3",
            "Consumer_IoT": "WMA-3"
        },
        "expense": {
            "AI_Compute_Infra": "YoY Growth Adjusted",
            "PC_Consumer": "WMA-3",
            "Consumer_IoT": "WMA-3"
        }
    }
}

# ----------------------------------------------------
# Main Forecasting Pipeline (Bottom-Up Segment-wise)
# ----------------------------------------------------
def forecast_quarterly(stock_code):
    # Load raw data
    if not os.path.exists(RAW_PERFORMANCE_CSV):
        print(f"Error: Data file {RAW_PERFORMANCE_CSV} not found!")
        return None
        
    df = pd.read_csv(RAW_PERFORMANCE_CSV)
    df_stock = df[df["stock_code"].astype(str) == str(stock_code)]
    if df_stock.empty:
        print(f"Error: No data found for stock {stock_code}")
        return None
        
    # Data Cleaning
    df_stock = df_stock.copy()
    df_stock["revenue_raw"] = df_stock["獲利金額_億_營業_收入"].astype(str).str.replace(",", "").str.strip()
    df_stock["profit_raw"] = df_stock["獲利金額_億_營業_利益"].astype(str).str.replace(",", "").str.strip()
    
    df_stock["revenue"] = pd.to_numeric(df_stock["revenue_raw"], errors="coerce")
    df_stock["profit"] = pd.to_numeric(df_stock["profit_raw"], errors="coerce")
    
    # Filter rows
    df_stock = df_stock.dropna(subset=["revenue", "profit"])
    df_stock = df_stock[df_stock["revenue"] > 0]
    
    # Parse and sort by quarter
    df_stock["parsed_q"] = df_stock["季度"].apply(parse_quarter)
    df_stock = df_stock.dropna(subset=["parsed_q"])
    df_stock = df_stock.sort_values("parsed_q")
    df_stock["display_q"] = df_stock["parsed_q"].apply(lambda x: f"{x[0]}/Q{x[1]}")
    df_stock["expense"] = df_stock["revenue"] - df_stock["profit"]
    
    quarters = df_stock["display_q"].tolist()
    total_revenue_vals = df_stock["revenue"].tolist()
    total_expense_vals = df_stock["expense"].tolist()
    total_profit_vals = df_stock["profit"].tolist()
    
    N = len(quarters)
    print(f"Loaded {N} valid quarters of data for {stock_code}.")
    if N < 16:
        print(f"Error: Insufficient data (at least 16 quarters required, got {N}).")
        return None
        
    # Load Cycle weights
    latest_weights = load_company_cycle_weights(stock_code)
    active_cycles = {c: w for c, w in latest_weights.items() if w > 0}
    print(f"Active Cycles for {stock_code}: {active_cycles}")
    
    # 1. Historical & Future Weight Reconstruction (Solution A: Dynamic Weights & True of Source)
    future_quarters = get_next_quarters(quarters[-1], 4)
    weights_timeline, true_source_flags = get_historical_and_future_weights(
        stock_code, quarters, future_quarters, latest_weights
    )
    weights_over_time = [weights_timeline[q] for q in quarters]
        
    # 2. Deconstruct historical total revenue & expense into segments (Solution B: Bottom-Up Segment-wise)
    segment_revenues = {c: [] for c in active_cycles}
    segment_expenses = {c: [] for c in active_cycles}
    segment_profits = {c: [] for c in active_cycles}
    
    for t in range(N):
        w_t = weights_over_time[t]
        for c in active_cycles:
            w = w_t.get(c, 0.0)
            rev_c = total_revenue_vals[t] * w
            prof_c = total_profit_vals[t] * w
            exp_c = rev_c - prof_c
            
            segment_revenues[c].append(rev_c)
            segment_expenses[c].append(exp_c)
            segment_profits[c].append(prof_c)
            
    # 3. Forecast each segment separately using 10-Model Pipeline (Solution B)
    backtest_start_idx = N - 12
    models = {
        "Seasonal Naive": model_seasonal_naive,
        "YoY Growth Adjusted": model_yoy_growth_adjusted,
        "Linear Trend": model_linear_trend,
        "AR-1 Rolling": model_ar1,
        "Seasonal Decomposition": model_seasonal_decomposition,
        "Holt Linear Double": model_holt_linear,
        "Holt-Winters Triple": model_holt_winters_multiplicative,
        "WMA-3": model_wma_3,
        "Fourier Seasonal": model_fourier_seasonal,
        "AR-2 Rolling": model_ar2
    }
    
    segment_results = {}
    
    for c in active_cycles:
        # We run walk-forward validation and final forecast for Revenue and Expense of this segment
        c_rev_history = segment_revenues[c]
        c_exp_history = segment_expenses[c]
        
        # Evaluate Revenue Models for Segment c
        c_models_rev = {}
        for name, func in models.items():
            val_preds = []
            for t in range(backtest_start_idx, N):
                train_data = c_rev_history[:t]
                val_preds.append(func(train_data, 1, quarters[:t])[0])
            # Metrics
            actuals = c_rev_history[backtest_start_idx:N]
            mape = np.mean(np.abs((np.array(actuals) - np.array(val_preds)) / np.array(actuals))) * 100.0
            mpe = np.mean((np.array(actuals) - np.array(val_preds)) / np.array(actuals)) * 100.0
            
            # Future 4 steps
            fut_raw = func(c_rev_history, 4, quarters)
            c_models_rev[name] = {
                "mape": mape, "mpe": mpe, "val_preds": val_preds, "future_raw": fut_raw
            }
            
        # Find Best Revenue Model for segment c
        stock_overrides = SEGMENT_MODEL_OVERRIDES.get(str(stock_code), {})
        rev_override = stock_overrides.get("revenue", {}).get(c)
        if rev_override and rev_override in c_models_rev:
            best_rev_name = rev_override
            print(f"[{stock_code}] Revenue Model Override for segment {c}: {best_rev_name}")
        else:
            best_rev_name = min(c_models_rev.keys(), key=lambda k: c_models_rev[k]["mape"])
        best_rev_data = c_models_rev[best_rev_name]
        
        # Apply MPE Correction & Industry Cycle Multipliers (Solution C)
        mult = CYCLE_MULTIPLIERS.get(c, 1.0)
        future_corr_rev = [v * (1.0 + best_rev_data["mpe"] / 100.0) * mult for v in best_rev_data["future_raw"]]
        
        # Evaluate Expense Models for Segment c
        c_models_exp = {}
        for name, func in models.items():
            val_preds = []
            for t in range(backtest_start_idx, N):
                train_data = c_exp_history[:t]
                val_preds.append(func(train_data, 1, quarters[:t])[0])
            # Metrics
            actuals = c_exp_history[backtest_start_idx:N]
            mape = np.mean(np.abs((np.array(actuals) - np.array(val_preds)) / np.array(actuals))) * 100.0
            mpe = np.mean((np.array(actuals) - np.array(val_preds)) / np.array(actuals)) * 100.0
            
            # Future 4 steps
            fut_raw = func(c_exp_history, 4, quarters)
            c_models_exp[name] = {
                "mape": mape, "mpe": mpe, "val_preds": val_preds, "future_raw": fut_raw
            }
            
        # Find Best Expense Model for segment c
        exp_override = stock_overrides.get("expense", {}).get(c)
        if exp_override and exp_override in c_models_exp:
            best_exp_name = exp_override
            print(f"[{stock_code}] Expense Model Override for segment {c}: {best_exp_name}")
        else:
            best_exp_name = min(c_models_exp.keys(), key=lambda k: c_models_exp[k]["mape"])
        best_exp_data = c_models_exp[best_exp_name]
        
        # Apply MPE Correction & Industry Cycle Multipliers (Solution C)
        future_corr_exp = [v * (1.0 + best_exp_data["mpe"] / 100.0) * mult for v in best_exp_data["future_raw"]]
        
        segment_results[c] = {
            "best_rev_model": best_rev_name,
            "best_rev_mape": best_rev_data["mape"],
            "best_rev_mpe": best_rev_data["mpe"],
            "val_preds_rev": best_rev_data["val_preds"],
            "future_corr_rev": future_corr_rev,
            
            "best_exp_model": best_exp_name,
            "best_exp_mape": best_exp_data["mape"],
            "best_exp_mpe": best_exp_data["mpe"],
            "val_preds_exp": best_exp_data["val_preds"],
            "future_corr_exp": future_corr_exp
        }
        
    # 4. Re-aggregate segment predictions to get total predictions (Bottom-Up Summation)
    total_val_preds_rev = [0.0] * 12
    total_val_preds_exp = [0.0] * 12
    
    total_future_rev = [0.0] * 4
    total_future_exp = [0.0] * 4
    
    for c in active_cycles:
        res_c = segment_results[c]
        for i in range(12):
            total_val_preds_rev[i] += res_c["val_preds_rev"][i]
            total_val_preds_exp[i] += res_c["val_preds_exp"][i]
        for i in range(4):
            total_future_rev[i] += res_c["future_corr_rev"][i]
            total_future_exp[i] += res_c["future_corr_exp"][i]
            
    total_val_preds_prof = [r - e for r, e in zip(total_val_preds_rev, total_val_preds_exp)]
    total_future_prof = [r - e for r, e in zip(total_future_rev, total_future_exp)]
    
    # Calculate Overall aggregated metrics
    actuals_rev = total_revenue_vals[backtest_start_idx:N]
    actuals_exp = total_expense_vals[backtest_start_idx:N]
    actuals_prof = total_profit_vals[backtest_start_idx:N]
    
    mape_rev = np.mean(np.abs((np.array(actuals_rev) - np.array(total_val_preds_rev)) / np.array(actuals_rev))) * 100.0
    mpe_rev = np.mean((np.array(actuals_rev) - np.array(total_val_preds_rev)) / np.array(actuals_rev)) * 100.0
    
    mape_exp = np.mean(np.abs((np.array(actuals_exp) - np.array(total_val_preds_exp)) / np.array(actuals_exp))) * 100.0
    mpe_exp = np.mean((np.array(actuals_exp) - np.array(total_val_preds_exp)) / np.array(actuals_exp)) * 100.0
    
    denom_prof = np.where(np.array(actuals_prof) == 0, 1e-9, np.array(actuals_prof))
    mape_prof = np.mean(np.abs((np.array(actuals_prof) - np.array(total_val_preds_prof)) / denom_prof)) * 100.0
    mpe_prof = np.mean((np.array(actuals_prof) - np.array(total_val_preds_prof)) / denom_prof) * 100.0
    
    future_quarters = get_next_quarters(quarters[-1], 4)
    
    # --- Consensus Benchmark Model Logic ---
    latest_capital = df_stock["股本_億"].iloc[-1] if "股本_億" in df_stock.columns else 20.0
    oprofit_ratio = 1.0
    if "獲利金額_億_稅後_淨利" in df_stock.columns:
        df_stock["net_income"] = pd.to_numeric(df_stock["獲利金額_億_稅後_淨利"].astype(str).str.replace(",", ""), errors="coerce")
        recent_profits = total_profit_vals[-4:]
        recent_net_incomes = df_stock["net_income"].dropna().tolist()[-4:]
        if recent_net_incomes and sum(recent_net_incomes) != 0:
            oprofit_ratio = sum(recent_profits) / sum(recent_net_incomes)
            
    yahoo_map, factset_map = load_all_consensus_data(
        stock_code, latest_capital, oprofit_ratio, quarters, future_quarters
    )
    
    yahoo_backtest_rev = [np.nan] * 12
    yahoo_backtest_prof = [np.nan] * 12
    factset_backtest_rev = [np.nan] * 12
    factset_backtest_prof = [np.nan] * 12
    
    for i in range(12):
        t = backtest_start_idx + i
        ann_date = get_approx_announcement_date(quarters[t])
        
        # Yahoo
        rev_y, prof_y = query_consensus_for_quarter(quarters[t], yahoo_map, ann_date)
        if rev_y is not None:
            yahoo_backtest_rev[i] = rev_y
        if prof_y is not None:
            yahoo_backtest_prof[i] = prof_y
            
        # FactSet
        rev_f, prof_f = query_consensus_for_quarter(quarters[t], factset_map, ann_date)
        if rev_f is not None:
            factset_backtest_rev[i] = rev_f
        if prof_f is not None:
            factset_backtest_prof[i] = prof_f
            
    yahoo_future_rev = [np.nan] * 4
    yahoo_future_prof = [np.nan] * 4
    factset_future_rev = [np.nan] * 4
    factset_future_prof = [np.nan] * 4
    
    for i, q_fut in enumerate(future_quarters):
        # Yahoo
        rev_y, prof_y = query_consensus_for_quarter(q_fut, yahoo_map, None)
        if rev_y is not None:
            yahoo_future_rev[i] = rev_y
        if prof_y is not None:
            yahoo_future_prof[i] = prof_y
            
        # FactSet
        rev_f, prof_f = query_consensus_for_quarter(q_fut, factset_map, None)
        if rev_f is not None:
            factset_future_rev[i] = rev_f
        if prof_f is not None:
            factset_future_prof[i] = prof_f
            
    # Calculate MAPEs for consensus models (nan-safe)
    def calc_nan_mape(actuals, preds):
        acts = np.array(actuals)
        prds = np.array(preds)
        mask = ~np.isnan(prds)
        if not np.any(mask):
            return np.nan
        denom = np.where(acts[mask] == 0, 1e-9, acts[mask])
        return np.mean(np.abs((acts[mask] - prds[mask]) / denom)) * 100.0
        
    mape_yahoo_rev = calc_nan_mape(actuals_rev, yahoo_backtest_rev)
    mape_yahoo_prof = calc_nan_mape(actuals_prof, yahoo_backtest_prof)
    mape_factset_rev = calc_nan_mape(actuals_rev, factset_backtest_rev)
    mape_factset_prof = calc_nan_mape(actuals_prof, factset_backtest_prof)
    
    return {
        "stock_code": stock_code,
        "company_name": df_stock["company_name"].iloc[0] if "company_name" in df_stock.columns else "台積電",
        "quarters": quarters,
        "revenue": total_revenue_vals,
        "expense": total_expense_vals,
        "profit": total_profit_vals,
        "backtest_start_idx": backtest_start_idx,
        "future_quarters": future_quarters,
        # Segment and Dynamic Weight details
        "active_cycles": active_cycles,
        "weights_over_time": weights_over_time,
        "weights_timeline": weights_timeline,
        "true_source_flags": true_source_flags,
        "segment_revenues": segment_revenues,
        "segment_results": segment_results,
        # Aggregated Best predictions
        "val_preds_rev": total_val_preds_rev,
        "future_corr_rev": total_future_rev,
        "val_preds_exp": total_val_preds_exp,
        "future_corr_exp": total_future_exp,
        "val_preds_prof": total_val_preds_prof,
        "future_corr_prof": total_future_prof,
        # Total metrics
        "mape_rev": mape_rev, "mpe_rev": mpe_rev,
        "mape_exp": mape_exp, "mpe_exp": mpe_exp,
        "mape_prof": mape_prof, "mpe_prof": mpe_prof,
        # Consensus forecasts and metrics
        "yahoo_backtest_rev": yahoo_backtest_rev,
        "yahoo_backtest_prof": yahoo_backtest_prof,
        "yahoo_future_rev": yahoo_future_rev,
        "yahoo_future_prof": yahoo_future_prof,
        "mape_yahoo_rev": mape_yahoo_rev,
        "mape_yahoo_prof": mape_yahoo_prof,
        
        "factset_backtest_rev": factset_backtest_rev,
        "factset_backtest_prof": factset_backtest_prof,
        "factset_future_rev": factset_future_rev,
        "factset_future_prof": factset_future_prof,
        "mape_factset_rev": mape_factset_rev,
        "mape_factset_prof": mape_factset_prof
    }

def generate_plots_and_report(res):
    if not res:
        print("Error: No prediction results available to generate report.")
        return
        
    stock_code = res["stock_code"]
    company_name = res["company_name"]
    
    quarters = res["quarters"]
    revenue = res["revenue"]
    expense = res["expense"]
    profit = res["profit"]
    
    future_quarters = res["future_quarters"]
    
    # 1. Prepare data for display (last 24 quarters of history + 4 quarters of future)
    N = len(quarters)
    display_start_idx = N - 24
    
    display_quarters = quarters[display_start_idx:]
    display_actual_rev = revenue[display_start_idx:]
    display_actual_exp = expense[display_start_idx:]
    display_actual_prof = profit[display_start_idx:]
    
    all_x_quarters = display_quarters + future_quarters
    pred_quarters = display_quarters[12:] + future_quarters
    
    pred_rev_line = res["val_preds_rev"] + res["future_corr_rev"]
    pred_exp_line = res["val_preds_exp"] + res["future_corr_exp"]
    pred_prof_line = res["val_preds_prof"] + res["future_corr_prof"]
    
    # ----------------------------------------------------
    # Chart 1: Revenue, Expense, Profit Forecast and Backtest
    # ----------------------------------------------------
    fig, ax = plt.subplots(figsize=(12, 6.5), dpi=300)
    
    # Plot Actual Data (solid lines)
    ax.plot(display_quarters, display_actual_rev, color="black", label="真實營業收入", linewidth=2.2, marker="o", markersize=5)
    ax.plot(display_quarters, display_actual_exp, color="#e53935", label="真實總支出 (成本+費用)", linewidth=2.0, marker="s", markersize=5)
    ax.plot(display_quarters, display_actual_prof, color="#2e7d32", label="真實營業利益", linewidth=2.5, marker="D", markersize=5)
    
    # Plot Predictions (dashed lines)
    ax.plot(pred_quarters, pred_rev_line, color="#1f77b4", linestyle="--", label="營收預測 (自下而上合力)", linewidth=1.8)
    ax.plot(pred_quarters, pred_exp_line, color="#ff7f0e", linestyle="--", label="支出預測 (自下而上合力)", linewidth=1.8)
    ax.plot(pred_quarters, pred_prof_line, color="#4caf50", linestyle="--", label="利益預測 (會計恆等)", linewidth=2.0)
    
    # Plot Consensus Benchmarks (Yahoo: dotted, FactSet: dash-dot)
    yahoo_rev_line = res["yahoo_backtest_rev"] + res["yahoo_future_rev"]
    yahoo_prof_line = res["yahoo_backtest_prof"] + res["yahoo_future_prof"]
    factset_rev_line = res["factset_backtest_rev"] + res["factset_future_rev"]
    factset_prof_line = res["factset_backtest_prof"] + res["factset_future_prof"]
    
    ax.plot(pred_quarters, yahoo_rev_line, color="#9c27b0", linestyle=":", linewidth=1.2, alpha=0.6, label="Yahoo共識營收 (基準)")
    ax.plot(pred_quarters, yahoo_prof_line, color="#ba68c8", linestyle=":", linewidth=1.2, alpha=0.5)
    
    ax.plot(pred_quarters, factset_rev_line, color="#3f51b5", linestyle="-.", linewidth=1.2, alpha=0.6, label="FactSet共識營收 (基準)")
    ax.plot(pred_quarters, factset_prof_line, color="#7986cb", linestyle="-.", linewidth=1.2, alpha=0.5)
    
    # Scheme A: Plot Consensus Markers (Revenue: Star, Profit: Diamond)
    first_star_yahoo_rev = True
    first_star_yahoo_prof = True
    first_star_factset_rev = True
    first_star_factset_prof = True
    
    for i, q in enumerate(pred_quarters):
        # Yahoo Revenue
        y_rev = yahoo_rev_line[i]
        if not np.isnan(y_rev):
            ax.plot(q, y_rev, marker='*', color='#9c27b0', markersize=9,
                    markeredgecolor='black', markeredgewidth=0.5, zorder=5,
                    label="Yahoo共識營收 (Consensus Rev)" if first_star_yahoo_rev else "")
            first_star_yahoo_rev = False
            
        # Yahoo Profit (Operating Income)
        y_prof = yahoo_prof_line[i]
        if not np.isnan(y_prof):
            ax.plot(q, y_prof, marker='d', color='#ba68c8', markersize=7,
                    markeredgecolor='black', markeredgewidth=0.4, zorder=5,
                    label="Yahoo共識利益 (Consensus Profit)" if first_star_yahoo_prof else "")
            first_star_yahoo_prof = False
            
        # FactSet Revenue
        f_rev = factset_rev_line[i]
        if not np.isnan(f_rev):
            ax.plot(q, f_rev, marker='*', color='#3f51b5', markersize=9,
                    markeredgecolor='black', markeredgewidth=0.5, zorder=5,
                    label="FactSet共識營收 (Consensus Rev)" if first_star_factset_rev else "")
            first_star_factset_rev = False
            
        # FactSet Profit (Operating Income)
        f_prof = factset_prof_line[i]
        if not np.isnan(f_prof):
            ax.plot(q, f_prof, marker='d', color='#7986cb', markersize=7,
                    markeredgecolor='black', markeredgewidth=0.4, zorder=5,
                    label="FactSet共識利益 (Consensus Profit)" if first_star_factset_prof else "")
            first_star_factset_prof = False
            
    # Scheme B: Plot Forecast Consensus Discrepancy Shade (Future Forecast range)
    future_x = future_quarters
    future_pred_rev = pred_rev_line[-4:]
    future_factset_rev = res["factset_future_rev"]
    future_yahoo_rev = res["yahoo_future_rev"]
    
    ref_future_rev = None
    if not np.isnan(future_factset_rev).all():
        ref_future_rev = [x if not np.isnan(x) else y for x, y in zip(future_factset_rev, future_pred_rev)]
    elif not np.isnan(future_yahoo_rev).all():
        ref_future_rev = [x if not np.isnan(x) else y for x, y in zip(future_yahoo_rev, future_pred_rev)]
        
    if ref_future_rev is not None:
        ax.fill_between(future_x, future_pred_rev, ref_future_rev, color="#3f51b5", alpha=0.1,
                        label="預測共識分歧帶 (Consensus Band)")
                        
    # Plot True of Source Markers (if any are in display_quarters)
    first_star = True
    for idx, q in enumerate(display_quarters):
        if res["true_source_flags"].get(q, False):
            y_val = display_actual_rev[idx]
            ax.plot(q, y_val, marker='*', color='#f1c40f', markersize=11,
                    markeredgecolor='black', markeredgewidth=0.8, zorder=6,
                    label='官方真實佔比揭露' if first_star else "")
            first_star = False
    
    # Draw vertical dashed line for boundary
    boundary_idx = 23.5
    ax.axvline(x=boundary_idx, color="#e53935", linestyle="--", linewidth=1.5, label="最新數據邊界")
    
    # Add background shade areas
    ax.axvspan(-0.5, 11.5, color="#e0e0e0", alpha=0.5, label="1. 模型初始暖機期 (Warm-up - 12Q)")
    ax.axvspan(11.5, 23.5, color="#fff59d", alpha=0.5, label="2. 滾動回測期 (Walk-Forward)")
    ax.axvspan(23.5, 27.5, color="#b2dfdb", alpha=0.5, label="3. 未來前瞻預測期 (Future - 4Q)")
    
    # Compute YoY% for future forecast
    annotation_lines = ["★ 預測展望 (自下而上融合預測)"]
    for i, q_fut in enumerate(future_quarters):
        actual_prev_idx = N - 4 + i
        prev_rev = revenue[actual_prev_idx]
        prev_prof = profit[actual_prev_idx]
        
        fut_rev = res["future_corr_rev"][i]
        fut_prof = res["future_corr_prof"][i]
        
        rev_yoy = (fut_rev - prev_rev) / prev_rev * 100.0
        prof_yoy = (fut_prof - prev_prof) / prev_prof * 100.0
        
        ax.plot(q_fut, fut_rev, marker="^", color="#1f77b4", markersize=6)
        ax.plot(q_fut, fut_prof, marker="^", color="#4caf50", markersize=6)
        
        annotation_lines.append(f"{q_fut}: 營收 {fut_rev:.1f}億 ({rev_yoy:+.1f}% YoY) | 利益 {fut_prof:.1f}億 ({prof_yoy:+.1f}% YoY)")
        
    annotation_text = "\n".join(annotation_lines)
    
    # Adjust Y-axis limit to leave room at the top for consolidated text box
    max_y = max(max(display_actual_rev), max(pred_rev_line))
    ax.set_ylim(0, max_y * 1.35)
    
    ax.text(0.98, 0.95, annotation_text, transform=ax.transAxes,
            ha='right', va='top', fontsize=8.5, fontweight='bold', color="#111111",
            bbox=dict(boxstyle="round,pad=0.4", fc="#ffffff", ec="#1f77b4", lw=1.2, alpha=0.95))
    
    # Labels and Formatting
    ax.set_title(f"{stock_code} {company_name} 季度損益預測與滾動回測對照圖", fontsize=14, fontweight="bold")
    ax.set_xlabel("季度", fontsize=11)
    ax.set_ylabel("金額 (億元新台幣)", fontsize=11)
    ax.grid(True, linestyle=":", alpha=0.6)
    
    ax.set_xticks(np.arange(len(all_x_quarters)))
    ax.set_xticklabels(all_x_quarters, rotation=45, ha='right', fontsize=9)
    
    plt.tight_layout()
    fig.subplots_adjust(left=0.08, bottom=0.20, right=0.96, top=0.90)
    
    ax.legend(loc="upper left", framealpha=0.9, fontsize=9.5)
    
    logo_path = os.path.join(ROOT, "logos", f"{stock_code}.png")
    if os.path.exists(logo_path):
        try:
            img = Image.open(logo_path).convert("RGBA")
            w, h = img.size
            target_width = 48
            zoom_factor = target_width / w
            logo_arr = np.array(img)
            imagebox = OffsetImage(logo_arr, zoom=zoom_factor, interpolation="lanczos", resample=True)
            ab = AnnotationBbox(imagebox, (0.01, 0.01), xycoords='figure fraction',
                                boxcoords="figure fraction", frameon=False, box_alignment=(0.0, 0.0))
            ax.add_artist(ab)
        except Exception as e:
            print(f"Failed to embed logo in main chart: {e}")
            
    plot_path1 = os.path.join(OUTPUT_DIR, f"quarterly_predict_{stock_code}.png")
    plt.savefig(plot_path1)
    plt.close()
    print(f"Generated Forecast Plot: {plot_path1}")
    
    # ----------------------------------------------------
    # Chart 2: Stacked Area Chart for Canonical Cycle Breakdown (Dynamic weights over time)
    # ----------------------------------------------------
    active_cycles = res["active_cycles"]
    sorted_active_cycles = sorted(active_cycles.items(), key=lambda x: x[1], reverse=True)
    cycle_names = [item[0] for item in sorted_active_cycles]
    
    # Build the 28 quarters stacked area timeline
    stack_data = []
    
    # For historical 24 quarters
    for c in cycle_names:
        row = []
        for t in range(display_start_idx, N):
            w = res["weights_over_time"][t].get(c, 0.0)
            row.append(revenue[t] * w)
        for i in range(4):
            # Dynamic future weights are derived from Bottom-Up forecasts:
            row.append(res["segment_results"][c]["future_corr_rev"][i])
            
        stack_data.append(row)
        
    CYCLE_COLORS = {
        "AI_Compute_Infra": "#1f77b4", # Strong Blue
        "AI_Compute": "#3498db",       # Light Blue
        "Memory": "#e67e22",           # Orange
        "Smartphone": "#2ecc71",       # Emerald Green
        "PC_Consumer": "#e74c3c",       # Red
        "EV_Automotive": "#9b59b6",     # Purple
        "Network_Infra": "#1abc9c",     # Turquoise
        "Software_SaaS": "#f1c40f",     # Yellow
        "Consumer_IoT": "#d35400",      # Pumpkin
        "Other": "#7f8c8d"             # Gray
    }
    colors_list = [CYCLE_COLORS.get(name, "#7f7f7f") for name in cycle_names]
    
    fig, ax = plt.subplots(figsize=(12, 6.5), dpi=300)
    
    ax.stackplot(all_x_quarters, stack_data, labels=[f"{name} (最新:{active_cycles.get(name, 0.0)*100:.1f}%)" for name in cycle_names],
                 colors=colors_list, alpha=0.85)
    
    ax.axvline(x=boundary_idx, color="#e53935", linestyle="--", linewidth=1.8)
    
    ax.text(boundary_idx - 0.1, max(pred_rev_line) * 0.95, "歷史數據", ha="right", va="center", color="#e53935", fontweight="bold", fontsize=10)
    ax.text(boundary_idx + 0.1, max(pred_rev_line) * 0.95, "未來預測", ha="left", va="center", color="#e53935", fontweight="bold", fontsize=10)
    
    ax.axvspan(23.5, 27.5, color="#b2dfdb", alpha=0.2, label="未來前瞻預測期 (Next 4Q)")
    
    ax.set_title(f"{stock_code} {company_name} 季度營收之 Canonical Cycle 拆解堆疊面積圖", fontsize=14, fontweight="bold")
    ax.set_xlabel("季度", fontsize=11)
    ax.set_ylabel("營業收入 (億元新台幣)", fontsize=11)
    ax.grid(True, linestyle=":", alpha=0.6)
    
    ax.set_xticks(np.arange(len(all_x_quarters)))
    ax.set_xticklabels(all_x_quarters, rotation=45, ha='right', fontsize=9)
    
    # Plot True of Source Markers (if any are in all_x_quarters)
    first_star = True
    for idx, q in enumerate(all_x_quarters):
        if res["true_source_flags"].get(q, False):
            y_val = display_actual_rev[idx] if idx < 24 else res["future_corr_rev"][idx - 24]
            ax.plot(idx, y_val, marker='*', color='#f1c40f', markersize=11,
                    markeredgecolor='black', markeredgewidth=0.8, zorder=6,
                    label='官方真實佔比 (True of Source)' if first_star else "")
            first_star = False
            
    plt.tight_layout()
    fig.subplots_adjust(left=0.08, bottom=0.20, right=0.96, top=0.90)
    
    ax.legend(loc="upper left", title="Canonical Cycle 標準分類與最新權重", framealpha=0.9, fontsize=9.5)
    
    if os.path.exists(logo_path):
        try:
            img = Image.open(logo_path).convert("RGBA")
            w, h = img.size
            target_width = 48
            zoom_factor = target_width / w
            logo_arr = np.array(img)
            imagebox = OffsetImage(logo_arr, zoom=zoom_factor, interpolation="lanczos", resample=True)
            ab = AnnotationBbox(imagebox, (0.01, 0.01), xycoords='figure fraction',
                                boxcoords="figure fraction", frameon=False, box_alignment=(0.0, 0.0))
            ax.add_artist(ab)
        except Exception as e:
            print(f"Failed to embed logo in cycle chart: {e}")
            
    plot_path2 = os.path.join(OUTPUT_DIR, f"quarterly_cycle_breakdown_{stock_code}.png")
    plt.savefig(plot_path2)
    plt.close()
    print(f"Generated Cycle Breakdown Plot: {plot_path2}")
    
    # ----------------------------------------------------
    # 3. Generate Markdown Report
    # ----------------------------------------------------
    report_markdown = []
    report_markdown.append(f"# {stock_code} {company_name} 季度營收、支出與利益預測決策報告")
    report_markdown.append(f"**分析時間**：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} CST\n")
    
    report_markdown.append("## 1. 核心模型預測評估摘要\n")
    report_markdown.append("本報告採用 **Bottom-Up（自下而上）板塊獨立預測管線**，結合 **Dynamic Weighting（歷史/未來權重動態演進）** 與 **Cycle Growth Multipliers（產業景氣成長修正）** 進行綜合預測與回測。\n")
    report_markdown.append(f"我們對 {company_name} 旗下各個標準景氣分類（Canonical Cycle）的營收與支出進行了獨立的時間序列擬合（10-Model 滾動回測），最終加總為 {company_name} 整體營收與支出預測，藉此消除傳統自上而下預測中「不同業務成長率被強行等同」的缺點。\n")
    report_markdown.append(f"*   **最新已公佈季度**：`{quarters[-1]}`\n")
    report_markdown.append(f"*   **總營業收入合力回測指標**：MAPE: `{res['mape_rev']:.2f}%`, MPE: `{res['mpe_rev']:.2f}%`\n")
    report_markdown.append(f"*   **總支出合力回測指標**：MAPE: `{res['mape_exp']:.2f}%`, MPE: `{res['mpe_exp']:.2f}%`\n")
    report_markdown.append(f"*   **營業利益合力推導指標**：MAPE: `{res['mape_prof']:.2f}%`, MPE: `{res['mpe_prof']:.2f}%`\n")
    
    def format_mape(val):
        return f"{val:.2f}%" if not np.isnan(val) else "N/A (資料不足)"
        
    report_markdown.append(f"*   **Yahoo共識回測指標 (Benchmark)**：營收 MAPE: `{format_mape(res['mape_yahoo_rev'])}`, 利益 MAPE: `{format_mape(res['mape_yahoo_prof'])}`\n")
    report_markdown.append(f"*   **FactSet共識回測指標 (Benchmark)**：營收 MAPE: `{format_mape(res['mape_factset_rev'])}`, 利益 MAPE: `{format_mape(res['mape_factset_prof'])}`\n")
    
    report_markdown.append("\n### 各業務分類（Segment-wise）最優模型適配：\n")
    report_markdown.append("| 業務分類 | 最新權重 | 營收最優模型 (MAPE) | 支出最優模型 (MAPE) | 景氣修正係數 |")
    report_markdown.append("|:---|:---:|:---|:---|:---:|")
    for c in cycle_names:
        seg = res["segment_results"][c]
        report_markdown.append(f"| **{c}** | {active_cycles[c]*100:.1f}% | {seg['best_rev_model']} ({seg['best_rev_mape']:.1f}%) | {seg['best_exp_model']} ({seg['best_exp_mape']:.1f}%) | {CYCLE_MULTIPLIERS.get(c, 1.0):+.2f}x |")
        
    report_markdown.append("\n---\n")
    report_markdown.append("## 2. 季度損益前瞻展望預測表 (未來 4 季)\n")
    report_markdown.append("下列為未來 4 季度自下而上加總之總體營收、總支出與營業利益的前瞻預估，已套用偏差修正與產業景氣加成：\n")
    report_markdown.append("| 預測季度 | 預估營收 (億元) | 營收 YoY% | 預估總支出 (億元) | 支出 YoY% | 預估營業利益 (億元) | 利益 YoY% |")
    report_markdown.append("|:---|:---:|:---:|:---:|:---:|:---:|:---:|")
    
    for i, q_fut in enumerate(future_quarters):
        actual_prev_idx = N - 4 + i
        prev_rev = revenue[actual_prev_idx]
        prev_exp = expense[actual_prev_idx]
        prev_prof = profit[actual_prev_idx]
        
        fut_rev = res["future_corr_rev"][i]
        fut_exp = res["future_corr_exp"][i]
        fut_prof = res["future_corr_prof"][i]
        
        rev_yoy = (fut_rev - prev_rev) / prev_rev * 100.0
        exp_yoy = (fut_exp - prev_exp) / prev_exp * 100.0
        prof_yoy = (fut_prof - prev_prof) / prev_prof * 100.0
        
        report_markdown.append(f"| **{q_fut}** | {fut_rev:.1f} | {rev_yoy:+.1f}% | {fut_exp:.1f} | {exp_yoy:+.1f}% | **{fut_prof:.1f}** | **{prof_yoy:+.1f}%** |")
        
    report_markdown.append("\n*註：YoY% 為與去年同季（4 季前）之真實數據相比。*\n")
    
    report_markdown.append("\n### 市場分析師共識預報對比表 (Consensus Benchmarks)：\n")
    report_markdown.append("下列為未來 4 季自下而上合力預估值與 Yahoo、FactSet 兩大市場共識（True of Consensus）數據之對比：\n")
    report_markdown.append("| 預測季度 | 自建預估營收 (億元) | Yahoo共識營收 | FactSet共識營收 | 自建預估利益 (億元) | Yahoo共識利益 | FactSet共識利益 |")
    report_markdown.append("|:---|:---:|:---:|:---:|:---:|:---:|:---:|")
    
    for i, q_fut in enumerate(future_quarters):
        fut_rev = res["future_corr_rev"][i]
        fut_prof = res["future_corr_prof"][i]
        
        y_rev = f"{res['yahoo_future_rev'][i]:.1f}" if not np.isnan(res['yahoo_future_rev'][i]) else "N/A"
        y_prof = f"{res['yahoo_future_prof'][i]:.1f}" if not np.isnan(res['yahoo_future_prof'][i]) else "N/A"
        
        f_rev = f"{res['factset_future_rev'][i]:.1f}" if not np.isnan(res['factset_future_rev'][i]) else "N/A"
        f_prof = f"{res['factset_future_prof'][i]:.1f}" if not np.isnan(res['factset_future_prof'][i]) else "N/A"
        
        report_markdown.append(f"| **{q_fut}** | {fut_rev:.1f} | {y_rev} | {f_rev} | **{fut_prof:.1f}** | {y_prof} | {f_prof} |")
    report_markdown.append("\n")
    
    report_markdown.append("---\n")
    report_markdown.append("## 3. 營業收入之 Canonical Cycle 景氣循環拆解展望\n")
    report_markdown.append("由於各業務單度預測且成長性不同，未來四季的營收結構佔比呈**動態變化**。例如，高成長的 AI 算力基礎設施佔比將逐季拉升，而 PC 佔比微幅下調：\n")
    report_markdown.append("| 景氣循環分類 | 最新權重 | " + " | ".join([f"{q} 預估 (億元) [佔比%]" for q in future_quarters]) + " |")
    report_markdown.append("|:---|:---:|:" + ":|:".join(["---" for _ in future_quarters]) + ":|")
    
    for name in cycle_names:
        w_latest = active_cycles.get(name, 0.0)
        row_str = f"| **{name}** | {w_latest*100:.1f}%"
        for i in range(4):
            fut_rev = res["future_corr_rev"][i]
            seg_rev = res["segment_results"][name]["future_corr_rev"][i]
            pct = (seg_rev / fut_rev * 100.0) if fut_rev > 0 else 0.0
            row_str += f" | {seg_rev:.1f} [{pct:.1f}%]"
        row_str += " |"
        report_markdown.append(row_str)
        
    report_markdown.append("\n---\n")
    report_markdown.append("## 4. 決策圖表參照\n")
    report_markdown.append(f"*   **季度損益預測與回測對照圖**：\n")
    report_markdown.append(f"    ![季度損益預測](file:///{OUTPUT_DIR.replace(os.sep, '/')}/quarterly_predict_{stock_code}.png)\n")
    report_markdown.append(f"*   **季度營收之 Canonical Cycle 堆疊面積圖**：\n")
    report_markdown.append(f"    ![季度營收拆解](file:///{OUTPUT_DIR.replace(os.sep, '/')}/quarterly_cycle_breakdown_{stock_code}.png)\n")
    
    report_path = os.path.join(OUTPUT_DIR, f"quarterly_predict_report_{stock_code}.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_markdown))
    print(f"Generated Markdown Report: {report_path}")

if __name__ == "__main__":
    stock = "2330"
    if len(sys.argv) > 1:
        stock = sys.argv[1]
    res = forecast_quarterly(stock)
    if res:
        generate_plots_and_report(res)
    else:
        print("Failed to run forecast pipeline.")
