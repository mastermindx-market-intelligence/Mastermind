"""Momentum upper-range and rollover exits on frozen SOXX nested-pivot entries.
Research-only. No network calls. All new results use exact prior immutable snapshots.
"""
import bisect,collections,csv,datetime as dt,hashlib,itertools,json,math,random,statistics,sys
from pathlib import Path
import nested_pivots as n
from exit_core import ExitSpec,simulate

YEAR_START=n.b.YEAR_START;YEAR_END=n.b.YEAR_END

def write_csv(path,rows):
    if not rows:return
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)

def indicators(ctx,recent=False):
    tf=[15,30,45,60,120,180,240] if recent else [60,120,180,240]
    panels={}
    for m in tf:
        if m>=120:bs=ctx['high'][m]
        else:bs=ctx['lower'][m]
        for speed,mac in [('classic',(12,26,9)),('responsive',(8,21,5))]:
            f=n.enrich(bs,mac,14)
            panels[m,speed]=(bs,f)
    return panels

def rule_events(raw,panels,tf,speed,family,threshold):
    """Sparse close-known events aligned to the execution-source bar closing time."""
    size=len(raw);arms=[False]*size;trigs=[False]*size
    index={r['end']:i for i,r in enumerate(raw)};bs,f=panels[tf,speed]
    rsi,k,d,h,z=f['rsi'],f['k'],f['d'],f['hist'],f['z']
    for i,r in enumerate(bs):
        j=index.get(r['end'])
        if j is None or i<3 or not r['complete'] or None in [rsi[i],k[i],d[i],k[i-1],d[i-1]]:continue
        fading=h[i]<h[i-1];cross=k[i]<d[i] and k[i-1]>=d[i-1]
        if family=='rsi_touch':a,t=rsi[i]>=threshold,True
        elif family=='rsi_back_below':a,t=rsi[i]>=threshold,rsi[i]<threshold and rsi[i-1]>=threshold
        elif family=='stoch_touch':a,t=k[i]>=threshold,True
        elif family=='stoch_roll':a,t=k[i]>=threshold,cross
        elif family=='stoch_roll_fade':a,t=k[i]>=threshold,cross and fading
        elif family=='joint_upper':a,t=k[i]>=80 and rsi[i]>=threshold,True
        elif family=='joint_roll':a,t=k[i]>=80 and rsi[i]>=threshold,cross and fading
        elif family=='hist_extreme_fade':a,t=z[i] is not None and z[i]>=threshold,h[i]>0 and fading and h[i-1]<h[i-2]
        elif family=='price_top':
            p=f['piv-1'][i];a=k[i]>=80 or rsi[i]>=threshold
            t=p is not None and p==i-1 and fading and rsi[i]<rsi[i-1]
        elif family=='macd_bear':a,t=True,h[i]<0 and h[i-1]>=0
        else:raise ValueError(family)
        arms[j]=bool(a);trigs[j]=bool(t)
    return arms,trigs

def catalog(raw,panels,recent=False):
    horizons=[19.5,32.5,65];book={};events={}
    def add(key,family,tf,speed,threshold,horizon,target=0,protection='none',partial=0,arm=None,trig=None):
        name=f'{key}|h{horizon:g}|{protection}|p{partial:g}'
        book[name]=dict(name=name,family=family,tf=tf,speed=speed,threshold=threshold,horizon=horizon,target=target,protection=protection,partial=partial)
        events[name]=(arm,trig)
    for hz in horizons:
        for target in [2,3,4,6,8,0]:add('fixed'+str(target),'fixed',0,'none',target,hz,target=target)
    tfs=[15,30,45,60,120,180,240] if recent else [60,120,180,240]
    families=[('rsi_touch',v) for v in (60,65,70,75)]+[('rsi_back_below',v) for v in (65,70)]+[('stoch_touch',v) for v in (80,90,95)]+[('stoch_roll',v) for v in (80,90)]+[('stoch_roll_fade',80)]+[('joint_upper',v) for v in (60,65,70)]+[('joint_roll',v) for v in (60,65)]+[('hist_extreme_fade',v) for v in (1.5,2)]+[('price_top',60),('macd_bear',0)]
    for tf,speed,(family,threshold) in itertools.product(tfs,['classic','responsive'],families):
        a,t=rule_events(raw,panels,tf,speed,family,threshold)
        key=f'{family}_{tf}_{speed}_{threshold:g}'
        for hz in horizons:add(key,family,tf,speed,threshold,hz,arm=a,trig=t)
        if speed=='classic' and family in ['stoch_roll_fade','joint_roll','price_top'] and threshold in [60,65,80]:
            for protection,partial in [('breakeven',0),('trail2atr',0),('trail3atr',0),('half_giveback',0),('none',.5),('breakeven',.5),('trail2atr',.5)]:
                add(key,family,tf,speed,threshold,32.5,protection=protection,partial=partial,arm=a,trig=t)
    for tf in [120,180,240]:
        a,_=rule_events(raw,panels,tf,'classic','joint_upper',60)
        for local in ([15,30,60] if recent else [60]):
            _,t=rule_events(raw,panels,local,'classic','stoch_roll_fade',80)
            for protection in ['none','breakeven','trail2atr']:
                add(f'parent_upper{tf}_localroll{local}','parent_upper_localroll',tf,'classic',local,32.5,protection=protection,arm=a,trig=t)
    for hz in horizons:
        for protection in ['breakeven','trail2atr','trail3atr','half_giveback']:
            for partial in [0,.5]:add('profit_runner','runner',0,'none',0,hz,protection=protection,partial=partial)
    return book,events

