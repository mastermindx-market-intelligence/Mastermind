"""Private source custody for a strict-v2 project root; no scheduler or grant store."""
from dataclasses import dataclass, field
import hashlib
import inspect
import json
import re
import time

from common.project_execution_private_contract import canonical, digest, KEY_RE

SCHEMA = "mastermind.project_execution_source.v1"
COMMISSION_PATH = "research/executive_commissions/PROJECT_EXECUTION.md"
ORIGINAL_SOURCE_MAX_PAYLOAD_BYTES = 65536
_SEAL = object()
_FIELDS = frozenset({"schema", "intent_id", "command_id", "work_ref", "operation_key",
    "intent_fingerprint", "arguments_sha256", "principal_scope_sha256", "workspace_permission_sha256",
    "context_sha256", "execution_binding_sha256", "dialogue_source_sha256",
    "input_fingerprint_sha256", "input_reference", "continuation_mode", "previous_run"})
_DIGESTS = _FIELDS - {"schema", "intent_id", "command_id", "work_ref", "operation_key", "input_reference", "continuation_mode", "previous_run"}


def validate_material(value):
    from common.workspace_project_plan_contract import validate_selection
    from control_plane import ceo_intent, ceo_request
    if type(value) is not dict or set(value) != _FIELDS or value["schema"] != SCHEMA:
        raise ValueError("PROJECT_EXECUTION_SOURCE_INVALID")
    validate_selection({"work_ref": value["work_ref"]})
    if value["continuation_mode"] not in {"DURABLE", "ATTENDED"}:
        raise ValueError("PROJECT_EXECUTION_SOURCE_INVALID")
    if value["previous_run"] is not None:
        from common.project_execution_private_contract import validate_previous_run
        validate_previous_run(value["previous_run"])
    key = value["operation_key"]
    if type(key) is not str or KEY_RE.fullmatch(key) is None:
        raise ValueError("PROJECT_EXECUTION_SOURCE_INVALID")
    expected = ceo_request.automated_intent_id(ceo_request.app_request_ref(key))
    if (value["intent_id"] != expected or value["command_id"] != ceo_intent.command_id_for(expected)
            or any(type(value[k]) is not str or re.fullmatch(r"[0-9a-f]{64}", value[k]) is None for k in _DIGESTS)):
        raise ValueError("PROJECT_EXECUTION_SOURCE_INVALID")
    ref = value["input_reference"]
    from control_plane.terminal_original_input_artifacts import REFERENCE_SCHEMA
    if (type(ref) is not dict or set(ref) != {"schema", "input_ref", "artifact_sha256", "payload_sha256"}
            or ref["schema"] != REFERENCE_SCHEMA
            or type(ref["input_ref"]) is not str or not re.fullmatch(r"terminal-input:[0-9a-f]{64}", ref["input_ref"])
            or any(type(ref[k]) is not str or not re.fullmatch(r"[0-9a-f]{64}", ref[k]) for k in ("artifact_sha256", "payload_sha256"))):
        raise ValueError("PROJECT_EXECUTION_INPUT_REFERENCE_INVALID")
    return json.loads(canonical(value))


@dataclass(frozen=True, slots=True)
class ProjectExecutionIssuer:
    """In-process identity of the existing control-service admission owner."""
    _seal: object
    service: object

    def __post_init__(self):
        from control_plane.executive_service import ExecutiveControlService
        if self._seal is not _SEAL or type(self.service) is not ExecutiveControlService:
            raise ValueError("PROJECT_EXECUTION_ISSUER_REQUIRED")


def bind_issuer(service):
    return ProjectExecutionIssuer(_SEAL, service)


