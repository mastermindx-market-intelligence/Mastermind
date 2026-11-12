"""Closed project execution frames. Project source identities are data, never grants."""
from dataclasses import dataclass
import hashlib
import json
import re

from common.project_planning_private_contract import PRINCIPAL_FIELDS
from common.workspace_project_plan_contract import validate_selection, validate_source

SCHEMA = "mastermind.project_execution_private.v1"
RESULT_SCHEMA = "mastermind.project_execution_private_result.v1"
PREVIEW_SCHEMA = "mastermind.project_execution_preview.v1"
MAX_BYTES = 65536
KEY_RE = re.compile(r"mmos-project-execute-[0-9a-f]{40}")
PREVIEW_KEY_RE = re.compile(r"mmos-project-preview-[0-9a-f]{40}")
STATES = frozenset({"WORK_CAPABLE", "QUEUED_NATIVE_RETURN", "PLAN_ONLY",
                    "AUTONOMY_OFF", "EXECUTION_UNAVAILABLE"})


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _fail():
    raise ValueError("invalid_project_execution_request")


def _hex(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        _fail()
    return value


def expected_context(value, work_ref):
    from common.project_plan_continuity_contract import _source, ADOPTION_REASONS
    if type(value) is not dict or set(value) != {"record_source", "adoption", "adoption_decision_source"}:
        _fail()
    validate_source(value["record_source"], work_ref)
    adoption, decision = value["adoption"], value["adoption_decision_source"]
    if adoption is None:
        if decision is not None:
            _fail()
    elif type(adoption) is not dict:
        _fail()
    elif adoption.get("state") == "UNAVAILABLE":
        if set(adoption) != {"state", "reason"} or adoption["reason"] not in ADOPTION_REASONS or decision is not None:
            _fail()
    elif adoption.get("state") == "AVAILABLE":
        if (set(adoption) != {"state", "decision_ref", "adopted_source", "display_revision", "matches_authored_record"}
                or type(adoption["decision_ref"]) is not str
                or re.fullmatch(r"DEC:[A-Z0-9]+(?:-[A-Z0-9]+)*", adoption["decision_ref"]) is None
                or type(adoption["matches_authored_record"]) is not bool):
            _fail()
        revision = adoption["display_revision"]
        if revision is not None and (type(revision) is not str or not revision.strip()
                                     or len(revision) > 128 or any(c in revision for c in "\x00\r\n")):
            _fail()
        _source(adoption["adopted_source"], work_ref)
        _source(decision)
        if (decision["repository"] != "mastermindx-market-intelligence/macro"
                or decision["path"] != "agentos/decisions/DEC-" + adoption["decision_ref"][4:] + ".md"):
            _fail()
    else:
        _fail()
    return json.loads(canonical(value))


def context_from_plan(plan):
    from common.workspace_project_plan_contract import validate_body, BODY_SCHEMA_V2
    plan = validate_body(plan)
    if plan["availability"] != "AVAILABLE":
        _fail()
    v2 = plan["schema"] == BODY_SCHEMA_V2
    decision = plan["continuity"]["adoption"] if v2 else None
    return expected_context(dict(record_source=plan["source"],
        adoption=plan["plan"]["adoption"] if v2 else None,
        adoption_decision_source=decision["decision_source"] if decision and decision["state"] == "AVAILABLE" else None),
        plan["selection"]["work_ref"])


def validate_previous_run(value):
    """Closed completion witness; it locates evidence and grants no authority."""
    keys = {"schema", "root_job_id", "root_event_id", "root_event_sha256",
        "project_execution_source_sha256", "input_fingerprint_sha256", "attempt_id",
        "result_envelope_sha256", "terminal_receipt_sha256"}
    if (type(value) is not dict or set(value) != keys
            or value["schema"] != "mastermind.project_execution_parent.v1"
            or type(value["root_job_id"]) is not str
            or re.fullmatch(r"JOB-[0-9]+", value["root_job_id"]) is None
            or type(value["root_event_id"]) is not int or not 0 < value["root_event_id"] < 2**53
            or type(value["attempt_id"]) is not str or not value["attempt_id"]
            or len(value["attempt_id"]) > 128 or any(ord(c) < 32 for c in value["attempt_id"])):
        _fail()
    for key in keys - {"schema", "root_job_id", "root_event_id", "attempt_id"}:
        _hex(value[key])
    return json.loads(canonical(value))


def objective_for_intent(value):
    """Keep the exact multiline goal privately; derive the incumbent scalar."""
    if type(value) is not str:
        _fail()
    return re.sub(r"[\r\n\t]+", " ", value)


def arguments(value, operation):
    fields = {"operation_key", "work_ref"}
    if operation in {"preview", "submit"}:
        fields.add("expected_context")
        if type(value) is dict and "previous_run" in value:
            fields.add("previous_run")
    if operation == "submit":
        fields |= {"context_sha256", "execution_binding_sha256", "execution_profile", "objective", "handoff_text", "continuation_mode"}
        if type(value) is dict:
            fields |= set(value) & {"allowed_write_paths", "validation"}
    if operation not in {"preview", "submit", "status"} or type(value) is not dict or set(value) != fields:
        _fail()
    validate_selection({"work_ref": value["work_ref"]})
    pattern = PREVIEW_KEY_RE if operation == "preview" else KEY_RE
    if type(value["operation_key"]) is not str or pattern.fullmatch(value["operation_key"]) is None:
        _fail()
    if operation in {"preview", "submit"}:
        expected_context(value["expected_context"], value["work_ref"])
        if "previous_run" in value:
            validate_previous_run(value["previous_run"])
    if operation == "submit":
        _hex(value["context_sha256"]); _hex(value["execution_binding_sha256"])
        if value["continuation_mode"] not in {"DURABLE", "ATTENDED"}:
            _fail()
        if value["execution_profile"] not in {"research_only", "bounded_code_change"}:
            _fail()
        if (type(value["objective"]) is not str or not value["objective"].strip()
                or len(value["objective"]) > 4000 or "\x00" in value["objective"]):
            _fail()
        handoff = value["handoff_text"]
        if handoff is not None and (type(handoff) is not str or "\x00" in handoff or len(handoff.encode("utf-8")) > 32768):
            _fail()
        # The incumbent normalizer owns requested path/validation semantics.
        from control_plane.ceo_request import normalize_automated_request
        normalize_automated_request(dict(objective=objective_for_intent(value["objective"]), department="executive-infrastructure",
            priority=0, execution_profile=value["execution_profile"], workstream=value["work_ref"], attempt_limit=1,
            **{k:value[k] for k in ("allowed_write_paths", "validation") if k in value}))
    raw = canonical(value)
    if len(raw) > MAX_BYTES - 8192:
        _fail()
    return json.loads(raw)


def operation_key(principal_scope, value):
    """Identity includes the exact source, binding, objective and handoff."""
    _hex(principal_scope)
    body = {key: item for key, item in value.items() if key != "operation_key"}
    return "mmos-project-execute-" + digest({"principal_scope": principal_scope, "request": body})[:40]


def frame(value):
    if (type(value) is not dict or set(value) != {"schema", "operation", "principal", "workspace_principal", "arguments"}
            or value["schema"] != SCHEMA):
        _fail()
    for key in ("principal", "workspace_principal"):
        principal = value[key]
        if type(principal) is not dict or set(principal) != PRINCIPAL_FIELDS or type(principal["scopes"]) is not list:
            _fail()
    arguments(value["arguments"], value["operation"])
    raw = canonical(value)
    if len(raw) > MAX_BYTES:
        _fail()
    return json.loads(raw)


def decode_frame(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                _fail()
            value[key] = item
        return value
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        _fail()
    return frame(json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
        parse_constant=lambda _: _fail()))


@dataclass(frozen=True)
class ProjectExecutionIngressOwner:
    handler: object

    async def handle_frame(self, value):
        value = frame(value)
        if not callable(self.handler):
            _fail()
        return await self.handler(value)
