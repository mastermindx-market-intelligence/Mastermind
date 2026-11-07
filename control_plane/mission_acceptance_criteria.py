"""Strict read-only candidate requirements from existing Executive objectives.

The OS launcher stores criteria *within the already admitted objective*, using
one closed versioned JSON-array suffix. It is single-line/printable so it does
not weaken the Executive CEO ingress's Cc/Cs prohibition or 4000-char ceiling.
The original Job, objective, operation identity, result and authority remain
with Executive Runtime. This module has no I/O, persistence, verdict or queue.

A parsed candidate is NEVER signed proof of origin, independent validation,
product acceptance, or a permission to execute. Future consumers must acquire
the original objective from the canonical owner and separately bind an exact
Job, Attempt, result revision and eligible reviewer to any acceptance ruling.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass


OPEN_MARKER = "[MASTERMIND_ACCEPTANCE_CRITERIA_V1:"
SECTION = " " + OPEN_MARKER
CLOSE = "]"
SCHEMA = "mastermind.mission_acceptance_criteria_candidate.v1"
MAX_OBJECTIVE_BYTES = 4000
MAX_CRITERIA = 6
MAX_CRITERION_UTF16_UNITS = 500


class AcceptanceCriteriaError(ValueError):
    """Reserved criteria syntax is present but malformed or ambiguous."""


@dataclass(frozen=True, slots=True)
class AcceptanceCriterion:
    ordinal: int
    requirement: str
    criterion_digest: str


@dataclass(frozen=True, slots=True)
class MissionAcceptanceCriteriaCandidate:
    schema: str
    objective_sha256: str
    goal: str
    criteria: tuple[AcceptanceCriterion, ...]
    state: str = "UNVERIFIED"


def _utf8_bytes(value: str) -> bytes:
    try:
        return value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise AcceptanceCriteriaError("objective contains malformed Unicode") from exc


def _utf16_units(value: str) -> int:
    try:
        return len(value.encode("utf-16-le", errors="strict")) // 2
    except UnicodeError as exc:
        raise AcceptanceCriteriaError("criterion contains malformed Unicode") from exc


def _forbidden(value: str, *, criterion: bool = False) -> bool:
    categories = {"Cc", "Cs"}
    if criterion:
        categories.update({"Zl", "Zp"})
    return any(unicodedata.category(char) in categories for char in value)


def parse_acceptance_criteria_candidate(objective: str) -> MissionAcceptanceCriteriaCandidate | None:
    """Recover structural v1 requirements, not their authenticity or passage.

    `None` means no v1 section was supplied; malformed reserved syntax is an
    error, not an empty/successful checklist. The SHA-256 identifies only the
    supplied objective text and MUST be re-bound to the trusted Runtime Job.
    """
    if not isinstance(objective, str):
        raise AcceptanceCriteriaError("objective must be text")
    if OPEN_MARKER not in objective:
        return None
    if objective.count(SECTION) != 1 or objective.count(OPEN_MARKER) != 1:
        raise AcceptanceCriteriaError("acceptance marker is missing or ambiguous")
    if not objective.endswith(CLOSE):
        raise AcceptanceCriteriaError("acceptance JSON section must end with closing marker")
    raw = _utf8_bytes(objective)
    if len(raw) > MAX_OBJECTIVE_BYTES:
        raise AcceptanceCriteriaError("objective exceeds the launch adapter byte ceiling")
    if _forbidden(objective):
        raise AcceptanceCriteriaError("objective contains control or surrogate characters")
    goal, section = objective.split(SECTION, 1)
    if not goal or goal != goal.strip():
        raise AcceptanceCriteriaError("goal is empty or noncanonical")
    encoded = section[:-len(CLOSE)]
    try:
        items = json.loads(encoded)
    except (ValueError, TypeError) as exc:
        raise AcceptanceCriteriaError("acceptance criteria must be an exact JSON array") from exc
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_CRITERIA:
        raise AcceptanceCriteriaError("acceptance criteria must be one to six items")
    if not all(isinstance(item, str) and item and item == item.strip()
               and _utf16_units(item) <= MAX_CRITERION_UTF16_UNITS
               and not _forbidden(item, criterion=True)
               for item in items):
        raise AcceptanceCriteriaError("acceptance criterion text is not canonical")
    # The exact compact representation produced by JavaScript JSON.stringify.
    # No extra keys, whitespace tricks, escaped alternate encodings or trailing
    # commentary may impersonate the original fixed browser-generated form.
    if encoded != json.dumps(items, ensure_ascii=False, separators=(",", ":")):
        raise AcceptanceCriteriaError("acceptance JSON serialization is not canonical")
    objective_digest = hashlib.sha256(raw).hexdigest()
    criteria = tuple(
        AcceptanceCriterion(
            ordinal=index,
            requirement=requirement,
            criterion_digest=hashlib.sha256(
                f"{SCHEMA}\0{objective_digest}\0{index}\0{requirement}".encode("utf-8")
            ).hexdigest(),
        )
        for index, requirement in enumerate(items, start=1)
    )
    return MissionAcceptanceCriteriaCandidate(
        schema=SCHEMA,
        objective_sha256=objective_digest,
        goal=goal,
        criteria=criteria,
    )
