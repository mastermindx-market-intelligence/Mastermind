"""Portfolio risk/rotation integration: synthetic source, real reader and consumers.

No production capture, LLM call, new evidence vote, or sizing-policy change.
"""
from __future__ import annotations

import copy
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from brain import neural_web_context as NWC

_FIXTURES = Path(__file__).parent / "fixtures"
_NOW = datetime(2026, 10, 8, 15, tzinfo=timezone.utc)
_SESSION = "2026-10-06"


class _Date(date):
    @classmethod
    def today(cls):
        return _NOW.date()


class _DateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return _NOW if tz else _NOW.replace(tzinfo=None)


@pytest.fixture
def envelope():
    return json.loads((_FIXTURES / "rotation_risk_envelope.json").read_text())


@pytest.fixture
def bridge(monkeypatch, tmp_path):
    monkeypatch.setattr(NWC, "date", _Date)
    monkeypatch.setattr(NWC, "datetime", _DateTime)
    monkeypatch.setenv("MASTERMIND_NW_CONTEXT", "1")
    path = tmp_path / "mastermind_context.json"
    monkeypatch.setattr(NWC, "_ARTIFACT_PATH", path)

    def write(envelope=None):
        raw = json.loads((_FIXTURES / "mastermind_context.json").read_text())
        raw["as_of"] = "2026-10-08"  # Deliberately fresher than the nested source.
        raw["generated_utc"] = "2026-10-08T14:59:00Z"
        for name, lobe in raw["lobes"].items():
            if isinstance(lobe, dict):
                lobe["as_of"] = _SESSION
            raw.setdefault("freshness", {})[name] = {"as_of": _SESSION, "stale": False}
        if envelope is not None:
            raw["lobes"]["market"]["risk_envelope"] = copy.deepcopy(envelope)
        else:
            raw["lobes"]["market"].pop("risk_envelope", None)
        path.write_text(json.dumps(raw))
        NWC._reset_context_cache()
        return raw

    yield write
    NWC._reset_context_cache()


def test_actual_composer_fixture_reaches_reader_with_clocks_and_native_overlap(bridge, envelope):
    bridge(envelope)
    plane = NWC.market_plane()
    native = plane["risk_envelope"]
    assert plane["stale"] is False
    assert plane["risk_envelope_status"]["qualified"] is True
    assert native["schema"] == "mastermind.risk_envelope/v1"
    assert native["source_session"] == _SESSION
    assert native["observed_at"] == "2026-10-07T12:00:00Z"
    assert native["produced_at"] != NWC.context()["generated_utc"]
    assert native["measured_state"] == envelope["measured_state"]
    assert native["rotation_context"]["early_context"]["as_of"] == _SESSION
    assert native["rotation_context"]["confirmed_events"]["as_of"] == "2026-09-25"
    assert native["rotation_context"]["confirmed_events"]["usable"] is False
    assert native["confluence"]["nonredundant_component_count"] is None
    assert ["market-state-latest", "site-marketdata-rotation-events"] in native["confluence"]["nonredundant_components"]
    assert native["authority"] == envelope["authority"]
    assert native["market_transition"]["latest_recorded_change"]["after"]["asof"] == "2026-09-30"
    # A consumer mutation cannot change the process-cached bridge.
    native["measured_state"]["score"] = 0
    assert NWC.market_plane()["risk_envelope"]["measured_state"]["score"] == 51


