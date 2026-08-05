import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional

class CostSimulator:
    """
    CostSimulator runs the chronological simulation of the market cost distribution.
    It supports:
    - Free-float turnover rate calculation (Refinement 1).
    - Dual-Pool Decay Model (Refinement 2: Active Pool vs. Core Pool).
    - Dynamic Weekly Shareholder Concentration Calibration.
    - Triangular Price Range Distribution (Refinement 3).
    - Corporate actions price adjustments on both pools (Refinement 4).
    - Dynamic bin sizing.
    - Hourly intraday data distribution (optional).
    """
    def __init__(self, bin_size: float = 0.5, decay_multiplier: float = 1.0, stock_code: Optional[str] = None, model_type: str = "single_pool"):
        self.bin_size = bin_size
        self.decay_multiplier = decay_multiplier
        self.stock_code = stock_code
        self.model_type = model_type
        
        # Dual-Pool Decay fractions
        if model_type == "single_pool":
            self.active_fraction = 1.0
            self.core_fraction = 0.0
            self.active_decay_factor = 1.0
            self.core_decay_factor = 0.0
        else: # double_pool_static or double_pool_dynamic
            self.active_fraction = 0.40
            self.core_fraction = 0.60
            self.active_decay_factor = 1.5
            self.core_decay_factor = 0.1
        
        # Two pools representing the cost distribution
        self.active_dist: Dict[float, float] = {}
        self.core_dist: Dict[float, float] = {}
        self.distribution: Dict[float, float] = {}

    def get_bin(self, price: float) -> float:
        """Finds the nearest bin center for a given price."""
        return round(price / self.bin_size) * self.bin_size

    def update_main_distribution(self):
        """Merges the active and core pools and normalizes to prevent floating point drift."""
        self.distribution = {}
        for k, v in self.active_dist.items():
            self.distribution[k] = self.distribution.get(k, 0.0) + v
        for k, v in self.core_dist.items():
            self.distribution[k] = self.distribution.get(k, 0.0) + v
            
        total_w = sum(self.distribution.values())
        if total_w > 0:
            self.distribution = {k: v / total_w for k, v in self.distribution.items()}

    def adjust_pool_fractions(self, new_active: float, new_core: float):
        """Rescales the active and core pools to match new concentration fractions."""
        active_sum = sum(self.active_dist.values())
        if active_sum > 0:
            scale = new_active / active_sum
            self.active_dist = {k: v * scale for k, v in self.active_dist.items()}
            
        core_sum = sum(self.core_dist.values())
        if core_sum > 0:
            scale = new_core / core_sum
            self.core_dist = {k: v * scale for k, v in self.core_dist.items()}
            
        self.active_fraction = new_active
        self.core_fraction = new_core
        self.update_main_distribution()

    def initialize_distribution(self, price: float, active_fraction: float = 0.40, core_fraction: float = 0.60):
        """Initializes both active and core pools at a single price point."""
        bin_center = self.get_bin(price)
        self.active_fraction = active_fraction
        self.core_fraction = core_fraction
        self.active_dist = {bin_center: active_fraction}
        self.core_dist = {bin_center: core_fraction}
        self.update_main_distribution()

    def apply_turnover_decay(self, turnover_rate: float) -> float:
        """
        Decays the active pool and core pool separately based on their decay factors.
        Returns the total weight removed to be re-distributed.
        """
        decay_active = min(max(turnover_rate * self.active_decay_factor * self.decay_multiplier, 0.0), 1.0)
        removed_active = 0.0
        new_active = {}
        for price_bin, weight in self.active_dist.items():
            decayed_weight = weight * (1.0 - decay_active)
            removed_active += weight * decay_active
            if decayed_weight > 1e-7:
                new_active[price_bin] = decayed_weight
        self.active_dist = new_active

        decay_core = min(max(turnover_rate * self.core_decay_factor * self.decay_multiplier, 0.0), 1.0)
        removed_core = 0.0
        new_core = {}
        for price_bin, weight in self.core_dist.items():
            decayed_weight = weight * (1.0 - decay_core)
            removed_core += weight * decay_core
            if decayed_weight > 1e-7:
                new_core[price_bin] = decayed_weight
        self.core_dist = new_core

        return removed_active + removed_core

    def distribute_daily_volume(self, low: float, high: float, vwap: float, total_weight: float) -> Dict[float, float]:
        """
        Refinement 3: Spreads today's transactions across the day's [Low, High] range
        using a triangular distribution peaking at VWAP.
        """
        if pd.isna(low) or pd.isna(high) or high <= low:
            bin_center = self.get_bin(vwap)
            return {bin_center: total_weight}
            
        start_bin = self.get_bin(low)
        end_bin = self.get_bin(high)
        
        bins = []
        curr = start_bin
        while curr <= end_bin:
            bins.append(curr)
            curr = round((curr + self.bin_size) / self.bin_size) * self.bin_size
            
        if not bins:
            bin_center = self.get_bin(vwap)
            return {bin_center: total_weight}
            
        raw_weights = []
        half_range = (high - low) / 2.0
        if half_range == 0:
            half_range = 1.0
            
        for b in bins:
            w = max(0.0, 1.0 - abs(b - vwap) / half_range)
            raw_weights.append(w)
            
        total_raw = sum(raw_weights)
        if total_raw == 0:
            raw_weights = [1.0] * len(bins)
            total_raw = len(bins)
            
        dist_contrib = {}
        for b, rw in zip(bins, raw_weights):
            dist_contrib[b] = (rw / total_raw) * total_weight
        return dist_contrib

    def add_new_cost_distribution(self, dist_contrib: Dict[float, float]):
        """Splits the newly distributed daily costs into the active and core pools."""
        for price_bin, weight in dist_contrib.items():
            active_w = weight * self.active_fraction
            self.active_dist[price_bin] = self.active_dist.get(price_bin, 0.0) + active_w
            
            core_w = weight * self.core_fraction
            self.core_dist[price_bin] = self.core_dist.get(price_bin, 0.0) + core_w
            
        self.update_main_distribution()

    def add_new_cost(self, price: float, weight: float):
        """Adds a single point transaction (for backward compatibility)."""
        if weight <= 0.0:
            return
        bin_center = self.get_bin(price)
        self.active_dist[bin_center] = self.active_dist.get(bin_center, 0.0) + weight * self.active_fraction
        self.core_dist[bin_center] = self.core_dist.get(bin_center, 0.0) + weight * self.core_fraction
        self.update_main_distribution()

    def apply_corporate_action(self, cash_dividend: float, stock_dividend_ratio: float):
        """
        Adjusts both pools for stock and cash dividend ex-rights/ex-dividend price changes.
        """
        if cash_dividend == 0.0 and stock_dividend_ratio == 0.0:
            return

        new_active = {}
        for price_bin, weight in self.active_dist.items():
            adjusted_price = (price_bin - cash_dividend) / (1.0 + stock_dividend_ratio)
            new_bin = self.get_bin(adjusted_price)
            new_active[new_bin] = new_active.get(new_bin, 0.0) + weight
        self.active_dist = new_active

        new_core = {}
        for price_bin, weight in self.core_dist.items():
            adjusted_price = (price_bin - cash_dividend) / (1.0 + stock_dividend_ratio)
            new_bin = self.get_bin(adjusted_price)
            new_core[new_bin] = new_core.get(new_bin, 0.0) + weight
        self.core_dist = new_core
        
        self.update_main_distribution()

    def get_free_float_ratio(self, stock_code: Optional[str]) -> float:
        """Refinement 1: Get free float ratio to adjust total outstanding shares."""
        if not stock_code:
            return 0.90
        
        lockup_ratios = {
            "2412": 0.50, # Chunghwa Telecom (Gov lockup)
            "3045": 0.45, # Taiwan Mobile (Fubon group lockup)
            "2382": 0.30, # Quanta (Founder Barry Lam)
            "2308": 0.20, # Delta (Founder family)
            "2357": 0.20, # ASUS
            "2454": 0.15, # MediaTek
            "2330": 0.15, # TSMC
            "2317": 0.15, # Foxconn
            "2303": 0.10, # UMC
        }
        code_str = str(stock_code).strip()
        return 1.0 - lockup_ratios.get(code_str, 0.10)

    def run_daily_simulation(
        self, 
        df_prices: pd.DataFrame, 
        shares_outstanding: float, 
        corporate_actions: List[Dict],
        shareholder_concentration: Optional[pd.DataFrame] = None,
        stock_code: Optional[str] = None
    ) -> List[Dict]:
        """Runs daily simulation using the new multi-pool and distributed framework."""
        current_stock_code = stock_code or self.stock_code
        free_float_ratio = self.get_free_float_ratio(current_stock_code)
        effective_shares = shares_outstanding * free_float_ratio if shares_outstanding > 0 else 0.0
        
        actions_by_date = {
            act["Date"].strftime("%Y-%m-%d"): act for act in corporate_actions
        }
        
        # Prepare concentration records sorted by date
        conc_records = []
        if self.model_type == "double_pool_dynamic" and shareholder_concentration is not None and not shareholder_concentration.empty:
            for _, r in shareholder_concentration.iterrows():
                conc_records.append((r["Date"], r["Core_Fraction"], r["Active_Fraction"]))
        conc_records.sort(key=lambda x: x[0])

        history_records = []
        conc_idx = 0
        
        for idx, row in df_prices.iterrows():
            current_date = row["Date"]
            date_str = current_date.strftime("%Y-%m-%d")
            close_price = row["Close"]
            high_price = row["High"]
            low_price = row["Low"]
            volume = row["Volume"]
            
            # Find latest shareholder concentration on or before current_date
            today_core = self.core_fraction
            today_active = self.active_fraction
            while conc_idx < len(conc_records) and conc_records[conc_idx][0] <= current_date:
                _, c_frac, a_frac = conc_records[conc_idx]
                today_core = c_frac
                today_active = a_frac
                conc_idx += 1
                
            if conc_idx > 0:
                _, today_core, today_active = conc_records[conc_idx - 1]
                
            # If concentration changed, dynamically rescale the pools
            if abs(today_core - self.core_fraction) > 1e-5 or abs(today_active - self.active_fraction) > 1e-5:
                if self.distribution:
                    self.adjust_pool_fractions(today_active, today_core)
                else:
                    self.active_fraction = today_active
                    self.core_fraction = today_core
            
            if date_str in actions_by_date:
                action = actions_by_date[date_str]
                self.apply_corporate_action(
                    cash_dividend=action["Cash_Dividend"],
                    stock_dividend_ratio=action["Stock_Dividend_Ratio"]
                )

            if pd.notna(high_price) and pd.notna(low_price) and high_price > 0 and low_price > 0:
                vwap = (high_price + low_price + close_price) / 3.0
            else:
                vwap = close_price
                
            if effective_shares > 0:
                turnover_rate = volume / effective_shares
            else:
                turnover_rate = 0.02
                
            turnover_rate = min(max(turnover_rate, 0.0), 0.20)

            if not self.distribution:
                self.initialize_distribution(vwap, self.active_fraction, self.core_fraction)
            else:
                removed_weight = self.apply_turnover_decay(turnover_rate)
                dist_contrib = self.distribute_daily_volume(low_price, high_price, vwap, removed_weight)
                self.add_new_cost_distribution(dist_contrib)
                
            self.update_main_distribution()
                
            snapshot = {k: v for k, v in self.distribution.items() if v > 1e-5}
            
            history_records.append({
                "Date": current_date,
                "Close": close_price,
                "VWAP": vwap,
                "Turnover_Rate": turnover_rate,
                "Distribution": snapshot
            })
            
        return history_records

    def run_hourly_simulation(
        self,
        df_hourly: pd.DataFrame,
        shares_outstanding: float,
        corporate_actions: List[Dict],
        shareholder_concentration: Optional[pd.DataFrame] = None,
        stock_code: Optional[str] = None
    ) -> List[Dict]:
        """Runs hourly intraday simulation using effective free-float shares and dynamic concentration."""
        current_stock_code = stock_code or self.stock_code
        free_float_ratio = self.get_free_float_ratio(current_stock_code)
        effective_shares = shares_outstanding * free_float_ratio if shares_outstanding > 0 else 0.0
        
        df_hourly = df_hourly.sort_values("Date").reset_index(drop=True)
        
        actions_by_date = {
            act["Date"].strftime("%Y-%m-%d"): act for act in corporate_actions
        }
        
        conc_records = []
        if self.model_type == "double_pool_dynamic" and shareholder_concentration is not None and not shareholder_concentration.empty:
            for _, r in shareholder_concentration.iterrows():
                conc_records.append((r["Date"], r["Core_Fraction"], r["Active_Fraction"]))
        conc_records.sort(key=lambda x: x[0])
        
        history_records = []
        applied_actions_dates = set()
        df_hourly["Day_Str"] = df_hourly["Date"].dt.strftime("%Y-%m-%d")
        
        conc_idx = 0
        
        for day_str, day_group in df_hourly.groupby("Day_Str"):
            day_date = pd.to_datetime(day_str)
            
            # Find latest concentration
            today_core = self.core_fraction
            today_active = self.active_fraction
            while conc_idx < len(conc_records) and conc_records[conc_idx][0] <= day_date:
                _, c_frac, a_frac = conc_records[conc_idx]
                today_core = c_frac
                today_active = a_frac
                conc_idx += 1
                
            if conc_idx > 0:
                _, today_core, today_active = conc_records[conc_idx - 1]
                
            if abs(today_core - self.core_fraction) > 1e-5 or abs(today_active - self.active_fraction) > 1e-5:
                if self.distribution:
                    self.adjust_pool_fractions(today_active, today_core)
                else:
                    self.active_fraction = today_active
                    self.core_fraction = today_core

            if day_str in actions_by_date and day_str not in applied_actions_dates:
                action = actions_by_date[day_str]
                self.apply_corporate_action(
                    cash_dividend=action["Cash_Dividend"],
                    stock_dividend_ratio=action["Stock_Dividend_Ratio"]
                )
                applied_actions_dates.add(day_str)
                
            day_volume = 0.0
            day_close = day_group.iloc[-1]["Close"]
            
            for _, hour_row in day_group.iterrows():
                h_close = hour_row["Close"]
                h_high = hour_row["High"]
                h_low = hour_row["Low"]
                h_volume = hour_row["Volume"]
                day_volume += h_volume
                
                h_vwap = (h_high + h_low + h_close) / 3.0 if (h_high > 0 and h_low > 0) else h_close
                h_turnover = h_volume / effective_shares if effective_shares > 0 else 0.002
                h_turnover = min(max(h_turnover, 0.0), 0.05)
                
                if not self.distribution:
                    self.initialize_distribution(h_vwap, self.active_fraction, self.core_fraction)
                else:
                    removed = self.apply_turnover_decay(h_turnover)
                    self.add_new_cost(h_vwap, removed)
                    
            self.update_main_distribution()
            snapshot = {k: v for k, v in self.distribution.items() if v > 1e-5}
            
            history_records.append({
                "Date": day_date,
                "Close": day_close,
                "VWAP": day_close,
                "Turnover_Rate": day_volume / effective_shares if effective_shares > 0 else 0.0,
                "Distribution": snapshot
            })
            
        return history_records
