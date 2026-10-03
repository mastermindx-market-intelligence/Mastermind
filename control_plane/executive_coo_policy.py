"""Closed reviewed policy for the inert Phase 1F-C COO run-once cycle.

Only the deliberately tiny YAML subset used by the single
``coo_cycle_policy`` mapping is accepted.  There are no defaults or overrides:
duplicate, unknown, missing, malformed, or drifted fields all refuse.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from types import MappingProxyType
from pathlib import Path
from typing import Any


_ROOT = Path(__file__).resolve().parent.parent
_POLICY_PATH = _ROOT / "config" / "authority_map.yml"

_SUPPORTED_POLICY_VERSIONS = (1, 2)
V1_POLICY = MappingProxyType({
    "schema_version": 1,
    "max_fan_out_per_parent": 8,
    "max_depth": 1,
    "max_repair_rounds": 2,
    "max_review_attempts_per_job": 2,
    "max_children_total": 16,
    "max_attempts_per_orchestration_job": 2,
    "review_job_attempt_limit": 1,
})
V2_POLICY = MappingProxyType({
    **V1_POLICY,
    "schema_version": 2,
    "max_depth": 2,
    "max_provider_work_units_per_root": 32,
    "reserved_domain_consumption_units": 1,
})
_CANONICAL_POLICIES = MappingProxyType({1: V1_POLICY, 2: V2_POLICY})
_EXPECTED_SCALARS_BY_VERSION = MappingProxyType(
    {
        1: MappingProxyType(V1_POLICY),
        2: MappingProxyType(V2_POLICY),
    }
)
_EXPECTED_SCALARS = V2_POLICY
_EXPECTED_COST_CLASSES = ("default", "small")
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_INTEGER_RE = re.compile(r"^(0|[1-9][0-9]*)$")
_INLINE_LIST_RE = re.compile(
    r"^\[([a-z][a-z0-9_]*(?:, [a-z][a-z0-9_]*)*)\]$"
)


class CooCyclePolicyError(RuntimeError):
    """The reviewed COO policy is missing, malformed, duplicated, or drifted."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _expected_policy_payload() -> dict[str, Any]:
    return {
        **_EXPECTED_SCALARS,
        "allowed_child_cost_classes": list(_EXPECTED_COST_CLASSES),
    }


def _payload(values: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(values),
        "allowed_child_cost_classes": list(_EXPECTED_COST_CLASSES),
    }


EXPECTED_V1_POLICY_SHA256 = hashlib.sha256(_canonical_json(_payload(V1_POLICY))).hexdigest()
EXPECTED_POLICY_SHA256 = hashlib.sha256(
    _canonical_json(_payload(V2_POLICY))
).hexdigest()
EXPECTED_POLICY_SHA256_BY_VERSION = MappingProxyType(
    {
        1: EXPECTED_V1_POLICY_SHA256,
        2: EXPECTED_POLICY_SHA256,
    }
)


def _extract_block(raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise CooCyclePolicyError("COO cycle policy source is not UTF-8") from exc
    if "\x00" in text or "\t" in text:
        raise CooCyclePolicyError("COO cycle policy source contains forbidden bytes")
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line == "coo_cycle_policy:"]
    if len(starts) != 1:
        raise CooCyclePolicyError(
            "authority_map.yml must contain one coo_cycle_policy mapping"
        )

    result: dict[str, Any] = {}
    for line in lines[starts[0] + 1 :]:
        if not line or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            break
        if not line.startswith("  ") or line.startswith("   ") or ":" not in line:
            raise CooCyclePolicyError("invalid coo_cycle_policy shape")
        key, raw_value = (part.strip() for part in line.strip().split(":", 1))
        if _KEY_RE.fullmatch(key) is None or key in result or not raw_value:
            raise CooCyclePolicyError("invalid or duplicate coo_cycle_policy field")
        if key == "allowed_child_cost_classes":
            match = _INLINE_LIST_RE.fullmatch(raw_value)
            if match is None:
                raise CooCyclePolicyError(
                    "allowed_child_cost_classes must be one closed inline list"
                )
            result[key] = tuple(match.group(1).split(", "))
        else:
            if _INTEGER_RE.fullmatch(raw_value) is None:
                raise CooCyclePolicyError(f"{key} must be a non-negative integer")
            result[key] = int(raw_value)
    return result


