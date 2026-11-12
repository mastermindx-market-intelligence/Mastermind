"""Captured native input -> real Portfolio consumers and MCP serialization.

These tests qualify consumer composition, not the upstream publisher or native
owner modules. No replacement producer, generation store or live service runs.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
import importlib
import json
from types import SimpleNamespace

import pytest

from brain import portfolio_intelligence as pi
from portfolio import prophet_feed


def _write(root, path, value):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value))


@pytest.fixture
def captured(monkeypatch, tmp_path):
    day = datetime.now(UTC).date().isoformat()
    root = tmp_path / "macro"
    monkeypatch.setattr(pi, "_V", root)
    monkeypatch.setattr(pi, "_ROOT", tmp_path / "mastermind")
    monkeypatch.setattr(prophet_feed, "index", lambda: {})
    monkeypatch.setattr(prophet_feed, "plans", list)
    receipt = {
        "schema": "sector_native_view.receipt.v1", "source": "macro.sector",
        "generation_id": "captured-generation-one", "source_session": day,
        "published_at": f"{day}T20:00:00Z", "qualification": "accepted",
        "input_version": "captured-input-one", "baseline_session": None,
        "content_sha256": "a" * 64,
    }
    state = SimpleNamespace(
        root=root, day=day, calls=[], static_reads=[],
        central={"as_of": day, "market": {"headline_en": "CAPTURE_ONE", "risk_on": True},
                 "sectors": [{"ticker": "XLK", "name": "Technology",
                              "rotation": {"rank": 1}, "conviction": {"score": 80}}],
                 "baskets": []},
        health={"artifact": "sectordata/sector_central.json", "available": True,
                "status": "fresh", "as_of": day, "stale": False, "authority": "context",
                "execution_authority": False, "source_mode": "selected_generation",
                "native_receipt": receipt},
    )

    def read_sector():
        state.calls.append(state.health.get("native_receipt", {}).get("generation_id"))
        return deepcopy(state.central), deepcopy(state.health)

    original_vendor = pi._read_vendor

    def read_vendor(rel, **kwargs):
        if rel == "site/sectordata/sector_central.json":
            state.static_reads.append(rel)
        return original_vendor(rel, **kwargs)

    monkeypatch.setattr(pi, "_read_sector_central", read_sector)
    monkeypatch.setattr(pi, "_read_vendor", read_vendor)
    return state


def _consume(kind):
    if kind == "surface":
        return pi.surface_packet("sector_central", limit=1)
    if kind == "catalog":
        return pi.context_catalog()
    return pi.market_packet()


def _sector_source(packet, kind):
    if kind == "surface":
        return packet["artifacts"][0]["source"]
    if kind == "catalog":
        row = next(row for row in packet["surfaces"] if row["id"] == "sector_central")
        return row["artifacts"][0]
    return packet["sector_rotation"]["health"]


def _assert_wire_preserves(packet):
    pytest.importorskip("claude_agent_sdk")
    from brain import bot_mcp

    response = bot_mcp._json(packet)
    text = response["content"][0]["text"]
    assert json.loads(text) == packet
    assert len(text.encode("utf-8")) <= 7900
    assert "_transport_truncated" not in packet
    assert not packet.get("packet_truncated", False)
    return text


@pytest.mark.parametrize("kind", ("surface", "catalog", "market"))
@pytest.mark.parametrize("static_present", (False, True), ids=("static-absent", "static-conflict"))
def test_native_consumers_use_one_capture_and_its_provenance(captured, kind, static_present):
    if static_present:
        _write(captured.root, "site/sectordata/sector_central.json", {
            "as_of": "2000-01-01", "market": {"headline_en": "UNRELATED_STATIC"}})

    result = _consume(kind)

    assert captured.calls == ["captured-generation-one"]
    assert captured.static_reads == []
    source = _sector_source(result, kind)
    assert source["available"] is True
    assert source["status"] == "fresh"
    assert source["source_mode"] == "selected_generation"
    assert source["native_receipt"] == captured.health["native_receipt"]
    assert source["stale"] is False
    assert source["execution_authority"] is False
    if kind == "surface":
        assert result["status"] == "ok"
        content = result["artifacts"][0]["content"]
        assert content["market"]["headline_en"] == "CAPTURE_ONE"
        assert content["health"]["native_receipt"] == source["native_receipt"]
    if kind == "market":
        assert result["sector_rotation"]["market"]["headline_en"] == "CAPTURE_ONE"
        critical = next(row for row in result["data_health"]["critical"]
                        if row["id"] == "sector_central")
        assert (critical["status"], critical["available"]) == ("fresh", True)
    _assert_wire_preserves(result)


@pytest.mark.parametrize("kind", ("surface", "catalog", "market"))
def test_fresh_static_cannot_conceal_native_unavailability(captured, kind):
    _write(captured.root, "site/sectordata/sector_central.json", {"as_of": captured.day})
    captured.central = None
    captured.health.update(available=False, status="missing", as_of=None, stale=None,
                           source_reason="native_generation_not_selected")
    captured.health.pop("native_receipt")

    result = _consume(kind)

    assert captured.calls == [None]
    assert captured.static_reads == []
    source = _sector_source(result, kind)
    assert source["available"] is False
    assert source["status"] == "missing"
    assert source["source_reason"] == "native_generation_not_selected"
    assert source["source_mode"] == "selected_generation"
    if kind == "surface":
        assert result["status"] == "unavailable"
        assert result["artifacts"][0]["content"] is None
    if kind == "market":
        critical = next(row for row in result["data_health"]["critical"]
                        if row["id"] == "sector_central")
        assert (critical["status"], critical["available"]) == ("missing", False)
    _assert_wire_preserves(result)


@pytest.mark.parametrize("kind", ("surface", "catalog", "market"))
def test_native_degraded_is_unknown_without_invented_staleness(captured, kind):
    captured.health.update(status="unknown", stale=None)
    captured.health["native_receipt"]["qualification"] = "degraded"

    result = _consume(kind)

    source = _sector_source(result, kind)
    assert source["status"] == "unknown"
    assert source["available"] is True
    assert source["stale"] is None
    assert source["native_receipt"]["qualification"] == "degraded"
    if kind == "catalog":
        row = next(row for row in result["surfaces"] if row["id"] == "sector_central")
        assert row["status"] == "unknown"
    if kind == "market":
        assert result["data_health"]["counts"]["unknown"] == 1
        assert sum(result["data_health"]["counts"].values()) == len(pi._SURFACES)
    assert len(captured.calls) == 1
    _assert_wire_preserves(result)


@pytest.mark.parametrize("kind", ("surface", "catalog", "market"))
@pytest.mark.parametrize("reason", ("invalid_legacy_rotation_input",
                                    "native_legacy_transport_budget_exceeded"))
def test_consumer_refusal_reason_survives_outer_projection(captured, kind, reason):
    if reason == "invalid_legacy_rotation_input":
        captured.central["baskets"] = 1
    else:
        captured.central["sectors"][0]["name"] = "界" * 3000

    result = _consume(kind)

    source = _sector_source(result, kind)
    assert source["available"] is False
    assert source["status"] == ("malformed" if reason == "invalid_legacy_rotation_input" else "unknown")
    assert source["source_reason"] == reason
    assert source["native_receipt"] == captured.health["native_receipt"]
    assert len(captured.calls) == 1
    _assert_wire_preserves(result)


def test_surface_refuses_utf8_content_overflow_without_compaction(captured):
    captured.central["sectors"][0]["name"] = "界" * 1700
    direct = pi.sector_rotation(limit=1)
    size = len(json.dumps(direct, ensure_ascii=False).encode("utf-8"))
    assert 6300 < size <= 7200
    captured.calls.clear()

    result = pi.surface_packet("sector_central", limit=1)

    assert result["status"] == "unavailable"
    assert result["artifacts"][0]["content"] is None
    source = result["artifacts"][0]["source"]
    assert source["available"] is False
    assert source["source_reason"] == "native_surface_content_budget_exceeded"
    assert source["native_receipt"] == captured.health["native_receipt"]
    assert len(captured.calls) == 1
    _assert_wire_preserves(result)


def test_catalog_refuses_whole_oversize_packet_but_retains_fixed_identities(captured):
    _write(captured.root, "data/regime/latest.json", {"asof": "unparsed-clock" * 900})

    result = pi.context_catalog()

    assert result["status"] == "unavailable"
    assert result["consumer_reason"] == "native_catalog_transport_budget_exceeded"
    assert [row["id"] for row in result["surfaces"]] == [row["id"] for row in pi._SURFACES]
    assert all(row["available"] is False and row["status"] == "unknown"
               and row["artifacts"] == [] for row in result["surfaces"])
    assert result["source"]["native_receipt"] == captured.health["native_receipt"]
    assert result["source"]["available"] is False
    assert result["policy"]["signals_are_context_not_orders"] is True
    assert len(captured.calls) == 1
    _assert_wire_preserves(result)


def test_market_uses_unfit_catalog_observations_without_a_second_capture(captured):
    _write(captured.root, "site/basketdata/foresight_cascade.json", {
        "as_of": "unparsed-clock" * 900})
    assert pi.context_catalog()["consumer_reason"] == "native_catalog_transport_budget_exceeded"
    captured.calls.clear()

    result = pi.market_packet()

    assert "consumer_reason" not in result
    assert result["sector_rotation"]["market"]["headline_en"] == "CAPTURE_ONE"
    assert result["data_health"]["counts"]["undated"] == 1
    assert len(captured.calls) == 1
    _assert_wire_preserves(result)


def test_surface_checks_complete_wrapper_after_content_fits(captured):
    # Exercise the existing disclosure maxima, not upstream generation admission.
    captured.health["native_receipt"].update(generation_id="𐀀" * 128, input_version="𐀀" * 128)
    captured.central["sectors"][0]["name"] = "界" * 1260
    direct = pi.sector_rotation(limit=1)
    assert direct["health"]["available"] is True
    assert len(json.dumps(direct, ensure_ascii=False).encode("utf-8")) <= 6300
    captured.calls.clear()

    result = pi.surface_packet("sector_central", limit=1)

    assert result["status"] == "unavailable"
    assert result["artifacts"][0]["content"] is None
    source = result["artifacts"][0]["source"]
    assert source["source_reason"] == "native_surface_transport_budget_exceeded"
    assert source["native_receipt"] == captured.health["native_receipt"]
    assert len(captured.calls) == 1
    _assert_wire_preserves(result)


def test_market_refuses_whole_utf8_oversize_packet(captured):
    _write(captured.root, "data/regime/latest.json", {
        "asof": captured.day, "quad_name": "界" * 4000})

    result = pi.market_packet()

    assert result["status"] == "unavailable"
    assert result["consumer_reason"] == "native_market_transport_budget_exceeded"
    assert "sector_rotation" not in result
    assert "regime" not in result
    assert result["source"]["available"] is False
    assert result["source"]["native_receipt"] == captured.health["native_receipt"]
    assert len(captured.calls) == 1
    _assert_wire_preserves(result)


def test_native_source_projection_is_closed_and_bounds_private_metadata(captured):
    captured.health.update(execution_authority=True, private_note="private-metadata" * 1000,
                           source_reason="private-metadata" * 1000)
    source = pi._source_ref(captured.health)
    assert source["execution_authority"] is False
    assert source["authority"] == "context"
    assert source["native_receipt"] == captured.health["native_receipt"]
    assert "source_reason" not in source
    assert "private-metadata" not in json.dumps(source)


@pytest.mark.parametrize("module_name", ("brain.autonomous_mcp", "brain.china_mcp", "brain.hk_mcp"))
@pytest.mark.parametrize("tool_name", ("get_surface_packet", "get_context_catalog"))
def test_actual_book_handlers_preserve_captured_native_receipt(captured, module_name, tool_name):
    pytest.importorskip("claude_agent_sdk")
    module = importlib.import_module(module_name)
    args = {"surface_id": "sector_central", "limit": 1} if tool_name == "get_surface_packet" else {}

    response = asyncio.run(getattr(module, tool_name).handler(args))

    text = response["content"][0]["text"]
    result = json.loads(text)
    kind = "surface" if tool_name == "get_surface_packet" else "catalog"
    assert _sector_source(result, kind)["native_receipt"] == captured.health["native_receipt"]
    assert captured.calls == ["captured-generation-one"]
    assert len(text.encode("utf-8")) <= 7900
    assert "_transport_truncated" not in result


def test_actual_us_market_handler_preserves_captured_native_receipt(captured):
    pytest.importorskip("claude_agent_sdk")
    from brain import autonomous_mcp

    response = asyncio.run(autonomous_mcp.get_market_packet.handler({}))

    text = response["content"][0]["text"]
    result = json.loads(text)
    assert result["sector_rotation"]["health"]["native_receipt"] == captured.health["native_receipt"]
    assert result["book"]["book"] == "autonomous"
    assert captured.calls == ["captured-generation-one"]
    assert len(text.encode("utf-8")) <= 7900
    assert "_transport_truncated" not in result