@pytest.mark.parametrize(("field", "value", "reason"), [
    ("schema", "unknown/v2", "invalid_schema"),
    ("source_session", None, "invalid_future_or_expired_session"),
    ("source_session", "2026-10-6", "invalid_future_or_expired_session"),
    ("source_session", "2026-10-09", "invalid_future_or_expired_session"),
    ("source_session", "2026-09-29", "invalid_future_or_expired_session"),
    ("source_session", "2026-10-07", "source_session_mismatch"),
    ("as_of", "2026-10-07", "source_session_mismatch"),
    ("observed_at", None, "missing_or_invalid_observed_at"),
    ("observed_at", "2026-10-08T14:00:00", "missing_or_invalid_observed_at"),
    ("observed_at", "2026-10-09T01:00:00Z", "future_observed_at"),
    ("observed_at", "2026-10-05T01:00:00Z", "observation_before_source_session"),
    ("produced_at", "2026-10-09T01:00:00Z", "future_produced_at"),
    ("produced_at", "2026-10-07T11:00:00Z", "incoherent_publication_clocks"),
    ("stale_after", "invalid", "invalid_or_expired_envelope"),
    ("stale_after", "2026-10-08T14:59:59Z", "invalid_or_expired_envelope"),
    ("revision", "future_revision", "invalid_revision"),
    ("data_state", "STALE", "unusable_data_state"),
    ("bundle_id", "", "missing_bundle_id"),
    ("measured_state", [], "invalid_measured_state"),
    ("hazard_summary", "NONE", "invalid_hazard_summary"),
    ("policy_summary", [], "invalid_policy_summary"),
    ("stale", True, "owner_stale"),
])
def test_fresh_wrapper_does_not_launder_invalid_inner_source(bridge, envelope, field, value, reason):
    envelope[field] = value
    bridge(envelope)
    plane = NWC.market_plane()
    assert plane["stale"] is False  # Other market evidence remains unchanged.
    assert plane["risk_envelope"] is None
    assert reason in plane["risk_envelope_status"]["reasons"]
    assert "Risk/rotation context unavailable" in NWC.seat_prompt_block(["NVDA"])


@pytest.mark.parametrize("field", ("measured_state", "freshness"))
def test_nested_session_mismatch_rejected(bridge, envelope, field):
    envelope[field]["as_of" if field == "measured_state" else "source_session"] = "2026-10-07"
    bridge(envelope)
    assert NWC.market_plane()["risk_envelope"] is None


def test_generated_utc_alias_cannot_replace_canonical_inner_clock(bridge, envelope):
    envelope["generated_utc"] = envelope.pop("observed_at")
    bridge(envelope)
    assert "missing_or_invalid_observed_at" in NWC.market_plane()["risk_envelope_status"]["reasons"]


@pytest.mark.parametrize("field", NWC._RISK_AUTHORITY_FLAGS)
def test_no_authority_escalation(bridge, envelope, field):
    envelope["authority"][field] = True
    bridge(envelope)
    assert NWC.market_plane()["risk_envelope"] is None


@pytest.mark.parametrize("field", ("statistical_independence_established", "changes_hazard_stage", "changes_policy"))
def test_confluence_cannot_grant_independence_or_authority(bridge, envelope, field):
    envelope["confluence"][field] = True
    bridge(envelope)
    assert "invalid_confluence_authority" in NWC.market_plane()["risk_envelope_status"]["reasons"]


def test_live_expiry_required_and_rechecked_after_cache_load(bridge, envelope, monkeypatch):
    envelope["revision"] = "live_provisional"
    bridge(envelope)
    assert "missing_live_expiry" in NWC.market_plane()["risk_envelope_status"]["reasons"]
    envelope["stale_after"] = "2026-10-08T15:01:00Z"
    bridge(envelope)
    cached = NWC.context()
    assert NWC.market_plane()["risk_envelope_status"]["qualified"] is True

    class Later(_DateTime):
        @classmethod
        def now(cls, tz=None):
            return _NOW + timedelta(minutes=2)

    monkeypatch.setattr(NWC, "datetime", Later)
    assert NWC.context() is cached
    assert NWC.market_plane()["risk_envelope"] is None
    assert "invalid_or_expired_envelope" in NWC.market_plane()["risk_envelope_status"]["reasons"]


def test_optional_stale_rotation_does_not_erase_qualified_backdrop(bridge, envelope):
    rotation = envelope["rotation_context"]
    rotation.update(state=None, usable=False, coverage="STALE", as_of="2026-09-25", excluded_reason="off_session")
    envelope["confluence"].update(state="ROTATION_UNAVAILABLE", rotation_state=None)
    envelope["freshness"].update(all_on_session=False, off_session_sources=["site-marketdata-rotation-events"])
    bridge(envelope)
    result = NWC.market_plane()["risk_envelope"]
    assert result["measured_state"]["score"] == 51
    assert result["hazard_summary"] == envelope["hazard_summary"]
    assert result["rotation_context"]["usable"] is False
    assert result["freshness"]["all_on_session"] is False
    assert "Early rotation: unavailable" in NWC.seat_prompt_block([])