@dataclasses.dataclass(frozen=True)
class CooCyclePolicy:
    schema_version: int
    max_fan_out_per_parent: int
    max_depth: int
    max_repair_rounds: int
    max_review_attempts_per_job: int
    max_children_total: int
    max_attempts_per_orchestration_job: int
    review_job_attempt_limit: int
    allowed_child_cost_classes: tuple[str, ...]
    policy_sha256: str
    source_sha256: str
    max_provider_work_units_per_root: int | None = None
    reserved_domain_consumption_units: int | None = None

    @classmethod
    def load(cls, path: str | Path | None = None) -> "CooCyclePolicy":
        source_path = Path(path).resolve() if path is not None else _POLICY_PATH
        try:
            raw = source_path.read_bytes()
        except OSError as exc:
            raise CooCyclePolicyError(f"COO cycle policy is unavailable: {exc}") from exc
        values = _extract_block(raw)
        expected_scalars = V2_POLICY
        expected_keys = set(expected_scalars) | {"allowed_child_cost_classes"}
        if set(values) != expected_keys:
            missing = sorted(expected_keys - set(values))
            extra = sorted(set(values) - expected_keys)
            raise CooCyclePolicyError(
                f"coo_cycle_policy has closed-key drift; missing={missing}, extra={extra}"
            )
        for key, expected in expected_scalars.items():
            if values[key] != expected:
                raise CooCyclePolicyError(
                    f"coo_cycle_policy.{key} must remain exactly {expected}"
                )
        if values["allowed_child_cost_classes"] != _EXPECTED_COST_CLASSES:
            raise CooCyclePolicyError(
                "allowed_child_cost_classes must remain exactly [default, small]"
            )
        return cls(
            **{key: values[key] for key in expected_scalars},
            allowed_child_cost_classes=values["allowed_child_cost_classes"],
            policy_sha256=hashlib.sha256(_canonical_json(_payload(values))).hexdigest(),
            source_sha256=hashlib.sha256(raw).hexdigest(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **{
                key: getattr(self, key)
                for key in _CANONICAL_POLICIES[self.schema_version]
            },
            "allowed_child_cost_classes": list(self.allowed_child_cost_classes),
        }

    def reserved_step_slots(self, *, review_required: bool) -> int:
        if not isinstance(review_required, bool):
            raise CooCyclePolicyError("review_required must be a boolean")
        if not review_required:
            return 1
        return (1 + self.max_repair_rounds) * (
            1 + self.max_review_attempts_per_job
        )

    def reserved_children_total(self, review_requirements: tuple[bool, ...]) -> int:
        if not isinstance(review_requirements, tuple):
            raise CooCyclePolicyError("review requirements must be an ordered tuple")
        if not 1 <= len(review_requirements) <= self.max_fan_out_per_parent:
            raise CooCyclePolicyError("logical work-plan fan-out is outside policy")
        total = 1 + sum(
            self.reserved_step_slots(review_required=value)
            for value in review_requirements
        )
        if total > self.max_children_total:
            raise CooCyclePolicyError("plan capacity exceeds max_children_total")
        return total


def _closed_source_version(
    values: dict[str, Any], *, requested_version: int
) -> int:
    """Validate the complete source block before selecting an immutable pin."""

    source_version = values.get("schema_version")
    if source_version not in _EXPECTED_SCALARS_BY_VERSION:
        raise CooCyclePolicyError(
            f"pinned COO v{requested_version} policy values are not exact"
        )
    expected_scalars = _EXPECTED_SCALARS_BY_VERSION[source_version]
    expected_keys = set(expected_scalars) | {"allowed_child_cost_classes"}
    if set(values) != expected_keys:
        raise CooCyclePolicyError(
            "pinned COO policy schema does not match the selected version"
        )
    if values["allowed_child_cost_classes"] != _EXPECTED_COST_CLASSES:
        raise CooCyclePolicyError(
            "pinned allowed_child_cost_classes must remain exactly [default, small]"
        )
    matched = [
        candidate
        for candidate in (1, 2)
        if set(values) == set(_EXPECTED_SCALARS_BY_VERSION[candidate]) | {
            "allowed_child_cost_classes"
        }
        and all(
            values[key] == expected
            for key, expected in _CANONICAL_POLICIES[candidate].items()
        )
    ]
    if len(matched) != 1:
        raise CooCyclePolicyError(
            f"pinned COO v{requested_version} policy values are not exact"
        )
    return matched[0]


def load_pinned_coo_cycle_policy(
    version: int, *, policy_sha256: str, path: str | Path | None = None
) -> CooCyclePolicy:
    """Load one exact historical or current pinned policy."""

    if type(version) is not int or version not in _SUPPORTED_POLICY_VERSIONS:
        raise CooCyclePolicyError("unsupported pinned COO policy version")
    if (
        type(policy_sha256) is not str
        or re.fullmatch(r"[0-9a-f]{64}", policy_sha256) is None
    ):
        raise CooCyclePolicyError("pinned COO policy digest is malformed")

    source_path = Path(path).resolve() if path is not None else _POLICY_PATH
    try:
        raw = source_path.read_bytes()
    except OSError as exc:
        raise CooCyclePolicyError(f"COO cycle policy is unavailable: {exc}") from exc
    values = _extract_block(raw)
    source_version = _closed_source_version(values, requested_version=version)
    if version == 1 and source_version == 2:
        values = {
            **dict(V1_POLICY),
            "allowed_child_cost_classes": _EXPECTED_COST_CLASSES,
        }
    elif version != source_version:
        raise CooCyclePolicyError(
            f"pinned COO v{version} policy values are not exact"
        )
    expected = _CANONICAL_POLICIES[version]
    if any(values[key] != value for key, value in expected.items()):
        raise CooCyclePolicyError(
            f"pinned COO v{version} policy values are not exact"
        )
    if values["allowed_child_cost_classes"] != _EXPECTED_COST_CLASSES:
        raise CooCyclePolicyError(
            "pinned allowed_child_cost_classes must remain exactly [default, small]"
        )
    if policy_sha256 != EXPECTED_POLICY_SHA256_BY_VERSION[version]:
        raise CooCyclePolicyError("pinned COO policy digest is not exact")
    return CooCyclePolicy(
        **{key: values[key] for key in expected},
        allowed_child_cost_classes=values["allowed_child_cost_classes"],
        policy_sha256=policy_sha256,
        source_sha256=hashlib.sha256(raw).hexdigest(),
    )


__all__ = [
    "CooCyclePolicy",
    "CooCyclePolicyError",
    "EXPECTED_POLICY_SHA256",
    "EXPECTED_POLICY_SHA256_BY_VERSION",
    "EXPECTED_V1_POLICY_SHA256",
    "load_pinned_coo_cycle_policy",
    "V1_POLICY",
    "V2_POLICY",
]
