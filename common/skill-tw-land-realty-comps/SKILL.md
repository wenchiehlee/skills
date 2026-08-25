---
name: skill-tw-land-realty-comps
description: 下載並彙整內政部實價登錄季資料，篩選指定地號/門牌周邊的土地或房屋成交紀錄，輸出近鄰統計、同棟/同段明細、年度活動與加權估值，供土地資產分析使用。
---

# 台灣不動產成交比對技能 (tw-land-realty-comps)

| 項目 | 內容 |
| :--- | :--- |
| 版本 | 1.1.0（詳見 `metadata.json`） |
| 來源 | https://github.com/wenchiehlee-money/LandAsset |
| 登錄庫 | https://github.com/wenchiehlee/skills （`common/skill-tw-land-realty-comps`） |
| 維護者 | wenchiehlee-money |

此技能封裝「內政部不動產成交案件實際資訊資料供應系統」（實價登錄，
https://plvr.land.moi.gov.tw/DownloadSeason）的下載、篩選與彙整流程，
取代過去在各 `Images/*.md` 分析頁裡手動下載 CSV、手動篩選門牌/日期、
手動算分位數的做法。

**同一支腳本同時支援土地與房屋分析**，不區分成獨立 skill：篩選條件
（`require_building` / `require_land`）由 `targets.json` 逐一設定，
交易標的欄位（`土地` / `建物` / `房地(土地+建物)` / `房地(土地+建物)+車位`
/ `車位`）本身就同時涵蓋兩種資產類型。

## 📦 技能結構說明

```text
tw-land-realty-comps/
├── SKILL.md                        # 技能描述與對接指引（本檔案）
├── metadata.json                   # 機器可讀 metadata，供版本檢查使用
├── self_update.py                  # 從 skills 登錄庫檢查並更新此技能的工具（上傳前為 no-op）
├── scripts/
│   ├── fetch_realty_season.py      # 下載實價登錄季資料 zip，快取指定縣市/交易類型 CSV
│   ├── fetch_price_index.py        # 抓政大信義不動產研究中心的區域單價指數，供時間效應校正
│   └── build_realty_comps.py       # 篩選/彙整快取 CSV，輸出比對 CSV + Markdown 報告
└── examples/
    ├── targets.example.json        # 目標設定檔範例（虛構資料，勿填真實地址）
    └── price_index.example.json    # 區域單價指數檔格式範例
```

## ⚙️ 前置環境配置

- 系統需安裝 `curl`（`fetch_realty_season.py` 透過 `curl` 子行程下載季資料 zip）。
- Python 標準函式庫即可，不需額外套件。

## 🚀 使用方式

### 步驟 1：準備 targets.json

複製 `examples/targets.example.json` 到專案內（例如 `data/realty_comps/targets.json`），
改成實際要分析的地號/門牌設定。**真實地址等私有資料只放在專案內的設定檔，
不要複製進這個 skill 的 `examples/`，也不要上傳到公開的 skills 登錄庫**
（比照 `skill-tw-land-geo-signal` 對 `targets.json` 的處理原則）。

主要欄位：

| 欄位 | 說明 |
| :--- | :--- |
| `target_id` | 短代號，沿用在輸出檔名 |
| `city_code` | 內政部實價登錄縣市代碼（如桃園市=`H`） |
| `asset_code` | 交易類型代碼，`A`=買賣 `B`=租賃 `C`=預售屋，預設 `A` |
| `district` | 鄉鎮市區篩選 |
| `road_keyword` | 地址需包含的路名關鍵字 |
| `require_building` / `require_land` | 是否限定交易標的含建物／含土地 |
| `date_from` / `date_to` | 交易日期篩選（ISO 格式） |
| `house_no` | 目標門牌號（用於算門牌號差） |
| `scopes` | 近鄰範圍清單，每項含 `label` 與 `house_no_diff_max`（`null`＝不限） |
| `building_group_house_nos` | 同棟/同段門牌群組，用於列出明細 |
| `yearly_scope_house_no_diff_max` | 年度統計採用的門牌號差範圍 |
| `valuation` | 加權估值設定，見下方「加權估值設定欄位」 |

