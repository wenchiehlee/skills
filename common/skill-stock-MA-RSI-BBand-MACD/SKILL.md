---
name: skill-stock-MA-RSI-BBand-MACD
description: 台股個股/ETF技術指標快照（MA/STD/布林通道、RSI、MACD）與歷史回測，以Fugle API還原股價（自動回溯調整除息+分割/減資）為權威來源，保留yfinance版本供交叉比對。
---

# Stock MA / RSI / BBand / MACD Skill

對一批台股代號算出以下技術指標的最新快照，輸出成一個CSV（每檔一列）：

- **MA/STD/z-score**：MA20/MA60/MA120/MA240（月/季/半年/年線）各自的均線、標準差、z-score（(現價-MA)/STD，可判斷偏離幾個標準差）
- **布林通道（BBand）**：以MA20/STD20為基礎，上軌=MA20+2σ、下軌=MA20-2σ
- **RSI(period可調，預設14)**：Wilder 1978原始定義（EMA遞迴平滑版本，不是簡單移動平均）
- **MACD(12,26,9)**：DIF、訊號線、柱狀圖(histogram)

## 歷史回測（`scripts/backtest.py` + `scripts/run_backtest.py`）

除了「當下快照」，`backtest.py` 提供一整套(0)~(13b)編號的條件分類法歷史回測——單日急跌、
跌破MA(短/中/長，各含組合/剛跌破事件/純狀態三種)、RSI超賣(兩個門檻，各三種)、創新高/新低
（兩組窗口）、z-score偏離（每個MA週期各-1σ/-2σ），對每個條件算歷史觸發次數、跟可設定的多個
horizon（例如60/180/360日）forward報酬/勝率。CLI用法見`run_backtest.py`檔頭docstring。

**除息還原是回測正確性的關鍵**：這套回測邏輯2026-08-10從GoogleSheet.Banks的`投資決策分層.md`
收進本skill時，發現該文件先前用的資料來源完全沒做除息回溯還原（只有0050的股票分割手動修正過，
其餘除息缺口都沒處理）——高殖利率的停泊股尤其嚴重，除息缺口會被誤判成「單日跌深」污染急跌類
條件的統計，MA/RSI/z-score也會系統性偏移。全部改用本skill的`fetch_fugle_adjusted()`（正確
回溯調整除息+分割）重算後，基準勝率普遍大幅上升、部分訊號結論方向整個反轉（例如RSI(20)訊號
品質，修正前資料顯示「因股而異」，修正後資料顯示「全面優於RSI(14)、沒有例外」）——這是本skill
存在的核心理由：回測邏輯抽成可重跑工具，才不會讓資料品質問題悄悄污染分析結論而不自知。

## 讓消費端把RSI變成「即時公式」，不是每天重跑一次的靜態值

`indicators.py` 額外提供 `calc_rsi_state(close, period)`，回傳
`{last_close, avg_gain, avg_loss}`——RSI是遞迴定義（今天的平滑值=昨天的平滑值*(n-1)/n
+今天漲跌*1/n），只知道「現價」沒辦法重算，但只要把這三個值當輔助欄位存進試算表，
下游就能寫一條公式讓RSI隨盤中報價即時變動，不必每次報價跳動都重新登入API重算整條序列：

```
gain_today = MAX(現價-上一收盤價, 0)
loss_today = MAX(上一收盤價-現價, 0)
avg_gain_today = avg_gain*(period-1)/period + gain_today/period
avg_loss_today = avg_loss*(period-1)/period + loss_today/period
RSI = 100 - 100/(1 + avg_gain_today/avg_loss_today)
```

GoogleSheet.Banks 的 `update_zscore_stats.py` 是這個模式的參考實作：`calc_rsi_state()`
算出的三個值寫進輔助欄（每天一次），P欄（RSI顯示欄）本身則是引用「現價欄+這三個輔助欄」
的公式，達到即時重算。

## 為什麼需要這個技能——還原股價口徑問題

MA/STD/RSI/MACD 這些指標全部建立在「連續、乾淨」的收盤價序列上，只要序列裡有一個
除息或分割造成的價格跳空沒被回溯調整，跳空前後幾百天內算出來的均線/標準差/RSI/MACD
全部會失真（跳空當天附近的STD會被異常放大、MA會被拉偏、RSI/MACD在跳空日附近會出現
不存在的假訊號）。

實測發現：**yfinance `auto_adjust=True` 不保證正確處理所有台股除權息事件**——0052這檔
ETF在2025年11月有一次1:7分割，`yf.Ticker.splits`沒有登記，導致 auto_adjust 完全沒調整到，
算出來的MA240誤差超過2倍。這個技能改用 **Fugle API 手動回溯調整**當權威來源：

1. `historical.candles` 抓原始（未還原）OHLC
2. `corporate_actions.dividends`（除息）+ `corporate_actions.capital_changes`
   （減資/分割）抓事件（兩者都是全市場端點，本地依代號過濾）
3. 依 `referencePrice/previousClose` 比例，把「事件交易日之前」的收盤價全部乘上該比例
   （多筆事件依時間先後累積相乘）

yfinance 版本沒有拿掉，保留給 `--verify` 模式做交叉比對——只要看到報告裡差異過大，
代表其中一邊的還原口徑對不上，可以進一步排查。