def test_mismatched_optional_rotation_is_excluded_without_erasing_backdrop(bridge, envelope):
    envelope["rotation_context"]["early_context"]["as_of"] = "2026-10-09"
    bridge(envelope)
    result = NWC.market_plane()
    assert result["risk_envelope"]["measured_state"]["score"] == 51
    assert result["risk_envelope"]["rotation_context"] is None
    assert result["risk_envelope"]["confluence"] is None
    assert "rotation_context" in result["risk_envelope_status"]["context_exclusions"]


def test_missing_optional_transition_stays_unknown(bridge, envelope):
    envelope.pop("market_transition")
    bridge(envelope)
    assert NWC.market_plane()["risk_envelope_status"]["qualified"] is True
    assert "Recorded market transition unavailable." in NWC.seat_prompt_block([])


def test_nonfinite_or_oversize_context_is_explicitly_unavailable(bridge, envelope):
    envelope["measured_state"]["score"] = float("nan")
    bridge(envelope)
    assert "invalid_json_values" in NWC.market_plane()["risk_envelope_status"]["reasons"]
    envelope["measured_state"]["score"] = 51
    envelope["rotation_context"]["extra_detail"] = "x" * 32768
    bridge(envelope)
    assert "context_size_limit" in NWC.market_plane()["risk_envelope_status"]["reasons"]


@pytest.mark.parametrize(("state", "label"), [
    ("BROADENING", "Broader-market proxies gaining relative strength"),
    ("MIXED_ROTATION", "Defensive groups and broader-market proxies gaining relative strength"),
    ("DEFENSIVE_RELATIVE_STRENGTH", "Defensive relative strength"),
])
def test_prompt_preserves_proxy_semantics_and_excludes_prose(bridge, envelope, state, label):
    envelope["rotation_context"]["state"] = state
    envelope["rotation_context"]["early_context"]["state"] = state
    pair = envelope["rotation_context"]["early_context"]["pairs"][0]
    pair["horizons"]["2s"].update(shape="BOTH_DOWN", numerator_return_pct=-1, denominator_return_pct=-3)
    pair["interpretation"] = "RELATIVE_RESILIENCE"
    envelope["confluence"]["rotation_state"] = state
    envelope["provenance"]["memo"] = "RISK_PROSE_SENTINEL"
    envelope["cortex"] = "CORTEX_SENTINEL_XYZ"
    bridge(envelope)
    text = NWC.seat_prompt_block(["NVDA"], max_chars=1200)
    assert len(text) <= 1200
    assert label in text
    assert "no extra evidence vote or sizing authority" in text
    assert "statistical independence is not established" in text
    assert "Relative prices do not establish fund flows." in text
    assert "2026-09-29 -> MIXED 2026-09-30" in text
    assert "broader participation" not in text.lower()
    assert "RISK_PROSE_SENTINEL" not in text
    assert "CORTEX_SENTINEL_XYZ" not in text
    assert "RISK_PROSE_SENTINEL" not in json.dumps(NWC.market_plane())


@pytest.mark.parametrize("mode", ("off", "shadow", "candidacy", "shrink", "vote"))
def test_every_existing_decision_mode_is_invariant(bridge, envelope, monkeypatch, mode):
    monkeypatch.setenv("MASTERMIND_NW_DECISION", mode)
    bridge()
    before = {ticker: NWC.decision_signals(ticker) for ticker in ("NVDA", "AMD", "UNKNOWN")}
    plane_before = NWC.market_plane()
    bridge(envelope)
    after = {ticker: NWC.decision_signals(ticker) for ticker in before}
    assert after == before
    assert NWC.market_plane()["contradiction_count"] == plane_before["contradiction_count"]


