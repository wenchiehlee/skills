#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild and plot biztrends.TW Taiwan cycle index from newest revenue data."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pandas as pd
from PIL import Image


def find_project_root() -> Path:
    env_root = os.environ.get("BIZTRENDS_TW_ROOT")
    candidates = []
    if env_root:
        candidates.append(Path(env_root))
    candidates.extend([Path.cwd(), *Path.cwd().parents])
    for candidate in candidates:
        if (candidate / "scripts" / "build_tw_cycle_index.py").is_file() and (candidate / "scripts" / "plot_tw_cycle_index.py").is_file():
            return candidate.resolve()
    raise SystemExit("Cannot find biztrends.TW root. Run from the repo root or set BIZTRENDS_TW_ROOT.")


def raw_revenue_path(root: Path) -> Path:
    local = root / "data" / "Python-Actions.GoodInfo.Analyzer" / "raw_revenue.csv"
    sibling = root.parent / "Python-Actions.GoodInfo.Analyzer" / "data" / "stage1_raw" / "raw_revenue.csv"
    for path in (local, sibling):
        if path.is_file():
            return path
    raise SystemExit(f"Cannot find raw_revenue.csv at {local} or {sibling}")


def latest_month_and_count(csv_path: Path, month_col: str) -> tuple[str, int]:
    df = pd.read_csv(csv_path)
    if month_col not in df.columns:
        raise SystemExit(f"{csv_path} missing required column: {month_col}")
    months = df[month_col].astype(str)
    latest = months.max()
    return latest, int((months == latest).sum())


def run(cmd: list[str], root: Path, env: dict[str, str] | None = None) -> None:
    print("$ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=root, env=env, check=True)


def fmt_num(value: float) -> str:
    return f"{value:,.1f}"


def fmt_pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f}%"


def previous_month(month: str) -> str:
    year, month_num = [int(part) for part in month.split("/")]
    if month_num == 1:
        return f"{year - 1}/12"
    return f"{year}/{month_num - 1:02d}"


def format_point(row: pd.Series) -> str:
    return f"{row['month']} / 營收 {fmt_num(float(row['revenue_twd_bn']))} 億元 / YoY {fmt_pct(float(row['yoy_pct']))}"


def latest_phase(latest_yoy: float, yoy_delta_3m: float | None) -> str:
    if latest_yoy >= 20 and yoy_delta_3m is not None and yoy_delta_3m > 5:
        return "擴張加速"
    if latest_yoy >= 20:
        return "高檔擴張"
    if latest_yoy >= 0 and yoy_delta_3m is not None and yoy_delta_3m < -5:
        return "成長降溫"
    if latest_yoy >= 0:
        return "溫和成長"
    if yoy_delta_3m is not None and yoy_delta_3m > 5:
        return "低檔修復"
    return "收縮"


def industry_lifecycle_stage(latest_yoy: float, yoy_delta_3m: float | None, top_is_end: bool, months_since_begin: int) -> str:
    # Stage vocabulary follows Malta Business School's four-stage Industry Life Cycle: Introduction, Growth, Maturity, Decline.
    if months_since_begin <= 3 and latest_yoy >= 0:
        return "Introduction / 導入"
    if latest_yoy < 0:
        return "Decline / 衰退"
    if latest_yoy >= 20 and (top_is_end or yoy_delta_3m is None or yoy_delta_3m >= -5):
        return "Growth / 成長"
    if latest_yoy >= 0 and yoy_delta_3m is not None and yoy_delta_3m < -20:
        return "Maturity-to-Decline / 成熟轉衰退"
    return "Maturity / 成熟"


