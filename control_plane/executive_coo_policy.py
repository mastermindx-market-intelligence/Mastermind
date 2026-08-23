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
from pathlib import Path
from typing import Any


_ROOT = Path(__file__).resolve().parent.parent
_POLICY_PATH = _ROOT / "config" / "authority_map.yml"

_EXPECTED_SCALARS = {
    "schema_version": 1,
    "max_fan_out_per_parent": 8,
    "max_depth": 1,
    "max_repair_rounds": 2,
    "max_review_attempts_per_job": 2,
    "max_children_total": 16,
    "max_attempts_per_orchestration_job": 2,
    "review_job_attempt_limit": 1,
}
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


EXPECTED_POLICY_SHA256 = hashlib.sha256(
    _canonical_json(_expected_policy_payload())
).hexdigest()


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

    @classmethod
    def load(cls, path: str | Path | None = None) -> "CooCyclePolicy":
        source_path = Path(path).resolve() if path is not None else _POLICY_PATH
        try:
            raw = source_path.read_bytes()
        except OSError as exc:
            raise CooCyclePolicyError(f"COO cycle policy is unavailable: {exc}") from exc
        values = _extract_block(raw)
        expected_keys = set(_EXPECTED_SCALARS) | {"allowed_child_cost_classes"}
        if set(values) != expected_keys:
            missing = sorted(expected_keys - set(values))
            extra = sorted(set(values) - expected_keys)
            raise CooCyclePolicyError(
                f"coo_cycle_policy has closed-key drift; missing={missing}, extra={extra}"
            )
        for key, expected in _EXPECTED_SCALARS.items():
            if values[key] != expected:
                raise CooCyclePolicyError(
                    f"coo_cycle_policy.{key} must remain exactly {expected}"
                )
        if values["allowed_child_cost_classes"] != _EXPECTED_COST_CLASSES:
            raise CooCyclePolicyError(
                "allowed_child_cost_classes must remain exactly [default, small]"
            )
        canonical = _expected_policy_payload()
        return cls(
            **{key: values[key] for key in _EXPECTED_SCALARS},
            allowed_child_cost_classes=values["allowed_child_cost_classes"],
            policy_sha256=hashlib.sha256(_canonical_json(canonical)).hexdigest(),
            source_sha256=hashlib.sha256(raw).hexdigest(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **{key: getattr(self, key) for key in _EXPECTED_SCALARS},
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


__all__ = ["CooCyclePolicy", "CooCyclePolicyError", "EXPECTED_POLICY_SHA256"]
