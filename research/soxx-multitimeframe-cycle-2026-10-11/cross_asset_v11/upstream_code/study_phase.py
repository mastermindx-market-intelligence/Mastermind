"""Phase-aware cycle failure vs fixed benchmarks; no parameter selection."""
from pathlib import Path
import collections,json,hashlib,statistics,sys
import study_cycle as s
from phase_failure import PhasePolicy,make_phase_panels,PHASE_MODES
from time_nextopen import TimedDecision
from policies_v6 import Policy,make_panels
import frozen_audit as a

_original=s.make_policy
def policy_factory(ctx,c,mode,clock=52,buffer=.1):
    base=mode.removesuffix('+slow')
    if base not in PHASE_MODES:return _original(ctx,c,mode,clock,buffer)
    p=PhasePolicy(base,ctx,ctx['_cycle'],c,buffer);monitor=p
    if mode.endswith('+slow'):p=s.Joined(p,Policy(dict(kind='legacy_joint',tf=180),ctx['raw'],ctx['_panels'],c['entry']))
    return TimedDecision(p,clock),monitor
s.make_policy=policy_factory
MODES=['time','slow','old_guard','impulse_only','phase_failure','phase_trim','impulse_only+slow','phase_failure+slow','phase_trim+slow']

def run(root):
    root=Path(root);out=root/'phase_results';out.mkdir(exist_ok=False)
    (out/'specification.json').write_text(json.dumps(dict(modes=MODES,lower_macd=[5,13,4],higher_macd=[8,21,5],
        initial_impulse='closed gain >=0.5 entry ATR and <2 ATR before established higher-low, followed by >half giveback, two-bar low breach and fast weakness',
        established='confirmed higher low followed by new closing high; thereafter require break of defended low with fast and parent histogram falling',
        basis='Task-specific hypotheses; all data already inspected; no best-fit assertion'),indent=2))
    summaries=[];trades=[];records=[];pairs=[];pareport=[];parity=[]
    for symbol,source,label in [('SOXX','rth_original.json','3H_1H_pivot'),('SOXX','rth_original.json','anyHTF_1H_pivot'),('SMH','SMH_60m.json','3H_1H_pivot')]:
        ctx=a.context_from_source(root/'inputs'/source);ctx['_panels']=make_panels(ctx);ctx['_cycle']=make_phase_panels(ctx)
        cs,_=a.v7.prepared(ctx,label);gaps=a.source_audit(ctx)['gaps']
        for fraction in [0,.25]:
            book={}
            for mode in MODES:
                ts,rr=s.execute(ctx,cs,mode,fraction,gaps);book[mode]=ts
                for phase in ['prior','year']:
                    subset=[r for r in ts if r['phase']==phase]
                    summaries.append(dict(symbol=symbol,label=label,mode=mode,fraction=fraction,phase=phase,**a.v7.summarize(subset)))
                for t in ts:trades.append(dict(symbol=symbol,label=label,**{k:v for k,v in t.items() if k not in ['marks','actions','fills']}))
                if symbol=='SOXX' and label=='3H_1H_pivot':
                    records.extend(rr)
                    repeat,_=s.execute(ctx,cs,mode,fraction,gaps,engine='engine')
                    for x,y in zip(ts,repeat):
                        if 'net_pct' in x and 'net_pct' in y:parity.append(abs(x['net_pct']-y['net_pct']))
            for mode in MODES:
                for ref in ['time','slow','old_guard']:
                    for phase in ['prior','year']:
                        pp,z=s.pair([t for t in book[mode] if t['phase']==phase],[t for t in book[ref] if t['phase']==phase])
                        pareport.append(dict(symbol=symbol,label=label,mode=mode,reference=ref,fraction=fraction,phase=phase,**pp))
                        for r in z:pairs.append(dict(symbol=symbol,label=label,mode=mode,reference=ref,fraction=fraction,phase=phase,**r))
    for name,rows in [('summary',summaries),('trades',trades),('records',records),('paired_summary',pareport),('pairs',pairs)]:
        a.v7.old.write_csv(out/(name+'.csv'),rows)
    (out/'summary.json').write_text(json.dumps(summaries));(out/'paired_summary.json').write_text(json.dumps(pareport))
    proof=dict(parity_cases=len(parity),max_return_difference=max(parity),hypotheses_not_validated=True)
    (out/'proof.json').write_text(json.dumps(proof));print('COMPLETE',len(MODES),len(summaries),proof)
    for r in summaries:
        if r['symbol']=='SOXX' and r['label']=='3H_1H_pivot' and r['phase']=='year':print('MAIN',{k:r.get(k) for k in ['mode','fraction','resolved','mean','win','cum','mdd']})
    print('PAIRED_QUARTER_VS_TIME')
    for r in pareport:
        if r['symbol']=='SOXX' and r['label']=='3H_1H_pivot' and r['phase']=='year' and r['fraction']==.25 and r['reference']=='time':
            print({k:r.get(k) for k in ['mode','n','mean_lift','improved','harmed','winner_harmed','loser_helped','savings','sacrificed']})
if __name__=='__main__':run(sys.argv[1])