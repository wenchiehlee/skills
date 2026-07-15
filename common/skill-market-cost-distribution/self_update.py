#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
self_update.py — market-cost-distribution 技能自我更新工具

以 skills 登錄庫（wenchiehlee/skills）作為唯一可信來源，
比較本地 metadata.json 與登錄庫中 common/skill-market-cost-distribution 的版本，
若登錄庫版本較新，則下載並覆寫本地技能檔案。

使用方式（在技能資料夾內執行）：

    python self_update.py

注意：
- 部署後的資料夾名稱可能不含 skill- 前綴，
  因此遠端子路徑採用固定值，而非由資料夾名稱推導。
- 僅在遠端版本嚴格大於本地版本時才會覆寫檔案。
"""
import json
import platform
import sys
import urllib.request
from pathlib import Path

# Fix Windows console encoding for Chinese characters
if platform.system() == "Windows":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

REMOTE_REPO = "wenchiehlee/skills"
SKILL_SUBPATH = "common/skill-market-cost-distribution"

# 登錄庫中此技能的全部檔案（新增檔案時需同步維護此清單）
FILES = [
    "SKILL.md",
    "metadata.json",
    "README.md",
    "self_update.py",
    "scripts/run_market_cost.py",
    "scripts/data_loader.py",
    "scripts/simulator.py",
    "scripts/metrics.py",
    "scripts/visualizer.py",
]


def _remote_url(relative_path: str) -> str:
    return f"https://raw.githubusercontent.com/{REMOTE_REPO}/main/{SKILL_SUBPATH}/{relative_path}"


def _fetch(relative_path: str) -> bytes:
    with urllib.request.urlopen(_remote_url(relative_path), timeout=30) as resp:
        return resp.read()


def _parse_version(version: str) -> tuple:
    try:
        return tuple(int(part) for part in version.strip().split("."))
    except Exception:
        return (0, 0, 0)


def _local_version(base_dir: Path) -> str:
    meta_path = base_dir / "metadata.json"
    try:
        with open(meta_path, encoding="utf-8") as f:
            return json.load(f).get("version", "0.0.0")
    except Exception:
        return "0.0.0"


def check_and_update() -> bool:
    """檢查登錄庫版本，必要時更新本地檔案。回傳是否有更新。"""
    base_dir = Path(__file__).resolve().parent

    try:
        remote_meta = json.loads(_fetch("metadata.json").decode("utf-8"))
    except Exception as e:
        print(f"[self_update] 無法取得登錄庫 metadata：{e}", file=sys.stderr)
        return False

    local_v = _local_version(base_dir)
    remote_v = remote_meta.get("version", "0.0.0")

    if _parse_version(remote_v) <= _parse_version(local_v):
        print(f"[self_update] 已是最新版本（本地 {local_v}，登錄庫 {remote_v}）")
        return False

    print(f"[self_update] 發現新版本：{local_v} → {remote_v}，開始更新…")
    for rel_path in FILES:
        dest = base_dir / rel_path
        try:
            data = _fetch(rel_path)
        except Exception as e:
            print(f"[self_update] 下載失敗 {rel_path}: {e}", file=sys.stderr)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
        print(f"[self_update] 已更新 {rel_path}")

    print(f"[self_update] 更新完成（{remote_v}）")
    return True


if __name__ == "__main__":
    check_and_update()
