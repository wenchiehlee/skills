# 季度損益預測 SOP (Quarterly Revenue · Expense · Profit Bottom-Up Forecast)

本文件定義 `biztrends.TW` 框架下，針對任意台灣上市櫃股票執行「**季度損益三線（營業收入 / 總支出 / 營業利益）預測、滾動回測、產業週期分段修正與視覺化**」的標準作業程序（SOP）。

對應的核心執行腳本為：
```
biztrends.TW/scripts/generate_quarterly_predict.py
```
執行後輸出至 `biztrends.TW/output/` 目錄的產物包含：
- `quarterly_predict_{股票代號}.png` — **損益三線預測圖（本技能主視覺）**
- `quarterly_cycle_breakdown_{股票代號}.png` — 產業週期分段堆疊面積圖
- `quarterly_predict_report_{股票代號}.md` — 文字摘要報告

---

## 1. 技能應用場景與觸發條件

| 觸發關鍵字 | 說明 |
|:---|:---|
| 「預測 [StockID] 季度損益」 | 執行三線預測並輸出圖表 |
| 「分析 [StockID] 季度展望」 | 含共識差距分析（Yahoo / FactSet） |
| 「[StockID] 季度利潤預測」 | 利用會計恆等式：利益 = 收入 − 支出 |
| 「[StockID] 自下而上預測」 | 以產業週期分段加權後匯總 |

---

## 2. 核心架構：三線預測工作流程

```
資料載入 (raw_performance1.csv)
    ↓
季度三線提取：Revenue / Expense / Profit
    Expense = Revenue − Operating Profit         ← 會計恆等式
    ↓
產業週期權重載入 (tw_major_company_cycle_weights.csv)
    支援動態歷史權重插值 (Solution A: True-of-Source)
    ↓
逐段拆解：segment_revenue[c] = total_revenue × w_c(t)
           segment_expense[c] = total_expense × w_c(t)
    ↓
各段獨立執行 10-Model Pipeline (Walk-Forward, 回測期=12Q)
    ├── 收入模型選優：min(MAPE)，可被 SEGMENT_MODEL_OVERRIDES 覆蓋
    └── 支出模型選優：min(MAPE)，可被 SEGMENT_MODEL_OVERRIDES 覆蓋
    ↓
MPE 偏差修正 + 產業乘數 (Solution C: CYCLE_MULTIPLIERS)
    future_corr_rev[c] = future_raw × (1 + MPE%) × cycle_mult
    future_corr_exp[c] = future_raw × (1 + MPE%) × cycle_mult
    ↓
自下而上匯總 (Solution B: Bottom-Up Summation)
    total_future_rev = Σ future_corr_rev[c]
    total_future_exp = Σ future_corr_exp[c]
    total_future_prof = total_future_rev − total_future_exp   ← 恆等式保持
    ↓
共識基準整合：Yahoo / FactSet consensus (載入 CSV, 依公告日對齊)
    ↓
生成輸出
    quarterly_predict_{code}.png           ← 損益三線預測主圖
    quarterly_cycle_breakdown_{code}.png   ← 週期分段堆疊圖
    quarterly_predict_report_{code}.md     ← Markdown 報告
```

---

## 3. 10 種季度預測模型（PERIOD = 4）

所有模型均以**季度**為單位（Period = 4），分別對 Revenue 與 Expense 各段獨立評估：

| # | 模型名稱 | 核心公式 |
|:---:|:---|:---|
| 1 | Seasonal Naive | Ŷ(t+k) = Y(t+k-4) |
| 2 | YoY Growth Adjusted | Ŷ(t+k) = Y(t+k-4) × (1 + avg_YoY) |
| 3 | Linear Trend | Ŷ(t+k) = a(t+k) + b |
| 4 | AR(1) Rolling | Y(t) = φ₁Y(t-1) + c |
| 5 | Seasonal Decomposition | Trend(adj) × S_q |
| 6 | Holt Linear (Double) | L(t) = αY(t) + (1-α)(L(t-1)+T(t-1)) |
| 7 | Holt-Winters Multiplicative | 三重指數平滑含乘法季節因子（需 N≥12） |
| 8 | WMA-3 | (3Y(t) + 2Y(t-1) + Y(t-2)) / 6（滾動） |
| 9 | Fourier Seasonal | β₀ + β₁t + β₂cos(2πt/4) + β₃sin(2πt/4) |
| 10 | AR(2) Rolling | Y(t) = φ₁Y(t-1) + φ₂Y(t-2) + c |

每一個**產業週期段（Segment）** 均對 Revenue 與 Expense **各自獨立**跑完 10 種模型，選出最低 MAPE 的模型，再套用 MPE 修正與產業乘數。Profit 不直接預測，而是由 `Revenue − Expense` 的會計恆等式推導，確保三線數學一致。

---

## 4. 產業週期段與乘數（CYCLE_MULTIPLIERS）

