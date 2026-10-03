"""Render the shared valuation chart for non-Taiwan tickers from local Yahoo/ConceptStocks data."""
from __future__ import annotations
import argparse, importlib.util, json
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("dynamic_renderer", HERE / "render_dynamic_valuation_box.py")
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)

def _eps_rows(income: pd.DataFrame, symbol: str) -> pd.DataFrame:
    q = income[income["symbol"].astype(str).str.upper() == symbol.upper()].copy()
    q["end_date"] = pd.to_datetime(q["end_date"], errors="coerce")
    q["eps"] = pd.to_numeric(q["eps"], errors="coerce")
    # ConceptStocks has a known Alphabet inconsistency around the 2022
    # 20-for-1 split: 2022 Q1 is on the pre-split EPS basis while Q2/FY are
    # already post-split. Normalize stale pre-split values before deriving Q4.
    if symbol.upper() == "GOOGL":
        q.loc[q["end_date"] < pd.Timestamp("2022-04-01"), "eps"] /= 20.0
    q = q.dropna(subset=["end_date"])
    quarterly = q[q["period"].isin(["Q1", "Q2", "Q3", "Q4"]) & q["eps"].notna()].sort_values("end_date").drop_duplicates("end_date", keep="last")
    rows = quarterly[["end_date", "eps"]].rename(columns={"end_date": "period_end", "eps": "value"}).to_dict("records")
    fy_rows = q[(q["period"] == "FY") & q["eps"].notna()].copy()
    fy_rows = fy_rows[fy_rows["fiscal_year"].astype(str) == fy_rows["end_date"].dt.year.astype(str)]
    for _, fy in fy_rows.sort_values("end_date").drop_duplicates("end_date", keep="last").iterrows():
        prior = quarterly[(quarterly["end_date"] < fy["end_date"]) & (quarterly["end_date"] >= fy["end_date"] - pd.DateOffset(years=1))].tail(3)
        if len(prior) == 3:
            derived_q4 = float(fy["eps"] - prior["eps"].sum())
            # Annual weighted-average EPS is not always reconcilable to
            # quarterly EPS in international source data. Never create a
            # fictitious negative Q4/TTM EPS from that mismatch.
            if derived_q4 >= -0.1:
                rows.append({"period_end": fy["end_date"], "value": derived_q4})
    if not rows:
        return pd.DataFrame(columns=["available_date", "period_end", "eps", "ttm_eps"])
    eps = pd.DataFrame(rows).drop_duplicates("period_end", keep="last").sort_values("period_end")
    if eps.empty: return pd.DataFrame(columns=["available_date", "period_end", "eps", "ttm_eps"])
    eps["available_date"] = eps["period_end"] + pd.Timedelta(days=45)
    eps["ttm_eps"] = eps["value"].rolling(4).sum()
    return eps[["available_date", "period_end", "value", "ttm_eps"]].rename(columns={"value": "eps"})

def _revenue_rows(income: pd.DataFrame, symbol: str) -> pd.DataFrame:
    q = income[income["symbol"].astype(str).str.upper() == symbol.upper()].copy()
    q["end_date"] = pd.to_datetime(q["end_date"], errors="coerce")
    q["revenue"] = pd.to_numeric(q["total_revenue"], errors="coerce") / 1e6
    q = q.dropna(subset=["end_date", "revenue"])
    quarterly = q[q["period"].isin(["Q1", "Q2", "Q3"])].sort_values("end_date").drop_duplicates("end_date", keep="last")
    rows = quarterly[["end_date", "revenue"]].to_dict("records")
    for _, fy in q[q["period"] == "FY"].sort_values("end_date").drop_duplicates("end_date", keep="last").iterrows():
        prior = quarterly[(quarterly["end_date"] < fy["end_date"]) & (quarterly["end_date"] >= fy["end_date"] - pd.DateOffset(years=1))].tail(3)
        if len(prior) == 3:
            rows.append({"end_date": fy["end_date"], "revenue": float(fy["revenue"] - prior["revenue"].sum())})
    if not rows:
        return pd.DataFrame(columns=["date", "revenue_m_twd", "revenue_yoy_pct", "analyzer_revenue_m_twd", "analyzer_yoy_pct", "finmind_revenue_m_twd", "finmind_yoy_pct"])
    revenue = pd.DataFrame(rows).sort_values("end_date")
    if not revenue.empty:
        revenue = revenue.drop_duplicates("end_date", keep="last").sort_values("end_date")
        # ConceptStocks can emit the same fiscal revenue twice on nearby
        # dates. Keep one bar so chart 4 and chart 5 do not overlap.
        duplicate = revenue["revenue"].eq(revenue["revenue"].shift()) & revenue["end_date"].diff().le(pd.Timedelta(days=10))
        revenue = revenue.loc[~duplicate].drop_duplicates("end_date", keep="last")
    if revenue.empty: return pd.DataFrame(columns=["date", "revenue_m_twd", "revenue_yoy_pct", "analyzer_revenue_m_twd", "analyzer_yoy_pct", "finmind_revenue_m_twd", "finmind_yoy_pct"])
    revenue = revenue.rename(columns={"end_date": "date", "revenue": "revenue_m_twd"})
    revenue["revenue_yoy_pct"] = revenue["revenue_m_twd"].pct_change(4) * 100
    for c in ["analyzer_revenue_m_twd", "analyzer_yoy_pct", "finmind_revenue_m_twd", "finmind_yoy_pct"]: revenue[c] = float("nan")
    return revenue[["date", "revenue_m_twd", "revenue_yoy_pct", "analyzer_revenue_m_twd", "analyzer_yoy_pct", "finmind_revenue_m_twd", "finmind_yoy_pct"]]


