---
name: skill-sharepoint-sync
description: Resolve SharePoint SSO 401 blocking automated access by authenticating via Microsoft Graph API (MSAL device-code login, cached token), then read/write a single SharePoint file. Use when asked to "download SharePoint file", "SharePoint 401 SSO", "sync draft to SharePoint", or when a background fetch of a *.sharepoint.com link returns 401 Unauthorized.
---

# SharePoint Sync Skill（繞過企業 SSO 401 的單檔讀寫）

## 問題背景

像 `barcozone.sharepoint.com` 這類企業 SharePoint 站點，瀏覽器開啟時會
要求 Azure AD SSO 登入。背景自動化工具（例如用 `requests`/`curl` 直接打
分享連結）沒有登入 session，收到的回應是：

```
由於 SharePoint 需要企業 SSO 驗證（回傳 401），因此自動存取被封鎖。
```

這不是連結失效或權限不足，而是**background fetch 天生就無法通過互動式
SSO**。解法不是繞過驗證，而是用正式的 OAuth device-code 流程走一次互動
登入，把可長期使用的 refresh token 快取在本機，之後背景腳本就能靜默
（silent）換發 access token，不需要每次都開瀏覽器登入。

## 適用場景

- 自動化工具嘗試下載一個 SharePoint 分享連結的檔案，收到 401，需要改用
  有效的認證方式重新存取。
- 需要定期把本地草稿（例如 ADR 文件）同步覆寫回一個固定的 SharePoint
  檔案，或反過來把 SharePoint 上的最新版本拉下來本地編輯/摘要。
- 只需要查詢一個 SharePoint 檔案目前的 metadata（名稱、大小、最後修改
  時間、網址），確認版本狀態。

**不適用**：批次處理整個 SharePoint 站點/資料庫、管理權限與分享設定、
操作 SharePoint List/清單資料（這些需要更廣的 Graph 權限與不同的 API，
超出本技能範圍）。

## 認證方式：MSAL device-code + 本地 token 快取

走 Microsoft Graph API 的 **delegated（代表使用者）** 認證，用個人企業
帳號登入一次即可，**不需要向 IT 申請 Azure AD App Registration**：

- `client_id` 預設使用 Microsoft 官方公開用戶端 ID
  `14d82eec-204b-4c2f-b7e8-296a70dab67e`（Microsoft Graph PowerShell），
  絕大多數企業租戶已預先存在這個 App 且同意過基本 Graph 權限，可直接
  拿來做 device-code 登入。若公司政策擋掉這個 client id，再改用自己
  申請的 App Registration（設 `SHAREPOINT_CLIENT_ID` 覆寫即可）。
- 第一次執行 `login` 子指令會印出一個網址 + 一次性代碼，到瀏覽器完成
  SSO 登入後，MSAL 會把 refresh token 序列化存到
  `~/.cache/skill-sharepoint-sync/token_cache.json`。
- 之後每次執行 `read` / `write` / `info`，腳本會先嘗試
  `acquire_token_silent`，用快取的 refresh token 換發新的 access
  token，不會再跳出登入畫面（除非 refresh token 過期或被撤銷）。

## 環境變數

| 變數 | 說明 |
| --- | --- |
| `SHAREPOINT_TENANT_ID` | Azure AD 租戶 ID 或網域（例如 `barco.onmicrosoft.com`）；不確定可先填 `common` |
| `SHAREPOINT_CLIENT_ID` | 選填，覆寫預設的公開用戶端 ID |
| `SHAREPOINT_SHARE_URL` | 目標檔案的分享連結（就是背景存取會 401 的那個網址） |

放進 `.env`（不要提交進 git）：

```env
SHAREPOINT_TENANT_ID=barco.onmicrosoft.com
SHAREPOINT_SHARE_URL=https://barcozone.sharepoint.com/:w:/r/sites/xxx/_layouts/15/...
```

## 安裝依賴

```bash
pip install -r scripts/requirements.txt
```

## 核心指令

### 第一次使用：登入並快取 token

```bash
python scripts/sharepoint_sync.py login
```

會印出類似：

```
To sign in, use a web browser to open the page https://microsoft.com/devicelogin
and enter the code XXXXXXXXX to authenticate.
```

到瀏覽器完成公司帳號 SSO 登入即可，之後不用再重複這步，除非 token 過期
或切換到別的分享連結需要存取新資源（視租戶的 conditional access 政策）。

### 查詢檔案 metadata（info）

```bash
python scripts/sharepoint_sync.py info
```

### 下載檔案（read）

```bash
python scripts/sharepoint_sync.py read --output draft.docx
```

未指定 `--output` 時會用 SharePoint 上的原始檔名存到目前目錄。

### 覆寫檔案（write）

```bash
python scripts/sharepoint_sync.py write draft.docx

# 先預覽，不真的上傳
python scripts/sharepoint_sync.py write draft.docx --dry-run
```

`write` 是整份檔案覆寫（PUT content），不是差異合併。

### 用 `--url` 覆寫目標檔案

四個子指令都支援 `--url`，可臨時指定另一個分享連結，蓋過
`SHAREPOINT_SHARE_URL`。

## 常見錯誤

| 情況 | 處理 |
| --- | --- |
| 背景直接打連結收到 401 | 這就是本技能要解決的問題——改用 `login` 走一次 device-code 登入，之後用 `read`/`write` |
| `login` 後 `read`/`write` 還是 401 | 重新執行一次 `login`（`--force` 行為已內建在 login 子指令）；也可能是這個帳號對該檔案本身沒有存取權限，需先在瀏覽器確認能不能打開 |
| 公司政策擋掉預設 client id（AADSTS70011 之類錯誤） | 向 IT 申請一個 public client App Registration，設定 `SHAREPOINT_CLIENT_ID` 環境變數覆寫 |
| `SHAREPOINT_TENANT_ID` 不知道填什麼 | 先填 `common`，MSAL 登入時會依帳號自動導到正確租戶 |
| token 快取檔案損毀或想重新登入 | 刪除 `~/.cache/skill-sharepoint-sync/token_cache.json` 後重跑 `login` |

## 完成前檢查

- [ ] `login` 後已用 `info` 確認能正確解析分享連結，再進行 `read`/`write`
- [ ] `write` 前先用 `info` 或 `read` 確認目前版本，避免覆蓋別人未同步的變更
- [ ] token 快取檔案（含 refresh token）只存在本機 `~/.cache/`，沒有提交進 git 或分享給他人

## 未來可擴充方向（視需求而定）

v1.0.0 只處理單一檔案的讀寫與登入快取。若後續出現以下需求，再依當時
情境決定是否升版：

- 批次處理多個分享連結或整個資料夾
- SharePoint List（清單）資料的讀寫，而非檔案
- 用 Azure AD App Registration + client secret 走 application-only
  （無人值守）認證，取代目前的 delegated 登入
- 自動偵測 token 快取過期並主動提示重新登入
