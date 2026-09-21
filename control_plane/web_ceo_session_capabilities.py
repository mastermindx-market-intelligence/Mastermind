"""Fail-closed effective-tool preflight for attended Web CEO placement.

This module closes one narrow gap between Web-session observation and the
existing Capacity placement/commitment path. It does not discover ChatGPT
tools, grant authority, mutate Capacity, create RuntimeBindings, select a
provider, or perform a retry/failover. It consumes a point-in-time, exact
session-bound capability receipt produced by an accepted surface/tool observer
and determines whether the already-selected attended Web CEO may cross the
pre-START placement-commitment boundary.

The important asymmetry is deliberate:

* an absent required capability may exclude a PRE_START/effect=NONE candidate;
* an unknown capability never widens authority or causes automatic rebinding;
* schema presence alone never proves a positive capability; a successful
  current-generation no-effect serviceability probe is required;
* after START, or while an effect is unknown, the current binding stays sticky.

The real effectful consumer is still the existing Capacity-C2 commitment
contract. The guarded commitment helper simply refuses to call that owner
unless this preflight is READY and bound to the exact selected worker/quota
identity.
"""
from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from control_plane import executive_placement_commitment as c2
from control_plane import executive_placement_selection as c1
from control_plane.executive_steward import EffectState


RECEIPT_SCHEMA = "mastermind.web_ceo_session_capability_receipt.v1"
PREFLIGHT_SCHEMA = "mastermind.web_ceo_session_capability_preflight.v1"
MAX_RECEIPT_TTL_MS = 300_000

_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CAPABILITY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")

_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "worker_id",
        "quota_class",
        "session_ref",
        "binding_ref",
        "binding_generation",
        "observed_at_ms",
        "expires_at_ms",
        "schema_complete",
        "tool_schema_digest",
        "observations",
        "evidence_digest",
    }
)
_OBSERVATION_KEYS = frozenset({"name", "state", "proof_class"})

KNOWN_EFFECTIVE_CAPABILITIES = (
    "desktop_commander_command",
    "desktop_commander_read",
    "desktop_commander_write",
    "executive_read",
    "executive_submit",
    "github_read",
    "github_write",
    "studio_direct_command",
    "studio_direct_read",
    "studio_direct_write",
)

CAPABILITY_FAMILIES = {
    "desktop_commander_command": "desktop_commander",
    "desktop_commander_read": "desktop_commander",
    "desktop_commander_write": "desktop_commander",
    "executive_read": "executive",
    "executive_submit": "executive",
    "github_read": "github",
    "github_write": "github",
    "studio_direct_command": "studio_direct",
    "studio_direct_read": "studio_direct",
    "studio_direct_write": "studio_direct",
}
SERVICEABILITY_FAMILIES = frozenset(CAPABILITY_FAMILIES.values())


