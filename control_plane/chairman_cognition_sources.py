"""Compose Chairman-cognition input from existing canonical read projections.

This is a pure owner-preserving adapter. It consumes an already-produced CEO boot
packet plus explicit receipts from existing owners. It performs no source crawling,
I/O, scheduling, mutation, authority grant, or durable storage.

The JSON values supplied to this module are evidence inputs, not authenticated source
identity. A CURRENT attestation is meaningful only when a separately accepted trusted
adapter acquired the owner payload and attestation together. Arbitrary or model-authored
local JSON remains fixture/test input and grants no authority.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from control_plane.chairman_cognition import INPUT_SCHEMA, evaluate_document
from control_plane.wake_events import canonical_json_bytes

SOURCE_BUNDLE_SCHEMA = "mastermind.chairman_cognition_source_bundle.v1"
COMPOSITION_SCHEMA = "mastermind.chairman_cognition_composition.v1"
ERROR_SCHEMA = "mastermind.chairman_cognition_source_error.v1"
BOOT_PACKET_SCHEMA = "mastermind.ceo_boot_packet.v1"
STRATEGIC_STATE_SCHEMA = "mastermind.strategic_state.v1"
AGENT_OS_BRIEF_SCHEMA = "ceo_brief.v1"
AGENT_OS_READINESS_SCHEMA = "agentos.readiness.v1"
MASTERMIND_REVISION_SOURCE_REF = "GITHUB:Mastermind:protected-master"
AGENT_OS_REVISION_SOURCE_REF = "AGENT_OS:canonical-revision"
STRATEGIC_SOURCE_REF = "STRATEGIC_STATE:config/strategic_state.yml"
AGENT_OS_SOURCE_REF = "AGENT_OS:ceo_brief"

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_RESERVED_OWNERS = frozenset({"CHAIRMAN_DIRECTIVE", "STRATEGIC_STATE", "AGENT_OS"})
_REQUIRED_CONSTRAINTS = frozenset(
    {
        "autonomous_production_deploy",
        "autonomous_live_capital_execution",
        "duplicate_control_planes",
        "unbounded_autonomous_strategic_modification",
    }
)
_AGENT_OS_BRIEF_REQUIRED_FIELDS = frozenset(
    {
        "schema",
        "generated_at",
        "since",
        "since_label",
        "counts",
        "inputs",
        "needs_ceo",
        "blocked",
        "finished",
        "running",
        "readiness",
        "warnings",
    }
)
_AGENT_OS_COUNT_FIELDS = frozenset(
    {"total", "active", "awaiting_ci", "blocked", "done_in_window"}
)
_AGENT_OS_RUNNING_FIELDS = frozenset(
    {
        "active",
        "awaiting_ci",
        "awaiting_review",
        "blocked",
        "proposed",
        "open_prs",
        "stale_claims",
        "claims_without_worktree",
    }
)
_AGENT_OS_READINESS_FIELDS = frozenset(
    {
        "workstream",
        "wave",
        "state",
        "reason_code",
        "reason",
        "depends_on",
        "unmet_dependencies",
        "source",
    }
)
_AGENT_OS_READINESS_STATES = frozenset(
    {"ready", "blocked", "in_progress", "done", "unknown"}
)
_MAX_ADDITIONAL_RECEIPTS = 123


class ChairmanCognitionSourceError(ValueError):
    """The bundle cannot be composed without inventing company truth."""


def compose_input(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Compose and validate one closed Chairman-cognition input document."""
    doc = _closed_mapping(
        bundle,
        required={
            "schema",
            "as_of",
            "chairman_directive",
            "mastermind_revision_attestation",
            "agentos_revision_attestation",
            "boot_packet",
            "additional_source_receipts",
            "delegation_envelope",
            "options",
        },
        where="source bundle",
    )
    if doc["schema"] != SOURCE_BUNDLE_SCHEMA:
        raise ChairmanCognitionSourceError("unsupported source bundle schema")

    as_of = _text(doc["as_of"], "as_of", 40)
    boot = _boot_packet(doc["boot_packet"])
    generated_at = _text(boot["generated_at"], "boot_packet.generated_at", 40)

    chairman = _chairman_receipt(doc["chairman_directive"])
    mastermind_revision = _revision_attestation(
        doc["mastermind_revision_attestation"],
        source_ref=MASTERMIND_REVISION_SOURCE_REF,
        owner="GITHUB",
        where="mastermind_revision_attestation",
    )
    agentos_revision = _revision_attestation(
        doc["agentos_revision_attestation"],
        source_ref=AGENT_OS_REVISION_SOURCE_REF,
        owner="AGENT_OS",
        where="agentos_revision_attestation",
    )
    strategic_receipt, constraints = _strategic_receipt(
        boot, generated_at, mastermind_revision
    )
    agentos_receipt = _agentos_receipt(boot, generated_at, agentos_revision)
    additions = _additional_receipts(doc["additional_source_receipts"])

    receipts = [
        chairman,
        mastermind_revision,
        strategic_receipt,
        agentos_revision,
        agentos_receipt,
        *additions,
    ]
    refs = [item["source_ref"] for item in receipts]
    if len(refs) != len(set(refs)):
        raise ChairmanCognitionSourceError("duplicate source_ref across composed sources")

    composed = {
        "schema": INPUT_SCHEMA,
        "as_of": as_of,
        "source_receipts": receipts,
        "strategic_constraints": constraints,
        "delegation_envelope": doc["delegation_envelope"],
        "options": doc["options"],
    }
    # A1 remains the controlling closed grammar and decision preflight.
    evaluate_document(composed)
    return composed


