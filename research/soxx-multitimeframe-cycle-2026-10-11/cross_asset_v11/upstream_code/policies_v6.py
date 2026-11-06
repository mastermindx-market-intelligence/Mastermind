"""Price-structure, volatility, and conditional exit policies. Research-only.
Panels are point-in-time, completed OHLC bars. All orders are decided after close.
"""
from collections import defaultdict
import bisect, math, statistics
import nested_pivots as n

def make_panels(ctx):
    raw=ctx['raw'];ends=[r['end'] for r in raw];panels={}
    for tf,bs in {**ctx['lower'],**ctx['high']}.items():
        f=n.enrich(bs,(12,26,9),14);cl=[b['close'] for b in bs]
        e10=n.b.ema(cl,10);e20=n.b.ema(cl,20);kama=[];v=cl[0]
        vols=defaultdict(list);items=[];lasttop=None
        for i,b in enumerate(bs):
            atr=f['atr'][i];look=10;window=cl[max(0,i-look):i+1]
            path=sum(abs(y-x) for x,y in zip(window,window[1:]));signed=(window[-1]-window[0])/path if path else 0
            er=abs(signed);alpha=(er*(2/3-2/31)+2/31)**2;v=v+alpha*(cl[i]-v);kama.append(v)
            lowp=f['piv1'][i];highp=f['piv-1'][i];div=False;div_start=None
            if highp is not None and highp!=lasttop:
                if lasttop is not None and atr and bs[highp]['high']>bs[lasttop]['high']+.1*atr:
                    a,z=f['rsi'][highp],f['rsi'][lasttop]
                    div=bool(a is not None and z is not None and a<z-3)
                    div|=f['hist'][lasttop]>0 and f['hist'][highp]<.7*f['hist'][lasttop]
                    div_start=bs[highp]['start']
                lasttop=highp
            slot=(b['start']%(24*3600),round((b['end']-b['start'])/60))
            history=vols[slot][-20:];rv=b['volume']/statistics.median(history) if history and statistics.median(history)>0 else None
            vols[slot].append(b['volume'])
            spread=b['high']-b['low'];pos=(b['close']-b['low'])/spread if spread else .5
            wick=(b['high']-max(b['open'],b['close']))/spread if spread else 0
            valid=b.get('complete',True) and i>50 and atr and f['rsi'][i] is not None
            item=dict(i=i,end=b['end'],start=b['start'],valid=bool(valid),close=b['close'],open=b['open'],
              high=b['high'],low=b['low'],atr=atr,rsi=f['rsi'][i],k=f['k'][i],d=f['d'][i],hist=f['hist'][i],
              prev_hist=f['hist'][i-1] if i else 0,fade2=i>1 and f['hist'][i]<f['hist'][i-1]<f['hist'][i-2],
              kd_cross=i>0 and None not in [f['k'][i],f['d'][i],f['k'][i-1],f['d'][i-1]] and f['k'][i]<f['d'][i] and f['k'][i-1]>=f['d'][i-1],
              ema10=e10[i],ema20=e20[i],kama=v,prev_kama=kama[i-1] if i else v,
              prev_close=cl[i-1] if i else cl[i],er=signed,rv=rv,closepos=pos,upperwick=wick,
              divergence=div,div_start=div_start,pivot_low=bs[lowp]['low'] if lowp is not None else None,
              pivot_start=bs[lowp]['start'] if lowp is not None else None,
              low3=min(x['low'] for x in bs[max(0,i-3):i]) if i else b['low'],
              high5=max(x['high'] for x in bs[max(0,i-5):i]) if i else b['high'],
              high10=max(x['high'] for x in bs[max(0,i-10):i]) if i else b['high'])
            for w in [3,5,8,14]:item['trail_low'+str(w)]=min(x['low'] for x in bs[max(0,i-w+1):i+1])
            items.append(item)
        bends=[b['end'] for b in bs];aligned=[]
        for end in ends:
            a=bisect.bisect_right(bends,end)-1
            aligned.append(items[a] if a>=0 else None)
        panels[tf]=aligned
    return panels

