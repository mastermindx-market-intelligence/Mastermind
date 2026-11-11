"""Read-only paid Capacity observation over the incumbent paid owner gateway.

Source-only observer: it grants nothing. ``provider_readiness`` is always
UNKNOWN; the Runtime parent independently owns availability and admission.
Every projected fact is a retained cache reading or lease row obtained through
the actual owner's own handles. No live provider, refresh, write, credential,
process or network access exists on this path, and no data shape ever becomes
authorization.
"""
from __future__ import annotations

import json
import math
import re
import time
from datetime import datetime, timezone

from control_plane.paid_model_execution_contract import (
    ADAPTER_ID, PROFILE_ID, canonical, digest,
)

SCHEMA_VERSION = 'mastermind.paid_fabric_capacity_observation/v1'
PROVIDER = 'glm'
POOL = 'glm'
MODELS = frozenset({'glm-5.3', 'glm-5.3-flash'})
PROVIDER_READINESS = 'UNKNOWN'

OBSERVATION_TTL_S = 15.0
FRESH_LIMIT_S = 300.0
FUTURE_TOLERANCE_S = 5.0
QUERY_LIMIT = 4097
MAX_ROWS = 4096

_OBSERVATION_STATES = frozenset({'OBSERVED', 'OFFLINE'})
_REASONS = frozenset({
    'OBSERVED', 'ACCOUNT_UNKNOWN', 'INVALID_READING', 'CONTRADICTORY_TIME',
    'INCOHERENT_READING', 'STALE_READING', 'ACTIVE_COOLDOWN',
    'FULL_UTILIZATION', 'BROKER_UNAVAILABLE', 'BROKER_OVERFLOW',
    'EXPIRED_RETAINED', 'STATUS_NOT_OBSERVED'})
_MEMBERSHIP = frozenset({'PRESENT', 'UNKNOWN'})
_FRESHNESS = frozenset({'FRESH', 'STALE', 'UNKNOWN'})
_BROKER_FRESHNESS = frozenset({'OBSERVED', 'UNKNOWN'})
_COOLDOWN = frozenset({'YES', 'NO', 'UNKNOWN'})

_ACCOUNT_FIELDS = frozenset({'membership', 'freshness', 'observed_at',
    'age_seconds', 'pct_5h', 'pct_week', 'exhausted_until', 'next_reset_5h',
    'cooldown', 'canonical_status_state', 'canonical_status_observed_at'})
_BROKER_FIELDS = frozenset({'freshness', 'held_pool', 'held_account',
    'held_model', 'held_host', 'held_route', 'legacy_model_count',
    'expired_retained_count', 'rows_observed'})
_BROKER_COUNTS = frozenset({'held_pool', 'held_account', 'held_model',
    'held_host', 'held_route', 'legacy_model_count', 'expired_retained_count',
    'rows_observed'})
_SCOPE_FIELDS = frozenset({'worker_id', 'provider', 'host_ref', 'model',
    'account_label', 'quota_class', 'pool', 'physical_binding_sha256',
    'worker_source_config_digest', 'transport_host'})
_TOP_FIELDS = frozenset({'schema_version', 'profile_id', 'adapter_id',
    'observation_state', 'reason', 'observed_at', 'expires_at', 'scope',
    'account', 'broker', 'provider_readiness'})

_STATE_FIELDS = frozenset({'exhausted_until_ts', 'last_pct_5h',
    'last_pct_week', 'observed_at', 'next_reset_5h'})
_SNAPSHOT_FIELDS = frozenset({'name', 'exhausted_until', 'pct_5h',
    'pct_week', 'observed_at'})

_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_EPOCH_MAX = 10.0 ** 11
_MS_EPOCH = 10.0 ** 10

_LEASE_SQL = ('SELECT pool,account,model,host,state,granted_at,ttl,'
              'last_heartbeat,renewable FROM leases '
              "WHERE state IN ('held','rented') AND (pool=? OR host=?) "
              'LIMIT ?')


def _now():
    """Local clock anchor; tests monkeypatch this module hook, not arguments."""
    return time.time()


class PaidCapacityRefused(ValueError):
    """Invalid observation arguments or a refused actual-owner guard."""


class _ReadingError(Exception):
    """A retained account reading cannot be normalized; never escapes."""


