#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
self_update.py — tw-land-realty-comps 技能自我更新工具

此技能目前尚未上傳至 skills 登錄庫（wenchiehlee/skills），metadata.json 的
registry 欄位為 "pending-upstream"。在正式上傳、registry 欄位改為實際路徑之前，
執行本檔僅會回報「尚未設定登錄庫來源」，不會嘗試下載。

上傳後請將下方 REMOTE_REPO / SKILL_SUBPATH 改為實際登錄庫路徑，
並比照 skill-tw-land-geo-signal/self_update.py 的邏輯運作：
先更新登錄庫版本，再用本檔案同步回各使用端專案。
"""
import json
import platform
import sys
import urllib.request
from pathlib import Path

if platform.system() == "Windows":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

REMOTE_REPO = "wenchiehlee/skills"
SKILL_SUBPATH = "common/skill-tw-land-realty-comps"

FILES = [
    "SKILL.md",
    "metadata.json",
    "self_update.py",
    "scripts/fetch_realty_season.py",
    "scripts/fetch_price_index.py",
    "scripts/build_realty_comps.py",
    "examples/targets.example.json",
    "examples/price_index.example.json",
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


def _local_registry(base_dir: Path) -> str:
    meta_path = base_dir / "metadata.json"
    try:
        with open(meta_path, encoding="utf-8") as f:
            return json.load(f).get("registry", "")
    except Exception:
        return ""


def check_and_update() -> bool:
    """檢查登錄庫版本，必要時更新本地檔案。回傳是否有更新。"""
    base_dir = Path(__file__).resolve().parent

    if _local_registry(base_dir) == "pending-upstream":
        print("[self_update] 此技能尚未上傳至 skills 登錄庫，略過線上檢查。")
        return False

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
