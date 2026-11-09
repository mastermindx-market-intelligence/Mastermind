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
    "CHILD_EXECUTION_REQUEST_SCHEMA_V1_1",
    "FALLBACK_MODES",
    "ExecutionBinding",
    "EXECUTION_BINDING_SCHEMA",
    "EXECUTION_BINDING_SCHEMA_V1_1",
    "KNOWN_RUNTIME_KINDS",
    "DESCENDANT_POLICIES",
    "WORKSPACE_MODES",
    "RESERVATION_MODELS",
    "FanoutEnvelope",
    "LocalitySpec",
    "WorkspaceRequirements",
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


def _pop_schema(data: dict, accepted: tuple[str, ...], owner: str) -> None:
    """Accept any of ``accepted`` schema labels (v1 + v1.1 compat read);
    the reconstructed record's own extension content decides which label
    it serializes with."""
    supplied = data.pop("schema", None)
    if supplied is not None and supplied not in accepted:
        raise ValueError(f"{owner}.schema must be one of {accepted}, got {supplied!r}")


def _sparse_v1_1(payload: dict, extension_fields: tuple[str, ...],
                 has_extensions: bool) -> dict:
    """SPARSE v1.1 serialization: a record with no extension fields set
    serializes EXACTLY like v1 (unset extension keys are omitted), so
    old records round-trip byte-identically through the extended code
    and strict ``additionalProperties: false`` consumers keep working."""
    if not has_extensions:
        for name in extension_fields:
            payload.pop(name, None)
    return payload


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


# --- 2b. Rev 5 v1.1 extension vocabulary and nested records (D1) ---------------
#
# Rev 5 §5 ("Reservation and identity") + change order §3A extend the v1
# envelopes compatibly: every new field is OPTIONAL with a default, old
# v1 records parse and serialize byte-identically, and a record only
# declares schema ``*.v1.1`` when at least one extension field is set
# (auto-upgrade in ``__post_init__``; a v1.1-labelled record with no
# extension fields IS a v1 record and normalizes to one).

CHILD_EXECUTION_REQUEST_SCHEMA_V1_1 = "ChildExecutionRequest.v1.1"
EXECUTION_BINDING_SCHEMA_V1_1 = "ExecutionBinding.v1.1"

#: Runtime/harness dimension of a route (Rev 5 §5 "runtime/harness × ...").
#: Open vocabulary — the shared boundary validates non-blank, not
#: membership, so newer runtimes pass through (same forward-compat rule
#: as ``canonical_task_complexity``).  Core Rev 5 kinds:
KNOWN_RUNTIME_KINDS = (
    "hermes-native",      # persistent Hermes team/executive harness
    "t3-native",          # T3 Code environment/thread/run lifecycle
    "dsh-acp",            # DeepSeek Harness under ACP (--profile acp)
    "opencode-free-cli",  # scoped free OpenCode CLI lane (WO-18)
    "fabric-native",      # Mastermind Fabric-managed worker process
    "codex-cli",          # attested Codex CLI adapter
    "claude-code",        # Claude Code adapter family
    "acp",                # generic ACP (runtime != any specific harness)
    "api-direct",         # metered API principal, no native harness
)

#: Descendant admission policy every runtime descriptor must declare one
#: of (Rev 5 §6 "Descendant policy: the most important integration
#: detail").  ``bounded_native_fanout`` requires a declared
#: :class:`FanoutEnvelope` naming its native enforcement.
DESCENDANT_POLICIES = (
    "fabric_per_child",
    "bounded_native_fanout",
    "native_fanout_disabled",
)

#: Workspace intent (Rev 5 §3 "Placement unit and locality").
WORKSPACE_MODES = (
    "read_only_snapshot",
    "single_writer",
    "isolated_patch",
)

#: One reservation model per profile (Rev 5 §6 l.385): either the whole
#: envelope is reserved up front, or each admitted child is reserved on
#: its own — never both for the same profile.
RESERVATION_MODELS = (
    "envelope_reserved",
    "per_child_reserved",
)


