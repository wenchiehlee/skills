#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
whisper_issue_client.py — Issue-driven client for the Mac-mini Whisper pipeline
(skill-mlx-api-server-whisper).

Unlike the OCR client (ocr_client.py), this does NOT call an HTTP endpoint.
The Whisper pipeline is asynchronous and stateful (multi-experiment transcription
→ LLM postprocess → CER verification → git commit), so it is driven by opening a
GitHub issue on the target repo (which runs a self-hosted-runner workflow) and
polling for the resulting FIN.srt to land back in this repo.

Usage (module):
    from scripts.whisper_issue_client import WhisperIssueClient

    client = WhisperIssueClient()  # reads .env: WHISPER_* vars
    client.sync_manifest("audio_manifest.json")   # open/close issues for every stem

Usage (CLI):
    python scripts/whisper_issue_client.py sync audio_manifest.json
    python scripts/whisper_issue_client.py status <stem>
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path.cwd() / ".env")
except ImportError:
    pass

API_ROOT = "https://api.github.com"

# source_type 決定 stem 命名慣例，與 skill-mlx-api-server-whisper 的解析規則對稱：
#   investor_conference : {stock_id}_{year}_q{quarter}   → group_id = stock_id
#   youtube              : {channel}_{video_id}           → group_id = channel（video_id 固定 11 碼）
STEM_PATTERNS = {
    "investor_conference": re.compile(r"^(?P<stock_id>[A-Za-z0-9]+)_(?P<year>\d{4})_q(?P<quarter>[1-4])$", re.I),
    "youtube": re.compile(r"^(?P<channel>.+)_(?P<video_id>[A-Za-z0-9_-]{11})$"),
}


def parse_stem(stem: str, source_type: str) -> dict:
    """Return {'group_id': ..., 'stock_id': ...(optional)} parsed per source_type."""
    pattern = STEM_PATTERNS.get(source_type)
    if pattern is None:
        raise ValueError(f"Unsupported source_type: {source_type}")
    m = pattern.match(stem)
    if not m:
        raise ValueError(f"Invalid stem '{stem}' for source_type={source_type}")
    if source_type == "youtube":
        return {"group_id": m.group("channel")}
    return {"group_id": m.group("stock_id"), "stock_id": m.group("stock_id")}


class GitHubClient:
    def __init__(self, token: str) -> None:
        self.token = token

    def request(self, method: str, path: str, payload: dict | None = None) -> dict | list | None:
        data = None
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(f"{API_ROOT}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API {method} {path} failed: {exc.code} {detail}") from exc
        if not body:
            return None
        return json.loads(body.decode("utf-8"))


