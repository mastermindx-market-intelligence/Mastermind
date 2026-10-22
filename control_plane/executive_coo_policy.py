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
_HIERARCHY_SCALARS = {
    **_EXPECTED_SCALARS,
    "schema_version": 2,
    "max_fan_out_per_parent": 16,
    "max_depth": 3,
}
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


def _expected_policy_payload(version: int = 1) -> dict[str, Any]:
    return {
        **(_EXPECTED_SCALARS if version == 1 else _HIERARCHY_SCALARS),
        "allowed_child_cost_classes": list(_EXPECTED_COST_CLASSES),
    }


EXPECTED_POLICY_SHA256 = hashlib.sha256(
    _canonical_json(_expected_policy_payload())
).hexdigest()
HIERARCHY_POLICY_SHA256 = hashlib.sha256(
    _canonical_json(_expected_policy_payload(2))
).hexdigest()


def _extract_block(raw: bytes, block: str = "coo_cycle_policy") -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise CooCyclePolicyError("COO cycle policy source is not UTF-8") from exc
    if "\x00" in text or "\t" in text:
        raise CooCyclePolicyError("COO cycle policy source contains forbidden bytes")
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line == block + ":"]
    if len(starts) != 1:
        raise CooCyclePolicyError(
            f"authority_map.yml must contain one {block} mapping"
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
    def load(cls, path: str | Path | None = None, *, version: int = 1) -> "CooCyclePolicy":
        if type(version) is not int or version not in (1, 2):
            raise CooCyclePolicyError("unsupported COO policy version")
        source_path = Path(path).resolve() if path is not None else _POLICY_PATH
        try:
            raw = source_path.read_bytes()
        except OSError as exc:
            raise CooCyclePolicyError(f"COO cycle policy is unavailable: {exc}") from exc
        values = _extract_block(raw, "coo_cycle_policy" if version == 1 else "coo_hierarchy_policy")
        scalars = _EXPECTED_SCALARS if version == 1 else _HIERARCHY_SCALARS
        expected_keys = set(_EXPECTED_SCALARS) | {"allowed_child_cost_classes"}
        if set(values) != expected_keys:
            missing = sorted(expected_keys - set(values))
            extra = sorted(set(values) - expected_keys)
            raise CooCyclePolicyError(
                f"coo_cycle_policy has closed-key drift; missing={missing}, extra={extra}"
            )
        for key, expected in scalars.items():
            if values[key] != expected:
                raise CooCyclePolicyError(
                    f"coo_cycle_policy.{key} must remain exactly {expected}"
                )
        if values["allowed_child_cost_classes"] != _EXPECTED_COST_CLASSES:
            raise CooCyclePolicyError(
                "allowed_child_cost_classes must remain exactly [default, small]"
            )
        canonical = _expected_policy_payload(version)
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

    @classmethod
    def for_digest(cls, digest: str, path: str | Path | None = None) -> "CooCyclePolicy":
        """Replay the admitted policy, never silently upgrade an existing root."""
        version = ({EXPECTED_POLICY_SHA256: 1, HIERARCHY_POLICY_SHA256: 2}.get(digest)
                   if isinstance(digest, str) else None)
        if version is None:
            raise CooCyclePolicyError("unrecognized admitted COO policy digest")
        return cls.load(path, version=version)

    def reserved_hierarchy_children(self, steps: tuple[dict[str, Any], ...], *,
                                    coordinator_depth: int, descendant_limit: int,
                                    max_depth: int) -> int:
        """Partition one inherited allowance, including this coordinator's planner.

        A coordinator step consumes its own Job plus its entire subtree reserve;
        a leaf consumes its existing review/repair reserve. Descendants do not
        each receive a fresh root allowance.
        """
        if self.schema_version != 2:
            raise CooCyclePolicyError("nested delegation requires policy v2")
        for value in (coordinator_depth, descendant_limit, max_depth):
            if type(value) is not int:
                raise CooCyclePolicyError("hierarchy bounds must be integers")
        if not (0 <= coordinator_depth < max_depth <= self.max_depth
                and 1 <= descendant_limit <= self.max_children_total):
            raise CooCyclePolicyError("hierarchy bounds exceed original grant")
        if not isinstance(steps, tuple) or not 1 <= len(steps) <= self.max_fan_out_per_parent:
            raise CooCyclePolicyError("hierarchy plan fan-out is outside policy")
        reserved = 1  # this coordinator's planner is inside its allowance
        for step in steps:
            if not isinstance(step, dict) or type(step.get("review_required")) is not bool:
                raise CooCyclePolicyError("invalid hierarchy step")
            delegation = step.get("delegation")
            if delegation is None:
                reserved += self.reserved_step_slots(review_required=step["review_required"])
                continue
            if (not isinstance(delegation, dict)
                    or set(delegation) != {"descendant_limit", "max_depth"}
                    or step["review_required"]):
                raise CooCyclePolicyError("invalid coordinator delegation")
            count, depth = delegation["descendant_limit"], delegation["max_depth"]
            if (type(count) is not int or type(depth) is not int
                    or not 2 <= count < descendant_limit
                    or not coordinator_depth + 1 < depth <= max_depth):
                raise CooCyclePolicyError("coordinator delegation widens inherited bounds")
            reserved += 1 + count
        if reserved > descendant_limit:
            raise CooCyclePolicyError("nested plan capacity exceeds inherited allowance")
        return reserved

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


__all__ = ["CooCyclePolicy", "CooCyclePolicyError", "EXPECTED_POLICY_SHA256", "HIERARCHY_POLICY_SHA256"]
