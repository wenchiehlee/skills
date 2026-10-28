---
name: skill-document-vids-prompt-generate
description: 將 Wikipedia 長篇條目、PPT 投影片或長文文件轉化為最適合 Google Vids (Gemini Omni 模型) 吸收的高畫質分鏡與影片生成提示詞；嚴格消除 AI 罐頭感，產出具備專業導演風格的視覺描述與口播配音腳本。
---

# 文件轉 Google Vids 導演級分鏡提示詞產生器

將維基百科（Wikipedia）長篇條目、PPT 投影片或研究報告，轉化為最適合 **Google Vids（Gemini Omni 多模態模型）** 吸收的高畫質分鏡腳本、視覺生成提示詞與配音口播詞。

---

## 命名規範與治理對齊

本技能依據 `skill-investment-decision-coach` 的技能分類治理規範命名：
- **格式規範**：`skill-<domain>-<object>-<action>`
- **語意責任分析**：
  - **`<domain>` = `document`**：輸入責任涵蓋維基百科長文、PPT 投影片與長篇分析文件，與 `skill-document-ppt-design`、`skill-document-diagram-design` 同屬文件與內容架構領域。
  - **`<object>` = `vids-prompt`**：核心交付物為 Google Vids 專用分鏡提示詞（Prompt Blocks）與視覺腳本。
  - **`<action>` = `generate`**：負責分析、切分、消減 AI 罐頭感並生成結構化分鏡。
- **Category**：`document`

---

## 目的

1. **結構化萃取**：將維基百科浩瀚的歷史長文或 PPT 簡報重點，精煉為清晰的故事主線與節奏。
2. **多模態對齊**：依據 Google Vids 的多模態規格，產出包含鏡頭運動、光影色調、實體道具與畫面構圖的精密提示詞。
3. **消除 AI 罐頭感**：嚴格遵循維基百科防 AI 寫作指南（Wikipedia Anti-AI Slop Guidelines），剔除空洞套話與陳腔濫調，賦予影片如公共電視或 BBC 人類紀錄片導演般的專業質感。

---

## 執行工作流

```text
[輸入來源: Wikipedia 條目 / PPT 簡報 / 架構文檔]
               │
               ▼
   風格路由：[向量動畫解說 (Vector Explainer)] 或 [電影紀錄片 (Cinematic)]
               │
               ▼
   步驟 1. 核心時間軸 / 三幕式架構 (痛點 ➔ 嘗試與瓶頸 ➔ 突破與閉環)
               │
               ▼
   步驟 2. 依 Google Vids 規格切碎分鏡 (3-10s / 16:9 或 9:16)
               │
               ▼
   步驟 3. 導演級「防 AI 罐頭」潤飾 (精準動詞驅動、實體隱喻具象化)
               │
               ▼
[交付物: 結構化 Google Vids 分鏡卡 + 提示詞清單]
```

### 步驟 0：判斷視覺風格體系 (Style System Selection)
- **向量動態解說風格 (`vector-explainer`)**：
  - 適用：技術規格、軟體流程（如架構流程圖、Flow Map）、商業計畫書、PPT 轉影片。
  - 特徵：暖米色背景（Warm Cream `#F5F2EB`）、扁平俐落幾何、統一的角色錨點（如機器人 Mascot）、三欄白板與連線流程圖。
- **電影紀錄片風格 (`cinematic`)**：
  - 適用：維基歷史事件、人物傳記、戰役史、科學發現。
  - 特徵：35mm 膠卷感、真實歷史道具、自然逆光、慢速推軌運鏡。

### 步驟 1：萃取核心結構與敘事線
- **技術/產品/PPT 模式（三幕式解說敘事弧）**：
  1. *Act I (痛點直擊)*：否定空話，直接指出「AI 不懂你的產品/上下文」。
  2. *Act II (瓶頸瓶頸)*：解釋為什麼死背靜態文檔會失敗（程式碼隨時在變、記憶體溢出）。
  3. *Act III (突破與閉環)*：教它畫地圖（Flow Map）、程式碼異動時主動舉手、真人簽核（Human in the loop）。
- **維基百科模式（時間軸/Top 5 事實）**：
  - 提煉 5～12 個具備因果推進關係的客觀歷史事實。

### 步驟 2：切碎成 Google Vids 場景提示詞 (Scene Prompt Blocks)
- **硬性約束**：
  - **單一場景時長**：嚴格限制在 **3 至 10 秒** 之間。
  - **畫幅規格**：橫螢幕 `16:9`（預設，適於 YouTube/簡報解說）或直螢幕 `9:16`（適於 Shorts/Reels）。
  - **字數預算**：中文配音按每秒 3.5 字嚴格控管（3 秒 ≤ 11 字；5 秒 ≤ 18 字；8 秒 ≤ 28 字），避免 TTS 配音爆時或吞字。
- **畫面五要素**：每個場景的視覺提示詞必須明確定義：
  1. `Camera Movement`（鏡頭移動方式：如 Slow dolly in, Crane down, Steadycam tracking）
  2. `Shot Framing`（景別：如 Extreme Close-Up, Wide Establishing Shot）
  3. `Subject & Action`（主體與物理動作，不可抽象）
  4. `Lighting & Color`（光線、色溫、時代氛圍）
  5. `Texture & Medium`（質地：如 35mm film grain, Archival tint, Hasselblad medium format look）

### 步驟 3：嚴格防 AI 罐頭感 (Anti-AI Slop Enforcement)
- **旁白排毒**：
  - ❌ 徹底剔除：「在當今快節奏的世界中」、「值得注意的是」、「猶如璀璨的明珠」、「深入探討」、「這不僅是……更是……」。
  - ✅ 改採人類說話節奏：短句、具體動詞、冷靜客觀、富有呼吸感。
- **視覺排毒**：
  - ❌ 徹底剔除：`photorealistic`, `8k`, `epic atmosphere`, `cinematic masterpiece` 等無幾何控制力的無效標籤。
  - ✅ 改以具體光學與實體細節控制畫面（如 `scratched brass microscope, diffused window light, shallow depth of field, dust particles in sunbeam`）。

---

## 交付物結構標準 (Output Specification)

每個產出的場景需採用統一的「導演分鏡卡」：

```markdown
### Scene [X]: [場景主題]
- **規格**：[時長] 秒 | 畫幅 [16:9 或 9:16]
- **鏡頭調度**：[景別與運動，例如：中特寫，由右向左平移]
- **Google Vids 視覺提示詞**：
  > [可直接複製至 Gemini Omni 的英文或高精度中文視覺 Prompt]
- **人類導演配音腳本**：
  > 「[完全符合秒數預算的口播配音詞]」
- **畫面字卡 / 關鍵年代**：[可選]
```

---

## 工具與腳本

- **`scripts/wiki_to_vids_prompt.py`**：快速文字萃取與秒數切分工具。
  ```bash
  python scripts/wiki_to_vids_prompt.py --input article.txt --aspect-ratio 16:9 --top-facts 5
  ```
- **`references/anti-ai-writing-guide.md`**：完整防 AI 罐頭詞黑名單與對比手冊。
- **`references/vids-prompt-patterns.md`**：Google Vids 分鏡模板與節奏指南。
