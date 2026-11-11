"""Frozen-entry volatility-normalised emergency-stop falsification.
Four predeclared rules; no signal or indicator refit. All study-only.
"""
from pathlib import Path
import collections,csv,datetime as dt,hashlib,json,statistics,sys,math
ROOT=Path(__file__).resolve().parent
PARENT=Path('/private/tmp/soxx_coherent_cycle_20261010_v10')
sys.path.insert(0,str(PARENT))
import frozen_audit as fa
import study_cycle as cy
from cycle_failure import make_cycle_panels
from policies_v6 import make_panels
BASKET=json.loads((ROOT/'SPECIFICATION.json').read_text())['symbols_precommitted'][:8]
SYMBOLS=['SOXX','SMH']+BASKET
SOURCE={'SOXX':PARENT/'inputs/rth_original.json','SMH':PARENT/'inputs/SMH_60m.json'}
SOURCE.update({s:ROOT/'inputs'/(s+'.json') for s in BASKET})
MODELS={
  'fixed_1p5':dict(rule='fixed',scalar=1.5,cap=1.5),
  'ATR_1p0_cap3':dict(rule='atr',scalar=1.0,cap=3.0),
  'ATR_1p5_cap4':dict(rule='atr',scalar=1.5,cap=4.0),
  'max_fixed_1p5_or_ATR1_cap3':dict(rule='max',scalar=1.0,cap=3.0),
}
MODES=('time','old_guard')
def choose_risk(c,ctx,model):
 px=ctx['raw'][c['entry']]['open'];a=c['atr']
 if not (a and a>0 and px>0):return None,None
 ar=100*a/px
 if model['rule']=='fixed':r=model['scalar']
 elif model['rule']=='atr':r=ar*model['scalar']
 else:r=max(1.5,ar*model['scalar'])
 if not .4<=r<=model['cap']:return None,r
 return px*(1-r/100),r
