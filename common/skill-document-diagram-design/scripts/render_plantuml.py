#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_plantuml.py — PlantUML (.puml / .planuml) 舊圖表比對用渲染工具

⚠️ 這不是本技能的輸出格式。本技能只用原生 HTML+SVG 產出圖表；PlantUML 只是
匯入來源（見 references/plantuml-support.md 的遷移流程與
scripts/import_plantuml_mindmap.py）。此腳本存在的唯一目的是在遷移過程中，
需要「先看一眼舊 PlantUML 圖現在長怎樣」以便跟改畫後的新版 SVG 對照時使用，
遷移完成後就用不到了——不要把它的輸出當成最終交付物。

三個子命令：
  proxy-src   印出「來源檔已在 GitHub 上」的 Markdown 嵌入片段（僅供對照舊版長相，
              不要用來當作遷移後的最終嵌入方式）
  hex-url     印出不需要先 push 檔案的 hex 內嵌 image URL
  fetch       下載渲染結果（svg/png）到本地檔案，供比對用

渲染引擎優先順序：
  1. 若設定環境變數 PLANTUML_JAR，改用本地 `java -jar $PLANTUML_JAR` 渲染（不連外）。
  2. 否則打公開伺服器 https://www.plantuml.com/plantuml （proxy-src / hex-url / fetch 皆同）。
"""
from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import urllib.request
from pathlib import Path

if platform.system() == "Windows":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PLANTUML_SERVER = "https://www.plantuml.com/plantuml"


def _read_source(path: Path) -> str:
    if not path.exists():
        print(f"[render_plantuml] 找不到來源檔：{path}", file=sys.stderr)
        sys.exit(1)
    return path.read_text(encoding="utf-8")


def _hex_encode(text: str) -> str:
    return text.encode("utf-8").hex()


def cmd_proxy_src(args: argparse.Namespace) -> None:
    raw_url = (
        f"https://raw.githubusercontent.com/{args.repo}/{args.branch}/{args.path}"
    )
    image_url = f"{PLANTUML_SERVER}/proxy?cache=no&fmt={args.fmt}&src={raw_url}"
    caption = args.caption or Path(args.path).stem
    print("<figure markdown=\"span\">")
    print(f"  ![{caption}]({image_url})")
    print(f"  <figcaption>{caption}</figcaption>")
    print("</figure>")
    print(f"\n# 一般 Markdown（Docsify 亦適用）：\n![{caption}]({image_url})")


def cmd_hex_url(args: argparse.Namespace) -> None:
    source = _read_source(Path(args.source))
    hex_text = _hex_encode(source)
    url = f"{PLANTUML_SERVER}/{args.fmt}/~h{hex_text}"
    print(url)


def _fetch_local_jar(jar: str, source_path: Path, fmt: str, out_path: Path) -> None:
    flag = {"svg": "-tsvg", "png": "-tpng"}.get(fmt)
    if flag is None:
        print(f"[render_plantuml] 本地 plantuml.jar 不支援格式：{fmt}", file=sys.stderr)
        sys.exit(1)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["java", "-jar", jar, flag, "-pipe"],
        input=source_path.read_bytes(),
        capture_output=True,
    )
    if result.returncode != 0:
        print(f"[render_plantuml] 本地渲染失敗：{result.stderr.decode('utf-8', 'replace')}", file=sys.stderr)
        sys.exit(1)
    out_path.write_bytes(result.stdout)
    print(f"[render_plantuml] 已輸出（本地 plantuml.jar）：{out_path}")


def cmd_fetch(args: argparse.Namespace) -> None:
    source_path = Path(args.source)
    out_path = Path(args.out) if args.out else source_path.with_suffix(f".{args.fmt}")

    jar = os.environ.get("PLANTUML_JAR")
    if jar:
        _fetch_local_jar(jar, source_path, args.fmt, out_path)
        return

    source = _read_source(source_path)
    hex_text = _hex_encode(source)
    url = f"{PLANTUML_SERVER}/{args.fmt}/~h{hex_text}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = resp.read()
    except Exception as e:
        print(f"[render_plantuml] 連線公開伺服器失敗：{e}", file=sys.stderr)
        print("[render_plantuml] 如在無法連外的環境，請設定 PLANTUML_JAR 指向本地 plantuml.jar。", file=sys.stderr)
        sys.exit(1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)
    print(f"[render_plantuml] 已輸出（公開伺服器）：{out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="PlantUML (.puml/.planuml) 產出工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("proxy-src", help="印出 proxy-src 模式的 Markdown 嵌入片段")
    p1.add_argument("path", help="來源檔在 repo 內的相對路徑，例如 docs/InvestmentStackVision.planuml")
    p1.add_argument("--repo", required=True, help="owner/repo，例如 wenchiehlee/mkdocs-investment")
    p1.add_argument("--branch", default="main")
    p1.add_argument("--fmt", default="svg", choices=["svg", "png"])
    p1.add_argument("--caption", default=None)
    p1.set_defaults(func=cmd_proxy_src)

    p2 = sub.add_parser("hex-url", help="印出 hex 內嵌 image URL（不需先 push）")
    p2.add_argument("source", help="本地 .puml/.planuml 檔案路徑")
    p2.add_argument("--fmt", default="svg", choices=["svg", "png"])
    p2.set_defaults(func=cmd_hex_url)

    p3 = sub.add_parser("fetch", help="下載渲染結果到本地檔案")
    p3.add_argument("source", help="本地 .puml/.planuml 檔案路徑")
    p3.add_argument("--fmt", default="svg", choices=["svg", "png"])
    p3.add_argument("--out", default=None, help="輸出檔案路徑（預設同名換副檔名）")
    p3.set_defaults(func=cmd_fetch)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
