"""Closed lossless Phase 1F-C orchestration result and raw observation wires.

Pure validation only: no provider calls, database writes, files, logs, or result
store.  The complete canonical envelope remains in memory until Runtime seals it
as immutable evidence.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import posixpath
import re
from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from scripts.ohf.redaction import evidence_contains_secret, redact_evidence


RESULT_SCHEMA = "mastermind.executive_orchestration_result/v1"
RAW_OBSERVATION_SCHEMA = "mastermind.operator_raw_role_result_observation/v1"
MAX_CANONICAL_RESULT_BYTES = 8_388_608
ROLES = frozenset({"plan", "work", "review", "repair", "aggregation"})
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_AUTHORITY_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,31}$")


class OrchestrationResultError(ValueError):
    """The result/observation is not the exact closed Phase 1F-C wire."""


def _schema_string(*, maximum: int = 8192, minimum: int = 0) -> dict[str, Any]:
    return {"type": "string", "minLength": minimum, "maxLength": maximum}


def _schema_identifier() -> dict[str, Any]:
    return {
        "type": "string",
        "minLength": 1,
        "maxLength": 128,
        "pattern": _ID_RE.pattern,
    }


def _schema_digest() -> dict[str, Any]:
    return {"type": "string", "pattern": _DIGEST_RE.pattern}


def _schema_array(
    items: Mapping[str, Any],
    *,
    minimum: int = 0,
    maximum: int = 64,
    unique: bool = False,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "type": "array",
        "items": dict(items),
        "minItems": minimum,
        "maxItems": maximum,
    }
    if unique:
        value["uniqueItems"] = True
    return value


def _schema_object(
    properties: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Return one closed object whose complete property set is required."""

    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": {name: dict(value) for name, value in properties.items()},
    }


def _lineage_schema_properties() -> dict[str, dict[str, Any]]:
    return {
        "root_job_id": _schema_identifier(),
        "plan_attempt_id": _schema_identifier(),
        "plan_digest": _schema_digest(),
        "plan_step_id": _schema_identifier(),
    }


def _role_body_schema(role: str) -> dict[str, Any]:
    """Executable JSON Schema 2020-12 body for one frozen role.

    Relational checks (for example, a review target matching the persisted
    current revision) remain Runtime-owned.  This constructor closes every
    syntactic object/array/discriminator boundary before provider output can be
    collected, and :func:`validate_envelope` repeats the full typed/relational
    checks before persistence.
    """

    if role not in ROLES:
        raise OrchestrationResultError("role is not in the closed orchestration set")
    text = _schema_string()
    digest = _schema_digest()
    identifier = _schema_identifier()
    evidence = _schema_array(digest, unique=True)
    artifact = _schema_object({"path": _schema_string(maximum=1024, minimum=1), "digest": digest})

    if role == "plan":
        step = _schema_object(
            {
                "ordinal": {"type": "integer", "minimum": 0, "maximum": 7},
                "step_id": identifier,
                "objective": _schema_string(minimum=1),
                "business_impact": {
                    "type": "string",
                    "enum": ["routine", "material", "critical"],
                },
                "review_required": {"type": "boolean"},
                "requested_authorities": _schema_array(
                    {"type": "string", "pattern": _AUTHORITY_RE.pattern},
                    minimum=1,
                    maximum=16,
                    unique=True,
                ),
                "allowed_write_paths": _schema_array(
                    _schema_string(maximum=1024, minimum=1),
                    maximum=32,
                    unique=True,
                ),
                "validation_ids": _schema_array(digest, unique=True),
                "attempt_limit": {"type": "integer", "minimum": 1, "maximum": 2},
                "cost_class": {"type": "string", "enum": ["default", "small"]},
            }
        )
        return _schema_object(
            {
                "schema_version": {"const": "mastermind.execution_plan/v1"},
                "root_job_id": identifier,
                "plan_attempt_id": identifier,
                "steps": _schema_array(step, minimum=1, maximum=8),
            }
        )

    if role in {"work", "repair"}:
        properties: dict[str, Mapping[str, Any]] = {
            "schema_version": {
                "const": (
                    "mastermind.repair_result/v1"
                    if role == "repair"
                    else "mastermind.work_result/v1"
                )
            },
            **_lineage_schema_properties(),
            "repair_round": {
                "const": 0
            }
            if role == "work"
            else {"type": "integer", "minimum": 1, "maximum": 2},
        }
        if role == "repair":
            properties.update(
                {
                    "supersedes_job_id": identifier,
                    "rejected_review_job_id": identifier,
                    "rejected_review_result_digest": digest,
                }
            )
        properties.update(
            {
                "artifacts": _schema_array(artifact, unique=True),
                "evidence_digests": evidence,
            }
        )
        return _schema_object(properties)

    if role == "review":
        finding = _schema_object(
            {
                "code": identifier,
                "severity": {
                    "type": "string",
                    "enum": ["info", "warning", "blocking"],
                },
                "message": text,
                "evidence_digests": evidence,
            }
        )
        return _schema_object(
            {
                "schema_version": {"const": "mastermind.review_result/v1"},
                **_lineage_schema_properties(),
                "reviewed_job_id": identifier,
                "reviewed_attempt_id": identifier,
                "reviewed_result_digest": digest,
                "repair_round": {"type": "integer", "minimum": 0, "maximum": 2},
                "verdict": {"type": "string", "enum": ["approve", "reject"]},
                "evidence_digests": evidence,
                "findings": _schema_array(finding, unique=True),
            }
        )

    nullable_identifier = {"oneOf": [identifier, {"type": "null"}]}
    nullable_digest = {"oneOf": [digest, {"type": "null"}]}
    revision = _schema_object(
        {
            "ordinal": {"type": "integer", "minimum": 0, "maximum": 7},
            "plan_step_id": identifier,
            "current_job_id": identifier,
            "current_attempt_id": identifier,
            "current_result_digest": digest,
            "repair_round": {"type": "integer", "minimum": 0, "maximum": 2},
            "review_required": {"type": "boolean"},
            "qualifying_review_job_id": nullable_identifier,
            "qualifying_review_attempt_id": nullable_identifier,
            "qualifying_review_result_digest": nullable_digest,
        }
    )
    return _schema_object(
        {
            "schema_version": {"const": "mastermind.aggregation_result/v1"},
            "root_job_id": identifier,
            "handoff_digest": digest,
            "policy_sha": digest,
            "plan_attempt_id": identifier,
            "plan_digest": digest,
            "revisions": _schema_array(revision, minimum=1, maximum=8),
            "aggregate_summary": text,
            "evidence_digests": evidence,
        }
    )


