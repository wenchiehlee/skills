#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
easymap_snapshot.py — 內政部 easymap 地號官方地圖快照

呼叫內政部地政司 easymap（https://easymap.land.moi.gov.tw/P02）依 office/
sectNo/landNo 取得地號中心座標與官方圖層疊圖，套用 WMTS 電子地圖底圖後輸出
單張 PNG 快照。

此資料源與 TY_UPGIS（fetch_tyupgis_layers.py / build_city_signal.py）完全
不同：easymap 走 token + cookie 的表單驗證流程，且圖層資料為官方地籍疊圖，而
非案件位置點位查詢，因此獨立成一支腳本，不與 TY_UPGIS 流程共用同一 CLI。

使用方式：
    python scripts/easymap_snapshot.py \
        --office <地政事務所代碼> --sect <段小段代碼> --land <地號> \
        --out Images/easymap_<地號>.png
"""
import argparse
import base64
import io
import json
import math
import os
import re
import ssl
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

from PIL import Image, ImageDraw, ImageFont

BASE = "https://easymap.land.moi.gov.tw/P02"
TOKEN_URL = f"{BASE}/pages/setToken.jsp"
CENTER_URL = f"{BASE}/Map_json_getMapCenter"
LAYER_URL = f"{BASE}/Map_json_getMapImageLayers"
WMTS_URL_TMPL = "https://wmts.nlsc.gov.tw/wmts/EMAP/default/EPSG:3857/{z}/{row}/{col}"
SSL_CTX = ssl._create_unverified_context()


def latlon_to_global_px(lon: float, lat: float, zoom: int):
    scale = 256 * (2 ** zoom)
    x = (lon + 180.0) / 360.0 * scale
    lat_rad = math.radians(lat)
    y = (1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * scale
    return x, y


def fetch_json(opener, url, data_dict):
    body = urllib.parse.urlencode(data_dict).encode("utf-8")
    req = urllib.request.Request(url, data=body)
    with opener.open(req, timeout=30) as r:
        text = r.read().decode("utf-8", errors="ignore")
    return json.loads(text)


def get_token(opener):
    req = urllib.request.Request(TOKEN_URL)
    with opener.open(req, timeout=30) as r:
        html = r.read().decode("utf-8", errors="ignore")
    m = re.search(r'name="token" value="([^"]+)"', html)
    if not m:
        raise RuntimeError("Failed to get token")
    return m.group(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--office", required=True, help="地政事務所代碼")
    parser.add_argument("--sect", required=True, help="段小段代碼")
    parser.add_argument("--land", required=True, help="地號")
    parser.add_argument("--out", required=True, help="輸出 PNG 路徑")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument("--zoom", type=int, default=17)
    args = parser.parse_args()

    cj = CookieJar()
    https_handler = urllib.request.HTTPSHandler(context=SSL_CTX)
    opener = urllib.request.build_opener(https_handler, urllib.request.HTTPCookieProcessor(cj))

    token_center = get_token(opener)
    center = fetch_json(
        opener,
        CENTER_URL,
        {
            "office": args.office,
            "sectNo": args.sect,
            "landNo": args.land,
            "qryResult": "M2",
            "struts.token.name": "token",
            "token": token_center,
        },
    )
    cx_lon = float(center["X"])
    cy_lat = float(center["Y"])

    token_layer = get_token(opener)
    layers = fetch_json(
        opener,
        LAYER_URL,
        {
            "office": args.office,
            "sectNo": args.sect,
            "landNo": args.land,
            "struts.token.name": "token",
            "token": token_layer,
        },
    )

    center_px_x, center_px_y = latlon_to_global_px(cx_lon, cy_lat, args.zoom)
    tl_x = center_px_x - args.width / 2
    tl_y = center_px_y - args.height / 2

    min_tx = int(math.floor(tl_x / 256))
    max_tx = int(math.floor((tl_x + args.width - 1) / 256))
    min_ty = int(math.floor(tl_y / 256))
    max_ty = int(math.floor((tl_y + args.height - 1) / 256))

    n = 2 ** args.zoom
    canvas = Image.new("RGB", (args.width, args.height), (245, 245, 245))

    for ty in range(min_ty, max_ty + 1):
        if ty < 0 or ty >= n:
            continue
        for tx in range(min_tx, max_tx + 1):
            tx_mod = tx % n
            tile_url = WMTS_URL_TMPL.format(z=args.zoom, row=ty, col=tx_mod)
            try:
                req = urllib.request.Request(tile_url)
                with opener.open(req, timeout=30) as r:
                    data = r.read()
                tile = Image.open(io.BytesIO(data)).convert("RGB")
            except Exception:
                continue
            px = int(round(tx * 256 - tl_x))
            py = int(round(ty * 256 - tl_y))
            canvas.paste(tile, (px, py))

    overlay_canvas = canvas.convert("RGBA")

    for item in layers.get("IMG", []):
        ext = item.get("EXT", [])
        b64 = item.get("IMG", "")
        if len(ext) != 4 or not b64:
            continue

        min_lon, min_lat, max_lon, max_lat = map(float, ext)
        tl_overlay_x, tl_overlay_y = latlon_to_global_px(min_lon, max_lat, args.zoom)
        br_overlay_x, br_overlay_y = latlon_to_global_px(max_lon, min_lat, args.zoom)

        ow = max(1, int(round(br_overlay_x - tl_overlay_x)))
        oh = max(1, int(round(br_overlay_y - tl_overlay_y)))

        raw = base64.b64decode(b64)
        img = Image.open(io.BytesIO(raw)).convert("RGBA")
        img = img.resize((ow, oh), Image.Resampling.BILINEAR)

        r, g, b, a = img.split()
        a = a.point(lambda v: int(v * 0.30))
        img = Image.merge("RGBA", (r, g, b, a))

        px = int(round(tl_overlay_x - tl_x))
        py = int(round(tl_overlay_y - tl_y))
        overlay_canvas.alpha_composite(img, (px, py))

    draw = ImageDraw.Draw(overlay_canvas)
    mx = int(round(center_px_x - tl_x))
    my = int(round(center_px_y - tl_y))
    pin_color = (216, 52, 52, 255)
    draw.ellipse((mx - 8, my - 22, mx + 8, my - 6), fill=pin_color, outline=(255, 255, 255, 235), width=2)
    draw.polygon([(mx, my + 2), (mx - 6, my - 8), (mx + 6, my - 8)], fill=pin_color, outline=(255, 255, 255, 235))

    label = f"MOI Easymap snapshot | 地號 {args.land}"
    font = ImageFont.load_default()
    label_w = max(220, len(label) * 7 + 10)
    draw.rectangle((8, args.height - 26, 8 + label_w, args.height - 6), fill=(255, 255, 255, 180))
    draw.text((12, args.height - 21), label, fill=(40, 40, 40, 255), font=font)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    overlay_canvas.save(args.out, "PNG")
    print(f"saved: {args.out}")


if __name__ == "__main__":
    main()
