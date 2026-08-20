# skill-company-reputation-research 使用說明

`skill-company-reputation-research` 用來協助求職者在面試或接受 offer 前，針對指定公司彙整台灣及全球常見求職資訊管道，判讀公司聲譽、面試流程、薪資與工時、工作氛圍、勞資風險與職涯適配性。

## 何時使用

當你想查一間公司的真實工作資訊時，可以指定這個 skill，例如：

```text
with the skill "skill-company-reputation-research", I want to find information on "力旺" for 2 year engineer
```

也可以用中文描述：

```text
使用 skill-company-reputation-research，幫我查「新代科技」給 2 年資歷軟體工程師是否值得去。
```

## 建議輸入格式

請盡量提供以下資訊，結果會更準：

- 公司名稱：中文名、英文名、股票代號或品牌名皆可。
- 目標職缺：例如軟體工程師、電路設計工程師、產品工程師、驗證工程師、FAE。
- 年資背景：例如新鮮人、2 年 engineer、5 年 senior。
- 地點：例如新竹、竹北、台北、中和、海外分公司。
- 你在意的重點：薪資、工時、升遷、技術成長、離職率、面試難度、部門風氣。

範例：

```text
使用 skill-company-reputation-research，查「晶焱」給 2 年類比/驗證工程師的薪資、工時、面試準備和職涯風險。
```

```text
with skill-company-reputation-research, compare 力旺、新代、晶焱 for a 2-year engineer. Focus on compensation, work-life balance, technical growth, and interview preparation.
```

## Skill 會查哪些來源

此 skill 會優先交叉比對公開資訊與求職者常用平台，包括：

- 台灣求職平台：GoodJob、面試趣、比薪水、求職天眼通、518 好公司。
- 社群討論：Dcard、PTT、Mobile01，以及搜尋結果中出現的相關論壇。
- 官方與公開資料：公司官網、104 公司頁、公開資訊觀測站、年報、永續報告書、商工登記、法院或勞動法令紀錄。
- 全球平台：Glassdoor、Indeed、Blind、Levels.fyi、Reddit、LinkedIn、Layoffs.fyi 等，視公司與職缺是否具跨國性使用。

## 預期輸出

預設會用繁體中文輸出，並包含：

1. 公司識別：公司正式名稱、英文名、股票代號、產業、地點。
2. 資料來源總覽：每個來源提供什麼資訊，以及可信度限制。
3. 重點發現：面試流程、薪資、工時、福利、文化、離職/裁員/勞資訊號。
4. 風險分級：Low / Medium / High / Unknown，並說明證據強弱。
5. 面試前建議追問：可直接拿去問 HR 或主管的問題。
6. 引用來源：重要判斷需附公開來源連結。

## 判讀原則

- 匿名留言只當作線索，不當作事實。
- 多個獨立來源重複出現的訊號，權重高於單一爆料。
- 近期、具職務/年資/地點脈絡的分享，權重高於很舊或很籠統的留言。
- 薪資要看 total package，不只看月薪；需分清楚底薪、保底月數、年終、季獎金、分紅與股票。
- 若資料不足，應明確標示 `Unknown`，不要硬下結論。

## 常用 Prompt 範本

查單一公司：

```text
使用 skill-company-reputation-research，幫我查「公司名稱」對 2 年資歷「職稱」是否值得去。請重點看薪資、工時、面試流程、部門文化、職涯風險，並附來源。
```

比較多家公司：

```text
使用 skill-company-reputation-research，比較「公司A、公司B、公司C」給 2 年 engineer 的 offer 吸引力。請用表格整理薪資、工時、成長性、風險，最後給排序與追問清單。
```

準備面試：

```text
使用 skill-company-reputation-research，幫我準備「公司名稱」「職稱」面試。請整理常見筆試/面試題、需要複習的科目、薪資談判重點，以及我應該反問主管的問題。
```
