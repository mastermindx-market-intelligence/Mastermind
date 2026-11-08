"""Actual installed constructors/core binding; final preparation is an inert spy.

The spy is ONLY the unchanged proposal preparation boundary. It proves the
relocated call's exact receiver/arguments and rejection before entry, not a
qualified planning-result/basis or permission to publish.
"""
import pytest
from tests.test_installed_source_git_identity import identity
from tests.test_knowledge_installed_source_join import owner, env, isolated_git_env, install_actual_compiler
from integrations.mastermind_workspace_app.installed_source_operations import InstalledWorkspaceSourceOperations
from integrations.mastermind_workspace_app.source_operations import WorkspaceSourceOperationService
from integrations.mastermind_workspace_app.project_plan_proposal_service import ProjectPlanProposalSourceOwner
from control_plane.workspace_source_operation_binding import prepare_project_plan_proposal


@pytest.mark.parametrize('damage', [None, 'method', 'proposal', 'host'])
def test_fixed_proposal_handoff_retains_actual_installed_owner_and_current_checks(owner, identity, tmp_path, monkeypatch, damage):
    o = owner
    git_identity, _, _, _ = identity
    collector, _ = install_actual_compiler(o, tmp_path, monkeypatch)
    calls = []
    sentinel = object()
    def prepared(self, request, principal, *, basis, result):
        calls.append((self, request, principal, basis, result))
        return sentinel
    monkeypatch.setattr(ProjectPlanProposalSourceOwner, 'prepare_qualified', prepared)
    factory = InstalledWorkspaceSourceOperations(collector=collector, policy=o['service']._permissions.policy,
        load_bindings=lambda: o['bindings'], git_identity=git_identity, runtime_guard=lambda runtime: runtime is o['runtime'])
    supervisor = o['private'].supervisor
    issued = factory(o['runtime'], supervisor)
    assert type(issued.owner) is WorkspaceSourceOperationService
    actual_proposal = issued.owner._proposal
    assert type(actual_proposal) is ProjectPlanProposalSourceOwner
    request, principal, basis, result = object(), object(), object(), object()
    if damage == 'method':
        monkeypatch.setattr(issued.owner, 'prepare_project_plan_proposal', lambda *a, **k: calls.append('foreign'))
    elif damage == 'proposal':
        monkeypatch.setattr(issued.owner, '_proposal', object())
    def invoke():
        return prepare_project_plan_proposal(issued, request, runtime=o['runtime'], supervisor=supervisor,
            host_guard=lambda: damage != 'host', principal=principal, basis=basis, result=result)
    if damage is None:
        assert invoke() is sentinel
        assert calls == [(actual_proposal, request, principal, basis, result)]
    else:
        with pytest.raises((ValueError, PermissionError, AttributeError)):
            invoke()
        assert calls == []
    assert o['runtime'].events.list_events() == []
    assert o['runtime'].jobs.list_jobs() == []


@pytest.mark.parametrize('guard_kind', ['method', 'object'])
def test_existing_installed_constructor_accepts_its_actual_callable_guard(owner, identity, tmp_path, monkeypatch, guard_kind):
    """The original constructor accepts callables, not only plain functions."""
    from control_plane.workspace_read_provider_binding import installed_read_source_binding
    o = owner
    git_identity, _, _, _ = identity
    collector, _ = install_actual_compiler(o, tmp_path, monkeypatch)
    calls = []
    class Guard:
        def current(self, runtime):
            calls.append(runtime)
            return runtime is o['runtime']
        def __call__(self, runtime):
            return self.current(runtime)
    held = Guard()
    guard = held.current if guard_kind == 'method' else held
    source = InstalledWorkspaceSourceOperations(collector=collector, policy=o['service']._permissions.policy,
        load_bindings=lambda: o['bindings'], git_identity=git_identity, runtime_guard=guard)
    binding = installed_read_source_binding(source.read_bindings)
    assert binding is not None and binding.guard_function is guard
    assert calls == []  # Descriptor issuance is not a READ/permission check.
    pair = source.read_bindings(o['runtime'])
    assert pair[0].store is o['runtime'].store and pair[1].store is o['runtime'].store
    assert calls and all(value is o['runtime'] for value in calls)
    assert o['runtime'].events.list_events() == []
