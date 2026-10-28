# 防 AI 罐頭寫作指南 (Anti-AI Slop & Editorial Guide)

本指南參考維基百科社群對 AI 生成內容的偵測特徵（Wikipedia:Signs of AI-generated text）與專業紀錄片導演的分鏡規範，用於在生成任何影片分鏡（Google Vids、Veo/Sora/Runway/Kling、程式化渲染、簡報旁白）時消除「AI 罐頭感」。Applies to every target adapter.

---

## 1. 什麼是「AI 罐頭感」（AI Slop）？

LLM 生成影片腳本與分鏡時常犯的三大通病：
1. **空洞的浮誇詞（Puffery & Superlatives）**：滿篇「璀璨的明珠」、「劃時代的里程碑」、「不可抹滅的貢獻」、「深深震撼了世人」。
2. **公式化過渡與開場（Formulaic Transitions）**：每一段都以「在當今快節奏的世界中」、「值得注意的是」、「此外」、「總結來說」、「讓我們一同深入探討」開頭。
3. **模糊泛化的視覺描述（Vague Visuals）**：例如「畫面上展示科技感背景與光影交織，展現未來的繁榮」——這種描述對影片生成模型（Gemini Omni、Veo、Sora、Runway、Kling）而言缺乏實體細節，生成出來往往是一團混亂的廉價 CGI。

---

## 2. 嚴格禁用詞彙庫（Negative Word Bank）

### 旁白配音禁用詞（Voiceover Ban List）
- ❌ **開場套話**：
  - 「在當今這個……的時代」、「你有沒有想過……」、「今天我們就來聊聊……」、「讓我們一起揭開……的神秘面紗」。
- ❌ **空洞結論**：
  - 「這不僅是……更是……」、「這無疑是人類歷史上一座偉大的里程碑」、「留給後人無限的啟發與深思」。
- ❌ **AI 銜接詞**：
  - 「值得注意的是」、「深入探討」、「猶如璀璨的明珠」、「令人嘆為觀止的是」、「不可忽視的是」。
- ❌ **English equivalents**:
  - "In today's fast-paced world", "It's worth noting", "Let's dive in / delve into", "game-changer", "revolutionize",
    "seamless", "cutting-edge", "unlock / harness the power of", "a testament to", "embark on a journey", "paving the way".
  - Fix: name the concrete actor + verb + object ("The agent reads 400 tickets in a minute").

### 視覺提示詞禁用詞（Visual Prompt Ban List）
- ❌ **抽象空詞**：`hyperrealistic`, `4k`, `8k`, `photorealistic`, `masterpiece`, `trending on artstation`, `stunning atmosphere`（這些對現代 Diffusion / Omni 模型大多無實質幾何控制力）。
- ❌ **模糊情緒詞**：`feeling sad`, `looks epic`, `inspiring vibe`。
- ✅ **替代做法**：改用客觀光學與物理特徵（如 `dappled sunlight through oak canopy, 35mm film grain, rim light on subject silhouette, slow push-in dolly`）。

---

## 3. 人類導演分鏡的三大鐵則

### 規則一：實體動作替代抽象形容（Show, Don't Preach）
- ❌ *AI 寫法*：「科學家們夜以繼日地努力，終於克服了重重困難。」
- ✅ *導演寫法*：「深夜兩點的實驗室，桌上堆滿冷掉的咖啡紙杯與示波器螢幕跳動的綠色波形。研究員雙手微顫地旋轉最後一顆微調電位器。」

### 規則二：短句頓挫與呼吸感（Human Cadence）
- 配音是用來「聽」的，不是用來「看」的。
- 句子長度控制在 8～18 個字之間，留給配音員氣口與畫面停留時間。
- 避免複雜的多重從屬子句。

### 規則三：嚴格對齊單場景秒數（Duration vs. Word Budget）
單一場景長度受目標工具限制（Vids 3–10 秒、AI 影片單段 5–20 秒、程式化渲染不限；見 `adapters/`），但字數預算一律如下：
- **中文語速標準**：每秒 3.5 ～ 4 個字。
  - 3 秒場景：10 ～ 12 字。
  - 5 秒場景：18 ～ 20 字。
  - 8 秒場景：28 ～ 32 字。
  - 10 秒場景：35 ～ 40 字。
- 英文語速標準：每秒約 2.5 words（3 s ≈ 7 words；5 s ≈ 12；8 s ≈ 20）。
- 超出字數會導致 TTS 配音被強制加速或分鏡切換突兀。`scripts/source_to_storyboard.py --lint` 會自動檢查。

---

### 規則四：精準動詞驅動，拒絕空泛形容詞 (Verb-Driven Storytelling)

觀摩高水準解說影片（如 `mx-flow-map-global-v7-2.mp4`）可發現，真正具有說服力的旁白幾乎**沒有多餘的華麗形容詞**，而是大量使用日常、具象、富有畫面感的精準動詞：

| 概念 | ❌ 典型的 AI 灌水形容詞 | ✅ 真人導演的高動態動詞 |
|---|---|---|
| 需求定義 | 「深入進行非常全面且細緻的分析」 | **Pin down** requirements |
| 系統架構 | 「具備高度協同且宏觀的架構視野」 | Explore how everything **fits together** |
| 記憶體超載 | 「造成極為沉重的計算負擔與知識瓶頸」 | The agent's head **overflows** |
| 狀態檢測 | 「系統將智慧化地自動發出異常告警通知」 | The map **raises its hand** |
| 人類審核 | 「確保符合高標準的人工品質監督管控」 | A person **signs off** before it counts |
| 核心傳承 | 「留下極具啟發性的卓越方法論」 | Teach once, **map forever** |

---

## 4. 導演視角的分鏡提示詞語法

每個場景的視覺提示詞（Visual Prompt）應包含以下五大核心要素：

```text
[鏡頭景別與運動] + [主體與具體動作] + [環境與物理道具] + [光線與色溫] + [畫面質地與風格]
```

### 範例對比

| 元素 | ❌ 典型 AI 罐頭提示詞 | ✅ 導演級視覺提示詞 |
|---|---|---|
| **視覺** | 一個很有歷史感的古老圖書館，滿滿的書，很有學術氛圍。 | 廣角低角度微仰拍。19 世紀維多利亞風格閱覽室，高聳的深胡桃木書架延伸至拱形天花板。晨光斜射穿過塵埃微粒，照亮桌上攤開的羊皮紙地圖。攝影機緩慢向前推軌（Slow Dolly In）。膠卷質感，暖調自然光。 |
| **旁白** | 知識的浩瀚在這裡得到了最好的體現，每一本書都記錄著古人無窮的智慧。 | 晨光穿過拱窗時，閱覽室通常很安靜。攤開的地圖邊緣，還留著墨水乾涸的深色指印。 |
