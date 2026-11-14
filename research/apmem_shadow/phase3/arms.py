"""Finite predeclared counterfactuals, not an optimization search space."""
from dataclasses import replace
from .portfolio import Policy


def core_policies():
    return [
        Policy('t1',family='t1'),Policy('t2',family='t2'),Policy('union'),
        Policy('union_ewma',sizing='ewma'),Policy('union_mem',sizing='mem'),
        Policy('union_rs',selection='positive_rs'),
        Policy('union_rs_mem',sizing='mem',selection='positive_rs'),
        Policy('union_rs_rank_mem',sizing='mem',selection='rs_rank'),
        Policy('union_time21',exit_rule='time21'),Policy('union_stop21',exit_rule='stop21'),
        Policy('union_trail63',exit_rule='trail63'),
        Policy('union_trail63_mem',exit_rule='trail63',sizing='mem'),
        Policy('breakout20',family='breakout20'),Policy('reclaim50',family='reclaim50'),
        Policy('trend63_126',family='trend63_126'),
        Policy('union_price_ev',selection='ev_positive'),
        Policy('union_risk_ev',selection='ev_positive'),
        Policy('union_interaction_ev',selection='ev_positive'),
        Policy('union_risk_ev_rank_mem',selection='ev_rank',sizing='mem'),
        Policy('union_stop_rank',selection='stop_rank'),
    ]


MODEL_ARMS={'union_price_ev':'price','union_risk_ev':'risk',
            'union_interaction_ev':'interaction','union_risk_ev_rank_mem':'risk',
            'union_stop_rank':'risk'}
SCENARIOS={'primary':{},'cost20':{'cost':.002},'delay1':{'delay':1},'cash3':{'cash_rate':.03}}
PORTFOLIO_CONTRASTS=(
    ('union_mem','union'),('union_ewma','union'),
    ('union_rs_mem','union_mem'),('union_rs_rank_mem','union_rs_mem'),
    ('union_risk_ev','union_price_ev'),('union_interaction_ev','union_risk_ev'),
    ('union_risk_ev_rank_mem','union_mem_model_common'),
    ('union_trail63','union'),('union_trail63_mem','union_trail63'),
    ('union_time21','union'),('union_stop21','union'),
)
CLASSIFIER_CONTRASTS=(('price','frequency'),('risk','price'),('interaction','risk'))
PRIMARY_TEST_FAMILY_SIZE=34


def scenario_policy(policy,scenario):
    if scenario not in SCENARIOS:raise ValueError('unregistered scenario')
    return replace(policy,**SCENARIOS[scenario])


def data_for_policy(events,predictions,policy):
    """Same risk-available opportunities; classifier arms share all-model coverage."""
    e=events[events.common_risk_available].copy()
    if policy.name in MODEL_ARMS or policy.name.endswith('_model_common'):
        if predictions.empty:return e.iloc[:0].assign(expected_net_payoff=float('nan'),p_stop=float('nan'))
        counts=predictions.groupby('event_id').model.nunique()
        common=set(counts[counts==4].index)
        e=e[e.event_id.isin(common)].copy()
        if policy.name in MODEL_ARMS:
            p=predictions[predictions.model.eq(MODEL_ARMS[policy.name])]
            if not p.event_id.is_unique:raise ValueError('duplicate conditional prediction')
            e=e.merge(p[['event_id','expected_net_payoff','p_stop']],on='event_id',how='inner',validate='one_to_one')
    return e
