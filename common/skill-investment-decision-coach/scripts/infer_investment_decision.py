#!/usr/bin/env python3
"""Create a source-grounded inference packet, optionally asking the LLM to answer."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import query_augmented_knowledge as query  # noqa: E402


def load_skill() -> str:
    return (SCRIPT_DIR.parent / "SKILL.md").read_text(encoding="utf-8")


def compact_context(context: str, limit: int) -> str:
    if len(context) <= limit:
        return context
    marker = "\n## "
    sections = context.split(marker)
    kept = sections[0]
    for section in sections[1:]:
        candidate = kept + marker + section
        if len(candidate) > limit:
            break
        kept = candidate
    return kept + "\n\n[其餘檢索 context 已保留在本地檔案，因 provider 長度限制未傳送。]"



def split_context(context: str, limit: int) -> list[str]:
    """Split retrieved sections without dropping them from the local artifact."""
    if len(context) <= limit:
        return [context]
    marker = "\n## "
    sections = context.split(marker)
    batches = []
    current = sections[0]
    for section in sections[1:]:
        candidate = current + marker + section
        if current and len(candidate) > limit:
            batches.append(current)
            current = marker + section
        else:
            current = candidate
    if current:
        batches.append(current)
    return batches


def make_batch_prompt(question: str, batch: str) -> str:
    return f"""你是投資研究資料整理器。
請只根據下列檢索 context，整理與問題直接相關的：核心原則、原文證據、限制、可能誤用。
不要補充目前市場事實，不要做買賣建議，不要捏造資料。使用繁體中文，保留來源檔案名稱。

問題：{question}

--- CONTEXT BATCH ---
{batch}
--- END CONTEXT BATCH ---
"""

def make_prompt(question: str, context: str, skill: str) -> str:
    return f"""你是投資決策教練。請嚴格依照以下 SKILL.md 回答問題。

回答必須分開標示：
1. 書中原則
2. 目前事實（若未提供，明確說明缺資料）
3. 推理與假設
4. thesis breaker 檢查
5. 條件式行動建議與待補資料

不可把書籍摘要當成目前市場事實，不可捏造資料，也不可把檢索結果直接當成買賣指令。

--- SKILL.md ---
{skill}
--- END SKILL.md ---

--- RETRIEVED CONTEXT ---
{context}
--- END RETRIEVED CONTEXT ---

使用者問題：{question}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("books_dir", type=Path)
    parser.add_argument("question", nargs="+")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-context-chars", type=int, default=24000)
    parser.add_argument("--batch-context-chars", type=int, default=12000,
                        help="--generate 時每批送給 context summarizer 的最大字元數")
    args = parser.parse_args()
    root = args.books_dir.expanduser().resolve()
    question = " ".join(args.question)
    query_terms = query.terms(question)
    records = []
    for book in query.book_dirs(root):
        records.extend(query.load_records(book, query_terms))
    if not records:
        raise SystemExit("沒有找到可用的增強知識 context")
    context = query.render(question, query_terms, records, args.top_k)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output or (root / ".work" / "inference" / f"{stamp}.md")
    output.parent.mkdir(parents=True, exist_ok=True)

    client = None
    batch_summaries = []
    if args.generate:
        from build_augmented_knowledge import get_llm_client, load_project_env
        load_project_env()
        client = get_llm_client(args.provider, args.model)
        batches = split_context(context, args.batch_context_chars)
        if len(batches) > 1:
            for index, batch in enumerate(batches, start=1):
                summary = client.generate(
                    make_batch_prompt(question, batch),
                    max_tokens=2500,
                    routing_task="investment_context_batch_summary",
                )
                batch_summaries.append(f"## Batch {index} Summary\n\n{summary}")
            generation_context = compact_context("\n\n".join(batch_summaries), args.max_context_chars)
        else:
            generation_context = compact_context(context, args.max_context_chars)
    else:
        batches = split_context(context, args.batch_context_chars)
        generation_context = compact_context(context, args.max_context_chars)
        batch_note = (
            f"\n\n[Inference batch mode: {len(batches)} batch(es); --generate 時會先逐批整理。]"
            if len(batches) > 1 else ""
        )
        generation_context += batch_note

    prompt = make_prompt(question, generation_context, load_skill())
    if not args.generate:
        output.write_text("# Investment Inference Packet\n\n" + prompt, encoding="utf-8")
        print(f"[ok] prepared {output}")
        return 0

    answer = client.generate(prompt, max_tokens=4096, routing_task="investment_decision_inference")
    output.write_text(
        "# Investment Inference Result\n\n"
        f"- question: {question}\n- provider: {client.last_provider}\n"
        f"- model: {client.last_model}\n\n{answer}\n\n"
        "## Batch Summaries\n\n" + ("\n\n".join(batch_summaries) or "（未分批；context 未超過 batch limit）") +
        "\n\n## Retrieved Context\n\n" + context,
        encoding="utf-8",
    )
    print(f"[ok] generated {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
