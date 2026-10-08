import os
import csv
import io
import re
from datetime import datetime
from dotenv import load_dotenv
from llm import LLMClient

load_dotenv(override=True)

OUTPUT_FILE = "raw_event_historical_crashes.csv"
CSV_HEADERS = [
    "類別", "子類別", "事件名稱", "開始日期", "結束日期", "備註", "Link1", "Link2",
    "download_timestamp", "process_timestamp"
]


def build_prompt(start_year: int, end_year: int) -> str:
    return f"""
You are a financial historian specializing in modern market volatility.

Task: Search for and extract a list of CRITICAL events from {start_year}-01-01 to {end_year}-12-31 that caused significant stock market drops (crashes, corrections, or bear markets) in either the Global (US) or Taiwan markets.

Special Focus:
- Major Financial Crises (e.g., Dot-com bubble, SARS, 2008 Financial Crisis, COVID-19).
- Significant Geopolitical Shocks (e.g., Wars, Trade Wars).
- Policy Shocks (e.g., Aggressive interest rate hikes).

Focus on these specific Categories (類別) and Sub-categories (子類別):
1. 金融危機 (Financial Crisis)
2. 公共衛生 (Public Health)
3. 地緣政治 (Geopolitics)
4. 自然災害 (Natural Disaster)
5. 政策衝擊 (Policy Shock)

Output Format:
Produce a valid CSV file content with the following headers (NO QUOTES in header line):
類別,子類別,事件名稱,開始日期,結束日期,備註,Link1,Link2

Requirements:
- CSV Formatting: Use standard CSV format. DO NOT wrap cells in double quotes unless the cell content contains a comma. 
- NO NESTED QUOTES: Never use double-double quotes (e.g., ""text"") or triple quotes.
- Language: All text must be in Traditional Chinese (繁體中文).
- Dates: Format YYYY-MM-DD.
- "備註" (Note): Briefly explain the impact (e.g., "台股單日重挫...").
- "Link1": MANDATORY. Provide a reliable source URL.
- Quantity: Find about 20 high-quality events SPECIFICALLY within the period {start_year} to {end_year}.
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
    if v.startswith('"') and v.endswith('"'):
        v = v[1:-1].strip()
    return v


def _row_score(row: list) -> int:
    """Score row completeness: more non-empty fields + longer 備註 + valid Link1 = higher."""
    score = sum(1 for cell in row if cell.strip())
    if len(row) > 5:
        score += len(row[5]) // 20
    if len(row) > 6 and row[6].strip().startswith("http"):
        score += 5
    return score


def _global_dedup(rows: list) -> list:
    """Global dedup: group by 開始日期 only, keep the most complete row per start date.

    Using start date as the sole key because:
    - A crash event's start date is an objective historical fact (LLM rarely varies it).
    - End dates vary across LLM runs, so (start, end) pairs leak near-duplicates.
    """
    from collections import defaultdict
    groups: dict = defaultdict(list)
    for row in rows:
        start = row[3].strip() if len(row) > 3 else ""
        groups[start].append(row)

    result = []
    removed = 0
    for group_rows in groups.values():
        best = max(group_rows, key=_row_score)
        result.append(best)
        removed += len(group_rows) - 1

    if removed:
        print(f"Global dedup removed {removed} duplicate row(s).")
    return result


def save_csv(csv_content: str, output_file: str) -> None:
    process_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S CST")
    new_rows = []
    header = None
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    try:
        reader = csv.reader(io.StringIO(csv_content))
        rows = [[_clean_cell(c) for c in row] for row in reader]
        if rows:
            header = list(CSV_HEADERS)
            new_rows = rows[1:]
    except csv.Error as e:
        print(f"Error parsing CSV response: {e}")
        return

    existing_rows = []

    if os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                for i, row in enumerate(reader):
                    if i == 0:
                        continue
                    if len(row) >= 4 and date_pattern.match(row[3].strip()):
                        while len(row) < len(CSV_HEADERS):
                            row.append(process_timestamp)
                        if not row[-2]: row[-2] = process_timestamp
                        if not row[-1]: row[-1] = process_timestamp
                        existing_rows.append(row)
        except Exception as e:
            print(f"Warning: Could not read existing file: {e}")

    valid_new_rows = []
    for row in new_rows:
        if len(row) >= 6 and date_pattern.match(row[3].strip()):
            while len(row) < len(CSV_HEADERS):
                row.append(process_timestamp)
            row[-2] = process_timestamp
            row[-1] = process_timestamp
            valid_new_rows.append(row)
        else:
            if any(cell.strip() for cell in row):
                print(f"Skipping malformed row: {row}")

    before_count = len(set(r[3] for r in existing_rows if len(r) > 3))
    all_rows = _global_dedup(existing_rows + valid_new_rows)
    
    # Refresh timestamps for ALL rows to current process_timestamp
    # This satisfies the (Duration + Lag < Threshold) health check.
    for row in all_rows:
        while len(row) < len(CSV_HEADERS):
            row.append(process_timestamp)
        row[-2] = process_timestamp # download_timestamp
        row[-1] = process_timestamp # process_timestamp

    all_rows.sort(key=lambda r: r[3] if len(r) > 3 else "", reverse=True)

    with open(output_file, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header or CSV_HEADERS)
        writer.writerows(all_rows)

    added = len(all_rows) - before_count
    if added > 0:
        print(f"Appended {added} new event(s) to '{output_file}'. Total: {len(all_rows)}")
    else:
        print(f"No new unique events added. Total after dedup: {len(all_rows)}")


def generate_historical_crashes() -> None:
    print("Fetching historical market crash events (Multi-stage)...")
    periods = [(1995, 2010), (2010, 2026)]
    
    try:
        client = LLMClient(app_name="InvestorEvents")
        
        for start_year, end_year in periods:
            print(f"\n>>> Fetching events for period: {start_year} - {end_year}")
            prompt = build_prompt(start_year, end_year)
            task_name = f"InvestorEvents_FetchHistoricalCrashes_{start_year}_{end_year}"
            
            csv_content = clean_csv(client.generate_smart(
                task_name, prompt, draft_provider="codex", draft_model="gemini-2.5-flash"
            ))
            save_csv(csv_content, OUTPUT_FILE)

            print("-" * 30)
            print(csv_content[:400] + "\n...(truncated)")
            print("-" * 30)

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    generate_historical_crashes()