class Policy:
    def __init__(self,plan,raw,panels,entry):
        self.plan=plan;self.raw=raw;self.panels=panels;self.entry=entry
        self.armed=False;self.upper=False;self.previous_i=-1;self.count=0
        self.div_until=-1;self.climax_low=None;self.climax_until=-1;self.soft=False
        self.vsum=0.;self.pvsum=0.;self.vwap_below=0;self.nohigh=0;self.highestclose=0
        self.lastfeature=None
    def __call__(self,st,b):
        p=self.plan;j=st['j'];kind=p['kind'];gain=(b['close']/st['px']-1)*100
        self.vsum+=b.get('volume',0);self.pvsum+=b.get('volume',0)*(b['high']+b['low']+b['close'])/3
        avwap=self.pvsum/self.vsum if self.vsum else b['close']
        self.vwap_below=self.vwap_below+1 if b['close']<avwap else 0
        f=self.panels[p.get('tf',60)][j];parent=self.panels[180][j]
        if f is None or not f['valid']:return {}
        fresh=f['i']!=self.previous_i
        if not fresh:return {}
        self.previous_i=f['i'];self.lastfeature=f;atr=f['atr'];c=f['close'];px=st['px']
        self.nohigh=0 if c>self.highestclose else self.nohigh+1;self.highestclose=max(c,self.highestclose)
        peak_gain=100*(st['peak_close']/px-1)
        self.armed|=peak_gain>=p.get('arm',2)
        joint=f['k'] is not None and f['rsi']>=65 and f['k']>=80
        self.upper|=joint
        bearish=f['hist']<f['prev_hist']
        risk=px-st['initial_stop'];R=(c-px)/risk
        stop=None;sell=0;reason=kind
        if kind=='legacy_joint':
            if self.upper and f['kd_cross'] and bearish:sell=st['remaining']
        elif kind=='time':pass
        elif kind=='failure_clock':
            if st['age_hours']>=p.get('hours',6.5) and st['peak_close']<px+.5*risk and c<px:
                sell=st['remaining']
        elif self.armed:
            if kind=='donchian':stop=f['trail_low'+str(p.get('window',5))]-.25*atr
            elif kind=='swing':
                if f['pivot_start'] is not None and f['pivot_start']>=self.raw[self.entry]['start']:
                    stop=f['pivot_low']-p.get('buffer',.25)*atr
            elif kind=='chandelier':stop=st['peak']-p.get('mult',3)*atr
            elif kind=='volatility_budget':
                room=max(p.get('mult',1.5)*atr,p.get('giveback',.4)*(st['peak']-px))
                stop=st['peak']-room
            elif kind=='adaptive_atr':
                strong=f['er']>.35 and c>f['ema20'] and f['hist']>=f['prev_hist']
                multiple=p.get('mult',3.5) if strong else p.get('weak_mult',2)
                stop=st['peak']-multiple*atr
            elif kind=='kama':
                self.count=self.count+1 if c<f['kama']-p.get('buffer',.25)*atr else 0
                if self.count>=p.get('confirm',2):sell=st['remaining']
            elif kind=='vwap_loss':
                if self.vwap_below>=p.get('confirm',2) and c<f['ema10'] and bearish:sell=st['remaining']
            elif kind=='failed_breakout':
                prior=f['high'+str(p.get('window',5))]
                if f['high']>prior+.1*atr and c<prior and c<f['open'] and f['closepos']<.4:
                    sell=st['remaining']
            elif kind=='climax':
                evidence=f['high']>f['high5'] and f['upperwick']>.35 and f['closepos']<.4 and (f['high']-f['low'])>1.5*atr and f['rsi']>=60
                if p.get('volume',False):evidence&=f['rv'] is not None and f['rv']>=1.5
                if evidence:self.climax_low=f['low'];self.climax_until=f['i']+3
                if evidence and not p.get('confirm',True):sell=st['remaining']
                if self.climax_low is not None and f['i']<=self.climax_until and c<self.climax_low:sell=st['remaining']
            elif kind=='divergence_break':
                if f['divergence'] and f['div_start']>=self.raw[self.entry]['start']:self.div_until=f['i']+6
                if f['i']<=self.div_until and c<f['low3']:sell=st['remaining']
            elif kind=='stagnation':
                if self.nohigh>=p.get('window',5) and f['er']<.25 and c<f['ema10'] and bearish:sell=st['remaining']
            elif kind=='risk_ladder':
                highR=(st['peak_close']-px)/risk
                for reached,locked in [(2,.25),(3,.75),(5,2),(8,4),(12,7)]:
                    if highR>=reached:stop=px+locked*risk
            elif kind in ['state_guard','state_trim']:
                mature=parent is not None and parent['valid'] and parent['k'] is not None and parent['rsi']>=60 and parent['k']>=80
                self.upper|=mature
                broken=c<f['low3'];lost_trend=c<f['ema10'] and bearish
                stall=self.nohigh>=p.get('window',4) and f['er']<.2
                climax=f['upperwick']>.35 and f['closepos']<.4 and f['high']>f['high5'] and f['high']-f['low']>1.5*atr
                if f['divergence']:self.div_until=f['i']+6
                score=int(broken)+int(lost_trend)+int(stall)+int(climax)+int(f['i']<=self.div_until)
                if not self.upper:
                    if R>=3:stop=st['peak']-p.get('mult',3.5)*atr
                else:
                    if score>=p.get('votes',2):
                        if kind=='state_trim' and not self.soft:
                            sell=min(st['remaining'],1/3);self.soft=True;reason='exhaustion_trim'
                        else:sell=st['remaining'];reason='exhaustion_exit'
                    if f['pivot_start'] is not None and f['pivot_start']>=self.raw[self.entry]['start']:
                        stop=f['pivot_low']-.25*atr
            elif kind=='dual_clock':
                mature=parent is not None and parent['valid'] and parent['k'] is not None and parent['rsi']>=p.get('upper',65) and parent['k']>=80
                self.upper|=mature
                if self.upper and c<f['low3'] and bearish:sell=st['remaining']
            elif kind=='session_defense':
                local=n.b.dt.datetime.fromtimestamp(b['end'],n.b.ET) if hasattr(n.b,'dt') else None
                if local is not None and local.hour==15 and local.minute==30 and c<f['ema10'] and bearish:
                    sell=st['remaining']
            else:raise ValueError('Unknown policy '+kind)
        if p.get('breakeven',False) and st['partial_hits']>0:stop=max(px,stop or 0)
        if p.get('failure_hours') and st['age_hours']>=p['failure_hours'] and st['peak_close']<px+.5*risk and c<px:
            sell=st['remaining'];reason='failure_to_launch'
        return dict(stop=stop,sell=sell,reason=reason)

