"""Cash-bounded re-entry research helpers. No data access or broker effects.
All prices are known observations; fees are charged on each purchase and sale.
The risk budget is a planned stop-distance limit, not a guaranteed loss limit.
"""
from math import isfinite

def quantities(sold_qty, sold_price, buy_price, first_net_pct, original_price,
               initial_risk_pct, fee_bps=5, stop_pct=1.5):
    vals=[sold_qty,sold_price,buy_price,first_net_pct,original_price,initial_risk_pct,fee_bps,stop_pct]
    if any(not isfinite(float(x)) for x in vals):raise ValueError('nonfinite sizing input')
    if min(sold_price,buy_price,original_price,initial_risk_pct,stop_pct)<=0 or sold_qty<0 or fee_bps<0:
        raise ValueError('nonpositive price or risk; negative quantity or fee')
    fee=fee_bps/10000
    if fee>=1 or stop_pct>=100:raise ValueError('invalid fee or stop')
    proceeds=sold_qty*sold_price*(1-fee)
    cash_quantity=proceeds/(buy_price*(1+fee))
    budget=max(0.,(first_net_pct+initial_risk_pct)/100*original_price)
    risk_per_share=buy_price*(stop_pct/100+fee*(2-stop_pct/100))
    return max(0.,min(sold_qty,cash_quantity,budget/risk_per_share))

def path_known(raw, entry, exit_time):
    """Reject unobserved intraday intervals, but not the intentional RTH overnight gap.
    This is an outcome audit, NOT a pre-entry condition. It does not prove tick coverage.
    """
    if not 0<=entry<len(raw):raise ValueError('entry index')
    for i in range(entry+1,len(raw)):
        a,b=raw[i-1],raw[i]
        if a['end']>=exit_time:return True
        if a['day']==b['day'] and a['end']!=b['start']:return False
        if b['start']>=exit_time:return True
    return exit_time<=raw[-1]['end']

def recovers(mode, bars, i, feature, previous_feature, threshold):
    if mode not in ('reclaim','break2','two_closes'):raise ValueError('unknown recovery rule')
    if i<2 or not feature or not previous_feature:return False
    f,p=feature,previous_feature
    if not f.get('valid') or not p.get('valid'):return False
    if any(f.get(k) is None for k in ('rsi','hist','prev_hist','ema10')):return False
    if any(p.get(k) is None for k in ('rsi','ema10')):return False
    c=bars[i]['close'];trend=c>f['ema10'] and f['rsi']>=50 and f['hist']>f['prev_hist']
    if mode=='reclaim':return trend and c>threshold
    if mode=='break2':return trend and c>max(bars[i-1]['high'],bars[i-2]['high']) and f['rsi']>p['rsi']
    return trend and bars[i-1]['close']>p['ema10'] and p['rsi']>=50

def combine(first, leg, quantity):
    """Combine two trades per original share, not by multiplying full-position returns."""
    if not 0<=quantity<=1:raise ValueError('re-entry share quantity')
    weight=quantity*leg['entry_price']/first['entry_price']
    result=dict(first)
    result.update(net_pct=first['net_pct']+weight*leg['net_pct'],
                  gross_pct=first['gross_pct']+weight*leg['gross_pct'],
                  marks=first['marks']+[(j,first['net_pct']+weight*v) for j,v in leg['marks']],
                  restored_quantity=quantity,restored_notional_fraction=weight)
    return result