def _profit_rows(income: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Build quarterly USD-million profit metrics for panels 8-11."""
    q = income[income["symbol"].astype(str).str.upper() == symbol.upper()].copy()
    q["end_date"] = pd.to_datetime(q["end_date"], errors="coerce")
    q["revenue"] = pd.to_numeric(q["total_revenue"], errors="coerce") / 1e6
    q["net_profit"] = pd.to_numeric(q["net_income"], errors="coerce") / 1e6
    q = q.dropna(subset=["end_date", "revenue", "net_profit"])
    quarterly = q[q["period"].isin(["Q1", "Q2", "Q3"])].sort_values("end_date").drop_duplicates("end_date", keep="last")
    rows = quarterly[["end_date", "revenue", "net_profit"]].to_dict("records")
    for _, fy in q[q["period"] == "FY"].sort_values("end_date").drop_duplicates("end_date", keep="last").iterrows():
        prior = quarterly[(quarterly["end_date"] < fy["end_date"]) & (quarterly["end_date"] >= fy["end_date"] - pd.DateOffset(years=1))].tail(3)
        if len(prior) == 3:
            rows.append({
                "end_date": fy["end_date"],
                "revenue": float(fy["revenue"] - prior["revenue"].sum()),
                "net_profit": float(fy["net_profit"] - prior["net_profit"].sum()),
            })
    if not rows:
        return pd.DataFrame(columns=["period_end", "available_date", "revenue", "net_profit", "net_profit_yoy_pct", "net_margin_pct", "net_margin_yoy_pct"])
    metrics = pd.DataFrame(rows).drop_duplicates("end_date", keep="last").sort_values("end_date")
    if metrics.empty:
        return pd.DataFrame(columns=["period_end", "available_date", "revenue", "net_profit", "net_profit_yoy_pct", "net_margin_pct", "net_margin_yoy_pct"])
    metrics["period_end"] = pd.to_datetime(metrics.pop("end_date"))
    metrics["available_date"] = metrics["period_end"] + pd.Timedelta(days=45)
    metrics["net_profit_yoy_pct"] = metrics["net_profit"].pct_change(4) * 100
    metrics["net_margin_pct"] = metrics["net_profit"].div(metrics["revenue"].replace(0, float("nan"))) * 100
    metrics["net_margin_yoy_pct"] = metrics["net_margin_pct"].diff(4)
    return metrics[["period_end", "available_date", "revenue", "net_profit", "net_profit_yoy_pct", "net_margin_pct", "net_margin_yoy_pct"]]


def render(symbol: str, years: int, price_csv: str, income_csv: str, output_dir: Path, name: str, yahoo_consensus_csv: str | None = None, factset_report_csv: str | None = None) -> None:
    prices = pd.read_csv(price_csv, dtype={"stock_code": str})
    prices = prices[prices["stock_code"].astype(str).str.upper() == symbol.upper()].copy()
    date_col = "交易_日期" if "交易_日期" in prices else "交易日期"
    close_col = "收盤價" if "收盤價" in prices else "收盤_價格_元"
    prices["date"] = pd.to_datetime(prices[date_col], errors="coerce")
    prices["close"] = pd.to_numeric(prices[close_col], errors="coerce")
    prices = prices[["date", "close"]].dropna().drop_duplicates("date").sort_values("date")
    income = pd.read_csv(income_csv, dtype={"symbol": str})
    eps = _eps_rows(income, symbol)
    if prices.empty or eps.empty:
        print(f"WARNING: skip {symbol}: no usable price or EPS rows", file=__import__("sys").stderr, flush=True)
        return
    daily = pd.merge_asof(prices, eps.sort_values("available_date"), left_on="date", right_on="available_date", direction="backward").set_index("date")
    bands = r.calc_pe_band_series(daily["close"], daily["ttm_eps"], period=120)
    daily = daily.join(bands[["pe", "pe_mean", "pe_std", "price_m2", "price_m1", "price_mean", "price_p1", "price_p2"]])
    forward_sources = [
        r._read_yahoo_consensus_eps(yahoo_consensus_csv, [symbol]),
        r._read_factset_eps(factset_report_csv, [symbol]),
    ]
    forward_sources = [frame for frame in forward_sources if not frame.empty]
    forward = pd.concat(forward_sources, ignore_index=True).sort_values("as_of_date") if forward_sources else pd.DataFrame(columns=["symbol", "as_of_date", "forward_eps"])
    for col in ["forward_pe", "forward_pe_mean", "forward_pe_std", "forward_price_m2", "forward_price_m1", "forward_price_mean", "forward_price_p1", "forward_price_p2"]: daily[col] = float("nan")
    if not forward.empty:
        daily = pd.merge_asof(
            daily.reset_index().sort_values("date"),
            forward[["as_of_date", "forward_eps"]].sort_values("as_of_date"),
            left_on="date", right_on="as_of_date", direction="backward",
        ).set_index("date")
        forward_bands = r.calc_pe_band_series(daily["close"], daily["forward_eps"], period=120, min_periods=20)
        daily["forward_pe"] = forward_bands["pe"]
        daily["forward_pe_mean"] = forward_bands["pe_mean"]
        daily["forward_pe_std"] = forward_bands["pe_std"]
        for field in ("m2", "m1", "mean", "p1", "p2"):
            daily[f"forward_price_{field}"] = daily["forward_eps"] * daily[f"forward_pe_{'mean' if field == 'mean' else 'mean'}"]
            if field != "mean":
                sigma = -2 if field == "m2" else -1 if field == "m1" else 1 if field == "p1" else 2
                daily[f"forward_price_{field}"] = daily["forward_eps"] * (daily["forward_pe_mean"] + sigma * daily["forward_pe_std"])
    monthly = _revenue_rows(income, symbol)
    profit_metrics = _profit_rows(income, symbol)
    trades = pd.DataFrame(columns=["symbol", "date", "side", "price", "lots"])
    yahoo_curve = r._yahoo_forward_curve(yahoo_consensus_csv, [symbol])
    factset_curve = r._factset_forward_curve(factset_report_csv, [symbol])
    r._plot(symbol, name, years, daily, eps, forward, trades, monthly, profit_metrics, output_dir, yahoo_curve, factset_curve, revenue_label="Quarterly revenue", revenue_axis_label="Revenue (M USD)", growth_label="Revenue YoY growth", profit_axis_label="Net profit (M USD)")

if __name__ == "__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--symbols", nargs="+", required=True); ap.add_argument("--years", type=int, choices=(2,3,4,5), default=3); ap.add_argument("--price-csv", default="../Yahoo.Finance/data/reports/raw_yahoo_finance_daily_price.csv"); ap.add_argument("--income-csv", default="../ConceptStocks/raw_conceptstock_company_income.csv"); ap.add_argument("--yahoo-consensus-csv"); ap.add_argument("--factset-report-csv"); ap.add_argument("--output-dir", default="output/dynamic_valuation_box"); ap.add_argument("--json-dir", default="data/enrichment_all"); args=ap.parse_args()
    for symbol in args.symbols:
        record=json.load(open(Path(args.json_dir)/f"{symbol}.json",encoding="utf-8")); render(symbol,args.years,args.price_csv,args.income_csv,Path(args.output_dir),record.get("company_name",symbol),args.yahoo_consensus_csv,args.factset_report_csv); print(symbol)
