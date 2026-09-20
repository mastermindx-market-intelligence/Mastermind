"""Seal one selected FP2 host qualification for atomic Runtime consumption.

FP2 proves feasibility and derives a Capacity-owned order, but its source
artifact intentionally retains only content-addressed qualification receipts.
The Runtime reservation owner needs the exact selected physical inputs as well.
This module closes that handoff without owning lifecycle, persistence,
reservation rows, BEGIN, transport, provider effects, retries, or host ranking.

A package may be minted only from one resolved v2 selection, the exact current
FP2 artifact/candidate set, and full inputs that reproduce the selected
qualification through the existing physical-resource owner.  Before a Runtime
transaction consumes the package, :meth:`SelectedPhysicalReservationPackage.evaluate_for_commit`
requires the selection, artifact, every qualified candidate, policy, charges,
and observations to remain byte-for-byte current, then reruns the existing
storeless reservation predicate at the commit time.  Any candidate movement
therefore invalidates the prior preference instead of silently reserving a
stale winner.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from control_plane.executive_capacity_join import (
    RegisteredCapacityJoin,
    validate_capacity_join,
)
from control_plane.executive_host_placement_preference import (
    HostCapacityPreferenceArtifact,
    QualifiedHostCandidate,
    qualify_host_candidate,
    validate_current_host_capacity_preference,
)
from control_plane.executive_physical_resources import (
    evaluate_reservation,
    validate_physical_request,
)
from control_plane.executive_placement_preference import (
    PREFERENCE_ADMISSIBLE,
    PlacementSelectionDecisionV2,
    validate_capacity_preference,
    validate_placement_selection_v2,
)
from control_plane.executive_placement_selection import (
    OccupancyState,
    PlacementCandidateFact,
    PlacementMode,
    SelectionState,
)
from control_plane.executive_steward import (
    CapacityState,
    EffectState,
    Freshness,
    SourceOwner,
    SourceRef,
)


PACKAGE_SCHEMA = "mastermind.selected_physical_reservation_package.v1"
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_PACKAGE_KEYS = frozenset(
    {
        "schema",
        "selection_v2",
        "capacity_source",
        "qualified_candidates",
        "selected_qualification",
        "reservation_input",
        "package_id",
    }
)
_RESERVATION_INPUT_KEYS = frozenset(
    {
        "placement_candidate",
        "registered_join",
        "capacity_observation",
        "request",
        "policy",
        "current_charges",
        "observations",
        "decision_time_ms",
    }
)
_SOURCE_KEYS = frozenset({"owner", "ref", "observed_at", "freshness"})
_CANDIDATE_KEYS = frozenset(
    {
        "worker_id",
        "provider",
        "account_label",
        "quota_class",
        "capabilities",
        "observed_at_ms",
        "occupancy",
        "occupancy_source",
        "capacity_state",
        "capacity_source",
        "host_source_closure_proven",
        "closure_source",
        "effect_state",
        "mode",
        "creation_surface_accessible",
        "session_creation_allowed",
    }
)
_REGISTERED_JOIN_KEYS = frozenset(
    {"worker_id", "quota_class", "provider", "capacity_join"}
)
_PACKAGE_SEAL = object()


class SelectedPhysicalReservationError(ValueError):
    """Closed refusal from the selected-reservation handoff."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _refuse(code: str) -> None:
    raise SelectedPhysicalReservationError(code)


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise SelectedPhysicalReservationError("PACKAGE_INVALID") from None


