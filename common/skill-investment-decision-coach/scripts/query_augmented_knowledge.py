#!/usr/bin/env python3
"""Retrieve source-grounded investment knowledge for a user question.

This is a retrieval layer, not an investment advisor. It returns ranked
context for the SKILL.md reasoning workflow and preserves source locations.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

STOPWORDS = {
    "什麼", "如何", "可以", "是否", "應該", "為什麼", "哪些", "這個", "那個",
    "我們", "你們", "以及", "還有", "投資", "問題", "請問", "需要", "目前",
}


def book_dirs(root: Path) -> list[Path]:
    if (root / ".knowledge").is_dir():
        return [root]
    return sorted(
        path for path in root.iterdir()
        if path.is_dir() and (path / ".knowledge").is_dir()
    )


def terms(question: str) -> list[str]:
    ascii_terms = re.findall(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,}", question.lower())
    cjk_runs = re.findall(r"[\u3400-\u9fff]+", question)
    cjk_terms = []
    for run in cjk_runs:
        if len(run) <= 8:
            cjk_terms.append(run)
        cjk_terms.extend(run[i:i + 2] for i in range(len(run) - 1))
        cjk_terms.extend(run[i:i + 3] for i in range(len(run) - 2))
    result = []
    for term in ascii_terms + cjk_terms:
        if len(term) > 1 and term not in STOPWORDS and term not in result:
            result.append(term)
    return result


def flatten_text(value) -> str:
    if isinstance(value, dict):
        return " ".join(f"{key} {flatten_text(item)}" for key, item in value.items())
    if isinstance(value, list):
        return " ".join(flatten_text(item) for item in value)
    return str(value)


def score(text: str, query_terms: list[str]) -> tuple[int, list[str]]:
    lowered = text.lower()
    hits = [term for term in query_terms if term.lower() in lowered]
    return sum(lowered.count(term.lower()) for term in set(hits)), hits


def snippets(path: Path, query_terms: list[str], limit: int = 3) -> list[dict]:
    paragraphs = re.split(r"\n\s*\n", path.read_text(encoding="utf-8", errors="replace"))
    ranked = []
    for paragraph in paragraphs:
        points, hits = score(paragraph, query_terms)
        if points:
            ranked.append((points, paragraph.strip(), hits))
    ranked.sort(key=lambda item: item[0], reverse=True)
    result = []
    for _, paragraph, hits in ranked[:limit]:
        clean = re.sub(r"\s+", " ", paragraph)
        if len(clean) > 900:
            clean = clean[:900].rstrip() + "…"
        result.append({"text": clean, "matched_terms": hits})
    return result


def load_records(book: Path, query_terms: list[str]) -> list[dict]:
    knowledge = book / ".knowledge"
    digest_path = knowledge / "chapter-digests.json"
    records = []
    if digest_path.exists():
        data = json.loads(digest_path.read_text(encoding="utf-8"))
        for item in data.get("chapters", []):
            digest_text = flatten_text(item.get("digest", ""))
            points, hits = score(digest_text, query_terms)
            if points:
                records.append({
                    "book": data.get("book", book.name),
                    "source": item["source"],
                    "source_sha256": item.get("source_sha256"),
                    "kind": "chapter-digest",
                    "score": points + 5,
                    "matched_terms": hits,
                    "model": item.get("model"),
                    "digest": item.get("digest"),
                })

    framework = book / "投資策略框架.md"
    if framework.exists():
        content = framework.read_text(encoding="utf-8", errors="replace")
        points, hits = score(content, query_terms)
        if points:
            records.append({
                "book": book.name,
                "source": framework.name,
                "kind": "investment-framework",
                "score": points + 8,
                "matched_terms": hits,
                "snippets": snippets(framework, query_terms),
            })

    for record in list(records):
        if record["kind"] != "chapter-digest":
            continue
        source_path = book / record["source"]
        if source_path.exists():
            record["source_snippets"] = snippets(source_path, query_terms)
    return records


def render(question: str, query_terms: list[str], records: list[dict], top_k: int) -> str:
    selected = sorted(records, key=lambda item: item["score"], reverse=True)[:top_k]
    lines = [
        "# Augmented Knowledge Retrieval Context",
        "",
        f"問題：{question}",
        f"檢索詞：{', '.join(query_terms)}",
        f"命中來源：{len(selected)}",
        "",
        "此文件是檢索 context，不是最終投資建議。回答時必須依照 SKILL.md "
        "區分書中原則、目前事實、推論與條件式建議。",
        "",
    ]
    for index, record in enumerate(selected, start=1):
        lines += [
            f"## {index}. {record['book']} / {record['source']}",
            "",
            f"- 類型：{record['kind']}",
            f"- 相關度：{record['score']}",
            f"- 命中詞：{', '.join(record['matched_terms'])}",
        ]
        if record.get("model"):
            lines.append(f"- digest model：{record['model']}")
        if "digest" in record:
            lines += ["", "### 結構化 digest", "",
                      json.dumps(record["digest"], ensure_ascii=False, indent=2)]
        for label in ("source_snippets", "snippets"):
            if record.get(label):
                lines += ["", "### 原始來源片段", ""]
                for snippet in record[label]:
                    lines.append(f"- {snippet['text']}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("books_dir", type=Path)
    parser.add_argument("question", nargs="+")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = args.books_dir.expanduser().resolve()
    if not root.is_dir():
        parser.error(f"資料夾不存在：{root}")
    question = " ".join(args.question)
    query_terms = terms(question)
    if not query_terms:
        parser.error("問題沒有可檢索的有效詞彙")
    records = []
    for book in book_dirs(root):
        records.extend(load_records(book, query_terms))
    if not records:
        print("沒有找到相關增強知識或書籍來源。")
        return 1
    output = render(question, query_terms, records, args.top_k)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
        print(f"[ok] saved {args.output}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
