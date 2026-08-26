---
name: skill-taiex-sync
description: 更新本地資料目錄索引，生成批次處理所需的投資標的清單
---

# TAIEX.TW Sync Skill

此技能用於掃描本地 `data/` 目錄下所有的 `raw_*.csv` 數據檔案，自動更新 `data_sync_table.csv` 的檔案同步時間與來源標記，並統合各個數據來源生成 `raw_investment_summary.csv`（作為批次生成報告時的標的清單）。

## 命令說明

| 命令格式 | 功能說明 |
|---------|--------|
| `python <SKILL_DIR>/scripts/data_collector.py` | 掃描本地數據並刷新同步表與標的清單 |

## 使用範例

```bash
python skills/common/skill-taiex-sync/scripts/data_collector.py
```
