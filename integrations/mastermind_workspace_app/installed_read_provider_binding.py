"""Installed source qualification for the private nominal read binding.

Owned by the actual InstalledWorkspaceSourceOperations constructor. This module
carries the installed-type/policy validation and the exact source context
capture that the core nominal lifetime must not import. Issuing the binding
grants no read authority: the same real policy, config and runtime checks run
before any current callback on every use.
"""
from dataclasses import astuple
from types import FunctionType,MethodType
import json

from control_plane.workspace_read_provider_binding import (
    _SOURCE_ATTRIBUTE,_fail,_issue_installed_read_source,_references,_same,
)


def _qualify(source):
    """Exact installed-type and constructor identity validation at issue time."""
    from integrations.mastermind_workspace_app.installed_source_operations import InstalledWorkspaceSourceOperations
    if type(source) is not InstalledWorkspaceSourceOperations:return False
    read,owner=source.read_bindings,source.canonical_data_owner
    if (type(read) is not MethodType or read.__self__ is not source
            or type(source).__dict__.get('read_bindings') is not read.__func__
            or type(owner) is not MethodType or owner.__self__ is not source
            or type(source).__dict__.get('canonical_data_owner') is not owner.__func__):return False
    return _source_types(source) is not None


def _source_types(source):
    """The actual installed constructor fields behind the captured context."""
    from integrations.mastermind_workspace_app.project_git_identity import InstalledProjectGitIdentity
    from integrations.executive_mcp.installed import InstalledBootPacketCollector
    from integrations.mastermind_workspace_app.source_operation_context import WorkspaceSourceOperationContextFactory
    permissions,collector,identity=source._permissions,source._collector,source._git
    if (type(permissions) is not WorkspaceSourceOperationContextFactory
            or type(collector) is not InstalledBootPacketCollector
            or type(identity) is not InstalledProjectGitIdentity):return None
    return permissions,collector,identity


def _capture(binding,factory,runtime,*,expected=None):
    """Exact installed source context capture and current checks, in order."""
    from integrations.mastermind_workspace_app.installed_source_operations import InstalledWorkspaceSourceOperations
    source=binding.source
    if (type(source) is not InstalledWorkspaceSourceOperations
            or type(source.read_bindings) is not MethodType
            or source.read_bindings.__func__ is not binding.read_function
            or type(source).__dict__.get('read_bindings') is not binding.read_function
            or type(source.canonical_data_owner) is not MethodType
            or source.canonical_data_owner.__func__ is not binding.owner_function
            or type(source).__dict__.get('canonical_data_owner') is not binding.owner_function):_fail()
    types=_source_types(source)
    if types is None:_fail()
    permissions,collector,identity=types
    # These remain actual CURRENT checks. No policy parser or config/grant
    # loader is bypassed, and this never calls a provider/GitHub account.
    from integrations.business_mcp_auth.contracts import validate_resource_policy
    policy=validate_resource_policy(permissions.policy)
    values=(source,permissions,permissions.policy,permissions._load_bindings,source._runtime_guard,
        collector,identity,identity.binding,identity._path,runtime,runtime.store,
        collector._source_root,collector._macro_root,collector._code_root,collector._python,
        collector._runner,permissions._now,binding.read_function,binding.owner_function,
        identity._configuration,identity.qualify,collector.read_project_plan,collector.read_project_discovery,
        collector.read_project_knowledge_catalogue,collector.read_project_knowledge_memory,
        collector.read_project_knowledge_source,collector.canonical_project_data_scope,
        collector.canonical_project_compilation_scope,collector._collect_packet,
        collector._capture_canonical_code,collector._bind_canonical_code_capture)
    source_fields=tuple(sorted(vars(source).items()))
    refs=tuple(ref for value in (*values,*(value for _,value in source_fields)) for ref in _references(value))
    # Mutable constructor metadata is compared, not retained as current.
    cells=tuple(cell.cell_contents for cell in (factory.__closure__ or ()))
    constructor=dict(zip(factory.__code__.co_freevars,cells))
    literals=(tuple(name for name,_ in source_fields),astuple(policy),identity.binding.fingerprint,identity._expected,
        json.dumps(identity._selection,sort_keys=True,separators=(',',':')),
        collector._expected_source_sha,collector._allow_synthetic_fixture,
        json.dumps(constructor.get('armed'),sort_keys=True,separators=(',',':')),
        json.dumps(constructor.get('runtime_identity'),sort_keys=True,separators=(',',':')))
    context=refs,literals
    if expected is not None and not _same(expected,context):_fail()
    # Reject descriptor drift before invoking any changed current callback.
    if source._runtime_guard is not binding.guard_function or source._runtime_guard(runtime) is not True:_fail()
    identity._configuration()
    return context


def install_installed_read_source(source):
    """Only the actual InstalledWorkspaceSourceOperations constructor issues this.

    The binding is private recognition data on its own source instance. It
    carries no permission, grant, registry or runtime effect.
    """
    if _qualify(source) is not True:_fail()
    guard=source._runtime_guard
    if not callable(guard):_fail()
    binding=_issue_installed_read_source(source,qualifier=_qualify,capture=_capture,
        read_function=source.read_bindings.__func__,
        owner_function=source.canonical_data_owner.__func__,
        guard_function=guard)
    setattr(source,_SOURCE_ATTRIBUTE,binding)
    return binding
