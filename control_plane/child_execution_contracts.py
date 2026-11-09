"""Shared child execution contracts for the Mastermind/Hermes routing boundary.

This module is the in-repo vendoring unit of the shared routing law
(``WO-02`` / Rev 4 master plan §S5 D1).  It ports the live Hermes
``mmx-router`` plugin's ``child_routing_policy.py`` (extracted in WO-00)
into the Mastermind repo and adds the versioned shared envelopes around
it: the classification record, ``ChildExecutionRequest.v1``,
``ExecutionBinding.v1``, ``RoutePreview.v1`` and one decision/event
schema for the JSONL explanation stream.

Law: ``research/SUBAGENT_FABRIC_ROUTING_AUDIT_2026-09-26.md`` and
``docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md``

* section 5 step 2 — bounded-task classification: the requested option
  names a task class, not a model pick.
* section 5 step 3 — model-class ceiling: C3 frontier judgment is lawful
  only with a concrete witness; without one the task is DOWNGRADED to the
  option's declared ``downgrade_to`` target (the law's sanctioned lane is
  C2_COMPLEX_BOUNDED), or refused when no lawful target exists — never
  silently run at frontier strength.
* section 3 / DEC law — business impact, urgency, "production", repo
  size, topology or a task being a subagent are NOT difficulty
  witnesses; they raise verification rigor, never model strength.

Canonical vocabulary (Chairman addendum): the shared boundary uses the
LONG enum names ``C0_MECHANICAL`` / ``C1_ROUTINE_BOUNDED`` /
``C2_COMPLEX_BOUNDED`` / ``C3_FRONTIER_JUDGMENT``; ``C0``–``C3`` are
display shorthand and are normalized on input.  The reviewer lane is a
separate lane, not a complexity rung.

Design rules that follow the decision everywhere:

* **Decision is not placement.**  A RoutingDecision names a class/tier,
  never a host, account or provider; where the child physically runs is
  the owner's separate admission decision.
* **Local fallback is advisory-only.**  A downgrade names a lawful lower
  class; any local fallback execution the caller performs is advice
  recorded for the owner, never a claim that the child ran or was
  accepted on the shared fabric.
* **A preview is never a launch grant.**  ``RoutePreview.v1`` carries
  ``authority = NONE_SOURCE_PREVIEW_ONLY`` as a fixed constant and
  ``production_armed = False`` by construction; actual execution
  selection belongs to the incumbent deployment/admission owner.

Historical bug this module pins (inherited from the plugin): goal and
context are joined with a NEWLINE before witness matching.  A space join
once hid a ``witness:`` line from the regex ``^`` anchor, silently
downgrading lawfully-witnessed frontier tasks.  ``evaluate`` must keep
the newline join.

Purity: stdlib only — no I/O, no claims, no leases, no state.  Every
record is a frozen dataclass; IDs are caller-supplied strings, the only
value the module mints itself is the ``request_digest`` (sha256 over a
canonical serialization of the request's semantic content).

Options shape: ``options`` maps option name -> route dict with keys
``name``, ``task_complexity`` (canonical long name; the plugin-era
``task_class`` key with ``C0``..``C3``/``reviewer`` shorthand is still
read and normalized, so the Hermes plugin's config shape passes through
with identical behaviour), ``description`` and optional
``requires_witness``, ``downgrade_to``, ``fallback_providers``.  Only
the classification keys (``task_complexity``/``task_class``,
``requires_witness``, ``downgrade_to``) are read; provider/model fields
in an options entry are ignored — decision is not placement.
"""

from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Mapping

__all__ = [
    "C0_MECHANICAL",
    "C1_ROUTINE_BOUNDED",
    "C2_COMPLEX_BOUNDED",
    "C3_FRONTIER_JUDGMENT",
    "REVIEW_LANE",
    "CANONICAL_TASK_COMPLEXITIES",
    "DISPLAY_SHORTHAND",
    "FRONTIER_DOWNGRADE_COMPLEXITY",
    "canonical_task_complexity",
    "POLICY_REVISION",
    "DEFAULT_WITNESS_MIN",
    "WITNESS_RE",
    "NOT_WITNESSES",
    "RoutingDecision",
    "find_witness",
    "witness_problems",
    "ChildRoutingPolicy",
    "CANONICAL_ROUTE_OPTIONS",
    "ExecutionProfile",
    "TaskClassification",
    "CapabilityRequest",
    "ChildExecutionRequest",
    "CHILD_EXECUTION_REQUEST_SCHEMA",
    "FALLBACK_MODES",
    "ExecutionBinding",
    "EXECUTION_BINDING_SCHEMA",
    "RoutePreview",
    "ROUTE_PREVIEW_SCHEMA",
    "PREVIEW_AUTHORITY",
    "CAPACITY_KNOWLEDGE",
    "RANK_BASIS",
    "WITNESS_DISPOSITIONS",
    "witness_disposition_of",
    "DecisionEvent",
    "DECISION_EVENT_SCHEMA",
    "DECISION_EVENT_KINDS",
]

