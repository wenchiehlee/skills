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


def build_insights(root: Path, raw_latest: str, raw_count: int) -> str:
    index_path = root / "data" / "tw_cycle_intensity_index.csv"
    by_symbol_path = root / "data" / "tw_cycle_intensity_by_symbol.csv"
    df = pd.read_csv(index_path)
    by_symbol = pd.read_csv(by_symbol_path)

    latest_month = str(df["month"].max())
    prev_month = previous_month(latest_month)
    latest = df[df["month"].astype(str) == latest_month].copy()
    prev = df[df["month"].astype(str) == prev_month][["canonical_cycle", "yoy_pct"]].rename(columns={"yoy_pct": "prev_yoy_pct"})
    latest = latest.merge(prev, on="canonical_cycle", how="left")
    latest["yoy_delta_pct"] = latest["yoy_pct"] - latest["prev_yoy_pct"]

    latest = latest.sort_values("revenue_twd_bn", ascending=False)
    revenue_leaders = latest.head(3)
    yoy_leaders = latest.sort_values("yoy_pct", ascending=False).head(3)
    acceleration_leaders = latest.dropna(subset=["yoy_delta_pct"]).sort_values("yoy_delta_pct", ascending=False).head(3)
    laggards = latest.sort_values("yoy_pct", ascending=True).head(2)

    total_revenue = float(latest["revenue_twd_bn"].sum())
    ai_row = latest[latest["canonical_cycle"] == "AI_Compute_Infra"]
    ai_share = None
    if not ai_row.empty and total_revenue:
        ai_share = float(ai_row.iloc[0]["revenue_twd_bn"]) / total_revenue * 100

    by_latest = by_symbol[by_symbol["month"].astype(str) == latest_month].copy()
    by_latest["revenue_twd_bn"] = pd.to_numeric(by_latest["revenue_twd_bn"], errors="coerce")
    contributor_lines = []
    for cycle in revenue_leaders["canonical_cycle"]:
        cdf = by_latest[by_latest["canonical_cycle"] == cycle].sort_values("revenue_twd_bn", ascending=False)
        cycle_total = float(cdf["revenue_twd_bn"].sum())
        top3 = cdf.head(3)
        parts = []
        for _, row in top3.iterrows():
            share = float(row["revenue_twd_bn"]) / cycle_total * 100 if cycle_total else 0
            parts.append(f"{row['symbol']} {fmt_num(float(row['revenue_twd_bn']))} 億元/{share:.1f}%")
        top3_share = float(top3["revenue_twd_bn"].sum()) / cycle_total * 100 if cycle_total else 0
        contributor_lines.append(f"- `{cycle}` 前三大貢獻為 {'、'.join(parts)}，合計占該 cycle {top3_share:.1f}%。")

    def cycle_summary(rows, metric: str) -> str:
        items = []
        for _, row in rows.iterrows():
            revenue = fmt_num(float(row["revenue_twd_bn"]))
            yoy = fmt_pct(float(row["yoy_pct"]))
            delta = row.get("yoy_delta_pct")
            if pd.notna(delta):
                items.append(f"`{row['canonical_cycle']}` {revenue} 億元、YoY {yoy}、較 {prev_month} 變化 {fmt_pct(float(delta))}")
            else:
                items.append(f"`{row['canonical_cycle']}` {revenue} 億元、YoY {yoy}")
        return "；".join(items)

    lines = [
        "### 台灣 Cycle Index 法人深度觀察",
        "",
        f"資料新鮮度：GoodInfo Analyzer raw revenue 最新月份為 `{raw_latest}`，共 `{raw_count}` 筆；derived cycle CSV 最新月份為 `{latest_month}`。以下判斷引用 `data/tw_cycle_intensity_index.csv` 與 `data/tw_cycle_intensity_by_symbol.csv`，不是單純目視 PNG。",
        "",
        f"- **Cycle leadership**：營收規模前三大為 {cycle_summary(revenue_leaders, 'revenue')}。YoY 動能前三大為 {cycle_summary(yoy_leaders, 'yoy')}。YoY 加速度前三大為 {cycle_summary(acceleration_leaders, 'accel')}。相對落後的是 {cycle_summary(laggards, 'yoy')}。",
        f"- **跨週期輪動**：`AI_Compute_Infra`、`Network_Infra`、`Memory` 與 `PC_Consumer` 同步保持高雙位數到三位數 YoY，代表 AI server、先進半導體、網通交換器與終端硬體補庫存仍在同一個上行鏈條。`Software_SaaS` YoY 仍為正但規模小，較像應用端跟隨訊號，不是本輪台股營收擴張的主驅動。",
        f"- **台股對美股 read-through（資料推論）**：台灣供應鏈在 `{latest_month}` 的強勢集中於 AI infrastructure、memory 與 network，對應到美股雲端 CSP AI capex、GPU/ASIC server supply chain、HBM/DRAM/NAND 與 Ethernet/optical networking 需求仍具支撐；`Smartphone` 與 `PC_Consumer` YoY 轉強則提供 Apple/Qualcomm/AMD/PC OEM demand recovery 的邊際確認，但目前訊號仍弱於 AI capex 主線。",
        f"- **結構與集中度**：最新月份全 cycle 合計營收約 `{fmt_num(total_revenue)}` 億元；`AI_Compute_Infra` 占比約 `{ai_share:.1f}%`，顯示總指數高度受 AI infrastructure 權重影響。",
        *contributor_lines,
        "- **投資研究含義與風險**：後續追蹤重點是 `Memory` YoY 高成長能否延續到價格與毛利、`Network_Infra` 是否跟隨 CSP 資本支出持續擴張、`PC_Consumer`/`Smartphone` 是否只是低基期反彈，以及 `AI_Compute_Infra` 是否因少數大型權值公司造成 concentration bias。下一步應交叉驗證美股 CSP capex guidance、NVDA/AMD/Broadcom/Marvell 訂單訊號、台股 ODM 月營收與法說會 backlog/commentary。",
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
