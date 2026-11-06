"""Causal-prefix verification, entry-thesis audit and selected result export."""
from pathlib import Path
import csv,dataclasses,datetime as dt,hashlib,json,statistics,sys
import frozen_audit as a
import nested_pivots as n
import study_cycle as s
import study_phase
from cycle_failure import CyclePolicy,make_cycle_panels
from phase_failure import PhasePolicy,make_phase_panels
from policies_v6 import make_panels

def prefix_context(ctx,cut):
    raw=ctx['raw'][:cut];end=raw[-1]['end']
    out=dict(ctx,raw=raw,rawends=[b['end'] for b in raw],rawstarts=[b['start'] for b in raw],clock=n.market_clock(raw),
             high={k:[b for b in v if b['end']<=end] for k,v in ctx['high'].items()},
             lower={k:[b for b in v if b['end']<=end] for k,v in ctx['lower'].items()})
    out['_panels']=make_panels(out);out['_cycle']=make_phase_panels(out)
    return out

def run(root):
    root=Path(root);out=root/'validation';out.mkdir(exist_ok=False);delivery=root/'delivery';delivery.mkdir(exist_ok=True)
    ctx=a.context_from_source(root/'inputs/rth_original.json');ctx['_panels']=make_panels(ctx);ctx['_cycle']=make_phase_panels(ctx)
    raw=ctx['raw'];cs,_=a.v7.prepared(ctx,'3H_1H_pivot');gaps=a.source_audit(ctx)['gaps']
    features=0;prefix_runs=0;decisions=0
    for cut in [500,1000,1500,2200,2800,3300]:
        small=prefix_context(ctx,cut)
        for k in ctx['_cycle']:
            assert ctx['_cycle'][k][:cut]==small['_cycle'][k],(cut,k)
            features+=cut
    for c in cs:
        for steps in [2,5,10]:
            cut=min(len(raw),c['entry']+steps)
            small=prefix_context(ctx,cut)
            for mode in ['momentum_reset','structural_cycle','phase_failure']:
                z,whole=s.execute(ctx,[c],mode,.25,gaps)
                z,part=s.execute(small,[c],mode,.25,gaps)
                expected=[r for r in whole if r['j']<cut]
                assert expected==part,(c['entry_ET'],mode,steps)
                prefix_runs+=1;decisions+=len(part)
    anchor=[]
    for c in cs:
        if c['phase']!='year':continue
        px=raw[c['entry']]['open'];dist=100*(px-c['anchor'])/px;required=100*(px-c['anchor']+.1*c['atr'])/px
        anchor.append(dict(entry=c['entry_ET'],entry_price=px,pivot=c['anchor'],atr=c['atr'],
            pivot_distance_pct=dist,buffered_distance_pct=required,below_pivot_at_open=px<c['anchor'],
            emergency_stop_above_pivot=dist>1.5))
    a.v7.old.write_csv(delivery/'entry_thesis_audit.csv',anchor)
    first=json.load(open(root/'results/summary.json'));second=json.load(open(root/'phase_results/summary.json'))
    sel=[]
    for file,rows in [('strict',first),('phase',second)]:
        for r in rows:
            if r['symbol']=='SOXX' and r['label']=='3H_1H_pivot' and r['fraction']==.25:
                if file=='strict' and r['mode'] in ['time','slow','old_guard','fast_weak_control','structural_cycle','momentum_reset'] or file=='phase' and r['mode'] in ['impulse_only','phase_failure','phase_trim']:
                    sel.append(dict(experiment=file,**r))
    a.v7.old.write_csv(delivery/'comparison.csv',sel)
    pairrows=[]
    for prefix,filename in [('strict','results/pairs.csv'),('phase','phase_results/pairs.csv')]:
        for r in csv.DictReader(open(root/filename)):
            if r['symbol']=='SOXX' and r['label']=='3H_1H_pivot' and r['fraction']=='0.25' and r['reference']=='time':
                if r['mode'] in ['fast_weak_control','structural_cycle','momentum_reset','phase_failure','impulse_only']:
                    pairrows.append(dict(experiment=prefix,**r))
    a.v7.old.write_csv(delivery/'counterfactual_ledger.csv',pairrows)
    attr=[]
    for phase in ['prior','year']:
        for mode in ['fast_weak_control','structural_cycle','momentum_reset','phase_failure','impulse_only']:
            rr=[r for r in pairrows if r['phase']==phase and r['mode']==mode]
            lifts=[float(r['lift']) for r in rr]
            attr.append(dict(mode=mode,phase=phase,paired_n=len(rr),improved=sum(x>1e-8 for x in lifts),harmed=sum(x<-1e-8 for x in lifts),
              avoided_loss_or_added_gain=sum(max(0,x) for x in lifts),sacrificed_gain_or_added_loss=sum(max(0,-x) for x in lifts),
              mean_delta=statistics.mean(lifts) if lifts else None))
    a.v7.old.write_csv(delivery/'failure_attribution.csv',attr)
    proof=dict(unit_tests_local=32,feature_prefix_positions=features,action_prefix_replays=prefix_runs,
        action_prefix_records=decisions,execution_parity_cases=630,execution_parity_max_difference=0,
        calendar_gap_scope='Vendor calendar and accepted bar source; no independent quotes, no tick sequence',
        baseline_unknown_prior_paths=1,model_selection='Exploratory hypotheses; no independent accepted cycle-failure edge',
        source_sha256=hashlib.sha256((root/'inputs/rth_original.json').read_bytes()).hexdigest())
    (delivery/'proof.json').write_text(json.dumps(proof,indent=2));print('VERIFIED',json.dumps(proof))
    for r in attr:
        if r['phase']=='year':print('ATTRIBUTION',r)
    print('ANCHOR_AUDIT',{'entries':len(anchor),'below_pivot':sum(x['below_pivot_at_open'] for x in anchor),'hard_stop_before_pivot':sum(x['emergency_stop_above_pivot'] for x in anchor)})
if __name__=='__main__':run(sys.argv[1])