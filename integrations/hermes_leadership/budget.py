"""Pure advisory seven-day Bot budget; Capacity owns atomic admission.

The host must supply a fresh observation of ONE actual provider meter and
exclusive, non-overlapping reservation totals from its existing Capacity owner.
Product labels, API keys and model suggestions are not independent quotas.
This function never observes a meter, reserves capacity or calls a provider.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import math
import re
from typing import Mapping

SCHEMA = 'mastermind.hermes_adviser_budget.v1'
METER_SCHEMA = 'mastermind.hermes_adviser_meter.v1'
MAX_AGE_SECONDS = 300
_BUCKETS = {'daily':7000,'weekly':1000,'urgent':2000}
_COUNT_FIELDS = frozenset({'remaining_bps','spent_daily_bps','spent_weekly_bps',
    'spent_urgent_bps','spent_today_daily_bps','reserved_daily_bps',
    'reserved_weekly_bps','reserved_urgent_bps'})
_METER_FIELDS = _COUNT_FIELDS | {'schema','meter_id','window_id','window_start',
                                'window_end','observed_at'}
_REQUEST_FIELDS = frozenset({'meter_id','window_id','purpose','estimate_bps'})
_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')


def _result(reason: str, maximum: int = 0, *, eligible: bool = False, **facts) -> dict:
    return {'schema':SCHEMA,'decision':'ELIGIBLE_FOR_CAPACITY_CHECK' if eligible else 'HOLD',
            'reason':reason,'maximum_bps':maximum,'admitted':False,
            'reservation_created':False,'capacity_recheck_required':True,**facts}


def _identifier(value: object) -> bool:
    return type(value) is str and _ID.fullmatch(value) is not None


def _count(value: object, *, positive: bool = False) -> bool:
    return type(value) is int and (1 if positive else 0) <= value <= 10000


def _utc(value: object) -> datetime:
    if type(value) is not str or len(value) > 40:
        raise ValueError('invalid_time')
    stamp = datetime.fromisoformat(value.replace('Z','+00:00'))
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError('timezone_required')
    return stamp.astimezone(timezone.utc)


def evaluate_adviser_budget(snapshot: Mapping[str,object], request: Mapping[str,object],
                             *, now: datetime) -> dict:
    """Recommend a bounded task only; caller must recheck/reserve atomically.

    remaining_bps is available provider quota BEFORE reservation subtraction.
    Spent totals and reservations are disjoint. Unknown external usage may
    reduce remaining quota but never creates a larger purpose allowance.
    Today's counter is relative to the provider's reset, not a guessed timezone.
    The fixed 70/10/20 policy applies only to a verified seven-day allowance.
    """
    if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
        return _result('invalid_now')
    now = now.astimezone(timezone.utc)
    if (type(snapshot) is not dict or set(snapshot) != _METER_FIELDS
            or snapshot.get('schema') != METER_SCHEMA
            or not _identifier(snapshot.get('meter_id'))
            or not _identifier(snapshot.get('window_id'))
            or any(not _count(snapshot.get(k)) for k in _COUNT_FIELDS)):
        return _result('invalid_meter_snapshot')
    if (type(request) is not dict or set(request) != _REQUEST_FIELDS
            or not _identifier(request.get('meter_id'))
            or not _identifier(request.get('window_id'))
            or type(request.get('purpose')) is not str
            or request['purpose'] not in _BUCKETS
            or not _count(request.get('estimate_bps'),positive=True)):
        return _result('invalid_request')
    if any(request[k] != snapshot[k] for k in ('meter_id','window_id')):
        return _result('meter_window_mismatch')
    try:
        start,end,observed = (_utc(snapshot[k]) for k in ('window_start','window_end','observed_at'))
    except (TypeError,ValueError,OverflowError):
        return _result('invalid_meter_snapshot')
    if end-start != timedelta(days=7):
        return _result('unsupported_meter_window')
    if not start <= now < end or not start <= observed < end:
        return _result('window_not_current')
    age = (now-observed).total_seconds()
    if age < 0 or age > MAX_AGE_SECONDS:
        return _result('meter_not_fresh')
    if (now-start).days != (observed-start).days:
        return _result('daily_counter_not_current')

    spent = {p:snapshot['spent_'+p+'_bps'] for p in _BUCKETS}
    reserved = {p:snapshot['reserved_'+p+'_bps'] for p in _BUCKETS}
    remaining = snapshot['remaining_bps']
    if (sum(spent.values()) > 10000-remaining or sum(reserved.values()) > remaining
            or snapshot['spent_today_daily_bps'] > spent['daily']):
        return _result('inconsistent_meter_accounting')
    bucket = {p:max(0,_BUCKETS[p]-spent[p]-reserved[p]) for p in _BUCKETS}
    available = remaining-sum(reserved.values())
    purpose = request['purpose']
    if purpose == 'daily':
        days = max(1,math.ceil((end-now).total_seconds()/86400))
        unreserved_daily = max(0,available-bucket['weekly']-bucket['urgent'])
        today = max(0,1000-snapshot['spent_today_daily_bps']-reserved['daily'])
        maximum = min(bucket['daily'],today,unreserved_daily//days)
    elif purpose == 'weekly':
        maximum = min(bucket['weekly'],max(0,available-bucket['urgent']))
    else:
        maximum = min(bucket['urgent'],available)
    eligible = request['estimate_bps'] <= maximum
    return _result('within_policy' if eligible else 'purpose_budget_exceeded',maximum,
        eligible=eligible,meter_id=snapshot['meter_id'],window_id=snapshot['window_id'],
        purpose=purpose,as_of=observed.isoformat(),window_end=end.isoformat())
