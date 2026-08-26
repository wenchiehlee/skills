---
name: skill-taiex-viz
description: 不需 LLM，用 matplotlib 直接生成美股分部營收靜態 PNG 圖
---

# TAIEX.TW Viz Skill

此技能提供不依賴 LLM 的純靜態圖形渲染功能。主要使用 Matplotlib 讀取 ConceptStocks 損益與分部數據，為指定股票（目前特別優化 NVDA）繪製高解析度（300 DPI）的分部季度營收堆疊柱狀圖。

## 命令說明

| 命令格式 | 功能說明 |
|---------|--------|
| `python <SKILL_DIR>/scripts/generate_revenue_breakdown.py <SYMBOL>` | 為指定美股代號繪製並輸出業務分部營收 PNG |

## 使用範例

```bash
python skills/common/skill-taiex-viz/scripts/generate_revenue_breakdown.py NVDA
```
