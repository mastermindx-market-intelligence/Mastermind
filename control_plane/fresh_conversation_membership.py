"""One existing canonical READ proof of newly created project membership.

A qualified source publication establishes DATA membership only. Executive
READ/SUBMIT, original parent, budget, profile and native admission stay with
FreshConversationOwner and its incumbent Runtime/foreground owners.
"""
from common import fresh_conversation_contract as wire
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

_PHASE = ContextVar("fresh_project_validation_phase", default=None)
_SEAL = object()


@dataclass(slots=True)
class _ProjectReadPhase:
    seal: object
    owner: object
    principal: object
    workspace: object
    work_ref: str
    view: object = None
    reader: object = None
    binding: object = None
    frame_digest: object = None
    snapshot_digest: object = None
    snapshot_identity: object = None
    material: object = None
    capture: object = None
    active: bool = False


@contextmanager
def _project_validation_phase(owner, principal, workspace, work_ref):
    """Synchronous pure current() only; it closes before any owner effect.

    One exact issued canonical observation supplies repeated nested host/live
    checks. Current grants stay fresh inside its nominal capture; full default,
    Event/config/source checks bracket the callback under its original15s.
    """
    from control_plane.fresh_conversation import FreshConversationOwner
    if type(owner) is not FreshConversationOwner:
        raise ValueError("CONVERSATION_PROJECT_UNAVAILABLE")
    parent = _PHASE.get()
    if parent is not None:
        if (parent.seal is not _SEAL or parent.owner is not owner
                or parent.principal is not principal or parent.workspace is not workspace
                or parent.work_ref != work_ref or not parent.active
                or getattr(owner, "_project_validation_phase", None) is not parent):
            raise ValueError("CONVERSATION_PROJECT_UNAVAILABLE")
        parent.view.check()
        yield
        parent.view.check()
        return
    phase = _ProjectReadPhase(_SEAL, owner, principal, workspace, work_ref)
    token = _PHASE.set(phase)
    owner._project_validation_phase = phase
    try:
        owner._project(principal, workspace, work_ref)
        if phase.view is None:
            raise ValueError("CONVERSATION_PROJECT_UNAVAILABLE")
        with phase.view.capture_scope() as capture:
            phase.capture, phase.active = capture, True
            try:
                yield
            finally:
                phase.active = False
    finally:
        phase.active = False
        phase.capture = phase.view = phase.material = None
        owner._project_validation_phase = None
        _PHASE.reset(token)


def _binding_current(binding):
    # Same installed binding postcondition as its ordinary read entry. No
    # mutable config/source/method identity is retained as current truth.
    return (binding.qualifier(binding.owner) is True
        and binding.owner.context_binding == binding.context_callback
        and type(binding.owner).__dict__.get("context_binding") is binding.context_callback.__func__
        and binding.context_callback() == binding.context
        and binding.owner.read_knowledge == binding.callback
        and type(binding.owner).__dict__.get("read_knowledge") is binding.callback.__func__
        and binding.owner.read_plan == binding.plan_callback
        and type(binding.owner).__dict__.get("read_plan") is binding.plan_callback.__func__)



def read_canonical_membership(reader, principal_frame, *, work_ref, snapshot, owner=None, executive_principal=None, workspace_principal=None):
    from control_plane.workspace_read_service import WorkspaceReadService, _qualified
    from control_plane.installed_canonical_project_data_binding import read_installed_project_data
    from common.workspace_project_plan_contract import validate_body, validate_source
    if type(reader) is not WorkspaceReadService or not _qualified(snapshot):
        raise ValueError("CONVERSATION_PROJECT_UNAVAILABLE")
    binding = reader._canonical_project_data
    if binding is None or binding.store is not reader.runtime.store:
        raise ValueError("CONVERSATION_PROJECT_UNAVAILABLE")
    phase = _PHASE.get()
    if phase is not None:
        if (phase.seal is not _SEAL or phase.owner is not owner or phase.work_ref != work_ref
                or phase.principal is not executive_principal or phase.workspace is not workspace_principal
                or getattr(owner, "_project_validation_phase", None) is not phase):
            raise ValueError("CONVERSATION_PROJECT_UNAVAILABLE")
        if phase.view is not None:
            from control_plane.project_canonical_data import _CAPTURE
            if (not phase.active or phase.capture is None or _CAPTURE.get() is not phase.capture
                    or phase.reader is not reader or phase.binding is not binding
                    or phase.frame_digest != wire.canonical_digest(principal_frame)
                    or phase.snapshot_digest != wire.canonical_digest(snapshot.document)
                    or phase.snapshot_identity[0] is not snapshot.owner
                    or phase.snapshot_identity[1:] != (snapshot.instance, snapshot.publication)
                    or not _binding_current(binding)):
                raise ValueError("CONVERSATION_PROJECT_CHANGED")
            phase.view.check()
            return json_copy(phase.material)
    data = read_installed_project_data(binding, principal_frame,
        operation="project_plan", selection={"work_ref": work_ref})
    if data is None:
        raise ValueError("CONVERSATION_PROJECT_UNAVAILABLE")
    body, view, _generation = data
    body = validate_body(body)
    witness = view.witness()
    publication = witness["source_operation"]
    if (body["availability"] != "AVAILABLE" or body["selection"] != {"work_ref": work_ref}
            or snapshot.document.get("sources", {}).get("macro_sha") != view.code_commit
            or view.code_commit == view.data_commit or publication is None
            or publication["selection"]["action"] != "publish_project_proposal"
            or publication["selection"]["work_ref"] != work_ref
            or publication["principal_scope"] != wire.canonical_digest(principal_frame)):
        raise ValueError("CONVERSATION_PROJECT_UNAVAILABLE")
    source = validate_source(body["source"], work_ref)
    matching = [item for item in publication["sources"]
        if item["path"] == source["path"] and item["content_sha256"] == source["content_sha256"]]
    if source["commit"] != view.data_commit or len(matching) != 1:
        raise ValueError("CONVERSATION_PROJECT_UNAVAILABLE")
    # Recheck the same actual default/Events/config/READ/latest before returning
    # DATA. No current-N/view/permission is cached or renewed here.
    view.check()
    after = reader.cache.snapshot()
    if (not _qualified(after) or snapshot.owner is not after.owner
            or snapshot.instance != after.instance or snapshot.publication != after.publication
            or wire.canonical_digest(snapshot.document) != wire.canonical_digest(after.document)):
        raise ValueError("CONVERSATION_PROJECT_CHANGED")
    material = dict(schema="mastermind.fresh_conversation_project_membership.v1",
        code_commit=view.code_commit, data_commit=view.data_commit, work_ref=work_ref,
        source=source, reader_closure_sha256=witness["reader_closure_sha256"],
        publication_sha256=wire.canonical_digest(publication),
        permission_binding_digest=view._operation.stamp)

    if phase is not None:
        phase.view, phase.reader, phase.binding = view, reader, binding
        phase.frame_digest = wire.canonical_digest(principal_frame)
        phase.snapshot_digest = wire.canonical_digest(snapshot.document)
        phase.snapshot_identity = (snapshot.owner, snapshot.instance, snapshot.publication)
        phase.material = json_copy(material)
    return material


def json_copy(value):
    import json
    return json.loads(json.dumps(value, allow_nan=False))
