"""Current paid source/status composition in the existing Control owner.

Registration starts OFFLINE. Status bootstrap is an explicit action retained
in existing Runtime Events before the paid owner can perform one quota GET.
Neither passive observation nor startup retries it. Actual inference still
requires Runtime admission, current R1/autonomy and the original broker lease.
"""
from __future__ import annotations

import json
import dataclasses
import secrets
import time
from control_plane.executive_runtime import StateConflict, WorkerStatus
from control_plane.executive_capacity_join import CapacityJoin, PROVIDER_CAPACITY_SCHEMA
from control_plane.executive_paid_fabric_composition import PaidBindingSource, PaidWorkPlacement, placement_member
from control_plane.model_router import ModelRouter
from control_plane.paid_model_execution_contract import digest


def _refuse():
    raise StateConflict('paid current source/status admission unavailable')


def _reserve_status(runtime, worker_id, quota_class, scope):
    """One actual Runtime transaction retains the operation before transport."""
    with runtime.store.transaction() as connection:
        row=connection.execute(
            "SELECT event_type,payload_json FROM events WHERE worker_id=? AND quota_class=? "
            "AND event_type IN ('PAID_QUOTA_STATUS_REQUESTED','PAID_QUOTA_STATUS_RETURNED') "
            "ORDER BY event_id DESC LIMIT 1",(worker_id,quota_class)).fetchone()
        if row is not None:
            previous=json.loads(row['payload_json'])
            if previous.get('scope')!=scope:_refuse()
            if (row['event_type']!='PAID_QUOTA_STATUS_RETURNED'
                    or previous.get('state')!='OBSERVED'):
                # Only read the original owner outcome. An absent/lost issuer
                # receipt never turns this same operation back into a new GET.
                return previous['operation_id'], 'reconcile'
        operation_id='paid-status-'+secrets.token_hex(16)
        runtime.store.append_event(connection,aggregate_type='worker',aggregate_id=worker_id,
            event_type='PAID_QUOTA_STATUS_REQUESTED',worker_id=worker_id,quota_class=quota_class,
            actor='control-paid-status-owner',payload=dict(operation_id=operation_id,scope=scope))
        return operation_id, 'bootstrap'


def _retain_status(runtime,worker_id,quota_class,scope,operation_id,result):
    with runtime.store.transaction() as connection:
        row=connection.execute(
            "SELECT event_type,payload_json FROM events WHERE worker_id=? AND quota_class=? "
            "AND event_type IN ('PAID_QUOTA_STATUS_REQUESTED','PAID_QUOTA_STATUS_RETURNED') "
            "ORDER BY event_id DESC LIMIT 1",(worker_id,quota_class)).fetchone()
        if row is not None and row['event_type']=='PAID_QUOTA_STATUS_RETURNED':
            previous=json.loads(row['payload_json'])
            if previous!=dict(operation_id=operation_id,scope=scope,state=result['state'],result=result):_refuse()
            return
        if (row is None or row['event_type']!='PAID_QUOTA_STATUS_REQUESTED'
                or json.loads(row['payload_json'])!=dict(operation_id=operation_id,scope=scope)):_refuse()
        runtime.store.append_event(connection,aggregate_type='worker',aggregate_id=worker_id,
            event_type='PAID_QUOTA_STATUS_RETURNED',worker_id=worker_id,quota_class=quota_class,
            actor='control-paid-status-owner',payload=dict(operation_id=operation_id,scope=scope,
                state=result['state'],result=result))