def test_actual_strategist_payload_receives_qualified_context(bridge, envelope, monkeypatch):
    from brain import strategist as S, decision_context as DC, pm_conviction as PM
    bridge(envelope)
    monkeypatch.setattr(S, "_load", lambda *_: {})
    monkeypatch.setattr(DC, "prompt_summary", lambda: {})
    monkeypatch.setattr(PM, "_read_market_view", lambda: None)
    payload = S._strategist_input({"quad": 1, "quad_name": "Goldilocks"}, _SESSION)
    context = payload["neural_web_context"]
    assert context["risk_envelope"]["source_session"] == _SESSION
    assert "candidate_context" not in context
    assert len(json.dumps(payload)) < 24000
    monkeypatch.setenv("MASTERMIND_NW_CONTEXT", "0")
    assert S._strategist_input({"quad": 1}, _SESSION)["neural_web_context"] == {}


def test_actual_pm_prompt_receives_descriptive_context_and_flag_boundary(bridge, envelope, monkeypatch):
    from brain import pm_conviction as PM
    bridge(envelope)
    monkeypatch.setattr(PM, "_read_market_view", lambda: None)
    payload = PM._pm_input(
        [{"ticker": "NVDA", "weight": 0.06, "sleeve": "conviction", "confluence": 0.7,
          "thesis": "synthetic test", "retained": False}],
        [], {"confirmed_themes": [], "backdrop_stance": "neutral", "supportive": True,
             "crowding_flags": []}, {"quad": 1, "quad_name": "Goldilocks"}, {},
        _SESSION, leadership=[], defensive=[],
    )
    before = copy.deepcopy(payload)
    prompt = PM._build_prompt(payload)
    assert "NEURAL WEB CONTEXT" in prompt
    assert "Early rotation: Defensive relative strength" in prompt
    assert "no extra evidence vote or sizing authority" in prompt
    assert payload == before
    monkeypatch.setenv("MASTERMIND_NW_CONTEXT", "0")
    assert "NEURAL WEB CONTEXT" not in PM._build_prompt(payload)


def test_actual_market_view_keeps_context_inside_one_advisory_plane(bridge, envelope, monkeypatch):
    from brain import market_view as MV, regime_frame as RF
    monkeypatch.setitem(RF._REGION_PATHS, "us", _FIXTURES / "market_view" / "regime_snapshot_incident.json")
    monkeypatch.setattr(RF, "_CYCLES_PATH", _FIXTURES / "market_view" / "sector_cycles_incident.json", raising=False)
    monkeypatch.setattr(RF, "_trading_days_since", lambda *_: 0, raising=False)
    bridge()
    before = MV.view("us", neural_web_out=NWC.market_plane())
    bridge(envelope)
    after = MV.view("us", neural_web_out=NWC.market_plane())
    rec = after["planes"]["neural_web"]
    assert rec["status"] == "advisory"
    assert rec["raw"]["risk_envelope"]["source_session"] == _SESSION
    assert rec["raw"]["risk_envelope_status"]["qualified"] is True
    assert list(after["planes"]) == list(before["planes"])
    assert after["net_posture_tilt"] == before["net_posture_tilt"]
    assert "neural_web" not in after["net_posture_tilt"]["contributors"]
    for key in ("direction", "magnitude", "confidence", "reading", "status"):
        assert rec.get(key) == before["planes"]["neural_web"].get(key)


@pytest.mark.parametrize(("field", "value"), [
    ("state", "UNKNOWN_ROTATION"),
    ("state", []),
])
def test_unknown_optional_rotation_state_cannot_poison_other_context(bridge, envelope, field, value):
    envelope["rotation_context"][field] = value
    bridge(envelope)
    result = NWC.market_plane()["risk_envelope"]
    assert result["measured_state"]["score"] == 51
    assert result["rotation_context"] is None
    assert "Early rotation: unavailable" in NWC.seat_prompt_block([])


def test_partial_lineage_cannot_supply_a_known_nonredundant_total(bridge, envelope):
    envelope["confluence"]["nonredundant_component_count"] = 3
    bridge(envelope)
    result = NWC.market_plane()
    assert result["risk_envelope"]["measured_state"]["score"] == 51
    assert result["risk_envelope"]["confluence"] is None
    assert result["risk_envelope_status"]["context_exclusions"]["confluence"] == "incomplete_lineage_count"