#: --- canonical vocabulary (long names at the shared boundary) -----------------
C0_MECHANICAL = "C0_MECHANICAL"
C1_ROUTINE_BOUNDED = "C1_ROUTINE_BOUNDED"
C2_COMPLEX_BOUNDED = "C2_COMPLEX_BOUNDED"
C3_FRONTIER_JUDGMENT = "C3_FRONTIER_JUDGMENT"
#: The reviewer lane is a separate lane, not a complexity rung.
REVIEW_LANE = "REVIEWER"

CANONICAL_TASK_COMPLEXITIES = (
    C0_MECHANICAL,
    C1_ROUTINE_BOUNDED,
    C2_COMPLEX_BOUNDED,
    C3_FRONTIER_JUDGMENT,
)

#: C0–C3 are display shorthand; never persisted at the shared boundary.
DISPLAY_SHORTHAND = {
    C0_MECHANICAL: "C0",
    C1_ROUTINE_BOUNDED: "C1",
    C2_COMPLEX_BOUNDED: "C2",
    C3_FRONTIER_JUDGMENT: "C3",
}

#: The law's only sanctioned downgrade lane for an insufficient frontier
#: witness (audit section 5 step 3): C2_COMPLEX_BOUNDED ("hard").
FRONTIER_DOWNGRADE_COMPLEXITY = C2_COMPLEX_BOUNDED

_LOOKUP_CANONICAL = {name.upper(): name for name in CANONICAL_TASK_COMPLEXITIES}
_LOOKUP_CANONICAL.update({short: full for full, short in DISPLAY_SHORTHAND.items()})
_LOOKUP_CANONICAL["REVIEWER"] = REVIEW_LANE


def canonical_task_complexity(value: Any) -> str:
    """Normalize a complexity spelling to its canonical long name.

    Accepts the canonical names (any case), the ``C0``..``C3`` display
    shorthand and ``reviewer``.  Unknown non-empty values pass through
    unchanged (forward compatibility: the shared law must classify, not
    crash, on a newer vocabulary it has not learned); empty stays empty.
    """
    text = str(value if value is not None else "").strip()
    if not text:
        return ""
    return _LOOKUP_CANONICAL.get(text.upper(), text)


#: --- the shared routing law (ported verbatim from the WO-00 extraction) -------
#: Bumped only when the law itself changes (gates, word lists, join
#: semantics).  Both sides of the share must agree on it before trusting
#: a decision.  (Plugin-era name: ``POLICY_VERSION``.)
POLICY_REVISION = "1.0.0"

#: ≥24-char FRONTIER_WITNESS floor — consistent with
#: ``control_plane/fable_api_principal.py`` (witness strip-length gate).
DEFAULT_WITNESS_MIN = 24

WITNESS_RE = re.compile(r"(?im)^[ \t>*-]*witness[ \t]*:[ \t]*(\S.*)$")
#: Words that must never raise model strength (audit section 3 / DEC law).
NOT_WITNESSES = (
    "important", "production", "critical", "urgent", "large repo", "long context",
    "subagent", "writes code", "frontier quota is unused", "i have not decomposed",
)
#: Inflation/impact vocabulary + glue: a witness made ONLY of these names no evidence.
_INFLATION_WORDS = frozenset({
    "important", "production", "critical", "urgent", "business", "impact", "large",
    "repo", "long", "context", "subagent", "writes", "code", "frontier", "quota",
    "unused", "decomposed", "very", "really", "extremely", "high", "low",
})
_GLUE_WORDS = frozenset({
    "this", "that", "the", "a", "an", "and", "or", "of", "for", "to", "is", "are",
    "was", "be", "been", "it", "its", "i", "we", "you", "they", "have", "has", "had",
    "not", "yet", "now", "so", "just", "only", "must", "should", "need", "needs",
    "work", "task", "mission", "program", "project",
})


