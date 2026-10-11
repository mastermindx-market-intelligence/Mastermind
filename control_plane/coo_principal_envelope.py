"""Pure COO principal envelope derivation for the existing Executive sink.

This is a pre-sink construction law only. It creates no Job/Event, opens no
Runtime, authenticates no OAuth token, selects no provider/host/account, reads
no clock, persists no state, and grants no source/release authority.

Public semantics come from control_plane.coo_principal_request. Trusted code
supplies only immutable principal/mission admission identity plus grounding and
the existing workspace root. A later reviewed sink discriminator remains the
only authority that may accept this envelope into Executive Runtime.
"""
from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from typing import Any

from control_plane import ceo_intent, ceo_request
from control_plane.coo_principal_request import (
    normalize_principal_request,
    principal_intent_id,
    principal_request_ref,
)


INTENT_SCHEMA = "mastermind.executive_principal_intent.v1"
ACTOR = "coo-principal"
SEAT = "coo"

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{1,255}$")
_WORK_REF_RE = re.compile(r"^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$")
_GROUNDING_KEYS = frozenset({"mastermind_sha", "macro_sha", "boot_packet_schema"})


class CooPrincipalEnvelopeError(ValueError):
    """Trusted principal-envelope derivation was refused."""


def _digest(value: object, field: str) -> str:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        raise CooPrincipalEnvelopeError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _ref(value: object, field: str, *, pattern: re.Pattern[str] = _REF_RE) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise CooPrincipalEnvelopeError(f"{field} is invalid")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class PrincipalAdmissionContext:
    """Immutable server-derived identity for one COO mission authority generation."""

    work_ref: str
    principal_binding_digest: str
    mission_authority_ref: str
    authority_generation_digest: str

    def __post_init__(self) -> None:
        _ref(self.work_ref, "work_ref", pattern=_WORK_REF_RE)
        _digest(self.principal_binding_digest, "principal_binding_digest")
        _ref(self.mission_authority_ref, "mission_authority_ref")
        _digest(self.authority_generation_digest, "authority_generation_digest")


def _grounding(value: object) -> dict[str, Any]:
    """Validate the existing two-SHA grounding shape without discovering state."""

    if not isinstance(value, Mapping):
        raise CooPrincipalEnvelopeError("grounding must be an object")
    keys = set(value)
    required = {"mastermind_sha", "macro_sha"}
    missing = sorted(required - keys)
    unexpected = sorted(keys - _GROUNDING_KEYS)
    if missing:
        raise CooPrincipalEnvelopeError(
            f"grounding is missing required field(s): {missing}"
        )
    if unexpected:
        raise CooPrincipalEnvelopeError(
            f"grounding has unexpected field(s): {unexpected}"
        )

    result: dict[str, Any] = {}
    for key in ("macro_sha", "mastermind_sha"):
        sha = value[key]
        if type(sha) is not str or ceo_intent.SHA_RE.fullmatch(sha) is None:
            raise CooPrincipalEnvelopeError(
                f"grounding.{key} must be a full 40-character lowercase Git SHA"
            )
        result[key] = sha

    if "boot_packet_schema" in value:
        schema = value["boot_packet_schema"]
        if (
            type(schema) is not str
            or not schema
            or len(schema) > 128
            or any(ord(char) < 32 or ord(char) == 127 for char in schema)
        ):
            raise CooPrincipalEnvelopeError("grounding.boot_packet_schema is invalid")
        result["boot_packet_schema"] = schema
    return result


def _execution_contract(
    normalized_request: Mapping[str, Any],
    *,
    intent_id: str,
    workspace_root: str,
) -> dict[str, Any]:
    """Reuse the incumbent worker-profile derivations without CEO provenance."""

    try:
        authorities = ceo_request.derive_authorities(
            str(normalized_request["execution_profile"])
        )
        branch = ceo_request.derive_branch(intent_id)
        worktree = ceo_request.derive_worktree(workspace_root, intent_id)
        commands = ceo_request.build_validation_commands(
            normalized_request.get("validation")
        )
    except ceo_request.CeoRequestError as exc:
        raise CooPrincipalEnvelopeError(
            "trusted worker-profile derivation is inconsistent"
        ) from exc

    contract: dict[str, Any] = {
        "requested_authorities": authorities,
        "authority_level": ceo_request.AUTHORITY_LEVEL,
        "branch": branch,
        "worktree": worktree,
        "attempt_limit": int(normalized_request["attempt_limit"]),
    }
    paths = list(normalized_request.get("allowed_write_paths") or [])
    if paths:
        contract["allowed_write_paths"] = paths
    if commands:
        contract["validation_commands"] = commands
    return contract


def derive_principal_envelope(
    public_request: object,
    *,
    context: PrincipalAdmissionContext,
    workspace_root: str,
    grounding: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the exact server-derived pre-sink COO principal envelope bundle."""

    if not isinstance(context, PrincipalAdmissionContext):
        raise TypeError("context must be PrincipalAdmissionContext")

    try:
        normalized = normalize_principal_request(
            public_request,
            expected_work_ref=context.work_ref,
        )
        request_ref = principal_request_ref(normalized)
        intent_id = principal_intent_id(request_ref)
    except ValueError as exc:
        raise CooPrincipalEnvelopeError(str(exc)) from exc

    if normalized["workstream"] != context.work_ref:
        raise CooPrincipalEnvelopeError(
            "normalized workstream differs from principal admission context"
        )

    envelope = {
        "schema": INTENT_SCHEMA,
        "intent_id": intent_id,
        "actor": ACTOR,
        "seat": SEAT,
        "principal_binding_digest": context.principal_binding_digest,
        "mission_authority_ref": context.mission_authority_ref,
        "authority_generation_digest": context.authority_generation_digest,
        "objective": str(normalized["objective"]),
        "department": str(normalized["department"]),
        "priority": int(normalized["priority"]),
        "workstream": str(normalized["workstream"]),
        "grounding": _grounding(grounding),
        "execution_contract": _execution_contract(
            normalized,
            intent_id=intent_id,
            workspace_root=workspace_root,
        ),
    }

    return {
        "request_ref": request_ref,
        "intent_id": intent_id,
        "normalized_request": normalized,
        "envelope": envelope,
    }


__all__ = [
    "ACTOR",
    "INTENT_SCHEMA",
    "SEAT",
    "CooPrincipalEnvelopeError",
    "PrincipalAdmissionContext",
    "derive_principal_envelope",
]
