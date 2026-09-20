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

from control_plane.executive_capacity_join import (
    MAX_CANDIDATES,
    RegisteredCapacityJoin,
)
from control_plane.executive_capacity_observation import (
    canonical_worker_capacity_observation_json,
    validate_worker_capacity_observation,
)
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
    PlacementCandidateFact,
    PlacementSelectionDecision,
    SelectionState,
)
from control_plane.executive_steward import Freshness, SourceOwner, SourceRef

EVIDENCE_SCHEMA = "mastermind.host_placement_preference_evidence.v1"
_CAPACITY_SOURCE_REF_PREFIX = "capacity-source-sha256:"
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_SCORE_LENGTH = 5
_SOURCE_ARTIFACT_KEYS = frozenset({
    "schema",
    "selection_input_digest",
    "generation",
    "decision_time_ms",
    "candidates",
    "preference_order",
})
_QUALIFIED_CANDIDATE_WIRE_KEYS = frozenset({
    "worker_id",
    "provider",
    "quota_class",
    "host_ref",
    "boot_ref",
    "capacity_capability_id",
    "worker_source_config_digest",
    "capacity_observation_sha256",
    "decision_time_ms",
    "request_fingerprint",
    "host_capacity_snapshot_sha256",
    "physical_evidence_digest",
    "score",
    "qualification_receipt_id",
})
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


def _qualification_receipt_id(
    *,
    worker_id: str,
    provider: str,
    quota_class: str,
    host_ref: str,
    boot_ref: str,
    capacity_capability_id: str,
    worker_source_config_digest: str,
    capacity_observation_sha256: str,
    decision_time_ms: int,
    request_fingerprint: str,
    host_capacity_snapshot_sha256: str,
    physical_evidence_digest: str,
    score: tuple[int, int, int, int, int],
) -> str:
    return _digest(
        {
            "worker_id": worker_id,
            "provider": provider,
            "quota_class": quota_class,
            "host_ref": host_ref,
            "boot_ref": boot_ref,
            "capacity_capability_id": capacity_capability_id,
            "worker_source_config_digest": worker_source_config_digest,
            "capacity_observation_sha256": capacity_observation_sha256,
            "decision_time_ms": decision_time_ms,
            "request_fingerprint": request_fingerprint,
            "host_capacity_snapshot_sha256": host_capacity_snapshot_sha256,
            "physical_evidence_digest": physical_evidence_digest,
            "score": list(score),
        }
    )


