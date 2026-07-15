#!/usr/bin/env python3
"""lint_sources.py — 法說會資料完整性檢查 (skill-investorconference-digest)

對指定公司/季度（或全庫）的資料來源執行機械性完整性檢查，
產出問題清單與可直接貼入 GitHub Issue 的 Markdown 表格草稿。
語意類錯誤（人名、術語、幻覺句）仍需 LLM 判讀，本腳本負責可自動化的部分。

檢查項目:
  [SRT]  時間戳格式、秒數 >= 60、時間戳倒退、空白字幕行、
         FIN 檔缺 [METADATA] 區塊、GT 檔 metadata/review level、字幕總長 vs audio_durations.json 音檔長度
  [Audio] audio_metadata.json duplicate/invalid 音檔錯配檢查
  [QA]   `webcast MM:SS` 引用時間戳無效（秒數 >= 60）或超出字幕總長
  [IR]   含財務關鍵字的頁面 OCR 數字遺失（疑似空頁）
  [檔案] 缺 GT 校正字幕、缺中文簡報 MD、缺 QA 檔

用法:
    python lint_sources.py 2357                     # 該公司全部季度
    python lint_sources.py 2357 2026 q1             # 指定季度
    python lint_sources.py --all                    # 全庫掃描
    python lint_sources.py 2357 --issue-draft out.md --issue-json out.json
"""
import argparse
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

QUARTER_RE = re.compile(r"^(?P<sid>[0-9A-Za-z]+)_(?P<year>\d{4})_q(?P<q>[1-4])")
SRT_LINE_RE = re.compile(r"^\((\d+):(\d{2})\.(\d{3})\)\s*(.*)$")
QA_TS_RE = re.compile(r"webcast\s+(\d+)[:：](\d+)", re.IGNORECASE)
IR_FIN_KEYWORDS = ("損益", "資產負債", "營收組合", "營運展望", "Revenue Mix", "Balance Sheet")
DURATION_TOLERANCE = 0.10  # 字幕總長與音檔長度差異容忍度


class Finding:
    def __init__(self, severity, file, location, problem, suggestion="", issue_type="data_quality"):
        self.severity = severity  # ERROR / WARN / INFO
        self.file = file
        self.location = location
        self.problem = problem
        self.suggestion = suggestion
        self.issue_type = issue_type

    @property
    def issue_severity(self):
        return {"ERROR": "blocker", "WARN": "major", "INFO": "minor"}.get(self.severity, "minor")

    def as_issue(self):
        return {
            "severity": self.issue_severity,
            "file": self.file,
            "location": self.location,
            "type": self.issue_type,
            "description": self.problem,
            "suggestion": self.suggestion,
        }


def find_repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "audio_durations.json").exists():
            return p
    return start


def load_audio_durations(root: Path) -> dict:
    f = root / "audio_durations.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}



def load_audio_metadata(root: Path) -> dict:
    f = root / "audio_metadata.json"
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            pass
    return {}


def check_audio_metadata(base: str, metadata: dict):
    findings = []
    item = metadata.get(base)
    if not isinstance(item, dict):
        return findings
    status = str(item.get("status", "ok"))
    duplicate_of = item.get("duplicate_of")
    if status in {"duplicate", "invalid"}:
        suggestion = "重新取得正確季度音檔；GT/digest 前不可把 FIN 當成本季音訊證據"
        if duplicate_of:
            suggestion += f"；目前標示 duplicate_of={duplicate_of}"
        findings.append(Finding(
            "ERROR", f"{base}.m4a", "audio_metadata.json",
            f"音檔 metadata 狀態為 {status}，疑似季度音訊錯配",
            suggestion, "audio_mismatch"))
    sha = str(item.get("sha256", "")).lower()
    if sha:
        same = sorted(
            stem for stem, other in metadata.items()
            if stem != base and isinstance(other, dict) and str(other.get("sha256", "")).lower() == sha
        )
        if same and status not in {"duplicate", "invalid"}:
            findings.append(Finding(
                "WARN", f"{base}.m4a", "audio_metadata.json",
                f"音檔 sha256 與其他 stem 相同: {', '.join(same)}",
                "確認是否為同一場法說會被錯掛；必要時標示 duplicate_of 或移除錯誤 release asset",
                "audio_mismatch"))
    return findings


