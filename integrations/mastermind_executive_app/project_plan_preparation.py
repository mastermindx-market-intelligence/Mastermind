"""Private SAME-S19 result-to-source preparation; no public proposal authority.

Only the original live ForegroundOperation's independently verified Executive
and Workspace resources can enter. Explicit result consumption precedes this
pure capture and the existing private source preparation. No planner is
created, result consumed, source published or plan adopted by this helper.
"""
from __future__ import annotations

import dataclasses

from integrations.business_mcp_auth.contracts import VerifiedPrincipal


def prepare_project_plan_proposal_for_original(factory,frame,operation,principal):
    from integrations.mastermind_executive_app.project_planning_factory import ProjectPlanningAppFactory
    from control_plane.foreground_operation import current_foreground_operation
    from integrations.mastermind_workspace_app.source_operation_principal import source_principal_scope
    from control_plane.workspace_source_operation_binding import (
        _current_source_operation,prepare_project_plan_proposal,
    )
    from control_plane.project_plan_canonical_basis import capture_current_plan_basis
    from control_plane.project_plan_result_source import _capture_consumed_planning_result

    if (type(factory) is not ProjectPlanningAppFactory
            or current_foreground_operation() is not operation
            or frame.get('operation')!='prepare_proposal'
            or operation._project_planning_operation!='prepare_proposal'):
        raise PermissionError('original planning preparation unavailable')
    args=frame['arguments']
    operation.require_arguments(args)

    def host_current():
        operation._require_live()
        factory._current(principal,operation,args['operation_key'],args['work_ref'])
        return True

    host_current()
    original,access,source,executive=factory.qualified_original_source(principal=principal,
        operation_key=args['operation_key'],work_ref=args['work_ref'])
    request=args['proposal_request']
    if (request['work_ref']!=args['work_ref'] or request['selection']['work_ref']!=args['work_ref']
            or request['selection']['job_id']!=original['job_id']):
        raise ValueError('proposal differs from original planning result')
    runtime=factory.service._require_runtime()
    mounted=factory.service._require_supervisor()
    workspace=VerifiedPrincipal(**dataclasses.asdict(operation._project_workspace_principal))
    if source.material()['publication']['principal_scope']!=source_principal_scope(workspace):
        raise PermissionError('proposal Workspace principal differs')
    provider=factory.app_binding.source_operation_provider_factory
    if not callable(provider):raise ValueError('proposal source owner unavailable')
    binding=provider(runtime,mounted)
    current=_current_source_operation(binding,runtime=runtime,supervisor=mounted,host_guard=host_current)
    data=binding.owner._canonical_data_source
    if data is None:raise ValueError('canonical plan basis unavailable')
    # The host-issued scope preserves one actual issued DATA view across
    # this pure result/basis capture. Its full current guards bracket the
    # block; no private input, Event or publication is written inside it.
    from control_plane.runtime_namespace_custody import ServiceRuntimeNamespaceCustody
    custody=factory.service._namespace_custody
    if type(custody) is not ServiceRuntimeNamespaceCustody:
        raise ValueError('original Runtime result custody unavailable')
    # ONE actual current response qualifies both terminal bytes and the prior
    # explicit Keep. Full source postchecks finish before this sealed result
    # returns; every later service effect boundary still observes freshly.
    result=_capture_consumed_planning_result(runtime,result_reader=custody.bound_runtime(runtime),
        selection=request['selection'],source=source,executive_admission=executive)
    if result.material()['result_digest']!=request['result_digest']:
        raise ValueError('proposal result differs')
    with factory.canonical_read_scope(principal=principal,operation_key=args['operation_key'],
            work_ref=args['work_ref']):
        current();host_current()
    view=None
    try:
        with factory.canonical_read_scope(principal=principal,operation_key=args['operation_key'],
                work_ref=args['work_ref']) as view:
            basis=capture_current_plan_basis(view,work_ref=args['work_ref'])
            current();host_current()
        # The distinct private sink rechecks the actual basis and result. Its
        # own pure blocks close before each private/Event mutation.
        factory._require_effect_outside_read(operation)
        receipt=prepare_project_plan_proposal(binding,request,runtime=runtime,supervisor=mounted,
            host_guard=host_current,principal=workspace,basis=basis,result=result)
        current();host_current()
        return receipt
    finally:
        if view is not None:data.collector._discard_canonical_code_capture(view)