@dataclasses.dataclass(frozen=True, slots=True)
class QualifiedHostCandidate:
    """Immutable proof that the physical owner admitted one exact host."""

    worker_id: str
    provider: str
    quota_class: str
    host_ref: str
    boot_ref: str
    capacity_capability_id: str
    worker_source_config_digest: str
    capacity_observation_sha256: str
    decision_time_ms: int
    request_fingerprint: str
    host_capacity_snapshot_sha256: str
    physical_evidence_digest: str
    score: tuple[int, int, int, int, int]
    qualification_receipt_id: str
    _seal: object = dataclasses.field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _QUALIFICATION_SEAL:
            _refuse("UNSEALED_QUALIFICATION")
        _worker_id(self.worker_id)
        for value, code in (
            (self.provider, "PROVIDER_INVALID"),
            (self.quota_class, "QUOTA_CLASS_INVALID"),
            (self.capacity_capability_id, "CAPABILITY_ID_INVALID"),
        ):
            if type(value) is not str or _TOKEN_RE.fullmatch(value) is None:
                _refuse(code)
        if type(self.host_ref) is not str or HOST_REF_RE.fullmatch(self.host_ref) is None:
            _refuse("HOST_REF_INVALID")
        if type(self.boot_ref) is not str or BOOT_REF_RE.fullmatch(self.boot_ref) is None:
            _refuse("BOOT_REF_INVALID")
        if type(self.decision_time_ms) is not int or self.decision_time_ms < 0:
            _refuse("DECISION_TIME_INVALID")
        for value in (
            self.worker_source_config_digest,
            self.capacity_observation_sha256,
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
        if (
            type(self.qualification_receipt_id) is not str
            or _DIGEST_RE.fullmatch(self.qualification_receipt_id) is None
        ):
            _refuse("QUALIFICATION_RECEIPT_INVALID")
        expected_receipt = _qualification_receipt_id(
            worker_id=self.worker_id,
            provider=self.provider,
            quota_class=self.quota_class,
            host_ref=self.host_ref,
            boot_ref=self.boot_ref,
            capacity_capability_id=self.capacity_capability_id,
            worker_source_config_digest=self.worker_source_config_digest,
            capacity_observation_sha256=self.capacity_observation_sha256,
            decision_time_ms=self.decision_time_ms,
            request_fingerprint=self.request_fingerprint,
            host_capacity_snapshot_sha256=self.host_capacity_snapshot_sha256,
            physical_evidence_digest=self.physical_evidence_digest,
            score=self.score,
        )
        if self.qualification_receipt_id != expected_receipt:
            _refuse("QUALIFICATION_RECEIPT_MISMATCH")

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "provider": self.provider,
            "quota_class": self.quota_class,
            "host_ref": self.host_ref,
            "boot_ref": self.boot_ref,
            "capacity_capability_id": self.capacity_capability_id,
            "worker_source_config_digest": self.worker_source_config_digest,
            "capacity_observation_sha256": self.capacity_observation_sha256,
            "decision_time_ms": self.decision_time_ms,
            "request_fingerprint": self.request_fingerprint,
            "host_capacity_snapshot_sha256": self.host_capacity_snapshot_sha256,
            "physical_evidence_digest": self.physical_evidence_digest,
            "score": list(self.score),
            "qualification_receipt_id": self.qualification_receipt_id,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class HostCapacityPreferenceArtifact:
    """One exact preference plus the immutable Capacity source bytes it cites."""

    preference: CapacityPlacementPreference
    source_bytes: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.preference, CapacityPlacementPreference):
            _refuse("PREFERENCE_INVALID")
        if type(self.source_bytes) is not bytes:
            _refuse("SOURCE_ARTIFACT_INVALID")
        try:
            source = json.loads(self.source_bytes)
        except (TypeError, ValueError, UnicodeDecodeError) as exc:
            raise HostPlacementPreferenceError("SOURCE_ARTIFACT_INVALID") from exc
        if (
            type(source) is not dict
            or set(source) != _SOURCE_ARTIFACT_KEYS
            or _canonical_bytes(source) != self.source_bytes
            or source.get("schema") != EVIDENCE_SCHEMA
        ):
            _refuse("SOURCE_ARTIFACT_INVALID")
        if (
            type(source.get("selection_input_digest")) is not str
            or _DIGEST_RE.fullmatch(source["selection_input_digest"]) is None
            or type(source.get("generation")) is not int
            or source["generation"] < 1
            or type(source.get("decision_time_ms")) is not int
            or source["decision_time_ms"] < 0
        ):
            _refuse("SOURCE_ARTIFACT_INVALID")
        candidates = source.get("candidates")
        if (
            type(candidates) is not list
            or not 1 <= len(candidates) <= MAX_CANDIDATES
            or any(
                type(candidate) is not dict
                or set(candidate) != _QUALIFIED_CANDIDATE_WIRE_KEYS
                for candidate in candidates
            )
        ):
            _refuse("SOURCE_ARTIFACT_INVALID")
        worker_ids: list[str] = []
        for candidate in candidates:
            worker_id = candidate.get("worker_id")
            if type(worker_id) is not str or _TOKEN_RE.fullmatch(worker_id) is None:
                _refuse("SOURCE_ARTIFACT_INVALID")
            worker_ids.append(worker_id)
            for field in ("provider", "quota_class", "capacity_capability_id"):
                value = candidate.get(field)
                if type(value) is not str or _TOKEN_RE.fullmatch(value) is None:
                    _refuse("SOURCE_ARTIFACT_INVALID")
            if (
                type(candidate.get("host_ref")) is not str
                or HOST_REF_RE.fullmatch(candidate["host_ref"]) is None
                or type(candidate.get("boot_ref")) is not str
                or BOOT_REF_RE.fullmatch(candidate["boot_ref"]) is None
                or type(candidate.get("decision_time_ms")) is not int
                or candidate["decision_time_ms"] != source["decision_time_ms"]
            ):
                _refuse("SOURCE_ARTIFACT_INVALID")
            for field in (
                "worker_source_config_digest",
                "capacity_observation_sha256",
                "request_fingerprint",
                "host_capacity_snapshot_sha256",
                "physical_evidence_digest",
                "qualification_receipt_id",
            ):
                value = candidate.get(field)
                if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
                    _refuse("SOURCE_ARTIFACT_INVALID")
            score = candidate.get("score")
            if (
                type(score) is not list
                or len(score) != _SCORE_LENGTH
                or any(type(item) is not int for item in score)
            ):
                _refuse("SOURCE_ARTIFACT_INVALID")
            expected_receipt = _qualification_receipt_id(
                worker_id=candidate["worker_id"],
                provider=candidate["provider"],
                quota_class=candidate["quota_class"],
                host_ref=candidate["host_ref"],
                boot_ref=candidate["boot_ref"],
                capacity_capability_id=candidate["capacity_capability_id"],
                worker_source_config_digest=candidate[
                    "worker_source_config_digest"
                ],
                capacity_observation_sha256=candidate[
                    "capacity_observation_sha256"
                ],
                decision_time_ms=candidate["decision_time_ms"],
                request_fingerprint=candidate["request_fingerprint"],
                host_capacity_snapshot_sha256=candidate[
                    "host_capacity_snapshot_sha256"
                ],
                physical_evidence_digest=candidate["physical_evidence_digest"],
                score=tuple(score),
            )
            if candidate["qualification_receipt_id"] != expected_receipt:
                _refuse("QUALIFICATION_RECEIPT_MISMATCH")
        if worker_ids != sorted(worker_ids) or len(set(worker_ids)) != len(worker_ids):
            _refuse("SOURCE_ARTIFACT_INVALID")
        if (
            type(source.get("preference_order")) is not list
            or set(source["preference_order"]) != set(worker_ids)
            or len(source["preference_order"]) != len(worker_ids)
        ):
            _refuse("SOURCE_ARTIFACT_INVALID")
        score_groups: dict[tuple[int, ...], list[str]] = {}
        for candidate in candidates:
            score_groups.setdefault(tuple(candidate["score"]), []).append(
                candidate["worker_id"]
            )
        if any(len(group) > 1 for group in score_groups.values()):
            _refuse("HOST_SCORE_TIE_UNRESOLVED")
        expected_order = [
            score_groups[score][0] for score in sorted(score_groups)
        ]
        if source["preference_order"] != expected_order:
            _refuse("SOURCE_ARTIFACT_ORDER_MISMATCH")
        if source["selection_input_digest"] != self.preference.selection_input_digest:
            _refuse("SOURCE_ARTIFACT_PREFERENCE_MISMATCH")
        if source["generation"] != self.preference.generation:
            _refuse("SOURCE_ARTIFACT_PREFERENCE_MISMATCH")
        if self.preference.capacity_source.observed_at != (
            f"ms-{source['decision_time_ms']}"
        ):
            _refuse("SOURCE_ARTIFACT_PREFERENCE_MISMATCH")
        if source["preference_order"] != list(self.preference.preference_order):
            _refuse("SOURCE_ARTIFACT_PREFERENCE_MISMATCH")
        expected_ref = (
            _CAPACITY_SOURCE_REF_PREFIX
            + hashlib.sha256(self.source_bytes).hexdigest()
        )
        if self.preference.capacity_source.ref != expected_ref:
            _refuse("SOURCE_ARTIFACT_DIGEST_MISMATCH")

    def resolved_capacity_sources(self) -> dict[str, bytes]:
        return {self.preference.capacity_source.ref: self.source_bytes}


