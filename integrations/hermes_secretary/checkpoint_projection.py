"""Immutable context and original-result recovery projections; no acquisition/I/O.

Only an authenticated host composition may supply these normalized owner facts.
Validation proves shape, joins and byte integrity, never authenticity or authority.
Runtime/SessionBridge retain requests, Jobs, Attempts and returns; Hermes retains
sessions, admissions and compaction. This module has no execution or write port.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import hmac
import json
import re


FACTS_SCHEMA = "mastermind.hermes_checkpoint_owner_facts.v1"
MANIFEST_SCHEMA = "mastermind.hermes_checkpoint_projection.v1"
RECOVERY_SCHEMA = "mastermind.hermes_checkpoint_recovery.v1"
MAX_FACTS_BYTES = 24 * 1024
MAX_CONTEXT_BYTES = 16 * 1024
MAX_SUMMARY_BYTES = 1024
MAX_READ_WINDOW_SECONDS = 300

# Validation vocabulary only, not a Job/Attempt state machine. The contract test
# compares these with the incumbent Runtime enums at the commissioned source.
_JOB_STATUSES = frozenset({"QUEUED", "RUNNING", "CHECKPOINTED", "RATE_LIMITED",
    "FAILED", "LOST", "CANCEL_REQUESTED", "COMPLETED", "CANCELLED", "UNAVAILABLE"})
_ATTEMPT_STATUSES = (_JOB_STATUSES - {"QUEUED"}) | {"CLAIMED", "NOT_APPLICABLE"}
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}\Z")
_JOB = re.compile(r"JOB-[0-9]{1,9}\Z")
_ATTEMPT = re.compile(r"ATT-[A-Za-z0-9_.:-]{1,124}\Z")
_SECRET_PREFIX = re.compile(r"(?:sk-|gh[pousr]_|github_pat_|xox[baprs]-|eyJ)", re.I)

_SHAPES = {
    "native": frozenset({"role", "profile_sha256", "session_sha256",
        "principal_sha256", "instance_sha256", "authority_epoch", "revision",
        "execution_generation"}),
    "runtime": frozenset({"root_id", "root_job_id", "work_ref", "job_id",
        "attempt_id", "parent_job_id", "attempt_status", "root_status"}),
    "original": frozenset({"kind", "principal_sha256", "target_ref", "operation_key",
        "request_ref", "request_revision", "read_ref", "input_sha256",
        "native_input_sha256", "binding_sha256", "submission_id", "commit_status",
        "admission_id", "admission_sequence", "admission_epoch",
        "admission_generation", "admission_status"}),
    "authority": frozenset({"principal_sha256", "generation", "read_permitted",
        "approval_status"}),
    "source": frozenset({"repository", "ref", "path", "sha256"}),
    "context": frozenset({"message_checkpoint_ref", "message_checkpoint_sha256",
        "compaction_generation"}),
    "return": frozenset({"result_status", "result_ref", "result_sha256",
        "result_outcome", "parent_request_ref", "parent_terminal_ref",
        "parent_terminal_sha256", "consumption_status", "consumption_ref",
        "executive_acceptance", "acceptance_ref"}),
    "observation": frozenset({"source_identity", "generation_before",
        "generation_after", "read_state", "observed_at", "valid_until",
        "write_uncertainty", "omitted_count", "receipt_schema", "receipt_state", "finalized"}),
}
_FACTS_KEYS = frozenset(_SHAPES) | {"schema", "snapshot_sha256"}
_MANIFEST_KEYS = frozenset({"schema", "facts", "summary", "omissions"})
_SUMMARY_KEYS = frozenset({"text", "limit_bytes", "truncated", "omitted_bytes"})
_OMITTED_CONTENT = ("RAW_PROMPT", "TRANSCRIPT", "RAW_RESULT", "SECRETS",
                    "FILESYSTEM_SNAPSHOT", "EXECUTION_AUTHORITY")


class CheckpointError(ValueError):
    """A closed code; invalid input values and exception details never escape."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise CheckpointError(code)


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _digest(value: dict) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _plain(value, *, depth: int = 0, count: list[int] | None = None) -> None:
    """Bound plain data before encoding; no custom Mapping or object callbacks."""
    count = [0] if count is None else count
    count[0] += 1
    _require(depth <= 8 and count[0] <= 512, "INPUT_OVER_BUDGET")
    if type(value) is dict:
        _require(len(value) <= 32, "INPUT_OVER_BUDGET")
        for key, item in value.items():
            _require(type(key) is str and len(key) <= 64, "INVALID_FIELD")
            _plain(item, depth=depth + 1, count=count)
    elif type(value) is list:
        _require(len(value) <= 32, "INPUT_OVER_BUDGET")
        for item in value:
            _plain(item, depth=depth + 1, count=count)
    elif type(value) is str:
        _require(len(value) <= 2048 and all(32 <= ord(c) < 127 for c in value),
                 "INVALID_TEXT")
    else:
        _require(value is None or type(value) is bool or
                 (type(value) is int and 0 <= value <= 2**63 - 1), "INVALID_VALUE")


