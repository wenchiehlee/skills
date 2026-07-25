#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_tyupgis_layers.py — 抓取桃園市 TY_UPGIS 圖層原始 JSON 快照

對每個 target（座標點）× 每個 layer id，查詢 TY_UPGIS MapServer 指定半徑內的
圖徵（features），快取為 <out-dir>/<target_id>_layer<layer_id>.json。

Targets 與 layers 皆由外部 JSON 設定檔提供，不寫死在腳本內，方便其他專案套用
同一套查詢邏輯分析不同地號/座標點。

targets.json 格式：
    [
      {"target_id": "example-A", "label": "範例地號 A", "lon": 121.5000, "lat": 25.0500},
      ...
    ]

layers.json 格式（僅需 id，name/color 供 build_city_signal.py 繪圖使用）：
    [
      {"id": 59, "name": "甲乙工申請案件位置", "color": [37, 99, 235]},
      ...
    ]

使用方式：
    python scripts/fetch_tyupgis_layers.py \
        --targets-file targets.json \
        --layers-file layers.json \
        --out-dir data/city_signal_2km/raw_json \
        --radius-m 2000

依賴：系統需安裝 curl（比照原始 bash 版本，沿用其 retry/resolve 語意）。
離線 DNS 解析（若 urbandatasrv.tycg.gov.tw 需指定 IP）：
    設定環境變數 TY_UPGIS_HOST_IP
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any

if platform.system() == "Windows":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

QUERY_URL_TMPL = (
    "https://urbandatasrv.tycg.gov.tw/server/rest/services/"
    "TY_UPGIS/TYMap_SDE/MapServer/{layer_id}/query"
)


def load_json_list(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array")
    return data


def build_query_url(layer_id: int, lon: float, lat: float, radius_m: int) -> str:
    params = {
        "f": "json",
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": str(radius_m),
        "units": "esriSRUnit_Meter",
        "geometry": f"{lon},{lat}",
    }
    return f"{QUERY_URL_TMPL.format(layer_id=layer_id)}?{urllib.parse.urlencode(params)}"


def fetch_to_file(url: str, out_path: Path, retries: int, retry_delay: int, timeout: int) -> None:
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    cmd = [
        "curl",
        "-sS",
        "--retry",
        str(retries),
        "--retry-delay",
        str(retry_delay),
        "--retry-all-errors",
        "--connect-timeout",
        "15",
        "--max-time",
        str(timeout),
    ]

    host_ip = os.getenv("TY_UPGIS_HOST_IP", "").strip()
    if host_ip:
        cmd.extend(["--resolve", f"urbandatasrv.tycg.gov.tw:443:{host_ip}"])

    cmd.extend(["-o", str(tmp_path), url])

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        if tmp_path.exists():
            tmp_path.unlink()
        raise RuntimeError(f"curl failed (exit {e.returncode})") from e

    tmp_path.replace(out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets-file", type=Path, required=True)
    parser.add_argument("--layers-file", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("data/city_signal_2km/raw_json"))
    parser.add_argument("--radius-m", type=int, default=2000)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--retry-delay", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument(
        "--target-id",
        help="只抓取指定 target_id（預設抓取 targets-file 內全部 targets）。",
    )
    args = parser.parse_args()

    targets = load_json_list(args.targets_file)
    layers = load_json_list(args.layers_file)

    if args.target_id:
        targets = [t for t in targets if t["target_id"] == args.target_id]
        if not targets:
            raise SystemExit(f"target_id not found in {args.targets_file}: {args.target_id}")

    args.out_dir.mkdir(parents=True, exist_ok=True)

    for target in targets:
        tid = target["target_id"]
        lon = float(target["lon"])
        lat = float(target["lat"])
        for layer in layers:
            layer_id = int(layer["id"])
            out_path = args.out_dir / f"{tid}_layer{layer_id}.json"
            url = build_query_url(layer_id, lon, lat, args.radius_m)

            try:
                fetch_to_file(url, out_path, args.retries, args.retry_delay, args.timeout)
            except RuntimeError as e:
                print(f"failed: {tid} layer {layer_id}: {e}", file=sys.stderr)
                raise SystemExit(1)

            try:
                payload = json.loads(out_path.read_text(encoding="utf-8", errors="ignore"))
                if payload.get("error"):
                    summary = f"ERROR: {payload['error'].get('message', '?')}"
                else:
                    summary = str(len(payload.get("features", [])))
            except Exception:
                summary = "unparsable response"

            print(f"{tid} layer {layer_id} -> {summary}")

    print(f"saved raw snapshots in: {args.out_dir}")


if __name__ == "__main__":
    main()
