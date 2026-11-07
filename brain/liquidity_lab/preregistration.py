"""GLT T14 preregistration card: loader, hash and validator.

This module is pure. Only :func:`load_card` touches the filesystem, and it reads
the card JSON alone. Nothing here reads an outcome, a price, a return or any data
file, so the card can be validated before any look.

Refusals come in two groups.

* :func:`structural_refusals` reports defects of the card itself. A frozen card
  must return an empty tuple.
* :func:`reveal_blockers` reports conditions outside the card that must clear
  before the reveal custodian may run a look: rights that are blank or unproven
  for a source feeding the first outcome, windows outside the target calendar's
  coverage, and feeding sources the register excludes.

Scientific controls enforced here:

* C17 (leaked validation residual): the train, development and reserved windows
  are ordered and disjoint, and every transform and baseline is fit on train only.
* C24 (one outcome, one primary horizon, no blank field, no blank rights): every
  required field is present and non-blank, and an unproven right may not feed the
  outcome.
* C25 (finite family and look budget): the trial family is the full declared
  cartesian product, and the declared looks fit inside a positive look budget.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from brain.liquidity_lab import target_card as _target_card
from brain.liquidity_lab.eventization import EventizationPolicy, event_definition_id

CARD_VERSION = "glt_preregistration_card.v1"
RIGHTS_STATES = frozenset({"OPEN", "LICENSED", "UNPROVEN"})
CURRENCY_BASES = frozenset({"local", "fx", "usd"})
DEFAULT_CARD_PATH = "research/liquidity_transmission/glt_preregistration_card.v1.json"
CUSTODIAN = "ForwardLedger"

REQUIRED_PATHS: tuple[str, ...] = (
    "card_version",
    "task_id",
    "frozen_at",
    "first_outcome.target_id",
    "first_outcome.symbol",
    "first_outcome.return_basis",
    "first_outcome.currency_basis",
    "first_outcome.outcome_variable",
    "first_outcome.selection_reasons",
    "horizons.unit",
    "horizons.candidates",
    "horizons.primary",
    "horizons.sensitivity",
    "horizons.selection_reasons",
    "event_definition_id",
    "event_policy.thresholds",
    "event_policy.event_calendar",
    "event_policy.target_calendar",
    "event_policy.decision_cutoff",
    "event_policy.correction_policy",
    "estimand.predictive",
    "estimand.interpretation",
    "estimand_card_ref.relation_id",
    "estimand_card_ref.identification_status",
    "sources",
    "universe.eligible_target_ids",
    "universe.first_study_target_ids",
    "windows.calendar",
    "windows.train_start",
    "windows.train_end",
    "windows.dev_start",
    "windows.dev_end",
    "windows.reserved_start",
    "windows.reserved_end",
    "windows.purge_sessions",
    "target_rules.anchor_price",
    "target_rules.anchor_rule",
    "target_rules.maturity_rule",
    "target_rules.ambiguous_data_rule",
    "models",
    "baselines",
    "paired_population",
    "coverage_denominator",
    "margins.error",
    "margins.utility",
    "margins.joint_rule",
    "margins.uncertainty_form",
    "power.design",
    "power.declared_underpowered",
    "power.non_rejection",
    "family.axes",
    "family.n_outcomes",
    "family.n_horizons",
    "family.n_models",
    "family.n_baselines",
    "family.n_trials_total",
    "family.trials",
    "multiplicity.rule",
    "multiplicity.alpha",
    "reveal.custodian",
    "reveal.look_budget",
    "reveal.looks_declared",
    "returns.artifact_ids",
    "returns.negative_result_handling",
    "returns.claim_disposition",
    "card_hash",
)

# Per-item required keys for list-of-object fields. ``rights_state`` is checked by
# reveal_blockers, not here, so a card can be structurally complete while its
# rights are still unresolved.
ITEM_REQUIRED_KEYS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("sources", ("source_id", "register_ref", "rights_basis", "register_verdict",
                 "feeds_first_outcome", "used_by")),
    ("models", ("model_id", "family", "transforms", "fit_on_definition", "hyperparameters",
                "tuning_budget", "selection_rule")),
    ("baselines", ("baseline_id", "definition", "inputs", "fit_on", "known_at", "test")),
    ("reveal.looks_declared", ("look_id", "at", "window", "horizons", "purpose")),
)

_LIST_OF_OBJECT_PATHS = frozenset(path for path, _ in ITEM_REQUIRED_KEYS)
_BLANK_TOKENS = frozenset({"TBD", "TODO"})
_WINDOWS = ("train", "dev", "reserved")


class _Missing:
    __slots__ = ()

    def __repr__(self) -> str:
        return "<missing>"


_MISSING = _Missing()


def canonical_json(mapping: Any) -> str:
    """Canonical JSON text: sorted keys, compact separators, UTF-8 preserved."""

    return json.dumps(mapping, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class PreregistrationCard:
    """Immutable card held as canonical JSON of the full mapping, card_hash included."""

    canonical: str

    @property
    def payload(self) -> dict[str, Any]:
        """A fresh copy of the card mapping on every call."""

        return json.loads(self.canonical)

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> PreregistrationCard:
        if not isinstance(mapping, Mapping):
            raise TypeError("a preregistration card must be a mapping")
        return cls(canonical=canonical_json(dict(mapping)))


def load_card(path: str | Path = DEFAULT_CARD_PATH) -> PreregistrationCard:
    """Read the card JSON. This is the only function in the module that does I/O."""

    return PreregistrationCard.from_mapping(json.loads(Path(path).read_text(encoding="utf-8")))


def _as_mapping(card: Any) -> Mapping[str, Any]:
    if isinstance(card, PreregistrationCard):
        return card.payload
    if isinstance(card, Mapping):
        return card
    raise TypeError("expected a PreregistrationCard or a mapping")


def card_hash(card_or_mapping: Any) -> str:
    """sha256 hex of the canonical JSON of the card without its top-level card_hash."""

    mapping = _as_mapping(card_or_mapping)
    body = {k: v for k, v in mapping.items() if k != "card_hash"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def _get(mapping: Any, path: str) -> Any:
    node = mapping
    for part in path.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return _MISSING
        node = node[part]
    return node


def _is_blank(value: Any) -> bool:
    if value is _MISSING or value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip()
        return stripped == "" or stripped.upper() in _BLANK_TOKENS
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _int_list(value: Any) -> list[int] | None:
    if not isinstance(value, list) or not all(_is_int(x) for x in value):
        return None
    return list(value)


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _dict_items(value: Any) -> list[Mapping[str, Any]] | None:
    if not isinstance(value, list) or not all(isinstance(x, Mapping) for x in value):
        return None
    return list(value)


def _blank_fields(m: Mapping[str, Any]) -> list[str]:
    codes: list[str] = []
    for path in REQUIRED_PATHS:
        value = _get(m, path)
        if _is_blank(value) or (path in _LIST_OF_OBJECT_PATHS and not isinstance(value, list)):
            codes.append(f"BLANK_FIELD:{path}")
    for path, keys in ITEM_REQUIRED_KEYS:
        items = _get(m, path)
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            for key in keys:
                value = item.get(key, _MISSING) if isinstance(item, Mapping) else _MISSING
                if _is_blank(value):
                    codes.append(f"BLANK_FIELD:{path}.{index}.{key}")
    return codes


def _invalid_enum(m: Mapping[str, Any]) -> bool:
    basis = _get(m, "first_outcome.currency_basis")
    if _is_blank(basis):
        return False
    return not isinstance(basis, str) or basis not in CURRENCY_BASES


def _ineligible_target(m: Mapping[str, Any]) -> bool:
    target_id = _get(m, "first_outcome.target_id")
    return_basis = _get(m, "first_outcome.return_basis")
    eligible = _get(m, "universe.eligible_target_ids")
    if not isinstance(target_id, str) or not isinstance(eligible, list):
        return True
    entries = {entry.target_id: entry for entry in _target_card.BROAD_TARGET_CARD_V1.entries}
    excluded = {target for target, _reason in _target_card.EXCLUDED}
    entry = entries.get(target_id)
    if entry is None or target_id in excluded or target_id not in eligible:
        return True
    return not isinstance(return_basis, str) or return_basis not in entry.allowed_bases


def _post_selected_lag(m: Mapping[str, Any]) -> bool:
    planning = set(_target_card.PLANNING_HORIZONS)
    primary = _get(m, "horizons.primary")
    candidates = _int_list(_get(m, "horizons.candidates"))
    sensitivity = _int_list(_get(m, "horizons.sensitivity"))
    if not _is_int(primary) or candidates is None or sensitivity is None:
        return True
    if primary not in candidates or primary not in planning:
        return True
    if any(h not in planning for h in sensitivity) or primary in sensitivity:
        return True
    looks = _dict_items(_get(m, "reveal.looks_declared"))
    if looks is None:
        return True
    declared = {primary, *sensitivity}
    frozen_at = _parse_date(m.get("frozen_at"))
    if frozen_at is None:
        return True
    for look in looks:
        look_horizons = _int_list(look.get("horizons"))
        if look_horizons is None or not set(look_horizons) <= declared:
            return True
        at = _parse_date(look.get("at"))
        if at is None or frozen_at > at:
            return True
    return False


def _late_threshold(m: Mapping[str, Any]) -> bool:
    stored = m.get("event_definition_id", _MISSING)
    if _is_blank(stored) or not isinstance(stored, str):
        return True
    thresholds = _get(m, "event_policy.thresholds")
    if not isinstance(thresholds, Mapping):
        return True
    try:
        policy = EventizationPolicy(**thresholds)
        computed = event_definition_id(policy)
    except Exception:
        return True
    return computed != stored


def _leaked_validation_residual(m: Mapping[str, Any]) -> bool:
    bounds = [_parse_date(_get(m, f"windows.{name}_{edge}"))
              for name in _WINDOWS for edge in ("start", "end")]
    if any(b is None for b in bounds):
        return True
    _train_start, train_end, dev_start, dev_end, reserved_start, reserved_end = bounds
    if not (train_end < dev_start <= dev_end < reserved_start <= reserved_end):
        return True
    models = _dict_items(_get(m, "models"))
    baselines = _dict_items(_get(m, "baselines"))
    if models is None or baselines is None:
        return True
    for model in models:
        transforms = _dict_items(model.get("transforms"))
        if transforms is None or any(t.get("fit_on") != "train" for t in transforms):
            return True
    return any(b.get("fit_on") != "train" for b in baselines)


def _incomplete_family(m: Mapping[str, Any]) -> bool:
    family = _get(m, "family")
    axes = _get(m, "family.axes")
    if not isinstance(family, Mapping) or not isinstance(axes, Mapping):
        return True
    counts = [family.get(k) for k in ("n_outcomes", "n_horizons", "n_models", "n_baselines",
                                      "n_trials_total")]
    if not all(_is_int(c) for c in counts):
        return True
    n_outcomes, n_horizons, n_models, n_baselines, n_trials_total = counts
    trials = family.get("trials")
    if not isinstance(trials, list) or not all(isinstance(t, str) for t in trials):
        return True
    outcomes = axes.get("outcomes")
    model_configs = axes.get("model_configs")
    axis_baselines = axes.get("baselines")
    axis_horizons = _int_list(axes.get("horizons"))
    if (axis_horizons is None
            or not isinstance(outcomes, list) or not all(isinstance(o, str) for o in outcomes)
            or not isinstance(model_configs, list) or not all(isinstance(c, str) for c in model_configs)
            or not isinstance(axis_baselines, list) or not all(isinstance(b, str) for b in axis_baselines)):
        return True
    if n_outcomes * n_horizons * n_models * n_baselines != n_trials_total:
        return True
    if len(trials) != n_trials_total or len(trials) != len(set(trials)):
        return True
    expected = {f"{o}|h{h}|{c}|{b}" for o in outcomes for h in axis_horizons
                for c in model_configs for b in axis_baselines}
    if set(trials) != expected:
        return True
    primary = _get(m, "horizons.primary")
    sensitivity = _int_list(_get(m, "horizons.sensitivity"))
    if not _is_int(primary) or sensitivity is None:
        return True
    if n_horizons != 1 + len(sensitivity) or set(axis_horizons) != {primary, *sensitivity}:
        return True
    models = _dict_items(_get(m, "models"))
    if models is None or not all(_is_int(x.get("tuning_budget")) for x in models):
        return True
    if n_models != sum(x["tuning_budget"] for x in models) or n_models != len(model_configs):
        return True
    baselines = _get(m, "baselines")
    if not isinstance(baselines, list):
        return True
    if n_baselines != len(baselines) or n_baselines != len(axis_baselines):
        return True
    if outcomes != [_get(m, "first_outcome.target_id")] or n_outcomes != len(outcomes):
        return True
    look_budget = _get(m, "reveal.look_budget")
    looks = _get(m, "reveal.looks_declared")
    if not _is_int(look_budget) or look_budget <= 0 or not isinstance(looks, list):
        return True
    return len(looks) > look_budget


def _no_custodian(m: Mapping[str, Any]) -> bool:
    return _get(m, "reveal.custodian") != CUSTODIAN


def _hash_mismatch(m: Mapping[str, Any]) -> bool:
    try:
        return card_hash(m) != m.get("card_hash")
    except Exception:
        return True


_STRUCTURAL_CHECKS = (
    ("INVALID_ENUM:first_outcome.currency_basis", _invalid_enum),
    ("INELIGIBLE_TARGET", _ineligible_target),
    ("POST_SELECTED_LAG", _post_selected_lag),
    ("LATE_THRESHOLD", _late_threshold),
    ("LEAKED_VALIDATION_RESIDUAL", _leaked_validation_residual),
    ("INCOMPLETE_FAMILY", _incomplete_family),
    ("NO_CUSTODIAN", _no_custodian),
    ("HASH_MISMATCH", _hash_mismatch),
)


def structural_refusals(card: Any) -> tuple[str, ...]:
    """Defects of the card itself, in the fixed code order. Never raises on a mapping.

    A check that meets a value of the wrong type reports its own code instead of
    raising, because a malformed field cannot satisfy the control it carries.
    """

    m = _as_mapping(card)
    codes = _blank_fields(m)
    for code, check in _STRUCTURAL_CHECKS:
        try:
            failed = check(m)
        except Exception:
            failed = True
        if failed:
            codes.append(code)
    return tuple(codes)


def _feeds(source: Mapping[str, Any]) -> bool:
    # Fail closed: only an explicit False marks a source as not feeding the outcome.
    return source.get("feeds_first_outcome") is not False


def _source_label(source: Any, index: int) -> str:
    if isinstance(source, Mapping):
        source_id = source.get("source_id")
        if isinstance(source_id, str) and not _is_blank(source_id):
            return source_id
    return f"#{index}"


def _check_coverage(calendar_coverage: Any) -> tuple[date, date]:
    if (not isinstance(calendar_coverage, tuple) or len(calendar_coverage) != 2
            or not all(isinstance(d, date) for d in calendar_coverage)):
        raise TypeError("calendar_coverage must be a (date, date) tuple")
    return calendar_coverage[0], calendar_coverage[1]


def reveal_blockers(card: Any, *,
                    calendar_coverage: tuple[date, date] = _target_card.CALENDAR_COVERAGE,
                    ) -> tuple[str, ...]:
    """Conditions outside the card that must clear before any look."""

    m = _as_mapping(card)
    low, high = _check_coverage(calendar_coverage)
    sources = m.get("sources")
    sources = list(enumerate(sources)) if isinstance(sources, list) else []
    codes: list[str] = []
    for index, source in sources:
        if not isinstance(source, Mapping):
            codes.append(f"BLANK_RIGHTS:{_source_label(source, index)}")
            continue
        state = source.get("rights_state")
        invalid = _is_blank(state) or not isinstance(state, str) or state not in RIGHTS_STATES
        if invalid or (state == "UNPROVEN" and _feeds(source)):
            codes.append(f"BLANK_RIGHTS:{_source_label(source, index)}")
    for name in _WINDOWS:
        start = _parse_date(_get(m, f"windows.{name}_start"))
        end = _parse_date(_get(m, f"windows.{name}_end"))
        if start is None or end is None or not (low <= start <= high and low <= end <= high):
            codes.append(f"UNCOVERED_CALENDAR:{name}")
    for index, source in sources:
        if isinstance(source, Mapping) and _feeds(source) and source.get("register_verdict") == "excluded":
            codes.append(f"NON_PIT_INPUT:{_source_label(source, index)}")
    return tuple(codes)


def validate_card(card: Any, *,
                  calendar_coverage: tuple[date, date] = _target_card.CALENDAR_COVERAGE,
                  ) -> tuple[str, ...]:
    """Structural refusals followed by reveal blockers."""

    return structural_refusals(card) + reveal_blockers(card, calendar_coverage=calendar_coverage)


def reveal_admissible(card: Any, *,
                      calendar_coverage: tuple[date, date] = _target_card.CALENDAR_COVERAGE,
                      ) -> bool:
    """True only when the card has no structural refusal and no reveal blocker."""

    return validate_card(card, calendar_coverage=calendar_coverage) == ()
