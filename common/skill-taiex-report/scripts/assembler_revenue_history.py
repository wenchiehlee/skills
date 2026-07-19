import os
import sys
import pandas as pd
import json
import re
from datetime import datetime, timedelta


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

# Add ../llm to sys.path
ROOT = find_repo_root()
WORKSPACE_ROOT = os.path.dirname(ROOT)
LLM_PATH = os.path.join(WORKSPACE_ROOT, "llm")
if LLM_PATH not in sys.path:
    sys.path.append(LLM_PATH)

try:
    from dotenv import load_dotenv
    local_env = os.path.join(ROOT, ".env")
    if os.path.exists(local_env):
        load_dotenv(local_env)
    from llm import LLMClient
except ImportError:
    LLMClient = None

# Data Paths
DATA_DIR = os.path.join(ROOT, "data")
SEG_CSV = os.path.join(DATA_DIR, "ConceptStocks", "raw_conceptstock_company_quarterly_segments.csv")
INC_CSV = os.path.join(DATA_DIR, "ConceptStocks", "raw_conceptstock_company_income.csv")
TW_REV_CSV = os.path.join(DATA_DIR, "Python-Actions.GoodInfo.Analyzer", "raw_revenue.csv")
TW_SEG_WEIGHTS_CSV = os.path.join(DATA_DIR, "company_segment_weights.csv")
OUTPUT_DIR = os.path.join(ROOT, "output", "visuals")

def get_history_data(symbol, target_period=None):
    if symbol.isdigit():
        return get_tw_history_data(symbol, target_period=target_period)
    
    if not os.path.exists(SEG_CSV) or not os.path.exists(INC_CSV):
        return None
    
    df_seg = pd.read_csv(SEG_CSV)
    df_seg = df_seg[df_seg["symbol"] == symbol].copy()
    df_inc = pd.read_csv(INC_CSV)
    df_inc = df_inc[df_inc["symbol"] == symbol].copy()
    
    if df_seg.empty:
        return None

    # Fill missing dates for NVDA Q4 using income CSV
    if symbol == "NVDA":
        for idx, row in df_seg[df_seg["end_date"].isna()].iterrows():
            try:
                match = df_inc[(df_inc["fiscal_year"].astype(int) == int(row["fiscal_year"])) & (df_inc["period"] == "Q4")]
                if not match.empty:
                    df_seg.at[idx, "end_date"] = match.iloc[0]["end_date"]
            except: pass

    df_seg["end_date"] = pd.to_datetime(df_seg["end_date"])
    df_seg = df_seg.dropna(subset=["end_date"])
    
    # Map segments dynamically
    def map_segment(seg):
        seg_lower = str(seg).lower()
        if "data center" in seg_lower: return "Data Center"
        if "gaming" in seg_lower: return "Gaming"
        if "intelligent cloud" in seg_lower: return "Intelligent Cloud"
        if "productivity" in seg_lower: return "Productivity"
        if "personal computing" in seg_lower: return "Personal Computing"
        if "other" in seg_lower: return "Other"
        return seg

    df_seg["mapped_segment"] = df_seg["segment_name"].apply(map_segment)
    df_seg["revenue_m"] = df_seg["revenue"] / 1_000_000
    
    df_grouped = df_seg.groupby(["end_date", "fiscal_year", "quarter", "mapped_segment"])["revenue_m"].sum().reset_index()
    
    # Filter by target_period
    if target_period:
        norm_target = target_period.replace("_", "")
        df_grouped["_per_label"] = df_grouped.apply(lambda r: f"{r['fiscal_year']}Q{r['quarter'][1]}", axis=1)
        df_grouped = df_grouped[df_grouped["_per_label"] <= norm_target]

    pivot_df = df_grouped.pivot(index="end_date", columns="mapped_segment", values="revenue_m").fillna(0)
    
    col_order = pivot_df.mean().sort_values(ascending=False).index.tolist()
    pivot_df = pivot_df[col_order]
    pivot_df = pivot_df.sort_index()
    
    history = []
    for date, row in pivot_df.iterrows():
        meta = df_grouped[df_grouped["end_date"] == date].iloc[0]
        label = f"Q{meta['quarter'][1]} FY{str(meta['fiscal_year'])[-2:]}"
        item = {"date": date.strftime("%Y-%m-%d"), "label": label, "total": round(row.sum(), 1)}
        for col in col_order:
            item[col.lower().replace(" ", "_")] = round(row[col], 1)
        history.append(item)
    
    return {"history": history, "segments": col_order}

