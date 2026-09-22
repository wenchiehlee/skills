#!/usr/bin/env python3
"""Build GoodInfo K-chart flow CSVs (Types 8, 12, 17 and 18) from FinMind."""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from fetch_to_csv import fetch_data
from price_cache import cached_dataset, cached_price
from token_env import TokenRotator
load_dotenv()

def eps_series(records):
 d=pd.DataFrame(records)
 if d.empty or 'type' not in d:return pd.DataFrame(columns=['date','eps'])
 d=d[d.type.astype(str).str.upper().eq('EPS')].copy(); d['date']=pd.to_datetime(d.date,errors='coerce'); d['eps']=pd.to_numeric(d.value,errors='coerce'); d=d.dropna(subset=['date','eps']).sort_values('date')
 if d.empty:return pd.DataFrame(columns=['date','eps'])
 d=d.groupby('date',as_index=False).eps.sum(); d['eps']=d.eps.rolling(4,min_periods=1).sum(); return d

def build(stock_id,name,prices,pers,financials,frequency,kind):
 px=pd.DataFrame(prices); pe=pd.DataFrame(pers); eps=eps_series(financials)
 if px.empty:return pd.DataFrame()
 px['date']=pd.to_datetime(px.date,errors='coerce'); px=px.dropna(subset=['date']).sort_values('date')
 if frequency=='daily': px['_period']=px.date.dt.strftime('%Y-%m-%d')
 elif frequency=='monthly': px['_period']=px.date.dt.strftime('%yM%m')
 else:
  px['_week']=px.date-pd.to_timedelta(px.date.dt.weekday,unit='D'); px['_period']=px._week.map(lambda x:f'{x.isocalendar().year%100:02d}W{x.isocalendar().week:02d}')
 groups=px.groupby('_period',sort=True); pe['date']=pd.to_datetime(pe.get('date'),errors='coerce') if not pe.empty else pd.Series(dtype='datetime64[ns]'); pe['PER']=pd.to_numeric(pe.get('PER'),errors='coerce') if not pe.empty else pd.Series(dtype=float); pe=pe.dropna(subset=['date']).sort_values('date') if not pe.empty else pe
 multipliers=(9,11,13,15,17,19) if frequency=='monthly' else (15,18,21,24,27,30)
 rows=[]; prev=np.nan; stamp=datetime.now().isoformat(timespec='seconds')
 for period,g in groups:
  last=g.iloc[-1]; close=float(last.close); change=close-prev if pd.notna(prev) else np.nan
  if frequency=='daily': label=period
  else: label=period
  last_date=last.date; p=pe[pe.date<=last_date].iloc[-1] if not pe.empty and (pe.date<=last_date).any() else None; per=float(p.PER) if p is not None and pd.notna(p.PER) else np.nan
  e=eps[eps.date<=last_date].iloc[-1].eps if not eps.empty and (eps.date<=last_date).any() else np.nan
  row={'stock_code':str(stock_id).zfill(4),'company_name':name,('交易_日期' if frequency=='daily' else '交易_月份' if frequency=='monthly' else '交易_週別'):label,'收盤價_元':close,'漲跌價_元':change,'漲跌幅_pct':f'{change/prev*100:.2f}%' if pd.notna(change) and prev else np.nan,'河流圖_eps_元':e,'目前_per_倍':per,'file_type':kind,'source_file':f'FinMind_API_TaiwanStockPrice_{str(stock_id).zfill(4)}','download_success':True,'download_timestamp':stamp,'process_timestamp':stamp,'stage1_process_timestamp':stamp}
  for m in multipliers: row[f'本益比試算價格_{m}x_元']=round(e*m,2) if pd.notna(e) else np.nan
  rows.append(row); prev=close
 if not rows:
  return pd.DataFrame()
 key = '交易_日期' if frequency == 'daily' else '交易_月份' if frequency == 'monthly' else '交易_週別'
 target_cols = [f'本益比試算價格_{m}x_元' for m in multipliers]
 meta = ['file_type','source_file','download_success','download_timestamp','process_timestamp','stage1_process_timestamp']
 return pd.DataFrame(rows)[[
  'stock_code','company_name',key,'收盤價_元','漲跌價_元','漲跌幅_pct','河流圖_eps_元','目前_per_倍',*target_cols,*meta
 ]]

def main():
 p=argparse.ArgumentParser(); p.add_argument('--type',type=int,choices=[8,12,17,18],required=True); p.add_argument('--stock-id',default='2330'); p.add_argument('--company-name',default='台積電'); p.add_argument('--start-date',default='2021-01-01'); p.add_argument('--end-date',default=(datetime.now()+timedelta(hours=8)).strftime('%Y-%m-%d')); p.add_argument('--output'); p.add_argument('--token',default=None); p.add_argument('--price-cache-dir',default=None); a=p.parse_args(); rot=TokenRotator(a.token); freq='daily' if a.type==18 else 'monthly' if a.type==12 else 'weekly'; kind={8:'ShowK_ChartFlow',12:'ShowMonthlyK_ChartFlow',17:'ShowWeeklyK_ChartFlow',18:'ShowDailyK_ChartFlow'}[a.type]
 prices=cached_price(a.stock_id,a.start_date,a.end_date,rot,a.price_cache_dir,fetch_data); pers=cached_dataset('TaiwanStockPER',a.stock_id,a.start_date,a.end_date,rot,a.price_cache_dir,fetch_data); fin=cached_dataset('TaiwanStockFinancialStatements',a.stock_id,a.start_date,a.end_date,rot,a.price_cache_dir,fetch_data)
 out=build(a.stock_id,a.company_name,prices.to_dict('records'),pers.to_dict('records'),fin.to_dict('records'),freq,kind)
 if out.empty:raise SystemExit('No price data available')
 if not a.output:a.output=f'financial/type{a.type}/raw_'+('monthly_flow' if a.type==12 else 'daily_k_chart_flow' if a.type==18 else 'weekly_k_chart_flow')+f'_{a.stock_id}.csv'
 Path(a.output).parent.mkdir(parents=True,exist_ok=True); out.to_csv(a.output,index=False,encoding='utf-8-sig'); print(f'Wrote {len(out)} rows to {a.output}')
if __name__=='__main__':main()