def get_entries(ctx,recent=False):
    def gen(name,lm,lp,state,trigger):return n.candidates(ctx,name,lm,lp,state,trigger,1)
    def union(lm,lp,state,trigger):
        found={}
        for name in n.PROFILES:
            for c in gen(name,lm,lp,state,trigger):found.setdefault(c['entry'],c)
        return sorted(found.values(),key=lambda c:c['entry'])
    if not recent:
        return {'3H_1H_pivot':(gen('3h_medium',60,'fast','armed','pivot_turn'),'tight'),
                'anyHTF_1H_pivot':(union(60,'balanced','armed','pivot_turn'),'tight'),
                'both_turning_pivot':(union(60,'balanced','turn','pivot_turn'),'tight'),
                'higher_cross_ATR':(union(60,'balanced','recovered','higher_only'),'atr')}
    ans={}
    for lm in [15,30,45,60]:
        ans[f'3H_{lm}m_pivot']=(gen('3h_medium',lm,'fast','armed','pivot_turn'),'micro')
        ans[f'HTFturn_{lm}m_reclaim']=(union(lm,'balanced','turn','pivot_break'),'micro')
    return ans

def summary(trades):
    if not trades:return dict(n=0,mean=None,win=None,cum=0.,mdd=0.)
    vals=[t['net_pct'] for t in trades];eq=1.;peak=1.;dd=0
    for t in trades:
        before=eq
        for _,mark in t['marks']:
            now=before*(1+mark/100);peak=max(peak,now);dd=min(dd,now/peak-1)
        eq=before*(1+t['net_pct']/100)
    pos=sum(max(v,0) for v in vals);neg=-sum(min(v,0) for v in vals)
    return dict(n=len(vals),wins=sum(v>0 for v in vals),win=round(100*sum(v>0 for v in vals)/len(vals),2),
       mean=round(statistics.mean(vals),4),median=round(statistics.median(vals),4),cum=round((eq-1)*100,3),mdd=round(dd*100,3),
       pf=round(pos/neg,3) if neg else None,worst=round(min(vals),4),best=round(max(vals),4),
       ex_best=round((sum(vals)-max(vals))/(len(vals)-1),4) if len(vals)>1 else None,
       stress=round(statistics.mean(t['gross_pct']-.15*(1+t['weighted_exit_ratio']) for t in trades),4),
       risk=round(statistics.mean(t['initial_risk_pct'] for t in trades),4),R=round(statistics.mean(t['net_R'] for t in trades),4),
       hold=round(statistics.mean(t['hold_market_hours'] for t in trades),3),
       gaveback_2_to_loss=sum(t['reached_2pct_before_exit'] and t['net_pct']<0 for t in trades),
       mean_giveback=round(statistics.mean(t['giveback_from_max_close_pct'] for t in trades),4),
       momentum_exits=sum(t['reason']=='momentum' for t in trades),stops=sum(t['reason'].startswith('stop') for t in trades),
       timed=sum(t['reason']=='time' for t in trades),win95=n.b.wilson(sum(v>0 for v in vals),len(vals)))

def eval_rule(ctx,cs,risk,desc,ev,atrs,shadow=False,common_horizon=65):
    raw,clock=ctx['raw'],ctx['clock'];out=[];last=-1;phase=None;reject=collections.Counter()
    spec=ExitSpec(desc['name'],desc['horizon'],desc['target'],desc['protection'],desc['partial'])
    for c in sorted(cs,key=lambda v:(v['entry'],v['profile'])):
        en=c['entry'];ph='year' if raw[en]['day']>=YEAR_START else 'prior'
        if phase!=ph:last=-1;phase=ph
        if not shadow and en<=last:reject['overlap']+=1;continue
        if clock[-1]-clock[en]<common_horizon*3600:reject['right_censored_common_horizon']+=1;continue
        endcap=bisect.bisect_left(clock,clock[en]+common_horizon*3600)-1
        if ph=='prior' and raw[endcap]['day']>=YEAR_START:reject['purged_common_boundary']+=1;continue
        path=raw[en:endcap+1]
        if any(x['day']==y['day'] and x['end']!=y['start'] for x,y in zip(path,path[1:])):
            reject['missing_common_path']+=1;continue
        lev=n.risk_levels(raw[en]['open'],1,risk,c['anchor'],c['atr'])
        if lev is None:reject['risk_bounds']+=1;continue
        t=simulate(raw,en,lev[0],spec,ev[0],ev[1],atrs)
        if t is None:reject['unobserved_exit']+=1;continue
        t.update(candidate_episode=c['episode'],entry_day=raw[en]['day'],entry_ET=raw[en]['local'],profile=c['profile'],phase=ph,
                 exit_ET=dt.datetime.fromtimestamp(t['exit_time'],n.b.ET).isoformat(),entry_idx=en)
        out.append(t);last=t['exit_idx']
    return out,dict(reject)