| 週期段 | 乘數 | 說明 |
|:---|:---:|:---|
| AI_Compute_Infra | 1.25 | AI 伺服器基礎設施高速成長 |
| AI_Compute | 1.25 | AI 算力核心晶片 |
| Memory | 1.08 | 記憶體景氣修復 |
| Software_SaaS | 1.10 | 軟體訂閱持續成長 |
| EV_Automotive | 1.05 | 電動車穩步增長 |
| Network_Infra | 1.03 | 網路基礎設施 |
| Consumer_IoT | 1.02 | 消費物聯網平穩 |
| Smartphone | 1.01 | 智慧手機成熟市場 |
| PC_Consumer | 0.98 | 消費 PC 略微衰退 |
| Other | 1.00 | 中性假設 |

---

## 5. 模型覆蓋（SEGMENT_MODEL_OVERRIDES）

針對特定股票的特定段，可強制指定使用某一模型（覆蓋 min-MAPE 自動選擇）：

```python
SEGMENT_MODEL_OVERRIDES = {
    "2382": {
        "revenue": {"AI_Compute_Infra": "YoY Growth Adjusted", "PC_Consumer": "WMA-3", ...},
        "expense": {"AI_Compute_Infra": "YoY Growth Adjusted", "PC_Consumer": "WMA-3", ...}
    },
    "2357": {
        "revenue": {"AI_Compute_Infra": "YoY Growth Adjusted", ...},
        "expense": {"AI_Compute_Infra": "YoY Growth Adjusted", ...}
    }
}
```

新增覆蓋規則時，只需在此字典中加入目標 `stock_code → segment → model_name` 對應即可。

---

## 6. quarterly_predict_*.png 圖表結構說明

圖表由腳本第 891–1082 行的 `generate_plots_and_report()` 函式產生，儲存路徑：
```python
plot_path1 = os.path.join(OUTPUT_DIR, f"quarterly_predict_{stock_code}.png")
plt.savefig(plot_path1)
```

圖表呈現 **24 季歷史 + 4 季未來**，共 28 個季度：

| 圖層 | 顏色 | 說明 |
|:---|:---:|:---|
| 真實營業收入（實線●） | 黑色 | 歷史已公告數據 |
| 真實總支出（實線■） | 紅色 #e53935 | Revenue − Profit |
| 真實營業利益（實線◆） | 深綠 #2e7d32 | 歷史已公告數據 |
| 營收預測（虛線） | 藍色 #1f77b4 | 自下而上融合預測 |
| 支出預測（虛線） | 橙色 #ff7f0e | 自下而上融合預測 |
| 利益預測（虛線） | 綠色 #4caf50 | 由恆等式推導 |
| Yahoo 共識基準（點線★） | 紫色 #9c27b0 | 外部共識對標 |
| FactSet 共識基準（點虛線★） | 深藍 #3f51b5 | 外部共識對標 |
| 共識分歧帶（fill_between） | 藍色半透明 | FactSet vs 模型預測之差距 |

背景區段：
- **灰色（前12Q）**：模型暖機期（Warm-up）
- **黃色（中12Q）**：滾動回測期（Walk-Forward Validation）
- **綠色（後4Q）**：未來前瞻預測期（Future Forecast）

---

## 7. 輸出報告嵌入語法

在 Markdown 報告或 MkDocs 頁面中嵌入本技能產出圖表：

```markdown
![季度損益預測圖](../output/quarterly_predict_2330.png)
![週期分段堆疊圖](../output/quarterly_cycle_breakdown_2330.png)
```

或在 Artifact 中使用絕對路徑：
```markdown
![季度損益預測](file:///C:/Users/WJLEE/SynologyDrive/NAS/github.com/biztrends.TW/output/quarterly_predict_2330.png)
```

---

## 8. 執行方式

```bash
# 單一股票
python scripts/generate_quarterly_predict.py 2330

# 批次執行（由 main() 讀取 stock list）
python scripts/generate_quarterly_predict.py
```

所需資料來源（放置於 `biztrends.TW/data/`）：

| 檔案 | 內容 |
|:---|:---|
| `Python-Actions.GoodInfo.Analyzer/raw_performance1.csv` | 季度損益原始數據（revenue / profit） |
| `tw_major_company_cycle_weights.csv` | 各公司主要產業週期權重（附期間） |
| `tw_company_cycle_mapping.csv` | 公司代號 → canonical_cycle 映射 |
| `tsm_platform_revenue.csv`（選用） | 台積電各平台比例（真實揭露數據） |

---

## 9. 與 skill-revenue-predict 的差異比較

| 項目 | skill-revenue-predict | skill-revenue-expense-profit-predict |
|:---|:---|:---|
| 預測維度 | 月度收入單線 | 季度收入 / 支出 / 利益三線 |
| 時間粒度 | 月（PERIOD=12） | 季（PERIOD=4） |
| 利益計算 | 不包含 | 由恆等式推導 |
| 產業週期 | 無分段加權 | 有分段加權（Bottom-Up） |
| 外部共識 | 無 | Yahoo / FactSet 共識整合 |
| 主輸出圖 | revenue_predict_*.png | quarterly_predict_*.png |

---

此檔案為 `skill-revenue-expense-profit-predict` 的標準化說明（`SKILL.md`），
請放入 `skills/common/skill-revenue-expense-profit-predict/` 目錄，
並確保 `biztrends.TW/skills/skill-revenue-expense-profit-predict/` 保持與此目錄同步。
