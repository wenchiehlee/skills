#!/usr/bin/env python3
"""Fetch FinMind dividend events and export GoodInfo Type 19 schedule CSV."""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from fetch_to_csv import fetch_data
from token_env import TokenRotator
load_dotenv()
COLUMNS=["stock_code","company_name","股利_發放_期間","股利_所屬_期間","股東會_日期","除息_交易日","除息_參考_價","填息_完成日","填息_花費_日數","現金_股利_發放日","除權_交易日","除權_參考_價","填權_完成日","填權_花費_日數","現金股利_盈餘","現金股利_公積","現金股利_合計","股票股利_盈餘","股票股利_公積","股票股利_合計","股利_合計","file_type","source_file","download_success","download_timestamp","process_timestamp","stage1_process_timestamp"]
def num(v):
 try:return float(v)
 except (TypeError,ValueError):return np.nan
def main():
 p=argparse.ArgumentParser();p.add_argument('--stock-id',default='2330');p.add_argument('--company-name',default='台積電');p.add_argument('--start-date',default='2018-01-01');p.add_argument('--end-date',default=(datetime.now()+timedelta(hours=8)).strftime('%Y-%m-%d'));p.add_argument('--output',default='financial/type19/raw_dividend_schedule_2330.csv');p.add_argument('--token',default=None);a=p.parse_args();rot=TokenRotator(a.token)
 d=fetch_data('TaiwanStockDividend',data_id=a.stock_id,start_date=a.start_date,end_date=a.end_date,token=rot); result=fetch_data('TaiwanStockDividendResult',data_id=a.stock_id,start_date=a.start_date,end_date=a.end_date,token=rot); rdf=pd.DataFrame(result)
 if d.empty:raise SystemExit('No dividend schedule data available')
 stamp=datetime.now().isoformat(timespec='seconds'); rows=[]
 for _,r in d.iterrows():
  pay=str(r.get('CashDividendPaymentDate') or ''); year=pay[:4] if pay[:4].isdigit() else str(r.get('date',''))[:4]; roc=str(r.get('year','')).split('年')[0]; belong=str(int(roc)+1911) if roc.isdigit() else '-'; cash=num(r.get('CashEarningsDistribution'))+num(r.get('CashStatutorySurplus')); stock=num(r.get('StockEarningsDistribution'))+num(r.get('StockStatutorySurplus')); row={"stock_code":str(a.stock_id).zfill(4),"company_name":a.company_name,"股利_發放_期間":year,"股利_所屬_期間":belong,"股東會_日期":r.get('AnnouncementDate') or np.nan,"除息_交易日":r.get('CashExDividendTradingDate') or np.nan,"除息_參考_價":np.nan,"填息_完成日":np.nan,"填息_花費_日數":np.nan,"現金_股利_發放日":pay or np.nan,"除權_交易日":r.get('StockExDividendTradingDate') or np.nan,"除權_參考_價":np.nan,"填權_完成日":np.nan,"填權_花費_日數":np.nan,"現金股利_盈餘":num(r.get('CashEarningsDistribution')),"現金股利_公積":num(r.get('CashStatutorySurplus')),"現金股利_合計":cash,"股票股利_盈餘":num(r.get('StockEarningsDistribution')),"股票股利_公積":num(r.get('StockStatutorySurplus')),"股票股利_合計":stock,"股利_合計":cash+stock,"file_type":"Dividenschedule","source_file":f"FinMind_API_TaiwanStockDividend_{str(a.stock_id).zfill(4)}","download_success":True,"download_timestamp":stamp,"process_timestamp":stamp,"stage1_process_timestamp":stamp}; rows.append(row)
 pd.DataFrame(rows,columns=COLUMNS).to_csv(a.output,index=False,encoding='utf-8-sig');print(f'Wrote {len(rows)} dividend schedule rows to {a.output}')
if __name__=='__main__':main()
