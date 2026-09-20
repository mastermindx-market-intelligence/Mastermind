"""Compose current physical-host evidence into one Capacity preference.

The existing physical-resource owner remains the hard feasibility and reserve
authority. This module only seals successful qualifications and orders an
already-existing v1 placement tie. It performs no I/O, sampling, reservation,
Runtime mutation, transport, provider call, or retry.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from control_plane.executive_host_capacity import (
    BOOT_REF_RE,
    HOST_REF_RE,
    HostCapacityContractError,
    validate_host_capacity_snapshot,
)
from control_plane.executive_physical_resources import evaluate_reservation
from control_plane.executive_placement_preference import (
    CapacityPlacementPreference,
    make_capacity_preference,
    selection_input_digest,
)
from control_plane.executive_placement_selection import (
    PlacementSelectionDecision,
    SelectionState,
)
from control_plane.executive_steward import Freshness, SourceOwner, SourceRef

EVIDENCE_SCHEMA = "mastermind.host_placement_preference_evidence.v1"
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_SCORE_LENGTH = 5
_QUALIFICATION_SEAL = object()


class HostPlacementPreferenceError(ValueError):
    """A closed refusal from the host-preference composition boundary."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(message or code)


def _refuse(code: str, message: str = "") -> None:
    raise HostPlacementPreferenceError(code, message)


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise HostPlacementPreferenceError(
            "EVIDENCE_NOT_CANONICAL",
            "host-placement evidence is not canonical JSON",
        ) from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _worker_id(value: object) -> str:
    if type(value) is not str or _TOKEN_RE.fullmatch(value) is None:
        _refuse("WORKER_ID_INVALID")
    return value


def _ratio(numerator: int, denominator: int) -> int:
    return 0 if denominator == 0 else numerator * 1_000_000 // denominator


def _host_score(snapshot: Mapping[str, Any]) -> tuple[int, int, int, int, int]:
    memory = int(snapshot["physical_memory_bytes"])
    page_size = int(snapshot["vm_page_size_bytes"])
    available = page_size * (
        int(snapshot["vm_free_pages"])
        + int(snapshot["vm_inactive_pages"])
        + int(snapshot["vm_speculative_pages"])
    )
    compressed = page_size * int(snapshot["vm_compressed_pages"])
    return (
        int(snapshot["load_ratio_milli"]),
        -_ratio(min(available, memory), memory),
        _ratio(
            int(snapshot["swap_used_bytes"]),
            int(snapshot["swap_total_bytes"]),
        ),
        _ratio(min(compressed, memory), memory),
        -_ratio(
            int(snapshot["pool_free_bytes"]),
            int(snapshot["pool_total_bytes"]),
        ),
    )


@dataclasses.dataclass(frozen=True, slots=True)
class QualifiedHostCandidate:
    """Immutable proof that the physical owner admitted one exact host."""

    worker_id: str
    host_ref: str
    boot_ref: str
    decision_time_ms: int
    request_fingerprint: str
    host_capacity_snapshot_sha256: str
    physical_evidence_digest: str
    score: tuple[int, int, int, int, int]
    _seal: object = dataclasses.field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _QUALIFICATION_SEAL:
            _refuse("UNSEALED_QUALIFICATION")
        _worker_id(self.worker_id)
        if type(self.host_ref) is not str or HOST_REF_RE.fullmatch(self.host_ref) is None:
            _refuse("HOST_REF_INVALID")
        if type(self.boot_ref) is not str or BOOT_REF_RE.fullmatch(self.boot_ref) is None:
            _refuse("BOOT_REF_INVALID")
        if type(self.decision_time_ms) is not int or self.decision_time_ms < 0:
            _refuse("DECISION_TIME_INVALID")
        for value in (
            self.request_fingerprint,
            self.host_capacity_snapshot_sha256,
            self.physical_evidence_digest,
        ):
            if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
                _refuse("DIGEST_INVALID")
        if (
            type(self.score) is not tuple
            or len(self.score) != _SCORE_LENGTH
            or any(type(item) is not int for item in self.score)
        ):
            _refuse("HOST_SCORE_INVALID")

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "host_ref": self.host_ref,
            "boot_ref": self.boot_ref,
            "decision_time_ms": self.decision_time_ms,
            "request_fingerprint": self.request_fingerprint,
            "host_capacity_snapshot_sha256": self.host_capacity_snapshot_sha256,
            "physical_evidence_digest": self.physical_evidence_digest,
            "score": list(self.score),
        }


