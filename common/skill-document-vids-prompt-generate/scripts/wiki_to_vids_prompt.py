#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wiki_to_vids_prompt.py — 維基百科與 PPT 轉 Google Vids 分鏡提示詞輔助工具

功能：
1. 提取 Wikipedia 條目或 PPT 文本中的關鍵事實與時間軸。
2. 根據 Google Vids 規範（單場景 3-10 秒、16:9 / 9:16）切分分鏡預算。
3. 檢查並警示 AI 罐頭詞（Puffery & AI Slop）。
4. 輸出標準化 Markdown / JSON 導演分鏡腳本。
"""

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

# AI 罐頭詞黑名單
AI_SLOP_KEYWORDS = [
    "璀璨的明珠", "劃時代的里程碑", "不可抹滅", "在當今快節奏的世界中",
    "值得注意的是", "深入探討", "令人嘆為觀止", "留給後人無限的啟發",
    "猶如", "不可忽視", "讓我們一同", "你有沒有想過", "揭開神秘面紗"
]

def check_ai_slop(text: str) -> list[str]:
    """檢測文本中是否包含 AI 罐頭關鍵詞"""
    found = []
    for kw in AI_SLOP_KEYWORDS:
        if kw in text:
            found.append(kw)
    return found

def estimate_duration_seconds(script: str) -> float:
    """估算旁白時長（中文字約每秒 3.5 字，英文單字每秒 2.5 字）"""
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', script))
    english_words = len(re.findall(r'[a-zA-Z0-9]+', script))
    duration = (chinese_chars / 3.6) + (english_words / 2.5)
    return max(round(duration, 1), 3.0)

def parse_facts_and_timeline(text: str, top_n: int = 5) -> list[dict]:
    """從文本中提取時間標記與核心事實"""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    facts = []
    year_pattern = re.compile(r'(\b\d{3,4}\s*年|\b(?:1[789]|20)\d{2}\b)')
    
    for line in lines:
        if len(line) < 15:
            continue
        match = year_pattern.search(line)
        time_tag = match.group(1) if match else "核心事實"
        facts.append({
            "time_tag": time_tag,
            "raw_text": line
        })
        if len(facts) >= top_n:
            break
            
    if not facts:
        # Fallback to lines
        for line in lines[:top_n]:
            facts.append({"time_tag": "重點", "raw_text": line})
            
    return facts

def generate_scene_template(facts: list[dict], aspect_ratio: str = "16:9", style: str = "vector-explainer") -> list[dict]:
    """將事實切分為符合 Google Vids 規範的分鏡草稿"""
    scenes = []
    for idx, fact in enumerate(facts, start=1):
        content = fact["raw_text"]
        short_script = content[:32] + ("…" if len(content) > 32 else "")
        dur = min(max(estimate_duration_seconds(short_script), 4.0), 8.0)

        if style == "vector-explainer":
            camera = "Static flat lay, subtle character animation" if idx % 2 == 1 else "Gentle push-in on UI whiteboard mockup"
            visual_prompt = (
                f"Minimalist 2D vector editorial illustration, warm cream background (#F5F2EB), modern flat design. "
                f"Subject: {content[:40]}. Clean rounded shapes, subtle drop shadows, pastel palette with teal and orange accents."
            )
            note = "扁平向量解說風格，保持角色與卡片視覺錨點一致，節奏明快。"
        else:
            camera = "Medium Shot, Steadycam push-in" if idx % 2 == 1 else "Wide Establishing, Slow tilt-down"
            visual_prompt = (
                f"Historical cinematic documentary footage, 1900s archival setting for: {content[:45]}. "
                "Cinematic natural lighting, 35mm film grain, authentic textures, no generic CGI."
            )
            note = f"聚焦於真實細節與時間感（{fact['time_tag']}），營造人類歷史紀錄片質感。"

        scene = {
            "scene_number": idx,
            "title": f"Scene {idx}: {fact['time_tag']}",
            "duration_seconds": int(dur),
            "aspect_ratio": aspect_ratio,
            "style": style,
            "camera_shot": camera,
            "visual_prompt": visual_prompt,
            "director_note": note,
            "voiceover_script": short_script,
            "ai_slop_warnings": check_ai_slop(short_script)
        }
        scenes.append(scene)
    return scenes

def format_markdown_output(scenes: list[dict]) -> str:
    """轉換為 Markdown 分鏡表"""
    lines = ["# Google Vids 導演級分鏡提示詞表\n"]
    for sc in scenes:
        lines.append(f"### Scene {sc['scene_number']}: {sc['title']}")
        lines.append(f"- **時長**：{sc['duration_seconds']}s | **畫幅**：{sc['aspect_ratio']}")
        lines.append(f"- **鏡頭運動**：{sc['camera_shot']}")
        lines.append(f"- **視覺提示詞 (Visual Prompt)**：\n  > {sc['visual_prompt']}")
        lines.append(f"- **導演筆記**：{sc['director_note']}")
        lines.append(f"- **配音腳本**：\n  > 「{sc['voiceover_script']}」")
        if sc["ai_slop_warnings"]:
            lines.append(f"- ⚠️ **AI 罐頭詞警告**：偵測到禁用詞 `{', '.join(sc['ai_slop_warnings'])}`，請重寫！")
        lines.append("")
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="Wikipedia / PPT to Google Vids Prompt Generator")
    parser.add_argument("--input", "-i", type=str, help="Input text file path")
    parser.add_argument("--text", "-t", type=str, help="Direct input string")
    parser.add_argument("--aspect-ratio", choices=["16:9", "9:16"], default="16:9", help="Target aspect ratio")
    parser.add_argument("--style", choices=["vector-explainer", "cinematic"], default="vector-explainer", help="Visual style system")
    parser.add_argument("--top-facts", type=int, default=5, help="Number of core facts to extract")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    args = parser.parse_args()

    text = ""
    if args.input:
        text = Path(args.input).read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        text = (
            "1903年12月17日，萊特兄弟在小鷹鎮完成了人類歷史上首次受控的動力飛行。\n"
            "1908年，萊特兄弟攜帶升級版飛行器抵達法國，在勒芒賽馬場公開飛行展示。\n"
            "1909年，美國陸軍通信兵團購買了首架軍用飛機，標誌著航空進入軍事領域。"
        )

    facts = parse_facts_and_timeline(text, top_n=args.top_facts)
    scenes = generate_scene_template(facts, aspect_ratio=args.aspect_ratio, style=args.style)

    if args.json:
        print(json.dumps(scenes, ensure_ascii=False, indent=2))
    else:
        print(format_markdown_output(scenes))

if __name__ == "__main__":
    main()
