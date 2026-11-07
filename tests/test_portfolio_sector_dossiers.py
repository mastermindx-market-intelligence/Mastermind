"""All-eleven dossier parity through the actual existing MCP handler and serializer.

Fixtures are byte-identical Macro producer outputs at 378e289b180b90ed2902a7689e960932a8a26fe6,
also retained by Terminal 260002504a80e2ce297cec2a82b2f5c73290816c. No live portfolio,
network, model, SDK turn or publication is invoked. Native source health remains unverified.

The exact-session companion section reuses the same tool, reader, artifact and serializer.  Its
fixtures are the corrected producer bytes at f55dda94ca7fe283e7066ceaad2d9438956062d9 (engine
SHA256 43b1cf3a19d3f73dc6a29a319bcc81f3745cda153c3419e492396b48b9068c61), published in
mastermind-terminal#1333.  They are synthetic producer output, not live market, point-in-time or
availability evidence, and the coherent November 5 parent below is labelled as such so it is
never confused with the October 9 legacy fixture set.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import math
from pathlib import Path

import bot  # noqa: F401
import pytest

from brain import autonomous_mcp, bot_mcp, portfolio_intelligence as pi

FIXTURES = Path(__file__).parent / "fixtures"
IDS = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]
FIELDS = ("rs_21d", "rs_63d")
FIXTURE_HASHES = {
    "sector_dossiers_v1.json": "22bb12e0516db2ca8f99b8d10af93deab0f75c96d362ae84a3fa99d95855fcb3",
    "sector_dossiers_unavailable_v1.json": "bdc6ab4fb723b8fd428a1d57f42103ebfe1455ad7ccdfcb1b5fea59153243cc0",
}


def fixture(name="sector_dossiers_v1.json"):
    raw = (FIXTURES / name).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FIXTURE_HASHES[name]
    return json.loads(raw)


def bind(monkeypatch, measured, health=None):
    data = {"as_of": "2026-10-09", "measured_read": measured}
    calls = []

    def read(rel, **kwargs):
        calls.append(rel)
        return data, health or {"status": "stale", "as_of": "2026-10-09", "stale": True}

    monkeypatch.setattr(pi, "_read_vendor", read)
    return data, calls


def decoded(monkeypatch, measured, args=None):
    data, calls = bind(monkeypatch, measured)
    before = copy.deepcopy(data)
    wire = asyncio.run(autonomous_mcp.get_sector_rotation.handler(
        args if args is not None else {"projection": "sector_dossiers"}))
    text = wire["content"][0]["text"]
    result = json.loads(text)
    assert len(text) <= 7200
    assert len(text.encode("utf-8")) <= 7200
    assert "_transport_truncated" not in result
    assert sorted(row["group_id"] for row in result["groups"]) == IDS
    assert len(result["groups"]) == 11
    assert result["context_only"] is True
    assert all(value is False for value in result["authority"].values())
    assert result["forecasts"] == {
        "status": "not_qualified", "expected_return": None,
        "persistence_estimate": None, "allocation_weight": None,
    }
    assert result["availability"]["historically_admissible"] is False
    assert result["availability"]["original_available_at"] is None
    assert result["freshness"]["status"] == "unverified"
    assert data == before
    assert calls == ["site/sectordata/sector_central.json"]
    return result


@pytest.mark.parametrize("name", list(FIXTURE_HASHES))
def test_actual_handler_preserves_native_values_qualifications_and_all_eleven(monkeypatch, name):
    measured = fixture(name)
    native = measured["sector_dossiers"]
    result = decoded(monkeypatch, measured)
    assert result["consumer_reason"] is None
    assert result["source_schema"] == native["schema"]
    assert result["cohort_status"] == "native_contract_admitted"
    assert result["artifact_health"] == {
        "status": "stale", "as_of": "2026-10-09", "stale": True, "execution_authority": False,
    }
    for key, value in native.items():
        if key not in ("schema", "groups"):
            assert result[key] == value
    source_rows = {row["group_id"]: row for row in native["groups"]}
    table = result["reason_table"]
    for row in result["groups"]:
        source = source_rows[row["group_id"]]
        assert row["status"] == source["status"]
        assert row["relative_wealth_pct"] == [source["relative_wealth_pct"][k] for k in FIELDS]
        assert [table[i] if i is not None else None for i in row["null_reason_refs"]] == [
            source["null_reasons"][k] for k in FIELDS]
        assert [table[i] for i in row["qualification_reason_refs"]] == source["qualification_reasons"]
    if name == "sector_dossiers_v1.json":
        assert next(row for row in result["groups"] if row["group_id"] == "XLK")["relative_wealth_pct"][1] == 0


MALFORMED = [
    (["schema"], "unrecognized/v2"),
    (["cohort_id"], "us_baskets"),
    (["windows_sessions"], [20, 63]),
    (["units"], "fraction"),
    (["price_basis"], "unadjusted"),
    (["benchmark"], "SPY\n"),
    (["as_of"], "2026-02-30"),
    (["as_of"], "2026-10-09\n"),
    (["compatibility_key"], "another_generation"),
    (["authority", "may_rank"], True),
    (["authority", "may_trade"], 0),
    (["forecasts", "expected_return"], 0.1),
    (["availability", "historically_admissible"], True),
    (["availability", "original_available_at"], "2026-10-09T10:00:00Z"),
    (["availability", "decision_cutoff"], "2026-10-09T10:00:00"),
    (["freshness", "status"], "fresh"),
    (["history", "naturally_observed"], True),
    (["mechanism", "status"], "available"),
    (["risk", "scope"], "sector"),
    (["groups", 0, "relative_wealth_pct", "rs_21d"], True),
    (["groups", 0, "relative_wealth_pct", "rs_21d"], -100.01),
    (["groups", 0, "relative_wealth_pct", "rs_21d"], "1"),
    (["groups", 0, "status"], "partial"),
    (["groups", 0, "group_id"], "XLC"),
    (["groups", 0, "null_reasons", "rs_21d"], "contradiction"),
    (["groups", 7, "null_reasons", "rs_21d"], None),
    (["groups", 7, "qualification_reasons"], ["missing_group\n"]),
    (["cross_sector_breadth_counts", "21", "measured_n"], 11),
    (["cross_sector_breadth_counts", "63", "positive_n"], 6),
    (["dependency_audit", "source_family_count"], 0),
    (["diagnostics", "duplicate_groups"], ["XLB"]),
    (["diagnostics", "outside_cohort"], ["XLK"]),
    (["diagnostics", "qualification_reasons"], ["source_invalid"]),
]


def set_path(value, path, replacement):
    for component in path[:-1]:
        value = value[component]
    value[path[-1]] = replacement


@pytest.mark.parametrize("path,value", MALFORMED)
def test_malformed_owner_claims_cannot_survive_as_complete_coverage(monkeypatch, path, value):
    measured = fixture()
    set_path(measured["sector_dossiers"], path, value)
    result = decoded(monkeypatch, measured)
    assert result["consumer_reason"] == "invalid_dossier_contract"
    assert result["cohort_status"] == "expected_not_admitted"
    assert all(row["relative_wealth_pct"] == [None, None] for row in result["groups"])


@pytest.mark.parametrize("path,value", [
    (["schema"], "unknown"), (["status"], "current"),
    (["generation", "cohort_id"], "different"),
    (["generation", "benchmark"], "QQQ"), (["generation", "session_end"], "2026-10-08"),
    (["groups", 0, "group_id"], "XLC"),
    (["groups", 0, "group_kind"], "theme"),
    (["groups", 0, "current", "metric"], "return_difference_pct"),
    (["groups", 0, "current", "units"], "fraction"),
    (["groups", 0, "current", "rs_21d"], 2),
])
def test_parent_binding_is_required(monkeypatch, path, value):
    measured = fixture()
    set_path(measured, path, value)
    assert decoded(monkeypatch, measured)["consumer_reason"] == "invalid_dossier_contract"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_owner_input_returns_bounded_all_null_packet(monkeypatch, value):
    measured = fixture()
    measured["sector_dossiers"]["groups"][0]["relative_wealth_pct"]["rs_21d"] = value
    bind(monkeypatch, measured)
    result = pi.sector_rotation(projection="sector_dossiers")
    wire = json.loads(bot_mcp._json(result)["content"][0]["text"])
    assert wire == result
    assert wire["consumer_reason"] == "invalid_dossier_contract"
    assert [row["group_id"] for row in wire["groups"]] == IDS


@pytest.mark.parametrize("measured,reason", [
    ({}, "dossier_not_supplied"), (None, "invalid_dossier_contract"),
    ([], "invalid_dossier_contract"),
    ({"sector_dossiers": {}}, "invalid_dossier_contract"),
])
def test_absent_and_invalid_addenda_keep_expected_identities(monkeypatch, measured, reason):
    assert decoded(monkeypatch, measured)["consumer_reason"] == reason


def test_missing_artifact_stays_unavailable(monkeypatch):
    monkeypatch.setattr(pi, "_read_vendor", lambda *a, **k: (None, {"status": "missing"}))
    packet = pi.sector_rotation(projection="sector_dossiers")
    assert packet["consumer_reason"] == "dossier_not_supplied"
    assert packet["artifact_health"]["status"] == "missing"
    assert [row["group_id"] for row in packet["groups"]] == IDS


@pytest.mark.parametrize("selector", ["unknown", None, False, 0, {}, []])
def test_invalid_selector_cannot_fall_back_to_legacy_ranked_values(monkeypatch, selector):
    monkeypatch.setattr(pi, "_read_vendor", lambda *a, **k: pytest.fail("must not read"))
    response = asyncio.run(autonomous_mcp.get_sector_rotation.handler({"projection": selector}))
    packet = json.loads(response["content"][0]["text"])
    assert packet["consumer_reason"] == "unsupported_projection"
    assert all(row["relative_wealth_pct"] == [None, None] for row in packet["groups"])


@pytest.mark.parametrize("unicode_reason", [False, True])
def test_transport_budget_refuses_whole_projection_without_losing_rows(monkeypatch, unicode_reason):
    measured = fixture("sector_dossiers_unavailable_v1.json")
    for i, row in enumerate(measured["sector_dossiers"]["groups"]):
        row["qualification_reasons"] = [
            f"reason_{i}_{j}_" + ("界" if unicode_reason else "x") * 90 for j in range(4)]
    assert len(json.dumps(measured["sector_dossiers"], ensure_ascii=False).encode()) < 32768
    result = decoded(monkeypatch, measured)
    assert result["consumer_reason"] == "dossier_transport_budget_exceeded"
    assert result["reason_table"] == ["dossier_transport_budget_exceeded"]


def test_oversized_and_extended_native_contracts_fail_closed(monkeypatch):
    measured = fixture()
    measured["sector_dossiers"]["extension"] = "x" * 40000
    assert decoded(monkeypatch, measured)["consumer_reason"] == "dossier_input_budget_exceeded"
    measured["sector_dossiers"]["extension"] = "x"
    assert decoded(monkeypatch, measured)["consumer_reason"] == "invalid_dossier_contract"


def test_as_known_remains_unavailable_even_with_valid_cutoff(monkeypatch):
    measured = fixture("sector_dossiers_unavailable_v1.json")
    availability = measured["sector_dossiers"]["availability"]
    availability.update(mode="as_known", decision_cutoff="2026-10-09T10:00:00Z",
                        reason="availability_time_missing")
    result = decoded(monkeypatch, measured)
    assert result["consumer_reason"] is None
    assert result["availability"] == availability
    assert all(row["relative_wealth_pct"] == [None, None] for row in result["groups"])


def test_projection_result_is_detached(monkeypatch):
    measured = fixture()
    data, _ = bind(monkeypatch, measured)
    before = copy.deepcopy(data)
    result = pi.sector_rotation(projection="sector_dossiers")
    result["groups"][0]["relative_wealth_pct"][0] = 999
    result["availability"]["reason"] = "changed"
    result["diagnostics"]["qualification_reasons"].append("changed")
    assert data == before


def test_legacy_reader_and_handler_keep_their_original_contract(monkeypatch):
    sectors = [
        {"ticker": f"S{i}", "name": f"Sector {i}", "rotation": {"rank": 10 - i}}
        for i in range(8)]
    data = {"as_of": "2026-10-09", "market": {"risk_on": False}, "sectors": sectors, "baskets": []}
    health = {"status": "stale", "as_of": "2026-10-09", "stale": True}
    monkeypatch.setattr(pi, "_read_vendor", lambda *a, **k: (data, health))
    before = json.dumps(pi.sector_rotation(), ensure_ascii=False)
    data["measured_read"] = fixture()
    assert json.dumps(pi.sector_rotation(), ensure_ascii=False) == before
    assert json.dumps(pi.sector_rotation(projection="legacy"), ensure_ascii=False) == before
    assert [row["ticker"] for row in json.loads(before)["sectors"]] == ["S7", "S6", "S5", "S4", "S3", "S2"]
    for args in ({}, {"projection": "legacy"}):
        wire = asyncio.run(autonomous_mcp.get_sector_rotation.handler(args))
        assert wire == bot_mcp._json(json.loads(before))
    assert len(pi.sector_rotation(limit=2)["sectors"]) == 2
    assert "sector_dossiers" not in json.loads(before)


# ---------------------------------------------------------------------------
# Exact-session companion (5/20/63 sessions) through the same tool and serializer.
# ---------------------------------------------------------------------------

WINDOW_FIXTURE_HASHES = {
    "sector_window_measurements.complete.v1.json":
        "6b33895711742dee8cb1366baab5572a6aef31d6ca9ca6d0f81e32ab879e6dae",
    "sector_window_measurements.unavailable.v1.json":
        "e4419e3a4d7dabce4ad4fd760c1fc37d05b8fe1111102ac5b0bb13b1a980f17e",
}
WINDOW_KEYS = ("5", "20", "63")
WINDOW_PACKET_SCHEMA = "mastermind.portfolio_intelligence.sector_window_measurements/v1"
WINDOW_NATIVE_SCHEMA = "leadership_rotation_context.sector_window_measurements/v1"


def window_fixture(name="sector_window_measurements.complete.v1.json"):
    raw = (FIXTURES / name).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == WINDOW_FIXTURE_HASHES[name]
    return json.loads(raw)


def window_parent(companion, *, schema="leadership_rotation_context.measured_group_read/v1",
                  status="available", generation=None):
    """Explicitly labelled coherent November 5 parent for the new companion fixtures."""
    bound = {"benchmark": "SPY", "cohort_id": "us_sectors_11", "price_basis": "total_return",
             "session_end": "2026-11-05", "id": "2026-11-05|SPY|us_sectors_11"}
    bound.update(generation or {})
    return {"schema": schema, "status": status, "generation": bound,
            "sector_window_measurements": companion}


def bind_window(monkeypatch, measured, health=None):
    data = {"as_of": "2026-11-05", "measured_read": measured}
    calls = []

    def read(rel, **kwargs):
        calls.append(rel)
        return data, health or {"status": "stale", "as_of": "2026-11-05", "stale": True}

    monkeypatch.setattr(pi, "_read_vendor", read)
    return data, calls


def decoded_window(monkeypatch, measured, sector, args=None):
    data, calls = bind_window(monkeypatch, measured)
    before = copy.deepcopy(data)
    wire = asyncio.run(autonomous_mcp.get_sector_rotation.handler(
        args if args is not None else {"projection": "sector_windows", "sector": sector}))
    text = wire["content"][0]["text"]
    result = json.loads(text)
    assert len(text) <= 7200
    assert len(text.encode("utf-8")) <= 7200
    assert "_transport_truncated" not in result
    assert data == before
    return result, calls, text


def recompute_native(companion):
    """Recompute the native counters and statuses after an explicit cell edit."""
    measured = complete = 0
    per_window_measured = {key: 0 for key in WINDOW_KEYS}
    per_window_complete = {key: 0 for key in WINDOW_KEYS}
    for row in companion["groups"]:
        for key in WINDOW_KEYS:
            cell = row["windows"][key]
            present = ((cell["absolute_return_pct"] is not None)
                       + (cell["relative_wealth_pct"] is not None))
            cell["status"] = ("available" if present == 2
                              else "partial" if present == 1 else "unavailable")
            measured += present > 0
            complete += present == 2
            per_window_measured[key] += present > 0
            per_window_complete[key] += present == 2
    for key in WINDOW_KEYS:
        companion["windows"][key]["status"] = (
            "available" if per_window_complete[key] == 11
            else "partial" if per_window_measured[key] else "unavailable")
    companion["diagnostics"]["measured_cells"] = measured
    companion["diagnostics"]["complete_cells"] = complete
    companion["status"] = ("available" if complete == 33
                            else "partial" if measured else "unavailable")
    return companion


def test_window_fixture_bytes_are_pinned_to_the_corrected_producer():
    for name, digest in WINDOW_FIXTURE_HASHES.items():
        raw = (FIXTURES / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest
        assert json.loads(raw)["schema"] == WINDOW_NATIVE_SCHEMA
    assert set(WINDOW_FIXTURE_HASHES) == {
        "sector_window_measurements.complete.v1.json",
        "sector_window_measurements.unavailable.v1.json",
    }


@pytest.mark.parametrize("name", list(WINDOW_FIXTURE_HASHES))
@pytest.mark.parametrize("sector", IDS)
def test_real_handler_keeps_all_eleven_and_projects_only_the_selected_member(monkeypatch, name, sector):
    companion = window_fixture(name)
    measured = window_parent(companion)
    result, calls, _ = decoded_window(monkeypatch, measured, sector)
    # One fixed artifact read, no legacy dossier, and the input is never mutated.
    assert calls == ["site/sectordata/sector_central.json"]
    assert "sector_dossiers" not in measured
    assert result["consumer_reason"] is None
    assert result["cohort_status"] == "native_contract_admitted"
    assert result["schema"] == WINDOW_PACKET_SCHEMA
    assert result["source_schema"] == WINDOW_NATIVE_SCHEMA
    assert result["context_only"] is True
    assert result["selected_group_id"] == sector
    assert result["cohort_id"] == "us_sectors_11"
    assert result["population"] == "eleven_sector_etf_proxies"
    assert result["windows_sessions"] == [5, 20, 63]
    assert result["source_session"] == "2026-11-05"
    assert result["end_session"] == "2026-11-05"
    assert result["benchmark"] == companion["benchmark"]
    assert result["price_basis"] == "total_return"
    assert result["units"] == "pct"
    assert result["endpoint_definition"] == companion["endpoint_definition"]
    assert result["clocks"] == companion["clocks"]
    assert result["limitations"] == companion["limitations"]
    assert result["status"] == companion["status"]
    assert result["reason"] == companion["reason"]
    assert all(value is False for value in result["authority"].values())
    assert result["artifact_health"] == {
        "status": "stale", "as_of": "2026-11-05", "stale": True, "execution_authority": False,
    }
    assert result["metadata_projection"] == {
        "receipt": "not_projected", "source_roots": "not_projected",
    }
    # All eleven identities, unique, in source order.
    assert [row["group_id"] for row in result["groups"]] == IDS
    assert len({row["group_id"] for row in result["groups"]}) == 11
    native = {row["group_id"]: row for row in companion["groups"]}
    table = result["reason_table"]
    for row in result["groups"]:
        source = native[row["group_id"]]
        assert row["window_status"] == [source["windows"][key]["status"] for key in WINDOW_KEYS]
        if row["group_id"] == sector:
            assert row["scope"] == "selected"
        else:
            assert row["scope"] == "status_only"
            # An unselected row never carries a metric or a placeholder value.
            assert set(row) == {"group_id", "scope", "window_status"}
    selected = native[sector]
    assert result["selected"]["group_id"] == sector
    assert result["selected"]["name_en"] == selected["name_en"]
    assert result["selected"]["name_zh"] == selected["name_zh"]
    for index, key in enumerate(WINDOW_KEYS):
        cell = selected["windows"][key]
        assert result["selected"]["absolute_return_pct"][index] == cell["absolute_return_pct"]
        assert result["selected"]["relative_wealth_pct"][index] == cell["relative_wealth_pct"]
        assert result["selected"]["observed_n"][index] == cell["coverage"]["observed_n"]
        assert result["selected"]["coverage_ratio"][index] == cell["coverage"]["ratio"]
        for field, refs in (("absolute_return_pct", "absolute_reason_refs"),
                            ("relative_wealth_pct", "relative_reason_refs")):
            ref = result["selected"][refs][index]
            native_reason = cell["null_reasons"][field]
            assert (table[ref] if ref is not None else None) == native_reason
    for key in WINDOW_KEYS:
        window = companion["windows"][key]
        projected = result["windows"][key]
        assert projected["window_sessions"] == window["window_sessions"]
        assert projected["expected_observations"] == window["benchmark_coverage"]["expected_n"]
        assert projected["start_session"] == window["start_session"]
        assert projected["end_session"] == window["end_session"]
        assert projected["status"] == window["status"]
        assert projected["benchmark_return_pct"] == window["benchmark_return_pct"]
        assert projected["benchmark_observed_n"] == window["benchmark_coverage"]["observed_n"]
        assert projected["benchmark_coverage_ratio"] == window["benchmark_coverage"]["ratio"]
        for field, ref_key in (("null_reason", "window_reason_ref"),
                               ("benchmark_null_reason", "benchmark_reason_ref")):
            ref = projected[ref_key]
            assert (table[ref] if ref is not None else None) == window[field]
    diagnostics = companion["diagnostics"]
    assert result["diagnostics"]["measured_cells"] == diagnostics["measured_cells"]
    assert result["diagnostics"]["complete_cells"] == diagnostics["complete_cells"]
    assert result["diagnostics"]["total_cells"] == diagnostics["total_cells"]
    assert result["diagnostics"]["block_reason_ref"] == (
        table.index(companion["reason"]) if companion["reason"] is not None else None)
    assert [table[ref] for ref in result["diagnostics"]["qualification_reason_refs"]] == \
        diagnostics["qualification_reasons"]


def test_future_tail_keeps_identities_dates_coverage_and_cause(monkeypatch):
    companion = window_fixture("sector_window_measurements.unavailable.v1.json")
    result, _, _ = decoded_window(monkeypatch, window_parent(companion), "XLK")
    # An admitted all-null source is not a consumer refusal.
    assert result["consumer_reason"] is None
    assert result["cohort_status"] == "native_contract_admitted"
    assert result["status"] == "unavailable"
    assert result["reason"] == "future_tail"
    assert [row["group_id"] for row in result["groups"]] == IDS
    assert result["selected"]["absolute_return_pct"] == [None, None, None]
    assert result["selected"]["relative_wealth_pct"] == [None, None, None]
    assert result["selected"]["observed_n"] == [6, 21, 64]
    assert result["selected"]["coverage_ratio"] == [1.0, 1.0, 1.0]
    assert result["reason_table"] == ["future_tail"]
    assert result["selected"]["absolute_reason_refs"] == [0, 0, 0]
    assert result["selected"]["relative_reason_refs"] == [0, 0, 0]
    for key in WINDOW_KEYS:
        window = result["windows"][key]
        assert window["start_session"] == companion["windows"][key]["start_session"]
        assert window["end_session"] == "2026-11-05"
        assert window["status"] == "unavailable"
        assert window["benchmark_return_pct"] is None
        assert window["benchmark_observed_n"] == \
            companion["windows"][key]["benchmark_coverage"]["observed_n"]
        assert window["benchmark_reason_ref"] == 0
        assert window["window_reason_ref"] == 0
    assert result["diagnostics"]["measured_cells"] == 0
    assert result["diagnostics"]["complete_cells"] == 0
    assert result["diagnostics"]["block_reason_ref"] == 0
    assert result["diagnostics"]["qualification_reason_refs"] == [0]


# Actual pure 43b1cf3 owner output, from an explicit synthetic canonical-session fixture.
_PARENT_OWNER_CASES = json.loads('{"absolute_percent_overflow":{"schema":"leadership_rotation_context.sector_window_measurements/v1","status":"partial","reason":null,"units":"pct","price_basis":"total_return","benchmark":"SPY","cohort_id":"us_sectors_11","population":"eleven_sector_etf_proxies","source_session":"2026-11-05","end_session":"2026-11-05","windows_sessions":[5,20,63],"endpoint_definition":"Endpoint return: P(T)/P(S_N) - 1, where T is the explicit end session and S_N is the canonical US session exactly N positions before T, so a 5-session return spans 6 session endpoints. Relative wealth is (1+R_group)/(1+R_benchmark) - 1 -- a wealth ratio, never a return difference. Interior gaps never move an endpoint; they are disclosed as observed coverage. Prices are strictly positive, finite, total-return adjusted closes read at the two endpoints only.","clocks":{"publication":null,"availability":null,"correction":null,"history":null},"source_roots":[],"receipt":null,"limitations":{"availability":{"status":"unknown","reason":"owner_availability_clock_not_supplied"},"publication":{"status":"unknown","reason":"owner_publication_clock_not_supplied"},"corrections":{"status":"unavailable","reason":"native_revision_selection_not_supplied"},"history":{"status":"unknown","reason":"owner_history_clock_not_supplied"},"freshness":{"status":"unverified","reason":"owner_freshness_receipt_not_supplied"},"point_in_time":{"status":"not_qualified","reason":"point_in_time_admission_not_supplied"}},"windows":{"5":{"window_sessions":5,"status":"partial","start_session":"2026-10-29","end_session":"2026-11-05","benchmark_return_pct":1e+307,"benchmark_null_reason":null,"benchmark_coverage":{"observed_n":6,"expected_n":6,"ratio":1.0},"null_reason":null},"20":{"window_sessions":20,"status":"available","start_session":"2026-10-08","end_session":"2026-11-05","benchmark_return_pct":-99.350649,"benchmark_null_reason":null,"benchmark_coverage":{"observed_n":21,"expected_n":21,"ratio":1.0},"null_reason":null},"63":{"window_sessions":63,"status":"available","start_session":"2026-08-07","end_session":"2026-11-05","benchmark_return_pct":-99.099099,"benchmark_null_reason":null,"benchmark_coverage":{"observed_n":64,"expected_n":64,"ratio":1.0},"null_reason":null}},"groups":[{"group_id":"XLB","name_en":"Materials","name_zh":"\\u539f\\u6750\\u6599","windows":{"5":{"status":"partial","absolute_return_pct":null,"relative_wealth_pct":9900.0,"null_reasons":{"absolute_return_pct":"non_finite_input","relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":-99.300699,"relative_wealth_pct":7.692308,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":-99.0,"relative_wealth_pct":11.0,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLC","name_en":"Communication Services","name_zh":"\\u901a\\u8baf\\u670d\\u52a1","windows":{"5":{"status":"available","absolute_return_pct":3.144654,"relative_wealth_pct":-100.0,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.888889,"relative_wealth_pct":17438.888889,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":62.376238,"relative_wealth_pct":17923.762376,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLE","name_en":"Energy","name_zh":"\\u80fd\\u6e90","windows":{"5":{"status":"available","absolute_return_pct":3.125,"relative_wealth_pct":-100.0,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.793103,"relative_wealth_pct":17424.137931,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":61.764706,"relative_wealth_pct":17855.882353,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLF","name_en":"Financials","name_zh":"\\u91d1\\u878d","windows":{"5":{"status":"available","absolute_return_pct":3.10559,"relative_wealth_pct":-100.0,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.69863,"relative_wealth_pct":17409.589041,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":61.165049,"relative_wealth_pct":17789.320388,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLI","name_en":"Industrials","name_zh":"\\u5de5\\u4e1a","windows":{"5":{"status":"available","absolute_return_pct":3.08642,"relative_wealth_pct":-100.0,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.605442,"relative_wealth_pct":17395.238095,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":60.576923,"relative_wealth_pct":17724.038462,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLK","name_en":"Technology","name_zh":"\\u79d1\\u6280","windows":{"5":{"status":"available","absolute_return_pct":3.067485,"relative_wealth_pct":-100.0,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.513514,"relative_wealth_pct":17381.081081,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":60.0,"relative_wealth_pct":17660.0,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLP","name_en":"Consumer Staples","name_zh":"\\u5fc5\\u9700\\u6d88\\u8d39","windows":{"5":{"status":"available","absolute_return_pct":3.04878,"relative_wealth_pct":-100.0,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.422819,"relative_wealth_pct":17367.114094,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":59.433962,"relative_wealth_pct":17597.169811,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLRE","name_en":"Real Estate","name_zh":"\\u623f\\u5730\\u4ea7","windows":{"5":{"status":"available","absolute_return_pct":3.030303,"relative_wealth_pct":-100.0,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.333333,"relative_wealth_pct":17353.333333,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":58.878505,"relative_wealth_pct":17535.514019,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLU","name_en":"Utilities","name_zh":"\\u516c\\u7528\\u4e8b\\u4e1a","windows":{"5":{"status":"available","absolute_return_pct":3.012048,"relative_wealth_pct":-100.0,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.245033,"relative_wealth_pct":17339.735099,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":58.333333,"relative_wealth_pct":17475.0,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLV","name_en":"Health Care","name_zh":"\\u533b\\u7597\\u4fdd\\u5065","windows":{"5":{"status":"available","absolute_return_pct":2.994012,"relative_wealth_pct":-100.0,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.157895,"relative_wealth_pct":17326.315789,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":57.798165,"relative_wealth_pct":17415.59633,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLY","name_en":"Consumer Discretionary","name_zh":"\\u975e\\u5fc5\\u9700\\u6d88\\u8d39","windows":{"5":{"status":"available","absolute_return_pct":2.97619,"relative_wealth_pct":-100.0,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.071895,"relative_wealth_pct":17313.071895,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":57.272727,"relative_wealth_pct":17357.272727,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}}],"diagnostics":{"panel_rows":64,"malformed_rows":0,"duplicate_sessions":[],"ambiguous_columns":[],"columns":["SPY","XLB","XLC","XLE","XLF","XLI","XLK","XLP","XLRE","XLU","XLV","XLY"],"binding_keys":[],"receipt_withheld":false,"future_tail_sessions":[],"expected_columns":12,"qualification_reasons":[],"measured_cells":33,"complete_cells":32,"total_cells":33,"coverage_note":"observed_n counts usable observations inside the window; an interior gap never moves an endpoint"},"authority":{"may_rank":false,"may_gate":false,"may_size":false,"may_trade":false,"may_escalate":false}},"missing_benchmark":{"schema":"leadership_rotation_context.sector_window_measurements/v1","status":"partial","reason":null,"units":"pct","price_basis":"total_return","benchmark":"SPY","cohort_id":"us_sectors_11","population":"eleven_sector_etf_proxies","source_session":"2026-11-05","end_session":"2026-11-05","windows_sessions":[5,20,63],"endpoint_definition":"Endpoint return: P(T)/P(S_N) - 1, where T is the explicit end session and S_N is the canonical US session exactly N positions before T, so a 5-session return spans 6 session endpoints. Relative wealth is (1+R_group)/(1+R_benchmark) - 1 -- a wealth ratio, never a return difference. Interior gaps never move an endpoint; they are disclosed as observed coverage. Prices are strictly positive, finite, total-return adjusted closes read at the two endpoints only.","clocks":{"publication":null,"availability":null,"correction":null,"history":null},"source_roots":[],"receipt":null,"limitations":{"availability":{"status":"unknown","reason":"owner_availability_clock_not_supplied"},"publication":{"status":"unknown","reason":"owner_publication_clock_not_supplied"},"corrections":{"status":"unavailable","reason":"native_revision_selection_not_supplied"},"history":{"status":"unknown","reason":"owner_history_clock_not_supplied"},"freshness":{"status":"unverified","reason":"owner_freshness_receipt_not_supplied"},"point_in_time":{"status":"not_qualified","reason":"point_in_time_admission_not_supplied"}},"windows":{"5":{"window_sessions":5,"status":"partial","start_session":"2026-10-29","end_session":"2026-11-05","benchmark_return_pct":null,"benchmark_null_reason":"benchmark_missing","benchmark_coverage":{"observed_n":5,"expected_n":6,"ratio":0.833333},"null_reason":null},"20":{"window_sessions":20,"status":"available","start_session":"2026-10-08","end_session":"2026-11-05","benchmark_return_pct":12.987013,"benchmark_null_reason":null,"benchmark_coverage":{"observed_n":20,"expected_n":21,"ratio":0.952381},"null_reason":null},"63":{"window_sessions":63,"status":"available","start_session":"2026-08-07","end_session":"2026-11-05","benchmark_return_pct":56.756757,"benchmark_null_reason":null,"benchmark_coverage":{"observed_n":63,"expected_n":64,"ratio":0.984375},"null_reason":null}},"groups":[{"group_id":"XLB","name_en":"Materials","name_zh":"\\u539f\\u6750\\u6599","windows":{"5":{"status":"partial","absolute_return_pct":3.164557,"relative_wealth_pct":null,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":"benchmark_missing"},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.986014,"relative_wealth_pct":0.884173,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":63.0,"relative_wealth_pct":3.982759,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLC","name_en":"Communication Services","name_zh":"\\u901a\\u8baf\\u670d\\u52a1","windows":{"5":{"status":"partial","absolute_return_pct":3.144654,"relative_wealth_pct":null,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":"benchmark_missing"},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.888889,"relative_wealth_pct":0.798212,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":62.376238,"relative_wealth_pct":3.584841,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLE","name_en":"Energy","name_zh":"\\u80fd\\u6e90","windows":{"5":{"status":"partial","absolute_return_pct":3.125,"relative_wealth_pct":null,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":"benchmark_missing"},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.793103,"relative_wealth_pct":0.713436,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":61.764706,"relative_wealth_pct":3.194726,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLF","name_en":"Financials","name_zh":"\\u91d1\\u878d","windows":{"5":{"status":"partial","absolute_return_pct":3.10559,"relative_wealth_pct":null,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":"benchmark_missing"},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.69863,"relative_wealth_pct":0.629822,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":61.165049,"relative_wealth_pct":2.812186,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLI","name_en":"Industrials","name_zh":"\\u5de5\\u4e1a","windows":{"5":{"status":"partial","absolute_return_pct":3.08642,"relative_wealth_pct":null,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":"benchmark_missing"},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.605442,"relative_wealth_pct":0.547345,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":60.576923,"relative_wealth_pct":2.437003,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLK","name_en":"Technology","name_zh":"\\u79d1\\u6280","windows":{"5":{"status":"partial","absolute_return_pct":3.067485,"relative_wealth_pct":null,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":"benchmark_missing"},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.513514,"relative_wealth_pct":0.465983,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":60.0,"relative_wealth_pct":2.068966,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLP","name_en":"Consumer Staples","name_zh":"\\u5fc5\\u9700\\u6d88\\u8d39","windows":{"5":{"status":"partial","absolute_return_pct":3.04878,"relative_wealth_pct":null,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":"benchmark_missing"},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.422819,"relative_wealth_pct":0.385713,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":59.433962,"relative_wealth_pct":1.707872,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLRE","name_en":"Real Estate","name_zh":"\\u623f\\u5730\\u4ea7","windows":{"5":{"status":"partial","absolute_return_pct":3.030303,"relative_wealth_pct":null,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":"benchmark_missing"},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.333333,"relative_wealth_pct":0.306513,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":58.878505,"relative_wealth_pct":1.353529,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLU","name_en":"Utilities","name_zh":"\\u516c\\u7528\\u4e8b\\u4e1a","windows":{"5":{"status":"partial","absolute_return_pct":3.012048,"relative_wealth_pct":null,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":"benchmark_missing"},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.245033,"relative_wealth_pct":0.228363,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":58.333333,"relative_wealth_pct":1.005747,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLV","name_en":"Health Care","name_zh":"\\u533b\\u7597\\u4fdd\\u5065","windows":{"5":{"status":"partial","absolute_return_pct":2.994012,"relative_wealth_pct":null,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":"benchmark_missing"},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.157895,"relative_wealth_pct":0.15124,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":57.798165,"relative_wealth_pct":0.664347,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLY","name_en":"Consumer Discretionary","name_zh":"\\u975e\\u5fc5\\u9700\\u6d88\\u8d39","windows":{"5":{"status":"partial","absolute_return_pct":2.97619,"relative_wealth_pct":null,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":"benchmark_missing"},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.071895,"relative_wealth_pct":0.075126,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":57.272727,"relative_wealth_pct":0.329154,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}}],"diagnostics":{"panel_rows":64,"malformed_rows":0,"duplicate_sessions":[],"ambiguous_columns":[],"columns":["SPY","XLB","XLC","XLE","XLF","XLI","XLK","XLP","XLRE","XLU","XLV","XLY"],"binding_keys":[],"receipt_withheld":false,"future_tail_sessions":[],"expected_columns":12,"qualification_reasons":[],"measured_cells":33,"complete_cells":22,"total_cells":33,"coverage_note":"observed_n counts usable observations inside the window; an interior gap never moves an endpoint"},"authority":{"may_rank":false,"may_gate":false,"may_size":false,"may_trade":false,"may_escalate":false}},"interior_gap":{"schema":"leadership_rotation_context.sector_window_measurements/v1","status":"available","reason":null,"units":"pct","price_basis":"total_return","benchmark":"SPY","cohort_id":"us_sectors_11","population":"eleven_sector_etf_proxies","source_session":"2026-11-05","end_session":"2026-11-05","windows_sessions":[5,20,63],"endpoint_definition":"Endpoint return: P(T)/P(S_N) - 1, where T is the explicit end session and S_N is the canonical US session exactly N positions before T, so a 5-session return spans 6 session endpoints. Relative wealth is (1+R_group)/(1+R_benchmark) - 1 -- a wealth ratio, never a return difference. Interior gaps never move an endpoint; they are disclosed as observed coverage. Prices are strictly positive, finite, total-return adjusted closes read at the two endpoints only.","clocks":{"publication":null,"availability":null,"correction":null,"history":null},"source_roots":[],"receipt":null,"limitations":{"availability":{"status":"unknown","reason":"owner_availability_clock_not_supplied"},"publication":{"status":"unknown","reason":"owner_publication_clock_not_supplied"},"corrections":{"status":"unavailable","reason":"native_revision_selection_not_supplied"},"history":{"status":"unknown","reason":"owner_history_clock_not_supplied"},"freshness":{"status":"unverified","reason":"owner_freshness_receipt_not_supplied"},"point_in_time":{"status":"not_qualified","reason":"point_in_time_admission_not_supplied"}},"windows":{"5":{"window_sessions":5,"status":"available","start_session":"2026-10-29","end_session":"2026-11-05","benchmark_return_pct":2.95858,"benchmark_null_reason":null,"benchmark_coverage":{"observed_n":6,"expected_n":6,"ratio":1.0},"null_reason":null},"20":{"window_sessions":20,"status":"available","start_session":"2026-10-08","end_session":"2026-11-05","benchmark_return_pct":12.987013,"benchmark_null_reason":null,"benchmark_coverage":{"observed_n":21,"expected_n":21,"ratio":1.0},"null_reason":null},"63":{"window_sessions":63,"status":"available","start_session":"2026-08-07","end_session":"2026-11-05","benchmark_return_pct":56.756757,"benchmark_null_reason":null,"benchmark_coverage":{"observed_n":64,"expected_n":64,"ratio":1.0},"null_reason":null}},"groups":[{"group_id":"XLB","name_en":"Materials","name_zh":"\\u539f\\u6750\\u6599","windows":{"5":{"status":"available","absolute_return_pct":3.164557,"relative_wealth_pct":0.200058,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":5,"expected_n":6,"ratio":0.833333}},"20":{"status":"available","absolute_return_pct":13.986014,"relative_wealth_pct":0.884173,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":20,"expected_n":21,"ratio":0.952381}},"63":{"status":"available","absolute_return_pct":63.0,"relative_wealth_pct":3.982759,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":63,"expected_n":64,"ratio":0.984375}}}},{"group_id":"XLC","name_en":"Communication Services","name_zh":"\\u901a\\u8baf\\u670d\\u52a1","windows":{"5":{"status":"available","absolute_return_pct":3.144654,"relative_wealth_pct":0.180727,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.888889,"relative_wealth_pct":0.798212,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":62.376238,"relative_wealth_pct":3.584841,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLE","name_en":"Energy","name_zh":"\\u80fd\\u6e90","windows":{"5":{"status":"available","absolute_return_pct":3.125,"relative_wealth_pct":0.161638,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.793103,"relative_wealth_pct":0.713436,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":61.764706,"relative_wealth_pct":3.194726,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLF","name_en":"Financials","name_zh":"\\u91d1\\u878d","windows":{"5":{"status":"available","absolute_return_pct":3.10559,"relative_wealth_pct":0.142786,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.69863,"relative_wealth_pct":0.629822,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":61.165049,"relative_wealth_pct":2.812186,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLI","name_en":"Industrials","name_zh":"\\u5de5\\u4e1a","windows":{"5":{"status":"available","absolute_return_pct":3.08642,"relative_wealth_pct":0.124166,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.605442,"relative_wealth_pct":0.547345,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":60.576923,"relative_wealth_pct":2.437003,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLK","name_en":"Technology","name_zh":"\\u79d1\\u6280","windows":{"5":{"status":"available","absolute_return_pct":3.067485,"relative_wealth_pct":0.105775,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.513514,"relative_wealth_pct":0.465983,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":60.0,"relative_wealth_pct":2.068966,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLP","name_en":"Consumer Staples","name_zh":"\\u5fc5\\u9700\\u6d88\\u8d39","windows":{"5":{"status":"available","absolute_return_pct":3.04878,"relative_wealth_pct":0.087609,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.422819,"relative_wealth_pct":0.385713,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":59.433962,"relative_wealth_pct":1.707872,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLRE","name_en":"Real Estate","name_zh":"\\u623f\\u5730\\u4ea7","windows":{"5":{"status":"available","absolute_return_pct":3.030303,"relative_wealth_pct":0.069662,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.333333,"relative_wealth_pct":0.306513,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":58.878505,"relative_wealth_pct":1.353529,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLU","name_en":"Utilities","name_zh":"\\u516c\\u7528\\u4e8b\\u4e1a","windows":{"5":{"status":"available","absolute_return_pct":3.012048,"relative_wealth_pct":0.051932,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.245033,"relative_wealth_pct":0.228363,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":58.333333,"relative_wealth_pct":1.005747,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLV","name_en":"Health Care","name_zh":"\\u533b\\u7597\\u4fdd\\u5065","windows":{"5":{"status":"available","absolute_return_pct":2.994012,"relative_wealth_pct":0.034414,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.157895,"relative_wealth_pct":0.15124,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":57.798165,"relative_wealth_pct":0.664347,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLY","name_en":"Consumer Discretionary","name_zh":"\\u975e\\u5fc5\\u9700\\u6d88\\u8d39","windows":{"5":{"status":"available","absolute_return_pct":2.97619,"relative_wealth_pct":0.017105,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.071895,"relative_wealth_pct":0.075126,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":57.272727,"relative_wealth_pct":0.329154,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}}],"diagnostics":{"panel_rows":64,"malformed_rows":0,"duplicate_sessions":[],"ambiguous_columns":[],"columns":["SPY","XLB","XLC","XLE","XLF","XLI","XLK","XLP","XLRE","XLU","XLV","XLY"],"binding_keys":[],"receipt_withheld":false,"future_tail_sessions":[],"expected_columns":12,"qualification_reasons":[],"measured_cells":33,"complete_cells":33,"total_cells":33,"coverage_note":"observed_n counts usable observations inside the window; an interior gap never moves an endpoint"},"authority":{"may_rank":false,"may_gate":false,"may_size":false,"may_trade":false,"may_escalate":false}},"zero_short_coverage":{"schema":"leadership_rotation_context.sector_window_measurements/v1","status":"partial","reason":null,"units":"pct","price_basis":"total_return","benchmark":"SPY","cohort_id":"us_sectors_11","population":"eleven_sector_etf_proxies","source_session":"2026-11-05","end_session":"2026-11-05","windows_sessions":[5,20,63],"endpoint_definition":"Endpoint return: P(T)/P(S_N) - 1, where T is the explicit end session and S_N is the canonical US session exactly N positions before T, so a 5-session return spans 6 session endpoints. Relative wealth is (1+R_group)/(1+R_benchmark) - 1 -- a wealth ratio, never a return difference. Interior gaps never move an endpoint; they are disclosed as observed coverage. Prices are strictly positive, finite, total-return adjusted closes read at the two endpoints only.","clocks":{"publication":null,"availability":null,"correction":null,"history":null},"source_roots":[],"receipt":null,"limitations":{"availability":{"status":"unknown","reason":"owner_availability_clock_not_supplied"},"publication":{"status":"unknown","reason":"owner_publication_clock_not_supplied"},"corrections":{"status":"unavailable","reason":"native_revision_selection_not_supplied"},"history":{"status":"unknown","reason":"owner_history_clock_not_supplied"},"freshness":{"status":"unverified","reason":"owner_freshness_receipt_not_supplied"},"point_in_time":{"status":"not_qualified","reason":"point_in_time_admission_not_supplied"}},"windows":{"5":{"window_sessions":5,"status":"partial","start_session":"2026-10-29","end_session":"2026-11-05","benchmark_return_pct":2.95858,"benchmark_null_reason":null,"benchmark_coverage":{"observed_n":6,"expected_n":6,"ratio":1.0},"null_reason":null},"20":{"window_sessions":20,"status":"partial","start_session":"2026-10-08","end_session":"2026-11-05","benchmark_return_pct":12.987013,"benchmark_null_reason":null,"benchmark_coverage":{"observed_n":21,"expected_n":21,"ratio":1.0},"null_reason":null},"63":{"window_sessions":63,"status":"partial","start_session":"2026-08-07","end_session":"2026-11-05","benchmark_return_pct":56.756757,"benchmark_null_reason":null,"benchmark_coverage":{"observed_n":64,"expected_n":64,"ratio":1.0},"null_reason":null}},"groups":[{"group_id":"XLB","name_en":"Materials","name_zh":"\\u539f\\u6750\\u6599","windows":{"5":{"status":"unavailable","absolute_return_pct":null,"relative_wealth_pct":null,"null_reasons":{"absolute_return_pct":"missing_input","relative_wealth_pct":"missing_input"},"coverage":{"observed_n":0,"expected_n":6,"ratio":0.0}},"20":{"status":"unavailable","absolute_return_pct":null,"relative_wealth_pct":null,"null_reasons":{"absolute_return_pct":"missing_input","relative_wealth_pct":"missing_input"},"coverage":{"observed_n":15,"expected_n":21,"ratio":0.714286}},"63":{"status":"unavailable","absolute_return_pct":null,"relative_wealth_pct":null,"null_reasons":{"absolute_return_pct":"missing_input","relative_wealth_pct":"missing_input"},"coverage":{"observed_n":58,"expected_n":64,"ratio":0.90625}}}},{"group_id":"XLC","name_en":"Communication Services","name_zh":"\\u901a\\u8baf\\u670d\\u52a1","windows":{"5":{"status":"available","absolute_return_pct":3.144654,"relative_wealth_pct":0.180727,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.888889,"relative_wealth_pct":0.798212,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":62.376238,"relative_wealth_pct":3.584841,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLE","name_en":"Energy","name_zh":"\\u80fd\\u6e90","windows":{"5":{"status":"available","absolute_return_pct":3.125,"relative_wealth_pct":0.161638,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.793103,"relative_wealth_pct":0.713436,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":61.764706,"relative_wealth_pct":3.194726,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLF","name_en":"Financials","name_zh":"\\u91d1\\u878d","windows":{"5":{"status":"available","absolute_return_pct":3.10559,"relative_wealth_pct":0.142786,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.69863,"relative_wealth_pct":0.629822,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":61.165049,"relative_wealth_pct":2.812186,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLI","name_en":"Industrials","name_zh":"\\u5de5\\u4e1a","windows":{"5":{"status":"available","absolute_return_pct":3.08642,"relative_wealth_pct":0.124166,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.605442,"relative_wealth_pct":0.547345,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":60.576923,"relative_wealth_pct":2.437003,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLK","name_en":"Technology","name_zh":"\\u79d1\\u6280","windows":{"5":{"status":"available","absolute_return_pct":3.067485,"relative_wealth_pct":0.105775,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.513514,"relative_wealth_pct":0.465983,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":60.0,"relative_wealth_pct":2.068966,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLP","name_en":"Consumer Staples","name_zh":"\\u5fc5\\u9700\\u6d88\\u8d39","windows":{"5":{"status":"available","absolute_return_pct":3.04878,"relative_wealth_pct":0.087609,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.422819,"relative_wealth_pct":0.385713,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":59.433962,"relative_wealth_pct":1.707872,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLRE","name_en":"Real Estate","name_zh":"\\u623f\\u5730\\u4ea7","windows":{"5":{"status":"available","absolute_return_pct":3.030303,"relative_wealth_pct":0.069662,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.333333,"relative_wealth_pct":0.306513,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":58.878505,"relative_wealth_pct":1.353529,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLU","name_en":"Utilities","name_zh":"\\u516c\\u7528\\u4e8b\\u4e1a","windows":{"5":{"status":"available","absolute_return_pct":3.012048,"relative_wealth_pct":0.051932,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.245033,"relative_wealth_pct":0.228363,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":58.333333,"relative_wealth_pct":1.005747,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLV","name_en":"Health Care","name_zh":"\\u533b\\u7597\\u4fdd\\u5065","windows":{"5":{"status":"available","absolute_return_pct":2.994012,"relative_wealth_pct":0.034414,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.157895,"relative_wealth_pct":0.15124,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":57.798165,"relative_wealth_pct":0.664347,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}},{"group_id":"XLY","name_en":"Consumer Discretionary","name_zh":"\\u975e\\u5fc5\\u9700\\u6d88\\u8d39","windows":{"5":{"status":"available","absolute_return_pct":2.97619,"relative_wealth_pct":0.017105,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":6,"expected_n":6,"ratio":1.0}},"20":{"status":"available","absolute_return_pct":13.071895,"relative_wealth_pct":0.075126,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":21,"expected_n":21,"ratio":1.0}},"63":{"status":"available","absolute_return_pct":57.272727,"relative_wealth_pct":0.329154,"null_reasons":{"absolute_return_pct":null,"relative_wealth_pct":null},"coverage":{"observed_n":64,"expected_n":64,"ratio":1.0}}}}],"diagnostics":{"panel_rows":64,"malformed_rows":0,"duplicate_sessions":[],"ambiguous_columns":[],"columns":["SPY","XLB","XLC","XLE","XLF","XLI","XLK","XLP","XLRE","XLU","XLV","XLY"],"binding_keys":[],"receipt_withheld":false,"future_tail_sessions":[],"expected_columns":12,"qualification_reasons":[],"measured_cells":30,"complete_cells":30,"total_cells":33,"coverage_note":"observed_n counts usable observations inside the window; an interior gap never moves an endpoint"},"authority":{"may_rank":false,"may_gate":false,"may_size":false,"may_trade":false,"may_escalate":false}}}')


@pytest.mark.parametrize("case", list(_PARENT_OWNER_CASES))
def test_actual_producer_independent_returns_and_coverage_survive_real_handler(monkeypatch, case):
    companion = copy.deepcopy(_PARENT_OWNER_CASES[case])
    result, _, text = decoded_window(monkeypatch, window_parent(companion), "XLB")
    assert result["consumer_reason"] is None
    assert result["cohort_status"] == "native_contract_admitted"
    selected = companion["groups"][0]
    for index, key in enumerate(WINDOW_KEYS):
        source = selected["windows"][key]
        assert result["selected"]["absolute_return_pct"][index] == source["absolute_return_pct"]
        assert result["selected"]["relative_wealth_pct"][index] == source["relative_wealth_pct"]
        assert result["selected"]["observed_n"][index] == source["coverage"]["observed_n"]
        assert result["windows"][key]["benchmark_return_pct"] == companion["windows"][key]["benchmark_return_pct"]
    if case == "absolute_percent_overflow":
        assert result["selected"]["absolute_return_pct"][0] is None
        assert result["selected"]["relative_wealth_pct"][0] == 9900.0
        assert result["reason_table"][result["selected"]["absolute_reason_refs"][0]] == "non_finite_input"
    elif case == "missing_benchmark":
        assert result["windows"]["5"]["benchmark_return_pct"] is None
        assert result["selected"]["absolute_return_pct"][0] is not None
        assert result["selected"]["relative_wealth_pct"][0] is None
        assert all(row["windows"]["5"]["relative_wealth_pct"] is None for row in companion["groups"])
    elif case == "interior_gap":
        assert result["selected"]["observed_n"] == [5, 20, 63]
        assert [result["windows"][key]["start_session"] for key in WINDOW_KEYS] == [
            "2026-10-29", "2026-10-08", "2026-08-07"]
    elif case == "zero_short_coverage":
        assert result["selected"]["observed_n"] == [0, 15, 58]
        assert result["selected"]["coverage_ratio"][0] == 0.0
        assert result["selected"]["absolute_return_pct"] == [None, None, None]
    assert len(text.encode("utf-8")) <= 7200


@pytest.mark.parametrize("value", [-100, 0, -0.0, 1e12])
def test_return_domain_has_no_arbitrary_cap(monkeypatch, value):
    companion = window_fixture("sector_window_measurements.complete.v1.json")
    selected = next(row for row in companion["groups"] if row["group_id"] == "XLK")
    selected["windows"]["5"]["absolute_return_pct"] = value
    result, _, _ = decoded_window(monkeypatch, window_parent(companion), "XLK")
    assert result["consumer_reason"] is None
    assert result["selected"]["absolute_return_pct"][0] == value


def test_signed_zero_is_preserved_and_not_flattened(monkeypatch):
    companion = window_fixture("sector_window_measurements.complete.v1.json")
    result, _, _ = decoded_window(monkeypatch, window_parent(companion), "XLP")
    assert result["consumer_reason"] is None
    value = result["selected"]["relative_wealth_pct"][2]
    assert value == 0.0
    assert math.copysign(1.0, value) < 0
    assert result["selected"]["relative_wealth_pct"][0] == 0.0
    assert math.copysign(1.0, result["selected"]["relative_wealth_pct"][0]) > 0


WINDOW_MALFORMED = [
    (["schema"], "unrecognized/v2"),
    (["status"], "current"),
    (["reason"], "not_a_reason"),
    (["units"], "fraction"),
    (["price_basis"], "unadjusted"),
    (["benchmark"], "SPY\n"),
    (["cohort_id"], "us_baskets"),
    (["population"], "twelve_sector_etf_proxies"),
    (["source_session"], "2026-02-30"),
    (["end_session"], "2026-11-04"),
    (["windows_sessions"], [20, 63]),
    (["endpoint_definition"], "Endpoint return: something else entirely."),
    (["windows", "5", "window_sessions"], 20),
    (["windows", "5", "end_session"], "2026-11-04"),
    (["windows", "5", "start_session"], "2026-11-06"),
    (["windows", "5", "benchmark_null_reason"], "benchmark_missing"),
    (["windows", "5", "null_reason"], "invalid_price"),
    (["windows", "5", "benchmark_coverage", "expected_n"], 20),
    (["groups", 0, "group_id"], "XLC"),
    (["groups", 0, "windows", "5", "status"], "partial"),
    (["groups", 0, "windows", "5", "absolute_return_pct"], None),
    (["groups", 0, "windows", "5", "null_reasons", "absolute_return_pct"], "contradiction"),
    (["groups", 0, "windows", "5", "coverage", "observed_n"], 99),
    (["groups", 0, "windows", "5", "coverage", "ratio"], 0.5),
    (["groups", 0, "name_en"], "x" * 121),
    (["diagnostics", "measured_cells"], 32),
    (["diagnostics", "complete_cells"], 32),
    (["diagnostics", "qualification_reasons"], ["future_tail"]),
    (["diagnostics", "columns"], ["XLK", "XLB"]),
    (["authority", "may_rank"], True),
    (["authority", "may_trade"], 1),
    (["clocks", "publication"], "2026-11-05T10:00:00"),
    (["limitations", "availability", "status"], "supplied"),
    (["source_roots"], ["x" * 257]),
    (["receipt"], {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": 1}}}}}}}}}),
]


@pytest.mark.parametrize("path,value", WINDOW_MALFORMED)
def test_invalid_member_refuses_the_whole_projection(monkeypatch, path, value):
    companion = window_fixture("sector_window_measurements.complete.v1.json")
    set_path(companion, path, value)
    result, _, _ = decoded_window(monkeypatch, window_parent(companion), "XLK")
    assert result["consumer_reason"] == "invalid_window_contract"
    assert result["cohort_status"] == "expected_not_admitted"
    assert [row["group_id"] for row in result["groups"]] == IDS
    assert result["selected"] is None
    assert result["windows"] == {}
    assert result["reason_table"] == ["invalid_window_contract"]
    assert result["source_session"] is None
    assert result["end_session"] is None
    assert all(clock is None for clock in result["clocks"].values())


def test_identity_order_and_window_shape_must_be_exact(monkeypatch):
    companion = window_fixture("sector_window_measurements.complete.v1.json")
    companion["groups"][0], companion["groups"][1] = companion["groups"][1], companion["groups"][0]
    result, _, _ = decoded_window(monkeypatch, window_parent(companion), "XLK")
    assert result["consumer_reason"] == "invalid_window_contract"

    companion = window_fixture("sector_window_measurements.complete.v1.json")
    companion["groups"][0]["windows"]["10"] = copy.deepcopy(companion["groups"][0]["windows"]["5"])
    result, _, _ = decoded_window(monkeypatch, window_parent(companion), "XLK")
    assert result["consumer_reason"] == "invalid_window_contract"

    companion = window_fixture("sector_window_measurements.complete.v1.json")
    del companion["groups"][0]["windows"]["63"]
    result, _, _ = decoded_window(monkeypatch, window_parent(companion), "XLK")
    assert result["consumer_reason"] == "invalid_window_contract"


@pytest.mark.parametrize("kwargs", [
    {"schema": "leadership_rotation_context.measured_group_read/v2"},
    {"status": "current"},
    {"generation": {"session_end": "2026-11-04"}},
    {"generation": {"benchmark": "QQQ"}},
    {"generation": {"cohort_id": "us_baskets"}},
    {"generation": {"price_basis": "price"}},
])
def test_parent_binding_is_required(monkeypatch, kwargs):
    companion = window_fixture("sector_window_measurements.complete.v1.json")
    result, _, _ = decoded_window(monkeypatch, window_parent(companion, **kwargs), "XLK")
    assert result["consumer_reason"] == "invalid_window_contract"


def test_parent_benchmark_normalization_is_derived_not_hardcoded(monkeypatch):
    companion = window_fixture("sector_window_measurements.complete.v1.json")
    companion["benchmark"] = "QQQ"
    parent = window_parent(companion, generation={"benchmark": " qqq "})
    result, _, _ = decoded_window(monkeypatch, parent, "XLK")
    assert result["consumer_reason"] is None
    assert result["benchmark"] == "QQQ"


def test_missing_artifact_or_companion_refuses_without_legacy_fallback(monkeypatch):
    monkeypatch.setattr(pi, "_read_vendor", lambda *a, **k: (None, {"status": "missing"}))
    packet = pi.sector_rotation(projection="sector_windows", sector="XLK")
    assert packet["consumer_reason"] == "window_companion_not_supplied"
    assert packet["cohort_status"] == "expected_not_admitted"
    assert packet["artifact_health"]["status"] == "missing"
    assert [row["group_id"] for row in packet["groups"]] == IDS

    companion = window_fixture("sector_window_measurements.complete.v1.json")
    measured = window_parent(companion)
    del measured["sector_window_measurements"]
    result, _, _ = decoded_window(monkeypatch, measured, "XLK")
    assert result["consumer_reason"] == "window_companion_not_supplied"
    assert [row["group_id"] for row in result["groups"]] == IDS


@pytest.mark.parametrize("args", [
    {"projection": "sector_windows"},
    {"projection": "sector_windows", "sector": "XLK "},
    {"projection": "sector_windows", "sector": "xlk"},
    {"projection": "sector_windows", "sector": "SPY"},
    {"projection": "sector_windows", "sector": None},
    {"projection": "sector_windows", "sector": 5},
    {"projection": "sector_windows", "sector": ["XLK"]},
    {"sector": "XLK"},
    {"sector": None},
    {"projection": "legacy", "sector": "XLK"},
    {"projection": "sector_dossiers", "sector": "XLK"},
])
def test_invalid_or_incompatible_selectors_never_fall_back_to_legacy(monkeypatch, args):
    monkeypatch.setattr(pi, "_read_vendor", lambda *a, **k: pytest.fail("must not read"))
    wire = asyncio.run(autonomous_mcp.get_sector_rotation.handler(args))
    text = wire["content"][0]["text"]
    packet = json.loads(text)
    assert len(text) <= 7200
    assert "_transport_truncated" not in packet
    assert packet["schema"] == WINDOW_PACKET_SCHEMA
    assert packet["cohort_status"] == "expected_not_admitted"
    assert [row["group_id"] for row in packet["groups"]] == IDS
    assert "sectors" not in packet
    assert packet["selected"] is None


def test_large_valid_metadata_is_validated_but_never_projected(monkeypatch):
    companion = window_fixture("sector_window_measurements.complete.v1.json")
    companion["receipt"] = {f"key_{index}": "v" * 400 for index in range(32)}
    companion["source_roots"] = [f"root/{index}" + "x" * 200 for index in range(32)]
    result, _, text = decoded_window(monkeypatch, window_parent(companion), "XLK")
    assert result["consumer_reason"] is None
    assert "receipt" not in result
    assert "source_roots" not in result
    assert result["metadata_projection"] == {
        "receipt": "not_projected", "source_roots": "not_projected"}
    assert len(text) <= 7200


def test_compact_budget_refuses_the_whole_projection_before_transport(monkeypatch):
    companion = window_fixture("sector_window_measurements.complete.v1.json")
    # The real compact path is measured against the real serializer text; the threshold is
    # tightened so the overflow branch is exercised end to end rather than assumed.
    monkeypatch.setattr(pi, "_PSL_MAX_BYTES", 3000)
    result, _, text = decoded_window(monkeypatch, window_parent(companion), "XLK")
    assert result["consumer_reason"] == "window_transport_budget_exceeded"
    assert result["cohort_status"] == "expected_not_admitted"
    assert [row["group_id"] for row in result["groups"]] == IDS
    assert result["selected"] is None
    assert result["windows"] == {}
    assert len(text) <= 7200
    assert "_transport_truncated" not in result


def test_valid_companion_fits_the_real_transport_budget_with_headroom(monkeypatch):
    companion = window_fixture("sector_window_measurements.complete.v1.json")
    companion["clocks"] = {
        "publication": "2026-11-05T16:00:00+00:00",
        "availability": "2026-11-05T15:59:59.500000+00:00",
        "correction": "2026-11-05T16:30:00+00:00",
        "history": "2026-11-05T16:45:00+00:00",
    }
    companion["limitations"] = {
        "availability": {"status": "supplied", "clock": companion["clocks"]["availability"]},
        "publication": {"status": "supplied", "clock": companion["clocks"]["publication"]},
        "history": {"status": "supplied", "clock": companion["clocks"]["history"]},
        "corrections": {"status": "unavailable", "reason": "native_revision_selection_not_supplied"},
        "freshness": {"status": "unverified", "reason": "owner_freshness_receipt_not_supplied"},
        "point_in_time": {"status": "not_qualified",
                          "reason": "point_in_time_admission_not_supplied"},
    }
    selected = next(row for row in companion["groups"] if row["group_id"] == "XLK")
    selected["name_en"] = "n" * 120
    selected["name_zh"] = "z" * 120
    result, _, text = decoded_window(monkeypatch, window_parent(companion), "XLK")
    assert result["consumer_reason"] is None
    assert result["clocks"] == companion["clocks"]
    assert result["limitations"] == companion["limitations"]
    assert len(text) <= 7200
    assert len(text.encode("utf-8")) <= 7200


def test_legacy_and_dossier_projections_ignore_the_companion(monkeypatch):
    sectors = [
        {"ticker": f"S{index}", "name": f"Sector {index}", "rotation": {"rank": 10 - index}}
        for index in range(8)]
    legacy_data = {"as_of": "2026-10-09", "market": {"risk_on": False},
                    "sectors": sectors, "baskets": []}
    health = {"status": "stale", "as_of": "2026-10-09", "stale": True}
    monkeypatch.setattr(pi, "_read_vendor", lambda *a, **k: (legacy_data, health))
    before = json.dumps(pi.sector_rotation(), ensure_ascii=False)
    legacy_data["measured_read"] = window_parent(
        window_fixture("sector_window_measurements.complete.v1.json"))
    assert json.dumps(pi.sector_rotation(), ensure_ascii=False) == before
    assert json.dumps(pi.sector_rotation(projection="legacy"), ensure_ascii=False) == before
    for args in ({}, {"projection": "legacy"}):
        wire = asyncio.run(autonomous_mcp.get_sector_rotation.handler(args))
        assert wire == bot_mcp._json(json.loads(before))
    assert "sector_dossiers" not in json.loads(before)

    # The closed 21/63 dossier projection is identical with the companion absent and present.
    dossier = fixture()
    without = {"as_of": "2026-10-09", "measured_read": copy.deepcopy(dossier)}
    with_companion = copy.deepcopy(without)
    with_companion["measured_read"]["sector_window_measurements"] = window_fixture(
        "sector_window_measurements.complete.v1.json")
    broken = copy.deepcopy(with_companion)
    broken["measured_read"]["sector_window_measurements"]["groups"][0]["group_id"] = "XLC"
    projections = []
    for artifact in (without, with_companion, broken):
        monkeypatch.setattr(pi, "_read_vendor", lambda *a, _a=artifact, **k: (_a, health))
        projected = pi.sector_rotation(projection="sector_dossiers")
        assert projected["consumer_reason"] is None
        assert len(projected["groups"]) == 11
        projections.append(projected)
    assert projections[0] == projections[1] == projections[2]


def test_tool_argument_schema_adds_only_the_intended_selectors():
    schema = autonomous_mcp.get_sector_rotation.input_schema
    assert set(schema["properties"]) == {"limit", "projection", "sector"}
    assert schema["properties"]["projection"]["enum"] == [
        "legacy", "sector_dossiers", "sector_windows"]
    assert schema["properties"]["sector"]["enum"] == list(pi.PSL_SECTOR_IDS)
    for banned in ("path", "file", "source", "artifact", "url", "date", "as_of", "ticker"):
        assert banned not in schema["properties"]


def test_limit_one_retains_all_eleven_identities(monkeypatch):
    companion = window_fixture("sector_window_measurements.complete.v1.json")
    result, _, _ = decoded_window(monkeypatch, window_parent(companion), "XLK",
                                   args={"projection": "sector_windows", "sector": "XLK",
                                         "limit": 1})
    assert [row["group_id"] for row in result["groups"]] == IDS
    assert result["selected"]["group_id"] == "XLK"


def test_window_projection_result_is_detached(monkeypatch):
    companion = window_fixture("sector_window_measurements.complete.v1.json")
    measured = window_parent(companion)
    data, _ = bind_window(monkeypatch, measured)
    before = copy.deepcopy(data)
    result = pi.sector_rotation(projection="sector_windows", sector="XLK")
    result["selected"]["absolute_return_pct"][0] = 999
    result["groups"][0]["window_status"][0] = "changed"
    result["clocks"]["publication"] = "changed"
    result["windows"]["5"]["benchmark_return_pct"] = 999
    assert data == before



@pytest.mark.parametrize("change", [
    "receipt_ascii_size", "receipt_container_length", "receipt_withheld_present",
    "selected_absolute_floor", "unselected_relative_floor", "benchmark_floor",
    "blocked_benchmark", "missing_benchmark_dependency", "local_block_cause",
    "local_insufficient_cause", "relative_only_missing", "relative_only_invalid",
    "duplicate_bad_date", "future_bad_date", "fractional_typed_count", "float_window",
])
def test_parent_window_source_counterexamples_refuse_whole_projection(monkeypatch, change):
    companion = window_fixture("sector_window_measurements.unavailable.v1.json"
        if change == "blocked_benchmark" else "sector_window_measurements.complete.v1.json")
    selected = companion["groups"][5]["windows"]["5"]
    if change == "receipt_ascii_size": companion["receipt"] = {"a": "中" * 3000}
    elif change == "receipt_container_length": companion["receipt"] = {"a": [0] * 257}
    elif change == "receipt_withheld_present":
        companion["receipt"] = {"a": 1}; companion["diagnostics"]["receipt_withheld"] = True
    elif change == "selected_absolute_floor": selected["absolute_return_pct"] = -100.01
    elif change == "unselected_relative_floor": companion["groups"][0]["windows"]["5"]["relative_wealth_pct"] = -100.01
    elif change == "benchmark_floor": companion["windows"]["5"]["benchmark_return_pct"] = -100.01
    elif change == "blocked_benchmark":
        companion["windows"]["5"].update(benchmark_return_pct=1.0, benchmark_null_reason=None)
    elif change == "missing_benchmark_dependency":
        companion["windows"]["5"].update(benchmark_return_pct=None, benchmark_null_reason="benchmark_missing")
    elif change in ("local_block_cause", "local_insufficient_cause"):
        selected["absolute_return_pct"] = selected["relative_wealth_pct"] = None
        cause = "future_tail" if change == "local_block_cause" else "insufficient_reference_history"
        selected["null_reasons"] = dict.fromkeys(("absolute_return_pct", "relative_wealth_pct"), cause)
        recompute_native(companion)
    elif change in ("relative_only_missing", "relative_only_invalid"):
        selected["absolute_return_pct"] = None
        selected["null_reasons"]["absolute_return_pct"] = (
            "missing_input" if change == "relative_only_missing" else "invalid_price")
        recompute_native(companion)
    elif change == "duplicate_bad_date": companion["diagnostics"]["duplicate_sessions"] = ["2026-02-30"]
    elif change == "future_bad_date": companion["diagnostics"]["future_tail_sessions"] = ["2026-02-30"]
    elif change == "fractional_typed_count": companion["diagnostics"]["panel_rows"] = 300.0
    elif change == "float_window": companion["windows"]["5"]["window_sessions"] = 5.0
    result, _, _ = decoded_window(monkeypatch, window_parent(companion), "XLK")
    assert result["consumer_reason"] == "invalid_window_contract"
    assert result["cohort_status"] == "expected_not_admitted"
    assert [row["group_id"] for row in result["groups"]] == IDS
    assert result["selected"] is None and result["windows"] == {}


@pytest.mark.parametrize("receipt", [{"a": "中" * 3000}, {"a": [0] * 257}])
def test_parent_receipt_admission_precedes_any_container_serialization(monkeypatch, receipt):
    companion = window_fixture("sector_window_measurements.complete.v1.json")
    companion["receipt"] = receipt
    original = pi.json.dumps
    def checked(value, *args, **kwargs):
        if value is companion or value is receipt:
            raise AssertionError("unqualified source container serialized")
        return original(value, *args, **kwargs)
    monkeypatch.setattr(pi.json, "dumps", checked)
    result = pi._sector_window_projection(
        {"measured_read": window_parent(companion)}, None, "XLK")
    assert result["consumer_reason"] == "invalid_window_contract"

@pytest.mark.parametrize("scope", ["group", "benchmark"])
@pytest.mark.parametrize("observed", [0, 1, 2, 22])
def test_parent_nested_window_coverage_is_one_captured_panel(monkeypatch, scope, observed):
    companion = window_fixture("sector_window_measurements.complete.v1.json")
    windows = companion["windows"] if scope == "benchmark" else companion["groups"][0]["windows"]
    key = "5" if observed < 3 else "63"
    count = observed if observed < 3 else 20
    coverage = windows[key]["benchmark_coverage" if scope == "benchmark" else "coverage"]
    coverage.update(observed_n=count, ratio=round(count / coverage["expected_n"], 6))
    result, _, _ = decoded_window(monkeypatch, window_parent(companion), "XLK")
    assert result["consumer_reason"] == "invalid_window_contract"


@pytest.mark.parametrize("receipt", [
    {"many": [None] * 256},
    {str(i): [{} for _ in range(10)] for i in range(32)},
    {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": 1}}}}}}}},
])
def test_parent_opaque_receipt_uses_owner_container_and_depth_bounds(monkeypatch, receipt):
    companion = window_fixture("sector_window_measurements.complete.v1.json")
    companion["receipt"] = receipt
    result, _, _ = decoded_window(monkeypatch, window_parent(companion), "XLK")
    assert result["consumer_reason"] is None
    assert "receipt" not in result
