#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_skills_index.py — 產生技能索引 YAML 與 README 技能總表

掃描各 LLM 群組資料夾（common/、codex/、claude/ …）底下的
<skill-name>/metadata.json，彙整為：

1. skills-index.yaml     — 機器可讀索引（名稱、版本、修訂日期等）
2. README.md 技能總表   — 取代 SKILLS-TABLE 標記之間的內容

修訂日期（revised_at）取該技能資料夾在 git 中的最後 commit 日期；
若無法取得 git 資訊，退回使用檔案系統的最後修改日期。

使用方式（在 repo 根目錄執行）：

    python scripts/generate_skills_index.py
"""
import datetime
import json
import platform
import subprocess
import sys
from pathlib import Path

import yaml

if platform.system() == "Windows":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = REPO_ROOT / "skills-index.yaml"
README_FILE = REPO_ROOT / "README.md"
TABLE_START = "<!-- SKILLS-TABLE:START -->"
TABLE_END = "<!-- SKILLS-TABLE:END -->"

# 不視為 LLM 群組的頂層資料夾
EXCLUDED_DIRS = {".git", ".github", "scripts"}


def _git_last_commit_date(path: Path) -> str | None:
    """回傳指定路徑在 git 中的最後 commit 日期（YYYY-MM-DD）。"""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", str(path.relative_to(REPO_ROOT))],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        date = result.stdout.strip()
        return date or None
    except Exception:
        return None


def _mtime_date(path: Path) -> str:
    """回傳資料夾內所有檔案的最新修改日期（YYYY-MM-DD）。"""
    mtimes = [p.stat().st_mtime for p in path.rglob("*") if p.is_file()]
    latest = max(mtimes) if mtimes else path.stat().st_mtime
    return datetime.date.fromtimestamp(latest).isoformat()


def collect_skills() -> list[dict]:
    skills = []
    for group_dir in sorted(REPO_ROOT.iterdir()):
        if not group_dir.is_dir() or group_dir.name in EXCLUDED_DIRS:
            continue
        for skill_dir in sorted(group_dir.iterdir()):
            meta_path = skill_dir / "metadata.json"
            if not meta_path.is_file():
                continue
            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception as e:
                print(f"[index] 略過 {meta_path}（metadata.json 解析失敗：{e}）", file=sys.stderr)
                continue
            skills.append({
                "name": skill_dir.name,
                "group": group_dir.name,
                "path": f"{group_dir.name}/{skill_dir.name}",
                "version": meta.get("version", "0.0.0"),
                "description": meta.get("description", ""),
                "maintainer": meta.get("maintainer", ""),
                "source": meta.get("source", ""),
                "updated_at": meta.get("updated_at", ""),
                "revised_at": _git_last_commit_date(skill_dir) or _mtime_date(skill_dir),
            })
    return skills


def write_index(skills: list[dict]) -> None:
    index = {
        "generated_at": datetime.date.today().isoformat(),
        "skills": skills,
    }
    header = "# 本檔案由 scripts/generate_skills_index.py 自動產生，請勿手動編輯。\n"
    body = yaml.safe_dump(index, allow_unicode=True, sort_keys=False, default_flow_style=False)
    INDEX_FILE.write_text(header + body, encoding="utf-8")
    print(f"[index] 已寫入 {INDEX_FILE.name}（{len(skills)} 個技能）")


def render_table(skills: list[dict]) -> str:
    lines = [
        "| 技能 | 群組 | 版本 | 說明 | 修訂日期 |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for s in skills:
        desc = s["description"].replace("|", "\\|")
        lines.append(
            f"| [{s['name']}]({s['path']}) | {s['group']} | {s['version']} | {desc} | {s['revised_at']} |"
        )
    return "\n".join(lines)


def update_readme(skills: list[dict]) -> None:
    content = README_FILE.read_text(encoding="utf-8")
    if TABLE_START not in content or TABLE_END not in content:
        print(f"[index] README.md 缺少 {TABLE_START} / {TABLE_END} 標記，未更新表格", file=sys.stderr)
        return
    before = content.split(TABLE_START)[0]
    after = content.split(TABLE_END)[1]
    generated = datetime.date.today().isoformat()
    new_section = (
        f"{TABLE_START}\n"
        f"{render_table(skills)}\n\n"
        f"最後產生日期：{generated}\n"
        f"{TABLE_END}"
    )
    README_FILE.write_text(before + new_section + after, encoding="utf-8")
    print("[index] 已更新 README.md 技能總表")


if __name__ == "__main__":
    all_skills = collect_skills()
    write_index(all_skills)
    update_readme(all_skills)
