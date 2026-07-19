import os
import sys
import pandas as pd
import json
import re
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

# Force UTF-8 output to avoid UnicodeEncodeError on Windows cp1252 terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add ../llm to sys.path
ROOT = find_repo_root()
WORKSPACE_ROOT = os.path.dirname(ROOT)
LLM_PATH = os.path.join(WORKSPACE_ROOT, "llm")
if LLM_PATH not in sys.path:
    sys.path.append(LLM_PATH)

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    local_env = os.path.join(ROOT, ".env")
    llm_env = os.path.join(LLM_PATH, ".env")
    if load_dotenv:
        if os.path.exists(llm_env):
            load_dotenv(llm_env, override=False)   # llm/.env 作為基底
        if os.path.exists(local_env):
            load_dotenv(local_env, override=True)  # local .env 覆蓋
    from llm import LLMClient
except ImportError:
    LLMClient = None

# Local Data Paths (Data pushed from upstream repos)
DATA_DIR = os.path.join(ROOT, "data")
RAW_TW_PERF = os.path.join(DATA_DIR, "Python-Actions.GoodInfo.Analyzer", "raw_performance1.csv")
RAW_FACTSET = os.path.join(DATA_DIR, "GoogleSearch.Factset", "raw_factset_detailed_report.csv")
RAW_TW_SEGMENTS = os.path.join(DATA_DIR, "tw_company_segment_weights.csv")
RAW_CAPEX = os.path.join(DATA_DIR, "raw_csp_capex_guidance.csv")
RAW_US_INCOME = os.path.join(DATA_DIR, "ConceptStocks", "raw_conceptstock_company_income.csv")
RAW_US_SEGMENTS = os.path.join(DATA_DIR, "ConceptStocks", "raw_conceptstock_company_quarterly_segments.csv")
RAW_CYCLE_MAP = os.path.join(DATA_DIR, "company_cycle_mapping.csv")
RAW_CYCLE_INDEX = os.path.join(DATA_DIR, "tw_cycle_intensity_index.csv")
RAW_REVENUE_TW = os.path.join(DATA_DIR, "Python-Actions.GoodInfo.Analyzer", "raw_revenue.csv")
RAW_EARNINGS_SUPP = os.path.join(DATA_DIR, "earnings_supplements.csv")
EARNINGS_CSV = os.path.join(DATA_DIR, "raw_event_upcoming_earnings.csv")

OUTPUT_DIR = os.path.join(ROOT, "output", "visuals")

def _quarter_label(end_date) -> str:
    try:
        dt = pd.to_datetime(end_date)
        q = (dt.month - 1) // 3 + 1
        return f"{q}Q{str(dt.year)[2:]}"
    except:
        return str(end_date)[-5:]


US_HIGHLIGHTS = {
    "GOOGL": [
        "營收、EPS 雙雙優於預期",
        "Google Cloud 持續加速，動能強勁",
        "搜尋廣告韌性佳，AI Overview 貢獻提升",
        "Capex 維持高位，AI 基礎設施持續擴張",
    ],
    "AMD": [
        "Data Center GPU 出貨超預期",
        "MI300X 系列持續放量",
        "Client 端回溫，Gaming 相對疲軟",
        "Embedded 部門正在復甦中",
    ],
    "NVDA": [
        "GB300/VR200 出貨看好",
        "整櫃式方案動能強",
        "CSP 資本支出上修",
        "資料中心營收新高",
    ],
}


