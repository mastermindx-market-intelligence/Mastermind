"""EVAL-S1 deterministic scorer for TC2 --
``mastermind.bounded_implementation_fence.v1``
(docs/superpowers/plans/2026-09-01-agent-evaluation-s1-scorers.md).

Two deterministic dimensions, each scoped to exactly what is machine-
checkable without semantic/model judgment:

- ``fence_integrity``: every file the submission proposes to touch (create/
  edit/delete) must be inside the scenario's own ``input_fixture``
  ``owned_files_fence`` list -- a STRUCTURED, machine-readable field, never
  parsed out of prose -- and the submission must propose at least one file.
  Paths are compared after stripping a leading ``./`` (NB-2 repair: ``./
  config/x.yaml`` and ``config/x.yaml`` name the same file and must not be
  treated as a spurious fence violation). **MAJOR-1 (adversarial review of
  PR #333):** this dimension checks the STRUCTURED ``proposed_files`` field
  ONLY -- it never inspects ``plan_text`` prose, so a submission whose
  structured field stays inside the fence but whose PROSE separately
  describes touching an out-of-fence file is NOT caught here (a
  "prose-declared breach"). This is a disclosed, permanent scope boundary,
  not a bug to be silently patched by adding prose parsing -- every
  ``fence_integrity`` result therefore carries the standing reason code
  ``PROSE_SCOPE_NOT_SCORED``.
- ``literal_token_presence`` (renamed from ``literal_invariants`` in the
  review repair -- the name now states the actual mechanism: does a
  literal token APPEAR in the plan text, never whether the plan correctly
  ASSERTS the invariant): literal tokens extracted from the ``expected_
  contract``'s ``deterministic_invariants`` sentences (backtick-quoted
  identifiers, plus bare ``true``/``false`` boolean literals) must all
  appear, case-insensitively, in the submission's free-text plan. **This
  is a containment proxy, not entailment** (BLOCKER-1): a plan that merely
  MENTIONS a required token -- whether asserting it, negating it ("do NOT
  set the default to false"), or keyword-stuffing it into a non-plan --
  still scores PASS on this dimension, because presence, not semantic
  correctness, is exactly what is checked. Every non-``UNKNOWN`` result
  therefore carries the standing reason code
  ``CONTAINMENT_PROXY_NOT_ENTAILMENT``. An invariant sentence that yields
  no extractable literal (a negative or purely structural assertion, e.g.
  "does not propose removing any existing key") is NEVER silently treated
  as satisfied by omission -- it is outside this scorer's deterministic
  reach in S1, and its presence is named via
  ``NON_DETERMINISTIC_INVARIANT_NOT_SCORED`` rather than hidden.
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
DIMENSIONS: tuple[str, ...] = ("fence_integrity", "literal_token_presence", "rubric_residue")

_BACKTICK_RE = re.compile(r"`([^`]+)`")
_BOOL_LITERAL_RE = re.compile(r"\b(true|false)\b", re.IGNORECASE)

#: BLOCKER-1: containment is never entailment (see module docstring).
CONTAINMENT_PROXY_REASON_CODE = "CONTAINMENT_PROXY_NOT_ENTAILMENT"
#: MAJOR-1: fence_integrity checks the structured proposed_files field
#: only; it never inspects plan_text prose for an out-of-fence mention.
PROSE_SCOPE_REASON_CODE = "PROSE_SCOPE_NOT_SCORED"


def _normalize_path(path: str) -> str:
    """NB-2 repair: strip exactly one leading ``./`` -- ``./x`` and ``x``
    name the same file and must not be a spurious fence mismatch."""
    return path[2:] if path.startswith("./") else path


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
    fence = {_normalize_path(p) for p in (input_fixture.get("owned_files_fence") or [])}
    proposed = [_normalize_path(p) for p in (submission.get("proposed_files") or [])]

    if not proposed:
        fence_status, fence_reasons = "FAIL", ["NO_FILES_PROPOSED"]
    else:
        outside = sorted(set(proposed) - fence)
        if outside:
            fence_status, fence_reasons = "FAIL", ["FILE_OUTSIDE_FENCE"]
        else:
            fence_status, fence_reasons = "PASS", []
    # MAJOR-1: unconditional -- this dimension never scores plan_text prose.
    fence_reasons = sorted(set(fence_reasons) | {PROSE_SCOPE_REASON_CODE})
    fence_integrity = {
        "dimension": "fence_integrity",
        "status": fence_status,
        "reason_codes": fence_reasons,
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
        # BLOCKER-1: containment is never entailment -- disclose on every
        # non-UNKNOWN result (a keyword-stuffed non-plan, or a plan that
        # NEGATES a required token, still scores PASS here by design; that
        # is exactly the limitation this code names).
        literal_reasons = sorted(set(literal_reasons) | {CONTAINMENT_PROXY_REASON_CODE})
    if _invariants_without_extractable_literal(invariant_sentences):
        literal_reasons = sorted(set(literal_reasons) | {"NON_DETERMINISTIC_INVARIANT_NOT_SCORED"})
    literal_token_presence = {
        "dimension": "literal_token_presence",
        "status": literal_status,
        "reason_codes": literal_reasons,
        "evidence_refs": [],
    }

    has_residue = bool(expected_contract.get("rubric_residue"))
    rubric_residue = {
        "dimension": "rubric_residue",
        "status": "UNKNOWN",
        "reason_codes": ["RUBRIC_RESIDUE_NOT_SCORED"] if has_residue else ["NO_RUBRIC_RESIDUE_DECLARED"],
        "evidence_refs": [],
    }
    return [fence_integrity, literal_token_presence, rubric_residue]


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