def _refuse():
    raise PaidCapacityRefused('canonical_paid_capacity_refused')


def _normalize_epoch(value):
    """Mirror the incumbent shim source parser for retained timestamps."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise _ReadingError()
    if type(value) in (int, float):
        seconds = float(value)
        if not math.isfinite(seconds):
            raise _ReadingError()
    elif type(value) is datetime:
        moment = value if value.tzinfo is not None else value.replace(
            tzinfo=timezone.utc)
        seconds = moment.astimezone(timezone.utc).timestamp()
    elif type(value) is str:
        text = value.strip()
        if not text or text.lower() in ('none', 'null', 'unknown'):
            return None
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            raise _ReadingError() from None
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        seconds = moment.astimezone(timezone.utc).timestamp()
    else:
        raise _ReadingError()
    if seconds <= 0.0:
        return None
    if seconds > _MS_EPOCH:
        seconds /= 1000.0
    if not math.isfinite(seconds) or seconds > _EPOCH_MAX:
        raise _ReadingError()
    return seconds


def _normalize_pct(value):
    if value is None:
        return None
    if type(value) not in (int, float):
        raise _ReadingError()
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 100.0:
        raise _ReadingError()
    return number


def _normalize_exhausted(value):
    if value is None:
        return None
    if type(value) not in (int, float):
        raise _ReadingError()
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise _ReadingError()
    return number if number > 0.0 else None


def _plain_data(value):
    stack = [(value, 0)]
    nodes = size = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > 2048 or depth > 12:
            _refuse()
        if type(item) is dict:
            if any(type(k) is not str for k in item):
                _refuse()
            stack.extend((v, depth + 1) for v in item.values())
        elif type(item) is str:
            size += len(item.encode('utf-8'))
            if len(item) > 4096 or size > 65536 or '\x00' in item:
                _refuse()
        elif item is None or type(item) is int:
            pass
        elif type(item) is float and math.isfinite(item):
            pass
        else:
            _refuse()


def _check_projection(physical, source_config):
    """Reuse the actual pure source owner; never construct a fake launch."""
    from control_plane.paid_fabric_wire import require_paid_source
    try:
        _plain_data(physical)
        _plain_data(source_config)
        require_paid_source(physical, source_config)
    except Exception:
        _refuse()


def _require_arguments(owner, physical, source_config, account_label,
                       quota_class):
    """Validate public arguments and the exact owner class before any read."""
    from control_plane.paid_fabric_backend import CanonicalPaidBackend
    if type(owner) is not CanonicalPaidBackend:
        _refuse()
    if (type(account_label) is not str or not _ID.fullmatch(account_label)
            or type(quota_class) is not str or not _ID.fullmatch(quota_class)):
        _refuse()
    _check_projection(physical, source_config)
    return CanonicalPaidBackend


_CANONICAL_STATES = frozenset({'PENDING', 'OBSERVED', 'AUTH_REFUSED', 'RATE_LIMITED', 'UNKNOWN'})


def _empty_account(reason, membership='PRESENT'):
    return dict(membership=membership, freshness='UNKNOWN', observed_at=None,
        age_seconds=None, pct_5h=None, pct_week=None, exhausted_until=None,
        next_reset_5h=None, cooldown='UNKNOWN', canonical_status_state='UNKNOWN',
        canonical_status_observed_at=None, reason=reason)


def _cache_data(value):
    if type(value) is not dict or any(type(k) is not str for k in value):
        return False
    return all(v is None or type(v) in (str, int, float, datetime) for v in value.values())


def _read_account(table, account_label, names, snapshot_rows, state_first, state, now):
    """Join only actual retained state and same-response canonical provenance."""
    if account_label not in names:
        return _empty_account('ACCOUNT_UNKNOWN', 'UNKNOWN')
    if (not _cache_data(state_first) or not _cache_data(state)
            or type(snapshot_rows) is not list or len(snapshot_rows) > 64):
        return _empty_account('INVALID_READING')
    allowed = _STATE_FIELDS | {'canonical_status_state', 'canonical_status_observed_at'}
    if (state_first != state or set(state_first) not in (_STATE_FIELDS, allowed)):
        return _empty_account('INCOHERENT_READING')
    selected = [row for row in snapshot_rows if type(row) is dict and type(row.get('name')) is str
                and row['name'] == account_label]
    if (len(selected) != 1 or not _cache_data(selected[0]) or set(selected[0]) != _SNAPSHOT_FIELDS
            or any(selected[0][target] != state_first[source] for target, source in (
                ('exhausted_until', 'exhausted_until_ts'), ('pct_5h', 'last_pct_5h'),
                ('pct_week', 'last_pct_week'), ('observed_at', 'observed_at')))):
        return _empty_account('INCOHERENT_READING')
    try:
        observed_at = _normalize_epoch(state_first['observed_at'])
        pct_5h = _normalize_pct(state_first['last_pct_5h'])
        pct_week = _normalize_pct(state_first['last_pct_week'])
        exhausted_until = _normalize_exhausted(state_first['exhausted_until_ts'])
        next_reset_5h = _normalize_epoch(state_first['next_reset_5h'])
        status = state_first.get('canonical_status_state', 'UNKNOWN')
        if type(status) is not str or status not in _CANONICAL_STATES:
            raise _ReadingError()
        status_at = _normalize_epoch(state_first.get('canonical_status_observed_at'))
    except (ValueError, TypeError, OverflowError, _ReadingError):
        return _empty_account('INVALID_READING')
    age = max(0.0, now - observed_at) if observed_at is not None else None
    freshness = ('UNKNOWN' if observed_at is None else
                 'STALE' if age >= FRESH_LIMIT_S else 'FRESH')
    reason = None
    if observed_at is not None and observed_at > now + FUTURE_TOLERANCE_S:
        reason = 'CONTRADICTORY_TIME'
    elif (observed_at is None or pct_5h is None or pct_week is None
            or exhausted_until is None and state_first['exhausted_until_ts'] is None):
        reason = 'INVALID_READING'
    elif status != 'OBSERVED' or status_at is None or status_at != observed_at:
        reason = 'STATUS_NOT_OBSERVED'
    elif exhausted_until is not None and exhausted_until > now:
        reason = 'ACTIVE_COOLDOWN'
    elif pct_5h == 100.0 or pct_week == 100.0:
        reason = 'FULL_UTILIZATION'
    elif freshness != 'FRESH':
        reason = 'STALE_READING' if freshness == 'STALE' else 'INVALID_READING'
    return dict(membership='PRESENT', freshness=freshness, observed_at=observed_at,
        age_seconds=age, pct_5h=pct_5h, pct_week=pct_week, exhausted_until=exhausted_until,
        next_reset_5h=next_reset_5h,
        cooldown='YES' if exhausted_until is not None and exhausted_until > now else 'NO',
        canonical_status_state=status, canonical_status_observed_at=status_at, reason=reason)


def _read_broker(gateway, account_label, host_ref, model, now):
    """One bounded read-only SELECT of existing leases; the connection is
    always closed here because the sqlite context manager does not close."""
    try:
        connection = gateway._connection()
    except Exception:
        return 'unavailable', None
    try:
        try:
            rows = connection.execute(
                _LEASE_SQL, (POOL, host_ref, QUERY_LIMIT)).fetchall()
        finally:
            connection.close()
    except Exception:
        return 'unavailable', None
    if type(rows) is not list or len(rows) > MAX_ROWS:
        return 'overflow', None
    held_pool = held_account = held_model = held_host = held_route = 0
    legacy_model = expired_retained = 0
    for row in rows:
        if type(row) is not tuple or len(row) != 9:
            return 'invalid', None
        pool, account, lease_model, host, state, granted_at, ttl, \
            last_heartbeat, renewable = row
        if (type(pool) is not str or type(account) is not str
                or type(lease_model) is not str or type(host) is not str
                or state not in ('held', 'rented')
                or type(granted_at) is not int and type(granted_at) is not float
                or type(ttl) is not int and type(ttl) is not float
                or type(last_heartbeat) is not int
                and type(last_heartbeat) is not float
                or renewable not in (0, 1) or type(renewable) is not int):
            return 'invalid', None
        granted = float(granted_at)
        span = float(ttl)
        heartbeat = float(last_heartbeat)
        if (not math.isfinite(granted) or not math.isfinite(span)
                or not math.isfinite(heartbeat) or granted <= 0.0
                or span <= 0.0 or heartbeat < granted
                or granted > now + FUTURE_TOLERANCE_S
                or heartbeat > now + FUTURE_TOLERANCE_S):
            return 'invalid', None
        if pool == POOL:
            held_pool += 1
        if host == host_ref:
            held_host += 1
        if account == account_label and pool == POOL:
            held_account += 1
            if pool == POOL:
                # Incumbent broker law: the full glm-5.3 label also serves the
                # legacy empty-model rows; Flash is the exact model only.
                if lease_model == '':
                    legacy_model += 1
                if lease_model.lower() == model or (model == 'glm-5.3'
                                            and lease_model == ''):
                    held_model += 1
                if lease_model.lower() == model and host == host_ref:
                    held_route += 1
        if heartbeat + span < now or renewable == 0 and granted + span < now:
            expired_retained += 1
    counts = dict(held_pool=held_pool, held_account=held_account,
        held_model=held_model, held_host=held_host, held_route=held_route,
        legacy_model_count=legacy_model, expired_retained_count=expired_retained,
        rows_observed=len(rows))
    return None, counts


def observe_paid_capacity(owner, *, physical, source_config, account_label,
                          quota_class):
    """Project a closed read-only Capacity observation; it grants nothing."""
    observed_at = _now()
    backend = _require_arguments(owner, physical, source_config,
                                 account_label, quota_class)
    backend.require_gateway(owner, owner._gateway)
    gateway = owner._gateway
    accounts = gateway._accounts
    table = owner._context.account_table
    if type(table) is not owner._shim.AccountTable:
        _refuse()
    if type(accounts) is not frozenset:
        _refuse()
    names = table.names()
    if frozenset(names) != accounts:
        _refuse()
    scope = dict(worker_id=physical['worker_id'], provider=PROVIDER,
        host_ref=physical['host_ref'], transport_host=physical['qualification']['registry_key'], model=physical['model'],
        account_label=account_label, quota_class=quota_class, pool=POOL,
        physical_binding_sha256=digest(physical),
        worker_source_config_digest=digest(source_config))
    try:
        state_first = table.state(account_label)
        snapshot_rows = table.snapshot()
        state = table.state(account_label)
    except Exception:
        # A failing retained-cache read never leaks a provider error and
        # never fabricates freshness.
        state_first = snapshot_rows = state = None
    if state_first is None or snapshot_rows is None or state is None:
        account = _empty_account('INCOHERENT_READING')
    else:
        account = _read_account(table, account_label, names, snapshot_rows, state_first, state, observed_at)
    reason = account.pop('reason')
    broker_failure, counts = _read_broker(gateway, account_label,
                                          scope['transport_host'], scope['model'],
                                          observed_at)
    if broker_failure == 'unavailable' or broker_failure == 'invalid':
        broker = dict(freshness='UNKNOWN', **{name: None
                                              for name in _BROKER_COUNTS})
        if reason is None:
            reason = 'BROKER_UNAVAILABLE'
    elif broker_failure == 'overflow':
        broker = dict(freshness='UNKNOWN', **{name: None
                                              for name in _BROKER_COUNTS})
        if reason is None:
            reason = 'BROKER_OVERFLOW'
    else:
        broker = dict(freshness='OBSERVED', **counts)
        if reason is None and counts['expired_retained_count'] > 0:
            reason = 'EXPIRED_RETAINED'
    # A canonical failure or PENDING transition during the DB read invalidates
    # the old pair, even when the first two cache reads agreed.
    try:
        if table.state(account_label) != state or table.names() != names:
            account = _empty_account('INCOHERENT_READING')
            reason = account.pop('reason')
    except Exception:
        account = _empty_account('INCOHERENT_READING')
        reason = account.pop('reason')
    if reason is None:
        reason = 'OBSERVED'
    observation_state = 'OBSERVED' if reason == 'OBSERVED' else 'OFFLINE'
    backend.require_gateway(owner, owner._gateway)
    if (owner._gateway is not gateway or gateway._accounts is not accounts
            or owner._context.account_table is not table):
        _refuse()
    expires_at = observed_at + OBSERVATION_TTL_S
    if observation_state == 'OBSERVED':
        expires_at = min(expires_at, account['observed_at'] + FRESH_LIMIT_S)
    return validate_paid_capacity_observation(dict(
        schema_version=SCHEMA_VERSION, profile_id=PROFILE_ID,
        adapter_id=ADAPTER_ID, observation_state=observation_state,
        reason=reason, observed_at=observed_at,
        expires_at=expires_at, scope=scope,
        account=account, broker=broker, provider_readiness=PROVIDER_READINESS))


def json_detached(value):
    """Closed plain JSON-safe projection; no aliased or custom containers."""
    return json.loads(canonical(value))


def _valid_number(value, low, high):
    return (type(value) is int or type(value) is float) and low <= value <= high


def _valid_epoch(value):
    return _valid_number(value, 0.0, _EPOCH_MAX) and value > 0.0


def _valid_count(value, high):
    if value is None:
        return True
    return type(value) is int and 0 <= value <= high


def _valid_optional_number(value, low, high):
    if value is None:
        return True
    return (type(value) is int or type(value) is float) and low <= value <= high


def _valid_id(value):
    return type(value) is str and bool(_ID.fullmatch(value))


def _valid_digest(value):
    return type(value) is str and bool(_SHA.fullmatch(value))


def validate_paid_capacity_observation(value):
    """Strict detached-DATA validator; validity never confers authority."""
    try:
        _plain_data(value)
        if type(value) is not dict or set(value) != _TOP_FIELDS:
            _refuse()
        if (value['schema_version'] != SCHEMA_VERSION
                or value['profile_id'] != PROFILE_ID
                or value['adapter_id'] != ADAPTER_ID
                or value['provider_readiness'] != PROVIDER_READINESS
                or value['observation_state'] not in _OBSERVATION_STATES
                or value['reason'] not in _REASONS):
            _refuse()
        state, reason = value['observation_state'], value['reason']
        observed_at, expires_at = value['observed_at'], value['expires_at']
        if (not _valid_epoch(observed_at) or not _valid_epoch(expires_at)
                or not 0.0 < expires_at - observed_at
                <= OBSERVATION_TTL_S + 1e-6):
            _refuse()
        if (state == 'OBSERVED') != (reason == 'OBSERVED'):
            _refuse()
        scope = value['scope']
        if type(scope) is not dict or set(scope) != _SCOPE_FIELDS:
            _refuse()
        if (scope['provider'] != PROVIDER or scope['pool'] != POOL
                or scope['model'] not in MODELS
                or not _valid_id(scope['quota_class'])
                or not _valid_id(scope['worker_id'])
                or type(scope['host_ref']) is not str
                or re.fullmatch(r'host-[0-9a-f]{64}', scope['host_ref']) is None
                or not _valid_id(scope['transport_host'])
                or not _valid_id(scope['account_label'])
                or not _valid_digest(scope['physical_binding_sha256'])
                or not _valid_digest(scope['worker_source_config_digest'])
                or any(type(scope[k]) is not str for k in (
                    'provider', 'model', 'quota_class', 'pool'))):
            _refuse()
        account = _validate_account(value['account'], state, reason,
                                    observed_at)
        broker = _validate_broker(value['broker'], state, reason)
        if (state == 'OBSERVED' and (
                account['freshness'] != 'FRESH'
                or account['membership'] != 'PRESENT'
                or account['cooldown'] != 'NO'
                or broker['freshness'] != 'OBSERVED')):
            _refuse()
        if not _reason_consistent(reason,account,broker,observed_at):_refuse()
        if state=='OBSERVED' and expires_at>account['observed_at']+FRESH_LIMIT_S:_refuse()
        return json_detached(dict(value))
    except PaidCapacityRefused:
        raise
    except (TypeError, ValueError, KeyError, OverflowError):
        _refuse()


def _validate_account(account, state, reason, observed_at):
    if type(account) is not dict or set(account) != _ACCOUNT_FIELDS:
        _refuse()
    if (account['membership'] not in _MEMBERSHIP or account['freshness'] not in _FRESHNESS
            or account['cooldown'] not in _COOLDOWN
            or account['canonical_status_state'] not in _CANONICAL_STATES):
        _refuse()
    if account['membership'] == 'UNKNOWN':
        if (account['freshness'] != 'UNKNOWN' or account['cooldown'] != 'UNKNOWN'
                or any(account[k] is not None for k in ('observed_at','age_seconds','pct_5h',
                    'pct_week','exhausted_until','next_reset_5h','canonical_status_observed_at'))
                or account['canonical_status_state'] != 'UNKNOWN' or state != 'OFFLINE'):
            _refuse()
        return account
    for name in ('pct_5h','pct_week'):
        if not _valid_optional_number(account[name],0,100):_refuse()
    for name in ('observed_at','canonical_status_observed_at','exhausted_until','next_reset_5h','age_seconds'):
        if not _valid_optional_number(account[name],0,_EPOCH_MAX):_refuse()
    if (account['freshness'] == 'UNKNOWN') != (account['observed_at'] is None):_refuse()
    if account['observed_at'] is not None:
        if not _valid_epoch(account['observed_at']) or account['age_seconds'] is None:_refuse()
        age=max(0,observed_at-account['observed_at'])
        if abs(age-account['age_seconds'])>1e-6:_refuse()
        if (account['freshness']=='FRESH') != (age<FRESH_LIMIT_S):_refuse()
    elif account['age_seconds'] is not None:_refuse()
    exhausted=account['exhausted_until']
    if account['cooldown']=='YES' and (exhausted is None or exhausted<=observed_at):_refuse()
    if account['cooldown']=='NO' and exhausted is not None and exhausted>observed_at:_refuse()
    if account['cooldown']=='UNKNOWN' and exhausted is not None:_refuse()
    if state=='OBSERVED' and (account['freshness']!='FRESH' or account['cooldown']!='NO'
            or account['canonical_status_state']!='OBSERVED'
            or account['canonical_status_observed_at']!=account['observed_at']
            or account['observed_at']>observed_at+FUTURE_TOLERANCE_S
            or any(account[k] is None or account[k]>=100 for k in ('pct_5h','pct_week'))):_refuse()
    return account


def _validate_broker(broker, state, reason):
    if type(broker) is not dict or set(broker)!=_BROKER_FIELDS:_refuse()
    if broker['freshness'] not in _BROKER_FRESHNESS:_refuse()
    if any(not _valid_count(broker[k],MAX_ROWS) for k in _BROKER_COUNTS):_refuse()
    if broker['freshness']=='UNKNOWN':
        if any(broker[k] is not None for k in _BROKER_COUNTS) or state=='OBSERVED':_refuse()
    else:
        if any(broker[k] is None for k in _BROKER_COUNTS):_refuse()
        if any(broker[k]>broker['rows_observed'] for k in _BROKER_COUNTS):_refuse()
        if (broker['held_account']>broker['held_pool'] or broker['held_model']>broker['held_account']
                or broker['held_route']>min(broker['held_model'],broker['held_host'])
                or broker['legacy_model_count']>broker['held_account']):_refuse()
        if state=='OBSERVED' and broker['expired_retained_count']:_refuse()
    return broker


def _reason_consistent(reason, account, broker, observed_at):
    conditions={
        'OBSERVED':True,
        'ACCOUNT_UNKNOWN':account['membership']=='UNKNOWN',
        'INVALID_READING':account['freshness']=='UNKNOWN' or any(account[k] is None for k in ('pct_5h','pct_week')),
        'INCOHERENT_READING':account['freshness']=='UNKNOWN',
        'CONTRADICTORY_TIME':account['observed_at'] is not None and account['observed_at']>observed_at+FUTURE_TOLERANCE_S,
        'STATUS_NOT_OBSERVED':account['canonical_status_state']!='OBSERVED' or account['canonical_status_observed_at'] is None or account['canonical_status_observed_at']!=account['observed_at'],
        'ACTIVE_COOLDOWN':account['cooldown']=='YES',
        'FULL_UTILIZATION':any(account[k]==100 for k in ('pct_5h','pct_week')),
        'STALE_READING':account['freshness']=='STALE',
        'BROKER_UNAVAILABLE':broker['freshness']=='UNKNOWN',
        'BROKER_OVERFLOW':broker['freshness']=='UNKNOWN',
        'EXPIRED_RETAINED':broker['freshness']=='OBSERVED' and broker['expired_retained_count']>0,
    }
    return conditions.get(reason,False)
