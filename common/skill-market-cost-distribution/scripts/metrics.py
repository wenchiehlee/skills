import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# Trust levels ordered from least to most trustworthy (for downgrade arithmetic)
TRUST_LEVELS = ["極低 (Very Low)", "低 (Low)", "中低 (Medium-Low)", "中 (Medium)", "高 (High)", "極高 (Very High)"]

LOCKUP_HEAVY = {"2412", "3045"}


class CostMetrics:
    """
    CostMetrics calculates statistical and trading metrics from a cost distribution.
    """
    @staticmethod
    def calculate_all(distribution: Dict[float, float], current_price: float) -> Dict:
        """
        Calculates all key metrics for a given cost distribution and current price.
        """
        if not distribution:
            return {}

        # Sort distribution items by price
        sorted_bins = sorted(distribution.items(), key=lambda x: x[0])
        prices = np.array([item[0] for item in sorted_bins])
        weights = np.array([item[1] for item in sorted_bins])
        
        # Ensure weights are normalized
        sum_weights = weights.sum()
        if sum_weights > 0:
            weights = weights / sum_weights

        # 1. Average Cost
        avg_cost = float(np.sum(prices * weights))

        # Cumulative weight
        cum_weights = np.cumsum(weights)

        # 2. Percentiles (10%, 25%, 50%, 75%, 90%)
        percentiles = {}
        target_pcts = [0.10, 0.25, 0.50, 0.75, 0.90]
        for pct in target_pcts:
            # Find the first index where cumulative weight >= pct
            idx = np.searchsorted(cum_weights, pct)
            if idx >= len(prices):
                idx = len(prices) - 1
            percentiles[f"Pct_{int(pct*100)}"] = float(prices[idx])

        # Median cost is Pct_50
        median_cost = percentiles["Pct_50"]

        # 3. Profit Ratio (cost < current_price)
        # In Taiwan, we usually count cost <= current_price as profit.
        profit_idx = prices <= current_price
        profit_ratio = float(np.sum(weights[profit_idx]))

        # Loss Ratio
        loss_ratio = 1.0 - profit_ratio

        # 4. Point of Control (POC) - price bin with maximum weight
        max_idx = np.argmax(weights)
        poc = float(prices[max_idx])
        poc_weight = float(weights[max_idx])

        # 5. Chip Concentration (籌碼集中度)
        # e.g., range between 15% and 85% of cumulative weight,
        # or range between 10% and 90%
        range_90_width = percentiles["Pct_90"] - percentiles["Pct_10"]
        range_90_pct = range_90_width / average_if_zero(avg_cost)

        return {
            "Average_Cost": avg_cost,
            "Median_Cost": median_cost,
            "Percentiles": percentiles,
            "Profit_Ratio": profit_ratio,
            "Loss_Ratio": loss_ratio,
            "POC": poc,
            "POC_Weight": poc_weight,
            "Range_90_Width": range_90_width,
            "Chip_Concentration_90_Pct": range_90_pct
        }

    @staticmethod
    def evaluate_trust(
        df_history: Optional[pd.DataFrame],
        total_trading_days: int,
        stock_code: Optional[str] = None,
        is_index: bool = False,
        data_as_of: Optional[pd.Timestamp] = None,
        as_of_now: Optional[datetime] = None,
    ) -> Dict:
        """
        Single source of truth for the model trust level, shared by the PNG,
        the CSV, and the markdown report.

        Basis: mean per-DAY free-float turnover rate taken from the simulation
        history records (df_history['Turnover_Rate']).

        Priority of rules:
          1. Index          -> reference-only label (turnover is a value/market-cap proxy)
          2. History length -> < 1000 daily bars means the warm-up cannot anchor
                               long-term holder costs (roughly 4 listed years)
          3. Heavy lockup   -> government/group-held stocks (2412, 3045)
          4. Turnover tiers -> >=0.40%/day 極高, >=0.25% 高, >=0.12% 中, else 低
          5. Freshness      -> stale data degrades the result: > 5 calendar days
                               downgrades one level, > 30 days overrides to 過期
        """
        avg_turnover_pct = 0.0
        if df_history is not None and not df_history.empty and "Turnover_Rate" in df_history.columns:
            avg_turnover_pct = float(df_history["Turnover_Rate"].mean()) * 100.0

        staleness_days = None
        if data_as_of is not None:
            now = as_of_now or datetime.now()
            as_of = pd.to_datetime(data_as_of)
            if as_of.tzinfo is not None:
                as_of = as_of.tz_localize(None)
            staleness_days = max(0, (pd.Timestamp(now).normalize() - as_of.normalize()).days)

        if is_index:
            label = "參考 (指數) - 換手率以成交值/總市值代理"
        elif total_trading_days < 1000:
            label = f"{TRUST_LEVELS[0]} - 新上市歷史過短"
        elif stock_code and str(stock_code).strip() in LOCKUP_HEAVY:
            label = f"{TRUST_LEVELS[2]} - 股權鎖定重"
        else:
            if avg_turnover_pct >= 0.4:
                level_idx = 5
            elif avg_turnover_pct >= 0.25:
                level_idx = 4
            elif avg_turnover_pct >= 0.12:
                level_idx = 3
            else:
                level_idx = 1

            if staleness_days is not None and staleness_days > 5:
                level_idx = max(0, level_idx - 1)
                label = f"{TRUST_LEVELS[level_idx]} - 資料略舊 {staleness_days} 天"
            else:
                label = TRUST_LEVELS[level_idx]

        if staleness_days is not None and staleness_days > 30 and not is_index:
            label = f"過期 (Stale) - 資料已 {staleness_days} 天未更新"

        return {
            "label": label,
            "avg_daily_turnover_pct": avg_turnover_pct,
            "staleness_days": staleness_days,
            "data_as_of": None if data_as_of is None else pd.to_datetime(data_as_of).strftime("%Y-%m-%d"),
            "total_trading_days": total_trading_days,
        }


def average_if_zero(val: float) -> float:
    return val if val != 0.0 else 1.0
