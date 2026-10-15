"""Independent audit of the v11 frozen cross-asset research outputs."""
from pathlib import Path
import csv,json,hashlib,math,statistics,collections,datetime
R=Path(__file__).resolve().parent
RR=R/'results'
def readcsv(s):return list(csv.DictReader((RR/s).open()))
rep=json.loads((RR/'report.json').read_text())
spec=json.loads((R/'SPECIFICATION.json').read_text())
assert len(spec['symbols_precommitted'])==10
assert len(rep['assets'])==13 and not rep['errors']
inputs={}
for sym,md in rep['assets'].items():
 if sym=='SOXX':path=Path('/private/tmp/soxx_coherent_cycle_20261010_v10/inputs/rth_original.json')
 elif sym=='SMH':path=Path('/private/tmp/soxx_coherent_cycle_20261010_v10/inputs/SMH_60m.json')
 elif sym=='QQQ':path=Path('/private/tmp/soxx_frozen_audit_20261010_v8/inputs/QQQ_60m.json')
 else:path=R/'inputs'/(sym+'.json')
 data=path.read_bytes()
 assert hashlib.sha256(data).hexdigest()==md['sha']
 assert md['raw_points']>=3400
 inputs[sym]=md['sha']
major=readcsv('asset_strategy_summary.csv')
pair=readcsv('paired_entry_deltas.csv')
assert len(major)==78 and len(pair)==264
bymode={(r['symbol'],r['policy']):r for r in major}
assert abs(float(bymode['SOXX','old_guard']['mean'])-4.18474)<.0001
assert abs(float(bymode['SOXX','time']['mean'])-3.70352)<.0001
def newsemi(r):return r['symbol'] in spec['symbols_precommitted'][:8]
n_paired=[r for r in pair if newsemi(r) and r['mode']=='old_guard']
assert len(n_paired)==53
lim=readcsv('limit_feasibility_detail.csv')
lims=readcsv('limit_feasibility_summary.csv')
assert len(lim)==sum(int(x['opportunities']) for x in lims)
soxx=[r for r in lims if r['symbol']=='SOXX' and int(r['expiry_bars'])==2][0]
assert int(soxx['opportunities'])==10 and int(soxx['admitted_open'])==2 and int(soxx['clean_limit_touches_unproven'])==1
for r in lim:
 if r['status'] in ('at_open','opening_contact'):
  assert float(r['entry_at_open'])>float(r['pivot'])
  assert float(r['entry_at_open'])<=float(r['limit_price'])+1e-8
  assert 100*(1-float(r['stop'])/float(r['entry_at_open']))<=1.5001
 if r['status']=='clean_limit_touch_unproven_fill':
  assert r['entry_at_open']=='' and float(r['low'])<=float(r['limit_price'])+1e-8
clock=readcsv('failure_timing_ledger.csv')
early=[r for r in clock if newsemi(r) and r['stop']=='True']
assert len(early)==48
assert sum(float(x['observed_market_hours_to_exit'])<=1.01 for x in early)==14
assert sum(float(x['observed_market_hours_to_exit'])<=3.01 for x in early)==26
risk=readcsv('risk_normalized_trades.csv')
base=[r for r in risk if newsemi(r) and r['model']=='fixed_1p5' and r['mode']=='time']
assert len(base)==55
atrunits=[1.5/float(r['original_ATR_pct']) for r in base]
assert sum(v<1 for v in atrunits)==40
rs=readcsv('risk_normalized_summary.csv')
alt=[r for r in rs if newsemi(r) and r['model']=='ATR_1p0_cap3' and r['mode']=='time']
assert sum(int(r['resolved']) for r in alt)==50
assert sum(int(r['rejected']) for r in alt)==3
for r in risk:
 if r['status']=='resolved' and r['initial_risk_pct']:
  assert float(r['initial_risk_pct'])>0
  if r['model']=='fixed_1p5':assert abs(float(r['initial_risk_pct'])-1.5)<1e-8
  if r['model']=='ATR_1p0_cap3':assert float(r['initial_risk_pct'])<=3.00001
  if r['model']=='ATR_1p5_cap4':assert float(r['initial_risk_pct'])<=4.00001
  # Returns divided by initial risk; diagnostic ratio, not risk-sized portfolio.
  assert abs(float(r['net_R'])-float(r['net_pct'])/float(r['initial_risk_pct']))<1e-8
kl=json.loads((R/'inputs/KLAC.json').read_bytes())['chart']['result'][0]
assert len(kl['events']['splits'])==1
assert next(iter(kl['events']['splits'].values()))['splitRatio']=='10:1'
cl=kl['indicators']['quote'][0]['close']
assert max(abs(cl[i]/cl[i-1]-1) for i in range(1,len(cl)) if cl[i] and cl[i-1])<.4
proof={'v11':'frozen peer transfer, limit feasibility, cycle-stop timing, ATR risk alternatives',
       'files_verified':len(inputs),'source_sha256':inputs,'asset_strategy_rows':len(major),
       'paired_trade_rows':len(pair),'new_semi_matched':len(n_paired),
       'risk_checked_rows':len(risk),'limit_checked_rows':len(lim),
       'stops_new_semi':len(early),'within_first_hour':14,'by_3h':26,
       'one_hour_atr_stop_under1ATR':40,'ATR1_cap3_admitted':50,'ATR1_cap3_rejected':3,
       'KLAC_split_ratio':'10:1','no_quote_or_overnight_claim':True,
       'no_production_or_trade_change':True,
       'statistical_note':'Cross-asset market factor and calendar weeks not independent; repeated inspected period. Rejected opportunities counted separately.',
       'result_sha256':hashlib.sha256((RR/'report.json').read_bytes()).hexdigest()}
path=RR/'VERIFICATION.json'
if path.exists():raise RuntimeError('Target exists; no overwrite without reconcile')
path.write_text(json.dumps(proof,indent=2))
print('PASS',json.dumps({k:proof[k] for k in ['files_verified','asset_strategy_rows','paired_trade_rows','new_semi_matched','risk_checked_rows','limit_checked_rows','stops_new_semi','one_hour_atr_stop_under1ATR','ATR1_cap3_admitted']}))
print('VERIFICATION_SHA256',hashlib.sha256(path.read_bytes()).hexdigest())