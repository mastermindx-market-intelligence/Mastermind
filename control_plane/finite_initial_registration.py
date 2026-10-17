"""Prospective V2 registration only; existing V1 identities are immutable."""
from control_plane.finite_initial_admission import CLASSIFICATION, WORKER, QUOTA
from control_plane.native_capacity_acquisition import NativeCapacitySource
from control_plane.native_capacity_v2 import JOIN_SCHEMA, SCHEMA, validate_join
from control_plane.fabric_attended_routing import placement_member
from control_plane.model_router import ModelRouter
from control_plane.executive_runtime import StateConflict, WorkerStatus


def register_initial(runtime, placement, source, guard):
    from ops.executive_os.capacity_source_contract import acquire_control_native_registration
    if (type(source) is not NativeCapacitySource or not callable(guard)
            or placement.qualification is None or placement.model_alias!='minimax.attended'
            or placement.quota_class!=QUOTA):
        raise StateConflict('finite V2 registration requires original typed owners')
    guard()
    physical=source._physical()
    raw, definition, attestation=source.probe.configuration(physical)
    registration=acquire_control_native_registration(source.probe,physical)
    if registration['source_release_commit']!=source.release:
        raise StateConflict('finite V2 registration source release differs')
    join=validate_join({'schema':JOIN_SCHEMA,'provider_capacity_schema':SCHEMA,
        'host_ref':physical.host_ref,'capacity_capability_id':registration['capacity_capability_id'],
        'capability_generation':registration['capability_generation'],
        'worker_source_config_digest':physical.worker_source_config_digest})
    if (physical.worker_id!=WORKER or definition.get('worker_user')!='_mastermind_minimax'
            or definition.get('worker_uid')!=physical.worker_uid
            or definition.get('worker_gid')!=physical.worker_gid):
        raise StateConflict('finite V2 registration physical principal differs')
    route=placement_member(ModelRouter.load(),placement)['attended_route']
    if route['provider_alias']!=physical.provider or route['model'].lower()!=physical.model.lower():
        raise StateConflict('finite V2 registration route differs')
    metadata=dict(route,attended_route=route,capacity_join=join,finite_initial_capacity=CLASSIFICATION)
    # Never accept/migrate an existing V1, uncertain, previously used or even
    # equal-looking row. Same-operation registration recovery remains its owner.
    if runtime.workers.get_worker(WORKER) is not None:
        raise StateConflict('finite V2 registration requires genuinely absent identity')
    guard()
    if (source._physical()!=physical or source.probe.configuration(physical)!=(raw,definition,attestation)
            or acquire_control_native_registration(source.probe,physical)!=registration
            or placement_member(ModelRouter.load(),placement)['attended_route']!=route):
        raise StateConflict('finite V2 registration source changed')
    guard()
    return runtime.workers.register_worker(WORKER,provider='minimax',account_label='mastermind-minimax',
        worker_type='attended-fabric',status=WorkerStatus.OFFLINE,capabilities=['research'],
        metadata={'service_managed':True,'worker_source_config_digest':physical.worker_source_config_digest},
        quota_classes={QUOTA:dict(provider='minimax',model=route['model'],effort=route['effort'],
            cost_class=route['cost_class'],capabilities=['research'],metadata=metadata)})
