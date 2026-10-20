"""Tests for the GLT T14 preregistration card loader and validator.

Every mutation works on an in-memory copy of the frozen card and rehashes it, so
each test isolates one refusal code. No test writes the card file, and no test
reads an outcome, price or return.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
from datetime import date
from pathlib import Path

import pytest

from brain.liquidity_lab import ledger as lab_ledger
from brain.liquidity_lab import preregistration as prereg
from brain.liquidity_lab import target_card as lab_target_card
from brain.liquidity_lab.eventization import EventizationPolicy, event_definition_id

REPO = Path(__file__).resolve().parents[1]
CARD_PATH = REPO / prereg.DEFAULT_CARD_PATH
MODULE_PATH = REPO / "brain" / "liquidity_lab" / "preregistration.py"

FROZEN_CARD_HASH = "da060bf47e8eafc7e94d0cadbb4135c9207a069aad9eef3539ea9d62911d6aee"
FROZEN_EVENT_DEFINITION_ID = "evdef_f559621219beafdebd254b21458f06f97cc98b3566ae6e13a8bc0d5a8cb2eb66"
FROZEN_CARD_SHA256_PREFIX = "9519241fe3105f22"
FROZEN_VALIDATE = (
    "BLANK_RIGHTS:fx_eurusd",
    "BLANK_RIGHTS:fx_usdjpy",
    "BLANK_RIGHTS:spy_total_return_bars",
    "BLANK_RIGHTS:peer_etf_bars_efa_eem_hyg",
    "UNCOVERED_CALENDAR:train",
    "UNCOVERED_CALENDAR:dev",
    "UNCOVERED_CALENDAR:reserved",
)
FEEDING_UNPROVEN = (
    "fx_eurusd",
    "fx_usdjpy",
    "spy_total_return_bars",
    "peer_etf_bars_efa_eem_hyg",
)
WIDE_COVERAGE = (date(2000, 1, 1), date(2030, 12, 31))


@pytest.fixture(scope="module")
def card() -> prereg.PreregistrationCard:
    return prereg.load_card(CARD_PATH)


def _rehash(m: dict) -> dict:
    m["card_hash"] = prereg.card_hash(m)
    return m


def _source(m: dict, source_id: str) -> dict:
    return next(s for s in m["sources"] if s["source_id"] == source_id)


def _cleared(card: prereg.PreregistrationCard) -> dict:
    """The frozen card with the four feeding UNPROVEN rights set to LICENSED, in memory only."""

    m = card.payload
    for source_id in FEEDING_UNPROVEN:
        _source(m, source_id)["rights_state"] = "LICENSED"
    return _rehash(m)


def _regen_trials(m: dict) -> None:
    axes = m["family"]["axes"]
    trials = [f"{o}|h{h}|{c}|{b}" for o in axes["outcomes"] for h in axes["horizons"]
              for c in axes["model_configs"] for b in axes["baselines"]]
    m["family"]["trials"] = trials
    m["family"]["n_trials_total"] = len(trials)


def _set_horizons(m: dict, sensitivity: list[int]) -> None:
    """Move the sensitivity horizons and keep the trial family and looks consistent."""

    primary = m["horizons"]["primary"]
    m["horizons"]["sensitivity"] = list(sensitivity)
    m["family"]["axes"]["horizons"] = [primary, *sensitivity]
    m["family"]["n_horizons"] = 1 + len(sensitivity)
    _regen_trials(m)
    for look in m["reveal"]["looks_declared"]:
        if look["horizons"] != [primary]:
            look["horizons"] = list(sensitivity)


def _structural(m: dict) -> tuple[str, ...]:
    return prereg.structural_refusals(_rehash(m))


# --- frozen card -------------------------------------------------------------------------


def test_frozen_card_structural_refusals_empty(card):
    assert prereg.structural_refusals(card) == ()


def test_frozen_card_validate_exact_tuple(card):
    assert prereg.validate_card(card) == FROZEN_VALIDATE
    assert prereg.reveal_admissible(card) is False


def test_hash_recomputes_equal(card):
    assert prereg.card_hash(card) == "da060bf47e8eafc7e94d0cadbb4135c9207a069aad9eef3539ea9d62911d6aee"
    assert prereg.card_hash(card) == card.payload["card_hash"] == FROZEN_CARD_HASH
    assert prereg.card_hash(card.payload) == FROZEN_CARD_HASH


def test_event_definition_id_matches_policy(card):
    m = card.payload
    policy = EventizationPolicy(**m["event_policy"]["thresholds"])
    assert m["event_definition_id"] == "evdef_f559621219beafdebd254b21458f06f97cc98b3566ae6e13a8bc0d5a8cb2eb66"
    assert event_definition_id(policy) == FROZEN_EVENT_DEFINITION_ID == m["event_definition_id"]


def test_card_version_constant_matches_card(card):
    assert card.payload["card_version"] == prereg.CARD_VERSION


def test_admissible_in_memory_when_rights_and_calendar_cleared(card):
    m = _cleared(card)
    assert prereg.validate_card(m, calendar_coverage=WIDE_COVERAGE) == ()
    assert prereg.reveal_admissible(m, calendar_coverage=WIDE_COVERAGE) is True
    # With the target calendar's real coverage only the calendar gaps remain.
    assert prereg.validate_card(m) == FROZEN_VALIDATE[4:]


# --- C24: rights ---------------------------------------------------------------------------


def test_c24_unproven_feeding_source_blocks(card):
    m = _cleared(card)
    _source(m, "spy_total_return_bars")["rights_state"] = "UNPROVEN"
    _rehash(m)
    assert prereg.validate_card(m, calendar_coverage=WIDE_COVERAGE) == (
        "BLANK_RIGHTS:spy_total_return_bars",)


def test_c24_missing_rights_blocks(card):
    m = _cleared(card)
    del _source(m, "dtwexbgs")["rights_state"]
    _rehash(m)
    assert prereg.validate_card(m, calendar_coverage=WIDE_COVERAGE) == ("BLANK_RIGHTS:dtwexbgs",)


@pytest.mark.parametrize("state", ["PROBABLY_OK", "open", "", None, 1])
def test_c24_invalid_rights_state_blocks(card, state):
    m = _cleared(card)
    _source(m, "fed_rrp")["rights_state"] = state
    _rehash(m)
    assert prereg.validate_card(m, calendar_coverage=WIDE_COVERAGE) == ("BLANK_RIGHTS:fed_rrp",)


def test_c24_unproven_non_feeding_source_does_not_block(card):
    m = _cleared(card)
    hy_oas = _source(m, "hy_oas")
    assert hy_oas["rights_state"] == "UNPROVEN"
    assert hy_oas["feeds_first_outcome"] is False
    assert prereg.validate_card(m, calendar_coverage=WIDE_COVERAGE) == ()


def test_non_pit_feeding_source_blocks(card):
    m = _cleared(card)
    nfci = _source(m, "nfci_anfci")
    assert nfci["register_verdict"] == "excluded"
    nfci["feeds_first_outcome"] = True
    _rehash(m)
    assert prereg.validate_card(m, calendar_coverage=WIDE_COVERAGE) == ("NON_PIT_INPUT:nfci_anfci",)


# --- C24: blank fields ---------------------------------------------------------------------


@pytest.mark.parametrize("blank", [None, "", "  ", [], {}, "TBD", "todo"])
def test_blank_value_is_refused(card, blank):
    m = card.payload
    m["estimand"]["interpretation"] = blank
    assert _structural(m) == ("BLANK_FIELD:estimand.interpretation",)


@pytest.mark.parametrize("path", ["task_id", "margins.error", "returns.claim_disposition",
                                  "power.non_rejection", "paired_population"])
def test_missing_required_key_is_refused(card, path):
    m = card.payload
    *parents, leaf = path.split(".")
    node = m
    for part in parents:
        node = node[part]
    del node[leaf]
    assert _structural(m) == (f"BLANK_FIELD:{path}",)


def test_zero_and_false_are_not_blank(card):
    m = card.payload
    assert m["windows"]["refractory_sessions"] == 0
    m["power"]["declared_underpowered"] = False
    m["windows"]["purge_sessions"] = 0
    m["multiplicity"]["alpha"] = 0.0
    assert _structural(m) == ()


def test_per_item_blank_reports_index(card):
    m = card.payload
    index = next(i for i, s in enumerate(m["sources"]) if s["source_id"] == "fx_eurusd")
    m["sources"][index]["rights_basis"] = ""
    assert _structural(m) == (f"BLANK_FIELD:sources.{index}.rights_basis",)


def test_per_item_blank_on_look_and_baseline(card):
    m = card.payload
    del m["reveal"]["looks_declared"][1]["purpose"]
    m["baselines"][4]["test"] = "TBD"
    assert _structural(m) == ("BLANK_FIELD:baselines.4.test",
                              "BLANK_FIELD:reveal.looks_declared.1.purpose")


def test_blocked_questions_not_required(card):
    m = card.payload
    del m["blocked_questions"]
    assert _structural(m) == ()


# --- POST_SELECTED_LAG -----------------------------------------------------------------------


def test_post_selected_lag_primary_not_in_candidates(card):
    m = card.payload
    m["horizons"]["candidates"] = [5, 60]
    assert _structural(m) == ("POST_SELECTED_LAG",)


def test_post_selected_lag_sensitivity_outside_planning_horizons(card):
    m = card.payload
    assert 120 not in lab_target_card.PLANNING_HORIZONS
    _set_horizons(m, [5, 120])
    assert _structural(m) == ("POST_SELECTED_LAG",)


def test_post_selected_lag_primary_inside_sensitivity(card):
    m = card.payload
    m["horizons"]["sensitivity"] = [5, 20, 60]
    codes = _structural(m)
    assert "POST_SELECTED_LAG" in codes
    # A primary repeated as a sensitivity also breaks the family count; nothing else fires.
    assert set(codes) <= {"POST_SELECTED_LAG", "INCOMPLETE_FAMILY"}


def test_post_selected_lag_undeclared_look_horizon(card):
    m = card.payload
    m["reveal"]["looks_declared"][0]["horizons"] = [10]
    assert _structural(m) == ("POST_SELECTED_LAG",)


def test_post_selected_lag_frozen_after_a_look(card):
    m = card.payload
    m["frozen_at"] = "2026-10-21"
    assert _structural(m) == ("POST_SELECTED_LAG",)


def test_post_selected_lag_unparseable_dates(card):
    m = card.payload
    m["frozen_at"] = "yesterday"
    assert _structural(m) == ("POST_SELECTED_LAG",)
    m = card.payload
    m["reveal"]["looks_declared"][2]["at"] = "soon"
    assert _structural(m) == ("POST_SELECTED_LAG",)


# --- LATE_THRESHOLD ------------------------------------------------------------------------


def test_late_threshold_changed_value(card):
    m = card.payload
    m["event_policy"]["thresholds"]["material_abs_z"] = 1.5
    assert _structural(m) == ("LATE_THRESHOLD",)


def test_late_threshold_missing_event_definition_id(card):
    m = card.payload
    del m["event_definition_id"]
    assert _structural(m) == ("BLANK_FIELD:event_definition_id", "LATE_THRESHOLD")


def test_late_threshold_invalid_threshold_key(card):
    m = card.payload
    m["event_policy"]["thresholds"]["material_z"] = 1.0
    assert _structural(m) == ("LATE_THRESHOLD",)


def test_late_threshold_policy_rejects_values(card):
    m = card.payload
    m["event_policy"]["thresholds"]["reset_abs_z"] = 2.0
    assert _structural(m) == ("LATE_THRESHOLD",)


# --- C17: LEAKED_VALIDATION_RESIDUAL --------------------------------------------------------


def test_c17_dev_starts_before_train_ends(card):
    m = card.payload
    m["windows"]["dev_start"] = "2017-06-01"
    assert _structural(m) == ("LEAKED_VALIDATION_RESIDUAL",)


def test_c17_reserved_overlaps_dev(card):
    m = card.payload
    m["windows"]["reserved_start"] = "2021-06-01"
    assert _structural(m) == ("LEAKED_VALIDATION_RESIDUAL",)


def test_c17_transform_fit_on_dev(card):
    m = card.payload
    m["models"][0]["transforms"][0]["fit_on"] = "dev"
    assert _structural(m) == ("LEAKED_VALIDATION_RESIDUAL",)


def test_c17_baseline_fit_on_full_history(card):
    m = card.payload
    m["baselines"][2]["fit_on"] = "full_history"
    assert _structural(m) == ("LEAKED_VALIDATION_RESIDUAL",)


def test_c17_unparseable_window_counts_as_leaked(card):
    m = card.payload
    m["windows"]["dev_end"] = "end of 2021"
    assert _structural(m) == ("LEAKED_VALIDATION_RESIDUAL",)


# --- C25: INCOMPLETE_FAMILY ----------------------------------------------------------------


def test_c25_trial_dropped(card):
    m = card.payload
    m["family"]["trials"].pop()
    assert _structural(m) == ("INCOMPLETE_FAMILY",)


def test_c25_trial_duplicated(card):
    m = card.payload
    m["family"]["trials"][-1] = m["family"]["trials"][0]
    assert _structural(m) == ("INCOMPLETE_FAMILY",)


def test_c25_n_trials_total_mismatch(card):
    m = card.payload
    m["family"]["n_trials_total"] += 1
    assert _structural(m) == ("INCOMPLETE_FAMILY",)


def test_c25_extra_horizon_on_axis(card):
    m = card.payload
    m["family"]["axes"]["horizons"].append(120)
    assert _structural(m) == ("INCOMPLETE_FAMILY",)


def test_c25_n_models_differs_from_tuning_budget(card):
    m = card.payload
    m["models"][0]["tuning_budget"] -= 1
    assert _structural(m) == ("INCOMPLETE_FAMILY",)


def test_c25_looks_over_budget(card):
    m = card.payload
    m["reveal"]["look_budget"] = len(m["reveal"]["looks_declared"]) - 1
    assert _structural(m) == ("INCOMPLETE_FAMILY",)


@pytest.mark.parametrize("budget", [True, 0, -1, 3.0, "3"])
def test_c25_look_budget_must_be_positive_int(card, budget):
    m = card.payload
    m["reveal"]["look_budget"] = budget
    assert _structural(m) == ("INCOMPLETE_FAMILY",)


# --- custodian, hash, enum, target ------------------------------------------------------------


def test_no_custodian(card):
    m = card.payload
    m["reveal"]["custodian"] = "TrialLedger"
    assert _structural(m) == ("NO_CUSTODIAN",)


def test_forward_ledger_exists():
    assert isinstance(lab_ledger.ForwardLedger, type)
    assert lab_ledger.ForwardLedger.__name__ == prereg.CUSTODIAN


def test_hash_mismatch_without_rehash(card):
    m = card.payload
    m["task_id"] = "T99"
    assert prereg.structural_refusals(m) == ("HASH_MISMATCH",)


def test_invalid_currency_basis(card):
    m = card.payload
    m["first_outcome"]["currency_basis"] = "eur"
    assert _structural(m) == ("INVALID_ENUM:first_outcome.currency_basis",)


def test_ineligible_target_btc(card):
    m = card.payload
    m["first_outcome"]["target_id"] = "btc"
    m["family"]["axes"]["outcomes"] = ["btc"]
    _regen_trials(m)
    assert _structural(m) == ("INELIGIBLE_TARGET",)


def test_ineligible_target_basis_not_allowed(card):
    m = card.payload
    entry = next(e for e in lab_target_card.BROAD_TARGET_CARD_V1.entries if e.target_id == "spy")
    bad = next((b for b in lab_target_card.RETURN_BASES if b not in entry.allowed_bases),
               "not_a_return_basis")
    m["first_outcome"]["return_basis"] = bad
    assert _structural(m) == ("INELIGIBLE_TARGET",)


def test_ineligible_target_not_in_universe(card):
    m = card.payload
    m["universe"]["eligible_target_ids"] = [t for t in m["universe"]["eligible_target_ids"] if t != "spy"]
    assert _structural(m) == ("INELIGIBLE_TARGET",)


# --- robustness and purity -------------------------------------------------------------------


@pytest.mark.parametrize("path, garbage", [
    ("family", "x"),
    ("sources", 3),
    ("models", None),
    ("baselines", {"B1": "train"}),
    ("windows", []),
    ("reveal", "x"),
    ("horizons", 5),
    ("first_outcome", []),
    ("event_policy", 7),
    ("universe", "spy"),
])
def test_structural_refusals_never_raises_on_garbage(card, path, garbage):
    m = card.payload
    m[path] = garbage
    codes = _structural(m)
    assert codes
    assert all(isinstance(c, str) for c in codes)
    assert isinstance(prereg.reveal_blockers(m), tuple)


def test_wrong_list_type_is_refused_as_blank(card):
    m = card.payload
    m["sources"] = 3
    codes = _structural(m)
    assert "BLANK_FIELD:sources" in codes
    assert prereg.reveal_admissible(m, calendar_coverage=WIDE_COVERAGE) is False


def test_structural_refusals_never_raises_on_unserialisable_mapping():
    codes = prereg.structural_refusals({"card_hash": "x", "task_id": object()})
    assert "HASH_MISMATCH" in codes
    assert "BLANK_FIELD:card_version" in codes


def test_load_card_is_frozen(card):
    with pytest.raises(dataclasses.FrozenInstanceError):
        card.canonical = "{}"  # type: ignore[misc]
    payload = card.payload
    payload["task_id"] = "mutated"
    payload["sources"].clear()
    assert card.payload["task_id"] != "mutated"
    assert card.payload["sources"]
    assert prereg.card_hash(card) == FROZEN_CARD_HASH


_FORBIDDEN_MODULES = {"pandas", "pyarrow", "yfinance", "requests"}
_PATH_SUFFIXES = (".json", ".parquet", ".csv", ".feather")


def test_module_has_no_outcome_reader():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in _FORBIDDEN_MODULES, alias.name
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in _FORBIDDEN_MODULES, node.module
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            target = node.func.value
            if node.func.attr == "load" and isinstance(target, ast.Name):
                assert target.id not in {"np", "numpy"}
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
            if "/" in text and text.endswith(_PATH_SUFFIXES):
                assert text.startswith("research/liquidity_transmission/"), text


def test_card_file_unmodified_by_tests():
    before = hashlib.sha256(CARD_PATH.read_bytes()).hexdigest()
    loaded = prereg.load_card(CARD_PATH)
    prereg.structural_refusals(loaded)
    prereg.validate_card(loaded)
    prereg.validate_card(loaded.payload, calendar_coverage=WIDE_COVERAGE)
    prereg.card_hash(loaded)
    after = hashlib.sha256(CARD_PATH.read_bytes()).hexdigest()
    assert before == after
    assert after.startswith(FROZEN_CARD_SHA256_PREFIX)
