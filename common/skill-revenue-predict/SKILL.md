# 營收預測與多模型評估標準作業程序 (Revenue Forecasting & 10-Model Benchmark SOP)

本文件定義了 `biztrends.TW` 框架下，針對任意台灣上市櫃股票進行「月度營業收入預測、10-Model 滾動回測評估、模型適用性過濾、偏差修正與視覺化」的標準作業程序（SOP）。未來任何 Coding Agent 或數據分析人員在執行營收預測任務時，均應嚴格遵循此技能指引。

---

## 1. 技能應用場景與觸發條件

*   **觸發場景**：當用戶提出「預測 [StockID] 營收」、「分析 [StockID] 展望」或「進行 [StockID] 10-Model 循環回測」時。
*   **預設基準**：不使用死板的固定區間切分，而是採用更具實務價值的**一步向前滾動回測 (Walk-Forward Validation / Rolling Forecast)**：
    *   **1. 模型初始暖機期 (Warm-up Period - 24m)**：最前期的 24 個月。此區間模型只有真實數據，沒有模型曲線（作為起步訓練集）。
    *   **2. 滾動回測與驗證期 (Walk-Forward Validation)**：從暖機期結束到最新已發布月份。在此區間內，每個月的預測均使用「截至該月前所有已知真實數據」進行模型重新校準與重新訓練，只預測該月（1步），將各月預測值串接以進行迴歸驗證 (Regression Verify) 並評估其滾動回測表現（MAPE & MPE）。
    *   **3. 未來前瞻預測期 (Future Forecast - Next 3m)**：最新已公佈月份後的未來 3 個月。此時以截至最新公佈月份的所有已知數據作為訓練集，外推預測 3 步。
    *   **視覺化**：於圖中以紅色垂直虛線標示「最新數據邊界」，並以背景陰影明確劃分上述 1、2、3 三個區間。

---

## 2. 步驟零：數據完整性與模型適用性過濾規範 (Data Integrity & Model Filtering)

> [!CRITICAL]
> **數據缺失在數據分析中是極高風險的異常事件，且盲目在短期數據個股上使用長期季節模型會導入極大預測風險。本 SOP 規定在執行任何預測前，必須優先進行「數據完整性檢查」與「模型適用性過濾」。**

### 2.1 數據完整性檢查流程 (Data Completeness Check)
1.  載入目標個股的月度營收序列（近 5 年，約 60 個月）。
2.  檢查序列中是否存在任何空值（NaN、`-` 或缺失月份）。
3.  **觸發嚴重警告 (Severe Warning)**：
    *   若發現任何缺失月份，Agent 必須暫停預測流程，並輸出以下警告框：

    > [!WARNING]
> **【數據缺失警告】** 股票代碼 `[StockID]` 在 `[缺失月份]` 存在月營收數據缺失！
> 請優先排查上游下載管線 `Python-Actions.GoodInfo` 是否正常同步。

### 2.2 插值之最後退路與標記限制 (Last Resort & Flagging)
*   **啟用前提**：只有在確認上游下載源頭確實不存在該數據（例如公司在該年度尚未上市，交易所無月營收申報，但有年報歷史）時，才被允許啟用「插值補齊」。
*   **顯著標記規範**：一旦啟用插值，在最終輸出報告中**必須在最上方以 [!CAUTION] 標籤顯著標記**：

    注意：[插值區間] 之月營收數據為估算插值，非交易所真實申報營收，預測精準度可能受此影響。

### 2.3 模型適用性過濾與插值啟用機制 (Model Applicability & Interpolation Guidelines)

> [!IMPORTANT]
> **長期模型啟用原則：如果個股的真實月度申報數據小於 36 個月，但本地數據庫中擁有至少 5 年（60個月）的年度與季度營收歷史，應透過「步驟二：比例分佈插值補齊算法」補齊歷史月營收，進而全面啟用 10 種預測模型（包括需要長期數據的 Holt-Winters 三重平滑、季節分解與傅立葉季節回歸），不應直接將其標記為不適用 (N/A) 停用。**

1.  **數據長度與模型需求評估**：
    *   某些先進時間序列模型（如 Model 7 Holt-Winters、Model 5 季節分解、Model 9 傅立葉季節回歸）需要 3 ~ 5 年以上的歷史月度數據才能精準估算季節指數與趨勢。
    *   若個股真實申報之月營收數據長度 $N_{\text{real}} < 36$ 個月，但有完整的年報與季報數據可追溯至 5 年以上，**必須執行比例分佈插值**以將月營收序列補齊至 5 年（60個月）。
    *   補齊後，**必須對所有 10 種模型進行評估與訓練**，不可直接標記為不適用。
2.  **誠實標記與透明度 (Transparency Requirement)**：
    *   若模型訓練中使用了插值數據，必須在最終決測報告的最上方以 `[!CAUTION]` 或 `[!WARNING]` 標籤顯著列出插值所覆蓋的區間與比例。
    *   在視覺化對照圖中，必須以顯著的背景陰影或不同顏色標示出「插值估算區間」，與「真實申報區間」做出明確區隔。