@dataclass(frozen=True)
class RoutingDecision:
    """The outcome of classifying one child task under the routing law.

    Fields:
        requested: the option name the caller asked for (pre-policy).
        resolved: the option name actually served.  EMPTY STRING MEANS
            REFUSED (e.g. an unwitnessed frontier with no lawful
            downgrade target) — ``reason`` then carries the refusal
            message the caller should surface.  Decision is not
            placement: this is a class/tier name from ``options``,
            never a host, account or provider.
        task_complexity: the served option's task complexity in
            CANONICAL long form (``C0_MECHANICAL``..``C3_FRONTIER_JUDGMENT``,
            or ``REVIEWER`` for the separate reviewer lane); ``""`` when
            refused.  (Plugin-era field name: ``task_class``, short
            ``C0``..``C3`` spelling.)
        downgraded: True when ``resolved`` differs from ``requested``.
        witness_problem: None when the requested class needs no witness;
            ``""`` when a required witness was accepted; otherwise the
            concrete reason the witness failed (which is what
            gated/downgraded the REQUESTED class, even when ``resolved``
            moved to a lower class).
        reason: ``""`` for a plain resolution; the downgrade note
            (``downgraded <from>-><to>: <witness_problem>``) when
            downgraded; the refusal message when refused.
        witness: the extracted witness text (``""`` when none / not
            required) — evidence for the ledger and for owner-side
            admission review.
        policy_revision: the law revision that produced this decision.
    """

    requested: str
    resolved: str
    task_complexity: str
    downgraded: bool
    witness_problem: str | None
    reason: str
    witness: str = ""
    policy_revision: str = POLICY_REVISION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "task_complexity", canonical_task_complexity(self.task_complexity))

    def to_dict(self) -> dict[str, Any]:
        return _record_to_dict(self)

    @classmethod
    def from_dict(cls, payload: "Mapping[str, Any] | RoutingDecision") -> "RoutingDecision":
        """Accepts the canonical field names plus the plugin-era aliases
        ``task_class`` (short ``C0``..``C3`` spelling) and ``policy_version``."""
        if isinstance(payload, RoutingDecision):
            return payload
        data = dict(payload or {})
        if "task_complexity" in data:
            if "task_class" in data and (
                    canonical_task_complexity(data["task_class"])
                    != canonical_task_complexity(data["task_complexity"])):
                raise ValueError("task_class and task_complexity disagree")
            data.pop("task_class", None)
        elif "task_class" in data:
            data["task_complexity"] = data.pop("task_class")
        if "policy_revision" not in data and "policy_version" in data:
            data["policy_revision"] = data.pop("policy_version")
        return cls(**data)


def find_witness(text: str) -> str:
    """The first ``witness:`` line's content, stripped. '' when there is none."""
    for match in WITNESS_RE.finditer(text or ""):
        content = match.group(1).strip()
        if content:
            return content
    return ""


def witness_problems(witness: str, min_chars: int) -> str:
    """Why this witness is not a witness ('' when it is one). An inflation word
    alone is explicitly not a witness, mirroring the audit's non-witness list;
    so is a sentence whose every word is impact vocabulary or glue — that names
    urgency, not evidence."""
    if not witness:
        return "no 'witness:' line in the task"
    if len(witness) < min_chars:
        return f"witness is {len(witness)} chars (< {min_chars})"
    lowered = witness.lower().rstrip(".!")
    if lowered in NOT_WITNESSES:
        return f"witness is a bare inflation word ({lowered!r}), not concrete evidence"
    words = re.findall(r"[a-z0-9]+", lowered)
    informative = [w for w in words if w not in _INFLATION_WORDS and w not in _GLUE_WORDS]
    if words and not informative:
        return "witness contains only impact/inflation words, no concrete evidence"
    return ""

def _entry_task_complexity(entry: Mapping[str, Any]) -> str:
    """Canonical complexity of an options entry.  Reads the canonical
    ``task_complexity`` key first, then the plugin-era ``task_class`` key
    (``C0``..``C3`` / ``reviewer`` shorthand) so the Hermes plugin's raw
    config shape passes through identically."""
    raw = entry.get("task_complexity")
    if raw is None or str(raw) == "":
        raw = entry.get("task_class")
    return canonical_task_complexity(raw)


#: The canonical option set at the shared boundary, in canonical long
#: names.  Deliberately carries NO provider/model rows: decision is not
#: placement, so the shared law only classifies.  ``frontier``'s declared
#: ``downgrade_to`` is the ``hard`` option, whose complexity is
#: ``C2_COMPLEX_BOUNDED`` — the explicit downgrade lane of the law.
CANONICAL_ROUTE_OPTIONS: dict[str, dict[str, Any]] = {
    "mechanical": {
        "name": "mechanical", "task_complexity": C0_MECHANICAL,
        "description": "Deterministic transforms and mechanical sweeps.",
    },
    "routine": {
        "name": "routine", "task_complexity": C1_ROUTINE_BOUNDED,
        "description": "Ordinary bounded implementation or research.",
    },
    "hard": {
        "name": "hard", "task_complexity": C2_COMPLEX_BOUNDED,
        "description": "Workhorse lane for bounded multi-file reasoning.",
    },
    "frontier": {
        "name": "frontier", "task_complexity": C3_FRONTIER_JUDGMENT,
        "description": "Frontier judgment; gated on a concrete witness.",
        "requires_witness": True, "downgrade_to": "hard",
    },
    "review": {
        "name": "review", "task_complexity": REVIEW_LANE,
        "description": "Independent reviewer lane (separate from the ladder).",
    },
}


