#!/usr/bin/env python3
"""Fetch FinMind dividends and export a GoodInfo Type 1 CSV."""
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
COLUMNS=["stock_code","company_name","股利_發放_期間","股利_所屬_期間","現金股利_盈餘","現金股利_公積","現金股利_合計","股票股利_盈餘","股票股利_公積","股票股利_合計","股利_合計","填息_花費_日數","填權_花費_日數","股價_年度","現金殖利率_除息前_價格","現金殖利率_除息前_利率","現金殖利率_年均價_價格","現金殖利率_年均價_利率","現金殖利率_成交價_價格","現金殖利率_成交價_利率","現金殖利率_最高價_價格","現金殖利率_最高價_利率","現金殖利率_最低價_價格","現金殖利率_最低價_利率","file_type","source_file","download_success","download_timestamp","process_timestamp","stage1_process_timestamp"]
def num(v):
 try:return float(v)
 except (TypeError,ValueError):return 0.0
def build(stock_id,name,dividends,prices):
 d=pd.DataFrame(dividends); p=pd.DataFrame(prices)
 if d.empty:return pd.DataFrame(columns=COLUMNS)
 d["pay_date"]=pd.to_datetime(d.get("CashDividendPaymentDate"),errors="coerce")
 d["period_year"]=d.pay_date.dt.year
 d=d.dropna(subset=["period_year"]); d["period_year"]=d.period_year.astype(int)
 d["belong_year"]=d["year"].astype(str).str.extract(r"(\d+)")[0].astype(float).add(1911).astype("Int64")
 grouped=d.groupby("period_year",sort=True)
 if not p.empty:
  p["date"]=pd.to_datetime(p["date"],errors="coerce"); p["year"]=p.date.dt.year
 rows=[]; previous=np.nan; stamp=datetime.now().isoformat(timespec="seconds")
 for year,g in grouped:
  cash=g.CashEarningsDistribution.map(num).sum(); reserve=g.CashStatutorySurplus.map(num).sum(); stock=g.StockEarningsDistribution.map(num).sum(); stock_reserve=g.StockStatutorySurplus.map(num).sum(); total_cash=cash+reserve; total_stock=stock+stock_reserve; total=total_cash+total_stock
  row={"stock_code":str(stock_id).zfill(4),"company_name":name,"股利_發放_期間":str(year),"股利_所屬_期間":str(int(g.belong_year.dropna().iloc[0])) if g.belong_year.notna().any() else "-","現金股利_盈餘":cash,"現金股利_公積":reserve,"現金股利_合計":total_cash,"股票股利_盈餘":stock,"股票股利_公積":stock_reserve,"股票股利_合計":total_stock,"股利_合計":total,"填息_花費_日數":"-","填權_花費_日數":"-","股價_年度":str(year),"file_type":"DividendDetail","source_file":f"FinMind_API_TaiwanStockDividend_{str(stock_id).zfill(4)}","download_success":True,"download_timestamp":stamp,"process_timestamp":stamp,"stage1_process_timestamp":stamp}
  for c in ["現金殖利率_除息前_價格","現金殖利率_年均價_價格","現金殖利率_成交價_價格","現金殖利率_最高價_價格","現金殖利率_最低價_價格"]: row[c]=np.nan
  for c in ["現金殖利率_除息前_利率","現金殖利率_年均價_利率","現金殖利率_成交價_利率","現金殖利率_最高價_利率","現金殖利率_最低價_利率"]: row[c]=np.nan
  rows.append(row)
 return pd.DataFrame(rows,columns=COLUMNS)
def main():
 p=argparse.ArgumentParser();p.add_argument('--stock-id',default='2330');p.add_argument('--company-name',default='台積電');p.add_argument('--start-date',default='2018-01-01');p.add_argument('--end-date',default=(datetime.now()+timedelta(hours=8)).strftime('%Y-%m-%d'));p.add_argument('--output',default='financial/type1/raw_dividends_2330.csv');p.add_argument('--token',default=None);p.add_argument('--price-cache-dir',default=None);a=p.parse_args();rot=TokenRotator(a.token); d=fetch_data('TaiwanStockDividend',data_id=a.stock_id,start_date=a.start_date,end_date=a.end_date,token=rot); px=cached_price(a.stock_id,a.start_date,a.end_date,rot,a.price_cache_dir,fetch_data); out=build(a.stock_id,a.company_name,d.to_dict('records'),px.to_dict('records'));
 if out.empty:raise SystemExit('No dividend data available')
 Path(a.output).parent.mkdir(parents=True,exist_ok=True);out.to_csv(a.output,index=False,encoding='utf-8-sig');print(f'Wrote {len(out)} annual dividend rows to {a.output}')
if __name__=='__main__':main()
