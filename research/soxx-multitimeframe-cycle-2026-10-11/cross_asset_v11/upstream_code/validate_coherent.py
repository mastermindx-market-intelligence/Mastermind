"""Causal admission, matched same-entry exits, independent execution and short fine-data probe."""
from pathlib import Path
import bisect, json, hashlib, statistics, sys
import study_coherent as s
import tactical_admission as ta
from dynamic_replay import replay

CASES=[('legacy',1.5,'old_guard52'),('strict_structure',1.5,'defended_stop52'),
       ('strict_structure',6,'defended_stop52'),('signal_low',1.5,'defended_stop52'),
       ('signal_low_then_price_pivot',3,'defended_stop52'),('pivot_retest',1.5,'defended_stop52')]

def prefix_context(ctx,cut):
    raw=ctx['raw'][:cut];closes=ctx['closes']
    high={m:s.n.aggregate_minutes(raw,m,closes) for m in [120,180,240]}
    low={60:s.n.aggregate_minutes(raw,60,closes)}
    out=dict(raw=raw,closes=closes,rejected={},high=high,lower=low,
       hf={name:s.n.enrich(high[tf],mac,p) for name,(tf,mac,p) in s.n.PROFILES.items()},
       lf={(60,name):s.n.enrich(low[60],mac,p) for name,(mac,p) in s.n.LOWERS.items()},
       clock=s.n.market_clock(raw),rawends=[r['end'] for r in raw],rawstarts=[r['start'] for r in raw],recent=False,first=s.n.b.CAL_START)
    out['_panels']=s.make_panels(out)
    return out