class ChildRoutingPolicy:
    """The routing law's classification gates (audit section 5, steps 2-3).

    Stateless apart from ``witness_min_chars``; safe to share, fork per call,
    or vendor.  ``evaluate`` performs no I/O and never mutates ``options``.
    This is a faithful port of the Hermes ``mmx-router`` plugin's policy:
    identical gate order, word lists, message strings and newline-join
    semantics, with complexities reported in canonical long names.
    """

    def __init__(self, witness_min_chars: int = DEFAULT_WITNESS_MIN) -> None:
        self.witness_min_chars = int(witness_min_chars)

    def evaluate(self, requested_option: str, goal: str, context: str,
                 options: Mapping[str, Any] | None = None) -> RoutingDecision:
        """Classify one child task: gate the requested class, downgrade lawlessly
        strong requests to their declared target, or refuse.

        ``goal`` and ``context`` are the task texts.  They are joined with a
        NEWLINE before witness matching so a ``witness:`` line stays a line —
        a space join would hide it from the regex ``^`` anchor (past bug).
        ``options`` defaults to :data:`CANONICAL_ROUTE_OPTIONS` for standalone
        consumers; Hermes callers pass their normalized options dict.
        """
        requested = requested_option or ""
        options = dict(CANONICAL_ROUTE_OPTIONS if options is None else options)
        if not requested or requested not in options:
            # Hermes core refuses enum violations before dispatch; this guard is
            # for standalone consumers of the shared module.
            return RoutingDecision(
                requested=requested, resolved="", task_complexity="", downgraded=False,
                witness_problem=None,
                reason=f"option {requested!r} is not a configured route",
                witness="", policy_revision=POLICY_REVISION)

        entry = options[requested]
        requires_witness = bool(entry.get("requires_witness"))
        downgrade_to = entry.get("downgrade_to") or ""
        # newline-joined so a witness line stays a line (a space join would hide it from ^)
        text = "\n".join((str(goal or ""), str(context or "")))

        witness, witness_problem = "", (None if not requires_witness else "")
        if requires_witness:
            witness = find_witness(text)
            witness_problem = witness_problems(witness, self.witness_min_chars)
            if witness_problem:
                target = downgrade_to
                if target and target in options:
                    return RoutingDecision(
                        requested=requested, resolved=target,
                        task_complexity=_entry_task_complexity(options[target]),
                        downgraded=target != requested,
                        witness_problem=witness_problem,
                        reason=f"downgraded {requested}->{target}: {witness_problem}",
                        witness=witness, policy_revision=POLICY_REVISION)
                return RoutingDecision(
                    requested=requested, resolved="", task_complexity="", downgraded=False,
                    witness_problem=witness_problem,
                    reason=(f"Option {requested!r} needs a concrete witness: "
                            f"{witness_problem}. Add a 'witness:' line "
                            f"({self.witness_min_chars}+ chars) naming the frontier "
                            f"evidence, or pick a lower class."),
                    witness=witness, policy_revision=POLICY_REVISION)

        return RoutingDecision(
            requested=requested, resolved=requested,
            task_complexity=_entry_task_complexity(entry),
            downgraded=False, witness_problem=witness_problem, reason="",
            witness=witness, policy_revision=POLICY_REVISION)

# --- shared serialization helpers (pure; JSON round-trips for every record) ----

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

#: Bound on one idempotency-triple field.  The triple is joined into a
#: single durable command id, so an unbounded field would inflate every
#: event row that records it.
BOUNDED_IDENTIFIER_MAX_LENGTH = 256


def _record_to_dict(record: Any) -> dict[str, Any]:
    """Every dataclass field, JSON-native (tuples -> lists, nested records -> dicts)."""
    return {f.name: _jsonable(getattr(record, f.name)) for f in dataclasses.fields(record)}


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _record_to_dict(value)
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _require_non_empty(value: Any, field_name: str) -> None:
    if not str(value if value is not None else "").strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_hex64(value: Any, field_name: str) -> None:
    if not _HEX64_RE.match(str(value or "")):
        raise ValueError(f"{field_name} must be a 64-char lowercase hex sha256 digest")


def _require_bounded_identifier(value: Any, field_name: str) -> None:
    """Fence one idempotency-triple field: bounded, printable, unambiguous.

    The triple ``(root_ref, immediate_parent_run_ref, logical_child_key)``
    is joined with ``\\x1f`` to mint the durable command id, so a field
    that may carry that separator — or any other control/non-printable
    character — lets two DISTINCT triples hash to one command id, which
    the Runtime then reports as a spurious ``CHILD_REQUEST_DIGEST_CONFLICT``
    naming the wrong logical key.  Nothing about identity requires such a
    character, so it is refused at the contract rather than tolerated at
    the join.
    """

    _require_non_empty(value, field_name)
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string identifier")
    if len(value) > BOUNDED_IDENTIFIER_MAX_LENGTH:
        raise ValueError(
            f"{field_name} must be at most {BOUNDED_IDENTIFIER_MAX_LENGTH} "
            f"characters, got {len(value)}")
    for offset, char in enumerate(value):
        if not char.isprintable():
            raise ValueError(
                f"{field_name} must be a printable identifier: control or "
                f"separator character {char!r} at offset {offset}")


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _pop_const(data: dict, key: str, const: str, owner: str) -> None:
    supplied = data.pop(key, None)
    if supplied is not None and supplied != const:
        raise ValueError(f"{owner}.{key} must be {const!r}, got {supplied!r}")