GT_REQUIRED_METADATA = (
    "Source",
    "Review-Level",
    "Reviewer",
    "Reviewed-At",
    "Audio-Checked",
    "Correction-Sources",
    "Corrections",
    "Confidence",
)
GT_REVIEW_LEVELS = {"human_verified", "partial_audio_checked", "conservative_from_FIN"}
GT_AUDIO_CHECKED = {"full", "sampled", "none"}
GT_CONFIDENCE = {"high", "medium", "low"}


def read_metadata(lines: list[str]) -> dict[str, str]:
    meta = {}
    if not lines or lines[0].strip() != "[METADATA]":
        return meta
    for line in lines[1:]:
        line = line.strip()
        if line == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta


def check_gt_metadata(path: Path, lines: list[str]):
    findings = []
    rel = path.name
    meta = read_metadata(lines)
    if not meta:
        findings.append(Finding(
            "WARN", rel, "檔首",
            "GT 檔缺 [METADATA] 區塊，無法判定 review level",
            "依 digest SOP 補上 Source/Review-Level/Audio-Checked/Correction-Sources 等欄位"))
        return findings

    missing = [k for k in GT_REQUIRED_METADATA if not meta.get(k)]
    if missing:
        findings.append(Finding(
            "WARN", rel, "檔首",
            f"GT metadata 缺必要欄位: {', '.join(missing)}",
            "依 digest SOP 補齊 GT metadata"))

    level = meta.get("Review-Level", "")
    if level and level not in GT_REVIEW_LEVELS:
        findings.append(Finding(
            "WARN", rel, "Review-Level",
            f"GT Review-Level 不合法: {level}",
            "限用 human_verified / partial_audio_checked / conservative_from_FIN"))

    audio_checked = meta.get("Audio-Checked", "")
    if audio_checked and audio_checked not in GT_AUDIO_CHECKED:
        findings.append(Finding(
            "WARN", rel, "Audio-Checked",
            f"GT Audio-Checked 不合法: {audio_checked}",
            "限用 full / sampled / none"))

    confidence = meta.get("Confidence", "")
    if confidence and confidence not in GT_CONFIDENCE:
        findings.append(Finding(
            "WARN", rel, "Confidence",
            f"GT Confidence 不合法: {confidence}",
            "限用 high / medium / low"))

    if level == "human_verified" and audio_checked == "none":
        findings.append(Finding(
            "ERROR", rel, "metadata",
            "Review-Level 為 human_verified 但 Audio-Checked 為 none",
            "改為 partial_audio_checked/conservative_from_FIN，或補做音訊校對"))

    if level == "conservative_from_FIN":
        findings.append(Finding(
            "INFO", rel, "Review-Level",
            "GT 為 conservative_from_FIN，屬 GT-candidate，非完整人工校正版",
            "Digest 可使用但重大結論需交叉驗證；後續可補音訊校對"))

    return findings


def parse_srt(path: Path):
    """回傳 (findings, last_seconds)。"""
    findings = []
    rel = path.name
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    has_metadata = any(l.strip() == "[METADATA]" for l in lines[:5])
    if path.name.endswith("_FIN.srt") and not has_metadata:
        findings.append(Finding("INFO", rel, "檔首", "FIN 檔缺 [METADATA] 區塊", "補上 Source/Language"))
    if path.name.endswith("_GT.srt"):
        findings += check_gt_metadata(path, lines)

    prev = -1.0
    last = 0.0
    n_ts = 0
    for i, line in enumerate(lines, 1):
        m = SRT_LINE_RE.match(line.strip())
        if not m:
            continue
        n_ts += 1
        mm, ss, ms, body = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
        if ss >= 60:
            findings.append(Finding("ERROR", rel, f"第{i}行 ({m.group(1)}:{m.group(2)})",
                                    f"時間戳秒數無效 ({ss} >= 60)", "確認正確時間"))
            continue
        t = mm * 60 + ss + ms / 1000.0
        if t < prev - 0.5:
            findings.append(Finding("WARN", rel, f"第{i}行 ({m.group(1)}:{m.group(2)})",
                                    "時間戳倒退（順序異常）", "檢查轉錄切分"))
        prev = max(prev, t)
        last = max(last, t)
        if not body.strip():
            findings.append(Finding("INFO", rel, f"第{i}行", "時間戳後無字幕內容", "確認是否漏字"))
    if n_ts == 0:
        findings.append(Finding("ERROR", rel, "全檔", "解析不到任何 (MM:SS.mmm) 時間戳", "確認檔案格式"))
    return findings, last


