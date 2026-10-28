# Narrative & Style Patterns / 敘事與風格模式

Tool-neutral: these patterns decide **what** the video says and **how it looks**. Tool limits (scene length,
clip caps, text rendering) live in `references/adapters/*.md`.
與工具無關：本文件決定影片「說什麼、長什麼樣」；各工具的硬性限制請見 `references/adapters/`。

---
## 1. 雙大視覺風格系統 (Visual Style Systems)

Two proven style systems. Pick one per video and keep its anchor (palette + mascot / lens + era) identical in every scene. 依成功案例，文件轉影片主要分為兩大視覺體系，全片只選一種並保持錨點一致：

### 風格 A：極簡向量動態解說風格 (Minimalist Vector Explainer)
> **適用情境**：技術架構、軟體流程、流程地圖（如 `mx-flow-map`）、商業模式、PPT 轉影片。

- **美學特徵**：
  - **背景**：純淨溫暖的米色/淺灰背景（`Warm Cream #F5F2EB` 或 `Soft Gray`），讓視覺焦點留在主體。
  - **色彩計畫**：高對比但低飽和的現代扁平配色（深海軍藍文字、薄荷綠主體、活力橙引導線、淡彩色卡片）。
  - **角色與視覺錨點 (Visual Anchor)**：設定一致的形象角色（如圓角簡約機器人作為 Agent 錨點、具備職能特徵的人物線條）。
  - **抽象隱喻具象化 (Metaphorical Translation)**：
    - *抽象知識* → 整齊疊放的紙張卡片（Stack of white rounded cards）。
    - *程式碼與多模組* → 圓角 IDE 深色視窗搭配彩色代碼條、帶有進度條的大腦圖標。
    - *流程追蹤* → 三欄式看板上的連線折線圖，節點附帶文件標籤（Flow Map nodes）。
    - *審核機制 (Human-in-the-loop)* → 真人手持實體印章蓋印（Stamp sign-off）。
  - **提示詞結構範例**：
    ```text
    Minimalist 2D vector editorial illustration, warm cream background (#F5F2EB), modern flat design, cute rounded teal robot mascot wearing orange backpack, standing in front of a clean three-column whiteboard displaying a node-based flow map with glowing orange connection lines. Clean vector lines, subtle soft drop shadows, pastel color palette, tech company explainer animation style.
    ```

---

### 風格 B：歷史電影紀錄片風格 (Cinematic Documentary)
> **適用情境**：歷史人物、戰役事件、地理發現、科學發明史。

- **美學特徵**：
  - **攝影光學**：35mm 膠卷顆粒、變形寬銀幕鏡頭眩光、自然側逆光（Rim Lighting）。
  - **道具與環境**：真實歷史檔案質感（磨損銅器、羊皮紙、泛黃手稿、真實年代工具）。
  - **運鏡手法**：Slow Dolly In（緩慢推軌）、Ken Burns 慢速平移、深景深聚焦。
  - **提示詞結構範例**：
    ```text
    Historical cinematic documentary, 1900s archival atmosphere, slow push-in shot of vintage wooden workbench covered with draft sketches, brass calipers and oil lamps. Warm golden hour sunlight streaming through industrial window panes with visible airborne dust motes. 35mm film grain, muted earth tones, authentic period details.
    ```

---

## 2. 三幕式解說敘事弧線 (The 3-Act Explainer Arc)

從優秀範例（`mx-flow-map-global-v7-2.mp4`）提煉的最佳旁白節奏：

```text
[Act I: 痛點與共鳴] ──▶ [Act II: 嘗試與崩潰點] ──▶ [Act III: 核心突破與驗證]
(00:00 - 00:35)         (00:35 - 01:45)            (01:45 - 02:40)
```

1. **第一幕：痛點直擊 (The Hook & Context)**
   - 否定常見無效做法，直擊現場矛盾：
     > 「每個人都被要求在工作中使用 AI Agent，但 Agent 根本不懂你的工作流，它也不懂你的產品。」
   - 引出本地成功經驗，並列舉關鍵利害關係人（Product Owners, Architects, Engineers）。
2. **第二幕：傳統做法的極限 (The Bottleneck & Breakdown)**
   - 具體化說明為什麼傳統解法行不通：
     > 「知識不是寫在靜態紙頁上，程式碼每天都在變；如果寫下來，就必須一改再改。」
     > 「Agent 的腦容量有限，跨多個元件追蹤一項功能，它的大腦就會超載溢出。」
3. **第三幕：架構突破與人間驗收 (Breakthrough & Human Sign-off)**
   - 哲學比喻（授人以魚不如授人以漁）。
   - 展示核心架構（從送紙頁改為畫地圖 Flow Map）。
   - 人機協同閉環：程式碼變更時地圖主動舉手，AI 修復、**真人簽核**（Human in the loop）。

---

## 3. 輸入源處理模式 (Source Modes)

### 模式 A：維基百科條目 (Wikipedia Source)
1. **事實提煉**：跳過序言空泛評價，直接抓取「年表/時間軸（Timeline）」或「Top 5 關鍵轉折事實」。
2. **視覺錨點**：條目中的歷史照片、檔案文獻、專利圖解轉化為動態重現鏡頭。
3. **場景編排**：
   - Scene 1: 鉤子鏡頭（現場關鍵物件或突發事件，3-5s）
   - Scene 2-4: 歷史背景與衝突起點（各 4-6s）
   - Scene 5-8: 關鍵事件推進與高潮點（各 5-7s）
   - Scene 9-11: 轉折、影響與具體數據驗證（各 5-6s）
   - Scene 12: 餘韻定鏡（不作說教總結，定格於當代遺跡或具體物件，4-5s）

### 模式 B：PPT 投影片 (Presentation Deck Source)
1. **單頁解構**：每一頁 PPT 投影片拆解為 1～2 個連續鏡頭。
2. **圖表動態化**：靜態折線圖、流程圖轉化為「攝影機掃過手繪藍圖或全像投影介面」。
3. **消除條列感**：禁止念出「第一點、第二點」，將 Bullet Points 轉化為前後因果故事線。
### 模式 C：技術文件 / 規格 / Flow Map (Technical Source)
1. 用三幕式弧線（§2）而非時間軸；每個流程步驟 → 一個 `flow` / `cards` 場景。
2. 一個場景只講一個機制；數字（延遲、次數、節省時間）優先用 `stat` 場景呈現。
3. 結尾給具體行動（CTA），不要用「讓我們一起擁抱未來」收尾。

---

## 4. Pacing defaults / 節奏預設

| Video length | Scenes | Typical scene | Notes |
|---|---|---|---|
| 30 s teaser | 5–6 | 4–6 s | Hook → 3 beats → CTA |
| 60–90 s explainer | 10–14 | 5–8 s | Three-act arc |
| 2–3 min explainer | 12–20 | 6–10 s | Add one recap scene before CTA |
| Slides + narration | 1 slide ≈ 20–60 s | — | Notes carry the VO; slides carry ≤ 6 bullets |