def _shape(value, keys) -> None:
    _require(type(value) is dict and set(value) == keys, "INVALID_FIELDS")


def _enum(value, options) -> None:
    _require(type(value) is str and value in options, "INVALID_STATUS")


def _number(value, minimum: int = 0, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    _require(type(value) is int and minimum <= value <= 2**63 - 1, "INVALID_COUNTER")


def _hash(value, *, nullable: bool = False, length: int = 64) -> None:
    if value is None and nullable:
        return
    pattern = _HEX if length == 64 else re.compile(r"[0-9a-f]{%d}\Z" % length)
    _require(type(value) is str and pattern.fullmatch(value) is not None, "INVALID_DIGEST")


def _ref(value, *, nullable: bool = False, pattern=_TOKEN) -> None:
    if value is None and nullable:
        return
    _require(type(value) is str and pattern.fullmatch(value) is not None
             and _SECRET_PREFIX.match(value) is None, "INVALID_REFERENCE")


def _pair(value: dict, reference: str, digest: str) -> None:
    _ref(value[reference], nullable=True)
    _hash(value[digest], nullable=True)
    _require((value[reference] is None) == (value[digest] is None), "PARTIAL_REFERENCE")


def _validate_facts(value: dict) -> dict:
    _plain(value)
    _shape(value, _FACTS_KEYS)
    _require(value["schema"] == FACTS_SCHEMA, "UNSUPPORTED_FACTS_SCHEMA")
    _require(len(_canonical(value)) <= MAX_FACTS_BYTES, "INPUT_OVER_BUDGET")
    for name, keys in _SHAPES.items():
        _shape(value[name], keys)
    _hash(value["snapshot_sha256"])
    body = {k: v for k, v in value.items() if k != "snapshot_sha256"}
    _require(hmac.compare_digest(value["snapshot_sha256"], _digest(body)), "SNAPSHOT_DIGEST_MISMATCH")

    native, runtime, original = (value[k] for k in ("native", "runtime", "original"))
    authority, source, context, returned, observation = (
        value[k] for k in ("authority", "source", "context", "return", "observation"))
    _enum(native["role"], {"mmsecretary", "mmmeta"})
    for key in ("profile_sha256", "session_sha256", "principal_sha256"):
        _hash(native[key])
    _hash(native["instance_sha256"], nullable=True)
    for key in ("authority_epoch", "revision", "execution_generation"):
        _number(native[key], 1 if key == "authority_epoch" else 0, nullable=True)
    current_native = [native[k] for k in ("instance_sha256", "authority_epoch", "revision", "execution_generation")]
    _require(all(v is None for v in current_native) or all(v is not None for v in current_native),
             "PARTIAL_NATIVE_TARGET")

    _ref(runtime["root_id"])
    _ref(runtime["root_job_id"], pattern=_JOB)
    _ref(runtime["work_ref"], pattern=re.compile(r"WS:[A-Z0-9][A-Z0-9_-]{0,119}\Z"))
    _ref(runtime["job_id"], nullable=True, pattern=_JOB)
    _ref(runtime["attempt_id"], nullable=True, pattern=_ATTEMPT)
    _ref(runtime["parent_job_id"], nullable=True, pattern=_JOB)
    _enum(runtime["root_status"], _JOB_STATUSES)
    _enum(runtime["attempt_status"], _ATTEMPT_STATUSES)
    if runtime["attempt_status"] == "NOT_APPLICABLE":
        _require(all(runtime[k] is None for k in ("job_id", "attempt_id", "parent_job_id")),
                 "INVALID_ATTEMPT_SCOPE")
    elif runtime["attempt_status"] != "UNAVAILABLE":
        _require(runtime["job_id"] is not None and runtime["attempt_id"] is not None,
                 "PARTIAL_ATTEMPT")
    if runtime["job_id"] is not None:
        _require(runtime["job_id"] != runtime["parent_job_id"], "WRONG_PARENT")
        _require((runtime["job_id"] == runtime["root_job_id"]) == (runtime["parent_job_id"] is None),
                 "WRONG_PARENT")

    _enum(original["kind"], {"HERMES_SECRETARY", "NATIVE_CONTINUATION"})
    if original["kind"] == "HERMES_SECRETARY":
        _require(runtime["attempt_status"] == "NOT_APPLICABLE", "ORIGINAL_ATTEMPT_SCOPE_MISMATCH")
    else:
        _require(runtime["job_id"] is not None and runtime["attempt_id"] is not None
                 and runtime["attempt_status"] != "NOT_APPLICABLE", "ORIGINAL_ATTEMPT_SCOPE_MISMATCH")
    for key in ("principal_sha256", "request_revision", "input_sha256", "binding_sha256"):
        _hash(original[key])
    _ref(original["target_ref"])
    _ref(original["operation_key"])
    key = _digest({"schema": "mastermind.session_bridge.continue_request.v1",
                   "operation_key": original["operation_key"]})
    _require(original["read_ref"] == "session-reply-" + key
             and original["request_ref"] == "session-bridge-continue:" + key,
             "ORIGINAL_REQUEST_JOIN_MISMATCH")
    _hash(original["native_input_sha256"], nullable=True)
    if original["kind"] == "HERMES_SECRETARY":
        _require(re.fullmatch(r"hermes_secretary:[0-9a-f]{64}", original["target_ref"]) is not None,
                 "ORIGINAL_TARGET_MISMATCH")
        operation = "session-continue-" + _digest({
            "schema": "mastermind.session_bridge.hermes_secretary_operation.v1",
            "target_ref": original["target_ref"]})
        _require(original["operation_key"] == operation and original["submission_id"] == "session-secretary-" + key
                 and original["native_input_sha256"] is not None, "ORIGINAL_REQUEST_JOIN_MISMATCH")
    else:
        _require(original["submission_id"] is None and original["native_input_sha256"] is None,
                 "INVALID_NATIVE_REQUEST_METADATA")
    _enum(original["commit_status"], {"COMMITTED", "NOT_COMMITTED", "UNKNOWN"})
    _ref(original["admission_id"], nullable=True)
    for name in ("admission_sequence", "admission_epoch", "admission_generation"):
        _number(original[name], 0 if name == "admission_generation" else 1, nullable=True)
    if original["admission_id"] is None:
        _require(all(original[k] is None for k in ("admission_sequence", "admission_epoch",
                     "admission_generation", "admission_status")), "PARTIAL_ADMISSION")
    else:
        _enum(original["admission_status"], {"queued", "started", "unknown", "terminal"})
        _require(original["admission_sequence"] is not None and original["admission_epoch"] is not None
                 and original["commit_status"] == "COMMITTED", "PARTIAL_ADMISSION")
        if native["authority_epoch"] is not None:
            _require(original["admission_epoch"] <= native["authority_epoch"], "STALE_NATIVE_EPOCH")

    _hash(authority["principal_sha256"])
    _number(authority["generation"], nullable=True)
    _require(type(authority["read_permitted"]) is bool, "INVALID_PERMISSION")
    _enum(authority["approval_status"], {"CURRENT", "REVOKED", "UNAVAILABLE"})
    _require(source["repository"] == "mastermindx-market-intelligence/Mastermind", "FOREIGN_SOURCE")
    _hash(source["ref"], length=40)
    _hash(source["sha256"])
    path = source["path"]
    _require(type(path) is str and len(path) <= 256 and re.fullmatch(
        r"(?:docs|integrations|control_plane)/[A-Za-z0-9_./-]+", path) is not None
        and all(p and not p.startswith(".") for p in path.split("/")), "INVALID_SOURCE_PATH")
    _pair(context, "message_checkpoint_ref", "message_checkpoint_sha256")
    _number(context["compaction_generation"], nullable=True)

    _enum(returned["result_status"], {"RETAINED", "PENDING", "UNAVAILABLE", "UNKNOWN"})
    _pair(returned, "result_ref", "result_sha256")
    _enum(returned["result_outcome"], {"SUCCESS", "FAILED", "UNKNOWN"})
    _require((returned["result_status"] == "RETAINED") == (returned["result_ref"] is not None),
             "PARTIAL_RESULT")
    if returned["result_status"] == "RETAINED":
        _require(original["commit_status"] == "COMMITTED", "UNCOMMITTED_RESULT")
        if original["kind"] == "HERMES_SECRETARY":
            _require(original["admission_status"] == "terminal", "NONTERMINAL_RESULT")
    else:
        _require(returned["result_outcome"] == "UNKNOWN", "RESULT_OUTCOME_WITHOUT_RESULT")
    _require(returned["parent_request_ref"] == original["request_ref"], "WRONG_PARENT")
    _pair(returned, "parent_terminal_ref", "parent_terminal_sha256")
    _enum(returned["consumption_status"], {"UNKNOWN", "UNCONSUMED", "DELIVERED", "CONSUMED"})
    _ref(returned["consumption_ref"], nullable=True)
    _require((returned["consumption_status"] == "CONSUMED") == (returned["consumption_ref"] is not None),
             "CONSUMPTION_WITHOUT_RECEIPT")
    if returned["consumption_status"] in {"DELIVERED", "CONSUMED"}:
        _require(returned["parent_terminal_ref"] is not None, "CONSUMPTION_WITHOUT_RETURN")
    _enum(returned["executive_acceptance"], {"NOT_OBSERVED", "ACCEPTED", "REJECTED"})
    _ref(returned["acceptance_ref"], nullable=True)
    _require((returned["executive_acceptance"] == "NOT_OBSERVED") == (returned["acceptance_ref"] is None),
             "ACCEPTANCE_WITHOUT_RECEIPT")
    if returned["result_status"] == "PENDING":
        _require(returned["parent_terminal_ref"] is None
                 and returned["consumption_status"] not in {"DELIVERED", "CONSUMED"}
                 and returned["executive_acceptance"] == "NOT_OBSERVED"
                 and original["admission_status"] != "terminal", "PENDING_TERMINAL_CONTRADICTION")

    _require(observation["receipt_schema"] == "mastermind.runtime_read_observation.v1",
             "UNSUPPORTED_OBSERVATION_SCHEMA")
    _enum(observation["receipt_state"], {"SAME", "CONFLICT", "UNKNOWN"})
    _require(type(observation["finalized"]) is bool, "INVALID_OBSERVATION_FINALIZATION")
    _hash(observation["source_identity"], length=32, nullable=True)
    for name in ("generation_before", "generation_after"):
        _number(observation[name], nullable=True)
    for name in ("observed_at", "valid_until", "omitted_count"):
        _number(observation[name])
    _enum(observation["read_state"], {"CURRENT", "PARTIAL", "HISTORICAL", "UNAVAILABLE"})
    _enum(observation["write_uncertainty"], {"NONE", "PENDING_SUBMIT", "EFFECT_UNKNOWN"})
    _require(0 <= observation["valid_until"] - observation["observed_at"] <= MAX_READ_WINDOW_SECONDS,
             "INVALID_READ_WINDOW")
    # Detached JSON, never a caller-owned nested container.
    return json.loads(_canonical(value))


def _summary(facts: dict, limit: int) -> dict:
    _number(limit)
    _require(limit <= MAX_SUMMARY_BYTES, "SUMMARY_OVER_BUDGET")
    returned = facts["return"]
    text = (f"Original result: {returned['result_status']}. "
            f"Parent consumption: {returned['consumption_status']}. "
            f"Executive acceptance: {returned['executive_acceptance']}. "
            "Context only. Reacquire the original request and current owner facts.")
    # Entirely generated ASCII, not redaction heuristics over an arbitrary prompt.
    return {"text": text[:limit], "limit_bytes": limit, "truncated": len(text) > limit,
            "omitted_bytes": max(0, len(text) - limit)}


def _omissions(facts: dict) -> dict:
    missing = []
    if facts["native"]["instance_sha256"] is None:
        missing.append("NATIVE_CURRENT_TARGET")
    if facts["original"]["admission_id"] is None:
        missing.append("NATIVE_ADMISSION")
    if facts["authority"]["generation"] is None:
        missing.append("AUTHORITY_GENERATION")
    if not facts["observation"]["finalized"] or facts["observation"]["receipt_state"] != "SAME":
        missing.append("QUALIFIED_RUNTIME_OBSERVATION")
    if facts["runtime"]["attempt_status"] == "UNAVAILABLE":
        missing.append("RUNTIME_ATTEMPT")
    if facts["context"]["message_checkpoint_ref"] is None:
        missing.append("MESSAGE_CHECKPOINT")
    if facts["context"]["compaction_generation"] is None:
        missing.append("COMPACTION_GENERATION")
    if facts["return"]["parent_terminal_ref"] is None:
        missing.append("PARENT_TERMINAL_RETURN")
    if facts["return"]["consumption_status"] == "UNKNOWN":
        missing.append("PARENT_CONSUMPTION")
    if facts["return"]["executive_acceptance"] == "NOT_OBSERVED":
        missing.append("EXECUTIVE_ACCEPTANCE")
    return {"content": list(_OMITTED_CONTENT), "metadata_unavailable": missing,
            "event_history_included": False}


@dataclass(frozen=True, slots=True)
class CheckpointManifest:
    """Canonical immutable bytes. The existing owner chooses where to retain them."""

    canonical_json: bytes

    def __post_init__(self) -> None:
        _require(type(self.canonical_json) is bytes, "INVALID_MANIFEST")
        _require(len(self.canonical_json) <= MAX_CONTEXT_BYTES, "CONTEXT_BUDGET_EXCEEDED")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json).hexdigest()

    def as_dict(self) -> dict:
        return json.loads(self.canonical_json)


