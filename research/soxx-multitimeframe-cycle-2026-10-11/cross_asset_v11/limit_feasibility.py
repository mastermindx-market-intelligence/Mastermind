"""Bounded counterfactual, not an execution model: risk-compatible buy limits.
Every limit and structural stop is computed at the original completed signal.
No quote or queue fills assumed. Count rejected/missed opportunities separately.
"""
from pathlib import Path
import collections,csv,datetime as dt,hashlib,json,statistics,sys
HERE=Path(__file__).resolve().parent
PARENT=Path('/private/tmp/soxx_coherent_cycle_20261010_v10')
sys.path.insert(0,str(PARENT))
import frozen_audit as fa
import study_coherent as sc
from coherent_cycle import assess_entry
SPECS=json.loads((HERE/'SPECIFICATION.json').read_text())
SOURCES={'SOXX':PARENT/'inputs/rth_original.json','SMH':PARENT/'inputs/SMH_60m.json',
         'QQQ':Path('/private/tmp/soxx_frozen_audit_20261010_v8/inputs/QQQ_60m.json')}
for s in SPECS['symbols_precommitted']:SOURCES[s]=HERE/'inputs'/(s+'.json')
def safe_mean(xs):
 return round(statistics.mean(xs),4) if xs else None
def eligibility(ctx,c,cap=1.5,n=2):
    raw=ctx['raw'];i=c['entry'];r=raw[i]
    if c['atr'] is None or c['atr']<=0:return dict(status='atr_missing',touches=0)
    pivot=c['anchor'];stop=pivot-.1*c['atr']
    if stop<=0 or r['open']<=pivot:
        return dict(status='pivot_invalid_at_first_open',touches=0,pivot=pivot,stop=stop)
    price=stop/(1-cap/100)
    if price<=pivot:return dict(status='risk_cap_infeasible_near_pivot',touches=0,limit_price=price,pivot=pivot,stop=stop)
    # Valid at next open: opening-market admission still assumes actual execution at open.
    if r['open']<=price:
        return dict(status='at_open',touches=1,limit_price=price,pivot=pivot,stop=stop,
                    entry_at_open=r['open'],lag_bars=0)
    gaps=fa.source_audit(ctx)['gaps'] if '_auditgaps' not in ctx else ctx['_auditgaps']
    # The opening and following observed bars are the only authorized good-till-expiry windows.
    for k in range(n):
        j=i+k
        if j>=len(raw):return dict(status='right_censored',touches=0,limit_price=price,pivot=pivot,stop=stop)
        b=raw[j]
        if fa.intersecting_gaps(gaps,raw[i]['start'],b['end']):
            return dict(status='source_gap',touches=0,limit_price=price,pivot=pivot,stop=stop)
        if b['open']<=pivot:
            return dict(status='gap_below_pivot',touches=0,limit_price=price,pivot=pivot,stop=stop,lag_bars=k)
        # Any hourly low crossing pivot also invalidates holding the proposed structural thesis.
        if b['low']<=pivot:
            return dict(status='pivot_broken_within_contact_bar',touches=int(b['low']<=price),
                        limit_price=price,pivot=pivot,stop=stop,lag_bars=k)
        if b['open']<=price:
            return dict(status='opening_contact',touches=1,limit_price=price,pivot=pivot,stop=stop,
                        entry_at_open=b['open'],lag_bars=k)
        if b['low']<=price:
            return dict(status='clean_limit_touch_unproven_fill',touches=1,limit_price=price,pivot=pivot,
                        stop=stop,lag_bars=k,low=b['low'])
    return dict(status='unfilled',touches=0,limit_price=price,pivot=pivot,stop=stop,
                max_entry_discount_pct=round(100*(1-price/r['open']),3))
def run():
    details=[];summaries=[];provenance={}
    baseline=list(csv.DictReader((HERE/'results/asset_trade_ledger.csv').open()))
    lookup={(r['symbol'],r['entry_ET']):float(r['net_pct']) for r in baseline
            if r['policy']=='time' and r['phase']=='year' and r['status']=='resolved' and r['net_pct']}
    for sym,path in SOURCES.items():
        ctx=fa.context_from_source(path);ctx['_auditgaps']=fa.source_audit(ctx)['gaps']
        origins,_=fa.v7.prepared(ctx,'3H_1H_pivot')
        raw=ctx['raw']
        provenance[sym]=hashlib.sha256(path.read_bytes()).hexdigest()
        for cap in (1.5,):
            for n in (1,2):
                results=[]
                for c in origins:
                    if c['phase']!='year':continue
                    z=eligibility(ctx,c,cap,n)
                    base=lookup.get((sym,c['entry_ET']))
                    row=dict(symbol=sym,cap_pct=cap,expiry_bars=n,original_entry=c['entry_ET'],
                             first_open=round(raw[c['entry']]['open'],5),
                             anchor=round(c['anchor'],5),atr=round(c['atr'],5),
                             source_first_bar_hours=round((raw[c['entry']]['end']-raw[c['entry']]['start'])/3600,3),
                             baseline_52h_net_pct=round(base,4) if base is not None else None,
                             **z)
                    results.append(row);details.append(row)
                count=collections.Counter(x['status'] for x in results)
                admitted=[r for r in results if r['status'] in ('at_open','opening_contact')]
                clean=[r for r in results if r['status']=='clean_limit_touch_unproven_fill']
                skipped=[r for r in results if r['status'] not in ('at_open','opening_contact','clean_limit_touch_unproven_fill')]
                foregone=[r['baseline_52h_net_pct'] for r in skipped if r['baseline_52h_net_pct'] is not None]
                summaries.append(dict(symbol=sym,group='new_semis' if sym in set('AMD AVGO MU INTC NVDA AMAT LRCX KLAC'.split()) else 'other',
                    cap_pct=cap,expiry_bars=n,opportunities=len(results),admitted_open=len(admitted),
                    clean_limit_touches_unproven=len(clean),no_clean_entry=len(skipped),
                    statuses=json.dumps(dict(count),sort_keys=True),
                    known_baseline_skipped=len(foregone),positive_baseline_skipped=sum(t>0 for t in foregone),
                    avg_baseline_skipped=safe_mean(foregone)))
    def write_csv(name,rs):
        keys=list(dict.fromkeys(k for r in rs for k in r))
        with (HERE/'results'/name).open('w',newline='') as f:
            w=csv.DictWriter(f,keys);w.writeheader();w.writerows(rs)
    write_csv('limit_feasibility_detail.csv',details)
    write_csv('limit_feasibility_summary.csv',summaries)
    totals=[]
    for group in ('new_semis','all_symbols'):
        for n in (1,2):
            x=[r for r in summaries if r['expiry_bars']==n and (group=='all_symbols' or r['group']=='new_semis')]
            totals.append(dict(group=group,expiry_bars=n,opportunities=sum(r['opportunities'] for r in x),
                admitted_open=sum(r['admitted_open'] for r in x),
                clean_limit_touches_unproven=sum(r['clean_limit_touches_unproven'] for r in x),
                no_clean_entry=sum(r['no_clean_entry'] for r in x),
                skipped_original_winners=sum(r['positive_baseline_skipped'] for r in x)))
    p=HERE/'results/limit_feasibility.json'
    p.write_text(json.dumps(dict(totals=totals,provenance=provenance,rules='No assumed passive-order fills. Touch without pivot break not a fill; pivot-through invalid.'),indent=2))
    print('TOTALS',totals)
    print('SOXX', [x for x in summaries if x['symbol']=='SOXX'])
    print('SHA',hashlib.sha256(p.read_bytes()).hexdigest())
if __name__=='__main__':run()