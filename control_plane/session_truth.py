"""Pure Session Truth receipt assembly, admission and bounded rendering.

The receipt is a deterministic comparison artifact, not a lifecycle, queue, retry,
identity, transport, projection or persistence authority. Inputs are already-normalized
owner observations. Acquisition-envelope clocks are deliberately excluded from the
semantic hash; source revisions, source timestamps, facts, findings, admission and
scope remain covered.
"""
from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from control_plane.session_truth_contract import (
    FINDING_SEVERITIES,
    RECEIPT_SCHEMA,
    SessionTruthContractError,
    semantic_hash,
    validate_input_document,
)
from control_plane.session_truth_rules import detect_findings


_SOURCE_ORDER = (
    "skillpack",
    "agentos",
    "github",
    "linear",
    "slack",
    "executive",
    "identities",
)
_REVISION_FIELDS = {
    "skillpack": ("sha",),
    "agentos": ("source_sha",),
    "github": ("observed_at",),
    "linear": ("observed_at",),
    "slack": ("observed_at",),
    "executive": ("observed_at", "grounding_sha"),
    "identities": ("observed_at",),
}
_SAFE_MODES = frozenset({"GROUNDING_COMPLETE", "GROUNDING_PARTIAL"})


def _source_available(value: object) -> bool:
    return isinstance(value, Mapping) and value.get("available") is True


def _required_sources(inputs: Mapping[str, Any]) -> set[str]:
    """Return sources required by the exact requested scope.

    Skillpack is always required for modification-capable grounding. Agent OS,
    GitHub and Linear become required only when their exact identifiers are in
    scope. Executive state is required only for an Executive-dependent request.
    Slack transport and identity projection remain optional unless their own
    deterministic findings make the requested action blocking/fatal.
    """

    scope = inputs.get("scope")
    if not isinstance(scope, Mapping):
        return {"skillpack"}

    required = {"skillpack"}
    if scope.get("workstreams"):
        required.add("agentos")
    if scope.get("repositories"):
        required.add("github")
    if scope.get("linear"):
        required.add("linear")
    if scope.get("requires_executive") is True:
        required.add("executive")
    return required


def _finding_codes(
    findings: Sequence[Mapping[str, Any]], severity: str
) -> list[str]:
    codes: set[str] = set()
    for index, finding in enumerate(findings):
        if not isinstance(finding, Mapping):
            raise SessionTruthContractError(
                f"findings[{index}] must be an object"
            )
        observed_severity = finding.get("severity")
        if observed_severity not in FINDING_SEVERITIES:
            raise SessionTruthContractError(
                f"findings[{index}].severity is invalid: {observed_severity!r}"
            )
        code = finding.get("code")
        if not isinstance(code, str) or not code:
            raise SessionTruthContractError(
                f"findings[{index}].code must be a non-empty string"
            )
        if observed_severity == severity:
            codes.add(code)
    return sorted(codes)


def compute_admission(
    inputs: Mapping[str, Any],
    findings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compute deterministic admission precedence for the requested scope.

    This is a reconciliation safety decision only. ``modification_safe=true``
    does not replace Chairman intent, Skillpack, carrier, app or runtime gates.
    """

    if not isinstance(inputs, Mapping):
        raise SessionTruthContractError("inputs must be an object")

    fatal_codes = _finding_codes(findings, "FATAL")
    blocking_codes = _finding_codes(findings, "BLOCKING")
    warning_codes = _finding_codes(findings, "WARNING")

    required = _required_sources(inputs)
    unavailable = {
        name for name in _SOURCE_ORDER if not _source_available(inputs.get(name))
    }
    required_unavailable = sorted(unavailable & required)
    optional_unavailable = sorted(unavailable - required)

    if fatal_codes:
        mode = "MODIFICATION_REFUSED"
    elif blocking_codes or required_unavailable:
        mode = "DIALOGUE_ONLY"
    elif warning_codes or optional_unavailable:
        mode = "GROUNDING_PARTIAL"
    else:
        mode = "GROUNDING_COMPLETE"

    return {
        "mode": mode,
        "modification_safe": mode in _SAFE_MODES,
        "refusal_codes": fatal_codes,
        "blocking_codes": blocking_codes,
        "warning_codes": warning_codes,
        "required_sources_unavailable": required_unavailable,
        "optional_sources_unavailable": optional_unavailable,
    }


def _observation_time(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise SessionTruthContractError(f"{label} must be an offset-aware timestamp")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise SessionTruthContractError(
            f"{label} must be an offset-aware timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SessionTruthContractError(f"{label} must be an offset-aware timestamp")
    return parsed


def semantic_projection(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Project only semantic receipt state, excluding acquisition envelope clocks/hash."""

    if not isinstance(receipt, Mapping):
        raise SessionTruthContractError("receipt must be an object")
    return {
        key: copy.deepcopy(value)
        for key, value in receipt.items()
        if key not in {"observation", "semantic_hash"}
    }


def build_receipt(
    inputs: Mapping[str, Any],
    *,
    observed_started_at: str,
    observed_ended_at: str,
) -> dict[str, Any]:
    """Assemble one deterministic, read-only Session Truth Receipt."""

    started = _observation_time(observed_started_at, "observed_started_at")
    ended = _observation_time(observed_ended_at, "observed_ended_at")
    if ended < started:
        raise SessionTruthContractError(
            "observed_ended_at must not precede observed_started_at"
        )

    normalized = validate_input_document(inputs)
    findings = detect_findings(normalized)
    admission = compute_admission(normalized, findings)

    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "scope": normalized["scope"],
        "skillpack": normalized["skillpack"],
        "observation": {
            "started_at": observed_started_at,
            "ended_at": observed_ended_at,
        },
        "observations": {
            "agentos": normalized["agentos"],
            "github": normalized["github"],
            "linear": normalized["linear"],
            "slack": normalized["slack"],
            "executive": normalized["executive"],
            "identities": normalized["identities"],
        },
        "findings": findings,
        "admission": admission,
    }
    receipt["semantic_hash"] = semantic_hash(semantic_projection(receipt))
    return receipt


