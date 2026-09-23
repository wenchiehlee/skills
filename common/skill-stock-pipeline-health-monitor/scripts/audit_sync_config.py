"""
audit_sync_config.py
---------------------
Composite-skill helper for skill-stock-pipeline-health-monitor.

Cross-checks docs/data_sync_table.md against the actual repo-file-sync-action
YAML files living in each sibling source repo (../<source_repo>/<yaml>), so the
"跨 Repo CSV 同步" documentation does not silently drift from what the workflows
actually sync. Read-only: never edits another repo's files.
"""

import csv
import os
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
SIBLING_ROOT = ROOT.parent
DATA_SYNC_TABLE_MD = ROOT / "docs" / "data_sync_table.md"

sys.path.insert(0, str(ROOT / "scripts"))
from generate_sync_table import parse_sync_config  # noqa: E402


ROW_RE = re.compile(
    r"^\|\s*\*{0,2}(?P<source_repo>[^|*]+?)\*{0,2}\s*\|\s*\*{0,2}(?P<source_file>[^|]+?)\*{0,2}\s*\|"
    r"\s*\*{0,2}(?P<dest>[^|]+?)\*{0,2}\s*\|\s*\*{0,2}(?P<definition>[^|]+?)\*{0,2}\s*\|"
    r"\s*\*{0,2}(?P<target_repo>[^|]+?)\*{0,2}\s*\|\s*`(?P<yaml>[^`]+)`\s*\|$"
)


def clean(value):
    return value.strip().strip("`").strip()


def parse_data_sync_table():
    if not DATA_SYNC_TABLE_MD.exists():
        print(f"找不到 {DATA_SYNC_TABLE_MD}")
        return []

    rows = []
    for line in DATA_SYNC_TABLE_MD.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        m = ROW_RE.match(line.strip())
        if not m:
            continue
        source_repo = clean(m.group("source_repo"))
        if source_repo in ("來源 Repo", "---"):
            continue
        rows.append({
            "source_repo": source_repo,
            "source_file": clean(m.group("source_file")),
            "dest": clean(m.group("dest")),
            "target_repo": clean(m.group("target_repo")),
            "yaml": clean(m.group("yaml")),
        })
    return rows


def collect_yaml_entries(yaml_path):
    parsed = parse_sync_config(yaml_path)
    sources = set()
    for group in parsed.get("group", []):
        for f in group.get("files", []):
            src = f.get("source")
            if src:
                sources.add(src.rsplit("/", 1)[-1])
                sources.add(src)
    return sources


def main():
    rows = parse_data_sync_table()
    if not rows:
        return 1

    by_yaml = {}
    for row in rows:
        key = (row["source_repo"], row["yaml"])
        by_yaml.setdefault(key, []).append(row)

    missing_yaml = []
    mismatched = []
    checked = 0

    for (source_repo, yaml_name), doc_rows in sorted(by_yaml.items()):
        yaml_path = SIBLING_ROOT / source_repo / yaml_name
        if not yaml_path.exists():
            missing_yaml.append((source_repo, yaml_name, len(doc_rows)))
            continue

        checked += 1
        try:
            yaml_sources = collect_yaml_entries(yaml_path)
        except Exception as exc:  # noqa: BLE001
            missing_yaml.append((source_repo, yaml_name, f"讀取失敗：{exc}"))
            continue

        for row in doc_rows:
            source_file = row["source_file"]
            basename = source_file.rsplit("/", 1)[-1]
            if source_file not in yaml_sources and basename not in yaml_sources:
                mismatched.append((source_repo, yaml_name, source_file, row["target_repo"]))

    print(f"=== 跨 Repo CSV 同步 YAML 稽核（docs/data_sync_table.md，{len(rows)} 列，{len(by_yaml)} 個 YAML） ===")
    print(f"本機可讀取並比對的 YAML：{checked}/{len(by_yaml)}")

    if missing_yaml:
        print("\n[MISSING] 文件提到但本機找不到的 YAML（可能是 sibling repo 未同層、或 workflow 已刪除）：")
        for source_repo, yaml_name, note in missing_yaml:
            print(f"  - {source_repo}/{yaml_name}（文件內 {note} 列涉及此 YAML）" if isinstance(note, int)
                  else f"  - {source_repo}/{yaml_name}（{note}）")

    if mismatched:
        print("\n[STALE-DOC] YAML 存在，但文件列的來源檔案不在該 YAML 的 files 清單中（文件可能過期）：")
        for source_repo, yaml_name, source_file, target_repo in mismatched:
            print(f"  - {source_repo}/{yaml_name}: {source_file} -> {target_repo}")

    if not missing_yaml and not mismatched:
        print("\n文件與本機可讀取到的 YAML 設定一致。")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