def build_checkpoint(facts: dict, *, summary_limit_bytes: int = 512,
                     context_budget_bytes: int = MAX_CONTEXT_BYTES) -> CheckpointManifest:
    """Build context from a closed metadata-only export, never from a transcript."""
    _number(context_budget_bytes, 1)
    _require(context_budget_bytes <= MAX_CONTEXT_BYTES, "CONTEXT_BUDGET_EXCEEDED")
    clean = _validate_facts(facts)
    result = {"schema": MANIFEST_SCHEMA, "facts": clean,
              "summary": _summary(clean, summary_limit_bytes), "omissions": _omissions(clean)}
    encoded = _canonical(result)
    _require(len(encoded) <= context_budget_bytes, "CONTEXT_BUDGET_EXCEEDED")
    return CheckpointManifest(encoded)


def _unique(pairs) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result, "DUPLICATE_JSON_FIELD")
        result[key] = value
    return result


def validate_checkpoint(value, *, expected_sha256: str) -> CheckpointManifest:
    """Require the digest retained by the caller's existing canonical owner.

    An attacker-supplied document plus its own hash is not authenticated evidence.
    Consumers must still obtain fresh authorized facts before projecting recovery.
    """
    _hash(expected_sha256)
    if type(value) is CheckpointManifest:
        value = value.canonical_json
    if type(value) is bytes:
        _require(len(value) <= MAX_CONTEXT_BYTES, "CONTEXT_BUDGET_EXCEEDED")
        try:
            document = json.loads(value, object_pairs_hook=_unique)
        except (ValueError, UnicodeError, RecursionError):
            raise CheckpointError("INVALID_MANIFEST_JSON") from None
        _plain(document)
        _require(value == _canonical(document), "NONCANONICAL_MANIFEST")
    else:
        _require(type(value) is dict, "INVALID_MANIFEST")
        _plain(value)
        document = value
    _shape(document, _MANIFEST_KEYS)
    _require(document["schema"] == MANIFEST_SCHEMA, "UNSUPPORTED_MANIFEST_SCHEMA")
    encoded = _canonical(document)
    _require(len(encoded) <= MAX_CONTEXT_BYTES, "CONTEXT_BUDGET_EXCEEDED")
    _require(hmac.compare_digest(hashlib.sha256(encoded).hexdigest(), expected_sha256),
             "MANIFEST_DIGEST_MISMATCH")
    facts = _validate_facts(document["facts"])
    _shape(document["summary"], _SUMMARY_KEYS)
    _require(type(document["summary"]["truncated"]) is bool, "UNQUALIFIED_SUMMARY")
    _number(document["summary"]["omitted_bytes"])
    _require(document["summary"] == _summary(facts, document["summary"]["limit_bytes"]),
             "UNQUALIFIED_SUMMARY")
    _shape(document["omissions"], {"content", "metadata_unavailable", "event_history_included"})
    _require(document["omissions"]["event_history_included"] is False, "UNQUALIFIED_OMISSIONS")
    _require(document["omissions"] == _omissions(facts), "UNQUALIFIED_OMISSIONS")
    return CheckpointManifest(encoded)


