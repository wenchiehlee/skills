---
name: skill-sharepoint-sync
description: Access a single SharePoint file through an approved Microsoft Graph delegated app or the user's policy-compliant signed-in browser. Use when asked to download or sync a SharePoint file, when a *.sharepoint.com background fetch returns 401, or when enterprise SSO or device-compliance policy blocks automated access.
---

# SharePoint Sync Skill（符合企業政策的單檔讀寫與下載）

## 問題背景

像 `barcozone.sharepoint.com` 這類企業 SharePoint 站點，瀏覽器開啟時會
要求 Azure AD SSO 登入。背景自動化工具（例如用 `requests`/`curl` 直接打
分享連結）沒有登入 session，收到的回應是：

```
由於 SharePoint 需要企業 SSO 驗證（回傳 401），因此自動存取被封鎖。
```

這不一定代表連結失效；背景請求沒有使用者的登入 session。優先使用租戶
核准的 Microsoft Graph delegated app。若租戶限制該應用程式或要求受管理
裝置，必須遵守該政策，改用核准的登入方式或由使用者透過合規瀏覽器下載；
不得嘗試繞過 SSO、應用程式指派或裝置合規要求。

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

## Graph 認證：核准的 delegated app

走 Microsoft Graph API 的 **delegated（代表使用者）** 認證，用個人企業
帳號登入。能否使用特定 app、權限與登入流程由租戶政策決定：

- `client_id` 未設定 `SHAREPOINT_CLIENT_ID` 時使用 Microsoft Graph PowerShell
  的公開用戶端 ID
  `14d82eec-204b-4c2f-b7e8-296a70dab67e`。租戶可能封鎖此 app，或要求
  管理員指派使用者、核准 delegated permissions；不能假設可直接登入，也
  不能藉由換用未核准的 client ID 解決。
- 只有在 IT 核准或指派 app 後，才使用其 client ID。第一次執行 `login`
  會啟動 device-code 登入；由使用者在 Microsoft 登入頁完成 SSO/MFA。
  MSAL 會把 token cache 存到
  `~/.cache/skill-sharepoint-sync/token_cache.json`。
- 之後每次執行 `read` / `write` / `info`，腳本會先嘗試
  `acquire_token_silent`，用快取的 refresh token 換發新的 access
  token，不會再跳出登入畫面（除非 refresh token 過期或被撤銷）。
- **不要要求、接收或儲存使用者密碼或 MFA 驗證碼。** 不使用密碼式
  OAuth（ROPC），也不從瀏覽器擷取 cookie、access token 或 refresh token。

## 瀏覽器下載備援：遵守 SSO 與裝置政策

遇到 `AADSTS50105`、Conditional Access 拒絕，或瀏覽器提示裝置/用戶端不
符合組織政策時，停止重試目前的 Graph app 或切換登入流程。錯誤表示 app
指派或裝置政策不符合，不是密碼輸入問題。

若使用者可透過瀏覽器存取該檔案：

1. 在組織核准且符合裝置合規要求的瀏覽器開啟原始 SharePoint 連結。若
   Chrome 被要求安裝組織擴充功能，只有在使用者/IT 核准時才安裝；可改用
   組織核准的 Microsoft Edge。
   Windows 上若 Edge 已安裝，可將原始連結交給 Edge 開啟：

   ```powershell
   $url = "<SharePoint share URL>"
   Start-Process "microsoft-edge:$url"
   ```

2. 由使用者直接在瀏覽器完成登入與 MFA。不得請使用者把密碼、MFA 驗證碼
   或瀏覽器 token 貼到對話中。
3. 使用 SharePoint 頁面提供的 **Download** 功能。若目前工具無法控制該
   合規瀏覽器，請使用者自行下載並提供本機檔案；不要宣稱已下載，除非
   已確認檔案實際存在。

瀏覽器 fallback 只使用瀏覽器正常提供的已登入頁面與下載操作；它不會為
Graph 腳本建立 token cache，也不會讀取或匯出瀏覽器憑證。若 Graph API
仍是必要路徑，請 IT 指派目前 app，或提供核准的 public-client app 與所需
delegated permissions。

Chrome DevTools/CDP 只能連到已符合組織政策的使用者瀏覽器，並用於正常的
頁面導覽與下載操作；不得建立未受管理的替代 session、讀取瀏覽器儲存區，
或檢查/複製網路請求中的 cookie 與 token。

## 環境變數

| 變數 | 說明 |
| --- | --- |
| `SHAREPOINT_TENANT_ID` | Azure AD 租戶 ID 或網域（例如 `barco.onmicrosoft.com`）；不確定可先填 `common` |
| `SHAREPOINT_CLIENT_ID` | 選填；只有使用 IT 核准或指派的 public-client app 時才覆寫 |
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

在 Microsoft 登入頁完成公司帳號 SSO/MFA。若登入回報 app 未指派或租戶
政策拒絕，停止重試並依「瀏覽器下載備援」處理，或請 IT 核准 app。

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
| 背景直接打連結收到 401 | 使用已核准的 Graph delegated app；若無法使用，透過合規瀏覽器由使用者下載 |
| `AADSTS50105` / app 要求使用者指派 | 停止重試及切換 client ID；請 IT 指派使用者或提供核准的 app registration |
| Chrome 因裝置或用戶端政策被阻擋 | 不要繞過政策；改用組織核准、符合裝置合規要求的 Edge，或按 IT 指示安裝核准的擴充功能 |
| Graph API 回傳 401 | 確認 token、核准的 app 權限及檔案存取權；只有 token 過期或撤銷時才重新登入。若登入回報 `AADSTS50105`，停止重試並聯絡 IT |
| Graph scope 未獲核准或 consent 被拒絕 | 請 IT 核准所需 delegated permissions；不要改用未核准的 client ID |
| `SHAREPOINT_TENANT_ID` 不知道填什麼 | 先填 `common`，MSAL 登入時會依帳號自動導到正確租戶 |
| token 快取檔案損毀或想重新登入 | 刪除 `~/.cache/skill-sharepoint-sync/token_cache.json` 後重跑 `login` |

## 完成前檢查

- [ ] Graph 路徑使用核准的 app，且 `login` 後已用 `info` 確認能正確解析分享連結，再進行 `read`/`write`
- [ ] `write` 前先用 `info` 或 `read` 確認目前版本，避免覆蓋別人未同步的變更
- [ ] token 快取檔案（含 refresh token）只存在本機 `~/.cache/`，沒有提交進 git 或分享給他人
- [ ] 瀏覽器 fallback 僅使用組織核准的合規瀏覽器與頁面下載功能；未複製或匯出瀏覽器憑證

## 未來可擴充方向（視需求而定）

v1.1.0 支援單一檔案的 Graph 讀寫，以及在 Graph app/SSO 政策阻擋時由使用者
透過合規瀏覽器下載。若後續出現以下需求，再依當時
情境決定是否升版：

- 批次處理多個分享連結或整個資料夾
- SharePoint List（清單）資料的讀寫，而非檔案
- 用 Azure AD App Registration + client secret 走 application-only
  （無人值守）認證，取代目前的 delegated 登入
- 自動偵測 token 快取過期並主動提示重新登入
