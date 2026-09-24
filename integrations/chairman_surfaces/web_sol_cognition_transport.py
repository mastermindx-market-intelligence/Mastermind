"""Closed, production-inert wire contract for Web-Sol cognition transport.

This module owns no browser, native host, Runtime lifecycle, retry, persistence,
placement, result store, or provider action. It only validates the bounded payloads
that a later accepted Web-Sol transport action may carry.

The assignment/result source owners remain authoritative:
- mastermind.web_sol_cognition_assignment/v1 is produced by the assignment owner;
- mastermind.executive_orchestration_result/v1 is reduced/validated by the result owner.

R1 transport integration must wrap these payloads inside the incumbent Web-Sol
surface action/receipt envelope. This module intentionally does not extend that
enumeration while #836 remains under independent review.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any, Final

from common.commission_ref import CommissionRefError, normalize_commission_ref


ASSIGNMENT_SCHEMA: Final[str] = "mastermind.web_sol_cognition_assignment/v1"
ORCHESTRATION_RESULT_SCHEMA: Final[str] = (
    "mastermind.executive_orchestration_result/v1"
)
SUBMIT_PAYLOAD_SCHEMA: Final[str] = (
    "mastermind.web_sol_cognition_submit_payload/v1"
)
OBSERVE_PAYLOAD_SCHEMA: Final[str] = (
    "mastermind.web_sol_cognition_result_observe_payload/v1"
)
RESULT_OBSERVATION_SCHEMA: Final[str] = (
    "mastermind.web_sol_cognition_result_observation/v1"
)

MAX_ASSIGNMENT_BYTES: Final[int] = 22 * 1024
MAX_RESULT_BYTES: Final[int] = 24 * 1024
MAX_TRANSPORT_PAYLOAD_BYTES: Final[int] = 48 * 1024

_SUPPORTED_ROLES = frozenset({"work", "review"})
_ASSIGNMENT_KEYS = frozenset(
    {
        "continuation",
        "continuation_digest",
        "effect_contract",
        "job",
        "result_contract",
        "schema_version",
        "source",
    }
)
_JOB_KEYS = frozenset(
    {
        "attempt_id",
        "job_id",
        "objective",
        "plan_attempt_id",
        "plan_digest",
        "plan_step_id",
        "quota_class",
        "repair_round",
        "review_required",
        "reviews_job_id",
        "role",
        "root_job_id",
        "worker_id",
    }
)
_EFFECT_KEYS = frozenset(
    {
        "allowed_write_paths",
        "external_effects_allowed",
        "requested_authorities",
    }
)
_RESULT_CONTRACT_KEYS = frozenset({"schema", "schema_digest"})
_SOURCE_KEYS = frozenset(
    {"work_ref", "commission_ref", "dialogue_source_digest"}
)
_IDENTITY_KEYS = frozenset(
    {
        "turn_id",
        "assignment_digest",
        "result_schema_digest",
        "runtime_binding_id",
        "runtime_binding_generation",
        "runtime_binding_fingerprint",
        "job_id",
        "attempt_id",
        "worker_id",
        "root_job_id",
        "role",
    }
)
_SUBMIT_KEYS = _IDENTITY_KEYS | frozenset({"schema", "assignment"})
_OBSERVE_KEYS = _IDENTITY_KEYS | frozenset({"schema"})
_RESULT_OBSERVATION_KEYS = _IDENTITY_KEYS | frozenset(
    {
        "schema",
        "status",
        "document_epoch",
        "provider_native_turn_id",
        "provider_turn_artifact_digest",
        "result",
        "result_digest",
        "result_byte_length",
    }
)
_RESULT_KEYS = frozenset(
    {
        "schema_version",
        "job_id",
        "run_id",
        "worker_id",
        "role",
        "status",
        "role_result",
        "summary",
        "current_state",
        "next_actions",
        "errors",
        "validations",
    }
)
_PRIVATE_FIELD_NAMES = frozenset(
    {
        "transcript",
        "raw_transcript",
        "raw_context",
        "raw_dom",
        "cookie",
        "cookies",
        "storage",
        "clipboard",
        "selector",
        "script",
        "coordinates",
        "shell",
        "argv",
        "url",
        "account",
        "profile_id",
        "folder_id",
    }
)

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
_HEX32_RE = re.compile(r"^[0-9a-f]{32}$")
_RUNTIME_BINDING_ID_RE = re.compile(r"^bind-wsx-[0-9a-f]{48}$")
_ENTITY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TURN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,255}$")
_BOUNDED_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


class WebSolCognitionTransportError(ValueError):
    """One cognition wire payload violated the closed transport contract."""


def _error(path: str, message: str) -> WebSolCognitionTransportError:
    return WebSolCognitionTransportError(f"{path}: {message}")


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise _error("$", "must be canonical JSON compatible") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _exact(value: Any, keys: frozenset[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error(path, "must be an object")
    actual = set(value)
    missing = keys - actual
    extra = actual - keys
    if missing:
        raise _error(path, f"missing keys: {', '.join(sorted(missing))}")
    if extra:
        raise _error(path, f"unknown keys: {', '.join(sorted(str(x) for x in extra))}")
    return value


def _walk_private_fields(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise _error(path, "object keys must be strings")
            child_path = f"{path}.{key}"
            if key.lower() in _PRIVATE_FIELD_NAMES:
                raise _error(child_path, f"forbidden private field {key!r}")
            _walk_private_fields(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_private_fields(child, f"{path}[{index}]")


def _hex64(value: Any, path: str) -> str:
    if not isinstance(value, str) or _HEX64_RE.fullmatch(value) is None:
        raise _error(path, "must be 64 lowercase hexadecimal characters")
    return value


def _entity_id(value: Any, path: str) -> str:
    if not isinstance(value, str) or _ENTITY_ID_RE.fullmatch(value) is None:
        raise _error(path, "must be a canonical bounded entity identity")
    return value


def _turn_id(value: Any, path: str) -> str:
    if not isinstance(value, str) or _TURN_ID_RE.fullmatch(value) is None:
        raise _error(path, "must be a bounded provider/turn identity")
    return value


def _bounded_token(value: Any, path: str) -> str:
    if not isinstance(value, str) or _BOUNDED_TOKEN_RE.fullmatch(value) is None:
        raise _error(path, "must be a bounded token")
    return value


def _binding_id(value: Any, path: str) -> str:
    if not isinstance(value, str) or _RUNTIME_BINDING_ID_RE.fullmatch(value) is None:
        raise _error(path, "must be a canonical Web-Sol RuntimeBinding identity")
    return value


def _binding_generation(value: Any, path: str) -> int:
    if type(value) is not int or not 1 <= value <= 9007199254740991:
        raise _error(path, "must be a positive safe integer")
    return value


def _role(value: Any, path: str) -> str:
    if value not in _SUPPORTED_ROLES:
        raise _error(path, "must be work or review")
    return str(value)


def _optional_entity(value: Any, path: str) -> None:
    if value is not None:
        _entity_id(value, path)


def _validate_result_schema_identity(
    schema: Any,
    *,
    job_id: str,
    attempt_id: str,
    worker_id: str,
    root_job_id: str,
    role: str,
) -> None:
    if not isinstance(schema, dict):
        raise _error("$.assignment.result_contract.schema", "must be an object")
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise _error(
            "$.assignment.result_contract.schema.properties",
            "must be an object",
        )
    expected = {
        "job_id": job_id,
        "run_id": attempt_id,
        "worker_id": worker_id,
        "role": role,
    }
    for field, identity in expected.items():
        node = properties.get(field)
        if not isinstance(node, dict) or node.get("const") != identity:
            raise _error(
                f"$.assignment.result_contract.schema.properties.{field}",
                f"must bind {field} to the exact assignment identity",
            )
    role_result = properties.get("role_result")
    role_properties = (
        role_result.get("properties")
        if isinstance(role_result, dict)
        else None
    )
    root = (
        role_properties.get("root_job_id")
        if isinstance(role_properties, dict)
        else None
    )
    if not isinstance(root, dict) or root.get("const") != root_job_id:
        raise _error(
            "$.assignment.result_contract.schema.properties.role_result."
            "properties.root_job_id",
            "must bind root_job_id to the exact assignment root",
        )


def _validate_assignment(
    assignment: Any,
    *,
    job_id: str,
    attempt_id: str,
    worker_id: str,
    root_job_id: str,
    role: str,
) -> dict[str, Any]:
    value = _exact(assignment, _ASSIGNMENT_KEYS, "$.assignment")
    _walk_private_fields(value, "$.assignment")
    if value["schema_version"] != ASSIGNMENT_SCHEMA:
        raise _error(
            "$.assignment.schema_version",
            f"must equal {ASSIGNMENT_SCHEMA!r}",
        )

    continuation = value["continuation"]
    if not isinstance(continuation, dict):
        raise _error("$.assignment.continuation", "must be an object")
    _hex64(value["continuation_digest"], "$.assignment.continuation_digest")
    if value["continuation_digest"] != _digest(continuation):
        raise _error(
            "$.assignment.continuation_digest",
            "must match the canonical continuation document",
        )

    effect = _exact(
        value["effect_contract"],
        _EFFECT_KEYS,
        "$.assignment.effect_contract",
    )
    if effect["external_effects_allowed"] is not False:
        raise _error(
            "$.assignment.effect_contract.external_effects_allowed",
            "must be false",
        )
    if effect["allowed_write_paths"] != []:
        raise _error(
            "$.assignment.effect_contract.allowed_write_paths",
            "must be empty",
        )
    authorities = effect["requested_authorities"]
    allowed = (
        (["READ"], ["READ", "RESEARCH"])
        if role == "work"
        else (["READ"],)
    )
    if authorities not in allowed:
        raise _error(
            "$.assignment.effect_contract.requested_authorities",
            "does not match the effect-free role contract",
        )

    job = _exact(value["job"], _JOB_KEYS, "$.assignment.job")
    for field, expected in (
        ("job_id", job_id),
        ("attempt_id", attempt_id),
        ("worker_id", worker_id),
        ("root_job_id", root_job_id),
        ("role", role),
    ):
        if job[field] != expected:
            raise _error(
                f"$.assignment.job.{field}",
                f"must equal the exact {field}",
            )
    if not isinstance(job["objective"], str) or not job["objective"].strip():
        raise _error("$.assignment.job.objective", "must be non-empty text")
    _optional_entity(job["plan_attempt_id"], "$.assignment.job.plan_attempt_id")
    if job["plan_digest"] is not None:
        _hex64(job["plan_digest"], "$.assignment.job.plan_digest")
    _optional_entity(job["plan_step_id"], "$.assignment.job.plan_step_id")
    _bounded_token(job["quota_class"], "$.assignment.job.quota_class")
    if type(job["repair_round"]) is not int or job["repair_round"] < 0:
        raise _error("$.assignment.job.repair_round", "must be a non-negative integer")
    if type(job["review_required"]) is not bool:
        raise _error("$.assignment.job.review_required", "must be boolean")
    _optional_entity(job["reviews_job_id"], "$.assignment.job.reviews_job_id")

    result_contract = _exact(
        value["result_contract"],
        _RESULT_CONTRACT_KEYS,
        "$.assignment.result_contract",
    )
    _hex64(
        result_contract["schema_digest"],
        "$.assignment.result_contract.schema_digest",
    )
    if result_contract["schema_digest"] != _digest(result_contract["schema"]):
        raise _error(
            "$.assignment.result_contract.schema_digest",
            "must match the canonical result schema",
        )
    _validate_result_schema_identity(
        result_contract["schema"],
        job_id=job_id,
        attempt_id=attempt_id,
        worker_id=worker_id,
        root_job_id=root_job_id,
        role=role,
    )

    source = _exact(value["source"], _SOURCE_KEYS, "$.assignment.source")
    _bounded_token(source["work_ref"], "$.assignment.source.work_ref")
    _hex64(
        source["dialogue_source_digest"],
        "$.assignment.source.dialogue_source_digest",
    )
    try:
        normalize_commission_ref(source["commission_ref"])
    except CommissionRefError as exc:
        raise _error(
            "$.assignment.source.commission_ref",
            "commission_ref is invalid",
        ) from exc

    size = len(_canonical_bytes(value))
    if size > MAX_ASSIGNMENT_BYTES:
        raise _error(
            "$.assignment",
            f"assignment exceeds {MAX_ASSIGNMENT_BYTES} UTF-8 bytes",
        )
    return copy.deepcopy(value)


def _validate_identity(value: dict[str, Any], *, path: str = "$") -> None:
    _turn_id(value["turn_id"], f"{path}.turn_id")
    _hex64(value["assignment_digest"], f"{path}.assignment_digest")
    _hex64(value["result_schema_digest"], f"{path}.result_schema_digest")
    _binding_id(value["runtime_binding_id"], f"{path}.runtime_binding_id")
    _binding_generation(
        value["runtime_binding_generation"],
        f"{path}.runtime_binding_generation",
    )
    _hex64(
        value["runtime_binding_fingerprint"],
        f"{path}.runtime_binding_fingerprint",
    )
    for field in ("job_id", "attempt_id", "worker_id", "root_job_id"):
        _entity_id(value[field], f"{path}.{field}")
    _role(value["role"], f"{path}.role")


def _ensure_transport_budget(value: object, path: str = "$") -> None:
    size = len(_canonical_bytes(value))
    if size > MAX_TRANSPORT_PAYLOAD_BYTES:
        raise _error(
            path,
            f"payload exceeds {MAX_TRANSPORT_PAYLOAD_BYTES} UTF-8 bytes",
        )


def build_assignment_submit_payload(
    *,
    assignment: dict[str, Any],
    turn_id: str,
    runtime_binding_id: str,
    runtime_binding_generation: int,
    runtime_binding_fingerprint: str,
    job_id: str,
    attempt_id: str,
    worker_id: str,
    root_job_id: str,
    role: str,
) -> dict[str, Any]:
    """Build one closed inner payload for a future assignment-submit action."""

    accepted_role = _role(role, "$.role")
    accepted_assignment = _validate_assignment(
        assignment,
        job_id=job_id,
        attempt_id=attempt_id,
        worker_id=worker_id,
        root_job_id=root_job_id,
        role=accepted_role,
    )
    payload = {
        "schema": SUBMIT_PAYLOAD_SCHEMA,
        "assignment": accepted_assignment,
        "turn_id": turn_id,
        "assignment_digest": _digest(accepted_assignment),
        "result_schema_digest": accepted_assignment["result_contract"][
            "schema_digest"
        ],
        "runtime_binding_id": runtime_binding_id,
        "runtime_binding_generation": runtime_binding_generation,
        "runtime_binding_fingerprint": runtime_binding_fingerprint,
        "job_id": job_id,
        "attempt_id": attempt_id,
        "worker_id": worker_id,
        "root_job_id": root_job_id,
        "role": accepted_role,
    }
    return validate_assignment_submit_payload(payload)


def validate_assignment_submit_payload(value: Any) -> dict[str, Any]:
    """Validate and detach one closed assignment-submit inner payload."""

    payload = _exact(value, _SUBMIT_KEYS, "$")
    if payload["schema"] != SUBMIT_PAYLOAD_SCHEMA:
        raise _error("$.schema", f"must equal {SUBMIT_PAYLOAD_SCHEMA!r}")
    _validate_identity(payload)
    assignment = _validate_assignment(
        payload["assignment"],
        job_id=payload["job_id"],
        attempt_id=payload["attempt_id"],
        worker_id=payload["worker_id"],
        root_job_id=payload["root_job_id"],
        role=payload["role"],
    )
    if payload["assignment_digest"] != _digest(assignment):
        raise _error(
            "$.assignment_digest",
            "must match the canonical assignment document",
        )
    if (
        payload["result_schema_digest"]
        != assignment["result_contract"]["schema_digest"]
    ):
        raise _error(
            "$.result_schema_digest",
            "must match the assignment result contract",
        )
    _ensure_transport_budget(payload)
    return copy.deepcopy(payload)


def build_result_observe_payload(
    *,
    turn_id: str,
    assignment_digest: str,
    result_schema_digest: str,
    runtime_binding_id: str,
    runtime_binding_generation: int,
    runtime_binding_fingerprint: str,
    job_id: str,
    attempt_id: str,
    worker_id: str,
    root_job_id: str,
    role: str,
) -> dict[str, Any]:
    """Build one read-only exact-result observation inner payload."""

    payload = {
        "schema": OBSERVE_PAYLOAD_SCHEMA,
        "turn_id": turn_id,
        "assignment_digest": assignment_digest,
        "result_schema_digest": result_schema_digest,
        "runtime_binding_id": runtime_binding_id,
        "runtime_binding_generation": runtime_binding_generation,
        "runtime_binding_fingerprint": runtime_binding_fingerprint,
        "job_id": job_id,
        "attempt_id": attempt_id,
        "worker_id": worker_id,
        "root_job_id": root_job_id,
        "role": role,
    }
    return validate_result_observe_payload(payload)


def validate_result_observe_payload(value: Any) -> dict[str, Any]:
    """Validate and detach one read-only result observation inner payload."""

    payload = _exact(value, _OBSERVE_KEYS, "$")
    if payload["schema"] != OBSERVE_PAYLOAD_SCHEMA:
        raise _error("$.schema", f"must equal {OBSERVE_PAYLOAD_SCHEMA!r}")
    _validate_identity(payload)
    _ensure_transport_budget(payload)
    return copy.deepcopy(payload)


def _validate_result_identity(value: dict[str, Any]) -> None:
    if value["schema_version"] != ORCHESTRATION_RESULT_SCHEMA:
        raise _error(
            "$.result.schema_version",
            f"must equal {ORCHESTRATION_RESULT_SCHEMA!r}",
        )
    for field, expected in (
        ("job_id", value["_expected_job_id"]),
        ("run_id", value["_expected_attempt_id"]),
        ("worker_id", value["_expected_worker_id"]),
        ("role", value["_expected_role"]),
    ):
        if value[field] != expected:
            raise _error(f"$.result.{field}", f"must equal the exact {field}")
    if value["status"] != "COMPLETED":
        raise _error("$.result.status", "must equal COMPLETED")
    if value["validations"] != []:
        raise _error("$.result.validations", "must be empty at provider boundary")
    if not isinstance(value["role_result"], dict):
        raise _error("$.result.role_result", "must be an object")
    if value["role_result"].get("root_job_id") != value["_expected_root_job_id"]:
        raise _error(
            "$.result.role_result.root_job_id",
            "must equal the exact root_job_id",
        )


def validate_result_observation(value: Any) -> dict[str, Any]:
    """Validate one transient result observation emitted by the content reducer."""

    observation = _exact(value, _RESULT_OBSERVATION_KEYS, "$")
    if observation["schema"] != RESULT_OBSERVATION_SCHEMA:
        raise _error(
            "$.schema",
            f"must equal {RESULT_OBSERVATION_SCHEMA!r}",
        )
    _validate_identity(observation)

    if not isinstance(observation["document_epoch"], str) or _HEX32_RE.fullmatch(
        observation["document_epoch"]
    ) is None:
        raise _error("$.document_epoch", "must be 32 lowercase hexadecimal characters")

    status = observation["status"]
    if status not in {
        "COGNITION_RESULT_READY",
        "COGNITION_RESULT_PENDING",
        "COGNITION_RESULT_REFUSED",
    }:
        raise _error("$.status", "contains an unknown cognition result state")

    if status != "COGNITION_RESULT_READY":
        if (
            observation["provider_native_turn_id"] is not None
            or observation["provider_turn_artifact_digest"] is not None
            or observation["result"] is not None
            or observation["result_digest"] is not None
            or observation["result_byte_length"] != 0
        ):
            raise _error(
                "$",
                "non-ready observation must carry no provider/result content",
            )
        _ensure_transport_budget(observation)
        return copy.deepcopy(observation)

    _turn_id(
        observation["provider_native_turn_id"],
        "$.provider_native_turn_id",
    )
    _hex64(
        observation["provider_turn_artifact_digest"],
        "$.provider_turn_artifact_digest",
    )
    _hex64(observation["result_digest"], "$.result_digest")
    result = _exact(observation["result"], _RESULT_KEYS, "$.result")
    _walk_private_fields(result, "$.result")

    result_for_identity = dict(result)
    result_for_identity.update(
        {
            "_expected_job_id": observation["job_id"],
            "_expected_attempt_id": observation["attempt_id"],
            "_expected_worker_id": observation["worker_id"],
            "_expected_root_job_id": observation["root_job_id"],
            "_expected_role": observation["role"],
        }
    )
    _validate_result_identity(result_for_identity)

    encoded = _canonical_bytes(result)
    if len(encoded) > MAX_RESULT_BYTES:
        raise _error(
            "$.result",
            f"result exceeds {MAX_RESULT_BYTES} UTF-8 bytes",
        )
    if observation["result_byte_length"] != len(encoded):
        raise _error(
            "$.result_byte_length",
            "must equal the canonical UTF-8 result size",
        )
    if observation["result_digest"] != hashlib.sha256(encoded).hexdigest():
        raise _error(
            "$.result_digest",
            "must match the canonical result document",
        )
    _ensure_transport_budget(observation)
    return copy.deepcopy(observation)


__all__ = [
    "ASSIGNMENT_SCHEMA",
    "MAX_ASSIGNMENT_BYTES",
    "MAX_RESULT_BYTES",
    "MAX_TRANSPORT_PAYLOAD_BYTES",
    "OBSERVE_PAYLOAD_SCHEMA",
    "ORCHESTRATION_RESULT_SCHEMA",
    "RESULT_OBSERVATION_SCHEMA",
    "SUBMIT_PAYLOAD_SCHEMA",
    "WebSolCognitionTransportError",
    "build_assignment_submit_payload",
    "build_result_observe_payload",
    "validate_assignment_submit_payload",
    "validate_result_observation",
    "validate_result_observe_payload",
]
