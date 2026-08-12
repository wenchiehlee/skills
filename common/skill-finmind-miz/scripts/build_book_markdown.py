#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_book_markdown.py — 將 chrome-devtools 從 books.miz.com.tw epub 閱讀器
擷取出的章節 JSON，轉換為 Miz.Fetch 專案規範的 books/[書名]/ 資料夾結構
（metadata.md + 01.md, 02.md, ...）。

輸入 JSON 結構（由 SKILL.md 步驟 3 的 evaluate_script 產生）：
  {
    "toc": [ {"href": "...", "label": "...", "subitems": [...]}, ... ],
    "results": [ {"href": "Text/xxx.xhtml", "index": 0, "text": "..."}, ... ]
  }

用法：
  python build_book_markdown.py \
    --json book_201.json \
    --out-dir "books/窮查理的普通常識" \
    --title "窮查理的普通常識" \
    --author "查理．蒙格" \
    --source-url "https://books.miz.com.tw/read/201/epub" \
    --publisher "商業周刊"
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import sys
from pathlib import Path

if platform.system() == "Windows":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def flatten_toc(toc: list[dict]) -> dict[str, str]:
    """將（可能巢狀的）toc 攤平為 {href basename: label}。"""
    mapping: dict[str, str] = {}

    def walk(items: list[dict]) -> None:
        for item in items:
            href = item.get("href", "")
            key = re.sub(r"^(\.\./)?Text/", "", href)
            label = (item.get("label") or "").strip()
            if key and label:
                mapping[key] = label
            subitems = item.get("subitems") or []
            if subitems:
                walk(subitems)

    walk(toc)
    return mapping


def build_chapters(data: dict, out_dir: Path, min_len: int) -> list[tuple[str, str, int]]:
    toc_map = flatten_toc(data.get("toc") or [])
    results = data.get("results") or []

    written: list[tuple[str, str, int]] = []
    n = 0
    for item in results:
        text = (item.get("text") or "").strip()
        if len(text) < min_len:
            continue
        key = re.sub(r"^Text/", "", item.get("href", ""))
        label = toc_map.get(key) or re.sub(r"\.xhtml$", "", key)
        n += 1
        fname = f"{n:02d}.md"
        (out_dir / fname).write_text(f"# {label}\n\n{text}\n", encoding="utf-8")
        written.append((fname, label, len(text)))
    return written


def write_metadata(
    out_dir: Path,
    title: str,
    author: str,
    source_url: str,
    publisher: str | None,
    fetch_date: str,
    intro: str,
) -> None:
    lines = [
        "# 書籍中繼資料",
        "",
        f"- **書名：** {title}",
        f"- **作者：** {author}",
    ]
    if publisher:
        lines.append(f"- **出版社：** {publisher}")
    lines += [
        f"- **來源：** {source_url}",
        f"- **擷取日期：** {fetch_date}",
        "",
        "## 簡介",
        intro or "（待補）",
        "",
    ]
    (out_dir / "metadata.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", required=True, type=Path, help="chrome-devtools 擷取出的章節 JSON 路徑")
    parser.add_argument("--out-dir", required=True, type=Path, help="輸出資料夾，例如 books/書名")
    parser.add_argument("--title", required=True, help="書名（寫入 metadata.md）")
    parser.add_argument("--author", required=True, help="作者（寫入 metadata.md）")
    parser.add_argument("--source-url", required=True, help="來源網址（寫入 metadata.md）")
    parser.add_argument("--publisher", default=None, help="出版社（可選）")
    parser.add_argument("--fetch-date", default=None, help="擷取日期 YYYY-MM-DD，預設留給呼叫端指定")
    parser.add_argument("--intro", default="", help="metadata.md 的簡介文字（可選）")
    parser.add_argument("--min-len", type=int, default=50, help="過濾章節的最小字數門檻，預設 50")
    args = parser.parse_args()

    if not args.json.exists():
        print(f"[build_book_markdown] 找不到 JSON 檔：{args.json}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(args.json.read_text(encoding="utf-8"))

    args.out_dir.mkdir(parents=True, exist_ok=True)

    fetch_date = args.fetch_date
    if not fetch_date:
        print(
            "[build_book_markdown] 未指定 --fetch-date，metadata.md 的擷取日期需自行補上。",
            file=sys.stderr,
        )
        fetch_date = ""

    written = build_chapters(data, args.out_dir, args.min_len)
    write_metadata(
        args.out_dir,
        title=args.title,
        author=args.author,
        source_url=args.source_url,
        publisher=args.publisher,
        fetch_date=fetch_date,
        intro=args.intro,
    )

    print(f"[build_book_markdown] 輸出 {len(written)} 個章節至 {args.out_dir}")
    for fname, label, length in written:
        print(f"  {fname}  {label}  ({length} 字)")
    print(f"  metadata.md")


if __name__ == "__main__":
    main()
