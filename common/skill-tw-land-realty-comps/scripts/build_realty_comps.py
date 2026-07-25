#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_realty_comps.py — 彙整 fetch_realty_season.py 快取的實價登錄季資料 CSV，
依 targets.json 設定篩選出指定地號/門牌周邊的土地或房屋成交紀錄，
輸出比對用 CSV 與 Markdown 報告（近鄰範圍統計、同棟/同段明細、年度統計、加權估值）。

不區分土地或房屋兩種 skill：篩選條件（require_building/require_land）由
targets.json 逐一設定，同一支腳本同時支援土地地號分析頁與房屋分析頁。

使用方式：
    python build_realty_comps.py \
        --raw-dir data/realty_comps/raw \
        --targets-file data/realty_comps/targets.json \
        --target-id 782_11F \
        --out-dir data/realty_comps
"""
import argparse
import csv
import glob
import json
import os
import re
import statistics
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SQM_PER_PING = 3.305785
CN_DIGIT = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


def cn_to_int(token):
    token = token.strip()
    if not token:
        return None
    if token == "十":
        return 10
    if "十" in token:
        left, _, right = token.partition("十")
        tens = CN_DIGIT.get(left, 1) if left else 1
        ones = CN_DIGIT.get(right, 0) if right else 0
        return tens * 10 + ones
    return CN_DIGIT.get(token)


def parse_floor_field(raw):
    """回傳該筆交易的最低移轉樓層（int）；解析不出來則回傳 None。"""
    if not raw:
        return None
    raw = raw.strip()
    if not raw or raw in ("全", "見其他登記事項"):
        return None
    raw = raw.replace("地下", "")
    parts = re.split("[，,、]", raw)
    floors = []
    for part in parts:
        part = part.replace("層", "").replace("樓", "").strip()
        value = cn_to_int(part)
        if value is not None:
            floors.append(value)
    return min(floors) if floors else None


def extract_house_no(address):
    """從門牌地址擷取「號」前的門牌號數字（取最後一個符合的片段）。"""
    if not address:
        return None
    normalized = address.translate(FULLWIDTH_DIGITS)
    matches = re.findall(r"(\d+)號", normalized)
    return int(matches[-1]) if matches else None


def roc_date_to_iso(raw):
    """民國年月日（6~7 碼數字字串）轉 ISO 日期字串，解析失敗回傳 None。"""
    if not raw or not raw.isdigit():
        return None
    if len(raw) == 7:
        roc_year, month, day = int(raw[:3]), int(raw[3:5]), int(raw[5:7])
    elif len(raw) == 6:
        roc_year, month, day = int(raw[:2]), int(raw[2:4]), int(raw[4:6])
    else:
        return None
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    year = roc_year + 1911
    return f"{year:04d}-{month:02d}-{day:02d}"


def load_rows(raw_dir, city_code, asset_code):
    pattern = os.path.join(raw_dir, city_code.upper(), asset_code.upper(), "*.csv")
    rows = []
    for path in sorted(glob.glob(pattern)):
        season = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                tx_date_raw = (row.get("交易年月日") or "").strip()
                if not tx_date_raw.isdigit():
                    continue  # 略過英文欄名說明列
                row["_season"] = season
                rows.append(row)
    return rows


def build_record(row):
    address = row.get("土地位置建物門牌", "")
    tx_date_iso = roc_date_to_iso((row.get("交易年月日") or "").strip())
    if tx_date_iso is None:
        return None

    try:
        total_price = float(row.get("總價元") or 0)
    except ValueError:
        total_price = 0.0
    try:
        unit_price_sqm = float(row.get("單價元平方公尺") or 0)
    except ValueError:
        unit_price_sqm = 0.0
    try:
        building_sqm = float(row.get("建物移轉總面積平方公尺") or 0)
    except ValueError:
        building_sqm = 0.0

    return {
        "district": row.get("鄉鎮市區", ""),
        "asset_kind": row.get("交易標的", ""),
        "address": address,
        "house_no": extract_house_no(address),
        "tx_date": tx_date_iso,
        "tx_year": int(tx_date_iso[:4]),
        "tx_quarter": f"{tx_date_iso[:4]}Q{(int(tx_date_iso[5:7]) - 1) // 3 + 1}",
        "floor_min": parse_floor_field(row.get("移轉層次", "")),
        "floor_raw": row.get("移轉層次", ""),
        "building_type": row.get("建物型態", ""),
        "total_price_wan": round(total_price / 10000, 2),
        "unit_price_wan_ping": round(unit_price_sqm * SQM_PER_PING / 10000, 2) if unit_price_sqm else 0.0,
        "building_ping": round(building_sqm / SQM_PER_PING, 2) if building_sqm else 0.0,
        "has_parking": "車位" in (row.get("交易標的") or ""),
        "note": row.get("備註", ""),
        "serial_no": row.get("編號", ""),
        "season": row.get("_season", ""),
    }


def filter_target_pool(records, target):
    district = target.get("district")
    road_keyword = target.get("road_keyword")
    require_building = target.get("require_building", True)
    require_land = target.get("require_land", False)
    date_from = target.get("date_from")
    date_to = target.get("date_to")

    out = []
    seen_serial = set()
    for rec in records:
        if district and rec["district"] != district:
            continue
        if road_keyword and road_keyword not in rec["address"]:
            continue
        if require_building and "建物" not in rec["asset_kind"]:
            continue
        if require_land and "土地" not in rec["asset_kind"]:
            continue
        if date_from and rec["tx_date"] < date_from:
            continue
        if date_to and rec["tx_date"] > date_to:
            continue
        key = rec["serial_no"] or (rec["address"], rec["tx_date"], rec["total_price_wan"])
        if key in seen_serial:
            continue
        seen_serial.add(key)
        out.append(rec)
    return out


def percentile(values, pct):
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * (pct / 100)
    f, c = int(k), min(int(k) + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] + (values[c] - values[f]) * (k - f)


def scope_stats(records, house_no, house_no_diff_max):
    if house_no_diff_max is not None:
        records = [r for r in records if r["house_no"] is not None and abs(r["house_no"] - house_no) <= house_no_diff_max]
    unit_prices = [r["unit_price_wan_ping"] for r in records if r["unit_price_wan_ping"]]
    total_prices = [r["total_price_wan"] for r in records if r["total_price_wan"]]
    return {
        "count": len(records),
        "unit_p20": percentile(unit_prices, 20),
        "unit_median": percentile(unit_prices, 50),
        "unit_p80": percentile(unit_prices, 80),
        "total_median": percentile(total_prices, 50),
    }


def yearly_stats(records, house_no, house_no_diff_max):
    if house_no_diff_max is not None:
        records = [r for r in records if r["house_no"] is not None and abs(r["house_no"] - house_no) <= house_no_diff_max]
    by_year = {}
    for r in records:
        by_year.setdefault(r["tx_year"], []).append(r)
    out = []
    for year in sorted(by_year):
        group = by_year[year]
        unit_prices = [r["unit_price_wan_ping"] for r in group if r["unit_price_wan_ping"]]
        total_prices = [r["total_price_wan"] for r in group if r["total_price_wan"]]
        out.append({
            "year": year,
            "count": len(group),
            "unit_median": percentile(unit_prices, 50),
            "total_median": percentile(total_prices, 50),
        })
    return out


def building_group_records(records, house_nos):
    return [r for r in records if r["house_no"] in set(house_nos)]


def load_price_index(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["index"]


def deflate_to_quarter(unit_price, tx_quarter, target_quarter, price_index):
    """用真實市場指數把 tx_quarter 的單價換算成 target_quarter 等值價格。

    找不到指數值的季度（例如比指數資料還早）就不換算，直接回傳原始單價，
    並回報 True/False 是否成功換算，讓呼叫端知道這筆是否有經過市場基準校正。
    """
    base = price_index.get(tx_quarter)
    target = price_index.get(target_quarter)
    if base is None or target is None or base == 0:
        return unit_price, False
    return round(unit_price * target / base, 2), True


def weighted_valuation(records, valuation_cfg):
    """以「樓層 x 坪數」距離加權估算單價與總價，時間效應改用真實市場指數換算
    （而非武斷的時間衰減）。

    做法：
    1. 若 valuation_cfg 提供 price_index_file（見 load_price_index），先把每筆
       歷史成交的單價，依真實市場指數換算成「price_index_target_quarter」
       （預設用指數資料裡最新一季）的等值價格——例如 2021 年成交的單價，換算
       成「如果現在賣，市場水準大概是多少」，而不是單純假設越新的成交權重越高。
       這避免了「單一個案新成交」被誤判成「市場普遍上漲」（見案例：某筆最新
       成交單價遠高於當季區域中位數，換算後才看得出是個案溢價、不是市場水準）。
    2. 換算後的價格，再用「樓層 x 坪數」距離連續衰減加權（不做任何硬性篩選）：
           w_floor = floor_decay ** abs(floor - target_floor)
           w_size  = size_decay ** (abs(ping - size_ping) / size_halflife_ping)
           weight  = w_floor * w_size
    3. 若沒有提供 price_index_file，退回舊行為：改用時間衰減
       （w_time = 0.5 ** (years_ago / time_halflife_years)）近似市場時間效應，
       準確度不如真實指數，但至少比不做任何時間校正更合理。

    輸出同時給「全母體距離加權平均」（含所有可比交易，越不相似權重越低，較不
    受單一樣本左右）與「Top-K 最相似樣本加權平均」（只看距離最近的少數樣本，
    對單一極端成交更敏感），兩者互為交叉檢查，不強制單一結論。
    """
    pool = records
    date_from = valuation_cfg.get("date_from")
    if date_from:
        pool = [r for r in pool if r["tx_date"] >= date_from]
    if valuation_cfg.get("require_parking"):
        pool = [r for r in pool if r["has_parking"]]
    pool = [r for r in pool if r["floor_min"] is not None and r["unit_price_wan_ping"] and r["building_ping"]]
    if not pool:
        return None, []

    floor_min_cfg = valuation_cfg.get("floor_min")
    floor_max_cfg = valuation_cfg.get("floor_max")
    if valuation_cfg.get("target_floor") is not None:
        target_floor = valuation_cfg["target_floor"]
    elif floor_min_cfg is not None and floor_max_cfg is not None:
        target_floor = (floor_min_cfg + floor_max_cfg) / 2
    elif floor_min_cfg is not None:
        target_floor = floor_min_cfg
    else:
        target_floor = None

    size_ping = valuation_cfg.get("size_ping")
    floor_decay = valuation_cfg.get("floor_decay", 0.85)
    size_decay = valuation_cfg.get("size_decay", 0.85)
    size_halflife_ping = valuation_cfg.get("size_halflife_ping", 5)
    top_k = valuation_cfg.get("top_k", 4)

    price_index = None
    price_index_target_quarter = None
    price_index_file = valuation_cfg.get("price_index_file")
    if price_index_file:
        price_index = load_price_index(price_index_file)
        price_index_target_quarter = valuation_cfg.get("price_index_target_quarter") or max(price_index)

    time_halflife = valuation_cfg.get("time_halflife_years", 3)
    ref_year = valuation_cfg.get("as_of_year") or max(r["tx_year"] for r in pool)

    weighted = []
    for r in pool:
        market_price = r["unit_price_wan_ping"]
        deflated = False
        if price_index is not None:
            market_price, deflated = deflate_to_quarter(
                r["unit_price_wan_ping"], r["tx_quarter"], price_index_target_quarter, price_index
            )
            w = 1.0
        else:
            years_ago = ref_year - r["tx_year"]
            w = 0.5 ** (years_ago / time_halflife)
        if target_floor is not None:
            w *= floor_decay ** abs(r["floor_min"] - target_floor)
        if size_ping:
            w *= size_decay ** (abs(r["building_ping"] - size_ping) / size_halflife_ping)
        weighted.append((r, w, market_price, deflated))
    weighted.sort(key=lambda x: -x[1])

    total_w = sum(w for _, w, _, _ in weighted)
    pool_weighted_avg = sum(mp * w for _, w, mp, _ in weighted) / total_w

    top_comps = weighted[:top_k]
    top_w = sum(w for _, w, _, _ in top_comps)
    top_k_avg = sum(mp * w for _, w, mp, _ in top_comps) / top_w if top_w else None

    market_prices = [mp for _, _, mp, _ in weighted]
    result = {
        "sample_count": len(weighted),
        "top_k": len(top_comps),
        "price_index_used": price_index is not None,
        "price_index_target_quarter": price_index_target_quarter,
        "unit_p25": percentile(market_prices, 25),
        "unit_p50": percentile(market_prices, 50),
        "unit_pool_weighted_avg": round(pool_weighted_avg, 2),
        "unit_top_k_avg": round(top_k_avg, 2) if top_k_avg is not None else None,
        "unit_p75": percentile(market_prices, 75),
    }
    if size_ping:
        for key in ("unit_p25", "unit_p50", "unit_pool_weighted_avg", "unit_top_k_avg", "unit_p75"):
            if result.get(key) is not None:
                result[key.replace("unit_", "total_")] = round(result[key] * size_ping, 0)
    top_comps_out = [
        {**r, "market_adjusted_unit_price_wan_ping": mp, "price_index_deflated": deflated}
        for r, _, mp, deflated in top_comps
    ]
    return result, top_comps_out


def render_markdown(target, scopes_out, group_records, yearly_out, valuation_result, valuation_pool):
    lines = []
    lines.append(f"## 近鄰成交統計（{target['target_id']}）\n")
    lines.append("| 範圍 | 筆數 | 單價 P20 (萬/坪) | 單價中位數 (萬/坪) | 單價 P80 (萬/坪) | 總價中位數 (萬) |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for label, stats in scopes_out:
        lines.append(
            f"| {label} | {stats['count']} | {stats['unit_p20'] or '-'} | {stats['unit_median'] or '-'} | "
            f"{stats['unit_p80'] or '-'} | {stats['total_median'] or '-'} |"
        )

    if group_records:
        lines.append(f"\n## 同棟/同段門牌群組成交明細（{target['target_id']}）\n")
        lines.append("| 交易日期 | 門牌號 | 交易標的 | 建物型態 | 移轉層次 | 總價 (萬) | 單價 (萬/坪) | 建物面積 (坪) | 來源季別 |")
        lines.append("|---|---:|---|---|---|---:|---:|---:|---|")
        for r in sorted(group_records, key=lambda x: x["tx_date"], reverse=True):
            lines.append(
                f"| {r['tx_date']} | {r['house_no']} | {r['asset_kind']} | {r['building_type']} | {r['floor_raw']} | "
                f"{r['total_price_wan']} | {r['unit_price_wan_ping']} | {r['building_ping']} | {r['season']} |"
            )

    if yearly_out:
        lines.append(f"\n## 年度活動（{target['target_id']}）\n")
        lines.append("| 年度 | 成交筆數 | 單價中位數 (萬/坪) | 總價中位數 (萬) |")
        lines.append("|---:|---:|---:|---:|")
        for row in yearly_out:
            lines.append(f"| {row['year']} | {row['count']} | {row['unit_median'] or '-'} | {row['total_median'] or '-'} |")

    if valuation_result:
        lines.append(f"\n## 加權估值（{target['target_id']}）\n")
        lines.append(f"- 樣本數: `{valuation_result['sample_count']}`（Top-K 相似樣本數: `{valuation_result['top_k']}`）")
        if valuation_result["price_index_used"]:
            lines.append(
                f"- 時間效應處理: 用真實市場指數把每筆歷史成交換算成 `{valuation_result['price_index_target_quarter']}` "
                "等值價格（而非假設越新權重越高），避免單一個案新成交被誤判成市場整體漲幅。"
            )
        lines.append(
            "- 加權方式: 樓層 x 坪數距離聯合加權（每差 1 層權重 x0.85、每差 5 坪權重 x0.85），非單一因子硬篩選；"
            "「全母體加權平均」涵蓋所有可比交易、越不相似權重越低，「Top-K 加權平均」只看距離最相似的少數樣本，"
            "兩者互為交叉檢查。"
        )
        lines.append("\n| 指標 | 單價 (萬/坪) | 總價估值 (萬) |")
        lines.append("|---|---:|---:|")
        for key, label in (
            ("unit_p25", "P25（原始未加權）"),
            ("unit_p50", "P50（原始未加權）"),
            ("unit_pool_weighted_avg", "全母體距離加權平均"),
            ("unit_top_k_avg", "Top-K 最相似樣本加權平均"),
            ("unit_p75", "P75（原始未加權）"),
        ):
            if valuation_result.get(key) is None:
                continue
            total_key = key.replace("unit_", "total_")
            total_val = valuation_result.get(total_key, "-")
            lines.append(f"| {label} | {valuation_result[key]} | {total_val} |")

    if valuation_pool:
        lines.append(f"\n### Top-K 最相似樣本明細（{target['target_id']}）\n")
        if valuation_pool[0].get("price_index_deflated") is not None:
            lines.append("| 交易日期 | 門牌號 | 移轉層次 | 建物面積 (坪) | 原始單價 (萬/坪) | 市場基準換算單價 (萬/坪) | 總價 (萬) |")
            lines.append("|---|---:|---|---:|---:|---:|---:|")
            for r in valuation_pool:
                lines.append(
                    f"| {r['tx_date']} | {r['house_no']} | {r['floor_raw']} | {r['building_ping']} | "
                    f"{r['unit_price_wan_ping']} | {r['market_adjusted_unit_price_wan_ping']} | {r['total_price_wan']} |"
                )
        else:
            lines.append("| 交易日期 | 門牌號 | 移轉層次 | 建物面積 (坪) | 單價 (萬/坪) | 總價 (萬) |")
            lines.append("|---|---:|---|---:|---:|---:|")
            for r in valuation_pool:
                lines.append(
                    f"| {r['tx_date']} | {r['house_no']} | {r['floor_raw']} | {r['building_ping']} | "
                    f"{r['unit_price_wan_ping']} | {r['total_price_wan']} |"
                )

    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw-dir", required=True, help="fetch_realty_season.py 的輸出快取根目錄")
    ap.add_argument("--targets-file", required=True, help="targets.json 路徑")
    ap.add_argument("--target-id", required=True, help="要處理的 target_id")
    ap.add_argument("--out-dir", required=True, help="輸出 CSV / Markdown 報告的目錄")
    args = ap.parse_args()

    with open(args.targets_file, encoding="utf-8") as f:
        targets = json.load(f)
    target = next((t for t in targets if t["target_id"] == args.target_id), None)
    if target is None:
        print(f"找不到 target_id={args.target_id}", file=sys.stderr)
        sys.exit(1)

    raw_rows = load_rows(args.raw_dir, target["city_code"], target.get("asset_code", "A"))
    if not raw_rows:
        print(f"警告：{args.raw_dir}/{target['city_code']}/{target.get('asset_code', 'A')} 找不到任何快取 CSV，"
              f"請先執行 fetch_realty_season.py", file=sys.stderr)

    records = [build_record(r) for r in raw_rows]
    records = [r for r in records if r is not None]
    pool = filter_target_pool(records, target)

    house_no = target.get("house_no")
    scopes_out = []
    for scope in target.get("scopes", []):
        stats = scope_stats(pool, house_no, scope.get("house_no_diff_max"))
        scopes_out.append((scope["label"], stats))

    group_house_nos = target.get("building_group_house_nos", [])
    group_records = building_group_records(pool, group_house_nos) if group_house_nos else []

    yearly_scope = target.get("yearly_scope_house_no_diff_max")
    yearly_out = yearly_stats(pool, house_no, yearly_scope) if yearly_scope is not None else []

    valuation_result, valuation_pool = (None, [])
    if "valuation" in target and group_records:
        valuation_result, valuation_pool = weighted_valuation(group_records, target["valuation"])

    os.makedirs(args.out_dir, exist_ok=True)

    matched_csv_path = os.path.join(args.out_dir, f"{target['target_id']}_matched.csv")
    with open(matched_csv_path, "w", newline="", encoding="utf-8-sig") as f:
        fieldnames = ["tx_date", "house_no", "district", "asset_kind", "building_type", "floor_raw",
                      "total_price_wan", "unit_price_wan_ping", "building_ping", "has_parking", "address", "season"]
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in sorted(pool, key=lambda x: x["tx_date"], reverse=True):
            writer.writerow(r)
    print(f"已輸出比對明細: {matched_csv_path}（{len(pool)} 筆）")

    report_md_path = os.path.join(args.out_dir, f"{target['target_id']}_report.md")
    report_md = render_markdown(target, scopes_out, group_records, yearly_out, valuation_result, valuation_pool)
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(report_md)
    print(f"已輸出 Markdown 報告: {report_md_path}")


if __name__ == "__main__":
    main()
