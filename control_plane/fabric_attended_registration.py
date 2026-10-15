"""Fixed finite identity registration through the existing Control command.

New rows are OFFLINE. Source identity is not Capacity readiness, enrollment or
authority to run; only the existing capacity owner can later qualify availability.
"""
from __future__ import annotations

from control_plane.executive_capacity_join import CapacityJoin, PROVIDER_CAPACITY_SCHEMA
from control_plane.executive_runtime import StateConflict, WorkerStatus
from control_plane.fabric_attended_routing import placement_member
from control_plane.model_router import ModelRouter


def register_fixed_finite(runtime, placement, binding_source, probe_source, guard):
    if (placement.qualification is None or placement.model_alias != 'minimax.attended'
            or placement.quota_class != 'minimax-finite-read'
            or len(binding_source.bindings) != 1 or not callable(guard)):
        raise StateConflict('fixed finite registration requires its original owner')
    guard()
    physical, = binding_source.bindings
    if (physical.worker_id != 'minimax-finite-01' or physical.provider != 'minimax'
            or binding_source(physical.host_ref, physical.worker_id) != physical):
        raise StateConflict('finite registration physical owner differs')
    _, definition, _ = probe_source.configuration(physical)
    if (definition.get('worker_id') != physical.worker_id
            or definition.get('worker_uid') != physical.worker_uid
            or definition.get('worker_gid') != physical.worker_gid):
        raise StateConflict('finite registration definition differs')
    join = CapacityJoin(physical.host_ref, definition.get('capacity_capability_id'),
        PROVIDER_CAPACITY_SCHEMA, physical.worker_source_config_digest)
    route = placement_member(ModelRouter.load(), placement)['attended_route']
    if route['provider_alias'] != physical.provider or route['model'].lower() != physical.model.lower():
        raise StateConflict('finite registration model differs')
    quota_metadata = dict(route, attended_route=route, capacity_join=join.to_dict())
    worker_metadata = dict(service_managed=True, worker_source_config_digest=physical.worker_source_config_digest)
    if definition.get('worker_user') != '_mastermind_minimax':
        raise StateConflict('finite account must use its actual isolated principal')
    # Runtime labels begin with an alphanumeric character. This fixed label
    # names the checked OS principal; it neither identifies a vendor account
    # nor authenticates the credential installed for that principal.
    label = 'mastermind-minimax'
    existing = runtime.workers.get_worker(physical.worker_id)
    if existing is not None:
        quota = runtime.workers.get_quota_class(physical.worker_id, placement.quota_class)
        if (existing.provider != physical.provider or existing.account_label != label
                or existing.worker_type != 'attended-fabric' or existing.capabilities != ['research']
                or existing.metadata != worker_metadata or quota is None
                or quota.provider != physical.provider or quota.model != route['model'].lower()
                or quota.effort != route['effort'] or quota.cost_class != route['cost_class']
                or quota.capabilities != ['research'] or quota.metadata != quota_metadata
                or existing.status not in {WorkerStatus.OFFLINE, WorkerStatus.AVAILABLE}
                or quota.status not in {WorkerStatus.OFFLINE, WorkerStatus.AVAILABLE}
                or existing.active_job_id is not None or quota.active_attempt_id is not None):
            raise StateConflict('existing finite identity, capacity or held state differs')
    # Re-read original host/config/catalogue before the canonical write. An
    # unknown post-write response leaves an OFFLINE row; no cleanup or promotion.
    guard()
    if (binding_source(physical.host_ref, physical.worker_id) != physical
            or probe_source.configuration(physical)[1] != definition
            or placement_member(ModelRouter.load(), placement)['attended_route'] != route):
        raise StateConflict('finite registration source changed')
    guard()
    if existing is not None:
        return existing
    return runtime.workers.register_worker(physical.worker_id, provider=physical.provider,
        account_label=label, worker_type='attended-fabric', capabilities=['research'],
        status=WorkerStatus.OFFLINE, metadata=worker_metadata,
        quota_classes={placement.quota_class: dict(provider=physical.provider,
            model=route['model'], effort=route['effort'], cost_class=route['cost_class'],
            capabilities=['research'], metadata=quota_metadata)})
