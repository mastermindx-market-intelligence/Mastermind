"""Deterministic seven-day budgeting; recommendations cannot reserve quota."""
from __future__ import annotations
import copy
import importlib
from datetime import datetime,timedelta,timezone
import pytest

START=datetime(2026,11,6,tzinfo=timezone.utc)
NOW=START+timedelta(hours=1)

def iso(t): return t.isoformat()

def snapshot(**changes):
    s={'schema':'mastermind.hermes_adviser_meter.v1','meter_id':'legacy-bot-1','window_id':'week-1',
       'window_start':iso(START),'window_end':iso(START+timedelta(days=7)),
       'observed_at':iso(NOW),'remaining_bps':10000,'spent_daily_bps':0,
       'spent_weekly_bps':0,'spent_urgent_bps':0,'spent_today_daily_bps':0,
       'reserved_daily_bps':0,'reserved_weekly_bps':0,'reserved_urgent_bps':0}
    s.update(changes);return s

def request(purpose='daily',estimate=500,**changes):
    r={'meter_id':'legacy-bot-1','window_id':'week-1','purpose':purpose,'estimate_bps':estimate}
    r.update(changes);return r

def evaluate(s=None,r=None,now=NOW):
    m=importlib.import_module('integrations.hermes_leadership.budget')
    return m.evaluate_adviser_budget(snapshot() if s is None else s,request() if r is None else r,now=now)

def hold(result):
    assert result['decision']=='HOLD'
    assert result['admitted'] is False and result['reservation_created'] is False
    assert result['capacity_recheck_required'] is True


def test_budget_module_exists():
    assert importlib.util.find_spec('integrations.hermes_leadership.budget') is not None


@pytest.mark.parametrize(('purpose','limit'), [('daily',1000),('weekly',1000),('urgent',2000)])
def test_exact_bucket_boundary(purpose,limit):
    one=evaluate(r=request(purpose,limit))
    assert one['decision']=='ELIGIBLE_FOR_CAPACITY_CHECK' and one['maximum_bps']==limit
    assert one['admitted'] is False and one['reservation_created'] is False
    hold(evaluate(r=request(purpose,limit+1)))


def test_daily_pacing_keeps_both_reserves():
    s=snapshot(remaining_bps=5000)
    out=evaluate(s,request(estimate=285))
    assert out['maximum_bps']==285 # (5000-2000-1000)//7
    assert out['decision']=='ELIGIBLE_FOR_CAPACITY_CHECK'
    hold(evaluate(s,request(estimate=286)))


def test_daily_limit_includes_spent_and_reservations():
    s=snapshot(remaining_bps=9500,spent_daily_bps=500,spent_today_daily_bps=500,reserved_daily_bps=200)
    assert evaluate(s,request(estimate=300))['maximum_bps']==300
    hold(evaluate(s,request(estimate=301)))


def test_reservations_are_not_added_to_budget_or_subtracted_twice():
    s=snapshot(reserved_weekly_bps=1000,reserved_urgent_bps=2000)
    assert evaluate(s,request(estimate=1000))['maximum_bps']==1000
    hold(evaluate(s,request('weekly',1)))
    hold(evaluate(s,request('urgent',1)))


def test_weekly_review_preserves_emergency_reserve():
    hold(evaluate(snapshot(remaining_bps=2000),request('weekly',1)))
    assert evaluate(snapshot(remaining_bps=2500),request('weekly',500))['maximum_bps']==500


def test_urgent_uses_only_remaining_urgent_bucket():
    s=snapshot(remaining_bps=8500,spent_urgent_bps=1500,reserved_urgent_bps=100)
    assert evaluate(s,request('urgent',400))['maximum_bps']==400
    hold(evaluate(s,request('urgent',401)))