@dataclass(frozen=True)
class FanoutEnvelope:
    """The declared descendant envelope for ``bounded_native_fanout``.

    A configuration promise without a real native enforcement mechanism
    is insufficient (Rev 5 §6): when the policy is
    ``bounded_native_fanout`` the envelope must be declared AND carry a
    non-empty ``enforcement_ref`` naming the native control that
    actually bounds the fan-out.
    """

    max_descendants: int
    max_concurrent: int | None = None
    reservation_model: str = ""
    enforcement_ref: str = ""

    def __post_init__(self) -> None:
        if self.max_descendants < 0:
            raise ValueError("max_descendants must be >= 0")
        if self.max_concurrent is not None and self.max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1 when supplied")
        if self.reservation_model and self.reservation_model not in RESERVATION_MODELS:
            raise ValueError(
                f"reservation_model must be one of {RESERVATION_MODELS}, got "
                f"{self.reservation_model!r}")

    def to_dict(self) -> dict[str, Any]:
        return _record_to_dict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | FanoutEnvelope | None) -> "FanoutEnvelope | None":
        if payload is None or isinstance(payload, FanoutEnvelope):
            return payload
        return cls(**dict(payload or {}))


@dataclass(frozen=True)
class LocalitySpec:
    """Placement locality of one child (Rev 5 §3; change order §3D).

    ``parent_host_preference`` is SOFT (warm caches, lower transfer
    cost).  ``hard_affinity`` pins the child to its parent's host and is
    lawful only with a concrete ``hard_affinity_reason`` — a real local
    service, a nonportable dependency, or an exact mutable workspace
    lease.  If hard-affinity work cannot fit, it queues or the parent
    decomposes it; the cap is never evaded.
    """

    parent_host_preference: bool = False
    hard_affinity: bool = False
    hard_affinity_reason: str = ""

    def __post_init__(self) -> None:
        if self.hard_affinity and not self.hard_affinity_reason.strip():
            raise ValueError(
                "hard_affinity requires hard_affinity_reason (real local "
                "service, nonportable dependency, or exact mutable workspace)")

    def to_dict(self) -> dict[str, Any]:
        return _record_to_dict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | LocalitySpec | None) -> "LocalitySpec | None":
        if payload is None or isinstance(payload, LocalitySpec):
            return payload
        return cls(**dict(payload or {}))


