"""Controlled research on frozen SOXX entries: do not execute trades or fetch data."""
import bisect,collections,csv,datetime as dt,hashlib,itertools,json,math,os,statistics,sys
from pathlib import Path
import nested_pivots as n
import momentum_study as m
from policies_v6 import Policy,make_panels,plans
from engine_v6 import simulate

def write_csv(path,rows):
    if not rows:return
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)

def stats(ts):
    if not ts:return dict(n=0,mean=None,win=None,cum=0,mdd=0,ex_best=None)
    vs=[t['net_pct'] for t in ts];eq=peak=1.;dd=0
    for t in ts:
        for _,value in t.get('marks',[]):
            mark=eq*(1+value/100);peak=max(peak,mark);dd=min(dd,mark/peak-1)
        eq*=1+t['net_pct']/100;peak=max(peak,eq);dd=min(dd,eq/peak-1)
    neg=-sum(min(0,x) for x in vs);pos=sum(max(0,x) for x in vs)
    return dict(n=len(vs),mean=round(statistics.mean(vs),6),win=round(100*sum(x>0 for x in vs)/len(vs),3),
      median=round(statistics.median(vs),6),cum=round(100*(eq-1),6),mdd=round(100*dd,6),pf=round(pos/neg,5) if neg else None,
      worst=round(min(vs),6),best=round(max(vs),6),ex_best=round((sum(vs)-max(vs))/(len(vs)-1),6) if len(vs)>1 else None,
      ex_top2=round(statistics.mean(sorted(vs)[:-2]),6) if len(vs)>2 else None,
      stress=round(statistics.mean(t['gross_pct']-.15*(1+t['weighted_exit_ratio']) for t in ts),6),
      risk=round(statistics.mean(t['initial_risk_pct'] for t in ts),5),R=round(statistics.mean(t['net_R'] for t in ts),5),
      hold=round(statistics.mean(t['hold_hours'] for t in ts),4),stops=sum(t['reason'].startswith('stop') for t in ts),
      timer=sum(t['reason']=='time' for t in ts),giveback=round(statistics.mean(max([v for j,v in t.get('marks',[])] or [t['net_pct']])-t['net_pct'] for t in ts),5),
      gaveback2=sum(t['reached2'] and t['net_pct']<0 for t in ts),win95=n.b.wilson(sum(x>0 for x in vs),len(vs)))

def common_candidates(ctx,cs,risk):
    raw,clock=ctx['raw'],ctx['clock'];accepted=[];rejected=[]
    for c in sorted(cs,key=lambda c:c['entry']):
        en=c['entry'];ph='year' if raw[en]['day']>=n.b.YEAR_START else 'prior';why=None
        if clock[-1]-clock[en]<65*3600:why='right_censored'
        end=bisect.bisect_left(clock,clock[en]+65*3600)-1
        if why is None:
            if ph=='prior' and raw[end]['day']>=n.b.YEAR_START:why='boundary_purge'
            else:
                xs=raw[en:end+1]
                if any(a['day']==b['day'] and a['end']!=b['start'] for a,b in zip(xs,xs[1:])):why='missing_maximal_path'
        levels=n.risk_levels(raw[en]['open'],1,risk,c['anchor'],c['atr'])
        if levels is None:why='initial_risk'
        if why:rejected.append(dict(entry_ET=raw[en]['local'],reason=why));continue
        accepted.append(dict(c,stop=levels[0],phase=ph,entry_ET=raw[en]['local']))
    return accepted,rejected

def entry_sets(ctx):
    _,frozen=m.prepare(ctx)
    out={label:(cs,risk) for label,(cs,risk) in frozen.items()}
    if not ctx['recent']:
        raw=ctx['raw'];bs=ctx['lower'][60];f=ctx['lf'][60,'fast'];cs=[]
        for i,b in enumerate(bs):
            if i<100 or b['day']<ctx['first'] or not n.lower_trigger(bs,f,i,1,'pivot_turn'):continue
            en=b['lastidx']+1
            if en>=len(raw):continue
            cs.append(dict(entry=en,anchor=b['low'],atr=f['atr'][i],profile='ungated',episode='u'+str(i)))
        out['ungated_1H']=(cs,'tight')
    return out

def evaluate(ctx,panels,cs,plan,*,delay=1,cost=5,stop_slippage=0,amb='stop_first',shadow=False,limit_buffer=0):
    raw=ctx['raw'];trades=[];last=-1;phase=None
    for c in cs:
        if phase!=c['phase']:last=-1;phase=c['phase']
        if not shadow and c['entry']<=last:continue
        policy=Policy(plan,raw,panels,c['entry'])
        t=simulate(raw,c['entry'],c['stop'],decision=policy,horizon=plan.get('horizon',65),
          target=plan.get('target',0),partials=plan.get('partials',()),delay=delay,cost_bps=cost,
          stop_slippage_bps=stop_slippage,ambiguity=amb,limit_buffer_bps=limit_buffer)
        if t is None:raise RuntimeError('Complete admitted path lacks exit')
        t.update(phase=c['phase'],entry_ET=c['entry_ET'],entry_day=raw[c['entry']]['day'],episode=c['episode'],profile=c['profile'],
          exit_ET=dt.datetime.fromtimestamp(t['exit_time'],n.b.ET).isoformat())
        trades.append(t);last=t['exit_idx']
    return trades

