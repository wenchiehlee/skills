#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_epub_to_md.py — 從 books.miz.com.tw（自架 Calibre-Web）用已登入 session
直接下載書籍的原始 epub 檔（/show/{id}/epub/file.epub），解析 OPF 取得書名/
作者/出版社，並依 spine 順序把每個 XHTML 章節轉成保留格式（標題/粗體/斜體/
清單/圖片）的 Markdown，同時抽出所有內嵌圖片，輸出成 Miz.Fetch 專案規範的
books/[書名]/ 資料夾結構（metadata.md + 00.md, 01.md, ...）。

這是本技能的**主要方法**：比透過 epub.js 閱讀器逐頁擷取純文字（見 SKILL.md
的 chrome-devtools 備援流程）更完整（保留排版與圖片），也更快（單次下載，
不需逐章節等待瀏覽器渲染）。前提是需要一組有效的登入 session cookie。

用法：
  python fetch_epub_to_md.py --id 201 --out-dir "books/窮查理的普通常識" \
      --session-cookie "$MIZ_SESSION_COOKIE"

  # 或先 export MIZ_SESSION_COOKIE=... 再省略 --session-cookie
  export MIZ_SESSION_COOKIE="eyJj..."
  python fetch_epub_to_md.py --id 152 --out-dir "books/投資最重要的事"

如何取得 session cookie：
  1. 用瀏覽器登入 https://books.miz.com.tw/login
  2. 打開瀏覽器 DevTools → Application/Storage → Cookies，複製 `session` 這個
     cookie 的值（一長串 JWT-like 字串）。
  3. 這組 cookie 通常效期頗長，但若失效（下載回傳非 200 或非 zip 內容），
     需要重新登入取得新值。