@dataclass(frozen=True, slots=True)
class RecoveryProjection:
    """An advisory read/refusal map, never a grant, lock, ACK or resume operation."""

    state: str
    reason: str
    read_ref: str | None = None
    request_ref: str | None = None
    operation_key: str | None = None
    attempt_id: str | None = None
    result_ref: str | None = None
    result_sha256: str | None = None
    parent_terminal_ref: str | None = None
    consumption_status: str = "UNKNOWN"
    executive_acceptance: str = "NOT_OBSERVED"
    gateway_restarted: bool | None = None
    context_compacted: bool | None = None

    def __post_init__(self) -> None:
        _enum(self.state, {"REFUSED", "EVIDENCE_ONLY", "RECONCILE_ORIGINAL",
            "RECOVER_ORIGINAL_RESULT", "AWAIT_ORIGINAL_RESULT", "ALREADY_CONSUMED"})
        _ref(self.reason)
        for value in (self.read_ref, self.request_ref, self.operation_key, self.attempt_id,
                      self.result_ref, self.parent_terminal_ref):
            _ref(value, nullable=True)
        _hash(self.result_sha256, nullable=True)
        _enum(self.consumption_status, {"UNKNOWN", "UNCONSUMED", "DELIVERED", "CONSUMED"})
        _enum(self.executive_acceptance, {"NOT_OBSERVED", "ACCEPTED", "REJECTED"})
        for value in (self.gateway_restarted, self.context_compacted):
            _require(value is None or type(value) is bool, "INVALID_VALUE")

    @property
    def schema(self) -> str:
        return RECOVERY_SCHEMA

    @property
    def can_write(self) -> bool:
        return False

    @property
    def can_resume_execution(self) -> bool:
        return False

    def as_dict(self) -> dict:
        return {"schema": self.schema, **asdict(self), "can_write": False,
                "can_resume_execution": False}


