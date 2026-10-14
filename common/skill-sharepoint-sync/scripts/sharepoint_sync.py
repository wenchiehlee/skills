#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sharepoint_sync.py — 透過租戶核准的 OAuth delegated 認證讀寫一個
SharePoint 檔案。

背景：像 barcozone.sharepoint.com 這類企業 SharePoint 站點要求 Azure AD
SSO 登入，單純用 requests/urllib 背景連線下載分享連結會收到 401。本腳本
改用 MSAL delegated device-code flow 取得 access token，並在本地快取 token。
登入仍受租戶的 app assignment、permission consent 與 Conditional Access
政策限制；預設 client ID 不保證可供每個租戶或使用者使用。

環境變數：
    SHAREPOINT_TENANT_ID   Azure AD 租戶 ID 或網域（例如 barco.onmicrosoft.com），
                           不確定可先填 "common"，登入時用公司帳號即可
    SHAREPOINT_CLIENT_ID   選填，IT 核准或指派的 public-client app ID。
                           未設定時使用 Microsoft Graph PowerShell 公開
                           用戶端 ID；租戶可能要求指派或拒絕此 app。
    SHAREPOINT_SHARE_URL   目標檔案的 SharePoint 分享連結或檔案網址
                           （就是瀏覽器點開會要求 SSO 登入、背景存取會
                           401 的那個連結）

用法：
    # 第一次使用：以租戶核准的 app 跑 device-code 登入並快取 token
    python scripts/sharepoint_sync.py login

    # 讀取檔案內容，存成本地檔案
    python scripts/sharepoint_sync.py read --output draft.docx

    # 查詢檔案 metadata（name / size / lastModified / webUrl）
    python scripts/sharepoint_sync.py info

    # 用本地檔案覆寫 SharePoint 上的檔案內容
    python scripts/sharepoint_sync.py write draft.docx

    # 以 Microsoft Edge 開啟 SharePoint 檔案並啟用 CDP 遠端偵錯（預設埠 9222）
    python scripts/sharepoint_sync.py edge
