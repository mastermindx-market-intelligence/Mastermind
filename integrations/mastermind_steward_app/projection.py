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
from integrations.mastermind_secretary_mcp.schemas import (
    GatewayError,
    MAX_FACTS,
    PUBLIC_FACT_CONTRACTS,
)

CONTROL_ROOM_SCHEMA = "mastermind.chairman_control_room.v1"
DEFAULT_STALE_AFTER_SECONDS = 900
MAX_RESPONSIBILITIES = 4096
MAX_PUBLIC_AGE_SECONDS = 31_536_000

_WORK_RE = re.compile(r"^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,223}$")
_Z_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
_UUID_RE = re.compile(
    r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[1-5][0-9A-Fa-f]{3}-"
    r"[89ABab][0-9A-Fa-f]{3}-[0-9A-Fa-f]{12}$"
)
_REASONS = frozenset({
    "AMBIGUOUS_JOIN", "DEPENDENCY_UNAVAILABLE", "EFFECT_UNKNOWN", "NO_SOURCE",
    "POLICY_REFUSAL", "RESPONSIBILITY_UNKNOWN", "RUNTIME_UNKNOWN",
    "STALE_SOURCE", "STEWARD_DEGRADED", "SURFACE_UNKNOWN",
})
_RESP_STATE = {
    "active": "ACTIVE", "in_progress": "ACTIVE", "in-progress": "ACTIVE",
    "running": "ACTIVE", "started": "ACTIVE", "open": "ACTIVE",
    "blocked": "BLOCKED", "done": "COMPLETE", "complete": "COMPLETE",
    "completed": "COMPLETE", "finished": "COMPLETE", "killed": "COMPLETE",
    "waiting": "WAITING", "queued": "WAITING", "pending": "WAITING",
    "backlog": "WAITING", "todo": "WAITING", "paused": "WAITING",
    "ready": "WAITING", "proposed": "WAITING",
}
_RUNTIME = {
    "claimed": "RUNNING", "running": "RUNNING", "checkpointed": "RUNNING",
    "executing": "RUNNING", "in_progress": "RUNNING", "started": "RUNNING",
    "paused": "PAUSED", "blocked": "PAUSED", "cancel_requested": "PAUSED",
    "queued": "IDLE", "pending": "IDLE", "ready": "IDLE",
}
_STOPPED = {"completed", "complete", "done", "failed", "cancelled", "canceled", "killed"}
_TARGET = {"chairman": "CHAIRMAN_REQUIRED", "ceo": "SOL_REQUIRED", "coo": "COO_REQUIRED"}
_TARGET_SEAT = {"chairman": "CHAIRMAN", "ceo": "CEO", "coo": "COO"}

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
    attention_by_id: Mapping[str, tuple[Mapping[str, Any], ...]]
    attention_valid: bool
    runtime_db_present: bool | None
    bindings_path_present: bool
    conflicts: tuple[Mapping[str, Any], ...]
    conflicts_valid: bool
    reasons: tuple[str, ...]


def responsibility_ref_for(work_ref: str) -> str:
    if not isinstance(work_ref, str) or _WORK_RE.fullmatch(work_ref) is None:
        raise ProjectionError("RESPONSIBILITY_UNKNOWN")
    digest = hashlib.sha256(
        b"mastermind-steward-responsibility-v1\x00" + work_ref.encode()
    ).hexdigest()
    return f"responsibility:{digest}"


def _attention_work_ref(value: object, source: object) -> str | None:
    if not isinstance(value, str) or not value or source not in {"agent_os", "runtime"}:
        return None
    if source == "runtime" and not value.startswith("WS:"):
        return None
    candidate = value if value.startswith("WS:") else f"WS:{value}"
    return candidate if _WORK_RE.fullmatch(candidate) is not None else None


def _seq(value: object) -> list[Any]:
    return list(value) if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else []


def _strict_sequence(value: object) -> tuple[list[Any], bool]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return [], False
    return list(value), True


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
    raw_age = (now - parsed).total_seconds()
    if raw_age < 0:
        return _Fresh("UNKNOWN", None, None, "STALE_SOURCE")
    age = int(raw_age)
    public_age = age if age <= MAX_PUBLIC_AGE_SECONDS else None
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


