"""Production-inert Harness^2 evidence bridge for Mastermind Agent Evaluation.

This is a pure scoring/proposal function, NOT a harness installer or promotion plane.
Harness^2 task adaptation remains an external, isolated experiment until existing
EVAL + Outcome Learning + Agent OS owners accept its evidence.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping

SCHEMA = "mastermind.harness2_comparison.v1"
RESULT_SCHEMA = "mastermind.harness2_assessment.v1"
DIGEST = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_FIELDS = frozenset({
    "schema", "experiment_id", "harness2_source_sha", "baseline_harness_digest",
    "candidate_harness_digest", "configuration_digest", "holdout_commitment_digest",
    "task_domain", "observations",
})
OBS_FIELDS = frozenset({
    "case_id", "split", "arm", "score", "accepted", "resource_units",
    "authority_violations", "effect_state", "grader_digest",
})
MIN_PAIRS = 10
MIN_MEAN_IMPROVEMENT = 0.02


class Harness2ComparisonError(ValueError):
    """Input is untrusted, incomplete, incomparable, or structurally invalid."""


def _text(value: object, name: str, max_length: int = 128) -> str:
    if type(value) is not str or not value or len(value) > max_length:
        raise Harness2ComparisonError(f"{name} must be a nonempty bounded string")
    if any(ord(c) < 32 for c in value):
        raise Harness2ComparisonError(f"{name} contains control characters")
    return value


def _digest(value: object, name: str) -> str:
    if type(value) is not str or not DIGEST.fullmatch(value):
        raise Harness2ComparisonError(f"{name} must be lowercase sha256")
    return value


def _number(value: object, name: str, *, maximum: float = 1.0) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise Harness2ComparisonError(f"{name} must be a finite number")
    if value < 0 or value > maximum:
        raise Harness2ComparisonError(f"{name} out of range")
    return float(value)


def assess(payload: Mapping) -> dict:
    """Compare predeclared baseline/candidate on paired held-out tasks.

    Returns a non-authoritative assessment. This function never reads a file,
    contacts a provider, runs a model, schedules a Job, or mutates Agent OS.
    """
    if not isinstance(payload, Mapping) or set(payload) != ALLOWED_FIELDS:
        raise Harness2ComparisonError("comparison requires exactly its closed fields")
    if payload["schema"] != SCHEMA:
        raise Harness2ComparisonError("unsupported comparison schema")
    experiment_id = _text(payload["experiment_id"], "experiment_id")
    domain = _text(payload["task_domain"], "task_domain")
    sha = payload["harness2_source_sha"]
    if type(sha) is not str or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise Harness2ComparisonError("harness2_source_sha must be a pinned git SHA")
    baseline = _digest(payload["baseline_harness_digest"], "baseline_harness_digest")
    candidate = _digest(payload["candidate_harness_digest"], "candidate_harness_digest")
    if baseline == candidate:
        raise Harness2ComparisonError("candidate must differ from baseline")
    cfg = _digest(payload["configuration_digest"], "configuration_digest")
    holdout = _digest(payload["holdout_commitment_digest"], "holdout_commitment_digest")
    rows = payload["observations"]
    if type(rows) is not list or not 1 <= len(rows) <= 4096:
        raise Harness2ComparisonError("observations must be a bounded nonempty list")

    cases: dict[str, dict[str, dict]] = {}
    grader = None
    for i, raw in enumerate(rows):
        if type(raw) is not dict or set(raw) != OBS_FIELDS:
            raise Harness2ComparisonError(f"observations[{i}] has incorrect fields")
        case = _text(raw["case_id"], f"observations[{i}].case_id")
        if raw["split"] != "sealed_holdout":
            raise Harness2ComparisonError("only sealed_holdout may support comparison")
        arm = raw["arm"]
        if arm not in ("baseline", "candidate"):
            raise Harness2ComparisonError("unknown arm")
        gd = _digest(raw["grader_digest"], "grader_digest")
        if grader is None:
            grader = gd
        elif grader != gd:
            raise Harness2ComparisonError("grader changed during matched comparison")
        score = _number(raw["score"], "score")
        resource = _number(raw["resource_units"], "resource_units", maximum=1e12)
        if type(raw["accepted"]) is not bool:
            raise Harness2ComparisonError("accepted must be boolean")
        if type(raw["authority_violations"]) is not int or raw["authority_violations"] < 0:
            raise Harness2ComparisonError("authority_violations must be nonnegative integer")
        if raw["effect_state"] != "NONE":
            raise Harness2ComparisonError("effect state must be definitively NONE")
        entries = cases.setdefault(case, {})
        if arm in entries:
            raise Harness2ComparisonError("duplicate case/arm observation")
        entries[arm] = {"score": score, "resource": resource,
                        "accepted": raw["accepted"],
                        "violations": raw["authority_violations"]}

    if any(set(v) != {"baseline", "candidate"} for v in cases.values()):
        raise Harness2ComparisonError("holdout requires exactly paired arms per case")
    ordered = [cases[k] for k in sorted(cases)]
    gains = [r["candidate"]["score"] - r["baseline"]["score"] for r in ordered]
    mean = sum(gains) / len(gains)
    any_regression = any(
        r["baseline"]["accepted"] and not r["candidate"]["accepted"]
        or r["candidate"]["violations"] > 0
        or r["candidate"]["resource"] > 2 * max(r["baseline"]["resource"], 0.001)
        for r in ordered
    )
    enough = len(ordered) >= MIN_PAIRS
    improved = mean >= MIN_MEAN_IMPROVEMENT
    status = ("PROPOSAL_ELIGIBLE_FOR_INDEPENDENT_REVIEW"
              if enough and improved and not any_regression
              else "INSUFFICIENT_OR_REGRESSIVE_EVIDENCE")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True).encode("utf-8")
    return {
        "schema": RESULT_SCHEMA,
        "experiment_id": experiment_id,
        "task_domain": domain,
        "input_sha256": hashlib.sha256(canonical).hexdigest(),
        "harness2_source_sha": sha,
        "baseline_harness_digest": baseline,
        "candidate_harness_digest": candidate,
        "configuration_digest": cfg,
        "holdout_commitment_digest": holdout,
        "grader_digest": grader,
        "matched_holdout_cases": len(ordered),
        "mean_score_delta": round(mean, 8),
        "any_policy_or_acceptance_or_resource_regression": any_regression,
        "status": status,
        "promotion": "NONE",
        "runtime_authority": "NONE",
        "automatic_agentos_write": False,
        "requires": [
            "existing EVAL evidence-content verification and scorer passes",
            "independent reviewer and genuine held-out provenance",
            "existing Outcome Learning and Agent OS decision/discovery admission",
            "existing release owner and governed reversible deployment",
        ],
        "evidence_limit": "caller-supplied input; no bytes or holdout sealing authenticated",
    }
