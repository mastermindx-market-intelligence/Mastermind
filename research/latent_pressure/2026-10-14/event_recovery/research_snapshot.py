"""Read-only, historical research observation; no production forecast/call writer.
Example: --executions private/full_scan/executions.csv.gz --at 2026-10-05T14:00:00-04:00
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json
import pandas as pd
from event_study import NAMES,load,make_rows,clock,digest

def observe(executions:Path,as_of:str):
 t=pd.Timestamp(as_of)
 if t.tz is None:raise ValueError('as-of must include timezone')
 ns=int(t.tz_convert('UTC').value)
 if not clock('09:45')<=ns<=clock('15:45'):raise ValueError('outside qualified historical observation window')
 x=load(executions);prefix=x[x.send_ns<=ns];z,_=make_rows(prefix,labels=False);records=[]
 for name in NAMES:
  g=z[z.ticker==name] if len(z) else z
  if g.empty:
   records.append({'ticker':name,'status':'INSUFFICIENT_ELIGIBLE_HISTORY','forecast_probability':None});continue
  r=g.iloc[-1];records.append({'ticker':name,'status':'HISTORICAL_EXECUTION_OBSERVATION_ONLY','last_source_send_ns':str(int(r.decision_ns)),'last_sequence':str(int(r.sequence)),'print_age_seconds_at_cutoff':(ns-int(r.decision_ns))/1e9,'last20_observed_repeated_order_volume_share':float(r.repeat_volume),'last20_order_volume_hhi':float(r.hhi),'last20_previously_seen_fill_fraction':float(r.seen_fraction),'last20_execution_elapsed_seconds':float(__import__('numpy').expm1(r.logelapsed)),'observed_recent_print_direction':'UP' if r.median_momentum>0 else ('DOWN' if r.median_momentum<0 else 'SAME'),'pressure_direction':None,'remaining_hidden_inventory':None,'quote_recovery':None,'forecast_probability':None,'forecast_state':'NO_VALIDATED_INCREMENTAL_FORECAST'})
 return {'schema':'research_execution_observation.v1_NOT_PRODUCTION','as_of':t.isoformat(),'decision_cutoff_ns':str(ns),'created_at':datetime.now(timezone.utc).isoformat(),'source':'IEX HIST DEEP+ 2026-10-05','source_access':'READ_ONLY_EXISTING_ARCHIVE','clock':'IEX source send time, not end-user availability','input_sha256':digest(executions),'covered_tickers':NAMES,'records':records,'uncertainties':['IEX venue-only displayed executions','standard condition flag0 filter; no hidden T or external-venue coverage','no aggressor-side or NBBO observation','first observed execution is not order-entry time','quiet/stale prints do not imply an empty order book','full book adapter held unverified'],'authority':{'rotation_call_write':False,'live_alert':False,'rank':False,'size':False},'attribution':'Data provided for free by IEX. By accessing or using IEX Historical Data, you agree to the IEX Historical Data Terms of Use.','terms':'https://www.iex.io/legal/hist-data-terms'}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--executions',type=Path,required=True);p.add_argument('--at',required=True);a=p.parse_args();print(json.dumps(observe(a.executions,a.at),indent=2,allow_nan=False))
