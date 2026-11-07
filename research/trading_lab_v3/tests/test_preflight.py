from dataclasses import replace
from datetime import timedelta, datetime
from decimal import Decimal as D
import copy
import json
import pytest
from backend.preflight import Plan, Context, Position, ContractError, number, evaluate, review_binding, verify_preview
from backend.fixtures import NOW, SAMPLE_PLAN, context, CASES


def plan(**kw):
    return Plan.from_payload({**SAMPLE_PLAN, **kw})


def codes(result):
    return {x['code'] for x in result['checks']}


def reviewed(p, c):
    return replace(c, review_state='complete', reviewed_binding=review_binding(p, c), review_valid_until=NOW+timedelta(seconds=15))


def test_real_economic_preview_is_not_fake_ai_or_execution():
    r = evaluate(plan(), context(), now=NOW)
    assert r['state'] == 'REVIEW_NEEDED'
    assert r['preview']['value'] == '5025.00'
    assert r['preview']['cash_after'] == '64975.00'
    assert r['preview']['shares_after'] == '1250'
    assert r['valuation']['equity'] == '100000.00'
    assert r['preview']['equity_after'] == '99975.00'
    assert r['forecast_probability'] is None
    assert r['thesis_quality'] == 'NOT_ASSESSED_BY_THIS_ENGINE'
    assert r['execution_authority'] is False and r['order_submitted'] is False


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity', '-1', '0', '1e99', '1e-99', True, False, 1.5, None, {}, []])
def test_malformed_amounts_refused(value):
    with pytest.raises(ContractError):
        plan(amount=value)


@pytest.mark.parametrize('field,value', [('review_state','complete'),('user_id','other'),('account_id','other'),
    ('cash','999999'),('quote_ask','1'),('market_generation','forged'),('evidence_score',100)])
def test_browser_cannot_supply_owner_facts(field,value):
    with pytest.raises(ContractError):
        plan(**{field:value})


@pytest.mark.parametrize('field,value', [('side','short'), ('horizon','forever'), ('unit','percent'),
    ('instrument_id','../../secrets'),('thesis',123), ('thesis','x'*4001), ('thesis','hello\x00world')])
def test_invalid_plan_contract(field,value):
    with pytest.raises(ContractError):
        plan(**{field:value})


@pytest.mark.parametrize('case', CASES)
def test_no_case_grants_execution(case):
    r = evaluate(plan(), context(case), now=NOW)
    assert r['execution_authority'] is False
    assert r['binding_is_authorization'] is False
    assert r['order_submitted'] is False
    json.dumps(r, allow_nan=False)


def test_oversize_is_not_silently_clamped():
    r = evaluate(plan(amount='5000'), context(), now=NOW)
    assert 'INSUFFICIENT_CASH' in codes(r)
    assert r['preview']['shares'] == '5000'
    assert r['preview']['cash_after'] is None


def test_reserved_cash_is_unavailable():
    c = replace(context(), reserved_cash=D('69000'))
    assert 'INSUFFICIENT_CASH' in codes(evaluate(plan(),c,now=NOW))


def test_reserved_shares_cannot_be_sold_twice():
    r = evaluate(plan(side='sell', amount='950'), context(), now=NOW)
    assert 'INSUFFICIENT_SHARES' in codes(r)


def test_reduction_not_held_by_deep_review_outage():
    r = evaluate(plan(side='sell', amount='100', thesis='', trigger='', invalidation='', counter_case=''), context(), now=NOW)
    assert r['state'] == 'REDUCTION_PREVIEW'
    assert r['preview']['cash_after'] == '72000.00'
    assert not any(k.startswith('REVIEW') for k in codes(r))


def test_sell_still_requires_current_bid_and_account():
    for case in ('quote_expired', 'account_error', 'market_closed'):
        assert evaluate(plan(side='sell'), context(case), now=NOW)['state'] == 'BLOCKED'


def test_missing_mark_never_equals_zero_or_average_cost():
    r = evaluate(plan(), context('missing_marks'), now=NOW)
    assert r['valuation']['equity'] is None
    assert r['preview']['position_weight_after'] is None
    assert r['valuation']['available_cash'] == '65000.00'
    assert 'LIMIT_NOT_EVALUABLE' in codes(r)


def test_reduction_can_preview_without_unrelated_mark():
    r = evaluate(plan(side='sell'), context('missing_marks'), now=NOW)
    assert r['state'] == 'REDUCTION_PREVIEW' and r['valuation']['equity'] is None


