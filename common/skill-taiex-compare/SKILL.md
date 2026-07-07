---
name: skill-taiex-compare
description: 財報公布後，從 GitHub Issue 取得貼文內容，與內部 CSV 數字逐欄比對，自動回報差異
---

# TAIEX.TW Compare Skill

此技能用於在財報季期間，自動從 GitHub Issue 中抓取社群貼文（Facebook.Fetch）的財報報告連結，使用 LLM 擷取貼文中的非標準數據與營收/EPS，並與本地 ConceptStocks/GoodInfo 等數據來源的內部 CSV 進行精確的比對。自動產生差異報告（Markdown 格式），並在比對無誤時關閉對應的 GitHub Issue。

## 命令說明

| 命令格式 | 功能說明 |
|---------|--------|
| `python <SKILL_DIR>/scripts/compare_references.py --issue <N> [--close]` | 比對指定 Issue 號碼的貼文與內部 CSV，可選比對無誤後自動關閉 Issue |
| `python <SKILL_DIR>/scripts/compare_references.py --symbol <SYM> --period <PER> --file-path <PATH>` | 手動指定股票、期別與貼文路徑進行比對 |

## 使用範例

```bash
# 比對 Issue 7 的財報貼文與內部 CSV，無誤後自動關閉 Issue
python skills/common/skill-taiex-compare/scripts/compare_references.py --issue 7 --close
```
