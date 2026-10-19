"""GLT T17: causal identification receipts and a separately labelled causal estimate.

Measurement only.  NOT_IDENTIFIED is the default and the only state the real
data can reach today.  The module adds three things and changes nothing that
already exists:

* the frozen identification card (``glt_identification_card.v1.json``),
  loaded by ``load_identification_card`` and checked by
  ``validate_identification_card``.  The card fixes relevance, anticipation,
  pre-trend, reverse-response, placebo, confounding-news and exclusion rules
  before any fit; its ``definition_hash`` binds every field but itself and its
  ``forbidden_controls`` must equal the estimand card's, byte for byte;
* ``qualify_identification``, which reads only the instrument panel, the
  announcement calendar and pre-announcement outcome windows, and returns an
  ``IdentificationReceipt`` listing EVERY failure.  A missing input is a failure
  code.  Any outcome row at or after the announcement is an outcome-firewall
  breach, and any row reaching the preregistration card's reserved window
  raises ``ReservedWindowTouched`` after the guard counts the refusal;
* ``causal_response``, which refuses (``IdentificationRequired``) without an
  identified receipt whose hashes match the card, and otherwise returns a
  ``CausalEstimateCard`` labelled ``identified_causal_for_context``.  That card
  is a different class from the T16 ``ResponseEvidenceProjection``: it carries no
  projection field names and offers no conversion.  T16's predictive claims stay
  ``NOT_IDENTIFIED`` whatever this module returns.

A residual, a threshold crossing or an orthogonalised series never implies
exogeneity (C20): a candidate whose announcement type names one of the estimand
card's ``non_exogenous_constructions`` is refused, and only the two instrument
shock classes of the eventization vocabulary may be qualified.

GAP (receipt interface): T16 exposes no hook that accepts a receipt and T11's
eventization label checks only the receipt's shape.  ``IdentificationReceipt.
label_receipt`` supplies that shape for an identified receipt; binding the label
to a verified receipt is future work for the eventization owner.

Statistical tests use the Macro HAC judge ``engine.validation.newey_west_tstat``
(or an injected judge with the same call shape) and the Macro BH judge through
``apply_bh_fdr``.  When the Macro judge is absent the dependency is quoted
verbatim and the affected test is UNTESTED, never passed.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from brain.liquidity_lab.contracts import HORIZONS_BDAYS, ContractError
from brain.liquidity_lab.estimator import ForwardReturnObservation
from brain.liquidity_lab.eventization import NOT_IDENTIFIED, SHOCK_CLASSES
from brain.liquidity_lab.preregistration import canonical_json
from brain.liquidity_lab.preregistration import card_hash as preregistration_card_hash
from brain.liquidity_lab.response_path import LocalProjectionChallenger
from brain.liquidity_lab.validation import StatisticalDependencyUnavailable, apply_bh_fdr
from brain.liquidity_lab.window_guard import ReservedWindowTouched, WindowGuard

CARD_VERSION = "glt_identification_card.v1"
DEFAULT_CARD_PATH = "research/liquidity_transmission/glt_identification_card.v1.json"
IDENTIFIED_FOR_CONTEXT = "IDENTIFIED_FOR_CONTEXT"
RECEIPT_STATUSES = (IDENTIFIED_FOR_CONTEXT, NOT_IDENTIFIED)
CAUSAL_LABEL = "identified_causal_for_context"
CAUSAL_EVIDENCE_TIER = "identified_causal (context-bound)"
RECEIPT_METHOD = "external_instrument_reduced_form_and_iv_ratio"
RIGHTS_PROVEN = "RIGHTS_PROVEN"
POINT_IN_TIME_CLOCK = "first_system_known"
INFORMATION_PURGED_SUFFIX = "_information_purged"
SAME_EVENT_RULES = ("never_counts", "counts_unless_information_purged")

# The two eventization shock classes that can name an outside instrument.  The
# eventization identified class is reached only through a receipt (label_receipt).
INSTRUMENT_SHOCK_CLASSES = ("forecast_innovation", "policy_announcement_surprise")
assert set(INSTRUMENT_SHOCK_CLASSES) <= set(SHOCK_CLASSES)

# Condition keys carried by outcome-frame rows.
EVENT_KEY = "event_id"
WINDOW_KEY = "window"
INSTRUMENT_KEY = "instrument_surprise"
TREATMENT_KEY = "instrument_treatment"
ANTICIPATION_WINDOW = "anticipation"
PRE_TREND_WINDOW = "pre_trend"
REACTION_WINDOW = "reaction_lookback"
PRE_ANNOUNCEMENT_WINDOWS = (ANTICIPATION_WINDOW, PRE_TREND_WINDOW, REACTION_WINDOW)

HAC_DEPENDENCY_MESSAGE = "engine.validation.newey_west_tstat is required for T17 identification tests"

_REQUIRED_PATHS = (
    "card_version",
    "task_id",
    "frozen_at",
    "relation_id",
    "estimand_card_ref.path",
    "estimand_card_ref.card_hash",
    "preregistration_card_ref.path",
    "preregistration_card_ref.card_hash",
    "event_definition_id",
    "shock_class",
    "relevance_rule.statistic",
    "relevance_rule.min_value",
    "relevance_rule.hac_lags",
    "relevance_rule.min_thinned_events",
    "anticipation_rule.window_sessions_before",
    "anticipation_rule.max_abs_t",
    "pre_trend_rule.sessions",
    "pre_trend_rule.max_abs_t",
    "reverse_response_rule.lookback_sessions",
    "reverse_response_rule.max_abs_t",
    "placebo_design.n_placebo_dates",
    "placebo_design.seed",
    "placebo_design.level",
    "placebo_design.pool_window.start",
    "placebo_design.pool_window.end",
    "placebo_design.min_weekdays_from_event",
    "inference_rule.interval_level",
    "confounding_news_exclusions",
    "forbidden_controls",
    "admissible_specifications",
    "outcome_firewall.reserved_start",
    "outcome_firewall.rule",
    "definition_hash",
)
_POSITIVE_THRESHOLDS = (
    "relevance_rule.min_value",
    "anticipation_rule.max_abs_t",
    "pre_trend_rule.max_abs_t",
    "reverse_response_rule.max_abs_t",
)
_POSITIVE_INTEGERS = (
    "relevance_rule.hac_lags",
    "relevance_rule.min_thinned_events",
    "anticipation_rule.window_sessions_before",
    "pre_trend_rule.sessions",
    "reverse_response_rule.lookback_sessions",
)
_CANDIDATE_KEYS = ("instrument_id", "rights_state", "clock_rule", "announcement_type")
_EXCLUSION_KEYS = ("class", "weekdays_before", "weekdays_after", "same_event_rule")
_MISSING = object()


class IdentificationRequired(ContractError):
    """A causal estimate was requested without an identified, hash-matched receipt."""


# --------------------------------------------------------------------- inputs
@dataclass(frozen=True, slots=True)
class InstrumentObservation:
    """One announcement-level instrument value, first known at ``known_at``."""

    instrument_id: str
    event_id: str
    session: date
    known_at: datetime
    surprise: float
    treatment: float
    announcement_type: str


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    """One dated announcement used only for confounding-news exclusion."""

    event_id: str
    event_class: str
    session: date


@dataclass(frozen=True, slots=True)
class TestResult:
    """One named identification test with its statistic, threshold and verdict."""

    __test__ = False  # not a pytest class

    name: str
    statistic: str
    value: float | None
    threshold: float | None
    passed: bool


# ----------------------------------------------------------------------- card
def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def identification_definition_hash(document: Mapping[str, Any]) -> str:
    """sha256 of the canonical JSON of every card field except ``definition_hash``."""

    body = {key: value for key, value in document.items() if key != "definition_hash"}
    return _sha256(canonical_json(body).encode("utf-8"))


@dataclass(frozen=True)
class IdentificationCard:
    """Immutable identification card plus the estimand and preregistration cards it binds."""

    canonical: str
    estimand_canonical: str
    estimand_sha256: str
    preregistration_canonical: str
    preregistration_file_sha256: str
    source_path: str | None = None

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self.canonical)

    @property
    def estimand(self) -> dict[str, Any]:
        return json.loads(self.estimand_canonical)

    @property
    def preregistration(self) -> dict[str, Any]:
        return json.loads(self.preregistration_canonical)

    @property
    def definition_hash(self) -> str:
        return str(self.document.get("definition_hash") or "")

    @property
    def estimand_card_hash(self) -> str:
        return str((self.document.get("estimand_card_ref") or {}).get("card_hash") or "")

    @property
    def event_definition_id(self) -> str:
        return str(self.document.get("event_definition_id") or "")

    @property
    def shock_class(self) -> str:
        return str(self.document.get("shock_class") or "")

    @property
    def windows(self) -> Mapping[str, Any]:
        return self.preregistration.get("windows") or {}


def build_identification_card(
    document: Mapping[str, Any],
    *,
    estimand_bytes: bytes,
    preregistration_bytes: bytes,
    source_path: str | None = None,
) -> IdentificationCard:
    """Pure constructor: the card mapping plus the raw bytes of the two cards it references."""

    if not isinstance(document, Mapping):
        raise TypeError("an identification card must be a mapping")
    estimand = json.loads(estimand_bytes.decode("utf-8"))
    preregistration = json.loads(preregistration_bytes.decode("utf-8"))
    return IdentificationCard(
        canonical=canonical_json(dict(document)),
        estimand_canonical=canonical_json(estimand),
        estimand_sha256=_sha256(estimand_bytes),
        preregistration_canonical=canonical_json(preregistration),
        preregistration_file_sha256=_sha256(preregistration_bytes),
        source_path=source_path,
    )


def _find_root(card_path: Path, relative: str) -> Path:
    for parent in card_path.resolve().parents:
        if (parent / relative).is_file():
            return parent
    raise ContractError(f"referenced card {relative!r} not found above {card_path}")


def load_identification_card(
    path: str | Path = DEFAULT_CARD_PATH, *, repo_root: str | Path | None = None
) -> IdentificationCard:
    """Read the card and the two cards it references.  The only I/O in this module."""

    card_path = Path(path)
    document = json.loads(card_path.read_text(encoding="utf-8"))
    estimand_rel = str((document.get("estimand_card_ref") or {}).get("path") or "")
    prereg_rel = str((document.get("preregistration_card_ref") or {}).get("path") or "")
    if not estimand_rel or not prereg_rel:
        raise ContractError("identification card does not name its estimand and preregistration cards")
    root = Path(repo_root) if repo_root is not None else _find_root(card_path, estimand_rel)
    return build_identification_card(
        document,
        estimand_bytes=(root / estimand_rel).read_bytes(),
        preregistration_bytes=(root / prereg_rel).read_bytes(),
        source_path=str(card_path),
    )


def _get(mapping: Any, dotted: str) -> Any:
    node = mapping
    for part in dotted.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return _MISSING
        node = node[part]
    return node


def _blank(value: Any) -> bool:
    if value is _MISSING or value is None:
        return True
    if isinstance(value, str):
        return not value.strip() or value.strip().upper() in {"TBD", "TODO"}
    return False


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _positive_int(value: Any, *, allow_zero: bool = False) -> bool:
    if not isinstance(value, int) or isinstance(value, bool):
        return False
    return value >= 0 if allow_zero else value > 0


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _non_exogenous_ids(estimand: Mapping[str, Any]) -> frozenset[str]:
    return frozenset(
        str(item.get("id")).strip().lower()
        for item in estimand.get("non_exogenous_constructions") or ()
        if isinstance(item, Mapping) and item.get("id")
    )


def _add(codes: list[str], code: str) -> None:
    if code not in codes:
        codes.append(code)


def validate_identification_card(card: IdentificationCard) -> tuple[str, ...]:
    """Every card violation, in a fixed order; ``()`` means the card is admissible.

    Codes: ``BLANK_FIELD:<path>``, ``UNPROVEN_INSTRUMENT_RIGHTS:<id>``,
    ``FORBIDDEN_CONTROLS_DIVERGE``, ``HASH_MISMATCH`` (definition_hash) and
    ``HASH_MISMATCH:<ref>``, ``NON_FINITE_PLACEBO``, ``RESERVED_WINDOW_IN_RULE``,
    ``NON_FINITE_THRESHOLD:<path>``, ``SHOCK_CLASS_NOT_INSTRUMENT:<class>``,
    ``NON_EXOGENOUS_INSTRUMENT:<id>``, ``CLOCK_RULE_NOT_POINT_IN_TIME:<id>``.
    """

    doc = card.document
    estimand = card.estimand
    prereg = card.preregistration
    codes: list[str] = []

    for dotted in _REQUIRED_PATHS:
        if _blank(_get(doc, dotted)):
            _add(codes, f"BLANK_FIELD:{dotted}")

    for dotted in _POSITIVE_THRESHOLDS:
        value = _get(doc, dotted)
        if value is not _MISSING and value is not None and not (_finite_number(value) and float(value) > 0):
            _add(codes, f"NON_FINITE_THRESHOLD:{dotted}")
    for dotted in _POSITIVE_INTEGERS:
        value = _get(doc, dotted)
        if value is not _MISSING and value is not None and not _positive_int(value):
            _add(codes, f"NON_FINITE_THRESHOLD:{dotted}")
    level = _get(doc, "inference_rule.interval_level")
    if level is not _MISSING and level is not None and not (_finite_number(level) and 0 < float(level) < 1):
        _add(codes, "NON_FINITE_THRESHOLD:inference_rule.interval_level")

    if doc.get("shock_class") not in INSTRUMENT_SHOCK_CLASSES and not _blank(doc.get("shock_class", _MISSING)):
        _add(codes, f"SHOCK_CLASS_NOT_INSTRUMENT:{doc.get('shock_class')}")

    non_exogenous = _non_exogenous_ids(estimand)
    candidates = doc.get("instrument_candidates")
    if not isinstance(candidates, list):
        _add(codes, "BLANK_FIELD:instrument_candidates")
        candidates = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            _add(codes, f"BLANK_FIELD:instrument_candidates[{index}]")
            continue
        for key in _CANDIDATE_KEYS:
            if _blank(candidate.get(key, _MISSING)):
                _add(codes, f"BLANK_FIELD:instrument_candidates[{index}].{key}")
        instrument_id = str(candidate.get("instrument_id") or f"[{index}]")
        source_ref = candidate.get("source_ref")
        source_blank = not isinstance(source_ref, Mapping) or any(
            _blank(source_ref.get(key, _MISSING)) for key in ("repo", "path", "sha")
        )
        if candidate.get("rights_state") != RIGHTS_PROVEN or source_blank:
            _add(codes, f"UNPROVEN_INSTRUMENT_RIGHTS:{instrument_id}")
        if not _blank(candidate.get("clock_rule", _MISSING)) and candidate.get("clock_rule") != POINT_IN_TIME_CLOCK:
            _add(codes, f"CLOCK_RULE_NOT_POINT_IN_TIME:{instrument_id}")
        announcement = str(candidate.get("announcement_type") or "").strip().lower()
        construction = str(candidate.get("construction") or "").strip().lower()
        if announcement in non_exogenous or construction in non_exogenous:
            _add(codes, f"NON_EXOGENOUS_INSTRUMENT:{instrument_id}")

    exclusions = doc.get("confounding_news_exclusions")
    for index, item in enumerate(exclusions if isinstance(exclusions, list) else ()):
        if not isinstance(item, Mapping):
            _add(codes, f"BLANK_FIELD:confounding_news_exclusions[{index}]")
            continue
        for key in _EXCLUSION_KEYS:
            value = item.get(key, _MISSING)
            invalid = _blank(value)
            if key in ("weekdays_before", "weekdays_after") and not invalid:
                invalid = not _positive_int(value, allow_zero=True)
            if key == "same_event_rule" and not invalid:
                invalid = value not in SAME_EVENT_RULES
            if invalid:
                _add(codes, f"BLANK_FIELD:confounding_news_exclusions[{index}].{key}")

    specs = doc.get("admissible_specifications")
    for index, spec in enumerate(specs if isinstance(specs, list) else ()):
        if not isinstance(spec, Mapping) or _blank(spec.get("spec_id", _MISSING)):
            _add(codes, f"BLANK_FIELD:admissible_specifications[{index}].spec_id")
        elif not isinstance(spec.get("controls"), list):
            _add(codes, f"BLANK_FIELD:admissible_specifications[{index}].controls")

    if canonical_json(doc.get("forbidden_controls")) != canonical_json(estimand.get("forbidden_controls")):
        _add(codes, "FORBIDDEN_CONTROLS_DIVERGE")

    if doc.get("definition_hash") != identification_definition_hash(doc):
        _add(codes, "HASH_MISMATCH")
    if card.estimand_card_hash != card.estimand_sha256:
        _add(codes, "HASH_MISMATCH:estimand_card_ref")
    prereg_ref = doc.get("preregistration_card_ref") or {}
    prereg_computed = preregistration_card_hash(prereg)
    if prereg_ref.get("card_hash") != prereg_computed or prereg.get("card_hash") != prereg_computed:
        _add(codes, "HASH_MISMATCH:preregistration_card_ref")
    if doc.get("event_definition_id") != prereg.get("event_definition_id"):
        _add(codes, "HASH_MISMATCH:event_definition_id")
    if doc.get("relation_id") != estimand.get("relation_id"):
        _add(codes, "HASH_MISMATCH:relation_id")

    placebo = doc.get("placebo_design") or {}
    n_dates, seed, level = placebo.get("n_placebo_dates"), placebo.get("seed"), placebo.get("level")
    if not (
        _positive_int(n_dates)
        and isinstance(seed, int)
        and not isinstance(seed, bool)
        and _finite_number(level)
        and 0 < float(level) < 1
        and _positive_int(placebo.get("min_weekdays_from_event"), allow_zero=True)
    ):
        _add(codes, "NON_FINITE_PLACEBO")

    windows = prereg.get("windows") or {}
    reserved = _parse_date(windows.get("reserved_start"))
    pool_end = _parse_date(_get(placebo, "pool_window.end"))
    firewall_reserved = _get(doc, "outcome_firewall.reserved_start")
    if (
        reserved is None
        or (pool_end is not None and pool_end >= reserved)
        or (firewall_reserved is not _MISSING and str(firewall_reserved) != str(windows.get("reserved_start")))
    ):
        _add(codes, "RESERVED_WINDOW_IN_RULE")
    return tuple(codes)


# ----------------------------------------------------------- specifications
def _ids(items: Any) -> set[str]:
    return {
        str(item.get("id")).strip().lower()
        for item in items or ()
        if isinstance(item, Mapping) and item.get("id")
    }


def validate_specification(spec: Mapping[str, Any], estimand_card: Any) -> tuple[str, ...]:
    """Check a specification's controls against the estimand card read from disk.

    Names are compared case- and whitespace-insensitively.  Codes:
    ``FORBIDDEN_CONTROL:<name>``, ``MEDIATOR_AS_CONTROL:<name>``,
    ``COLLIDER_AS_CONTROL:<name>`` and ``UNDECLARED_CONTROL:<name>`` (a control
    that is not one of the card's declared pre-treatment confounders).
    """

    estimand = estimand_card.estimand if isinstance(estimand_card, IdentificationCard) else estimand_card
    if not isinstance(estimand, Mapping):
        raise TypeError("validate_specification needs the estimand card mapping")
    forbidden = _ids(estimand.get("forbidden_controls"))
    mediators = _ids(estimand.get("mediators"))
    colliders = _ids(estimand.get("colliders"))
    confounders = _ids(estimand.get("confounders"))
    controls = spec.get("controls") if isinstance(spec, Mapping) else None
    if not isinstance(controls, (list, tuple)):
        raise ContractError("a specification must list its controls")
    codes: list[str] = []
    for raw in controls:
        name = str(raw).strip().lower()
        flagged = False
        if name in forbidden:
            _add(codes, f"FORBIDDEN_CONTROL:{name}")
            flagged = True
        if name in mediators:
            _add(codes, f"MEDIATOR_AS_CONTROL:{name}")
            flagged = True
        if name in colliders:
            _add(codes, f"COLLIDER_AS_CONTROL:{name}")
            flagged = True
        if not flagged and name not in confounders:
            _add(codes, f"UNDECLARED_CONTROL:{name}")
    return tuple(codes)


# -------------------------------------------------------------------- receipt
def _iso(value: Any) -> Any:
    """JSON-native copy: dates as ISO strings, tuples as lists, mapping keys as strings."""

    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _iso(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_iso(item) for item in value]
    return value


@dataclass(frozen=True)
class IdentificationReceipt:
    """The outcome of ``qualify_identification``; NOT_IDENTIFIED unless every test passed."""

    status: str
    context: Mapping[str, Any]
    reasons: tuple[str, ...]
    tests_run: tuple[TestResult, ...]
    estimand_card_hash: str
    definition_hash: str
    event_definition_id: str
    known_at: datetime

    def __post_init__(self) -> None:
        if self.status not in RECEIPT_STATUSES:
            raise ContractError(f"unknown receipt status {self.status!r}")
        if self.status == IDENTIFIED_FOR_CONTEXT:
            if self.reasons:
                raise ContractError("an identified receipt carries no failure reasons")
            if not self.tests_run or not all(test.passed for test in self.tests_run):
                raise ContractError("an identified receipt needs every test run and passed")
        elif not self.reasons:
            raise ContractError("a NOT_IDENTIFIED receipt must state its reasons")

    @property
    def identified(self) -> bool:
        return self.status == IDENTIFIED_FOR_CONTEXT

    def to_record(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "context": {key: _iso(value) for key, value in dict(self.context).items()},
            "reasons": list(self.reasons),
            "tests_run": [
                {
                    "name": test.name,
                    "statistic": test.statistic,
                    "value": test.value,
                    "threshold": test.threshold,
                    "passed": test.passed,
                }
                for test in self.tests_run
            ],
            "estimand_card_hash": self.estimand_card_hash,
            "definition_hash": self.definition_hash,
            "event_definition_id": self.event_definition_id,
            "known_at": self.known_at.isoformat(),
        }

    @property
    def receipt_id(self) -> str:
        return _sha256(canonical_json(self.to_record()).encode("utf-8"))

    def label_receipt(self) -> dict[str, Any]:
        """The receipt shape the eventization label accepts; refused unless identified."""

        if not self.identified:
            raise IdentificationRequired(
                f"receipt status {self.status}: no identification label may be attached ({', '.join(self.reasons)})"
            )
        return {
            "receipt_id": self.receipt_id,
            "method": RECEIPT_METHOD,
            "weak_instrument": False,
            "instrument_id": self.context.get("instrument_id"),
            "shock_class": self.context.get("shock_class"),
            "definition_hash": self.definition_hash,
            "estimand_card_hash": self.estimand_card_hash,
        }


# ---------------------------------------------------------------- statistics
MeanTest = Callable[..., Mapping[str, Any]]


def _resolve_mean_test(mean_test_fn: MeanTest | None, lags: int) -> MeanTest:
    if mean_test_fn is not None:
        return mean_test_fn
    try:
        from engine.validation import newey_west_tstat  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        raise StatisticalDependencyUnavailable(HAC_DEPENDENCY_MESSAGE) from exc
    return lambda values: newey_west_tstat(values, lags=lags)


def _judge(mean_test: MeanTest, series: np.ndarray) -> Mapping[str, Any]:
    return dict(mean_test(pd.Series(np.asarray(series, dtype=float), dtype=float)))


def _t_of(result: Mapping[str, Any]) -> float | None:
    value = result.get("t")
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _residualize(values: np.ndarray, controls: np.ndarray | None) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if controls is None or controls.shape[1] == 0:
        return values - values.mean()
    design = np.column_stack([np.ones(len(values)), controls])
    coef, *_ = np.linalg.lstsq(design, values, rcond=None)
    return values - design @ coef


def _slope_inference(mean_test: MeanTest, z: np.ndarray, y: np.ndarray) -> dict[str, float | None]:
    """OLS slope with a HAC sandwich t: the judge sees b + n*z*u/Szz, whose mean is b."""

    szz = float(np.dot(z, z))
    if szz == 0.0:
        return {"slope": None, "t": None, "se": None}
    slope = float(np.dot(z, y) / szz)
    resid = y - slope * z
    series = slope + len(z) * z * resid / szz
    result = _judge(mean_test, series)
    t = _t_of(result)
    se = result.get("se")
    se = float(se) if se is not None and math.isfinite(float(se)) and float(se) > 0 else None
    if se is None and t not in (None, 0.0):
        se = abs(slope / t)
    return {"slope": slope, "t": t, "se": se}


def _weekday_distance(start: date, end: date) -> int:
    """Signed weekdays from ``start`` to ``end`` (numpy Mon-Fri, no holidays)."""

    if end >= start:
        return int(np.busday_count(start.isoformat(), end.isoformat()))
    return -int(np.busday_count(end.isoformat(), start.isoformat()))


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _panel_sha256(panel: Sequence[InstrumentObservation]) -> str:
    rows = sorted(
        (
            {
                "instrument_id": row.instrument_id,
                "event_id": row.event_id,
                "session": row.session.isoformat(),
                "known_at": _as_utc(row.known_at).isoformat(),
                "surprise": float(row.surprise),
                "treatment": float(row.treatment),
                "announcement_type": row.announcement_type,
            }
            for row in panel
        ),
        key=lambda item: (item["event_id"], item["session"]),
    )
    return _sha256(canonical_json(rows).encode("utf-8"))


def _candidates(card: IdentificationCard) -> dict[str, Mapping[str, Any]]:
    return {
        str(item.get("instrument_id")): item
        for item in card.document.get("instrument_candidates") or ()
        if isinstance(item, Mapping) and item.get("instrument_id")
    }


def confounded_events(
    panel: Sequence[InstrumentObservation],
    calendar: Sequence[CalendarEvent],
    card: IdentificationCard,
) -> tuple[tuple[str, str, date], ...]:
    """Every (class, event_id, session) the card's confounding-news rules exclude.

    Reads only the announcement calendar, never an outcome.  Callers may drop
    these events upstream and report them; any that remain fail qualification.
    """

    candidates = _candidates(card)
    hits: list[tuple[str, str, date]] = []
    for rule in card.document.get("confounding_news_exclusions") or ():
        klass = str(rule["class"])
        before, after = int(rule["weekdays_before"]), int(rule["weekdays_after"])
        same_event_rule = rule["same_event_rule"]
        for obs in panel:
            announcement = str(
                obs.announcement_type
                or (candidates.get(obs.instrument_id) or {}).get("announcement_type")
                or ""
            )
            purged = announcement.endswith(INFORMATION_PURGED_SUFFIX)
            for event in calendar:
                if event.event_class != klass:
                    continue
                distance = _weekday_distance(obs.session, event.session)
                if not -before <= distance <= after:
                    continue
                if event.event_id == obs.event_id:
                    if same_event_rule == "never_counts":
                        continue
                    if same_event_rule == "counts_unless_information_purged" and purged:
                        continue
                hit = (klass, obs.event_id, obs.session)
                if hit not in hits:
                    hits.append(hit)
    return tuple(hits)


# --------------------------------------------------------------- qualification
def _window_lengths(doc: Mapping[str, Any]) -> dict[str, int]:
    return {
        ANTICIPATION_WINDOW: int(doc["anticipation_rule"]["window_sessions_before"]),
        PRE_TREND_WINDOW: int(doc["pre_trend_rule"]["sessions"]),
        REACTION_WINDOW: int(doc["reverse_response_rule"]["lookback_sessions"]),
    }


def _admit_and_fence(guard: WindowGuard, rows: Sequence[ForwardReturnObservation]) -> list[ForwardReturnObservation]:
    """Count every refusal first, then raise if any row reaches the reserved window."""

    admitted = guard.admit(rows, fold="dev")
    guard.assert_no_reserved(rows)
    return admitted


def _episodes(
    card: IdentificationCard,
    rows: Sequence[ForwardReturnObservation],
    instrument: Mapping[str, float],
) -> list[tuple[float, float, str]]:
    """The incumbent's honest-N thinning (T16 local projection) with the instrument as impulse.

    Returns (instrument value, mean response, event id) per thinned episode.
    """

    challenger = LocalProjectionChallenger(
        card_hash=str(card.document["preregistration_card_ref"]["card_hash"]),
        min_effective_n=2,
        size_key=INSTRUMENT_KEY,
        bucket_key=EVENT_KEY,
    )
    augmented = [
        replace(row, conditions={**dict(row.conditions), INSTRUMENT_KEY: float(instrument[row.conditions[EVENT_KEY]])})
        for row in rows
    ]
    prefix = f"{EVENT_KEY}="
    return [(size, response, bucket[len(prefix):]) for size, response, bucket in challenger._episodes(augmented)]


def qualify_identification(
    card: IdentificationCard,
    *,
    instrument_panel: Sequence[InstrumentObservation] | None,
    event_calendar: Sequence[CalendarEvent] | None,
    outcome_frame: Sequence[ForwardReturnObservation] | None,
    guard: WindowGuard | None,
    as_of: datetime,
    horizons: Sequence[int] | None = None,
    mean_test_fn: MeanTest | None = None,
) -> IdentificationReceipt:
    """Run every frozen identification rule and collect EVERY failure.

    Reads the instrument panel, the announcement calendar and pre-announcement
    outcome windows only.  Returns ``IDENTIFIED_FOR_CONTEXT`` only when no reason
    is recorded; otherwise ``NOT_IDENTIFIED`` with all reasons.
    """

    doc = card.document
    reasons: list[str] = []
    tests: list[TestResult] = []
    as_of = _as_utc(as_of)
    windows = card.windows
    reserved_start = _parse_date(windows.get("reserved_start"))
    train_start = _parse_date(windows.get("train_start"))
    dev_end = _parse_date(windows.get("dev_end"))
    grid = tuple(int(h) for h in (horizons if horizons is not None else card.preregistration["horizons"]["candidates"]))
    for horizon in grid:
        if horizon not in HORIZONS_BDAYS:
            raise ContractError(f"horizon {horizon} is not precommitted")

    # 1. card admissibility (rights failures are reported as NO_RIGHTS)
    card_codes = validate_identification_card(card)
    for code in card_codes:
        if code.startswith("UNPROVEN_INSTRUMENT_RIGHTS:"):
            _add(reasons, "NO_RIGHTS:" + code.split(":", 1)[1])
        else:
            _add(reasons, f"CARD_INVALID:{code}")
    tests.append(TestResult("card_admissible", "violations", float(len(card_codes)), 0.0, not card_codes))

    # 2. specifications from the card, checked against the estimand card
    spec_codes: list[str] = []
    for spec in doc.get("admissible_specifications") or ():
        for code in validate_specification(spec, card.estimand):
            _add(spec_codes, code)
    for code in spec_codes:
        _add(reasons, code)
    tests.append(TestResult("specifications_admissible", "violations", float(len(spec_codes)), 0.0, not spec_codes))

    # 3. the instrument
    candidates = _candidates(card)
    if not candidates:
        _add(reasons, "NO_INSTRUMENT")
    tests.append(TestResult("instrument_declared", "candidates", float(len(candidates)), 1.0, bool(candidates)))

    if guard is None:
        _add(reasons, "MISSING_INPUT:guard")
    elif guard.card_hash != doc.get("preregistration_card_ref", {}).get("card_hash"):
        raise ContractError("the WindowGuard is bound to a different preregistration card")

    instrument_id: str | None = None
    panel: list[InstrumentObservation] = []
    if not instrument_panel:
        _add(reasons, "MISSING_INPUT:instrument_panel")
    else:
        ids = sorted({row.instrument_id for row in instrument_panel})
        if len(ids) != 1:
            raise ContractError(f"one instrument per qualification; the panel names {ids}")
        instrument_id = ids[0]
        if reserved_start is not None:
            touched = [row.event_id for row in instrument_panel if row.session >= reserved_start]
            if touched:
                raise ReservedWindowTouched(
                    f"{len(touched)} instrument row(s) reach reserved_start {reserved_start.isoformat()}: {touched[:5]}"
                )
        seen: set[str] = set()
        for row in instrument_panel:
            if row.event_id in seen:
                raise ContractError(f"duplicate instrument event {row.event_id}")
            seen.add(row.event_id)
            if not (math.isfinite(float(row.surprise)) and math.isfinite(float(row.treatment))):
                raise ContractError(f"non-finite instrument value on {row.event_id}")
            if (train_start and row.session < train_start) or (dev_end and row.session > dev_end):
                continue
            panel.append(row)
        if instrument_id not in candidates:
            _add(reasons, f"UNDECLARED_INSTRUMENT:{instrument_id}")
        future = [
            row.session.isoformat()
            for row in sorted(panel, key=lambda r: r.session)
            if _as_utc(row.known_at).date() > row.session or _as_utc(row.known_at) > as_of
        ]
        for session in future:
            _add(reasons, f"FUTURE_INSTRUMENT:{session}")
        tests.append(TestResult("point_in_time_instrument", "future_rows", float(len(future)), 0.0, not future))
        if not panel:
            _add(reasons, "MISSING_INPUT:instrument_panel")

    # 4. confounding policy-information news (calendar only)
    if event_calendar is None:
        _add(reasons, "MISSING_INPUT:event_calendar")
    elif panel:
        hits = confounded_events(panel, event_calendar, card)
        for klass, _event_id, session in hits:
            _add(reasons, f"CONFOUNDING_NEWS:{klass}:{session.isoformat()}")
        tests.append(TestResult("confounding_news", "confounded_events", float(len(hits)), 0.0, not hits))

    # 5. statistical tests (HAC judge); the dependency is quoted verbatim when absent
    relevance = doc.get("relevance_rule") or {}
    min_events = int(relevance.get("min_thinned_events") or 0)
    mean_test: MeanTest | None = None
    dependency_error: str | None = None
    try:
        mean_test = _resolve_mean_test(mean_test_fn, int(relevance.get("hac_lags") or 4))
    except StatisticalDependencyUnavailable as exc:
        dependency_error = f"StatisticalDependencyUnavailable: {exc}"

    by_event = {row.event_id: row for row in panel}
    if panel:
        if dependency_error:
            _add(reasons, f"UNTESTED:first_stage_relevance:{dependency_error}")
        else:
            z = np.asarray([row.surprise for row in panel], dtype=float)
            d = np.asarray([row.treatment for row in panel], dtype=float)
            minimum = float(relevance["min_value"])
            if len(panel) < min_events:
                _add(reasons, f"WEAK_RELEVANCE:thinned_events={len(panel)}<{min_events}")
                tests.append(TestResult("first_stage_relevance", "thinned_events", float(len(panel)), float(min_events), False))
            else:
                t = _slope_inference(mean_test, z - z.mean(), d - d.mean())["t"]
                f_stat = 0.0 if t is None else t * t
                passed = f_stat >= minimum
                if not passed:
                    _add(reasons, f"WEAK_RELEVANCE:first_stage_F={f_stat:.3f}<{minimum:g}")
                tests.append(TestResult("first_stage_relevance", "first_stage_F", f_stat, minimum, passed))

    # 6. pre-announcement windows behind the outcome firewall
    target_id: str | None = None
    if outcome_frame is None:
        _add(reasons, "MISSING_INPUT:outcome_frame")
    elif guard is not None:
        admitted = _admit_and_fence(guard, outcome_frame)
        lengths = _window_lengths(doc)
        clean: dict[str, list[ForwardReturnObservation]] = {window: [] for window in PRE_ANNOUNCEMENT_WINDOWS}
        breaches = 0
        targets = {row.target_id for row in admitted}
        if len(targets) > 1:
            raise ContractError(f"one target per qualification; the frame names {sorted(targets)}")
        target_id = next(iter(targets), None)
        for row in admitted:
            event_id = row.conditions.get(EVENT_KEY)
            window = row.conditions.get(WINDOW_KEY)
            obs = by_event.get(str(event_id)) if event_id is not None else None
            if obs is None:
                if instrument_panel:
                    raise ContractError(f"outcome row {row.shock_id} names no instrument event in the panel")
                continue
            if window not in PRE_ANNOUNCEMENT_WINDOWS or row.exit_session >= obs.session:
                breaches += 1
                continue
            if int(row.horizon_bdays) != lengths[window]:
                raise ContractError(
                    f"{window} row {row.shock_id} spans {row.horizon_bdays} sessions; the card declares {lengths[window]}"
                )
            clean[window].append(row)
        if breaches:
            _add(reasons, "OUTCOME_FIREWALL_BREACH")
        tests.append(TestResult("outcome_firewall", "post_announcement_rows", float(breaches), 0.0, not breaches))
        pre_trend_exit = {row.conditions[EVENT_KEY]: row.exit_session for row in clean[PRE_TREND_WINDOW]}
        for row in clean[ANTICIPATION_WINDOW]:
            end = pre_trend_exit.get(row.conditions[EVENT_KEY])
            if end is not None and end > row.anchor_session:
                raise ContractError(f"pre-trend window overlaps the anticipation window for {row.conditions[EVENT_KEY]}")

        instrument = {event: obs.surprise for event, obs in by_event.items()}
        rules = (
            ("anticipation", ANTICIPATION_WINDOW, "ANTICIPATION", doc["anticipation_rule"]),
            ("pre_trend", PRE_TREND_WINDOW, "PRE_TREND", doc["pre_trend_rule"]),
            ("reverse_response", REACTION_WINDOW, "REVERSE_RESPONSE", doc["reverse_response_rule"]),
        )
        for name, window, code, rule in rules:
            rows = clean[window]
            if not rows:
                _add(reasons, f"MISSING_INPUT:outcome_frame.{window}")
                continue
            if dependency_error:
                _add(reasons, f"UNTESTED:{name}:{dependency_error}")
                continue
            episodes = _episodes(card, rows, instrument)
            if len(episodes) < min_events:
                _add(reasons, f"UNTESTED:{name}:thinned_events={len(episodes)}<{min_events}")
                tests.append(TestResult(name, "thinned_events", float(len(episodes)), float(min_events), False))
                continue
            z = np.asarray([e[0] for e in episodes], dtype=float)
            y = np.asarray([e[1] for e in episodes], dtype=float)
            if name == "reverse_response":  # the instrument regressed on the lagged target return
                t = _slope_inference(mean_test, y - y.mean(), z - z.mean())["t"]
            else:
                t = _slope_inference(mean_test, z - z.mean(), y - y.mean())["t"]
            limit = float(rule["max_abs_t"])
            if t is None:
                _add(reasons, f"UNTESTED:{name}:judge_returned_no_t")
                tests.append(TestResult(name, "slope_t", None, limit, False))
                continue
            passed = abs(t) <= limit
            if not passed:
                _add(reasons, f"{code}:t={t:.3f}")
            tests.append(TestResult(name, "slope_t", t, limit, passed))

    context = {
        "shock_class": card.shock_class,
        "instrument_id": instrument_id,
        "target_id": target_id,
        "horizons": grid,
        "window": {
            "fold": "dev",
            "start": windows.get("train_start"),
            "end": windows.get("dev_end"),
            "reserved_start": windows.get("reserved_start"),
        },
        "instrument_panel_sha256": _panel_sha256(panel) if panel else None,
    }
    return IdentificationReceipt(
        status=NOT_IDENTIFIED if reasons else IDENTIFIED_FOR_CONTEXT,
        context=context,
        reasons=tuple(reasons),
        tests_run=tuple(tests),
        estimand_card_hash=card.estimand_card_hash,
        definition_hash=card.definition_hash,
        event_definition_id=card.event_definition_id,
        known_at=as_of,
    )


# ----------------------------------------------------------- causal estimate
@dataclass(frozen=True)
class CausalEstimateCard:
    """A context-bound causal estimate.  Not a T16 projection and never convertible to one."""

    label: str
    receipt: IdentificationReceipt
    spec_id: str
    target_id: str
    horizons: tuple[int, ...]
    per_horizon: Mapping[int, Mapping[str, Any]]
    joint: Mapping[str, Any]
    specifications_run: tuple[Mapping[str, Any], ...]
    placebo_design: Mapping[str, Any]
    window_guard: Mapping[str, Any]
    evidence_tier: str = CAUSAL_EVIDENCE_TIER
    validated: bool = False

    def __post_init__(self) -> None:
        if self.label != CAUSAL_LABEL:
            raise ContractError(f"a causal estimate card is labelled {CAUSAL_LABEL!r}")
        if not isinstance(self.receipt, IdentificationReceipt) or not self.receipt.identified:
            raise IdentificationRequired("the causal label travels only with an identified receipt")
        if self.evidence_tier != CAUSAL_EVIDENCE_TIER:
            raise ContractError(f"evidence_tier must be {CAUSAL_EVIDENCE_TIER!r}")
        if self.validated is not False:
            raise ContractError("a T17 causal estimate is never validated")

    def to_causal_record(self) -> dict[str, Any]:
        return _iso({
            "label": self.label,
            "receipt": self.receipt.to_record(),
            "receipt_id": self.receipt.receipt_id,
            "spec_id": self.spec_id,
            "target_id": self.target_id,
            "horizons": list(self.horizons),
            "per_horizon": {str(h): dict(v) for h, v in self.per_horizon.items()},
            "joint": dict(self.joint),
            "specifications_run": [dict(item) for item in self.specifications_run],
            "placebo_design": dict(self.placebo_design),
            "window_guard": dict(self.window_guard),
            "evidence_tier": self.evidence_tier,
            "validated": self.validated,
        })


def _control_matrix(
    events: Sequence[str],
    first_row: Mapping[str, ForwardReturnObservation],
    controls: Sequence[str],
) -> tuple[np.ndarray | None, str | None]:
    if not controls:
        return None, None
    matrix = np.empty((len(events), len(controls)), dtype=float)
    for i, event in enumerate(events):
        conditions = first_row[event].conditions
        for j, name in enumerate(controls):
            value = conditions.get(name)
            if not _finite_number(value):
                return None, f"missing_control:{name}"
            matrix[i, j] = float(value)
    return matrix, None


def _anderson_rubin(
    mean_test: MeanTest,
    z: np.ndarray,
    y: np.ndarray,
    d: np.ndarray,
    *,
    center: float,
    scale: float,
    critical: float,
    points: int = 801,
) -> dict[str, Any]:
    grid = np.linspace(center - 10.0 * scale, center + 10.0 * scale, points)
    accepted = []
    for beta in grid:
        t = _t_of(_judge(mean_test, z * (y - beta * d)))
        accepted.append(t is not None and abs(t) <= critical)
    mask = np.asarray(accepted, dtype=bool)
    out: dict[str, Any] = {"method": "anderson_rubin_grid", "grid_points": points}
    if not mask.any():
        return {**out, "shape": "empty", "lower": None, "upper": None}
    if mask[0] or mask[-1]:
        return {**out, "shape": "unbounded", "lower": None, "upper": None}
    inside = grid[mask]
    contiguous = bool(np.all(np.diff(np.flatnonzero(mask)) == 1))
    return {**out, "shape": "bounded", "lower": float(inside.min()), "upper": float(inside.max()), "convex": contiguous}


def _estimate_spec(
    mean_test: MeanTest,
    episodes: Sequence[tuple[float, float, str]],
    first_row: Mapping[str, ForwardReturnObservation],
    treatment: Mapping[str, float],
    controls: Sequence[str],
) -> tuple[dict[str, Any], tuple[np.ndarray, np.ndarray, np.ndarray] | None]:
    events = [e[2] for e in episodes]
    matrix, missing = _control_matrix(events, first_row, controls)
    if missing:
        return {"status": "not_run", "reason": missing}, None
    z = _residualize(np.asarray([e[0] for e in episodes], dtype=float), matrix)
    y = _residualize(np.asarray([e[1] for e in episodes], dtype=float), matrix)
    d = _residualize(np.asarray([treatment[event] for event in events], dtype=float), matrix)
    reduced = _slope_inference(mean_test, z, y)
    first = _slope_inference(mean_test, z, d)
    t_first = first["t"]
    gamma = first["slope"]
    iv = None if gamma in (None, 0.0) or reduced["slope"] is None else reduced["slope"] / gamma
    return {
        "status": "run",
        "effective_n": len(episodes),
        "reduced_form": reduced,
        "first_stage": {"slope": gamma, "F": None if t_first is None else t_first * t_first},
        "estimate": iv,
    }, (z, y, d)


def causal_response(
    receipt: IdentificationReceipt | None,
    spec: Mapping[str, Any],
    observations: Sequence[ForwardReturnObservation],
    *,
    horizons: Sequence[int],
    guard: WindowGuard,
    card: IdentificationCard,
    instrument_panel: Sequence[InstrumentObservation],
    placebo_observations: Sequence[ForwardReturnObservation],
    mean_test_fn: MeanTest | None = None,
    fdr_fn: Callable[..., Mapping[str, Mapping[str, object]]] | None = None,
) -> CausalEstimateCard:
    """Reduced form and IV ratio per horizon, for an identified context only.

    Raises ``IdentificationRequired`` without an identified receipt, on any hash
    mismatch between receipt, card and estimand card, for another instrument
    panel, for horizons outside the receipt's context, or for a specification
    the estimand card or the identification card does not admit.
    """

    if receipt is None or not isinstance(receipt, IdentificationReceipt):
        raise IdentificationRequired("no identification receipt: the causal label is refused")
    if not receipt.identified:
        raise IdentificationRequired(
            f"receipt status {receipt.status}: {', '.join(receipt.reasons)}"
        )
    if card.estimand_card_hash != card.estimand_sha256 or validate_identification_card(card):
        raise IdentificationRequired("the identification card is not admissible")
    if receipt.estimand_card_hash != card.estimand_card_hash:
        raise IdentificationRequired("receipt estimand_card_hash does not match the estimand card")
    if receipt.definition_hash != card.definition_hash:
        raise IdentificationRequired("receipt definition_hash does not match the identification card")
    if receipt.event_definition_id != card.event_definition_id:
        raise IdentificationRequired("receipt event_definition_id does not match the card")
    spec_hash = spec.get("estimand_card_hash") if isinstance(spec, Mapping) else None
    if spec_hash is not None and spec_hash != card.estimand_card_hash:
        raise IdentificationRequired("specification names a different estimand card")
    spec_codes = validate_specification(spec, card.estimand)
    if spec_codes:
        raise IdentificationRequired(f"specification refused: {', '.join(spec_codes)}")
    admissible = {
        str(item.get("spec_id")): [str(c) for c in item.get("controls") or ()]
        for item in card.document.get("admissible_specifications") or ()
    }
    spec_id = str(spec.get("spec_id"))
    if admissible.get(spec_id) != [str(c) for c in spec.get("controls") or ()]:
        raise IdentificationRequired(f"specification {spec_id!r} is not admissible on the identification card")
    grid = tuple(int(h) for h in horizons)
    if not grid or not set(grid) <= set(receipt.context.get("horizons") or ()):
        raise IdentificationRequired("requested horizons fall outside the receipt's context")
    if _panel_sha256(instrument_panel) != receipt.context.get("instrument_panel_sha256"):
        raise IdentificationRequired("the instrument panel differs from the one the receipt qualified")
    if guard.card_hash != card.document["preregistration_card_ref"]["card_hash"]:
        raise ContractError("the WindowGuard is bound to a different preregistration card")

    admitted = _admit_and_fence(guard, observations)
    pool_rows = _admit_and_fence(guard, placebo_observations)
    target_id = str(receipt.context.get("target_id"))
    if {row.target_id for row in admitted} - {target_id} or {row.target_id for row in pool_rows} - {target_id}:
        raise ContractError(f"observations must all be target {target_id}")

    doc = card.document
    relevance = doc["relevance_rule"]
    mean_test = _resolve_mean_test(mean_test_fn, int(relevance["hac_lags"]))
    placebo = doc["placebo_design"]
    level = float(doc["inference_rule"]["interval_level"])
    critical = NormalDist().inv_cdf(1.0 - (1.0 - level) / 2.0)
    min_events = int(relevance["min_thinned_events"])
    min_f = float(relevance["min_value"])
    by_event = {row.event_id: row for row in instrument_panel}
    instrument = {event: obs.surprise for event, obs in by_event.items()}
    treatment = {event: obs.treatment for event, obs in by_event.items()}
    event_sessions = sorted(obs.session for obs in instrument_panel)

    per_horizon: dict[int, dict[str, Any]] = {}
    alternatives: dict[str, dict[int, Any]] = {key: {} for key in admissible}
    placebo_p: dict[str, float] = {}
    for horizon in grid:
        rows = [row for row in admitted if int(row.horizon_bdays) == horizon]
        for row in rows:
            obs = by_event.get(str(row.conditions.get(EVENT_KEY)))
            if obs is None:
                raise ContractError(f"outcome row {row.shock_id} names no instrument event")
            if row.anchor_session < obs.session:
                raise ContractError(f"outcome row {row.shock_id} is anchored before its announcement")
        episodes = _episodes(card, rows, instrument) if rows else []
        first_row: dict[str, ForwardReturnObservation] = {}
        for row in rows:
            first_row.setdefault(str(row.conditions[EVENT_KEY]), row)
        if len(episodes) < min_events:
            per_horizon[horizon] = {
                "horizon": horizon,
                "effective_n": len(episodes),
                "estimate": None,
                "interval": None,
                "placebo_p": None,
                "bh_q": None,
                "abstention_reason": f"thinned_events={len(episodes)}<{min_events}",
            }
            for key in alternatives:
                alternatives[key][horizon] = {"status": "not_run", "reason": "insufficient_thinned_events"}
            continue
        for key, controls in admissible.items():
            result, _ = _estimate_spec(mean_test, episodes, first_row, treatment, controls)
            alternatives[key][horizon] = {
                k: result.get(k) for k in ("status", "reason", "effective_n", "estimate", "reduced_form")
                if k in result
            }
        primary, arrays = _estimate_spec(mean_test, episodes, first_row, treatment, admissible[spec_id])
        if arrays is None:
            raise ContractError(f"primary specification {spec_id} cannot run: {primary.get('reason')}")
        z, y, d = arrays
        first_f = primary["first_stage"]["F"]
        reduced = primary["reduced_form"]
        if first_f is None or first_f < min_f or primary["estimate"] is None:
            per_horizon[horizon] = {
                "horizon": horizon,
                "effective_n": len(episodes),
                "estimate": None,
                "interval": None,
                "placebo_p": None,
                "bh_q": None,
                "abstention_reason": f"WEAK_RELEVANCE:first_stage_F={0.0 if first_f is None else first_f:.3f}<{min_f:g}",
            }
            continue

        # placebo: relocate every thinned event to admitted non-event sessions
        min_gap = int(placebo["min_weekdays_from_event"])
        pool: dict[date, list[float]] = {}
        for row in pool_rows:
            if int(row.horizon_bdays) != horizon:
                continue
            if any(abs(_weekday_distance(session, row.anchor_session)) < min_gap for session in event_sessions):
                continue
            pool.setdefault(row.anchor_session, []).append(float(row.forward_return))
        sessions = sorted(pool)
        if len(sessions) < len(z):
            raise ContractError(
                f"placebo pool at horizon {horizon} has {len(sessions)} sessions; {len(z)} are needed"
            )
        pool_y = np.asarray([float(np.mean(pool[s])) for s in sessions], dtype=float)
        rng = np.random.default_rng(int(placebo["seed"]))  # one frozen stream per horizon
        szz = float(np.dot(z, z))
        actual = abs(float(reduced["slope"]))
        draws = int(placebo["n_placebo_dates"])
        exceed = 0
        for _ in range(draws):
            picked = pool_y[rng.choice(len(sessions), size=len(z), replace=False)]
            slope = float(np.dot(z, picked - picked.mean()) / szz)
            exceed += abs(slope) >= actual
        p_value = (1 + exceed) / (1 + draws)
        placebo_p[f"h{horizon}"] = p_value

        se = reduced["se"]
        rf_interval = (
            None
            if se is None
            else {"kind": "pointwise", "level": level, "lower": reduced["slope"] - critical * se, "upper": reduced["slope"] + critical * se}
        )
        gamma = float(primary["first_stage"]["slope"])
        scale = max(abs(primary["estimate"]), (se or 0.0) / abs(gamma), 1e-9)
        per_horizon[horizon] = {
            "horizon": horizon,
            "effective_n": len(episodes),
            "estimate": primary["estimate"],
            "interval": {
                "kind": "pointwise",
                "level": level,
                **_anderson_rubin(mean_test, z, y, d, center=primary["estimate"], scale=scale, critical=critical),
            },
            "reduced_form": {"estimate": reduced["slope"], "t": reduced["t"], "interval": rf_interval},
            "first_stage": primary["first_stage"],
            "placebo_p": p_value,
            "bh_q": None,
            "abstention_reason": None,
        }

    family_level = float(placebo["level"])
    joint: dict[str, Any] = {
        "family": "horizons",
        "treatment": placebo["family_treatment"],
        "level": family_level,
        "tested": sorted(placebo_p),
        "simultaneous_band": None,
        "path_claim_allowed": False,
        "note": "pointwise intervals and BH over horizons; a path or region claim needs a simultaneous band, which the card does not declare (S32)",
    }
    if placebo_p:
        try:
            adjusted = apply_bh_fdr(placebo_p, alpha=family_level, fdr_fn=fdr_fn)
        except StatisticalDependencyUnavailable as exc:
            joint["status"] = "abstained"
            joint["reason"] = f"StatisticalDependencyUnavailable: {exc}"
        else:
            joint["status"] = "adjusted"
            joint["rejected"] = sorted(key for key, value in adjusted.items() if value.get("reject"))
            for key, value in adjusted.items():
                horizon = int(key[1:])
                per_horizon[horizon]["bh_q"] = float(value["q"]) if value.get("q") is not None else None
                per_horizon[horizon]["bh_reject"] = bool(value.get("reject"))
    else:
        joint["status"] = "no_estimated_horizon"

    return CausalEstimateCard(
        label=CAUSAL_LABEL,
        receipt=receipt,
        spec_id=spec_id,
        target_id=target_id,
        horizons=grid,
        per_horizon=per_horizon,
        joint=joint,
        specifications_run=tuple(
            {"spec_id": key, "controls": admissible[key], "per_horizon": {str(h): v for h, v in values.items()}}
            for key, values in alternatives.items()
        ),
        placebo_design=dict(placebo),
        window_guard=guard.receipt(),
    )


__all__ = [
    "CAUSAL_EVIDENCE_TIER",
    "CAUSAL_LABEL",
    "CalendarEvent",
    "CausalEstimateCard",
    "IDENTIFIED_FOR_CONTEXT",
    "INSTRUMENT_SHOCK_CLASSES",
    "IdentificationCard",
    "IdentificationReceipt",
    "IdentificationRequired",
    "InstrumentObservation",
    "TestResult",
    "build_identification_card",
    "causal_response",
    "confounded_events",
    "identification_definition_hash",
    "load_identification_card",
    "qualify_identification",
    "validate_identification_card",
    "validate_specification",
]
