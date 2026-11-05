#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
jira_sync.py — 以與 confluence_sync.py 相同的 Atlassian 認證讀取 Jira issue / 留言

沿用同一組環境變數（或 .env），不需要額外設定：

    CONFLUENCE_EMAIL      Atlassian 帳號 email
    CONFLUENCE_API_TOKEN  Atlassian API token
    CONFLUENCE_BASE_URL   例如 https://yourcompany.atlassian.net（有無 /wiki 皆可）

TARGET 可以是 issue key（CS0048-8843）或 Jira 網址
（https://x.atlassian.net/browse/CS0048-8843?focusedCommentId=1724781，
Outlook safelinks 包裝過的網址也能解析）。

用法：
    python scripts/jira_sync.py issue CS0048-8843           # 摘要 / 狀態 / 描述
    python scripts/jira_sync.py comments CS0048-8843        # 全部留言
    python scripts/jira_sync.py comment <URL or KEY> [--id 1724781]
    python scripts/jira_sync.py add-comment CS0048-8843 "文字" [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from urllib.parse import parse_qs, unquote, urlparse

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

REQUIRED_VARS = ["CONFLUENCE_EMAIL", "CONFLUENCE_API_TOKEN", "CONFLUENCE_BASE_URL"]


def get_session() -> tuple[requests.Session, str]:
    missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
    if missing:
        print("ERROR: 缺少環境變數: " + ", ".join(missing), file=sys.stderr)
        sys.exit(1)
    base = os.environ["CONFLUENCE_BASE_URL"].rstrip("/")
    if base.endswith("/wiki"):
        base = base[: -len("/wiki")]
    session = requests.Session()
    session.auth = (os.environ["CONFLUENCE_EMAIL"], os.environ["CONFLUENCE_API_TOKEN"])
    session.headers.update({"Accept": "application/json"})
    return session, f"{base}/rest/api/3"


def parse_target(target: str) -> tuple[str, str | None]:
    """回傳 (issue_key, focusedCommentId)；支援 safelinks 包裝的網址。"""
    if target.startswith("http"):
        parsed = urlparse(target)
        inner = parse_qs(parsed.query).get("url")
        if inner:  # Outlook safelinks
            return parse_target(unquote(inner[0]))
        m = re.search(r"/browse/([A-Z][A-Z0-9]+-\d+)", parsed.path)
        if not m:
            print(f"ERROR: 無法從網址解析 issue key: {target}", file=sys.stderr)
            sys.exit(1)
        return m.group(1), parse_qs(parsed.query).get("focusedCommentId", [None])[0]
    return target, None


def adf_to_text(node) -> str:
    """把 Atlassian Document Format 攤平成純文字。"""
    if isinstance(node, list):
        return "".join(adf_to_text(n) for n in node)
    if not isinstance(node, dict):
        return ""
    t = node.get("type")
    if t == "text":
        return node.get("text", "")
    if t == "mention":
        return node["attrs"].get("text", "")
    if t == "inlineCard":
        return node["attrs"].get("url", "")
    if t == "hardBreak":
        return "\n"
    inner = adf_to_text(node.get("content", []))
    if t in ("paragraph", "heading", "listItem", "codeBlock"):
        return inner + "\n"
    return inner


def check(resp: requests.Response, what: str) -> dict:
    if resp.status_code == 401:
        print("ERROR: 認證失敗（401），請檢查 CONFLUENCE_EMAIL / CONFLUENCE_API_TOKEN", file=sys.stderr)
        sys.exit(1)
    if resp.status_code in (403, 404):
        print(f"ERROR: 無法存取 {what}（{resp.status_code}）", file=sys.stderr)
        sys.exit(1)
    resp.raise_for_status()
    return resp.json() if resp.content else {}


def print_comment(c: dict) -> None:
    print(f"--- {c['id']} | {c['author']['displayName']} | {c['created']}")
    print(adf_to_text(c["body"]).rstrip())


def cmd_issue(args) -> None:
    session, api = get_session()
    key, _ = parse_target(args.target)
    f = check(
        session.get(f"{api}/issue/{key}", params={"fields": "summary,status,description,assignee"}),
        key,
    )["fields"]
    print(f"{key}: {f['summary']}")
    print(f"Status:   {f['status']['name']}")
    print(f"Assignee: {(f.get('assignee') or {}).get('displayName', '-')}")
    print("\n" + adf_to_text(f.get("description")).rstrip())


def cmd_comments(args) -> None:
    session, api = get_session()
    key, _ = parse_target(args.target)
    data = check(session.get(f"{api}/issue/{key}/comment", params={"orderBy": "created"}), key)
    for c in data["comments"]:
        print_comment(c)
        print()


def cmd_comment(args) -> None:
    session, api = get_session()
    key, focused = parse_target(args.target)
    cid = args.id or focused
    if not cid:
        print("ERROR: 需要 --id 或含 focusedCommentId 的網址", file=sys.stderr)
        sys.exit(1)
    print_comment(check(session.get(f"{api}/issue/{key}/comment/{cid}"), f"{key} comment {cid}"))


def cmd_add_comment(args) -> None:
    session, api = get_session()
    key, _ = parse_target(args.target)
    body = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": line}]}
                for line in args.text.splitlines()
                if line.strip()
            ],
        }
    }
    if args.dry_run:
        print(f"DRY-RUN：將在 {key} 新增留言：\n{args.text}")
        return
    c = check(session.post(f"{api}/issue/{key}/comment", json=body), key)
    print(f"已新增留言 {c['id']} 到 {key}")


def main() -> None:
    p = argparse.ArgumentParser(description="讀取 Jira issue / 留言（與 confluence_sync 共用認證）")
    sub = p.add_subparsers(dest="command", required=True)

    for name, fn, h in (("issue", cmd_issue, "issue 摘要與描述"), ("comments", cmd_comments, "列出全部留言")):
        s = sub.add_parser(name, help=h)
        s.add_argument("target", help="issue key 或 Jira 網址")
        s.set_defaults(func=fn)

    s = sub.add_parser("comment", help="讀取單一留言")
    s.add_argument("target", help="issue key 或含 focusedCommentId 的網址")
    s.add_argument("--id", help="留言 ID（網址已含時可省略）")
    s.set_defaults(func=cmd_comment)

    s = sub.add_parser("add-comment", help="新增留言（純文字）")
    s.add_argument("target")
    s.add_argument("text")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_add_comment)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
