"""T07: producer envelope / sole consumer reader / lab adapter parity.

Every test hands the SAME producer bytes (the committed W-LIQ.1 fixture, byte-identical
to the reader's own fixture) to both sides -- ``brain.liquidity_transmission`` (the sole
consumer reader) and ``brain.liquidity_lab.adapter.adapt_producer_state`` -- and compares
the actual objects they return, never a paraphrase of either.

Acceptance case map (new tests in this module, existing tests cited, never duplicated):

* C08 raw first-difference and standardized magnitude cannot substitute:
  ``test_raw_and_standardized_impulse_stay_distinct_units``,
  ``test_raw_z_value_swap_with_units_intact_is_refused`` (the RED->GREEN case: before the
  raw-unit label re-derivation in the adapter, a VALUE swap with the unit strings left
  intact was accepted), plus the unit/field-name swap refusals in
  ``tests/test_liquidity_lab_adapter.py`` (~L66-80).
* C10 a correction is an amendment to first-known truth -- ALREADY pinned, cited only:
  ``tests/test_liquidity_lab_adapter.py::test_synthetic_adapter_event_registry_retry_and_correction``
  (~L294: create -> duplicate replay -> amend -> first-known retained) and
  ``tests/test_liquidity_lab_ledgers.py`` (~L64: keep-first + append-only amendment).
* C13 every authority mode stays financially inert:
  ``test_every_mode_is_inert_and_projects_identical_shared_facts``; see also
  ``tests/test_liquidity_transmission.py::TestAuthorityLadder::test_every_mode_is_inert_this_wave``
  (~L459) and ``TestZeroDecisionEffect`` (~L539).
* C14 same-clock conflicts fail closed, exact replay is idempotent, a stale gap cannot
  reset state -- through ADAPTER-DERIVED refs rather than hand-built ones:
  ``test_adapter_refs_conflicting_same_clock_fail_closed``,
  ``test_adapter_refs_exact_replay_is_idempotent``,
  ``test_adapter_refs_stale_low_reading_cannot_reset_episode`` (synthetic-ref versions
  live in ``tests/test_liquidity_lab_eventization.py`` ~L82-L135).
* Shared facts and family swaps:
  ``test_reader_and_adapter_share_the_evidence_and_known_clocks``,
  ``test_confidence_is_data_lineage_only_on_both_sides``,
  ``test_direction_vocabulary_is_liquidity_not_risk``,
  ``test_predictive_confidence_kind_is_refused_by_adapter``,
  ``test_risk_words_as_direction_are_refused_or_degraded``,
  ``test_warmup_zero_and_null_permutations_agree``.

Two clocks, two questions (B1).  Both sides bind the SAME producer clocks:
``observed_at`` = ``evidence_available_at`` and ``known_at`` = ``first_known_at``.  What
they derive from them differs on purpose: the reader's ``stale``/``age_days`` is the LIVE
age of ``evidence_available_at`` against the reader's own wall clock, while the adapter's
``freshness`` is the producer's status AT ``first_known_at``.  Neither upgrades the other,
so this module asserts clock identity and never forces the two freshness verdicts equal.

Reader-owned gaps pinned here as CURRENT behaviour (never edited from this module): the
reader has no flat-band check, so it reports a raw<->z value swap verbatim under the
unchanged unit strings; and it echoes ``quality.confidence.kind`` verbatim, including a
predictive kind the adapter refuses.  Its plane stays inert either way.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import itertools
import json
from pathlib import Path
import unittest.mock as mock

import pytest

from brain.liquidity_lab.adapter import (
    QUALITY_LABELS,
    RAW_UNIT,
    STATE_LABELS,
    Z_UNIT,
    adapt_producer_state,
)
from brain.liquidity_lab.contracts import ContractError
from brain.liquidity_lab.eventization import EventizationPolicy, eventize

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "liquidity_lab" / "glt_producer_20260904.json"
READER_FIXTURE = FIXTURES / "global_liquidity_transmission.json"
CUTOFF = datetime(2026, 9, 4, 12, tzinfo=timezone.utc)
RAW_BYTES = FIXTURE.read_bytes()

RISK_WORDS = ("risk_on", "risk_off", "neutral", "bullish", "bearish",
              "long", "short", "buy", "sell")
SHARED_FACTS = ("observed_at", "known_at", "magnitude", "magnitude_unit", "magnitude_z",
                "magnitude_z_unit", "confidence", "confidence_kind", "direction_label",
                "direction_sign", "quality")
POLICY = EventizationPolicy(2.0, 0.5, 0.8, 0.5, 10, 5)


def doc() -> dict:
    return json.loads(RAW_BYTES)


def dump(payload: dict) -> bytes:
    return json.dumps(payload).encode()


def adapt(payload: dict):
    return adapt_producer_state(deepcopy(payload), as_of=CUTOFF)


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class _FakeDatetime(datetime):
    """The reader's wall clock pinned to CUTOFF (mirrors tests/test_liquidity_transmission.py)."""

    @classmethod
    def now(cls, tz=None):
        return CUTOFF if tz is None else CUTOFF.astimezone(tz)


