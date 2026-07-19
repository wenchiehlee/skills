#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild and plot biztrends.TW Taiwan cycle index from newest revenue data."""

from __future__ import annotations

import argparse
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
        if (candidate / "scripts" / "build_company_cycle_index_taiwan.py").is_file() and (candidate / "scripts" / "plot_company_cycle_index_taiwan.py").is_file():
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


def segment_weight_summary(root: Path) -> tuple[int, int, str]:
    path = root / "data" / "company_segment_weights.csv"
    if not path.is_file():
        raise SystemExit(f"Segment weights file is required but missing: {path.relative_to(root)}")
    df = pd.read_csv(path)
    required = {"stock_code", "segment_name", "weight_pct"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"{path.relative_to(root)} missing required columns: {', '.join(missing)}")
    valid = df.dropna(subset=["stock_code", "segment_name", "weight_pct"]).copy()
    if "market" in valid.columns:
        valid = valid[valid["market"].fillna("Taiwan").eq("Taiwan")].copy()
    if valid.empty:
        raise SystemExit(f"{path.relative_to(root)} has no usable Taiwan segment weight rows")
    source_period = ""
    if "source_period" in valid.columns:
        source_periods = valid["source_period"].dropna().astype(str)
        if not source_periods.empty:
            source_period = source_periods.max()
    return int(valid["stock_code"].astype(str).nunique()), int(len(valid)), source_period


