#!/usr/bin/env python3
"""Deterministically scan Miz.Fetch investment-book Markdown sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

SPECIAL_ROLES = {
    "metadata.md": "metadata",
    "書籍摘要.md": "book-summary",
    "投資策略框架.md": "investment-framework",
}
CHAPTER_RE = re.compile(r"^(?P<number>\d{1,4})(?:[-_].*)?\.md$", re.IGNORECASE)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def headings(path: Path) -> list[str]:
    result = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match:
            result.append(match.group(1).strip())
    return result


def classify(path: Path) -> tuple[str, int | None]:
    if path.name in SPECIAL_ROLES:
        return SPECIAL_ROLES[path.name], None
    match = CHAPTER_RE.match(path.name)
    return ("chapter", int(match.group("number"))) if match else ("supplementary", None)


def book_dirs(root: Path) -> list[Path]:
    if any(root.glob("*.md")):
        return [root]
    return sorted(path for path in root.iterdir() if path.is_dir() and not path.name.startswith("."))


def build_manifest(book: Path) -> dict:
    files = []
    for path in sorted(book.rglob("*.md")):
        relative = path.relative_to(book)
        if any(part.startswith(".") for part in relative.parts):
            continue
        role, number = classify(path)
        item = {
            "path": relative.as_posix(),
            "role": role,
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
            "headings": headings(path),
        }
        if number is not None:
            item["chapter_number"] = number
        files.append(item)

    chapters = sorted(
        (item for item in files if item["role"] == "chapter"),
        key=lambda item: (item["chapter_number"], item["path"]),
    )
    numbers = [item["chapter_number"] for item in chapters]
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    missing = []
    if numbers:
        missing = sorted(set(range(min(numbers), max(numbers) + 1)) - set(numbers))
    warnings = []
    if duplicates:
        warnings.append(f"duplicate chapter numbers: {duplicates}")
    if missing:
        warnings.append(f"missing chapter numbers: {missing}")
    if not chapters:
        warnings.append("no numeric chapter Markdown files found")

    return {
        "schema_version": 1,
        "book": book.name,
        "book_path": str(book),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
        "chapter_count": len(chapters),
        "chapter_numbers": numbers,
        "duplicate_chapters": duplicates,
        "missing_chapters": missing,
        "warnings": warnings,
    }


def render_index(manifest: dict) -> str:
    lines = [
        f"# {manifest['book']}：書籍來源索引",
        "",
        "此檔案由 scan_investment_books.py 產生，僅整理來源，不取代原始書籍內容。",
        "",
        f"- 來源資料夾：{manifest['book_path']}",
        f"- 章節數：{manifest['chapter_count']}",
        f"- 產生時間：{manifest['generated_at']}",
        "",
    ]
    if manifest["warnings"]:
        lines += ["## 掃描警告", ""] + [f"- {item}" for item in manifest["warnings"]] + [""]
    lines += [
        "## 檔案索引",
        "",
        "| 類型 | 檔案 | 章節 | 標題 | SHA-256 |",
        "|---|---|---:|---|---|",
    ]
    for item in manifest["files"]:
        title = "；".join(item["headings"][:3]) or "（無 Markdown 標題）"
        number = str(item.get("chapter_number", "")) if item["role"] == "chapter" else ""
        lines.append(
            f"| {item['role']} | {item['path']} | {number} | {title} | {item['sha256'][:16]}... |"
        )
    lines += [
        "",
        "## 使用規則",
        "",
        "- 原始章節檔是書籍證據的最高優先級。",
        "- 投資策略框架.md 是既有的投資應用整理，不等同於作者原文。",
        "- 後續 digest 或 augment 結論必須保留原始檔案路徑與標題。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("books_dir", type=Path, help="一本書的資料夾，或包含多本書的 books/ 根目錄")
    parser.add_argument("--output-dir", type=Path, help="覆寫知識輸出根目錄，預設寫入各書的 .knowledge/")
    args = parser.parse_args()

    root = args.books_dir.expanduser().resolve()
    if not root.is_dir():
        parser.error(f"資料夾不存在：{root}")
    directories = book_dirs(root)
    if not directories:
        parser.error(f"找不到書籍資料夾：{root}")

    for book in directories:
        manifest = build_manifest(book)
        output = (args.output_dir / book.name) if args.output_dir else book / ".knowledge"
        output.mkdir(parents=True, exist_ok=True)
        (output / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (output / "chapter-index.md").write_text(render_index(manifest), encoding="utf-8")
        print(f"[ok] {book}: {manifest['chapter_count']} chapters -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
