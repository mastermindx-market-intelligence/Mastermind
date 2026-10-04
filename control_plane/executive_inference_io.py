"""Pure I/O contracts for one direct VPS inference Attempt.

No Runtime access, filesystem I/O, lifecycle, routing, credentials, retries, or
provider selection live here. Existing Executive owners may consume these
closed contracts when the direct service lane is composed.
"""
from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping

from common.executive_workspace_contract import _check_attempt_id, _check_job_id

REQUEST_SCHEMA = "mastermind.executive_service_inference_request.v1"
WORKER_RESULT_SCHEMA = "mastermind.executive_service_inference_worker_result.v1"
RESULT_REF_SCHEMA = "mastermind.executive_service_inference_result_ref.v1"
RESULT_DOCUMENT_SCHEMA = "mastermind.executive_service_inference_result_document.v1"
CONSTRAINT_KEY = "service_inference_request"

MAX_REQUEST_BYTES = 48 * 1024
MAX_OUTPUT_CHARS = 128 * 1024
MAX_RESULT_BYTES = 192 * 1024

_WORKER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class InferenceIOError(ValueError):
    """One pure service-inference I/O document is invalid."""
def canonical_bytes(value) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise InferenceIOError("inference document is not canonical JSON") from exc


def _text(value, field: str, *, empty: bool = False) -> str:
    if not isinstance(value, str):
        raise InferenceIOError(f"{field} must be a string")
    if "\x00" in value:
        raise InferenceIOError(f"{field} contains NUL")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise InferenceIOError(f"{field} is not valid UTF-8 text") from exc
    if not empty and not value.strip():
        raise InferenceIOError(f"{field} must not be empty")
    return value


def normalize_request(value: Mapping) -> dict:
    if not isinstance(value, Mapping) or set(value) != {
        "schema", "system_prompt", "input_text", "max_output_chars"
    }:
        raise InferenceIOError("inference request shape is invalid")
    if value["schema"] != REQUEST_SCHEMA:
        raise InferenceIOError("inference request schema is invalid")
    maximum = value["max_output_chars"]
    if type(maximum) is not int or not 1 <= maximum <= MAX_OUTPUT_CHARS:
        raise InferenceIOError("max_output_chars is outside the bounded range")
    normalized = {
        "schema": REQUEST_SCHEMA,
        "system_prompt": _text(value["system_prompt"], "system_prompt", empty=True),
        "input_text": _text(value["input_text"], "input_text"),
        "max_output_chars": maximum,
    }
    if len(canonical_bytes(normalized)) > MAX_REQUEST_BYTES:
        raise InferenceIOError("inference request exceeds the canonical byte ceiling")
    return normalized
def worker_result_schema(*, job_id: str, run_id: str, worker_id: str,
                         max_output_chars: int) -> dict:
    _identity(job_id, run_id, worker_id)
    if type(max_output_chars) is not int or not 1 <= max_output_chars <= MAX_OUTPUT_CHARS:
        raise InferenceIOError("max_output_chars is outside the bounded range")
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "job_id", "run_id", "worker_id", "status", "answer"],
        "properties": {
            "schema_version": {"const": WORKER_RESULT_SCHEMA},
            "job_id": {"const": job_id},
            "run_id": {"const": run_id},
            "worker_id": {"const": worker_id},
            "status": {"const": "COMPLETED"},
            "answer": {"type": "string", "minLength": 1, "maxLength": max_output_chars},
        },
    }


def _identity(job_id: str, run_id: str, worker_id: str) -> None:
    if not _check_job_id(job_id):
        raise InferenceIOError("job_id is invalid")
    if not _check_attempt_id(run_id):
        raise InferenceIOError("run_id is invalid")
    if not isinstance(worker_id, str) or _WORKER_ID_RE.fullmatch(worker_id) is None:
        raise InferenceIOError("worker_id is invalid")