def built_segment_weight_summary(root: Path) -> tuple[int, int]:
    mapping_path = root / "data" / "company_cycle_mapping.csv"
    major_path = root / "data" / "company_major_cycle_weights.csv"
    for path in (mapping_path, major_path):
        if not path.is_file():
            raise SystemExit(f"Segment weight audit output missing after build: {path.relative_to(root)}")

    mapping = pd.read_csv(mapping_path)
    if "segment_weight_override" not in mapping.columns:
        raise SystemExit(f"{mapping_path.relative_to(root)} missing required column: segment_weight_override")
    override_count = int((mapping["segment_weight_override"].fillna("").astype(str) == "Y").sum())
    if override_count == 0:
        raise SystemExit("No segment_weight_override=Y rows found after build; segment weights were not applied")

    major = pd.read_csv(major_path)
    if major.empty:
        raise SystemExit(f"{major_path.relative_to(root)} is empty; segment weight cycle allocation was not written")
    return override_count, int(len(major))


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
    index_path = root / "data" / "company_cycle_intensity_taiwan.csv"
    by_symbol_path = root / "data" / "company_cycle_intensity_by_symbol_taiwan.csv"
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
    latest = latest.sort_values("revenue_twd_bn", ascending=False)
    leadership = latest.sort_values("yoy_pct", ascending=False).head(3)
    laggards = latest.sort_values("yoy_pct", ascending=True).head(2)

    prior_month = previous_month(latest_month)
    prior = plot_df[plot_df["month"].astype(str) == prior_month][["canonical_cycle", "yoy_pct"]].rename(columns={"yoy_pct": "prior_yoy_pct"})
    latest_with_prior = latest.merge(prior, on="canonical_cycle", how="left")
    latest_with_prior["mom_yoy_change"] = latest_with_prior["yoy_pct"] - latest_with_prior["prior_yoy_pct"]
    accelerating = latest_with_prior.dropna(subset=["mom_yoy_change"]).sort_values("mom_yoy_change", ascending=False).head(3)

    ai_row = latest[latest["canonical_cycle"] == "AI_Compute_Infra"]
    memory_row = latest[latest["canonical_cycle"] == "Memory"]
    network_row = latest[latest["canonical_cycle"] == "Network_Infra"]
    pc_row = latest[latest["canonical_cycle"] == "PC_Consumer"]
    smartphone_row = latest[latest["canonical_cycle"] == "Smartphone"]
    software_row = latest[latest["canonical_cycle"] == "Software_SaaS"]

    def one(cycle: str) -> pd.Series | None:
        rows = latest[latest["canonical_cycle"] == cycle]
        if rows.empty:
            return None
        return rows.iloc[0]

    def cycle_value(cycle: str) -> str:
        row = one(cycle)
        if row is None:
            return f"`{cycle}` n/a"
        return f"`{cycle}` YoY {fmt_pct(float(row['yoy_pct']))} / {fmt_num(float(row['revenue_twd_bn']))} 億元"

    def compact_cycle_list(rows: pd.DataFrame) -> str:
        return "、".join(
            f"`{row['canonical_cycle']}` YoY {fmt_pct(float(row['yoy_pct']))} / {fmt_num(float(row['revenue_twd_bn']))} 億元"
            for _, row in rows.iterrows()
        )

    def compact_accel_list(rows: pd.DataFrame) -> str:
        return "、".join(
            f"`{row['canonical_cycle']}` YoY 月變化 {fmt_pct(float(row['mom_yoy_change']))}"
            for _, row in rows.iterrows()
        )

    def top3_share(cycle: str) -> str:
        cdf = by_latest[by_latest["canonical_cycle"] == cycle].sort_values("revenue_twd_bn", ascending=False)
        if cdf.empty:
            return "n/a"
        total = float(cdf["revenue_twd_bn"].sum())
        if total == 0:
            return "n/a"
        parts = []
        for _, row in cdf.head(3).iterrows():
            revenue = float(row["revenue_twd_bn"])
            share = revenue / total * 100
            parts.append(f"{row['symbol']} {fmt_num(revenue)} 億/{share:.1f}%")
        share = float(cdf.head(3)["revenue_twd_bn"].sum()) / total * 100
        return f"{'、'.join(parts)}；Top3 {share:.1f}%"

    def top3_pct(cycle: str) -> float | None:
        cdf = by_latest[by_latest["canonical_cycle"] == cycle].sort_values("revenue_twd_bn", ascending=False)
        if cdf.empty:
            return None
        total = float(cdf["revenue_twd_bn"].sum())
        if total == 0:
            return None
        return float(cdf.head(3)["revenue_twd_bn"].sum()) / total * 100

    def interpretation_qa_summary() -> str:
        return (
            "本次解讀已先把 `AI_Compute_Infra` 視為加權 exposure proxy，而不是純 AI server 營收；"
            "同時檢查 YoY 極端值、YoY 月變化、Top contributors 集中度與 `Other` 占比，"
            "用來降低因公司分項揭露缺漏、混合營收或分類權重假設造成的資料誤讀。"
        )

    def anomaly_summary() -> str:
        notes = []
        yoy_extremes = latest_with_prior[latest_with_prior["yoy_pct"].abs() >= 100].sort_values("yoy_pct", ascending=False)
        if not yoy_extremes.empty:
            notes.append("YoY 極端值：" + "、".join(
                f"`{row['canonical_cycle']}` {fmt_pct(float(row['yoy_pct']))}"
                for _, row in yoy_extremes.iterrows()
            ))
        slope_extremes = latest_with_prior.dropna(subset=["mom_yoy_change"])
        slope_extremes = slope_extremes[slope_extremes["mom_yoy_change"].abs() >= 25].sort_values("mom_yoy_change", key=lambda s: s.abs(), ascending=False)
        if not slope_extremes.empty:
            notes.append("YoY 斜率突變：" + "、".join(
                f"`{row['canonical_cycle']}` 月變化 {fmt_pct(float(row['mom_yoy_change']))}"
                for _, row in slope_extremes.head(4).iterrows()
            ))
        concentrated = []
        for cycle in sorted(set(by_latest["canonical_cycle"])):
            share = top3_pct(cycle)
            if share is not None and share >= 80:
                concentrated.append(f"`{cycle}` Top3 {share:.1f}%")
        if concentrated:
            notes.append("成分集中：" + "、".join(concentrated[:5]))
        other = one("Other")
        if other is not None:
            other_share = float(other["revenue_twd_bn"]) / latest_total * 100 if latest_total else 0
            if other_share >= 10:
                notes.append(f"`Other` 占總 cycle revenue {other_share:.1f}%，可能稀釋或扭曲主題週期訊號")
        if not notes:
            return "未偵測到明顯異常值；仍需逐月確認 raw revenue 與 cycle mapping 是否有分類或申報口徑變動，並回查 AI server / data server / PC 拆分所依賴的 investor conference、法說會或年報揭露是否完整。"
        return "；".join(notes) + "。這些訊號應先視為需要查證的研究提醒，優先回看原始月營收、分類權重、一次性出貨或低基期，而不是直接外推成長趨勢；`AI_Compute_Infra` 應視為 AI/data center exposure proxy，不代表成分公司只做 AI server；AI server / data server / PC 拆分也需回查 investor conference、法說會或年報揭露，因部分公司可能缺漏分項、揭露口徑不同，或同時包含 PC、手機、消費與其他業務。"

    ai_text = cycle_value("AI_Compute_Infra")
    memory_text = cycle_value("Memory")
    network_text = cycle_value("Network_Infra")
    pc_text = cycle_value("PC_Consumer")
    smartphone_text = cycle_value("Smartphone")
    software_text = cycle_value("Software_SaaS")

    ai_concentration = top3_share("AI_Compute_Infra")
    memory_concentration = top3_share("Memory")
    network_concentration = top3_share("Network_Infra")

    ai_yoy = float(ai_row.iloc[0]["yoy_pct"]) if not ai_row.empty else None
    memory_yoy = float(memory_row.iloc[0]["yoy_pct"]) if not memory_row.empty else None
    network_yoy = float(network_row.iloc[0]["yoy_pct"]) if not network_row.empty else None
    software_yoy = float(software_row.iloc[0]["yoy_pct"]) if not software_row.empty else None

    if ai_yoy is not None and memory_yoy is not None and network_yoy is not None and min(ai_yoy, memory_yoy, network_yoy) > 40:
        regime = "AI demand 已從單一 GPU training 主線，擴散到 inference 伺服器、網通交換、儲存與記憶體補庫存。"
    elif ai_yoy is not None and ai_yoy > 20:
        regime = "AI demand 仍是主要成長來源，但擴散強度需要用 Memory 與 Network_Infra 是否同步確認。"
    else:
        regime = "AI demand 對總指數的支撐轉弱，後續需看終端與傳統 IT 是否接棒。"

    if software_yoy is not None and software_yoy < 10:
        software_read = "Software_SaaS YoY 低於硬體週期，代表台灣供應鏈目前反映的是 AI infrastructure capex，而不是軟體 monetization 的同步放大。"
    else:
        software_read = "Software_SaaS 未明顯落後硬體週期，需進一步確認是否有應用層需求擴散。"

    lines = [
        "### 台灣 Cycle Index 深度觀察",
        "",
        f"資料新鮮度：GoodInfo Analyzer raw revenue 最新月份為 `{raw_latest}`，共 `{raw_count}` 筆；derived cycle CSV 最新月份為 `{latest_month}`。以下分析使用 `data/company_cycle_intensity_taiwan.csv` 的 `{plot_start}` ~ `{latest_month}` 近 60 個月 YoY 序列，並以 `data/company_cycle_intensity_by_symbol_taiwan.csv` 驗證最新月份貢獻結構。",
        "",
        f"**策略主軸**：最新月份總 cycle revenue 約 `{fmt_num(latest_total)}` 億元，YoY 領先為 {compact_cycle_list(leadership)}，相對落後為 {compact_cycle_list(laggards)}。這代表目前台灣電子供應鏈的景氣主線仍偏向 AI infrastructure 與資料中心相關資本支出，而不是單純的終端消費電子復甦；但 `AI_Compute_Infra` 是依公司揭露資料與權重建立的 AI/data center exposure proxy，不代表成分公司只聚焦 AI server；AI server / data server / PC 的拆分需要用分項揭露覆蓋率檢查其穩定性。{regime}",
        "",
        f"**週期輪動**：{ai_text}、{network_text}、{memory_text} 同步位於高成長區，顯示 AI/data center demand 從 compute 擴張到 networking、memory/storage 的 read-through 正在成立；{pc_text} 與 {smartphone_text} 同步轉強，較像 AI PC、邊緣裝置與一般補庫存的第二層擴散，但仍需區分低基期反彈與真正需求上修。{software_read}",
        "",
        f"**結構與集中度**：AI_Compute_Infra 的主要貢獻為 {ai_concentration}；Memory 為 {memory_concentration}；Network_Infra 為 {network_concentration}。因此指數解讀不能只看總 YoY，還要看成長是否由少數大型權值股貢獻；若 Top3 集中度維持高檔，代表投資結論更偏供應鏈龍頭與關鍵零組件，而不是全面性產業復甦。",
        "",
        f"**跨台股與美股 read-through（資料推論）**：目前台股營收訊號對應到美股應優先觀察 CSP AI capex、GPU/ASIC server、HBM/DRAM/NAND、Ethernet/optical networking 與電源散熱鏈。若後續 {compact_accel_list(accelerating)} 持續，代表 AI inference 與 agentic workload 帶來的儲存、記憶體、CPU/GPU 協同需求可能繼續往台灣供應鏈擴散；反之，若 AI_Compute_Infra YoY 高檔但 Memory 或 Network_Infra 斜率先轉弱，需警覺 capex 節奏或庫存週期降溫。",
        "",
        f"**資料解讀 QA**：{interpretation_qa_summary()}",
        "",
        f"**異常與非預期資料提醒**：{anomaly_summary()}",
        "",
        "**研究含義**：短線重點是確認 AI infrastructure 是否從龍頭營收擴散到記憶體、網通、ODM、電源散熱與終端裝置。後續追蹤三個訊號：第一，AI_Compute_Infra、Memory、Network_Infra 的 YoY 斜率是否同步維持；第二，PC_Consumer 與 Smartphone 是否能延續兩到三個月而非一次性補庫存；第三，Top3 貢獻是否下降並讓更多公司參與成長。主要風險是高基期、CSP capex 遞延、記憶體價格波動，以及終端需求未跟上 infrastructure build-out。",
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
    command_line = "產出指令：`python ../skills/common/skill-company-cycle-index/scripts/run_company_cycle_index.py`"
    content = content.replace("產出指令：`python scripts/plot_company_cycle_index_taiwan.py`", command_line)

    import datetime
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S CST")
    generated = f"產生時間：{timestamp}"
    content = replace_or_insert_section(
        content,
        "<!-- company_cycle_index_taiwan_generated -->",
        "<!-- /company_cycle_index_taiwan_generated -->",
        generated,
        command_line,
    )
    insights = build_insights(root, raw_latest, raw_count)
    content = replace_or_insert_section(
        content,
        "<!-- company_cycle_index_taiwan_insights_start -->",
        "<!-- company_cycle_index_taiwan_insights_end -->",
        insights,
        "<!-- /company_cycle_index_taiwan_generated -->",
    )
    readme_path.write_text(content, encoding="utf-8", newline="")
    print(f"README.md TW cycle insights updated -> {timestamp}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild TW cycle index from newest revenue data, plot PNG, and update README insights."
    )
    parser.parse_args()

    root = find_project_root()
    print(f"Project root: {root}")

    raw_path = raw_revenue_path(root)
    raw_latest, raw_count = latest_month_and_count(raw_path, "月別")
    print(f"Raw revenue: {raw_path}")
    print(f"Raw latest month: {raw_latest} ({raw_count} rows)")

    segment_company_count, segment_row_count, segment_latest_period = segment_weight_summary(root)
    suffix = f", latest source period: {segment_latest_period}" if segment_latest_period else ""
    print(
        "Taiwan segment weights: "
        f"data/company_segment_weights.csv "
        f"({segment_company_count} companies, {segment_row_count} rows{suffix})"
    )

    run(["python3", "scripts/build_company_cycle_index_taiwan.py"], root)

    override_count, major_weight_rows = built_segment_weight_summary(root)
    print(
        "Segment weight audit: "
        f"company_cycle_mapping.csv segment_weight_override=Y companies: {override_count}; "
        f"company_major_cycle_weights.csv rows: {major_weight_rows}"
    )

    derived_files = [
        root / "data" / "company_cycle_intensity_taiwan.csv",
        root / "data" / "company_cycle_intensity_by_symbol_taiwan.csv",
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
    run(["python3", "scripts/plot_company_cycle_index_taiwan.py"], root, env=env)

    png_path = root / "output" / "company_cycle_index_taiwan.png"
    if not png_path.is_file():
        raise SystemExit(f"PNG not generated: {png_path}")
    with Image.open(png_path) as im:
        print(f"PNG: {png_path} {im.format} {im.size} {im.mode}")

    update_readme(root, raw_latest, raw_count)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
