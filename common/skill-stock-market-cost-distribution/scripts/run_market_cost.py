#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_market_cost.py
市場籌碼成本分佈模擬器（台新 Nova API 小時 K + Yahoo 日 K 暖機混和模型）。

對每一檔輸入股票輸出：
  <output>/<symbol>_cost_distribution_taishin.png   雙欄圖（股價走勢 + 成本分佈）
  <output>/csv/<symbol>_cost_distribution_taishin.csv
      欄位: price, weight, trust_level, data_as_of, staleness_days
  <output>/taishin_observation_validation_report.md 總報告（總覽表 + 全部圖 + 失敗清單）

小時 K 線會快取在 <intraday-dir>/<symbol>_intraday_60m.csv；
全部命中快取時完全離線執行（不登入台新 API）。
"""
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SKILL_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_SCRIPTS_DIR))

from data_loader import DataLoader
from simulator import CostSimulator
from metrics import CostMetrics
from visualizer import CostVisualizer

plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
plt.rcParams['font.family'] = 'Microsoft JhengHei'
plt.rcParams['axes.unicode_minus'] = False

# TAIEX: the API rejects "0000"; the index symbol is IX0001 and its candle
# volume field is trade VALUE (NTD), not share count.
INDEX_CODE = "0000"
INDEX_API_SYMBOL = "IX0001"
TAIWAN_MARKET_CAP_NTD = 75e12

HOURLY_EARLIEST = "2023-05-23"


def parse_args():
    p = argparse.ArgumentParser(description="市場籌碼成本分佈模擬器")
    p.add_argument("--list", dest="list_csv", help="股票清單 CSV（需含 代號,名稱 兩欄）")
    p.add_argument("--symbol", nargs="*", default=[], help="直接指定一或多檔股票代號（可與 --list 併用）")
    p.add_argument("--data-dir", default="data", help="資料根目錄（含 Yahoo.Finance/ 與 Python-Actions.GoodInfo.Analyzer/）")
    p.add_argument("--intraday-dir", default=None, help="小時 K 快取目錄（預設 <data-dir>/Taishin.Intraday）")
    p.add_argument("--output-dir", default="output", help="輸出目錄")
    p.add_argument("--env-file", default="C:/Users/WJLEE/SynologyDrive/NAS/github.com/GoogleSheet.Banks/.env",
                   help="台新憑證 .env（僅在快取缺漏需要下載時使用）")
    p.add_argument("--cert-base", default="C:/Users/WJLEE/SynologyDrive/NAS/github.com/GoogleSheet.Banks",
                   help="憑證相對路徑的基準目錄")
    p.add_argument("--offline", action="store_true", help="強制離線：快取缺漏的股票直接列入失敗，不登入 API")
    return p.parse_args()


class LazyTaishin:
    """Logs in to the Taishin Nova API only when a download is actually needed."""

    def __init__(self, env_file: str, cert_base: str):
        self.env_file = Path(env_file)
        self.cert_base = Path(cert_base)
        self._reststock = None

    def reststock(self):
        if self._reststock is None:
            creds = {}
            for line in self.env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    creds[k.strip()] = v.strip()
            cert_path = str(self.cert_base / creds["FUGLE_USER1_CERT_PATH"])
            from taishin_sdk import TaishinSDK
            sdk = TaishinSDK()
            accounts = sdk.login(creds["FUGLE_USER1_PERSONAL_ID"], creds["FUGLE_USER1_PASSWORD"],
                                 cert_path, creds["FUGLE_USER1_CERT_PASS"])
            sdk.init_realtime(accounts[0])
            print(f"  * 台新 Nova API 登入成功: {accounts[0].name}")
            self._reststock = sdk.marketdata.rest_client.stock
        return self._reststock


def get_company_name(data_dir: Path, stock_code: str) -> str:
    perf_csv = data_dir / "Python-Actions.GoodInfo.Analyzer" / "cleaned_performance.csv"
    if perf_csv.exists():
        try:
            df = pd.read_csv(perf_csv, dtype={"stock_code": str})
            df = df[df["stock_code"] == str(stock_code).strip()].dropna(subset=["company_name"])
            if not df.empty:
                return df.iloc[0]["company_name"]
        except Exception:
            pass
    return "個股"


def download_hourly(api, symbol: str, api_symbol: str, is_index: bool, cache_path: Path):
    today_str = datetime.now().strftime("%Y-%m-%d")
    # Each range strictly < 365 days to satisfy the API limit
    chunks = [
        (HOURLY_EARLIEST, "2024-03-31"),
        ("2024-04-01", "2025-01-31"),
        ("2025-02-01", "2025-11-30"),
        ("2025-12-01", today_str),
    ]
    all_candles = []
    for start_date, end_date in chunks:
        try:
            print(f"  * 下載分段: {start_date} ~ {end_date}...")
            res = api.historical.candles(**{
                "symbol": api_symbol, "timeframe": "60",
                "from": start_date, "to": end_date
            })
            if res and "data" in res and res["data"]:
                all_candles.extend(res["data"])
            time.sleep(1.0)
        except Exception as e:
            print(f"    [Error] 下載分段失敗: {e}")
            time.sleep(2.0)

    if not all_candles:
        return None

    unique = {c["date"]: c for c in all_candles}
    df = pd.DataFrame([unique[k] for k in sorted(unique.keys())])
    df = df.rename(columns={"date": "Date", "open": "Open", "high": "High",
                            "low": "Low", "close": "Close", "volume": "Volume"})
    df["Date"] = pd.to_datetime(df["Date"])
    if not is_index:
        # Stocks: convert lots (張) to shares; index volume is already trade value in NTD
        df["Volume"] = df["Volume"] * 1000
    df = df.sort_values("Date").reset_index(drop=True)
    df.to_csv(cache_path, index=False)
    return df


def process_symbol(symbol: str, name_hint: str, loader: DataLoader, taishin: LazyTaishin,
                   intraday_dir: Path, output_dir: Path, offline: bool):
    is_index = (symbol == INDEX_CODE)
    api_symbol = INDEX_API_SYMBOL if is_index else symbol
    company_name = "台灣加權指數" if is_index else get_company_name(loader.data_dir, symbol)
    if company_name == "個股":
        company_name = name_hint or "個股"

    cache_path = intraday_dir / f"{symbol}_intraday_60m.csv"
    df_hourly = None
    if cache_path.exists() and cache_path.stat().st_size > 10000:
        try:
            df_hourly = pd.read_csv(cache_path)
            df_hourly["Date"] = pd.to_datetime(df_hourly["Date"])
            print(f"  * 載入本地快取: {cache_path.name} ({len(df_hourly)} 筆小時 K)")
        except Exception:
            df_hourly = None

    if df_hourly is None:
        if offline:
            raise RuntimeError("離線模式且無小時 K 快取")
        df_hourly = download_hourly(taishin.reststock(), symbol, api_symbol, is_index, cache_path)
        if df_hourly is None:
            raise RuntimeError("未取得任何 K 線資料")

    if is_index:
        # Index has no share capital; volume is trade value (NTD), so divide by
        # total market cap. free_float default 0.90 -> scale up to land on ~75e12.
        shares_outstanding = TAIWAN_MARKET_CAP_NTD / 0.90
        corporate_actions = []
        shareholder_concentration = pd.DataFrame()
    else:
        shares_outstanding = loader.load_shares_outstanding(symbol)
        corporate_actions = loader.load_corporate_actions(symbol)
        shareholder_concentration = loader.load_weekly_shareholder_concentration(symbol)

    # Daily prices for the pre-hourly warming period (max 10 years back)
    df_daily_pre = pd.DataFrame()
    df_daily = pd.DataFrame()
    if not is_index:
        try:
            df_daily = loader.load_daily_prices(symbol)
            df_daily["Date_Naive"] = pd.to_datetime(df_daily["Date"]).dt.tz_localize(None)
            hourly_start_day = pd.to_datetime(df_hourly.iloc[0]["Date"]).normalize().tz_localize(None)
            ten_years_ago = hourly_start_day - pd.DateOffset(years=10)
            df_daily_pre = df_daily[(df_daily["Date_Naive"] >= ten_years_ago) &
                                    (df_daily["Date_Naive"] < hourly_start_day)].copy()
            df_daily_pre = df_daily_pre.drop(columns=["Date_Naive"])
            if not df_daily_pre.empty:
                print(f"  * 日 K 暖機 {len(df_daily_pre)} 筆 ({df_daily_pre['Date'].min():%Y/%m/%d} ~ {df_daily_pre['Date'].max():%Y/%m/%d})")
        except Exception as e:
            print(f"  [Warning] 無法載入日 K 暖機: {e}")

    first_price = df_hourly.iloc[0]["Close"]
    raw_size = first_price * 0.005
    if raw_size < 0.1:
        bin_size = 0.05
    elif raw_size < 0.5:
        bin_size = 0.1
    elif raw_size < 1.0:
        bin_size = 0.5
    elif raw_size < 5.0:
        bin_size = 1.0
    else:
        bin_size = 5.0

    simulator = CostSimulator(bin_size=bin_size, model_type="double_pool_dynamic")

    daily_history = []
    if not df_daily_pre.empty:
        # Daily prices in the CSV are already back-adjusted -> no corporate actions here
        daily_history = simulator.run_daily_simulation(
            df_prices=df_daily_pre, shares_outstanding=shares_outstanding,
            corporate_actions=[], shareholder_concentration=shareholder_concentration,
            stock_code=symbol)

        # Transition scaling: map adjusted daily bins onto the unadjusted hourly start price
        daily_end_price = df_daily_pre.iloc[-1]["Close"]
        hourly_start_price = df_hourly.iloc[0]["Close"]
        if daily_end_price > 0:
            scale = hourly_start_price / daily_end_price
            simulator.active_dist = {simulator.get_bin(p * scale): w for p, w in simulator.active_dist.items()}
            simulator.core_dist = {simulator.get_bin(p * scale): w for p, w in simulator.core_dist.items()}
            simulator.update_main_distribution()

    hourly_history = simulator.run_hourly_simulation(
        df_hourly=df_hourly, shares_outstanding=shares_outstanding,
        corporate_actions=corporate_actions,
        shareholder_concentration=shareholder_concentration, stock_code=symbol)

    history_records = daily_history + hourly_history
    final_dist = simulator.distribution
    last_close = df_hourly.iloc[-1]["Close"]
    metrics = CostMetrics.calculate_all(final_dist, last_close)

    df_hist = pd.DataFrame(history_records)
    total_trading_days = len(df_daily) if not df_daily.empty else 0
    trust = CostMetrics.evaluate_trust(
        df_history=df_hist, total_trading_days=total_trading_days,
        stock_code=symbol, is_index=is_index,
        data_as_of=df_hourly.iloc[-1]["Date"])

    chart_path = output_dir / f"{symbol}_cost_distribution_taishin.png"
    CostVisualizer.plot_cost_chart(
        df_history=df_hist, final_dist=final_dist, metrics=metrics,
        stock_code=symbol, company_name=company_name, save_path=chart_path,
        shares_outstanding=shares_outstanding,
        trust_level=trust["label"], data_as_of=trust["data_as_of"])

    csv_dir = output_dir / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"price": k, "weight": v, "trust_level": trust["label"],
         "data_as_of": trust["data_as_of"], "staleness_days": trust["staleness_days"]}
        for k, v in sorted(final_dist.items())
    ]).to_csv(csv_dir / f"{symbol}_cost_distribution_taishin.csv", index=False)

    return {
        "Symbol": symbol, "Name": company_name, "Close": last_close,
        "AvgCost": metrics["Average_Cost"], "MedianCost": metrics["Median_Cost"],
        "POC": metrics["POC"], "POC_Weight": metrics["POC_Weight"] * 100,
        "ProfitRatio": metrics["Profit_Ratio"] * 100, "LossRatio": metrics["Loss_Ratio"] * 100,
        "TrustLevel": trust["label"], "DataAsOf": trust["data_as_of"]
    }


def write_report(results, failed, output_dir: Path):
    report_path = output_dir / "taishin_observation_validation_report.md"
    table = [
        "| 股票代號與名稱 | 最新收盤價 (元) | 平均成本 (元) | 中位成本 (元) | 最密集籌碼點 POC | 獲利籌碼佔比 | 套牢籌碼佔比 | 模型可信度 | 資料截至 |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |"
    ]
    images = []
    for r in results:
        table.append(
            f"| **{r['Symbol']} {r['Name']}** | {r['Close']:.2f} | {r['AvgCost']:.2f} | {r['MedianCost']:.2f} "
            f"| {r['POC']:.2f} ({r['POC_Weight']:.1f}%) | {r['ProfitRatio']:.2f}% | {r['LossRatio']:.2f}% "
            f"| **{r['TrustLevel']}** | {r.get('DataAsOf') or '-'} |")
        images.append(f"### {r['Symbol']} {r['Name']}\n\n![{r['Name']}](./{r['Symbol']}_cost_distribution_taishin.png)")

    failed_block = ""
    if failed:
        lines = ["## 三、 處理失敗清單\n", "| 股票代號 | 名稱 | 原因 |", "| :--- | :--- | :--- |"]
        lines += [f"| {f['Symbol']} | {f['Name']} | {f['Reason']} |" for f in failed]
        failed_block = "\n".join(lines)

    content = f"""# 觀察名單籌碼持股成本分佈評估報告 (台新 Nova API 高頻小時級)