def top_contributors(by_latest: pd.DataFrame, cycle: str) -> str:
    cdf = by_latest[by_latest["canonical_cycle"] == cycle].sort_values("revenue_twd_bn", ascending=False)
    if cdf.empty:
        return "無 by-symbol 資料"
    cycle_total = float(cdf["revenue_twd_bn"].sum())
    parts = []
    for _, row in cdf.head(3).iterrows():
        revenue = float(row["revenue_twd_bn"])
        share = revenue / cycle_total * 100 if cycle_total else 0
        parts.append(f"{row['symbol']} {fmt_num(revenue)} 億/{share:.1f}%")
    top3_share = float(cdf.head(3)["revenue_twd_bn"].sum()) / cycle_total * 100 if cycle_total else 0
    return f"{'、'.join(parts)}；Top3 {top3_share:.1f}%"


def first_recovery_after_bottom(cdf: pd.DataFrame, bottom_pos: int) -> pd.Series:
    after_bottom = cdf.iloc[bottom_pos:].reset_index(drop=True)
    non_negative = after_bottom[after_bottom["yoy_pct"] >= 0]
    if not non_negative.empty:
        return non_negative.iloc[0]
    return cdf.iloc[bottom_pos]


def ai_regime_anchor(cdf: pd.DataFrame) -> pd.Series | None:
    anchor = cdf[cdf["month"].astype(str) >= "2023/01"]
    if anchor.empty:
        return None
    return anchor.iloc[0]


def build_cycle_lifecycle(cycle_df: pd.DataFrame, by_latest: pd.DataFrame, cycle: str) -> str:
    cdf = cycle_df.sort_values("month_dt").reset_index(drop=True)
    cdf["yoy_pct"] = pd.to_numeric(cdf["yoy_pct"], errors="coerce")
    cdf["revenue_twd_bn"] = pd.to_numeric(cdf["revenue_twd_bn"], errors="coerce")
    cdf = cdf.dropna(subset=["yoy_pct", "revenue_twd_bn"]).reset_index(drop=True)
    if cdf.empty:
        return f"| `{cycle}` | n/a | n/a | n/a | n/a | YoY 資料不足 |"

    bottom_pos = int(cdf["yoy_pct"].idxmin())
    bottom = cdf.iloc[bottom_pos]
    begin = first_recovery_after_bottom(cdf, bottom_pos)
    begin_pos = int(cdf.index[cdf["month"] == begin["month"]][0])
    after_begin = cdf.iloc[begin_pos:]
    top = after_begin.loc[after_begin["yoy_pct"].idxmax()] if not after_begin.empty else cdf.loc[cdf["yoy_pct"].idxmax()]
    end = cdf.iloc[-1]
    top_is_end = str(top["month"]) == str(end["month"])
    months_since_begin = len(cdf.iloc[begin_pos:]) - 1

    begin_text = format_point(begin)
    anchor = ai_regime_anchor(cdf) if cycle == "AI_Compute_Infra" else None
    if anchor is not None and str(anchor["month"]) != str(begin["month"]):
        begin_text = f"AI regime anchor {anchor['month']} / data recovery {begin_text}"

    latest_yoy = float(end["yoy_pct"])
    yoy_delta_3m = None
    if len(cdf) >= 4:
        yoy_delta_3m = latest_yoy - float(cdf.iloc[-4]["yoy_pct"])
    phase = latest_phase(latest_yoy, yoy_delta_3m)
    lifecycle_stage = industry_lifecycle_stage(latest_yoy, yoy_delta_3m, top_is_end, months_since_begin)
    slope_text = "n/a" if yoy_delta_3m is None else fmt_pct(yoy_delta_3m)
    contributors = top_contributors(by_latest, cycle)
    read = (
        f"{phase}；bottom -> end YoY 修復 {fmt_pct(float(end['yoy_pct']) - float(bottom['yoy_pct']))}；"
        f"近 3 個月 YoY 變化 {slope_text}；Top contributors: {contributors}"
    )
    return "| " + " | ".join([
        f"`{cycle}`",
        lifecycle_stage,
        begin_text,
        format_point(top),
        format_point(bottom),
        format_point(end),
        read,
    ]) + " |"


