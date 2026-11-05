"""Private, denial-only fresh-conversation restriction in existing Job receipts.

No DB schema, registry, grant, target, session or lifecycle is added. A nominal
live source is required to label a fresh root; serialized metadata only fences
autonomy. Every actual initial write still needs its original ForegroundOperation.
"""
from dataclasses import dataclass, asdict
from contextlib import contextmanager, nullcontext
import time
import json
import re

from common.fresh_conversation_contract import canonical_digest
from control_plane.foreground_operation import ForegroundOperation, current_foreground_operation

SCHEMA = "mastermind.fresh_conversation_creation.v1"
TASK_KIND = "fresh_conversation"
_SEAL = object()
_FIELDS = frozenset({"schema", "intent_id", "command_id", "work_ref", "intent_fingerprint",
    "arguments_sha256", "principal_scope_sha256", "workspace_permission_sha256", "project_sha256",
    "dialogue_source_sha256", "host_binding_sha256", "principal_expires_at"})
_DIGESTS = _FIELDS - {"schema", "intent_id", "command_id", "work_ref", "principal_expires_at"}


def validate_restriction(value):
    if (type(value) is not dict or set(value) != _FIELDS or value["schema"] != SCHEMA
            or type(value["intent_id"]) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value["intent_id"])
            or value["command_id"] != "ceo-intent:" + value["intent_id"]
            or type(value["work_ref"]) is not str or not re.fullmatch(r"WS:[A-Za-z0-9][A-Za-z0-9._-]{0,68}", value["work_ref"])
            or type(value["principal_expires_at"]) is not int or value["principal_expires_at"] <= 0
            or any(type(value[key]) is not str or not re.fullmatch(r"[0-9a-f]{64}", value[key]) for key in _DIGESTS)):
        raise ValueError("FRESH_CONVERSATION_SOURCE_INVALID")
    return dict(value)


