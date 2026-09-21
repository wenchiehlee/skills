#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
svg_to_pptx.py — 把一組已轉出的 PNG 圖表組成 PowerPoint（.pptx）

輸入的圖片必須已經是 PNG（原生管線用 svg_to_png.py、PlantUML 管線用
render_plantuml.py fetch --fmt png 轉出），本腳本不做任何向量轉點陣的工作。

版型固定：16:9、每筆一張投影片、標題置頂、圖片等比縮放置中、可選講者備忘稿。
需要客製版型時，直接把 PNG 貼進既有 PPTX 範本更實際，不在此腳本擴充。

用法：
  python scripts/svg_to_pptx.py manifest.json --out deck.pptx

manifest.json 格式：
  [
    {
      "id": "flowchart",
      "title": "投資十步流程",
      "image": "flowchart.png",
      "notes": "對應 SKILL.md 十步判斷",
      "hotspots": [
        {"x": 0.1, "y": 0.2, "w": 0.15, "h": 0.08, "target": "detail-step3", "label": "第三步細節"}
      ],
      "nav": true
    },
    {"id": "detail-step3", "title": "第三步細節", "image": "step3.png"}
  ]
image 路徑為相對於 manifest.json 所在目錄的路徑。

pptx 原生只支援兩種「互動」：超連結跳轉（含 hotspots／action button）與預先定義的
播放動畫；後者的動畫時序（<p:timing>）沒有官方 API，本腳本不提供，需要動畫觸發的
簡報改用 open-slide（見 references/output-openslide.md）。

- `hotspots`（選填）：疊在圖片上的隱形可點擊熱區，x/y/w/h 是相對「圖片實際繪製範圍」
  的比例（0–1，非整張投影片），`target` 可以是別筆項目的 `id`，或 1-based 投影片編號。
  用於「點圖表裡的某個節點，跳到對應的詳細投影片」這種非線性瀏覽。
- `nav`（選填，布林值）：在該張投影片右下角加上 上一張／下一張／回首張 三個內建
  action button 圖示，方便非線性簡報時手動導覽。
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

if platform.system() == "Windows":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _resolve_target(entries: list, slides: list, ref) -> "object | None":
    """把 hotspot/nav 的 target 參照（id 字串或 1-based 編號）解成 slide 物件。"""
    if ref is None:
        return None
    if isinstance(ref, int):
        idx = ref - 1
    else:
        idx = next((i for i, e in enumerate(entries) if e.get("id") == ref), None)
        if idx is None:
            return None
    if 0 <= idx < len(slides):
        return slides[idx]
    return None