#### 加權估值設定欄位（`valuation`）

| 欄位 | 說明 |
| :--- | :--- |
| `require_parking` | 是否限定含車位交易才計入估值母體 |
| `floor_min` / `floor_max` | 目標戶樓層範圍，用來算 `target_floor`（兩者平均） |
| `size_ping` | 目標戶坪數，用於算總價估值與坪數距離權重 |
| `floor_decay` / `size_decay` | 樓層/坪數每差 1 單位（樓層=1層、坪數=`size_halflife_ping`坪）的權重衰減率，預設 `0.85` |
| `size_halflife_ping` | 坪數權重衰減的單位級距（坪），預設 `5` |
| `top_k` | 列出最相似的前 K 筆做交叉檢查，預設 `4` |
| `price_index_file` | （建議設定）區域單價指數檔路徑，見下方「時間效應校正」；設定後改用真實市場指數換算歷史成交，不設定則退回時間衰減近似法 |
| `price_index_target_quarter` | 換算目標季度，預設用指數檔內最新一季 |
| `time_halflife_years` | 僅在**未設定** `price_index_file` 時生效：時間衰減半衰期（年），預設 `3` |
| `date_from` | 估值母體的交易日期下限（可選） |

### 步驟 2：下載/更新實價登錄季資料快取

```bash
python scripts/fetch_realty_season.py \
  --city-codes H \
  --asset-codes A \
  --year-from 105 --year-to 114 \
  --out-dir data/realty_comps/raw
```

- `season` 格式為「民國年+S+季別」（如 `114S4`）；本腳本會抓 `year-from`~`year-to`
  範圍內所有季別，尚未公開的未來季會自動跳過並提示。
- 已快取的季別預設略過，加 `--force` 可強制重抓覆寫。
- 下載來源為全國 zip（單一 zip 內含各縣市 x 各交易類型 CSV），本腳本只解壓需要的
  `{縣市代碼}_lvr_land_{交易類型代碼}.csv` 存入 `<out-dir>/<city_code>/<asset_code>/<season>.csv`。

### 步驟 3：（建議）抓區域單價指數，供加權估值做真實時間效應校正

```bash
python scripts/fetch_price_index.py \
  --county-district 桃園市桃園區 \
  --start-year 2016 --start-month 1 \
  --end-year 2026 --end-month 7 \
  --fetched-at 2026-07-25 \
  --out data/realty_comps/price_index_taoyuan_taoyuan.json
```

- 資料來源：政大商學院信義不動產研究發展中心實登統計
  （<https://restat.ncscre.nccu.edu.tw/>），彙整自內政部實價登錄，免費、無需登入、
  無 Cloudflare 防護，但對 `User-Agent` 含 `curl` 的請求會回應 500，本腳本已內建
  瀏覽器風格的 `User-Agent`。
- `--county-district` 需與網站選單文字一致（例如「桃園市桃園區」），拼字錯誤會
  導致抓不到資料或回傳空序列。
- 輸出檔案裡的 `caveat_車位` 欄位會說明：這個指數是該行政區「全部買賣交易」
  （含車位與不含車位混合）的單價統計，**不是**乾淨分離的含車位/不含車位序列，
  只適合當作區域房價整體走勢的時間校正基準；個別交易的車位可比性，仍由
  `build_realty_comps.py` 的 `require_parking` 篩選（依各筆交易的「交易標的」
  欄位）處理，兩者職責不同、不要混用。
- 把輸出路徑填入 `targets.json` 的 `valuation.price_index_file`，`build_realty_comps.py`
  就會改用真實市場指數換算時間效應，不再用武斷的時間衰減假設。

### 步驟 4：彙整比對 CSV 與 Markdown 報告