def qualify_host_candidate(
    *,
    worker_id: str,
    request: Mapping[str, Any],
    policy: Mapping[str, Any],
    current_charges: Sequence[Mapping[str, Any]],
    observations: Mapping[str, Any],
    decision_time_ms: int,
) -> QualifiedHostCandidate:
    """Freeze one snapshot and ask the existing physical owner to qualify it."""

    worker = _worker_id(worker_id)
    if type(decision_time_ms) is not int or decision_time_ms < 0:
        _refuse("DECISION_TIME_INVALID")
    if isinstance(current_charges, (str, bytes)) or not isinstance(
        current_charges, Sequence
    ):
        _refuse("CURRENT_CHARGES_INVALID")
    try:
        frozen_request = copy.deepcopy(request)
        frozen_policy = copy.deepcopy(policy)
        frozen_charges = copy.deepcopy(list(current_charges))
        frozen_observations = copy.deepcopy(observations)
    except Exception as exc:
        raise HostPlacementPreferenceError(
            "EVIDENCE_COPY_FAILED",
            "host-placement inputs could not be frozen",
        ) from exc

    result = evaluate_reservation(
        frozen_request,
        policy=frozen_policy,
        current_charges=frozen_charges,
        observations=frozen_observations,
        decision_time_ms=decision_time_ms,
    )
    if (
        type(result) is not dict
        or result.get("admitted") is not True
        or result.get("code") != "RESERVED"
        or result.get("fresh_begin") is not False
    ):
        _refuse("PHYSICAL_QUALIFICATION_INVALID")
    try:
        capacity_evidence = frozen_observations["host_capacity_evidence"]
        snapshot = validate_host_capacity_snapshot(capacity_evidence["snapshot"])
    except (KeyError, TypeError, HostCapacityContractError) as exc:
        raise HostPlacementPreferenceError(
            "HOST_CAPACITY_EVIDENCE_INVALID"
        ) from exc
    capacity_digest = result.get("host_capacity_snapshot_sha256")
    if (
        type(capacity_digest) is not str
        or _DIGEST_RE.fullmatch(capacity_digest) is None
        or capacity_digest != capacity_evidence.get("snapshot_sha256")
    ):
        _refuse("HOST_CAPACITY_EVIDENCE_INVALID")
    request_fingerprint = result.get("request_fingerprint")
    if type(request_fingerprint) is not str or _DIGEST_RE.fullmatch(
        request_fingerprint
    ) is None:
        _refuse("PHYSICAL_QUALIFICATION_INVALID")

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "worker_id": worker,
        "decision_time_ms": decision_time_ms,
        "request_fingerprint": request_fingerprint,
        "policy_sha256": _digest(frozen_policy),
        "current_charges_sha256": _digest(frozen_charges),
        "observations_sha256": _digest(frozen_observations),
        "reservation_result_sha256": _digest(result),
        "host_capacity_snapshot_sha256": capacity_digest,
    }
    return QualifiedHostCandidate(
        worker_id=worker,
        host_ref=snapshot["host_ref"],
        boot_ref=snapshot["boot_ref"],
        decision_time_ms=decision_time_ms,
        request_fingerprint=request_fingerprint,
        host_capacity_snapshot_sha256=capacity_digest,
        physical_evidence_digest=_digest(evidence),
        score=_host_score(snapshot),
        _seal=_QUALIFICATION_SEAL,
    )


def _validate_tie_source(source: SourceRef | None) -> SourceRef:
    if (
        not isinstance(source, SourceRef)
        or source.owner is not SourceOwner.CAPACITY
        or source.freshness is not Freshness.CURRENT
        or type(source.ref) is not str
        or _TOKEN_RE.fullmatch(source.ref) is None
        or type(source.observed_at) is not str
        or _TOKEN_RE.fullmatch(source.observed_at) is None
    ):
        _refuse("TIE_SOURCE_INVALID")
    return source


def _source_wire(source: SourceRef) -> dict[str, Any]:
    return {
        "owner": source.owner.value,
        "ref": source.ref,
        "observed_at": source.observed_at,
        "freshness": source.freshness.value,
    }


