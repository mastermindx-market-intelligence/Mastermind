"""Private source custody for a strict-v2 project root; no scheduler or grant store."""
from dataclasses import dataclass
import hashlib
import inspect
import json
import re

from common.project_execution_private_contract import canonical, digest, KEY_RE

SCHEMA = "mastermind.project_execution_source.v1"
COMMISSION_PATH = "research/executive_commissions/PROJECT_EXECUTION.md"
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
class ProjectExecutionSource:
    _seal: object
    _issuer: object
    _operation: object
    _material: bytes
    _guard: object

    def __post_init__(self):
        from integrations.mastermind_executive_app.project_execution_factory import ProjectExecutionAppFactory
        from control_plane.foreground_operation import ForegroundOperation
        if (self._seal is not _SEAL or type(self._issuer) is not ProjectExecutionAppFactory
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


def read_source(runtime, root):
    """Read only the original immutable root; current project text is irrelevant."""
    from control_plane.executive_runtime import StateConflict
    try:
        if root is None:
            raise ValueError()
        event = runtime.store.unique_root_created_event(root.job_id)
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


def require_same_source(runtime, root_id, source):
    from control_plane.ceo_intent import CeoIntentConflict
    actual = read_source(runtime, runtime.jobs.get_job(root_id))
    if type(source) is not ProjectExecutionSource or actual != source.material():
        raise CeoIntentConflict("project execution original input differs")
    return actual


def read_original_input(supervisor, material):
    from control_plane.terminal_original_input_artifacts import TerminalOriginalInputArtifacts
    material = validate_material(material)
    ref = material["input_reference"]
    from control_plane.executive_supervisor import ExecutiveSupervisor
    owner = getattr(supervisor, "_project_input_owner", None) or supervisor
    if (type(owner) is not ExecutiveSupervisor or owner.runtime is not supervisor.runtime
            or owner.instance_id != supervisor.instance_id or owner._project_input_owner is not None):
        raise ValueError("PROJECT_EXECUTION_ORIGINAL_INPUT_OWNER_INVALID")
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
        if (type(value) is not dict or set(value) != {"witness", "objective", "handoff_text",
                "result_envelope", "terminal_receipt"} or value["witness"] != witness
                or type(value["objective"]) is not str or not value["objective"]
                or value["handoff_text"] is not None and type(value["handoff_text"]) is not str
                or digest(value["result_envelope"]) != witness["result_envelope_sha256"]
                or digest(value["terminal_receipt"]) != witness["terminal_receipt_sha256"]):
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