成功 {len(results)} 檔 / 失敗 {len(failed)} 檔。台新小時 K（{HOURLY_EARLIEST} 起）搭配最長 10 年日 K 暖機的混和模擬。

---

## 一、 數據總覽

{chr(10).join(table)}

---

## 二、 個股籌碼分佈圖

{chr(10).join(images)}

{failed_block}

報告生成時間：{datetime.now():%Y-%m-%d %H:%M}
"""
    report_path.write_text(content, encoding="utf-8")
    print(f"報告已輸出: {report_path}")


def main():
    args = parse_args()
    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    intraday_dir = Path(args.intraday_dir) if args.intraday_dir else data_dir / "Taishin.Intraday"
    intraday_dir.mkdir(parents=True, exist_ok=True)

    targets = []
    if args.list_csv:
        df = pd.read_csv(args.list_csv, dtype={"代號": str})
        targets += [(str(r["代號"]).strip(), str(r["名稱"]).strip()) for _, r in df.iterrows()]
    for s in args.symbol:
        targets.append((str(s).strip(), ""))
    if not targets:
        print("[Error] 請用 --list 或 --symbol 指定股票")
        sys.exit(1)

    loader = DataLoader(data_dir=data_dir)
    taishin = LazyTaishin(args.env_file, args.cert_base)

    results, failed = [], []
    for i, (symbol, name) in enumerate(targets):
        print(f"\n[{i+1}/{len(targets)}] 處理 {name or symbol} ({symbol})")
        try:
            results.append(process_symbol(symbol, name, loader, taishin,
                                          intraday_dir, output_dir, args.offline))
            print("  * 完成")
        except Exception as e:
            print(f"  [Error] {e}")
            failed.append({"Symbol": symbol, "Name": name or symbol, "Reason": str(e)})

    write_report(results, failed, output_dir)
    print(f"\n完成: 成功 {len(results)} / 失敗 {len(failed)}")


if __name__ == "__main__":
    main()