@pytest.mark.parametrize('purpose,spent', [('daily','spent_daily_bps'),('weekly','spent_weekly_bps'),('urgent','spent_urgent_bps')])
def test_exhausted_and_overdrawn_bucket_holds(purpose,spent):
    cap={'daily':7000,'weekly':1000,'urgent':2000}[purpose]
    for amount in (cap,cap+1):
        hold(evaluate(snapshot(**{spent:amount,'remaining_bps':10000-amount}),request(purpose,1)))


def test_last_day_retains_daily_cap():
    now=START+timedelta(days=6,hours=1)
    s=snapshot(observed_at=iso(now),remaining_bps=4000,spent_daily_bps=6000)
    assert evaluate(s,request(estimate=1000),now=now)['maximum_bps']==1000
    hold(evaluate(s,request(estimate=1001),now=now))


@pytest.mark.parametrize('field,value', [('remaining_bps',True),('remaining_bps',10000.0),
 ('remaining_bps',-1),('remaining_bps',10001),('spent_daily_bps',float('nan')),
 ('spent_weekly_bps',None),('reserved_daily_bps',-1),('meter_id',''),('window_id','x\nsecret'),
 ('schema','wrong'),('observed_at','2026-11-06T01:00:00'),('window_start','bad')])
def test_malformed_snapshot_is_value_free_hold(field,value):
    result=evaluate(snapshot(**{field:value}))
    hold(result)
    assert result['reason']=='invalid_meter_snapshot'
    assert 'secret' not in str(result)


@pytest.mark.parametrize('changes', [{'extra':'SECRET'}, {'estimate_bps':True}, {'estimate_bps':0},
 {'estimate_bps':1.1},{'estimate_bps':10001},{'purpose':'poll_forever'},{'meter_id':[] }])
def test_malformed_request_is_hold(changes):
    result=evaluate(r=request(**changes));hold(result)
    assert 'SECRET' not in str(result)


@pytest.mark.parametrize('changes', [{'remaining_bps':9000,'spent_daily_bps':2000},
 {'remaining_bps':100,'reserved_daily_bps':101}, {'spent_today_daily_bps':1},
 {'remaining_bps':9000,'spent_daily_bps':500,'spent_weekly_bps':600}])
def test_inconsistent_accounting_holds(changes): hold(evaluate(snapshot(**changes)))


def test_extra_snapshot_field_refused(): hold(evaluate(snapshot(api_key='SECRET')))


@pytest.mark.parametrize('changes', [{'meter_id':'other'},{'window_id':'week-2'}])
def test_exact_meter_and_window_required(changes):
    out=evaluate(r=request(**changes));hold(out)
    assert out['reason']=='meter_window_mismatch'


@pytest.mark.parametrize('age',[301,-1])
def test_stale_or_future_observation_holds(age):
    hold(evaluate(snapshot(observed_at=iso(NOW-timedelta(seconds=age)))))


def test_freshness_boundary_inclusive():
    assert evaluate(snapshot(observed_at=iso(NOW-timedelta(seconds=300))))['decision']=='ELIGIBLE_FOR_CAPACITY_CHECK'


def test_reset_and_prior_day_snapshot_are_not_reused():
    hold(evaluate(now=START+timedelta(days=7)))
    boundary=START+timedelta(days=1)
    hold(evaluate(snapshot(observed_at=iso(boundary-timedelta(seconds=1))),now=boundary))


def test_non_weekly_window_holds():
    hold(evaluate(snapshot(window_end=iso(START+timedelta(days=8)))))


@pytest.mark.parametrize('now',[None,True,1,NOW.replace(tzinfo=None)])
def test_invalid_now_holds(now): hold(evaluate(now=now))


def test_offset_times_and_no_input_mutation():
    offset=timezone(timedelta(hours=5))
    s=snapshot(observed_at=NOW.astimezone(offset).isoformat())
    r=request(); before=copy.deepcopy((s,r))
    assert evaluate(s,r)==evaluate(s,r)
    assert (s,r)==before
    assert evaluate(s,r)['decision']=='ELIGIBLE_FOR_CAPACITY_CHECK'