# --- 2. the classification record (Rev 4 §S3.A l.181–186) ----------------------

@dataclass(frozen=True)
class ExecutionProfile:
    """Native tools + CPU/memory/scratch requirements of the child.

    Describes what the child needs to run, never where it runs or which
    model serves it (decision is not placement).
    """

    native_tools: tuple[str, ...] = ()
    cpu_cores: int | None = None
    memory_gib: float | None = None
    scratch_gib: float | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "ExecutionProfile":
        data = dict(payload or {})
        data["native_tools"] = _string_tuple(data.get("native_tools"))
        return cls(**data)


@dataclass(frozen=True)
class TaskClassification:
    """The five kept-separate classification dimensions (Rev 4 §S3.A).

    ``task_kind`` — mechanical / research / code / review / ...
    ``task_complexity`` — canonical long name ``C0_MECHANICAL`` ..
    ``C3_FRONTIER_JUDGMENT`` (``REVIEWER`` is the separate lane).
    ``execution_risk`` — the existing authority/effect classification.
    ``business_impact`` — consequence, NOT automatic model promotion:
    impact vocabulary is on the law's non-witness list and never clears
    the frontier witness gate.
    ``execution_profile`` — native tools + CPU/memory/scratch needs.
    ``frontier_witness`` — the extracted witness line when C3 is claimed.
    """

    task_kind: str
    task_complexity: str
    execution_risk: str = ""
    business_impact: str = ""
    execution_profile: ExecutionProfile = field(default_factory=ExecutionProfile)
    frontier_witness: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "task_complexity", canonical_task_complexity(self.task_complexity))
        object.__setattr__(
            self, "execution_profile",
            self.execution_profile
            if isinstance(self.execution_profile, ExecutionProfile)
            else ExecutionProfile.from_dict(self.execution_profile))

    def problems(self, witness_min_chars: int = DEFAULT_WITNESS_MIN) -> tuple[str, ...]:
        """Invariants of a lawful classification; empty tuple when lawful.

        Note what is deliberately absent: ``business_impact`` and
        ``execution_risk`` are never consulted for the witness gate —
        consequence raises verification rigor, never model strength.
        """
        found: list[str] = []
        if not str(self.task_kind or "").strip():
            found.append("task_kind is required")
        if (self.task_complexity not in CANONICAL_TASK_COMPLEXITIES
                and self.task_complexity != REVIEW_LANE):
            found.append(f"task_complexity {self.task_complexity!r} is not canonical")
        if self.task_complexity == C3_FRONTIER_JUDGMENT:
            problem = witness_problems(self.frontier_witness, witness_min_chars)
            if problem:
                found.append(
                    f"frontier witness gate: {problem} "
                    f"(business impact is never a witness)")
        return tuple(found)

    def to_dict(self) -> dict[str, Any]:
        return _record_to_dict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskClassification":
        data = dict(payload or {})
        data.pop("schema", None)
        return cls(**data)


@dataclass(frozen=True)
class CapabilityRequest:
    """One tool/permission the child needs, with its justification.

    Justifications are recorded so a later review can catch capability
    over-asking the same way the witness gate catches class over-asking.
    """

    capability: str
    required: bool = True
    justification: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | CapabilityRequest) -> "CapabilityRequest":
        if isinstance(payload, CapabilityRequest):
            return payload
        return cls(**dict(payload or {}))


# --- 3. ChildExecutionRequest.v1 (Rev 4 §S1 l.56–65; promoted from the draft) --

CHILD_EXECUTION_REQUEST_SCHEMA = "ChildExecutionRequest.v1"
FALLBACK_MODES = ("shared", "advisory_only")


