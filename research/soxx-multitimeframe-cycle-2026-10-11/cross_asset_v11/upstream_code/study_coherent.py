"""Frozen parent opportunities; prospective pivot-valid admission and structural exits.
Offline experiment. Rejected/no-fill opportunities remain in the denominator.
"""
from pathlib import Path
import bisect, collections, datetime as dt, hashlib, json, statistics, sys
import frozen_audit as a
import nested_pivots as n
from coherent_cycle import assess_entry, DefendedSwing
from engine_v6 import simulate
from policies_v6 import Policy, make_panels
from lifecycle_v6 import WindowPolicy
from time_nextopen import TimedDecision

ENTRIES=['legacy','pivot_valid','strict_structure','fresh_pivot_6.5h','fresh_pivot_13h']
EXITS=['time52','old_guard52','slow52','defended_stop52','defended_stop_slow52']

class DefendedPolicy:
    def __init__(self,ctx,c):
        self.ctx=ctx;self.c=c;self.seen=-1;self.rows=[]
        self.bars=ctx['lower'][c['lower_minutes']]
        self.f=ctx['lf'][c['lower_minutes'],c['lower_params']]
        self.ends=[b['end'] for b in self.bars]
        self.structure=DefendedSwing(c['anchor'],c['stop'])
        self.entrytime=ctx['raw'][c['entry']]['start']
        self.first=bisect.bisect_left([b['start'] for b in self.bars],self.entrytime)
    def __call__(self,st,b):
        i=n.asof(self.ends,b['end'])
        if i<3 or i==self.seen or not self.bars[i]['complete']:return {}
        self.seen=i;q=self.bars[i];av=self.f['atr'][i]
        if av is None:return {}
        assert q['end']<=b['end']
        promoted=self.structure.observe(i,q['close'],q['low'],av)
        pv=self.f['piv1'][i]
        if pv is not None and i==pv+1 and self.bars[pv]['start']>=self.entrytime:
            xs=self.bars[self.first:pv]
            if xs:
                barrier=max(x['high'] for x in xs)
                if barrier>=self.bars[pv]['low']:
                    self.structure.propose(i,self.bars[pv]['low'],barrier,av)
        if promoted:
            self.rows.append(dict(signal_time=b['end'],index=i,level=self.structure.level,stop=self.structure.stop))
            return dict(stop=self.structure.stop)
        return {}

class Joined:
    def __init__(self,first,second):self.first=first;self.second=second
    def __call__(self,st,b):
        x=self.first(st,b);y=self.second(st,b)
        return dict(x,**y)

def original_metadata(ctx,c):
    return dict(origin_entry=c['entry'],origin_time=c['entry_ET'],origin_phase=c['phase'],origin_episode=c['episode'])

