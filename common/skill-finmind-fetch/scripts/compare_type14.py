#!/usr/bin/env python3
"""Compare FinMind Type 14 weekly output with GoodInfo Analyzer CSV."""
from __future__ import annotations
import argparse
import pandas as pd

NUMERIC_COLUMNS = [
    "收盤_價格_元", "漲跌_價格_元", "漲跌_pct", "成交_張數", "融資_買進_張", "融資_賣出_張", "融資_現償_張", "融資_增減_張", "融資_餘額_張", "融資_使用率_pct", "融券_買進_張", "融券_賣出_張", "融券_現償_張", "融券_增減_張", "融券_餘額_張", "融券_使用率_pct", "資券互抵_張", "資券當沖_pct", "券資比_pct", "現股當沖_pct",
]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--candidate', required=True)
    p.add_argument('--reference', required=True)
    p.add_argument('--stock-id', default='2330')
    args=p.parse_args()
    left=pd.read_csv(args.candidate, dtype={'stock_code':str})
    right=pd.read_csv(args.reference, dtype={'stock_code':str})
    left=left[left.stock_code.str.zfill(4)==args.stock_id.zfill(4)].set_index('期別')
    right=right[right.stock_code.str.zfill(4)==args.stock_id.zfill(4)].set_index('期別')
    common=left.index.intersection(right.index)
    exact=within=compared=0
    for key in common:
        for col in NUMERIC_COLUMNS:
            if col not in left or col not in right: continue
            a=pd.to_numeric(left.loc[key,col], errors='coerce'); b=pd.to_numeric(right.loc[key,col], errors='coerce')
            if pd.isna(a) and pd.isna(b): continue
            if pd.isna(a) or pd.isna(b): continue
            compared+=1; exact += int(a == b); within += int(abs(a-b) <= max(0.01, abs(b)*1e-6))
    print(f'common_weeks={len(common)} compared={compared} exact={exact} within_tolerance={within}')

if __name__ == '__main__': main()