@dataclass(frozen=True)
class ChildExecutionRequest:
    """The admission envelope a caller sends to the shared owner.

    Idempotency: the child operation is idempotent within
    ``(root_ref, immediate_parent_run_ref, logical_child_key)``; the same
    key with a different ``request_digest`` is a CONFLICT, not another
    execution (Rev 4 §S1 l.65).  Caller-supplied IDs are references, not
    credentials.  Goal/context prose never rides in the envelope — only
    refs and digests (least data); the embedded ``routing_decision`` was
    produced by the caller evaluating the SHARED policy locally, and the
    owner may re-run the policy to detect version drift.

    ``fallback_mode``: ``shared`` — only the owner may run the child;
    ``advisory_only`` — the caller may run locally and report it, but a
    local fallback record is advice for the owner's ledger, never a
    claim of a shared run.
    """

    schema: str = field(default=CHILD_EXECUTION_REQUEST_SCHEMA, init=False)
    root_ref: str
    immediate_parent_run_ref: str
    logical_child_key: str
    operation_key: str = ""
    task_kind: str = ""
    requested_complexity: str = ""
    frontier_witness: str = ""
    routing_decision: RoutingDecision | None = None
    brief_ref: str = ""
    brief_digest: str = ""
    required_capabilities: tuple[CapabilityRequest, ...] = ()
    harness_preference: str = ""
    scope_ref: str = ""
    scope_digest: str = ""
    budget_grant_ref: str = ""
    preview_id: str = ""
    policy_revision: str = POLICY_REVISION
    fallback_mode: str = "advisory_only"
    notes: str = ""

    def __post_init__(self) -> None:
        _require_bounded_identifier(self.root_ref, "root_ref")
        _require_bounded_identifier(
            self.immediate_parent_run_ref, "immediate_parent_run_ref")
        _require_bounded_identifier(self.logical_child_key, "logical_child_key")
        complexity = canonical_task_complexity(self.requested_complexity)
        if complexity not in CANONICAL_TASK_COMPLEXITIES and complexity != REVIEW_LANE:
            raise ValueError(
                f"requested_complexity must be a canonical class, got "
                f"{self.requested_complexity!r}")
        object.__setattr__(self, "requested_complexity", complexity)
        if self.fallback_mode not in FALLBACK_MODES:
            raise ValueError(f"fallback_mode must be one of {FALLBACK_MODES}")
        if self.brief_digest:
            _require_hex64(self.brief_digest, "brief_digest")
        if self.scope_digest:
            _require_hex64(self.scope_digest, "scope_digest")
        if (self.routing_decision is not None
                and self.routing_decision.policy_revision != self.policy_revision):
            raise ValueError(
                "policy revision drift: embedded routing_decision was produced by "
                f"revision {self.routing_decision.policy_revision!r} but the request "
                f"declares {self.policy_revision!r}")

    def idempotency_key(self) -> tuple[str, str, str]:
        """The idempotency triple (root, immediate_parent, logical_child_key)."""
        return (self.root_ref, self.immediate_parent_run_ref, self.logical_child_key)

    def canonical_payload(self) -> dict[str, Any]:
        """The digest input: every semantic field.  ``notes`` is excluded —
        free-text never participates in request identity."""
        payload = _record_to_dict(self)
        payload.pop("notes", None)
        return payload

    @property
    def request_digest(self) -> str:
        """sha256 over the canonical JSON serialization of the semantic content."""
        return sha256(_canonical_json_bytes(self.canonical_payload())).hexdigest()

    def is_idempotent_retry(self, other: "ChildExecutionRequest") -> bool:
        """Same idempotency key AND same digest — a redelivery, not new work."""
        return (self.idempotency_key() == other.idempotency_key()
                and self.request_digest == other.request_digest)

    def is_idempotency_conflict(self, other: "ChildExecutionRequest") -> bool:
        """Same idempotency key with a DIFFERENT digest — a conflict, never
        another execution (Rev 4 §S1 l.65)."""
        return (self.idempotency_key() == other.idempotency_key()
                and self.request_digest != other.request_digest)

    def to_dict(self) -> dict[str, Any]:
        payload = _record_to_dict(self)
        payload["request_digest"] = self.request_digest
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ChildExecutionRequest":
        data = dict(payload or {})
        _pop_const(data, "schema", CHILD_EXECUTION_REQUEST_SCHEMA, cls.__name__)
        supplied_digest = data.pop("request_digest", None)
        decision = data.get("routing_decision")
        if isinstance(decision, Mapping):
            data["routing_decision"] = RoutingDecision.from_dict(decision)
        if data.get("required_capabilities") is not None:
            data["required_capabilities"] = tuple(
                CapabilityRequest.from_dict(c) for c in data["required_capabilities"])
        request = cls(**data)
        if supplied_digest is not None and supplied_digest != request.request_digest:
            raise ValueError(
                "request_digest mismatch: payload content does not match the "
                "supplied digest (conflict or tampering)")
        return request


# --- 4. ExecutionBinding.v1 (Rev 4 §S3.D l.277–285) ----------------------------

EXECUTION_BINDING_SCHEMA = "ExecutionBinding.v1"