def choose_entry(ctx,c,model,gaps,cap=1.5):
    raw=ctx['raw'];px=raw[c['entry']]['open']
    x=assess_entry(px,c['anchor'],c['atr'],max_risk_pct=cap)
    meta=original_metadata(ctx,c);notes=[dict(time=raw[c['entry']]['start'],**x)]
    if model=='legacy':return dict(c,**meta,admission=model),notes
    if model=='pivot_valid':
        return (dict(c,**meta,admission=model) if px>c['anchor'] else None),notes
    if x['accepted']:
        return dict(c,**meta,stop=x['stop'],admission=model,structural_risk_pct=x['risk_pct']),notes
    if not model.startswith('fresh_pivot_'):return None,notes
    wait=float(model.removeprefix('fresh_pivot_').removesuffix('h'))
    lb=ctx['lower'][c['lower_minutes']];lf=ctx['lf'][c['lower_minutes'],c['lower_params']]
    for i in range(c['lower_index']+1,len(lb)):
        q=lb[i];en=bisect.bisect_left(ctx['rawstarts'],q['end'])
        if en>=len(raw):break
        lag=(ctx['clock'][en]-ctx['clock'][c['entry']])/3600
        if lag>wait or c['arm_to_entry_rth_hours']+lag>26:break
        if not n.lower_trigger(lb,lf,i,1,'pivot_turn'):continue
        pv=lf['piv1'][i]
        if pv is None or lb[pv]['start']<raw[c['entry']]['start']:continue
        if a.intersecting_gaps(gaps,c['signal_time'],q['end']):
            notes.append(dict(time=q['end'],accepted=False,reason='unobserved_wait_path'));break
        hi=n.asof([b['end'] for b in ctx['high'][n.PROFILES[c['profile']][0]]],q['end'])
        hb=ctx['high'][n.PROFILES[c['profile']][0]]
        if hi<0 or not hb[hi]['complete']:continue
        z=assess_entry(raw[en]['open'],lb[pv]['low'],lf['atr'][i],max_risk_pct=cap)
        notes.append(dict(time=raw[en]['start'],**z))
        if not z['accepted']:continue
        si=n.asof(ctx['rawends'],q['end'])
        assert raw[en]['start']>=q['end'] and hb[hi]['end']<=q['end']
        out=dict(c,**meta,entry=en,entry_ET=raw[en]['local'],phase='year' if raw[en]['day']>=n.b.YEAR_START else 'prior',
            signal_idx=si,signal_time=q['end'],higher_index=hi,higher_time=hb[hi]['end'],lower_index=i,
            anchor=lb[pv]['low'],pivot_index=pv,atr=lf['atr'][i],stop=z['stop'],admission=model,
            structural_risk_pct=z['risk_pct'],arm_to_entry_rth_hours=c['arm_to_entry_rth_hours']+lag,
            lower_k=lf['k'][i],lower_rsi=lf['rsi'][i])
        return out,notes
    return None,notes

def policy(ctx,c,exit_name):
    raw=ctx['raw'];panels=ctx['_panels'];en=c['entry'];tracker=None
    if exit_name=='old_guard52':p=WindowPolicy(dict(grace=3,expiry=6.5,retain=.5),raw,panels,en)
    elif exit_name=='slow52':p=Policy(dict(kind='legacy_joint',tf=180),raw,panels,en)
    elif exit_name.startswith('defended_stop'):
        tracker=DefendedPolicy(ctx,c);p=tracker
        if exit_name=='defended_stop_slow52':p=Joined(p,Policy(dict(kind='legacy_joint',tf=180),raw,panels,en))
    else:p=Policy(dict(kind='time',tf=180),raw,panels,en)
    return TimedDecision(p,52),tracker

def evaluate(ctx,origins,entry_model,exit_name,fraction,gaps,cap=1.5,selector=None):
    raw=ctx['raw'];planned=[];rows=[];attempts=[]
    for c in origins:
        z,notes=(selector or choose_entry)(ctx,c,entry_model,gaps,cap)
        for note in notes:attempts.append(dict(origin=c['entry_ET'],model=entry_model,**note))
        if z:planned.append(z)
        else:rows.append(dict(**original_metadata(ctx,c),entry_ET=c['entry_ET'],phase=c['phase'],status='not_admitted',reason=notes[-1]['reason'],net_pct=0))
    last=-1;phase=None
    for c in sorted(planned,key=lambda x:(x['entry'],x['profile'])):
        if phase!=c['phase']:phase=c['phase'];last=-1
        en=c['entry'];meta=original_metadata(ctx,c)
        meta={k:c[k] for k in ['origin_entry','origin_time','origin_phase','origin_episode']}
        if en<=last:
            rows.append(dict(**meta,entry_ET=c['entry_ET'],phase=phase,status='position_overlap',net_pct=0));continue
        dec,mon=policy(ctx,c,exit_name)
        t=simulate(raw,en,c['stop'],horizon=100000,partials=[(2,fraction)] if fraction else [],decision=dec,cost_bps=5)
        if t is None:
            last=len(raw)-1;rows.append(dict(**meta,entry_ET=c['entry_ET'],phase=phase,status='right_censored'));continue
        last=t['exit_idx'];bad=a.intersecting_gaps(gaps,raw[en]['start'],t['exit_time'])
        status='unobserved_session_path' if bad else 'resolved'
        if phase=='prior' and raw[last]['day']>=n.b.YEAR_START:status='period_boundary'
        t.update(**meta,entry_ET=c['entry_ET'],phase=phase,status=status,anchor=c['anchor'],initial_stop=c['stop'],
            signal_time=c['signal_time'],promotions=mon.rows if mon else [],revalidation_hours=(ctx['clock'][en]-ctx['clock'][c['origin_entry']])/3600,
            exit_ET=dt.datetime.fromtimestamp(t['exit_time'],n.b.ET).isoformat(),missing=bad)
        rows.append(t)
    return rows,attempts