## 資料來源可選（不是每個consumer repo都有Fugle憑證）

`--source fugle`（預設）跟 `--source yahoo` 二選一，決定輸出CSV的**主要**資料來源：

- **有Fugle/TaishinSDK憑證的repo**（例如本skill的來源專案GoogleSheet.Banks）：用預設的
  `--source fugle`，可以額外加 `--verify` 讓 yfinance 當第二個來源做交叉比對，兩邊都跑
  最完整、最能互相驗證。
- **沒有Fugle憑證的repo**：改用 `--source yahoo`，完全不需要TaishinSDK/broker帳密，直接
  用yfinance當唯一來源——代號要直接傳yfinance ticker格式（例如`0050.TW`、`2330.TW`），
  跟`--source fugle`模式下代號是「純Fugle symbol、不用後綴」不一樣，別搞混。這個模式下
  `--verify`沒有意義（沒有第二來源可比對），傳了會被忽略並印警告。

兩種模式的CSV輸出格式（FIELD_ORDER）完全一樣，差別只在資料口徑（Fugle手動回溯調整 vs
yfinance auto_adjust），下游程式不用因為換來源改讀取邏輯。

## 命令說明

| 命令格式 | 功能說明 |
|---------|--------|
| `python <SKILL_DIR>/scripts/run_indicators.py --symbols 0050 0052 2330 --fugle-env-prefix USER1_ --output out.csv` | Fugle為主要來源（預設），直接指定代號清單 |
| `python <SKILL_DIR>/scripts/run_indicators.py --list StockID.csv --fugle-env-prefix USER1_ --output out.csv` | 從CSV讀取代號清單（欄位：代號/symbol/stock_code，可選yahoo_symbol） |
| `python <SKILL_DIR>/scripts/run_indicators.py --source yahoo --symbols 0050.TW 2330.TW --output out.csv` | 只用yfinance，不需要任何Fugle憑證，代號要直接是yfinance ticker |
| 加上 `--verify` | 額外抓yfinance版本，印出跟Fugle版本的RSI(14)/z-score(MA240)差異報告（不影響輸出CSV；只對CSV裡有yahoo_symbol欄的代號生效） |
| `--years N`（預設2） | 還原股價回溯年數，2年足夠算MA240/RSI14/MACD的暖機視窗 |

## 使用範例

```bash
# 從consumer repo根目錄執行（.env裡的FUGLE_USER1_*會被自動讀到）
python skills/skill-stock-MA-RSI-BBand-MACD/scripts/run_indicators.py \
  --symbols 0050 0052 2330 2357 \
  --fugle-env-prefix USER1_ \
  --output output/ma_rsi_bband_macd.csv \
  --verify
```

## 環境需求

| 需求 | 用途 |
|------|------|
| `taishin_sdk`（`pip install taishin_sdk`，內部依賴 `fugle-marketdata`） | Fugle 還原股價登入與資料下載 |
| `FUGLE_{prefix}PERSONAL_ID` / `PASSWORD` / `CERT_PASS` / `CERT_B64`(或`CERT_PATH`) | TaishinSDK 登入憑證（跟券商/複委託帳號一致），環境變數或 `.env` 皆可 |
| `yfinance`（`--verify` 才需要） | 交叉比對來源 |
| `python-dotenv`（選用） | 自動讀取consumer repo根目錄的`.env`；用`find_dotenv(usecwd=True)`定位，避免搜到skill自己所在的目錄樹 |

TaishinSDK 登入有明顯開銷（憑證交握，通常幾秒到十幾秒），**不建議每次盤中報價更新都重跑**——
MA/STD/RSI/MACD 本來就是日頻指標，同一天內不會因為報價跳動而改變，建議一天執行一次即可
（例如排程在收盤後或隔天開盤前）。

## 輸出契約

CSV 欄位（固定順序）：

```
symbol, close,
MA20, STD20, zscore_MA20, MA60, STD60, zscore_MA60,
MA120, STD120, zscore_MA120, MA240, STD240, zscore_MA240,
BB20_upper, BB20_mid, BB20_lower,
RSI14,
MACD_dif, MACD_signal, MACD_hist
```

暖機資料不足（少於20筆日線）的代號，除了`symbol`欄以外全部留空。

## 已知限制

- Fugle `historical.candles` 單次查詢上限1年，`from`參數必須用 `**{"from": ...}` 字典展開
  傳入（Python `from_=` 這個kwarg名字會被API安靜忽略，退回一個很短的預設區間，不會報錯，
  容易誤判成「資料真的只有這麼少」）。
- `corporate_actions.dividends` / `capital_changes` 是全市場端點，不接受symbol篩選，
  批次處理多檔代號時建議只呼叫一次涵蓋整段查詢範圍、在本地過濾（`run_indicators.py`
  已經這樣做，`fetch_fugle_market_adjustment_events()`只會呼叫一次）。
- `--verify`用的yfinance來源已知對部分台股ETF分割事件還原不完整，只拿來當警示訊號，
  不建議直接採用yfinance版本的數字。
- 需要有效的台新/複委託帳號憑證才能用Fugle來源；沒有憑證時只能退化成純yfinance模式
  （目前`run_indicators.py`還沒有實作「只跑yfinance當主要來源」的模式，只有`--verify`
  比對用途，如果要支援離線/無憑證場景需要額外擴充）。
