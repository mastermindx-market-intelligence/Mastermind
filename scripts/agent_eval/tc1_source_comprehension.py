"""EVAL-S1 deterministic scorer for TC1 --
``mastermind.current_source_comprehension.v1``
(docs/superpowers/plans/2026-09-01-agent-evaluation-s1-scorers.md).

Deterministic fact-match against the scenario's ``expected_contract`` gold
``answer``. Never model-graded: the gold answer is split into semicolon-
delimited FACT CLAUSES (the deterministic scoring unit), and a submission's
own ``answer`` text is checked for normalized-substring containment of each
clause. ``PASS`` when every clause is present, ``FAIL`` when none are,
``PARTIAL`` otherwise. The gold ``rationale`` field's REASONING QUALITY is
never deterministically checkable -- it is explicit rubric residue, always
emitted as a separate ``UNKNOWN`` dimension result pointing at the
scenario's own ``expected_contract`` artifact (never inlined as prose; the
scorer-pass schema's ``evidence_refs`` field is a reference list, not a
text field).

This module performs no filesystem, network, or environment access -- the
gold-fact content and the submission are both supplied by the caller
(a test fixture built from the real committed corpus, or a future runner
integration); scoring is a pure function of its arguments.

Scorer identity: ``mastermind.tc1_source_comprehension.v1``, method
``DETERMINISTIC``. Dimensions: ``correctness`` (deterministic), ``rubric_
residue`` (always ``UNKNOWN`` -- this scorer never claims to grade
reasoning quality).
"""
from __future__ import annotations

import re

from scripts.agent_eval import scoring

SCORER_ID = "mastermind.tc1_source_comprehension.v1"
DIMENSIONS: tuple[str, ...] = ("correctness", "rubric_residue")

_WHITESPACE_RE = re.compile(r"\s+")


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
        correctness = {
            "dimension": "correctness",
            "status": "UNKNOWN",
            "reason_codes": ["NO_GOLD_FACT_CLAUSES"],
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
        correctness = {
            "dimension": "correctness",
            "status": status,
            "reason_codes": sorted(set(reason_codes)),
            "evidence_refs": [],
        }

    rubric_residue = {
        "dimension": "rubric_residue",
        "status": "UNKNOWN",
        "reason_codes": ["RUBRIC_RESIDUE_NOT_SCORED"],
        "evidence_refs": [],
    }
    return [correctness, rubric_residue]


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