@pytest.mark.parametrize(("field", "value"), [
    ("asof", "2026-10-09"),
    ("logged_at", "2026-10-09T01:00:00Z"),
    ("logged_at", "2026-09-30T01:00:00"),
])
def test_future_or_malformed_history_receipt_is_never_presented_as_recorded(bridge, envelope, field, value):
    envelope["market_transition"]["latest_recorded_change"]["after"][field] = value
    bridge(envelope)
    result = NWC.market_plane()
    assert result["risk_envelope"]["measured_state"]["score"] == 51
    assert result["risk_envelope"]["market_transition"] is None
    assert "Recorded market transition unavailable." in NWC.seat_prompt_block([])


def test_unknown_record_basis_does_not_become_first_writer_proof(bridge, envelope):
    envelope["market_transition"]["basis"] = "recomputed_snapshot"
    bridge(envelope)
    assert NWC.market_plane()["risk_envelope"]["market_transition"] is None


def test_settled_session_ages_out_even_when_outer_context_is_cached(bridge, envelope, monkeypatch):
    bridge(envelope)
    cached = NWC.context()
    assert NWC.market_plane()["risk_envelope"] is not None

    class Later(_DateTime):
        @classmethod
        def now(cls, tz=None):
            return _NOW + timedelta(days=5)

    monkeypatch.setattr(NWC, "datetime", Later)
    assert NWC.context() is cached
    assert NWC.market_plane()["risk_envelope"] is None
    assert "invalid_future_or_expired_session" in NWC.market_plane()["risk_envelope_status"]["reasons"]


def test_actual_research_evidence_block_keeps_existing_entry_decision(bridge, envelope):
    from brain import research_paper as RP
    bridge(envelope)
    text = RP.build_evidence_block(
        "WMT", entry_report={"verdict": "WAIT"}, context_report=None, prophet_line=None,
    )
    assert "Early rotation: Defensive relative strength" in text
    assert "no extra evidence vote or sizing authority" in text
    assert "WAIT" in text
    assert "CORTEX_SENTINEL_XYZ" not in text
    # Existing early return stays unchanged: NW context is not an independent
    # reason to originate a research entry or supply an additional evidence vote.
    assert RP.build_evidence_block(
        "WMT", entry_report=None, context_report=None, prophet_line=None,
    ) == RP._NO_EVIDENCE_MARKER


def _replace_bridge(raw):
    """Use the source owner's atomic publication shape; never reset reader cache."""
    path = NWC._ARTIFACT_PATH
    replacement = path.with_suffix(".replacement")
    replacement.write_text(json.dumps(raw))
    replacement.replace(path)


def test_us_session_day_uses_new_york_before_utc_midnight_boundary(envelope):
    envelope.update(source_session="2026-10-09", as_of="2026-10-09",
                    observed_at="2026-10-09T00:30:00Z", produced_at="2026-10-09T00:31:00Z",
                    rotation_context=None, confluence=None, market_transition=None)
    envelope["measured_state"]["as_of"] = "2026-10-09"
    envelope["freshness"]["source_session"] = "2026-10-09"
    native, status = NWC._risk_envelope_context(
        envelope, "2026-10-09", now=datetime(2026, 10, 9, 1, tzinfo=timezone.utc),
    )
    assert native is None
    assert "invalid_future_or_expired_session" in status["reasons"]
    # The UTC date may advance while the actual US observation session remains Oct8.
    envelope.update(source_session="2026-10-08", as_of="2026-10-08")
    envelope["measured_state"]["as_of"] = "2026-10-08"
    envelope["freshness"]["source_session"] = "2026-10-08"
    native, status = NWC._risk_envelope_context(
        envelope, "2026-10-08", now=datetime(2026, 10, 9, 1, tzinfo=timezone.utc),
    )
    assert status["qualified"] is True
    assert native["source_session"] == "2026-10-08"


def test_observation_cannot_precede_its_new_york_source_session(envelope):
    envelope.update(observed_at="2026-10-06T00:30:00Z", produced_at="2026-10-06T00:31:00Z")
    native, status = NWC._risk_envelope_context(envelope, _SESSION, now=_NOW)
    assert native is None
    assert "observation_before_source_session" in status["reasons"]


