"""Rates evidence is context, never trading authority or a retroactive receipt."""
from copy import deepcopy
import json
import pytest
from brain import decision_context as DC

TENORS = ("2y", "5y", "10y", "20y", "30y")

def source():
    return {"schema": "rates_command.v1", "asof": "2026-09-16",
            "built": "2026-09-16T21:00:00Z", "yield_momentum": {
        "schema": "yield_momentum.v1", "asof": "2026-09-16", "series": {
            tenor: {"source_column": "us" + tenor, "status": "available",
                    "as_of": "2026-09-16", "available_at": "2026-09-16T20:00:00Z",
                    "level": 4.5, "velocity_bp": {"5d": 12.0, "22d": 20.0, "63d": 30.0},
                    "acceleration_bp": -8.0, "turn_watch": "extreme_high_watch"}
            for tenor in TENORS}}}

def context(artifact=None, cutoff=None, asof="2026-09-16"):
    return DC.assemble({"date": asof}, {}, neural_web={}, rates_command=artifact,
                       rates_cutoff=cutoff, built_at="2026-09-17T00:00:00Z")

def project(artifact=None, cutoff=None, asof="2026-09-16"):
    return context(artifact, cutoff, asof)["rates_evidence"]

def test_missing_rates_is_explicit():
    out = DC.assemble({"date": "2026-09-16"}, {}, neural_web={})
    assert "rates_evidence" in out
    assert out["rates_evidence"]["status"] == "unavailable"

def test_real_consumer_preserves_horizons_and_prompt_projection():
    out = context(source()); rates = out["rates_evidence"]
    assert rates["schema"] == "decision_context.rates_evidence.v1"
    assert set(rates["series"]) == set(TENORS)
    assert rates["series"]["10y"]["level"] == 4.5
    assert rates["series"]["10y"]["velocity_bp"]["5d"] == 12.0
    assert rates["series"]["10y"]["acceleration_bp"] == -8.0
    assert rates["horizon_basis"] == "source_frame_intervals"
    assert rates["level_unit"] == "percent"
    assert DC.prompt_summary(out)["rates_evidence"] == rates

def test_authority_cannot_be_inherited_from_input():
    a=source(); a.update(can_trade=True, can_size=True, authority=True)
    a["yield_momentum"].update(can_score=True, can_rank=True)
    out=project(a)
    assert out["authority"]["allowed_effect"] == "annotate_only"
    for key in ("can_rank", "can_score", "can_size", "can_gate", "can_trade"):
        assert out["authority"][key] is False
    assert out["as_observed_replay_certified"] is False

@pytest.mark.parametrize("clock", [None, "2026-09-16", "not-a-clock", "2026-09-16T20:00:00"])
def test_unknown_date_only_invalid_or_naive_clock_cannot_enter_cutoff_view(clock):
    a=source(); a["yield_momentum"]["series"]["10y"]["available_at"]=clock
    live=project(a); strict=project(a, "2026-09-16T22:00:00Z")
    assert live["series"]["10y"]["level"] == 4.5
    assert strict["series"]["10y"]["level"] is None
    assert strict["series"]["10y"]["usable_for_context"] is False
    assert strict["as_observed_replay_certified"] is False

def test_before_cutoff_is_inspectable_but_not_vintage_certified():
    out=project(source(), "2026-09-16T22:00:00Z")
    assert out["coverage"]["context_rows"] == 5
    assert out["series"]["10y"]["available_at"] == "2026-09-16T20:00:00+00:00"
    assert out["as_observed_replay_certified"] is False

def test_after_cutoff_is_withheld_even_with_same_observation_date():
    a=source(); a["yield_momentum"]["series"]["10y"]["available_at"]="2026-09-16T22:30:00Z"
    a["built"]="2026-09-16T23:00:00Z"
    out=project(a, "2026-09-16T22:00:00Z")
    assert out["series"]["10y"]["level"] is None
    assert out["coverage"]["context_rows"] == 0