class WebCeoSessionCapabilityError(ValueError):
    """Fixed, secret-safe refusal for Web CEO capability-preflight input."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _ValueEnum(str, enum.Enum):
    """String enum whose value is the public wire value."""


class CapabilityObservationState(_ValueEnum):
    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"


class CapabilityProofClass(_ValueEnum):
    EFFECTIVE_SCHEMA = "effective_schema"
    NO_EFFECT_PROBE = "no_effect_probe"


class SessionStartState(_ValueEnum):
    PRE_START = "pre_start"
    STARTED = "started"


class PreflightState(_ValueEnum):
    READY = "ready"
    CAPABILITY_PROOF_REQUIRED = "capability_proof_required"
    PRESTART_REBIND_REQUIRED = "prestart_rebind_required"
    STICKY_DEGRADED = "sticky_degraded"
    STARTED_STICKY = "started_sticky"
    STALE_EVIDENCE = "stale_evidence"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    EFFECT_UNKNOWN = "effect_unknown"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _token(value: object, *, code: str) -> str:
    if not isinstance(value, str) or _TOKEN_RE.fullmatch(value) is None:
        raise WebCeoSessionCapabilityError(code)
    return value


def _capability(value: object) -> str:
    if not isinstance(value, str) or _CAPABILITY_RE.fullmatch(value) is None:
        raise WebCeoSessionCapabilityError("CAPABILITY_NAME_INVALID")
    return value


def _positive_int(value: object, *, code: str) -> int:
    if type(value) is not int or value < 1:
        raise WebCeoSessionCapabilityError(code)
    return value


def _enum(value: object, enum_type: type[_ValueEnum], *, code: str) -> _ValueEnum:
    if not isinstance(value, enum_type):
        raise WebCeoSessionCapabilityError(code)
    return value


def _tool_name(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 256
        or any(char.isspace() or ord(char) < 32 for char in value)
    ):
        raise WebCeoSessionCapabilityError("EFFECTIVE_TOOL_NAME_INVALID")
    return value


def _family_action_present(
    tool_names: tuple[str, ...],
    *,
    family_prefix: str,
    actions: frozenset[str],
) -> bool:
    return any(
        name.startswith(family_prefix)
        and any(name.endswith("__" + action) for action in actions)
        for name in tool_names
    )


def _capabilities_from_effective_tool_schema(
    tool_names: tuple[str, ...],
) -> dict[str, bool]:
    github_prefix = "mcp__GitHub__"
    executive_prefix = "mcp__Mastermind_Executive"
    studio_prefix = "mcp__Studio_Direct"
    desktop_prefix = "mcp__Remote_Desktop_Commander__"
    return {
        "github_read": _family_action_present(
            tool_names,
            family_prefix=github_prefix,
            actions=frozenset({"fetch", "fetch_file", "search"}),
        ),
        "github_write": _family_action_present(
            tool_names,
            family_prefix=github_prefix,
            actions=frozenset(
                {
                    "create_file",
                    "update_file",
                    "delete_file",
                    "create_pull_request",
                    "merge_pull_request",
                }
            ),
        ),
        "executive_read": _family_action_present(
            tool_names,
            family_prefix=executive_prefix,
            actions=frozenset({"executive_state", "executive_inbox", "executive_job"}),
        ),
        "executive_submit": _family_action_present(
            tool_names,
            family_prefix=executive_prefix,
            actions=frozenset({"submit_ceo_intent"}),
        ),
        "studio_direct_read": _family_action_present(
            tool_names,
            family_prefix=studio_prefix,
            actions=frozenset({"get_config", "read_file", "list_directory"}),
        ),
        "studio_direct_write": _family_action_present(
            tool_names,
            family_prefix=studio_prefix,
            actions=frozenset({"write_file", "edit_block", "move_file"}),
        ),
        "studio_direct_command": _family_action_present(
            tool_names,
            family_prefix=studio_prefix,
            actions=frozenset({"start_process"}),
        ),
        "desktop_commander_read": _family_action_present(
            tool_names,
            family_prefix=desktop_prefix,
            actions=frozenset({"get_config", "read_file", "list_directory"}),
        ),
        "desktop_commander_write": _family_action_present(
            tool_names,
            family_prefix=desktop_prefix,
            actions=frozenset({"write_file", "edit_block", "move_file"}),
        ),
        "desktop_commander_command": _family_action_present(
            tool_names,
            family_prefix=desktop_prefix,
            actions=frozenset({"start_process"}),
        ),
    }


@dataclasses.dataclass(frozen=True, slots=True)
class CapabilityObservation:
    """One capability observation, with a closed non-prose proof class."""

    name: str
    state: CapabilityObservationState
    proof_class: CapabilityProofClass

    def __post_init__(self) -> None:
        _capability(self.name)
        _enum(
            self.state,
            CapabilityObservationState,
            code="CAPABILITY_OBSERVATION_STATE_INVALID",
        )
        _enum(
            self.proof_class,
            CapabilityProofClass,
            code="CAPABILITY_PROOF_CLASS_INVALID",
        )
        if (
            self.state is CapabilityObservationState.PRESENT
            and self.proof_class is not CapabilityProofClass.NO_EFFECT_PROBE
        ):
            raise WebCeoSessionCapabilityError(
                "PRESENT_REQUIRES_SERVICEABILITY_PROOF"
            )
        if (
            self.state is CapabilityObservationState.ABSENT
            and self.proof_class is not CapabilityProofClass.EFFECTIVE_SCHEMA
        ):
            raise WebCeoSessionCapabilityError("ABSENCE_REQUIRES_SCHEMA_PROOF")

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "state": self.state.value,
            "proof_class": self.proof_class.value,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class WebCeoSessionCapabilityReceipt:
    """Exact-session point-in-time effective-tool evidence.

    schema_complete means the source supplied a complete effective tool schema
    for the exact observed session generation. Only such a receipt may prove
    absence; a failed/no-effect probe can prove presence or uncertainty but
    cannot prove that an unobserved tool is absent.
    """

    worker_id: str
    quota_class: str
    session_ref: str
    binding_ref: str
    binding_generation: int
    observed_at_ms: int
    expires_at_ms: int
    schema_complete: bool
    tool_schema_digest: str
    observations: tuple[CapabilityObservation, ...]

    def __post_init__(self) -> None:
        _token(self.worker_id, code="WORKER_ID_INVALID")
        _token(self.quota_class, code="QUOTA_CLASS_INVALID")
        _token(self.session_ref, code="SESSION_REF_INVALID")
        _token(self.binding_ref, code="BINDING_REF_INVALID")
        _positive_int(self.binding_generation, code="BINDING_GENERATION_INVALID")
        observed = _positive_int(self.observed_at_ms, code="OBSERVED_AT_INVALID")
        expires = _positive_int(self.expires_at_ms, code="EXPIRES_AT_INVALID")
        if expires < observed or expires - observed > MAX_RECEIPT_TTL_MS:
            raise WebCeoSessionCapabilityError("CAPABILITY_RECEIPT_TTL_INVALID")
        if type(self.schema_complete) is not bool:
            raise WebCeoSessionCapabilityError("SCHEMA_COMPLETENESS_INVALID")
        if (
            not isinstance(self.tool_schema_digest, str)
            or _DIGEST_RE.fullmatch(self.tool_schema_digest) is None
        ):
            raise WebCeoSessionCapabilityError("TOOL_SCHEMA_DIGEST_INVALID")
        if not isinstance(self.observations, tuple):
            raise WebCeoSessionCapabilityError("CAPABILITY_OBSERVATIONS_INVALID")
        normalized: list[CapabilityObservation] = []
        names: set[str] = set()
        for item in self.observations:
            if not isinstance(item, CapabilityObservation):
                raise WebCeoSessionCapabilityError("CAPABILITY_OBSERVATIONS_INVALID")
            if item.name in names:
                raise WebCeoSessionCapabilityError("DUPLICATE_CAPABILITY_OBSERVATION")
            if (
                item.state is CapabilityObservationState.ABSENT
                and not self.schema_complete
            ):
                raise WebCeoSessionCapabilityError(
                    "ABSENCE_REQUIRES_COMPLETE_SCHEMA"
                )
            names.add(item.name)
            normalized.append(item)
        normalized.sort(key=lambda item: item.name)
        object.__setattr__(self, "observations", tuple(normalized))

    def _evidence_body(self) -> dict[str, Any]:
        return {
            "schema_version": RECEIPT_SCHEMA,
            "worker_id": self.worker_id,
            "quota_class": self.quota_class,
            "session_ref": self.session_ref,
            "binding_ref": self.binding_ref,
            "binding_generation": self.binding_generation,
            "observed_at_ms": self.observed_at_ms,
            "expires_at_ms": self.expires_at_ms,
            "schema_complete": self.schema_complete,
            "tool_schema_digest": self.tool_schema_digest,
            "observations": [item.to_dict() for item in self.observations],
        }

    @property
    def evidence_digest(self) -> str:
        return _digest(self._evidence_body())

    def to_dict(self) -> dict[str, Any]:
        value = self._evidence_body()
        value["evidence_digest"] = self.evidence_digest
        return value


def build_receipt_from_effective_tool_schema(
    *,
    tool_names: Sequence[str],
    worker_id: str,
    quota_class: str,
    session_ref: str,
    binding_ref: str,
    binding_generation: int,
    observed_at_ms: int,
    expires_at_ms: int,
    family_serviceability: Mapping[str, bool] | None = None,
) -> WebCeoSessionCapabilityReceipt:
    """Derive capability evidence from schema plus no-effect serviceability.

    A complete effective schema may prove that a capability is absent. It may
    not prove that a visible connector is actually usable. Positive capability
    therefore requires a successful current-generation no-effect serviceability
    probe for that connector family. Failed or unprobed serviceability remains
    UNKNOWN and cannot cross the placement commitment fence.

    family_serviceability is deliberately coarse to connector families, never
    organizational permission. It says only whether a safe read or health probe
    for that exact current family generation succeeded.
    """

    if isinstance(tool_names, (str, bytes)) or not isinstance(tool_names, Sequence):
        raise WebCeoSessionCapabilityError("EFFECTIVE_TOOL_SCHEMA_INVALID")
    normalized = tuple(sorted(_tool_name(item) for item in tool_names))
    if len(set(normalized)) != len(normalized):
        raise WebCeoSessionCapabilityError("DUPLICATE_EFFECTIVE_TOOL_NAME")
    effective = _capabilities_from_effective_tool_schema(normalized)
    if tuple(sorted(effective)) != KNOWN_EFFECTIVE_CAPABILITIES:
        raise WebCeoSessionCapabilityError("EFFECTIVE_CAPABILITY_MAP_INVALID")

    if family_serviceability is None:
        probes: dict[str, bool] = {}
    elif isinstance(family_serviceability, Mapping):
        probes = dict(family_serviceability)
    else:
        raise WebCeoSessionCapabilityError("SERVICEABILITY_PROBES_INVALID")
    if any(
        family not in SERVICEABILITY_FAMILIES or type(result) is not bool
        for family, result in probes.items()
    ):
        raise WebCeoSessionCapabilityError("SERVICEABILITY_PROBES_INVALID")
    for family, result in probes.items():
        if result and not any(
            effective[name]
            for name in KNOWN_EFFECTIVE_CAPABILITIES
            if CAPABILITY_FAMILIES[name] == family
        ):
            raise WebCeoSessionCapabilityError(
                "SERVICEABILITY_PROBE_WITHOUT_SURFACE"
            )

    observations: list[CapabilityObservation] = []
    for name in KNOWN_EFFECTIVE_CAPABILITIES:
        if not effective[name]:
            state = CapabilityObservationState.ABSENT
            proof = CapabilityProofClass.EFFECTIVE_SCHEMA
        else:
            probe = probes.get(CAPABILITY_FAMILIES[name])
            if probe is True:
                state = CapabilityObservationState.PRESENT
                proof = CapabilityProofClass.NO_EFFECT_PROBE
            elif probe is False:
                state = CapabilityObservationState.UNKNOWN
                proof = CapabilityProofClass.NO_EFFECT_PROBE
            else:
                state = CapabilityObservationState.UNKNOWN
                proof = CapabilityProofClass.EFFECTIVE_SCHEMA
        observations.append(
            CapabilityObservation(name=name, state=state, proof_class=proof)
        )

    return WebCeoSessionCapabilityReceipt(
        worker_id=worker_id,
        quota_class=quota_class,
        session_ref=session_ref,
        binding_ref=binding_ref,
        binding_generation=binding_generation,
        observed_at_ms=observed_at_ms,
        expires_at_ms=expires_at_ms,
        schema_complete=True,
        tool_schema_digest=_digest({"tool_names": list(normalized)}),
        observations=tuple(observations),
    )


def build_receipt_from_negative_schema_projection(
    *,
    absent_capabilities: Sequence[str],
    tool_schema_digest: str,
    worker_id: str,
    quota_class: str,
    session_ref: str,
    binding_ref: str,
    binding_generation: int,
    observed_at_ms: int,
    expires_at_ms: int,
) -> WebCeoSessionCapabilityReceipt:
    """Consume a complete-schema, negative-only exact-session projection.

    This seam exists for transports that can attribute one finished turn to an
    exact RuntimeBinding but must not expose raw transcript or raw tool names.
    The projection may remove capabilities from eligibility only. Every closed
    capability not declared absent remains UNKNOWN; this function can never
    mint PRESENT or grant authority.

    absent_capabilities MUST be the complete absent subset of the closed
    KNOWN_EFFECTIVE_CAPABILITIES vocabulary for the observed schema generation,
    not merely the current demand's missing subset.
    """

    if (
        isinstance(absent_capabilities, (str, bytes))
        or not isinstance(absent_capabilities, Sequence)
    ):
        raise WebCeoSessionCapabilityError(
            "NEGATIVE_SCHEMA_PROJECTION_INVALID"
        )
    absent = tuple(sorted(_capability(item) for item in absent_capabilities))
    if not absent or len(set(absent)) != len(absent):
        raise WebCeoSessionCapabilityError(
            "NEGATIVE_SCHEMA_PROJECTION_INVALID"
        )
    if any(item not in KNOWN_EFFECTIVE_CAPABILITIES for item in absent):
        raise WebCeoSessionCapabilityError(
            "NEGATIVE_CAPABILITY_OUTSIDE_CLOSED_SET"
        )
    if (
        not isinstance(tool_schema_digest, str)
        or _DIGEST_RE.fullmatch(tool_schema_digest) is None
    ):
        raise WebCeoSessionCapabilityError("TOOL_SCHEMA_DIGEST_INVALID")

    observations = tuple(
        CapabilityObservation(
            name=name,
            state=(
                CapabilityObservationState.ABSENT
                if name in absent
                else CapabilityObservationState.UNKNOWN
            ),
            proof_class=CapabilityProofClass.EFFECTIVE_SCHEMA,
        )
        for name in KNOWN_EFFECTIVE_CAPABILITIES
    )
    return WebCeoSessionCapabilityReceipt(
        worker_id=worker_id,
        quota_class=quota_class,
        session_ref=session_ref,
        binding_ref=binding_ref,
        binding_generation=binding_generation,
        observed_at_ms=observed_at_ms,
        expires_at_ms=expires_at_ms,
        schema_complete=True,
        tool_schema_digest=tool_schema_digest,
        observations=observations,
    )


@dataclasses.dataclass(frozen=True, slots=True)
class WebCeoCapabilityPreflightDecision:
    """Machine-readable pre-START fence; never a placement commitment."""

    state: PreflightState
    worker_id: str
    quota_class: str
    session_ref: str
    binding_ref: str
    binding_generation: int
    required_capabilities: tuple[str, ...]
    proven_capabilities: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    unknown_capabilities: tuple[str, ...]
    evidence_digest: str
    rebind_allowed: bool
    exclusion: dict[str, str] | None
    selection_is_commitment: bool = False

    def __post_init__(self) -> None:
        _enum(self.state, PreflightState, code="PREFLIGHT_STATE_INVALID")
        _token(self.worker_id, code="WORKER_ID_INVALID")
        _token(self.quota_class, code="QUOTA_CLASS_INVALID")
        _token(self.session_ref, code="SESSION_REF_INVALID")
        _token(self.binding_ref, code="BINDING_REF_INVALID")
        _positive_int(self.binding_generation, code="BINDING_GENERATION_INVALID")
        if (
            not isinstance(self.evidence_digest, str)
            or _DIGEST_RE.fullmatch(self.evidence_digest) is None
        ):
            raise WebCeoSessionCapabilityError("EVIDENCE_DIGEST_INVALID")
        for field in (
            self.required_capabilities,
            self.proven_capabilities,
            self.missing_capabilities,
            self.unknown_capabilities,
        ):
            if not isinstance(field, tuple):
                raise WebCeoSessionCapabilityError("PREFLIGHT_CAPABILITY_SET_INVALID")
            if tuple(sorted(field)) != field or len(set(field)) != len(field):
                raise WebCeoSessionCapabilityError("PREFLIGHT_CAPABILITY_SET_INVALID")
            for item in field:
                _capability(item)
        if type(self.rebind_allowed) is not bool:
            raise WebCeoSessionCapabilityError("REBIND_FLAG_INVALID")
        if self.selection_is_commitment is not False:
            raise WebCeoSessionCapabilityError("PREFLIGHT_CANNOT_BE_COMMITMENT")
        if self.rebind_allowed:
            expected = {
                "worker_id": self.worker_id,
                "quota_class": self.quota_class,
                "reason": "effective_capability_missing",
            }
            if self.state is not PreflightState.PRESTART_REBIND_REQUIRED:
                raise WebCeoSessionCapabilityError("REBIND_STATE_INVALID")
            if self.exclusion != expected:
                raise WebCeoSessionCapabilityError("REBIND_EXCLUSION_INVALID")
        elif self.exclusion is not None:
            raise WebCeoSessionCapabilityError("REBIND_EXCLUSION_INVALID")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PREFLIGHT_SCHEMA,
            "state": self.state.value,
            "worker_id": self.worker_id,
            "quota_class": self.quota_class,
            "session_ref": self.session_ref,
            "binding_ref": self.binding_ref,
            "binding_generation": self.binding_generation,
            "required_capabilities": list(self.required_capabilities),
            "proven_capabilities": list(self.proven_capabilities),
            "missing_capabilities": list(self.missing_capabilities),
            "unknown_capabilities": list(self.unknown_capabilities),
            "evidence_digest": self.evidence_digest,
            "rebind_allowed": self.rebind_allowed,
            "exclusion": dict(self.exclusion) if self.exclusion is not None else None,
            "selection_is_commitment": False,
        }


def validate_session_capability_receipt(
    value: object,
) -> WebCeoSessionCapabilityReceipt:
    """Rebuild one closed receipt and verify its canonical digest."""

    if not isinstance(value, Mapping):
        raise WebCeoSessionCapabilityError("CAPABILITY_RECEIPT_SHAPE_INVALID")
    raw = dict(value)
    if set(raw) != _RECEIPT_KEYS:
        raise WebCeoSessionCapabilityError("CAPABILITY_RECEIPT_SHAPE_INVALID")
    if raw.get("schema_version") != RECEIPT_SCHEMA:
        raise WebCeoSessionCapabilityError("CAPABILITY_RECEIPT_SCHEMA_INVALID")
    observations_raw = raw.get("observations")
    if not isinstance(observations_raw, list):
        raise WebCeoSessionCapabilityError("CAPABILITY_RECEIPT_SHAPE_INVALID")
    observations: list[CapabilityObservation] = []
    for item in observations_raw:
        if not isinstance(item, Mapping) or set(item) != _OBSERVATION_KEYS:
            raise WebCeoSessionCapabilityError("CAPABILITY_RECEIPT_SHAPE_INVALID")
        try:
            state = CapabilityObservationState(item["state"])
            proof = CapabilityProofClass(item["proof_class"])
        except (KeyError, TypeError, ValueError) as exc:
            raise WebCeoSessionCapabilityError(
                "CAPABILITY_RECEIPT_SHAPE_INVALID"
            ) from exc
        observations.append(
            CapabilityObservation(
                name=item["name"],
                state=state,
                proof_class=proof,
            )
        )
    receipt = WebCeoSessionCapabilityReceipt(
        worker_id=raw["worker_id"],
        quota_class=raw["quota_class"],
        session_ref=raw["session_ref"],
        binding_ref=raw["binding_ref"],
        binding_generation=raw["binding_generation"],
        observed_at_ms=raw["observed_at_ms"],
        expires_at_ms=raw["expires_at_ms"],
        schema_complete=raw["schema_complete"],
        tool_schema_digest=raw["tool_schema_digest"],
        observations=tuple(observations),
    )
    if raw["evidence_digest"] != receipt.evidence_digest:
        raise WebCeoSessionCapabilityError("CAPABILITY_RECEIPT_DIGEST_MISMATCH")
    return receipt


def _decision(
    *,
    state: PreflightState,
    receipt: WebCeoSessionCapabilityReceipt,
    required: tuple[str, ...],
    proven: tuple[str, ...],
    missing: tuple[str, ...],
    unknown: tuple[str, ...],
    rebind_allowed: bool = False,
) -> WebCeoCapabilityPreflightDecision:
    exclusion = (
        {
            "worker_id": receipt.worker_id,
            "quota_class": receipt.quota_class,
            "reason": "effective_capability_missing",
        }
        if rebind_allowed
        else None
    )
    return WebCeoCapabilityPreflightDecision(
        state=state,
        worker_id=receipt.worker_id,
        quota_class=receipt.quota_class,
        session_ref=receipt.session_ref,
        binding_ref=receipt.binding_ref,
        binding_generation=receipt.binding_generation,
        required_capabilities=required,
        proven_capabilities=proven,
        missing_capabilities=missing,
        unknown_capabilities=unknown,
        evidence_digest=receipt.evidence_digest,
        rebind_allowed=rebind_allowed,
        exclusion=exclusion,
    )


def assess_web_ceo_session_capabilities(
    *,
    receipt: WebCeoSessionCapabilityReceipt,
    required_capabilities: frozenset[str],
    expected_worker_id: str,
    expected_quota_class: str,
    expected_session_ref: str,
    expected_binding_ref: str,
    expected_binding_generation: int,
    now_ms: int,
    start_state: SessionStartState,
    effect_state: EffectState,
) -> WebCeoCapabilityPreflightDecision:
    """Assess exact-session effective tools without reading clocks or tools."""

    if not isinstance(receipt, WebCeoSessionCapabilityReceipt):
        raise WebCeoSessionCapabilityError("CAPABILITY_RECEIPT_INVALID")
    if not isinstance(required_capabilities, frozenset) or not required_capabilities:
        raise WebCeoSessionCapabilityError("REQUIRED_CAPABILITIES_INVALID")
    required = tuple(sorted(_capability(item) for item in required_capabilities))
    _token(expected_worker_id, code="EXPECTED_WORKER_ID_INVALID")
    _token(expected_quota_class, code="EXPECTED_QUOTA_CLASS_INVALID")
    _token(expected_session_ref, code="EXPECTED_SESSION_REF_INVALID")
    _token(expected_binding_ref, code="EXPECTED_BINDING_REF_INVALID")
    _positive_int(
        expected_binding_generation,
        code="EXPECTED_BINDING_GENERATION_INVALID",
    )
    current_ms = _positive_int(now_ms, code="CURRENT_TIME_INVALID")
    _enum(start_state, SessionStartState, code="SESSION_START_STATE_INVALID")
    if not isinstance(effect_state, EffectState):
        raise WebCeoSessionCapabilityError("EFFECT_STATE_INVALID")

    observed = {item.name: item for item in receipt.observations}
    proven: list[str] = []
    missing: list[str] = []
    unknown: list[str] = []
    for name in required:
        item = observed.get(name)
        if item is None:
            if receipt.schema_complete:
                missing.append(name)
            else:
                unknown.append(name)
        elif item.state is CapabilityObservationState.PRESENT:
            proven.append(name)
        elif item.state is CapabilityObservationState.ABSENT:
            missing.append(name)
        else:
            unknown.append(name)
    proven_tuple = tuple(proven)
    missing_tuple = tuple(missing)
    unknown_tuple = tuple(unknown)

    if (
        receipt.worker_id != expected_worker_id
        or receipt.quota_class != expected_quota_class
        or receipt.session_ref != expected_session_ref
        or receipt.binding_ref != expected_binding_ref
        or receipt.binding_generation != expected_binding_generation
    ):
        return _decision(
            state=PreflightState.RECONCILIATION_REQUIRED,
            receipt=receipt,
            required=required,
            proven=proven_tuple,
            missing=missing_tuple,
            unknown=unknown_tuple,
        )

    if effect_state is EffectState.EFFECT_UNKNOWN:
        return _decision(
            state=PreflightState.EFFECT_UNKNOWN,
            receipt=receipt,
            required=required,
            proven=proven_tuple,
            missing=missing_tuple,
            unknown=unknown_tuple,
        )

    if current_ms < receipt.observed_at_ms or current_ms > receipt.expires_at_ms:
        return _decision(
            state=PreflightState.STALE_EVIDENCE,
            receipt=receipt,
            required=required,
            proven=proven_tuple,
            missing=missing_tuple,
            unknown=unknown_tuple,
        )

    if (
        start_state is SessionStartState.PRE_START
        and effect_state is not EffectState.NONE
    ):
        return _decision(
            state=PreflightState.RECONCILIATION_REQUIRED,
            receipt=receipt,
            required=required,
            proven=proven_tuple,
            missing=missing_tuple,
            unknown=unknown_tuple,
        )

    # A proven required absence is dispositive: the candidate cannot satisfy
    # the accepted demand even if sibling required capabilities are still
    # UNKNOWN. Before START with no effect, exclude/rebind now rather than
    # waiting for irrelevant positive proof. After START the same known
    # absence is sticky degradation and never authorizes carrier movement.
    if missing_tuple:
        if (
            start_state is SessionStartState.PRE_START
            and effect_state is EffectState.NONE
        ):
            return _decision(
                state=PreflightState.PRESTART_REBIND_REQUIRED,
                receipt=receipt,
                required=required,
                proven=proven_tuple,
                missing=missing_tuple,
                unknown=unknown_tuple,
                rebind_allowed=True,
            )
        return _decision(
            state=PreflightState.STICKY_DEGRADED,
            receipt=receipt,
            required=required,
            proven=proven_tuple,
            missing=missing_tuple,
            unknown=unknown_tuple,
        )

    if unknown_tuple:
        return _decision(
            state=PreflightState.CAPABILITY_PROOF_REQUIRED,
            receipt=receipt,
            required=required,
            proven=proven_tuple,
            missing=missing_tuple,
            unknown=unknown_tuple,
        )

    if start_state is SessionStartState.STARTED:
        return _decision(
            state=PreflightState.STARTED_STICKY,
            receipt=receipt,
            required=required,
            proven=proven_tuple,
            missing=missing_tuple,
            unknown=unknown_tuple,
        )

    return _decision(
        state=PreflightState.READY,
        receipt=receipt,
        required=required,
        proven=proven_tuple,
        missing=missing_tuple,
        unknown=unknown_tuple,
    )


def build_guarded_commitment_plan_from_selection_decision(
    *,
    source_root_job_id: str,
    expected_source_root_revision: int,
    placement_selection: c1.PlacementSelectionDecision,
    validated_target_facts: Any,
    capability_preflight: WebCeoCapabilityPreflightDecision,
) -> c2.PlacementCommitmentPlan:
    """Call existing C2 commitment only after an exact READY preflight."""

    if not isinstance(capability_preflight, WebCeoCapabilityPreflightDecision):
        raise WebCeoSessionCapabilityError("CAPABILITY_PREFLIGHT_INVALID")
    if capability_preflight.state is not PreflightState.READY:
        raise WebCeoSessionCapabilityError("CAPABILITY_PREFLIGHT_NOT_READY")
    if not isinstance(placement_selection, c1.PlacementSelectionDecision):
        raise WebCeoSessionCapabilityError("PLACEMENT_SELECTION_INVALID")
    wire = placement_selection.to_dict()
    selected = wire.get("selected")
    if not isinstance(selected, Mapping):
        raise WebCeoSessionCapabilityError("PLACEMENT_SELECTION_INVALID")
    if (
        selected.get("worker_id") != capability_preflight.worker_id
        or selected.get("quota_class") != capability_preflight.quota_class
    ):
        raise WebCeoSessionCapabilityError(
            "CAPABILITY_PREFLIGHT_SELECTION_MISMATCH"
        )
    return c2.build_commitment_plan_from_selection_decision(
        source_root_job_id=source_root_job_id,
        expected_source_root_revision=expected_source_root_revision,
        placement_selection=placement_selection,
        validated_target_facts=validated_target_facts,
    )


__all__ = [
    "CapabilityObservation",
    "CapabilityObservationState",
    "CapabilityProofClass",
    "KNOWN_EFFECTIVE_CAPABILITIES",
    "MAX_RECEIPT_TTL_MS",
    "PREFLIGHT_SCHEMA",
    "PreflightState",
    "RECEIPT_SCHEMA",
    "SessionStartState",
    "WebCeoCapabilityPreflightDecision",
    "WebCeoSessionCapabilityError",
    "WebCeoSessionCapabilityReceipt",
    "assess_web_ceo_session_capabilities",
    "build_guarded_commitment_plan_from_selection_decision",
    "build_receipt_from_effective_tool_schema",
    "build_receipt_from_negative_schema_projection",
    "validate_session_capability_receipt",
]
