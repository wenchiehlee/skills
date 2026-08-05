# 多模型與分析師共識效能評估標準作業程序 (Models vs Consensus Benchmarking SOP)

本文件定義了 `biztrends.TW` 框架下，針對自建之 10 個統計預測模型與市場兩大共識指標（Yahoo Finance 與 FactSet）進行「歷史預測精準度對比、勝率統計、平均誤差縮減分析」的標準作業程序（SOP）。未來任何 Coding Agent 或數據分析人員在執行效能評估任務時，均應遵循此技能指引。

---

## 1. 技能應用場景與觸發條件

*   **觸發場景**：當用戶提出「對抗市場分析師預期」、「比對 10 模型與共識表現」、「產出多模型對照報告」或「計算模型勝率與 Alpha」時。
*   **評估定位**：藉由回測期的 MAPE，客觀評估自建的「自下而上板塊預報法 (Bottom-Up Segment-wise)」是否能有效擊敗「市場平均共識 (True of Consensus)」，藉此驗證預估管線的實務價值。

---

## 2. 評估指標定義與計算規範

評估應包含以下核心量化指標：

1.  **歷史 MAPE (平均絕對百分比誤差) 對比**：
    評估每個模型與共識在歷史滾動回測期的平均誤差大小。
    $$
    \text{MAPE} = \frac{100\%}{n} \sum_{t=1}^{n} \left| \frac{\text{真實值}_t - \text{預估值}_t}{\text{真實值}_t} \right|
    $$
2.  **市場共識總勝率 (Win Rate)**：
    統計自建最優模型（10 個統計模型中 MAPE 最小者）在歷史預估中，精準度（MAPE）勝過任何市場共識模型（Yahoo 或 FactSet）的個股比例。
    $$
    \text{Win Rate} = \frac{\text{自建模型 MAPE 小於市場共識的最優個股數}}{\text{含有市場共識的個股總數}} \times 100\%
    $$
3.  **平均誤差縮減幅度 (Mean Error Reduction)**：
    自建模型相較於市場最優共識，平均降低了多少個百分點的預測誤差（單位：pp，Percentage Points）。正值代表自建模型精準度提升。
    $$
    \text{Error Reduction} = \text{Consensus\_MAPE} - \text{Model\_MAPE}
    $$

---

## 3. 數據對齊與回測基準

為了確保比較結果的公正性，必須遵循**無後窺偏差（No Look-ahead Bias）**原則：

1.  **10 種統計模型**：採用一步向前滾動回測 (Walk-Forward Validation)，在每個回測點僅使用當前月份之前的歷史數據進行模型重新校準與重新訓練。
2.  **Yahoo Finance 歷史共識**：歷史回測點的共識值必須是該月份營收公告日（次月 10 號）之前且最接近的 `forecast_asof_date` 紀錄。
3.  **FactSet 歷史共識**：歷史回測點的共識值必須是該期公告日之前且最接近的 `MD日期` 紀錄。
4.  **共識月度分拆**：由於共識資料為季度/年度資料，須利用該月前過去 3 年的歷史同月營收在其所屬季度中的佔比（Seasonal Weight）進行拆解。

---

## 4. 評估與比較作業步驟 (SOP)

### 4.1 執行評估腳本
Agent 應呼叫專門的評估腳本 [compare_all_models.py](file:///C:/Users/WJLEE/SynologyDrive/NAS/github.com/biztrends.TW/scripts/compare_all_models.py) 來執行跨股票的效能比對。

*   **執行焦點股票分析**（台積電 2330、華碩 2357、廣達 2382、敦陽科 2480，約數秒內完成）:
    ```powershell
    python scripts/compare_all_models.py
    ```
*   **執行所有股票分析**（遍歷 CSV 中所有股票，約需 1~2 分鐘）:
    ```powershell
    python scripts/compare_all_models.py --all
    ```

### 4.2 產出報告與視覺化確認
評估腳本將在 `output/` 目錄下自動產生 [all_models_benchmark_report.md](file:///C:/Users/WJLEE/SynologyDrive/NAS/github.com/biztrends.TW/output/all_models_benchmark_report.md) 報告。Agent 必須：
1.  檢查報告中的核心指標，包含**總勝率 (Win Rate)** 與**平均誤差縮減 (Error Reduction)**。
2.  在報告的個股對照表中，確認每檔個股的**表現最優預測者**是自建統計模型還是市場共識。
3.  向用戶回報評估報告的連結，並總結核心評估發現。
