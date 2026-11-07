"""All-eleven dossier parity through the actual existing MCP handler and serializer.

Fixtures are byte-identical Macro producer outputs at 378e289b180b90ed2902a7689e960932a8a26fe6,
also retained by Terminal 260002504a80e2ce297cec2a82b2f5c73290816c. No live portfolio,
network, model, SDK turn or publication is invoked. Native source health remains unverified.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
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