def qualify_host_candidate(
    *,
    placement_candidate: PlacementCandidateFact,
    registered_join: RegisteredCapacityJoin,
    capacity_observation: Mapping[str, Any],
    request: Mapping[str, Any],
    policy: Mapping[str, Any],
    current_charges: Sequence[Mapping[str, Any]],
    observations: Mapping[str, Any],
    decision_time_ms: int,
) -> QualifiedHostCandidate:
    """Bind one tied worker to its registered ready host, then qualify it."""

    if not isinstance(placement_candidate, PlacementCandidateFact):
        _refuse("PLACEMENT_CANDIDATE_INVALID")
    if not isinstance(registered_join, RegisteredCapacityJoin):
        _refuse("CAPACITY_JOIN_INVALID")
    worker = _worker_id(placement_candidate.worker_id)
    if (
        registered_join.worker_id != worker
        or registered_join.provider != placement_candidate.provider
        or registered_join.quota_class != placement_candidate.quota_class
    ):
        _refuse("CANDIDATE_JOIN_MISMATCH")
    join = registered_join.capacity_join
    if join.host_ref == "local-unbound":
        _refuse("CAPACITY_JOIN_INVALID")
    validated_capacity_observation = validate_worker_capacity_observation(
        capacity_observation,
        expected_host_ref=join.host_ref,
        expected_capacity_capability_id=join.capacity_capability_id,
        expected_source_config_digest=join.worker_source_config_digest,
        trusted_current_ms=decision_time_ms,
    )
    capacity_observation_sha256 = hashlib.sha256(
        canonical_worker_capacity_observation_json(
            validated_capacity_observation
        )
    ).hexdigest()
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

    if frozen_request.get("host_id") != join.host_ref:
        _refuse("CAPACITY_JOIN_HOST_MISMATCH")

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
        "provider": registered_join.provider,
        "quota_class": registered_join.quota_class,
        "capacity_join_sha256": _digest(registered_join.to_dict()),
        "capacity_observation_sha256": capacity_observation_sha256,
        "decision_time_ms": decision_time_ms,
        "request_fingerprint": request_fingerprint,
        "policy_sha256": _digest(frozen_policy),
        "current_charges_sha256": _digest(frozen_charges),
        "observations_sha256": _digest(frozen_observations),
        "reservation_result_sha256": _digest(result),
        "host_capacity_snapshot_sha256": capacity_digest,
    }
    physical_evidence_digest = _digest(evidence)
    score = _host_score(snapshot)
    qualification_receipt_id = _qualification_receipt_id(
        worker_id=worker,
        provider=registered_join.provider,
        quota_class=registered_join.quota_class,
        host_ref=snapshot["host_ref"],
        boot_ref=snapshot["boot_ref"],
        capacity_capability_id=join.capacity_capability_id,
        worker_source_config_digest=join.worker_source_config_digest,
        capacity_observation_sha256=capacity_observation_sha256,
        decision_time_ms=decision_time_ms,
        request_fingerprint=request_fingerprint,
        host_capacity_snapshot_sha256=capacity_digest,
        physical_evidence_digest=physical_evidence_digest,
        score=score,
    )
    return QualifiedHostCandidate(
        worker_id=worker,
        provider=registered_join.provider,
        quota_class=registered_join.quota_class,
        host_ref=snapshot["host_ref"],
        boot_ref=snapshot["boot_ref"],
        capacity_capability_id=join.capacity_capability_id,
        worker_source_config_digest=join.worker_source_config_digest,
        capacity_observation_sha256=capacity_observation_sha256,
        decision_time_ms=decision_time_ms,
        request_fingerprint=request_fingerprint,
        host_capacity_snapshot_sha256=capacity_digest,
        physical_evidence_digest=physical_evidence_digest,
        score=score,
        qualification_receipt_id=qualification_receipt_id,
        _seal=_QUALIFICATION_SEAL,
    )



