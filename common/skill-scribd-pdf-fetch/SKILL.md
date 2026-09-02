---
name: skill-scribd-pdf-fetch
description: 從 Scribd 文件網址（/document/... 或舊版 /doc/...）下載乾淨的 PDF 副本，透過外部工具 themrsami/scribd-downloader（headless Chrome + CDP 逐頁列印）執行，不將該工具原始碼複製進本登錄庫；自動處理 Chrome 130+（含 152.x）因 excludeSwitches 選項導致啟動即崩潰的已知相容性問題。適用於需要把 Scribd 上分享的券商報告、簡報、文件轉存為本地 PDF 的情境。
---

# Scribd PDF 擷取技能 (skill-scribd-pdf-fetch)

| 項目 | 內容 |
| :--- | :--- |
| 版本 | 1.0.0（詳見 `metadata.json`） |
| 登錄庫 | https://github.com/wenchiehlee/skills （`common/skill-scribd-pdf-fetch`） |
| 維護者 | wenchiehlee-money |
| 上游工具 | https://github.com/themrsami/scribd-downloader （外部相依，不隨本技能複製散布） |

此技能把「給一個 Scribd 文件網址、拿到本地乾淨 PDF」包裝成可重用流程。實際下載邏輯完全交給
外部開源工具 [`themrsami/scribd-downloader`](https://github.com/themrsami/scribd-downloader)（headless
Chrome 逐頁載入 + Chrome DevTools Protocol `Page.printToPDF`），本技能只負責：定位/下載該工具、
套用已知相容性修補、以非互動方式呼叫、整理輸出路徑。

## 📦 技能結構說明
```text
skill-scribd-pdf-fetch/
├── SKILL.md               # 本檔案
├── metadata.json          # 機器可讀 metadata，供版本檢查使用
├── self_update.py         # 從 skills 登錄庫檢查並更新此技能的工具
└── scripts/
    └── scribd_pdf_fetch.py  # 包裝腳本：定位/clone 上游 repo、套修補、呼叫下載、整理輸出
```

## ⚙️ 前置環境配置

- Python 3.10+、已安裝 Google Chrome。
- 不需要手動安裝 `selenium`/`pypdf` 等套件到*這個*技能環境——`scribd_pdf_fetch.py` 只是
  `subprocess` 呼叫上游 repo 裡的 `scribd-downloader.py`，套件是裝在**上游那個 clone 目錄**
  裡（用 `--install-deps` 觸發，或自行先 `pip install -r requirements.txt`）。

## 🚀 使用方式

### 方式 A：直接下載（自動 clone 上游 repo + 自動套相容性修補）
```bash
python scripts/scribd_pdf_fetch.py \
  "https://www.scribd.com/document/1072508675/Bernstein-Taiwan-Semiconductor-..." \
  --install-deps
```
第一次執行會把上游 repo clone 到預設路徑
`~/SynologyDrive/NAS/github.com/scribd-downloader`（可用 `--repo-dir` 覆蓋，例如已經手動
clone 過、或想指到另一份 checkout）。PDF 預設留在該 clone 目錄下，檔名與上游規則一致
（網址最後一段 + `.pdf`）。

### 方式 B：指定輸出目錄
```bash
python scripts/scribd_pdf_fetch.py "<scribd_url>" --out-dir ./data/reports
```
下載完成後把 PDF 從 `--repo-dir` 移動到 `--out-dir`（自動建立目錄）。

### 方式 C：指向已存在的本地 checkout
```bash
python scripts/scribd_pdf_fetch.py "<scribd_url>" --repo-dir /path/to/scribd-downloader
```

### 方式 D：作為模組整合進自己的排程腳本
```python
from pathlib import Path
from scripts.scribd_pdf_fetch import find_or_clone_repo, apply_chrome_compat_patch, run_downloader

repo_dir = find_or_clone_repo(Path.home() / "SynologyDrive/NAS/github.com/scribd-downloader")
apply_chrome_compat_patch(repo_dir)
pdf_path = run_downloader(repo_dir, "https://www.scribd.com/document/123456789/Title")
```

### 進階調校（透傳給上游）

大型/圖片多的文件可用上游支援的環境變數（見上游 README「Troubleshooting」），在呼叫
`scribd_pdf_fetch.py` 前於同一個 shell 設定即可：

```powershell
$env:SCRIBD_CDP_TIMEOUT="900"
$env:SCRIBD_PAGE_LOAD_TIMEOUT="180"
$env:SCRIBD_EXPORT_BATCH_SIZE="4"
python scripts/scribd_pdf_fetch.py "<scribd_url>"
```

## 已知相容性問題與自動修補

上游 `build_chrome_options()` 預設帶了：

```python
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)
```

在 Chrome 130+（已於 2026-09-02 用 Chrome 152.0.7977.65 + 對應版本 chromedriver 實測重現）
上，`excludeSwitches: ["enable-automation"]` 會讓 Chrome 進程啟動後立刻結束，
Selenium 回報 `session not created: Chrome instance exited.`。這兩行選項原本只是用來隱藏
「Chrome 正受到自動化軟體控制」的提示橫幅，headless 模式下本來就不會顯示該橫幅，移除後
下載流程可正常完成（已用 19 頁文件實測成功）。

`apply_chrome_compat_patch()` 會在**執行前**檢查並移除這兩行（只修改使用者本機的 clone，
不是上游原始碼的一部分、也不會被本技能重新散布）；找不到這兩行時視為已修好或版本不同，
安全略過（不會報錯）。要停用此行為（例如懷疑是別的原因造成崩潰、想看原始錯誤訊息），加
`--no-patch`。

若之後上游自行修好這個問題，`apply_chrome_compat_patch()` 會因為比對不到而自動變成 no-op，
不需要另外調整。

## 授權與合規注意事項（License / Compliance）

- 上游 repo：https://github.com/themrsami/scribd-downloader ，作者 Usama Nazir
  （GitHub: `fullstackusama` / `themrsami`）。
- 上游 README 聲明「Licensed under the MIT License」，但**該 repo 目前沒有實際的 LICENSE
  檔案**——已於 2026-09-02 查證：`gh api repos/themrsami/scribd-downloader/license` 回傳
  404，`git log --diff-filter=A --all` 也顯示這個 repo 從未新增過任何 LICENSE 檔。README
  裡的 MIT 徽章與「see the LICENSE file for details」連結目前是死連結。
- 因此本技能**不把 `scribd-downloader.py` 原始碼複製進 `wenchiehlee/skills`**（本登錄庫
  本身是公開、MIT 授權的 repo）——避免在我們自己的公開 MIT repo 裡間接夾帶一份只有 README
  文字聲明、缺少正式 LICENSE 檔的第三方程式碼，造成授權狀態不清楚。處理方式比照本登錄庫對
  `yt-dlp`（見 `skill-youtube-channel-fetch`）的作法：把它當成外部工具，執行期才
  clone/呼叫使用者自己機器上的副本，本登錄庫只保存呼叫它的包裝腳本（我們自己撰寫、屬於本
  repo 既有 MIT 授權範圍）與必要的相容性修補說明。
- 若上游之後補上正式 LICENSE 檔或修改授權聲明，需重新檢查本技能是否可以改為直接 vendor 原
  始碼；在那之前維持「外部相依、不 vendor」的作法。
- **使用範圍限制（延續上游 README 的 Disclaimer）**：僅供教育與研究用途，使用者需自行確保
  遵守著作權法與 Scribd 服務條款，只下載自己有權存取的文件。不得用於下載需付費解鎖、未取得
  授權或明確標示 DRM 保護的內容；若文件受 DRM 保護，上游工具本身也可能只會輸出空白頁（見上
  游 README「Troubleshooting → Blank pages in PDF」），不代表本技能繞過了任何保護機制。

## 🔄 版本管理與更新
- 唯一可信來源為 skills 登錄庫中的 `common/skill-scribd-pdf-fetch`
- 版本採語意化版本，記錄於 `metadata.json`
- 檢查並更新到登錄庫最新版本：
  ```bash
  python self_update.py
  ```
