---
name: skill-confluence-sync
description: Read and overwrite a single Confluence Wiki page via REST API using CONFLUENCE_EMAIL / CONFLUENCE_API_TOKEN / CONFLUENCE_BASE_URL / CONFLUENCE_PAGE_ID. Use when asked to "read Confluence page", "sync to Confluence", "update Confluence wiki", or "export a Confluence page to Markdown".
---

# Confluence Sync Skill（單頁 Confluence Wiki 讀寫）

這個技能只做一件事：讀取與覆寫**一個固定的 Confluence 頁面**。設計參考
[SpillwaveSolutions/confluence-skill](https://github.com/SpillwaveSolutions/confluence-skill)，
但大幅簡化——不處理多頁面、子頁面樹、附件、圖片或 space 層級操作，只用
四個環境變數定位並操作單一頁面，適合「本地 Markdown 筆記 ↔ 一份團隊
Wiki 頁面」這種固定對應關係。

## 適用場景

- 把本地維護的 Markdown 文件（例如 README、決策記錄、進度報告）同步到
  一個固定的 Confluence 頁面。
- 把一個 Confluence 頁面的內容拉下來，轉成 Markdown 供本地編輯或讓
  Claude 閱讀/摘要。
- 查詢一個頁面目前的 version / title / URL，確認覆寫前的狀態。

**不適用**：建立新頁面、管理子頁面樹、上傳附件/圖片、跨 space 搬移頁面、
批次處理多個頁面。若有這些需求，請參考上游的
[confluence-skill](https://github.com/SpillwaveSolutions/confluence-skill)
或擴充本技能。

## 環境變數（必要）

| 變數 | 說明 |
| --- | --- |
| `CONFLUENCE_EMAIL` | Atlassian 帳號 email，作為 Basic Auth 的使用者名稱 |
| `CONFLUENCE_API_TOKEN` | Atlassian API token，於 <https://id.atlassian.com/manage-profile/security/api-tokens> 建立 |
| `CONFLUENCE_BASE_URL` | 站點根網址，例如 `https://yourcompany.atlassian.net`（不含 `/wiki`） |
| `CONFLUENCE_PAGE_ID` | 目標頁面的數字 ID（頁面網址中 `/pages/<ID>/`那一段） |

可以直接 export 成 shell 環境變數，或在執行目錄放一份 `.env`（腳本會
自動載入，若已安裝 `python-dotenv`）：

```env
CONFLUENCE_EMAIL=you@example.com
CONFLUENCE_API_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxx
CONFLUENCE_BASE_URL=https://yourcompany.atlassian.net
CONFLUENCE_PAGE_ID=123456789
```

**切勿把 `.env` 或 API token 提交進 git。**

## 安裝依賴

```bash
pip install -r scripts/requirements.txt
```

`requests` 與 `python-dotenv` 為必要；`markdown`（寫入 Markdown 時轉成
storage format）與 `markdownify`（讀取時轉成 Markdown）為選用——未安裝
時腳本會改用原始 storage HTML 並印出警告，不會中斷。

## 核心指令

統一入口是 `scripts/confluence_sync.py`，三個子指令：

### 讀取頁面（read）

```bash
# 轉成 Markdown，印到 stdout
python scripts/confluence_sync.py read

# 存成本地檔案
python scripts/confluence_sync.py read --output notes.md

# 保留原始 storage format（Confluence 的 XHTML）
python scripts/confluence_sync.py read --format storage
```

### 覆寫頁面（write）

會自動抓目前頁面版本號並 +1，不需要手動管理 version。

```bash
# 用本地 Markdown 覆寫（預設標題沿用 Confluence 上現有標題）
python scripts/confluence_sync.py write notes.md

# 送出前先預覽（不會真的呼叫 API）
python scripts/confluence_sync.py write notes.md --dry-run

# 覆寫標題、加版本註記
python scripts/confluence_sync.py write notes.md --title "週報 2026-10-14" --message "自動同步"

# 內容本身已經是 storage format（跳過 Markdown 轉換）
python scripts/confluence_sync.py write page.html --format storage
```

`write` 永遠是**整頁覆寫**，不是追加或合併。覆寫前務必先 `read` 確認
目前內容，或用 `--dry-run` 檢查轉換結果。

### 查詢 metadata（info）

```bash
python scripts/confluence_sync.py info
```

輸出目前的 title、space key、version number、頁面 URL，適合在覆寫前
確認沒有版本衝突。

### 用 `--page-id` 覆寫目標頁面

三個子指令都支援 `--page-id`，可在不改環境變數的情況下臨時指定另一個
頁面 ID，蓋過 `CONFLUENCE_PAGE_ID`。

## 常見錯誤

| 情況 | 處理 |
| --- | --- |
| `401 認證失敗` | 檢查 `CONFLUENCE_EMAIL` / `CONFLUENCE_API_TOKEN` 是否正確；API token 需在 Atlassian 帳號設定頁重新產生 |
| `404 找不到頁面` | 確認 `CONFLUENCE_PAGE_ID` 是否為正確的頁面 ID（不是 space key，也不是頁面標題） |
| `409 版本衝突` | 頁面已被其他人更新；重新 `read` 一次取得最新內容後再 `write` |
| Markdown 轉換結果跑掉（表格/程式碼區塊跑版） | 改用 `--format storage` 直接提供 Confluence storage format，或手動調整 Markdown 語法後再試 |

## 完成前檢查

- [ ] 覆寫前已用 `read` 或 `info` 確認目前版本，避免覆蓋他人未同步的變更
- [ ] 若內容包含表格、程式碼區塊等複雜語法，先用 `--dry-run` 檢查轉換後的 storage HTML 是否正確
- [ ] 認證資訊只放在環境變數或未加入版控的 `.env`，沒有寫死在腳本或提交進 git

## 未來可擴充方向（視需求而定）

v1.0.0 刻意只做單頁讀寫。若實際使用後出現以下需求，再依當時情境決定
是否升版擴充，不需要預先實作：

- 多頁面 / 子頁面樹（批次 page_ids 或遞迴下載 children）
- 附件與圖片上傳（目前完全未處理 attachment）
- 建立新頁面（目前只支援覆寫既有 `CONFLUENCE_PAGE_ID`，不支援 create）
- space 層級操作（搬移頁面、跨 space 複製）
- 對應上游 `confluence-skill` 的 mark CLI / CI-CD 同步流程
