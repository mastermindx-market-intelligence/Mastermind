"""Research-side normalization and falsifiable bar/quote clocks for Mastermind.

Offline importer only. Not a Tiingo/Alpaca collector, new Data OS writer, broker
adapter, live feed, backtest selector, quote distributor, or order executor.
Consumes explicitly supplied licensed vendor payloads and retains provenance.
No invented trading events, fills, candles, or absent-volume assumptions.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
from collections import Counter, defaultdict
from bisect import bisect_right
import math

ET=ZoneInfo('America/New_York')
UTC=timezone.utc


def _aware(ts):
    if isinstance(ts,str):
        ts=datetime.fromisoformat(ts.replace('Z','+00:00'))
    if not isinstance(ts,datetime) or ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError('UTC-offset-aware timestamp required; no naive timestamp inference')
    return ts.astimezone(UTC)


def _num(n,*,positive=True):
    if isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n):
        raise ValueError('invalid non-finite or non-numeric market value')
    if (n<=0 if positive else n<0):raise ValueError('nonpositive/negative market value')
    return float(n)


@dataclass(frozen=True)
class Bar:
    symbol:str
    utc:datetime
    minutes:int
    open:float
    high:float
    low:float
    close:float
    volume:int|None
    source:str
    basis:str

    def __post_init__(self):
        if not self.symbol or self.symbol!=self.symbol.upper():raise ValueError('canonical uppercase symbol required')
        object.__setattr__(self,'utc',_aware(self.utc))
        if self.minutes not in (1,5,15,30,60):raise ValueError('source bar interval unsupported')
        if self.basis not in ('split','raw'):raise ValueError('adjustment basis must be explicit')
        if not self.source:raise ValueError('source provenance required')
        o,h,l,c=(_num(v) for v in (self.open,self.high,self.low,self.close))
        if h<max(o,c) or l>min(o,c) or h<l:raise ValueError('impossible OHLC')
        if self.volume is not None and (isinstance(self.volume,bool) or not isinstance(self.volume,int) or self.volume<0):
            raise ValueError('invalid volume; unknown is None, not zero')

    @property
    def end(self):return self.utc+timedelta(minutes=self.minutes)


def classify_session(ts,regular_close=None):
    """Explicit ET classifications; vendor actual trading-calendar holds final authority."""
    t=_aware(ts).astimezone(ET)
    hm=t.hour*60+t.minute;dow=t.weekday()
    if dow==5 or dow==6 and hm<1200 or dow==4 and hm>=1200:
        return 'closed'
    if hm>=1200 or hm<240:return 'overnight'
    if hm<570:return 'premarket'
    if isinstance(regular_close,dict):
        close=regular_close.get(t.date().isoformat())
        if close is None:close=960
    else:close=960
    if not isinstance(close,int) or not 570<=close<=960:raise ValueError('bad regular closing minute')
    if hm<close:return 'rth'
    if hm<1200:return 'postmarket'
    return 'closed'


def trade_date(ts):
    t=_aware(ts).astimezone(ET)
    return (t+timedelta(days=1)).date() if t.hour>=20 else t.date()


def _make(row,symbol,minutes,source,basis,ts_key,ohlc_keys):
    ts=_aware(row[ts_key]);o,h,l,c=(_num(row[key]) for key in ohlc_keys)
    vol=row.get('v',row.get('volume'))
    if vol is not None:
        if isinstance(vol,bool) or not isinstance(vol,int) or vol<0:raise ValueError('invalid volume')
    return Bar(symbol,ts,minutes,o,h,l,c,vol,source,basis)


def normalize_alpaca(payload,symbol,minutes,basis='split'):
    """Accept archived `/v2/stocks/bars?feed=boats&adjustment=split` response.
    `next_page_token` is a hard refusal, not evidence of complete history.
    """
    if not isinstance(payload,dict) or not isinstance(payload.get('bars'),dict):
        raise ValueError('expected Alpaca historical bars envelope')
    if payload.get('next_page_token'):raise ValueError('unconsumed provider page token: incomplete series')
    items=payload['bars'].get(symbol,[])
    if not isinstance(items,list):raise ValueError('invalid vendor rows')
    out=[]
    for row in items:
        if not isinstance(row,dict):raise ValueError('invalid vendor bar')
        b=_make(row,symbol,minutes,'alpaca-boats',basis,'t',('o','h','l','c'))
        if classify_session(b.utc)=='overnight':out.append(b)
    return sorted(out,key=lambda b:b.utc)


def normalize_tiingo(payload,symbol,minutes,basis='raw'):
    """Archive input only: historical Tiingo `/boats/<symbol>/prices` list.
    Historical OHLCV is not a historical order book. Volume can be omitted.
    """
    if not isinstance(payload,list):raise ValueError('expected Tiingo historical array')
    out=[]
    for row in payload:
        if not isinstance(row,dict):raise ValueError('invalid Tiingo row')
        b=_make(row,symbol,minutes,'tiingo-boats',basis,'date',('open','high','low','close'))
        if classify_session(b.utc)=='overnight':out.append(b)
    return sorted(out,key=lambda b:b.utc)


def normalize_terminal_display(rows,symbol,minutes,basis='split',source='massive',overnight_evidence=None):
    """Decode Terminal's ET-display-epoch (not real UTC) for 04:00-20:00 only.
    BOATS must be supplied with real provider UTC to avoid DST fold ambiguity.
    """
    if not isinstance(rows,list):raise ValueError('expected Terminal bar rows')
    out=[]
    for row in rows:
        if not isinstance(row,(list,tuple)) or len(row)<5:raise ValueError('invalid Terminal bar')
        fake=datetime.fromtimestamp(int(row[0]),UTC)
        hm=fake.hour*60+fake.minute
        if hm<240 or hm>=1200:
            if source not in ('alpaca-boats','tiingo-boats') or overnight_evidence!='available':
                raise ValueError('Terminal overnight display epoch requires explicit BOATS provider + available status')
        elif source in ('alpaca-boats','tiingo-boats'):
            raise ValueError('BOATS provider cannot establish a daytime bar')
        naive=fake.replace(tzinfo=None)
        if naive.replace(tzinfo=ET,fold=0).utcoffset()!=naive.replace(tzinfo=ET,fold=1).utcoffset():
            raise ValueError('DST-ambiguous ET display epoch requires original provider UTC')
        dt=naive.replace(tzinfo=ET).astimezone(UTC)
        vals={'t':dt,'o':row[1],'h':row[2],'l':row[3],'c':row[4]}
        if len(row)>5:vals['v']=row[5]
        b=_make(vals,symbol,minutes,source,basis,'t',('o','h','l','c'))
        if classify_session(b.utc)=='closed':raise ValueError('daytime bar outside allowed trading time')
        out.append(b)
    return sorted(out,key=lambda b:b.utc)


def stitch(daytime,overnight):
    """No silent vendor winner, basis mixing, duplicate timestamps or forward fill."""
    out=sorted(list(daytime)+list(overnight),key=lambda b:b.utc)
    if not out:return []
    syms={b.symbol for b in out};bases={b.basis for b in out};grains={b.minutes for b in out}
    if len(syms)!=1 or len(bases)!=1 or len(grains)!=1:
        raise ValueError('incompatible instrument, split basis or timeframe')
    last_end=None
    for b in out:
        if last_end and b.utc<last_end:raise ValueError('overlapping or duplicated vendor bars')
        last_end=b.end
        cls=classify_session(b.utc)
        if cls=='closed':raise ValueError('bar outside supported weekly session')
        if cls=='overnight' and b.source not in ('alpaca-boats','tiingo-boats'):
            raise ValueError('unverified overnight vendor')
        if cls!='overnight' and b.source in ('alpaca-boats','tiingo-boats'):
            raise ValueError('BOATS source in daytime')
    return out


def _session_anchor(ts):
    local=_aware(ts).astimezone(ET)
    d=trade_date(ts)
    return datetime.combine(d-timedelta(days=1),time(20,0),ET).astimezone(UTC)


def aggregates(bars,timeframe_minutes):
    """Aggregate one 20:00-20:00 trade-date clock, with missing-bar evidence.
    Incomplete groups are emitted but cannot become signals.
    """
    if timeframe_minutes not in (60,120,180,240):raise ValueError('unsupported HTF')
    ordered=stitch([b for b in bars if b.source not in ('alpaca-boats','tiingo-boats')],
                   [b for b in bars if b.source in ('alpaca-boats','tiingo-boats')])
    if not ordered:return []
    base=ordered[0].minutes
    if timeframe_minutes%base:raise ValueError('timeframes not divisible')
    groups=defaultdict(list)
    for b in ordered:
        anchor=_session_anchor(b.utc)
        offset=int((b.utc-anchor).total_seconds()//60)
        if not 0<=offset<1440:raise ValueError('bar outside trade-day boundary')
        slot=offset//timeframe_minutes
        start=anchor+timedelta(minutes=slot*timeframe_minutes)
        groups[(start,trade_date(b.utc))].append(b)
    out=[]
    count_expected=timeframe_minutes//base
    for (start,day),bs in sorted(groups.items()):
        bs.sort(key=lambda b:b.utc)
        expected=[start+timedelta(minutes=i*base) for i in range(count_expected)]
        got={b.utc for b in bs}
        complete=len(bs)==count_expected and got==set(expected)
        sessions=sorted(set(classify_session(b.utc) for b in bs))
        out.append({'start':start,'end':start+timedelta(minutes=timeframe_minutes),
            'trade_date':day.isoformat(),'complete':complete,'observed':len(bs),
            'expected':count_expected,'sessions':sessions,'missing':len(set(expected)-got),
            'open':bs[0].open,'high':max(b.high for b in bs),
            'low':min(b.low for b in bs),'close':bs[-1].close,
            'volume':sum(b.volume for b in bs) if all(b.volume is not None for b in bs) else None,
            'source_labels':sorted(set(b.source for b in bs)),'mixed':len(sessions)>1})
    return out


def asof_signal(agg,decision_utc):
    at=_aware(decision_utc)
    historical=[x for x in agg if x['end']<=at]
    if not historical:return None
    most_recent=max(historical,key=lambda b:b['end'])
    # A missing earlier bucket in the same trading-day cycle invalidates the
    # causal indicator chain, even if the newest bar happens to be complete.
    same_day=[x for x in historical if x['trade_date']==most_recent['trade_date']]
    if any(not x['complete'] for x in same_day):return None
    # A completely missing HTF bucket produces no aggregate row at all.
    # Require contiguous slots since the beginning of the session trade date.
    anchor=_session_anchor(most_recent['start'])
    tf=most_recent['end']-most_recent['start']
    expected=[anchor+i*tf for i in range(int((most_recent['end']-anchor)/tf))]
    if set(expected)!={x['start'] for x in same_day}:return None
    return most_recent if most_recent['complete'] and at-most_recent['end']<=tf else None


@dataclass(frozen=True)
class Quote:
    symbol:str
    utc:datetime
    bid:float
    ask:float
    bid_size:int
    ask_size:int
    source:str
    def __post_init__(self):
        object.__setattr__(self,'utc',_aware(self.utc))
        if not self.symbol or self.symbol!=self.symbol.upper() or not self.source:raise ValueError('missing quote provenance')
        _num(self.bid);_num(self.ask)
        if self.bid>=self.ask or not isinstance(self.bid_size,int) or not isinstance(self.ask_size,int) or self.bid_size<0 or self.ask_size<0:
            raise ValueError('invalid or crossed quote')


def quote_decision(quotes,decision_utc,side,limit_price,quantity,*,symbol,max_age_seconds=30,max_spread_pct=1):
    """Quote-based marketability only, NEVER a confirmed historical fill."""
    at=_aware(decision_utc)
    if side not in ('buy','sell'):raise ValueError('invalid side')
    _num(limit_price)
    if not isinstance(quantity,int) or quantity<=0:raise ValueError('invalid quantity')
    if not symbol or symbol!=symbol.upper():raise ValueError('canonical quote symbol required')
    valid=[q for q in quotes if q.symbol==symbol and q.utc<=at and (at-q.utc).total_seconds()<=max_age_seconds]
    if not valid:return {'status':'quote_unavailable'}
    q=max(valid,key=lambda x:x.utc)
    if 100*(q.ask-q.bid)/((q.ask+q.bid)/2)>max_spread_pct:return {'status':'spread_unacceptable'}
    price=q.ask if side=='buy' else q.bid
    depth=q.ask_size if side=='buy' else q.bid_size
    if depth<quantity:return {'status':'displayed_size_insufficient'}
    if side=='buy' and price>limit_price or side=='sell' and price<limit_price:
        return {'status':'limit_not_marketable'}
    return {'status':'quote_marketable_unfilled','reference_price':price,
            'spread_pct':100*(q.ask-q.bid)/((q.ask+q.bid)/2),
            'quote_age_seconds':(at-q.utc).total_seconds(),'source':q.source}


def coverage(bars,start_utc,base_minutes,count):
    t=_aware(start_utc)
    expected={t+timedelta(minutes=i*base_minutes) for i in range(count)}
    matched=[b for b in bars if b.utc in expected and b.minutes==base_minutes]
    got={b.utc for b in matched}
    return {'complete':len(got)==count,'observed':len(got),
            'missing':len(expected-got),'expected':count,
            'provenance':sorted(set(b.source for b in matched))}


def provenance_summary(bars):
    sessions=Counter(classify_session(b.utc) for b in bars)
    return {'rows':len(bars),'overnight_rows':sessions.get('overnight',0),
            'sessions':dict(sessions),'sources':dict(Counter(b.source for b in bars)),
            'whole_24h_proven':False,
            'note':'Explicit full-session coverage and separate quote availability must be checked per day.'}