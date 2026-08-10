# skill-stock-TopCrash

任意指數/股票在指定年份範圍內的「崩盤Top N」清單技能。詳細指令與輸出契約見 [SKILL.md](SKILL.md)。

## 快速開始

```bash
python scripts/run_topcrash.py --symbol ^TWII --years 10 --top-n 50 --output crash_top50.csv
```

## 檔案結構

```
skill-stock-TopCrash/
  SKILL.md              # 技能指令與輸出契約
  metadata.json         # 版本與來源 metadata
  self_update.py         # 通用技能自我更新工具（跟其他skill共用同一份，勿修改）
  scripts/
    run_topcrash.py       # CLI進入點：下載價格、偵測崩盤、標事件、補VIX情境、算恢復天數、寫CSV
    crash_detector.py      # 純邏輯：1/3/5/7/9/11日跌幅偵測 + 排序 + 去重
    event_labeler.py        # 具名事件JSON + 細粒度事件CSV 兩層比對
    vix_context.py           # VIX/CNN恐慌貪婪指數查詢與分級標籤
    recovery.py               # 崩盤前參考價 + 恢復天數/V-U修復形態判定
```

## 版本

- 1.0.0 (2026-08-10)：自 GoogleSheet.Banks 的 `taiex_crash_top50.py` 收錄並泛化——
  拿掉對特定Google Sheet寫入邏輯，改成通用CLI + CSV輸出；補上原本只存在於試算表裡
  （非程式碼生成）的「恢復天數/恢復形態」欄位，自行設計計算方法並用5筆已知案例驗證；
  `--symbol` 泛化成任意yfinance ticker，不再綁死`^TWII`。