@dataclass(frozen=True, slots=True)
class ProjectExecutionSource:
    _seal: object
    _issuer: object
    _operation: object
    _material: bytes
    _guard: object

    def __post_init__(self):
        from control_plane.foreground_operation import ForegroundOperation
        if (self._seal is not _SEAL or type(self._issuer) is not ProjectExecutionIssuer
                or type(self._operation) is not ForegroundOperation or not callable(self._guard)
                or inspect.iscoroutinefunction(self._guard)):
            raise ValueError("PROJECT_EXECUTION_SOURCE_REQUIRED")

    def material(self):
        if self._seal is not _SEAL:
            raise ValueError("PROJECT_EXECUTION_SOURCE_REQUIRED")
        return validate_material(json.loads(self._material))

    def check_intent(self, intent):
        """Pure matching: an original replay must not need fresh authority."""
        from control_plane.ceo_intent import INTENT_SCHEMA_V2, intent_fingerprint
        material = self.material()
        if (intent.get("schema") != INTENT_SCHEMA_V2 or intent.get("intent_id") != material["intent_id"]
                or intent.get("workstream") != material["work_ref"]
                or intent_fingerprint(intent) != material["intent_fingerprint"]):
            raise ValueError("PROJECT_EXECUTION_SOURCE_MISMATCH")

    def check_fresh(self):
        from control_plane.foreground_operation import current_foreground_operation
        material, operation = self.material(), self._operation
        if (current_foreground_operation() is not operation
                or operation._runtime is not self._issuer.service._require_runtime()
                or operation._command != material["command_id"]
                or operation._arguments_sha256 != material["arguments_sha256"]
                or operation._project_execution_operation != "submit"
                or operation._preexisting is not None or operation._root is not None
                or getattr(operation, "_project_execution_source", None) is not self):
            raise ValueError("PROJECT_EXECUTION_SOURCE_CHANGED")
        result = self._guard()
        if inspect.isawaitable(result):
            if inspect.iscoroutine(result):
                result.close()
            raise ValueError("PROJECT_EXECUTION_SOURCE_CHANGED")
        if result is not None:
            raise ValueError("PROJECT_EXECUTION_SOURCE_CHANGED")
        operation._require_live()


def issue_source(issuer, operation, material, guard):
    if getattr(operation, "_project_execution_source", None) is not None:
        raise ValueError("PROJECT_EXECUTION_SOURCE_ALREADY_ISSUED")
    source = ProjectExecutionSource(_SEAL, issuer, operation, canonical(validate_material(material)), guard)
    operation._project_execution_source = source
    source.check_fresh()
    return source


def validate_original_root_source(root, event):
    """Validate the original Job and its owner-qualified unique creation Event.

    This pure part is shared with bounded root-origin acquisition. The caller
    still owns unique Event selection, raw-byte limits and the physical source
    observation; this function never opens Runtime or qualifies current DATA.
    """
    from control_plane.executive_runtime import StateConflict
    try:
        if (root is None or event is None or event.event_type != "JOB_CREATED"
                or event.job_id != root.job_id or event.aggregate_type != "job"
                or event.aggregate_id != root.job_id):
            raise ValueError()
        payload = event.payload
        provenance = payload.get("provenance") or {}
        if type(provenance) is not dict:
            raise ValueError()
        commission = (provenance.get("dialogue_source") or {}).get("commission_ref") or {}
        if (commission.get("path") != COMMISSION_PATH and not any(k in provenance
                for k in ("project_execution", "project_execution_digest")) and "project_execution_admission" not in payload):
            return None
        material = validate_material(provenance.get("project_execution"))
        if (root.parent_job_id is not None or root.root_job_id != root.job_id or root.orchestration_role != "aggregation"
                or provenance.get("project_execution_digest") != digest(material)
                or payload.get("project_execution_admission") != {"schema": "mastermind.project_execution_driven_root.v1", "source": material, "source_digest": digest(material)}
                or event.command_id != material["command_id"]
                or provenance.get("intent_id") != material["intent_id"]
                or provenance.get("fingerprint") != material["intent_fingerprint"]
                or provenance.get("workstream") != material["work_ref"]
                or root.orchestration_provenance.get("command_id") != material["command_id"]
                or root.orchestration_provenance.get("source_digest") != material["intent_fingerprint"]
                or provenance.get("schema") != "mastermind.ceo_intent.v2"
                or root.orchestration_provenance.get("creator") != "ceo_intent"
                or digest(provenance.get("dialogue_source")) != material["dialogue_source_sha256"]):
            raise ValueError()
        return material
    except (ValueError, TypeError, KeyError, AttributeError):
        raise StateConflict("PROJECT_EXECUTION_ORIGINAL_SOURCE_INVALID") from None


def read_source(runtime, root):
    """Read only the original immutable root; current project text is irrelevant."""
    from control_plane.executive_runtime import StateConflict
    try:
        if root is None:
            raise ValueError()
        event = runtime.store.unique_root_created_event(
            root.job_id, max_payload_bytes=ORIGINAL_SOURCE_MAX_PAYLOAD_BYTES)
        return validate_original_root_source(root, event)
    except (ValueError, TypeError, KeyError, AttributeError):
        raise StateConflict("PROJECT_EXECUTION_ORIGINAL_SOURCE_INVALID") from None


def require_same_source(runtime, root_id, source):
    from control_plane.ceo_intent import CeoIntentConflict
    actual = read_source(runtime, runtime.jobs.get_job(root_id))
    if type(source) is not ProjectExecutionSource or actual != source.material():
        raise CeoIntentConflict("project execution original input differs")
    return actual


