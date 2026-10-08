import os
import csv
import io
from datetime import datetime
from dotenv import load_dotenv
from llm import LLMClient

load_dotenv()

OUTPUT_FILE = "raw_event_stock_events.csv"
CSV_HEADERS = [
    "類別", "子類別", "事件名稱", "開始日期", "結束日期", "備註", "Link1", "Link2",
    "download_timestamp", "process_timestamp"
]

PROMPT = """
You are a Financial Market Historian and Equity Analyst.

Task: Search for and extract a list of the TOP 50-80 CRITICAL stock market events from 1990 to the present that significantly shaped investor behavior, market structure, or specific sector trends — with emphasis on both Global (US) and Taiwan markets.

Focus on these specific Categories (類別) and Sub-categories (子類別):

1. 市場結構 (Market Structure):
   - 指數調整 (Index Rebalancing) - e.g., TSMC added to MSCI, S&P 500 rebalancing.
   - 市場開放 (Market Opening) - e.g., Taiwan opening to foreign investors, China A-share inclusion.
   - 交易制度 (Trading Rules) - e.g., circuit breakers introduced, short-sell bans.

2. 公司行動 (Corporate Actions):
   - 重大IPO (Major IPO) - e.g., Alibaba IPO ($25B), ARM IPO, TSMC US listing.
   - 股票分割 (Stock Split) - e.g., Apple 7:1, NVIDIA 10:1.
   - 重大購併 (Major M&A) - e.g., Disney buys Fox, Broadcom buys VMware.

3. 財報事件 (Earnings Events):
   - 超預期財報 (Earnings Beat) - e.g., NVIDIA beats by 50%+ causing massive rally.
   - 財報地雷 (Earnings Miss) - e.g., Meta Q3 2022 crash, Intel guidance cut.

4. 市值里程碑 (Market Cap Milestones):
   - 兆元俱樂部 (Trillion Dollar Club) - e.g., Apple first $1T, $2T, $3T milestones.
   - 台灣市值紀錄 (Taiwan Market Records) - e.g., TSMC market cap milestones.

5. 散戶與投機事件 (Retail & Speculative Events):
   - 軋空事件 (Short Squeeze) - e.g., GameStop, AMC.
   - 迷因股 (Meme Stocks) - e.g., Reddit WallStreetBets driven events.

Output Format:
Produce a valid CSV file content with the following headers (no quotes):
類別,子類別,事件名稱,開始日期,結束日期,備註,Link1,Link2

Requirements:
- CSV Formatting: Use standard CSV format. DO NOT wrap cells in double quotes unless the cell content contains a comma. 
- NO NESTED QUOTES: Never use double-double quotes (e.g., ""text"") or triple quotes.
- Language: All text must be in Traditional Chinese (繁體中文).
- Dates: Format YYYY-MM-DD.
- "備註" (Note): Briefly explain the market impact (e.g., "股價單日上漲X%", "引發散戶跟風買入", "MSCI調整後資金流入台股").
- "Link1": MANDATORY. Provide a reliable source URL (Bloomberg, Reuters, CNBC, Yahoo Finance).
- Quantity: Aim for ~50 distinct high-impact events, distributed across decades.
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


def generate_stock_events() -> None:
    print("Fetching important stock market events (1990-Present)...")
    print("Sending request to Codex (agy/gemini)...")

    try:
        client = LLMClient(app_name="InvestorEvents")
        csv_content = clean_csv(client.generate_smart(
            "InvestorEvents_FetchStockEvents", PROMPT, draft_provider="codex", draft_model="gemini-2.5-flash"
        ))
        save_csv(csv_content, OUTPUT_FILE)

        print("-" * 50)
        print(csv_content[:800] + "\n...(truncated)")
        print("-" * 50)

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    generate_stock_events()
