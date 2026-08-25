---
name: skill-stock-topcrash
description: 任意指數/股票在指定年份範圍內的「崩盤Top N」清單——1/3/5/7/9/11日跌幅、事件標籤、VIX/CNN恐慌貪婪情境、恢復天數與形態(V/U修復)，輸出CSV。
---

# Stock Top Crash Skill

對任一 yfinance ticker（預設台灣加權指數 `^TWII`）在指定年份範圍內，找出最嚴重的
N 次崩盤事件，附完整情境 metadata，輸出成一個CSV。

## 判定邏輯

1. **崩盤偵測**：對每個交易日算 1/3/5/7/9/11 日報酬，六者最小值當「這天最壞表現」，
   全樣本依最壞表現排序，依序選入直到湊滿 top-n。
2. **去重**：同一個具名事件（見下方「事件標籤」）只取最壞的一筆；沒有具名標籤的
   「其他」事件用日期間隔（預設10天）去重，避免同一波段連續好幾天都上榜。
3. **事件標籤**（可選）：可傳入具名大事件清單（JSON）+ 細粒度事件CSV，兩層比對，
   都沒命中就標「其他」；兩個輸入都不給的話全部標「其他」，只做日期去重。
4. **VIX/CNN情境**（可選）：需要一份VIX/CNN合併CSV，補上崩盤日前5/3/1日跟當日的
   US VIX、台灣VIX、當日CNN恐慌貪婪指數，每個數值都帶標籤（例如「72.0 (非理性恐慌)」）。
5. **恢復天數/形態**：以崩盤日前N天（預設120天）內最高收盤價當參考價，往後找第一個
   收盤價回到這個參考價的交易日，天數≤45算V修復（快速反彈），否則算U修復（緩慢/
   長期修復），資料涵蓋範圍內都沒回到參考價則標「未恢復」。詳細方法論與已知限制見
   `scripts/recovery.py` 檔頭註解。

## 命令說明

| 參數 | 說明 |
|------|------|
| `--symbol` | yfinance ticker，預設`^TWII`（可以是任何股票/ETF/指數） |
| `--start` / `--years` | 年份範圍，二擇一（`--years 10`＝回溯10年到今天） |
| `--top-n` | 取前幾名（預設50） |
| `--min-drop` | 最壞跌幅門檻%，低於此值才列入（預設-3.0） |
| `--events-csv` | 細粒度事件CSV（欄位：事件名稱,開始日期,結束日期） |
| `--named-events-json` | 具名大事件JSON（優先於events-csv） |
| `--vix-csv` | VIX/CNN合併CSV（欄位：Date,US_VIX,Taiwan_VIX,CNN_FG），不給就不輸出VIX情境欄位 |
| `--recovery-lookback-days` | 恢復天數參考價的回溯視窗（日曆天，預設120） |
| `--output` | 輸出CSV路徑 |

## 使用範例

```bash
# TAIEX 近10年崩盤Top50，含VIX情境跟具名事件
python skills/skill-stock-topcrash/scripts/run_topcrash.py \
  --symbol ^TWII --years 10 --top-n 50 --min-drop -3.0 \
  --vix-csv data/VIX/raw_vix_merged.csv \
  --events-csv data/InvestorEvents/raw_event_historical_crashes.csv \
  --named-events-json named_events.json \
  --output output/crash_top50.csv

# 任意個股（例如0050），不需要VIX/事件輸入，純技術面偵測
python skills/skill-stock-topcrash/scripts/run_topcrash.py \
  --symbol 0050.TW --start 2016-01-01 --top-n 20 --output output/0050_crash.csv
```

`named_events.json` 格式：

```json
[
  {"name": "全球COVID 2020/2", "start": "2020-01-30", "end": "2021-06-30"},
  {"name": "Fed升息 2022/1", "start": "2022-01-17", "end": "2023-03-31"}
]
```

## 輸出契約

CSV 欄位（固定順序，跟原始GoogleSheet.Banks「崩盤Top50」分頁一致）：

```
排名, 最壞日期, 單日跌幅%, 3日跌幅%, 5日跌幅%, 7日跌幅%, 9日跌幅%, 11日跌幅%,
最大跌幅%, 跌幅類型, 當日收盤, 事件,
前5日 US VIX, 前3日 US VIX, 前1日 US VIX, US VIX,
前5日 台灣VIX, 前3日 台灣VIX, 前1日 台灣VIX, 台灣VIX, CNN恐慌,
恢復天數, 恢復形態(≤45天=V)
```

沒給 `--vix-csv` 時，VIX/CNN 那9個欄位不會出現在輸出CSV裡（不是留空，是整組欄位不存在）。

## 已知限制

- 恢復天數/形態的計算方法（崩盤前N日內最高收盤價當參考）是自行設計、經5筆已知案例
  （COVID/Fed升息/日圓崩盤/台灣COVID/Trump關稅）驗證過4/5完全吻合，1筆（Fed升息2022，
  一段長達478天的緩慢修復期）有落差、原因未查出——長期U型修復事件的恢復天數精確度
  比V型修復事件低，數字可用但要打折。
- VIX分級門檻（`vix_context.py`裡的`label_vix`/`label_cnn`）是從既有資料反推校準，
  不是官方公告的分級標準。
- 「未恢復」不代表「永遠不會恢復」，只代表在目前抓到的資料範圍內還沒回到參考價，
  資料範圍(`--end`)愈接近現在，最近幾筆崩盤事件愈容易被標成「未恢復」（因為還沒過
  足夠的時間），這是正常現象不是bug。
- `--symbol` 傳非台股/非TWII的標的（例如美股ETF）時，VIX情境欄位（US VIX/台灣VIX）
  的意義可能不對應（例如分析美股崩盤卻附上台灣VIX），要不要用VIX情境欄位取決於
  分析對象跟台股/美股市場的關聯性，本模組不會自動判斷。