def prepare(ctx):
    entries=get_entries(ctx,ctx['recent']);frozen={}
    for label,(cs,risk) in entries.items():
        baseline,_=n.evaluate(ctx,cs,risk,1)
        chosen={t['entry_idx'] for t in baseline}
        frozen[label]=([c for c in cs if c['entry'] in chosen],risk)
    return entries,frozen

def run(root,out):
    root,out=Path(root),Path(out)
    if out.exists():raise ValueError('Output exists: inspect original operation before rerun')
    out.mkdir(parents=True)
    spec={'mission':'SOXX momentum-exhaustion exits beyond 2%; frozen entry candidates first','window':[YEAR_START,YEAR_END],
      'protected_sha':'326c8469a21d7f50fc9ecb1848196bf1c6e66685','retrospective':True,'overnight_data':False,
      'common_horizon_hours':65,'fees_bps_per_side':5,'execution':'next bar open for indicator signals; gap-aware stops; conservative limit fills',
      'source_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['rth_original.json','15m_60d.json']}}
    (out/'specification.json').write_text(json.dumps(spec,indent=2))
    grid=[];frozen_records=[];alltrades=[];coverage={};baselines={};price_records=[]
    for recent in [False,True]:
        cohort='recent15' if recent else 'annual60';ctx=n.build_context(root,recent)
        raw=ctx['raw'];panels=indicators(ctx,recent);book,events=catalog(raw,panels,recent)
        atrs=n.b.atr(raw);entries,frozen=prepare(ctx)
        (out/f'{cohort}_candidates.json').write_text(json.dumps({'all':entries,'frozen':frozen}))
        coverage[cohort]={'source_rows':len(raw),'start':ctx['first'],'end':YEAR_END,'exit_rules':len(book),'entry_families':len(entries)}
        for label,(cs,risk) in entries.items():
            baseline,_=n.evaluate(ctx,cs,risk,1)
            baselines[cohort+'|'+label]={p:summary([t|{'marks':[], 'weighted_exit_ratio':t['exit_price']/t['entry_price'],'net_R':t['R'],
                    'reached_2pct_before_exit':False,'giveback_from_max_close_pct':0} for t in baseline if ('year' if t['entry_day']>=YEAR_START else 'prior')==p]) for p in ['prior','year']}
            for key,desc in book.items():
                ts,rej=eval_rule(ctx,cs,risk,desc,events[key],atrs)
                row=dict(cohort=cohort,entry=label,risk_model=risk,**desc,rejections=rej)
                for phase in ['prior','year']:
                    s=summary([t for t in ts if t['phase']==phase]);row.update({phase+'_'+k:v for k,v in s.items()})
                grid.append(row)
                for t in ts:alltrades.append(dict(cohort=cohort,entry=label,exit_rule=key,**{k:v for k,v in t.items() if k not in ['marks','fills']}))
                if not recent:
                    fs,_=eval_rule(ctx,frozen[label][0],risk,desc,events[key],atrs,shadow=True)
                    for phase in ['prior','year']:
                        ss=summary([t for t in fs if t['phase']==phase]);ss.pop('cum',None);ss.pop('mdd',None)
                        frozen_records.append(dict(entry=label,exit_rule=key,phase=phase,**ss))
        price_records.extend(dict(cohort=cohort,**r) for r in raw if r['day']>=YEAR_START)
        print('DONE_COHORT',cohort,'grid',len(grid),'trade_rows',len(alltrades),flush=True)
    (out/'grid.json').write_text(json.dumps(grid));write_csv(out/'grid.csv',grid)
    write_csv(out/'trades.csv',alltrades);write_csv(out/'fixed_entry_comparison.csv',frozen_records)
    (out/'audit.json').write_text(json.dumps({'coverage':coverage,'baseline_reproduction':baselines},indent=2))
    print('COMPLETE',len(grid),len(alltrades),hashlib.sha256((out/'grid.json').read_bytes()).hexdigest())

if __name__=='__main__':run(*sys.argv[1:])