@dataclass(frozen=True, slots=True)
class FreshConversationCreationSource:
    _seal: object
    _issuer: object
    _operation: ForegroundOperation
    _material: bytes
    _guard: object
    _public_operation_key: str
    _project_principal: object = None
    _workspace_principal: object = None

    def __post_init__(self):
        from control_plane.fresh_conversation import FreshConversationOwner
        if (self._seal is not _SEAL or type(self._issuer) is not FreshConversationOwner
                or type(self._operation) is not ForegroundOperation or not callable(self._guard)):
            raise ValueError("FRESH_CONVERSATION_SOURCE_REQUIRED")

    def material(self):
        if self._seal is not _SEAL:
            raise ValueError("FRESH_CONVERSATION_SOURCE_REQUIRED")
        return validate_restriction(json.loads(self._material))

    def check(self):
        # Current-C/default callers retain the incumbent strict path. Only the
        # original host-issued canonical-N source may share this pure body.
        # Every check remains fresh; the full original15s source bracket ends
        # before its caller can insert a Root Event or perform another effect.
        if self._project_principal is None and self._workspace_principal is None:
            return self._check_current()
        with self._root_validation_scope(self._operation):
            return self._check_current()

    def _check_current(self):
        material = self.material()
        operation = self._operation
        issued = getattr(operation, "_fresh_conversation_creation_source", None)
        if (current_foreground_operation() is not operation
                or type(issued) is not tuple or len(issued) != 2 or issued[0] is not self
                or issued[1] != canonical_digest(material)
                or operation._runtime is not self._issuer._runtime
                or operation._command != material["command_id"]
                or operation._arguments_sha256 != material["arguments_sha256"]
                or operation._preexisting is not None or operation._root is not None
                or operation._principal.expires_at != material["principal_expires_at"]):
            raise ValueError("FRESH_CONVERSATION_SOURCE_CHANGED")
        if self._guard() is not None:
            raise ValueError("FRESH_CONVERSATION_SOURCE_CHANGED")
        from control_plane.fresh_conversation import scoped_operation_key
        from control_plane import ceo_intent, ceo_request
        key = self._public_operation_key
        if (type(key) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}", key)
                or ceo_intent.command_id_for(ceo_request.automated_intent_id(
                    ceo_request.app_request_ref(scoped_operation_key(operation._principal, key)))) != material["command_id"]):
            raise ValueError("FRESH_CONVERSATION_ORIGINAL_KEY_CHANGED")
        operation._require_live()

    def _require_root_validation_issuer(self, operation):
        # This checks the actual issuance/foreground identity without calling
        # check()/require_root()/host_current while issuing its read view.
        # The original two live/root checks still execute inside the bracket.
        from control_plane.foreground_operation import _ACTIVE, ForegroundOperation
        from control_plane.fresh_conversation import FreshConversationOwner
        material = self.material()
        issued = getattr(operation, "_fresh_conversation_creation_source", None)
        owner_issued = getattr(self._issuer, "_root_validation_source", None)
        if (self._seal is not _SEAL or type(operation) is not ForegroundOperation
                or operation is not self._operation or _ACTIVE.get() is not operation
                or operation._closed or type(self._issuer) is not FreshConversationOwner
                or operation._runtime is not self._issuer._runtime
                or type(issued) is not tuple or len(issued) != 2 or issued[0] is not self
                or issued[1] != canonical_digest(material)
                or type(owner_issued) is not tuple or len(owner_issued) != 2
                or owner_issued[0] is not operation or owner_issued[1] is not self
                or operation._command != material["command_id"]
                or operation._arguments_sha256 != material["arguments_sha256"]
                or operation._principal.expires_at != material["principal_expires_at"]
                or not operation._principal.issued_at <= time.time() < operation._principal.expires_at):
            raise ValueError("FRESH_CONVERSATION_SOURCE_CHANGED")
        return material

    @contextmanager
    def _root_validation_scope(self, operation):
        material = self._require_root_validation_issuer(operation)
        p, workspace = self._project_principal, self._workspace_principal
        if p is None and workspace is None:
            # Current-C and legacy initial admission preserve strict behavior.
            yield
            self._require_root_validation_issuer(operation)
            return
        from control_plane.principal_projection import NeutralPrincipalProjection
        if (type(p) is not NeutralPrincipalProjection or type(workspace) is not NeutralPrincipalProjection
                or asdict(p) != asdict(operation._principal)):
            raise ValueError("FRESH_CONVERSATION_SOURCE_CHANGED")
        from control_plane.fresh_conversation_membership import _project_validation_phase
        with _project_validation_phase(self._issuer, p, workspace, material["work_ref"],
                expected_project_sha256=material["project_sha256"]):
            yield
            self._require_root_validation_issuer(operation)

    def public_operation_key(self):
        self.check()
        return self._public_operation_key

    def check_intent(self, intent):
        from control_plane.ceo_intent import intent_fingerprint, INTENT_SCHEMA_V2
        self.check()
        material = self.material()
        if (intent.get("schema") != INTENT_SCHEMA_V2 or intent.get("intent_id") != material["intent_id"]
                or intent.get("workstream") != material["work_ref"]
                or intent_fingerprint(intent) != material["intent_fingerprint"]
                or intent["execution_contract"]["attempt_limit"] != 1):
            raise ValueError("FRESH_CONVERSATION_SOURCE_MISMATCH")


def _issue_creation_source(issuer, operation, material, guard, *, public_operation_key,
        project_principal=None, workspace_principal=None):
    material = validate_restriction(material)
    source = FreshConversationCreationSource(_SEAL, issuer, operation,
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode(), guard, public_operation_key,
        project_principal, workspace_principal)
    if getattr(operation, "_fresh_conversation_creation_source", None) is not None:
        raise ValueError("FRESH_CONVERSATION_SOURCE_ALREADY_ISSUED")
    operation._fresh_conversation_creation_source = (source, canonical_digest(material))
    issuer._root_validation_source = (operation, source)
    source.check()
    return source