@pytest.mark.parametrize('mode', ['REAL','REPLAY','SYNTHETIC'])
def test_account_mode_fence(mode):
    assert 'WRONG_MODE' in codes(evaluate(plan(),replace(context(),mode=mode),now=NOW))


def test_future_quotes_block():
    c = replace(context(), quote_observed_at=NOW+timedelta(seconds=1),quote_received_at=NOW+timedelta(seconds=2))
    assert 'FUTURE_QUOTE' in codes(evaluate(plan(),c,now=NOW))


def test_expiry_is_exclusive():
    c = context()
    assert 'QUOTE_EXPIRED' in codes(evaluate(plan(),c,now=c.quote_valid_until))


def test_missing_ask_not_replaced_with_bid_or_last():
    r = evaluate(plan(),replace(context(),quote_ask=None),now=NOW)
    assert 'NO_EXECUTABLE_QUOTE' in codes(r) and r['preview']['value'] is None


def test_crossed_quote_is_malformed():
    with pytest.raises(ContractError):
        evaluate(plan(),replace(context(),quote_bid=D('22')),now=NOW)


def test_quote_refresh_preserves_thesis_review_but_invalidates_economic_preview():
    p = plan(); c = reviewed(p,context()); r = evaluate(p,c,now=NOW)
    assert r['state'] == 'PREVIEW_READY'
    assert verify_preview(r,p,c,now=NOW)
    changed = replace(c, quote_ask=D('20.11'))
    assert evaluate(p,changed,now=NOW)['evidence_review'] == 'complete'
    assert evaluate(p,changed,now=NOW)['preview']['value'] == '5027.50'
    assert not verify_preview(r,p,changed,now=NOW)


@pytest.mark.parametrize('change', ['thesis','trigger','invalidation','counter_case','horizon','side'])
def test_every_thesis_meaning_change_invalidates_review(change):
    p=plan();c=reviewed(p,context())
    raw=dict(SAMPLE_PLAN)
    raw[change]={'amount':'251','horizon':'investment','side':'sell','unit':'dollars'}.get(change,'changed intent')
    p2=Plan.from_payload(raw)
    assert review_binding(p2,c) != c.reviewed_binding


@pytest.mark.parametrize('change,value', [('account_version',8),('policy_version',3),('market_generation','new-market'),
    ('evidence_generation','corrected-evidence'),('cash',D('69999')),('reserved_cash',D('1')),('principal_id','other-user'),
    ('account_id','other-account'),('max_name_weight',D('0.30'))])
def test_owner_changes_invalidate_preview(change,value):
    p=plan(); c=reviewed(p,context());r=evaluate(p,c,now=NOW)
    assert not verify_preview(r,p,replace(c,**{change:value}),now=NOW)


def test_reviewer_status_downgrade_invalidates_preview():
    p=plan(); c=reviewed(p,context()); r=evaluate(p,c,now=NOW)
    assert not verify_preview(r,p,replace(c,review_state='failed'),now=NOW)


def test_reviewer_expiry_invalidates_preview():
    p=plan(); c=reviewed(p,context()); r=evaluate(p,c,now=NOW)
    assert not verify_preview(r,p,c,now=NOW+timedelta(seconds=15))


def test_advisory_does_not_mislabel_review_complete():
    r=evaluate(plan(),context('advisory'),now=NOW)
    assert r['state']=='UNREVIEWED_PREVIEW'
    assert r['evidence_review']=='not_current'


@pytest.mark.parametrize('field', ['thesis','trigger','invalidation','counter_case'])
def test_next_action_points_to_missing_field(field):
    r=evaluate(plan(**{field:''}),context(),now=NOW)
    assert r['state']=='PLAN_INCOMPLETE'
    assert r['checks'][0]['field']==field and r['next_action']=='edit_plan'


def test_notional_sizing_explicit_round_down():
    r=evaluate(plan(unit='dollars',amount='1000'),context(),now=NOW)
    assert r['preview']['shares']=='49'
    assert r['preview']['value']=='984.90'
    assert 'NOTIONAL_ROUNDING' in codes(r)


def test_share_sizing_never_silent_rounding():
    assert 'INVALID_SHARE_INCREMENT' in codes(evaluate(plan(amount='1.5'),context(),now=NOW))