def input_owner(supervisor):
    """Resolve only the nominal composed primary and its original input owner."""
    from control_plane.executive_supervisor import ExecutiveSupervisor
    from control_plane.mixed_worker_supervisor import MixedExecutionOwnerSupervisor
    primary = supervisor.primary if type(supervisor) is MixedExecutionOwnerSupervisor else supervisor
    if (type(primary) is not ExecutiveSupervisor or primary.runtime is not supervisor.runtime
            or primary.instance_id != supervisor.instance_id):
        raise ValueError("PROJECT_EXECUTION_ORIGINAL_INPUT_OWNER_INVALID")
    owner = primary._project_input_owner or primary
    if (type(owner) is not ExecutiveSupervisor or owner.runtime is not primary.runtime
            or owner.instance_id != primary.instance_id or owner._project_input_owner is not None):
        raise ValueError("PROJECT_EXECUTION_ORIGINAL_INPUT_OWNER_INVALID")
    return owner


def read_original_input(supervisor, material):
    from control_plane.terminal_original_input_artifacts import TerminalOriginalInputArtifacts
    material = validate_material(material)
    ref = material["input_reference"]
    owner = input_owner(supervisor)
    payload = TerminalOriginalInputArtifacts(owner.runs_root).read(
        command_id=material["command_id"], issuer_scope_sha256=material["principal_scope_sha256"],
        fingerprint_sha256=material["input_fingerprint_sha256"], expected_artifact_sha256=ref["artifact_sha256"])
    if hashlib.sha256(payload).hexdigest() != ref["payload_sha256"]:
        raise ValueError("PROJECT_EXECUTION_ORIGINAL_INPUT_UNAVAILABLE")
    from common import project_execution_private_contract as wire
    from control_plane import ceo_intent
    try:
        value = json.loads(payload)
        if (type(value) is not dict or set(value) != {"schema", "work_ref", "request", "grounding",
                "dialogue_source", "intent", "execution_binding", "project", "previous_run"}
                or value["schema"] != "mastermind.project_execution_input.v1"
                or value["work_ref"] != material["work_ref"]):
            raise ValueError()
        request = wire.arguments(value["request"], "submit")
        intent = ceo_intent.validate_intent(value["intent"])
        project = value["project"]
        if (request["work_ref"] != material["work_ref"] or request["operation_key"] != material["operation_key"]
                or request["operation_key"] != wire.operation_key(material["principal_scope_sha256"], request)
                or digest(request) != material["arguments_sha256"]
                or request["continuation_mode"] != material["continuation_mode"]
                or request.get("previous_run") != material["previous_run"]
                or not _previous_snapshot_matches(value["previous_run"], material["previous_run"])
                or request["context_sha256"] != material["context_sha256"]
                or request["execution_binding_sha256"] != material["execution_binding_sha256"]
                or intent["schema"] != ceo_intent.INTENT_SCHEMA_V2
                or intent["intent_id"] != material["intent_id"]
                or intent["workstream"] != material["work_ref"]
                or ceo_intent.intent_fingerprint(intent) != material["intent_fingerprint"]
                or value["grounding"] != intent["grounding"]
                or digest(value["dialogue_source"]) != material["dialogue_source_sha256"]
                or value["dialogue_source"]["work_ref"] != material["work_ref"]
                or value["dialogue_source"]["commission_ref"]["path"] != COMMISSION_PATH
                or digest(value["execution_binding"]) != material["execution_binding_sha256"]
                or type(value["previous_run"]) is dict and "workspace_revision" in value["previous_run"]
                and value["execution_binding"].get("base_sha") != value["previous_run"]["workspace_revision"]["commit"]
                or type(project) is not dict or set(project) != {"expected_context", "plan", "files"}
                or digest(project) != material["context_sha256"]
                or project["expected_context"] != request["expected_context"]
                or digest(dict(schema="mastermind.project_execution_input_identity.v1",
                    command_id=material["command_id"], principal_scope=material["principal_scope_sha256"],
                    intent_fingerprint=material["intent_fingerprint"], context_sha256=material["context_sha256"],
                    input_sha256=hashlib.sha256(payload).hexdigest())) != material["input_fingerprint_sha256"]):
            raise ValueError()
    except (ValueError, TypeError, KeyError, UnicodeError, ceo_intent.CeoIntentError):
        raise ValueError("PROJECT_EXECUTION_ORIGINAL_INPUT_UNAVAILABLE") from None
    return payload


_INPUT_READ_SEAL = object()