def row_of(label,plan,ts,cohort='annual'):
    a=stats([t for t in ts if t['phase']=='prior']);b=stats([t for t in ts if t['phase']=='year'])
    return dict(cohort=cohort,label=label,**plan,**{'prior_'+k:v for k,v in a.items()},**{'year_'+k:v for k,v in b.items()})

def run(inputs,out):
    inputs,out=Path(inputs),Path(out)
    if out.exists():raise ValueError('Output exists; reconcile original before replay')
    out.mkdir(parents=True)
    manifest=dict(mission='SOXX granular exit mechanisms on frozen entries',scope='offline research, no broker/auth/production',
      protected_sha='326c8469a21d7f50fc9ecb1848196bf1c6e66685',retrospective=True,common_horizon=65,cost_bps=5,
      selection_score='prior_mean_ex_best minus 0.1*abs(prior_mark_drawdown), minimum5 prior trades; no year data in selector',
      goal='Pareto tradeoffs: realized return, drawdown, giveback, prior survival, latency and gap stress',
      source_shas={f:hashlib.sha256((inputs/f).read_bytes()).hexdigest() for f in ['rth_original.json','15m_60d.json']},
      code_shas={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*v6.py')})
    (out/'specification.json').write_text(json.dumps(manifest,indent=2))
    grid=[];allts=[];data={};refs=[]
    for recent in [False,True]:
        cohort='recent' if recent else 'annual';ctx=n.build_context(inputs,recent);pn=make_panels(ctx);book=plans(recent)
        sets=entry_sets(ctx);prepared={};rejs={}
        for label,(cs,risk) in sets.items():
            prepared[label],rejs[label]=common_candidates(ctx,cs,risk)
        (out/f'{cohort}_candidates.json').write_text(json.dumps(prepared))
        data[cohort]=dict(raw_rows=len(ctx['raw']),start=ctx['first'],end=n.b.YEAR_END,rejections=rejs,
          admitted={label:dict(collections.Counter(c['phase'] for c in cs)) for label,cs in prepared.items()})
        if not recent:
            legacybook,legacyevents=m.catalog(ctx['raw'],m.indicators(ctx));atrs=n.b.atr(ctx['raw'])
            originalcs,risk=sets['3H_1H_pivot']
            for oldid,tag in [('fixed2|h65|none|p0','old_fixed2'),('joint_roll_180_classic_65|h65|none|p0','old_joint_full')]:
                ot,_=m.eval_rule(ctx,originalcs,risk,legacybook[oldid],legacyevents[oldid],atrs)
                plan=next(p for p in book if p.get('tag')==tag)
                nt=evaluate(ctx,pn,prepared['3H_1H_pivot'],plan)
                a={x['entry_idx']:x for x in ot};b={x['entry_idx']:x for x in nt}
                assert set(a)==set(b),(tag,'entry mismatch',set(a)^set(b))
                assert all(abs(a[k]['net_pct']-b[k]['net_pct'])<1e-8 for k in a),(tag,'return mismatch')
                refs.append(dict(tag=tag,matched=len(a),maximum_difference=max(abs(a[k]['net_pct']-b[k]['net_pct']) for k in a)))
        for label,cs in prepared.items():
            for plan in book:
                ts=evaluate(ctx,pn,cs,plan)
                grid.append(row_of(label,plan,ts,cohort))
                allts.extend(dict(cohort=cohort,label=label,plan_id=plan['id'],**{k:v for k,v in t.items() if k not in ['marks','actions','fills']}) for t in ts)
        print('PHASE',cohort,'rules',len(book),'grid_cumulative',len(grid),'rows',len(allts),flush=True)
    (out/'grid.json').write_text(json.dumps(grid));write_csv(out/'grid.csv',grid);write_csv(out/'trades.csv',allts)
    (out/'data_audit.json').write_text(json.dumps(dict(coverage=data,baseline_parity=refs),indent=2))
    shortlist=[]
    for label in ['3H_1H_pivot','anyHTF_1H_pivot','higher_cross_ATR','ungated_1H']:
        eligible=[r for r in grid if r['cohort']=='annual' and r['label']==label and r['prior_n']>=5 and r['prior_ex_best'] is not None]
        for kind in sorted(set(r['kind'] for r in eligible)):
            rows=[r for r in eligible if r['kind']==kind]
            selected=max(rows,key=lambda r:(r['prior_ex_best']-.1*abs(r['prior_mdd']),r['prior_mean'],-len(r['id'])))
            shortlist.append(selected)
    (out/'prior_selected.json').write_text(json.dumps(shortlist,indent=2))
    print('RESULT_HASH',hashlib.sha256((out/'grid.json').read_bytes()).hexdigest())
    print('BASELINE_PARITY',refs)
    print('PRIMARY_FAMILY_PRIOR_SELECTIONS')
    for r in shortlist:
        if r['label']=='3H_1H_pivot':print({k:r.get(k) for k in ['id','kind','tf','partials','prior_n','prior_mean','prior_ex_best','year_n','year_mean','year_win','year_mdd','year_ex_best','year_hold']})

if __name__=='__main__':run(*sys.argv[1:])