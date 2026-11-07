"""T13: the GLT estimand/identification card is frozen, association-only and outcome-free."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

from brain.liquidity_lab.contracts import canonical_hash
from brain.liquidity_lab.target_card import (
    BROAD_TARGET_CARD_V1,
    BROAD_TARGET_CARD_V1_SHA256,
    CARD_VERSION,
    V1_FROZEN_AT,
)

ROOT = Path(__file__).resolve().parents[1]
CARD_PATH = ROOT / "research" / "liquidity_transmission" / "glt_estimand_card.v1.json"
SIX_FALSIFIERS = (
    "anticipation",
    "reverse_policy_reaction",
    "common_risk_factor",
    "mechanical_target_overlap",
    "placebo_leads",
    "weak_instrument",
)
FUNDING_COMPONENTS = frozenset({"broad_dollar", "real_yield_10y", "high_yield_oas"})
FUNDING_FAMILY_TARGETS = frozenset({
    "tlt", "hyg", "lqd", "gld", "slv", "dbc", "uso", "cper", "efa", "eem", "fxi", "mchi", "kweb",
})
ASSOCIATION_STATUSES = frozenset({"association_only", "NOT_IDENTIFIED"})
NON_EXOGENOUS = (
    "ols_residual",
    "eventization_threshold_crossing",
    "causal_orthogonal_residual",
    "significant_response_curve_cell",
)
FORBIDDEN_KEY = re.compile(r"probability|alpha|score", re.IGNORECASE)


def _card() -> dict:
    return json.loads(CARD_PATH.read_text(encoding="utf-8"))


def _status_is_lawful(card: dict) -> bool:
    """association_only / NOT_IDENTIFIED, or anything else only with a receipt object."""
    if card.get("identification_status") in ASSOCIATION_STATUSES:
        return True
    receipt = card.get("identification_receipt")
    return isinstance(receipt, dict) and bool(receipt)


def _walk_keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _walk_keys(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_keys(value)


def _walk_values(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from _walk_values(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_values(value)
    else:
        yield node


def _ids(entries: list[dict]) -> list[str]:
    return [entry["id"] for entry in entries]


def test_card_parses_and_is_a_frozen_unvalidated_research_card():
    card = _card()
    assert card["card_version"] == "glt_estimand_card.v1"
    assert card["relation_id"] == "glt_rel_monetary_impulse_to_broad_targets.v1"
    assert date.fromisoformat(card["frozen_at"]) == V1_FROZEN_AT
    assert card["validated"] is False
    assert card["evidence_tier"] == "research_measurement_only"
    assert card["identification_status"] == "association_only"
    assert isinstance(card["abstention_reason"], str) and card["abstention_reason"].strip()


def test_identification_status_needs_a_receipt_unless_association_only():
    card = _card()
    assert "identification_receipt" not in card
    assert _status_is_lawful(card)
    promoted = {**card, "identification_status": "identified"}
    assert not _status_is_lawful(promoted)
    assert _status_is_lawful({**promoted, "identification_receipt": {"receipt_id": "r1", "method": "m"}})
    assert not _status_is_lawful({**promoted, "identification_receipt": "r1"})
    assert not _status_is_lawful({**promoted, "identification_receipt": {}})
    assert _status_is_lawful({**card, "identification_status": "NOT_IDENTIFIED"})
    assert card["treatment"]["identification_status"] == "NOT_IDENTIFIED"


def test_forbidden_controls_never_appear_among_confounders():
    card = _card()
    lists = {name: card[name] for name in ("confounders", "mediators", "colliders", "forbidden_controls")}
    for name, entries in lists.items():
        assert entries, name
        ids = _ids(entries)
        assert len(ids) == len(set(ids)), f"duplicate id in {name}"
    confounders = set(_ids(lists["confounders"]))
    mediators = set(_ids(lists["mediators"]))
    colliders = set(_ids(lists["colliders"]))
    forbidden = set(_ids(lists["forbidden_controls"]))
    assert confounders & forbidden == set()
    assert mediators <= forbidden
    assert colliders <= forbidden
    for confounder in lists["confounders"]:
        assert confounder["timing"] == "pre_treatment"
        assert confounder["id"].startswith("lagged_")
    for entry in lists["forbidden_controls"]:
        applies_to = entry["applies_to"]
        assert isinstance(applies_to, list) and applies_to
        assert set(applies_to) <= {"predictive", "causal"}


def test_every_funding_family_target_leaves_its_family_out():
    card = _card()
    targets = card["outcome_family"]["targets"]
    for target in targets:
        families = set(target["overlap_families"])
        assert families <= FUNDING_COMPONENTS
        assert target["leave_target_family_out"] is bool(families & FUNDING_COMPONENTS)
        if target["asset_class"] == "us_equity":
            assert target["leave_target_family_out"] is False
    left_out = {target["target_id"] for target in targets if target["leave_target_family_out"] is True}
    assert left_out == FUNDING_FAMILY_TARGETS


def test_all_six_falsifiers_are_declared_in_order():
    card = _card()
    assert tuple(falsifier["id"] for falsifier in card["falsifiers"]) == SIX_FALSIFIERS
    for falsifier in card["falsifiers"]:
        for field in ("threat", "test", "refutes"):
            assert isinstance(falsifier[field], str) and falsifier[field].strip(), (falsifier["id"], field)


def test_no_field_is_named_probability_alpha_or_score():
    assert [key for key in _walk_keys(_card()) if FORBIDDEN_KEY.search(key)] == []


def test_card_hash_pins_the_frozen_broad_target_card():
    card = _card()
    assert (
        card["card_hash"]
        == card["outcome_family"]["target_card_sha256"]
        == BROAD_TARGET_CARD_V1_SHA256
        == canonical_hash(BROAD_TARGET_CARD_V1.to_dict())
    )
    assert card["outcome_family"]["card"] == "BROAD_TARGET_CARD_V1"
    assert card["outcome_family"]["target_card_version"] == CARD_VERSION


def test_outcome_family_matches_the_card_entries_and_planning_horizons():
    card = _card()
    targets = card["outcome_family"]["targets"]
    assert [(t["target_id"], t["asset_class"]) for t in targets] == [
        (entry.target_id, entry.asset_class) for entry in BROAD_TARGET_CARD_V1.entries
    ]
    target_ids = {t["target_id"] for t in targets}
    assert "btc" not in target_ids and "baba" not in target_ids
    planning = BROAD_TARGET_CARD_V1.to_dict()["horizon_roles"]["planning_candidates"]
    assert set(card["outcome_family"]["planning_horizons_bdays"]) <= set(planning)
    assert card["outcome_family"]["primary_horizon_bdays"] is None


def test_treatment_cites_t04_t05_by_path_at_sha():
    treatment = _card()["treatment"]
    commit = treatment["source_commit"]["commit"]
    assert re.fullmatch(r"[0-9a-f]{40}", commit)
    sources = {source["role"]: source for source in treatment["sources"]}
    assert len(sources) == len(treatment["sources"])
    assert set(sources) == {"producer", "T04_accounting", "T05_knowledge_time", "config"}
    for source in treatment["sources"]:
        assert source["ref"] == f'{source["path"]}@{commit}'
        assert re.fullmatch(r"[0-9a-f]{40}", source["blob"])
    assert "decompose_fx_change" in sources["T04_accounting"]["symbols"]
    assert "eligible_as_of" in sources["T05_knowledge_time"]["symbols"]
    assert "causal_orthogonal_residual" in sources["producer"]["symbols"]
    assert treatment["shock_class"] == "observed_state_change"


def test_predictive_and_causal_estimands_are_separate_and_causal_is_not_estimable():
    estimands = _card()["estimands"]
    assert set(estimands) == {"predictive", "causal"}
    assert estimands["predictive"]["id"] != estimands["causal"]["id"]
    assert estimands["causal"]["estimable"] is False
    assert "identification_receipt" in estimands["causal"]["requires"]


def test_record_names_why_four_constructions_are_not_exogenous_shocks():
    constructions = _card()["non_exogenous_constructions"]
    assert tuple(entry["id"] for entry in constructions) == NON_EXOGENOUS
    for entry in constructions:
        for field in ("where", "why_not_exogenous"):
            assert isinstance(entry[field], str) and entry[field].strip(), (entry["id"], field)


def test_card_carries_no_estimate_or_outcome_number():
    # Integers such as horizons and the PR number are allowed; any float would be an estimate or outcome.
    assert [value for value in _walk_values(_card()) if isinstance(value, float)] == []


def test_exclusion_assumptions_are_not_claimed_to_hold():
    assumptions = _card()["exclusion_assumptions"]
    assert assumptions
    for assumption in assumptions:
        assert assumption["status"] in {"not_defended", "violated_by_measurement_construction"}, assumption["id"]