@pytest.fixture()
def reader(monkeypatch, tmp_path):
    """Point the sole reader at the fixture (None) or at mutated bytes, clock pinned."""
    import brain.liquidity_transmission as GLT

    monkeypatch.delenv("MASTERMIND_GLT_MODE", raising=False)
    counter = itertools.count()

    def point(raw: bytes | None = None):
        path = FIXTURE
        if raw is not None:
            path = tmp_path / f"glt_{next(counter)}.json"
            path.write_bytes(raw)
        monkeypatch.setattr(GLT, "_ARTIFACT_PATH", path)
        GLT._reset_context_cache()
        return GLT

    with mock.patch.object(GLT, "datetime", _FakeDatetime):
        yield point
    GLT._reset_context_cache()


def test_lab_fixture_is_byte_identical_to_reader_fixture():
    assert RAW_BYTES == READER_FIXTURE.read_bytes()


def test_reader_and_adapter_share_the_evidence_and_known_clocks(reader):
    payload = doc()
    plane = reader().market_plane()
    ref = adapt(payload)
    clocks = payload["state"]["event_reference"]["clocks"]
    assert clocks == payload["freshness"]["clocks"]
    assert plane["status"] == "present"
    assert _ts(plane["observed_at"]) == ref.observed_at == _ts(clocks["evidence_available_at"])
    assert _ts(plane["known_at"]) == ref.known_at == _ts(clocks["first_known_at"])
    assert plane["observed_date"] == ref.observed_at.date().isoformat() == "2026-08-28"
    # two clocks, two questions: live age (reader) vs producer status at first-known (adapter)
    assert plane["stale"] is False and 0 < plane["age_days"] < 10
    assert ref.freshness == payload["freshness"]["status"] == "fresh"


def test_raw_and_standardized_impulse_stay_distinct_units(reader):
    payload = doc()
    plane = reader().market_plane()
    ref = adapt(payload)
    state = payload["state"]
    assert plane["magnitude"] == state["monetary_impulse"] == state["event_reference"]["magnitude"]
    assert plane["magnitude_unit"] == RAW_UNIT == state["units"]["monetary_impulse"]
    assert plane["magnitude_z"] == ref.magnitude_z == state["monetary_impulse_z"]
    assert plane["magnitude_z_unit"] == Z_UNIT == state["units"]["monetary_impulse_z"]
    assert RAW_UNIT != Z_UNIT
    assert plane["magnitude"] != plane["magnitude_z"]
    assert ref.magnitude_z != plane["magnitude"]


def test_confidence_is_data_lineage_only_on_both_sides(reader):
    payload = doc()
    plane = reader().market_plane()
    ref = adapt(payload)
    confidence = payload["quality"]["confidence"]
    assert plane["confidence"] == ref.confidence == confidence["value"]
    assert plane["confidence_kind"] == confidence["kind"] == "data_lineage_and_coverage_only"
    assert "predictive_probability" in confidence["not"]


def test_direction_vocabulary_is_liquidity_not_risk(reader):
    payload = doc()
    plane = reader().market_plane()
    ref = adapt(payload)
    assert plane["direction_label"] in STATE_LABELS
    assert plane["direction_label"] == payload["state"]["label"] == "flat"
    assert plane["direction_sign"] == ref.direction == 1
    assert plane["quality"] in QUALITY_LABELS and plane["quality"] == ref.quality
    assert set(STATE_LABELS) & set(QUALITY_LABELS) == {"unknown"}
    strings = {value for value in plane.values() if isinstance(value, str)}
    assert not strings & set(RISK_WORDS)


@pytest.mark.parametrize("mode", ["off", "shadow", "display", "candidacy", "context",
                                  "vote", "garbled"])
def test_every_mode_is_inert_and_projects_identical_shared_facts(reader, monkeypatch, mode):
    glt = reader()
    baseline_plane = glt.market_plane()
    assert baseline_plane["mode"] == "shadow"
    baseline = {key: baseline_plane[key] for key in SHARED_FACTS}
    monkeypatch.setenv("MASTERMIND_GLT_MODE", mode)
    glt._reset_context_cache()
    plane = glt.market_plane()
    assert plane["mode"] == ("off" if mode == "garbled" else mode)
    assert {key: plane[key] for key in SHARED_FACTS} == baseline
    assert glt.target("SPY") == {}
    assert glt.opportunities() == []
    signals = glt.decision_signals("SPY")
    assert (signals["candidacy"], signals["tilt"], signals["size_multiplier"],
            signals["vote"]) == (None, None, None, None)
    assert signals["inert"] is True
    assert plane["decision_effect"] == "none" and plane["signs_posture"] is False


def _swap_raw_and_z(payload: dict) -> dict:
    state, event = payload["state"], payload["state"]["event_reference"]
    state["monetary_impulse"], state["monetary_impulse_z"] = (
        state["monetary_impulse_z"], state["monetary_impulse"])
    event["magnitude"], event["magnitude_z"] = event["magnitude_z"], event["magnitude"]
    return payload


