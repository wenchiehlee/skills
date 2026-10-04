#!/usr/bin/env python3
"""Build traceable chapter digests for the investment-book knowledge layer.

Default mode prepares prompts in .work. Pass --generate to call the repository's
LLMClient and save chapter digests under .knowledge. Generated chapters are
checkpointed after each successful chapter and can be resumed safely.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SOURCE_MARKER_RE = re.compile(r"\n?={10,}save results:={10,}\n?", re.IGNORECASE)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(book: Path) -> dict:
    path = book / ".knowledge" / "manifest.json"
    if not path.exists():
        raise SystemExit(f"缺少 manifest：{path}；請先執行 scan_investment_books.py")
    return json.loads(path.read_text(encoding="utf-8"))


def compact_source(content: str) -> str:
    """Remove OCR save-result separators and duplicate blocks, preserving order."""
    parts = SOURCE_MARKER_RE.split(content)
    seen = set()
    unique = []
    for part in parts:
        value = part.strip()
        normalized = re.sub(r"\s+", " ", value)
        if value and normalized not in seen:
            seen.add(normalized)
            unique.append(value)
    return "\n\n".join(unique)


def chunks(content: str, limit: int) -> list[str]:
    """Split at paragraph boundaries while keeping prompts below provider limits."""
    if len(content) <= limit:
        return [content]
    result = []
    current = []
    size = 0
    for paragraph in content.split("\n\n"):
        pieces = [paragraph[i:i + limit] for i in range(0, len(paragraph), limit)] or [""]
        for piece in pieces:
            if current and size + len(piece) + 2 > limit:
                result.append("\n\n".join(current))
                current = []
                size = 0
            current.append(piece)
            size += len(piece) + 2
    if current:
        result.append("\n\n".join(current))
    return result


def prompt_for(book: str, item: dict, content: str, part: int, total: int) -> str:
    headings = "；".join(item.get("headings", [])) or "（無標題）"
    part_label = f"（第 {part}/{total} 段）" if total > 1 else ""
    return f"""你是投資研究知識整理者。請分析以下投資書籍章節，輸出 JSON，不要輸出 Markdown。

書籍：{book}
來源檔案：{item["path"]}{part_label}
章節標題：{headings}

請使用繁體中文，建立可供投資決策教練檢索的結構化摘要。不要長篇逐字引用，也不要補充章節沒有支持的事實。輸出欄位必須包含：
{{
  "chapter_summary": "章節核心命題",
  "concepts": [{{"name": "概念", "definition": "定義", "investment_relevance": "投資關聯"}}],
  "principles": [{{"claim": "原則", "mechanism": "因果機制", "conditions": ["成立條件"], "misuse": ["常見誤用"]}}],
  "decision_questions": ["可用來檢查投資決策的問題"],
  "risks_and_failure_modes": ["限制、風險或失效條件"],
  "evidence": [{{"heading": "原始標題", "note": "支持哪個摘要結論"}}]
}}

原始章節內容：
---BEGIN SOURCE---
{content}
---END SOURCE---
"""


def load_project_env() -> None:
    """Load simple KEY=VALUE entries from the repository .env if unset."""
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name and value and name not in os.environ:
            os.environ[name] = value


def get_llm_client(provider: str | None, model: str | None):
    llm_root = Path(__file__).resolve().parents[4] / "llm"
    if llm_root.is_dir():
        sys.path.insert(0, str(llm_root))
    try:
        from llm import LLMClient
    except ImportError as exc:
        raise SystemExit("找不到 llm package；請設定相依路徑或不要使用 --generate") from exc
    kwargs = {"app_name": "MizFetchInvestmentKnowledge"}
    if provider:
        kwargs["providers"] = [provider]
    if model:
        kwargs["model"] = model
    return LLMClient(**kwargs)


def load_checkpoint(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 2, "book": "", "chapters": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_checkpoint(path: Path, manifest: dict, entries: list[dict]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "book": manifest["book"],
                "source_manifest_generated_at": manifest["generated_at"],
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "chapters": entries,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_dir", type=Path)
    parser.add_argument("--generate", action="store_true", help="呼叫 LLM 並保存 chapter-digests.json")
    parser.add_argument("--provider", help="LLM provider，例如 gemini、codex 或 mlx")
    parser.add_argument("--model", help="LLM model，例如 gpt-5.6-luna")
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--chunk-size", type=int, default=36000)
    parser.add_argument("--force", action="store_true", help="忽略既有同 hash digest，重新生成")
    args = parser.parse_args()

    book = args.book_dir.expanduser().resolve()
    manifest = load_manifest(book)
    chapters = [item for item in manifest["files"] if item["role"] == "chapter"]
    work = book / ".work" / "digest-prompts"
    knowledge = book / ".knowledge"
    output = knowledge / "chapter-digests.json"
    if not chapters:
        raise SystemExit("manifest 中沒有章節")
    if args.generate:
        load_project_env()
    client = get_llm_client(args.provider, args.model) if args.generate else None
    checkpoint = load_checkpoint(output)
    existing = {
        item["source"]: item
        for item in checkpoint.get("chapters", [])
        if item.get("source") and item.get("source_sha256")
    }
    entries = []
    prepared = 0

    for item in chapters:
        source = book / item["path"]
        source_hash = sha256(source)
        old = existing.get(item["path"])
        if args.generate and old and old["source_sha256"] == source_hash and not args.force:
            entries.append(old)
            print(f"[skip] {item['path']} unchanged")
            continue

        content = compact_source(source.read_text(encoding="utf-8", errors="replace"))
        source_chunks = chunks(content, args.chunk_size)
        prompts = [
            prompt_for(manifest["book"], item, part, index, len(source_chunks))
            for index, part in enumerate(source_chunks, start=1)
        ]

        if not args.generate:
            for index, prompt in enumerate(prompts, start=1):
                target = work / f"{Path(item['path']).stem}-part{index:02d}.json"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    json.dumps(
                        {
                            "source": item["path"],
                            "source_sha256": source_hash,
                            "part": index,
                            "parts": len(prompts),
                            "prompt": prompt,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            prepared += len(prompts)
            continue

        results = []
        for prompt in prompts:
            results.append(
                client.generate_json(
                    prompt,
                    max_tokens=args.max_tokens,
                    routing_task="book_chapter_digest",
                )
            )
        digest = results[0] if len(results) == 1 else {
            "chunk_digests": results,
            "source_chunks": len(results),
            "note": "本章因 provider prompt 上限分段消化；查詢時應合併所有 chunk_digests。",
        }
        entry = {
            "source": item["path"],
            "source_sha256": source_hash,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "provider": client.last_provider,
            "model": client.last_model,
            "source_chars_after_compaction": len(content),
            "digest": digest,
        }
        entries.append(entry)
        entries.sort(key=lambda value: value["source"])
        save_checkpoint(output, manifest, entries)
        print(f"[ok] digested {item['path']} ({len(prompts)} part(s)); checkpoint saved")

    if args.generate:
        print(f"[ok] saved {output} ({len(entries)} chapter(s))")
    else:
        print(f"[ok] prepared {prepared} prompt(s) under {work}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