def plans(recent=False):
    out=[]
    def add(kind,tf=60,**kw):
        d=dict(kind=kind,tf=tf,horizon=65,arm=2,partials=[],**kw)
        d['id']=kind+'_'+str(tf)+'_'+str(len(out));out.append(d)
    add('time',target=2,tag='old_fixed2');add('time',target=8,tag='fixed8');add('time',tag='hold65')
    add('legacy_joint',180,tag='old_joint_half',partials_override=[(2,.5)])
    add('legacy_joint',180,tag='old_joint_full')
    tfs=[60,120,180,240] if not recent else [15,30,60,120,180,240]
    for tf in tfs:
        for w in [3,5,8]:add('donchian',tf,window=w)
        for mult in [2,3,4]:add('chandelier',tf,mult=mult)
        for giveback in [.35,.5,.65]:add('volatility_budget',tf,mult=1.5,giveback=giveback)
        for mult,weak in [(3,1.5),(3.5,2),(4,2.5)]:add('adaptive_atr',tf,mult=mult,weak_mult=weak)
        for confirm in [1,2]:add('kama',tf,confirm=confirm,buffer=.25)
        for buffer in [.25,.5]:add('swing',tf,buffer=buffer)
        for w in [3,5,8]:add('stagnation',tf,window=w)
        for w in [5,10]:add('failed_breakout',tf,window=w)
        for confirm,volume in [(False,False),(True,False),(True,True)]:add('climax',tf,confirm=confirm,volume=volume)
        add('vwap_loss',tf,confirm=2);add('divergence_break',tf);add('risk_ladder',tf)
        if tf<=120:
            for votes in [2,3]:add('state_guard',tf,votes=votes);add('state_trim',tf,votes=votes)
            for upper in [60,65]:add('dual_clock',tf,upper=upper)
    for hours in [6.5,13]:add('failure_clock',hours=hours)
    base=out.copy()
    for p in base:
        if (p['tf'] in [60,120,180] and p['kind'] in ['swing','adaptive_atr','state_guard','state_trim','volatility_budget','donchian','risk_ladder'] and
           p.get('mult',3.5) in [1.5,3.5] and p.get('window',5)==5 and p.get('giveback',.5)==.5 and p.get('buffer',.25)==.25 and p.get('votes',2)==2):
            for partial in [.25,.5]:
                q=p.copy();q['id']=p['id']+'_partial'+str(partial);q['partials']=[(2,partial)];out.append(q)
    for p in out:
        if 'partials_override' in p:p['partials']=p.pop('partials_override')
    return out