def _current(facts: dict, now: int) -> None:
    observation, authority = facts["observation"], facts["authority"]
    # READ and execution approval are distinct incumbent grants. A revoked
    # execution approval does not erase separately authorized historical evidence.
    _require(authority["read_permitted"], "READ_AUTHORITY_UNAVAILABLE")
    _require(authority["generation"] is not None, "AUTHORITY_GENERATION_UNAVAILABLE")
    _require(authority["principal_sha256"] == facts["original"]["principal_sha256"], "FOREIGN_PRINCIPAL")
    _require(observation["read_state"] == "CURRENT" and observation["omitted_count"] == 0,
             "PARTIAL_OR_NONCURRENT_SNAPSHOT")
    _require(observation["finalized"], "OBSERVATION_NOT_FINALIZED")
    _require(observation["receipt_state"] == "SAME" and observation["source_identity"] is not None
             and observation["generation_before"] is not None
             and observation["generation_after"] is not None, "RUNTIME_OBSERVATION_UNQUALIFIED")
    _require(observation["generation_before"] == observation["generation_after"], "SOURCE_CHANGED_DURING_READ")
    _require(observation["observed_at"] <= now <= observation["valid_until"], "STALE_OR_FUTURE_SNAPSHOT")
    _require(facts["runtime"]["root_status"] != "UNAVAILABLE"
             and facts["runtime"]["attempt_status"] != "UNAVAILABLE", "RUNTIME_STATUS_UNAVAILABLE")


