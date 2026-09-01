"""EVAL-S1 deterministic scorer for TC2 --
``mastermind.bounded_implementation_fence.v1``
(docs/superpowers/plans/2026-09-01-agent-evaluation-s1-scorers.md).

Two deterministic dimensions, each scoped to exactly what is machine-
checkable without semantic/model judgment:

- ``fence_integrity``: every file the submission proposes to touch (create/
  edit/delete) must be inside the scenario's own ``input_fixture``
  ``owned_files_fence`` list -- a STRUCTURED, machine-readable field, never
  parsed out of prose -- and the submission must propose at least one file.
- ``literal_invariants``: literal tokens extracted from the ``expected_
  contract``'s ``deterministic_invariants`` sentences (backtick-quoted
  identifiers, plus bare ``true``/``false`` boolean literals) must all
  appear, case-insensitively, in the submission's free-text plan. An
  invariant sentence that yields no extractable literal (a negative or
  purely structural assertion, e.g. "does not propose removing any
  existing key") is NEVER silently treated as satisfied by omission -- it
  is outside this scorer's deterministic reach in S1, and its presence is
  named via ``NON_DETERMINISTIC_INVARIANT_NOT_SCORED`` rather than hidden.
- ``rubric_residue``: ``UNKNOWN`` whenever ``expected_contract`` declares
  one (every C0 TC2 case does), ``evidence_refs`` citing the scenario's own
  ``expected_contract`` artifact -- prose style/formatting idiom is never
  model-graded here.

This module performs no filesystem, network, or environment access; the
gold-fact content, the scenario's structured fence, and the submission are
all supplied by the caller.

Scorer identity: ``mastermind.tc2_implementation_fence.v1``, method
``DETERMINISTIC``.
"""
from __future__ import annotations

import re

from scripts.agent_eval import scoring

SCORER_ID = "mastermind.tc2_implementation_fence.v1"
DIMENSIONS: tuple[str, ...] = ("fence_integrity", "literal_invariants", "rubric_residue")

_BACKTICK_RE = re.compile(r"`([^`]+)`")
_BOOL_LITERAL_RE = re.compile(r"\b(true|false)\b", re.IGNORECASE)


def extract_literal_tokens(invariant_sentences: list[str]) -> list[str]:
    """Deterministic literal-token extraction: backtick-quoted identifiers,
    plus bare ``true``/``false`` boolean literals, normalized to casefold
    and returned sorted-unique. A sentence contributing no extractable
    token contributes nothing here -- see the module docstring's disclosed
    boundary."""
    tokens: list[str] = []
    for sentence in invariant_sentences:
        tokens.extend(match.casefold() for match in _BACKTICK_RE.findall(sentence))
        tokens.extend(match.casefold() for match in _BOOL_LITERAL_RE.findall(sentence))
    return sorted(set(tokens))


def _invariants_without_extractable_literal(invariant_sentences: list[str]) -> list[str]:
    return [
        sentence
        for sentence in invariant_sentences
        if not _BACKTICK_RE.search(sentence) and not _BOOL_LITERAL_RE.search(sentence)
    ]


def score_submission(expected_contract: dict, input_fixture: dict, submission: dict) -> list[dict]:
    """Pure deterministic scoring.

    ``input_fixture`` is the scenario's deserialized ``input.json`` content
    (carries the structured ``owned_files_fence``); ``expected_contract``
    is the deserialized ``expected.json`` content (``deterministic_
    invariants`` + ``rubric_residue``); ``submission`` is
    ``{"proposed_files": [str, ...], "plan_text": str}``."""
    fence = set(input_fixture.get("owned_files_fence") or [])
    proposed = list(submission.get("proposed_files") or [])

    if not proposed:
        fence_status, fence_reasons = "FAIL", ["NO_FILES_PROPOSED"]
    else:
        outside = sorted(set(proposed) - fence)
        if outside:
            fence_status, fence_reasons = "FAIL", ["FILE_OUTSIDE_FENCE"]
        else:
            fence_status, fence_reasons = "PASS", []
    fence_integrity = {
        "dimension": "fence_integrity",
        "status": fence_status,
        "reason_codes": sorted(set(fence_reasons)),
        "evidence_refs": [],
    }

    invariant_sentences = list(expected_contract.get("deterministic_invariants") or [])
    literals = extract_literal_tokens(invariant_sentences)
    plan_text = str(submission.get("plan_text") or "").casefold()
    if not literals:
        literal_status, literal_reasons = "UNKNOWN", ["NO_EXTRACTABLE_LITERAL_INVARIANTS"]
    else:
        missing = [token for token in literals if token not in plan_text]
        if not missing:
            literal_status, literal_reasons = "PASS", []
        elif len(missing) == len(literals):
            literal_status, literal_reasons = "FAIL", ["LITERAL_INVARIANT_MISSING"]
        else:
            literal_status, literal_reasons = "PARTIAL", ["LITERAL_INVARIANT_MISSING"]
    if _invariants_without_extractable_literal(invariant_sentences):
        literal_reasons = sorted(set(literal_reasons) | {"NON_DETERMINISTIC_INVARIANT_NOT_SCORED"})
    literal_invariants = {
        "dimension": "literal_invariants",
        "status": literal_status,
        "reason_codes": sorted(set(literal_reasons)),
        "evidence_refs": [],
    }

    has_residue = bool(expected_contract.get("rubric_residue"))
    rubric_residue = {
        "dimension": "rubric_residue",
        "status": "UNKNOWN",
        "reason_codes": ["RUBRIC_RESIDUE_NOT_SCORED"] if has_residue else ["NO_RUBRIC_RESIDUE_DECLARED"],
        "evidence_refs": [],
    }
    return [fence_integrity, literal_invariants, rubric_residue]


def build_scorer_pass(
    run: dict,
    scenario: dict,
    input_fixture: dict,
    expected_contract: dict,
    submission: dict,
    *,
    scorer_pass_id: str,
    scorer_code_ref: str,
    scorer_version: str = "1",
    created_at: str,
    grader_identity: str | None = None,
    supersedes: str | None = None,
) -> dict:
    dimension_results = score_submission(expected_contract, input_fixture, submission)
    for result in dimension_results:
        if result["dimension"] == "rubric_residue":
            result["evidence_refs"] = [dict(scenario["expected_contract"])]
    return scoring.build_scorer_pass_document(
        run,
        scorer_pass_id=scorer_pass_id,
        scorer_id=SCORER_ID,
        scorer_version=scorer_version,
        scorer_code_ref=scorer_code_ref,
        method="DETERMINISTIC",
        dimension_results=dimension_results,
        created_at=created_at,
        grader_identity=grader_identity,
        supersedes=supersedes,
    )