def test_a_later_rebuild_is_not_historical_proof():
    a=source(); a["built"]="2026-09-17T09:00:00Z"
    out=project(a, "2026-09-16T22:00:00Z")
    assert out["coverage"]["context_rows"] == 0
    assert "producer_build_after_cutoff" in out["issues"]

def test_cutoff_comparison_uses_timezone_not_lexical_order():
    a=source(); a["built"]="2026-09-16T16:59:00-04:00"
    a["yield_momentum"]["series"]["10y"]["available_at"]="2026-09-16T16:30:00-04:00"
    out=project(a, "2026-09-16T21:00:00Z")
    assert out["series"]["10y"]["level"] == 4.5

@pytest.mark.parametrize("cutoff", ["2026-09-16", "2026-09-16T22:00:00", "invalid", 42, ""])
def test_invalid_cutoff_fails_closed(cutoff):
    out=project(source(), cutoff)
    assert out["coverage"]["context_rows"] == 0
    assert "invalid_analysis_cutoff" in out["issues"]

@pytest.mark.parametrize("status", ["stale", "missing", "invented-status"])
def test_unusable_source_status_withholds_values(status):
    a=source(); a["yield_momentum"]["series"]["10y"]["status"]=status
    row=project(a)["series"]["10y"]
    assert row["level"] is None
    assert row["turn_watch"] is None
    assert all(v is None for v in row["velocity_bp"].values())

@pytest.mark.parametrize("observed", ["2026-09-17", "2026-09-15", "garbage", None])
def test_row_date_not_current_is_not_made_fresh_by_wrapper(observed):
    a=source(); a["yield_momentum"]["series"]["10y"]["as_of"]=observed
    row=project(a)["series"]["10y"]
    assert row["level"] is None
    assert row["usable_for_context"] is False

@pytest.mark.parametrize("bad", [True, False, float("nan"), float("inf"), "4.5", {}, []])
def test_non_numeric_or_nonfinite_level_is_not_a_signal(bad):
    a=source(); a["yield_momentum"]["series"]["10y"]["level"]=bad
    out=project(a)
    assert out["series"]["10y"]["level"] is None
    json.dumps(out, allow_nan=False)

def test_zero_and_negative_yields_are_preserved_without_percent_change():
    a=source(); a["yield_momentum"]["series"]["2y"]["level"]=0.0
    a["yield_momentum"]["series"]["5y"]["level"]=-0.1
    out=project(a)
    assert out["series"]["2y"]["level"] == 0.0
    assert out["series"]["5y"]["level"] == -0.1
    assert out["series"]["5y"]["velocity_bp"]["5d"] == 12.0

def test_twenty_year_series_cannot_silently_change_source():
    a=source(); a["yield_momentum"]["series"]["20y"]["source_column"]="DGS20"
    out=project(a)
    assert out["series"]["20y"]["level"] is None
    assert "unexpected_source_column" in out["series"]["20y"]["issues"]

@pytest.mark.parametrize("schema", ["wrong", None])
def test_wrong_or_missing_schema_is_withheld(schema):
    a=source(); a["schema"]=schema
    assert project(a)["coverage"]["context_rows"] == 0

def test_unsupported_features_and_prose_are_not_injected():
    a=source(); a["private_instructions"]="NEVER_INCLUDE_"*10000
    a["yield_momentum"]["series"]["real10"]={"level":3.0}
    a["yield_momentum"]["series"]["10y"]["turn_watch"]="NEVER_INCLUDE"
    out=project(a); encoded=json.dumps(out)
    assert "NEVER_INCLUDE" not in encoded
    assert "real10" not in out["series"]
    assert out["capabilities"]["real_yield_momentum"] is False
    assert out["capabilities"]["meeting_specific_surprise"] is False
    assert out["capabilities"]["intraday_rate_timing"] is False
    assert len(encoded) < 12000

def test_immutable_inputs_and_unrelated_decision_planes():
    a=source(); before=deepcopy(a)
    base=context(); out=context(a)
    assert a == before
    for key in ("governor", "signals", "regime", "data_quality", "neural_web"):
        assert out[key] == base[key]