@dataclass(frozen=True)
class ExecutionBinding:
    """The fenced assignment issued by the incumbent broker/owner at claim.

    The binding is issued/resolved through the authenticated broker owner
    over the existing channel; it contains opaque grant references, never
    credentials.  ``POOL_ORCHESTRATOR_ID``/``PARENT_RUN_ID`` style env
    values are server-derived compatibility projections of this record —
    children cannot promote themselves by changing them.  Root stays
    conserved; the immediate parent changes correctly per level.
    """

    schema: str = field(default=EXECUTION_BINDING_SCHEMA, init=False)
    root_run_ref: str
    immediate_parent_run_ref: str
    logical_child_key: str
    request_digest: str
    effective_complexity: str
    original_root_orchestrator_ref: str = ""
    task_kind: str = ""
    job_ref: str = ""
    attempt_ref: str = ""
    policy_revision: str = POLICY_REVISION
    decision_ref: str = ""
    scope_digest: str = ""
    budget_grant_ref: str = ""
    adapter_id: str = ""
    model_ref: str = ""
    provider_ref: str = ""
    pool_ref: str = ""
    shared_quota_resource_refs: tuple[str, ...] = ()
    host_id: str = ""
    worker_id: str = ""
    host_boot_id: str = ""
    assignment_generation: int = 0
    fence_counter: int = 0
    lease_expiry: str = ""

    def __post_init__(self) -> None:
        _require_non_empty(self.root_run_ref, "root_run_ref")
        _require_non_empty(self.immediate_parent_run_ref, "immediate_parent_run_ref")
        _require_non_empty(self.logical_child_key, "logical_child_key")
        _require_hex64(self.request_digest, "request_digest")
        complexity = canonical_task_complexity(self.effective_complexity)
        if complexity not in CANONICAL_TASK_COMPLEXITIES and complexity != REVIEW_LANE:
            raise ValueError(
                f"effective_complexity must be a canonical class, got "
                f"{self.effective_complexity!r}")
        object.__setattr__(self, "effective_complexity", complexity)
        if self.assignment_generation < 0:
            raise ValueError("assignment_generation must be >= 0")
        if self.fence_counter < 0:
            raise ValueError("fence_counter must be >= 0")
        if self.scope_digest:
            _require_hex64(self.scope_digest, "scope_digest")

    def child_identity(self) -> tuple[str, str, str]:
        """The (root, immediate_parent, logical_child_key) placement identity."""
        return (self.root_run_ref, self.immediate_parent_run_ref, self.logical_child_key)

    def binds_request(self, request: ChildExecutionRequest) -> bool:
        """True when this binding is the fenced assignment OF that request:
        same child identity triple and same admitted request digest."""
        return (self.child_identity() == request.idempotency_key()
                and self.request_digest == request.request_digest)

    def to_dict(self) -> dict[str, Any]:
        return _record_to_dict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExecutionBinding":
        data = dict(payload or {})
        _pop_const(data, "schema", EXECUTION_BINDING_SCHEMA, cls.__name__)
        if data.get("shared_quota_resource_refs") is not None:
            data["shared_quota_resource_refs"] = _string_tuple(
                data["shared_quota_resource_refs"])
        return cls(**data)


# --- 5. RoutePreview.v1 (Rev 4 §S3.B l.199–212) --------------------------------

ROUTE_PREVIEW_SCHEMA = "RoutePreview.v1"
#: Fixed by law: a preview never reserves or launches; it cannot become a
#: live route by flipping a source-preview field.
PREVIEW_AUTHORITY = "NONE_SOURCE_PREVIEW_ONLY"
CAPACITY_KNOWLEDGE = ("observed", "configured_only", "unknown")
RANK_BASIS = ("suitability_only", "observed_headroom", "bounded_unknown")
WITNESS_DISPOSITIONS = ("not_required", "accepted", "insufficient", "downgraded")


def witness_disposition_of(decision: RoutingDecision) -> str:
    """Map a RoutingDecision onto the preview's witness_disposition field."""
    if decision.witness_problem is None:
        return "not_required"
    if decision.witness_problem == "":
        return "accepted"
    if decision.resolved:
        return "downgraded"
    return "insufficient"


