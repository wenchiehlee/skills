#!/usr/bin/env python3
"""Validate traceability and source/digest consistency for augmented knowledge."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def flatten(value) -> str:
    if isinstance(value, dict):
        return " ".join(f"{key} {flatten(item)}" for key, item in value.items())
    if isinstance(value, list):
        return " ".join(flatten(item) for item in value)
    return str(value)


def terms(text: str) -> set[str]:
    words = set(re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", text.lower()))
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        words.update(run[i:i + 2] for i in range(len(run) - 1))
    return words


def headings(source: str) -> list[str]:
    return [line.lstrip("# ").strip() for line in source.splitlines()
            if line.startswith("#")]


def validate(book: Path) -> dict:
    knowledge = book / ".knowledge"
    manifest = json.loads((knowledge / "manifest.json").read_text(encoding="utf-8"))
    digest_path = knowledge / "chapter-digests.json"
    digests = json.loads(digest_path.read_text(encoding="utf-8")) if digest_path.exists() else {"chapters": []}
    digest_by_source = {item.get("source"): item for item in digests.get("chapters", [])}
    quality_path = knowledge / "source-quality.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8")) if quality_path.exists() else {"issues": []}
    reviewed = {item.get("source"): item for item in quality.get("issues", [])}
    issues = []
    checked = 0

    for item in manifest.get("files", []):
        if item.get("role") != "chapter":
            continue
        checked += 1
        source_path = book / item["path"]
        digest_item = digest_by_source.get(item["path"])
        if not digest_item:
            issues.append({"source": item["path"], "severity": "error", "code": "missing_digest",
                           "message": "找不到對應 chapter digest"})
            continue
        actual_hash = sha256(source_path)
        if actual_hash != digest_item.get("source_sha256"):
            issues.append({"source": item["path"], "severity": "error", "code": "hash_mismatch",
                           "message": "原始章節已變更，digest 必須重新生成"})

        digest_text = flatten(digest_item.get("digest", ""))
        source_text = source_path.read_text(encoding="utf-8", errors="replace")
        overlap = len(terms(digest_text) & terms(source_text))
        source_headings = headings(source_text)
        evidence = digest_item.get("digest", {}).get("evidence", [])
        # A low overlap is a review signal only: OCR and paraphrasing can be valid.
        if overlap < 8:
            issues.append({"source": item["path"], "severity": "warning", "code": "low_source_overlap",
                           "message": f"digest 與原文可辨識詞彙重疊偏低（{overlap}）"})
        reviewed_issue = reviewed.get(item["path"])
        if reviewed_issue:
            issues.append({"source": item["path"], "severity": "warning", "acknowledged": True,
                           "code": reviewed_issue.get("status", "reviewed_source_issue"),
                           "message": reviewed_issue.get("impact", "已人工複核的來源品質問題")})

    return {
        "schema_version": 1,
        "book": manifest.get("book", book.name),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checked_chapters": checked,
        "passed": not any(issue["severity"] == "error" for issue in issues),
        "issues": issues,
    }


def render(report: dict) -> str:
    lines = [f"# Augmented Knowledge Validation: {report['book']}", "",
             f"檢查章節：{report['checked_chapters']}",
             f"結果：{'PASS' if report['passed'] else 'FAIL'}", ""]
    if not report["issues"]:
        lines.append("沒有發現問題。")
    else:
        lines += ["## 問題", ""]
        for issue in report["issues"]:
            label = "acknowledged-warning" if issue.get("acknowledged") else issue["severity"]
            lines.append(f"- [{label}] {issue['source']} `{issue['code']}`：{issue['message']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_dir", type=Path)
    args = parser.parse_args()
    book = args.book_dir.expanduser().resolve()
    report = validate(book)
    knowledge = book / ".knowledge"
    (knowledge / "validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (knowledge / "validation.md").write_text(render(report), encoding="utf-8")
    print(render(report), end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
