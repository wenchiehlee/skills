#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
confluence_sync.py — 讀寫單一 Confluence Wiki 頁面

只處理「一個固定頁面」的讀取與覆寫，不處理多頁面、子頁面、附件或 space
層級操作。認證與目標頁面皆由環境變數（或 .env）提供：

    CONFLUENCE_EMAIL      Atlassian 帳號 email（Basic Auth 使用者名稱）
    CONFLUENCE_API_TOKEN  Atlassian API token（https://id.atlassian.com/manage-profile/security/api-tokens）
    CONFLUENCE_BASE_URL   例如 https://yourcompany.atlassian.net（不含 /wiki）
    CONFLUENCE_PAGE_ID    目標頁面的數字 ID

用法：
    # 讀取頁面，轉成 Markdown 印到 stdout
    python scripts/confluence_sync.py read

    # 讀取頁面，存成檔案
    python scripts/confluence_sync.py read --output page.md

    # 讀取原始 storage format（Confluence 的 XHTML）
    python scripts/confluence_sync.py read --format storage

    # 用本地 Markdown 檔覆寫頁面內容（會自動遞增 version）
    python scripts/confluence_sync.py write page.md

    # 覆寫前先預覽，不送出
    python scripts/confluence_sync.py write page.md --dry-run

    # 查詢頁面目前的 metadata（title / version / url）
    python scripts/confluence_sync.py info