def _freeze(value: Any) -> Any:
    try:
        return json.loads(_canonical_bytes(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        raise SelectedPhysicalReservationError("PACKAGE_INVALID") from None


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _source_to_dict(source: SourceRef) -> dict[str, Any]:
    return {
        "owner": source.owner.value,
        "ref": source.ref,
        "observed_at": source.observed_at,
        "freshness": source.freshness.value,
    }


def _source_from_dict(value: object) -> SourceRef:
    if type(value) is not dict or set(value) != _SOURCE_KEYS:
        _refuse("PACKAGE_INVALID")
    try:
        return SourceRef(
            owner=SourceOwner(value["owner"]),
            ref=value["ref"],
            observed_at=value["observed_at"],
            freshness=Freshness(value["freshness"]),
        )
    except (KeyError, TypeError, ValueError):
        raise SelectedPhysicalReservationError("PACKAGE_INVALID") from None


def _candidate_to_dict(candidate: PlacementCandidateFact) -> dict[str, Any]:
    if not isinstance(candidate, PlacementCandidateFact):
        raise TypeError("placement_candidate must be PlacementCandidateFact")
    return {
        "worker_id": candidate.worker_id,
        "provider": candidate.provider,
        "account_label": candidate.account_label,
        "quota_class": candidate.quota_class,
        "capabilities": sorted(candidate.capabilities),
        "observed_at_ms": candidate.observed_at_ms,
        "occupancy": candidate.occupancy.value,
        "occupancy_source": _source_to_dict(candidate.occupancy_source),
        "capacity_state": candidate.capacity_state.value,
        "capacity_source": _source_to_dict(candidate.capacity_source),
        "host_source_closure_proven": candidate.host_source_closure_proven,
        "closure_source": _source_to_dict(candidate.closure_source),
        "effect_state": candidate.effect_state.value,
        "mode": candidate.mode.value,
        "creation_surface_accessible": candidate.creation_surface_accessible,
        "session_creation_allowed": candidate.session_creation_allowed,
    }


def _candidate_from_dict(value: object) -> PlacementCandidateFact:
    if type(value) is not dict or set(value) != _CANDIDATE_KEYS:
        _refuse("PACKAGE_INVALID")
    capabilities = value.get("capabilities")
    if (
        type(capabilities) is not list
        or not capabilities
        or any(type(item) is not str for item in capabilities)
        or capabilities != sorted(set(capabilities))
    ):
        _refuse("PACKAGE_INVALID")
    try:
        return PlacementCandidateFact(
            worker_id=value["worker_id"],
            provider=value["provider"],
            account_label=value["account_label"],
            quota_class=value["quota_class"],
            capabilities=frozenset(capabilities),
            observed_at_ms=value["observed_at_ms"],
            occupancy=OccupancyState(value["occupancy"]),
            occupancy_source=_source_from_dict(value["occupancy_source"]),
            capacity_state=CapacityState(value["capacity_state"]),
            capacity_source=_source_from_dict(value["capacity_source"]),
            host_source_closure_proven=value["host_source_closure_proven"],
            closure_source=_source_from_dict(value["closure_source"]),
            effect_state=EffectState(value["effect_state"]),
            mode=PlacementMode(value["mode"]),
            creation_surface_accessible=value["creation_surface_accessible"],
            session_creation_allowed=value["session_creation_allowed"],
        )
    except (KeyError, TypeError, ValueError):
        raise SelectedPhysicalReservationError("PACKAGE_INVALID") from None


def _registered_join_from_dict(value: object) -> RegisteredCapacityJoin:
    if type(value) is not dict or set(value) != _REGISTERED_JOIN_KEYS:
        _refuse("PACKAGE_INVALID")
    try:
        return RegisteredCapacityJoin(
            worker_id=value["worker_id"],
            quota_class=value["quota_class"],
            provider=value["provider"],
            capacity_join=validate_capacity_join(value["capacity_join"]),
        )
    except (KeyError, TypeError, ValueError):
        raise SelectedPhysicalReservationError("PACKAGE_INVALID") from None


def _sorted_candidate_wires(
    candidates: Sequence[QualifiedHostCandidate],
) -> list[dict[str, Any]]:
    if isinstance(candidates, (str, bytes)) or not isinstance(candidates, Sequence):
        _refuse("QUALIFIED_CANDIDATES_MOVED")
    frozen = tuple(candidates)
    if not frozen or any(not isinstance(row, QualifiedHostCandidate) for row in frozen):
        _refuse("QUALIFIED_CANDIDATES_MOVED")
    worker_ids = [row.worker_id for row in frozen]
    if len(worker_ids) != len(set(worker_ids)):
        _refuse("QUALIFIED_CANDIDATES_MOVED")
    return [row.to_dict() for row in sorted(frozen, key=lambda row: row.worker_id)]


def _package_without_id(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value[key]) for key in _PACKAGE_KEYS if key != "package_id"}


def _validate_wire(value: object) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _PACKAGE_KEYS:
        _refuse("PACKAGE_INVALID")
    package_id = value.get("package_id")
    if type(package_id) is not str or _DIGEST_RE.fullmatch(package_id) is None:
        _refuse("PACKAGE_INVALID")
    if package_id != _digest(_package_without_id(value)):
        _refuse("PACKAGE_ID_MISMATCH")
    if value.get("schema") != PACKAGE_SCHEMA:
        _refuse("PACKAGE_INVALID")

    capacity_source = value.get("capacity_source")
    if type(capacity_source) is not dict:
        _refuse("PACKAGE_INVALID")
    source_bytes = _canonical_bytes(capacity_source)
    selection_raw = value.get("selection_v2")
    if type(selection_raw) is not dict:
        _refuse("PACKAGE_INVALID")
    preference_raw = selection_raw.get("preference")
    try:
        preference = validate_capacity_preference(preference_raw)
        selection = validate_placement_selection_v2(
            selection_raw,
            resolved_capacity_sources={preference.capacity_source.ref: source_bytes},
        )
        artifact = HostCapacityPreferenceArtifact(
            preference=preference,
            source_bytes=source_bytes,
        )
    except (TypeError, ValueError):
        raise SelectedPhysicalReservationError("PACKAGE_INVALID") from None
    if (
        selection["state"] != SelectionState.SELECTED.value
        or selection["preference_admissibility"] != PREFERENCE_ADMISSIBLE
        or selection["selected"] is None
    ):
        _refuse("SELECTION_NOT_RESOLVED")

    qualified = value.get("qualified_candidates")
    if type(qualified) is not list or not qualified:
        _refuse("PACKAGE_INVALID")
    try:
        artifact_source = json.loads(artifact.source_bytes)
    except (TypeError, ValueError, UnicodeDecodeError):
        raise SelectedPhysicalReservationError("PACKAGE_INVALID") from None
    if qualified != artifact_source.get("candidates"):
        _refuse("PACKAGE_INVALID")
    selected_id = selection["selected"]["worker_id"]
    matches = [row for row in qualified if row.get("worker_id") == selected_id]
    if len(matches) != 1 or value.get("selected_qualification") != matches[0]:
        _refuse("SELECTED_INPUT_MISMATCH")

    reservation_input = value.get("reservation_input")
    if type(reservation_input) is not dict or set(reservation_input) != _RESERVATION_INPUT_KEYS:
        _refuse("PACKAGE_INVALID")
    placement_candidate = _candidate_from_dict(
        reservation_input.get("placement_candidate")
    )
    registered_join = _registered_join_from_dict(
        reservation_input.get("registered_join")
    )
    request_raw = reservation_input.get("request")
    try:
        normalized_request = validate_physical_request(request_raw)
    except (TypeError, ValueError):
        raise SelectedPhysicalReservationError("PACKAGE_INVALID") from None
    if normalized_request != request_raw:
        _refuse("PACKAGE_INVALID")
    policy = reservation_input.get("policy")
    current_charges = reservation_input.get("current_charges")
    observations = reservation_input.get("observations")
    decision_time_ms = reservation_input.get("decision_time_ms")
    if (
        type(policy) is not dict
        or type(current_charges) is not list
        or type(observations) is not dict
        or type(decision_time_ms) is not int
        or decision_time_ms < 0
        or type(reservation_input.get("capacity_observation")) is not dict
    ):
        _refuse("PACKAGE_INVALID")
    try:
        reproduced = qualify_host_candidate(
            placement_candidate=placement_candidate,
            registered_join=registered_join,
            capacity_observation=reservation_input["capacity_observation"],
            request=normalized_request,
            policy=policy,
            current_charges=current_charges,
            observations=observations,
            decision_time_ms=decision_time_ms,
        )
    except (TypeError, ValueError):
        raise SelectedPhysicalReservationError("PACKAGE_INVALID") from None
    if reproduced.to_dict() != matches[0]:
        _refuse("SELECTED_INPUT_MISMATCH")
    return _freeze(value)


def validate_selected_physical_reservation_package(value: object) -> dict[str, Any]:
    """Validate one closed package and re-run its selected qualification."""

    return _validate_wire(value)


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class SelectedPhysicalReservationPackage:
    """Immutable selected reservation inputs awaiting Runtime atomic commit."""

    _wire_json: str
    _seal: object = dataclasses.field(repr=False, compare=False)

    def __init__(self, wire: Mapping[str, Any], *, _seal: object) -> None:
        if _seal is not _PACKAGE_SEAL:
            _refuse("UNSEALED_PACKAGE")
        normalized = _validate_wire(dict(wire))
        object.__setattr__(
            self,
            "_wire_json",
            _canonical_bytes(normalized).decode("ascii"),
        )
        object.__setattr__(self, "_seal", _PACKAGE_SEAL)

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self._wire_json)

    @property
    def package_id(self) -> str:
        return self.to_dict()["package_id"]

    @property
    def selected_worker_id(self) -> str:
        return self.to_dict()["selection_v2"]["selected"]["worker_id"]

    @property
    def host_ref(self) -> str:
        return self.to_dict()["selected_qualification"]["host_ref"]

    @property
    def boot_ref(self) -> str:
        return self.to_dict()["selected_qualification"]["boot_ref"]

    def evaluate_for_commit(
        self,
        *,
        selection: PlacementSelectionDecisionV2,
        artifact: HostCapacityPreferenceArtifact,
        qualified_candidates: Sequence[QualifiedHostCandidate],
        policy: Mapping[str, Any],
        current_charges: Sequence[Mapping[str, Any]],
        observations: Mapping[str, Any],
        decision_time_ms: int,
    ) -> dict[str, Any]:
        """Revalidate all ranking inputs, then rerun the physical predicate.

        This method remains storeless.  The incumbent Runtime owner consumes
        the returned request/result inside its own transaction; this module
        never writes a claim, reservation, BEGIN, attempt, or provider effect.
        """

        wire = self.to_dict()
        if not isinstance(selection, PlacementSelectionDecisionV2):
            _refuse("SELECTION_MOVED")
        if selection.to_dict() != wire["selection_v2"]:
            _refuse("SELECTION_MOVED")
        if not isinstance(artifact, HostCapacityPreferenceArtifact):
            _refuse("CAPACITY_SOURCE_MOVED")
        try:
            current_source = json.loads(artifact.source_bytes)
        except (TypeError, ValueError, UnicodeDecodeError):
            raise SelectedPhysicalReservationError("CAPACITY_SOURCE_MOVED") from None
        if current_source != wire["capacity_source"]:
            _refuse("CAPACITY_SOURCE_MOVED")
        current_candidate_wires = _sorted_candidate_wires(qualified_candidates)
        if current_candidate_wires != wire["qualified_candidates"]:
            _refuse("QUALIFIED_CANDIDATES_MOVED")
        try:
            validate_current_host_capacity_preference(
                artifact=artifact,
                decision=selection.base_v1,
                candidates=qualified_candidates,
                generation=wire["capacity_source"]["generation"],
            )
            validated_selection = validate_placement_selection_v2(
                selection.to_dict(),
                resolved_capacity_sources=artifact.resolved_capacity_sources(),
            )
        except (TypeError, ValueError):
            raise SelectedPhysicalReservationError("SELECTION_MOVED") from None
        if validated_selection != wire["selection_v2"]:
            _refuse("SELECTION_MOVED")

        sealed = wire["reservation_input"]
        if _freeze(policy) != sealed["policy"]:
            _refuse("POLICY_MOVED")
        if _freeze(list(current_charges)) != sealed["current_charges"]:
            _refuse("CURRENT_CHARGES_MOVED")
        if _freeze(observations) != sealed["observations"]:
            _refuse("OBSERVATIONS_MOVED")
        reservation = evaluate_reservation(
            sealed["request"],
            policy=policy,
            current_charges=current_charges,
            observations=observations,
            decision_time_ms=decision_time_ms,
        )
        qualification = wire["selected_qualification"]
        if (
            reservation.get("admitted") is not True
            or reservation.get("code") != "RESERVED"
            or reservation.get("fresh_begin") is not False
            or reservation.get("request_fingerprint")
            != qualification["request_fingerprint"]
            or reservation.get("host_capacity_snapshot_sha256")
            != qualification["host_capacity_snapshot_sha256"]
        ):
            _refuse("PHYSICAL_RESERVATION_MOVED")
        return {
            "package_id": wire["package_id"],
            "selected_worker_id": self.selected_worker_id,
            "host_ref": self.host_ref,
            "boot_ref": self.boot_ref,
            "request": copy.deepcopy(sealed["request"]),
            "reservation": copy.deepcopy(reservation),
        }


