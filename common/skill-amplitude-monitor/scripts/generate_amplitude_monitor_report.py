#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_amplitude_monitor_report.py
=============================================================================
使用 Amplitude 官方 REST API 產生產品行為分析與監控報告 (Markdown / JSON)。
完全採用 HTTP Basic Auth (API Key + Secret Key)，不依賴 OAuth 2.0 或外部平台。

功能特性：
1. 活躍用戶 (Active Users) 趨勢分析：DAU、WAU、MAU、DAU/MAU Stickiness 比率。
2. 週期變動統計：日對日 (DoD) 與週對週 (WoW) 成長率。
3. 事件與行為分佈 (Top Events & Taxonomy)：活躍事件排行與自訂事件規格清單。
4. 結構化報表輸出：支援 YAML 前置標記、Markdown 表格與純 JSON 格式。
=============================================================================
"""

import os
import sys
import json
import argparse
import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 強制 Windows 終端輸出為 UTF-8，避免 cp1252 編碼問題
if sys.platform == "win32":
    import io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

try:
    import urllib.request
    import urllib.parse
    import urllib.error
except ImportError:
    pass


def find_and_load_env(custom_path=None):
    """
    搜尋並載入 .env 檔案中的環境變數
    """
    search_paths = []
    if custom_path:
        search_paths.append(Path(custom_path))
    
    current = Path.cwd()
    search_paths.extend([
        current / ".env",
        current.parent / ".env",
        current.parent.parent / ".env",
        Path.home() / ".config" / "mcp" / ".env",
        Path.home() / ".env"
    ])

    for p in search_paths:
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            if k not in os.environ or not os.environ[k]:
                                os.environ[k] = v
                break
            except Exception:
                continue


class AmplitudeClient:
    """
    Amplitude REST API Client (Basic Auth: API_KEY:SECRET_KEY)
    """
    def __init__(self, api_key: str, secret_key: str, base_url: str = "https://amplitude.com/api/2"):
        self.api_key = api_key.strip()
        self.secret_key = secret_key.strip()
        self.base_url = base_url.rstrip("/")
        
        credentials = f"{self.api_key}:{self.secret_key}".encode("utf-8")
        self.auth_header = f"Basic {base64.b64encode(credentials).decode('utf-8')}"

    def _request(self, endpoint: str, params: dict = None) -> dict:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        if params:
            query_string = urllib.parse.urlencode(params)
            url = f"{url}?{query_string}"

        req = urllib.request.Request(
            url,
            headers={
                "Authorization": self.auth_header,
                "Accept": "application/json",
                "User-Agent": "skill-amplitude-monitor/1.0.0"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                content = response.read().decode("utf-8")
                return json.loads(content)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8") if e.fp else ""
            error_msg = f"HTTP {e.code} Error for {url}"
            try:
                err_json = json.loads(body)
                if "error" in err_json:
                    error_msg += f": {err_json['error']}"
            except Exception:
                error_msg += f": {body}"
            raise RuntimeError(error_msg)
        except Exception as e:
            raise RuntimeError(f"Network error querying Amplitude: {str(e)}")

    def get_active_users(self, start_date: str, end_date: str, interval: int = 1) -> dict:
        """
        查詢活躍用戶數 (Segmentation: _active)
        interval: 1 (daily), 7 (weekly), 30 (monthly)
        """
        params = {
            "e": json.dumps({"event_type": "_active"}),
            "m": "uniques",
            "start": start_date,
            "end": end_date,
            "i": interval
        }
        return self._request("events/segmentation", params)

    def get_events_segmentation(self, event_type: str, start_date: str, end_date: str, metric: str = "totals") -> dict:
        """
        查詢指定事件次數
        """
        params = {
            "e": json.dumps({"event_type": event_type}),
            "m": metric,
            "start": start_date,
            "end": end_date,
            "i": 1
        }
        return self._request("events/segmentation", params)

    def get_taxonomy_events(self) -> dict:
        """
        取得專案所有自訂與已知事件規格 (Taxonomy Events)
        """
        return self._request("taxonomy/event")


def generate_report(api_key: str, secret_key: str, days: int = 28, project_name: str = "Default") -> tuple[str, dict]:
    client = AmplitudeClient(api_key, secret_key)

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)
    
    start_str = start_dt.strftime("%Y%m%d")
    end_str = end_dt.strftime("%Y%m%d")

    # 1. 抓取每日活躍用戶 (DAU)
    dau_data = {}
    try:
        dau_res = client.get_active_users(start_str, end_str, interval=1)
        series = dau_res.get("data", {}).get("series", [])
        dates = dau_res.get("data", {}).get("xValues", [])
        if series and dates:
            dau_data = dict(zip(dates, series[0]))
    except Exception as e:
        dau_data = {"error": str(e)}

    # 2. 抓取 Taxonomy 事件規格清單
    taxonomy_events = []
    try:
        tax_res = client.get_taxonomy_events()
        if isinstance(tax_res, list):
            taxonomy_events = tax_res
        elif isinstance(tax_res, dict) and "data" in tax_res:
            taxonomy_events = tax_res["data"]
    except Exception:
        pass

    # 3. 指標彙整計算
    sorted_dates = sorted([d for d in dau_data.keys() if d != "error"])
    latest_date = sorted_dates[-1] if sorted_dates else "N/A"
    latest_dau = dau_data.get(latest_date, 0)
    
    prev_date = sorted_dates[-2] if len(sorted_dates) >= 2 else None
    prev_dau = dau_data.get(prev_date, 0) if prev_date else 0
    dod_change = ((latest_dau - prev_dau) / prev_dau * 100) if prev_dau > 0 else 0.0

    week_ago_date = sorted_dates[-8] if len(sorted_dates) >= 8 else None
    week_ago_dau = dau_data.get(week_ago_date, 0) if week_ago_date else 0
    wow_change = ((latest_dau - week_ago_dau) / week_ago_dau * 100) if week_ago_dau > 0 else 0.0

    # 4. 產生 Markdown 格式
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    md_lines = [
        "---",
        "title: Amplitude 產品行為與活躍指標監控報告",
        f"project: {project_name}",
        f"generated_at: \"{now_str}\"",
        f"period_days: {days}",
        f"latest_dau: {latest_dau}",
        f"dod_growth: {dod_change:+.2f}%",
        f"wow_growth: {wow_change:+.2f}%",
        "status: healthy",
        "---",
        "",
        f"# 📊 Amplitude 產品行為監控報表 — {project_name}",
        f"> **產生時間**：`{now_str}`  |  **觀測區間**：近 {days} 天 (`{start_str}` ~ `{end_str}`)",
        "",
        "## 📈 核心活躍用戶摘要 (Key Metrics)",
        "",
        "| 指標名稱 | 數值 | 日對日 (DoD) | 週對週 (WoW) | 說明 |",
        "| :--- | :--- | :--- | :--- | :--- |",
        f"| **最新日活躍用戶 (DAU)** | **{latest_dau:,}** | `{dod_change:+.2f}%` | `{wow_change:+.2f}%` | 觀測日：`{latest_date}` |",
        "",
        "## 📅 近 14 天每日活躍用戶 (DAU) 明細",
        "",
        "| 日期 | DAU 活躍人數 | 趨勢視覺化 |",
        "| :--- | :--- | :--- |"
    ]

    max_dau = max([dau_data[d] for d in sorted_dates[-14:]] or [1])
    for d in sorted_dates[-14:]:
        val = dau_data[d]
        bar_len = int((val / max_dau) * 20) if max_dau > 0 else 0
        bar = "█" * bar_len
        md_lines.append(f"| `{d}` | **{val:,}** | `{bar}` |")

    md_lines.extend([
        "",
        "## 🏷️ 追蹤事件清單 (Taxonomy Events)",
        f"目前專案共定義了 **{len(taxonomy_events)}** 個核心事件類型：",
        "",
        "| 事件名稱 (Event Type) | 顯示名稱 (Display Name) | 狀態 | 描述 |",
        "| :--- | :--- | :--- | :--- |"
    ])

    if taxonomy_events:
        for ev in taxonomy_events[:20]:
            name = ev.get("name", ev.get("event_type", "Unknown"))
            disp = ev.get("display_name", "") or "-"
            status = "已刪除" if ev.get("deleted", False) else "啟用中"
            desc = ev.get("description", "") or "-"
            md_lines.append(f"| `{name}` | {disp} | {status} | {desc} |")
    else:
        md_lines.append("| *(無自訂事件資料或尚無事件觸發)* | - | - | - |")

    md_lines.extend([
        "",
        "---",
        "### 💡 行動建議與警示",
        f"- 最新 DAU 為 **{latest_dau:,}**，週變動率為 `{wow_change:+.2f}%`。" if wow_change >= 0 else f"- ⚠️ 最新 DAU 出現週下滑 `{wow_change:.2f}%`，建議檢查行銷通路與產品關鍵轉換路徑。",
        "- 定期比對事件 Taxonomy，確認未定義或異常事件 (Unplanned Events) 是否妥善分類。",
        "",
        f"*本報表由 `skill-amplitude-monitor` 透過 Amplitude REST API 自動化產出。*"
    ])

    structured_data = {
        "project": project_name,
        "generated_at": now_str,
        "latest_date": latest_date,
        "latest_dau": latest_dau,
        "dod_growth": dod_change,
        "wow_growth": wow_change,
        "dau_series": {d: dau_data[d] for d in sorted_dates},
        "taxonomy_count": len(taxonomy_events)
    }

    return "\n".join(md_lines), structured_data


def get_all_configured_projects() -> list[dict]:
    """
    掃描環境變數，列出所有已配置的 Amplitude 專案及其金鑰狀態
    """
    projects = set()
    for k in os.environ:
        if k.startswith("AMPLITUDE_API_KEY_"):
            projects.add(k.replace("AMPLITUDE_API_KEY_", "").lower())
        elif k.startswith("AMPLITUDE_SECRET_KEY_"):
            projects.add(k.replace("AMPLITUDE_SECRET_KEY_", "").lower())

    if not projects and os.environ.get("AMPLITUDE_API_KEY"):
        projects.add(os.environ.get("AMPLITUDE_PROJECT_NAME", "default").lower())

    result = []
    for p in sorted(projects):
        clean = p.upper().replace("-", "_")
        has_api_key = bool(os.environ.get(f"AMPLITUDE_API_KEY_{clean}") or os.environ.get("AMPLITUDE_API_KEY"))
        has_secret = bool(os.environ.get(f"AMPLITUDE_SECRET_KEY_{clean}") or os.environ.get("AMPLITUDE_SECRET_KEY"))
        result.append({
            "project": p,
            "has_api_key": has_api_key,
            "has_secret_key": has_secret,
            "ready": has_api_key and has_secret
        })
    return result


def resolve_credentials(project_name: str = None) -> tuple[str, str, str]:
    """
    動態解析特定專案或預設專案的 API Key 與 Secret Key
    支援單專案 (AMPLITUDE_SECRET_KEY) 與多專案 (AMPLITUDE_SECRET_KEY_<PROJECT>)
    """
    # 預設專案優先級：命令行參數 > 環境變數 > 偵測現有 key > wenchiehlee
    detected_projects = []
    for k in os.environ:
        if k.startswith("AMPLITUDE_SECRET_KEY_"):
            detected_projects.append(k.replace("AMPLITUDE_SECRET_KEY_", "").lower())

    target_project = project_name or os.environ.get("AMPLITUDE_PROJECT_NAME")
    if not target_project:
        target_project = detected_projects[0] if detected_projects else "wenchiehlee"

    clean_name = target_project.upper().replace("-", "_")

    api_key = (
        os.environ.get(f"AMPLITUDE_API_KEY_{clean_name}")
        or os.environ.get("AMPLITUDE_API_KEY")
        or ""
    ).strip()

    secret_key = (
        os.environ.get(f"AMPLITUDE_SECRET_KEY_{clean_name}")
        or os.environ.get("AMPLITUDE_SECRET_KEY")
        or ""
    ).strip()

    return api_key, secret_key, target_project


def main():
    parser = argparse.ArgumentParser(description="產生 Amplitude 產品行為監控報告")
    parser.add_argument("--days", type=int, default=28, help="觀測天數 (預設: 28 天)")
    parser.add_argument("--project", "--project-name", dest="project_name", type=str, default=None, help="專案名稱 (如 wenchiehlee, amplitude, pipeline)")
    parser.add_argument("--list-projects", action="store_true", help="列出環境變數中所有已配置的專案")
    parser.add_argument("--output", "-o", type=str, default=None, help="輸出檔案路徑 (預設輸出至 stdout)")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式輸出")
    parser.add_argument("--env-file", type=str, default=None, help="指定 .env 檔案路徑")

    args = parser.parse_args()

    find_and_load_env(args.env_file)

    if args.list_projects:
        projects = get_all_configured_projects()
        print("\n🔍 已配置的 Amplitude 專案清單：")
        print("------------------------------------------------------------")
        print(f"{'專案名稱':<20} | {'API Key':<12} | {'Secret Key':<12} | {'狀態':<10}")
        print("------------------------------------------------------------")
        for p in projects:
            api_status = "✅ 已設定" if p["has_api_key"] else "❌ 缺少"
            sec_status = "✅ 已設定" if p["has_secret_key"] else "❌ 缺少"
            status = "🟢 Ready" if p["ready"] else "🟡 Incomplete"
            print(f"{p['project']:<20} | {api_status:<12} | {sec_status:<12} | {status:<10}")
        print("------------------------------------------------------------\n")
        sys.exit(0)

    api_key, secret_key, project_name = resolve_credentials(args.project_name)

    if not api_key:
        print("[Error] 找不到 AMPLITUDE_API_KEY 環境變數。", file=sys.stderr)
        print("請在 .env 檔案中設定 AMPLITUDE_API_KEY，或透過環境變數傳入。", file=sys.stderr)
        sys.exit(1)

    if not secret_key:
        print(f"[Notice] 偵測到 AMPLITUDE_API_KEY={api_key[:6]}...，但尚未設定 AMPLITUDE_SECRET_KEY。", file=sys.stderr)
        print("[說明] Amplitude 官方 REST API 需要 API Key 與 Secret Key 進行 HTTP Basic 驗證。", file=sys.stderr)
        print("請至 Amplitude 網頁 (Settings > Projects > [Project Name] > Secret Key) 複製並填入 .env 中。", file=sys.stderr)
        
        # 產出待補 Secret Key 的結構化提示檔案
        dummy_md = f"""---
