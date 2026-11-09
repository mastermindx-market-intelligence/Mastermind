"""Bounded tactical revalidation and prospective structural-risk sensitivity.
No parameter is changed after entry. New pivots do not require a second RSI washout.
"""
import bisect, json, hashlib, sys
from pathlib import Path
import study_coherent as s
from coherent_cycle import assess_entry

MODELS=['signal_low','signal_low_then_price_pivot','pivot_then_price_pivot','pivot_retest']

def choose(ctx,c,model,gaps,cap=1.5):
    if model not in MODELS:return s.choose_entry(ctx,c,model,gaps,cap)
    raw=ctx['raw'];meta=s.original_metadata(ctx,c);basis=dict(c)
    if model.startswith('signal_low'):
        basis['anchor']=raw[c['signal_idx']]['low'];basis['anchor_kind']='confirmation_candle_low'
    z,notes=s.choose_entry(ctx,basis,'strict_structure',gaps,cap)
    if z:return dict(z,admission=model),notes
    if model=='signal_low':return None,notes
    if model=='pivot_retest' and raw[c['entry']]['open']<=c['anchor']:return None,notes
    lb=ctx['lower'][c['lower_minutes']];lf=ctx['lf'][c['lower_minutes'],c['lower_params']]
    hbars=ctx['high'][s.n.PROFILES[c['profile']][0]];hends=[q['end'] for q in hbars]
    for i in range(c['lower_index']+1,len(lb)):
        q=lb[i];en=bisect.bisect_left(ctx['rawstarts'],q['end'])
        if en>=len(raw):break
        lag=(ctx['clock'][en]-ctx['clock'][c['entry']])/3600
        if lag>13 or c['arm_to_entry_rth_hours']+lag>26:break
        if not q['complete'] or lf['atr'][i] is None:continue
        if s.a.intersecting_gaps(gaps,c['signal_time'],q['end']):
            notes.append(dict(time=q['end'],accepted=False,reason='unobserved_wait_path'));break
        if model=='pivot_retest':
            if q['low']<c['anchor']:
                notes.append(dict(time=q['end'],accepted=False,reason='original_pivot_broken_while_waiting'));break
            anchor=c['anchor'];pv=c['pivot_index']
            if not (q['close']>q['open'] and q['close']>lb[i-1]['close']):continue
        else:
            pv=lf['piv1'][i]
            if pv is None or i!=pv+1 or lb[pv]['start']<raw[c['entry']]['start']:continue
            if not (q['close']>q['open'] and q['close']>lb[i-1]['close']):continue
            anchor=lb[pv]['low']
        hi=s.n.asof(hends,q['end'])
        if hi<0 or not hbars[hi]['complete']:continue
        x=assess_entry(raw[en]['open'],anchor,lf['atr'][i],max_risk_pct=cap)
        notes.append(dict(time=raw[en]['start'],**x))
        if not x['accepted']:continue
        si=s.n.asof(ctx['rawends'],q['end'])
        assert raw[en]['start']>=q['end'] and hbars[hi]['end']<=q['end']
        return dict(c,**meta,entry=en,entry_ET=raw[en]['local'],phase='year' if raw[en]['day']>=s.n.b.YEAR_START else 'prior',
            signal_idx=si,signal_time=q['end'],higher_index=hi,higher_time=hbars[hi]['end'],lower_index=i,
            anchor=anchor,pivot_index=pv,anchor_kind='confirmed_price_pivot' if model!='pivot_retest' else 'original_pivot_retest',
            atr=lf['atr'][i],stop=x['stop'],admission=model,structural_risk_pct=x['risk_pct'],
            arm_to_entry_rth_hours=c['arm_to_entry_rth_hours']+lag,lower_k=lf['k'][i],lower_rsi=lf['rsi'][i]),notes
    return None,notes

def run(root):
    root=Path(root);out=root/'tactical_results';out.mkdir(exist_ok=False)
    specs=dict(entry_models=['strict_structure',*MODELS],caps=[1.5,3.0,6.0],exits=['time52','old_guard52','defended_stop52'],
        fractions=[0,.25],note='Risk caps set prospectively. No recommended allocation. Retrospective diagnostic; not optimization.')
    (out/'SPECIFICATION.json').write_text(json.dumps(specs,indent=2))
    summary=[];ledger=[];details=[];attempts=[]
    for symbol,file in [('SOXX','rth_original.json'),('SMH','SMH_60m.json')]:
        ctx=s.a.context_from_source(root/'inputs'/file);ctx['_panels']=s.make_panels(ctx);gaps=s.a.source_audit(ctx)['gaps']
        cs,_=s.a.v7.prepared(ctx,'3H_1H_pivot')
        for model in specs['entry_models']:
            for cap in specs['caps']:
                for exitname in specs['exits']:
                    for fraction in specs['fractions']:
                        rs,ns=s.evaluate(ctx,cs,model,exitname,fraction,gaps,cap,selector=choose)
                        tag=dict(symbol=symbol,entry_model=model,cap=cap,exit_model=exitname,partial=fraction)
                        for ph in ['prior','year']:summary.append(dict(**tag,phase=ph,**s.summarize([r for r in rs if r['phase']==ph])))
                        for r in rs:ledger.append(dict(**tag,**{k:v for k,v in r.items() if k not in ['marks','fills','actions','promotions','missing']}))
                        if symbol=='SOXX' and fraction==0:details.extend(dict(**tag,**r) for r in rs)
                        if fraction==0 and exitname=='time52':attempts.extend(dict(symbol=symbol,cap=cap,**r) for r in ns)
    for name,rs in [('summary',summary),('ledger',ledger),('attempts',attempts)]:s.a.v7.old.write_csv(out/(name+'.csv'),rs)
    (out/'results.json').write_text(json.dumps(dict(summary=summary,trades=details)))
    print('COMPLETE',len(summary),'summary_rows')
    for r in summary:
        if r['symbol']=='SOXX' and r['phase']=='year' and r['partial']==0 and r['exit_model']=='defended_stop52':
            print('TACTICAL',json.dumps({k:r.get(k) for k in ['entry_model','cap','filled','mean','win','opportunity_mean','mean_risk','mean_net_R','cum','mdd','promotions']}))
    print('RESULT_SHA256',hashlib.sha256((out/'results.json').read_bytes()).hexdigest())
if __name__=='__main__':run(sys.argv[1])