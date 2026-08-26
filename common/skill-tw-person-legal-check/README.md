# skill-tw-person-legal-check

針對指定人物（公司負責人、經營層、合作對象）彙整台灣公開的法律/訴訟風險資訊，產出附風險分級與佐證來源的查核報告。詳細流程與輸出契約見 [SKILL.md](SKILL.md)。

依賴 [`skill-tw-court-records-search`](../skill-tw-court-records-search) 做裁判書查詢層——本技能只負責身分脈絡建構、新聞/重大訊息佐證與風險分級，不重複實作查詢邏輯。同樣沒有可執行腳本，由 agent 依 SKILL.md 流程執行。

## 快速開始

在對話中提供：

- 人名（建議附上職稱/任職公司，尤其常見姓名時）
- 或一篇提及該人物的新聞連結/全文

即可觸發本技能，輸出人物識別、裁判書查詢結果、新聞佐證與風險分級報告。

## 檔案結構

```
skill-tw-person-legal-check/
  SKILL.md              # 技能指令與輸出契約
  metadata.json         # 版本與來源 metadata
  self_update.py         # 通用技能自我更新工具（跟其他skill共用同一份，勿修改）
```

## 版本

- 1.0.0 (2026-08-26)：首版，建立在 `skill-tw-court-records-search` 之上，新增身分脈絡建構、MOPS重大訊息交叉比對與四級風險分級（高/中/低/無明顯風險）。