@dataclass(frozen=True)
class WorkspaceRequirements:
    """What the child needs of a workspace (Rev 5 §3/§4).

    ``mode`` uses the supported workspace intent vocabulary; empty means
    unspecified (the owner's default applies).  Refs are opaque and
    credential-free.
    """

    mode: str = ""
    workspace_ref: str = ""
    base_ref: str = ""
    scratch_gib: float | None = None

    def __post_init__(self) -> None:
        if self.mode and self.mode not in WORKSPACE_MODES:
            raise ValueError(
                f"mode must be one of {WORKSPACE_MODES}, got {self.mode!r}")
        if self.scratch_gib is not None and self.scratch_gib < 0:
            raise ValueError("scratch_gib must be >= 0 when supplied")

    def to_dict(self) -> dict[str, Any]:
        return _record_to_dict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | WorkspaceRequirements | None) -> "WorkspaceRequirements | None":
        if payload is None or isinstance(payload, WorkspaceRequirements):
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
    # --- Rev 5 v1.1 extension (all OPTIONAL; absent = a plain v1 record) ---
    #: Soft/hard placement locality (Rev 5 §3; change order §3D).
    locality: LocalitySpec | None = None
    #: Preferred runtime/harness (soft hint; KNOWN_RUNTIME_KINDS vocabulary,
    #: open set).  Decision stays separate from placement — the owner may
    #: place elsewhere and records why.
    runtime_preference: str = ""
    #: Workspace intent + refs the child needs (Rev 5 §3/§4).
    workspace_requirements: WorkspaceRequirements | None = None
    #: Declared descendant envelope when the child itself will fan out
    #: natively (pairs with the binding's ``descendant_policy``).
    declared_fanout: FanoutEnvelope | None = None

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
        if self.runtime_preference and not self.runtime_preference.strip():
            raise ValueError("runtime_preference must be non-blank when supplied")
        if self._has_v1_1_extensions:
            object.__setattr__(
                self, "schema", CHILD_EXECUTION_REQUEST_SCHEMA_V1_1)

    @property
    def _has_v1_1_extensions(self) -> bool:
        """True when any Rev 5 extension field is declared (drives the
        v1 → v1.1 schema auto-upgrade and the digest input)."""
        return bool(
            self.locality is not None
            or self.runtime_preference
            or self.workspace_requirements is not None
            or self.declared_fanout is not None)

    def idempotency_key(self) -> tuple[str, str, str]:
        """The idempotency triple (root, immediate_parent, logical_child_key)."""
        return (self.root_ref, self.immediate_parent_run_ref, self.logical_child_key)

    def canonical_payload(self) -> dict[str, Any]:
        """The digest input: every semantic field.  ``notes`` is excluded —
        free-text never participates in request identity.  Absent v1.1
        extension fields are excluded too, so a v1 request digests
        IDENTICALLY before and after the Rev 5 extension (redelivering a
        v1-era request after an upgrade is a retry, never a conflict);
        declared v1.1 content participates (a request that adds locality
        or a fan-out envelope is semantically different work)."""
        payload = _record_to_dict(self)
        payload.pop("notes", None)
        return _sparse_v1_1(
            payload,
            ("locality", "runtime_preference", "workspace_requirements",
             "declared_fanout"),
            self._has_v1_1_extensions)

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
        payload = _sparse_v1_1(
            _record_to_dict(self),
            ("locality", "runtime_preference", "workspace_requirements",
             "declared_fanout"),
            self._has_v1_1_extensions)
        payload["request_digest"] = self.request_digest
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ChildExecutionRequest":
        data = dict(payload or {})
        _pop_schema(data, (CHILD_EXECUTION_REQUEST_SCHEMA,
                           CHILD_EXECUTION_REQUEST_SCHEMA_V1_1), cls.__name__)
        supplied_digest = data.pop("request_digest", None)
        decision = data.get("routing_decision")
        if isinstance(decision, Mapping):
            data["routing_decision"] = RoutingDecision.from_dict(decision)
        if data.get("required_capabilities") is not None:
            data["required_capabilities"] = tuple(
                CapabilityRequest.from_dict(c) for c in data["required_capabilities"])
        data["locality"] = LocalitySpec.from_dict(data.get("locality"))
        data["workspace_requirements"] = WorkspaceRequirements.from_dict(
            data.get("workspace_requirements"))
        data["declared_fanout"] = FanoutEnvelope.from_dict(data.get("declared_fanout"))
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
    # --- Rev 5 v1.1 extension: native runtime identity / workspace /
    # operation / descendant policy (change order §3A binding list; all
    # OPTIONAL — absent = a plain v1 binding).  Refs are opaque and
    # credential-free; native IDs stay distinct identities joined to
    # company IDs by this durable mapping (Rev 5 §5 l.267).
    #: Runtime/harness kind of the bound execution (KNOWN_RUNTIME_KINDS
    #: vocabulary, open set).
    runtime_kind: str = ""
    #: T3 native identity chain (environment → server → project → thread → run).
    t3_environment_ref: str = ""
    t3_server_ref: str = ""
    project_ref: str = ""
    thread_ref: str = ""
    run_ref: str = ""
    #: Provider instance + native session the run is actually bound to.
    provider_instance_ref: str = ""
    native_session_ref: str = ""
    #: Workspace containment block (Rev 5 §4; change order §3E).
    workspace_ref: str = ""
    base_ref: str = ""
    writer_epoch: int | None = None
    lease_ref: str = ""
    #: Operation block: ``operation_key`` carries the native launch
    #: ``clientRequestId`` (T3 source-supported idempotency key) and
    #: ``caller_namespace`` the authenticated principal/namespace it was
    #: minted under — both must be persisted and replayed unchanged
    #: after a lost reply (Rev 5 §7 l.412; change order §3A).
    operation_key: str = ""
    caller_namespace: str = ""
    #: Descendant admission policy in force for this execution (Rev 5 §6).
    descendant_policy: str = ""
    #: The declared/enforced envelope when ``descendant_policy`` is
    #: ``bounded_native_fanout``.
    declared_fanout_envelope: FanoutEnvelope | None = None

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
        # --- v1.1 extension normalization/validation ---
        runtime_kind = self.runtime_kind.strip().lower()
        object.__setattr__(self, "runtime_kind", runtime_kind)
        if self.writer_epoch is not None and self.writer_epoch < 0:
            raise ValueError("writer_epoch must be >= 0 when supplied")
        if self.descendant_policy and self.descendant_policy not in DESCENDANT_POLICIES:
            raise ValueError(
                f"descendant_policy must be one of {DESCENDANT_POLICIES}, got "
                f"{self.descendant_policy!r}")
        if self.descendant_policy == "bounded_native_fanout":
            envelope = self.declared_fanout_envelope
            if envelope is None:
                raise ValueError(
                    "descendant_policy 'bounded_native_fanout' requires a "
                    "declared_fanout_envelope")
            if envelope.max_descendants < 1:
                raise ValueError(
                    "bounded_native_fanout envelope must bound at least one "
                    "descendant (use 'native_fanout_disabled' for zero)")
            if not envelope.enforcement_ref.strip():
                raise ValueError(
                    "bounded_native_fanout requires enforcement_ref naming the "
                    "native control that enforces the envelope")
        if self._has_v1_1_extensions:
            object.__setattr__(self, "schema", EXECUTION_BINDING_SCHEMA_V1_1)

    @property
    def _has_v1_1_extensions(self) -> bool:
        """True when any Rev 5 extension field is set (drives the v1 →
        v1.1 schema auto-upgrade)."""
        return bool(
            self.runtime_kind
            or self.t3_environment_ref or self.t3_server_ref
            or self.project_ref or self.thread_ref or self.run_ref
            or self.provider_instance_ref or self.native_session_ref
            or self.workspace_ref or self.base_ref
            or self.writer_epoch is not None or self.lease_ref
            or self.operation_key or self.caller_namespace
            or self.descendant_policy
            or self.declared_fanout_envelope is not None)

    def child_identity(self) -> tuple[str, str, str]:
        """The (root, immediate_parent, logical_child_key) placement identity."""
        return (self.root_run_ref, self.immediate_parent_run_ref, self.logical_child_key)

    def to_dict(self) -> dict[str, Any]:
        return _sparse_v1_1(
            _record_to_dict(self),
            ("runtime_kind", "t3_environment_ref", "t3_server_ref",
             "project_ref", "thread_ref", "run_ref",
             "provider_instance_ref", "native_session_ref",
             "workspace_ref", "base_ref", "writer_epoch", "lease_ref",
             "operation_key", "caller_namespace", "descendant_policy",
             "declared_fanout_envelope"),
            self._has_v1_1_extensions)

    def binds_request(self, request: ChildExecutionRequest) -> bool:
        """True when this binding is the fenced assignment OF that request:
        same child identity triple and same admitted request digest."""
        return (self.child_identity() == request.idempotency_key()
                and self.request_digest == request.request_digest)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExecutionBinding":
        data = dict(payload or {})
        _pop_schema(data, (EXECUTION_BINDING_SCHEMA,
                           EXECUTION_BINDING_SCHEMA_V1_1), cls.__name__)
        if data.get("shared_quota_resource_refs") is not None:
            data["shared_quota_resource_refs"] = _string_tuple(
                data["shared_quota_resource_refs"])
        data["declared_fanout_envelope"] = FanoutEnvelope.from_dict(
            data.get("declared_fanout_envelope"))
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
