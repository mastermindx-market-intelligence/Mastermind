"""Strict additive V2 reader and conservative finite decision, never acquisition."""
from __future__ import annotations
import copy
import hashlib
import json
import re
from datetime import datetime

SCHEMA = 'mastermind.provider_capacity.v2'
JOIN_SCHEMA = 'mastermind.executive_capacity_join/v2'
HEX = re.compile(r'[0-9a-f]{64}')
TOKEN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}')
TOP = {'schema','generated_at_ms','source','producer_sha256','slots','snapshot_hash'}
SOURCE = {'source_release_commit','previous_release_commit','material_source_digest',
          'source_receipt_digest','registration_receipt_digest'}
ROW = {'host_ref','boot_ref','capacity_capability_id','capability_generation',
       'realm_generation','enrollment_receipt_digest','provider','provider_enabled',
       'worker_source_config_digest','observed_at','realm_auth','provider_health',
       'cooling','quota_horizons','last_provider_outcome'}

class NativeCapacityRefusal(ValueError):
    pass

def refuse(code):
    raise NativeCapacityRefusal(code)

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def closed(value, keys):
    if type(value) is not dict or set(value) != keys:
        refuse('V2_FIELDS_INVALID')
    return value

def integer(value, minimum=1):
    if type(value) is not int or not minimum <= value < 2**63:
        refuse('V2_INTEGER_INVALID')
    return value

def reference(value, prefix=''):
    if type(value) is not str or not value.startswith(prefix) or HEX.fullmatch(value[len(prefix):]) is None:
        refuse('V2_REFERENCE_INVALID')

def timestamp(value):
    if type(value) is not str or re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z',value) is None:
        refuse('V2_TIME_INVALID')
    try:
        return int(datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()*1000)
    except ValueError:
        refuse('V2_TIME_INVALID')

def fresh(observed, now_ms, lifetime=15000):
    if not now_ms-lifetime-2000 <= observed <= now_ms+2000:
        refuse('V2_OBSERVATION_STALE')

def validate_join(value):
    closed(value, {'schema','host_ref','capacity_capability_id','provider_capacity_schema',
                  'worker_source_config_digest','capability_generation'})
    if value['schema'] != JOIN_SCHEMA or value['provider_capacity_schema'] != SCHEMA:
        refuse('V2_JOIN_SCHEMA_INVALID')
    reference(value['host_ref'],'host-')
    reference(value['worker_source_config_digest'])
    integer(value['capability_generation'])
    if type(value['capacity_capability_id']) is not str or TOKEN.fullmatch(value['capacity_capability_id']) is None:
        refuse('V2_CAPABILITY_INVALID')
    return copy.deepcopy(value)

