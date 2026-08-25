# skill-stock-ma-rsi-bband-macd-peband

台股個股/ETF技術指標快照技能（MA/STD/布林通道、RSI(14)、MACD）加上標準 common market PE band。Fugle API 還原股價為權威來源，yfinance 版本保留供 `--verify` 交叉比對；PEBand 需要呼叫端提供 dated EPS CSV，並明確區分 `trailing_eps`、`forward_eps`、`forward_consensus_eps`。詳細指令與輸出契約見 [SKILL.md](SKILL.md)。

## 快速開始

```bash
# 直接指定代號
python scripts/run_indicators.py --symbols 0050 0052 2330 --fugle-env-prefix USER1_ --output out.csv

# 從清單CSV讀取，並跟yfinance交叉比對
python scripts/run_indicators.py --list StockID.csv --fugle-env-prefix USER1_ --output out.csv --verify

# 加入 PEBand：EPS CSV 至少包含 symbol/stock_code/代號 與 eps 欄
python scripts/run_indicators.py --source yahoo --symbols 2330.TW --output out.csv \
  --pe-eps-file eps.csv \
  --pe-eps-columns trailing_eps=eps_ttm,forward_eps=model_eps_2027e,forward_consensus_eps=consensus_eps_2027e \
  --pe-eps-horizon FY2027E --pe-period 1200
```

## 檔案結構

```
skill-stock-ma-rsi-bband-macd-peband/
  SKILL.md              # 技能指令與輸出契約
  metadata.json         # 版本與來源 metadata
  self_update.py         # 通用技能自我更新工具（跟其他skill共用同一份，勿修改）
  scripts/
    run_indicators.py    # CLI進入點：批次算指標快照、寫CSV、選配--verify交叉比對
    build_trailing_ttm_eps.py # utility：季度actual EPS -> trailing TTM EPS dated series
    run_backtest.py       # CLI進入點：(0)~(13b)條件分類法歷史回測，多horizon
    backtest.py            # 純邏輯：回測條件偵測+forward報酬/勝率統計
    price_loader.py         # Fugle還原股價（除息+分割回溯調整）+ yfinance交叉來源
    indicators.py            # 純數學：MA/STD/BBand/z-score/RSI/MACD(12,26,9)/PEBand
```

## 版本

- 1.7.0 (2026-08-24)：新增 `scripts/build_trailing_ttm_eps.py`，把 quarterly actual EPS fact table 轉成 `trailing_eps` / TTM dated series，供標準 PEBand 使用；支援 official overlay row，並在缺少 historical disclosure date 時標示 `period_end_effective_for_historical_band_until_disclosure_dates_available`。
- 1.6.1 (2026-08-24)：default `--pe-period` 改為 `1200`，對應常見 5Y normalized PE band；文件明確標示 `60`=季度短期 regime、`240`=1Y trading band、`720`=3Y、`1200`=5Y。
- 1.6.0 (2026-08-24)：PEBand 改成標準 historical PE series 定義：EPS CSV 預設必須有 `date` / `asof_date` / `forecast_asof_date`，逐日計算 `PE_t = adjusted_close_t / EPS_t` 後再算 μ、樣本 σ、μ±1σ/±2σ；沒有日期欄的固定 EPS 只能用 `--pe-allow-static-eps-band` 作為非標準 fallback。
- 1.5.0 (2026-08-24)：PEBand EPS 輸入新增明確 scope：`trailing_eps`、`forward_eps`、`forward_consensus_eps`。新增 `--pe-eps-scope`、`--pe-eps-columns`、`--pe-eps-horizon`、`--pe-eps-source`，可在同一輸出同時計算多組 PE band，避免 TTM / 單一 forward / consensus forward EPS 混算。
- 1.4.0 (2026-08-24)：建立 renamed skill `skill-stock-MA-RSI-BBand-MACD-PEBand`，新增可選 `--pe-eps-file` / `--pe-eps-column` / `--pe-period`。PEBand 採 common market PE band 口徑：每個交易日先算 `PE_t = adjusted_close_t / EPS_t`，再對最近 N 個有效 `PE_t` 算 μ 與樣本 σ（ddof=1），輸出 μ、μ±1σ/±2σ 與用同一 scope latest EPS 換算的價格帶；EPS 必須由呼叫端資料層提供；標準模式必須是含日期的 daily/as-of EPS 序列，固定 EPS 只屬非標準 fallback。

- 1.3.1 (2026-08-11)：修正Python 3.8相容性——`list[dict]`/`X | None`這類PEP585/604型別
  標註語法在3.8會直接讓import炸掉（`TypeError: 'type' object is not subscriptable`），
  受影響的每個檔案開頭加`from __future__ import annotations`延遲型別標註求值。是造成
  GoogleSheet.Banks的`Fugle Stock Data`跟`TAIEX Crash Top50 Weekly`兩個排程失敗的元兇
  （self-hosted runner卡在Python 3.8）。

- 1.3.0 (2026-08-10)：新增歷史回測模組 `backtest.py`/`run_backtest.py`——(0)~(13b)條件
  分類法（單日急跌/跌破均線/RSI超賣/z-score偏離/創新高新低），支援多horizon（例如
  60/180/360日）forward報酬/勝率統計。`price_loader.fetch_fugle_adjusted()` 新增明確
  `start_date`/`end_date` 參數（原本只能「回溯N年到今天」，長期回測要能指定任意歷史區間），
  `fetch_fugle_market_adjustment_events()` 自動分段處理Fugle除息/分割端點的3年查詢上限。
  這次把GoogleSheet.Banks `投資決策分層.md` 的回測邏輯收進來時，發現該文件先前的資料完全
  沒做除息回溯還原，藉這次機會一併修正，詳見SKILL.md。
- 1.2.0 (2026-08-10)：`indicators.py` 新增 `calc_rsi_state(close, period)`，回傳
  Wilder RSI遞迴平滑在最後一筆收盤價當下的內部狀態（last_close/avg_gain/avg_loss），
  讓消費端能把RSI做成即時公式（引用「現價+這三個輔助值」），不必每天/每次報價變動都
  重新登入API重算整條序列。GoogleSheet.Banks的`update_zscore_stats.py`已改用這個模式。
- 1.1.0 (2026-08-10)：新增 `--source {fugle,yahoo}` 選擇主要資料來源——沒有Fugle/
  TaishinSDK憑證的consumer repo可以改用 `--source yahoo`（純yfinance，不需要任何憑證），
  代號直接傳yfinance ticker格式；有Fugle憑證的repo維持預設的 `--source fugle` + 選配
  `--verify` 雙來源交叉比對。兩種來源輸出的CSV欄位格式完全一致。
- 1.0.0 (2026-08-10)：自 GoogleSheet.Banks 的 `update_zscore_stats.py` 收錄並泛化——
  拿掉對特定Google Sheet的依賴，改成通用CLI（`--symbols`/`--list` + CSV輸出），
  新增MACD(12,26,9)與明確的布林通道(BBand)輸出，`--verify`交叉比對機制沿用原本已驗證過
  能抓出yfinance還原缺陷（0052分割事件）的方法論。
