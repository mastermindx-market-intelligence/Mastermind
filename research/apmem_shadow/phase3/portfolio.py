"""Shared-capital long/cash research book with causal order sequencing.

Signals use the prior close. Only open exits finance new opening entries;
intraday proceeds cannot retroactively fund orders at that same day's open.
The gross cap applies at decision opens; intraday drift is reported, not denied.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from .labels import RULES, barrier_fill


@dataclass(frozen=True)
class Policy:
    name: str
    family: str = 'union'
    sizing: str = 'none'
    selection: str = 'identifier'
    exit_rule: str = 'barrier21'
    target_vol: float = .30
    static_multiplier: float = 1.
    cost: float = .0005
    cash_rate: float = 0.
    delay: int = 0
    maximum_positions: int = 10
    base_weight: float = .08
    gross_cap: float = .80
    barrier_order: str = 'stop_first'
    distribution_cash: str = 'receivable'

    def validate(self):
        if (any(type(v) is not int for v in (self.maximum_positions,self.delay))
                or not np.isfinite([self.target_vol,self.static_multiplier,self.cost,self.cash_rate,self.base_weight,self.gross_cap]).all()
                or self.distribution_cash not in ('receivable','ex_date_spendable')
                or self.exit_rule not in RULES or self.sizing not in ('none','ewma','mem','static')
                or self.selection not in ('identifier','positive_rs','rs_rank','ev_positive','ev_rank','stop_rank')
                or not 0 < self.target_vol <= 2 or not 0 <= self.static_multiplier <= 1
                or not 0 <= self.cost < .1 or not 0 <= self.cash_rate < 1
                or type(self.delay) is not int or self.delay < 0
                or not 1 <= self.maximum_positions <= 100 or not 0 < self.base_weight <= self.gross_cap <= 1
                or self.barrier_order not in ('stop_first','target_first')):
            raise ValueError('invalid research portfolio policy')


class Market:
    def __init__(self, panels: dict[str,pd.DataFrame], calendar: pd.DatetimeIndex):
        if not calendar.is_unique or not calendar.is_monotonic_increasing:
            raise ValueError('invalid market calendar')
        self.dates = calendar
        self.names = sorted(panels)
        self.lookup = {t:i for i,t in enumerate(self.names)}
        self.values = {}
        for col in ('open','high','low','close','dividend','split','signal_close'):
            self.values[col] = np.column_stack([panels[t][col].reindex(calendar).to_numpy(float) for t in self.names])
        self.values['trail20'] = np.column_stack([
            panels[t].signal_close.shift(1).rolling(20,min_periods=20).min().reindex(calendar).to_numpy(float)
            for t in self.names])

    def bar(self, i: int, k: int):
        values = [self.values[c][i,k] for c in ('open','high','low','close','dividend','split')]
        if not np.isfinite(values).all() or min(values[:4]) <= 0 or values[4] < 0 or values[5] <= 0:
            raise ValueError('held/candidate instrument has unavailable bar: '+self.names[k])
        return values


def summarize(equity, dates, exposure, turnover, cash_rate=0.):
    eq = np.asarray(equity,float)
    if len(eq) != len(dates)+1 or (eq <= 0).any() or not np.isfinite(eq).all():
        raise ValueError('invalid marked equity')
    r = eq[1:]/eq[:-1]-1
    year = max((dates[-1]-dates[0]).days+1,1)/365.25
    gaps = np.r_[0.,np.diff(dates.to_numpy()).astype('timedelta64[D]').astype(float)]
    rf = (1+cash_rate)**(gaps/365.25)-1
    excess = r-rf
    vol = float(np.std(excess,ddof=1)*np.sqrt(252)) if len(r)>1 else 0.
    downside = float(np.sqrt(np.mean(np.minimum(excess,0)**2))*np.sqrt(252))
    dd = eq/np.maximum.accumulate(eq)-1
    worst = np.sort(r)[:max(1,int(np.ceil(.05*len(r))))]
    underwater = longest = 0
    for value in dd:
        underwater = underwater+1 if value < -1e-12 else 0
        longest=max(longest,underwater)
    cagr = float(eq[-1]**(1/year)-1)
    return {'sessions':len(r),'total_return':float(eq[-1]-1),'cagr':cagr,
            'sharpe':float(excess.mean()*252/vol) if vol>1e-12 else None,
            'sortino':float(excess.mean()*252/downside) if downside>1e-12 else None,
            'calmar':float(cagr/abs(dd.min())) if dd.min() < -1e-12 else None,
            'annualized_excess_vol':vol,'maximum_close_drawdown':float(dd.min()),
            'worst_5pct_daily_mean':float(worst.mean()),'worst_day':float(r.min()),
            'ulcer_index':float(np.sqrt(np.mean(dd**2))),'longest_underwater_sessions':longest,
            'mean_close_equity_exposure':float(np.mean(exposure)),
            'turnover_per_year':float(np.sum(turnover)/year),
            'first_session':str(dates[0].date()),'last_session':str(dates[-1].date())}


def simulate(market: Market, events: pd.DataFrame, policy: Policy,
             start='2020-01-02', end='2026-06-02') -> dict:
    policy.validate()
    required={'event_id','ticker','origin','family','mem_h5','ewma_h5','relative_momentum'}
    if not required.issubset(events):
        raise ValueError('missing explicit decision fields')
    # Future path/outcome fields never enter the execution engine.
    columns=list(required)+[c for c in ('expected_net_payoff','p_stop') if c in events]
    e=events.loc[events.family.eq(policy.family),columns].copy()
    if not e.event_id.is_unique:
        raise ValueError('duplicate opportunity identity')
    dates=market.dates
    begin=int(dates.searchsorted(pd.Timestamp(start)))
    finish=int(dates.searchsorted(pd.Timestamp(end),side='right'))
    if finish-begin<2:
        raise ValueError('empty portfolio window')
    schedule={};rejections={}
    def reject(reason):rejections[reason]=rejections.get(reason,0)+1
    for row in e.to_dict('records'):
        t=row['ticker'];origin=pd.Timestamp(row['origin'])
        if t not in market.lookup or origin not in dates:
            reject('unknown_instrument_or_origin');continue
        fill=int(dates.get_loc(origin))+1+policy.delay
        if fill<begin or fill>=finish:continue
        if policy.selection in ('positive_rs','rs_rank') and (not np.isfinite(row['relative_momentum']) or row['relative_momentum']<=0):
            reject('relative_strength_not_positive');continue
        if policy.selection in ('ev_positive','ev_rank') and (not np.isfinite(row.get('expected_net_payoff',np.nan)) or row['expected_net_payoff']<=0):
            reject('expected_net_payoff_not_positive_or_unavailable');continue
        if policy.selection=='stop_rank' and not np.isfinite(row.get('p_stop',np.nan)):
            reject('risk_probability_unavailable');continue
        schedule.setdefault(fill,[]).append(row)
    positions={};cash=1.;receivable=0.;equity=[1.];exposure=[];opening_exposure=[];turnovers=[];trades=[];fills=[]
    rule=RULES[policy.exit_rule]
    peak_open_gross=0.;ambiguous_count=gap_exit_count=0

    def value(i,kind):
        return sum(p['quantity']*market.values[kind][i,k] for k,p in positions.items())

    for i in range(begin,finish):
        day=dates[i];turnover=0.
        if i>begin:
            cash *= (1+policy.cash_rate)**((dates[i]-dates[i-1]).days/365.25)
        # Actions belong to pre-existing holders; opening buyers do not receive today's dividend.
        for k,p in positions.items():
            o,h,l,c,dividend,split=market.bar(i,k)
            p['quantity']*=split
            p['stop']=p['stop']/split if p['stop'] is not None else None
            p['target']=p['target']/split if p['target'] is not None else None
            distribution=p['quantity']*dividend
            if policy.distribution_cash=='receivable':receivable+=distribution
            else:cash+=distribution
            p['received']+=distribution
        open_wealth=cash+receivable+value(i,'open')
        if not np.isfinite(open_wealth) or open_wealth<=0:raise ValueError('invalid opening wealth')

        def sell(k, price, reason, quantity=None):
            nonlocal cash,turnover
            p=positions[k]
            q=p['quantity'] if quantity is None else quantity
            notional=q*price;proceeds=notional*(1-policy.cost)
            cash+=proceeds;p['received']+=proceeds;p['quantity']-=q
            turnover+=notional/open_wealth
            fills.append({'date':str(day.date()),'ticker':market.names[k],'side':'sell','reason':reason,
                          'notional_equity_units':notional,'cost_equity_units':notional*policy.cost})
            if p['quantity']<=1e-13:
                trades.append({'event_id':p['event_id'],'ticker':market.names[k],
                               'origin':p['origin'],'entry_date':p['entry_date'],'exit_date':str(day.date()),
                               'reason':reason,'days_held':i-p['entry_index']+1,
                               'net_return_on_committed_cash':p['received']/p['spent']-1})
                del positions[k]

        # Only known opening exits may release capital before new opening entries.
        for k in list(positions):
            p=positions[k];o=market.values['open'][i,k]
            if p['pending_trailing']:
                sell(k,o,'trailing_next_open')
            elif p['stop'] is not None and o<=p['stop']:
                gap_exit_count+=1;sell(k,o,'gap_stop')
            elif p['target'] is not None and o>=p['target']:
                gap_exit_count+=1;sell(k,o,'gap_target')
        wealth=cash+receivable+value(i,'open');gross=value(i,'open')
        if gross>policy.gross_cap*wealth+1e-12:
            trim=(gross-policy.gross_cap*wealth)/(1-policy.gross_cap*policy.cost)
            fraction=min(1.,trim/gross)
            for k in list(positions):
                sell(k,market.values['open'][i,k],'common_gross_cap',positions[k]['quantity']*fraction)
        candidates=schedule.get(i,[])
        if policy.selection=='rs_rank':candidates=sorted(candidates,key=lambda r:(-r['relative_momentum'],r['ticker']))
        elif policy.selection=='ev_rank':candidates=sorted(candidates,key=lambda r:(-r['expected_net_payoff'],r['ticker']))
        elif policy.selection=='stop_rank':candidates=sorted(candidates,key=lambda r:(r['p_stop'],r['ticker']))
        else:candidates=sorted(candidates,key=lambda r:(r['ticker'],r['event_id']))
        for row in candidates:
            k=market.lookup[row['ticker']]
            if k in positions:reject('already_held');continue
            if len(positions)>=policy.maximum_positions:reject('position_limit');continue
            o,h,l,c,d,s=market.bar(i,k)
            if policy.sizing in ('mem','ewma'):
                forecast=row[policy.sizing+'_h5']
                if not np.isfinite(forecast) or forecast<=0:reject('forecast_unavailable');continue
                multiplier=min(1.,policy.target_vol/np.sqrt(252*forecast))
            else:multiplier=policy.static_multiplier if policy.sizing=='static' else 1.
            wealth=cash+receivable+value(i,'open');gross=value(i,'open')
            cap_room=max(0.,(policy.gross_cap*wealth-gross)/(1+policy.gross_cap*policy.cost))
            notional=min(policy.base_weight*wealth*multiplier,cap_room,cash/(1+policy.cost))
            if notional<1e-10:reject('cash_or_gross_limit');continue
            spent=notional*(1+policy.cost);cash-=spent;turnover+=notional/open_wealth
            positions[k]={'quantity':notional/o,'spent':spent,'received':0.,'entry_index':i,
                          'entry_date':str(day.date()),'origin':row['origin'],'event_id':row['event_id'],
                          'stop':o*(1-rule.stop) if rule.stop is not None else None,
                          'target':o*(1+rule.target) if rule.target is not None else None,
                          'pending_trailing':False}
            fills.append({'date':str(day.date()),'ticker':row['ticker'],'side':'buy','reason':policy.family,
                          'notional_equity_units':notional,'cost_equity_units':notional*policy.cost})
        gross=value(i,'open');wealth=cash+receivable+gross
        if cash < -1e-10 or gross/wealth > policy.gross_cap+1e-9:
            raise AssertionError('opening cash/gross constraint violated')
        peak_open_gross=max(peak_open_gross,gross/wealth)
        opening_exposure.append(gross/wealth)
        # Intraday exits occur AFTER all opening entries, with no same-open cash recycling.
        for k in list(positions):
            p=positions[k];o,h,l,c,d,s=market.bar(i,k)
            price,reason,ambiguous,gap=barrier_fill(o,h,l,p['stop'],p['target'],order=policy.barrier_order)
            if price is not None:
                ambiguous_count+=int(ambiguous);gap_exit_count+=int(gap)
                sell(k,price,'intraday_'+reason);continue
            if i-p['entry_index']+1>=rule.horizon:
                sell(k,c,'timeout');continue
            if rule.trailing_close:
                level=market.values['trail20'][i,k]
                p['pending_trailing']=bool(np.isfinite(level) and market.values['signal_close'][i,k]<level)
        if i==finish-1:
            for k in list(positions):sell(k,market.values['close'][i,k],'terminal_liquidation')
        gross=value(i,'close');wealth=cash+receivable+gross
        if not np.isfinite(wealth) or wealth<=0 or cash < -1e-10:raise AssertionError('invalid closing account')
        equity.append(wealth);exposure.append(gross/wealth);turnovers.append(turnover)
    d=dates[begin:finish]
    metrics=summarize(equity,d,exposure,turnovers,policy.cash_rate)
    metrics.update(policy=policy.name,family=policy.family,sizing=policy.sizing,selection=policy.selection,
                   exit_rule=policy.exit_rule,one_way_cost=policy.cost,cash_rate=policy.cash_rate,
                   delay=policy.delay,closed_trades=len(trades),ambiguous_exit_bars=ambiguous_count,
                   gap_exits=gap_exit_count,maximum_decision_open_gross=peak_open_gross,
                   terminal_trades=sum(t['reason']=='terminal_liquidation' for t in trades),
                   mean_decision_open_gross=float(np.mean(opening_exposure)),
                   distribution_cash_convention=policy.distribution_cash,
                   terminal_receivable_wealth=float(receivable))
    return {'metrics':metrics,'dates':d,'equity':np.asarray(equity),
            'returns':np.diff(np.asarray(equity))/np.asarray(equity)[:-1],
            'exposure':np.asarray(exposure),'opening_exposure':np.asarray(opening_exposure),
            'turnover':np.asarray(turnovers),
            'trades':pd.DataFrame(trades),'fills':pd.DataFrame(fills),'rejections':rejections}