@dataclass(frozen=True, slots=True)
class ProjectExecutionInputReadOwner:
    """One captured service/supervisor input reader, with no execution grant.

    The enrolled help owner must independently qualify its principal pair,
    exact root and actual current Plan before calling this private port.
    Original private bytes never leave it. A missing owner is not substituted.
    """
    _seal: object = field(repr=False)
    _service: object = field(repr=False)
    _runtime: object = field(repr=False)
    _binding: object = field(repr=False)
    _supervisor: object = field(repr=False)
    _original_owner: object = field(repr=False)
    _namespace: object = field(repr=False)
    _runs_root: object = field(repr=False)

    def _current(self):
        from control_plane.executive_service import ExecutiveControlService
        from control_plane.runtime_namespace_custody import ServiceRuntimeNamespaceCustody
        service = self._service
        if (self._seal is not _INPUT_READ_SEAL or type(service) is not ExecutiveControlService
                or service._closing or service._require_runtime() is not self._runtime
                or service._ceo_ingress_app_binding is not self._binding or self._binding is None
                or service._require_supervisor() is not self._supervisor
                or type(self._namespace) is not ServiceRuntimeNamespaceCustody
                or service._namespace_custody is not self._namespace
                or self._original_owner is None
                or input_owner(self._supervisor) is not self._original_owner
                or self._original_owner.runs_root != self._runs_root):
            raise ValueError("PROJECT_EXECUTION_INPUT_READ_OWNER_UNAVAILABLE")
        return self._namespace.bound_runtime(self._runtime)

    def read(self, *, selected_scope, expected_source_sha256, adopted_content,
             project_plan_sha256, deadline=None):
        from common import coo_project_help_contract as help_wire
        from common.project_task_contract import parse_plan, contract_digest
        from control_plane.terminal_original_input_artifacts import MAX_PAYLOAD_BYTES
        from control_plane.workspace_owned_task import remaining_read_seconds
        if deadline is None:
            deadline = time.monotonic() + help_wire.PRIVATE_READ_MAX_SECONDS
        def current():
            remaining_read_seconds(deadline, maximum=help_wire.PRIVATE_READ_MAX_SECONDS)
            return self._current()
        current()
        selected = help_wire.scope(selected_scope)
        expected_source_sha256 = help_wire._digest(expected_source_sha256)
        help_wire._digest(project_plan_sha256)
        if type(adopted_content) is not str:
            raise ValueError("PROJECT_EXECUTION_INPUT_READ_UNAVAILABLE")
        current_bytes = adopted_content.encode("utf-8", errors="strict")
        if not 0 < len(current_bytes) <= MAX_PAYLOAD_BYTES:
            raise ValueError("PROJECT_EXECUTION_INPUT_READ_UNAVAILABLE")
        work_ref = selected["source_plan"]["work_ref"]
        root_job_id = selected["root_job_id"]

        def original_source():
            bound = current()
            material = read_source(bound, bound.jobs.get_job(root_job_id))
            if (material is None or material["work_ref"] != work_ref
                    or digest(material) != expected_source_sha256):
                raise ValueError("PROJECT_EXECUTION_INPUT_READ_UNAVAILABLE")
            bound.store.read_binding.validate_before_core_return()
            current()
            return material

        material = original_source()
        payload = read_original_input(self._supervisor, material)
        current()
        original = json.loads(payload)
        project = original["project"]
        plan = project["plan"]
        if (type(plan) is not dict or set(plan) != {"schema", "work_ref", "authored_record",
                "adoption", "adopted_plan", "decisions"}
                or plan["schema"] != "mastermind.project_execution_plan_input.v1"
                or plan["work_ref"] != work_ref or type(plan["adopted_plan"]) is not dict
                or set(plan["adopted_plan"]) != {"source", "content"}
                or type(plan["adopted_plan"]["content"]) is not str):
            raise ValueError("PROJECT_EXECUTION_INPUT_READ_UNAVAILABLE")
        adopted = plan["adopted_plan"]
        original_bytes = adopted["content"].encode("utf-8", errors="strict")
        parsed = parse_plan(original_bytes)
        original_plan = help_wire.source_plan(dict(schema=help_wire.PLAN_SCHEMA, work_ref=work_ref,
            source=adopted["source"], contract_sha256=contract_digest(parsed)))
        expected_adoption = project["expected_context"]["adoption"]
        if (parsed["workstream"] != work_ref or original_plan != selected["source_plan"]
                or hashlib.sha256(original_bytes).hexdigest() != original_plan["source"]["content_sha256"]
                or original_bytes != current_bytes
                or type(expected_adoption) is not dict or expected_adoption.get("state") != "AVAILABLE"
                or expected_adoption.get("adopted_source") != adopted["source"]
                or original_source() != material):
            raise ValueError("PROJECT_EXECUTION_INPUT_READ_UNAVAILABLE")
        witness = dict(schema=help_wire.EXECUTION_WITNESS_SCHEMA,
            selection=dict(work_ref=work_ref, root_job_id=root_job_id),
            original_source_sha256=digest(material), input_reference_sha256=digest(material["input_reference"]),
            input_artifact_sha256=material["input_reference"]["artifact_sha256"],
            input_payload_sha256=hashlib.sha256(payload).hexdigest(), input_context_sha256=material["context_sha256"],
            original_source_plan=original_plan, current_adoption=dict(
                state="MATCHES_ORIGINAL_ADOPTED_SOURCE_AND_BYTES",
                source_plan_sha256=help_wire.digest(selected["source_plan"]), project_plan_sha256=project_plan_sha256),
            execution_authorized=False)
        current()
        return help_wire.validate_execution_witness(witness, selected_scope=selected,
            project_plan_sha256=project_plan_sha256)