async def paid_capacity_action(runtime, source, *, mode, availability_guard):
    """Only the installed Control constructor supplies the root-read source."""
    if type(source) is not PaidBindingSource or mode not in {'observe','bootstrap'}:_refuse()
    from control_plane.paid_fabric_capacity import validate_paid_capacity_observation
    returned=[]
    for physical in source.bindings:
        current=source.source_for(physical)
        quota=source.quota_for(physical)
        route=placement_member(ModelRouter.load(),PaidWorkPlacement('glm.paid.sealed-input',quota))['paid_execution_route']
        if route['provider_alias']!=physical.provider or route['model']!=physical.model:_refuse()
        scope=dict(physical_binding_sha256=digest(dataclasses.asdict(physical)),worker_source_config_digest=digest(current))
        nonce=secrets.token_hex(16)
        client=source.client_for(physical,{})
        payload=dict(nonce=nonce,worker_id=physical.worker_id,quota_class=quota,mode='observe')
        # Passive source/account observation is necessary to register the exact
        # identity OFFLINE; it never falls through to provider metadata IO.
        observed=await client.request('native-capacity-observation',payload)
        _validate_response(observed,payload,scope,validate_paid_capacity_observation,physical,current)
        account=observed['account_label']
        metadata=dict(route,paid_execution_route=route,
            capacity_join=CapacityJoin(physical.host_ref,current['capacity_capability_id'],
                PROVIDER_CAPACITY_SCHEMA,physical.worker_source_config_digest).to_dict())
        worker_meta=dict(service_managed=True,worker_source_config_digest=physical.worker_source_config_digest)
        existing=runtime.workers.get_worker(physical.worker_id)
        if existing is None:
            runtime.workers.register_worker(physical.worker_id,provider='glm',account_label=account,
                worker_type='canonical-paid-fabric',capabilities=['read','research'],status=WorkerStatus.OFFLINE,
                metadata=worker_meta,quota_classes={quota:dict(provider='glm',model=route['model'],
                    effort=route['effort'],cost_class=route['cost_class'],capabilities=['read','research'],metadata=metadata)})
        _require_registration(runtime,physical,quota,account,route,metadata,worker_meta)
        if (mode=='bootstrap' and not (observed['observation']['observation_state']=='OBSERVED'
                and observed['observation']['observed_at']<=time.time()<observed['observation']['expires_at'])):
            operation_id,owner_mode=_reserve_status(runtime,physical.worker_id,quota,scope)
            payload=dict(payload,mode=owner_mode,operation_id=operation_id,nonce=secrets.token_hex(16))
            observed=await client.request('native-capacity-observation',payload)
            _validate_response(observed,payload,scope,validate_paid_capacity_observation,physical,current)
            if observed['account_label']!=account:_refuse()
            _retain_status(runtime,physical.worker_id,quota,scope,operation_id,observed['bootstrap'])
        if source.source_for(physical)!=current:_refuse()
        _require_registration(runtime,physical,quota,account,route,metadata,worker_meta)
        # A status observation alone never mints availability. Existing actual
        # admission predicates and the R1/autonomy owner must also accept it.
        ready=False
        observation=observed['observation']
        if observation['observation_state']=='OBSERVED':
            ready=bool(availability_guard(observation))
        row=runtime.workers.get_quota_class(physical.worker_id,quota)
        if row.active_attempt_id is not None:_refuse()
        runtime.workers.set_worker_status(physical.worker_id,
            WorkerStatus.AVAILABLE if ready else WorkerStatus.OFFLINE,quota_class=quota)
        returned.append(dict(worker_id=physical.worker_id,quota_class=quota,
            state='AVAILABLE' if ready else 'OFFLINE',observation=observation,
            bootstrap=observed['bootstrap']))
    return returned


def _validate_response(value,payload,scope,validator,physical,source):
    if (type(value) is not dict or set(value)!={'observation','bootstrap','physical_binding_sha256',
            'worker_source_config_digest','worker_id','quota_class','account_label','nonce'}
            or any(value.get(k)!=payload[k] for k in ('nonce','worker_id','quota_class'))
            or any(value.get(k)!=v for k,v in scope.items())):_refuse()
    observation=validator(value['observation'])
    expected=dict(scope,worker_id=physical.worker_id,quota_class=payload['quota_class'],
        account_label=value['account_label'],provider=physical.provider,model=physical.model,
        host_ref=physical.host_ref,transport_host=source['qualification']['registry_key'],pool='glm')
    if observation['scope']!=expected:_refuse()
    if payload['mode']=='observe' and value['bootstrap'] is not None:_refuse()
    if payload['mode'] in {'bootstrap','reconcile'}:
        from control_plane.paid_fabric_bootstrap import validate_bootstrap_result
        validate_bootstrap_result(value['bootstrap'])
    account=value['account_label']
    import re
    if type(account) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}',account) is None:_refuse()


def _require_registration(runtime,physical,quota,account,route,metadata,worker_meta):
    worker=runtime.workers.get_worker(physical.worker_id)
    row=runtime.workers.get_quota_class(physical.worker_id,quota)
    if (worker is None or worker.provider!='glm' or worker.account_label!=account
            or worker.worker_type!='canonical-paid-fabric' or worker.capabilities!=['read','research']
            or worker.metadata!=worker_meta or row is None or row.provider!='glm'
            or row.model!=route['model'] or row.effort!=route['effort']
            or row.cost_class!=route['cost_class'] or row.capabilities!=['read','research']
            or row.metadata!=metadata):_refuse()
