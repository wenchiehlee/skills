---
name: skill-taiex-monitor
description: 財報行事曆監控：偵測資料缺漏並自動開 Issue，更新 README 看板
---

# TAIEX.TW Monitor Skill

此技能包含兩個主要任務：
1. `check_calendar_gaps.py`：掃描 README.md 財報行事曆，對於在時間範圍內已公布財報但本地 CSV 資料尚未準備完成的標的，自動在對應的 upstream repo 提交「Data Lag」GitHub Issue 催更數據。
2. `update_readme.py`：依據最新的行事曆事件與本地 `/output/visuals/` 目錄中已 commit 的 SVG 報告，自動重新渲染 README.md 的財報行事曆看板與縮圖連結。

## 命令說明

| 命令格式 | 功能說明 |
|---------|--------|
| `python <SKILL_DIR>/scripts/check_calendar_gaps.py` | 掃描行事曆，回報並自動提交數據缺漏 Issue |
| `python <SKILL_DIR>/scripts/update_readme.py` | 刷新 README.md 上的財報日曆與 SVG 縮圖狀態表 |

## 使用範例

```bash
# 偵測並開 Issue 催更數據
python skills/common/skill-taiex-monitor/scripts/check_calendar_gaps.py
# 刷新 README 看板
python skills/common/skill-taiex-monitor/scripts/update_readme.py
```