def evaluate_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Compose and evaluate a bundle without granting execution authority."""
    composed = compose_input(bundle)
    packet = evaluate_document(composed)
    result: dict[str, Any] = {
        "schema": COMPOSITION_SCHEMA,
        "source_bundle_digest": hashlib.sha256(
            canonical_json_bytes(bundle)
        ).hexdigest(),
        "composed_input_digest": hashlib.sha256(
            canonical_json_bytes(composed)
        ).hexdigest(),
        "source_summary": [
            {
                "source_ref": item["source_ref"],
                "owner": item["owner"],
                "revision": item["revision"],
                "state": item["state"],
                "load_bearing": item["load_bearing"],
                "observed_at": item["observed_at"],
            }
            for item in composed["source_receipts"]
        ],
        "packet": packet,
        "execution_authority_granted": False,
    }
    result["composition_digest"] = hashlib.sha256(
        canonical_json_bytes(result)
    ).hexdigest()
    return result


def _boot_packet(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ChairmanCognitionSourceError("boot_packet must be a mapping")
    if value.get("schema") != BOOT_PACKET_SCHEMA:
        raise ChairmanCognitionSourceError("unsupported CEO boot packet schema")
    for key in (
        "generated_at",
        "mastermind",
        "macro",
        "strategic_state",
        "brief",
        "degraded",
    ):
        if key not in value:
            raise ChairmanCognitionSourceError(
                "CEO boot packet is missing required fields"
            )
    if not isinstance(value["mastermind"], Mapping):
        raise ChairmanCognitionSourceError(
            "boot_packet.mastermind must be a mapping"
        )
    if not isinstance(value["macro"], Mapping):
        raise ChairmanCognitionSourceError("boot_packet.macro must be a mapping")
    if not isinstance(value["degraded"], list) or not all(
        isinstance(item, str) for item in value["degraded"]
    ):
        raise ChairmanCognitionSourceError(
            "boot_packet.degraded must be a string list"
        )
    return value


def _chairman_receipt(value: Any) -> dict[str, Any]:
    item = _closed_mapping(
        value,
        required={"source_ref", "revision", "state", "load_bearing", "observed_at"},
        where="chairman_directive",
    )
    if item["load_bearing"] is not True:
        raise ChairmanCognitionSourceError(
            "Chairman directive must be explicitly load-bearing"
        )
    return {
        "source_ref": _text(item["source_ref"], "chairman source_ref", 256),
        "owner": "CHAIRMAN_DIRECTIVE",
        "revision": _text(item["revision"], "chairman revision", 256),
        "state": _source_state(item["state"]),
        "load_bearing": True,
        "observed_at": _text(item["observed_at"], "chairman observed_at", 40),
    }


def _revision_attestation(
    value: Any,
    *,
    source_ref: str,
    owner: str,
    where: str,
) -> dict[str, Any]:
    item = _closed_mapping(
        value,
        required={"revision", "state", "load_bearing", "observed_at"},
        where=where,
    )
    revision = _text(item["revision"], f"{where}.revision", 40)
    if _SHA_RE.fullmatch(revision) is None:
        raise ChairmanCognitionSourceError(
            f"{where}.revision must be a full commit SHA"
        )
    if item["load_bearing"] is not True:
        raise ChairmanCognitionSourceError(
            f"{where} must be explicitly load-bearing"
        )
    return {
        "source_ref": source_ref,
        "owner": owner,
        "revision": revision,
        "state": _source_state(item["state"]),
        "load_bearing": True,
        "observed_at": _text(item["observed_at"], f"{where}.observed_at", 40),
    }


def _strategic_receipt(
    boot: Mapping[str, Any],
    observed_at: str,
    canonical_revision: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    strategic = boot.get("strategic_state")
    if not isinstance(strategic, Mapping):
        raise ChairmanCognitionSourceError("strategic state is unavailable")
    if strategic.get("schema") != STRATEGIC_STATE_SCHEMA:
        raise ChairmanCognitionSourceError("unsupported strategic state schema")
    constraints = strategic.get("constraints")
    if not isinstance(constraints, Mapping):
        raise ChairmanCognitionSourceError("strategic constraints are unavailable")

    normalized: dict[str, str] = {}
    for raw_name, raw_level in constraints.items():
        name = _text(raw_name, "strategic constraint name", 128)
        level = _text(raw_level, "strategic constraint level", 32)
        if level not in {"permitted", "constrained", "prohibited"}:
            raise ChairmanCognitionSourceError("unknown strategic constraint level")
        normalized[name] = level
    if not _REQUIRED_CONSTRAINTS <= set(normalized):
        raise ChairmanCognitionSourceError(
            "load-bearing strategic constraint missing"
        )

    checkout_sha = boot["mastermind"].get("sha")
    branch = boot["mastermind"].get("branch")
    checkout_known = (
        isinstance(checkout_sha, str)
        and _SHA_RE.fullmatch(checkout_sha) is not None
    )
    canonical_sha = canonical_revision["revision"]
    if not checkout_known or branch != "master":
        state = "UNKNOWN"
    elif checkout_sha != canonical_sha:
        state = "CONFLICT"
    else:
        state = canonical_revision["state"]

    content_digest = hashlib.sha256(canonical_json_bytes(strategic)).hexdigest()
    checkout_label = checkout_sha if checkout_known else "UNRESOLVED"
    return (
        {
            "source_ref": STRATEGIC_SOURCE_REF,
            "owner": "STRATEGIC_STATE",
            "revision": (
                f"sha256:{content_digest};mastermind:{checkout_label};"
                f"canonical:{canonical_sha}"
            ),
            "state": state,
            "load_bearing": True,
            "observed_at": _latest_observed_at(
                observed_at, canonical_revision["observed_at"]
            ),
        },
        normalized,
    )


def _agentos_receipt(
    boot: Mapping[str, Any],
    fallback_observed_at: str,
    canonical_revision: Mapping[str, Any],
) -> dict[str, Any]:
    brief = boot.get("brief")
    checkout_sha = boot["macro"].get("sha")
    checkout_known = (
        isinstance(checkout_sha, str)
        and _SHA_RE.fullmatch(checkout_sha) is not None
    )
    canonical_sha = canonical_revision["revision"]

    valid_brief, brief_observed_at = _agentos_brief_status(brief)
    observed_at = brief_observed_at or fallback_observed_at
    state = "UNKNOWN"
    if valid_brief and checkout_known:
        if checkout_sha != canonical_sha:
            state = "CONFLICT"
        else:
            state = canonical_revision["state"]

    brief_digest = (
        hashlib.sha256(canonical_json_bytes(brief)).hexdigest()
        if isinstance(brief, Mapping)
        else None
    )
    checkout_label = checkout_sha if checkout_known else "UNRESOLVED"
    revision = (
        (
            f"sha256:{brief_digest};macro:{checkout_label};"
            f"canonical:{canonical_sha}"
        )
        if brief_digest is not None
        else f"UNRESOLVED;macro:{checkout_label};canonical:{canonical_sha}"
    )
    return {
        "source_ref": AGENT_OS_SOURCE_REF,
        "owner": "AGENT_OS",
        "revision": revision,
        "state": state,
        "load_bearing": True,
        "observed_at": _latest_observed_at(
            observed_at, canonical_revision["observed_at"]
        ),
    }


def _agentos_brief_status(value: Any) -> tuple[bool, str | None]:
    """Return whether the current owner contract supports a CURRENT claim.

    This validates only the published `ceo_brief.v1` wire shape and degradation
    receipts. It does not re-rank work, infer escalation, or recompute readiness.
    """
    if not isinstance(value, Mapping):
        return False, None

    observed_at = _valid_utc_text(value.get("generated_at"))
    if not _AGENT_OS_BRIEF_REQUIRED_FIELDS <= set(value):
        return False, observed_at
    if value.get("schema") != AGENT_OS_BRIEF_SCHEMA or observed_at is None:
        return False, None
    if _valid_utc_text(value.get("since")) is None:
        return False, observed_at
    if not _valid_text(value.get("since_label")):
        return False, observed_at

    counts = value.get("counts")
    if not _nonnegative_int_mapping(counts, _AGENT_OS_COUNT_FIELDS):
        return False, observed_at

    inputs = value.get("inputs")
    if not isinstance(inputs, Mapping):
        return False, observed_at
    if not _nonnegative_int(inputs.get("worktrees")):
        return False, observed_at
    age = inputs.get("active_builds_age_hours")
    if age is not None and (
        isinstance(age, bool) or not isinstance(age, (int, float)) or age < 0
    ):
        return False, observed_at
    degraded = inputs.get("degraded")
    if not _string_list(degraded):
        return False, observed_at

    for field in ("needs_ceo", "blocked", "finished"):
        rows = value.get(field)
        if not _mapping_list(rows):
            return False, observed_at

    running = value.get("running")
    if not _nonnegative_int_mapping(running, _AGENT_OS_RUNNING_FIELDS):
        return False, observed_at

    readiness = value.get("readiness")
    if not _valid_readiness(readiness):
        return False, observed_at

    warnings = value.get("warnings")
    if not _string_list(warnings):
        return False, observed_at

    readiness_degraded = readiness.get("degraded")
    healthy = not degraded and not warnings and not readiness_degraded
    return healthy, observed_at


def _valid_readiness(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    if value.get("schema") != AGENT_OS_READINESS_SCHEMA:
        return False
    records = value.get("records")
    degraded = value.get("degraded")
    if not isinstance(records, list) or not _string_list(degraded):
        return False
    return all(_valid_readiness_record(record) for record in records)


def _valid_readiness_record(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    if not _AGENT_OS_READINESS_FIELDS <= set(value):
        return False
    if not _valid_text(value.get("workstream")):
        return False
    wave = value.get("wave")
    if wave is not None and not _valid_text(wave):
        return False
    if value.get("state") not in _AGENT_OS_READINESS_STATES:
        return False
    for field in ("reason_code", "reason", "source"):
        if not _valid_text(value.get(field)):
            return False
    return _string_list(value.get("depends_on")) and _string_list(
        value.get("unmet_dependencies")
    )


def _nonnegative_int_mapping(value: Any, required: frozenset[str]) -> bool:
    return (
        isinstance(value, Mapping)
        and required <= set(value)
        and all(_nonnegative_int(value.get(field)) for field in required)
    )


def _nonnegative_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def _mapping_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, Mapping) for item in value)


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _valid_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def _valid_utc_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        return None
    return value


def _additional_receipts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > _MAX_ADDITIONAL_RECEIPTS:
        raise ChairmanCognitionSourceError(
            "additional_source_receipts must be a bounded list"
        )
    out: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            raise ChairmanCognitionSourceError(
                "additional receipt must be a mapping"
            )
        if raw.get("owner") in _RESERVED_OWNERS:
            raise ChairmanCognitionSourceError(
                "reserved canonical source must use its dedicated composer path"
            )
        out.append(dict(raw))
    out.sort(key=lambda item: str(item.get("source_ref", "")))
    return out


def _latest_observed_at(*values: str) -> str:
    parsed: list[tuple[str, datetime]] = []
    for raw in values:
        text = _text(raw, "observed_at", 40)
        try:
            instant = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ChairmanCognitionSourceError(
                "observed_at must be UTC ISO-8601"
            ) from exc
        if instant.tzinfo is None or instant.utcoffset() != timezone.utc.utcoffset(
            instant
        ):
            raise ChairmanCognitionSourceError(
                "observed_at must be UTC ISO-8601"
            )
        parsed.append((text, instant))
    return max(parsed, key=lambda item: item[1])[0]


def _closed_mapping(
    value: Any, *, required: set[str], where: str
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ChairmanCognitionSourceError(f"{where} must be a mapping")
    keys = set(value)
    if required - keys:
        raise ChairmanCognitionSourceError(f"{where} is missing required fields")
    if keys - required:
        raise ChairmanCognitionSourceError(f"{where} contains unknown fields")
    return value


def _text(value: Any, name: str, max_len: int) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ChairmanCognitionSourceError(f"{name} must be a trimmed string")
    if len(value) > max_len or any(ord(char) < 32 for char in value):
        raise ChairmanCognitionSourceError(f"{name} is out of bounds")
    return value


def _source_state(value: Any) -> str:
    text = _text(value, "source state", 16)
    if text not in {"CURRENT", "STALE", "CONFLICT", "UNKNOWN"}:
        raise ChairmanCognitionSourceError("unknown source state")
    return text


__all__ = [
    "AGENT_OS_REVISION_SOURCE_REF",
    "AGENT_OS_SOURCE_REF",
    "COMPOSITION_SCHEMA",
    "ERROR_SCHEMA",
    "MASTERMIND_REVISION_SOURCE_REF",
    "SOURCE_BUNDLE_SCHEMA",
    "STRATEGIC_SOURCE_REF",
    "ChairmanCognitionSourceError",
    "compose_input",
    "evaluate_bundle",
]