def build_insights(root: Path, raw_latest: str, raw_count: int) -> str:
    index_path = root / "data" / "tw_cycle_intensity_index.csv"
    by_symbol_path = root / "data" / "tw_cycle_intensity_by_symbol.csv"
    df = pd.read_csv(index_path)
    by_symbol = pd.read_csv(by_symbol_path)
    df["month_dt"] = pd.to_datetime(df["month"], format="%Y/%m")
    df["yoy_pct"] = pd.to_numeric(df["yoy_pct"], errors="coerce")
    df["revenue_twd_bn"] = pd.to_numeric(df["revenue_twd_bn"], errors="coerce")
    by_symbol["revenue_twd_bn"] = pd.to_numeric(by_symbol["revenue_twd_bn"], errors="coerce")

    latest_month = str(df["month"].max())
    max_dt = df["month_dt"].max()
    cutoff = max_dt - pd.DateOffset(months=59)
    plot_df = df[df["month_dt"] >= cutoff].copy()
    plot_start = str(plot_df["month"].min())
    by_latest = by_symbol[by_symbol["month"].astype(str) == latest_month].copy()

    latest = plot_df[plot_df["month"].astype(str) == latest_month].copy()
    latest_total = float(latest["revenue_twd_bn"].sum())
    leadership = latest.sort_values("yoy_pct", ascending=False).head(3)
    laggards = latest.sort_values("yoy_pct", ascending=True).head(2)

    def compact_cycle_list(rows: pd.DataFrame) -> str:
        return "、".join(
            f"`{row['canonical_cycle']}` YoY {fmt_pct(float(row['yoy_pct']))} / {fmt_num(float(row['revenue_twd_bn']))} 億元"
            for _, row in rows.iterrows()
        )

    cycle_order = [
        "AI_Compute_Infra",
        "AI_Compute",
        "Memory",
        "Network_Infra",
        "Smartphone",
        "PC_Consumer",
        "EV_Automotive",
        "Software_SaaS",
        "Consumer_IoT",
        "Digital_Ads",
        "Other",
    ]
    cycles = [c for c in cycle_order if c in set(plot_df["canonical_cycle"])]
    cycles += [c for c in sorted(set(plot_df["canonical_cycle"])) if c not in cycles]
    table_rows = [build_cycle_lifecycle(plot_df[plot_df["canonical_cycle"] == cycle], by_latest, cycle) for cycle in cycles]

    lines = [
        "### 台灣 Cycle Index 深度觀察",
        "",
        f"資料新鮮度：GoodInfo Analyzer raw revenue 最新月份為 `{raw_latest}`，共 `{raw_count}` 筆；derived cycle CSV 最新月份為 `{latest_month}`。以下分析使用 `data/tw_cycle_intensity_index.csv` 的 `{plot_start}` ~ `{latest_month}` 近 60 個月 YoY 序列，並以 `data/tw_cycle_intensity_by_symbol.csv` 驗證最新月份貢獻結構。",
        "",
        f"最新月份總 cycle revenue 約 `{fmt_num(latest_total)}` 億元；YoY 領先為 {compact_cycle_list(leadership)}；相對落後為 {compact_cycle_list(laggards)}。以下逐一拆解每個 Canonical Cycle 的 begin -> top-peak -> bottom-peak -> end；begin 採用「bottom-peak 後首個 YoY 轉正月」，AI_Compute_Infra 另標註 2023 OpenAI/ChatGPT regime anchor。Industry lifecycle stage 採用 Malta Business School 對 Introduction / Growth / Maturity / Decline 的四階段定義作為語意框架，再用本地 YoY 與營收資料判斷。",
        "",
        "| Canonical Cycle | Industry lifecycle stage | Begin | Top-peak | Bottom-peak | End | 研究解讀 |",
        "|---|---|---|---|---|---|---|",
        *table_rows,
        "",
        "**跨台股與美股 read-through（資料推論）**：若 `AI_Compute_Infra`、`Network_Infra`、`Memory` 同時處於高檔擴張或擴張加速，通常對應美股 CSP AI capex、GPU/ASIC server、HBM/DRAM/NAND、Ethernet/optical networking 需求仍強；若 `PC_Consumer`、`Smartphone` 從 bottom-peak 後續修復，代表終端補庫存改善，但需用 Apple/Qualcomm/AMD/PC OEM guidance 驗證是否為持續需求，而非低基期反彈。",
        "",
        "**下一步驗證**：逐月追蹤各 cycle 的 end 是否持續接近 top-peak、YoY 3 個月斜率是否轉負、Top3 貢獻是否過度集中；同步交叉檢查美股 NVDA/AMD/Broadcom/Marvell、CSP capex guidance，以及台股 ODM/網通/記憶體法說會 backlog 與價格評論。",
    ]
    return "\n".join(lines)


