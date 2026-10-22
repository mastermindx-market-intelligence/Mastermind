"""Evidence-conditioned risk budget for PBR — SHADOW ONLY (spec §4).

Given one name and one decision, the budget derives an ``eligible_weight`` and
a fully explained five-step waterfall from: the categorical cap in force
(passed in as data — the sizing policy's own numbers are inputs, never
re-declared here), the position role's declared adverse-scenario loss budget,
evidence quality (independent source families, primary-vs-derived mix,
technical coverage, contradicted/unreconciled fact outcomes), and declared
concentration exposure.

Zero-influence rule (spec §4.2, frozen law 11): a stated thesis probability
whose ``calibration_status != "calibrated"`` has ZERO allocation influence —
it enters no waterfall step.  Calibration status is judged against the
de-confidencing-only contract of ``brain/calibration.py`` (a seat needs
``MIN_N`` resolved decisions before its confidence is evidence at all);
``brain/calibration`` is imported read-only for that threshold and for
nothing else.

Boundaries (this wave, seat ruling Q3): nothing here is called from
``brain.decision_submission.normalize``; there is no allocator behaviour
change, no registry membership, no pending-target route and no settlement
call (frozen law 2 isolated shadow, law 23 existing planes stay canonical,
settlement boundary §8.7).  The only I/O is ``load_params(path)`` on an
explicit caller-supplied path — there is no default path; the frozen file is
``config/pbr_shadow_risk_budget.yml`` (``freeze_owner: pbr-seat``).  Output is
a plain dict; it vetoes nothing live.

Blocking fact outcomes (seat ruling Q2): a supporting fact that is
CONTRADICTED, or BASIS_UNRECONCILED against a *qualified* reference mark
(``brain.facts`` owns the typed-mark qualification), multiplies the evidence
step by the configured ``unreconciled_fact_factor`` (0.0) — contradiction is
not averaged away, and the rule is conditional on the recorded evidence, never
on the instrument.
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from brain import facts
from brain.calibration import FLOOR as _CALIBRATION_FLOOR
from brain.calibration import MIN_N as _CALIBRATION_MIN_N

ASSESSMENT_SCHEMA = "pbr.shadow_risk_budget_assessment.v1"
PARAMS_SCHEMA = "pbr.shadow_risk_budget_params.v1"

#: Undeclared roles default to the least-proven role (fail-safe, recorded as an
#: assumption) — an initiation must never be sized on an implicit "established".
DEFAULT_POSITION_ROLE = "starter"

_POSITION_ROLES = ("starter", "established", "risk_reduction")
_PRIMARY_MIXES = ("primary_dominant", "mixed", "derived_only")
_COVERAGE = ("ok", "degraded", "absent")
_SOURCE_FAMILY_KEYS = {"1": "1", "2": "2", "3plus": "3plus"}

_ACTIONS = frozenset(facts.RISK_INCREASING_ACTIONS) | frozenset(
    facts.RISK_NEUTRAL_OR_REDUCING_ACTIONS
)


class ParamsError(ValueError):
    """Invalid or non-frozen parameter file (missing frozen_at, bare justification…)."""


# ─────────────────────────────── parameters ─────────────────────────────────


def _unwrap(node: Any) -> Any:
    """A leaf parameter is ``{value: X, justification: str}``; unwrap to X."""
    if isinstance(node, Mapping) and set(node) >= {"value"} and "justification" in node:
        return node["value"]
    return node


def _pv(params: Mapping, dotted: str) -> Any:
    node: Any = params
    for part in dotted.split("."):
        if not isinstance(node, Mapping) or part not in node:
            raise ParamsError(f"missing parameter {dotted!r} in shadow risk budget config")
        node = node[part]
    return _unwrap(node)


def _check_justifications(node: Any, path: str = "") -> int:
    """Every leaf parameter ({value, justification}) needs a written justification."""
    checked = 0
    if isinstance(node, Mapping):
        if "value" in node:
            justification = node.get("justification")
            if (
                not isinstance(justification, str)
                or len(justification.strip()) < 40
                or " " not in justification.strip()
            ):
                raise ParamsError(
                    f"parameter {path or '<root>'!r} has a missing or bare justification"
                )
            try:
                float(node["value"])
            except (TypeError, ValueError) as exc:
                raise ParamsError(
                    f"parameter {path or '<root>'!r} value must be numeric"
                ) from exc
            return 1
        for key, child in node.items():
            checked += _check_justifications(child, f"{path}.{key}" if path else str(key))
    return checked


def load_params(path: Path) -> dict:
    """Load and validate ``pbr.shadow_risk_budget_params.v1`` from an explicit path.

    Refuses a missing/late ``frozen_at``, a missing ``version``, a missing
    ``freeze_owner``, a schema mismatch, and any parameter with a missing or
    bare justification (spec §4.3 audit mechanism 1 — the config test refuses
    a missing/late ``frozen_at``).
    """
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ParamsError(f"{path}: config must be a mapping")
    if raw.get("schema") != PARAMS_SCHEMA:
        raise ParamsError(f"{path}: schema must be {PARAMS_SCHEMA}")
    version = raw.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ParamsError(f"{path}: version must be a positive integer")
    frozen_at = raw.get("frozen_at")
    if not frozen_at:
        raise ParamsError(f"{path}: frozen_at is required (parameters must be frozen ex ante)")
    if isinstance(frozen_at, str):
        try:
            datetime.fromisoformat(frozen_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ParamsError(f"{path}: frozen_at is not a parseable ISO timestamp") from exc
    else:
        raise ParamsError(f"{path}: frozen_at must be an ISO timestamp string")
    if not str(raw.get("freeze_owner") or "").strip():
        raise ParamsError(f"{path}: freeze_owner is required (who owns the freeze)")
    checked = _check_justifications(raw)
    if checked < 1:
        raise ParamsError(f"{path}: no justified parameters found")
    return dict(raw)


# ──────────────────────────────── input shape ───────────────────────────────


def _num(value: Any, name: str, *, low: float = 0.0, high: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric, got {value!r}") from exc
    if not math.isfinite(number) or number < low - 1e-12 or number > high + 1e-12:
        raise ValueError(f"{name} out of range [{low}, {high}]: {number}")
    return number


def _validated_input(inputs: Mapping) -> dict:
    if not isinstance(inputs, Mapping):
        raise ValueError("inputs must be a mapping")
    out = dict(inputs)
    for key in ("book", "ticker", "action", "categorical_cap", "cap_source"):
        if not out.get(key) and out.get(key) != 0:
            raise ValueError(f"inputs.{key} is required")
    action = str(out["action"]).strip().lower()
    if action not in _ACTIONS:
        raise ValueError(f"unknown action {out['action']!r}; expected one of {sorted(_ACTIONS)}")
    out["action"] = action
    out["categorical_cap"] = _num(out["categorical_cap"], "categorical_cap")
    if not str(out["cap_source"]).strip():
        raise ValueError("cap_source is required (which cap is in force, as data)")
    role = out.get("position_role")
    if role is None:
        out["position_role"] = None
    else:
        role = str(role).strip().lower()
        if role not in _POSITION_ROLES:
            raise ValueError(f"position_role must be one of {_POSITION_ROLES}, got {role!r}")
        out["position_role"] = role
    families = out.get("source_families", 0)
    try:
        families = int(families)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"source_families must be an integer, got {families!r}") from exc
    if families < 0:
        raise ValueError("source_families must be >= 0")
    out["source_families"] = families
    mix = str(out.get("primary_mix") or "derived_only").strip().lower()
    if mix not in _PRIMARY_MIXES:
        raise ValueError(f"primary_mix must be one of {_PRIMARY_MIXES}, got {mix!r}")
    out["primary_mix"] = mix
    coverage = str(out.get("technical_coverage") or "absent").strip().lower()
    if coverage not in _COVERAGE:
        raise ValueError(f"technical_coverage must be one of {_COVERAGE}, got {coverage!r}")
    out["technical_coverage"] = coverage
    out["existing_same_issuer_weight"] = _num(
        out.get("existing_same_issuer_weight", 0.0), "existing_same_issuer_weight"
    )
    out["correlated_event_overlap"] = _num(
        out.get("correlated_event_overlap", 0.0), "correlated_event_overlap"
    )
    probability = out.get("stated_probability")
    if probability is not None:
        if not isinstance(probability, Mapping):
            raise ValueError("stated_probability must be a mapping with value/calibration_status")
        _num(probability.get("value"), "stated_probability.value")
        if not str(probability.get("calibration_status") or "").strip():
            raise ValueError("stated_probability.calibration_status is required")
    outcomes = out.get("fact_outcomes") or ()
    out["fact_outcomes"] = list(outcomes)
    return out


# ─────────────────────────────── waterfall steps ────────────────────────────


def _family_key(source_families: int) -> str:
    if source_families >= 3:
        return "3plus"
    return _SOURCE_FAMILY_KEYS[str(max(1, source_families))]


def _evidence_step(inputs: Mapping, params: Mapping, running: float) -> tuple[dict, list[dict]]:
    drivers: dict[str, Any] = {}
    assumptions: list[dict] = []
    families = int(inputs["source_families"])
    if families == 0:
        assumptions.append(
            {
                "code": "source_families_defaulted_to_one",
                "detail": "no source-family count recorded; treated as one family (heaviest factor)",
            }
        )
    family_key = _family_key(families)
    family_factor = float(_pv(params, f"evidence_multiplier.source_family_factor.{family_key}"))
    mix = inputs["primary_mix"]
    mix_factor = float(_pv(params, f"evidence_multiplier.primary_mix_factor.{mix}"))
    coverage = inputs["technical_coverage"]
    coverage_factor = float(
        _pv(params, f"evidence_multiplier.technical_coverage_factor.{coverage}")
    )
    floor = float(_pv(params, "evidence_multiplier.multiplier_floor"))
    composition = family_factor * mix_factor * coverage_factor
    clamped = max(floor, min(1.0, composition))
    if clamped != composition:
        assumptions.append(
            {
                "code": "composition_multiplier_floored",
                "detail": f"composition multiplier {composition:.6f} floored at {floor}",
            }
        )
    blocking_verdicts = sorted(
        {
            str(outcome.get("verdict"))
            for outcome in inputs["fact_outcomes"]
            if outcome.get("verdict") in facts.BLOCKING_VERDICTS
        }
    )
    # A CONTRADICTED or BASIS_UNRECONCILED supporting fact bypasses the
    # composition floor entirely: the fact factor is a hard zero.
    fact_factor = 0.0 if blocking_verdicts else 1.0
    multiplier = clamped * fact_factor
    drivers.update(
        {
            "source_families": families,
            "source_family_key": family_key,
            "source_family_factor": family_factor,
            "primary_mix": mix,
            "primary_mix_factor": mix_factor,
            "technical_coverage": coverage,
            "technical_coverage_factor": coverage_factor,
            "composition_multiplier": composition,
            "multiplier_floor": floor,
            "blocking_verdicts": blocking_verdicts,
            "fact_factor": fact_factor,
            "unreconciled_fact_factor": float(
                _pv(params, "evidence_multiplier.unreconciled_fact_factor")
            ),
        }
    )
    if blocking_verdicts:
        explanation = (
            "supporting facts carry "
            f"{', '.join(blocking_verdicts)} outcomes: contradiction is not averaged "
            "away, so the evidence step multiplies by zero and no eligible weight "
            "remains for a risk-increasing action (conditional on the recorded "
            "evidence, never on the instrument)"
        )
    else:
        explanation = (
            f"{families} independent source famil"
            f"{'y' if families == 1 else 'ies'} (x{family_factor}), {mix} primary mix "
            f"(x{mix_factor}), {coverage} technical coverage (x{coverage_factor}), "
            f"floored at {floor}: composition multiplier {clamped:.4f}"
        )
    step = {
        "step": "evidence_haircut",
        "value": round(running * multiplier, 6),
        "multiplier": round(multiplier, 6),
        "drivers": drivers,
        "explanation": explanation,
    }
    return step, assumptions


def assess(inputs: Mapping, params: Mapping) -> dict:
    """Return the shadow ``RiskBudgetAssessment`` for one name/decision (spec §4.1).

    Five fully explained steps (categorical cap, role budget, evidence haircut,
    concentration limit, eligible weight) plus recorded assumptions.  The
    eligible weight is the minimum of the step values; the assessment is
    shadow output and vetoes nothing live.
    """
    inp = _validated_input(inputs)
    assumptions: list[dict] = []

    # Step 1 — the categorical cap in force, passed in as data.
    cap = float(inp["categorical_cap"])
    cap_step = {
        "step": "categorical_cap",
        "value": round(cap, 6),
        "source": str(inp["cap_source"]),
        "explanation": (
            "categorical cap in force for this book/conviction, passed in as data "
            "from the sizing policy; never re-declared or recomputed here"
        ),
    }

    # Step 2 — the role's declared adverse-scenario loss budget, converted to a
    # weight ceiling by the single shared stress-move assumption.
    role = inp["position_role"]
    if role is None:
        role = DEFAULT_POSITION_ROLE
        assumptions.append(
            {
                "code": "role_undeclared_defaulted_to_starter",
                "detail": (
                    "position_role not declared; treated as the least-proven role "
                    f"({DEFAULT_POSITION_ROLE!r}) — fail-safe default"
                ),
            }
        )
    loss_budget = float(_pv(params, f"role_loss_budgets.{role}.max_adverse_nav_fraction"))
    stress_move = float(_pv(params, "role_loss_budgets.stress_move_assumption"))
    role_budget = loss_budget / stress_move
    role_step = {
        "step": "role_budget",
        "value": round(role_budget, 6),
        "role": role,
        "declared_loss_budget": loss_budget,
        "stress_move_assumption": stress_move,
        "config_ref": f"role_loss_budgets.{role}.max_adverse_nav_fraction",
        "explanation": (
            f"role {role!r} declares an adverse-scenario loss budget of {loss_budget} "
            f"of portfolio NAV; divided by the shared {stress_move} stress move, the "
            f"weight ceiling is {role_budget:.6f}"
        ),
    }

    running = min(cap, role_budget)

    # Step 3 — evidence haircut (composition drivers, floored; a contradicted or
    # basis-unreconciled supporting fact multiplies by zero).
    evidence_step, evidence_assumptions = _evidence_step(inp, params, running)
    assumptions.extend(evidence_assumptions)

    # Step 4 — declared concentration exposure.
    max_single = float(_pv(params, "concentration.max_single_name_weight"))
    issuer_cap = float(_pv(params, "concentration.same_issuer_total_cap"))
    event_cap = float(_pv(params, "concentration.correlated_event_cap"))
    existing = float(inp["existing_same_issuer_weight"])
    overlap = float(inp["correlated_event_overlap"])
    issuer_room = max(0.0, issuer_cap - existing)
    event_room = max(0.0, event_cap - overlap)
    concentration = min(max_single, issuer_room, event_room)
    concentration_step = {
        "step": "concentration_limit",
        "value": round(concentration, 6),
        "drivers": {
            "max_single_name_weight": max_single,
            "same_issuer_total_cap": issuer_cap,
            "existing_same_issuer_weight": existing,
            "issuer_room": round(issuer_room, 6),
            "correlated_event_cap": event_cap,
            "correlated_event_overlap": overlap,
            "event_room": round(event_room, 6),
        },
        "explanation": (
            f"minimum of the {max_single} single-name ceiling, {issuer_room:.6f} "
            f"remaining room under the {issuer_cap} same-issuer cap and "
            f"{event_room:.6f} remaining room under the {event_cap} correlated-event cap"
        ),
    }

    # Step 5 — eligible weight: the minimum of every predecessor.
    step_values = {
        "categorical_cap": cap_step["value"],
        "role_budget": role_step["value"],
        "evidence_haircut": evidence_step["value"],
        "concentration_limit": concentration_step["value"],
    }
    eligible = round(min(step_values.values()), 6)
    binding = min(
        (name for name, value in step_values.items() if value == min(step_values.values())),
        key=lambda name: list(step_values).index(name),
    )
    eligible_step = {
        "step": "eligible_weight",
        "value": eligible,
        "binding_step": binding,
        "explanation": (
            "minimum of the four predecessor steps; bound by "
            f"{binding!r} at {eligible}"
        ),
    }

    # Zero-influence rule for uncalibrated probabilities (spec §4.2, law 11).
    probability = inp.get("stated_probability")
    if probability is not None:
        status = str(probability["calibration_status"]).strip().lower()
        assumptions.append(
            {
                "code": "stated_probability_zero_influence",
                "detail": (
                    f"stated thesis probability {probability['value']} carried "
                    f"calibration_status {status!r}: it entered no waterfall step. "
                    "Only calibrated probability (per brain/calibration.py's "
                    f"de-confidencing-only contract, MIN_N={_CALIBRATION_MIN_N} resolved "
                    f"decisions, floor {_CALIBRATION_FLOOR}) could ever be considered, "
                    "and no probability input is wired to sizing in this wave"
                ),
            }
        )
        if status == "calibrated":
            assumptions.append(
                {
                    "code": "calibrated_probability_not_wired",
                    "detail": (
                        "calibration status is 'calibrated' but the waterfall consumes no "
                        "probability input in this wave (law 11: no LLM-probability "
                        "sizing authority at birth)"
                    ),
                }
            )
    if not inp["fact_outcomes"]:
        assumptions.append(
            {
                "code": "no_fact_outcomes_supplied",
                "detail": (
                    "no verification outcomes were supplied, so the zeroing "
                    "fact factor could not fire; evidence quality rests on the "
                    "declared composition drivers alone"
                ),
            }
        )

    return {
        "schema": ASSESSMENT_SCHEMA,
        "book": str(inp["book"]),
        "ticker": str(inp["ticker"]),
        "action": inp["action"],
        "position_role": role,
        "eligible_weight": eligible,
        "waterfall": [
            cap_step,
            role_step,
            evidence_step,
            concentration_step,
            eligible_step,
        ],
        "assumptions": assumptions,
        "config_version": params.get("version"),
        "config_frozen_at": params.get("frozen_at"),
        "config_schema": params.get("schema"),
        "live": False,
    }


def summarize_assessments(assessments: Sequence[Mapping]) -> dict:
    """Small helper for shadow reports: per-name eligible weights and binding steps."""
    return {
        str(a.get("ticker")): {
            "eligible_weight": a.get("eligible_weight"),
            "binding_step": (a.get("waterfall") or [{}])[-1].get("binding_step"),
            "config_version": a.get("config_version"),
        }
        for a in (assessments or ())
    }