def run(root):
    root=Path(root);out=root/'validation';out.mkdir(exist_ok=False)
    ctx=s.a.context_from_source(root/'inputs/rth_original.json');ctx['_panels']=s.make_panels(ctx)
    raw=ctx['raw'];gaps=s.a.source_audit(ctx)['gaps'];origins,_=s.a.v7.prepared(ctx,'3H_1H_pivot')
    parity=[];curves=[];riskchecks=[]
    for em,cap,ex in CASES:
        for fraction in [0,.25]:
            rs,_=s.evaluate(ctx,origins,em,ex,fraction,gaps,cap,selector=ta.choose)
            accepted={c['entry_ET']:ta.choose(ctx,c,em,gaps,cap)[0] for c in origins}
            for order in ['OLHC','OHLC']:
                reread=[]
                for row in rs:
                    if row['status'] in ['not_admitted','position_overlap']:
                        reread.append(row);continue
                    c=accepted[row['origin_time']]
                    dec,mon=s.policy(ctx,c,ex)
                    p=replay(raw,c['entry'],c['stop'],decision=dec,partial=fraction,horizon=100000,order=order,fee=5)
                    if p is None:assert row['status']=='right_censored';reread.append(row);continue
                    delta=p['net_pct']-row['net_pct']
                    if order=='OLHC':assert abs(delta)<1e-8,(em,ex,row['entry_ET'],delta)
                    parity.append(dict(entry_model=em,cap=cap,exit_model=ex,fraction=fraction,order=order,
                        entry=row['entry_ET'],difference=delta,exit_same=p['exit_time']==row['exit_time']))
                    stops=[c['stop']]+[x['level'] for x in row['actions'] if x.get('kind')=='stop']
                    assert stops==sorted(stops)
                    if em!='legacy':assert c['stop']<c['anchor']<raw[c['entry']]['open'] and row['initial_risk_pct']<=cap+1e-8
                    riskchecks.append(True)
                    reread.append(dict(row,**p,net_R=p['net_pct']/p['initial_risk_pct'],promotions=mon.rows if mon else []))
                for ph in ['prior','year']:curves.append(dict(entry_model=em,cap=cap,exit_model=ex,fraction=fraction,order=order,phase=ph,
                    **s.summarize([z for z in reread if z['phase']==ph])))
    # Compare continuation stops on identical accepted entries, without portfolio concurrency.
    matched=[]
    for em,cap,_ in CASES[1:]:
        for c in origins:
            aa,_=s.evaluate(ctx,[c],em,'time52',0,gaps,cap,selector=ta.choose)
            bb,_=s.evaluate(ctx,[c],em,'defended_stop52',0,gaps,cap,selector=ta.choose)
            a,b=aa[0],bb[0]
            if a['status']!='resolved' or b['status']!='resolved':continue
            assert a['entry_ET']==b['entry_ET']
            matched.append(dict(model=em,cap=cap,phase=c['phase'],origin=c['entry_ET'],entry=a['entry_ET'],
                initial_only=a['net_pct'],defended=b['net_pct'],delta=b['net_pct']-a['net_pct'],
                held_initial=a['hold_hours'],held_defended=b['hold_hours'],promotions=len(b['promotions']),
                stopped_above_initial=any(x.get('kind')=='stop' and x['level']>b['initial_stop'] for x in b['actions'])))
    # Recompute features on truncated inputs and compare only decisions already knowable.
    admission_prefix=0;action_prefix=0
    for cut in [600,1200,1800,2400,3000,len(raw)-40]:
        pc=prefix_context(ctx,cut);pg=s.a.source_audit(pc)['gaps']
        for c in origins:
            if c['entry']>=cut:continue
            for em,cap,ex in CASES:
                full,_=ta.choose(ctx,c,em,gaps,cap);short,_=ta.choose(pc,c,em,pg,cap)
                full_visible=full if full is not None and full['entry']<cut else None
                assert (short is None)==(full_visible is None),(cut,c['entry_ET'],em)
                if short:
                    assert short['entry']==full_visible['entry'] and abs(short['stop']-full_visible['stop'])<1e-8
                    assert short['signal_time']<=pc['raw'][short['entry']]['start']
                admission_prefix+=1
                if short and ex=='defended_stop52':
                    dec1,m1=s.policy(ctx,full,ex);dec2,m2=s.policy(pc,short,ex)
                    t1=s.simulate(raw,full['entry'],full['stop'],decision=dec1,horizon=100000)
                    t2=s.simulate(pc['raw'],short['entry'],short['stop'],decision=dec2,horizon=100000)
                    expected=[x for x in m1.rows if x['signal_time']<=pc['raw'][-1]['end']]
                    assert expected==m2.rows,(cut,c['entry_ET'],em)
                    action_prefix+=1
    # Genuine fine-data probe; each label is an alternative view of the same market episode.
    fine=s.n.build_context(root/'inputs',recent=True);fine['_panels']=s.make_panels(fine)
    fg=s.a.source_audit(fine)['gaps'];fr=[];ft=[]
    for label in ['3H_15m_pivot','3H_30m_pivot','3H_60m_pivot','HTFturn_30m_reclaim']:
        cs,_=s.a.v7.prepared(fine,label)
        for model in ['legacy','strict_structure','signal_low_then_price_pivot']:
            for ex in ['time52','old_guard52','defended_stop52']:
                if model=='legacy' and ex.startswith('defended'):continue
                rs,_=s.evaluate(fine,cs,model,ex,0,fg,1.5,selector=ta.choose)
                fr.append(dict(label=label,entry_model=model,exit_model=ex,**s.summarize(rs)))
                for t in rs:ft.append(dict(label=label,entry_model=model,exit_model=ex,**{k:v for k,v in t.items() if k not in ['marks','actions','fills','promotions','missing']}))
    for name,rows in [('independent_curves',curves),('parity',parity),('matched_exits',matched),('fine_summary',fr),('fine_trades',ft)]:s.a.v7.old.write_csv(out/(name+'.csv'),rows)
    proof=dict(independent_replays=len(parity),maximum_low_first_return_difference=max(abs(x['difference']) for x in parity if x['order']=='OLHC'),
      ambiguous_high_first_cases=sum(abs(x['difference'])>1e-8 for x in parity if x['order']=='OHLC'),
      admission_prefix_checks=admission_prefix,defended_action_prefix_cases=action_prefix,risk_and_monotonicity_checks=len(riskchecks),
      fine_source_sha256=hashlib.sha256((root/'inputs/15m_60d.json').read_bytes()).hexdigest(),
      qualifications=['Original inspected dataset; no independent edge claim.','OHLC orderings are scenarios, not tick truth.','Price-gated opening assumptions are not observed limit-order fills.'])
    (out/'proof.json').write_text(json.dumps(proof,indent=2))
    print('PROOF',json.dumps(proof))
    for model,cap,_ in CASES[1:]:
        xs=[x for x in matched if x['model']==model and x['cap']==cap and x['phase']=='year']
        print('PAIRED_EXIT',model,cap,len(xs),sum(x['delta']>1e-8 for x in xs),sum(x['delta']<-1e-8 for x in xs),round(statistics.mean(x['delta'] for x in xs),4) if xs else None)
    print('FINE',json.dumps([{k:x.get(k) for k in ['label','entry_model','exit_model','filled','mean','mean_risk']} for x in fr if x['exit_model']=='defended_stop52']))
if __name__=='__main__':run(sys.argv[1])