def bind_original_input_reader(service, runtime):
    """Capture the existing service's exact owner; defer unavailable reads.

    A legacy help/COO read does not depend on this optional port being ready.
    Only an execution-resource help read enters it and requires real custody.
    """
    from control_plane.executive_service import ExecutiveControlService
    if type(service) is not ExecutiveControlService or service._require_runtime() is not runtime:
        raise ValueError("PROJECT_EXECUTION_INPUT_READ_OWNER_UNAVAILABLE")
    supervisor = service.supervisor
    try:
        original = input_owner(supervisor)
    except (AttributeError, TypeError, ValueError):
        original = None
    return ProjectExecutionInputReadOwner(_INPUT_READ_SEAL, service, runtime,
        service._ceo_ingress_app_binding, supervisor, original, service._namespace_custody,
        None if original is None else original.runs_root)


def input_for_job(supervisor, job):
    from control_plane.executive_runtime import _hierarchy_material, _constraints_with_host_execution_binding
    runtime = supervisor.runtime
    actual = runtime.jobs.get_job(job.job_id)
    if actual is None or any(getattr(actual, key) != getattr(job, key) for key in (
            "root_job_id", "parent_job_id", "depth", "orchestration_role", "orchestration_provenance_digest")):
        raise ValueError("PROJECT_EXECUTION_JOB_LINEAGE_INVALID")
    root = runtime.jobs.get_job(actual.root_job_id or actual.job_id)
    material = read_source(runtime, root)
    if material is None:
        return None
    with runtime.store.read() as connection:
        row = connection.execute("SELECT * FROM jobs WHERE job_id=?", (actual.job_id,)).fetchone()
        if row is None or row["root_job_id"] != root.job_id:
            raise ValueError("PROJECT_EXECUTION_JOB_LINEAGE_INVALID")
        jobs, _ = _hierarchy_material(connection, row)
        if actual.job_id not in jobs:
            raise ValueError("PROJECT_EXECUTION_JOB_LINEAGE_INVALID")
    payload = read_original_input(supervisor, material)
    value = json.loads(payload)
    expected = _constraints_with_host_execution_binding(
        value["intent"]["execution_contract"].get("constraints"), value["execution_binding"])
    if root.constraints != expected:
        raise ValueError("PROJECT_EXECUTION_ORIGINAL_SOURCE_INVALID")
    return payload.decode("utf-8", errors="strict")


class PreviousRunConflict(ValueError):
    """A distinct user turn may not fork an already continued project run."""


def _previous_snapshot_matches(value, witness):
    if witness is None:
        return value is None
    from common.project_execution_private_contract import validate_previous_run
    from control_plane.executive_orchestration_result import validate_envelope
    try:
        validate_previous_run(witness)
        if (type(value) is not dict or set(value) not in ({"witness", "objective", "handoff_text",
                "result_envelope", "terminal_receipt"}, {"witness", "objective", "handoff_text",
                "result_envelope", "terminal_receipt", "workspace_revision"}) or value["witness"] != witness
                or type(value["objective"]) is not str or not value["objective"]
                or value["handoff_text"] is not None and type(value["handoff_text"]) is not str
                or digest(value["result_envelope"]) != witness["result_envelope_sha256"]
                or digest(value["terminal_receipt"]) != witness["terminal_receipt_sha256"]
                or "workspace_revision" in value
                and not _workspace_revision_matches(value["workspace_revision"], witness)):
            return False
        validate_envelope(value["result_envelope"], expected_job_id=witness["root_job_id"],
            expected_run_id=witness["attempt_id"], expected_worker_id=value["result_envelope"].get("worker_id"),
            expected_role="aggregation", expected_root_job_id=witness["root_job_id"])
        return True
    except (ValueError, TypeError, KeyError, AttributeError):
        return False