class WhisperIssueClient:
    """
    Opens/closes 'generate-FIN' issues on the target repo (Mac-mini) to drive
    skill-mlx-api-server-whisper, and checks whether the resulting FIN.srt has
    landed back in this (source) repo.

    Config is read from environment / .env:
      WHISPER_TARGET_REPO   — repo that runs run-pipeline.yml, e.g. "ZhongZheng782/Mac-mini"
      WHISPER_SOURCE_REPO   — this repo (owner/name), e.g. "wenchiehlee-money/YoutubeAudio.Fetch"
      WHISPER_SOURCE_TYPE   — "investor_conference" | "youtube"
      REPO_FILE_SYNC_<TARGET_OWNER>_<...> (e.g. REPO_FILE_SYNC_ZHONGZHENG782_MONEY) / GH_TOKEN
        — PAT with Issues: Read and write on WHISPER_TARGET_REPO only (no contents access needed;
        FIN.srt landing is checked as a local file, see check_fin_status()).
    """

    LABELS_BASE = ["generate-FIN", "auto-generated"]

    def __init__(
        self,
        target_repo: str | None = None,
        source_repo: str | None = None,
        source_type: str | None = None,
        token: str | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self.target_repo = target_repo or os.environ.get("WHISPER_TARGET_REPO", "")
        self.source_repo = source_repo or os.environ.get("WHISPER_SOURCE_REPO", "")
        self.source_type = source_type or os.environ.get("WHISPER_SOURCE_TYPE", "investor_conference")
        # REPO_FILE_SYNC_* takes precedence (matches the naming convention already used by
        # tools/manage_missing_fin_issues.py and the Mac-mini Actions secrets); GH_TOKEN is
        # a generic fallback for local/ad-hoc use.
        token = token or next(
            (v for k, v in os.environ.items() if k.startswith("REPO_FILE_SYNC_")), None
        ) or os.environ.get("GH_TOKEN")
        if not self.target_repo or not self.source_repo:
            raise RuntimeError("WHISPER_TARGET_REPO and WHISPER_SOURCE_REPO must be set (env or .env)")
        if not token:
            raise RuntimeError("A REPO_FILE_SYNC_* var (or GH_TOKEN) is required")
        self.client = GitHubClient(token)
        self.repo_root = repo_root or Path.cwd()
        # source_repo's own name is used as a label so multiple source repos can
        # share the same target repo/issue tracker without colliding.
        self.source_label = self.source_repo.split("/", 1)[-1]

    @property
    def labels(self) -> list[str]:
        return self.LABELS_BASE + [self.source_label]

    def ensure_labels(self) -> None:
        colors = {"generate-FIN": "0E8A16", "auto-generated": "C5DEF5"}
        for label in self.labels:
            try:
                self.client.request("GET", f"/repos/{self.target_repo}/labels/{urllib.parse.quote(label)}")
            except RuntimeError:
                self.client.request(
                    "POST",
                    f"/repos/{self.target_repo}/labels",
                    {"name": label, "color": colors.get(label, "5319E7"), "description": "Managed by whisper_issue_client"},
                )

    def issue_title(self, stem: str) -> str:
        return f"Generate FIN.srt: {stem}"

    def issue_body(self, stem: str, audio_url: str, fin_path: str, task_type: str = "generate_fin_srt", stock_id: str | None = None) -> str:
        parsed = parse_stem(stem, self.source_type)
        metadata = {
            "task_type": task_type,
            "source_repo": self.source_repo,
            "source_type": self.source_type,
            "stem": stem,
            "audio_url": audio_url,
            "expected_fin_srt_path": fin_path,
        }
        if stock_id or parsed.get("stock_id"):
            metadata["stock_id"] = stock_id or parsed.get("stock_id")
        yaml_lines = [f'{key}: "{value}"' for key, value in metadata.items()]
        return f"{self.source_label} detected audio with no FIN.srt.\n\n```yaml\n" + "\n".join(yaml_lines) + "\n```\n"

    def fin_path_for(self, stem: str) -> str:
        parsed = parse_stem(stem, self.source_type)
        return f"data/{parsed['group_id']}/{stem}_FIN.srt"

    def list_open_issues(self) -> dict[str, dict]:
        labels = urllib.parse.quote(",".join(["generate-FIN", self.source_label]))
        issues_by_title: dict[str, dict] = {}
        page = 1
        while True:
            path = f"/repos/{self.target_repo}/issues?state=open&labels={labels}&per_page=100&page={page}"
            issues = self.client.request("GET", path)
            if not isinstance(issues, list) or not issues:
                break
            for issue in issues:
                if "pull_request" not in issue:
                    issues_by_title[issue.get("title", "")] = issue
            page += 1
        return issues_by_title

    def open_fin_request(self, stem: str, audio_url: str, task_type: str = "generate_fin_srt", stock_id: str | None = None) -> dict | None:
        """Open a generate-FIN issue for `stem` if one isn't already open. Idempotent."""
        open_issues = self.list_open_issues()
        title = self.issue_title(stem)
        if title in open_issues:
            return None
        fin_path = self.fin_path_for(stem)
        # Labels must be added via a separate call, not inline in the create payload:
        # GitHub does not fire a `labeled` webhook event for labels set at creation
        # time, only for labels added to an already-existing issue. run-pipeline.yml
        # triggers on `issues: types: [labeled]`, so an inline-labeled issue would
        # silently never run the pipeline (found via Mac-mini issue #21, stuck ~3 weeks).
        new_issue = self.client.request(
            "POST",
            f"/repos/{self.target_repo}/issues",
            {"title": title, "body": self.issue_body(stem, audio_url, fin_path, task_type, stock_id)},
        )
        self.client.request(
            "POST",
            f"/repos/{self.target_repo}/issues/{new_issue['number']}/labels",
            {"labels": self.labels},
        )
        return new_issue

    def check_fin_status(self, stem: str) -> bool:
        """True if FIN.srt for `stem` already exists locally in this (source) repo."""
        return (self.repo_root / self.fin_path_for(stem)).exists()

    def close_if_done(self, stem: str) -> bool:
        """If FIN.srt exists locally and a matching open issue exists, comment + close it."""
        if not self.check_fin_status(stem):
            return False
        open_issues = self.list_open_issues()
        issue = open_issues.get(self.issue_title(stem))
        if not issue:
            return False
        fin_path = self.fin_path_for(stem)
        self.client.request(
            "POST",
            f"/repos/{self.target_repo}/issues/{issue['number']}/comments",
            {"body": f"Fixed: `{self.source_repo}` now contains `{fin_path}` for `{stem}`."},
        )
        self.client.request("PATCH", f"/repos/{self.target_repo}/issues/{issue['number']}", {"state": "closed"})
        return True

    def sync_manifest(self, manifest_path: str | Path) -> dict[str, int]:
        """
        Read a {stem: audio_url} JSON manifest and, for every stem:
          - close+comment the issue if FIN.srt already landed,
          - otherwise open a generate-FIN issue if none is open yet.
        Mirrors the original InvestorConference tools/manage_missing_fin_issues.py loop,
        generalized to any source_repo/source_type.
        """
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        self.ensure_labels()
        created = closed = skipped = 0
        for stem, audio_url in sorted(manifest.items()):
            try:
                if self.check_fin_status(stem):
                    if self.close_if_done(stem):
                        closed += 1
                    continue
                if self.open_fin_request(stem, audio_url) is None:
                    skipped += 1
                else:
                    created += 1
            except ValueError as e:
                print(f"[whisper_issue_client] skip {stem}: {e}", file=sys.stderr)
                skipped += 1
        print(f"[whisper_issue_client] done. created={created} closed={closed} skipped={skipped}")
        return {"created": created, "closed": closed, "skipped": skipped}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sync_p = sub.add_parser("sync", help="Open/close issues for every stem in a manifest.json")
    sync_p.add_argument("manifest", help="Path to {stem: audio_url} JSON manifest")

    status_p = sub.add_parser("status", help="Check whether FIN.srt already exists for a stem")
    status_p.add_argument("stem")

    args = parser.parse_args()
    client = WhisperIssueClient()

    if args.cmd == "sync":
        client.sync_manifest(args.manifest)
    elif args.cmd == "status":
        print("done" if client.check_fin_status(args.stem) else "pending")
