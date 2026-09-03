#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
import_plantuml_mindmap.py — 把 PlantUML mindmap（@startmindmap ... @endmindmap）
解析成中繼格式（IR，JSON），供手刻原生 HTML+SVG mindmap 用。

這是「匯入」工具，不是「輸出」工具：本技能不產出 PlantUML，只用它把舊圖表的
結構讀出來，改畫成原生風格。細節與遷移流程見 references/plantuml-support.md。

PlantUML mindmap 語法規則（本腳本支援的子集）：
  - 每行開頭是連續的 `+` 或 `-`，數量代表深度（1 個 = 第 1 層）；
    `+` 畫在右側、`-` 畫在左側（PlantUML 慣例）。
  - 深度符號後可接 `[#顏色名]` 標記節點顏色。
  - 節點文字可包含 `**粗體**`（轉成 IR 的 "bold": true，文字本身移除星號）。
  - 忽略 `!theme`、`skinparam` 等樣式指令與空行/註解（'）。

用法：
  python scripts/import_plantuml_mindmap.py InvestmentStackVision.planuml --out out.ir.json
  python scripts/import_plantuml_mindmap.py InvestmentStackVision.planuml   # 印到 stdout
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import sys
from pathlib import Path
from typing import Optional

if platform.system() == "Windows":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

LINE_RE = re.compile(r"^(?P<sign>[+-]{1,})(\[#(?P<color>[A-Za-z0-9]+)\])?\s*(?P<text>.+)$")


class Node:
    def __init__(self, text: str, bold: bool, color: Optional[str], side: str):
        self.text = text
        self.bold = bold
        self.color = color
        self.side = side
        self.children: list["Node"] = []

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "bold": self.bold,
            "color": self.color,
            "side": self.side,
            "children": [c.to_dict() for c in self.children],
        }


def _parse_text(raw: str) -> tuple[str, bool]:
    bold = "**" in raw
    text = raw.replace("**", "").strip()
    return text, bold


def parse_mindmap(source: str) -> Node:
    lines = [l.rstrip() for l in source.splitlines()]
    body_lines = []
    in_block = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("@startmindmap"):
            in_block = True
            continue
        if stripped.startswith("@endmindmap"):
            break
        if not in_block:
            continue
        if not stripped or stripped.startswith("'"):
            continue
        if stripped.startswith("!") or stripped.startswith("skinparam"):
            continue
        body_lines.append(line)

    if not body_lines:
        raise ValueError("找不到 @startmindmap/@endmindmap 區塊，或區塊內沒有節點")

    root: Optional[Node] = None
    stack: list[tuple[int, Node]] = []  # (depth, node)

    for line in body_lines:
        m = LINE_RE.match(line.strip())
        if not m:
            print(f"[import_plantuml_mindmap] 略過無法解析的行：{line!r}", file=sys.stderr)
            continue

        sign = m.group("sign")
        depth = len(sign)
        side = "right" if sign[0] == "+" else "left"
        color = m.group("color")
        text, bold = _parse_text(m.group("text"))

        node = Node(text=text, bold=bold, color=color, side=side)

        if root is None:
            root = node
            stack = [(depth, node)]
            continue

        while stack and stack[-1][0] >= depth:
            stack.pop()

        if not stack:
            print(
                f"[import_plantuml_mindmap] 節點 {text!r} 深度異常（找不到父節點），掛回根節點",
                file=sys.stderr,
            )
            root.children.append(node)
        else:
            stack[-1][1].children.append(node)

        stack.append((depth, node))

    if root is None:
        raise ValueError("解析後沒有任何節點")

    return root


def main() -> None:
    parser = argparse.ArgumentParser(description="把 PlantUML mindmap 解析成 IR JSON")
    parser.add_argument("source", help="來源 .puml/.planuml 檔案路徑")
    parser.add_argument("--out", default=None, help="輸出 JSON 路徑，預設印到 stdout")
    args = parser.parse_args()

    source_path = Path(args.source)
    if not source_path.exists():
        print(f"[import_plantuml_mindmap] 找不到來源檔：{source_path}", file=sys.stderr)
        sys.exit(1)

    text = source_path.read_text(encoding="utf-8")
    try:
        root = parse_mindmap(text)
    except ValueError as e:
        print(f"[import_plantuml_mindmap] {e}", file=sys.stderr)
        sys.exit(1)

    ir = {"type": "mindmap", "root": root.to_dict()}
    output = json.dumps(ir, ensure_ascii=False, indent=2)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"[import_plantuml_mindmap] 已輸出：{out_path}")
    else:
        print(output)


if __name__ == "__main__":
    main()