def check_srt_vs_audio(srt_name: str, srt_end: float, sid: str, year: int, q: int,
                       durations: dict):
    findings = []
    keys = [k for k in durations if k.startswith(f"data/{sid}/{sid}_{year}_q{q}.")]
    if not keys or srt_end <= 0:
        return findings
    audio = float(durations[keys[0]])
    diff = abs(audio - srt_end) / audio
    if diff > DURATION_TOLERANCE:
        findings.append(Finding(
            "WARN", srt_name, f"字幕迄 {srt_end/60:.1f} 分 vs 音檔 {audio/60:.1f} 分",
            f"字幕總長與音檔長度差異 {diff:.0%}（可能轉錄不完整或音檔不符）",
            "重新轉錄或確認音檔對應"))
    return findings


def check_qa(path: Path, srt_end: float):
    findings = []
    rel = path.name
    text = path.read_text(encoding="utf-8", errors="replace")
    for m in QA_TS_RE.finditer(text):
        mm, ss = int(m.group(1)), int(m.group(2))
        loc = f"webcast {m.group(1)}:{m.group(2)}"
        if ss >= 60:
            findings.append(Finding("ERROR", rel, loc, f"引用時間戳無效（秒數 {ss} >= 60）",
                                    "確認正確時間點"))
            continue
        t = mm * 60 + ss
        if srt_end > 0 and t > srt_end + 60:
            findings.append(Finding("WARN", rel, loc,
                                    f"引用時間點超出字幕總長 ({srt_end/60:.1f} 分)",
                                    "確認引用或字幕完整性"))
    return findings


def check_ir(path: Path):
    findings = []
    rel = path.name
    text = path.read_text(encoding="utf-8", errors="replace")
    pages = re.split(r"^## Page (\d+)\s*$", text, flags=re.MULTILINE)
    # pages: [前置, 頁碼, 內容, 頁碼, 內容, ...]
    for idx in range(1, len(pages) - 1, 2):
        page_no, content = pages[idx], pages[idx + 1]
        if not any(kw in content for kw in IR_FIN_KEYWORDS):
            continue
        digit_chars = sum(c.isdigit() for c in content)
        if digit_chars < 8:
            kw = next(k for k in IR_FIN_KEYWORDS if k in content)
            findings.append(Finding(
                "ERROR", rel, f"Page {page_no}",
                f"含財務關鍵字「{kw}」但數字幾乎全部遺失（疑似 OCR 空頁）",
                "重跑 OCR 或人工補數字（比照 2357_2026_q1_ir.md Page 8 補萃取區塊）"))
    return findings


def lint_quarter(root: Path, sid: str, year: int, q: int, durations: dict, audio_metadata: dict):
    company = root / "data" / sid
    base = f"{sid}_{year}_q{q}"
    findings = []
    findings += check_audio_metadata(base, audio_metadata)

    gt = company / f"{base}_GT.srt"
    fin = company / f"{base}_FIN.srt"
    is_us = not sid.isdigit()
    ir = company / f"{base}_ir.md"
    us_report = company / f"{base}_report_en.md"
    us_tables = company / f"{base}_financial_tables.md"
    us_review = company / f"{base}_performance_review.md"
    qa = company / f"{base}_qa.md"

    srt_end = 0.0
    if gt.exists():
        f, srt_end = parse_srt(gt)
        findings += f
        findings += check_srt_vs_audio(gt.name, srt_end, sid, year, q, durations)
    if fin.exists():
        f, fin_end = parse_srt(fin)
        findings += f
        findings += check_srt_vs_audio(fin.name, fin_end, sid, year, q, durations)
        srt_end = max(srt_end, fin_end)
    if not gt.exists() and fin.exists():
        findings.append(Finding("WARN", f"{base}_GT.srt", "—",
                                "缺人工校正字幕（僅有 FIN Whisper 版）", "建議補做 GT"))
    if not gt.exists() and not fin.exists():
        findings.append(Finding("WARN", f"{base}_*.srt", "—", "本季無任何字幕檔", "確認是否有音檔可轉錄"))

    if is_us:
        company_docs = [p for p in (us_report, us_tables, us_review, company / f"{base}_ir_en.md") if p.exists()]
        if not company_docs:
            findings.append(Finding("WARN", f"{base}_report_en.md", "—",
                                    "缺美股公司正式財務文件（earnings release/report、financial tables 或 performance review）",
                                    "用 ingest 補抓公司文件；digest 不應只依 FIN 產出財務結論"))
    else:
        if ir.exists():
            findings += check_ir(ir)
        else:
            findings.append(Finding("INFO", ir.name, "—", "缺中文簡報 MD", "確認 PDF 是否已轉檔"))

    if qa.exists():
        findings += check_qa(qa, srt_end)
    return findings