def _single_line(value: object) -> str:
    return str(value).replace("\r", "\\r").replace("\n", "\\n")


def _source_line(name: str, source: object) -> str:
    if not isinstance(source, Mapping) or source.get("available") is not True:
        reason = source.get("reason") if isinstance(source, Mapping) else "MALFORMED"
        return (
            f"source.{name}: available=false reason="
            f"{_single_line(reason or 'UNAVAILABLE')}"
        )

    parts = [f"source.{name}: available=true"]
    for field in _REVISION_FIELDS[name]:
        value = source.get(field)
        if value is not None:
            parts.append(f"{field}={_single_line(value)}")
    return " ".join(parts)


def render_receipt(receipt: Mapping[str, Any]) -> str:
    """Render a bounded deterministic summary without replaying raw source payloads."""

    if not isinstance(receipt, Mapping) or receipt.get("schema") != RECEIPT_SCHEMA:
        raise SessionTruthContractError(
            f"receipt.schema must be exactly {RECEIPT_SCHEMA!r}"
        )
    admission = receipt.get("admission")
    if not isinstance(admission, Mapping):
        raise SessionTruthContractError("receipt.admission must be an object")
    semantic = receipt.get("semantic_hash")
    if not isinstance(semantic, str) or not semantic:
        raise SessionTruthContractError("receipt.semantic_hash must be a non-empty string")

    lines = [
        "Session Truth Receipt",
        f"mode: {_single_line(admission.get('mode'))}",
        f"semantic_hash: {_single_line(semantic)}",
        "modification_safe: "
        + ("true" if admission.get("modification_safe") is True else "false"),
    ]

    observations = receipt.get("observations")
    if not isinstance(observations, Mapping):
        raise SessionTruthContractError("receipt.observations must be an object")
    source_values = {"skillpack": receipt.get("skillpack")}
    source_values.update({name: observations.get(name) for name in _SOURCE_ORDER[1:]})
    for name in _SOURCE_ORDER:
        lines.append(_source_line(name, source_values.get(name)))

    findings = receipt.get("findings")
    if not isinstance(findings, list):
        raise SessionTruthContractError("receipt.findings must be a list")
    counts = Counter(
        finding.get("severity")
        for finding in findings
        if isinstance(finding, Mapping)
    )
    lines.append(
        "findings: "
        f"total={len(findings)} "
        f"FATAL={counts['FATAL']} "
        f"BLOCKING={counts['BLOCKING']} "
        f"WARNING={counts['WARNING']} "
        f"INFO={counts['INFO']}"
    )

    for index, finding in enumerate(findings):
        if not isinstance(finding, Mapping):
            raise SessionTruthContractError(f"receipt.findings[{index}] must be an object")
        lines.append(
            "finding: "
            f"{_single_line(finding.get('severity'))} "
            f"{_single_line(finding.get('code'))} "
            f"subject={_single_line(finding.get('subject'))} "
            f"canonical_owner={_single_line(finding.get('canonical_owner'))} "
            f"repair_owner={_single_line(finding.get('repair_owner'))} "
            "consequence="
            f"{_single_line(finding.get('modification_consequence'))}"
        )

    return "\n".join(lines) + "\n"
