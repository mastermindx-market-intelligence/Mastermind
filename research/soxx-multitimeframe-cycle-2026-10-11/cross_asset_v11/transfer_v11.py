"""Freeze v9/v10 SOXX rules and test unchanged across semiconductor constituents + controls.
No optimisation, no stock selection after viewing outcomes, no orders or deployment.
"""
import collections,csv,datetime as dt,hashlib,json,math,random,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PARENT=Path('/private/tmp/soxx_coherent_cycle_20261010_v10')
sys.path.insert(0,str(PARENT))
import frozen_audit as a
import study_cycle as cy
import study_coherent as co
import tactical_admission as tac
from policies_v6 import make_panels
from cycle_failure import make_cycle_panels
BASKET=json.loads((ROOT/'SPECIFICATION.json').read_text())['symbols_precommitted']
SEMI=set('AMD AVGO MU INTC NVDA AMAT LRCX KLAC'.split())
EXISTING={'SOXX':PARENT/'inputs/rth_original.json','SMH':PARENT/'inputs/SMH_60m.json',
          'QQQ':Path('/private/tmp/soxx_frozen_audit_20261010_v8/inputs/QQQ_60m.json')}
POLICIES=('time','old_guard','fast_weak_control','momentum_reset')
PHASES=('prior','year')
def summary(result):
    xs=[x for x in result if x.get('status')=='resolved']
    yr=[r for r in result if r.get('phase')=='year']
    known=[r for r in yr if r.get('status')=='resolved']
    return dict(candidates=len(yr),resolved=len(known),
                statuses=dict(collections.Counter(r.get('status') for r in yr)),
                mean=round(statistics.mean(r['net_pct'] for r in known),5) if known else None,
                win=round(100*sum(r['net_pct']>0 for r in known)/len(known),1) if known else None,
                sum_net=round(sum(r['net_pct'] for r in known),4) if known else 0)
def relevant_metadata(path):
    data=json.loads(path.read_bytes())['chart']['result'][0]
    ev=data.get('events',{}).get('splits',{})
    q=data['indicators']['quote'][0]
    return dict(sha=hashlib.sha256(path.read_bytes()).hexdigest(),raw_points=len(data['timestamp']),
                splits=[{'date':dt.datetime.fromtimestamp(int(k),dt.timezone.utc).isoformat(),
                        'ratio':v.get('splitRatio')} for k,v in ev.items()],
                zero_close=sum(v is None or v==0 for v in q['close']))
def safe_mean(xs):
    return round(statistics.mean(xs),5) if xs else None