@dataclass(frozen=True)
class RoutePreview:
    """A read-only route preview; NEVER a reservation or launch grant.

    ``authority`` is the fixed constant ``NONE_SOURCE_PREVIEW_ONLY`` and
    ``production_armed`` is False BY CONSTRUCTION (both are non-init
    fields — no caller can set them).  ``preview_id``, ``decision_id``
    and ``attempt_ref`` are kept DISTINCT identities (Rev 4 §S3.B
    l.212): a stale preview may influence an explanation but can never
    overwrite the authoritative served placement.  Actual execution
    selection belongs to the incumbent deployment/admission owner.
    """

    schema: str = field(default=ROUTE_PREVIEW_SCHEMA, init=False)
    authority: str = field(default=PREVIEW_AUTHORITY, init=False)
    production_armed: bool = field(default=False, init=False)
    preview_id: str
    requested_complexity: str
    effective_complexity: str
    witness_disposition: str
    request_digest: str = ""
    policy_revision: str = POLICY_REVISION
    registry_revision: str = ""
    suitability_tiers: tuple[str, ...] = ()
    candidate_reason_codes: tuple[str, ...] = ()
    observation_refs: tuple[str, ...] = ()
    observed_at: str = ""
    expires_at: str = ""
    capacity_knowledge: str = "unknown"
    rank_basis: str = "suitability_only"
    decision_id: str = ""
    attempt_ref: str = ""

    def __post_init__(self) -> None:
        _require_non_empty(self.preview_id, "preview_id")
        for name in ("requested_complexity", "effective_complexity"):
            complexity = canonical_task_complexity(getattr(self, name))
            if complexity not in CANONICAL_TASK_COMPLEXITIES and complexity != REVIEW_LANE:
                raise ValueError(f"{name} must be a canonical class, got "
                                 f"{getattr(self, name)!r}")
            object.__setattr__(self, name, complexity)
        if self.witness_disposition not in WITNESS_DISPOSITIONS:
            raise ValueError(f"witness_disposition must be one of {WITNESS_DISPOSITIONS}")
        if self.capacity_knowledge not in CAPACITY_KNOWLEDGE:
            raise ValueError(f"capacity_knowledge must be one of {CAPACITY_KNOWLEDGE}")
        if self.rank_basis not in RANK_BASIS:
            raise ValueError(f"rank_basis must be one of {RANK_BASIS}")
        for left, right in (("preview_id", "decision_id"),
                            ("preview_id", "attempt_ref"),
                            ("decision_id", "attempt_ref")):
            a, b = getattr(self, left), getattr(self, right)
            if a and b and a == b:
                raise ValueError(
                    f"{left} and {right} must stay distinct identities, got {a!r} twice")

    def to_dict(self) -> dict[str, Any]:
        return _record_to_dict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RoutePreview":
        data = dict(payload or {})
        _pop_const(data, "schema", ROUTE_PREVIEW_SCHEMA, cls.__name__)
        _pop_const(data, "authority", PREVIEW_AUTHORITY, cls.__name__)
        armed = data.pop("production_armed", None)
        if armed not in (None, False):
            raise ValueError("a preview is never production-armed")
        for name in ("suitability_tiers", "candidate_reason_codes", "observation_refs"):
            if data.get(name) is not None:
                data[name] = _string_tuple(data[name])
        return cls(**data)


# --- 6. the shared decision/event schema (Rev 4 §S3.E l.295; §S5 l.331) --------

#: The one decision/event schema for the JSONL explanation/export stream.
#: The canonical admitted decision/assignment itself attaches to the
#: existing Executive Job/Attempt records; this event is the compatible
#: export stream, correlated by root, parent, child key, preview ID,
#: authoritative decision ID, attempt and fence — it is NOT another
#: placement ledger and NOT a retry owner.
DECISION_EVENT_SCHEMA = "mastermind.child_execution.decision_event/v1"
DECISION_EVENT_KINDS = (
    "request_classified",
    "preview_issued",
    "admission_decided",
    "binding_issued",
)


@dataclass(frozen=True)
class DecisionEvent:
    """One exported decision/event record for the shared JSONL stream."""

    schema: str = field(default=DECISION_EVENT_SCHEMA, init=False)
    event_id: str
    event_kind: str
    occurred_at: str = ""
    root_run_ref: str = ""
    immediate_parent_run_ref: str = ""
    logical_child_key: str = ""
    preview_id: str = ""
    decision_id: str = ""
    attempt_ref: str = ""
    fence_counter: int = 0
    request_digest: str = ""
    task_kind: str = ""
    requested_complexity: str = ""
    effective_complexity: str = ""
    downgraded: bool = False
    witness_problem: str | None = None
    reason: str = ""
    witness: str = ""
    policy_revision: str = POLICY_REVISION
    routing_decision: RoutingDecision | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.event_id, "event_id")
        if self.event_kind not in DECISION_EVENT_KINDS:
            raise ValueError(f"event_kind must be one of {DECISION_EVENT_KINDS}")
        if self.request_digest:
            _require_hex64(self.request_digest, "request_digest")
        for name in ("requested_complexity", "effective_complexity"):
            value = getattr(self, name)
            if value:
                complexity = canonical_task_complexity(value)
                if (complexity not in CANONICAL_TASK_COMPLEXITIES
                        and complexity != REVIEW_LANE):
                    raise ValueError(f"{name} must be a canonical class, got {value!r}")
                object.__setattr__(self, name, complexity)
        if self.fence_counter < 0:
            raise ValueError("fence_counter must be >= 0")

    def to_dict(self) -> dict[str, Any]:
        return _record_to_dict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DecisionEvent":
        data = dict(payload or {})
        _pop_const(data, "schema", DECISION_EVENT_SCHEMA, cls.__name__)
        decision = data.get("routing_decision")
        if isinstance(decision, Mapping):
            data["routing_decision"] = RoutingDecision.from_dict(decision)
        return cls(**data)

    def to_json_line(self) -> str:
        """One compact, key-sorted JSON line of the JSONL export stream."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False)

    @classmethod
    def from_json_line(cls, line: str) -> "DecisionEvent":
        return cls.from_dict(json.loads(line))