def test_build_reads_existing_artifact_without_new_writer(tmp_path, monkeypatch):
    path=tmp_path/"rates.json"; path.write_text(json.dumps(source()))
    monkeypatch.setattr(DC, "_RATES_COMMAND_PATH", path)
    out=DC.build(regime={"date":"2026-09-16"}, market_view={}, neural_web={}, write=False)
    assert out["rates_evidence"]["series"]["10y"]["level"] == 4.5
    assert json.loads(path.read_text()) == source()

def test_build_explicit_empty_input_does_not_fall_back(tmp_path, monkeypatch):
    path=tmp_path/"rates.json"; path.write_text(json.dumps(source()))
    monkeypatch.setattr(DC, "_RATES_COMMAND_PATH", path)
    out=DC.build(regime={"date":"2026-09-16"}, market_view={}, neural_web={}, rates_command={}, write=False)
    assert out["rates_evidence"]["coverage"]["context_rows"] == 0


def test_observation_cannot_predate_its_own_availability():
    a=source(); a["yield_momentum"]["series"]["10y"]["as_of"]="2026-09-17"
    out=project(a, asof="2026-09-17")
    assert out["series"]["10y"]["level"] is None
    assert "observation_after_available_date" in out["series"]["10y"]["issues"]


def test_us_observation_date_respects_new_york_cutoff_day():
    a=source(); a["built"]="2026-09-16T00:30:00Z"
    for row in a["yield_momentum"]["series"].values():
        row["available_at"]="2026-09-16T00:00:00Z"
    out=project(a, "2026-09-16T01:00:00Z")
    assert out["coverage"]["context_rows"] == 0


def test_invalid_changes_remain_null_without_polluting_other_maturities():
    a=source(); a["yield_momentum"]["series"]["10y"]["velocity_bp"]["5d"]=True
    a["yield_momentum"]["series"]["10y"]["acceleration_bp"]=float("nan")
    out=project(a)
    assert out["series"]["10y"]["velocity_bp"]["5d"] is None
    assert out["series"]["10y"]["acceleration_bp"] is None
    assert out["series"]["5y"]["velocity_bp"]["5d"] == 12.0
    json.dumps(out, allow_nan=False)


@pytest.mark.parametrize("field", ["available_at", "built"])
def test_date_only_clock_cannot_precede_observation(field):
    a = source()
    if field == "built":
        a["built"] = "2026-09-15"
        for row in a["yield_momentum"]["series"].values():
            row["available_at"] = None
    else:
        a["yield_momentum"]["series"]["10y"]["available_at"] = "2026-09-15"
    row = project(a)["series"]["10y"]
    assert row["usable_for_context"] is False
    assert row["level"] is None


def test_market_conventions_are_explicit():
    out = project(source())
    assert out["observation_timezone"] == "America/New_York"
    assert out["market"] == "US"


@pytest.mark.parametrize("day,before,after", [
    ("2026-01-15", "2026-01-15T04:59:59Z", "2026-01-15T05:00:00Z"),
    ("2026-07-15", "2026-07-15T03:59:59Z", "2026-07-15T04:00:00Z"),
    ("2026-03-09", "2026-03-09T03:59:59Z", "2026-03-09T04:00:00Z"),
    ("2026-11-02", "2026-11-02T04:59:59Z", "2026-11-02T05:00:00Z"),
])
def test_new_york_day_boundary_in_winter_summer_and_dst(day, before, after):
    from brain.rates_evidence import _clock, _market_date
    from datetime import date, timedelta
    assert _market_date(_clock(before)[1]) == date.fromisoformat(day) - timedelta(days=1)
    assert _market_date(_clock(after)[1]) == date.fromisoformat(day)


@pytest.mark.parametrize("stamp", ["2026-11-01T01:30:00-04:00", "2026-11-01T01:30:00-05:00"])
def test_fall_back_ambiguous_local_hour_is_resolved_by_offset(stamp):
    from brain.rates_evidence import _clock, _market_date
    from datetime import date
    assert _market_date(_clock(stamp)[1]) == date(2026, 11, 1)


