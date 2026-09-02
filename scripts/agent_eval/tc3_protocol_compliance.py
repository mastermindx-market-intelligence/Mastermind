"""EVAL-S1 deterministic scorer for TC3 --
``mastermind.carrier_protocol_compliance.v1``
(docs/superpowers/plans/2026-09-01-agent-evaluation-s1-scorers.md).

Three dimensions:

- ``correctness``: the submission's ``selected_action`` must exactly equal
  ``expected_contract``'s gold ``answer`` -- one of the scenario's own
  ``input_fixture.candidate_actions``. A selection outside the declared
  candidate set, or no selection at all, is a deterministic ``FAIL``, never
  a soft/partial outcome (this task class is ``risk_tier: HIGH`` --a wrong
  answer is an authority/collision risk). **NB-2 repair (adversarial
  review of PR #333):** this stays STRICT -- a whitespace/case variant of a
  candidate action is NEVER silently credited as a match, fail-closed by
  design -- but when a rejected selection is a DETECTABLE normalization-
  only variant of a declared candidate action (casefold + whitespace-
  collapsed equality), the more specific reason code
  ``NORMALIZATION_ONLY_MISMATCH`` is attached alongside the generic one,
  so a reviewer can distinguish "this was a formatting slip" from "this is
  a genuinely wrong action" without changing the pass/fail outcome.
- ``rationale_provided``: PASS iff the submission supplies a non-empty,
  non-whitespace ``rationale`` string whenever ``expected_contract``
  declares one (every C0 TC3 case does). ONLY presence is checked --
  whether the rationale's CONTENT correctly explains why is never
  deterministically checkable; that is rubric residue (see below), never
  folded silently into this dimension.
- ``rubric_residue``: always ``UNKNOWN``, ``evidence_refs`` citing the
  scenario's own ``expected_contract`` artifact -- rationale reasoning
  quality is never model-graded by this scorer.

This module performs no filesystem, network, or environment access; the
gold answer/rationale, the scenario's candidate-action set, and the
submission are all supplied by the caller.

Scorer identity: ``mastermind.tc3_protocol_compliance.v1``, method
``DETERMINISTIC``.
"""
from __future__ import annotations

import re

from scripts.agent_eval import scoring

SCORER_ID = "mastermind.tc3_protocol_compliance.v1"
DIMENSIONS: tuple[str, ...] = ("correctness", "rationale_provided", "rubric_residue")

_WHITESPACE_RE = re.compile(r"\s+")

#: NB-2: a whitespace/case variant of a candidate action is a detectable
#: formatting slip, distinct from a genuinely wrong action -- disclosed,
#: never silently credited (this scorer still fails closed).
NORMALIZATION_ONLY_REASON_CODE = "NORMALIZATION_ONLY_MISMATCH"


def _normalize_action(value: object) -> str:
    return _WHITESPACE_RE.sub(" ", str(value or "")).strip().casefold()


def score_submission(expected_contract: dict, input_fixture: dict, submission: dict) -> list[dict]:
    """Pure deterministic scoring.

    ``input_fixture`` carries the scenario's own ``candidate_actions`` (used
    only to sanity-check the gold/selected actions are legitimate members
    of the declared choice set -- this scorer never invents a choice set of
    its own). ``submission`` is
    ``{"selected_action": str, "rationale": str}``."""
    gold_action = expected_contract.get("answer")
    candidate_actions = list(input_fixture.get("candidate_actions") or [])
    selected = submission.get("selected_action")

    reason_codes: list[str] = []
    if candidate_actions and gold_action not in candidate_actions:
        reason_codes.append("GOLD_ACTION_NOT_IN_CANDIDATE_SET")
    if selected is None:
        status = "FAIL"
        reason_codes.append("NO_ACTION_SELECTED")
    elif candidate_actions and selected not in candidate_actions:
        status = "FAIL"
        reason_codes.append("SELECTED_ACTION_NOT_IN_CANDIDATE_SET")
        # NB-2: still fails closed -- this only ADDS a more specific,
        # disclosed diagnostic when the miss is detectably a formatting
        # variant (case/whitespace) of a declared candidate action.
        normalized_selected = _normalize_action(selected)
        normalization_only_candidates = {
            _normalize_action(candidate) for candidate in candidate_actions
        }
        if normalized_selected in normalization_only_candidates:
            reason_codes.append(NORMALIZATION_ONLY_REASON_CODE)
    elif selected == gold_action:
        status = "PASS"
    else:
        status = "FAIL"
        reason_codes.append("SELECTED_ACTION_MISMATCH")
    correctness = {
        "dimension": "correctness",
        "status": status,
        "reason_codes": sorted(set(reason_codes)),
        "evidence_refs": [],
    }

    gold_rationale = expected_contract.get("rationale")
    submitted_rationale = submission.get("rationale")
    if not gold_rationale:
        rationale_status, rationale_reasons = "UNKNOWN", ["NO_GOLD_RATIONALE_DECLARED"]
    elif isinstance(submitted_rationale, str) and submitted_rationale.strip():
        rationale_status, rationale_reasons = "PASS", []
    else:
        rationale_status, rationale_reasons = "FAIL", ["RATIONALE_MISSING"]
    rationale_provided = {
        "dimension": "rationale_provided",
        "status": rationale_status,
        "reason_codes": sorted(set(rationale_reasons)),
        "evidence_refs": [],
    }

    rubric_residue = {
        "dimension": "rubric_residue",
        "status": "UNKNOWN",
        "reason_codes": ["RUBRIC_RESIDUE_NOT_SCORED"],
        "evidence_refs": [],
    }
    return [correctness, rationale_provided, rubric_residue]


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