def summarize(rows):
    filled=sorted([r for r in rows if r['status'] not in ['not_admitted','position_overlap']],key=lambda r:r.get('entry_idx',1e9))
    known=[r for r in filled if r['status']=='resolved'];sm=a.v7.summarize(filled)
    out=dict(opportunities=len(rows),filled=len(filled),skipped=len(rows)-len(filled),resolved=len(known),
             mean=sm.get('mean'),win=sm.get('win'),cum=sm.get('cum',0 if not filled else None),mdd=sm.get('mdd',0 if not filled else None),
             status_counts=dict(collections.Counter(r['status'] for r in rows)))
    out['opportunity_mean']=sum(t['net_pct'] for t in known)/len(rows) if rows and len(known)==len(filled) else None
    if known:out.update(mean_risk=statistics.mean(t['initial_risk_pct'] for t in known),mean_net_R=statistics.mean(t['net_R'] for t in known),
                         max_risk=max(t['initial_risk_pct'] for t in known),worst=min(t['net_pct'] for t in known),
                         promotions=sum(len(t['promotions']) for t in known),mean_wait=statistics.mean(t['revalidation_hours'] for t in known))
    return out

def run(root):
    root=Path(root);out=root/'results';out.mkdir(exist_ok=False);summary=[];ledger=[];attempts=[];details=[];audits={}
    for symbol,file in [('SOXX','rth_original.json'),('SMH','SMH_60m.json')]:
        ctx=a.context_from_source(root/'inputs'/file);ctx['_panels']=make_panels(ctx);audit=a.source_audit(ctx);audits[symbol]=audit
        cs,_=a.v7.prepared(ctx,'3H_1H_pivot')
        for em in ENTRIES:
            for ex in EXITS:
                if em in ['legacy','pivot_valid'] and ex.startswith('defended'):continue
                for frac in [0,.25]:
                    rs,ns=evaluate(ctx,cs,em,ex,frac,audit['gaps'])
                    tag=dict(symbol=symbol,entry_model=em,exit_model=ex,partial=frac)
                    for ph in ['prior','year']:summary.append(dict(**tag,phase=ph,**summarize([r for r in rs if r['phase']==ph])))
                    for r in rs:ledger.append(dict(**tag,**{k:v for k,v in r.items() if k not in ['marks','fills','actions','promotions','missing']}))
                    if frac==0 and ex=='time52':attempts.extend(dict(symbol=symbol,**z) for z in ns)
                    if symbol=='SOXX':details.extend(dict(**tag,**r) for r in rs)
    for name,rows in [('summary',summary),('trades',ledger),('admission_attempts',attempts)]:a.v7.old.write_csv(out/(name+'.csv'),rows)
    (out/'results.json').write_text(json.dumps(dict(summary=summary,trades=details,audits=audits)))
    print('COMPLETE',len(summary),'summary_rows',len(ledger),'opportunity_outcomes')
    for r in summary:
        if r['symbol']=='SOXX' and r['phase']=='year' and r['partial']==0 and r['exit_model'] in ['time52','defended_stop52']:
            print('MAIN',json.dumps(r))
    print('RESULT_SHA256',hashlib.sha256((out/'results.json').read_bytes()).hexdigest())
if __name__=='__main__':run(sys.argv[1])