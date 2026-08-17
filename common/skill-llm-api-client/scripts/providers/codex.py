"""LLM-CLI-APIServer provider（Mac-mini Flask bridge to ChatGPT Pro）。"""
from __future__ import annotations

import logging
import os

import httpx

from . import BaseProvider

logger = logging.getLogger(__name__)

MAX_PROMPT_LENGTH = 50_000  # 與 LLM-CLI-APIServer CODEX_MAX_PROMPT_LENGTH 一致
_CONNECT_TIMEOUT = 10       # 連線建立上限（秒）
_READ_TIMEOUT = 180         # codex exec 最長執行時間（秒）


class CodexProvider(BaseProvider):
    name = "llm-cli"

    def __init__(self, url: str | None = None, api_key: str | None = None, model: str | None = None):
        self.url = (url or os.getenv("CODEX_API_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("CODEX_API_KEY", "")
        self.model = model or "chatgpt-pro"
        if not self.url:
            raise RuntimeError("Missing env var: CODEX_API_URL")
        if not self.api_key:
            raise RuntimeError("Missing env var: CODEX_API_KEY")

    def generate(self, prompt: str, *, json_mode: bool = False, max_tokens: int = 8192) -> str:
        if len(prompt) > MAX_PROMPT_LENGTH:
            raise ValueError(f"Prompt 超過長度上限（{len(prompt)} > {MAX_PROMPT_LENGTH}）")

        # 若模型為 gemini 開頭，則走 /gemini/exec 端點
        if self.model.startswith("gemini"):
            endpoint = "/gemini/exec"
            payload = {"prompt": prompt, "model": self.model, "json_mode": json_mode}
        else:
            endpoint = "/exec"
            payload = {"prompt": prompt, "json_mode": json_mode}

        resp = httpx.post(
            f"{self.url}{endpoint}",
            json=payload,
            headers={"X-API-Key": self.api_key, "Content-Type": "application/json"},
            timeout=httpx.Timeout(connect=_CONNECT_TIMEOUT, read=_READ_TIMEOUT,
                                  write=_CONNECT_TIMEOUT, pool=_CONNECT_TIMEOUT),
        )
        resp.raise_for_status()
        return resp.json().get("output", "")

    def generate_smart(
        self,
        task_name: str,
        prompt: str,
        *,
        draft_cli: str = "gemini",
        judge_cli: str = "gemini",
        model: str | None = None,
        json_mode: bool = False,
        max_tokens: int = 8192,
    ) -> str:
        """調用伺服器端的智慧路由端點 (消除網路延遲)。"""
        if len(prompt) > MAX_PROMPT_LENGTH:
            raise ValueError(f"Prompt 超過長度上限（{len(prompt)} > {MAX_PROMPT_LENGTH}）")

        endpoint = "/smart/exec"
        payload = {
            "task_name": task_name,
            "prompt": prompt,
            "draft_cli": draft_cli,
            "judge_cli": judge_cli,
            "model": model or (self.model if self.model.startswith("gemini") else ""),
            "json_mode": json_mode
        }

        resp = httpx.post(
            f"{self.url}{endpoint}",
            json=payload,
            headers={"X-API-Key": self.api_key, "Content-Type": "application/json"},
            timeout=httpx.Timeout(connect=_CONNECT_TIMEOUT, read=_READ_TIMEOUT * 2,  # 評估模式可能需要兩次執行時間
                                  write=_CONNECT_TIMEOUT, pool=_CONNECT_TIMEOUT),
        )
        resp.raise_for_status()
        data = resp.json()

        # 紀錄最後使用的 provider (可能是 draft 或 judge)
        self.last_provider_used = data.get("provider", self.name)
        return data.get("output", "")