def validate_worker_result(value: Mapping, *, job_id: str, run_id: str,
                           worker_id: str, max_output_chars: int) -> dict:
    _identity(job_id, run_id, worker_id)
    if type(max_output_chars) is not int or not 1 <= max_output_chars <= MAX_OUTPUT_CHARS:
        raise InferenceIOError("max_output_chars is outside the bounded range")
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version", "job_id", "run_id", "worker_id", "status", "answer"
    }:
        raise InferenceIOError("worker inference result shape is invalid")
    if (value["schema_version"] != WORKER_RESULT_SCHEMA
            or value["job_id"] != job_id or value["run_id"] != run_id
            or value["worker_id"] != worker_id or value["status"] != "COMPLETED"):
        raise InferenceIOError("worker inference result identity is invalid")
    answer = _text(value["answer"], "answer")
    if len(answer) > max_output_chars:
        raise InferenceIOError("worker inference answer exceeds its requested ceiling")
    normalized = dict(value, answer=answer)
    if len(canonical_bytes(normalized)) > MAX_RESULT_BYTES:
        raise InferenceIOError("worker inference result exceeds the byte ceiling")
    return copy.deepcopy(normalized)
def result_reference(*, job_id: str, attempt_id: str, worker_id: str,
                     result_sha256: str) -> dict:
    _identity(job_id, attempt_id, worker_id)
    if not isinstance(result_sha256, str) or _SHA256_RE.fullmatch(result_sha256) is None:
        raise InferenceIOError("result_sha256 is invalid")
    return {
        "schema": RESULT_REF_SCHEMA,
        "job_id": job_id,
        "attempt_id": attempt_id,
        "worker_id": worker_id,
        "result_sha256": result_sha256,
    }


def validate_result_reference(value: Mapping, *, job_id: str) -> dict:
    if not isinstance(value, Mapping) or set(value) != {
        "schema", "job_id", "attempt_id", "worker_id", "result_sha256"
    }:
        raise InferenceIOError("direct inference result reference shape is invalid")
    if value["schema"] != RESULT_REF_SCHEMA or value["job_id"] != job_id:
        raise InferenceIOError("direct inference result reference belongs to another job")
    return result_reference(
        job_id=value["job_id"], attempt_id=value["attempt_id"],
        worker_id=value["worker_id"], result_sha256=value["result_sha256"],
    )


def result_document(*, reference: Mapping, result: Mapping,
                    max_output_chars: int, raw_result_sha256: str) -> dict:
    if not isinstance(reference, Mapping):
        raise InferenceIOError("direct inference result reference shape is invalid")
    ref = validate_result_reference(reference, job_id=reference.get("job_id"))
    if raw_result_sha256 != ref["result_sha256"]:
        raise InferenceIOError("raw result digest disagrees with its reference")
    output = validate_worker_result(
        result, job_id=ref["job_id"], run_id=ref["attempt_id"],
        worker_id=ref["worker_id"], max_output_chars=max_output_chars,
    )
    document = {"schema": RESULT_DOCUMENT_SCHEMA, "reference": ref, "result": output}
    if len(canonical_bytes(document)) > MAX_RESULT_BYTES:
        raise InferenceIOError("result document exceeds the byte ceiling")
    return copy.deepcopy(document)


def validate_result_document(value: Mapping, *, job_id: str,
                             max_output_chars: int) -> dict:
    if not isinstance(value, Mapping) or set(value) != {"schema", "reference", "result"}:
        raise InferenceIOError("result document shape is invalid")
    if value["schema"] != RESULT_DOCUMENT_SCHEMA:
        raise InferenceIOError("result document schema is invalid")
    ref = validate_result_reference(value["reference"], job_id=job_id)
    output = validate_worker_result(
        value["result"], job_id=job_id, run_id=ref["attempt_id"],
        worker_id=ref["worker_id"], max_output_chars=max_output_chars,
    )
    document = {"schema": RESULT_DOCUMENT_SCHEMA, "reference": ref, "result": output}
    if len(canonical_bytes(document)) > MAX_RESULT_BYTES:
        raise InferenceIOError("result document exceeds the byte ceiling")
    return copy.deepcopy(document)


__all__ = [
    "REQUEST_SCHEMA", "WORKER_RESULT_SCHEMA", "RESULT_REF_SCHEMA",
    "RESULT_DOCUMENT_SCHEMA", "CONSTRAINT_KEY", "MAX_REQUEST_BYTES",
    "MAX_OUTPUT_CHARS", "MAX_RESULT_BYTES", "InferenceIOError",
    "canonical_bytes", "normalize_request", "worker_result_schema",
    "validate_worker_result", "result_reference", "validate_result_reference",
    "result_document", "validate_result_document",
]
