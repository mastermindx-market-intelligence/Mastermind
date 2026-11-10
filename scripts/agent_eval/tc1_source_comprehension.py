"""EVAL-S1 deterministic scorer for TC1 --
``mastermind.current_source_comprehension.v1``
(docs/superpowers/plans/2026-09-01-agent-evaluation-s1-scorers.md).

Deterministic fact-match against the scenario's ``expected_contract`` gold
``answer``. Never model-graded: the gold answer is split into semicolon-
delimited FACT CLAUSES.

**Review repair (BLOCKER-1, adversarial review of PR #333):** the original
containment-based check let a submission that merely CONTAINED the gold
token score PASS even when the submission (a) regurgitated the source
extract verbatim (which itself contains the gold token as a substring) or
(b) NEGATED the correct answer ("The status is NOT INVALID_EFFECT_UNKNOWN")
-- containment cannot distinguish "states X" from "quotes X" or "denies X".
The fix is scoped by clause count, never by task class:

- A gold with exactly ONE fact clause (a closed-vocabulary token, e.g.
  ``INVALID_EFFECT_UNKNOWN``) is scored by NORMALIZED WHOLE-ANSWER
  EQUALITY, never containment. Regurgitating the extract or negating the
  token no longer scores PASS -- the whole submitted answer must equal the
  gold token. Documented tradeoff: a correct-but-reworded answer (extra
  words around the right token) now FAILS too. That is an accepted,
  disclosed cost of closing the regurgitation/negation hole for
  closed-vocabulary golds, not a bug -- see ``tests/test_agent_eval_s1_
  scorers.py::test_tc1_probe3_reworded_correct_answer_fails_under_equality_by_design``.
- A gold with MORE THAN ONE fact clause (free-form multi-fact prose) keeps
  substring containment -- exact-whole-answer equality is too brittle for
  a paraphrased multi-sentence explanation -- but every non-``UNKNOWN``
  result now carries the standing reason code
  ``CONTAINMENT_PROXY_NOT_ENTAILMENT``: containment is a PROXY for "the
  submission states this fact," never a claim of actual semantic
  entailment, and this scorer never lets that distinction go unstated.

The gold ``rationale`` field's reasoning quality is NEVER scored -- it is
emitted as a separate ``rubric_residue`` dimension, status ``UNKNOWN``,
``evidence_refs`` citing the scenario's own ``expected_contract`` artifact
(never inlined as prose -- the scorer-pass schema's ``evidence_refs``
field is a reference list, not free text).

This module performs no filesystem, network, or environment access -- the
gold-fact content and the submission are both supplied by the caller
(a test fixture built from the real committed corpus, or a future runner
integration); scoring is a pure function of its arguments.

Scorer identity: ``mastermind.tc1_source_comprehension.v1``, method
``DETERMINISTIC``. Dimensions: ``gold_clause_containment`` (renamed from
``correctness`` in the review repair -- the name now states the actual
mechanism, equality-for-one-clause/containment-for-many, never implying a
stronger "correctness" guarantee than the mechanism provides),
``rubric_residue`` (always ``UNKNOWN`` -- this scorer never claims to
grade reasoning quality).
"""
from __future__ import annotations

import re

from scripts.agent_eval import scoring

SCORER_ID = "mastermind.tc1_source_comprehension.v1"
DIMENSIONS: tuple[str, ...] = ("gold_clause_containment", "rubric_residue")

_WHITESPACE_RE = re.compile(r"\s+")

#: BLOCKER-1: containment is never entailment -- this proxy code is
#: attached to every non-UNKNOWN multi-clause result, disclosing that a
#: PASS/PARTIAL/FAIL here means "the literal clause text is/isn't a
#: substring," never a semantic-correctness claim.
CONTAINMENT_PROXY_REASON_CODE = "CONTAINMENT_PROXY_NOT_ENTAILMENT"


def _normalize(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip().casefold()


def gold_fact_clauses(expected_contract: dict) -> list[str]:
    """The deterministic scoring unit for TC1: ``expected_contract["answer"]``
    split on ``;`` into independently checkable, normalized fact clauses.
    Never touches ``rationale`` -- that field's content is rubric residue,
    not a scoring input."""
    answer = expected_contract.get("answer") or ""
    clauses = [_normalize(part) for part in answer.split(";")]
    return [clause for clause in clauses if clause]


def score_submission(expected_contract: dict, submission: dict) -> list[dict]:
    """Pure deterministic scoring. Returns unsorted ``dimension_result``
    dicts (the caller/``scoring.build_scorer_pass_document`` sorts them).

    ``submission`` is ``{"answer": str}`` -- the structured task-output
    contract this scorer consumes."""
    clauses = gold_fact_clauses(expected_contract)
    submitted_answer = _normalize(str(submission.get("answer") or ""))

    if not clauses:
        gold_clause_containment = {
            "dimension": "gold_clause_containment",
            "status": "UNKNOWN",
            "reason_codes": ["NO_GOLD_FACT_CLAUSES"],
            "evidence_refs": [],
        }
    elif len(clauses) == 1:
        # BLOCKER-1: single closed-vocabulary clause -- normalized WHOLE-
        # ANSWER EQUALITY, never containment (see module docstring).
        status = "PASS" if submitted_answer == clauses[0] else "FAIL"
        reason_codes = [] if status == "PASS" else ["GOLD_FACT_CLAUSE_MISSING"]
        gold_clause_containment = {
            "dimension": "gold_clause_containment",
            "status": status,
            "reason_codes": sorted(set(reason_codes)),
            "evidence_refs": [],
        }
    else:
        present = [clause for clause in clauses if clause in submitted_answer]
        if len(present) == len(clauses):
            status, reason_codes = "PASS", []
        elif not present:
            status, reason_codes = "FAIL", ["GOLD_FACT_CLAUSE_MISSING"]
        else:
            status, reason_codes = "PARTIAL", ["GOLD_FACT_CLAUSE_MISSING"]
        reason_codes = sorted(set(reason_codes) | {CONTAINMENT_PROXY_REASON_CODE})
        gold_clause_containment = {
            "dimension": "gold_clause_containment",
            "status": status,
            "reason_codes": reason_codes,
            "evidence_refs": [],
        }

    rubric_residue = {
        "dimension": "rubric_residue",
        "status": "UNKNOWN",
        "reason_codes": ["RUBRIC_RESIDUE_NOT_SCORED"],
        "evidence_refs": [],
    }
    return [gold_clause_containment, rubric_residue]


def build_scorer_pass(
    run: dict,
    scenario: dict,
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
    """``expected_contract`` is the DESERIALIZED gold-fact content (e.g. the
    real corpus scenario's ``fixtures/expected.json`` bytes, already parsed
    by the caller -- this module never reads a file itself). ``scenario``
    supplies the scenario's own ``expected_contract`` ``{artifact_ref,
    digest}`` pointer, cited as evidence for the ``rubric_residue``
    dimension."""
    dimension_results = score_submission(expected_contract, submission)
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