def completed_run(supervisor, root_job_id, work_ref, principal_scope):
    """One original-principal result through the canonical completion validator."""
    from control_plane.executive_runtime import JobStatus, StateConflict
    runtime = supervisor.runtime
    root = runtime.jobs.get_job(root_job_id)
    material = read_source(runtime, root)
    if (material is None or material["work_ref"] != work_ref
            or material["principal_scope_sha256"] != principal_scope
            or root.status is not JobStatus.COMPLETED or not root.current_attempt_id):
        raise StateConflict("PROJECT_EXECUTION_COMPLETED_PARENT_REQUIRED")
    original = json.loads(read_original_input(supervisor, material))
    event = runtime.store.unique_root_created_event(root.job_id)
    # The actual writable service Runtime owns this single canonical read
    # transaction. It is not a separately granted namespace READ capability.
    completed = runtime.validated_role_completion(root.job_id,
        expected_attempt_id=root.current_attempt_id)
    if completed.job.root_job_id != root.job_id or completed.job.parent_job_id is not None:
        raise StateConflict("PROJECT_EXECUTION_PARENT_RESULT_CHANGED")
    witness = dict(schema="mastermind.project_execution_parent.v1", root_job_id=root.job_id,
        root_event_id=event.event_id, root_event_sha256=digest(event.to_dict()),
        project_execution_source_sha256=digest(material),
        input_fingerprint_sha256=material["input_fingerprint_sha256"],
        attempt_id=completed.attempt.attempt_id, result_envelope_sha256=digest(completed.result_envelope),
        terminal_receipt_sha256=digest(completed.terminal_receipt))
    value = dict(witness=witness, objective=original["request"]["objective"],
        handoff_text=original["request"]["handoff_text"],
        result_envelope=completed.result_envelope, terminal_receipt=completed.terminal_receipt)
    # Re-observe the exact immutable source after the result transaction closes.
    if (read_source(runtime, runtime.jobs.get_job(root.job_id)) != material
            or runtime.store.unique_root_created_event(root.job_id).to_dict() != event.to_dict()
            or not _previous_snapshot_matches(value, witness)):
        raise StateConflict("PROJECT_EXECUTION_PARENT_RESULT_CHANGED")
    return json.loads(canonical(value))


def require_unused_parent(runtime, witness, *, connection=None):
    """Serial admission fence in the incumbent Job/Event write transaction."""
    if witness is None:
        return
    if connection is None:
        with runtime.store.read() as owned:
            return require_unused_parent(runtime, witness, connection=owned)
    runtime.store._assert_owned_snapshot_connection(connection)
    rows = connection.execute("""SELECT job_id FROM events
        WHERE event_type='JOB_CREATED' AND aggregate_type='job'
          AND json_extract(payload_json,'$.project_execution_admission.source.previous_run.root_job_id')=?
        LIMIT 1""", (witness["root_job_id"],)).fetchall()
    if rows:
        raise PreviousRunConflict("PROJECT_EXECUTION_PREVIOUS_RUN_ALREADY_CONTINUED")


def _check_parent_transaction(source, connection):
    """Re-prove completion and single successor before the same Job insertion."""
    from control_plane.executive_runtime import _event_from_row, _validated_role_completion_snapshot, StateConflict
    runtime = source._issuer.service._require_runtime()
    runtime.store._assert_owned_snapshot_connection(connection)
    material = source.material()
    witness = material["previous_run"]
    if witness is None:
        return
    rows = connection.execute("""SELECT event_id,length(CAST(payload_json AS BLOB)) AS bytes
        FROM events WHERE job_id=? AND event_type='JOB_CREATED' ORDER BY event_id LIMIT 2""",
        (witness["root_job_id"],)).fetchall()
    if (len(rows) != 1 or rows[0]["event_id"] != witness["root_event_id"] or rows[0]["bytes"] > 65536):
        raise StateConflict("PROJECT_EXECUTION_PARENT_SOURCE_CHANGED")
    event = _event_from_row(connection.execute("SELECT * FROM events WHERE event_id=?",
        (witness["root_event_id"],)).fetchone())
    parent = validate_material(event.payload["project_execution_admission"]["source"])
    if (digest(event.to_dict()) != witness["root_event_sha256"]
            or digest(parent) != witness["project_execution_source_sha256"]
            or parent["input_fingerprint_sha256"] != witness["input_fingerprint_sha256"]
            or parent["principal_scope_sha256"] != material["principal_scope_sha256"]
            or parent["work_ref"] != material["work_ref"]):
        raise StateConflict("PROJECT_EXECUTION_PARENT_SOURCE_CHANGED")
    completed = _validated_role_completion_snapshot(connection,
        job_token=witness["root_job_id"], attempt_token=witness["attempt_id"])
    if (completed.job.parent_job_id is not None or completed.job.root_job_id != completed.job.job_id
            or digest(completed.result_envelope) != witness["result_envelope_sha256"]
            or digest(completed.terminal_receipt) != witness["terminal_receipt_sha256"]):
        raise StateConflict("PROJECT_EXECUTION_PARENT_RESULT_CHANGED")
    require_unused_parent(runtime, witness, connection=connection)