"""
from __future__ import annotations

import argparse
import io
import os
import platform
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

if platform.system() == "Windows":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import requests
except ImportError:
    print("[fetch_epub_to_md] 需要 requests：pip install requests", file=sys.stderr)
    sys.exit(1)

XLINK = "http://www.w3.org/1999/xlink"
BASE_URL = "https://books.miz.com.tw"


# ── XHTML → Markdown ─────────────────────────────────────────────────────────

def walk(elem) -> str:
    raw_tag = elem.tag
    tag = raw_tag.split("}")[-1].lower() if "}" in raw_tag else raw_tag.lower()

    if tag in ("script", "style", "head", "nav"):
        return ""

    text = elem.text or ""
    tail = elem.tail or ""
    children = "".join(walk(c) for c in elem)
    inner = text + children

    if tag == "h1":
        return f"# {inner.replace(chr(10), ' ').strip()}\n\n" + tail
    if tag == "h2":
        return f"## {inner.replace(chr(10), ' ').strip()}\n\n" + tail
    if tag == "h3":
        return f"### {inner.replace(chr(10), ' ').strip()}\n\n" + tail
    if tag == "h4":
        return f"#### {inner.replace(chr(10), ' ').strip()}\n\n" + tail
    if tag == "h5":
        return f"##### {inner.replace(chr(10), ' ').strip()}\n\n" + tail
    if tag == "p":
        t = inner.strip()
        return (t + "\n\n") + tail if t else tail
    if tag == "br":
        return "\n" + tail
    if tag in ("strong", "b"):
        return f"**{inner}**" + tail
    if tag in ("em", "i"):
        return f"*{inner}*" + tail
    if tag == "span":
        cls = elem.get("class", "")
        if "bold" in cls:
            return f"**{inner}**" + tail
        return inner + tail
    if tag == "li":
        return f"- {inner.strip()}\n" + tail
    if tag in ("ul", "ol"):
        return inner + "\n" + tail
    if tag == "img":
        src = elem.get("src", "")
        alt = elem.get("alt", "")
        name = os.path.basename(src.split("?")[0])
        return f"![{alt}](images/{name})\n\n" + tail
    if tag == "image":  # SVG <image>
        href = elem.get("href", "") or elem.get(f"{{{XLINK}}}href", "")
        if href:
            name = os.path.basename(href.split("?")[0])
            return f"![](images/{name})\n\n" + tail
        return tail
    return inner + tail


def xhtml_to_md(raw: str) -> str:
    raw = re.sub(r"<\?xml[^>]*\?>", "", raw)
    raw = re.sub(r"<!DOCTYPE[^>]*>", "", raw)
    for prefix, uri in [
        ("epub", "http://www.idpf.org/2007/ops"),
        ("xlink", XLINK),
        ("svg", "http://www.w3.org/2000/svg"),
    ]:
        ET.register_namespace(prefix, uri)
    try:
        root = ET.fromstring(raw.encode("utf-8"))
    except ET.ParseError:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)).strip()

    body = None
    for el in root.iter():
        t = el.tag.split("}")[-1].lower() if "}" in el.tag else el.tag.lower()
        if t == "body":
            body = el
            break
    if body is None:
        body = root

    md = walk(body)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


# ── OPF / spine parsing ───────────────────────────────────────────────────────

def get_opf_path(z: zipfile.ZipFile) -> str:
    container = z.read("META-INF/container.xml").decode("utf-8")
    m = re.search(r'full-path="([^"]+)"', container)
    if not m:
        raise ValueError("container.xml 缺少 full-path")
    return m.group(1)


def get_metadata(opf: str) -> dict:
    def _find(pattern: str) -> str:
        m = re.search(pattern, opf, re.S)
        return re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""

    return {
        "title": _find(r"<dc:title[^>]*>(.*?)</dc:title>"),
        "creator": _find(r"<dc:creator[^>]*>(.*?)</dc:creator>"),
        "publisher": _find(r"<dc:publisher[^>]*>(.*?)</dc:publisher>"),
        "language": _find(r"<dc:language[^>]*>(.*?)</dc:language>"),
    }


def get_spine(z: zipfile.ZipFile, opf_path: str, opf: str) -> list[str]:
    opf_dir = opf_path.rsplit("/", 1)[0] if "/" in opf_path else ""

    manifest = {
        m.group(1): m.group(2)
        for m in re.finditer(r'<item\b[^>]+\bid="([^"]+)"[^>]+\bhref="([^"]+)"', opf)
    }
    for m in re.finditer(r'<item\b[^>]+\bhref="([^"]+)"[^>]+\bid="([^"]+)"', opf):
        manifest.setdefault(m.group(2), m.group(1))

    spine_ids = re.findall(r'<itemref\b[^>]+\bidref="([^"]+)"', opf)
    result = []
    for sid in spine_ids:
        href = manifest.get(sid)
        if not href:
            continue
        zip_path = (opf_dir + "/" + href) if opf_dir else href
        result.append(zip_path.lstrip("/"))
    return result


# ── metadata.md ───────────────────────────────────────────────────────────────

def write_metadata_md(
    out_dir: Path,
    title: str,
    author: str,
    publisher: str,
    source_url: str,
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
        f"- **擷取日期：** {fetch_date}" if fetch_date else "- **擷取日期：** （待補）",
        "",
        "## 簡介",
        intro or "（待補）",
        "",
    ]
    (out_dir / "metadata.md").write_text("\n".join(lines), encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--id", required=True, type=int, help="books.miz.com.tw 的 book id")
    parser.add_argument("--out-dir", required=True, type=Path, help="輸出資料夾，例如 books/書名")
    parser.add_argument(
        "--session-cookie",
        default=os.environ.get("MIZ_SESSION_COOKIE", ""),
        help="Calibre-Web 登入後的 session cookie 值；預設讀取 MIZ_SESSION_COOKIE 環境變數",
    )
    parser.add_argument("--fetch-date", default="", help="擷取日期 YYYY-MM-DD，寫入 metadata.md")
    parser.add_argument("--intro", default="", help="metadata.md 的簡介文字（可選）")
    args = parser.parse_args()

    if not args.session_cookie:
        print(
            "[fetch_epub_to_md] 缺少 session cookie，請用 --session-cookie 或設定 MIZ_SESSION_COOKIE 環境變數。",
            file=sys.stderr,
        )
        sys.exit(1)

    headers = {
        "Cookie": f"session={args.session_cookie}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": f"{BASE_URL}/",
    }

    url = f"{BASE_URL}/show/{args.id}/epub/file.epub"
    source_url = f"{BASE_URL}/read/{args.id}/epub"
    print(f"[fetch_epub_to_md] 下載 {url} ...")
    resp = requests.get(url, headers=headers, timeout=120)
    if resp.status_code != 200:
        print(f"[fetch_epub_to_md] 下載失敗（HTTP {resp.status_code}）；session cookie 可能已過期。", file=sys.stderr)
        sys.exit(1)
    print(f"[fetch_epub_to_md]   {len(resp.content) // 1024} KB")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    img_dir = args.out_dir / "images"
    img_dir.mkdir(exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        all_names = z.namelist()

        img_names = [f for f in all_names if re.search(r"\.(jpe?g|png|gif|webp|svg)$", f, re.I)]
        for img_zip_path in img_names:
            dest = img_dir / os.path.basename(img_zip_path)
            dest.write_bytes(z.read(img_zip_path))
        print(f"[fetch_epub_to_md] 圖片：{len(img_names)} 張 → images/")

        opf_path = get_opf_path(z)
        opf = z.read(opf_path).decode("utf-8")
        meta = get_metadata(opf)
        spine = get_spine(z, opf_path, opf)
        print(f"[fetch_epub_to_md] 章節：{len(spine)} 個")

        written = 0
        for idx, zip_path in enumerate(spine):
            md_file = args.out_dir / f"{idx:02d}.md"
            try:
                raw = z.read(zip_path).decode("utf-8", errors="replace")
                md = xhtml_to_md(raw)
            except KeyError:
                print(f"[fetch_epub_to_md]   警告：{zip_path} 不存在於 zip 內", file=sys.stderr)
                md = ""
            except Exception as e:
                print(f"[fetch_epub_to_md]   錯誤 {zip_path}: {e}", file=sys.stderr)
                md = ""
            md_file.write_text(md, encoding="utf-8")
            written += 1

    write_metadata_md(
        args.out_dir,
        title=meta["title"],
        author=meta["creator"],
        publisher=meta["publisher"],
        source_url=source_url,
        fetch_date=args.fetch_date,
        intro=args.intro,
    )

    print(f"[fetch_epub_to_md] 完成：{written} 個章節 md + metadata.md → {args.out_dir}")
    print(f"[fetch_epub_to_md]   書名：{meta['title']}")
    print(f"[fetch_epub_to_md]   作者：{meta['creator']}")


if __name__ == "__main__":
    main()