def get_tw_history_data(symbol, target_period=None):
    """Calculate historical quarterly segment revenue for TW stocks."""
    if not os.path.exists(TW_REV_CSV) or not os.path.exists(TW_SEG_WEIGHTS_CSV):
        return None
    
    df_rev = pd.read_csv(TW_REV_CSV)
    df_rev = df_rev[df_rev["stock_code"].astype(str) == symbol].copy()
    df_weights = pd.read_csv(TW_SEG_WEIGHTS_CSV)
    df_weights = df_weights[df_weights["stock_code"].astype(str) == symbol].copy()
    
    if df_rev.empty or df_weights.empty:
        return None
    
    # Process monthly revenue into quarterly
    df_rev["_dt"] = pd.to_datetime(df_rev["月別"], errors="coerce")
    df_rev = df_rev.dropna(subset=["_dt"])
    df_rev["year"] = df_rev["_dt"].dt.year
    df_rev["quarter"] = (df_rev["_dt"].dt.month - 1) // 3 + 1
    
    # Handle numeric columns
    rev_col = "合併營業收入_營收_億"
    df_rev[rev_col] = pd.to_numeric(df_rev[rev_col], errors="coerce").fillna(0)
    
    # Group by Quarter
    q_rev = df_rev.groupby(["year", "quarter"])[rev_col].sum().reset_index()
    q_rev["_per_label"] = q_rev.apply(lambda r: f"{r['year']}Q{r['quarter']}", axis=1)
    
    # Filter by target_period
    if target_period:
        norm_target = target_period.replace("_", "")
        q_rev = q_rev[q_rev["_per_label"] <= norm_target]
    
    q_rev = q_rev.sort_values(["year", "quarter"], ascending=False).head(12).sort_values(["year", "quarter"]) # Last 3 years
    
    segments = df_weights["segment_name"].unique().tolist()
    history = []
    for _, row in q_rev.iterrows():
        y, q = int(row["year"]), int(row["quarter"])
        total_rev = row[rev_col]
        item = {
            "date": f"{y}-{q*3:02d}-28", # Approx end
            "label": f"{y} Q{q}",
            "total": round(total_rev, 1)
        }
        for seg in segments:
            weight = df_weights[df_weights["segment_name"] == seg]["weight_pct"].iloc[0]
            val = total_rev * (float(weight) / 100.0)
            item[seg.lower().replace(" ", "_")] = round(val, 1)
        history.append(item)
    
    return {"history": history, "segments": segments}

def build_prompt(symbol, data):
    history_json = json.dumps(data["history"], ensure_ascii=False)
    segments = data["segments"]
    
    palette = ["#2b7b59", "#81b622", "#000000", "#2563EB", "#7C3AED", "#F59E0B"]
    seg_configs = []
    for i, seg in enumerate(segments):
        color = palette[i % len(palette)]
        icon = "Box"
        if "Cloud" in seg or "Server" in seg: icon = "Server"
        elif "Productivity" in seg or "System" in seg: icon = "Office/PC"
        elif "Personal" in seg or "Gaming" in seg: icon = "Game Controller/PC"
        elif "Automotive" in seg: icon = "Car"
        elif "Infrastructure" in seg: icon = "Network"
        seg_configs.append(f"- **{seg}**: Color {color}. Icon: [{icon}]")

    seg_list_str = "\n".join(seg_configs)

    return f"""
SYSTEM: You are a elite financial infographic designer. Your goal is to recreate a clean "App Economy Insights" style revenue breakdown chart.
GOAL: Generate a professional, high-fidelity SVG for {symbol} historical revenue.
CANVAS: width="1200" height="900". Background: #FFFFFF (White).
FONT: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

DATA (in $ million or local unit):
{history_json}

MANDATORY VISUAL ELEMENTS:
1. **Brand Identity (y=0 to 120)**:
   - Top-Left: Large text "{symbol}" in a bold brand-specific font.
   - Beside it: Large text "Revenue Breakdown" in dark gray (#1F2937).
   - Below title: Text "Revenue Trend" in gray.
   - Draw a thin horizontal divider line at y=110.

2. **Visual Key / Legend (Top-Left quadrant of chart area, x=80, y=140)**:
   - Place icons and labels in the top-left area of the chart (below divider).
{seg_list_str}
   - Arrange these horizontally in a single row or vertically in a compact block.
   - DO NOT show hex color codes.

3. **Stacked Bar Chart (Main Area, x=80 to 1150)**:
   - Use the full width of the canvas.
   - X-Axis: Quarters (e.g. 2026 Q1). Bottom labels at y=830, tilted -45 degrees.
   - Vertical Scale: Ensure the tallest bar fits within y=150 to 780.
   - Layers: Stack segments in the order provided (first in list = bottom).
   - **Labeling**:
     * Inside each segment: The numeric value centered. ONLY if segment height > 30px.
     * Top of Bar: The TOTAL revenue (black, extra bold, size 14) positioned above the bar.

4. **Safety Rules**:
   - Use horizontal dashed grid lines (#F3F4F6) for readability.
   - NO watermarks, NO footers.
   - Output raw SVG code ONLY. Start with <svg and end with </svg>.
"""

def _report_period(data):
    data_list = data["history"]
    latest_dt = datetime.strptime(data_list[-1]["date"], "%Y-%m-%d")
    approx_end = latest_dt - timedelta(days=30)
    q = (approx_end.month - 1) // 3 + 1
    return f"{approx_end.year}_Q{q}"

def generate_history_svg(symbol, tag="codex-cli", target_period=None):
    data = get_history_data(symbol, target_period=target_period)
    if not data:
        print(f"No data for {symbol}")
        return

    prompt = build_prompt(symbol, data)
    providers = ["codex"] if tag == "codex-cli" else ["codex", "gemini"]
    
    print(f"Generating [{tag}] revenue history SVG for {symbol}...")
    client = LLMClient(app_name="TAIEX_Revenue_History", providers=providers)
    svg_code = client.generate(prompt, max_tokens=32768)
    
    svg_code = re.sub(r'^```(svg|html|xml)?\n?', '', svg_code)
    svg_code = re.sub(r'\n?```$', '', svg_code)
    svg_code = svg_code.strip()
    
    period = _report_period(data)
    tag_label = tag.replace("-", "_")
    fname = f"{symbol}_{tag_label}_{period}_revenue_history.svg"
    out_path = os.path.join(OUTPUT_DIR, fname)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg_code)
    
    print(f"  Generated by: {client.last_provider}")
    print(f"  Saved: {out_path} ({len(svg_code)/1024:.1f} KB)")

if __name__ == "__main__":
    sid = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    tag = sys.argv[2] if len(sys.argv) > 2 else "codex-cli"
    period_arg = sys.argv[3] if len(sys.argv) > 3 else None
    generate_history_svg(sid, tag, target_period=period_arg)