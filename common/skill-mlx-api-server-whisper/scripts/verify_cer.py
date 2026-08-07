"""
verify_cer.py — Language-Adaptive measurement (CER/WER) with stable report outputs.

Features:
- Adaptive CER/WER based on CJK ratio.
- key_WER/key_CER focused KPIs (weighted).
- Per-stem cer_report and key_cer_detail outputs with legacy-compatible structure.
- Global cross-stem leaderboard generation.
"""

from __future__ import annotations
import argparse
import datetime
import io
import re
import sys
from pathlib import Path
from datetime import timedelta, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 定義固定時區為 CST (UTC+8)
TZ_CST = timezone(timedelta(hours=8))

def _now_cst() -> str:
    return datetime.datetime.now(TZ_CST).strftime("%Y-%m-%d %H:%M CST")

# ── Text extraction ───────────────────────────────────────────────────────────

def extract_text(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    if "---" in content:
        content = content.split("---", 1)[-1]
    return " ".join(re.sub(r"\([\d:.]+\)\s*", " ", content).split())


def extract_segments(path: Path) -> list[str] | None:
    content = path.read_text(encoding="utf-8")
    if "---" in content:
        content = content.split("---", 1)[-1]
    pattern = re.compile(r"^\([\d:.]+\)\s*(.*)")
    segs = [m.group(1).strip() for line in content.splitlines() if (m := pattern.match(line.strip()))]
    return segs if segs else None


def extract_rtf(path: Path) -> str:
    m = re.search(r"^RTF:\s*([0-9.]+)", path.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else "—"


# ── Error analysis ────────────────────────────────────────────────────────────

def _normalize_text(text: str, mode: str = "cer") -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s\u4e00-\u9fff]", "", text)
    if mode == "wer":
        return " ".join(text.split())
    var_map = str.maketrans("儘裏噁麼一二三四五六七八九零", "盡裡惡麽1234567890")
    return "".join(text.translate(var_map).split())


def _error_rate(reference: str, hypothesis: str) -> tuple[float, str]:
    from jiwer import cer, wer

    ref_clean = reference.replace(" ", "")
    cjk_count = len([c for c in reference if "\u4e00" <= c <= "\u9fff"])
    if len(ref_clean) > 0 and (cjk_count / len(ref_clean)) < 0.1:
        return wer(_normalize_text(reference, "wer"), _normalize_text(hypothesis, "wer")), "WER"
    return cer(_normalize_text(reference, "cer"), _normalize_text(hypothesis, "cer")), "CER"


_TRIVIAL = frozenset({
    "的", "那", "了", "在", "個", "好", "嘛", "呢", "哦", "嗯", "啊", "也", "都", "吧",
    "這個", "那個", "就是", "然後", "a", "an", "the", "um", "uh", "ah", "oh", "well",
    "so", "like", "you", "know", "i", "mean", "actually", "right",
})


def _is_trivial(seg: str) -> bool:
    return seg.strip().lower() in _TRIVIAL or seg.strip() == ""


def _classify_errors(reference: str, hypothesis: str) -> dict:
    import difflib

    raw_rate, mode = _error_rate(reference, hypothesis)
    if mode == "WER":
        ref_tokens = _normalize_text(reference, "wer").split()
        hyp_tokens = _normalize_text(hypothesis, "wer").split()
    else:
        ref_tokens = list(_normalize_text(reference, "cer"))
        hyp_tokens = list(_normalize_text(hypothesis, "cer"))

    matcher = difflib.SequenceMatcher(None, ref_tokens, hyp_tokens)
    sub = ins = dele = 0
    key_sub = key_ins = key_del = 0
    w_sub = w_ins = w_del = 0

    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        n = max(i2 - i1, j2 - j1) if op == "replace" else (i2 - i1 if op == "delete" else j2 - j1)
        ref_seg = "".join(ref_tokens[i1:i2]) if mode == "CER" else " ".join(ref_tokens[i1:i2])
        hyp_seg = "".join(hyp_tokens[j1:j2]) if mode == "CER" else " ".join(hyp_tokens[j1:j2])
        if op == "replace":
            sub += n
            if not (_is_trivial(ref_seg) and _is_trivial(hyp_seg)):
                w_sub += n
                key_sub += n
        elif op == "insert":
            ins += n
            if not _is_trivial(hyp_seg):
                w_ins += n
                key_ins += n
        elif op == "delete":
            dele += n
            if not _is_trivial(ref_seg):
                w_del += n
                key_del += n

    denom = len(ref_tokens) if ref_tokens else 1
    weighted_rate = (w_sub + w_ins + w_del) / denom
    return {
        "raw_rate": raw_rate,
        "weighted_rate": weighted_rate,
        "mode": mode,
        "sub": sub,
        "ins": ins,
        "del": dele,
        "key_sub": key_sub,
        "key_ins": key_ins,
        "key_del": key_del,
    }


def _get_key_error_details(reference: str, hypothesis: str, mode: str, context_chars: int = 15) -> list[dict]:
    import difflib

    if mode == "WER":
        ref_tokens = _normalize_text(reference, "wer").split()
        hyp_tokens = _normalize_text(hypothesis, "wer").split()
    else:
        ref_tokens = list(_normalize_text(reference, "cer"))
        hyp_tokens = list(_normalize_text(hypothesis, "cer"))

    matcher = difflib.SequenceMatcher(None, ref_tokens, hyp_tokens)
    errors = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        ref_seg = "".join(ref_tokens[i1:i2]) if mode == "CER" else " ".join(ref_tokens[i1:i2])
        hyp_seg = "".join(hyp_tokens[j1:j2]) if mode == "CER" else " ".join(hyp_tokens[j1:j2])
        if op == "replace":
            is_key = not (_is_trivial(ref_seg) and _is_trivial(hyp_seg))
            n = max(i2 - i1, j2 - j1)
        elif op == "insert":
            is_key = not _is_trivial(hyp_seg)
            n = j2 - j1
        else:
            is_key = not _is_trivial(ref_seg)
            n = i2 - i1
        if not is_key:
            continue

        if mode == "CER":
            before = "".join(ref_tokens[max(0, i1 - context_chars):i1])
            after = "".join(ref_tokens[i2:min(len(ref_tokens), i2 + context_chars)])
        else:
            before = " ".join(ref_tokens[max(0, i1 - context_chars):i1])
            after = " ".join(ref_tokens[i2:min(len(ref_tokens), i2 + context_chars)])
        errors.append({"op": op, "n": n, "ref": ref_seg, "hyp": hyp_seg, "ctx_before": before, "ctx_after": after})
    return errors


# ── Discovery ────────────────────────────────────────────────────────────────

def find_ground_truths(stem: str, sandbox: Path) -> dict[str, Path]:
    base = Path(__file__).parent
    gts: dict[str, Path] = {}
    gt = sandbox / f"{stem}_GT.srt"
    if not gt.exists():
        gt = base / "GroundTrue" / f"{stem}_GT.srt"
    if gt.exists():
        gts["gt"] = gt
    yt = sandbox / f"{stem}_YT.srt"
    if not yt.exists():
        yt = base / "GroundTrue" / f"{stem}_YT.srt"
    if yt.exists():
        gts["yt"] = yt
    return gts


def find_stages(stem: str, sandbox: Path) -> dict[str, Path]:
    stages: dict[str, Path] = {}
    for p in sorted(sandbox.glob(f"{stem}_exp*.srt")):
        label = p.stem.replace(f"{stem}_", "")
        stages[label] = p
    for p in sorted(sandbox.glob(f"{stem}_FIN.srt")):
        stages["FIN"] = p
    for p in sorted(sandbox.glob(f"{stem}_fix.srt")):
        stages["fix"] = p
    for p in sorted(sandbox.glob(f"{stem}_merged.srt")):
        stages["merged"] = p
    return stages


# ── KPI helpers ──────────────────────────────────────────────────────────────

def _kpi(text: str, segments: list[str] | None = None) -> dict:
    display_chars = len(text.replace(" ", ""))
    clauses = len(segments) if segments is not None else 1
    avg_cl_len = display_chars / clauses if clauses else 0.0
    trad_pct = "N/A"
    return {"chars": display_chars, "trad_pct": trad_pct, "clauses": clauses, "avg_cl_len": avg_cl_len}


def _score_stage(chars: int, gt_chars: int, weighted_rate: float) -> float:
    return (1.0 - weighted_rate) * 80 + min(1.0, chars / gt_chars) * 10 + 10


def _status_table(stem: str, sandbox: Path) -> list[tuple[str, str, str]]:
    m = re.match(r"^(.*?)(?:_stage([012]))?$", stem)
    base = m.group(1) if m else stem
    rows = []
    for label, suffix in [("stage0", "_stage0"), ("stage1", "_stage1"), ("stage2", "_stage2"), ("full", "")]:
        report_name = f"{base}{suffix}_cer_report.md"
        exists = (sandbox / report_name).exists() or stem == f"{base}{suffix}"
        rows.append((label, "✅ Done" if exists else "⏳ Pending", report_name if exists else "—"))
    return rows


def _build_cross_stage_summary(stem: str, sandbox: Path) -> str:
    m = re.match(r"^(.*?)(?:_stage[012])?$", stem)
    base = m.group(1) if m else stem
    stems = [base, f"{base}_stage0", f"{base}_stage1", f"{base}_stage2"]
    stage_labels = {base: "full", f"{base}_stage0": "stage0", f"{base}_stage1": "stage1", f"{base}_stage2": "stage2"}
    available = {}
    for s in stems:
        gts = find_ground_truths(s, sandbox)
        stages = find_stages(s, sandbox)
        if not gts or not stages:
            continue
        gt_text = extract_text(gts["gt"] if "gt" in gts else next(iter(gts.values())))
        per_stage = {}
        for stage_name, path in stages.items():
            per_stage[stage_name] = _classify_errors(gt_text, extract_text(path))["weighted_rate"]
        available[s] = per_stage
    if len(available) < 2:
        return ""

    all_models = []
    for data in available.values():
        for model in data:
            if model not in all_models:
                all_models.append(model)

    lines = [f"\n---\n## Cross-Stage CER Summary — {base}\n", "**完整對比（所有 stage，verify_cer.py 官方數字）　格式： key (raw)**", "*（🟢 全域最佳；🔴 全域第二）*\n"]
    header = ["exp", "full", "stage0", "stage1", "stage2", "key avg"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|---|:---------:|:---------:|:---------:|:---------:|------:|")
    for model in all_models:
        vals = []
        cells = [model]
        for s in [base, f"{base}_stage0", f"{base}_stage1", f"{base}_stage2"]:
            v = available.get(s, {}).get(model)
            if v is None:
                cells.append("—")
            else:
                vals.append(v)
                cells.append(f"{v:.1%} ({v:.1%})")
        avg = sum(vals) / len(vals) if vals else 1.0
        cells.append(f"{avg:.1%}")
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


# ── Writers ──────────────────────────────────────────────────────────────────

def _write_key_detail(stem: str, sandbox: Path, gts: dict[str, Path], stages: dict[str, Path], results: dict[str, dict[str, dict]]) -> None:
    primary_mode = next(iter(next(iter(results.values())).values()))["mode"] if results else "CER"
    lines = [f"# Key {primary_mode} Detail — {stem}", "", "", "## Error Breakdown (sub/ins/del)", "", f"| Stage | GT | sub | ins | del | key_sub | key_ins | key_del | key_{primary_mode} |", "|-------|----|----:|----:|----:|--------:|--------:|--------:|--------:|"]
    for stage, gt_map in results.items():
        for gt_label, res in gt_map.items():
            lines.append(f"| {stage} | {gt_label} | {res['sub']} | {res['ins']} | {res['del']} | {res['key_sub']} | {res['key_ins']} | {res['key_del']} | {res['weighted_rate']:.1%} |")
    lines.extend(["", "---", ""])

    for gt_label, gt_path in gts.items():
        lines.extend(["", f"## GT: {gt_label}", ""])
        ref = extract_text(gt_path)
        mode = next(iter(results.values()))[gt_label]["mode"] if results and gt_label in next(iter(results.values())) else primary_mode
        for stage, path in stages.items():
            res = results[stage][gt_label]
            n_key = res["key_sub"] + res["key_ins"] + res["key_del"]
            lines.extend(["", f"### {stage}  (key_{mode}={res['weighted_rate']:.1%}, {n_key} key errors)", ""])
            errors = _get_key_error_details(ref, extract_text(path), mode)
            if not errors:
                lines.append("_No key errors._")
                lines.append("")
                continue
            lines.append("| # | Type | GT | Hyp | Context |")
            lines.append("|---|------|----|-----|---------|")
            for idx, err in enumerate(errors, 1):
                ref_disp = f"`{err['ref']}`" if err['ref'] else "—"
                hyp_disp = f"`{err['hyp']}`" if err['hyp'] else "—"
                ctx = f"{err['ctx_before']}**[{err['ref'] or '∅'}→{err['hyp'] or '∅'}]**{err['ctx_after']}"
                lines.append(f"| {idx} | {err['op']}×{err['n']} | {ref_disp} | {hyp_disp} | {ctx} |")
            lines.append("")
    (sandbox / f"{stem}_key_cer_detail.md").write_text("\n".join(lines), encoding="utf-8")


def _write_cer_report(stem: str, sandbox: Path, gts: dict[str, Path], stages: dict[str, Path], results: dict[str, dict[str, dict]]) -> None:
    primary_gt = "gt" if "gt" in gts else next(iter(gts))
    primary_mode = next(iter(results.values()))[primary_gt]["mode"] if results else "CER"
    gt_text = extract_text(gts[primary_gt])
    gt_chars = len(gt_text.replace(" ", ""))
    lines = ["# Close Loop Verification — CER per stage vs all ground truths", "", "| Key | Value |", "|-----|-------|", f"| **Now** | {_now_cst()} |", f"| Sandbox | `{sandbox}` |", f"| Stem | `{stem}` |", "", "### 📊 轉寫進度狀態 (Processing Status)", "| 階段 | 狀態 | 報告檔案 |", "|:---|:---:|:---|"]
    for label, status, report in _status_table(stem, sandbox):
        lines.append(f"| {label} | {status} | `{report}` |" if report != "—" else f"| {label} | {status} | — |")
    lines.append("")
    for gt_label, path in gts.items():
        lines.append(f"| GT/{gt_label} | `{path.name}` ({len(extract_text(path).replace(' ', ''))} chars) |")
    lines.extend(["", "### KPI 報告", "", "**評分說明 (Weights):**", "- **字數 (Coverage):** 45%~70% (以 GT 字數為上限，避免幻覺加分)", "- **繁體% (Traditional):** 20%~25%", f"- **{primary_mode} Accuracy:** 30% (當有 {primary_mode} 數據時)", "- **實句 (Substantial):** 5%~10%", "- *（🟢 評分最佳；🔴 評分第二）*", ""])

    headers = ["階段", "字數", "Δ", "繁體%", "分句", "均長", "RTF"] + [f"key_{primary_mode}/{gt_label}" for gt_label in gts.keys()] + ["評分"]
    lines.append("|" + "|".join(["------", "-----:", "--:", "------:", "-----:", "-----:", "----:"] + ["----------:"] * len(gts) + ["-----:"]) + "|")
    lines.append("| " + " | ".join(headers) + " |")

    stage_rows = []
    scores = []
    for stage, path in stages.items():
        text = extract_text(path)
        kpi = _kpi(text, extract_segments(path))
        primary_rate = results[stage][primary_gt]["weighted_rate"]
        score = _score_stage(kpi["chars"], gt_chars, primary_rate)
        scores.append(score)
        stage_rows.append((stage, path, kpi, score))
    unique_scores = sorted(set(scores), reverse=True)
    best = unique_scores[0] if unique_scores else -1
    second = unique_scores[1] if len(unique_scores) > 1 else None
    for stage, path, kpi, score in stage_rows:
        badge = " 🟢" if abs(score - best) < 0.1 else (" 🔴" if second is not None and abs(score - second) < 0.1 else "")
        row = [stage, str(kpi["chars"]), f"{kpi['chars'] - gt_chars:+d}", str(kpi["trad_pct"]), str(kpi["clauses"]), f"{kpi['avg_cl_len']:.1f}", extract_rtf(path)]
        for gt_label in gts.keys():
            row.append(f"{results[stage][gt_label]['weighted_rate']:.1%}")
        row.append(f"**{score:.1f}**{badge}")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("|------|-----:|--:|------:|-----:|-----:|------:|" + "|".join(["----:"] * len(gts)) + "|-----:|")
    gt_kpi = _kpi(gt_text, extract_segments(gts[primary_gt]))
    gt_row = [f"GT/{primary_gt}", str(gt_kpi["chars"]), "—", str(gt_kpi["trad_pct"]), str(gt_kpi["clauses"]), f"{gt_kpi['avg_cl_len']:.1f}", "—"]
    for _ in gts.keys():
        gt_row.append("—")
    gt_row.append("—")
    lines.append("| " + " | ".join(gt_row) + " |")
    detail_name = f"{stem}_key_cer_detail.md"
    lines.append(f"[key_cer_detail saved] {sandbox / detail_name}")
    lines.append("")
    lines.append(f"**詳細錯誤分析:** [查看 {detail_name}]({detail_name})")
    xsum = _build_cross_stage_summary(stem, sandbox)
    if xsum:
        lines.append("")
        lines.append(xsum)
    (sandbox / f"{stem}_cer_report.md").write_text("\n".join(lines), encoding="utf-8")


# ── Leaderboard ──────────────────────────────────────────────────────────────

def _build_cross_stem_summary(all_data: dict, requested_stems: list[str]) -> str:
    buf = io.StringIO()
    buf.write("\n---\n# 全域效能排行榜 (Global Performance Leaderboard)\n\n")
    buf.write(f"| Key | Value |\n|:---|:---|\n| **Generated Now** | {_now_cst()} |\n| **執行樣本數** | {len(all_data)} / {len(requested_stems)} |\n\n")

    def get_stage_info(stem_name: str) -> tuple[str, str]:
        m = re.search(r"(_stage(\d+))$", stem_name)
        if m:
            return m.group(2), stem_name.replace(m.group(1), "")
        return "full", stem_name

    buf.write("## 樣本品質總覽 (Sample Quality Overview)\n\n*規則: Best Avg <= 8% 為 OK，否則為 NG。每格格式為 `BestExp / FIN`。*\n\n")
    overview = {}
    for stem_name, data in all_data.items():
        stage_id, base = get_stage_info(stem_name)
        rates = data["rates"]
        exp_rates = {model: value for model, value in rates.items() if re.fullmatch(r"exp\d+", model)}
        best_model = min(exp_rates, key=exp_rates.get) if exp_rates else None
        best_rate = exp_rates[best_model] if best_model else None
        fin_rate = rates.get("FIN")
        overview.setdefault(base, {})[stage_id] = {
            "best_model": best_model,
            "best_rate": best_rate,
            "fin_rate": fin_rate,
        }

    stage_order = ["0", "1", "2", "full"]
    labels = {"0": "stage0", "1": "stage1", "2": "stage2", "full": "full"}
    buf.write("| 樣本 | " + " | ".join(labels[s] for s in stage_order) + " | Best Avg | Best 達標 | FIN Avg | FIN 達標 |\n")
    buf.write("|:---|" + "|".join([":---:" for _ in stage_order]) + "|---:|:---:|---:|:---:|\n")
    for base in sorted(overview):
        best_vals = []
        fin_vals = []
        cells = []
        for sid in stage_order:
            row = overview[base].get(sid)
            if not row:
                cells.append("—")
                continue
            best_rate = row["best_rate"]
            fin_rate = row["fin_rate"]
            if best_rate is not None:
                best_vals.append(best_rate)
            if fin_rate is not None:
                fin_vals.append(fin_rate)
            best_disp = f"{row['best_model']} {best_rate:.1%}" if row["best_model"] and best_rate is not None else "—"
            fin_disp = f"FIN {fin_rate:.1%}" if fin_rate is not None else "—"
            cells.append(f"{best_disp} / {fin_disp}")
        best_avg = (sum(best_vals) / len(best_vals)) if best_vals else None
        fin_avg = (sum(fin_vals) / len(fin_vals)) if fin_vals else None
        best_avg_s = f"{best_avg:.1%}" if best_avg is not None else "—"
        fin_avg_s = f"{fin_avg:.1%}" if fin_avg is not None else "—"
        best_status = "OK" if best_avg is not None and best_avg <= 0.08 else "NG"
        fin_status = "OK" if fin_avg is not None and fin_avg <= 0.08 else "NG"
        buf.write(f"| {base} | " + " | ".join(cells) + f" | {best_avg_s} | {best_status} | {fin_avg_s} | {fin_status} |\n")

    def render_win_table(data_subset: dict, title: str):
        if not data_subset:
            return
        stats = {}
        for _, data in data_subset.items():
            rates = data["rates"]
            best = min(rates.values())
            for model, value in rates.items():
                stats.setdefault(model, {"wins": 0, "vals": [], "count": 0})
                stats[model]["vals"].append(value)
                stats[model]["count"] += 1
                if abs(value - best) < 1e-6:
                    stats[model]["wins"] += 1
        ranking = []
        for model, s in stats.items():
            ranking.append({"model": model, "wins": s["wins"], "avg": sum(s["vals"]) / len(s["vals"]), "count": s["count"], "wr": s["wins"] / len(data_subset)})
        ranking.sort(key=lambda x: (-x["wins"], x["avg"]))
        buf.write(f"\n### {title}\n\n| 模型 (Model) | 🥇 1st | 🥇 勝率 | 平均 Error | 樣本 |\n|:---|---:|---:|---:|---:|\n")
        for r in ranking[:10]:
            buf.write(f"| {r['model']} | {r['wins']} | {r['wr']:.1%} | {r['avg']:.1%} | {r['count']} |\n")

    render_win_table(all_data, "🏆 總合排行榜 (Overall - All Stages)")
    by_stage = {}
    for stem_name, data in all_data.items():
        sid, _ = get_stage_info(stem_name)
        by_stage.setdefault(sid, {})[stem_name] = data
    stage_titles = {"0": "📍 Intro (開場)", "1": "📍 Presentation (簡報)", "2": "📍 Q&A (問答)", "full": "📍 🥇 Full Stream (全量轉錄戰報)"}
    for sid in ["0", "1", "2", "full"]:
        if sid in by_stage:
            render_win_table(by_stage[sid], stage_titles[sid])
    return buf.getvalue()


# ── Main ─────────────────────────────────────────────────────────────────────

def verify_stem(stem: str, sandbox: Path) -> dict:
    gts = find_ground_truths(stem, sandbox)
    stages = find_stages(stem, sandbox)
    if not gts or not stages:
        return {}

    report_path = sandbox / f"{stem}_cer_report.md"
    if report_path.exists():
        content = report_path.read_text(encoding="utf-8")
        # Extract report timestamp: | **Now** | 2026-04-15 07:57 CST |
        m_now = re.search(r"\|\s*\*\*Now\*\*\s*\|\s*([\d-]+ [\d:]+)\s*CST\s*\|", content)
        if m_now:
            try:
                # Parse as naive datetime then attach TZ_CST
                dt_report = datetime.datetime.strptime(m_now.group(1), "%Y-%m-%d %H:%M")
                report_timestamp = dt_report.replace(tzinfo=TZ_CST).timestamp()
                
                # Get the latest modification time from all source files (GT and experiments)
                src_files = list(gts.values()) + list(stages.values())
                latest_src_timestamp = max(p.stat().st_mtime for p in src_files)
                
                # If report is newer than all sources, skip re-calculation
                if report_timestamp > latest_src_timestamp:
                    print(f"Skipping recalculation for {stem} (content timestamp is up-to-date)")
                    rates = {}
                    # Parse existing rates from report table
                    for line in content.splitlines():
                        if line.startswith("|") and not any(x in line for x in ["階段", "---", "GT/", "Now", "Sandbox", "Stem"]):
                            parts = [p.strip() for p in line.split("|")]
                            if len(parts) >= 9:
                                label = parts[1]
                                m_pct = re.search(r"([\d.]+)%", line)
                                if m_pct:
                                    rates[label] = float(m_pct.group(1)) / 100.0
                    
                    m_mode = re.search(r"key_(CER|WER)", content)
                    mode = m_mode.group(1) if m_mode else "CER"
                    if rates:
                        return {"rates": rates, "mode": mode}
            except Exception as e:
                print(f"Warning: Failed to parse timestamp or rates for {stem}: {e}")

    print(f"Calculating CER for {stem}...")
    gt_texts = {label: extract_text(path) for label, path in gts.items()}
    results: dict[str, dict[str, dict]] = {}
    for stage, path in stages.items():
        hyp = extract_text(path)
        if not hyp:
            continue
        results[stage] = {}
        for gt_label, ref in gt_texts.items():
            results[stage][gt_label] = _classify_errors(ref, hyp)
    _write_key_detail(stem, sandbox, gts, stages, results)
    _write_cer_report(stem, sandbox, gts, stages, results)
    primary_gt = "gt" if "gt" in gts else next(iter(gts))
    primary_rates = {stage: data[primary_gt]["weighted_rate"] for stage, data in results.items()}
    primary_mode = next(iter(results.values()))[primary_gt]["mode"]
    return {"rates": primary_rates, "mode": primary_mode}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stems", nargs="+")
    parser.add_argument("--sandbox", default="whisper-sandbox")
    args = parser.parse_args()
    sandbox = Path(__file__).parent / args.sandbox
    stems = args.stems
    if stems == ["all"]:
        stems = sorted([p.name.replace("_cer_report.md", "") for p in sandbox.glob("*_cer_report.md")])
    
    all_results = {}
    for stem in stems:
        data = verify_stem(stem, sandbox)
        if data:
            all_results[stem] = data
    
    if all_results:
        leaderboard_data = {stem: {"rates": data["rates"], "mode": data["mode"]} for stem, data in all_results.items()}
        (sandbox / "cross_stem_cer_leaderboard.md").write_text(_build_cross_stem_summary(leaderboard_data, stems), encoding="utf-8")
        print(f"Successfully updated cross_stem_cer_leaderboard.md with {len(all_results)} stems.")


if __name__ == "__main__":
    main()
