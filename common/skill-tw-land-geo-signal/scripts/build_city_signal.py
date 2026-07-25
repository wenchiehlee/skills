#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_city_signal.py — 從 TY_UPGIS 原始快照彙整城市信號 CSV 與疊圖 PNG

讀取 fetch_tyupgis_layers.py 產生的 <target_id>_layer<layer_id>.json 快取，
彙整成三張 CSV（每 target/layer 的圖徵計數、逐點座標、地圖產出紀錄），並為
每個 target 產生一張以衛星/底圖 + 2km 範圍圈 + 各圖層圖徵點位疊加的合併地圖。

targets.json / layers.json 格式與 fetch_tyupgis_layers.py 相同。

可選的 stations.json（參考站點，如捷運站、公車站，僅供地圖標籤參考距離）：
    [
      {"id": "S1", "label": "S1（範例參考站點）", "lon": 121.4950, "lat": 25.0480},
      ...
    ]

使用方式：
    python scripts/build_city_signal.py \
        --targets-file targets.json \
        --layers-file layers.json \
        --raw-dir data/city_signal_2km/raw_json \
        --out-root data/city_signal_2km \
        --images-dir Images

雙 target 疊合比對（例如比較兩筆地號周邊同一圖層的案件重疊/獨有情形）不需要
專用腳本：對 city_signal_2km_feature_points.csv 依 target_id、layer_id、
feature_key 做 groupby/set 運算即可，範例見 SKILL.md。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from PIL import Image, ImageDraw, ImageFont

EXPORT_URL = (
    "https://urbandatasrv.tycg.gov.tw/server/rest/services/"
    "TY_UPGIS/TYMap_SDE/MapServer/export"
)


