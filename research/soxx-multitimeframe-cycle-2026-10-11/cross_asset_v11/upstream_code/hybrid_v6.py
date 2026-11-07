"""Second-stage studies: grace-period profit failure and buffered protection.
Designed after inspecting failure shapes; explicitly retrospective, not untouched OOS.
"""
import bisect,collections,datetime as dt,hashlib,json,math,statistics,sys
from pathlib import Path
import study_v6 as s
import nested_pivots as n
from policies_v6 import Policy,make_panels
from engine_v6 import simulate

def failed_profit_guard(age,peak_gain,current_gain,rsi,below_ema,grace,retained):
    return age>=grace and peak_gain>=2 and current_gain<2*retained and (rsi<50 or below_ema)

def continuation_models(ctx,panels):
    """16 transparent bins. Train only completed 6.5-hour outcomes before quarter start.
    Conditional means are shrunk by 50 global observations; overlapping labels are not
    represented as independent evidence. This is a descriptive alternative, not ML proof.
    """
    raw,clock=ctx['raw'],ctx['clock'];model_by_quarter={};out=[]
    def state(f):return (f['close']>f['ema20'],f['hist']<f['prev_hist'],f['er']>.3,f['rsi']>=60)
    for j,b in enumerate(raw):
        date=dt.date.fromisoformat(b['day']);q=(date.year,(date.month-1)//3)
        if q not in model_by_quarter:
            cutoff=int(dt.datetime(date.year,q[1]*3+1,1,tzinfo=n.b.ET).timestamp());groups=collections.defaultdict(list);allv=[];last=0
            for i in range(100,j):
                end=bisect.bisect_left(clock,clock[i+1]+6.5*3600)-1
                if end>=len(raw) or raw[end]['end']>=cutoff:continue
                f=panels[60][i]
                if f is None or not f['valid']:continue
                path=raw[i+1:end+1]
                if not path or any(a['day']==z['day'] and a['end']!=z['start'] for a,z in zip(path,path[1:])):continue
                ret=100*(raw[end]['close']/raw[i+1]['open']-1)
                groups[state(f)].append(ret);allv.append(ret);last=max(last,raw[end]['end'])
            globalmean=statistics.mean(allv) if allv else 0
            model={k:dict(mean=(sum(v)+50*globalmean)/(len(v)+50),n=len(v)) for k,v in groups.items()}
            assert last<cutoff
            model_by_quarter[q]=dict(model=model,cutoff=cutoff,trained_through=last,n=len(allv))
        m=model_by_quarter[q];f=panels[60][j]
        z=m['model'].get(state(f),{}) if f and f['valid'] else {}
        out.append(dict(**z,cutoff=m['cutoff'],trained_through=m['trained_through']))
    audit=[dict(quarter=str(q),**{k:v for k,v in m.items() if k!='model'},bins=len(m['model'])) for q,m in model_by_quarter.items()]
    return out,audit

class Hybrid:
    def __init__(self,plan,raw,panels,entry,forecast=None):
        self.plan=plan;self.raw=raw;self.panels=panels;self.entry=entry;self.forecast=forecast
        base=dict(kind='legacy_joint',tf=plan.get('exit_tf',180),arm=2)
        self.base=Policy(base,raw,panels,entry);self.last=-1
    def __call__(self,st,b):
        p=self.plan;action=self.base(st,b);j=st['j'];f=self.panels[p.get('local_tf',60)][j]
        if f is None or not f['valid'] or f['i']==self.last:return action
        self.last=f['i'];gain=100*(b['close']/st['px']-1);peakgain=100*(st['peak']/st['px']-1)
        risk=st['px']-st['initial_stop'];mode=p['mode'];grace=p.get('grace',3)
        if st['age_hours']>=grace:
            if mode=='buffer_floor' and st['partial_hits']:
                action['stop']=max(action.get('stop') or 0,st['px']-p.get('buffer_R',.5)*risk)
            if mode in ['profit_failure','profit_failure_trail','session_failure']:
                failure=failed_profit_guard(st['age_hours'],peakgain,gain,f['rsi'],b['close']<f['ema10'],grace,p.get('retain',.5))
                if mode=='session_failure':
                    now=dt.datetime.fromtimestamp(b['end'],n.b.ET);failure&=now.hour==15 and now.minute==30
                if failure:action.update(sell=st['remaining'],reason=mode)
                if mode=='profit_failure_trail' and 100*(st['peak_close']/st['px']-1)>=p.get('trail_arm',6):
                    slow=self.panels[120][j]
                    if slow and slow['valid'] and slow['pivot_start'] is not None and slow['pivot_start']>=self.raw[self.entry]['start']:
                        action['stop']=max(action.get('stop') or 0,slow['pivot_low']-.25*slow['atr'])
            if mode=='continuation' and peakgain>=2 and self.forecast:
                z=self.forecast[j]
                if z.get('n',0)>=30 and z.get('mean',0)<p.get('forecast_cut',0) and b['close']<f['ema10']:
                    action.update(sell=st['remaining'],reason='negative_continuation')
        return action

def registry():
    out=[]
    def add(mode,**kw):
        p=dict(mode=mode,grace=3,retain=.5,exit_tf=180,local_tf=60,horizon=65,partial=.5)
        p.update(kw);p['id']='H'+str(len(out))+'_'+mode;out.append(p)
    for grace in [2,3,4,6.5]:
        for retain in [.25,.5,.75]:
            for partial in [0,.25,.5]:add('profit_failure',grace=grace,retain=retain,partial=partial)
    for grace in [2,3,4]:
        for buffer in [.25,.5,.75,1.0]:add('buffer_floor',grace=grace,buffer_R=buffer)
    for grace in [2,3,4]:
        for partial in [.25,.5]:
            add('session_failure',grace=grace,partial=partial)
            add('profit_failure_trail',grace=grace,partial=partial)
    for cut in [-.25,0,.25]:
        for partial in [0,.5]:add('continuation',forecast_cut=cut,partial=partial)
    return out

def evaluate(ctx,panels,cs,plan,forecast=None,*,delay=1,cost=5,stop_slippage=0,amb='stop_first',shadow=False,limit_buffer=0):
    raw=ctx['raw'];out=[];last=-1;phase=None
    for c in cs:
        if phase!=c['phase']:phase=c['phase'];last=-1
        if not shadow and c['entry']<=last:continue
        p=Hybrid(plan,raw,panels,c['entry'],forecast)
        parts=[(2,plan['partial'])] if plan.get('partial') else []
        t=simulate(raw,c['entry'],c['stop'],horizon=plan.get('horizon',65),partials=parts,decision=p,
              cost_bps=cost,delay=delay,stop_slippage_bps=stop_slippage,ambiguity=amb,limit_buffer_bps=limit_buffer)
        if t is None:raise RuntimeError('missing horizon')
        t.update(phase=c['phase'],entry_ET=c['entry_ET'],entry_day=raw[c['entry']]['day'],episode=c['episode'],profile=c['profile'],
          exit_ET=dt.datetime.fromtimestamp(t['exit_time'],n.b.ET).isoformat())
        out.append(t);last=t['exit_idx']
    return out

def run(inputs,result):
    result=Path(result)
    if result.exists():raise ValueError('output exists')
    result.mkdir();grid=[];trades=[];plans=registry()
    (result/'plan.json').write_text(json.dumps(dict(retrospective=True,known_failure_shapes_inspected=True,plans=plans),indent=2))
    for recent in [False,True]:
        cohort='recent' if recent else 'annual';ctx=n.build_context(inputs,recent);panels=make_panels(ctx)
        forecast,audit=continuation_models(ctx,panels) if not recent else (None,[])
        (result/(cohort+'_forecast_audit.json')).write_text(json.dumps(audit,indent=2))
        for label,(cs,risk) in s.entry_sets(ctx).items():
            cs,rejs=s.common_candidates(ctx,cs,risk)
            for plan in plans:
                if recent and plan['mode']=='continuation':continue
                ts=evaluate(ctx,panels,cs,plan,forecast)
                grid.append(s.row_of(label,dict(kind=plan['mode'],**plan),ts,cohort))
                for t in ts:trades.append(dict(cohort=cohort,label=label,id=plan['id'],**{k:v for k,v in t.items() if k not in ['marks','actions','fills']}))
    (result/'grid.json').write_text(json.dumps(grid));s.write_csv(result/'grid.csv',grid);s.write_csv(result/'trades.csv',trades)
    print('HYBRID_DONE',len(plans),len(grid),len(trades),hashlib.sha256((result/'grid.json').read_bytes()).hexdigest())
    keys=['id','mode','grace','retain','partial','prior_n','prior_mean','prior_ex_best','year_n','year_mean','year_cum','year_win','year_mdd','year_ex_best','year_stress']
    for mode in ['profit_failure','buffer_floor','session_failure','profit_failure_trail','continuation']:
        xs=[r for r in grid if r['cohort']=='annual' and r['label']=='3H_1H_pivot' and r['mode']==mode and r['prior_n']>=5]
        best=max(xs,key=lambda r:r['prior_ex_best']-.1*abs(r['prior_mdd']))
        print('EARLIER_SELECTED',{k:best.get(k) for k in keys})
    for r in grid:
        if r['cohort']=='annual' and r['label']=='3H_1H_pivot' and r['mode']=='profit_failure' and r['grace']==3 and r['retain']==.5:
            print('DEFINED_DEFAULT',{k:r.get(k) for k in keys})
if __name__=='__main__':run(*sys.argv[1:])