@pytest.mark.parametrize(("alias", "value"), [
    ("as_of", "2026-10-09"),
    ("source_session", "2026-10-09"),
    ("observed_at", "2026-10-10T01:00:00Z"),
    ("produced_at", "2026-10-10T01:00:00Z"),
    ("available_at", "2026-10-10T01:00:00Z"),
    ("generated_utc", "2026-10-10T01:00:00Z"),
    ("generated_utc", "2026-10-10 01:00:00"),
])
def test_all_present_native_history_date_and_clock_aliases_are_qualified(bridge, envelope, alias, value):
    envelope["market_transition"]["current_snapshot"][alias] = value
    bridge(envelope)
    result = NWC.market_plane()
    assert result["stale"] is False
    assert result["risk_envelope"]["measured_state"]["score"] == 51
    assert result["risk_envelope"]["market_transition"] is None
    assert "Recorded market transition unavailable." in NWC.seat_prompt_block([])


@pytest.mark.parametrize("clock", ("observed_at", "produced_at", "stale_after"))
def test_extreme_optional_clock_does_not_change_legacy_decision_eligibility(bridge, envelope, monkeypatch, clock):
    monkeypatch.setenv("MASTERMIND_NW_DECISION", "vote")
    raw = bridge(envelope)
    raw["lobes"]["contradictions"]["records"] = [{}, {}, {}]
    raw["candidate_context"]["NVDA"]["graph_conflicts"] = []
    raw["candidate_context"]["NVDA"]["kernel"]["fdr_cleared"] = True
    _replace_bridge(raw)
    before = NWC.decision_signals("NVDA")
    assert before["clean_in_conflicted"] is True
    raw["lobes"]["market"]["risk_envelope"][clock] = "9999-12-31T23:00:00-02:00"
    _replace_bridge(raw)
    plane = NWC.market_plane()
    assert plane["stale"] is False
    assert plane["risk_envelope"] is None
    assert NWC.decision_signals("NVDA") == before


def test_unexpected_optional_qualification_failure_is_isolated(bridge, envelope, monkeypatch):
    bridge(envelope)
    before = NWC.market_plane()
    signals = NWC.decision_signals("NVDA")

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic optional-reader fault")

    monkeypatch.setattr(NWC, "_qualify_risk_envelope_context", fail)
    after = NWC.market_plane()
    assert after["stale"] is False
    assert after["verdict"] == before["verdict"]
    assert after["contradiction_count"] == before["contradiction_count"]
    assert after["risk_envelope_status"]["reasons"] == ["invalid_envelope"]
    assert NWC.decision_signals("NVDA") == signals
    assert "Risk/rotation context unavailable" in NWC.seat_prompt_block([])


def test_atomic_replacement_becomes_visible_without_cache_reset(bridge, envelope):
    raw = bridge(envelope)
    cached = NWC.context()
    assert NWC.market_plane()["risk_envelope"]["bundle_id"] == envelope["bundle_id"]
    raw["lobes"]["market"]["risk_envelope"].update(
        bundle_id="replacement-current-source", produced_at="2026-10-08T14:59:00Z",
    )
    _replace_bridge(raw)
    after = NWC.market_plane()
    assert NWC.context() is not cached
    assert after["risk_envelope"]["bundle_id"] == "replacement-current-source"
    assert after["risk_envelope"]["observed_at"] == envelope["observed_at"]


def test_deleted_then_present_source_recovers_without_reset(bridge, envelope):
    raw = bridge(envelope)
    assert NWC.market_plane()["risk_envelope"] is not None
    NWC._ARTIFACT_PATH.unlink()
    assert NWC.context() == {}
    assert NWC.market_plane()["stale"] is True
    _replace_bridge(raw)
    assert NWC.market_plane()["risk_envelope"]["bundle_id"] == envelope["bundle_id"]


def test_malformed_replacement_cannot_keep_previous_bundle_fresh(bridge, envelope):
    raw = bridge(envelope)
    assert NWC.market_plane()["risk_envelope"] is not None
    replacement = NWC._ARTIFACT_PATH.with_suffix(".replacement")
    replacement.write_text("{malformed")
    replacement.replace(NWC._ARTIFACT_PATH)
    assert NWC.context() == {}
    assert NWC.market_plane()["stale"] is True
    _replace_bridge(raw)
    assert NWC.market_plane()["risk_envelope"]["bundle_id"] == envelope["bundle_id"]


