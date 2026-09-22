#!/usr/bin/env python3
"""Fetch FinMind monthly revenue and export a GoodInfo Type 5 CSV."""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from fetch_to_csv import fetch_data
from price_cache import cached_price
from token_env import TokenRotator
load_dotenv()

COLUMNS=["stock_code","company_name","月別","當月股價_開盤","當月股價_收盤","當月股價_最高","當月股價_最低","當月股價_漲跌_元","當月股價_漲跌_pct","營業收入_營收_億","營業收入_月增_pct","營業收入_年增_pct","營業收入_累計_億","營業收入_累計年增_pct","合併營業收入_營收_億","合併營業收入_月增_pct","合併營業收入_年增_pct","合併營業收入_累計_億","合併營業收入_累計年增_pct","file_type","source_file","download_success","download_timestamp","process_timestamp","stage1_process_timestamp"]

def n(v):
    try: return float(v)
    except (TypeError,ValueError): return np.nan

def build_rows(stock_id, company_name, revenue, prices):
    rev=pd.DataFrame(revenue); px=pd.DataFrame(prices)
    if rev.empty: return pd.DataFrame(columns=COLUMNS)
    rev["year"]=pd.to_numeric(rev["revenue_year"],errors="coerce").astype("Int64")
    rev["month"]=pd.to_numeric(rev["revenue_month"],errors="coerce").astype("Int64")
    rev=rev.dropna(subset=["year","month"]).copy(); rev["period"]=[f"{int(y):04d}/{int(m):02d}" for y,m in zip(rev.year,rev.month)]
    rev=rev.sort_values(["year","month"])
    rev["revenue_value"]=pd.to_numeric(rev["revenue"],errors="coerce")/1e8
    rev["mom"]=rev["revenue_value"].pct_change()*100
    prior=rev.set_index(["year","month"])["revenue_value"]
    rev["yoy"]=[(value/prior.get((int(y)-1,int(m)))-1)*100 if pd.notna(value) and prior.get((int(y)-1,int(m))) not in (None,0) else np.nan for value,y,m in zip(rev.revenue_value,rev.year,rev.month)]
    rev["cumulative"]=rev.groupby("year")["revenue_value"].cumsum()
    cumulative=rev.set_index(["year","month"])["cumulative"]
    rev["cum_yoy"]=[(value/cumulative.get((int(y)-1,int(m)))-1)*100 if pd.notna(value) and cumulative.get((int(y)-1,int(m))) not in (None,0) else np.nan for value,y,m in zip(rev.cumulative,rev.year,rev.month)]
    if not px.empty:
        px["date"]=pd.to_datetime(px["date"],errors="coerce"); px=px.dropna(subset=["date"]); px["period"]=px.date.dt.strftime("%Y/%m")
    rows=[]; timestamp=datetime.now().isoformat(timespec="seconds"); previous_close=np.nan
    for _,r in rev.iterrows():
        p=px[px.period==r.period].sort_values("date") if not px.empty else pd.DataFrame()
        close=p.iloc[-1].get("close",np.nan) if not p.empty else np.nan
        change=close-previous_close if pd.notna(close) and pd.notna(previous_close) else np.nan
        row={"stock_code":str(stock_id).zfill(4),"company_name":company_name,"月別":r.period,"當月股價_開盤":p.iloc[0].get("open",np.nan) if not p.empty else np.nan,"當月股價_收盤":close,"當月股價_最高":p["max"].max() if not p.empty else np.nan,"當月股價_最低":p["min"].min() if not p.empty else np.nan,"當月股價_漲跌_元":change,"當月股價_漲跌_pct":round(change/previous_close*100,2) if pd.notna(change) and previous_close else np.nan,"營業收入_營收_億":round(r.revenue_value),"營業收入_月增_pct":round(r.mom,2) if pd.notna(r.mom) else np.nan,"營業收入_年增_pct":round(r.yoy,2) if pd.notna(r.yoy) else np.nan,"營業收入_累計_億":round(r.cumulative),"營業收入_累計年增_pct":round(r.cum_yoy,2) if pd.notna(r.cum_yoy) else np.nan,"合併營業收入_營收_億":round(r.revenue_value),"合併營業收入_月增_pct":round(r.mom,2) if pd.notna(r.mom) else np.nan,"合併營業收入_年增_pct":round(r.yoy,2) if pd.notna(r.yoy) else np.nan,"合併營業收入_累計_億":round(r.cumulative),"合併營業收入_累計年增_pct":round(r.cum_yoy,2) if pd.notna(r.cum_yoy) else np.nan,"file_type":"ShowSaleMonChart","source_file":f"FinMind_API_TaiwanStockMonthRevenue_{str(stock_id).zfill(4)}","download_success":True,"download_timestamp":timestamp,"process_timestamp":timestamp,"stage1_process_timestamp":timestamp}
        rows.append(row)
        if pd.notna(close): previous_close=close
    return pd.DataFrame(rows,columns=COLUMNS)

def main():
    p=argparse.ArgumentParser(); p.add_argument('--stock-id',default='2330'); p.add_argument('--company-name',default='台積電'); p.add_argument('--start-date',default='2021-01-01'); p.add_argument('--end-date',default=(datetime.now()+timedelta(hours=8)).strftime('%Y-%m-%d')); p.add_argument('--output',default='financial/type5/raw_revenue_2330.csv'); p.add_argument('--token',default=None); p.add_argument('--price-cache-dir',default=None); a=p.parse_args(); rot=TokenRotator(a.token)
    rev=fetch_data('TaiwanStockMonthRevenue',data_id=a.stock_id,start_date=a.start_date,end_date=a.end_date,token=rot)
    px=cached_price(a.stock_id,a.start_date,a.end_date,rot,a.price_cache_dir,fetch_data)
    out=build_rows(a.stock_id,a.company_name,rev.to_dict('records'),px.to_dict('records'))
    if out.empty: raise SystemExit('No revenue data available')
    Path(a.output).parent.mkdir(parents=True,exist_ok=True); out.to_csv(a.output,index=False,encoding='utf-8-sig'); print(f'Wrote {len(out)} monthly revenue rows to {a.output}')
if __name__=='__main__': main()