def build_pptx(manifest_path: Path, out_path: Path) -> None:
    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt, Emu
        from pptx.enum.shapes import MSO_SHAPE
    except ImportError:
        print("[svg_to_pptx] 缺少 python-pptx，請先執行：pip install python-pptx", file=sys.stderr)
        sys.exit(1)

    from PIL import Image

    if not manifest_path.exists():
        print(f"[svg_to_pptx] 找不到 manifest：{manifest_path}", file=sys.stderr)
        sys.exit(1)

    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    base_dir = manifest_path.parent

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    slide_w = prs.slide_width
    slide_h = prs.slide_height
    title_h = Inches(0.9)
    margin = Inches(0.5)

    # 第一輪：建立每張投影片與圖片，記錄畫面範圍供 hotspot 換算座標用。
    # slides[i] 對應 entries[i]（略過的項目仍佔位為 None，避免 target 編號位移）。
    slides: list = [None] * len(entries)
    image_boxes: list = [None] * len(entries)

    for i, entry in enumerate(entries):
        title = entry.get("title", "")
        image_rel = entry.get("image")
        notes = entry.get("notes")

        if not image_rel:
            print(f"[svg_to_pptx] 略過缺少 image 欄位的項目：{entry}", file=sys.stderr)
            continue

        image_path = base_dir / image_rel
        if not image_path.exists():
            print(f"[svg_to_pptx] 找不到圖片，略過：{image_path}", file=sys.stderr)
            continue

        slide = prs.slides.add_slide(blank_layout)
        slides[i] = slide

        if title:
            tb = slide.shapes.add_textbox(margin, Inches(0.2), slide_w - 2 * margin, title_h)
            tf = tb.text_frame
            tf.text = title
            tf.paragraphs[0].font.size = Pt(28)
            tf.paragraphs[0].font.bold = True

        with Image.open(image_path) as img:
            img_w_px, img_h_px = img.size

        area_top = title_h + Inches(0.3) if title else margin
        area_w = slide_w - 2 * margin
        area_h = slide_h - area_top - margin

        img_ratio = img_w_px / img_h_px
        area_ratio = area_w / area_h

        if img_ratio > area_ratio:
            draw_w = area_w
            draw_h = int(area_w / img_ratio)
        else:
            draw_h = area_h
            draw_w = int(area_h * img_ratio)

        left = margin + (area_w - draw_w) // 2
        top = area_top + (area_h - draw_h) // 2

        slide.shapes.add_picture(str(image_path), left, top, width=draw_w, height=draw_h)
        image_boxes[i] = (left, top, draw_w, draw_h)

        if notes:
            slide.notes_slide.notes_text_frame.text = notes

    # 第二輪：hotspots 與 nav 可能參照到任何一張投影片（含後面才建立的），
    # 所有投影片都存在後再統一加上去，避免 target 尚未建立。
    for i, entry in enumerate(entries):
        slide = slides[i]
        if slide is None:
            continue

        for hotspot in entry.get("hotspots", []):
            target_slide = _resolve_target(entries, slides, hotspot.get("target"))
            if target_slide is None:
                print(f"[svg_to_pptx] hotspot 找不到 target，略過：{hotspot}", file=sys.stderr)
                continue

            box = image_boxes[i]
            if box is None:
                continue
            left, top, draw_w, draw_h = box
            hx = left + Emu(int(hotspot.get("x", 0) * draw_w))
            hy = top + Emu(int(hotspot.get("y", 0) * draw_h))
            hw = Emu(int(hotspot.get("w", 0.1) * draw_w))
            hh = Emu(int(hotspot.get("h", 0.1) * draw_h))

            shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, hx, hy, hw, hh)
            shape.fill.background()  # 隱形熱區：無填色
            shape.line.fill.background()  # 無邊框
            shape.shadow.inherit = False
            if hotspot.get("label"):
                shape.name = hotspot["label"]
            shape.click_action.target_slide = target_slide

        if entry.get("nav"):
            built_indices = [k for k, s in enumerate(slides) if s is not None]
            pos = built_indices.index(i)
            first_slide = slides[built_indices[0]]
            prev_slide = slides[built_indices[pos - 1]] if pos > 0 else None
            next_slide = slides[built_indices[pos + 1]] if pos < len(built_indices) - 1 else None

            btn_size = Inches(0.4)
            btn_gap = Inches(0.1)
            btn_y = slide_h - margin - btn_size
            # (shape type, target slide) — target_slide 只接受實際 slide 物件（見
            # python-pptx ActionSetting.target_slide 的 setter），沒有公開 API 可直接
            # 寫「相對跳轉」（PP_ACTION.NEXT_SLIDE/PREVIOUS_SLIDE 沒有對應 setter），
            # 所以在這裡直接解成前一張/後一張的實際物件。
            btn_specs = [
                (MSO_SHAPE.ACTION_BUTTON_HOME, first_slide),
                (MSO_SHAPE.ACTION_BUTTON_BACK_OR_PREVIOUS, prev_slide),
                (MSO_SHAPE.ACTION_BUTTON_FORWARD_OR_NEXT, next_slide),
            ]
            for j, (shape_type, target) in enumerate(btn_specs):
                if target is None:
                    continue
                bx = slide_w - margin - (len(btn_specs) - j) * (btn_size + btn_gap)
                btn = slide.shapes.add_shape(shape_type, bx, btn_y, btn_size, btn_size)
                btn.click_action.target_slide = target

    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out_path))
    built = sum(1 for s in slides if s is not None)
    print(f"[svg_to_pptx] 已輸出：{out_path}（{built} 張投影片）")


def main() -> None:
    parser = argparse.ArgumentParser(description="把一組 PNG 圖表組成 PowerPoint")
    parser.add_argument("manifest", help="manifest.json 路徑")
    parser.add_argument("--out", required=True, help="輸出 .pptx 路徑")
    args = parser.parse_args()

    build_pptx(Path(args.manifest), Path(args.out))


if __name__ == "__main__":
    main()