def get_company_data(symbol, target_period=None):
    is_tw = symbol.isdigit()
    rows = pd.DataFrame()
    data = {
        "symbol": symbol, "company": "",
        "revenue": {"actual": "N/A", "surprise": "N/A", "estimate": "N/A", "yoy": "N/A"},
        "eps": {"actual": "N/A", "surprise": "N/A", "estimate": "N/A", "yoy": "N/A"},
        "segments_yoy": [], "segments_mix": [],
        "margin_trend": [],
        "highlights": [], "capex": "N/A",
        "cycle_context": "N/A",
        "valuation": {"target_price": "N/A", "analyst_count": "N/A", "eps_range": "N/A"},
    }
    
    if is_tw:
        if os.path.exists(RAW_TW_PERF):
            df_perf = pd.read_csv(RAW_TW_PERF)
            if target_period:
                rows = df_perf[(df_perf["stock_code"].astype(str) == symbol) & (df_perf["季度"] == target_period)]
            else:
                rows = df_perf[df_perf["stock_code"].astype(str) == symbol].sort_values("季度", ascending=False)
            
            def to_float(val):
                try: return float(str(val).replace(',', '').replace('-', '0'))
                except: return 0.0

            valid_rows = rows[rows['獲利金額_億_營業_收入'].apply(lambda x: str(x).replace('.','',1).replace('-','').isdigit())]
            
            if not valid_rows.empty:
                latest = valid_rows.iloc[0]
                actual_period = latest["季度"] # e.g. 2026Q1
                data["company"] = latest["company_name"]
                data["revenue"]["actual"] = f"{to_float(latest['獲利金額_億_營業_收入']):.1f} 億"
                data["eps"]["actual"] = f"{to_float(latest['eps_元_稅後_eps']):.2f}"
                
                all_sym = df_perf[df_perf["stock_code"].astype(str) == symbol].sort_values("季度", ascending=False)
                trend_rows = all_sym[all_sym["季度"] <= actual_period].head(5).sort_values("季度")

                for _, r in trend_rows.iterrows():
                    # Normalize TW period 2026Q1 -> 1Q26
                    q_str = str(r["季度"])
                    m = re.search(r"(\d{4})Q([1-4])", q_str)
                    display_period = f"{m.group(2)}Q{m.group(1)[2:]}" if m else q_str[-5:]
                    
                    data["margin_trend"].append({
                        "period": display_period, 
                        "overall": to_float(r.get("獲利率_pct_營業_利益", 0)),
                        "segment": to_float(r.get("獲利率_pct_營業_毛利", 0))
                    })
                
                if os.path.exists(RAW_REVENUE_TW):
                    df_rev = pd.read_csv(RAW_REVENUE_TW)
                    df_rev['合併營業收入_營收_億'] = pd.to_numeric(df_rev['合併營業收入_營收_億'], errors='coerce')
                    
                    m = re.match(r"(\d{4})Q([1-4])", actual_period)
                    if m:
                        year = int(m.group(1))
                        q = int(m.group(2))
                        months = [f"{year}/{m:02}" for m in range(q*3-2, q*3+1)]
                        curr_rev = df_rev[(df_rev['stock_code'].astype(str)==symbol) & (df_rev['月別'].isin(months))]['合併營業收入_營收_億'].sum()
                        
                        if curr_rev > 0:
                            data["revenue"]["actual"] = f"{curr_rev:.1f} 億"
                            prev_year = year - 1
                            prev_months = [f"{prev_year}/{m:02}" for m in range(q*3-2, q*3+1)]
                            prev_rev = df_rev[(df_rev['stock_code'].astype(str)==symbol) & (df_rev['月別'].isin(prev_months))]['合併營業收入_營收_億'].sum()
                            if prev_rev > 0:
                                data["revenue"]["yoy"] = f"{(curr_rev/prev_rev-1)*100:+.1f}%"

        if os.path.exists(RAW_FACTSET):
            df_fs = pd.read_csv(RAW_FACTSET)
            df_sym = df_fs[df_fs["代號"].astype(str) == symbol].copy()
            if not df_sym.empty:
                if os.path.exists(EARNINGS_CSV):
                    df_ev = pd.read_csv(EARNINGS_CSV, encoding="utf-8-sig")
                    ev = df_ev[
                        (df_ev["類別"] == "財報公告") &
                        (df_ev["事件名稱"].str.contains(symbol))
                    ].sort_values("開始日期", ascending=False)
                    if not ev.empty:
                        earnings_dt = pd.to_datetime(ev.iloc[0]["開始日期"], errors="coerce")
                        df_sym["_search_dt"] = pd.to_datetime(df_sym["搜尋日期"], errors="coerce")
                        pre = df_sym[df_sym["_search_dt"] < earnings_dt]
                        df_sym = pre if not pre.empty else df_sym
                r = df_sym.sort_values("搜尋日期", ascending=False).iloc[0]

                est_rev_year = r.get("2026營收平均值")
                if pd.notna(est_rev_year):
                    est_q = float(est_rev_year) * 1000 / 4 / 100000000
                    data["revenue"]["estimate"] = f"{est_q:.1f} 億"
                    try:
                        act_val = float(data["revenue"]["actual"].split()[0].replace(',', ''))
                        surp = (act_val / est_q - 1) * 100
                        data["revenue"]["surprise"] = f"{surp:+.1f}%"
                    except: pass

                est_eps_year = pd.to_numeric(r.get("2026EPS平均值"), errors="coerce")
                if pd.notna(est_eps_year):
                    est_eps_q = float(est_eps_year) / 4
                    data["eps"]["estimate"] = f"{est_eps_q:.2f}"
                    try:
                        act_eps = float(str(data["eps"]["actual"]).split()[0])
                        data["eps"]["surprise"] = f"{(act_eps / est_eps_q - 1) * 100:+.1f}%"
                    except: pass

                target = pd.to_numeric(r.get("目標價"), errors="coerce")
                if pd.notna(target):
                    data["valuation"]["target_price"] = f"{float(target):,.0f}"
                analysts = r.get("分析師數量", "")
                if analysts:
                    data["valuation"]["analyst_count"] = str(analysts)
                eps_hi = pd.to_numeric(r.get("2026EPS最高值"), errors="coerce")
                eps_lo = pd.to_numeric(r.get("2026EPS最低值"), errors="coerce")
                if pd.notna(eps_hi) and pd.notna(eps_lo):
                    data["valuation"]["eps_range"] = f"{float(eps_lo):.1f} ~ {float(eps_hi):.1f}"
        
        if os.path.exists(RAW_CYCLE_MAP) and os.path.exists(RAW_CYCLE_INDEX):
            df_map = pd.read_csv(RAW_CYCLE_MAP)
            match = df_map[df_map["stock_code"].astype(str) == symbol]
            if not match.empty:
                cycle = match.iloc[0]["canonical_cycle"]
                sub_cycle = match.iloc[0].get("sub_cycle", "")
                df_idx = pd.read_csv(RAW_CYCLE_INDEX)
                c_data = df_idx[df_idx["canonical_cycle"] == cycle].sort_values("month", ascending=False)
                if c_data.empty and sub_cycle:
                    c_data = df_idx[df_idx["canonical_cycle"] == sub_cycle].sort_values("month", ascending=False)
                    cycle = sub_cycle
                if not c_data.empty:
                    cycle_yoy = float(c_data.iloc[0].get("yoy_pct", 0))
                    data["cycle_context"] = f"{cycle} (Cycle YoY: {cycle_yoy:+.1f}%)"

        if symbol == "2330":
            data["highlights"] = ["先進製程需求強勁", "CoWoS 產能擴張", "HPC 帶動營收", "Capex 維持高檔"]
            data["capex"] = "320~340 億美元"

        if os.path.exists(RAW_EARNINGS_SUPP):
            df_supp = pd.read_csv(RAW_EARNINGS_SUPP)
            supp = df_supp[df_supp["symbol"].astype(str) == symbol]
            if not supp.empty:
                s = supp.sort_values("fiscal_year", ascending=False).iloc[0]
                eps_act  = pd.to_numeric(s.get("non_gaap_eps"),        errors="coerce")
                eps_est  = pd.to_numeric(s.get("eps_estimate"),        errors="coerce")
                eps_surp = pd.to_numeric(s.get("eps_surprise_pct"),    errors="coerce")
                if pd.notna(eps_act):
                    data["eps"]["actual"] = f"{float(eps_act):.2f}"
                if pd.notna(eps_est):
                    data["eps"]["estimate"] = f"{float(eps_est):.2f}"
                if pd.notna(eps_surp):
                    data["eps"]["surprise"] = f"{float(eps_surp):+.1f}%"

    else:
        if os.path.exists(RAW_US_INCOME):
            df_inc = pd.read_csv(RAW_US_INCOME)
            q_rows = df_inc[
                (df_inc["symbol"] == symbol) &
                (df_inc["period"].str.match(r"Q[1-4]", na=False))
            ].copy()
            q_rows["end_date_dt"] = pd.to_datetime(q_rows["end_date"], errors="coerce")
            q_rows["eps_num"] = pd.to_numeric(q_rows["eps"], errors="coerce")
            q_rows["eps_ok"] = q_rows["eps_num"].notna().astype(int)
            q_rows = q_rows.sort_values(
                ["fiscal_year", "period", "eps_ok", "end_date_dt"],
                ascending=[True, True, False, False]
            ).drop_duplicates(subset=["fiscal_year", "period"], keep="first")
            q_rows = q_rows.sort_values("end_date_dt", ascending=False)
            rows = q_rows

            if not rows.empty:
                latest = rows.iloc[0]
                data["company"] = latest["company_name"]
                data["revenue"]["actual"] = f"{float(latest['total_revenue'])/1e9:.1f} B"
                yoy_pct = latest.get("revenue_yoy_pct")
                if pd.notna(yoy_pct):
                    data["revenue"]["yoy"] = f"{float(yoy_pct)*100:+.1f}%"

                q_rows["non_gaap_eps_num"] = pd.to_numeric(q_rows.get("non_gaap_eps", pd.Series(dtype=float)), errors="coerce")
                rows_nongaap = q_rows[q_rows["non_gaap_eps_num"].notna()].sort_values("end_date_dt", ascending=False)
                rows_eps = rows[rows["eps_num"].notna()]
                if not rows_nongaap.empty:
                    eps_row = rows_nongaap.iloc[0]
                    data["eps"]["actual"] = f"{float(eps_row['non_gaap_eps_num']):.2f} (Non-GAAP)"
                    est = pd.to_numeric(eps_row.get("eps_estimate"), errors="coerce")
                    if pd.notna(est):
                        data["eps"]["estimate"] = f"{float(est):.2f}"
                    surp = pd.to_numeric(eps_row.get("eps_surprise_pct"), errors="coerce")
                    if pd.notna(surp):
                        data["eps"]["surprise"] = f"{float(surp):+.1f}%"
                elif not rows_eps.empty:
                    eps_row = rows_eps.iloc[0]
                    data["eps"]["actual"] = f"{float(eps_row['eps_num']):.2f}"
                if not rows_eps.empty:
                    eps_row = rows_eps.iloc[0]
                    try:
                        same_q_prev = rows_eps[
                            rows_eps["end_date_dt"].dt.year == (eps_row["end_date_dt"].year - 1)
                        ]
                        if not same_q_prev.empty:
                            prev_eps = float(same_q_prev.iloc[0]["eps_num"])
                            curr_eps = float(eps_row["eps_num"])
                            if prev_eps != 0:
                                data["eps"]["yoy"] = f"{(curr_eps / prev_eps - 1) * 100:+.1f}%"
                    except:
                        pass

                trend_rows = rows.head(5).sort_values("end_date_dt")
                for _, r in trend_rows.iterrows():
                    m = float(r.get("operating_margin") or 0)
                    if m != 0 and abs(m) < 1:
                        m *= 100
                    data["margin_trend"].append({
                        "period": _quarter_label(r["end_date_dt"]),
                        "overall": round(m, 1),
                        "segment": round(m, 1),
                    })

        if os.path.exists(RAW_CAPEX):
            df_cx = pd.read_csv(RAW_CAPEX)
            cx_row = df_cx[df_cx["symbol"] == symbol]
            if not cx_row.empty:
                data["capex"] = f"{cx_row.iloc[0]['capex_low_usd_bn']}B - {cx_row.iloc[0]['capex_high_usd_bn']}B"

        data["highlights"] = US_HIGHLIGHTS.get(symbol, [])

        if os.path.exists(RAW_EARNINGS_SUPP):
            df_supp = pd.read_csv(RAW_EARNINGS_SUPP)
            if not rows.empty:
                latest_fy = int(rows.iloc[0]["fiscal_year"])
                latest_period = rows.iloc[0]["period"]
                supp = df_supp[
                    (df_supp["symbol"] == symbol) &
                    (df_supp["fiscal_year"].astype(int) == latest_fy) &
                    (df_supp["period"] == latest_period)
                ]
                if not supp.empty:
                    s = supp.iloc[0]
                    rev_est  = pd.to_numeric(s.get("revenue_estimate"),    errors="coerce")
                    rev_surp = pd.to_numeric(s.get("revenue_surprise_pct"),errors="coerce")
                    ng_eps   = pd.to_numeric(s.get("non_gaap_eps"),        errors="coerce")
                    eps_est  = pd.to_numeric(s.get("eps_estimate"),        errors="coerce")
                    eps_surp = pd.to_numeric(s.get("eps_surprise_pct"),    errors="coerce")
                    if pd.notna(rev_est):
                        data["revenue"]["estimate"] = f"{float(rev_est)/1e9:.2f} B"
                    if pd.notna(rev_surp):
                        data["revenue"]["surprise"] = f"{float(rev_surp):+.1f}%"
                    if pd.notna(ng_eps) and data["eps"]["actual"] == "N/A":
                        data["eps"]["actual"] = f"{float(ng_eps):.2f}"
                    if pd.notna(eps_est):
                        data["eps"]["estimate"] = f"{float(eps_est):.2f}"
                    if pd.notna(eps_surp):
                        data["eps"]["surprise"] = f"{float(eps_surp):+.1f}%"

    if is_tw and os.path.exists(RAW_TW_SEGMENTS):
        df_w = pd.read_csv(RAW_TW_SEGMENTS)
        segs = df_w[df_w["stock_code"].astype(str) == symbol]

        curr_total = prev_total = 0.0
        if os.path.exists(RAW_REVENUE_TW):
            df_rev = pd.read_csv(RAW_REVENUE_TW)
            df_rev["合併營業收入_營收_億"] = pd.to_numeric(df_rev["合併營業收入_營收_億"], errors="coerce")
            df_sym = df_rev[df_rev["stock_code"].astype(str) == symbol]
            
            # Determine period for total revenue calculation
            if not rows.empty:
                actual_period = rows.iloc[0]["季度"]
                m = re.match(r"(\d{4})Q([1-4])", actual_period)
                if m:
                    year, q = int(m.group(1)), int(m.group(2))
                    months = [f"{year}/{m:02}" for m in range(q*3-2, q*3+1)]
                    curr_total = df_sym[df_sym["月別"].isin(months)]["合併營業收入_營收_億"].sum()
                    prev_months = [f"{year-1}/{m:02}" for m in range(q*3-2, q*3+1)]
                    prev_total = df_sym[df_sym["月別"].isin(prev_months)]["合併營業收入_營收_億"].sum()

        for _, s in segs.iterrows():
            data["segments_mix"].append({"name": s["segment_name"], "pct": f"{s['weight_pct']}%"})
            try:
                prev_w = float(s.get("prev_weight_pct") or 0)
                curr_w = float(s["weight_pct"])
                if prev_w > 0 and curr_total > 0 and prev_total > 0:
                    yoy = (curr_total * curr_w / 100) / (prev_total * prev_w / 100) - 1
                    data["segments_yoy"].append({"name": s["segment_name"], "yoy": f"{yoy*100:+.1f}%"})
                else:
                    data["segments_yoy"].append({"name": s["segment_name"], "yoy": "N/A"})
            except Exception:
                data["segments_yoy"].append({"name": s["segment_name"], "yoy": "N/A"})
    elif not is_tw and os.path.exists(RAW_US_SEGMENTS):
        df_s = pd.read_csv(RAW_US_SEGMENTS)
        sym_segs = df_s[df_s["symbol"] == symbol].copy()
        if not sym_segs.empty:
            sym_segs["end_date_dt"] = pd.to_datetime(sym_segs["end_date"], errors="coerce")
            latest_seg_date = sym_segs["end_date_dt"].max()
            segs = sym_segs[sym_segs["end_date_dt"] == latest_seg_date]
            total = float(segs["revenue"].sum())

            prev_date = latest_seg_date - pd.DateOffset(years=1)
            prev_segs_df = sym_segs[
                (sym_segs["end_date_dt"] >= prev_date - pd.Timedelta(days=45)) &
                (sym_segs["end_date_dt"] <= prev_date + pd.Timedelta(days=45))
            ]
            prev_rev_map = {}
            prev_total = 0.0
            if not prev_segs_df.empty:
                prev_date_max = prev_segs_df["end_date_dt"].max()
                prev_segs_latest = prev_segs_df[prev_segs_df["end_date_dt"] == prev_date_max]
                prev_total = float(prev_segs_latest["revenue"].sum())
                prev_rev_map = {r["segment_name"]: float(r["revenue"]) for _, r in prev_segs_latest.iterrows()}

            income_dt = rows.iloc[0]["end_date_dt"] if not rows.empty else pd.NaT
            if pd.isna(income_dt) or latest_seg_date > income_dt:
                data["revenue"]["actual"] = f"{total / 1e9:.1f} B"
                if prev_total > 0:
                    data["revenue"]["yoy"] = f"{(total / prev_total - 1) * 100:+.1f}%"
            elif data["revenue"]["yoy"] == "N/A" and prev_total > 0:
                data["revenue"]["yoy"] = f"{(total / prev_total - 1) * 100:+.1f}%"

            for _, s in segs.iterrows():
                pct = (float(s["revenue"]) / total * 100) if total > 0 else 0
                seg_name = s["segment_name"]
                curr_rev = float(s["revenue"])
                prev_rev = prev_rev_map.get(seg_name)
                yoy = f"{(curr_rev / prev_rev - 1) * 100:+.1f}%" if prev_rev else "N/A"
                data["segments_mix"].append({"name": seg_name, "pct": f"{pct:.1f}%"})
                data["segments_yoy"].append({"name": seg_name, "yoy": yoy})

    return data