def test_timezone_database_unavailable_never_becomes_utc_fallback(monkeypatch):
    from brain import rates_evidence as RE
    from zoneinfo import ZoneInfoNotFoundError
    def unavailable(_key):
        raise ZoneInfoNotFoundError("controlled missing timezone database")
    monkeypatch.setattr(RE, "ZoneInfo", unavailable)
    out = project(source(), "2026-09-16T22:00:00Z")
    assert out["coverage"]["context_rows"] == 0
    assert all("market_timezone_conversion_unavailable" in row["issues"] for row in out["series"].values())


@pytest.mark.parametrize("stamp", ["0001-01-01T00:00:00Z", "9999-12-31T23:59:59-23:59", "2026-09-16T20:00:00+99:00"])
def test_extreme_or_bad_timezone_clocks_are_json_safe(stamp):
    a = source(); a["built"] = stamp
    out = project(a, stamp)
    assert out["coverage"]["context_rows"] == 0
    json.dumps(out, allow_nan=False)


def test_cutoff_equality_is_inclusive_to_microsecond():
    a = source(); a["built"] = "2026-09-16T21:00:00.123456Z"
    for row in a["yield_momentum"]["series"].values():
        row["available_at"] = a["built"]
    assert project(a, a["built"])["coverage"]["context_rows"] == 5
    assert project(a, "2026-09-16T21:00:00.123455Z")["coverage"]["context_rows"] == 0


def test_later_availability_date_is_not_rejected_as_inconsistent():
    a = source(); a["built"] = "2026-09-17T12:00:00Z"
    for row in a["yield_momentum"]["series"].values():
        row["available_at"] = "2026-09-17T11:00:00Z"
    assert project(a, a["built"])["coverage"]["context_rows"] == 5
    assert project(a, a["built"])["as_observed_replay_certified"] is False


@pytest.mark.parametrize("bad", [None, [], True, 0, "payload", {"yield_momentum": []}])
def test_top_level_non_mapping_sources_degrade(bad):
    out = project(bad)
    assert out["coverage"]["context_rows"] == 0
    json.dumps(out, allow_nan=False)


def test_current_context_legacy_untimed_rows_stay_dated_not_certified():
    a = source()
    for row in a["yield_momentum"]["series"].values():
        row["available_at"] = None
    out = project(a)
    assert out["coverage"] == {"requested_rows": 5, "context_rows": 5, "timed_context_rows": 0}
    assert out["as_observed_replay_certified"] is False
    assert project(a, "2026-09-17T22:00:00Z")["coverage"]["context_rows"] == 0



def test_matching_old_snapshot_dates_do_not_certify_current_session_freshness():
    a = source()
    a["asof"] = "2020-01-02"
    a["built"] = "2020-01-03T12:00:00Z"
    a["yield_momentum"]["asof"] = "2020-01-02"
    for row in a["yield_momentum"]["series"].values():
        row["as_of"] = "2020-01-02"
        row["available_at"] = "2020-01-02T21:00:00Z"
    out = project(a, asof="2020-01-02")
    assert out["coverage"]["context_rows"] == 5
    assert out["analysis_mode"] == "dated_context"
    assert out["current_session_freshness"] == "not_certified"
    assert out["freshness_basis"] == "frame_alignment_only"


def test_cutoff_inspection_does_not_certify_live_freshness():
    out = project(source(), "2026-09-16T22:00:00Z")
    assert out["analysis_mode"] == "cutoff_inspection"
    assert out["current_session_freshness"] == "not_certified"
    assert out["as_observed_replay_certified"] is False


def test_feature_frame_does_not_certify_raw_observation_origin():
    from brain.rates_evidence import project_rates
    out = project_rates(None)
    assert out["observation_origin"] == "unverified"
    assert out["horizon_basis"] == "source_frame_intervals"
    assert out["freshness_basis"] == "frame_alignment_only"
    assert "forward-filled" in " ".join(out["limitations"])
    assert out["as_observed_replay_certified"] is False