def replace_or_insert_section(content: str, start: str, end: str, section: str, anchor: str) -> str:
    if start in content and end in content:
        before = content.split(start)[0]
        after = content.split(end, 1)[1]
        return before + start + "\n" + section.strip() + "\n" + end + after
    if anchor not in content:
        raise SystemExit(f"README anchor not found: {anchor}")
    return content.replace(anchor, anchor + "\n\n" + start + "\n" + section.strip() + "\n" + end, 1)


def update_readme(root: Path, raw_latest: str, raw_count: int) -> None:
    readme_path = root / "README.md"
    content = readme_path.read_text(encoding="utf-8")
    command_line = "產出指令：`python ../skills/common/skill-tw-cycle-index/scripts/run_tw_cycle_index.py`"
    content = content.replace("產出指令：`python scripts/plot_tw_cycle_index.py`", command_line)

    import datetime
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S CST")
    generated = f"產生時間：{timestamp}"
    content = replace_or_insert_section(
        content,
        "<!-- tw_cycle_index_generated -->",
        "<!-- /tw_cycle_index_generated -->",
        generated,
        command_line,
    )
    insights = build_insights(root, raw_latest, raw_count)
    content = replace_or_insert_section(
        content,
        "<!-- tw_cycle_index_insights_start -->",
        "<!-- tw_cycle_index_insights_end -->",
        insights,
        "<!-- /tw_cycle_index_generated -->",
    )
    readme_path.write_text(content, encoding="utf-8", newline="")
    print(f"README.md TW cycle insights updated -> {timestamp}")


def main() -> int:
    root = find_project_root()
    print(f"Project root: {root}")

    raw_path = raw_revenue_path(root)
    raw_latest, raw_count = latest_month_and_count(raw_path, "月別")
    print(f"Raw revenue: {raw_path}")
    print(f"Raw latest month: {raw_latest} ({raw_count} rows)")

    run(["python3", "scripts/build_tw_cycle_index.py"], root)

    derived_files = [
        root / "data" / "tw_cycle_intensity_index.csv",
        root / "data" / "tw_cycle_intensity_by_symbol.csv",
    ]
    for path in derived_files:
        latest, count = latest_month_and_count(path, "month")
        print(f"{path.relative_to(root)} latest month: {latest} ({count} rows)")
        if latest < raw_latest:
            raise SystemExit(
                f"Derived data is stale: {path.relative_to(root)} latest={latest}, raw latest={raw_latest}"
            )

    env = os.environ.copy()
    env["CI"] = "1"
    run(["python3", "scripts/plot_tw_cycle_index.py"], root, env=env)

    png_path = root / "output" / "tw_cycle_index.png"
    if not png_path.is_file():
        raise SystemExit(f"PNG not generated: {png_path}")
    with Image.open(png_path) as im:
        print(f"PNG: {png_path} {im.format} {im.size} {im.mode}")

    update_readme(root, raw_latest, raw_count)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
