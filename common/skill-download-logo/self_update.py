#!/usr/bin/env python3
"""
self_update.py

此模組會在被 import 時自動檢查遠端 GitHub repo（wenchiehlee/skills）對應 skill
目錄的最新檔案，無論版本號為何，都會直接下載覆寫本地檔案，並在完成後
重新執行當前腳本，使使用者得到最新的實作。

使用方式：在每個 skill 的入口程式（如 download_logo.py）最前面加入
`import self_update`，即可獲得自動更新功能。
"""
import os
import sys
import urllib.request
from pathlib import Path

# -------------------------------------------------
# 1️⃣ 設定 - 只需要提供遠端 repo 與本 skill 的子路徑
# -------------------------------------------------
REMOTE_REPO = "wenchiehlee/skills"
# 本檔案所在的父目錄即為 skill 子目錄名稱（download-logo、skill-all-models-benchmark、...）
SKILL_SUBPATH = Path(__file__).resolve().parent.name

# 取得遠端檔案的 URL
def _remote_url(relative_path: str) -> str:
    return f"https://raw.githubusercontent.com/{REMOTE_REPO}/main/{SKILL_SUBPATH}/{relative_path}"

# -------------------------------------------------
# 2️⃣ 下載單一檔案（若失敗會印錯誤但不中斷流程）
# -------------------------------------------------
def _download_file(rel_path: str, dest_path: Path):
    url = _remote_url(rel_path)
    try:
        with urllib.request.urlopen(url) as resp:
            data = resp.read()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(data)
        print(f"[self_update] 已下載 {rel_path} → {dest_path}")
    except Exception as e:
        print(f"[self_update] 下載失敗 {rel_path}: {e}", file=sys.stderr)

# -------------------------------------------------
# 3️⃣ 執行更新動作：下載 SKILL.md、metadata.json 以及 scripts/*
# -------------------------------------------------
def _perform_update():
    base_dir = Path(__file__).resolve().parent
    # 必要檔案
    for fn in ["SKILL.md", "metadata.json"]:
        _download_file(fn, base_dir / fn)
    # scripts 目錄（若存在）
    scripts_dir = base_dir / "scripts"
    if scripts_dir.is_dir():
        # 取得遠端 scripts 檔案清單（簡化為下載所有 .py）
        # 這裡直接列舉目前本地的 .py 檔名，遠端若有新檔會在下次執行時被加入
        for py_file in scripts_dir.glob("*.py"):
            _download_file(f"scripts/{py_file.name}", scripts_dir / py_file.name)
        # 若遠端有新 .py 檔（本地不存在），嘗試下載目錄清單（此範例不支援自動列舉，
        # 使用者可自行在未來加入新檔案的下載）
    print("[self_update] 更新完成")

# -------------------------------------------------
# 4️⃣ 主流程：在 import 時執行檢查與更新
# -------------------------------------------------
def _needs_update() -> bool:
    # 簡化邏輯：只要遠端檔案可取得即認為需要更新（不比較版本）
    # 若想更精細，可在未來加入 eTag/Last-Modified 檢查
    try:
        # 嘗試抓取遠端 SKILL.md，如果回傳 200 即視為可更新
        with urllib.request.urlopen(_remote_url("SKILL.md")) as resp:
            return resp.status == 200
    except Exception:
        return False

if _needs_update():
    _perform_update()
    # 重新啟動當前腳本，保留原始參數
    os.execv(sys.executable, [sys.executable] + sys.argv)
else:
    # 沒有更新需求，直接返回
    pass