def _same_original(saved: dict, current: dict) -> None:
    for key in ("role", "profile_sha256", "session_sha256", "principal_sha256"):
        _require(saved["native"][key] == current["native"][key], "FOREIGN_NATIVE_SCOPE")
    _require(saved["source"] == current["source"], "SOURCE_REVISION_CHANGED")
    # Runtime observation source_identity is request-scoped. Its data_version
    # counters are comparable only inside that namespace, never across restart
    # or a fresh owner read. Persistent joins use the original request/binding.
    _require(saved["authority"]["principal_sha256"] == current["authority"]["principal_sha256"],
             "FOREIGN_PRINCIPAL")
    _require(saved["authority"]["generation"] == current["authority"]["generation"],
             "AUTHORITY_GENERATION_CHANGED")
    for key in ("root_id", "root_job_id", "work_ref", "job_id", "attempt_id", "parent_job_id"):
        _require(saved["runtime"][key] == current["runtime"][key], "ORIGINAL_RUNTIME_IDENTITY_CHANGED")
    mutable = {"commit_status", "admission_id", "admission_sequence", "admission_epoch",
               "admission_generation", "admission_status"}
    for key in _SHAPES["original"] - mutable:
        _require(saved["original"][key] == current["original"][key], "ORIGINAL_REQUEST_CHANGED")
    for key in ("admission_id", "admission_sequence", "admission_epoch", "admission_generation"):
        if saved["original"][key] is not None:
            _require(saved["original"][key] == current["original"][key], "ORIGINAL_ADMISSION_CHANGED")
    if saved["original"]["commit_status"] == "COMMITTED":
        _require(current["original"]["commit_status"] == "COMMITTED", "ORIGINAL_COMMIT_LOST")
    if saved["original"]["admission_status"] == "terminal":
        _require(current["original"]["admission_status"] == "terminal", "ORIGINAL_ADMISSION_REGRESSED")
    if saved["return"]["result_status"] == "RETAINED":
        _require(current["return"]["result_status"] != "PENDING", "ORIGINAL_RESULT_REGRESSED")
    if saved["return"]["result_status"] == "RETAINED" and current["return"]["result_status"] == "RETAINED":
        _require(all(saved["return"][k] == current["return"][k] for k in
                     ("result_ref", "result_sha256", "result_outcome")), "ORIGINAL_RESULT_CHANGED")
    for reference, digest in (("parent_terminal_ref", "parent_terminal_sha256"),):
        if saved["return"][reference] is not None and current["return"][reference] is not None:
            _require(all(saved["return"][k] == current["return"][k] for k in (reference, digest)),
                     "PARENT_RETURN_CHANGED")
    if saved["return"]["consumption_status"] == "CONSUMED":
        _require(current["return"]["consumption_status"] == "CONSUMED"
                 and saved["return"]["consumption_ref"] == current["return"]["consumption_ref"],
                 "PARENT_CONSUMPTION_REGRESSED")


