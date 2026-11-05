"""Opaque fixed source-action binding owned by installed integration composition.

No integration import, public capability, registry, store or generic dispatcher.
The accepted kernel App peer and actual installed source factory supply this
process-local binding; the action owner still checks its distinct current grant.
"""
from dataclasses import dataclass
from types import MethodType

_ISSUER = object()


@dataclass(frozen=True, slots=True)
class _SourceOperationBinding:
    issuer: object
    owner: object
    store: object
    supervisor: object
    callback: MethodType
    context: tuple
    context_callback: MethodType
    qualify: object


def _issue_source_operation_binding(owner, *, qualified_owner):
    if not callable(qualified_owner) or qualified_owner(owner) is not True:
        raise ValueError("SOURCE_OPERATION_UNAVAILABLE")
    callback = owner.handle
    if (type(callback) is not MethodType or callback.__self__ is not owner
            or type(owner).__dict__.get("handle") is not callback.__func__):
        raise ValueError("SOURCE_OPERATION_UNAVAILABLE")
    context_callback = owner._context_binding
    if (type(context_callback) is not MethodType or context_callback.__self__ is not owner
            or type(owner).__dict__.get("_context_binding") is not context_callback.__func__):
        raise ValueError("SOURCE_OPERATION_UNAVAILABLE")
    return _SourceOperationBinding(_ISSUER, owner, owner._store, owner._supervisor,
                                   callback, context_callback(), context_callback, qualified_owner)


def _current_source_operation(binding, *, runtime, supervisor, host_guard):
    """Shared private binding fence; no client data can issue one."""
    def current():
        if (type(binding) is not _SourceOperationBinding or binding.issuer is not _ISSUER
                or binding.store is not runtime.store or binding.supervisor is not supervisor
                or supervisor.runtime is not runtime or host_guard() is not True
                or binding.qualify(binding.owner) is not True):
            return False
        live = getattr(binding.owner, "handle", None)
        return (type(live) is MethodType and live.__self__ is binding.owner
                and live.__func__ is binding.callback.__func__
                and type(binding.owner).__dict__.get("handle") is live.__func__
                and type(binding.owner).__dict__.get("_context_binding") is binding.context_callback.__func__
                and getattr(binding.owner, "_context_binding", None) == binding.context_callback
                and binding.context_callback() == binding.context)
    if not current():
        raise PermissionError("SOURCE_OPERATION_UNAVAILABLE")
    return current


def invoke_source_operation(binding, frame, *, runtime, supervisor, host_guard):
    current = _current_source_operation(binding,runtime=runtime,supervisor=supervisor,host_guard=host_guard)
    result = binding.callback(frame, peer_guard=current)
    if not current():
        raise PermissionError("SOURCE_OPERATION_UNAVAILABLE")
    return result


def prepare_project_plan_proposal(binding, request, *, runtime, supervisor, host_guard,
                                  principal, basis, result):
    """SAME authenticated S19 invocation's fixed private nominal handoff."""
    current = _current_source_operation(binding,runtime=runtime,supervisor=supervisor,host_guard=host_guard)
    from integrations.mastermind_workspace_app.source_operations import WorkspaceSourceOperationService
    from integrations.mastermind_workspace_app.project_plan_proposal_service import ProjectPlanProposalSourceOwner
    if (type(binding.owner) is not WorkspaceSourceOperationService
            or type(binding.owner._proposal) is not ProjectPlanProposalSourceOwner):
        raise ValueError("SOURCE_OPERATION_UNAVAILABLE")
    value = binding.owner._proposal.prepare_qualified(request,principal,basis=basis,result=result)
    if not current():
        raise PermissionError("SOURCE_OPERATION_UNAVAILABLE")
    return value
