#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_price_index.py — 從政大商學院信義不動產研究發展中心的實登統計網站
（https://restat.ncscre.nccu.edu.tw/）抓取指定縣市/行政區的單價（萬/坪）
時間序列指數，供 build_realty_comps.py 的 weighted_valuation() 做真實市場
時間效應校正（取代武斷的時間衰減假設）。

背景：房屋/土地估值常需要把「過去的成交價」換算成「現在等值價格」，若只
用「越新權重越高」的衰減公式來近似，會把單一個案的異常高價（例如某戶剛好
裝潢好、景觀佳）誤判成「市場普遍上漲」。這支腳本改抓官方實登彙整的區域
單價中位數/平均數季度序列，讓換算有真實市場資料支撐、可重現、可稽核。

使用方式：
    python fetch_price_index.py \
        --county-district 桃園市桃園區 \
        --out data/realty_comps/price_index_taoyuan_taoyuan.json

輸出 JSON 格式（可直接填入 targets.json 的 valuation.price_index_file）：
    {
      "source_url": "...",
      "unit": "萬/坪（單價中位數）",
      "fetched_at": "2026-07-25",
      "index": {"2016Q1": 18, "2016Q2": 19, ...}
    }

注意：此網站無需登入、無 Cloudflare 防護，但對 User-Agent 含有 "curl" 的
請求會回應 500（推測為簡易 WAF 規則），因此本腳本一律帶上瀏覽器風格的
User-Agent。
"""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_URL = "https://restat.ncscre.nccu.edu.tw"
STAT_KEY = {"median": "med", "average": "avg"}


def fetch_series(county_district, transaction, period, price_type, building,
                  start_year, start_month, end_year, end_month, transaction_url_segment):
    params = {
        "type": 0,
        "transactionOption": transaction,
        "area": county_district,
        "period": period,
        "building": building,
        "price": price_type,
        "presale": 0,
        "extreme": 0,
        "special": 0,
        "advanced": 0,
        "date": 1,
        "sy": start_year, "sm": start_month, "ey": end_year, "em": end_month,
    }
    url = f"{BASE_URL}/search/data?" + urllib.parse.urlencode(params)
    referer_path = "/".join(
        urllib.parse.quote(seg, safe="") for seg in (transaction_url_segment, county_district, "價量趨勢圖")
    )
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{BASE_URL}/search/{referer_path}",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def align_series(data, stat_key):
    """labels 只涵蓋請求的日期範圍，但 avg/med/box 是網站內部完整歷史序列
    （不受 sy/ey 篩選），需要用陣列長度差取尾端對齊 labels。"""
    labels = data["labels"]
    values = data[stat_key]
    offset = len(values) - len(labels)
    if offset < 0:
        raise ValueError(f"回傳的 {stat_key} 序列比 labels 短，資料格式可能已變動")
    return dict(zip(labels, values[offset:]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--county-district", required=True, help="縣市+行政區，如「桃園市桃園區」")
    ap.add_argument("--transaction", default="買賣", choices=["買賣", "租賃"], help="交易方式，預設買賣")
    ap.add_argument("--period", default="季", choices=["月", "季", "年"], help="統計期間粒度，預設季")
    ap.add_argument("--stat", default="median", choices=["median", "average"], help="取中位數或平均數，預設中位數")
    ap.add_argument("--building", default="全部", help="建物型態篩選，預設全部（可選：住宅電梯大樓/公寓/透天厝）")
    ap.add_argument("--start-year", type=int, required=True, help="起始年（西元）")
    ap.add_argument("--start-month", type=int, default=1, help="起始月，預設 1")
    ap.add_argument("--end-year", type=int, required=True, help="結束年（西元）")
    ap.add_argument("--end-month", type=int, default=12, help="結束月，預設 12")
    ap.add_argument("--fetched-at", required=True, help="資料擷取日期（ISO 格式，寫入輸出檔供追蹤）")
    ap.add_argument("--out", required=True, help="輸出 JSON 路徑")
    args = ap.parse_args()

    try:
        data = fetch_series(
            args.county_district, args.transaction, args.period, "單價", args.building,
            args.start_year, args.start_month, args.end_year, args.end_month, args.transaction,
        )
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}：抓取失敗，請確認 --county-district 拼字（需與網站選單一致，如「桃園市桃園區」）", file=sys.stderr)
        sys.exit(1)

    stat_key = STAT_KEY[args.stat]
    index = align_series(data, stat_key)

    out = {
        "_comment": (
            f"{args.county_district} {args.transaction} 單價{'中位數' if args.stat == 'median' else '平均數'}"
            f"指數（萬/坪），依{args.period}。來源: 政大商學院信義不動產研究發展中心 實登統計 "
            f"https://restat.ncscre.nccu.edu.tw/（資料來源: 內政部不動產交易實價查詢服務網，"
            f"{args.fetched_at} 擷取，資料更新日期 {data.get('updateDate', '')}）"
        ),
        "caveat_車位": (
            "此指數為該行政區全部買賣交易（含『房地(土地+建物)+車位』與不含車位的『房地(土地+建物)』混合）的"
            "單價統計，restat 網站未提供是否含車位的篩選選項，也未公開單價計算時車位坪數/價格的處理方式"
            "（是否已從建物移轉面積或總價中 netted out）。因此本指數只適合當作『區域房價整體走勢』的時間校正基準，"
            "不宜直接視為『含車位』或『不含車位』的乾淨分離序列；individual 交易的車位可比性，"
            "請用 build_realty_comps.py 的 require_parking 篩選（依各筆交易的『交易標的』欄位）處理，不依賴此指數。"
        ),
        "source_url": (
            f"{BASE_URL}/search/"
            + "/".join(urllib.parse.quote(s, safe="") for s in (args.transaction, args.county_district, "價量趨勢圖"))
        ),
        "unit": f"萬/坪（單價{'中位數' if args.stat == 'median' else '平均數'}）",
        "fetched_at": args.fetched_at,
        "index": index,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    quarters = list(index.keys())
    print(f"已輸出 {len(index)} 筆資料點（{quarters[0]} ~ {quarters[-1]}）到 {args.out}")


if __name__ == "__main__":
    main()