```bash
python scripts/build_realty_comps.py \
  --raw-dir data/realty_comps/raw \
  --targets-file data/realty_comps/targets.json \
  --target-id 782_11F \
  --out-dir data/realty_comps
```

輸出：
- `<out-dir>/<target_id>_matched.csv`：符合篩選條件的成交明細（含推算的萬/坪單價、
  建物坪數、最低移轉樓層等欄位），供後續自訂分析。
- `<out-dir>/<target_id>_report.md`：近鄰範圍統計表、同棟/同段明細表、年度活動表、
  加權估值表（格式比照既有 `Images/782_11F.md` 的表格結構），可直接貼入對應的
  `Images/*.md` 分析頁。

## 📐 計算口徑

- 單價 `萬/坪 = 單價元平方公尺 × 3.305785 / 10000`。
- 建物面積 `坪 = 建物移轉總面積平方公尺 / 3.305785`。
- 門牌號取地址字串中最後一個「數字+號」片段（處理全形數字）。
- 移轉樓層取該筆交易列出樓層中的最小值（中文數字轉換，`全` 視為無法判斷樓層）。
- **加權估值**（`weighted_valuation()`）採「樓層 x 坪數」距離連續加權，不做任何
  單一因子的硬性篩選：
  - `w_floor = floor_decay ** abs(floor - target_floor)`（每差 1 層權重衰減）
  - `w_size = size_decay ** (abs(ping - size_ping) / size_halflife_ping)`（每差
    `size_halflife_ping` 坪權重衰減）
  - 若設定 `price_index_file`：時間效應改用真實市場指數把每筆歷史成交換算成
    `price_index_target_quarter` 等值價格（`市場基準換算單價 = 原始單價 x
    指數[目標季] / 指數[成交季]`），此時不再對「新舊」本身給權重——避免單一
    個案的異常新高價被誤判成市場整體漲幅（實測案例：某筆最新成交單價遠高於
    當季區域中位數，換算後才看得出是個案溢價、不是市場水準，見
    `Images/782_11F.md` 第10節）。
  - 若未設定 `price_index_file`：退回 `w_time = 0.5 ** (years_ago / time_halflife_years)`
    的時間衰減近似法，準確度不如真實指數。
  - 輸出「全母體距離加權平均」（所有可比交易，越不相似權重越低）與「Top-K
    最相似樣本加權平均」（只看距離最近的少數樣本）兩種口徑互相交叉檢查。
  - 此為透明、可調整、可重現的近似方法，非法定鑑價依據，僅供決策參考。

## 🔒 資料性質與隱私

- 實價登錄季資料為內政部依法公開之去識別化資料（不含買賣雙方姓名、身分證等個資，
  僅含門牌、面積、價格、格局等交易資訊），可安全快取與版本控制；但檔案量體較大，
  建議在使用端專案的 `.gitignore` 排除原始快取目錄（如 `data/realty_comps/raw/`），
  彙整後的 CSV/Markdown 報告再視需要納入版控。
- `targets.json` 內的地號/門牌等分析標的屬於各使用端專案的私有資料，僅存在於
  該私有 repo，切勿複製進公開的 skills 登錄庫或本技能的 `examples/`。

## 🔄 版本管理與更新

- 本技能的唯一可信來源為 skills 登錄庫中的 `common/skill-tw-land-realty-comps`；
  各專案（LandAsset 等）內的副本皆由登錄庫部署而來。
- 版本採語意化版本（`MAJOR.MINOR.PATCH`），記錄於 `metadata.json` 的 `version` 欄位。
- 檢查並更新到登錄庫最新版本：在技能資料夾內執行
  ```bash
  python self_update.py
  ```
  僅當登錄庫版本較新時才會覆寫本地檔案。
- 修改此技能時，請先更新登錄庫中的版本（並提升版本號），再部署到各使用端專案，避免副本之間出現分歧。