COMPARE_CONFIGS = [
    {"tag": "codex-cli",  "providers": ["codex"],          "model": None},
    {"tag": "gemini-cli", "providers": ["gemini"],          "model": "gemini-2.5-flash"},
    {"tag": "gemma4",     "providers": ["mlx"],            "model": "mlx-gemma4"},
    {"tag": "qwen3",      "providers": ["mlx"],            "model": "mlx-qwen3"},
]

TEMPLATE_SVG_PATH = os.path.join(OUTPUT_DIR, "GOOGL_codex_cli_2026_Q1_finguider_report.svg")

def _load_template() -> str:
    if os.path.exists(TEMPLATE_SVG_PATH):
        with open(TEMPLATE_SVG_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def _build_prompt(symbol, data, period: str = ""):
    template_svg = _load_template()
    template_section = f"""
TEMPLATE SVG (已通過品質審核，版面零重疊):
以下是 GOOGL 的完整 SVG，作為版面模板。請嚴格沿用其：
- 所有 y 座標分區（頁首/指標卡/中排/下排/底部）
- 環形圖的半徑、stroke-width、圓心位置
- 文字與圖表的間距規則
只需將 GOOGL 的數據、公司名、股票代號、色彩替換為 {symbol} 的對應資料。

{template_svg}
""" if template_svg else ""

    return f"""
SYSTEM: You are a professional financial infographic designer.
GOAL: Generate a financial summary dashboard SVG for {data['company']} ({symbol}), modelled exactly on the template below.
{template_section}
MANDATORY RULES:
1. **Canvas**: exactly width="1200" height="1200". White (#FFFFFF) background. NO OVERLAPPING elements.
2. **Layout**: reuse the template's section y-ranges and chart geometry exactly — do NOT redesign.
3. **Indicator Cards (y=130-300)**: 
   - Left Card (Actual): x=90, title font-size=44.
   - Right Card (Actual): x=650, title font-size=44.
   - Estimates: x=350 (left card), x=910 (right card), font-size=25.
   - **CRITICAL**: If the "Actual" value string (e.g. "營收 12345.6 億") is long (> 10 chars), you MUST reduce its font-size to 32 to avoid overlapping with the estimate column.
4. **Language**: All labels in Traditional Chinese (繁體中文).
5. **Color**: positive values → #2563EB, negative → #DC2626, card bg → #F3F4F6.
6. **Completeness**: all 5 sections must be present. Minimum file size ~8KB.

REPORT HEADER (頁首，必須完全照用):
- 左側大型股票代號: {symbol}
- 右側標題: 必須是「{period.replace("_", " ")} 財報總結」(e.g. "2026 Q1 財報總結") — 不得改動

DATA for {symbol}:
- 指標: 營收 {json.dumps(data['revenue'], ensure_ascii=False)} | EPS {json.dumps(data['eps'], ensure_ascii=False)}
- 估值: 目標價 {data['valuation']['target_price']} | 分析師數量 {data['valuation']['analyst_count']} | 2026 EPS區間 {data['valuation']['eps_range']}
- 業務年增率: {json.dumps(data['segments_yoy'], ensure_ascii=False)}
- 營收組成: {json.dumps(data['segments_mix'], ensure_ascii=False)}
- 利潤率趨勢: {json.dumps(data['margin_trend'])}
- 資本支出: {data['capex']} | 重點摘要: {json.dumps(data['highlights'], ensure_ascii=False)}
- 產業循環: {data['cycle_context']}

OUTPUT: Raw SVG code ONLY. Start with <svg and end with </svg>. No markdown fences.
"""

# Data Source Mapping for Diagnostics
DATA_SOURCE_MAP = {
    "TW": {
        "performance": {"file": "data/Python-Actions.GoodInfo.Analyzer/raw_performance1.csv", "repo": "wenchiehlee-investment/Python-Actions.GoodInfo.Analyzer"},
        "revenue": {"file": "data/Python-Actions.GoodInfo.Analyzer/raw_revenue.csv", "repo": "wenchiehlee-investment/Python-Actions.GoodInfo.Analyzer"},
        "factset": {"file": "data/GoogleSearch.Factset/raw_factset_detailed_report.csv", "repo": "wenchiehlee-investment/GoogleSearch.Factset"},
        "segments": {"file": "data/tw_company_segment_weights.csv", "repo": "wenchiehlee-investment/Python-Actions.GoodInfo.Analyzer"},
    },
    "US": {
        "income": {"file": "data/ConceptStocks/raw_conceptstock_company_income.csv", "repo": "wenchiehlee-investment/ConceptStocks"},
        "segments": {"file": "data/ConceptStocks/raw_conceptstock_company_quarterly_segments.csv", "repo": "wenchiehlee-investment/ConceptStocks"},
    }
}

def _is_data_ready(symbol: str, data: dict, target_period: str = None) -> tuple:
    def _blank(v):
        return not v or str(v).strip().lower() in ("n/a", "nan", "none", "", "0", "0.0")

    is_tw = symbol.isdigit()
    m_info = DATA_SOURCE_MAP["TW"] if is_tw else DATA_SOURCE_MAP["US"]
    gaps = [] # List of (message, repo) tuples

    # 1. Check basic revenue/EPS
    if _blank(data.get("revenue", {}).get("actual")):
        src = m_info["performance"] if is_tw else m_info["income"]
        gaps.append((f"Revenue missing (Expected in {src['file']})", src['repo']))
    
    if _blank(data.get("eps", {}).get("actual")):
        src = m_info["performance"] if is_tw else m_info["income"]
        gaps.append((f"EPS missing (Expected in {src['file']})", src['repo']))

    # 2. Check margin trend (must include the target period)
    mt = data.get("margin_trend", [])
    if not mt:
        src = m_info["performance"] if is_tw else m_info["income"]
        gaps.append((f"Margin trend empty (Expected in {src['file']})", src['repo']))
    elif target_period:
        # Normalize target_period to XQX format (e.g. 1Q26) to match margin_trend periods
        m = re.search(r"(\d{4})[_\s]*Q([1-4])", target_period)
        if m:
            short_tp = f"{m.group(2)}Q{m.group(1)[2:]}"
        else:
            short_tp = target_period[2:] if len(target_period) == 6 else target_period[-4:]
        
        found = False
        for entry in mt:
            if entry.get("period") == short_tp:
                if not _blank(entry.get("overall")) or not _blank(entry.get("segment")):
                    found = True; break
        if not found:
            src = m_info["performance"] if is_tw else m_info["income"]
            gaps.append((f"Target period {target_period} margin data missing (Expected in {src['file']})", src['repo']))

    # 3. Check segments
    if not is_tw and not data.get("segments_mix"):
        src = m_info["segments"]
        gaps.append((f"US segment data missing (Expected in {src['file']})", src['repo']))
    
    if gaps:
        return False, gaps
    return True, []


def _submit_data_gap_issue(symbol, period, gaps):
    """Submit a data gap issue to GitHub using gh CLI."""
    import subprocess
    # gaps is a list of (msg, repo)
    if not gaps: return
    
    # Group gaps by repo
    repo_gaps = {}
    for msg, repo in gaps:
        if repo not in repo_gaps: repo_gaps[repo] = []
        repo_gaps[repo].append(msg)
    
    for repo, msgs in repo_gaps.items():
        title = f"[Data Lag] {symbol} {period} Financial Data Missing"
        # Escaping for shell compatibility
        body_content = f"### 數據缺失診斷回報 (Automated Data Gap Report)\\n\\n"
        body_content += f"**標的**: {symbol}\\n**期別**: {period}\\n\\n"
        body_content += "**偵測到的缺口 (Detected Gaps)**:\\n"
        for m in msgs:
            body_content += f"- {m}\\n"
        body_content += f"\\n**來源檔案**: 已由 TAIEX.TW 自動偵測到數據滯後。\\n"
        body_content += "\\n**預期行動**: 請確認上游抓取任務是否正常，並重新同步數據。"
        
        try:
            # Check if issue already exists in the TARGET repo
            check = subprocess.run(["gh", "issue", "list", "--repo", repo, "--search", title, "--json", "number"], 
                                   capture_output=True, text=True)
            if check.returncode == 0 and "[]" not in check.stdout:
                print(f"  Issue already exists for {symbol} {period} in {repo}, skipping submission.")
                continue

            subprocess.run(["gh", "issue", "create", "--repo", repo, "--title", title, "--body", body_content, "--label", "Data Lag"], check=True)
            print(f"  Successfully submitted data gap issue for {symbol} {period} to {repo}.")
        except Exception as e:
            print(f"  Failed to submit issue to {repo}: {e}")


def _fix_legend_overflow(svg: str) -> str:
    def _replace(m):
        before_size = m.group(1); size = int(m.group(2)); after_size = m.group(3); content = m.group(4); close_tag = m.group(5)
        available = 155
        if size * 0.62 * len(content) > available:
            for new_size in range(size - 1, 9, -1):
                if new_size * 0.62 * len(content) <= available:
                    size = new_size; break
        return f'{before_size}{size}{after_size}{content}{close_tag}'
    pattern = re.compile(r'(<text\s[^>]*x="9[2-9]\d"[^>]*font-size=")(\d+)("(?:[^>]*)>)([^<]{10,})(</text>)', re.DOTALL)
    return pattern.sub(_replace, svg)


def _report_period(symbol: str, data: dict, target_period: str = None) -> str:
    if target_period:
        m = re.match(r"(\d{4})Q([1-4])", target_period)
        if m: return f"{m.group(1)}_Q{m.group(2)}"
        return target_period

    is_tw = symbol.isdigit()
    seg_path = RAW_TW_PERF if is_tw else RAW_US_SEGMENTS
    if os.path.exists(seg_path):
        df_s = pd.read_csv(seg_path)
        col = "stock_code" if is_tw else "symbol"
        sym_rows = df_s[df_s[col].astype(str) == symbol].copy()
        date_col = "季度" if is_tw else "end_date"
        if not sym_rows.empty:
            sym_rows["_dt"] = pd.to_datetime(sym_rows[date_col], errors="coerce")
            latest = sym_rows["_dt"].max()
            if pd.notna(latest):
                approx = latest - pd.Timedelta(days=30)
                return f"{approx.year}_Q{(approx.month - 1) // 3 + 1}"
    return f"{datetime.now().year}_Q{(datetime.now().month - 1) // 3 + 1}"


def _fix_indicator_overlap(svg: str) -> str:
    def _replace(m):
        prefix = m.group(1); x_coord = int(m.group(2)); attrs = m.group(3); size = int(m.group(4)); suffix = m.group(5); content = m.group(6); close = m.group(7)
        width = size * 0.65 * len(content)
        if x_coord + width > (360 if x_coord < 600 else 920):
            for new_size in range(size - 2, 20, -2):
                if x_coord + (new_size * 0.65 * len(content)) <= (360 if x_coord < 600 else 920):
                    size = new_size; break
            else: size = 24
        return f'{prefix}{x_coord}{attrs}{size}{suffix}{content}{close}'
    pattern = re.compile(r'(<text\s[^>]*x=")(90|650)("[^>]*font-size=")(\d+)("(?![^>]*text-anchor)[^>]*>)([^<]+)(</text>)', re.DOTALL)
    return pattern.sub(_replace, svg)


def generate_finguider_svg(symbol, data, providers=None, model=None, tag=None, target_period=None, auto_report=True):
    if not LLMClient: return
    
    # 1. Determine the intended period
    period = _report_period(symbol, data, target_period=target_period)
    norm_period = period.replace("_", "") # e.g. 2026Q1
    
    # 2. Enhanced check: does data match the intended period?
    ready, gaps = _is_data_ready(symbol, data, norm_period)
    if not ready:
        msgs = [g[0] for g in gaps]
        print(f"  [{symbol}] Skipped: {', '.join(msgs)}")
        if auto_report:
            _submit_data_gap_issue(symbol, norm_period, gaps)
        return

    prompt = _build_prompt(symbol, data, period)
    providers = providers or ["codex", "gemini"]
    label = tag or providers[0]
    print(f"Generating [{label}] finguider dashboard for {symbol} ({period})...")
    client = LLMClient(app_name="TAIEX_Finguider_Pro", providers=providers, model=model)
    svg_code = client.generate(prompt, max_tokens=32768)
    
    svg_code = re.sub(r'^```(svg|html|xml)?\n?', '', svg_code)
    svg_code = re.sub(r'\n?```$', '', svg_code)
    svg_code = svg_code.strip()
    svg_code = _fix_legend_overflow(svg_code)
    svg_code = _fix_indicator_overlap(svg_code)
    tag_label = label.replace("-", "_")
    fname = f"{symbol}_{tag_label}_{period}_finguider_report.svg" if tag else f"{symbol}_{period}_finguider_report.svg"
    output_path = os.path.join(OUTPUT_DIR, fname)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(svg_code)
    print(f"  Saved: {output_path} ({len(svg_code.encode())/1024:.1f} KB)")

def compare_generate(symbol):
    stock_data = get_company_data(symbol)
    for cfg in COMPARE_CONFIGS:
        try:
            generate_finguider_svg(symbol, stock_data, providers=cfg["providers"], model=cfg["model"], tag=cfg["tag"])
        except Exception as e: print(f"  [{cfg['tag']}] Error: {e}")

def batch_generate():
    summary_path = os.path.join(DATA_DIR, "raw_investment_summary.csv")
    if not os.path.exists(summary_path): return
    df = pd.read_csv(summary_path)
    for _, row in df.iterrows():
        sid = str(row["stock_code"])
        if sid == "nan" or not sid: continue
        try:
            stock_data = get_company_data(sid)
            generate_finguider_svg(sid, stock_data)
        except Exception as e: print(f"Error processing {sid}: {e}")

if __name__ == "__main__":
    sid = sys.argv[1] if len(sys.argv) > 1 else "GOOGL"
    tag_arg = sys.argv[2] if len(sys.argv) > 2 else None
    period_arg = sys.argv[3] if len(sys.argv) > 3 else None

    if sid == "batch":
        batch_generate()
    elif sid == "compare":
        target = sys.argv[2] if len(sys.argv) > 2 else "GOOGL"
        compare_generate(target)
    else:
        stock_data = get_company_data(sid, target_period=period_arg)
        if tag_arg:
            cfg = next((c for c in COMPARE_CONFIGS if c["tag"] == tag_arg), None)
            if cfg:
                generate_finguider_svg(sid, stock_data,
                                       providers=cfg["providers"],
                                       model=cfg["model"],
                                       tag=cfg["tag"],
                                       target_period=period_arg)
            else:
                print(f"Unknown tag '{tag_arg}'. Available: {[c['tag'] for c in COMPARE_CONFIGS]}")
        else:
            generate_finguider_svg(sid, stock_data, target_period=period_arg)