def test_tiny_order_cannot_round_to_free_money():
    c=replace(context(),share_step=D('0.000001'))
    assert 'BELOW_CASH_PRECISION' in codes(evaluate(plan(amount='0.000001'),c,now=NOW))


def test_empty_account_has_cash_value_without_fake_positions():
    r=evaluate(plan(),replace(context(),positions=()),now=NOW)
    assert r['valuation']['equity']=='70000.00'


def test_explicit_concentration_limit():
    r=evaluate(plan(amount='1000'),context(),now=NOW)
    assert 'NAME_LIMIT' in codes(r)


def test_horizon_context_mismatch_warns_not_fabricated_matching_state():
    r=evaluate(plan(horizon='investment'),context(),now=NOW)
    assert 'MARKET_CONTEXT_UNFIT' in codes(r)
    assert r['forecast_probability'] is None


@pytest.mark.parametrize('change,value', [('cash',D('-1')),('cash','70000'),('cash',D('NaN')),
    ('reserved_cash',D('70001')),('account_version',True),('policy_version',-1),('max_name_weight',D('2')),
    ('session','extended'),('policy_mode','whatever'),('quote_currency','HKD'),('review_is_fixture','yes')])
def test_bad_owner_state_fails_closed(change,value):
    with pytest.raises(ContractError):
        evaluate(plan(),replace(context(),**{change:value}),now=NOW)


def test_duplicate_positions_cannot_double_count_equity():
    c=context()
    with pytest.raises(ContractError):
        evaluate(plan(),replace(c,positions=(c.positions[0],c.positions[0])),now=NOW)


def test_naive_clock_refused():
    with pytest.raises(ContractError):
        evaluate(plan(),context(),now=datetime(2026,9,9))


def test_pure_no_input_mutation_and_repeatable():
    p=plan(); c=context(); before=copy.deepcopy((p,c))
    a=evaluate(p,c,now=NOW); b=evaluate(p,c,now=NOW)
    assert a==b and (p,c)==before


def test_semantically_equal_decimal_input_same_identity():
    assert plan(amount='250.00').fingerprint==plan(amount='250').fingerprint


def test_fixture_review_only_matches_original_example():
    c=context('reviewed_example')
    assert evaluate(plan(),c,now=NOW)['evidence_review']=='fixture_complete'
    assert evaluate(plan(amount='251'),c,now=NOW)['evidence_review']=='fixture_complete'
    assert 'REVIEW_INVALIDATED' in codes(evaluate(plan(thesis='Changed mechanism'),c,now=NOW))


@pytest.mark.parametrize('change', ['amount','unit'])
def test_sizing_does_not_require_another_ai_thesis_review(change):
    p=plan(); c=reviewed(p,context()); old=evaluate(p,c,now=NOW)
    p2=plan(**{change:'251' if change=='amount' else 'dollars'})
    new=evaluate(p2,c,now=NOW)
    assert new['evidence_review']=='complete'
    assert new['review_binding']==old['review_binding']
    assert new['binding']!=old['binding']
    assert not verify_preview(old,p2,c,now=NOW)


def test_valid_thesis_never_bypasses_new_economic_risk():
    p=plan(); c=reviewed(p,context())
    r=evaluate(plan(amount='5000'),c,now=NOW)
    assert r['evidence_review']=='complete' and r['state']=='BLOCKED'
    assert 'INSUFFICIENT_CASH' in codes(r)


@pytest.mark.parametrize('key,value', [('evidence_generation','correction'),
    ('market_generation','transition'),('policy_version',9),('principal_id','another')])
def test_material_context_changes_do_require_new_review(key,value):
    p=plan();c=reviewed(p,context())
    assert 'REVIEW_INVALIDATED' in codes(evaluate(p,replace(c,**{key:value}),now=NOW))


def test_reservations_refresh_without_new_thesis_review():
    p=plan();c=reviewed(p,context())
    r=evaluate(p,replace(c,reserved_cash=D('69000')),now=NOW)
    assert r['evidence_review']=='complete' and r['state']=='BLOCKED'


def test_review_scope_is_not_a_quality_or_execution_promise():
    r=evaluate(plan(),context('reviewed_example'),now=NOW)
    assert r['review_scope']=='thesis_and_context_only'
    assert r['economic_checks_recomputed'] is True
    assert r['forecast_probability'] is None and r['execution_authority'] is False