def list_company_quarters(root: Path, sid: str):
    company = root / "data" / sid
    quarters = set()
    if company.is_dir():
        for f in company.iterdir():
            m = QUARTER_RE.match(f.name)
            if m and m.group("sid") == sid:
                quarters.add((int(m.group("year")), int(m.group("q"))))
    return sorted(quarters)


def all_companies(root: Path):
    return sorted(d.name for d in (root / "data").iterdir()
                  if d.is_dir() and re.fullmatch(r"[0-9A-Z]{2,6}", d.name)
                  and any(QUARTER_RE.match(f.name) for f in d.iterdir()))


def issue_table(findings):
    lines = ["## 資料品質問題彙整（lint_sources.py 自動檢出）", "",
             "| 嚴重度 | 檔案 | 位置 | 問題 | 建議修正 |", "|---|---|---|---|---|"]
    for f in findings:
        lines.append(f"| {f.issue_severity} | `{f.file}` | {f.location} | {f.problem} | {f.suggestion} |")
    lines += ["", "_機械性檢查結果；人名/術語/幻覺句等語意類錯誤需另行人工或 LLM 判讀。_"]
    return "\n".join(lines)


def issue_json_payload(stock_id, year, quarter, findings):
    q = str(quarter).lower().lstrip("q")
    return {
        "stock_id": stock_id or "all",
        "quarter": f"{year}_q{q}" if year and quarter else None,
        "issues": [f.as_issue() for f in findings],
    }


def main():
    ap = argparse.ArgumentParser(description="法說會資料完整性檢查")
    ap.add_argument("stock_id", nargs="?")
    ap.add_argument("year", nargs="?", type=int)
    ap.add_argument("quarter", nargs="?")
    ap.add_argument("--all", action="store_true", help="掃描全庫所有公司")
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument("--issue-draft", type=Path, help="輸出 Issue Markdown 草稿到指定檔案")
    ap.add_argument("--issue-json", type=Path, help="輸出 machine-readable issue sidecar JSON")
    args = ap.parse_args()

    root = (args.root or find_repo_root(Path.cwd())).resolve()
    durations = load_audio_durations(root)
    audio_metadata = load_audio_metadata(root)

    targets = []  # (sid, year, q)
    if args.all:
        for sid in all_companies(root):
            targets += [(sid, y, q) for y, q in list_company_quarters(root, sid)]
    elif args.stock_id and args.year and args.quarter:
        targets = [(args.stock_id, args.year, int(str(args.quarter).lstrip("qQ")))]
    elif args.stock_id:
        targets = [(args.stock_id, y, q) for y, q in list_company_quarters(root, args.stock_id)]
    else:
        ap.error("請指定 stock_id 或 --all")

    all_findings = []
    for sid, year, q in targets:
        fs = lint_quarter(root, sid, year, q, durations, audio_metadata)
        if fs:
            print(f"\n== {sid} {year} Q{q}: {len(fs)} 項 ==")
            for f in sorted(fs, key=lambda x: ("ERROR", "WARN", "INFO").index(x.severity)):
                print(f"  [{f.severity}] {f.file} @ {f.location}")
                print(f"        {f.problem}" + (f"｜建議: {f.suggestion}" if f.suggestion else ""))
        all_findings += fs

    n_err = sum(1 for f in all_findings if f.severity == "ERROR")
    n_warn = sum(1 for f in all_findings if f.severity == "WARN")
    print(f"\n合計: {len(all_findings)} 項（ERROR {n_err} / WARN {n_warn} / "
          f"INFO {len(all_findings) - n_err - n_warn}）")

    if args.issue_draft and all_findings:
        args.issue_draft.write_text(issue_table(all_findings), encoding="utf-8")
        print(f"Issue 草稿已寫入: {args.issue_draft}")

    if args.issue_json and all_findings:
        payload = issue_json_payload(args.stock_id, args.year, args.quarter, all_findings)
        args.issue_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Issue JSON 已寫入: {args.issue_json}")

    sys.exit(1 if n_err else 0)


if __name__ == "__main__":
    main()