def test_atomic_replacement_during_read_abstains_then_reads_coherent_source(bridge, envelope, monkeypatch):
    replacement_raw = bridge(envelope)
    replacement_raw["lobes"]["market"]["risk_envelope"]["bundle_id"] = "replacement-during-read"
    original_load = NWC._load_raw
    replaced = False

    def replace_during_read():
        nonlocal replaced
        raw = original_load()
        if not replaced:
            replaced = True
            _replace_bridge(replacement_raw)
        return raw

    monkeypatch.setattr(NWC, "_load_raw", replace_during_read)
    assert NWC.context() == {}  # No old bytes attributed to the replacement identity.
    assert NWC.market_plane()["risk_envelope"]["bundle_id"] == "replacement-during-read"


def test_cached_outer_source_expires_on_its_own_clock_without_file_change(bridge, envelope, monkeypatch):
    bridge(envelope)
    assert NWC.context()

    class LaterDate(_Date):
        @classmethod
        def today(cls):
            return date(2026, 10, 13)

    monkeypatch.setattr(NWC, "date", LaterDate)
    assert NWC.context() == {}
    assert NWC.market_plane()["stale"] is True


def test_concurrent_readers_never_pair_old_bytes_with_replacement_identity(bridge, envelope, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    raw = bridge(envelope)
    assert NWC.market_plane()["risk_envelope"]["bundle_id"] == envelope["bundle_id"]
    raw["lobes"]["market"]["risk_envelope"]["bundle_id"] = "concurrent-replacement"
    _replace_bridge(raw)
    entered, release, second_started, second_done = Event(), Event(), Event(), Event()
    original_load = NWC._load_raw

    def delayed_load():
        result = original_load()
        entered.set()
        assert release.wait(5)
        return result

    def second_read():
        second_started.set()
        try:
            return NWC.market_plane()
        finally:
            second_done.set()

    monkeypatch.setattr(NWC, "_load_raw", delayed_load)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(NWC.market_plane)
        assert entered.wait(5)
        second = pool.submit(second_read)
        assert second_started.wait(5)
        # Give a second reader the opportunity to encounter an in-flight refresh.
        second_done.wait(0.2)
        release.set()
        results = [first.result(timeout=5), second.result(timeout=5)]
    assert all(row["risk_envelope"]["bundle_id"] == "concurrent-replacement" for row in results)


def test_one_decision_uses_one_captured_generation_across_atomic_replacement(bridge, envelope, monkeypatch):
    monkeypatch.setenv("MASTERMIND_NW_DECISION", "vote")
    generation_a = bridge(envelope)
    generation_a["lobes"]["contradictions"]["records"] = [{}, {}, {}]
    generation_a["candidate_context"]["NVDA"]["bottom"] = {"bottom_state": "CONFIRMED"}
    generation_a["candidate_context"]["NVDA"]["graph_conflicts"] = []
    generation_a["candidate_context"]["NVDA"]["kernel"]["fdr_cleared"] = True
    generation_b = copy.deepcopy(generation_a)
    generation_b["freshness"]["reliability"]["stale"] = True
    generation_b["candidate_context"]["NVDA"]["bottom"] = {"bottom_state": "WATCH"}
    generation_b["candidate_context"]["NVDA"]["graph_conflicts"] = ["conflict1", "conflict2"]
    generation_b["lobes"]["market"]["risk_envelope"]["bundle_id"] = "generation-b"
    _replace_bridge(generation_a)
    reference_a = NWC.decision_signals("NVDA")
    assert reference_a["candidacy"]["score"] == 0.5
    assert reference_a["entry_shrink"] is None
    _replace_bridge(generation_b)
    reference_b = NWC.decision_signals("NVDA")
    assert reference_b["inert"] is True
    _replace_bridge(generation_a)
    original_candidate = NWC.candidate

    def publish_between_reads(ticker, **kwargs):
        _replace_bridge(generation_b)
        return original_candidate(ticker, **kwargs)

    monkeypatch.setattr(NWC, "candidate", publish_between_reads)
    # The old code produced WATCH/.35 plus shrink.7, neither coherent A nor B.
    # Binding the existing captured c returns A; the NEXT decision can read B.
    assert NWC.decision_signals("NVDA") == reference_a
    assert NWC.decision_signals("NVDA") == reference_b
