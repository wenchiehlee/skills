#!/usr/bin/env python3
"""evaluate_digest.py — digest 品質檢查 (skill-conference-digest)

檢查產出的法說會 digest 是否符合投資決策導向 SOP：
- 投資決策摘要
- Surprise Matrix
- Q&A 壓力地圖
- 前次財測/承諾/措辭追蹤
- 加權評分
- 事件-模型-估值鏈條
- 證據台帳、證據類型、信心、來源

此工具只做結構與關鍵欄位檢查，不取代研究判斷。
"""
import argparse
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REQUIRED_PATTERNS = [
    ("投資決策摘要", r"零、投資決策摘要|##\s*零[、.]\s*投資決策摘要"),
    ("核心預期差", r"核心預期差|repo-only|市場共識|市場預期"),
    ("財測變化", r"財測變化|Guidance Delta|上修|下修|維持"),
    ("Q&A 增額資訊", r"Q&A[- ]?only|Q&A 增額資訊|僅在法人追問"),
    ("管理層可信度", r"管理層可信度|承諾追蹤|回答品質"),
    ("模型影響", r"模型影響|影響模型欄位|上修項目|下修項目"),
    ("Surprise Matrix", r"Surprise Matrix|本季實績.*QoQ.*YoY.*前次公司財測"),
    ("Q&A 壓力地圖", r"Q&A 壓力地圖|法人追問熱點|追問次數"),
    ("前次財測承諾措辭", r"前次財測.*承諾.*措辭|管理層承諾追蹤|措辭變化"),
    ("加權評分", r"加權紅黃綠燈|權重.*分數.*燈號"),
    ("事件模型估值", r"事件.*影響模型欄位.*可能估值影響|事件-模型-估值"),
    ("證據台帳", r"證據台帳|證據類型.*信心.*是否有矛盾"),
]

WARN_PATTERNS = [
    ("資料來源 metadata", r"資料來源"),
    ("分析模式 metadata", r"分析模式"),
    ("市場預期來源 metadata", r"市場預期來源"),
    ("資料品質 Issue metadata", r"資料品質 Issue"),
    ("EPS 品質", r"EPS 品質|一次性|匯兌|稅率|業外"),
    ("KPI 衛生", r"KPI|non-GAAP|自定義"),
    ("CapEx 風險", r"CapEx/營收|CapEx/折舊|折舊|FCF"),
]

OVERCONFIDENT_STOCK_PATTERNS = [
    r"股價(將|會|一定|必然)(上漲|下跌|大漲|大跌)",
    r"保證.*股價",
]


def line_of(text, pattern):
    m = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    return text.count("\n", 0, m.start()) + 1


def main():
    ap = argparse.ArgumentParser(description="檢查法說會 digest 是否符合 conference-digest SOP")
    ap.add_argument("digest", type=Path)
    args = ap.parse_args()

    if not args.digest.exists():
        print(f"[ERROR] 找不到檔案: {args.digest}", file=sys.stderr)
        sys.exit(2)

    text = args.digest.read_text(encoding="utf-8", errors="replace")
    errors = []
    warnings = []

    for name, pattern in REQUIRED_PATTERNS:
        if not re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            errors.append(f"缺少必要結構或欄位: {name}")

    for name, pattern in WARN_PATTERNS:
        if not re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            warnings.append(f"建議補強: {name}")

    for pattern in OVERCONFIDENT_STOCK_PATTERNS:
        loc = line_of(text, pattern)
        if loc:
            errors.append(f"第 {loc} 行疑似過度肯定股價預測，應改為條件式催化劑/風險分析")

    # 找出看似數字但附近缺來源的段落，作為弱檢查。
    numeric_lines = []
    for i, line in enumerate(text.splitlines(), 1):
        if re.search(r"\d+(?:\.\d+)?\s*(?:%|ppt|億|元|季|年|Q[1-4])", line):
            if not re.search(r"來源|Page|頁|Q&A|webcast|\(\d{1,3}:\d{2}(?:\.\d{3})?\)", line):
                numeric_lines.append(i)
    if len(numeric_lines) > 20:
        warnings.append(f"有 {len(numeric_lines)} 行含數字但同列未見來源標記，請確認重大數字已進入證據台帳")

    for msg in errors:
        print(f"[ERROR] {msg}")
    for msg in warnings:
        print(f"[WARN] {msg}")
    if not errors and not warnings:
        print("[OK] digest 結構符合 conference-digest SOP 的基本檢查")
    else:
        print(f"\n合計: ERROR {len(errors)} / WARN {len(warnings)}")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
