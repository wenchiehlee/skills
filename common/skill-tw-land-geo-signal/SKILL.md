---
name: skill-tw-land-geo-signal
description: 查詢桃園市 TY_UPGIS 圖層與內政部 easymap 地號官方地圖，彙整地號周邊指定半徑的城市信號 CSV 與疊圖 PNG，供土地資產分析使用。
---

# 台灣地號周邊城市信號技能 (tw-land-geo-signal)

| 項目 | 內容 |
| :--- | :--- |
| 版本 | 1.0.0（詳見 `metadata.json`） |
| 來源 | https://github.com/wenchiehlee-money/LandAsset |
| 登錄庫 | https://github.com/wenchiehlee/skills （`common/skill-tw-land-geo-signal`） |
| 維護者 | wenchiehlee-money |

此技能封裝兩條獨立的地號地理資料查詢流程，供分析特定座標點周邊城市發展信號（都市計畫案件、都市設計審議範圍等）與取得官方地籍地圖快照：

1. **TY_UPGIS 城市信號**（`fetch_tyupgis_layers.py` + `build_city_signal.py`）：查詢桃園市都市發展局 TY_UPGIS MapServer 圖層，找出目標座標半徑內的案件位置點位（如甲乙工變更申請、容積移轉、都市設計審議範圍），彙整成 CSV 與疊圖 PNG。
2. **easymap 官方地籍快照**（`easymap_snapshot.py`）：呼叫內政部地政司 easymap，依地政事務所代碼/段小段/地號取得官方地籍圖與電子地圖底圖疊合的快照。

兩者資料源、驗證方式（bbox 查詢 vs. token+cookie 表單）與輸出用途完全不同，因此各自獨立成一支腳本，而非合併成單一 CLI 子命令。

## 📦 技能結構說明

```text
tw-land-geo-signal/
├── SKILL.md                       # 技能描述與對接指引（本檔案）
├── metadata.json                  # 機器可讀 metadata，供版本檢查使用
├── self_update.py                 # 從 skills 登錄庫檢查並更新此技能的工具
├── scripts/
│   ├── fetch_tyupgis_layers.py    # 抓取 TY_UPGIS 圖層原始 JSON 快照
│   ├── build_city_signal.py       # 彙整快照為 CSV + 產生疊圖 PNG
│   └── easymap_snapshot.py        # 內政部 easymap 地號官方地圖快照
└── examples/
    ├── targets.example.json       # 目標座標點設定檔範例
    ├── layers.example.json        # TY_UPGIS 圖層設定檔範例
    └── stations.example.json      # 可選的地圖參考站點標籤範例
```

## ⚙️ 前置環境配置

### 1. 安裝 Python 套件依賴

```bash
pip install Pillow
```

### 2. 系統需安裝 `curl`

`fetch_tyupgis_layers.py` 與 `build_city_signal.py` 的底圖抓取皆透過 `curl` 子行程呼叫（沿用原始腳本的 retry/DNS resolve 邏輯），請確認執行環境已安裝。

### 3.（可選）DNS 解析覆寫

若 `urbandatasrv.tycg.gov.tw` 在執行環境中需要指定 IP 才能連線，設定環境變數：

```env
TY_UPGIS_HOST_IP=<ip-address>
```

## 🚀 使用方式

### 步驟 1：準備 targets/layers 設定檔

複製 `examples/targets.example.json`、`examples/layers.example.json` 到你的專案，改成實際要分析的地號座標與圖層。`target_id` 建議採用可讀的短代號（如地號編號或案件代碼），會沿用在快取檔名與 CSV 的 `target_id` 欄位，方便跨檔案追蹤同一標的。

### 步驟 2：抓取 TY_UPGIS 原始快照

```bash
python scripts/fetch_tyupgis_layers.py \
  --targets-file targets.json \
  --layers-file layers.json \
  --out-dir data/city_signal_2km/raw_json \
  --radius-m 2000
```

只需重抓單一 target：加 `--target-id example-A`。

### 步驟 3：彙整 CSV 與疊圖 PNG

```bash
python scripts/build_city_signal.py \
  --targets-file targets.json \
  --layers-file layers.json \
  --raw-dir data/city_signal_2km/raw_json \
  --out-root data/city_signal_2km \
  --images-dir Images
```

輸出：
- `<out-root>/city_signal_2km_counts.csv`：每 target × layer 的圖徵數量與狀態。
- `<out-root>/city_signal_2km_feature_points.csv`：每個圖徵的座標與 key，供後續分析。
- `<out-root>/city_signal_2km_maps.csv`：各 target 產出的地圖檔路徑與 bbox。
- `<images-dir>/city_signal_2km_<target_id>_layers.png`：底圖 + 2km 範圍圈 + 各圖層點位疊圖。

只重繪地圖、不重寫 CSV：加 `--render-only`；若要在地圖上標示參考站點（如鄰近捷運站，僅供距離感參考），加 `--stations-file stations.json`（格式見 `examples/stations.example.json`）。

### 步驟 4（可選）：兩個 target 之間的圖層重疊/獨有分析

不需要專用腳本，直接對 `city_signal_2km_feature_points.csv` 依 `target_id`、`layer_id`、`feature_key` 做集合運算即可：

```python
import pandas as pd

df = pd.read_csv("data/city_signal_2km/city_signal_2km_feature_points.csv")
layer_id = 54
keys_a = set(df[(df.target_id == "example-A") & (df.layer_id == layer_id)].feature_key)
keys_b = set(df[(df.target_id == "example-B") & (df.layer_id == layer_id)].feature_key)

overlap = keys_a & keys_b
only_a = keys_a - keys_b
only_b = keys_b - keys_a
```

### 步驟 5：內政部 easymap 官方地籍快照

```bash
python scripts/easymap_snapshot.py \
  --office <地政事務所代碼> --sect <段小段代碼> --land <地號> \
  --out Images/easymap_<地號>.png
```

## 🛡️ 穩健性設計

- `fetch_tyupgis_layers.py` 透過 `curl --retry` 處理暫時性網路失敗；下載先寫入 `.tmp` 檔再原子性 rename，避免中斷產生半殘檔。
- `build_city_signal.py` 的底圖快取（`background_cache/`）會重複使用，避免每次重繪都重新打 export API；加 `--refresh-background` 強制更新。
- 兩支腳本皆將 target/layer 設定外部化為 JSON，不寫死在程式碼內，換分析標的不需要改程式，只需換設定檔。

## 🔄 版本管理與更新

- 本技能的唯一可信來源為 skills 登錄庫中的 `common/skill-tw-land-geo-signal`；各專案（LandAsset 等）內的副本皆由登錄庫部署而來。
- 版本採語意化版本（`MAJOR.MINOR.PATCH`），記錄於 `metadata.json` 的 `version` 欄位。
- 檢查並更新到登錄庫最新版本：在技能資料夾內執行
  ```bash
  python self_update.py
  ```
  僅當登錄庫版本較新時才會覆寫本地檔案。
- 修改此技能時，請先更新登錄庫中的版本（並提升版本號），再部署到各使用端專案，避免副本之間出現分歧。