def project_recovery(checkpoint, *, expected_sha256: str, before: dict,
                     after: dict, now: int) -> RecoveryProjection:
    """Compare bracketing owner reads and select original-only read or refusal.

    The host obtains original admission and Runtime evidence on the SAME read
    carrier, then rechecks principal/source/authority generations after acquisition.
    Both snapshots are inputs, not authority minted by this function. It invokes
    no reader, writer, prompt, callback, provider, retry or state transition.
    """
    try:
        _number(now)
        saved = validate_checkpoint(checkpoint, expected_sha256=expected_sha256).as_dict()["facts"]
        first, last = _validate_facts(before), _validate_facts(after)
        _current(first, now)
        _current(last, now)
        _same_original(saved, first)
        _same_original(saved, last)
        _require(first["observation"]["observed_at"] <= last["observation"]["observed_at"],
                 "UNORDERED_READ_BRACKET")
        if first["observation"]["source_identity"] == last["observation"]["source_identity"]:
            _require(first["observation"]["generation_after"] == last["observation"]["generation_before"],
                     "SOURCE_CHANGED_WITHIN_OBSERVATION")
        _require(all(first[k] == last[k] for k in _SHAPES if k != "observation")
                 and first["observation"]["write_uncertainty"] == last["observation"]["write_uncertainty"],
                 "OWNER_FACTS_CHANGED_BETWEEN_READS")
        old, native = saved["native"], last["native"]
        # Original-only reads intentionally have no live-target or writer-lease
        # dependency. If current target evidence is available, stale evidence
        # fails; its absence is explicit and never permits session adoption.
        restarted = None
        if old["authority_epoch"] is not None and native["authority_epoch"] is not None:
            _require(native["authority_epoch"] >= old["authority_epoch"], "STALE_NATIVE_EPOCH")
            restarted = native["authority_epoch"] > old["authority_epoch"]
            _require((old["instance_sha256"] != native["instance_sha256"]) == restarted,
                     "NATIVE_EPOCH_INSTANCE_CONFLICT")
            _require(native["revision"] >= old["revision"]
                     and native["execution_generation"] >= old["execution_generation"],
                     "STALE_NATIVE_GENERATION")
        old_compaction, new_compaction = (item["context"]["compaction_generation"] for item in (saved, last))
        compacted = None
        if old_compaction is not None and new_compaction is not None:
            _require(new_compaction >= old_compaction, "STALE_CONTEXT_GENERATION")
            compacted = new_compaction > old_compaction
            if not compacted:
                _require(saved["context"] == last["context"], "CONTEXT_REFERENCE_CHANGED")

        original, returned = last["original"], last["return"]
        evidence = dict(read_ref=original["read_ref"], request_ref=original["request_ref"],
            operation_key=original["operation_key"], attempt_id=last["runtime"]["attempt_id"],
            result_ref=returned["result_ref"], result_sha256=returned["result_sha256"],
            parent_terminal_ref=returned["parent_terminal_ref"],
            consumption_status=returned["consumption_status"],
            executive_acceptance=returned["executive_acceptance"],
            gateway_restarted=restarted, context_compacted=compacted)
        if last["observation"]["write_uncertainty"] != "NONE":
            return RecoveryProjection("RECONCILE_ORIGINAL", "WRITE_EFFECT_UNCERTAIN", **evidence)
        if last["authority"]["approval_status"] != "CURRENT":
            evidence["read_ref"] = None
            return RecoveryProjection("EVIDENCE_ONLY", "EXECUTION_APPROVAL_NOT_CURRENT", **evidence)
        if last["runtime"]["root_status"] in {"CANCEL_REQUESTED", "CANCELLED"}:
            evidence["read_ref"] = None
            return RecoveryProjection("EVIDENCE_ONLY", "ROOT_CANCELLED", **evidence)
        if last["runtime"]["attempt_status"] in {"CANCEL_REQUESTED", "CANCELLED"}:
            evidence["read_ref"] = None
            return RecoveryProjection("EVIDENCE_ONLY", "ATTEMPT_CANCELLED", **evidence)
        if original["commit_status"] != "COMMITTED":
            return RecoveryProjection("RECONCILE_ORIGINAL", "ORIGINAL_COMMIT_UNPROVEN", **evidence)
        if original["kind"] == "HERMES_SECRETARY" and original["admission_status"] in {None, "unknown"}:
            return RecoveryProjection("RECONCILE_ORIGINAL", "ORIGINAL_ADMISSION_UNPROVEN", **evidence)
        if returned["result_status"] == "RETAINED":
            if returned["consumption_status"] == "CONSUMED":
                return RecoveryProjection("ALREADY_CONSUMED", "ORIGINAL_PARENT_RECEIPT", **evidence)
            return RecoveryProjection("RECOVER_ORIGINAL_RESULT", "ORIGINAL_RESULT_RETAINED", **evidence)
        if returned["result_status"] == "PENDING":
            return RecoveryProjection("AWAIT_ORIGINAL_RESULT", "ORIGINAL_PENDING", **evidence)
        return RecoveryProjection("EVIDENCE_ONLY", "RETAINED_RESULT_UNAVAILABLE", **evidence)
    except CheckpointError as exc:
        return RecoveryProjection("REFUSED", exc.code)