def run():
    outputs=[];pairs=[];ledgers=[];metadata={};failures=[]
    symbols=['SOXX','SMH','QQQ']+list(BASKET)
    for symbol in symbols:
        path=EXISTING.get(symbol,ROOT/'inputs'/(symbol+'.json'))
        if not path.exists():failures.append([symbol,'SOURCE_MISSING']);continue
        try:
            md=relevant_metadata(path)
            ctx=a.context_from_source(path)
            if len(ctx['raw'])<2900 or ctx['raw'][-1]['day']<'2026-10-08':
                raise RuntimeError('COVERAGE_INSUFFICIENT')
            ctx['_panels']=make_panels(ctx);ctx['_cycle']=make_cycle_panels(ctx)
            gaps=a.source_audit(ctx)['gaps']
            origins,_=a.v7.prepared(ctx,'3H_1H_pivot')
            metadata[symbol]=dict(**md,qualified_rows=len(ctx['raw']),origin_signals=len(origins),
                                  audit_gap_count=len(gaps),class_name='semi' if symbol in SEMI or symbol in ('SOXX','SMH') else 'control')
            if not origins:
                print('NO_SIGNALS',symbol,flush=True);continue
            sets={}
            for mode in POLICIES:
                t,_=cy.execute(ctx,origins,mode,.25,gaps)
                sets[mode]=t
                outputs.append(dict(symbol=symbol,asset_type=metadata[symbol]['class_name'],policy=mode,**summary(t)))
                for z in t:ledgers.append(dict(symbol=symbol,policy=mode,phase=z.get('phase'),entry_ET=z.get('entry_ET'),status=z.get('status'),net_pct=z.get('net_pct'),exit_ET=z.get('exit_ET'),reason=z.get('reason')))
            # Admission models: retain non-admissions in denominator (as zero), compare to originals.
            for model in ('strict_structure','pivot_retest'):
                selected,attempts=co.evaluate(ctx,origins,model,'defended_stop52',.25,gaps,cap=1.5,selector=tac.choose)
                outputs.append(dict(symbol=symbol,asset_type=metadata[symbol]['class_name'],policy=model,**summary(selected),
                    skipped=sum(r.get('status')=='not_admitted' for r in selected),
                    opportunity_mean=safe_mean([r.get('net_pct',0) for r in selected if r.get('status') in ('resolved','not_admitted')]) ))
                for z in selected:ledgers.append(dict(symbol=symbol,policy=model,phase=z.get('phase'),entry_ET=z.get('entry_ET'),status=z.get('status'),net_pct=z.get('net_pct'),exit_ET=z.get('exit_ET'),reason=z.get('reason')))
            # Matched same entry, same exposure fraction, same 52h max: compare cycle decisions with time reference.
            ref={x['entry_ET']:x for x in sets['time'] if x.get('phase')=='year'}
            for mode in POLICIES[1:]:
                for target in sets[mode]:
                    if target.get('phase')!='year':continue
                    base=ref.get(target['entry_ET'])
                    if not base or target.get('status')!='resolved' or base.get('status')!='resolved':continue
                    delta=target['net_pct']-base['net_pct']
                    local=dt.datetime.fromisoformat(target['entry_ET'])
                    start=local.date()-dt.timedelta(days=local.weekday())
                    pairs.append(dict(symbol=symbol,asset_type=metadata[symbol]['class_name'],mode=mode,
                        entry_ET=target['entry_ET'],week=start.isoformat(),
                        base=round(base['net_pct'],5),candidate=round(target['net_pct'],5),delta=round(delta,5),
                        helped=delta>0.000001,harmed=delta<-.000001,
                        winner_harmed=base['net_pct']>0 and delta<-.000001))
            print('EVALUATED',symbol,'entries',len(origins),'year',outputs[-6].get('candidates'),
                  'old_guard',outputs[-5].get('mean'),'pivot_admitted',outputs[-1].get('resolved'),flush=True)
        except Exception as e:
            failures.append([symbol,type(e).__name__,str(e)[:200]])
            print('FAILED_MODEL',symbol,repr(e)[:190],flush=True)
    # Month/week block bootstrap: preserve correlated asset outcomes in the same week.
    random.seed(971)
    cluster_stats=[]
    for mode in POLICIES[1:]:
        for category in ('new_semis','new_controls','all_semis','all_assets'):
            z=[r for r in pairs if r['mode']==mode and
               (category=='all_assets' or
                category=='new_semis' and r['symbol'] in SEMI or
                category=='new_controls' and r['symbol'] in ('SPY','XLV') or
                category=='all_semis' and r['asset_type']=='semi')]
            weeks=collections.defaultdict(list)
            for t in z:weeks[t['week']].append(t['delta'])
            pool=list(weeks.values());deltas=[t['delta'] for t in z]
            bootstrap=[]
            if len(pool)>2:
                for _ in range(3000):
                    draws=[random.choice(pool) for _ in pool]
                    bootstrap.append(sum(map(sum,draws))/sum(map(len,draws)))
                bootstrap.sort()
            cluster_stats.append(dict(mode=mode,category=category,n=len(z),
                unique_assets=len(set(t['symbol'] for t in z)),weeks=len(pool),
                lift_mean=safe_mean(deltas),positive=sum(x>0 for x in deltas),
                negative=sum(x<0 for x in deltas),
                sum_avoided=round(sum(max(0,x) for x in deltas),4),
                sum_sacrificed=round(-sum(min(0,x) for x in deltas),4),
                winner_harmed=sum(t['winner_harmed'] for t in z),
                week_bootstrap95=[round(bootstrap[int(.025*len(bootstrap))],4),round(bootstrap[int(.975*len(bootstrap))],4)] if bootstrap else None))
    out=ROOT/'results'
    def write_csv(name,records):
        if not records:return
        fields=list(dict.fromkeys(k for r in records for k in r))
        with (out/name).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(records)
    write_csv('asset_strategy_summary.csv',outputs)
    write_csv('paired_entry_deltas.csv',pairs)
    write_csv('paired_cluster_diagnostics.csv',cluster_stats)
    write_csv('asset_trade_ledger.csv',ledgers)
    report=dict(spec=json.loads((ROOT/'SPECIFICATION.json').read_text()),assets=metadata,
                errors=failures,asset_rows=len(outputs),pairs=len(pairs),cluster_stats=cluster_stats)
    (out/'report.json').write_text(json.dumps(report,indent=2))
    print('TOTAL',len(metadata),'symbols','strategy_rows',len(outputs),'paired_trade_rows',len(pairs),'failed',failures)
    for z in cluster_stats:print('CLUSTER',z)
    print('REPORT_SHA',hashlib.sha256((out/'report.json').read_bytes()).hexdigest())
if __name__=='__main__':run()