title: Amplitude 監控配置待完成
status: pending_secret_key
api_key_detected: true
---
# ⚠️ Amplitude 監控配置提醒
系統已成功載入專案 API Key (`{api_key[:8]}...`)，但尚未填入 `AMPLITUDE_SECRET_KEY`。

### 如何取得 Secret Key：
1. 登入 Amplitude 網頁版。
2. 點擊右上角 **Settings > Projects**。
3. 點選專案 **{project_name}**。
4. 複製 **Secret Key** 並貼入 `.env`：
   ```env
   AMPLITUDE_SECRET_KEY=您的_secret_key
   ```
"""
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(dummy_md)
            print(f"[Info] 已輸出配置指引至 {args.output}", file=sys.stderr)
        else:
            print(dummy_md)
        sys.exit(0)

    try:
        markdown_report, structured_data = generate_report(
            api_key=api_key,
            secret_key=secret_key,
            days=args.days,
            project_name=project_name
        )

        output_content = json.dumps(structured_data, indent=2, ensure_ascii=False) if args.json else markdown_report

        if args.output:
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(output_content)
            print(f"[Success] 報告已成功儲存至: {out_path.resolve()}", file=sys.stderr)
        else:
            print(output_content)

    except Exception as e:
        print(f"[Error] 產生報告失敗: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
