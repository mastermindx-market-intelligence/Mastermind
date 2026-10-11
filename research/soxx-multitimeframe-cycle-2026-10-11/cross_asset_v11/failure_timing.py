"""How early can a close-confirmed 1H cycle-failure rule actually act?
Frozen entry/stop/time exit. Interval-censored stop timing; no signal optimisation.
"""
from pathlib import Path
import collections,csv,json,statistics,sys
HERE=Path(__file__).resolve().parent
PARENT=Path('/private/tmp/soxx_coherent_cycle_20261010_v10')
sys.path.insert(0,str(PARENT))
import frozen_audit as fa
import study_cycle as cy
from policies_v6 import make_panels
from cycle_failure import make_cycle_panels
SPEC=json.loads((HERE/'SPECIFICATION.json').read_text())
SRC={'SOXX':PARENT/'inputs/rth_original.json','SMH':PARENT/'inputs/SMH_60m.json',
     'QQQ':Path('/private/tmp/soxx_frozen_audit_20261010_v8/inputs/QQQ_60m.json')}
for t in SPEC['symbols_precommitted']:SRC[t]=HERE/'inputs'/(t+'.json')
SEMIS=set(SPEC['symbols_precommitted'][:8])
def band(hours):
 if hours<=1.01:return 'within_first_hour'
 if hours<=3.01:return 'hour_1_to_3'
 if hours<=6.51:return 'hour_3_to_6p5'
 if hours<=13.01:return 'hour_6p5_to_13'
 return 'after_13h'
def run():
 rows=[];aggregates=[];counts=collections.defaultdict(collections.Counter)
 for sym,path in SRC.items():
  ctx=fa.context_from_source(path)
  ctx['_panels']=make_panels(ctx);ctx['_cycle']=make_cycle_panels(ctx)
  gap=fa.source_audit(ctx)['gaps']
  signals,_=fa.v7.prepared(ctx,'3H_1H_pivot')
  trades,_=cy.execute(ctx,signals,'time',.25,gap)
  raw=ctx['raw'];clock=ctx['clock']
  for t in trades:
   if t.get('phase')!='year':continue
   if t.get('status')!='resolved':continue
   idx=t['entry_idx'];x=t['exit_idx']
   age=(clock[x+1]-clock[idx])/3600
   is_loss=t['net_pct']<0
   stop='stop' in t.get('reason','')
   gapstop=t.get('reason')=='stop_gap'
   first=band(age)
   record=dict(symbol=sym,group='semiconductor' if sym in SEMIS or sym in ('SOXX','SMH') else 'other',
               entry=t['entry_ET'],exit=t.get('exit_ET'),net=round(t['net_pct'],4),
               reason=t.get('reason'),observed_market_hours_to_exit=round(age,2),
               elapsed_band=first,loss=is_loss,stop=stop,gapstop=gapstop,
               potential_1h_confirm_before_stop=(not stop or age>1.01),
               potential_3h_guard_before_stop=(not stop or age>3.01))
   rows.append(record)
 for group in ('new_semis','all_semis','all_assets'):
  selected=[r for r in rows if (group=='all_assets' or group=='new_semis' and r['symbol'] in SEMIS
                                 or group=='all_semis' and r['group']=='semiconductor')]
  losses=[r for r in selected if r['loss']]
  stops=[r for r in selected if r['stop']]
  bandcounts=dict(collections.Counter(r['elapsed_band'] for r in stops))
  aggregates.append(dict(group=group,known=len(selected),losses=len(losses),stops=len(stops),
                         gap_stops=sum(r['gapstop'] for r in stops),
                         stop_within_first_1h=sum(r['observed_market_hours_to_exit']<=1.01 for r in stops),
                         stop_within_first_3h=sum(r['observed_market_hours_to_exit']<=3.01 for r in stops),
                         stop_by_old_guard_activation=sum(r['observed_market_hours_to_exit']<=3.01 for r in stops),
                         stop_bands=json.dumps(bandcounts,sort_keys=True),
                         median_stop_age_market_h=round(statistics.median(r['observed_market_hours_to_exit'] for r in stops),3) if stops else None))
 def csvwrite(path,rs):
  with path.open('w',newline='') as f:
   w=csv.DictWriter(f,rs[0].keys());w.writeheader();w.writerows(rs)
 csvwrite(HERE/'results/failure_timing_ledger.csv',rows)
 csvwrite(HERE/'results/failure_timing_summary.csv',aggregates)
 print('SUMMARY',aggregates)
 print('SOXX_LOSS_TIMES',[r for r in rows if r['symbol']=='SOXX' and r['loss']])
if __name__=='__main__':run()