_WORKSPACE_REVISION_SCHEMA = "mastermind.project_workspace_revision.v1"


class PreviousWorkspaceUnavailable(ValueError):
    """A completed code result has no current, independently proven code tree."""


def _workspace_revision_matches(value, witness):
    try:
        if (type(value) is not dict or set(value) != {"schema", "root_job_id", "workspace_path",
                "branch", "root_base_sha", "commit", "tree", "terminal_receipt_sha256",
                "workspace_identity"}
                or value["schema"] != _WORKSPACE_REVISION_SCHEMA
                or value["root_job_id"] != witness["root_job_id"]
                or value["terminal_receipt_sha256"] != witness["terminal_receipt_sha256"]
                or any(type(value[key]) is not str or re.fullmatch(r"[0-9a-f]{40}", value[key]) is None
                       for key in ("root_base_sha", "commit", "tree"))
                or type(value["workspace_path"]) is not str or type(value["branch"]) is not str):
            return False
        identity = value["workspace_identity"]
        return (type(identity) is dict and set(identity) == {"path", "device", "inode", "uid", "gid"}
                and identity["path"] == value["workspace_path"]
                and all(type(identity[key]) is int and identity[key] >= 0
                        for key in ("device", "inode", "uid", "gid")))
    except (TypeError, KeyError):
        return False


def workspace_terminals(supervisor, root):
    """Collect bounded, validated native receipts; no model-provided Git claim."""
    from pathlib import Path
    from control_plane.executive_runtime import JobStatus, StateConflict
    from control_plane.executive_workspace import _project_manifest, PROJECT_WORKSPACE_MAX_TERMINALS
    runtime = supervisor.runtime
    material = read_source(runtime, root)
    if material is None:
        return []
    original = json.loads(read_original_input(supervisor, material))
    contract = original["intent"]["execution_contract"]
    if root.worktree != contract["worktree"] or root.branch != contract["branch"]:
        raise StateConflict("PROJECT_EXECUTION_WORKSPACE_ASSIGNMENT_CHANGED")
    with runtime.store.read() as connection:
        rows = connection.execute(
            "SELECT job_id,current_attempt_id FROM jobs WHERE root_job_id=? AND status='COMPLETED' LIMIT ?",
            (root.job_id, PROJECT_WORKSPACE_MAX_TERMINALS + 1)).fetchall()
    if len(rows) > PROJECT_WORKSPACE_MAX_TERMINALS:
        raise StateConflict("PROJECT_EXECUTION_WORKSPACE_RESULT_BOUND")
    values = []
    for row in rows:
        completed = runtime.validated_role_completion(row["job_id"],
            expected_attempt_id=row["current_attempt_id"])
        job = completed.job
        if job.status is not JobStatus.COMPLETED or job.root_job_id != root.job_id:
            raise StateConflict("PROJECT_EXECUTION_WORKSPACE_RESULT_CHANGED")
        evidence = completed.terminal_receipt.get("result_evidence") or {}
        if evidence.get("schema_version") != "mastermind.sealed_worker_result_evidence/v1":
            # Paid/model-only and operator results are never filesystem evidence.
            if completed.result_envelope.get("role_result", {}).get("artifacts"):
                raise StateConflict("PROJECT_EXECUTION_WORKSPACE_NATIVE_RESULT_REQUIRED")
            continue
        collection = evidence["collection_receipt"]["collection"]["result"]
        seal = evidence["assignment_seal_receipt"]
        boundary = seal["paths"].get("workspace")
        if job.worktree != root.worktree:
            # Existing readonly/v1 child clones keep their separate custody.
            continue
        if (type(boundary) is not dict or boundary.get("worker_traversal_revoked") is not True
                or boundary["after"]["path"] != root.worktree or boundary["after"]["mode"] != 0o700
                or boundary["after"]["uid"] != seal["control_uid"]
                or Path(root.worktree).parent != Path(original["intent"]["execution_contract"]["worktree"]).parent):
            raise StateConflict("PROJECT_EXECUTION_WORKSPACE_SEAL_INVALID")
        git = collection["git_manifest"]
        if (type(git) is not dict or set(git) - {"base_sha", "head_sha", "changed_paths", "status_sha256"}
                or any(type(git.get(key)) is not str or re.fullmatch(r"[0-9a-f]{40}", git[key]) is None
                       for key in ("base_sha", "head_sha"))
                or git["base_sha"] != git["head_sha"]
                or type(git.get("changed_paths")) is not list):
            raise StateConflict("PROJECT_EXECUTION_WORKSPACE_GIT_EVIDENCE_INVALID")
        value = dict(job_id=job.job_id, attempt_id=completed.attempt.attempt_id,
            terminal_receipt_sha256=digest(completed.terminal_receipt),
            role=job.orchestration_role, base_sha=git["base_sha"], head_sha=git["head_sha"],
            artifacts=collection["artifact_manifest"],
            workspace_identity={key: boundary["after"][key]
                                for key in ("path", "device", "inode", "uid", "gid")})
        manifest = _project_manifest(value)
        if (sorted(git["changed_paths"]) != sorted(item["path"] for item in manifest)
                or manifest and (job.orchestration_role not in {"work", "repair"}
                                 or "WRITE_BRANCH" not in job.requested_authorities)):
            raise StateConflict("PROJECT_EXECUTION_WORKSPACE_ARTIFACT_EVIDENCE_INVALID")
        values.append(value)
    if read_source(runtime, runtime.jobs.get_job(root.job_id)) != material:
        raise StateConflict("PROJECT_EXECUTION_WORKSPACE_SOURCE_CHANGED")
    return values


