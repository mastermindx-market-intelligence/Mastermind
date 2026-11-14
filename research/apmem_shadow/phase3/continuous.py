"""Persistent-momentum controls, separate from rare event-triggered entries.

Targets use the preceding close. The self-financing solve includes actual weight
drift and turnover costs. Distribution receivables are wealth, not spending cash.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from .portfolio import Market,summarize


@dataclass(frozen=True)
class ContinuousPolicy:
    name: str
    selection: str = 'relative'
    selection_cadence: int = 21
    sizing: str = 'none'
    risk_cadence: int = 21
    cost: float = .0005
    target_vol: float = .30
    cash_rate: float = 0.
    gross_cap: float = .80
    base_weight: float = .08
    slots: int = 10

    def validate(self):
        if (self.selection not in ('relative','identifier') or self.sizing not in ('none','mem','ewma')
                or any(type(v) is not int or v<1 for v in (self.selection_cadence,self.risk_cadence,self.slots))
                or not np.isfinite([self.cost,self.target_vol,self.cash_rate,self.gross_cap,self.base_weight]).all()
                or not 0<=self.cost<.1 or not 0<self.target_vol<=2 or not 0<=self.cash_rate<1
                or not 0<self.base_weight<=self.gross_cap<=1):
            raise ValueError('invalid continuous research policy')


def controls():
    return [ContinuousPolicy('trend_identifier_monthly',selection='identifier'),
            ContinuousPolicy('trend_relative_monthly'),
            ContinuousPolicy('trend_relative_mem_daily',sizing='mem',risk_cadence=1),
            ContinuousPolicy('trend_relative_ewma_daily',sizing='ewma',risk_cadence=1),
            ContinuousPolicy('trend_relative_mem_monthly',sizing='mem'),
            ContinuousPolicy('trend_relative_daily',selection_cadence=1,risk_cadence=1)]


def rebalance_targets(cash,receivable,holdings,weights,cost):
    """Return post-cost holdings and liquid cash; all arguments are dollar units."""
    h,w=np.asarray(holdings,float),np.asarray(weights,float)
    if (h.shape!=w.shape or h.ndim!=1 or not np.isfinite(h).all() or not np.isfinite(w).all()
            or (h<0).any() or (w<0).any() or w.sum()>1+1e-12
            or not np.isfinite([cash,receivable,cost]).all() or min(cash,receivable,cost)<0 or cost>=.1):
        raise ValueError('invalid rebalance arguments')
    wealth=cash+receivable+h.sum()
    if wealth<=0:raise ValueError('nonpositive account wealth')
    # Conservative liquid-wealth bound, including the maximum sale/buy fee bill.
    liquid_budget=max(0.,(cash+h.sum()-cost*h.sum())/(wealth*(1+cost)))
    if w.sum()>liquid_budget and w.sum()>0:w=w*(liquid_budget/w.sum())
    lo,hi=0.,wealth
    for _ in range(55):
        mid=(lo+hi)/2
        residual=mid+cost*np.abs(w*mid-h).sum()-wealth
        if residual>0:hi=mid
        else:lo=mid
    after=(lo+hi)/2;target=w*after;delta=target-h
    sales=-np.minimum(delta,0).sum();buys=np.maximum(delta,0).sum()
    fee=cost*(sales+buys)
    remaining=cash+sales*(1-cost)-buys*(1+cost)
    if remaining < -1e-9 or abs(remaining+receivable+target.sum()-after)>1e-9:
        raise AssertionError('self-financing target solve failed')
    return target,max(0.,remaining),float(fee),float(sales+buys)


def simulate(market: Market,features: dict[str,pd.DataFrame],policy: ContinuousPolicy,
             start='2020-01-02',end='2026-06-02'):
    policy.validate();dates=market.dates
    begin=int(dates.searchsorted(pd.Timestamp(start)));finish=int(dates.searchsorted(pd.Timestamp(end),side='right'))
    if begin<1 or finish-begin<2:raise ValueError('prior close and nonempty evaluation window required')
    required=('eligible','relative_momentum','mem_h5','ewma_h5')
    if set(features)!=set(market.names):raise ValueError('feature instrument set differs')
    values={k:np.column_stack([features[t][k].reindex(dates).to_numpy(float) for t in market.names]) for k in required}
    quantity=np.zeros(len(market.names));cash=1.;receivable=0.;equity=[1.]
    opened=[];closed=[];turnover=[];holdings=[];fees=[];selected=[];rebalances=0
    transactions=0;cap_trims=0
    for i in range(begin,finish):
        if i>begin:cash*=(1+policy.cash_rate)**((dates[i]-dates[i-1]).days/365.25)
        held=quantity>1e-14
        for k in np.flatnonzero(held):market.bar(i,int(k))
        quantity*=np.where(held,market.values['split'][i],1.)
        receivable+=float(np.sum(np.where(held,quantity*market.values['dividend'][i],0.)))
        old=np.where(quantity>1e-14,quantity*market.values['open'][i],0.)
        wealth=cash+receivable+old.sum();step=i-begin
        choose=step%policy.selection_cadence==0
        if choose:
            eligible=(values['eligible'][i-1]==1)&np.isfinite(values['mem_h5'][i-1])&np.isfinite(values['ewma_h5'][i-1])
            eligible&=(values['mem_h5'][i-1]>0)&(values['ewma_h5'][i-1]>0)
            candidates=np.flatnonzero(eligible).tolist()
            if policy.selection=='relative':
                candidates=[k for k in candidates if np.isfinite(values['relative_momentum'][i-1,k]) and values['relative_momentum'][i-1,k]>0]
                candidates.sort(key=lambda k:(-values['relative_momentum'][i-1,k],market.names[k]))
            selected=candidates[:policy.slots]
        rebalance=choose or (policy.sizing!='none' and step%policy.risk_cadence==0)
        daily_turnover=0.;daily_fee=0.
        if rebalance:
            weights=np.zeros(len(quantity))
            for k in selected:
                market.bar(i,int(k))
                if policy.sizing=='none':scale=1.
                else:
                    forecast=values[policy.sizing+'_h5'][i-1,k]
                    scale=min(1.,policy.target_vol/np.sqrt(252*forecast)) if np.isfinite(forecast) and forecast>0 else 0.
                weights[k]=policy.base_weight*scale
            if weights.sum()>policy.gross_cap:weights*=policy.gross_cap/weights.sum()
            target,cash,fee,traded=rebalance_targets(cash,receivable,old,weights,policy.cost)
            transactions+=int(np.sum(np.abs(target-old)>1e-10));daily_fee+=fee;daily_turnover+=traded/wealth
            quantity=np.divide(target,market.values['open'][i],out=np.zeros(len(quantity)),where=target>0)
            rebalances+=1
        elif old.sum()>policy.gross_cap*wealth+1e-12:
            trim=(old.sum()-policy.gross_cap*wealth)/(1-policy.gross_cap*policy.cost)
            fraction=min(1.,trim/old.sum());quantity*=1-fraction
            cash+=trim*(1-policy.cost);daily_fee+=trim*policy.cost;daily_turnover+=trim/wealth;cap_trims+=1
        gross=float(np.sum(np.where(quantity>1e-14,quantity*market.values['open'][i],0.)))
        open_wealth=cash+receivable+gross
        if cash < -1e-10 or gross/open_wealth>policy.gross_cap+1e-9:raise AssertionError('continuous opening cap/cash violation')
        opened.append(gross/open_wealth)
        close_values=np.where(quantity>1e-14,quantity*market.values['close'][i],0.)
        if not np.isfinite(close_values).all():raise ValueError('missing held closing observation')
        if i==finish-1:
            liquidation=float(close_values.sum());cash+=liquidation*(1-policy.cost)
            daily_fee+=liquidation*policy.cost;daily_turnover+=liquidation/wealth
            transactions+=int(np.sum(quantity>1e-14));quantity[:]=0.;close_values[:]=0.
        wealth=cash+receivable+close_values.sum()
        equity.append(wealth);closed.append(float(close_values.sum()/wealth));turnover.append(daily_turnover);fees.append(daily_fee)
        holdings.append(close_values/wealth)
    day=dates[begin:finish]
    metrics=summarize(equity,day,closed,turnover,policy.cash_rate)
    metrics.update(policy=policy.name,mean_decision_open_gross=float(np.mean(opened)),
                   maximum_decision_open_gross=float(np.max(opened)),rebalances=rebalances,
                   transaction_count=transactions,common_cap_trims=cap_trims,
                   terminal_receivable_wealth=float(receivable),one_way_cost=policy.cost,
                   selected_constituents_cadence=policy.selection_cadence,risk_update_cadence=policy.risk_cadence,
                   distribution_cash_convention='receivable',exploratory_control=True)
    return {'metrics':metrics,'dates':day,'equity':np.asarray(equity),'returns':np.diff(equity)/np.asarray(equity)[:-1],
            'opening_exposure':np.asarray(opened),'exposure':np.asarray(closed),
            'turnover':np.asarray(turnover),'fees':np.asarray(fees),
            'holdings_weights':np.asarray(holdings),'instruments':market.names}