def load_json_list(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array")
    return data


def geometry_center(geom: dict[str, Any]) -> tuple[float | None, float | None]:
    if geom.get("x") is not None and geom.get("y") is not None:
        return float(geom["x"]), float(geom["y"])

    rings = geom.get("rings")
    if isinstance(rings, list) and rings:
        pts: list[tuple[float, float]] = []
        for ring in rings:
            for p in ring:
                if isinstance(p, list) and len(p) >= 2:
                    pts.append((float(p[0]), float(p[1])))
        if pts:
            return (
                sum(p[0] for p in pts) / len(pts),
                sum(p[1] for p in pts) / len(pts),
            )

    paths = geom.get("paths")
    if isinstance(paths, list) and paths:
        pts = []
        for path in paths:
            for p in path:
                if isinstance(p, list) and len(p) >= 2:
                    pts.append((float(p[0]), float(p[1])))
        if pts:
            return (
                sum(p[0] for p in pts) / len(pts),
                sum(p[1] for p in pts) / len(pts),
            )

    return None, None


def feature_key(attrs: dict[str, Any], index: int) -> str:
    for k in ("CaseID", "CID", "ID", "OBJECTID", "OBJECTID_1"):
        v = attrs.get(k)
        if v is not None:
            return str(v)
    return f"idx_{index}"


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def build_bbox(
    target: dict[str, Any],
    radius_m: int,
    points: list[tuple[float, float]],
    mode: str,
) -> tuple[float, float, float, float]:
    lat_radius_deg = radius_m / 111320.0
    lon_radius_deg = radius_m / (111320.0 * max(0.1, math.cos(math.radians(target["lat"]))))

    min_lon = target["lon"] - lon_radius_deg
    max_lon = target["lon"] + lon_radius_deg
    min_lat = target["lat"] - lat_radius_deg
    max_lat = target["lat"] + lat_radius_deg

    if mode == "auto" and points:
        min_lon = min(min_lon, min(p[0] for p in points))
        max_lon = max(max_lon, max(p[0] for p in points))
        min_lat = min(min_lat, min(p[1] for p in points))
        max_lat = max(max_lat, max(p[1] for p in points))

    if mode == "circle":
        pad_lon = max((max_lon - min_lon) * 0.05, 0.001)
        pad_lat = max((max_lat - min_lat) * 0.05, 0.001)
    else:
        pad_lon = max((max_lon - min_lon) * 0.08, 0.002)
        pad_lat = max((max_lat - min_lat) * 0.08, 0.002)
    min_lon -= pad_lon
    max_lon += pad_lon
    min_lat -= pad_lat
    max_lat += pad_lat

    return min_lon, min_lat, max_lon, max_lat


def fetch_background_image(
    bbox: tuple[float, float, float, float],
    size: tuple[int, int],
    cache_path: Path,
    refresh: bool,
) -> Image.Image:
    if cache_path.exists() and not refresh:
        return Image.open(cache_path).convert("RGB")

    width, height = size
    min_lon, min_lat, max_lon, max_lat = bbox
    params = {
        "bbox": f"{min_lon},{min_lat},{max_lon},{max_lat}",
        "bboxSR": "4326",
        "imageSR": "4326",
        "size": f"{width},{height}",
        "format": "png32",
        "transparent": "false",
        "f": "image",
    }
    url = f"{EXPORT_URL}?{urlencode(params)}"

    tmp_path = cache_path.with_suffix(".tmp.png")
    cmd = [
        "curl",
        "-sS",
        "--retry",
        "4",
        "--retry-delay",
        "1",
        "--retry-all-errors",
        "--connect-timeout",
        "15",
        "--max-time",
        "90",
    ]

    host_ip = os.getenv("TY_UPGIS_HOST_IP", "").strip()
    if host_ip:
        cmd.extend(["--resolve", f"urbandatasrv.tycg.gov.tw:443:{host_ip}"])

    cmd.extend(["-o", str(tmp_path), url])

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.check_call(cmd)
        tmp_path.replace(cache_path)
    except subprocess.CalledProcessError:
        if tmp_path.exists():
            tmp_path.unlink()
        if cache_path.exists():
            return Image.open(cache_path).convert("RGB")
        return Image.new("RGB", size, (244, 246, 248))

    return Image.open(cache_path).convert("RGB")


def draw_combined_map(
    out_png: Path,
    target: dict[str, Any],
    radius_m: int,
    layers: list[dict[str, Any]],
    layer_data: dict[int, dict[str, Any]],
    stations: list[dict[str, Any]],
    bbox: tuple[float, float, float, float],
    background_cache_path: Path,
    refresh_background: bool,
) -> None:
    width, height = 1200, 1200
    margin = 72

    bg = fetch_background_image(bbox, (width, height), background_cache_path, refresh_background)
    im = bg.copy()
    draw = ImageDraw.Draw(im, "RGBA")

    min_lon, min_lat, max_lon, max_lat = bbox
    draw_w = width - margin * 2
    draw_h = height - margin * 2

    def to_px(lon: float, lat: float) -> tuple[float, float]:
        x = margin + (lon - min_lon) / (max_lon - min_lon) * draw_w
        y = height - margin - (lat - min_lat) / (max_lat - min_lat) * draw_h
        return x, y

    lat_radius_deg = radius_m / 111320.0
    lon_radius_deg = radius_m / (111320.0 * max(0.1, math.cos(math.radians(target["lat"]))))

    cx, cy = to_px(target["lon"], target["lat"])
    rx = abs(to_px(target["lon"] + lon_radius_deg, target["lat"])[0] - cx)
    ry = abs(to_px(target["lon"], target["lat"] + lat_radius_deg)[1] - cy)

    draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), outline=(220, 38, 38, 230), width=3)
    red_r = 28
    draw.ellipse(
        (cx - red_r, cy - red_r, cx + red_r, cy + red_r),
        fill=(220, 38, 38, 255),
        outline=(255, 255, 255, 255),
        width=8,
    )

    for layer in layers:
        layer_id = int(layer["id"])
        data = layer_data[layer_id]
        if data["status"] != "ok":
            continue
        color = tuple(layer.get("color", (37, 99, 235)))
        for lon, lat in data["points"]:
            px, py = to_px(lon, lat)
            r = 9 if layer_id in (50, 54) else 12
            draw.ellipse(
                (px - r, py - r, px + r, py + r),
                fill=(*color, 180),
                outline=(20, 20, 20, 220),
                width=3,
            )

    if stations:
        label_font = load_font(20)
        for st in stations:
            px, py = to_px(float(st["lon"]), float(st["lat"]))
            color = (25, 25, 25, 255)
            draw.ellipse((px - 8, py - 8, px + 8, py + 8), fill=color, outline=(255, 255, 255, 255), width=2)
            tx, ty = px + 12, py - 24
            label = st.get("label", st.get("id", ""))
            box = draw.textbbox((tx, ty), label, font=label_font)
            draw.rectangle((box[0] - 4, box[1] - 2, box[2] + 4, box[3] + 2), fill=(255, 255, 255, 220))
            draw.text((tx, ty), label, fill=color, font=label_font, stroke_width=1, stroke_fill=(255, 255, 255, 255))

    out_png.parent.mkdir(parents=True, exist_ok=True)
    im.save(out_png)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets-file", type=Path, required=True)
    parser.add_argument("--layers-file", type=Path, required=True)
    parser.add_argument("--stations-file", type=Path, help="可選：地圖上疊加參考站點標籤")
    parser.add_argument("--radius-m", type=int, default=2000)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/city_signal_2km/raw_json"))
    parser.add_argument("--out-root", type=Path, default=Path("data/city_signal_2km"))
    parser.add_argument("--images-dir", type=Path, default=Path("Images"))
    parser.add_argument("--refresh-background", action="store_true")
    parser.add_argument("--target-id", help="只重繪單一 target 的地圖（搭配 --render-only 時 CSV 不變）。")
    parser.add_argument(
        "--bbox-mode",
        choices=["auto", "circle"],
        default="auto",
        help="auto：涵蓋所有圖層圖徵範圍；circle：僅聚焦在 2km 紅圈範圍。",
    )
    parser.add_argument("--render-only", action="store_true", help="只重新產生地圖 PNG，不重寫 CSV。")
    parser.add_argument(
        "--snapshot-time",
        default=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
    )
    args = parser.parse_args()

    targets = load_json_list(args.targets_file)
    layers = load_json_list(args.layers_file)
    stations = load_json_list(args.stations_file) if args.stations_file else []

    background_dir = args.out_root / "background_cache"
    background_dir.mkdir(parents=True, exist_ok=True)

    counts_rows: list[dict[str, Any]] = []
    points_rows: list[dict[str, Any]] = []
    maps_rows: list[dict[str, Any]] = []

    selected_targets = [t for t in targets if (not args.target_id or t["target_id"] == args.target_id)]

    for t in selected_targets:
        per_layer: dict[int, dict[str, Any]] = {}
        all_points: list[tuple[float, float]] = []

        for layer in layers:
            layer_id = int(layer["id"])
            raw_path = args.raw_dir / f"{t['target_id']}_layer{layer_id}.json"
            if not raw_path.exists():
                raise FileNotFoundError(
                    f"Missing raw snapshot: {raw_path}. "
                    "Run scripts/fetch_tyupgis_layers.py first."
                )

            payload = json.loads(raw_path.read_text(encoding="utf-8"))
            err = payload.get("error")
            if err:
                status = "error"
                count = 0
                features: list[dict[str, Any]] = []
                error_message = err.get("message", "unknown error")
            else:
                status = "ok"
                features = payload.get("features", [])
                count = len(features)
                error_message = ""

            counts_rows.append(
                {
                    "snapshot_time": args.snapshot_time,
                    "radius_m": args.radius_m,
                    "target_id": t["target_id"],
                    "target_label": t.get("label", t["target_id"]),
                    "target_lon": f"{t['lon']:.6f}",
                    "target_lat": f"{t['lat']:.6f}",
                    "layer_id": layer_id,
                    "layer_name": layer.get("name", ""),
                    "status": status,
                    "count": count,
                    "error_message": error_message,
                }
            )

            layer_points: list[tuple[float, float]] = []
            for idx, feat in enumerate(features, start=1):
                attrs = feat.get("attributes") or {}
                geom = feat.get("geometry") or {}
                lon, lat = geometry_center(geom)
                if lon is None or lat is None:
                    continue
                layer_points.append((lon, lat))
                points_rows.append(
                    {
                        "snapshot_time": args.snapshot_time,
                        "radius_m": args.radius_m,
                        "target_id": t["target_id"],
                        "layer_id": layer_id,
                        "feature_index": idx,
                        "feature_key": feature_key(attrs, idx),
                        "lon": f"{lon:.8f}",
                        "lat": f"{lat:.8f}",
                    }
                )

            per_layer[layer_id] = {
                "status": status,
                "count": count,
                "error_message": error_message,
                "points": layer_points,
            }
            all_points.extend(layer_points)

        bbox = build_bbox(t, args.radius_m, all_points, args.bbox_mode)

        png_name = f"city_signal_2km_{t['target_id']}_layers.png"
        png_path = args.images_dir / png_name
        bg_cache = background_dir / f"{t['target_id']}_2km_bg_{args.bbox_mode}.png"

        draw_combined_map(
            out_png=png_path,
            target=t,
            radius_m=args.radius_m,
            layers=layers,
            layer_data=per_layer,
            stations=stations,
            bbox=bbox,
            background_cache_path=bg_cache,
            refresh_background=args.refresh_background,
        )

        maps_rows.append(
            {
                "snapshot_time": args.snapshot_time,
                "radius_m": args.radius_m,
                "target_id": t["target_id"],
                "image_path": str(png_path),
                "bbox_min_lon": f"{bbox[0]:.6f}",
                "bbox_min_lat": f"{bbox[1]:.6f}",
                "bbox_max_lon": f"{bbox[2]:.6f}",
                "bbox_max_lat": f"{bbox[3]:.6f}",
            }
        )

    if args.render_only:
        print(f"Rendered map target(s): {', '.join(t['target_id'] for t in selected_targets)}")
        return

    counts_csv = args.out_root / "city_signal_2km_counts.csv"
    points_csv = args.out_root / "city_signal_2km_feature_points.csv"
    maps_csv = args.out_root / "city_signal_2km_maps.csv"

    counts_csv.parent.mkdir(parents=True, exist_ok=True)
    with counts_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(counts_rows[0].keys()))
        writer.writeheader()
        writer.writerows(counts_rows)

    with points_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "snapshot_time",
                "radius_m",
                "target_id",
                "layer_id",
                "feature_index",
                "feature_key",
                "lon",
                "lat",
            ],
        )
        writer.writeheader()
        writer.writerows(points_rows)

    with maps_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(maps_rows[0].keys()))
        writer.writeheader()
        writer.writerows(maps_rows)

    print(f"Wrote counts CSV: {counts_csv}")
    print(f"Wrote points CSV: {points_csv}")
    print(f"Wrote maps CSV: {maps_csv}")
    print(f"Wrote raw JSON directory: {args.raw_dir}")
    print(f"Wrote background cache: {background_dir}")


if __name__ == "__main__":
    main()