"""
from __future__ import annotations

import argparse
import base64
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Optional

# Fix Windows console encoding for Chinese characters
if platform.system() == "Windows":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import msal
except ImportError:
    print(
        "ERROR: 未安裝 msal，請先執行 pip install -r scripts/requirements.txt",
        file=sys.stderr,
    )
    sys.exit(1)


# Microsoft Graph PowerShell 的公開（public client）App ID。
# 租戶仍可能要求 app assignment、permission consent 或 Conditional Access。
DEFAULT_CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"

SCOPES = ["Files.ReadWrite.All", "Sites.ReadWrite.All"]

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

CACHE_DIR = Path.home() / ".cache" / "skill-sharepoint-sync"
CACHE_FILE = CACHE_DIR / "token_cache.json"


def get_config(share_url_override: Optional[str] = None) -> dict:
    tenant_id = os.getenv("SHAREPOINT_TENANT_ID")
    if not tenant_id:
        print("ERROR: 缺少 SHAREPOINT_TENANT_ID（不確定可先填 'common'）", file=sys.stderr)
        sys.exit(1)

    share_url = share_url_override or os.getenv("SHAREPOINT_SHARE_URL")
    if not share_url:
        print("ERROR: 缺少 SHAREPOINT_SHARE_URL（或用 --url 指定目標檔案連結）", file=sys.stderr)
        sys.exit(1)

    return {
        "tenant_id": tenant_id,
        "client_id": os.getenv("SHAREPOINT_CLIENT_ID", DEFAULT_CLIENT_ID),
        "share_url": share_url,
    }


def load_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if CACHE_FILE.exists():
        cache.deserialize(CACHE_FILE.read_text(encoding="utf-8"))
    return cache


def save_cache(cache: msal.SerializableTokenCache) -> None:
    if cache.has_state_changed:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(cache.serialize(), encoding="utf-8")


def get_app(config: dict, cache: msal.SerializableTokenCache) -> msal.PublicClientApplication:
    authority = f"https://login.microsoftonline.com/{config['tenant_id']}"
    return msal.PublicClientApplication(
        config["client_id"], authority=authority, token_cache=cache
    )


def acquire_token(config: dict, force_login: bool = False) -> str:
    cache = load_cache()
    app = get_app(config, cache)

    result = None
    if not force_login:
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(SCOPES, account=accounts[0])

    if not result:
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            print(f"ERROR: 無法啟動 device code flow: {flow}", file=sys.stderr)
            sys.exit(1)
        print(flow["message"])
        result = app.acquire_token_by_device_flow(flow)

    save_cache(cache)

    if "access_token" not in result:
        print(
            "ERROR: 登入失敗: "
            + result.get("error_description", str(result)),
            file=sys.stderr,
        )
        sys.exit(1)

    return result["access_token"]


def share_url_to_share_id(share_url: str) -> str:
    """Encode a SharePoint sharing URL into a Graph /shares/{shareId} token."""
    b64 = base64.urlsafe_b64encode(share_url.encode("utf-8")).decode("utf-8")
    return "u!" + b64.rstrip("=")


def resolve_drive_item(token: str, share_url: str) -> dict:
    share_id = share_url_to_share_id(share_url)
    url = f"{GRAPH_BASE}/shares/{share_id}/driveItem"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 401:
        print(
            "ERROR: Graph API 回傳 401 — 請確認 token、核准的 app 權限，"
            "以及帳號對此檔案的存取權。若登入回報 AADSTS50105，請停止重試並聯絡 IT。",
            file=sys.stderr,
        )
        sys.exit(1)
    if resp.status_code == 404:
        print("ERROR: 找不到這個分享連結對應的檔案（404）", file=sys.stderr)
        sys.exit(1)
    resp.raise_for_status()
    return resp.json()


def cmd_login(args: argparse.Namespace) -> None:
    config = get_config(args.url)
    acquire_token(config, force_login=True)
    print(f"登入成功，token 已快取到 {CACHE_FILE}")


def cmd_info(args: argparse.Namespace) -> None:
    config = get_config(args.url)
    token = acquire_token(config)
    item = resolve_drive_item(token, config["share_url"])

    print(f"Name:          {item.get('name')}")
    print(f"Size:          {item.get('size')} bytes")
    print(f"LastModified:  {item.get('lastModifiedDateTime')}")
    print(f"WebUrl:        {item.get('webUrl')}")
    print(f"DriveId:       {item.get('parentReference', {}).get('driveId')}")
    print(f"ItemId:        {item.get('id')}")


def cmd_read(args: argparse.Namespace) -> None:
    config = get_config(args.url)
    token = acquire_token(config)
    item = resolve_drive_item(token, config["share_url"])

    drive_id = item["parentReference"]["driveId"]
    item_id = item["id"]
    content_url = f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/content"

    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(content_url, headers=headers)
    resp.raise_for_status()

    output_path = Path(args.output) if args.output else Path(item["name"])
    output_path.write_bytes(resp.content)
    print(f"已下載 {item['name']} -> {output_path}（{len(resp.content):,} bytes）")


def cmd_write(args: argparse.Namespace) -> None:
    config = get_config(args.url)
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"ERROR: 找不到檔案 {args.file}", file=sys.stderr)
        sys.exit(1)

    token = acquire_token(config)
    item = resolve_drive_item(token, config["share_url"])

    drive_id = item["parentReference"]["driveId"]
    item_id = item["id"]
    content_url = f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/content"

    data = file_path.read_bytes()
    if args.dry_run:
        print("DRY-RUN，不會真的上傳")
        print(f"目標檔案: {item['name']} ({item_id})")
        print(f"本地檔案: {file_path}（{len(data):,} bytes）")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/octet-stream",
    }
    resp = requests.put(content_url, headers=headers, data=data)
    if resp.status_code == 401:
        print(
            "ERROR: Graph API 認證失敗（401）— 請確認 token、核准的 app 權限，"
            "以及帳號對此檔案的存取權。",
            file=sys.stderr,
        )
        sys.exit(1)
    resp.raise_for_status()
    result = resp.json()

    print(f"已更新 {result.get('name')}（{len(data):,} bytes）")
    print(result.get("webUrl"))


def find_edge_path() -> Optional[Path]:
    """尋找 Microsoft Edge 執行檔路徑。"""
    p = shutil.which("msedge")
    if p:
        return Path(p)
    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Microsoft"
        / "Edge"
        / "Application"
        / "msedge.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Microsoft"
        / "Edge"
        / "Application"
        / "msedge.exe",
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Microsoft"
        / "Edge"
        / "Application"
        / "msedge.exe",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def check_cdp_status(port: int = 9222) -> Optional[dict]:
    """檢查 CDP 埠號是否可正常通訊，回傳 /json/version 資料。"""
    try:
        resp = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=1.5)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def get_cdp_targets(port: int = 9222) -> list[dict]:
    """取得目前 Edge 瀏覽器中所有 targets / tabs。"""
    try:
        resp = requests.get(f"http://127.0.0.1:{port}/json/list", timeout=2)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return []


def open_cdp_tab(url: str, port: int = 9222) -> Optional[dict]:
    """透過 CDP HTTP endpoint 在既有瀏覽器實例中建立新分頁並導向 URL。"""
    try:
        quoted = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=")
        resp = requests.put(f"http://127.0.0.1:{port}/json/new?{quoted}", timeout=3)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def cmd_edge(args: argparse.Namespace) -> None:
    port = args.port
    share_url = args.url or os.getenv("SHAREPOINT_SHARE_URL")

    if args.check_only:
        ver = check_cdp_status(port)
        if ver:
            print(f"✓ CDP 遠端偵錯埠 (127.0.0.1:{port}) 連線正常")
            print(f"  瀏覽器版本 : {ver.get('Browser')}")
            print(f"  通訊協定   : {ver.get('Protocol-Version')}")
            print(f"  WebSocket  : {ver.get('webSocketDebuggerUrl')}")
            targets = get_cdp_targets(port)
            print(f"  目前分頁數 : {len(targets)}")
            for t in targets[:5]:
                print(f"    - [{t.get('type')}] {t.get('title', '')[:40]} ({t.get('url', '')[:60]})")
        else:
            print(f"✗ 無法連線至 CDP 埠號 127.0.0.1:{port}。請確認 Edge 是否已帶 --remote-debugging-port 啟動。")
            sys.exit(1)
        return

    if not share_url:
        print("ERROR: 缺少目標檔案連結，請使用 --url 指定或在 .env 設定 SHAREPOINT_SHARE_URL", file=sys.stderr)
        sys.exit(1)

    # 檢查 CDP 是否已經在監聽
    ver = check_cdp_status(port)
    if ver:
        print(f"✓ 偵測到既有 Edge 已啟用 CDP（127.0.0.1:{port}，{ver.get('Browser')}）")
        tab = open_cdp_tab(share_url, port)
        if tab:
            print(f"✓ 已透過 CDP 開啟分頁: {share_url}")
            print(f"  分頁 ID    : {tab.get('id')}")
            print(f"  WebSocket  : {tab.get('webSocketDebuggerUrl')}")
        else:
            print(f"⚠️  CDP 埠號在線上，但建立分頁失敗，請手動確認瀏覽器視窗。")
        return

    # 未監聽，需啟動 Edge
    edge_bin = find_edge_path()
    if not edge_bin:
        print("ERROR: 找不到 Microsoft Edge 執行檔 (msedge.exe)", file=sys.stderr)
        sys.exit(1)

    cmd = [str(edge_bin), f"--remote-debugging-port={port}"]

    if args.kill_existing:
        print("正在關閉既有 msedge 行程以套用預設 Profile 並啟用 CDP…")
        subprocess.run(["taskkill", "/IM", "msedge.exe", "/F"], capture_output=True)
        time.sleep(1)
    else:
        # 使用專用 User Data Dir，確保即使一般 Edge 正在執行也能成功啟動獨立 CDP 實例
        user_data_dir = args.user_data_dir
        if not user_data_dir:
            base_appdata = os.environ.get("LOCALAPPDATA", str(Path.home()))
            user_data_dir = str(Path(base_appdata) / "Microsoft" / "Edge" / "User Data - CDP")
        cmd.append(f"--user-data-dir={user_data_dir}")

    cmd.append(share_url)

    print(f"啟動 Microsoft Edge 並啟用 CDP（埠號 {port}）…")
    flags = (
        subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        if platform.system() == "Windows"
        else 0
    )
    subprocess.Popen(cmd, creationflags=flags)

    # 等待 CDP 埠號就緒
    connected = False
    for _ in range(10):
        time.sleep(0.5)
        ver = check_cdp_status(port)
        if ver:
            connected = True
            print(f"✓ Edge 已就緒且 CDP 監聽中（127.0.0.1:{port}）")
            print(f"  瀏覽器版本 : {ver.get('Browser')}")
            print(f"  WebSocket  : {ver.get('webSocketDebuggerUrl')}")
            break

    if not connected:
        print(f"⚠️  Edge 已啟動，但在 5 秒內未能偵測到 CDP 埠號 {port}。若未開啟成功，請嘗試加上 --kill-existing。")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="用租戶核准的 Microsoft Graph delegated app 讀寫一個 SharePoint 檔案"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    login_parser = subparsers.add_parser("login", help="跑一次 device code 登入並快取 token")
    login_parser.add_argument("--url", help="覆寫 SHAREPOINT_SHARE_URL")
    login_parser.set_defaults(func=cmd_login)

    info_parser = subparsers.add_parser("info", help="查詢檔案 metadata")
    info_parser.add_argument("--url", help="覆寫 SHAREPOINT_SHARE_URL")
    info_parser.set_defaults(func=cmd_info)

    read_parser = subparsers.add_parser("read", help="下載檔案內容")
    read_parser.add_argument("--url", help="覆寫 SHAREPOINT_SHARE_URL")
    read_parser.add_argument("--output", help="輸出檔案路徑（未指定則用原檔名存在目前目錄）")
    read_parser.set_defaults(func=cmd_read)

    write_parser = subparsers.add_parser("write", help="用本地檔案覆寫 SharePoint 上的內容")
    write_parser.add_argument("file", help="本地檔案路徑")
    write_parser.add_argument("--url", help="覆寫 SHAREPOINT_SHARE_URL")
    write_parser.add_argument("--dry-run", action="store_true", help="預覽但不送出")
    write_parser.set_defaults(func=cmd_write)

    edge_parser = subparsers.add_parser(
        "edge",
        aliases=["open-edge"],
        help="以 Microsoft Edge 開啟 SharePoint 檔案並啟用 CDP 遠端偵錯（預設埠 9222）",
    )
    edge_parser.add_argument("--url", help="覆寫 SHAREPOINT_SHARE_URL")
    edge_parser.add_argument("--port", type=int, default=9222, help="CDP 遠端偵錯埠號（預設 9222）")
    edge_parser.add_argument(
        "--user-data-dir",
        help="自訂 Profile 路徑（預設使用 %%LOCALAPPDATA%%\\Microsoft\\Edge\\User Data - CDP）",
    )
    edge_parser.add_argument(
        "--kill-existing",
        action="store_true",
        help="強制關閉既有 Edge 行程，以預設 Profile 啟動 CDP",
    )
    edge_parser.add_argument(
        "--check-only",
        action="store_true",
        help="僅檢查 CDP 埠號是否正常連線，不重新啟動瀏覽器",
    )
    edge_parser.set_defaults(func=cmd_edge)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