def make_host_capacity_preference(
    *,
    decision: PlacementSelectionDecision,
    candidates: Sequence[QualifiedHostCandidate],
    generation: int,
    capacity_tie_order: Sequence[str] | None = None,
    capacity_tie_source: SourceRef | None = None,
) -> CapacityPlacementPreference:
    """Derive one content-addressed Capacity order for one exact v1 tie."""

    if not isinstance(decision, PlacementSelectionDecision):
        _refuse("DECISION_INVALID")
    if decision.state is not SelectionState.TIE_ABSTAINED:
        _refuse("BASE_NOT_TIED")
    if type(generation) is not int or generation < 1:
        _refuse("GENERATION_INVALID")
    if isinstance(candidates, (str, bytes)) or not isinstance(candidates, Sequence):
        _refuse("CANDIDATES_INVALID")
    frozen = tuple(candidates)
    if any(
        not isinstance(candidate, QualifiedHostCandidate)
        or candidate._seal is not _QUALIFICATION_SEAL
        for candidate in frozen
    ):
        _refuse("UNSEALED_QUALIFICATION")

    worker_ids = tuple(candidate.worker_id for candidate in frozen)
    tied_ids = tuple(decision.tied_worker_ids)
    if (
        len(worker_ids) != len(tied_ids)
        or len(set(worker_ids)) != len(worker_ids)
        or set(worker_ids) != set(tied_ids)
    ):
        _refuse("CANDIDATE_SET_MISMATCH")
    decision_times = {candidate.decision_time_ms for candidate in frozen}
    if len(decision_times) != 1:
        _refuse("DECISION_TIME_MISMATCH")
    decision_time_ms = next(iter(decision_times))

    groups: dict[tuple[int, int, int, int, int], list[QualifiedHostCandidate]] = {}
    for candidate in frozen:
        groups.setdefault(candidate.score, []).append(candidate)
    has_tie = any(len(group) > 1 for group in groups.values())

    tie_order: tuple[str, ...] | None = None
    tie_source: SourceRef | None = None
    if has_tie:
        if capacity_tie_order is None:
            _refuse("HOST_SCORE_TIE_UNRESOLVED")
        if isinstance(capacity_tie_order, (str, bytes)) or not isinstance(
            capacity_tie_order, Sequence
        ):
            _refuse("TIE_ORDER_INVALID")
        tie_order = tuple(capacity_tie_order)
        if (
            len(tie_order) != len(tied_ids)
            or len(set(tie_order)) != len(tie_order)
            or set(tie_order) != set(tied_ids)
        ):
            _refuse("TIE_ORDER_INVALID")
        tie_source = _validate_tie_source(capacity_tie_source)
    elif capacity_tie_order is not None or capacity_tie_source is not None:
        _refuse("TIE_SOURCE_UNUSED")

    tie_index = (
        {worker_id: index for index, worker_id in enumerate(tie_order)}
        if tie_order is not None
        else {}
    )
    preference_order: list[str] = []
    for score in sorted(groups):
        group = groups[score]
        if len(group) == 1:
            preference_order.append(group[0].worker_id)
        else:
            preference_order.extend(
                candidate.worker_id
                for candidate in sorted(
                    group,
                    key=lambda candidate: tie_index[candidate.worker_id],
                )
            )

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "selection_input_digest": selection_input_digest(decision),
        "generation": generation,
        "decision_time_ms": decision_time_ms,
        "candidates": [
            candidate.to_dict()
            for candidate in sorted(frozen, key=lambda item: item.worker_id)
        ],
        "capacity_tie_order": None if tie_order is None else list(tie_order),
        "capacity_tie_source": (
            None if tie_source is None else _source_wire(tie_source)
        ),
    }
    capacity_source = SourceRef(
        owner=SourceOwner.CAPACITY,
        ref=f"host-placement-{_digest(evidence)}",
        observed_at=f"ms-{decision_time_ms}",
        freshness=Freshness.CURRENT,
    )
    return make_capacity_preference(
        decision=decision,
        preference_order=tuple(preference_order),
        capacity_source=capacity_source,
        generation=generation,
    )


def validate_current_host_capacity_preference(
    *,
    preference: CapacityPlacementPreference,
    decision: PlacementSelectionDecision,
    candidates: Sequence[QualifiedHostCandidate],
    generation: int,
    capacity_tie_order: Sequence[str] | None = None,
    capacity_tie_source: SourceRef | None = None,
) -> CapacityPlacementPreference:
    """Require a receipt to equal a recomputation from current evidence."""

    if not isinstance(preference, CapacityPlacementPreference):
        _refuse("PREFERENCE_INVALID")
    expected = make_host_capacity_preference(
        decision=decision,
        candidates=candidates,
        generation=generation,
        capacity_tie_order=capacity_tie_order,
        capacity_tie_source=capacity_tie_source,
    )
    if preference.to_dict() != expected.to_dict():
        _refuse("PREFERENCE_NOT_CURRENT")
    return preference


__all__ = [
    "EVIDENCE_SCHEMA",
    "HostPlacementPreferenceError",
    "QualifiedHostCandidate",
    "make_host_capacity_preference",
    "qualify_host_candidate",
    "validate_current_host_capacity_preference",
]