---

## 3. 步驟一：本地數據提取與對齊

Agent 應使用標準 Python 程式碼，自本地 CSV 讀取並映射個股的月度、季度與年度營收（詳細提取邏輯請參閱 Module 2 Ingestion SOP）。

---

## 4. 步驟二：比例分佈插值補齊算法 (Interpolation)

*(僅當滿足 2.2 條件且確認啟動插值時使用，用於補全分析基礎，但不得用於訓練 2.3 中被停用的長期模型)*

*   **情境 A：有季度總營收，缺少該季內月營收**。使用最鄰近基準季度的月營收佔該季比例 $P_m$，分拆季度總額 $R_{Q}$。
*   **情境 B：僅有年度總營收，缺少月度營收**。以基準年份的月營收比例分佈，將年度總額 $R_{Y}$ 進行乘法分配。

---

## 5. 步驟三：10 種預測模型實作與過濾指引

Agent 在載入數據後，必須根據步驟 2.3 的 $N_{\text{real}}$ 過濾模型。

### 10 種模型之數學公式與實作

1.  **季節性 Naive 模型 (Model 1: Seasonal Naive)**
    *   *公式*：$\hat{Y}_{t+k} = Y_{t+k-12}$
2.  **YoY 成長調整模型 (Model 2: YoY Growth Adjusted)**
    *   *公式*：$\hat{Y}_{t+k} = Y_{t+k-12} \times (1 + \text{Avg\_YoY}_{2025})$
3.  **線性趨勢模型 (Model 3: Linear Trend)**
    *   *公式*：$\hat{Y}_{t+k} = a \cdot (t+k) + b$ (最小平方法擬合 $a, b$)
4.  **AR(1) 滾動自迴歸模型 (Model 4: AR-1 Rolling)**
    *   *公式*：$Y_t = \phi_1 Y_{t-1} + c$
5.  **季節分解趨勢模型 (Model 5: Seasonal Decomposition Trend)**
    *   *公式*：去季節化 $Y^{adj}_t = Y_t / S_m$，擬合線性趨勢後外推，乘回季節指數 $S_{m+k}$。*(若真實數據不足，應使用5年插值數據進行訓練)*
