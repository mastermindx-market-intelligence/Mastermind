"""Additive Capacity-owned resolver for exact CAP-C1 placement ties.

V1 placement selection remains byte/semantic compatible: exact top ties still
abstain.  This module adds a v2 wrapper that may resolve *only* a v1
TIE_ABSTAINED result using a current Capacity-authored, content-addressed
preference receipt bound to the exact v1 selection inputs.

It performs no I/O, clock reads, persistence, reservation, provider work, or
Executive lifecycle mutation.  Capacity remains the fact owner; this module is
only the deterministic consumer of an already-observed preference.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from control_plane.executive_orchestration_principal import (
    build_placement_snapshot,
    validate_placement_snapshot,
)
from control_plane.executive_placement_selection import (
    PlacementCandidateFact,
    PlacementDemand,
    PlacementMode,
    PlacementSelectionDecision,
    SelectionState,
    select_placement,
    validate_placement_selection,
)
from control_plane.executive_steward import Freshness, ResponsibilityFact, SourceOwner, SourceRef

PREFERENCE_SCHEMA = "mastermind.capacity_placement_preference.v1"
SELECTION_V2_SCHEMA = "mastermind.executive_placement_selection.v2"
PREFERENCE_ADMISSIBLE = "admissible"
PREFERENCE_INADMISSIBLE = "inadmissible"
CAPACITY_SOURCE_UNRESOLVED = "CAPACITY_SOURCE_UNRESOLVED"
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CAPACITY_SOURCE_REF_RE = re.compile(r"^capacity-source-sha256:([0-9a-f]{64})$")


class PlacementPreferenceError(ValueError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def selection_input_digest(decision: PlacementSelectionDecision) -> str:
    """Digest the exact source inputs carried by a v1 decision.

    Output state/selection are excluded; v1's carried demand, responsibility
    freshness, and complete candidate evidence are sufficient to recompute it.
    """
    wire = decision.to_dict()
    return _digest(
        {
            "responsibility_ref": wire["responsibility_ref"],
            "responsibility_freshness": wire["responsibility_freshness"],
            "demand": wire["demand"],
            "evidence": wire["evidence"],
        }
    )


def _source_dict(source: SourceRef) -> dict[str, Any]:
    return {
        "owner": source.owner.value,
        "ref": source.ref,
        "observed_at": source.observed_at,
        "freshness": source.freshness.value,
    }


def _validate_source(source: SourceRef) -> None:
    if not isinstance(source, SourceRef):
        raise TypeError("capacity_source must be SourceRef")
    if source.owner is not SourceOwner.CAPACITY:
        raise PlacementPreferenceError("preference source owner must be Capacity")
    if source.freshness is not Freshness.CURRENT:
        raise PlacementPreferenceError("preference source must be current")
    if _CAPACITY_SOURCE_REF_RE.fullmatch(source.ref) is None:
        raise PlacementPreferenceError(
            "preference source ref must be an exact content-addressed Capacity artifact"
        )
    if source.observed_at is None or _TOKEN_RE.fullmatch(source.observed_at) is None:
        raise PlacementPreferenceError("preference source observed_at must be a bounded opaque token")


@dataclasses.dataclass(frozen=True, slots=True)
class CapacityPlacementPreference:
    responsibility_ref: str
    selection_input_digest: str
    preference_order: tuple[str, ...]
    capacity_source: SourceRef
    generation: int
    receipt_id: str

    def __post_init__(self) -> None:
        if _TOKEN_RE.fullmatch(self.responsibility_ref) is None:
            raise PlacementPreferenceError("responsibility_ref must be a bounded opaque token")
        if _DIGEST_RE.fullmatch(self.selection_input_digest) is None:
            raise PlacementPreferenceError("selection_input_digest must be lowercase sha256")
        if not isinstance(self.preference_order, tuple) or len(self.preference_order) < 2:
            raise PlacementPreferenceError("preference_order must contain at least two worker ids")
        if len(set(self.preference_order)) != len(self.preference_order):
            raise PlacementPreferenceError("preference_order must not contain duplicates")
        if any(_TOKEN_RE.fullmatch(worker_id) is None for worker_id in self.preference_order):
            raise PlacementPreferenceError("preference_order contains an invalid worker id")
        _validate_source(self.capacity_source)
        if type(self.generation) is not int or self.generation < 1:
            raise PlacementPreferenceError("generation must be an integer >= 1")
        if _DIGEST_RE.fullmatch(self.receipt_id) is None:
            raise PlacementPreferenceError("receipt_id must be lowercase sha256")
        if self.receipt_id != _digest(self._without_id()):
            raise PlacementPreferenceError("receipt_id does not match preference content")

    def _without_id(self) -> dict[str, Any]:
        return {
            "schema": PREFERENCE_SCHEMA,
            "responsibility_ref": self.responsibility_ref,
            "selection_input_digest": self.selection_input_digest,
            "preference_order": list(self.preference_order),
            "capacity_source": _source_dict(self.capacity_source),
            "generation": self.generation,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._without_id(), "receipt_id": self.receipt_id}


def make_capacity_preference(
    *,
    decision: PlacementSelectionDecision,
    preference_order: Sequence[str],
    capacity_source: SourceRef,
    generation: int,
) -> CapacityPlacementPreference:
    """Content-address one Capacity preference for one exact v1 tie."""
    if not isinstance(decision, PlacementSelectionDecision):
        raise TypeError("decision must be PlacementSelectionDecision")
    if decision.state is not SelectionState.TIE_ABSTAINED:
        raise PlacementPreferenceError("a preference may be minted only for an exact v1 tie")
    order = tuple(preference_order)
    if set(order) != set(decision.tied_worker_ids) or len(order) != len(decision.tied_worker_ids):
        raise PlacementPreferenceError("preference_order must exactly cover the v1 tied workers")
    _validate_source(capacity_source)
    provisional = {
        "schema": PREFERENCE_SCHEMA,
        "responsibility_ref": decision.responsibility_ref,
        "selection_input_digest": selection_input_digest(decision),
        "preference_order": list(order),
        "capacity_source": _source_dict(capacity_source),
        "generation": generation,
    }
    return CapacityPlacementPreference(
        responsibility_ref=decision.responsibility_ref,
        selection_input_digest=provisional["selection_input_digest"],
        preference_order=order,
        capacity_source=capacity_source,
        generation=generation,
        receipt_id=_digest(provisional),
    )


_PREFERENCE_KEYS = frozenset({
    "schema",
    "responsibility_ref",
    "selection_input_digest",
    "preference_order",
    "capacity_source",
    "generation",
    "receipt_id",
})
_SOURCE_KEYS = frozenset({"owner", "ref", "observed_at", "freshness"})
_V2_KEYS = frozenset({
    "schema",
    "base_v1",
    "preference",
    "preference_admissibility",
    "preference_refusal",
    "state",
    "selected",
    "selected_mode",
    "selection_is_commitment",
})
_PREFERENCE_REFUSAL_KEYS = frozenset({"code", "source_ref"})


def _source_from_dict(value: object) -> SourceRef:
    if not isinstance(value, Mapping) or set(value) != _SOURCE_KEYS:
        raise PlacementPreferenceError("capacity_source has an invalid closed shape")
    try:
        source = SourceRef(
            owner=SourceOwner(value["owner"]),
            ref=value["ref"],
            observed_at=value["observed_at"],
            freshness=Freshness(value["freshness"]),
        )
    except (TypeError, ValueError) as exc:
        raise PlacementPreferenceError("capacity_source is invalid") from exc
    _validate_source(source)
    return source


def validate_capacity_preference(value: object) -> CapacityPlacementPreference:
    """Closed-wire validation for one content-addressed Capacity preference."""
    if not isinstance(value, Mapping) or set(value) != _PREFERENCE_KEYS:
        raise PlacementPreferenceError("capacity preference has an invalid closed shape")
    if value["schema"] != PREFERENCE_SCHEMA:
        raise PlacementPreferenceError("unsupported capacity preference schema")
    order = value["preference_order"]
    if not isinstance(order, list) or not all(isinstance(item, str) for item in order):
        raise PlacementPreferenceError("preference_order must be a list of worker ids")
    return CapacityPlacementPreference(
        responsibility_ref=value["responsibility_ref"],
        selection_input_digest=value["selection_input_digest"],
        preference_order=tuple(order),
        capacity_source=_source_from_dict(value["capacity_source"]),
        generation=value["generation"],
        receipt_id=value["receipt_id"],
    )


def _selection_input_digest_from_wire(value: Mapping[str, Any]) -> str:
    normalized = validate_placement_selection(value)
    return _digest(
        {
            "responsibility_ref": normalized["responsibility_ref"],
            "responsibility_freshness": normalized["responsibility_freshness"],
            "demand": normalized["demand"],
            "evidence": normalized["evidence"],
        }
    )


def _capacity_source_resolves_exactly(
    source: SourceRef, resolved_capacity_sources: Mapping[str, bytes] | None
) -> bool:
    """Prove the referenced Capacity artifact is present at its exact content address."""
    if not isinstance(resolved_capacity_sources, Mapping):
        return False
    content = resolved_capacity_sources.get(source.ref)
    if type(content) is not bytes:
        return False
    match = _CAPACITY_SOURCE_REF_RE.fullmatch(source.ref)
    return match is not None and hashlib.sha256(content).hexdigest() == match.group(1)


def _capacity_source_refusal(source: SourceRef) -> dict[str, str]:
    return {
        "code": CAPACITY_SOURCE_UNRESOLVED,
        "source_ref": source.ref,
    }


def validate_placement_selection_v2(
    value: object,
    *,
    resolved_capacity_sources: Mapping[str, bytes] | None = None,
) -> dict[str, Any]:
    """Revalidate v2, including exact Capacity-source admissibility."""
    if not isinstance(value, Mapping) or set(value) != _V2_KEYS:
        raise PlacementPreferenceError("placement selection v2 has an invalid closed shape")
    if value["schema"] != SELECTION_V2_SCHEMA:
        raise PlacementPreferenceError("unsupported placement selection v2 schema")
    if value["selection_is_commitment"] is not False:
        raise PlacementPreferenceError("selection_is_commitment must be exactly false")
    try:
        base = validate_placement_selection(value["base_v1"])
        state = SelectionState(value["state"])
    except (TypeError, ValueError) as exc:
        raise PlacementPreferenceError("base_v1 or state is invalid") from exc

    pref_raw = value["preference"]
    preference = None if pref_raw is None else validate_capacity_preference(pref_raw)
    admissibility = value["preference_admissibility"]
    if admissibility not in {None, PREFERENCE_ADMISSIBLE, PREFERENCE_INADMISSIBLE}:
        raise PlacementPreferenceError("preference_admissibility is invalid")
    refusal_raw = value["preference_refusal"]
    if refusal_raw is None:
        refusal = None
    elif not isinstance(refusal_raw, Mapping) or set(refusal_raw) != _PREFERENCE_REFUSAL_KEYS:
        raise PlacementPreferenceError("preference_refusal has an invalid closed shape")
    elif type(refusal_raw["code"]) is not str or type(refusal_raw["source_ref"]) is not str:
        raise PlacementPreferenceError("preference_refusal is invalid")
    else:
        refusal = {
            "code": refusal_raw["code"],
            "source_ref": refusal_raw["source_ref"],
        }

    selected_raw = value["selected"]
    if selected_raw is None:
        selected = None
    else:
        try:
            selected = validate_placement_snapshot(selected_raw)
        except (TypeError, ValueError) as exc:
            raise PlacementPreferenceError("selected is not a valid placement snapshot") from exc
    selected_mode_raw = value["selected_mode"]
    try:
        selected_mode = None if selected_mode_raw is None else PlacementMode(selected_mode_raw)
    except ValueError as exc:
        raise PlacementPreferenceError("selected_mode is invalid") from exc

    base_state = SelectionState(base["state"])
    if base_state is not SelectionState.TIE_ABSTAINED:
        if preference is not None or admissibility is not None or refusal is not None:
            raise PlacementPreferenceError("preference is invalid when base_v1 did not tie")
        if state is not base_state or selected != base["selected"]:
            raise PlacementPreferenceError("v2 must preserve a non-tied v1 decision")
        expected_mode = base["selected_mode"]
        actual_mode = None if selected_mode is None else selected_mode.value
        if actual_mode != expected_mode:
            raise PlacementPreferenceError("v2 selected_mode must preserve base_v1")
    elif preference is None:
        if admissibility is not None or refusal is not None:
            raise PlacementPreferenceError("unresolved v2 tie without a receipt cannot carry preference status")
        if state is not SelectionState.TIE_ABSTAINED or selected is not None or selected_mode is not None:
            raise PlacementPreferenceError("unresolved v2 tie must preserve v1 abstention")
    else:
        if preference.responsibility_ref != base["responsibility_ref"]:
            raise PlacementPreferenceError("preference responsibility does not match base_v1")
        if preference.selection_input_digest != _selection_input_digest_from_wire(base):
            raise PlacementPreferenceError("preference does not bind the current base_v1 inputs")
        tied = tuple(base["tied_worker_ids"])
        if set(preference.preference_order) != set(tied) or len(preference.preference_order) != len(tied):
            raise PlacementPreferenceError("preference does not exactly cover the v1 tie")
        source_resolves = _capacity_source_resolves_exactly(
            preference.capacity_source, resolved_capacity_sources
        )
        if not source_resolves:
            if admissibility != PREFERENCE_INADMISSIBLE:
                raise PlacementPreferenceError(
                    "preference source does not resolve exactly at this seam"
                )
            if refusal != _capacity_source_refusal(preference.capacity_source):
                raise PlacementPreferenceError(
                    "inadmissible preference must name the unresolved Capacity source"
                )
            if state is not SelectionState.TIE_ABSTAINED or selected is not None or selected_mode is not None:
                raise PlacementPreferenceError(
                    "inadmissible preference must preserve v1 abstention"
                )
        else:
            if admissibility != PREFERENCE_ADMISSIBLE or refusal is not None:
                raise PlacementPreferenceError(
                    "resolved preference must be marked admissible without refusal"
                )
            if state is not SelectionState.SELECTED or selected is None or selected_mode is None:
                raise PlacementPreferenceError("resolved v2 tie must contain one selection")
            winner_id = preference.preference_order[0]
            if selected["worker_id"] != winner_id:
                raise PlacementPreferenceError("selected worker does not match Capacity preference")
            matching = [row for row in base["evidence"] if row["worker_id"] == winner_id]
            if len(matching) != 1 or matching[0]["mode"] != selected_mode.value:
                raise PlacementPreferenceError("selected mode does not match v1 candidate evidence")
            for field in ("provider", "account_label", "quota_class", "observed_at_ms"):
                if selected[field] != matching[0][field]:
                    raise PlacementPreferenceError("selected snapshot does not match v1 candidate evidence")

    return {
        "schema": SELECTION_V2_SCHEMA,
        "base_v1": base,
        "preference": None if preference is None else preference.to_dict(),
        "preference_admissibility": admissibility,
        "preference_refusal": refusal,
        "state": state.value,
        "selected": selected,
        "selected_mode": None if selected_mode is None else selected_mode.value,
        "selection_is_commitment": False,
    }


@dataclasses.dataclass(frozen=True, slots=True)
class PlacementSelectionDecisionV2:
    base_v1: PlacementSelectionDecision
    preference: CapacityPlacementPreference | None
    preference_admissibility: str | None
    preference_refusal: Mapping[str, str] | None
    state: SelectionState
    selected: Mapping[str, Any] | None
    selected_mode: PlacementMode | None

    def __post_init__(self) -> None:
        if not isinstance(self.base_v1, PlacementSelectionDecision):
            raise TypeError("base_v1 must be PlacementSelectionDecision")
        if not isinstance(self.state, SelectionState):
            raise TypeError("state must be SelectionState")
        if self.state is SelectionState.SELECTED:
            if self.selected is None or self.selected_mode is None:
                raise PlacementPreferenceError("selected v2 decision requires selected and selected_mode")
        elif self.selected is not None or self.selected_mode is not None:
            raise PlacementPreferenceError("non-selected v2 decision cannot carry a selected placement")
        if self.preference is not None and not isinstance(self.preference, CapacityPlacementPreference):
            raise TypeError("preference must be CapacityPlacementPreference or None")
        if self.preference is None:
            if self.preference_admissibility is not None or self.preference_refusal is not None:
                raise PlacementPreferenceError(
                    "preference status requires a Capacity preference receipt"
                )
        elif self.preference_admissibility == PREFERENCE_ADMISSIBLE:
            if self.preference_refusal is not None or self.state is not SelectionState.SELECTED:
                raise PlacementPreferenceError(
                    "admissible preference requires one selected placement and no refusal"
                )
        elif self.preference_admissibility == PREFERENCE_INADMISSIBLE:
            if (
                dict(self.preference_refusal or {})
                != _capacity_source_refusal(self.preference.capacity_source)
                or self.state is not SelectionState.TIE_ABSTAINED
            ):
                raise PlacementPreferenceError(
                    "inadmissible preference must name its unresolved source and abstain"
                )
        else:
            raise PlacementPreferenceError(
                "preference requires admissible or inadmissible disposition"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SELECTION_V2_SCHEMA,
            "base_v1": self.base_v1.to_dict(),
            "preference": None if self.preference is None else self.preference.to_dict(),
            "preference_admissibility": self.preference_admissibility,
            "preference_refusal": (
                None if self.preference_refusal is None else dict(self.preference_refusal)
            ),
            "state": self.state.value,
            "selected": None if self.selected is None else dict(self.selected),
            "selected_mode": None if self.selected_mode is None else self.selected_mode.value,
            "selection_is_commitment": False,
        }


def select_placement_v2(
    *,
    responsibility: ResponsibilityFact,
    demand: PlacementDemand,
    candidates: Sequence[PlacementCandidateFact],
    preference: CapacityPlacementPreference | None = None,
    resolved_capacity_sources: Mapping[str, bytes] | None = None,
) -> PlacementSelectionDecisionV2:
    """Run v1 unchanged, then resolve only an exact top tie with Capacity evidence."""
    if isinstance(candidates, (str, bytes)) or not isinstance(candidates, Sequence):
        raise TypeError("candidates must be a sequence of PlacementCandidateFact")
    candidate_tuple = tuple(candidates)
    base = select_placement(
        responsibility=responsibility,
        demand=demand,
        candidates=candidate_tuple,
    )
    if base.state is not SelectionState.TIE_ABSTAINED:
        if preference is not None:
            raise PlacementPreferenceError("preference is invalid when v1 did not tie")
        return PlacementSelectionDecisionV2(
            base_v1=base,
            preference=None,
            preference_admissibility=None,
            preference_refusal=None,
            state=base.state,
            selected=base.selected,
            selected_mode=base.selected_mode,
        )
    if preference is None:
        return PlacementSelectionDecisionV2(
            base_v1=base,
            preference=None,
            preference_admissibility=None,
            preference_refusal=None,
            state=base.state,
            selected=None,
            selected_mode=None,
        )
    if preference.responsibility_ref != base.responsibility_ref:
        raise PlacementPreferenceError("preference responsibility does not match selection")
    if preference.selection_input_digest != selection_input_digest(base):
        raise PlacementPreferenceError("preference does not bind the current selection inputs")
    if set(preference.preference_order) != set(base.tied_worker_ids):
        raise PlacementPreferenceError("preference no longer covers the exact tied workers")
    if not _capacity_source_resolves_exactly(
        preference.capacity_source, resolved_capacity_sources
    ):
        return PlacementSelectionDecisionV2(
            base_v1=base,
            preference=preference,
            preference_admissibility=PREFERENCE_INADMISSIBLE,
            preference_refusal=_capacity_source_refusal(preference.capacity_source),
            state=SelectionState.TIE_ABSTAINED,
            selected=None,
            selected_mode=None,
        )

    winner_id = preference.preference_order[0]
    matches = [candidate for candidate in candidate_tuple if candidate.worker_id == winner_id]
    if len(matches) != 1:
        raise PlacementPreferenceError("preferred worker is not uniquely present")
    winner = matches[0]
    selected = build_placement_snapshot(
        worker_id=winner.worker_id,
        quota_class=winner.quota_class,
        provider=winner.provider,
        account_label=winner.account_label,
        observed_at_ms=winner.observed_at_ms,
    )
    return PlacementSelectionDecisionV2(
        base_v1=base,
        preference=preference,
        preference_admissibility=PREFERENCE_ADMISSIBLE,
        preference_refusal=None,
        state=SelectionState.SELECTED,
        selected=selected,
        selected_mode=winner.mode,
    )


__all__ = [
    "CAPACITY_SOURCE_UNRESOLVED",
    "CapacityPlacementPreference",
    "PREFERENCE_ADMISSIBLE",
    "PREFERENCE_INADMISSIBLE",
    "PlacementPreferenceError",
    "PlacementSelectionDecisionV2",
    "PREFERENCE_SCHEMA",
    "SELECTION_V2_SCHEMA",
    "make_capacity_preference",
    "selection_input_digest",
    "select_placement_v2",
    "validate_capacity_preference",
    "validate_placement_selection_v2",
]
