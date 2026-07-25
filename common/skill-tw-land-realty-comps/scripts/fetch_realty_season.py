#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_realty_season.py — 下載內政部「不動產成交案件實際資訊資料供應系統」（實價登錄）
季資料 zip，取出指定縣市代碼 x 交易類型代碼的 CSV，快取到本地。

資料來源: https://plvr.land.moi.gov.tw/DownloadSeason
每一季（season，格式為「民國年+S+季別」，如 114S4）下載一份全國 zip，
內含各縣市 x 各交易類型的 CSV（檔名如 h_lvr_land_a.csv = 桃園市(H) 買賣(A)）。

使用方式：
    python fetch_realty_season.py \
        --city-codes H \
        --asset-codes A \
        --year-from 105 --year-to 114 \
        --out-dir data/realty_comps/raw

縣市代碼常見對照（節錄）：A=台北市 B=台中市 C=基隆市 D=台南市 E=高雄市
F=新北市 G=宜蘭縣 H=桃園市 I=嘉義市 J=新竹縣 K=苗栗縣 M=南投縣
N=彰化縣 O=新竹市 P=雲林縣 Q=嘉義縣 T=屏東縣 U=花蓮縣 V=台東縣
W=金門縣 X=澎湖縣 Z=連江縣。完整清單請參考內政部實價登錄查詢網站。

交易類型代碼：A=買賣 B=租賃 C=預售屋。
"""
import argparse
import os
import subprocess
import sys
import zipfile

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_URL = "https://plvr.land.moi.gov.tw/DownloadSeason"


def roc_seasons(year_from, year_to, seasons):
    for year in range(year_from, year_to + 1):
        for season_no in seasons:
            yield f"{year}S{season_no}"


def download_season_zip(season, out_tmp_path, retries=3, timeout=120):
    cmd = [
        "curl", "-sL", "--fail", "--retry", str(retries), "--max-time", str(timeout),
        "-o", out_tmp_path,
        f"{BASE_URL}?season={season}&type=zip&fileName=lvr_landcsv.zip",
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0 and os.path.exists(out_tmp_path) and os.path.getsize(out_tmp_path) > 0


def extract_city_files(zip_path, city_codes, asset_codes, out_dir, season):
    saved = []
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        for city in city_codes:
            for asset in asset_codes:
                fname = f"{city.lower()}_lvr_land_{asset.lower()}.csv"
                if fname not in names:
                    continue
                dest_dir = os.path.join(out_dir, city.upper(), asset.upper())
                os.makedirs(dest_dir, exist_ok=True)
                dest_path = os.path.join(dest_dir, f"{season}.csv")
                tmp_path = dest_path + ".tmp"
                with zf.open(fname) as src, open(tmp_path, "wb") as dst:
                    dst.write(src.read())
                os.replace(tmp_path, dest_path)
                saved.append(dest_path)
    return saved


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--city-codes", required=True, help="縣市代碼，逗號分隔，如 H 或 H,F")
    ap.add_argument("--asset-codes", default="A", help="交易類型代碼，逗號分隔，A=買賣 B=租賃 C=預售屋，預設 A")
    ap.add_argument("--year-from", type=int, required=True, help="民國年（起）")
    ap.add_argument("--year-to", type=int, required=True, help="民國年（迄）")
    ap.add_argument("--seasons", default="1,2,3,4", help="每年季別，逗號分隔，預設 1,2,3,4")
    ap.add_argument("--out-dir", required=True, help="快取輸出根目錄")
    ap.add_argument("--force", action="store_true", help="即使已快取也重新下載覆寫")
    args = ap.parse_args()

    city_codes = [c.strip() for c in args.city_codes.split(",") if c.strip()]
    asset_codes = [c.strip() for c in args.asset_codes.split(",") if c.strip()]
    seasons_list = [int(s) for s in args.seasons.split(",") if s.strip()]

    os.makedirs(args.out_dir, exist_ok=True)
    tmp_zip = os.path.join(args.out_dir, "_download.tmp.zip")

    for season in roc_seasons(args.year_from, args.year_to, seasons_list):
        already = all(
            os.path.exists(os.path.join(args.out_dir, city.upper(), asset.upper(), f"{season}.csv"))
            for city in city_codes for asset in asset_codes
        )
        if already and not args.force:
            print(f"[skip] {season} 已快取")
            continue

        print(f"[fetch] {season} ...")
        ok = download_season_zip(season, tmp_zip)
        if not ok:
            print(f"  跳過（該季尚未公開或下載失敗）: {season}")
            if os.path.exists(tmp_zip):
                os.remove(tmp_zip)
            continue

        try:
            saved = extract_city_files(tmp_zip, city_codes, asset_codes, args.out_dir, season)
            for path in saved:
                print(f"  saved {path}")
            if not saved:
                print(f"  警告：{season} zip 內找不到指定縣市/交易類型的檔案")
        except zipfile.BadZipFile:
            print(f"  跳過（zip 檔損毀）: {season}")
        finally:
            if os.path.exists(tmp_zip):
                os.remove(tmp_zip)


if __name__ == "__main__":
    main()
