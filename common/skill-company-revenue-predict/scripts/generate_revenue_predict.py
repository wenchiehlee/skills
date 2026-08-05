import os
import re
import csv
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

# Setup Chinese font support for Windows and Linux
if os.name == "posix":
    for font_path in [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansTC-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
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
RAW_REVENUE_CSV = os.path.join(ROOT, "data", "Python-Actions.GoodInfo.Analyzer", "raw_revenue.csv")
YAHOO_HISTORY_CSV = os.path.join(ROOT, "data", "Yahoo.Finance", "raw_yahoo_finance_consensus_history.csv")
FACTSET_DETAILED_CSV = os.path.join(ROOT, "data", "GoogleSearch.Factset", "raw_factset_detailed_report.csv")
OUTPUT_DIR = os.path.join(ROOT, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Consensus Helpers

def get_quarter_of_month(m_str):
    y, m = map(int, m_str.split("/"))
    if m in [1, 2, 3]:
        return f"{y}/Q1"
    elif m in [4, 5, 6]:
        return f"{y}/Q2"
    elif m in [7, 8, 9]:
        return f"{y}/Q3"
    else:
        return f"{y}/Q4"

def calc_monthly_seasonal_weight(m_str, months_list, revenue_list):
    y_target, m_target = map(int, m_str.split("/"))
    if m_target in [1, 2, 3]:
        q_months = [1, 2, 3]
    elif m_target in [4, 5, 6]:
        q_months = [4, 5, 6]
    elif m_target in [7, 8, 9]:
        q_months = [7, 8, 9]
    else:
        q_months = [10, 11, 12]
    
    weights = []
    for y_offset in [1, 2, 3]:
        y_prev = y_target - y_offset
        has_all = True
        q_vals = []
        for m_idx in q_months:
            m_key = f"{y_prev}/{m_idx:02d}"
            if m_key in months_list:
                val = revenue_list[months_list.index(m_key)]
                if not np.isnan(val) and val > 0:
                    q_vals.append(val)
                else:
                    has_all = False
                    break
            else:
                has_all = False
                break
        if has_all:
            q_sum = sum(q_vals)
            if q_sum > 0:
                target_val = q_vals[q_months.index(m_target)]
                weights.append(target_val / q_sum)
    
    if weights:
        return np.mean(weights)
    
    all_weights = []
    unique_years = sorted(list(set([int(m.split("/")[0]) for m in months_list if int(m.split("/")[0]) < y_target])))
    for y_prev in unique_years:
        has_all = True
        q_vals = []
        for m_idx in q_months:
            m_key = f"{y_prev}/{m_idx:02d}"
            if m_key in months_list:
                val = revenue_list[months_list.index(m_key)]
                if not np.isnan(val) and val > 0:
                    q_vals.append(val)
                else:
                    has_all = False
                    break
            else:
                has_all = False
                break
        if has_all:
            q_sum = sum(q_vals)
            if q_sum > 0:
                target_val = q_vals[q_months.index(m_target)]
                all_weights.append(target_val / q_sum)
    if all_weights:
        return np.mean(all_weights)
    
    return 1.0 / 3.0

def load_yahoo_monthly_consensus(stock_code):
    yahoo_map = {}
    if not os.path.exists(YAHOO_HISTORY_CSV):
        return yahoo_map
    try:
        df = pd.read_csv(YAHOO_HISTORY_CSV, encoding="utf-8")
        df.columns = df.columns.str.strip()
        df_stock = df[df["stock_code"].astype(str).str.strip() == str(stock_code)].copy()
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
        for _, row in df_stock.iterrows():
            dt_str = str(row["forecast_asof_date"]).split(" ")[0]
            dt = pd.to_datetime(dt_str).date()
            q0, q1 = get_q0_q1_from_date(dt)
            d_map = yahoo_map.setdefault(dt, {})
            rev_0q = float(row["revenue_0q_avg"]) / 1e8 if ("revenue_0q_avg" in row and not pd.isna(row["revenue_0q_avg"])) else None
            rev_1q = float(row["revenue_1q_avg"]) / 1e8 if ("revenue_1q_avg" in row and not pd.isna(row["revenue_1q_avg"])) else None
            if rev_0q is not None:
                d_map[q0] = rev_0q
            if rev_1q is not None:
                d_map[q1] = rev_1q
    except Exception as e:
        print(f"Error loading Yahoo consensus: {e}")
    return yahoo_map

def load_factset_monthly_consensus(stock_code):
    factset_map = {}
    if not os.path.exists(FACTSET_DETAILED_CSV):
        return factset_map
    try:
        df = pd.read_csv(FACTSET_DETAILED_CSV, encoding="utf-8")
        df.columns = df.columns.str.strip()
        code_col = "代號" if "代號" in df.columns else "股票代號"
        df_stock = df[df[code_col].astype(str).str.strip().str.replace("-TW", "").str.replace(".TW", "") == str(stock_code)].copy()
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
        for _, row in df_stock.iterrows():
            dt_str = str(row["MD日期"]).split(" ")[0]
            dt = pd.to_datetime(dt_str).date()
            q0, q1 = get_q0_q1_from_date(dt)
            d_map = factset_map.setdefault(dt, {})
            for q_key in [q0, q1]:
                q_year = q_key.split("/")[0]
                rev_col = f"{q_year}營收平均值"
                if rev_col in row and not pd.isna(row[rev_col]):
                    annual_rev = float(row[rev_col])
                    if annual_rev > 1e11:
                        scale = 1e-8
                    elif annual_rev > 1e8:
                        scale = 1e-5
                    else:
                        scale = 1.0
                    rev_val_annual = annual_rev * scale
                    rev_val = rev_val_annual * 0.25
                    d_map[q_key] = rev_val
    except Exception as e:
        print(f"Error loading FactSet consensus: {e}")
    return factset_map

def get_monthly_announcement_date(m_str):
    y, m = map(int, m_str.split("/"))
    m_ann = m + 1
    y_ann = y
    if m_ann > 12:
        m_ann = 1
        y_ann = y + 1
    return datetime.date(y_ann, m_ann, 10)

def query_monthly_consensus(m_str, consensus_map, target_date=None, months_list=[], revenue_list=[]):
    q_target = get_quarter_of_month(m_str)
    valid_dates = list(consensus_map.keys())
    if target_date is not None:
        valid_dates = [d for d in valid_dates if d <= target_date]
    if not valid_dates:
        return None
    latest_date = max(valid_dates)
    q_consensus = consensus_map[latest_date].get(q_target, None)
    if q_consensus is None:
        return None
    w = calc_monthly_seasonal_weight(m_str, months_list, revenue_list)
    return q_consensus * w

# 10 Models Implementation

def model_seasonal_naive(train, steps):
    predictions = []
    for k in range(steps):
        predictions.append(train[-12 + (k % 12)])
    return predictions

def model_yoy_growth_adjusted(train, train_months, steps):
    yoy_list = []
    if train_months:
        last_month = train_months[-1]
        match = re.match(r"(\d{4})/", last_month)
        if match:
            last_year = int(match.group(1))
            prev_year = last_year - 1
            last_year_str = f"{last_year}/"
            prev_year_str = f"{prev_year}/"
            idx_last = [i for i, m in enumerate(train_months) if m.startswith(last_year_str)]
            for idx in idx_last:
                m_last = train_months[idx]
                m_prev = m_last.replace(last_year_str, prev_year_str)
                if m_prev in train_months:
                    idx_prev = train_months.index(m_prev)
                    val_last = train[idx]
                    val_prev = train[idx_prev]
                    if val_prev > 0:
                        yoy_list.append((val_last - val_prev) / val_prev)
    avg_yoy = np.mean(yoy_list) if yoy_list else 0.0
    predictions = []
    for k in range(steps):
        base_val = train[-12 + (k % 12)]
        predictions.append(base_val * (1.0 + avg_yoy))
    return predictions, avg_yoy

def model_linear_trend(train, steps):
    n = len(train)
    x = np.arange(n)
    y = np.array(train)
    a, b = np.polyfit(x, y, 1)
    predictions = [a * (n + k) + b for k in range(steps)]
    return predictions

def model_ar1(train, steps):
    n = len(train)
    y = np.array(train)
    x = y[:-1]
    target = y[1:]
    a, b = np.polyfit(x, target, 1)
    predictions = []
    last_val = train[-1]
    for k in range(steps):
        next_val = a * last_val + b
        predictions.append(next_val)
        last_val = next_val
    return predictions

def model_seasonal_decomposition(train, steps):
    n = len(train)
    monthly_vals = {i: [] for i in range(1, 13)}
    for idx in range(n):
        month = (idx % 12) + 1
        monthly_vals[month].append(train[idx])
    monthly_avgs = {m: np.mean(vals) for m, vals in monthly_vals.items()}
    overall_mean = np.mean(train)
    S = {m: (monthly_avgs[m] / overall_mean if overall_mean > 0 else 1.0) for m in range(1, 13)}
    train_adj = [train[idx] / S[(idx % 12) + 1] for idx in range(n)]
    a, b = np.polyfit(np.arange(n), np.array(train_adj), 1)
    predictions = []
    for k in range(steps):
        t_val = n + k
        s_val = S[(t_val % 12) + 1]
        predictions.append((a * t_val + b) * s_val)
    return predictions

def model_holt_linear(train, steps, alpha=0.2, beta=0.2):
    n = len(train)
    L = [0.0] * n
    T = [0.0] * n
    L[0] = train[0]
    T[0] = train[1] - train[0]
    for t in range(1, n):
        L[t] = alpha * train[t] + (1 - alpha) * (L[t-1] + T[t-1])
        T[t] = beta * (L[t] - L[t-1]) + (1 - beta) * T[t-1]
    predictions = [L[-1] + (k + 1) * T[-1] for k in range(steps)]
    return predictions

def model_holt_winters_multiplicative(train, steps, alpha=0.2, beta=0.2, gamma=0.2):
    n = len(train)
    if n < 24:
        return model_seasonal_decomposition(train, steps)
    L_init = np.mean(train[:12])
    S = list(np.array(train[:12]) / L_init)
    L = [0.0] * n
    T = [0.0] * n
    L[11] = L_init
    T[11] = (np.mean(train[12:24]) - np.mean(train[:12])) / 12.0
    S_full = S + [1.0] * (n - 12)
    for t in range(12, n):
        S_prev_seasonal = S_full[t-12]
        L[t] = alpha * (train[t] / S_prev_seasonal) + (1 - alpha) * (L[t-1] + T[t-1])
        T[t] = beta * (L[t] - L[t-1]) + (1 - beta) * T[t-1]
        S_full[t] = gamma * (train[t] / L[t]) + (1 - gamma) * S_prev_seasonal
    predictions = []
    for k in range(steps):
        idx = n + k
        s_factor = S_full[-12 + (k % 12)]
        predictions.append((L[-1] + (k + 1) * T[-1]) * s_factor)
    return predictions

def model_wma_3(train, steps):
    predictions = []
    history = list(train)
    for k in range(steps):
        next_val = (3 * history[-1] + 2 * history[-2] + 1 * history[-3]) / 6.0
        predictions.append(next_val)
        history.append(next_val)
    return predictions

def model_fourier_seasonal(train, steps):
    n = len(train)
    t = np.arange(n)
    X = np.column_stack([
        np.ones(n),
        t,
        np.cos(2 * np.pi * t / 12),
        np.sin(2 * np.pi * t / 12),
        np.cos(4 * np.pi * t / 12),
        np.sin(4 * np.pi * t / 12)
    ])
    y = np.array(train)
    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    predictions = []
    for k in range(steps):
        t_fut = n + k
        x_fut = np.array([
            1.0,
            t_fut,
            np.cos(2 * np.pi * t_fut / 12),
            np.sin(2 * np.pi * t_fut / 12),
            np.cos(4 * np.pi * t_fut / 12),
            np.sin(4 * np.pi * t_fut / 12)
        ])
        predictions.append(np.dot(x_fut, beta))
    return predictions

def model_ar2(train, steps):
    n = len(train)
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

def evaluate_models_for_stock(stock_code):
    df_stock = pd.read_csv(RAW_REVENUE_CSV)
    df_stock = df_stock[df_stock["stock_code"].astype(str) == str(stock_code)]
    if df_stock.empty:
        print(f"Error: No data found for stock {stock_code}")
        return None
    df_stock = df_stock.sort_values("月別")
    months = df_stock["月別"].tolist()
    col_rev = "合併營業收入_營收_億" if "合併營業收入_營收_億" in df_stock.columns else "營業收入_營收_億"
    revenue = pd.to_numeric(df_stock[col_rev], errors="coerce").tolist()
    missing_months = [m for m, r in zip(months, revenue) if np.isnan(r) or r <= 0]
    if missing_months:
        valid_indices = [i for i, r in enumerate(revenue) if not np.isnan(r) and r > 0]
        months = [months[i] for i in valid_indices]
        revenue = [revenue[i] for i in valid_indices]
    total_len = len(months)
    display_len = min(60, total_len)
    display_months = months[-display_len:]
    display_revenue = revenue[-display_len:]
    warmup_len = 24
    if display_len <= 24:
        warmup_len = max(12, display_len // 2)
    warmup_months = display_months[:warmup_len]
    warmup_revenue = display_revenue[:warmup_len]
    backtest_months = display_months[warmup_len:]
    backtest_revenue = display_revenue[warmup_len:]
    val_steps = len(backtest_months)
    if val_steps == 0:
        print(f"Error: No backtest months found for stock {stock_code}")
        return None
    model_funcs = {
        "Model 1 (Seasonal Naive)": lambda tr, steps, tr_m: model_seasonal_naive(tr, steps),
        "Model 2 (YoY Growth Adjusted)": lambda tr, steps, tr_m: model_yoy_growth_adjusted(tr, tr_m, steps)[0],
        "Model 3 (Linear Trend)": lambda tr, steps, tr_m: model_linear_trend(tr, steps),
        "Model 4 (AR-1 Rolling)": lambda tr, steps, tr_m: model_ar1(tr, steps),
        "Model 5 (Seasonal Decomp)": lambda tr, steps, tr_m: model_seasonal_decomposition(tr, steps),
        "Model 6 (Holt Linear Double)": lambda tr, steps, tr_m: model_holt_linear(tr, steps),
        "Model 7 (Holt-Winters Triple)": lambda tr, steps, tr_m: model_holt_winClean(tr, steps) if len(tr) < 24 else model_holt_winters_multiplicative(tr, steps),
        "Model 8 (WMA-3)": lambda tr, steps, tr_m: model_wma_3(tr, steps),
        "Model 9 (Fourier Seasonal)": lambda tr, steps, tr_m: model_fourier_seasonal(tr, steps),
        "Model 10 (AR-2 Rolling)": lambda tr, steps, tr_m: model_ar2(tr, steps),
    }
    def model_holt_winClean(tr, steps):
        return model_holt_winters_multiplicative(tr, steps)
    results = []
    latest_val_month = backtest_months[-1]
    ly, lm = map(int, latest_val_month.split("/"))
    future_months = []
    curr_y, curr_m = ly, lm
    for _ in range(3):
        curr_m += 1
        if curr_m > 12:
            curr_m = 1
            curr_y += 1
        future_months.append(f"{curr_y}/{curr_m:02d}")
    for name, func in model_funcs.items():
        try:
            val_preds = []
            for m_bt in backtest_months:
                idx = months.index(m_bt)
                current_tr_data = revenue[:idx]
                current_tr_months = months[:idx]
                pred_1step = func(current_tr_data, 1, current_tr_months)
                val_preds.append(pred_1step[0])
            full_tr_data = revenue
            full_tr_months = months
            future_preds = func(full_tr_data, 3, full_tr_months)
            mape = np.mean(np.abs((np.array(backtest_revenue) - np.array(val_preds)) / np.array(backtest_revenue))) * 100.0
            mpe = np.mean((np.array(backtest_revenue) - np.array(val_preds)) / np.array(backtest_revenue)) * 100.0
            corrected_future_preds = [val * (1.0 + mpe / 100.0) for val in future_preds]
            results.append({
                "model_name": name,
                "mape": mape,
                "mpe": mpe,
                "val_preds": val_preds,
                "future_preds_raw": future_preds,
                "future_preds_corrected": corrected_future_preds
            })
        except Exception as e:
            print(f"   ⚠️ Model {name} failed: {e}")
    results.sort(key=lambda x: x["mape"])
    yahoo_map = load_yahoo_monthly_consensus(stock_code)
    factset_map = load_factset_monthly_consensus(stock_code)
    yahoo_backtest = []
    factset_backtest = []
    for m_bt in backtest_months:
        ann_dt = get_monthly_announcement_date(m_bt)
        y_val = query_monthly_consensus(m_bt, yahoo_map, ann_dt, months, revenue)
        yahoo_backtest.append(y_val if y_val is not None else np.nan)
        f_val = query_monthly_consensus(m_bt, factset_map, ann_dt, months, revenue)
        factset_backtest.append(f_val if f_val is not None else np.nan)
    yahoo_future = []
    factset_future = []
    for m_fut in future_months:
        y_val = query_monthly_consensus(m_fut, yahoo_map, None, months, revenue)
        yahoo_future.append(y_val if y_val is not None else np.nan)
        f_val = query_monthly_consensus(m_fut, factset_map, None, months, revenue)
        factset_future.append(f_val if f_val is not None else np.nan)
    def calc_nan_mape(actuals, preds):
        acts = np.array(actuals)
        prds = np.array(preds)
        mask = ~np.isnan(prds)
        if not np.any(mask):
            return np.nan
        denom = np.where(acts[mask] == 0, 1e-9, acts[mask])
        return np.mean(np.abs((acts[mask] - prds[mask]) / denom)) * 100.0
    mape_yahoo = calc_nan_mape(backtest_revenue, yahoo_backtest)
    mape_factset = calc_nan_mape(backtest_revenue, factset_backtest)
    return {
        "stock_code": stock_code,
        "company_name": df_stock["company_name"].iloc[0],
        "months": months,
        "revenue": revenue,
        "display_months": display_months,
        "display_revenue": display_revenue,
        "warmup_months": warmup_months,
        "warmup_revenue": warmup_revenue,
        "backtest_months": backtest_months,
        "backtest_revenue": backtest_revenue,
        "future_months": future_months,
        "model_results": results,
        "yahoo_backtest": yahoo_backtest,
        "factset_backtest": factset_backtest,
        "yahoo_future": yahoo_future,
        "factset_future": factset_future,
        "mape_yahoo": mape_yahoo,
        "mape_factset": mape_factset
    }

def generate_report_and_plots():
    stock_list_path = os.path.join(ROOT, "data", "Python-Actions.GoodInfo", "StockID_TWSE_TPEX.csv")
    stock_codes = []
    if os.path.exists(stock_list_path):
        try:
            df_list = pd.read_csv(stock_list_path, encoding="utf-8")
            df_list.columns = df_list.columns.str.strip()
            if "代號" in df_list.columns:
                codes = df_list["代號"].dropna().astype(str).str.strip().tolist()
                stock_codes = [c for c in codes if c != "0000" and c.strip()]
        except Exception as e:
            print(f"Error reading StockID_TWSE_TPEX.csv: {e}")
    if not stock_codes:
        output_files = os.listdir(OUTPUT_DIR)
        for f in output_files:
            m = re.match(r"revenue_predict_(\\w+)\\.png", f)
            if m:
                stock_codes.append(m.group(1))
        stock_codes = sorted(list(set(stock_codes)))
    if not stock_codes:
        stock_codes = ["2330", "2356", "2357", "2382", "6996"]
    stock_codes = sorted(list(set(stock_codes)))
    print("Target stock codes loaded from CSV:", stock_codes)
    report_markdown = []
    report_markdown.append("# 營收預測與多模型評估決策報告 (10-Model Forecast Report)")
    report_markdown.append(f"產生時間：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} CST\n")
    report_markdown.append("本報告基於 10 種時間序列預測模型，採用一步向前滾動回測（Walk-Forward Validation）進行評估。在歷史驗證區間內，每個月均使用截至該月前所有的已知真實數據進行重新校準與預測，以真實模擬模型在實務上的滾動預測與回測表現。\n")
    for code in stock_codes:
        print(f"\n=======================================================")
        print(f"Processing Stock: {code}")
        res = evaluate_models_for_stock(code)
        if not res:
            continue
        company_name = res["company_name"]
        print(f"Company: {company_name}")
        report_markdown.append(f"## {code} {company_name} 營收預測與回測表現排名表\n")
        report_markdown.append(f"最新已發布營收月份：{res['backtest_months'][-1]}\n")
        def format_mape(val):
            return f"{val:.2f}%" if not np.isnan(val) else "N/A (資料不足)"
        report_markdown.append(f"*   **Yahoo共識回測指標 (Benchmark)**：營收 MAPE: `{format_mape(res['mape_yahoo'])}`\n")
        report_markdown.append(f"*   **FactSet共識回測指標 (Benchmark)**：營收 MAPE: `{format_mape(res['mape_factset'])}`\n\n")
        report_markdown.append("| 排名 | 模型名稱 | MAPE (%)<br>(誤差大小) | MPE (%)<br>(偏差方向) | " + " | ".join([f"{m}預測 (Raw/Corrected)" for m in res["future_months"]]) + " | 狀態與評語 |")
        report_markdown.append("|:---:|:---|:---:|:---:|:---:|:---:|:---:|:---|")
        for rank, item in enumerate(res["model_results"][:5], 1):
            comment = "表現最優" if rank == 1 else ("表現次優" if rank == 2 else "表現穩定")
            pred_strs = []
            for raw_val, corr_val in zip(item["future_preds_raw"], item["future_preds_corrected"]):
                pred_strs.append(f"{raw_val:.1f} / {corr_val:.1f}")
            report_markdown.append(f"| **{rank}** | **{item['model_name']}** | **{item['mape']:.2f}%** | **{item['mpe']:.2f}%** | " + " | ".join(pred_strs) + f" | **{comment}** |")
        report_markdown.append("\n")
        report_markdown.append("### 市場分析師共識預測對比表 (Consensus Benchmarks)：\n")
        report_markdown.append("下列為未來 3 個月自建最優模型預估值與 Yahoo、FactSet 兩大市場共識（True of Consensus）數據之對比：\n")
        report_markdown.append("| 預測月份 | 自建最優預估營收 (億元) | Yahoo共識營收 | FactSet共識營收 |")
        report_markdown.append("|:---|:---:|:---:|:---:|")
        top_model = res["model_results"][0]
        for i, m_fut in enumerate(res["future_months"]):
            best_val = top_model["future_preds_corrected"][i]
            y_val = f"{res['yahoo_future'][i]:.1f}" if not np.isnan(res['yahoo_future'][i]) else "N/A"
            f_val = f"{res['factset_future'][i]:.1f}" if not np.isnan(res['factset_future'][i]) else "N/A"
            report_markdown.append(f"| **{m_fut}** | {best_val:.1f} | {y_val} | {f_val} |")
        report_markdown.append("\n")
        report_markdown.append(f"*   **月度營收預測與回測對照圖**：\n")
        report_markdown.append(f"    ![月度營收預測](file:///{OUTPUT_DIR.replace(os.sep, '/')}/revenue_predict_{code}.png)\n\n")
        report_markdown.append("---\n")
        fig, ax = plt.subplots(figsize=(10, 5), dpi=300)
        hist_months = res["display_months"]
        hist_rev = res["display_revenue"]
        ax.plot(hist_months, hist_rev, label="真實營收 (Actual)", color="black", linewidth=2.5, marker="o")
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c"]
        for idx, item in enumerate(res["model_results"][:3]):
            model_name = item["model_name"]
            full_preds = list(item["val_preds"]) + list(item["future_preds_corrected"])
            full_pred_months = res["backtest_months"] + res["future_months"]
            ax.plot(full_pred_months, full_preds, label=f"{model_name} (MAPE: {item['mape']:.1f}%)", color=colors[idx], linestyle="--", linewidth=1.5)
        warmup_end_idx = len(res["warmup_months"])
        fc_start_idx = len(res["display_months"])
        warmup_nans = [np.nan] * len(res["warmup_months"])
        yahoo_line = warmup_nans + list(res["yahoo_backtest"]) + list(res["yahoo_future"])
        factset_line = warmup_nans + list(res["factset_backtest"]) + list(res["factset_future"])
        all_x_months = hist_months + res["future_months"]
        if not np.all(np.isnan(yahoo_line)):
            ax.plot(all_x_months, yahoo_line, color="#9c27b0", linestyle=":", linewidth=1.2, alpha=0.6, label="Yahoo共識營收 (基準)")
        if not np.all(np.isnan(factset_line)):
            ax.plot(all_x_months, factset_line, color="#3f51b5", linestyle="-.", linewidth=1.2, alpha=0.6, label="FactSet共識營收 (基準)")
        ax.set_title(f"{code} {company_name} 10-Model 營收預測與滾動回測對照圖", fontsize=14, fontweight="bold")
        ax.set_xlabel("月份", fontsize=12)
        ax.set_ylabel("合併營業收入 (億元)", fontsize=12)
        ax.grid(True, linestyle=":", alpha=0.6)
        ticks = np.arange(0, len(all_x_months), 2)
        ax.set_xticks(ticks)
        ax.set_xticklabels([all_x_months[i] for i in ticks], rotation=45)
        plt.tight_layout()
        fig.subplots_adjust(left=0.15, bottom=0.22, right=0.96, top=0.90)
        ax.legend(loc="upper left")
        logo_path = os.path.join(ROOT, "logos", f"{code}.png")
        if os.path.exists(logo_path):
            try:
                img = Image.open(logo_path).convert("RGBA")
                w, h = img.size
                target_width = 48
                zoom_factor = target_width / w
                logo_arr = np.array(img)
                imagebox = OffsetImage(logo_arr, zoom=zoom_factor, interpolation="lanczos", resample=True)
                ab = AnnotationBbox(imagebox, (0.01, 0.01), xycoords='figure fraction', boxcoords="figure fraction", frameon=False, box_alignment=(0.0, 0.0))
                ax.add_artist(ab)
            except Exception as e:
                print(f"   ⚠️ Failed to add logo for {code}: {e}")
        plot_path = os.path.join(OUTPUT_DIR, f"revenue_predict_{code}.png")
        plt.savefig(plot_path)
        plt.close()
        print(f"Generated Plot: {plot_path}")
    report_file_path = os.path.join(OUTPUT_DIR, "revenue_predict_report.md")
    with open(report_file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_markdown))
    print(f"Generated Report: {report_file_path}")

if __name__ == "__main__":
    generate_report_and_plots()