def workspace_base_for_job(supervisor, job):
    """Launch-time base from exact source plus verified allocator snapshots."""
    from control_plane.executive_workspace import inspect_project_workspace_revision
    runtime = supervisor.runtime
    root = runtime.jobs.get_job(job.root_job_id or job.job_id)
    material = read_source(runtime, root)
    if material is None:
        return str(job.constraints.get("base_sha") or "") or None
    input_for_job(supervisor, job)
    if job.worktree != root.worktree:
        return str(job.constraints.get("base_sha") or "") or None
    value = inspect_project_workspace_revision(root.worktree, branch=root.branch,
        root_job_id=root.job_id, base_sha=root.constraints["base_sha"],
        terminals=workspace_terminals(supervisor, root))
    return value["commit"]


def requires_workspace_continuity(supervisor, root):
    material = read_source(supervisor.runtime, root)
    if material is None:
        return False
    original = json.loads(read_original_input(supervisor, material))
    return (original["request"]["execution_profile"] == "bounded_code_change"
            or type(original["previous_run"]) is dict
            and "workspace_revision" in original["previous_run"])


def completed_workspace_revision(supervisor, previous):
    """Effect-free qualification of the final aggregation collector's exact tree."""
    from pathlib import Path
    import stat
    from control_plane.executive_workspace import inspect_project_workspace_revision
    try:
        witness = previous["witness"]
        root = supervisor.runtime.jobs.get_job(witness["root_job_id"])
        material = read_source(supervisor.runtime, root)
        actual = completed_run(supervisor, root.job_id, material["work_ref"],
                               material["principal_scope_sha256"])
        if {key: previous[key] for key in actual} != actual:
            raise ValueError()
        terminals = workspace_terminals(supervisor, root)
        final = next(item for item in terminals if item["job_id"] == root.job_id
                     and item["terminal_receipt_sha256"] == witness["terminal_receipt_sha256"])
        observed = inspect_project_workspace_revision(root.worktree, branch=root.branch,
            root_job_id=root.job_id, base_sha=root.constraints["base_sha"], terminals=terminals)
        if (final["artifacts"] or final["base_sha"] != observed["commit"]
                or final["head_sha"] != observed["commit"]
                or final["workspace_identity"] != observed["workspace_identity"]
                or stat.S_IMODE(Path(root.worktree).lstat().st_mode) != 0o700):
            raise ValueError()
        revision = dict(schema=_WORKSPACE_REVISION_SCHEMA, root_job_id=root.job_id,
            workspace_path=root.worktree, branch=root.branch,
            root_base_sha=root.constraints["base_sha"], commit=observed["commit"], tree=observed["tree"],
            terminal_receipt_sha256=witness["terminal_receipt_sha256"],
            workspace_identity=observed["workspace_identity"])
        if not _workspace_revision_matches(revision, witness):
            raise ValueError()
        return revision
    except Exception as exc:
        if isinstance(exc, PreviousWorkspaceUnavailable):
            raise
        raise PreviousWorkspaceUnavailable("PROJECT_EXECUTION_PREVIOUS_WORKSPACE_UNAVAILABLE") from exc