def orchestration_result_schema(
    role: str,
    *,
    job_id: str | None = None,
    run_id: str | None = None,
    worker_id: str | None = None,
    root_job_id: str | None = None,
) -> dict[str, Any]:
    """Return the closed executable envelope schema for ``role``.

    The unbound form is the stable golden schema.  The supervisor supplies the
    four optional constants so a provider cannot swap Job, Attempt, worker, or
    root identity while still satisfying the same role shape.
    """

    if role not in ROLES:
        raise OrchestrationResultError("role is not in the closed orchestration set")
    for name, value in {
        "job_id": job_id,
        "run_id": run_id,
        "worker_id": worker_id,
        "root_job_id": root_job_id,
    }.items():
        if value is not None:
            _identifier(value, name=name)

    def bound_identifier(value: str | None) -> dict[str, Any]:
        return {"const": value} if value is not None else _schema_identifier()

    role_body = _role_body_schema(role)
    if root_job_id is not None:
        role_body = json.loads(json.dumps(role_body))
        role_body["properties"]["root_job_id"] = {"const": root_job_id}
    envelope = _schema_object(
        {
            "schema_version": {"const": RESULT_SCHEMA},
            "job_id": bound_identifier(job_id),
            "run_id": bound_identifier(run_id),
            "worker_id": bound_identifier(worker_id),
            "role": {"const": role},
            "status": {"const": "COMPLETED"},
            "role_result": role_body,
            "summary": _schema_string(),
            "current_state": _schema_string(),
            "next_actions": _schema_array(_schema_string(), maximum=16, unique=True),
            "errors": _schema_array(_schema_string(), maximum=16, unique=True),
            "validations": {"type": "array", "maxItems": 0},
        }
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **envelope,
    }