def _public_value(predicate: str, value: object) -> tuple[str | int | bool | None, str | None]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, "NO_SOURCE"
    try:
        return PUBLIC_FACT_CONTRACTS[predicate].normalize(value), None
    except GatewayError:
        return None, "STEWARD_DEGRADED"


def _append_fact(
    facts: list[GroundingFact],
    reasons: list[str],
    *,
    subject: str,
    predicate: str,
    value: object,
    source: GroundingSource,
    freshness: _Fresh,
) -> None:
    public, reason = _public_value(predicate, value)
    if reason is not None:
        reasons.append(reason)
        return
    assert public is not None
    facts.append(_fact(subject, predicate, public, source, freshness))


def _reason_tuple(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value in _REASONS}))


def _valid_conflict_row(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    work_ref = value.get("work_ref")
    role = value.get("role")
    binding_ids, ids_valid = _strict_sequence(value.get("binding_ids"))
    return (
        isinstance(work_ref, str)
        and _WORK_RE.fullmatch(work_ref) is not None
        and isinstance(role, str)
        and bool(role.strip())
        and ids_valid
        and bool(binding_ids)
        and all(
            isinstance(binding_id, str) and bool(binding_id.strip())
            for binding_id in binding_ids
        )
    )


def _result(facts: Sequence[GroundingFact], reasons: Sequence[str] = (), *, empty: str = "NO_SOURCE") -> StewardGrounding:
    issue = set(_reason_tuple(reasons))
    if len(facts) > MAX_FACTS:
        issue.add("STEWARD_DEGRADED")
        return StewardGrounding("UNKNOWN", (), _reason_tuple(tuple(issue)))
    chosen = tuple(facts)
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
    raw = [
        str(agent.get(key)).strip().lower()
        for key in ("state", "status")
        if agent.get(key) is not None and str(agent.get(key)).strip()
    ]
    if any(value not in _RESP_STATE for value in raw):
        return "UNKNOWN", ["STEWARD_DEGRADED"]
    found = {_RESP_STATE[value] for value in raw}
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
    if jobs and not statuses:
        return "UNKNOWN", ["RUNTIME_UNKNOWN"]
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


def _blocker(card: Mapping[str, Any]) -> tuple[bool | None, str | None, list[str]]:
    agent = _map(card.get("agent_os"))
    disagreements, disagreements_valid = _strict_sequence(card.get("disagreements"))
    if not disagreements_valid or any(
        not isinstance(item, str) or not item.strip()
        for item in disagreements
    ):
        return None, None, ["STEWARD_DEGRADED"]
    dependencies, dependencies_valid = _strict_sequence(
        agent.get("unmet_dependencies")
    )
    if not dependencies_valid or any(
        not isinstance(item, str) or not item.strip()
        for item in dependencies
    ):
        return None, None, ["STEWARD_DEGRADED"]
    if disagreements:
        return True, "SOURCE_AMBIGUOUS", ["AMBIGUOUS_JOIN"]
    if dependencies:
        return True, "EXTERNAL_DEPENDENCY", []
    if not agent:
        return True, "SOURCE_UNKNOWN", ["STEWARD_DEGRADED"]
    state, state_reasons = _responsibility_state(card)
    if state == "UNKNOWN":
        return None, None, state_reasons or ["STEWARD_DEGRADED"]
    if state != "BLOCKED":
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
            raise StewardUnavailableError("control room schema unavailable")
        generated = value.get("generated_at") if _parse_z(value.get("generated_at")) else None
        if generated is None:
            reasons.add("STALE_SOURCE")
        sources = _map(value.get("sources"))
        agent_at = sources.get("agent_os_state_generated_at")
        if _parse_z(agent_at) is None:
            agent_at = None
            reasons.add("STALE_SOURCE")
        runtime_present = sources.get("runtime_db_present")
        runtime_present = runtime_present if type(runtime_present) is bool else None
        bindings_present = sources.get("bindings_path_present") is True
        degraded, degraded_valid = _strict_sequence(value.get("degraded"))
        if (
            not degraded_valid
            or any(
                not isinstance(item, str) or not item.strip()
                for item in degraded
            )
            or degraded
        ):
            reasons.add("STEWARD_DEGRADED")

        raw_work = _seq(value.get("work"))
        raw_cards = [row for row in raw_work if isinstance(row, Mapping)]
        if len(raw_cards) != len(raw_work):
            reasons.add("STEWARD_DEGRADED")
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
            try:
                PUBLIC_FACT_CONTRACTS["responsibility.identity"].normalize(work_ref)
            except GatewayError:
                reasons.add("STEWARD_DEGRADED")
                continue
            public = responsibility_ref_for(work_ref)
            if public in by_public or work_ref in public_by_work:
                raise ProjectionError("AMBIGUOUS_JOIN")
            by_public[public] = card
            public_by_work[work_ref] = public

        rank = {
            "BLOCKED": 0,
            "ACTIVE": 1,
            "WAITING": 2,
            "UNKNOWN": 3,
            "COMPLETE": 4,
        }
        cards = tuple(sorted(by_public.values(), key=lambda card: (
            0 if _seq(card.get("attention_ids")) else 1,
            rank.get(_responsibility_state(card)[0], 5),
            str(card.get("work_ref") or ""),
        )))
        attention_by_id: dict[str, list[Mapping[str, Any]]] = {}
        attention_valid = True
        raw_attention = value.get("attention")
        if not isinstance(raw_attention, Mapping):
            raw_attention = {}
            attention_valid = False
            reasons.add("STEWARD_DEGRADED")
        for bucket in _TARGET:
            rows, rows_valid = _strict_sequence(raw_attention.get(bucket))
            if not rows_valid:
                attention_valid = False
                reasons.add("STEWARD_DEGRADED")
            for row in rows:
                if not isinstance(row, Mapping):
                    attention_valid = False
                    reasons.add("STEWARD_DEGRADED")
                    continue
                identifier = row.get("attention_id")
                if not isinstance(identifier, str) or not identifier:
                    attention_valid = False
                    reasons.add("STEWARD_DEGRADED")
                    continue
                if str(row.get("target") or "").strip().lower() != bucket:
                    attention_valid = False
                    reasons.add("AMBIGUOUS_JOIN")
                    continue
                attention_by_id.setdefault(identifier, []).append(row)
        raw_conflicts, conflicts_valid = _strict_sequence(
            value.get("binding_conflicts")
        )
        conflicts = tuple(
            row for row in raw_conflicts if _valid_conflict_row(row)
        )
        if not conflicts_valid or len(conflicts) != len(raw_conflicts):
            conflicts_valid = False
            reasons.add("STEWARD_DEGRADED")
        return _View(generated, agent_at, cards, by_public, public_by_work,
                     {key: tuple(rows) for key, rows in attention_by_id.items()},
                     attention_valid, runtime_present, bindings_present,
                     conflicts, conflicts_valid, _reason_tuple(tuple(reasons)))

    @staticmethod
    def _card(view: _View, ref: str) -> Mapping[str, Any] | None:
        return view.by_public.get(ref) if isinstance(ref, str) else None

    def _responsibility(self, view: _View, card: Mapping[str, Any], now: datetime) -> tuple[list[GroundingFact], list[str]]:
        work_ref = str(card["work_ref"])
        public = view.public_by_work[work_ref]
        agent = _map(card.get("agent_os"))
        if not agent:
            return [], ["NO_SOURCE"]
        state, reasons = _responsibility_state(card)
        source, fresh = _source("agent_os", "WS", work_ref, view.agent_at, now, self._stale, direct=work_ref)
        facts: list[GroundingFact] = []
        fact_reasons: list[str] = []
        _append_fact(
            facts,
            fact_reasons,
            subject=public,
            predicate="responsibility.identity",
            value=work_ref,
            source=source,
            freshness=fresh,
        )
        _append_fact(
            facts,
            fact_reasons,
            subject=public,
            predicate="responsibility.title",
            value=agent.get("title"),
            source=source,
            freshness=fresh,
        )
        _append_fact(
            facts,
            fact_reasons,
            subject=public,
            predicate="responsibility.next_action",
            value=agent.get("next_action"),
            source=source,
            freshness=fresh,
        )
        if state != "UNKNOWN":
            _append_fact(
                facts,
                fact_reasons,
                subject=public,
                predicate="responsibility.state",
                value=state,
                source=source,
                freshness=fresh,
            )
        elif not reasons:
            fact_reasons.append("NO_SOURCE")
        return facts, [
            *reasons,
            *fact_reasons,
            *([fresh.reason] if fresh.reason else []),
        ]

    async def list_responsibilities(self) -> StewardGrounding:
        view, now = await self._view(), self._now()
        facts: list[GroundingFact] = []
        reasons = list(view.reasons)
        represented = 0
        for card in view.cards:
            bundle, bundle_reasons = self._responsibility(view, card, now)
            if bundle and len(facts) + len(bundle) > MAX_FACTS:
                reasons.append("STEWARD_DEGRADED")
                break
            facts.extend(bundle)
            reasons.extend(bundle_reasons)
            represented += 1
        if represented < len(view.cards):
            reasons.append("STEWARD_DEGRADED")
        return _result(facts, reasons)

    async def get_responsibility(self, responsibility_ref: str) -> StewardGrounding:
        view = await self._view()
        card = self._card(view, responsibility_ref)
        if card is None:
            return StewardGrounding("UNKNOWN", (), ("RESPONSIBILITY_UNKNOWN",))
        facts, reasons = self._responsibility(view, card, self._now())
        return _result(facts, [*view.reasons, *reasons, "NO_SOURCE"])

    async def get_attention(self) -> StewardGrounding:
        view, now = await self._view(), self._now()
        if not view.attention_valid:
            return _result(
                (),
                [*view.reasons, "STEWARD_DEGRADED"],
                empty="STEWARD_DEGRADED",
            )
        facts: list[GroundingFact] = []
        reasons = list(view.reasons)
        represented = 0
        for card in view.cards:
            raw_ids, ids_valid = _strict_sequence(card.get("attention_ids"))
            if not ids_valid or any(
                not isinstance(item, str) or not item
                for item in raw_ids
            ):
                reasons.append("STEWARD_DEGRADED")
                continue
            ids = tuple(sorted(raw_ids))
            if not ids:
                continue
            if len(ids) != 1:
                reasons.append("AMBIGUOUS_JOIN")
                continue
            work_ref = str(card["work_ref"])
            identifier = ids[0]
            rows = view.attention_by_id.get(identifier, ())
            if len(rows) != 1:
                reasons.append("AMBIGUOUS_JOIN" if rows else "STEWARD_DEGRADED")
                continue
            row = rows[0]
            if _attention_work_ref(
                row.get("workstream"), row.get("source")
            ) != work_ref:
                reasons.append("AMBIGUOUS_JOIN")
                continue
            target = str(row.get("target") or "").strip().lower()
            state = _TARGET.get(target)
            target_seat = _TARGET_SEAT.get(target)
            source, fresh = _source(
                "executive_inbox",
                "executive-inbox",
                identifier,
                view.generated_at,
                now,
                self._stale,
            )
            public = view.public_by_work[work_ref]
            bundle: list[GroundingFact] = []
            bundle_reasons: list[str] = []
            candidates = (
                ("attention.ref", f"EXEC:{_hash('attention', identifier)}"),
                ("attention.target_seat", target_seat),
                ("attention.kind", row.get("kind")),
                ("attention.reason", row.get("reason")),
                ("attention.state", state),
            )
            for predicate, value in candidates:
                _append_fact(
                    bundle,
                    bundle_reasons,
                    subject=public,
                    predicate=predicate,
                    value=value,
                    source=source,
                    freshness=fresh,
                )
            # Control Room v1 carries no authoritative requested_action field.
            # existing_next_actions is a distinct runtime-owned list and must
            # not be relabelled to complete the protected Secretary bundle.
            bundle_reasons.append("NO_SOURCE")
            if len(facts) + len(bundle) > MAX_FACTS:
                reasons.append("STEWARD_DEGRADED")
                break
            facts.extend(bundle)
            reasons.extend(bundle_reasons)
            represented += 1
            if fresh.reason:
                reasons.append(fresh.reason)
        if represented < sum(
            1
            for card in view.cards
            if any(
                isinstance(item, str) and item
                for item in _seq(card.get("attention_ids"))
            )
        ) and len(facts) >= MAX_FACTS:
            reasons.append("STEWARD_DEGRADED")
        return _result(facts, reasons)

    async def get_current_runtime(self, responsibility_ref: str) -> StewardGrounding:
        view = await self._view()
        card = self._card(view, responsibility_ref)
        if card is None:
            return StewardGrounding("UNKNOWN", (), ("RESPONSIBILITY_UNKNOWN",))
        now = self._now()
        work_ref = str(card["work_ref"])
        public = view.public_by_work[work_ref]
        executive = _map(card.get("executive"))
        raw_jobs, jobs_valid = _strict_sequence(executive.get("jobs"))
        if not jobs_valid or any(not isinstance(row, Mapping) for row in raw_jobs):
            return _result(
                (),
                [
                    *view.reasons,
                    "EFFECT_UNKNOWN",
                    "RUNTIME_UNKNOWN",
                    "STEWARD_DEGRADED",
                ],
                empty="RUNTIME_UNKNOWN",
            )
        jobs = [row for row in raw_jobs if isinstance(row, Mapping)]
        if jobs and executive.get("joined_by") != "ceo_intent_provenance":
            return _result(
                (),
                [
                    *view.reasons,
                    "AMBIGUOUS_JOIN",
                    "EFFECT_UNKNOWN",
                    "RUNTIME_UNKNOWN",
                ],
                empty="AMBIGUOUS_JOIN",
            )
        if len(jobs) != 1:
            if len(jobs) > 1:
                reason = "AMBIGUOUS_JOIN"
            elif view.runtime_db_present is False:
                reason = "DEPENDENCY_UNAVAILABLE"
            else:
                reason = "RUNTIME_UNKNOWN"
            return _result((), [*view.reasons, reason], empty=reason)
        if jobs[0].get("workstream") != work_ref:
            return _result(
                (),
                [*view.reasons, "AMBIGUOUS_JOIN"],
                empty="AMBIGUOUS_JOIN",
            )
        job_id = jobs[0].get("job_id")
        job_status = jobs[0].get("status")
        if (
            not isinstance(job_id, str)
            or not job_id
            or not isinstance(job_status, str)
            or not job_status.strip()
        ):
            return _result(
                (),
                [
                    *view.reasons,
                    "EFFECT_UNKNOWN",
                    "RUNTIME_UNKNOWN",
                    "STEWARD_DEGRADED",
                ],
                empty="RUNTIME_UNKNOWN",
            )

        runtime, reasons = _runtime_state(card, view.runtime_db_present)
        executive_source, executive_fresh = _source(
            "executive_os",
            "executive-runtime",
            job_id,
            view.generated_at,
            now,
            self._stale,
        )
        facts: list[GroundingFact] = []
        fact_reasons: list[str] = []
        _append_fact(
            facts,
            fact_reasons,
            subject=public,
            predicate="runtime.state",
            value=runtime,
            source=executive_source,
            freshness=executive_fresh,
        )
        _append_fact(
            facts,
            fact_reasons,
            subject=public,
            predicate="runtime.effect_state",
            value="EFFECT_UNKNOWN",
            source=executive_source,
            freshness=executive_fresh,
        )
        if executive_fresh.age is not None:
            _append_fact(
                facts,
                fact_reasons,
                subject=public,
                predicate="runtime.age_seconds",
                value=executive_fresh.age,
                source=executive_source,
                freshness=executive_fresh,
            )
        return _result(
            facts,
            [
                *view.reasons,
                *reasons,
                *fact_reasons,
                "EFFECT_UNKNOWN",
                "RUNTIME_UNKNOWN",
                *([executive_fresh.reason] if executive_fresh.reason else []),
            ],
        )

    async def explain_blocker(self, responsibility_ref: str) -> StewardGrounding:
        view = await self._view()
        card = self._card(view, responsibility_ref)
        if card is None:
            return StewardGrounding("UNKNOWN", (), ("RESPONSIBILITY_UNKNOWN",))
        now = self._now()
        work_ref = str(card["work_ref"])
        public = view.public_by_work[work_ref]
        agent = _map(card.get("agent_os"))
        if not agent:
            return _result((), [*view.reasons, "NO_SOURCE"])
        present, kind, reasons = _blocker(card)
        source, fresh = _source("agent_os", "WS", work_ref, view.agent_at, now, self._stale, direct=work_ref)
        facts: list[GroundingFact] = []
        fact_reasons: list[str] = []
        for predicate, value in (
            ("blocker.present", present),
            ("blocker.kind", kind),
            ("blocker.explanation", agent.get("reason")),
        ):
            _append_fact(
                facts,
                fact_reasons,
                subject=public,
                predicate=predicate,
                value=value,
                source=source,
                freshness=fresh,
            )
        return _result(
            facts,
            [
                *view.reasons,
                *reasons,
                *fact_reasons,
                *([fresh.reason] if fresh.reason else []),
            ],
        )

    @staticmethod
    def _has_conflict(view: _View, card: Mapping[str, Any]) -> bool:
        work_ref = card.get("work_ref")
        ids = {str(row.get("binding_id")) for row in _seq(card.get("bindings")) if isinstance(row, Mapping) and row.get("binding_id") is not None}
        for conflict in view.conflicts:
            if conflict.get("work_ref") == work_ref:
                return True
            binding_ids, _ = _strict_sequence(conflict.get("binding_ids"))
            if ids & set(binding_ids):
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
        raw_bindings, bindings_valid = _strict_sequence(card.get("bindings"))
        reasons = list(view.reasons)
        if not bindings_valid or any(
            not isinstance(row, Mapping) for row in raw_bindings
        ):
            return _result(
                (),
                [*reasons, "STEWARD_DEGRADED", "SURFACE_UNKNOWN"],
                empty="SURFACE_UNKNOWN",
            )
        bindings = [row for row in raw_bindings if isinstance(row, Mapping)]
        if not view.bindings_path_present:
            return _result(
                (),
                [*reasons, "DEPENDENCY_UNAVAILABLE", "SURFACE_UNKNOWN"],
                empty="SURFACE_UNKNOWN",
            )
        elif not view.conflicts_valid:
            return _result(
                (),
                [*reasons, "STEWARD_DEGRADED", "SURFACE_UNKNOWN"],
                empty="SURFACE_UNKNOWN",
            )
        elif self._has_conflict(view, card) or len(bindings) > 1:
            return _result(
                (),
                [*reasons, "AMBIGUOUS_JOIN", "SURFACE_UNKNOWN"],
                empty="SURFACE_UNKNOWN",
            )
        elif not bindings:
            return _result((), [*reasons, "SURFACE_UNKNOWN"], empty="SURFACE_UNKNOWN")

        binding = bindings[0]
        if binding.get("work_ref") != work_ref:
            return _result(
                (),
                [*reasons, "AMBIGUOUS_JOIN", "SURFACE_UNKNOWN"],
                empty="AMBIGUOUS_JOIN",
            )
        identity = binding.get("binding_id")
        if not isinstance(identity, str) or _UUID_RE.fullmatch(identity) is None:
            return _result(
                (),
                [*reasons, "STEWARD_DEGRADED", "SURFACE_UNKNOWN"],
                empty="SURFACE_UNKNOWN",
            )
        observed = binding.get("last_verified_at") or binding.get("observed_at")
        source, fresh = _source(
            "surface_bindings",
            "surface-binding",
            identity,
            observed,
            now,
            self._stale,
        )
        facts: list[GroundingFact] = []
        fact_reasons: list[str] = []
        for predicate, value in (
            ("surface.locator_kind", binding.get("locator_kind")),
            ("surface.review_state", "UNKNOWN"),
            ("surface.health", "UNKNOWN"),
        ):
            _append_fact(
                facts,
                fact_reasons,
                subject=public,
                predicate=predicate,
                value=value,
                source=source,
                freshness=fresh,
            )
        if fresh.age is not None:
            _append_fact(
                facts,
                fact_reasons,
                subject=public,
                predicate="surface.observation_age_seconds",
                value=fresh.age,
                source=source,
                freshness=fresh,
            )
        return _result(
            facts,
            [
                *reasons,
                *fact_reasons,
                "SURFACE_UNKNOWN",
                *([fresh.reason] if fresh.reason else []),
            ],
        )


__all__ = [
    "CONTROL_ROOM_SCHEMA", "ControlRoomStewardReadPort",
    "DEFAULT_STALE_AFTER_SECONDS", "ProjectionError", "responsibility_ref_for",
]