def mean(xs):return round(statistics.mean(xs),4) if xs else None
def process():
 spec={'models':MODELS,'exits':MODES,'universe_precommitted':SYMBOLS,
  'rules':'As-of ATR at frozen signal; no widening an open stop, no extra shares or notional optimisation. Same 52 regular-hour expiry, 25% at 2% for all; count unfilled/rejected opportunities as zero; no price/quote proof',
  'retrospective':True}
 f=ROOT/'RISK_SPECIFICATION.json'
 if f.exists():assert json.loads(f.read_text())==spec
 else:f.write_text(json.dumps(spec,indent=2))
 allrows=[];summary=[];matched=[];by_asset={}
 for symbol in SYMBOLS:
  ctx=fa.context_from_source(SOURCE[symbol])
  ctx['_panels']=make_panels(ctx);ctx['_cycle']=make_cycle_panels(ctx)
  gaps=fa.source_audit(ctx)['gaps']
  origins,_=fa.v7.prepared(ctx,'3H_1H_pivot')
  fixed=[]
  for c in origins:
   if c['phase']=='year':fixed.append(c)
  by_asset[symbol]=len(fixed)
  book={}
  for name,model in MODELS.items():
   selected=[];skipped=[]
   for c in origins:
    stop,risk=choose_risk(c,ctx,model)
    if stop is None:skipped.append(c);continue
    selected.append(dict(c,stop=stop,risk_at_entry=risk))
   for mode in MODES:
    ts,_=cy.execute(ctx,selected,mode,.25,gaps,shadow=True)
    # All frozen opportunities including skipped contribute to opportunity-level arithmetic.
    years=[t for t in ts if t['phase']=='year']
    known={x['entry_ET']:x for x in years if x['status']=='resolved'}
    for c in fixed:
     t=known.get(c['entry_ET'])
     skipped_this=c['entry_ET'] in set(z['entry_ET'] for z in skipped if z['phase']=='year')
     if not skipped_this and t is None:
      status=next((x['status'] for x in years if x['entry_ET']==c['entry_ET']),'missing')
     else:status='risk_cap_rejected' if skipped_this else t['status']
     ret=t['net_pct'] if t else (0 if skipped_this else None)
     risk=t['risk_at_entry'] if t and 'risk_at_entry' in t else (choose_risk(c,ctx,model)[1] if not skipped_this else None)
     allrows.append(dict(symbol=symbol,group='new_semis' if symbol in BASKET else 'existing',
       entry=c['entry_ET'],model=name,mode=mode,status=status,
       net_pct=ret,initial_risk_pct=risk,net_R=ret/risk if ret is not None and risk else None,
       original_ATR_pct=100*c['atr']/ctx['raw'][c['entry']]['open']))
    use=[r for r in allrows if r['symbol']==symbol and r['model']==name and r['mode']==mode]
    eligible=[r for r in use if r['net_pct'] is not None]
    known_only=[r for r in eligible if r['status']=='resolved']
    summary.append(dict(symbol=symbol,model=name,mode=mode,
      original_opportunities=len(fixed),resolved=len(known_only),rejected=sum(r['status']=='risk_cap_rejected' for r in use),
      unknown=sum(r['net_pct'] is None for r in use),wins=sum(r['net_pct']>0 for r in known_only),
      raw_mean=mean([r['net_pct'] for r in known_only]),
      opportunity_mean=mean([r['net_pct'] for r in eligible]),
      median_R=mean([r['net_R'] for r in known_only if r['net_R'] is not None]),
      mean_risk=mean([r['initial_risk_pct'] for r in known_only])))
 # Paired risk variants at the same symbol, episode, and indicator-exit setting.
 index={(r['symbol'],r['entry'],r['model'],r['mode']):r for r in allrows}
 for symbol in SYMBOLS:
  for c in [r for r in allrows if r['symbol']==symbol and r['model']=='fixed_1p5']:
   base=c
   for alt in MODELS:
    if alt=='fixed_1p5':continue
    z=index[(symbol,c['entry'],alt,c['mode'])]
    if z['net_pct'] is None or base['net_pct'] is None:continue
    d=z['net_pct']-base['net_pct']
    d0=dt.datetime.fromisoformat(c['entry']).date()
    week=(d0-dt.timedelta(days=d0.weekday())).isoformat()
    matched.append(dict(symbol=symbol,group='new_semis' if symbol in BASKET else 'existing',
      week=week,entry=c['entry'],mode=c['mode'],model=alt,base_pct=base['net_pct'],
      alternative_pct=z['net_pct'],delta=d,
      initial_risk_pct=z['initial_risk_pct'],base_risk_pct=base['initial_risk_pct'],
      alternative_rejected=z['status']=='risk_cap_rejected',
      base_winner=base['net_pct']>0,improved=d>0.00001,harmed=d<-.00001))
 def write(name,records):
  with (ROOT/'results'/name).open('w',newline='') as f:
   fields=list(dict.fromkeys(k for x in records for k in x))
   w=csv.DictWriter(f,fields);w.writeheader();w.writerows(records)
 write('risk_normalized_trades.csv',allrows)
 write('risk_normalized_summary.csv',summary)
 write('risk_normalized_pairs.csv',matched)
 print('TOTAL_SIGNAL_COUNTS',by_asset)
 for alt in MODELS:
  for mode in MODES:
   xx=[r for r in matched if r['group']=='new_semis' and r['mode']==mode and r['model']==alt]
   if not xx:continue
   print('PAIRED',alt,mode,'n',len(xx),'delta_mean',mean([r['delta'] for r in xx]),
    'improved',sum(r['improved'] for r in xx),'harmed',sum(r['harmed'] for r in xx),
    'winner_harmed',sum(r['base_winner'] and r['harmed'] for r in xx),
    'avg_risk',mean([r['initial_risk_pct'] for r in xx if r['initial_risk_pct']]))
 for model in MODELS:
  for mode in MODES:
   s=[r for r in summary if r['symbol'] in BASKET and r['model']==model and r['mode']==mode]
   print('SUMMARIES',model,mode,'known',sum(r['resolved'] for r in s),
    'rejects',sum(r['rejected'] for r in s),
    'asset_return_means',[round(r['raw_mean'],3) if r['raw_mean'] is not None else None for r in s])
 print('SHA',hashlib.sha256((ROOT/'results/risk_normalized_pairs.csv').read_bytes()).hexdigest())
if __name__=='__main__':process()