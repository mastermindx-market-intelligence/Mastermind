"""Deterministic Chairman Control Room to protected Secretary grounding projection."""
from __future__ import annotations

import hashlib
import inspect
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from integrations.mastermind_secretary_mcp.adapter import (
    GroundingFact,
    GroundingRefusedError,
    GroundingSource,
    StewardGrounding,
    StewardUnavailableError,
)

CONTROL_ROOM_SCHEMA = "mastermind.chairman_control_room.v1"
DEFAULT_STALE_AFTER_SECONDS = 900
MAX_FACTS = 64
MAX_RESPONSIBILITIES = 4096
MAX_PUBLIC_AGE_SECONDS = 31_536_000

_WORK_RE = re.compile(r"^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,223}$")
_Z_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
_REASONS = frozenset({
    "AMBIGUOUS_JOIN", "DEPENDENCY_UNAVAILABLE", "NO_SOURCE", "POLICY_REFUSAL",
    "RESPONSIBILITY_UNKNOWN", "RUNTIME_UNKNOWN", "STALE_SOURCE",
    "STEWARD_DEGRADED", "SURFACE_UNKNOWN",
})
_RESP_STATE = {
    "active": "ACTIVE", "in_progress": "ACTIVE", "in-progress": "ACTIVE",
    "running": "ACTIVE", "started": "ACTIVE", "open": "ACTIVE",
    "blocked": "BLOCKED", "done": "COMPLETE", "complete": "COMPLETE",
    "completed": "COMPLETE", "finished": "COMPLETE", "killed": "COMPLETE",
    "waiting": "WAITING", "queued": "WAITING", "pending": "WAITING",
    "backlog": "WAITING", "todo": "WAITING", "paused": "WAITING",
}
_RUNTIME = {
    "claimed": "RUNNING", "running": "RUNNING", "checkpointed": "RUNNING",
    "executing": "RUNNING", "in_progress": "RUNNING", "started": "RUNNING",
    "paused": "PAUSED", "blocked": "PAUSED", "cancel_requested": "PAUSED",
    "queued": "IDLE", "pending": "IDLE", "ready": "IDLE",
}
_STOPPED = {"completed", "complete", "done", "failed", "cancelled", "canceled", "killed"}
_TARGET = {"chairman": "CHAIRMAN_REQUIRED", "ceo": "SOL_REQUIRED", "coo": "COO_REQUIRED"}

SnapshotProvider = Callable[[], Mapping[str, Any] | Awaitable[Mapping[str, Any]]]
Clock = Callable[[], datetime]


class ProjectionError(GroundingRefusedError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code if reason_code in _REASONS else "STEWARD_DEGRADED"
        super().__init__(self.reason_code)


@dataclass(frozen=True)
class _Fresh:
    value: str
    observed_at: str | None
    age: int | None
    reason: str | None


@dataclass(frozen=True)
class _View:
    generated_at: str | None
    agent_at: str | None
    cards: tuple[Mapping[str, Any], ...]
    by_public: Mapping[str, Mapping[str, Any]]
    public_by_work: Mapping[str, str]
    attention_targets: Mapping[str, tuple[str, ...]]
    runtime_db_present: bool | None
    bindings_path_present: bool
    conflicts: tuple[Mapping[str, Any], ...]
    reasons: tuple[str, ...]


def responsibility_ref_for(work_ref: str) -> str:
    if not isinstance(work_ref, str) or _WORK_RE.fullmatch(work_ref) is None:
        raise ProjectionError("RESPONSIBILITY_UNKNOWN")
    digest = hashlib.sha256(
        b"mastermind-steward-responsibility-v1\x00" + work_ref.encode()
    ).hexdigest()
    return f"responsibility:{digest}"


def _seq(value: object) -> list[Any]:
    return list(value) if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else []


def _map(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _parse_z(value: object) -> datetime | None:
    if not isinstance(value, str) or _Z_RE.fullmatch(value) is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _fresh(value: object, now: datetime, stale_after: int) -> _Fresh:
    parsed = _parse_z(value)
    if parsed is None:
        return _Fresh("UNKNOWN", None, None, "STALE_SOURCE")
    age = int((now - parsed).total_seconds())
    if age < -5:
        return _Fresh("UNKNOWN", None, None, "STALE_SOURCE")
    age = max(0, age)
    public_age = min(age, MAX_PUBLIC_AGE_SECONDS)
    if age > stale_after:
        return _Fresh("STALE", str(value), public_age, "STALE_SOURCE")
    return _Fresh("FRESH", str(value), public_age, None)


def _hash(domain: str, value: str) -> str:
    return hashlib.sha256(b"mastermind.steward.source.v1\0" + domain.encode() + b"\0" + value.encode()).hexdigest()


def _source(owner: str, prefix: str, identity: str, observed_at: object, now: datetime,
            stale_after: int, *, direct: str | None = None) -> tuple[GroundingSource, _Fresh]:
    freshness = _fresh(observed_at, now, stale_after)
    return GroundingSource(owner, direct or f"{prefix}:{_hash(owner, identity)}", freshness.observed_at), freshness


def _fact(subject: str, predicate: str, value: str | int | bool,
          source: GroundingSource, freshness: _Fresh) -> GroundingFact:
    return GroundingFact(subject, predicate, value, freshness.value, (source,))


def _reason_tuple(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value in _REASONS}))