def role_schema_digest(role: str) -> str:
    """Content identity of the unbound executable schema for one role."""

    return canonical_digest(orchestration_result_schema(role))


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise OrchestrationResultError("result is not canonical JSON data") from exc


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def parse_canonical_json(text: str) -> Any:
    if not isinstance(text, str) or not text or text.startswith("\ufeff"):
        raise OrchestrationResultError("canonical result must be non-empty BOM-free text")

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise ValueError("duplicate object key")
            result[key] = value
        return result

    try:
        parsed = json.loads(text, object_pairs_hook=pairs)
    except (TypeError, ValueError) as exc:
        raise OrchestrationResultError("canonical result is invalid JSON") from exc
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise OrchestrationResultError("canonical result is not UTF-8") from exc
    if len(encoded) > MAX_CANONICAL_RESULT_BYTES:
        raise OrchestrationResultError("canonical result exceeds 8 MiB")
    if canonical_bytes(parsed) != encoded:
        raise OrchestrationResultError("result text is not byte-for-byte canonical JSON")
    return parsed


def _closed(value: Any, *, name: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise OrchestrationResultError(f"{name} does not match its closed schema")
    return value


def _text(value: Any, *, name: str, maximum: int = 8192, nonempty: bool = False) -> str:
    if not isinstance(value, str) or "\x00" in value or len(value) > maximum:
        raise OrchestrationResultError(f"{name} must be UTF-8 text <= {maximum} characters")
    if nonempty and (not value or value != value.strip()):
        raise OrchestrationResultError(f"{name} must be non-empty canonical text")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise OrchestrationResultError(f"{name} is not UTF-8 text") from exc
    return value


def _identifier(value: Any, *, name: str) -> str:
    text = _text(value, name=name, maximum=128, nonempty=True)
    if _ID_RE.fullmatch(text) is None:
        raise OrchestrationResultError(f"{name} is not a canonical identifier")
    return text


def _digest(value: Any, *, name: str) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise OrchestrationResultError(f"{name} must be lowercase SHA-256")
    return value


def _integer(value: Any, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise OrchestrationResultError(f"{name} must be an integer {minimum}..{maximum}")
    return value


def _boolean(value: Any, *, name: str) -> bool:
    if not isinstance(value, bool):
        raise OrchestrationResultError(f"{name} must be a boolean")
    return value


def _array(value: Any, *, name: str, minimum: int = 0, maximum: int = 64) -> list[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, list):
        raise OrchestrationResultError(f"{name} must be an ordered array")
    if not minimum <= len(value) <= maximum:
        raise OrchestrationResultError(f"{name} must contain {minimum}..{maximum} items")
    return value


def _unique_strings(
    value: Any,
    *,
    name: str,
    maximum: int = 64,
    minimum: int = 0,
    validator=None,
) -> list[str]:
    items = _array(value, name=name, minimum=minimum, maximum=maximum)
    result: list[str] = []
    for index, item in enumerate(items):
        resolved = (
            validator(item, name=f"{name}[{index}]")
            if validator is not None
            else _text(item, name=f"{name}[{index}]", nonempty=True)
        )
        if resolved in result:
            raise OrchestrationResultError(f"{name} contains a duplicate item")
        result.append(resolved)
    return result


def _path(value: Any, *, name: str) -> str:
    path = _text(value, name=name, maximum=1024, nonempty=True)
    if (
        path.startswith("/")
        or "\\" in path
        or path in {".", "./"}
        or "//" in path
        or path != posixpath.normpath(path)
        or ".." in path.split("/")
        or (path != "/" and path.endswith("/"))
    ):
        raise OrchestrationResultError(f"{name} is not a canonical path")
    return path


def _artifacts(value: Any, *, name: str = "artifacts") -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for index, item in enumerate(_array(value, name=name)):
        raw = _closed(item, name=f"{name}[{index}]", keys={"path", "digest"})
        resolved = {
                "path": _path(raw["path"], name=f"{name}[{index}].path"),
                "digest": _digest(raw["digest"], name=f"{name}[{index}].digest"),
            }
        if resolved in result:
            raise OrchestrationResultError(f"{name} contains a duplicate object")
        result.append(resolved)
    return result


def _evidence(value: Any, *, name: str = "evidence_digests") -> list[str]:
    return _unique_strings(value, name=name, validator=_digest)


def _lineage(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "root_job_id": _identifier(raw["root_job_id"], name="root_job_id"),
        "plan_attempt_id": _identifier(raw["plan_attempt_id"], name="plan_attempt_id"),
        "plan_digest": _digest(raw["plan_digest"], name="plan_digest"),
        "plan_step_id": _identifier(raw["plan_step_id"], name="plan_step_id"),
    }


def _validate_plan(value: Any, *, outer: Mapping[str, Any]) -> dict[str, Any]:
    raw = _closed(
        value,
        name="plan role_result",
        keys={"schema_version", "root_job_id", "plan_attempt_id", "steps"},
    )
    if raw["schema_version"] != "mastermind.execution_plan/v1":
        raise OrchestrationResultError("unsupported plan schema")
    expected_root = outer.get("expected_root_job_id")
    if expected_root is None:
        raise OrchestrationResultError("plan validation requires expected_root_job_id")
    root_job_id = _identifier(raw["root_job_id"], name="root_job_id")
    if root_job_id != _identifier(expected_root, name="expected_root_job_id"):
        raise OrchestrationResultError("plan root_job_id mismatch")
    if raw["plan_attempt_id"] != outer["run_id"]:
        raise OrchestrationResultError("plan_attempt_id must equal outer run_id")
    steps: list[dict[str, Any]] = []
    step_ids: set[str] = set()
    for index, item in enumerate(_array(raw["steps"], name="steps", minimum=1, maximum=8)):
        step = _closed(
            item,
            name=f"steps[{index}]",
            keys={
                "ordinal", "step_id", "objective", "business_impact",
                "review_required", "requested_authorities", "allowed_write_paths",
                "validation_ids", "attempt_limit", "cost_class",
            },
        )
        if _integer(step["ordinal"], name="ordinal", minimum=0, maximum=7) != index:
            raise OrchestrationResultError("step ordinal must equal its array position")
        step_id = _identifier(step["step_id"], name="step_id")
        if step_id in step_ids:
            raise OrchestrationResultError("plan step_id values must be unique")
        step_ids.add(step_id)
        impact = step["business_impact"]
        if not isinstance(impact, str) or impact not in {"routine", "material", "critical"}:
            raise OrchestrationResultError("step business_impact is invalid")
        authorities = _unique_strings(
            step["requested_authorities"],
            name="requested_authorities",
            minimum=1,
            maximum=16,
            validator=lambda value, name: (
                str(value)
                if isinstance(value, str) and _AUTHORITY_RE.fullmatch(value)
                else (_ for _ in ()).throw(
                    OrchestrationResultError(f"{name} is not an authority")
                )
            ),
        )
        steps.append(
            {
                "ordinal": index,
                "step_id": step_id,
                "objective": _text(step["objective"], name="objective", nonempty=True),
                "business_impact": impact,
                "review_required": _boolean(step["review_required"], name="review_required"),
                "requested_authorities": authorities,
                "allowed_write_paths": _unique_strings(
                    step["allowed_write_paths"], name="allowed_write_paths", maximum=32,
                    validator=_path,
                ),
                "validation_ids": _unique_strings(
                    step["validation_ids"], name="validation_ids", validator=_digest
                ),
                "attempt_limit": _integer(
                    step["attempt_limit"], name="attempt_limit", minimum=1, maximum=2
                ),
                "cost_class": step["cost_class"],
            }
        )
        if not isinstance(step["cost_class"], str) or step["cost_class"] not in {"default", "small"}:
            raise OrchestrationResultError("step cost_class is invalid")
    return {
        "schema_version": "mastermind.execution_plan/v1",
        "root_job_id": root_job_id,
        "plan_attempt_id": raw["plan_attempt_id"],
        "steps": steps,
    }


def _validate_work(value: Any, *, repair: bool) -> dict[str, Any]:
    base = {
        "schema_version", "root_job_id", "plan_attempt_id", "plan_digest",
        "plan_step_id", "repair_round", "artifacts", "evidence_digests",
    }
    keys = base | ({"supersedes_job_id", "rejected_review_job_id", "rejected_review_result_digest"} if repair else set())
    raw = _closed(value, name="repair role_result" if repair else "work role_result", keys=keys)
    expected_schema = "mastermind.repair_result/v1" if repair else "mastermind.work_result/v1"
    if raw["schema_version"] != expected_schema:
        raise OrchestrationResultError("unsupported work/repair schema")
    result = {"schema_version": expected_schema, **_lineage(raw)}
    result["repair_round"] = _integer(
        raw["repair_round"], name="repair_round", minimum=1 if repair else 0,
        maximum=2 if repair else 0,
    )
    if repair:
        result.update(
            {
                "supersedes_job_id": _identifier(raw["supersedes_job_id"], name="supersedes_job_id"),
                "rejected_review_job_id": _identifier(raw["rejected_review_job_id"], name="rejected_review_job_id"),
                "rejected_review_result_digest": _digest(raw["rejected_review_result_digest"], name="rejected_review_result_digest"),
            }
        )
    result["artifacts"] = _artifacts(raw["artifacts"])
    result["evidence_digests"] = _evidence(raw["evidence_digests"])
    return result


def _validate_review(value: Any, *, outer_errors: list[Any]) -> dict[str, Any]:
    keys = {
        "schema_version", "root_job_id", "plan_attempt_id", "plan_digest",
        "plan_step_id", "reviewed_job_id", "reviewed_attempt_id",
        "reviewed_result_digest", "repair_round", "verdict", "evidence_digests",
        "findings",
    }
    raw = _closed(value, name="review role_result", keys=keys)
    if raw["schema_version"] != "mastermind.review_result/v1":
        raise OrchestrationResultError("unsupported review schema")
    result = {"schema_version": "mastermind.review_result/v1", **_lineage(raw)}
    result.update(
        {
            "reviewed_job_id": _identifier(raw["reviewed_job_id"], name="reviewed_job_id"),
            "reviewed_attempt_id": _identifier(raw["reviewed_attempt_id"], name="reviewed_attempt_id"),
            "reviewed_result_digest": _digest(raw["reviewed_result_digest"], name="reviewed_result_digest"),
            "repair_round": _integer(raw["repair_round"], name="repair_round", minimum=0, maximum=2),
            "verdict": raw["verdict"],
            "evidence_digests": _evidence(raw["evidence_digests"]),
        }
    )
    if not isinstance(raw["verdict"], str) or raw["verdict"] not in {"approve", "reject"}:
        raise OrchestrationResultError("review verdict must be approve or reject")
    findings: list[dict[str, Any]] = []
    for index, item in enumerate(_array(raw["findings"], name="findings")):
        finding = _closed(
            item, name=f"findings[{index}]",
            keys={"code", "severity", "message", "evidence_digests"},
        )
        if not isinstance(finding["severity"], str) or finding["severity"] not in {"info", "warning", "blocking"}:
            raise OrchestrationResultError("finding severity is invalid")
        resolved_finding = {
                "code": _identifier(finding["code"], name="finding.code"),
                "severity": finding["severity"],
                "message": _text(finding["message"], name="finding.message"),
                "evidence_digests": _evidence(finding["evidence_digests"]),
            }
        if resolved_finding in findings:
            raise OrchestrationResultError("findings contains a duplicate object")
        findings.append(resolved_finding)
    blocking = any(item["severity"] == "blocking" for item in findings)
    if raw["verdict"] == "approve" and (blocking or outer_errors):
        raise OrchestrationResultError("approve requires no blocking finding and no errors")
    if raw["verdict"] == "reject" and not blocking:
        raise OrchestrationResultError("reject requires at least one blocking finding")
    result["findings"] = findings
    return result


def _nullable_identifier(value: Any, *, name: str) -> str | None:
    return None if value is None else _identifier(value, name=name)


def _validate_aggregation(value: Any, *, outer_job_id: str) -> dict[str, Any]:
    keys = {
        "schema_version", "root_job_id", "handoff_digest", "policy_sha",
        "plan_attempt_id", "plan_digest", "revisions", "aggregate_summary",
        "evidence_digests",
    }
    raw = _closed(value, name="aggregation role_result", keys=keys)
    if raw["schema_version"] != "mastermind.aggregation_result/v1":
        raise OrchestrationResultError("unsupported aggregation schema")
    if raw["root_job_id"] != outer_job_id:
        raise OrchestrationResultError("aggregation root_job_id must equal outer job_id")
    revisions: list[dict[str, Any]] = []
    for index, item in enumerate(_array(raw["revisions"], name="revisions", minimum=1, maximum=8)):
        revision = _closed(
            item, name=f"revisions[{index}]",
            keys={
                "ordinal", "plan_step_id", "current_job_id", "current_attempt_id",
                "current_result_digest", "repair_round", "review_required",
                "qualifying_review_job_id", "qualifying_review_attempt_id",
                "qualifying_review_result_digest",
            },
        )
        if _integer(revision["ordinal"], name="ordinal", minimum=0, maximum=7) != index:
            raise OrchestrationResultError("revision ordinal must equal array position")
        review_required = _boolean(revision["review_required"], name="review_required")
        review_values = [
            revision["qualifying_review_job_id"],
            revision["qualifying_review_attempt_id"],
            revision["qualifying_review_result_digest"],
        ]
        if (review_required and not all(value is not None for value in review_values)) or (
            not review_required and any(value is not None for value in review_values)
        ):
            raise OrchestrationResultError("qualifying review fields have invalid nullability")
        resolved_revision = {
                "ordinal": index,
                "plan_step_id": _identifier(revision["plan_step_id"], name="plan_step_id"),
                "current_job_id": _identifier(revision["current_job_id"], name="current_job_id"),
                "current_attempt_id": _identifier(revision["current_attempt_id"], name="current_attempt_id"),
                "current_result_digest": _digest(revision["current_result_digest"], name="current_result_digest"),
                "repair_round": _integer(revision["repair_round"], name="repair_round", minimum=0, maximum=2),
                "review_required": review_required,
                "qualifying_review_job_id": _nullable_identifier(revision["qualifying_review_job_id"], name="qualifying_review_job_id"),
                "qualifying_review_attempt_id": _nullable_identifier(revision["qualifying_review_attempt_id"], name="qualifying_review_attempt_id"),
                "qualifying_review_result_digest": None if revision["qualifying_review_result_digest"] is None else _digest(revision["qualifying_review_result_digest"], name="qualifying_review_result_digest"),
            }
        if resolved_revision in revisions:
            raise OrchestrationResultError("revisions contains a duplicate object")
        revisions.append(resolved_revision)
    return {
        "schema_version": "mastermind.aggregation_result/v1",
        "root_job_id": raw["root_job_id"],
        "handoff_digest": _digest(raw["handoff_digest"], name="handoff_digest"),
        "policy_sha": _digest(raw["policy_sha"], name="policy_sha"),
        "plan_attempt_id": _identifier(raw["plan_attempt_id"], name="plan_attempt_id"),
        "plan_digest": _digest(raw["plan_digest"], name="plan_digest"),
        "revisions": revisions,
        "aggregate_summary": _text(raw["aggregate_summary"], name="aggregate_summary"),
        "evidence_digests": _evidence(raw["evidence_digests"]),
    }


_ENVELOPE_KEYS = {
    "schema_version", "job_id", "run_id", "worker_id", "role", "status",
    "role_result", "summary", "current_state", "next_actions", "errors",
    "validations",
}


def validate_envelope(
    value: Any,
    *,
    expected_job_id: str,
    expected_run_id: str,
    expected_worker_id: str,
    expected_role: str,
    expected_root_job_id: str | None = None,
) -> dict[str, Any]:
    raw = _closed(value, name="orchestration result", keys=_ENVELOPE_KEYS)
    if raw["schema_version"] != RESULT_SCHEMA:
        raise OrchestrationResultError("unsupported orchestration result schema")
    if raw["status"] != "COMPLETED" or raw["validations"] != []:
        raise OrchestrationResultError("completed result requires status=COMPLETED and validations=[]")
    identities = {
        "job_id": expected_job_id,
        "run_id": expected_run_id,
        "worker_id": expected_worker_id,
        "role": expected_role,
    }
    for name, expected in identities.items():
        actual = _identifier(raw[name], name=name) if name != "role" else raw[name]
        if actual != expected:
            raise OrchestrationResultError(f"outer {name} mismatch")
    if expected_role not in ROLES:
        raise OrchestrationResultError("expected role is not closed")
    errors = [
        _text(item, name=f"errors[{index}]")
        for index, item in enumerate(_array(raw["errors"], name="errors", maximum=16))
    ]
    if len(errors) != len(set(errors)):
        raise OrchestrationResultError("errors contains a duplicate item")
    context = {
        "run_id": expected_run_id,
        "expected_root_job_id": expected_root_job_id,
    }
    if expected_role == "plan":
        role_result = _validate_plan(raw["role_result"], outer=context)
    elif expected_role == "work":
        role_result = _validate_work(raw["role_result"], repair=False)
    elif expected_role == "review":
        role_result = _validate_review(raw["role_result"], outer_errors=errors)
    elif expected_role == "repair":
        role_result = _validate_work(raw["role_result"], repair=True)
    else:
        role_result = _validate_aggregation(raw["role_result"], outer_job_id=expected_job_id)
    next_actions = [
        _text(item, name=f"next_actions[{index}]")
        for index, item in enumerate(
            _array(raw["next_actions"], name="next_actions", maximum=16)
        )
    ]
    if len(next_actions) != len(set(next_actions)):
        raise OrchestrationResultError("next_actions contains a duplicate item")
    result = {
        "schema_version": RESULT_SCHEMA,
        "job_id": expected_job_id,
        "run_id": expected_run_id,
        "worker_id": expected_worker_id,
        "role": expected_role,
        "status": "COMPLETED",
        "role_result": role_result,
        "summary": _text(raw["summary"], name="summary"),
        "current_state": _text(raw["current_state"], name="current_state"),
        "next_actions": next_actions,
        "errors": errors,
        "validations": [],
    }
    encoded = canonical_bytes(result)
    if len(encoded) > MAX_CANONICAL_RESULT_BYTES:
        raise OrchestrationResultError("canonical result exceeds 8 MiB")
    if evidence_contains_secret(result) or redact_evidence(result) != result:
        raise OrchestrationResultError("result contains redaction-triggering sensitive material")
    return result


def parse_and_validate_envelope(text: str, **expected: Any) -> dict[str, Any]:
    parsed = parse_canonical_json(text)
    validated = validate_envelope(parsed, **expected)
    if canonical_bytes(validated) != text.encode("utf-8"):
        raise OrchestrationResultError("validated result did not round-trip byte-for-byte")
    return validated


@dataclasses.dataclass(frozen=True, repr=False)
class RawRoleResultObservation:
    attempt_id: str
    session_epoch_id: str
    process_generation_id: str
    turn_id: str
    provider_session_id: str
    provider_native_turn_id: str
    provider_turn_artifact_digest: str
    canonical_result_json: str
    canonical_result_digest: str
    canonical_result_byte_length: int
    schema_version: str = RAW_OBSERVATION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != RAW_OBSERVATION_SCHEMA:
            raise OrchestrationResultError("unsupported raw result observation schema")
        for name in (
            "attempt_id", "session_epoch_id", "process_generation_id", "turn_id",
            "provider_session_id", "provider_native_turn_id",
        ):
            _identifier(getattr(self, name), name=name)
        _digest(self.provider_turn_artifact_digest, name="provider_turn_artifact_digest")
        _digest(self.canonical_result_digest, name="canonical_result_digest")
        parsed = parse_canonical_json(self.canonical_result_json)
        encoded = self.canonical_result_json.encode("utf-8")
        if not 1 <= self.canonical_result_byte_length <= MAX_CANONICAL_RESULT_BYTES:
            raise OrchestrationResultError("raw result byte length is outside 1..8 MiB")
        if len(encoded) != self.canonical_result_byte_length:
            raise OrchestrationResultError("raw result byte length mismatch")
        if hashlib.sha256(encoded).hexdigest() != self.canonical_result_digest:
            raise OrchestrationResultError("raw result digest mismatch")
        if not isinstance(parsed, dict):
            raise OrchestrationResultError("raw result must hold one result object")

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def __repr__(self) -> str:
        return (
            "RawRoleResultObservation("
            f"attempt_id={self.attempt_id!r}, turn_id={self.turn_id!r}, "
            f"canonical_result_digest={self.canonical_result_digest!r}, "
            f"canonical_result_byte_length={self.canonical_result_byte_length!r}, "
            "canonical_result_json=<private>)"
        )


@runtime_checkable
class RawRoleResultAdapter(Protocol):
    def observe_raw_role_result(self, turn: Any) -> RawRoleResultObservation: ...


GOLDEN_ROLE_SCHEMA_DIGESTS = {
    role: role_schema_digest(role)
    for role in ("plan", "work", "review", "repair", "aggregation")
}


__all__ = [
    "GOLDEN_ROLE_SCHEMA_DIGESTS",
    "MAX_CANONICAL_RESULT_BYTES",
    "OrchestrationResultError",
    "RAW_OBSERVATION_SCHEMA",
    "RESULT_SCHEMA",
    "ROLES",
    "RawRoleResultAdapter",
    "RawRoleResultObservation",
    "canonical_bytes",
    "canonical_digest",
    "orchestration_result_schema",
    "parse_and_validate_envelope",
    "parse_canonical_json",
    "role_schema_digest",
    "validate_envelope",
]
