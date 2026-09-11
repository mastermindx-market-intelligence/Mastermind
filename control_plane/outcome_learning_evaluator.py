"""Deterministic evaluator for the Outcome Learning V1 (OL-V1) vertical.

Turns one sealed expectation receipt plus its canary request and outcome into a
DESCRIPTIVE_ONLY evaluation, an n=1 non-promoting self-model, and a candidate-only
Agent OS projection. Every derivation below is a pure function of its arguments —
no I/O, no subprocess, no network, no clock read (every ``recorded_at`` is supplied
by the caller) — mirroring the purity law of
:mod:`control_plane.outcome_learning_contracts`.

Interpretive notes (the frozen spec leaves these two shapes undefined; both choices
are conservative re-uses of already-closed vocabulary rather than new invention —
see the runbook's "what this module decided" section and the build packet's
DEVIATIONS for the full rationale):

* ``evaluation.restoration_check`` is a verbatim copy of ``outcome.restoration`` —
  the same four closed keys, cross-validated for equality.
* ``evaluation.realized_consequence`` is exactly ``outcome.effect_state`` — a
  closed-vocabulary restatement, not a new enum.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from control_plane.outcome_learning_contracts import (
    AGENTOS_PROJECTION_SCHEMA,
    EVALUATION_SCHEMA,
    PRIVACY_CLASS,
    SELF_MODEL_SCHEMA,
    OutcomeLearningContractError,
    canonical_digest,
    validate_agentos_projection,
    validate_canary_request,
    validate_evaluation,
    validate_expectation,
    validate_outcome,
    validate_self_model,
)


def evaluate_episode(
    expectation: Mapping[str, Any],
    outcome: Mapping[str, Any],
    request: Mapping[str, Any],
    *,
    recorded_at: str,
) -> dict[str, Any]:
    """Build and validate one ``mastermind.olv1_evaluation.v1`` document."""
    validate_expectation(expectation)
    validate_canary_request(request)
    validate_outcome(outcome, expectation, request)
    if request["operation_key"] != expectation["operation_key"]:
        raise OutcomeLearningContractError(
            "canary request operation_key does not match the expectation"
        )
    if outcome["operation_key"] != expectation["operation_key"]:
        raise OutcomeLearningContractError(
            "outcome operation_key does not match the expectation"
        )

    process_quality = _process_quality(outcome, expectation)
    forecast = _forecast(expectation, outcome)
    assumption_resolutions = _assumption_resolutions(expectation, outcome)
    confounding = _confounding(expectation)

    evaluation = {
        "schema": EVALUATION_SCHEMA,
        "operation_key": expectation["operation_key"],
        "expectation_sealed_hash": expectation["sealed_hash"],
        "outcome_digest": canonical_digest(outcome),
        "process_quality": process_quality,
        "forecast": forecast,
        "realized_consequence": outcome["effect_state"],
        "assumption_resolutions": assumption_resolutions,
        "confounding": confounding,
        "restoration_check": dict(outcome["restoration"]),
        "causal_grade": "DESCRIPTIVE_ONLY",
        "promotion": "NONE",
        "recorded_at": recorded_at,
        "privacy_class": PRIVACY_CLASS,
    }
    validate_evaluation(evaluation, expectation, outcome)
    return evaluation


def _process_quality(
    outcome: Mapping[str, Any], expectation: Mapping[str, Any]
) -> dict[str, bool]:
    """Every field here is RE-DERIVED from evidence the evaluator can independently
    recompute — never trusted verbatim from the outcome, and never true by mere
    absence of contrary evidence.

    A zero-call episode (``NOT_ATTEMPTED`` / ``INVALIDATED_BEFORE_EFFECT``, or an
    ``EFFECT_UNKNOWN`` that failed before any call completed) honestly reads False on
    ``single_apply_single_restore`` and ``readback_after_each_call`` — there is no
    call sequence and no readback to credit.

    Sol REQUEST_REPAIR (BLOCKER F, 2026-09-02): ``sealed_before_effect`` and
    ``effect_owner_revalidated`` are no longer derived from
    ``preflight.head_equals_sealed_commit`` alone — a single boolean the effect edge
    could still overclaim from. Both now additionally require EVERY field of
    ``outcome.effect_edge`` (the Blocker B/C revalidations actually performed —
    request reacquired from the sealed commit, its digest matched, the owner branch
    selector re-run, every binding cross-checked) to be True. An episode whose
    effect-edge receipt is incomplete honestly reads False here, even if
    ``head_equals_sealed_commit`` was True.
    """
    preflight = outcome["preflight"]
    effect_calls = outcome["effect_calls"]
    effect_edge = outcome["effect_edge"]

    recomputed_expectation_content_sha256 = canonical_digest(expectation).removeprefix(
        "sha256:"
    )
    effect_edge_fully_verified = all(effect_edge.values())
    sealed_before_effect = bool(
        preflight["head_equals_sealed_commit"] is True
        and preflight["expectation_content_sha256"] == recomputed_expectation_content_sha256
        and effect_edge_fully_verified
    )
    kinds = [call["kind"] for call in effect_calls]
    single_apply_single_restore = kinds == ["TITLE_APPLY", "TITLE_RESTORE"]
    readback_after_each_call = len(effect_calls) > 0 and all(
        call.get("readback") is not None for call in effect_calls
    )
    no_retry_used = len(kinds) == len(set(kinds))
    effect_owner_revalidated = bool(
        preflight["head_equals_sealed_commit"] is True and effect_edge_fully_verified
    )
    return {
        "sealed_before_effect": sealed_before_effect,
        "single_apply_single_restore": single_apply_single_restore,
        "readback_after_each_call": readback_after_each_call,
        "no_retry_used": no_retry_used,
        "effect_owner_revalidated": effect_owner_revalidated,
    }


# One metric_id -> a deterministic realized-event function of (expectation, outcome).
def _effect_applied_and_restored(outcome: Mapping[str, Any]) -> bool:
    return outcome["effect_state"] == "APPLIED_AND_RESTORED"


def _head_unchanged_through_effect(outcome: Mapping[str, Any]) -> bool:
    return bool(outcome["restoration"]["head_unchanged"])


def _byte_identical_restoration(outcome: Mapping[str, Any]) -> bool:
    return bool(outcome["restoration"]["byte_identical"])


def _effect_calls_exactly_two(outcome: Mapping[str, Any]) -> bool:
    return len(outcome["effect_calls"]) == 2


_REALIZED_FUNCTIONS = {
    "effect_applied_and_restored": _effect_applied_and_restored,
    "head_unchanged_through_effect": _head_unchanged_through_effect,
    "byte_identical_restoration": _byte_identical_restoration,
    "effect_calls_exactly_two": _effect_calls_exactly_two,
}


def _forecast(expectation: Mapping[str, Any], outcome: Mapping[str, Any]) -> list[dict[str, Any]]:
    """A metric is delayed (``realized``/``within_interval``/``brier_score`` all None)
    purely by its own ``horizon == "delayed"`` field — never by a fixed metric-id set,
    so any future metric automatically gets the same honest treatment without a code
    change here.

    Scoring is kind-specific: a probability-kind metric is scored with
    ``brier_score = (estimate - realized) ** 2`` and never carries
    ``within_interval`` (a hit/miss interval framing is incoherent for a point
    probability). A count/duration_seconds metric keeps the interval framing and
    never carries a ``brier_score``.
    """
    entries: list[dict[str, Any]] = []
    for metric in expectation["expectations"]:
        metric_id = metric["metric_id"]
        kind = metric["kind"]
        lower = metric["lower"]
        estimate = metric["estimate"]
        upper = metric["upper"]
        if metric["horizon"] == "delayed":
            entries.append(
                {
                    "metric_id": metric_id,
                    "kind": kind,
                    "estimate": estimate,
                    "lower": lower,
                    "upper": upper,
                    "realized": None,
                    "within_interval": None,
                    "brier_score": None,
                }
            )
            continue
        function = _REALIZED_FUNCTIONS.get(metric_id)
        if function is None:
            raise OutcomeLearningContractError(
                f"no deterministic realized-mapping is defined for metric_id {metric_id!r}"
            )
        realized_bool = function(outcome)
        realized_value = 1.0 if realized_bool else 0.0
        if kind == "probability":
            within_interval = None
            brier_score = (estimate - realized_value) ** 2
        else:
            within_interval = lower <= realized_value <= upper
            brier_score = None
        entries.append(
            {
                "metric_id": metric_id,
                "kind": kind,
                "estimate": estimate,
                "lower": lower,
                "upper": upper,
                "realized": realized_value,
                "within_interval": within_interval,
                "brier_score": brier_score,
            }
        )
    return entries


def _assumption_resolutions(
    expectation: Mapping[str, Any], outcome: Mapping[str, Any]
) -> list[dict[str, Any]]:
    preflight = outcome["preflight"]
    effect_calls = outcome["effect_calls"]
    effect_state = outcome["effect_state"]
    restoration = outcome["restoration"]
    resolutions: list[dict[str, Any]] = []
    for assumption in expectation["assumptions"]:
        assumption_id = assumption["assumption_id"]
        resolution, evidence_refs = _resolve_one_assumption(
            assumption_id,
            preflight=preflight,
            effect_calls=effect_calls,
            effect_state=effect_state,
            restoration=restoration,
        )
        resolutions.append(
            {
                "assumption_id": assumption_id,
                "resolution": resolution,
                "evidence_refs": evidence_refs,
            }
        )
    return resolutions


def _resolve_one_assumption(
    assumption_id: str,
    *,
    preflight: Mapping[str, Any],
    effect_calls: list[Mapping[str, Any]],
    effect_state: str,
    restoration: Mapping[str, Any],
) -> tuple[str, list[str]]:
    if assumption_id == "OLV1-A1":
        held = preflight["head_equals_sealed_commit"] is True
        resolution = "HELD" if held else "FALSIFIED"
        return resolution, ["preflight.head_equals_sealed_commit"]

    if assumption_id == "OLV1-A2":
        if effect_state == "EFFECT_UNKNOWN":
            return "CONFOUNDED", ["outcome.effect_state"]
        if not effect_calls:
            return "NOT_TESTED", ["outcome.effect_calls (empty)"]
        call1 = effect_calls[0]
        matches = (
            call1["readback"]["title_sha256"] == call1["payload_title_sha256"]
            and call1["readback"]["head_sha"] == preflight["sealed_commit_sha"]
        )
        resolution = "HELD" if matches else "FALSIFIED"
        return resolution, ["effect_calls[0].readback"]

    if assumption_id == "OLV1-A3":
        # Keyed on effect_state, NOT on effect_calls emptiness (unlike A2/A4): the
        # restoration block can carry real evidence — a reconciled poststate — even
        # when the apply itself never produced a completed call. A genuinely
        # not-attempted episode (NOT_ATTEMPTED / INVALIDATED_BEFORE_EFFECT) has
        # nothing to test; an EFFECT_UNKNOWN episode always has SOME restoration
        # verdict to report, even if that verdict is "we never observed the poststate
        # at all" (CONFOUNDED).
        if effect_state in {"NOT_ATTEMPTED", "INVALIDATED_BEFORE_EFFECT"}:
            return "NOT_TESTED", [f"outcome.effect_state ({effect_state})"]
        if restoration["poststate_title_sha256"] == "UNOBSERVED":
            # EFFECT_UNKNOWN with no reconciled title at all: genuinely no evidence
            # either way, never a silent HELD or a guessed FALSIFIED.
            return "CONFOUNDED", ["outcome.restoration.poststate_title_sha256 (UNOBSERVED)"]
        resolution = "HELD" if restoration["byte_identical"] else "FALSIFIED"
        evidence = (
            ["outcome.restoration.byte_identical"]
            if effect_state != "EFFECT_UNKNOWN"
            else ["outcome.restoration.byte_identical (reconciled observation)"]
        )
        return resolution, evidence

    if assumption_id == "OLV1-A4":
        if not effect_calls:
            return "NOT_TESTED", ["outcome.effect_calls (empty)"]
        expected_call2_title = preflight["original_title_sha256"]
        all_expected = True
        for call in effect_calls:
            if call["kind"] == "TITLE_APPLY":
                if call["readback"]["title_sha256"] != call["payload_title_sha256"]:
                    all_expected = False
            elif call["kind"] == "TITLE_RESTORE":
                if call["readback"]["title_sha256"] != expected_call2_title:
                    all_expected = False
        resolution = "HELD" if all_expected else "CONFOUNDED"
        return resolution, ["effect_calls[*].readback.title_sha256"]

    if assumption_id == "OLV1-A5":
        # v1's outcome schema does not distinguish a direct PATCH readback from a
        # single reconciliation GET recorded in the same slot — see the module
        # docstring / runbook. Honest ceiling: never independently assessable in v1.
        if not effect_calls:
            return "NOT_TESTED", ["outcome.effect_calls (empty)"]
        return "NOT_TESTED", ["v1 outcome schema cannot distinguish reconciled reads"]

    if assumption_id == "OLV1-A6":
        return "NOT_TESTED", ["no post-episode re-composition in v1"]

    return "UNRESOLVED", ["unrecognized assumption_id; no resolution rule defined"]


def _confounding(expectation: Mapping[str, Any]) -> dict[str, Any]:
    assessed = [
        {
            "confounder": confounder,
            "observed": False,
            "note": "No evidence of this confounder was present in the outcome record.",
        }
        for confounder in expectation["known_confounders"]
    ]
    return {"known_confounders_assessed": assessed, "additional_observed": []}


def build_self_model(
    evaluation: Mapping[str, Any],
    expectation: Mapping[str, Any],
    *,
    recorded_at: str,
) -> dict[str, Any]:
    """Build and validate one ``mastermind.olv1_self_model.v1`` document (n=1)."""
    evaluation_digest = canonical_digest(evaluation)
    context = expectation["context"]
    self_model = {
        "schema": SELF_MODEL_SCHEMA,
        "operation_key": expectation["operation_key"],
        "evaluation_digest": evaluation_digest,
        "sample_size": 1,
        "sample_state": "INSUFFICIENT_SAMPLE",
        "promotion": "NONE",
        "authority": "NONE",
        "universal_score": None,
        "cohort": {
            "decision_class": expectation["decision_kind"],
            "domain": context["program"],
            "ambiguity": context["ambiguity"],
            "blast_radius": "SINGLE_REVERSIBLE_CANARY",
        },
        "observations": [
            {
                "observation_id": "OLV1-OBS-EFFECT-STATE",
                "statement": (
                    "In this single episode, the observed effect state was "
                    f"{evaluation['realized_consequence']}."
                ),
                "basis_refs": [f"evaluation:{evaluation_digest}"],
            },
            {
                "observation_id": "OLV1-OBS-PROCESS-QUALITY",
                "statement": (
                    "In this single episode, every process-quality check evaluated to "
                    f"{all(evaluation['process_quality'].values())}."
                ),
                "basis_refs": [f"evaluation:{evaluation_digest}"],
            },
        ],
        "memory_law": {
            "remembered_action_is_not_authorized_action": True,
            "remembered_success_is_not_current_procedure": True,
            "remembered_tool_sequence_is_not_replayable_effect": True,
        },
        "recorded_at": recorded_at,
        "privacy_class": PRIVACY_CLASS,
    }
    validate_self_model(self_model, evaluation)
    return self_model


def build_agentos_projection(
    evaluation: Mapping[str, Any],
    expectation: Mapping[str, Any],
    outcome: Mapping[str, Any],
    *,
    recorded_at: str,
    key_hint: str,
) -> dict[str, Any]:
    """Build and validate one ``mastermind.olv1_agentos_projection.v1`` document.

    ``key_hint`` identifies the DSC candidate and is supplied by the caller (the CLI
    derives it from ``recorded_at``'s own date) rather than hardcoded here, so this
    module never invents its own notion of "today". The DSC candidate's ``so_what``
    is conditional on the outcome's actual ``effect_state`` — it must never assert a
    successful restoration for an episode that did not confirm one.
    """
    evaluation_digest = canonical_digest(evaluation)
    target_repository = expectation["context"]["repository"]
    effect_state = outcome["effect_state"]

    if effect_state == "APPLIED_AND_RESTORED":
        dsc_so_what = (
            "One reversible, supervised effect can be sealed, applied, and restored "
            "byte-identically with a two-call bound and no retry; this is evidence "
            "toward — not proof of — that pattern for future reversible canaries."
        )
    elif effect_state == "EFFECT_UNKNOWN":
        dsc_so_what = (
            "The episode stopped on an ambiguous effect rather than guessing or "
            "retrying — evidence toward the STOP discipline holding under real "
            "ambiguity, not evidence that any effect was cleanly restored. The "
            "restored state may be unconfirmed; read the outcome's restoration block "
            "before treating the carrying PR as clean."
        )
    else:  # NOT_ATTEMPTED / INVALIDATED_BEFORE_EFFECT
        dsc_so_what = (
            "No effect was attempted this episode; this is evidence only that the "
            "pre-effect refusal path itself fired, not that any effect can be applied "
            "and restored."
        )

    dsc_candidate = _build_candidate(
        kind="DSC_CANDIDATE",
        target_repository=target_repository,
        key_hint=key_hint,
        summary=(
            "OL-V1's single supervised GitHub PR-title canary reached effect_state="
            f"{evaluation['realized_consequence']} with byte-identical restoration="
            f"{evaluation['restoration_check']['byte_identical']}."
        ),
        falsifier=(
            "A second OL-V1-style canary episode on a different PR whose readback does "
            "not match its applied payload, or whose restore leaves the title byte-"
            "different from the original, falsifies generalizing this single result."
        ),
        so_what=dsc_so_what,
    )
    ws_candidate = _build_candidate(
        kind="WS_UPDATE_CANDIDATE",
        target_repository=target_repository,
        key_hint="WS:OUTCOME-LEARNING-POLICY-CALIBRATION",
        summary=(
            "Status note candidate: the OL-V1 n=1 vertical produced one DESCRIPTIVE_ONLY "
            "evaluation with promotion=NONE; WS:OUTCOME-LEARNING-POLICY-CALIBRATION should "
            "record this episode as evidence accrual, not as a policy change."
        ),
        falsifier=(
            "If a workstream owner finds this episode already recorded, or finds the "
            "underlying evaluation digest does not match the cited artifact, this "
            "candidate is stale and should not be applied."
        ),
        so_what=(
            "Keeps the workstream's evidence ledger current without granting any "
            "automatic authority — a human or a separately gauntleted process decides "
            "whether and how to act on it."
        ),
    )

    projection = {
        "schema": AGENTOS_PROJECTION_SCHEMA,
        "operation_key": expectation["operation_key"],
        "evaluation_digest": evaluation_digest,
        "automatic_writes": False,
        "grants_authority": False,
        "candidates": [dsc_candidate, ws_candidate],
        "recorded_at": recorded_at,
        "privacy_class": PRIVACY_CLASS,
    }
    validate_agentos_projection(projection, evaluation)
    return projection


def _build_candidate(
    *,
    kind: str,
    target_repository: str,
    key_hint: str,
    summary: str,
    falsifier: str,
    so_what: str,
) -> dict[str, Any]:
    payload = {
        "kind": kind,
        "target_repository": target_repository,
        "key_hint": key_hint,
        "summary": summary,
        "falsifier": falsifier,
        "so_what": so_what,
    }
    payload_digest = canonical_digest(payload)
    return {**payload, "payload_digest": payload_digest, "status": "CANDIDATE_ONLY"}


__all__ = [
    "evaluate_episode",
    "build_self_model",
    "build_agentos_projection",
]