def _result(facts: Sequence[GroundingFact], reasons: Sequence[str] = (), *, empty: str = "NO_SOURCE") -> StewardGrounding:
    chosen = tuple(facts[:MAX_FACTS])
    issue = set(_reason_tuple(reasons))
    if len(facts) > MAX_FACTS:
        issue.add("STEWARD_DEGRADED")
    for fact in chosen:
        if fact.freshness == "STALE":
            issue.add("STALE_SOURCE")
        elif fact.freshness == "UNKNOWN":
            issue.add("STEWARD_DEGRADED")
    if not chosen:
        issue.add(empty)
        return StewardGrounding("UNKNOWN", (), _reason_tuple(tuple(issue)))
    return StewardGrounding("DEGRADED" if issue else "FACTS", chosen, _reason_tuple(tuple(issue)))


def _responsibility_state(card: Mapping[str, Any]) -> tuple[str, list[str]]:
    agent = _map(card.get("agent_os"))
    found = {_RESP_STATE.get(str(agent.get(key)).strip().lower()) for key in ("state", "status") if agent.get(key) is not None}
    found.discard(None)
    if len(found) > 1:
        return "UNKNOWN", ["AMBIGUOUS_JOIN"]
    if found:
        return str(found.pop()), []
    return "UNKNOWN", ["NO_SOURCE"]


def _runtime_state(card: Mapping[str, Any], present: bool | None) -> tuple[str, list[str]]:
    jobs = [row for row in _seq(_map(card.get("executive")).get("jobs")) if isinstance(row, Mapping)]
    if len(jobs) > 1:
        return "UNKNOWN", ["AMBIGUOUS_JOIN"]
    statuses = [str(row.get("status") or "").strip().lower() for row in jobs if row.get("status") is not None]
    found = {_RUNTIME[status] for status in statuses if status in _RUNTIME}
    if len(found) > 1:
        return "UNKNOWN", ["AMBIGUOUS_JOIN"]
    if found:
        return found.pop(), []
    if statuses and all(status in _STOPPED for status in statuses):
        return "STOPPED", []
    if statuses:
        return "UNKNOWN", ["RUNTIME_UNKNOWN"]
    if present is True:
        return "IDLE", []
    if present is False:
        return "UNAVAILABLE", ["DEPENDENCY_UNAVAILABLE"]
    return "UNKNOWN", ["RUNTIME_UNKNOWN"]


def _blocker(card: Mapping[str, Any]) -> tuple[bool, str, list[str]]:
    agent = _map(card.get("agent_os"))
    if _seq(card.get("disagreements")):
        return True, "SOURCE_AMBIGUOUS", ["AMBIGUOUS_JOIN"]
    if _seq(agent.get("unmet_dependencies")):
        return True, "EXTERNAL_DEPENDENCY", []
    if not agent:
        return True, "SOURCE_UNKNOWN", ["STEWARD_DEGRADED"]
    if str(agent.get("state") or agent.get("status") or "").strip().lower() != "blocked":
        return False, "NONE", []
    code = str(agent.get("reason_code") or "").strip().lower()
    if any(token in code for token in ("authority", "chairman", "ceo", "sol")):
        return True, "AUTHORITY_REQUIRED", []
    if "capacity" in code:
        return True, "CAPACITY_REQUIRED", []
    if any(token in code for token in ("policy", "denied", "refus")):
        return True, "POLICY_REFUSAL", ["POLICY_REFUSAL"]
    if "runtime" in code:
        return True, "RUNTIME_UNAVAILABLE", ["RUNTIME_UNKNOWN"]
    if "surface" in code:
        return True, "SURFACE_UNAVAILABLE", ["SURFACE_UNKNOWN"]
    return True, "UNKNOWN", ["STEWARD_DEGRADED"]