6.  **Holt 雙重指數平滑模型 (Model 6: Holt's Linear Exponential Smoothing)**
    *   *公式*：
        $$L_t = \alpha Y_t + (1-\alpha)(L_{t-1} + T_{t-1})$$
        $$T_t = \beta (L_t - L_{t-1}) + (1-\beta)T_{t-1}$$
        $$\hat{Y}_{t+k} = L_t + k \cdot T_t$$
7.  **Holt-Winters 三重指數平滑模型 (Model 7: Holt-Winters Seasonal)**
    *   *公式*：同時捕捉基準、趨勢與加法季節性。*(若真實數據不足，應使用5年插值數據進行訓練，為長期季節性分析首選)*
8.  **滾動加權移動平均模型 (Model 8: Weighted Moving Average - WMA-3)**
    *   *公式*：$\hat{Y}_{t+1} = \frac{3 Y_t + 2 Y_{t-1} + 1 Y_{t-2}}{6}$ (滾動自迴歸預測)
9.  **傅立葉季節多元線性回歸 (Model 9: Fourier Seasonal Regression)**
    *   *公式*：$Y_t = \beta_0 + \beta_1 \cdot t + \beta_2 \cdot \cos(\frac{2\pi t}{12}) + \beta_3 \cdot \sin(\frac{2\pi t}{12}) + \beta_4 \cdot \cos(\frac{4\pi t}{12}) + \beta_5 \cdot \sin(\frac{4\pi t}{12})$。*(若真實數據不足，應使用5年插值數據進行訓練)*
10. **AR(2) 滾動自迴歸模型 (Model 10: AR-2 Rolling)**
    *   *公式*：$Y_t = \phi_1 Y_{t-1} + \phi_2 Y_{t-2} + c$

---

## 6. 步驟四：偏差評估與動能偏差修正 (Momentum Correction)

在測試集上對所有**適用模型**計算 **MAPE (平均絕對百分比誤差)** 與 **MPE (平均百分比誤差)**：
*   **MAPE (平均絕對百分比誤差)**：$\frac{1}{K} \sum \left| \frac{\text{實際} - \text{預測}}{\text{實際}} \right| \times 100\%$
*   **MPE (平均百分比誤差)**：$\frac{1}{K} \sum \left( \frac{\text{實際} - \text{預測}}{\text{實際}} \right) \times 100\%$

---

## 7. 步驟五：格式化決策報告與對照表範本

Agent 在輸出決策報告時，必須將所有 10 種模型進行滾動回測排名，格式如下：

### 10-Model 營收預測與回測表現排名表

| 排名 | 模型名稱 | MAPE (%<br>(誤差大小)) | MPE (%<br>(偏差方向)) | 6月預測 (Raw/Corrected) | 7月預測 (Raw/Corrected) | 8月預測 (Raw/Corrected) | 狀態與評語 |
|:---:| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **1** | **Model 7 (Holt-Winters Triple)** | **10.33%** | **+10.33%** | **2.19 / 2.44** | **2.46 / 2.74** | **2.63 / 2.94** | **表現最優**。利用5年插值數據成功建立季節模型，效果顯著。 |
| **2** | **Model 8 (WMA-3)** | **12.28%** | **-3.56%** | **2.64 / 2.55** | **2.64 / 2.55** | **2.64 / 2.55** | **表現次優**。權重偏向近期，能即時吸收最新動能。 |
| **3** | **Model 5 (Seasonal Decomp)** | **12.88%** | **+12.88%** | **2.02 / 2.32** | **2.27 / 2.60** | **2.44 / 2.80** | **表現優良**。有效拆解季節性，預估走勢與 Holt-Winters 相近。 |
| **4** | **Model 6 (Holt Linear Double)** | **13.49%** | **+0.59%** | **2.59 / 2.61** | **2.61 / 2.63** | **2.63 / 2.65** | **表現穩定**。幾乎達到完美的無偏差預測 (MPE僅+0.59%)。 |
| ... | ... | ... | ... | ... | ... | ... | ... |

---

## 8. 步驟六：預測結果視覺化 SOP (Visualization SOP)

Agent 必須執行以下標準 `matplotlib` 繪圖腳本，將歷史真實數據（不含插值）、2026 實際已發布點與前三名**最優適用模型**的預測線繪製成對照圖，並在圖中以半透明陰影標示預測區間。

### 8.1 公司 Logo 嵌入規範 (Logo Overlay Guidelines)
* **尋找 Logo**：從專案根目錄的 `logos` 目錄尋找 `[StockID].png` 檔案。
* **縮放與放置**：為了保持最高畫質的縮放細節，載入 Logo 時應保持高解析度原圖（不做 Pillow `.resize` 降低細節），並利用 `matplotlib.offsetbox.OffsetImage` 的 `zoom` 參數進行比例縮放（計算公式：`zoom = target_width / 原始寬度`，此處目標寬度為 48 像素，即原定 120 像素的 40% 大小）。透過 `AnnotationBbox` 將其放置於整張畫布最左下角（以 `figure fraction` 的 `(0.01, 0.01)` 座標定位，`box_alignment=(0.0, 0.0)` 左下對齊），並且必須明示調用 `fig.subplots_adjust(left=0.15, bottom=0.22)` 在左下方調整出足夠的空白邊距，以避免遮擋座標軸刻度或標籤等關鍵數據資訊。
* **畫質最佳化**：在 `OffsetImage` 中必須明確啟用 `interpolation="lanczos"` 與 `resample=True`，在 Matplotlib 引擎於儲存高解析度圖表時直接對高解析度原圖執行高品質 Lanczos 插值，以完全消除去背邊緣之鋸齒與黑邊。
* **強健性**：若找不到 Logo 檔案或載入失敗，應輸出警告，但必須繼續產生沒有 Logo 的圖表，不可中斷預測流程。

### 8.2 範例繪圖程式碼
```python
import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from PIL import Image

fig, ax = plt.subplots(figsize=(10, 5), dpi=300)

# ... [繪製5年歷史數據與預測線邏輯] ...
# 繪製垂直分界線與背景陰影標示：歷史實測與滾動回測期、未來前瞻預測期

# 每 2 個月顯示一次刻度標籤以防止文字重疊
ticks = np.arange(0, len(all_x_months), 2)
ax.set_xticks(ticks)
ax.set_xticklabels([all_x_months[i] for i in ticks], rotation=45)

plt.tight_layout()
fig.subplots_adjust(left=0.15, bottom=0.22, right=0.96, top=0.90)

# 嵌入公司 Logo
logo_path = os.path.join(ROOT, "logos", f"{stock_code}.png")
if os.path.exists(logo_path):
    try:
        img = Image.open(logo_path).convert("RGBA")
        w, h = img.size
        target_width = 48
        zoom_factor = target_width / w
        logo_arr = np.array(img)
        imagebox = OffsetImage(logo_arr, zoom=zoom_factor, interpolation="lanczos", resample=True)
        ab = AnnotationBbox(imagebox, (0.01, 0.01), xycoords='figure fraction',
                            boxcoords="figure fraction", frameon=False, box_alignment=(0.0, 0.0))
        ax.add_artist(ab)
    except Exception as e:
        print(f"Failed to add logo for {stock_code}: {e}")
```

報告嵌入語法：
`![營收預測 10-Model 對照圖](file:///[Artifact目錄路徑]/revenue_predict_[StockID].png)`

---

此檔案即為 `skill-revenue-predict` 的標準化說明（`SKILL.md`），請放入 `skills/common/skill-revenue-predict/` 目錄。
