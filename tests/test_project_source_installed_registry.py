"""Actual installed registry/private dispatch, disposable existing owners.

Reuses real CREATE/ADOPT fixtures and all existing validators. Principal,
physical child/Root seal/Git identity and PR observations retain their named
inert premises. This is not signed HTTP, live grant or installed host proof.
"""
import copy

import pytest
from tests.test_project_journey_canonical_create import joined, owner, env, isolated_git_env, identity
from tests.test_installed_plan_adoption import installed as adoption_installed
from tests.test_project_plan_adoption_source_owner import joined as adoption_joined
from tests.test_agentos_plan_continuity_capture import repository as adoption_repository
from control_plane.workspace_source_operation_binding import invoke_source_operation
from control_plane.workspace_source_operations import SourceOperationConflict
from common.workspace_source_operation_wire import FRAME_SCHEMA
from integrations.mastermind_workspace_app.contract import principal_frame
from integrations.mastermind_workspace_app.source_operations import WorkspaceSourceOperationService
from integrations.mastermind_workspace_app.project_plan_adoption_service import ProjectPlanAdoptionSourceOwner
from integrations.mastermind_workspace_app.installed_plan_adoption import InstalledPlanAdoptionRecipeAdapter


def test_actual_factory_registers_four_owners_and_read_does_not_acquire_data(joined, monkeypatch):
    j = joined; runtime = j['runtime']; supervisor = j['factory'].service.supervisor
    binding = j['installed'](runtime, supervisor); service = binding.owner
    assert service._create is not None and service._knowledge is not None and service._proposal is not None
    assert type(service._adoption) is ProjectPlanAdoptionSourceOwner
    assert type(service._adoption._adapter) is InstalledPlanAdoptionRecipeAdapter
    assert all(x._events.store is runtime.store for x in
        (service._create,service._knowledge,service._proposal,service._adoption))
    lookup = dict(schema='mastermind.workspace_source_operation_lookup.v1',
        action='ADOPT_PLAN', request_id='mmos-project-adopt-'+'a'*40,work_ref=j['args']['work_ref'])
    frame = dict(schema=FRAME_SCHEMA,operation='read',principal=principal_frame(j['workspace']),
        verified_expires_at=j['workspace'].expires_at,request=lookup)
    def call(value=frame):
        return invoke_source_operation(binding,value,runtime=runtime,supervisor=supervisor,host_guard=lambda:True)
    before = len(runtime.store.list_events())
    with pytest.raises(PermissionError): call()  # CREATE/READ never grants ADOPT.
    slot = j['document']['profiles'][j['document']['primary_profile']]
    slot['plan_adoption'] = dict(work_ref=lookup['work_ref'],permission_digest='f'*64)
    def no_capture(*a,**kw): raise AssertionError('status must not acquire current DATA')
    monkeypatch.setattr(service._canonical_data_source,'view',no_capture)
    status = call()
    assert status['reason'] == 'ORIGINAL_OPERATION_NOT_OBSERVED' and status['receipt'] is None
    foreign = copy.deepcopy(frame);foreign['request']['work_ref']='WS:FOREIGN'
    with pytest.raises(PermissionError): call(foreign)
    advance = copy.deepcopy(frame);advance['operation']='advance'
    advance['request'] = dict(schema='mastermind.workspace_source_operation_advance.v1',
        **{k:lookup[k] for k in ('action','request_id','work_ref')},phase_receipt_digest='a'*64)
    with pytest.raises(SourceOperationConflict): call(advance)  # Actual owner, not generic unavailable.
    original_actor = service._adoption._actor
    service._adoption._actor = lambda *unused: {}
    with pytest.raises(PermissionError): call()  # Original opaque binding includes this owner.
    service._adoption._actor = original_actor
    assert call() == status
    slot['plan_adoption'] = None
    with pytest.raises(PermissionError): call()
    assert len(runtime.store.list_events()) == before


@pytest.fixture
def actual_adoption_installed(tmp_path, monkeypatch, request):
    # Explicitly reuse the ORIGINAL actual fixture functions under distinct
    # names; its `joined` fixture is not the CREATE fixture above.
    repository = adoption_repository.__wrapped__(tmp_path)
    actual = adoption_joined.__wrapped__(repository,tmp_path,request)
    return adoption_installed.__wrapped__(actual,tmp_path,monkeypatch)


def test_actual_adoption_private_dispatch_preserves_both_phases(actual_adoption_installed):
    j = actual_adoption_installed; f = j.f
    service = WorkspaceSourceOperationService(adoption_owner=j.source,canonical_data_source=j.data,
        runtime_guard=lambda:True)
    binding = service.installed_binding(); runtime = f.events.store
    supervisor = f.private.supervisor; actual_runtime = supervisor.runtime
    assert actual_runtime.store is runtime
    def call(operation, request):
        frame = dict(schema=FRAME_SCHEMA,operation=operation,principal=principal_frame(f.who),
            verified_expires_at=f.who.expires_at,request=request)
        return invoke_source_operation(binding,frame,runtime=actual_runtime,
            supervisor=supervisor,host_guard=lambda:True)
    preview = call('prepare',dict(action='ADOPT_PLAN',request=j.request))
    assert preview['preview']['record_body_changed'] is False
    pending = call('submit',dict(action='ADOPT_PLAN',request_id=f.lookup['request_id'],
        work_ref=f.lookup['work_ref'],preview_witness=preview['preview_witness']))
    assert pending['receipt']['kind'] == 'PROPOSAL_OBSERVED'
    f.merge(pending)
    ready = call('reconcile',f.lookup)
    assert ready['reason'] == 'READY_FOR_ADVANCE'
    decision = call('advance',dict(schema='mastermind.workspace_source_operation_advance.v1',
        action='ADOPT_PLAN',request_id=f.lookup['request_id'],work_ref=f.lookup['work_ref'],
        phase_receipt_digest=ready['advance']['phase_receipt_digest']))
    assert decision['receipt']['kind'] == 'PROPOSAL_OBSERVED'
    f.merge(decision)
    accepted = call('reconcile',f.lookup)
    assert accepted['disposition'] == 'accepted' and accepted['phase'] == 'ADOPTION'
    assert call('read',f.lookup) == accepted