class ControlRoomStewardReadPort:
    """Six-tool read port; every public method gathers exactly one Control Room snapshot."""

    def __init__(self, snapshot_provider: SnapshotProvider, *, clock: Clock,
                 stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS) -> None:
        if not callable(snapshot_provider) or not callable(clock):
            raise TypeError("snapshot_provider and clock are required")
        if isinstance(stale_after_seconds, bool) or not 1 <= stale_after_seconds <= 86_400:
            raise ValueError("stale_after_seconds must be between 1 and 86400")
        self._provider = snapshot_provider
        self._clock = clock
        self._stale = stale_after_seconds

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ProjectionError("STEWARD_DEGRADED")
        return value.astimezone(timezone.utc)

    async def _view(self) -> _View:
        try:
            value = self._provider()
            if inspect.isawaitable(value):
                value = await value
        except Exception as exc:
            raise StewardUnavailableError("control room unavailable") from exc
        if not isinstance(value, Mapping):
            raise StewardUnavailableError("control room unavailable")
        reasons: set[str] = set()
        if value.get("schema") != CONTROL_ROOM_SCHEMA:
            reasons.add("DEPENDENCY_UNAVAILABLE")
        generated = value.get("generated_at") if _parse_z(value.get("generated_at")) else None
        if generated is None:
            reasons.add("STALE_SOURCE")
        sources = _map(value.get("sources"))
        agent_at = sources.get("agent_os_state_generated_at")
        if _parse_z(agent_at) is None:
            agent_at = generated
        runtime_present = sources.get("runtime_db_present")
        runtime_present = runtime_present if type(runtime_present) is bool else None
        bindings_present = sources.get("bindings_path_present") is True
        if _seq(value.get("degraded")):
            reasons.add("STEWARD_DEGRADED")

        raw_cards = [row for row in _seq(value.get("work")) if isinstance(row, Mapping)]
        if len(raw_cards) > MAX_RESPONSIBILITIES:
            raw_cards = raw_cards[:MAX_RESPONSIBILITIES]
            reasons.add("STEWARD_DEGRADED")
        by_public: dict[str, Mapping[str, Any]] = {}
        public_by_work: dict[str, str] = {}
        for card in raw_cards:
            work_ref = card.get("work_ref")
            if not isinstance(work_ref, str) or _WORK_RE.fullmatch(work_ref) is None:
                reasons.add("STEWARD_DEGRADED")
                continue
            public = responsibility_ref_for(work_ref)
            if public in by_public or work_ref in public_by_work:
                raise ProjectionError("AMBIGUOUS_JOIN")
            by_public[public] = card
            public_by_work[work_ref] = public

        rank = {"BLOCKED": 0, "ACTIVE": 1, "WAITING": 2, "UNKNOWN": 3, "COMPLETE": 4}
        cards = tuple(sorted(by_public.values(), key=lambda card: (
            0 if _seq(card.get("attention_ids")) else 1,
            rank.get(_responsibility_state(card)[0], 5),
            str(card.get("work_ref") or ""),
        )))
        targets: dict[str, set[str]] = {}
        for bucket, target in _TARGET.items():
            for row in _seq(_map(value.get("attention")).get(bucket)):
                if isinstance(row, Mapping) and isinstance(row.get("attention_id"), str):
                    targets.setdefault(str(row["attention_id"]), set()).add(target)
        conflicts = tuple(row for row in _seq(value.get("binding_conflicts")) if isinstance(row, Mapping))
        return _View(generated, agent_at, cards, by_public, public_by_work,
                     {key: tuple(sorted(found)) for key, found in targets.items()},
                     runtime_present, bindings_present, conflicts, _reason_tuple(tuple(reasons)))

    @staticmethod
    def _card(view: _View, ref: str) -> Mapping[str, Any] | None:
        return view.by_public.get(ref) if isinstance(ref, str) else None

    def _responsibility(self, view: _View, card: Mapping[str, Any], now: datetime) -> tuple[list[GroundingFact], list[str]]:
        work_ref = str(card["work_ref"])
        public = view.public_by_work[work_ref]
        state, reasons = _responsibility_state(card)
        source, fresh = _source("agent_os", "WS", work_ref, view.agent_at, now, self._stale, direct=work_ref)
        ids = tuple(sorted({item for item in _seq(card.get("attention_ids")) if isinstance(item, str) and item}))
        attention_source, attention_fresh = _source("executive_os", "MAS", work_ref + "\0" + "|".join(ids), view.generated_at, now, self._stale)
        return [
            _fact(public, "responsibility.state", state, source, fresh),
            _fact(public, "responsibility.requires_attention", bool(ids), attention_source, attention_fresh),
        ], [*reasons, *[item for item in (fresh.reason, attention_fresh.reason) if item]]

    async def list_responsibilities(self) -> StewardGrounding:
        view, now = await self._view(), self._now()
        facts: list[GroundingFact] = []
        reasons = list(view.reasons)
        for card in view.cards[:MAX_FACTS]:
            work_ref = str(card["work_ref"])
            state, state_reasons = _responsibility_state(card)
            source, fresh = _source("agent_os", "WS", work_ref, view.agent_at, now, self._stale, direct=work_ref)
            facts.append(_fact(view.public_by_work[work_ref], "responsibility.state", state, source, fresh))
            reasons.extend(state_reasons)
            if fresh.reason:
                reasons.append(fresh.reason)
        if len(view.cards) > MAX_FACTS:
            reasons.append("STEWARD_DEGRADED")
        return _result(facts, reasons)

    async def get_responsibility(self, responsibility_ref: str) -> StewardGrounding:
        view = await self._view()
        card = self._card(view, responsibility_ref)
        if card is None:
            return StewardGrounding("UNKNOWN", (), ("RESPONSIBILITY_UNKNOWN",))
        facts, reasons = self._responsibility(view, card, self._now())
        return _result(facts, [*view.reasons, *reasons])

    async def get_attention(self) -> StewardGrounding:
        view, now = await self._view(), self._now()
        facts: list[GroundingFact] = []
        reasons = list(view.reasons)
        for card in view.cards[:MAX_FACTS]:
            ids = tuple(sorted({item for item in _seq(card.get("attention_ids")) if isinstance(item, str) and item}))
            states: set[str] = set()
            missing = False
            for identifier in ids:
                found = view.attention_targets.get(identifier)
                if found:
                    states.update(found)
                else:
                    missing = True
            if not ids:
                value = "NONE"
            elif len(states) == 1 and not missing:
                value = next(iter(states))
            else:
                value = "UNKNOWN"
                reasons.append("AMBIGUOUS_JOIN" if len(states) > 1 else "STEWARD_DEGRADED")
            work_ref = str(card["work_ref"])
            source, fresh = _source("executive_os", "MAS", work_ref + "\0" + "|".join(ids), view.generated_at, now, self._stale)
            facts.append(_fact(view.public_by_work[work_ref], "attention.state", value, source, fresh))
            if fresh.reason:
                reasons.append(fresh.reason)
        return _result(facts, reasons)

    async def get_current_runtime(self, responsibility_ref: str) -> StewardGrounding:
        view = await self._view()
        card = self._card(view, responsibility_ref)
        if card is None:
            return StewardGrounding("UNKNOWN", (), ("RESPONSIBILITY_UNKNOWN",))
        now = self._now()
        work_ref = str(card["work_ref"])
        public = view.public_by_work[work_ref]
        runtime, reasons = _runtime_state(card, view.runtime_db_present)
        jobs = [row for row in _seq(_map(card.get("executive")).get("jobs")) if isinstance(row, Mapping)]
        job_identity = "|".join(sorted(str(row.get("job_id") or "") for row in jobs)) or work_ref
        executive_source, executive_fresh = _source("executive_os", "MAS", job_identity, view.generated_at, now, self._stale)
        bindings = [row for row in _seq(card.get("bindings")) if isinstance(row, Mapping)]
        binding_identity = "|".join(sorted(str(row.get("binding_id") or "") for row in bindings)) or work_ref
        observed = bindings[0].get("last_verified_at") or bindings[0].get("observed_at") if len(bindings) == 1 else view.generated_at
        binding_source, binding_fresh = _source("runtime_binding", "RUNTIME", binding_identity, observed, now, self._stale)
        if not view.bindings_path_present:
            continuity, continuity_reasons = "UNAVAILABLE", ["DEPENDENCY_UNAVAILABLE"]
        elif not bindings:
            continuity, continuity_reasons = "UNBOUND", []
        elif len(bindings) > 1:
            continuity, continuity_reasons = "AMBIGUOUS", ["AMBIGUOUS_JOIN"]
        elif binding_fresh.value == "STALE":
            continuity, continuity_reasons = "STALE", ["STALE_SOURCE"]
        elif binding_fresh.value == "FRESH":
            continuity, continuity_reasons = "BOUND", []
        else:
            continuity, continuity_reasons = "UNKNOWN", ["RUNTIME_UNKNOWN"]
        facts = [
            _fact(public, "runtime.state", runtime, executive_source, executive_fresh),
            _fact(public, "runtime.continuity", continuity, binding_source, binding_fresh),
        ]
        if executive_fresh.age is not None:
            facts.append(
                _fact(
                    public,
                    "runtime.age_seconds",
                    executive_fresh.age,
                    executive_source,
                    executive_fresh,
                )
            )
        reasons.extend(continuity_reasons)
        reasons.extend(item for item in (executive_fresh.reason, binding_fresh.reason) if item)
        return _result(facts, [*view.reasons, *reasons])

    async def explain_blocker(self, responsibility_ref: str) -> StewardGrounding:
        view = await self._view()
        card = self._card(view, responsibility_ref)
        if card is None:
            return StewardGrounding("UNKNOWN", (), ("RESPONSIBILITY_UNKNOWN",))
        now = self._now()
        work_ref = str(card["work_ref"])
        public = view.public_by_work[work_ref]
        present, kind, reasons = _blocker(card)
        source, fresh = _source("agent_os", "WS", work_ref, view.agent_at, now, self._stale, direct=work_ref)
        return _result([
            _fact(public, "blocker.present", present, source, fresh),
            _fact(public, "blocker.kind", kind, source, fresh),
        ], [*view.reasons, *reasons, *([fresh.reason] if fresh.reason else [])])

    @staticmethod
    def _has_conflict(view: _View, card: Mapping[str, Any]) -> bool:
        work_ref = card.get("work_ref")
        ids = {str(row.get("binding_id")) for row in _seq(card.get("bindings")) if isinstance(row, Mapping) and row.get("binding_id") is not None}
        for conflict in view.conflicts:
            if conflict.get("work_ref") == work_ref:
                return True
            candidate = {str(value) for key, value in conflict.items() if "binding" in str(key).lower() and value is not None}
            if ids & candidate:
                return True
        return False

    async def resolve_surface(self, responsibility_ref: str) -> StewardGrounding:
        view = await self._view()
        card = self._card(view, responsibility_ref)
        if card is None:
            return StewardGrounding("UNKNOWN", (), ("RESPONSIBILITY_UNKNOWN",))
        now = self._now()
        work_ref = str(card["work_ref"])
        public = view.public_by_work[work_ref]
        bindings = [row for row in _seq(card.get("bindings")) if isinstance(row, Mapping)]
        identity = "|".join(sorted(str(row.get("binding_id") or "") for row in bindings)) or work_ref
        observed = bindings[0].get("last_verified_at") or bindings[0].get("observed_at") if len(bindings) == 1 else view.generated_at
        source, fresh = _source("surface_binding", "SURFACE", identity, observed, now, self._stale)
        reasons = list(view.reasons)
        if not view.bindings_path_present:
            health, repair = "UNKNOWN", True
            reasons.append("SURFACE_UNKNOWN")
        elif self._has_conflict(view, card) or len(bindings) > 1:
            health, repair = "AMBIGUOUS", True
            reasons.append("AMBIGUOUS_JOIN")
        elif not bindings:
            health, repair = "TARGET_MISSING", True
            reasons.append("SURFACE_UNKNOWN")
        elif fresh.value == "STALE":
            health, repair = "DEGRADED", True
            reasons.append("STALE_SOURCE")
        else:
            health, repair = "UNKNOWN", fresh.value != "FRESH"
            if repair:
                reasons.append("SURFACE_UNKNOWN")
        facts = [
            _fact(public, "surface.health", health, source, fresh),
            _fact(public, "surface.repair_required", repair, source, fresh),
        ]
        if fresh.age is not None:
            facts.append(_fact(public, "surface.observation_age_seconds", fresh.age, source, fresh))
        return _result(facts, reasons)


__all__ = [
    "CONTROL_ROOM_SCHEMA", "ControlRoomStewardReadPort",
    "DEFAULT_STALE_AFTER_SECONDS", "ProjectionError", "responsibility_ref_for",
]
