---
name: skill-taiex-report
description: 生成台股/美股 SVG 投資決策報告（Finguider 卡片 + 營收歷史圖）
---

# TAIEX.TW Report Skill

此技能可用於生成個股（台股/美股）的 SVG 財務儀表板卡片與營收歷史趨勢圖。它會從本地 `data/` 下讀取相關的財務 CSV 數據，呼叫 LLMClient 進行排版與文本填充，並更新 README.md 中最新的狀態。

## 命令說明

| 命令格式 | 功能說明 |
|---------|--------|
| `python <SKILL_DIR>/scripts/generate_reports.py <SYMBOL> [TAG] [PERIOD]` | 生成個股完整的 Finguider SVG 與營收歷史 SVG 報告，並刷新 README 狀態 |
| `python <SKILL_DIR>/scripts/assembler_finguider.py <SYMBOL|batch> [TAG] [PERIOD]` | 僅生成指定的 Finguider 財務總結卡片 |
| `python <SKILL_DIR>/scripts/assembler_revenue_history.py <SYMBOL> [TAG] [PERIOD]` | 僅生成指定的營收歷史 stacked bar SVG |

## 使用範例

```bash
# 生成台積電 (2330) 2026 Q1 的完整報告
python skills/common/skill-taiex-report/scripts/generate_reports.py "2330" "gemini-cli" "2026_Q1"
```
