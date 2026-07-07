try:
    import self_update
except ImportError:
    pass

import os
import sys
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import re


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

def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_revenue_breakdown.py <SYMBOL>")
        return
    
    symbol = sys.argv[1]
root = find_repo_root()
    seg_csv = os.path.join(root, "data", "ConceptStocks", "raw_conceptstock_company_quarterly_segments.csv")
    inc_csv = os.path.join(root, "data", "ConceptStocks", "raw_conceptstock_company_income.csv")
    
    if not os.path.exists(seg_csv) or not os.path.exists(inc_csv):
        print("Missing data files.")
        return
        
    # 1. Load Data
    df_seg = pd.read_csv(seg_csv)
    df_seg = df_seg[df_seg["symbol"] == symbol].copy()
    df_inc = pd.read_csv(inc_csv)
    df_inc = df_inc[df_inc["symbol"] == symbol].copy()
    
    if df_seg.empty:
        print(f"No data found for {symbol}")
        return

    # 2. Data Cleaning & Alignment
    # Map segments to match NVIDIA categories
    def map_segment(seg):
        seg_lower = str(seg).lower()
        if "data center" in seg_lower: return "Data Center"
        if "gaming" in seg_lower: return "Gaming"
        return "Other"
    
    df_seg["mapped_segment"] = df_seg["segment_name"].apply(map_segment)
    
    # Fill missing end_dates for NVDA Q4 using income CSV
    # NVDA Q4 usually ends in late Jan
    if symbol == "NVDA":
        for idx, row in df_seg[df_seg["end_date"].isna()].iterrows():
            fy = int(row["fiscal_year"])
            # In NVDA case, Fiscal Year X Q4 ends in Jan of Year X
            # Find the date in income CSV matching fy and Q4
            match = df_inc[(df_inc["fiscal_year"].astype(int) == fy) & (df_inc["period"] == "Q4")]
            if not match.empty:
                df_seg.at[idx, "end_date"] = match.iloc[0]["end_date"]

    df_seg["end_date"] = pd.to_datetime(df_seg["end_date"])
    df_seg = df_seg.dropna(subset=["end_date"])
    df_seg["revenue_m"] = df_seg["revenue"] / 1_000_000
    
    # 3. Pivot & Sort
    df_grouped = df_seg.groupby(["end_date", "fiscal_year", "quarter", "mapped_segment"])["revenue_m"].sum().reset_index()
    pivot_df = df_grouped.pivot(index="end_date", columns="mapped_segment", values="revenue_m").fillna(0)
    
    # Ensure columns exist and order them
    for col in ["Data Center", "Gaming", "Other"]:
        if col not in pivot_df.columns: pivot_df[col] = 0
    pivot_df = pivot_df[["Data Center", "Gaming", "Other"]]
    pivot_df = pivot_df.sort_index()
    
    # 4. Labeling
    # Map the actual dates back to fiscal labels
    date_to_label = {}
    for _, row in df_grouped.iterrows():
        date_to_label[row["end_date"]] = f"{row['quarter']} FY{str(row['fiscal_year'])[-2:]}"
    
    labels = [date_to_label[d] for d in pivot_df.index]

    # 5. Plotting
    fig, ax = plt.subplots(figsize=(18, 10))
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    
    colors = {"Data Center": "#3a815a", "Gaming": "#78b935", "Other": "#000000"}
    bottom = pd.Series([0.0] * len(pivot_df), index=pivot_df.index)
    
    for col in ["Data Center", "Gaming", "Other"]:
        bars = ax.bar(labels, pivot_df[col], bottom=bottom, label=col, color=colors[col], width=0.7)
        
        # Add labels inside bars
        for i, val in enumerate(pivot_df[col]):
            if val > (pivot_df.sum(axis=1).max() * 0.05): # Only label if big enough
                ax.text(i, bottom.iloc[i] + val/2, f"{int(val):,}", 
                        ha='center', va='center', color='white', fontweight='bold', fontsize=9)
        bottom += pivot_df[col]
        
    # Add total values on top
    for i, total in enumerate(bottom):
        ax.text(i, total + (total * 0.01), f"{int(total):,}", 
                ha='center', va='bottom', color='black', fontweight='bold', fontsize=11)
    
    # Styling
    plt.suptitle(f"{symbol} Revenue Breakdown", fontsize=32, fontweight='bold', color="#1A1A1A", y=0.96)
    ax.set_title("in $ million", loc='center', fontsize=18, color="#666666", pad=20)
    
    ax.yaxis.set_major_formatter(ticker.StrMethodFormatter('{x:,.0f}'))
    ax.tick_params(axis='x', labelsize=11)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.yaxis.grid(True, linestyle='--', alpha=0.3)
    
    ax.legend(loc='upper left', frameon=False, fontsize=12)
    
    plt.tight_layout()
    
    out_dir = os.path.join(root, "output", "visuals")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{symbol}_revenue_breakdown.png")
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {out_path}")

if __name__ == "__main__":
    main()