import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from typing import Dict, Optional
from pathlib import Path

# Set style for professional presentation
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
plt.rcParams['font.family'] = 'Microsoft JhengHei'
plt.rcParams['axes.unicode_minus'] = False

class CostVisualizer:
    """
    CostVisualizer generates visual plots and text-based ASCII representations
    for the estimated market cost distribution.
    """
    @staticmethod
    def draw_ascii_profile(distribution: Dict[float, float], width: int = 40) -> str:
        """
        Generates an ASCII horizontal histogram of the cost distribution for terminal output.
        """
        if not distribution:
            return "No cost distribution data available."

        sorted_bins = sorted(distribution.items(), key=lambda x: x[0])
        max_weight = max(distribution.values()) if distribution.values() else 1.0
        
        lines = ["=== Market Cost Distribution Profile (ASCII) ==="]
        for price, weight in sorted_bins:
            bar_len = int((weight / max_weight) * width)
            bar = "█" * bar_len + "░" * (width - bar_len)
            lines.append(f"{price:7.2f} NTD: |{bar}| {weight*100:5.2f}%")
        
        return "\n".join(lines)

    @staticmethod
    def plot_cost_chart(
        df_history: pd.DataFrame, 
        final_dist: Dict[float, float], 
        metrics: Dict,
        stock_code: str,
        company_name: str,
        save_path: Path,
        shares_outstanding: Optional[float] = None,
        trust_level: Optional[str] = None,
        data_as_of: Optional[str] = None
    ):
        """
        Plots a professional dual-panel chart:
        - Left Panel: Historical Close Price line chart with POC & Avg Cost levels.
        - Right Panel: Horizontal cost distribution histogram sharing the Y-axis.
        """
        # Close all existing figures
        plt.close('all')

        fig, (ax_price, ax_cost) = plt.subplots(
            1, 2, 
            figsize=(12, 6), 
            gridspec_kw={'width_ratios': [3, 1]}, 
            sharey=True
        )

        fig.suptitle(f"{stock_code} {company_name} - 市場籌碼成本分佈圖 (Market Cost Distribution)", fontsize=14, fontweight='bold', y=0.96)

        # ---- Left Panel: Price Chart ----
        dates = df_history["Date"]
        prices = df_history["Close"]
        
        ax_price.plot(dates, prices, label="收盤價", color="#1f77b4", linewidth=1.5)
        
        # Draw Avg Cost & POC lines
        avg_cost = metrics["Average_Cost"]
        poc = metrics["POC"]
        curr_price = df_history.iloc[-1]["Close"]
        
        ax_price.axhline(avg_cost, color="orange", linestyle="--", linewidth=1.2, label=f"平均持股成本: {avg_cost:.2f}")
        ax_price.axhline(poc, color="red", linestyle=":", linewidth=1.5, label=f"Point of Control (POC): {poc:.2f}")
        
        ax_price.set_title("歷史股價與成本參考線", fontsize=11, fontweight='bold')
        ax_price.set_xlabel("日期", fontsize=10)
        ax_price.set_ylabel("價格 (NTD)", fontsize=10)
        ax_price.legend(loc="upper left")
        ax_price.tick_params(axis='x', rotation=15)

        # ---- Right Panel: Cost Profile ----
        sorted_bins = sorted(final_dist.items(), key=lambda x: x[0])
        dist_prices = np.array([item[0] for item in sorted_bins])
        dist_weights = np.array([item[1] for item in sorted_bins])

        # Separate profitable vs unprofitable shares
        # Profitable: cost <= current_price
        profitable = dist_prices <= curr_price
        
        # Draw horizontal bars
        # For profit shares, we draw green/blue; for loss, we draw red/orange
        bar_colors = ["#2ca02c" if p <= curr_price else "#d62728" for p in dist_prices]
        
        # Calculate a suitable height for the bars based on bin size
        bin_size = dist_prices[1] - dist_prices[0] if len(dist_prices) > 1 else 0.5
        
        ax_cost.barh(
            dist_prices, 
            dist_weights * 100, 
            height=bin_size * 0.8, 
            color=bar_colors, 
            alpha=0.8,
            align='center',
            edgecolor='none'
        )
        
        ax_cost.axhline(curr_price, color="#1f77b4", linestyle="-", linewidth=1.0)
        ax_cost.text(
            ax_cost.get_xlim()[1] * 0.5, 
            curr_price + bin_size, 
            f"現價: {curr_price:.1f}", 
            color="#1f77b4", 
            fontweight='bold', 
            ha='center'
        )

        ax_cost.set_title("籌碼成本分佈區 (綠:獲利 / 紅:套牢)", fontsize=11, fontweight='bold')
        ax_cost.set_xlabel("佔比 (%)", fontsize=10)

        # Trust level: prefer the caller-supplied label (single source of truth in
        # CostMetrics.evaluate_trust); fall back to the legacy turnover-only rule
        # for old callers that do not pass one.
        if trust_level is None:
            trust_level = "未知 (Unknown)"
            if "Turnover_Rate" in df_history.columns:
                avg_turnover_pct = df_history['Turnover_Rate'].mean() * 100

                lockup_heavy = ["2412", "3045"]
                if stock_code in lockup_heavy:
                    trust_level = "中低 (Medium-Low) - 股權鎖定重"
                elif avg_turnover_pct >= 0.4:
                    trust_level = "極高 (Very High)"
                elif avg_turnover_pct >= 0.25:
                    trust_level = "高 (High)"
                elif avg_turnover_pct >= 0.12:
                    trust_level = "中 (Medium)"
                else:
                    trust_level = "低 (Low)"

        # Add text box with metrics summary
        summary_text = (
            f"目前股價: {curr_price:.2f}\n"
            f"平均成本: {avg_cost:.2f}\n"
            f"中位成本: {metrics['Median_Cost']:.2f}\n"
            f"控制點(POC): {poc:.2f}\n"
            f"獲利籌碼比: {metrics['Profit_Ratio']*100:.1f}%\n"
            f"套牢籌碼比: {metrics['Loss_Ratio']*100:.1f}%\n"
            f"模型可信度: {trust_level}"
        )
        if data_as_of:
            summary_text += f"\n資料截至: {data_as_of}"
        
        # Place text box on the price chart
        props = dict(boxstyle='round', facecolor='wheat', alpha=0.3)
        ax_price.text(
            0.02, 0.05, 
            summary_text, 
            transform=ax_price.transAxes, 
            fontsize=9.5,
            verticalalignment='bottom', 
            bbox=props
        )

        plt.tight_layout()
        save_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        plt.close('all')
        print(f"Cost distribution chart successfully saved at: {save_path}")
