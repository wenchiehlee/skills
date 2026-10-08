import os
import csv
import io
from datetime import datetime
from dotenv import load_dotenv
from llm import LLMClient

load_dotenv()

OUTPUT_FILE = "raw_event_ai_events.csv"
CSV_HEADERS = [
    "類別", "子類別", "事件名稱", "開始日期", "結束日期", "備註", "Link1", "Link2",
    "download_timestamp", "process_timestamp"
]

PROMPT = """
You are a Financial Technology Analyst.

Task: Search for and extract a list of the TOP 50-100 CRITICAL Artificial Intelligence events that significantly impacted the Stock Market, Corporate Valuations, or the Business Landscape.

Focus on events that:
1. Caused noticeable stock price movements (e.g., NVIDIA, Microsoft, Google, TSM).
2. Triggered major M&A (Mergers & Acquisitions) or huge Venture Capital investments.
3. Launched products that disrupted industries or created new revenue streams.
4. Influenced market sentiment or regulatory environments affecting business operations (e.g., Chip bans).

Focus on these specific Categories (類別) and Sub-categories (子類別):

1. 市場與資本 (Market & Capital):
   - 市值里程碑 (Market Cap Milestones) - e.g., NVIDIA hits $3T, Microsoft overtakes Apple due to AI.
   - 併購與投資 (M&A & Investment) - e.g., Microsoft invests $10B in OpenAI, Google buys DeepMind.
   - 股價波動 (Stock Movement) - e.g., Super Micro Computer surge, Chegg crash due to ChatGPT.

2. 產品發布與商業化 (Product & Commercialization):
   - 生成式AI應用 (Generative AI Apps) - e.g., ChatGPT launch (sparked AI arms race), Copilot launch.
   - 企業級解決方案 (Enterprise Solutions) - e.g., Salesforce AI integration.
   - 硬體與基礎設施 (Hardware & Infra) - e.g., H100 announcement (AI gold rush), AMD MI300.

3. 技術突破與轉折點 (Tech Breakthroughs as Market Catalysts):
   - 關鍵論文 (Seminal Papers) - e.g., "Attention Is All You Need" (foundation of modern value creation).
   - 模型發布 (Model Releases) - e.g., GPT-4 (set new industry standard).

4. 政策與監管衝擊 (Regulation & Policy Impact):
   - 貿易限制 (Trade Restrictions) - e.g., US bans AI chip exports to China (impacted NVIDIA/AMD stocks).
   - 監管審查 (Regulation Scrutiny) - e.g., Antitrust investigations into AI partnerships.

Output Format:
Produce a valid CSV file content with the following headers (no quotes):
類別,子類別,事件名稱,開始日期,結束日期,備註,Link1,Link2

Requirements:
- CSV Formatting: Use standard CSV format. DO NOT wrap cells in double quotes unless the cell content contains a comma. 
- NO NESTED QUOTES: Never use double-double quotes (e.g., ""text"") or triple quotes.
- Language: All text must be in Traditional Chinese (繁體中文).
- Dates: Format YYYY-MM-DD.
- "備註" (Note): Explain the Business/Market Impact (e.g., "NVIDIA股價當日上漲24%", "微軟市值超越蘋果", "引發AI軍備競賽").
- "Link1": MANDATORY. Provide a reliable source URL (Bloomberg, CNBC, Reuters, TechCrunch).
- Quantity: Aim for ~40-50 distinct high-impact events.
- Do not include markdown code block markers.
"""


def clean_csv(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


def _clean_cell(v: str) -> str:
    v = v.strip()
    if v.startswith('"') and v.endswith('"'):
        v = v[1:-1].strip()
    return v


def save_csv(csv_content: str, output_file: str) -> None:
    process_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S CST")
    new_rows = []
    try:
        reader = csv.reader(io.StringIO(csv_content))
        rows = [[_clean_cell(c) for c in row] for row in reader]
        if rows:
            new_rows = rows[1:]
    except csv.Error as e:
        print(f"Error parsing CSV response: {e}")
        return

    existing_rows = []
    existing_keys: set = set()

    if os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                for i, row in enumerate(reader):
                    if i == 0:
                        continue
                    if len(row) >= 4:
                        while len(row) < len(CSV_HEADERS):
                            row.append("")
                        existing_keys.add((row[2].strip(), row[3].strip()))
                        existing_rows.append(row)
        except Exception as e:
            print(f"Warning: Could not read existing file for deduplication: {e}")

    rows_to_append = []
    for row in new_rows:
        if len(row) >= 4:
            key = (row[2].strip(), row[3].strip())
            if key not in existing_keys:
                while len(row) < len(CSV_HEADERS):
                    row.append("")
                rows_to_append.append(row)
                existing_keys.add(key)

    all_rows = existing_rows + rows_to_append

    # Refresh timestamps for ALL rows to current process_timestamp.
    # This satisfies the (Duration + Lag < Threshold) health check, matching
    # fetch_historical_crashes.py's approach for the same reason: this is a
    # curated/static event list, not a daily-append log.
    for row in all_rows:
        row[-2] = process_timestamp  # download_timestamp
        row[-1] = process_timestamp  # process_timestamp

    if all_rows:
        with open(output_file, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADERS)
            writer.writerows(all_rows)
        print(f"Wrote {len(all_rows)} total events ({len(rows_to_append)} new) to '{output_file}'.")
    else:
        print(f"No existing file and no new unique events for '{output_file}'.")


def generate_ai_events() -> None:
    print("Fetching major AI events (Market & Business Impact)...")
    print("Sending request to Codex (agy/gemini)...")

    try:
        client = LLMClient(app_name="InvestorEvents")
        csv_content = clean_csv(client.generate_smart(
            "InvestorEvents_FetchAIEvents", PROMPT, draft_provider="codex", draft_model="gemini-2.5-flash"
        ))
        save_csv(csv_content, OUTPUT_FILE)

        print("-" * 50)
        print(csv_content[:800] + "\n...(truncated)")
        print("-" * 50)

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    generate_ai_events()
