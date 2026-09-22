# FinMind Type 16 CSV

fetch_type16.py downloads FinMind quarterly fundamentals and writes the 164-column CSV schema used by Python-Actions.GoodInfo.Analyzer (raw_fin_ratio_quarter.csv).

## Local run

Copy .env.example to .env and set FINMIND_TOKEN. The token is loaded only from the environment; it is never written to output CSV.

    python3 -m pip install -r requirements.txt
    python3 skills/skill-finmind-fetch/scripts/fetch_type16.py --stock-id 2330 --company-name 台積電 --start-date 2020-01-01 --end-date 2026-12-31 --output financial/type16/raw_fin_ratio_quarter_2330.csv

Income-statement values are used as quarterly values. Cash-flow values are converted from year-to-date to single-quarter values. Unsupported GoodInfo-only scores and metrics remain blank.

Compare the generated CSV with the Analyzer CSV before extending the stock list.