def make_selected_physical_reservation_package(
    *,
    selection: PlacementSelectionDecisionV2,
    artifact: HostCapacityPreferenceArtifact,
    qualified_candidates: Sequence[QualifiedHostCandidate],
    placement_candidate: PlacementCandidateFact,
    registered_join: RegisteredCapacityJoin,
    capacity_observation: Mapping[str, Any],
    request: Mapping[str, Any],
    policy: Mapping[str, Any],
    current_charges: Sequence[Mapping[str, Any]],
    observations: Mapping[str, Any],
    decision_time_ms: int,
) -> SelectedPhysicalReservationPackage:
    """Seal exact physical inputs for the one resolved FP2 winner."""

    if not isinstance(selection, PlacementSelectionDecisionV2):
        raise TypeError("selection must be PlacementSelectionDecisionV2")
    if not isinstance(artifact, HostCapacityPreferenceArtifact):
        raise TypeError("artifact must be HostCapacityPreferenceArtifact")
    candidate_wires = _sorted_candidate_wires(qualified_candidates)
    try:
        source = json.loads(artifact.source_bytes)
        validate_current_host_capacity_preference(
            artifact=artifact,
            decision=selection.base_v1,
            candidates=qualified_candidates,
            generation=source["generation"],
        )
        validated_selection = validate_placement_selection_v2(
            selection.to_dict(),
            resolved_capacity_sources=artifact.resolved_capacity_sources(),
        )
    except (KeyError, TypeError, ValueError):
        raise SelectedPhysicalReservationError("SELECTION_NOT_RESOLVED") from None
    if (
        selection.state is not SelectionState.SELECTED
        or selection.preference_admissibility != PREFERENCE_ADMISSIBLE
        or validated_selection["selected"] is None
    ):
        _refuse("SELECTION_NOT_RESOLVED")
    selected_id = validated_selection["selected"]["worker_id"]

    try:
        normalized_request = validate_physical_request(copy.deepcopy(request))
        frozen_policy = _freeze(policy)
        frozen_charges = _freeze(list(current_charges))
        frozen_observations = _freeze(observations)
        frozen_capacity_observation = _freeze(capacity_observation)
        reproduced = qualify_host_candidate(
            placement_candidate=placement_candidate,
            registered_join=registered_join,
            capacity_observation=frozen_capacity_observation,
            request=normalized_request,
            policy=frozen_policy,
            current_charges=frozen_charges,
            observations=frozen_observations,
            decision_time_ms=decision_time_ms,
        )
    except SelectedPhysicalReservationError:
        raise
    except (TypeError, ValueError):
        raise SelectedPhysicalReservationError("SELECTED_INPUT_MISMATCH") from None
    matches = [row for row in candidate_wires if row["worker_id"] == selected_id]
    if (
        placement_candidate.worker_id != selected_id
        or registered_join.worker_id != selected_id
        or reproduced.worker_id != selected_id
        or len(matches) != 1
        or reproduced.to_dict() != matches[0]
    ):
        _refuse("SELECTED_INPUT_MISMATCH")

    reservation_input = {
        "placement_candidate": _candidate_to_dict(placement_candidate),
        "registered_join": registered_join.to_dict(),
        "capacity_observation": frozen_capacity_observation,
        "request": normalized_request,
        "policy": frozen_policy,
        "current_charges": frozen_charges,
        "observations": frozen_observations,
        "decision_time_ms": decision_time_ms,
    }
    without_id = {
        "schema": PACKAGE_SCHEMA,
        "selection_v2": validated_selection,
        "capacity_source": source,
        "qualified_candidates": candidate_wires,
        "selected_qualification": matches[0],
        "reservation_input": reservation_input,
    }
    wire = {**without_id, "package_id": _digest(without_id)}
    return SelectedPhysicalReservationPackage(wire, _seal=_PACKAGE_SEAL)


__all__ = [
    "PACKAGE_SCHEMA",
    "SelectedPhysicalReservationError",
    "SelectedPhysicalReservationPackage",
    "make_selected_physical_reservation_package",
    "validate_selected_physical_reservation_package",
]