def read_creation_restriction(runtime, root):
    """Rejoin BOTH current Job and immutable creation evidence before routing.

    Partial removal, malformed/copy/changed metadata or a missing creation
    Event refuses. A valid legacy record with no restriction stays unchanged.
    Nothing here admits a caller or resumes an operation.
    """
    from control_plane.executive_runtime import StateConflict, Runtime, RuntimeStore
    try:
        store = runtime.store if type(runtime) is Runtime else runtime
        if type(store) is not RuntimeStore:
            raise ValueError()
        with store.read() as connection:
            rows = connection.execute("SELECT command_id,payload_json FROM events WHERE event_type='JOB_CREATED' AND job_id=?", (root.job_id,)).fetchall()
            if len(rows) != 1:
                raise ValueError()
            payload = json.loads(rows[0]["payload_json"])
        provenance = payload.get("provenance")
        provenance = {} if provenance is None else provenance
        if type(provenance) is not dict:
            raise ValueError()
        marked = (root.constraints.get("task_kind") == TASK_KIND
            or "fresh_conversation_admission" in payload
            or any(key in provenance for key in ("fresh_conversation", "fresh_conversation_digest")))
        if not marked:
            return None
        material = validate_restriction(provenance.get("fresh_conversation"))
        admission = payload.get("fresh_conversation_admission")
        if (root.parent_job_id is not None or root.root_job_id != root.job_id or root.orchestration_role != "aggregation"
                or root.constraints.get("task_kind") != TASK_KIND
                or type(admission) is not dict or set(admission) != {"schema", "task_kind", "source", "source_digest"}
                or admission["schema"] != "mastermind.fresh_conversation_driven_root.v1" or admission["task_kind"] != TASK_KIND
                or admission["source"] != material or admission["source_digest"] != canonical_digest(material)
                or provenance.get("fresh_conversation_digest") != canonical_digest(material)
                or material["command_id"] != rows[0]["command_id"]
                or root.orchestration_provenance.get("command_id") != material["command_id"]
                or provenance.get("intent_id") != material["intent_id"]
                or provenance.get("workstream") != material["work_ref"]
                or provenance.get("fingerprint") != material["intent_fingerprint"]
                or root.orchestration_provenance.get("source_digest") != material["intent_fingerprint"]):
            raise ValueError()
        return material
    except (ValueError, TypeError, KeyError, AttributeError):
        raise StateConflict("FRESH_CONVERSATION_CREATION_RECORD_INVALID") from None


def require_original_creation_request(runtime, root, operation):
    material = read_creation_restriction(runtime, root)
    if material is None:
        return None
    if type(operation) is not ForegroundOperation:
        raise ValueError("FRESH_CONVERSATION_ORIGINAL_REQUEST_REQUIRED")
    operation.require_root(root.job_id)
    from control_plane.executive_runtime import Runtime
    store = runtime.store if type(runtime) is Runtime else runtime
    if (operation._runtime.store is not store or operation._command != material["command_id"]
            or operation._arguments_sha256 != material["arguments_sha256"]
            or operation._principal.expires_at != material["principal_expires_at"]):
        raise ValueError("FRESH_CONVERSATION_ORIGINAL_REQUEST_REQUIRED")
    return material


def require_initial_native_claim(store, *, root_job_id, role, profile):
    from control_plane.executive_runtime import JobRegistry, NATIVE_RETURN_TX5_EXECUTION_PROFILE
    if role != "plan" or profile != NATIVE_RETURN_TX5_EXECUTION_PROFILE:
        return None
    root = JobRegistry(store).get_job(root_job_id)
    if read_creation_restriction(store, root) is None:
        return None
    from control_plane.foreground_operation import _current_foreground_operation_or_none
    return require_original_creation_request(store, root, _current_foreground_operation_or_none())


def _fresh_root_validation_scope(operation):
    issued = getattr(operation, "_fresh_conversation_creation_source", None)
    if issued is None:
        return nullcontext()
    if type(issued) is not tuple or len(issued) != 2 or type(issued[0]) is not FreshConversationCreationSource:
        raise ValueError("FRESH_CONVERSATION_SOURCE_REQUIRED")
    return issued[0]._root_validation_scope(operation)