def make_host_capacity_preference(
    *,
    decision: PlacementSelectionDecision,
    candidates: Sequence[QualifiedHostCandidate],
    generation: int,
) -> HostCapacityPreferenceArtifact:
    """Derive one content-addressed Capacity artifact for one exact v1 tie."""

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
    decision_evidence = {
        row.worker_id: row
        for row in decision.evidence
        if row.worker_id in set(tied_ids)
    }
    if len(decision_evidence) != len(tied_ids):
        _refuse("CANDIDATE_IDENTITY_MISMATCH")
    for candidate in frozen:
        row = decision_evidence.get(candidate.worker_id)
        if (
            row is None
            or row.provider != candidate.provider
            or row.quota_class != candidate.quota_class
        ):
            _refuse("CANDIDATE_IDENTITY_MISMATCH")

    groups: dict[tuple[int, int, int, int, int], list[QualifiedHostCandidate]] = {}
    for candidate in frozen:
        groups.setdefault(candidate.score, []).append(candidate)
    if any(len(group) > 1 for group in groups.values()):
        _refuse("HOST_SCORE_TIE_UNRESOLVED")

    preference_order = [groups[score][0].worker_id for score in sorted(groups)]

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "selection_input_digest": selection_input_digest(decision),
        "generation": generation,
        "decision_time_ms": decision_time_ms,
        "candidates": [
            candidate.to_dict()
            for candidate in sorted(frozen, key=lambda item: item.worker_id)
        ],
        "preference_order": list(preference_order),
    }
    source_bytes = _canonical_bytes(evidence)
    capacity_source = SourceRef(
        owner=SourceOwner.CAPACITY,
        ref=(
            _CAPACITY_SOURCE_REF_PREFIX
            + hashlib.sha256(source_bytes).hexdigest()
        ),
        observed_at=f"ms-{decision_time_ms}",
        freshness=Freshness.CURRENT,
    )
    preference = make_capacity_preference(
        decision=decision,
        preference_order=tuple(preference_order),
        capacity_source=capacity_source,
        generation=generation,
    )
    return HostCapacityPreferenceArtifact(
        preference=preference,
        source_bytes=source_bytes,
    )


def validate_current_host_capacity_preference(
    *,
    artifact: HostCapacityPreferenceArtifact,
    decision: PlacementSelectionDecision,
    candidates: Sequence[QualifiedHostCandidate],
    generation: int,
) -> HostCapacityPreferenceArtifact:
    """Require an artifact to equal a recomputation from current evidence."""

    if not isinstance(artifact, HostCapacityPreferenceArtifact):
        _refuse("PREFERENCE_INVALID")
    expected = make_host_capacity_preference(
        decision=decision,
        candidates=candidates,
        generation=generation,
    )
    if (
        artifact.preference.to_dict() != expected.preference.to_dict()
        or artifact.source_bytes != expected.source_bytes
    ):
        _refuse("PREFERENCE_NOT_CURRENT")
    return artifact


__all__ = [
    "EVIDENCE_SCHEMA",
    "HostCapacityPreferenceArtifact",
    "HostPlacementPreferenceError",
    "QualifiedHostCandidate",
    "make_host_capacity_preference",
    "qualify_host_candidate",
    "validate_current_host_capacity_preference",
]