"""
from __future__ import annotations

import argparse
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


REQUIRED_VARS = ["CONFLUENCE_EMAIL", "CONFLUENCE_API_TOKEN", "CONFLUENCE_BASE_URL"]


def get_config(page_id_override: Optional[str] = None) -> dict:
    missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
    if missing:
        print(
            "ERROR: 缺少必要環境變數: " + ", ".join(missing) + "\n"
            "請設定 CONFLUENCE_EMAIL / CONFLUENCE_API_TOKEN / CONFLUENCE_BASE_URL"
            "（可用 .env 或 shell 環境變數）",
            file=sys.stderr,
        )
        sys.exit(1)

    page_id = page_id_override or os.getenv("CONFLUENCE_PAGE_ID")
    if not page_id:
        print(
            "ERROR: 缺少 CONFLUENCE_PAGE_ID（或用 --page-id 指定目標頁面）",
            file=sys.stderr,
        )
        sys.exit(1)

    base_url = os.getenv("CONFLUENCE_BASE_URL", "").rstrip("/")
    if base_url.endswith("/wiki"):
        base_url = base_url[: -len("/wiki")]

    return {
        "email": os.getenv("CONFLUENCE_EMAIL"),
        "token": os.getenv("CONFLUENCE_API_TOKEN"),
        "base_url": base_url,
        "api_base": f"{base_url}/wiki/rest/api",
        "page_id": page_id,
    }


def make_session(config: dict) -> requests.Session:
    session = requests.Session()
    session.auth = (config["email"], config["token"])
    session.headers.update({"Content-Type": "application/json"})
    return session


def get_page(session: requests.Session, config: dict) -> dict:
    url = f"{config['api_base']}/content/{config['page_id']}"
    params = {"expand": "body.storage,version,space"}
    resp = session.get(url, params=params)
    if resp.status_code == 404:
        print(f"ERROR: 找不到頁面 {config['page_id']}（404）", file=sys.stderr)
        sys.exit(1)
    if resp.status_code == 401:
        print("ERROR: 認證失敗（401），請檢查 CONFLUENCE_EMAIL / CONFLUENCE_API_TOKEN", file=sys.stderr)
        sys.exit(1)
    resp.raise_for_status()
    return resp.json()


def storage_to_markdown(storage_html: str) -> str:
    try:
        from markdownify import markdownify as md
    except ImportError:
        print(
            "WARNING: 未安裝 markdownify，輸出將是未轉換的 storage HTML。"
            " 可用 pip install markdownify 取得乾淨的 Markdown。",
            file=sys.stderr,
        )
        return storage_html
    return md(storage_html, heading_style="ATX", bullets="-").strip() + "\n"


def markdown_to_storage(markdown_text: str) -> str:
    try:
        import markdown as md_lib
    except ImportError:
        print(
            "ERROR: 未安裝 markdown 套件，無法將 Markdown 轉成 Confluence storage format。"
            " 請執行 pip install markdown，或改用 --format storage 直接寫入已是 XHTML 的內容。",
            file=sys.stderr,
        )
        sys.exit(1)
    return md_lib.markdown(markdown_text, extensions=["fenced_code", "tables"])


def cmd_read(args: argparse.Namespace) -> None:
    config = get_config(args.page_id)
    session = make_session(config)
    page = get_page(session, config)

    storage_html = page["body"]["storage"]["value"]
    if args.format == "storage":
        output = storage_html
    else:
        output = storage_to_markdown(storage_html)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"已寫入 {args.output}（{len(output)} 字元）")
    else:
        print(output)


def cmd_write(args: argparse.Namespace) -> None:
    config = get_config(args.page_id)
    session = make_session(config)

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"ERROR: 找不到檔案 {args.file}", file=sys.stderr)
        sys.exit(1)
    content = file_path.read_text(encoding="utf-8")

    if args.format == "markdown":
        storage_html = markdown_to_storage(content)
    else:
        storage_html = content

    page = get_page(session, config)
    current_version = page["version"]["number"]
    new_version = current_version + 1
    title = args.title or page["title"]

    if args.dry_run:
        print("=" * 60)
        print("DRY-RUN，不會送出任何變更")
        print(f"Page ID: {config['page_id']}")
        print(f"Title:   {title}")
        print(f"Version: {current_version} -> {new_version}")
        print("-" * 60)
        print(storage_html[:800])
        if len(storage_html) > 800:
            print("...")
        print("=" * 60)
        return

    url = f"{config['api_base']}/content/{config['page_id']}"
    body = {
        "id": config["page_id"],
        "type": "page",
        "title": title,
        "space": {"key": page["space"]["key"]},
        "body": {"storage": {"value": storage_html, "representation": "storage"}},
        "version": {"number": new_version, "message": args.message or "Updated via confluence_sync.py"},
    }
    resp = session.put(url, json=body)
    if resp.status_code == 401:
        print("ERROR: 認證失敗（401）", file=sys.stderr)
        sys.exit(1)
    if resp.status_code == 409:
        print("ERROR: 版本衝突（409）— 頁面已被其他人更新，請重新讀取後再試", file=sys.stderr)
        sys.exit(1)
    resp.raise_for_status()
    result = resp.json()

    page_url = f"{config['base_url']}/wiki{result['_links']['webui']}"
    print(f"已更新頁面 {config['page_id']}（version {result['version']['number']}）")
    print(page_url)


def cmd_info(args: argparse.Namespace) -> None:
    config = get_config(args.page_id)
    session = make_session(config)
    page = get_page(session, config)
    page_url = f"{config['base_url']}/wiki{page['_links']['webui']}"

    print(f"Page ID: {page['id']}")
    print(f"Title:   {page['title']}")
    print(f"Space:   {page['space']['key']}")
    print(f"Version: {page['version']['number']}")
    print(f"URL:     {page_url}")


def main() -> None:
    parser = argparse.ArgumentParser(description="讀寫單一 Confluence Wiki 頁面")
    subparsers = parser.add_subparsers(dest="command", required=True)

    read_parser = subparsers.add_parser("read", help="讀取頁面內容")
    read_parser.add_argument("--page-id", help="覆寫 CONFLUENCE_PAGE_ID")
    read_parser.add_argument("--output", help="輸出檔案路徑（未指定則印到 stdout）")
    read_parser.add_argument("--format", choices=["markdown", "storage"], default="markdown")
    read_parser.set_defaults(func=cmd_read)

    write_parser = subparsers.add_parser("write", help="用本地檔案覆寫頁面內容")
    write_parser.add_argument("file", help="本地 Markdown 或 storage-format HTML 檔案")
    write_parser.add_argument("--page-id", help="覆寫 CONFLUENCE_PAGE_ID")
    write_parser.add_argument("--title", help="覆寫頁面標題（預設沿用現有標題）")
    write_parser.add_argument("--message", help="版本註記（version comment）")
    write_parser.add_argument("--format", choices=["markdown", "storage"], default="markdown")
    write_parser.add_argument("--dry-run", action="store_true", help="預覽但不送出")
    write_parser.set_defaults(func=cmd_write)

    info_parser = subparsers.add_parser("info", help="查詢頁面 metadata")
    info_parser.add_argument("--page-id", help="覆寫 CONFLUENCE_PAGE_ID")
    info_parser.set_defaults(func=cmd_info)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