def test_raw_z_value_swap_with_units_intact_is_refused(reader):
    original = doc()
    swapped = _swap_raw_and_z(doc())
    assert swapped["state"]["units"] == original["state"]["units"]
    assert swapped["state"]["event_reference"]["magnitude_unit"] == RAW_UNIT
    with pytest.raises(ContractError, match="raw-unit direction label"):
        adapt(swapped)
    # Reader-owned GAP, pinned as current behaviour: no flat-band check, so it reports the
    # swapped values under the unchanged unit strings (still inert).
    plane = reader(dump(swapped)).market_plane()
    assert plane["status"] == "present"
    assert plane["magnitude"] == original["state"]["monetary_impulse_z"]
    assert plane["magnitude_unit"] == RAW_UNIT
    assert plane["decision_effect"] == "none"


@pytest.mark.parametrize("kind", ["predictive_probability", "alpha_confidence",
                                  "promotion_grade", "probability", "hit_rate"])
def test_predictive_confidence_kind_is_refused_by_adapter(reader, kind):
    payload = doc()
    payload["quality"]["confidence"]["kind"] = kind
    with pytest.raises(ContractError, match="confidence semantics"):
        adapt(payload)
    # Reader-owned GAP, pinned as current behaviour: the kind is echoed verbatim.
    plane = reader(dump(payload)).market_plane()
    assert plane["status"] == "present"
    assert plane["confidence_kind"] == kind
    assert plane["decision_effect"] == "none" and plane["signs_posture"] is False


@pytest.mark.parametrize("word", ["risk_on", "risk_off", "bullish", "bearish",
                                  "long", "short", "buy", "sell"])
def test_risk_words_as_direction_are_refused_or_degraded(reader, word):
    payload = doc()
    payload["state"]["label"] = word
    payload["state"]["event_reference"]["direction_label"] = word
    with pytest.raises(ContractError, match="direction_label vocabulary"):
        adapt(payload)
    plane = reader(dump(payload)).market_plane()
    assert plane["status"] == "present"
    assert plane["direction_label"] == "unknown"


def _warmup(payload: dict) -> None:
    state, event = payload["state"], payload["state"]["event_reference"]
    state["monetary_impulse_z"] = event["magnitude_z"] = None


def _zero_raw(payload: dict) -> None:
    state, event = payload["state"], payload["state"]["event_reference"]
    state["monetary_impulse"] = event["magnitude"] = 0.0
    event["direction"] = None
    assert state["label"] == "flat"


def _null_raw(payload: dict) -> None:
    state, event = payload["state"], payload["state"]["event_reference"]
    state["monetary_impulse"] = event["magnitude"] = None
    event["direction"] = None


@pytest.mark.parametrize("mutate,magnitude,magnitude_z,sign", [
    (_warmup, 0.003956, None, 1),
    (_zero_raw, 0.0, 0.077032, None),
    (_null_raw, None, 0.077032, None),
], ids=["warmup", "zero_raw", "null_raw"])
def test_warmup_zero_and_null_permutations_agree(reader, mutate, magnitude, magnitude_z, sign):
    payload = doc()
    mutate(payload)
    assert adapt(payload) is None
    plane = reader(dump(payload)).market_plane()
    assert plane["status"] == "present"
    assert plane["magnitude"] == magnitude
    assert plane["magnitude_z"] == magnitude_z
    assert plane["direction_sign"] == sign
    assert plane["magnitude_unit"] == RAW_UNIT and plane["magnitude_z_unit"] == Z_UNIT


def _material(z: float):
    payload = doc()
    payload["state"]["monetary_impulse_z"] = payload["state"]["event_reference"]["magnitude_z"] = z
    return adapt(payload)


def test_adapter_refs_conflicting_same_clock_fail_closed():
    first, second = _material(3.0), _material(3.5)
    assert (first.observed_at, first.known_at) == (second.observed_at, second.known_at)
    for inputs in ([first, second], [second, first]):
        with pytest.raises(ContractError, match="conflicting.*observation"):
            eventize(inputs, POLICY)


def test_adapter_refs_exact_replay_is_idempotent():
    ref = _material(3.0)
    once = [event.to_dict() for event in eventize([ref], POLICY)]
    assert len(once) == 1
    assert _material(3.0) == ref
    assert [event.to_dict() for event in eventize([ref, ref], POLICY)] == once
    assert [event.to_dict() for event in eventize([ref, ref, ref], POLICY)] == once


def test_adapter_refs_stale_low_reading_cannot_reset_episode():
    policy = EventizationPolicy(2.0, 0.5, 0.8, 0.5, 10, 0)
    first = _material(3.0)

    def later(ref, days: int, **changes):
        shift = timedelta(days=days)
        return replace(ref, observed_at=ref.observed_at + shift,
                       known_at=ref.known_at + shift, **changes)

    trusted_low = later(first, 4, magnitude_z=0.1)
    stale_low = later(first, 4, magnitude_z=0.1, freshness="stale")
    again = later(first, 6, magnitude_z=3.2)
    # control: a trusted low reading does reset, so the next material point re-mints
    assert len(eventize([first, trusted_low, again], policy)) == 2
    # a stale low reading cannot reset the episode
    events = eventize([first, stale_low, again], policy)
    assert [event.first_detected for event in events] == [first.known_at]