def validate_snapshot(value, *, now_ms):
    integer(now_ms)
    closed(value,TOP)
    try:
        wire = canonical(value)
    except (ValueError,TypeError,RecursionError):
        refuse('V2_ENCODING_INVALID')
    if len(wire.encode()) > 32768:
        refuse('V2_TOO_LARGE')
    value = json.loads(wire)
    if value['schema'] != SCHEMA:
        refuse('V2_SCHEMA_INVALID')
    fresh(integer(value['generated_at_ms']),now_ms,30000)
    reference(value['producer_sha256'])
    reference(value['snapshot_hash'])
    if digest({k:v for k,v in value.items() if k!='snapshot_hash'}) != value['snapshot_hash']:
        refuse('V2_HASH_MISMATCH')
    src = closed(value['source'],SOURCE)
    for key in SOURCE:
        pattern = r'[0-9a-f]{40}' if key.endswith('commit') else r'[0-9a-f]{64}'
        if type(src[key]) is not str or re.fullmatch(pattern,src[key]) is None:
            refuse('V2_SOURCE_INVALID')
    if type(value['slots']) is not list or not 1<=len(value['slots'])<=3:
        refuse('V2_SLOT_COUNT_INVALID')
    identities=set()
    for row in value['slots']:
        closed(row,ROW)
        validate_join({'schema':JOIN_SCHEMA,'provider_capacity_schema':SCHEMA,
            **{k:row[k] for k in ('host_ref','capacity_capability_id','capability_generation','worker_source_config_digest')}})
        reference(row['boot_ref'],'boot-')
        reference(row['enrollment_receipt_digest'])
        integer(row['realm_generation'])
        fresh(timestamp(row['observed_at']),now_ms)
        identity=(row['host_ref'],row['capacity_capability_id'])
        if identity in identities: refuse('V2_DUPLICATE_IDENTITY')
        identities.add(identity)
        if row['provider']!='minimax' or (row['provider_enabled'] is not None and type(row['provider_enabled']) is not bool):
            refuse('V2_PROVIDER_INVALID')
        auth=closed(row['realm_auth'],{'state','method','source_quality'})
        if (auth['state'] not in {'unknown','authenticated','unauthenticated'}
                or auth['method'] not in {'unknown','subscription_api_key'}
                or auth['source_quality'] not in {'unknown','native_provider'}):
            refuse('V2_AUTH_INVALID')
        health=closed(row['provider_health'],{'state','error_class','scope','observed_at'})
        cooling=closed(row['cooling'],{'active','kind','reset_at','evidence','scope','observed_at'})
        outcome=closed(row['last_provider_outcome'],{'class','scope','observed_at'})
        for fact in (health,cooling,outcome):
            if fact['scope'] not in {'unknown','host_local','capability_generation'}:
                refuse('V2_SCOPE_INVALID')
            if fact['observed_at'] is not None: fresh(timestamp(fact['observed_at']),now_ms)
        if health['state'] not in {'unknown','healthy','unhealthy'} or health['error_class'] not in {None,'auth','quota','transport','provider'}:
            refuse('V2_HEALTH_INVALID')
        if (cooling['active'] is not None and type(cooling['active']) is not bool
                or cooling['kind'] not in {None,'rate_limit','provider','account'}
                or cooling['evidence'] not in {'unknown','native_provider'}):
            refuse('V2_COOLING_INVALID')
        if cooling['reset_at'] is not None: timestamp(cooling['reset_at'])
        if outcome['class'] not in {'unknown','success','auth_failure','quota','transport','provider'}:
            refuse('V2_OUTCOME_INVALID')
        horizons=row['quota_horizons']
        if type(horizons) is not list or len(horizons)>8: refuse('V2_QUOTA_INVALID')
        seen=set()
        for horizon in horizons:
            closed(horizon,{'name','remaining','limit','reset_at','scope','observed_at'})
            if (type(horizon['name']) is not str or TOKEN.fullmatch(horizon['name']) is None
                    or horizon['name'] in seen or horizon['scope']!='capability_generation'):
                refuse('V2_QUOTA_INVALID')
            seen.add(horizon['name'])
            if integer(horizon['remaining'],0)>integer(horizon['limit']): refuse('V2_QUOTA_INVALID')
            if timestamp(horizon['reset_at'])<=now_ms: refuse('V2_QUOTA_EXPIRED')
            fresh(timestamp(horizon['observed_at']),now_ms)
    return value

def known_admissible(value, join, *, now_ms):
    """Pure decision only. Authentication must come from NativeCapacitySource."""
    value=validate_snapshot(value,now_ms=now_ms)
    join=validate_join(join)
    rows=[r for r in value['slots'] if all(r[k]==join[k] for k in (
        'host_ref','capacity_capability_id','capability_generation','worker_source_config_digest'))]
    if len(rows)!=1: refuse('V2_IDENTITY_JOIN_REFUSED')
    row=rows[0]
    if row['provider_enabled'] is not True: refuse('V2_PROVIDER_ENABLEMENT_UNQUALIFIED')
    if row['realm_auth']!={'state':'authenticated','method':'subscription_api_key','source_quality':'native_provider'}:
        refuse('V2_AUTH_UNQUALIFIED')
    health,cooling=row['provider_health'],row['cooling']
    if health['state']!='healthy' or health['error_class'] is not None or health['scope']!='capability_generation' or health['observed_at'] is None:
        refuse('V2_HEALTH_UNQUALIFIED')
    if (cooling['active'] is not False or cooling['evidence']!='native_provider'
            or cooling['scope']!='capability_generation' or cooling['observed_at'] is None
            or cooling['kind'] is not None or cooling['reset_at'] is not None):
        refuse('V2_COOLING_UNQUALIFIED')
    outcome=row['last_provider_outcome']
    if outcome['class'] not in {'success','unknown'}:
        refuse('V2_PROVIDER_OUTCOME_CONFLICT')
    if not row['quota_horizons'] or any(q['remaining']<1 for q in row['quota_horizons']):
        refuse('V2_QUOTA_UNQUALIFIED')
    return copy.deepcopy(row)
