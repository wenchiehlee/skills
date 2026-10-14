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
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path
from typing import Optional

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

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
