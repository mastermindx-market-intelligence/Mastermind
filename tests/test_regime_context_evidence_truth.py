"""The Brain regime tool must preserve core and optional-context availability truth."""
from __future__ import annotations

import asyncio
import importlib
import json
import sys
import types
from pathlib import Path
from contextlib import contextmanager

import pytest


@contextmanager
def _bot_mcp_with_fake_sdk(monkeypatch):
    import brain

    missing = object()
    previous_module = sys.modules.get("brain.bot_mcp", missing)
    previous_attribute = vars(brain).get("bot_mcp", missing)
    fake = types.ModuleType("claude_agent_sdk")

    class ToolWrap:
        def __init__(self, name, handler):
            self.name = name
            self.handler = handler

    def tool(name, _description, _schema):
        def deco(fn):
            return ToolWrap(name, fn)
        return deco

    fake.tool = tool
    fake.create_sdk_mcp_server = lambda **kwargs: kwargs
    with monkeypatch.context() as sdk_patch:
        sdk_patch.setitem(sys.modules, "claude_agent_sdk", fake)
        sys.modules.pop("brain.bot_mcp", None)
        vars(brain).pop("bot_mcp", None)
        try:
            yield importlib.import_module("brain.bot_mcp")
        finally:
            if previous_module is missing:
                sys.modules.pop("brain.bot_mcp", None)
            else:
                sys.modules["brain.bot_mcp"] = previous_module
            if previous_attribute is missing:
                vars(brain).pop("bot_mcp", None)
            else:
                setattr(brain, "bot_mcp", previous_attribute)


@pytest.fixture
def bot_mcp(monkeypatch):
    with _bot_mcp_with_fake_sdk(monkeypatch) as module:
        yield module


def _text(result: dict) -> str:
    return result["content"][0]["text"]


_DEFAULT_REGIME = object()


def _write_regime(vendor, payload=_DEFAULT_REGIME):
    path = vendor / "data" / "regime" / "latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": "2026-09-17",
        "quad": "Q1",
        "quad_name": "Goldilocks",
        "growth_score": 1.2,
        "inflation_score": -0.4,
        "liquidity_overlay": "supportive",
        "cycle_tag": "mid",
        "sector_rs": [{"ticker": "XLK"}],
    } if payload is _DEFAULT_REGIME else payload
    path.write_text(json.dumps(payload))
    return path


def _wire_optional_context(monkeypatch, *, market_fail=False, decision_fail=False):
    from brain import decision_context, pm_conviction

    if market_fail:
        def fail_market():
            raise RuntimeError("secret /Users/private/market_view token=do-not-return")
        monkeypatch.setattr(pm_conviction, "_read_market_view", fail_market)
    else:
        monkeypatch.setattr(pm_conviction, "_read_market_view", lambda: None)
        monkeypatch.setattr(pm_conviction, "_market_view_enrichment", lambda _mv: {})

    if decision_fail:
        def fail_decision(**_kwargs):
            raise RuntimeError("secret /Users/private/decision_context api_key=do-not-return")
        monkeypatch.setattr(decision_context, "prompt_summary", fail_decision)
    else:
        monkeypatch.setattr(decision_context, "prompt_summary", lambda **_kwargs: {})


def test_valid_core_with_absent_optional_context_keeps_success_shape(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_regime(vendor)
    _wire_optional_context(monkeypatch)

    payload = json.loads(_text(asyncio.run(bot_mcp.get_regime.handler({}))))
    assert payload["quad"] == "Q1"
    assert payload["sector_rs_top"] == [{"ticker": "XLK"}]
    assert "read_status" not in payload
    assert "failed_sources" not in payload


def test_missing_core_is_explicit_absent_not_false_empty(bot_mcp, tmp_path, monkeypatch):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path / "vendor")
    _wire_optional_context(monkeypatch)

    payload = json.loads(_text(asyncio.run(bot_mcp.get_regime.handler({}))))
    assert payload["read_status"] == "unavailable"
    assert payload["regime_status"] == "absent"
    assert payload["error"] == "regime_core_absent"
    assert payload["quad"] is None
    assert payload["sector_rs_top"] is None


def test_corrupt_core_is_closed_unavailable_not_exception(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    path = vendor / "data" / "regime" / "latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ broken")
    _wire_optional_context(monkeypatch)

    raw = _text(asyncio.run(bot_mcp.get_regime.handler({})))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["regime_status"] == "unavailable"
    assert payload["error"] == "regime_core_unavailable"
    assert payload["failed_sources"] == ["regime"]
    assert payload["sector_rs_top"] is None
    assert "broken" not in raw


def test_market_view_failure_is_partial_and_secret_safe(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_regime(vendor)
    _wire_optional_context(monkeypatch, market_fail=True)

    raw = _text(asyncio.run(bot_mcp.get_regime.handler({})))
    payload = json.loads(raw)
    assert payload["quad"] == "Q1"
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["market_view"]
    assert "secret" not in raw and "/Users/private" not in raw and "do-not-return" not in raw


def test_decision_context_failure_is_partial_and_secret_safe(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_regime(vendor)
    _wire_optional_context(monkeypatch, decision_fail=True)

    raw = _text(asyncio.run(bot_mcp.get_regime.handler({})))
    payload = json.loads(raw)
    assert payload["quad"] == "Q1"
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["decision_context"]
    assert "secret" not in raw and "api_key" not in raw


def test_both_optional_context_failures_are_named_without_losing_core(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_regime(vendor)
    _wire_optional_context(monkeypatch, market_fail=True, decision_fail=True)

    payload = json.loads(_text(asyncio.run(bot_mcp.get_regime.handler({}))))
    assert payload["quad"] == "Q1"
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["market_view", "decision_context"]


def _payload(bot_mcp):
    return json.loads(_text(asyncio.run(bot_mcp.get_regime.handler({}))))


def _healthy_context():
    publication = {"asof": "2026-09-17", "seq": 7, "built_at": "2026-09-17T12:00:00Z"}
    market = {
        "publication": publication,
        "plane_summaries": [{
            "name": "risk_radar", "direction": "risk_off", "status": "advisory",
            "freshness": {"asof": "2026-08-07", "stale": True, "age_sessions": 30},
        }],
        "serving_freshness": {"current_confirmation_available": False},
    }
    decision = {
        "schema_version": "decision_context.v1", "market_asof": "2026-09-17",
        "hard_label": None, "publication": publication,
        "serving_freshness": {"current_assessment_available": False},
        "liquidity": {"quantity_overlay": "neutral", "quality": {"label": "mixed", "asof": "2026-09-16"}},
        "market_driver": {"label": "liquidity", "direction": "neutral", "confidence": 0.5},
        "governor": {"relationship": "unavailable", "confirmed": False, "net_tilt": None},
    }
    return market, decision


def _wire_payloads(monkeypatch, market, decision, calls=None):
    from brain import decision_context, pm_conviction

    monkeypatch.setattr(pm_conviction, "_read_market_view", lambda: {})
    monkeypatch.setattr(pm_conviction, "_market_view_enrichment", lambda _mv: market)

    def summary(**kwargs):
        if calls is not None:
            calls.append(kwargs)
        return decision

    monkeypatch.setattr(decision_context, "prompt_summary", summary)


@pytest.mark.parametrize("value", [None, {}, [], False, 0, "not-a-core"])
def test_present_invalid_core_is_unavailable(bot_mcp, tmp_path, monkeypatch, value):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    _write_regime(tmp_path, value)
    _wire_optional_context(monkeypatch)
    payload = _payload(bot_mcp)
    assert payload["regime_status"] == "unavailable"
    assert payload["failed_sources"] == ["regime"]
    assert payload["error"] == "regime_core_unavailable"
    assert payload["quad"] is None and payload["sector_rs_top"] is None


@pytest.mark.parametrize("value", [False, 0, "", {}, 1, "not-a-list"])
def test_invalid_sector_rows_do_not_look_like_empty_evidence(bot_mcp, tmp_path, monkeypatch, value):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    _write_regime(tmp_path, {"quad": "Q1", "sector_rs": value})
    _wire_optional_context(monkeypatch)
    payload = _payload(bot_mcp)
    assert payload["regime_status"] == "unavailable"
    assert payload["failed_sources"] == ["regime"]
    assert payload["sector_rs_top"] is None


@pytest.mark.parametrize("value", [None, [], [{"ticker": str(n)} for n in range(8)]])
def test_valid_sector_projection_keeps_optional_empty_and_six_row_limit(bot_mcp, tmp_path, monkeypatch, value):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    _write_regime(tmp_path, {"quad": "Q1", "sector_rs": value})
    _wire_optional_context(monkeypatch)
    payload = _payload(bot_mcp)
    assert payload["quad"] == "Q1"
    assert payload["sector_rs_top"] == (value or [])[:6]
    assert "read_status" not in payload


@pytest.mark.parametrize("mode", ["directory", "dangling", "permission", "exists_false"])
def test_core_file_boundary_uses_actual_read_and_true_absence(bot_mcp, tmp_path, monkeypatch, mode):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    path = _write_regime(tmp_path)
    _wire_optional_context(monkeypatch)
    if mode == "directory":
        path.unlink()
        path.mkdir()
    elif mode == "dangling":
        path.unlink()
        path.symlink_to(tmp_path / "missing-core-target")
    elif mode == "permission":
        original = Path.read_text

        def read_text(candidate, *args, **kwargs):
            if candidate == path:
                raise PermissionError("private core secret token=do-not-return")
            return original(candidate, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", read_text)
    else:
        original = Path.exists
        monkeypatch.setattr(Path, "exists", lambda candidate: False if candidate == path else original(candidate))
    raw = _text(asyncio.run(bot_mcp.get_regime.handler({})))
    payload = json.loads(raw)
    if mode == "exists_false":
        assert payload["quad"] == "Q1"
        assert "read_status" not in payload
    else:
        assert payload["regime_status"] == "unavailable"
        assert payload["failed_sources"] == ["regime"]
        assert payload["error"] == "regime_core_unavailable"
    assert "private core" not in raw and "do-not-return" not in raw


def test_absent_core_does_not_query_optional_sources(bot_mcp, tmp_path, monkeypatch):
    from brain import decision_context, pm_conviction

    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    calls = []
    monkeypatch.setattr(pm_conviction, "_read_market_view", lambda: calls.append("market_view"))
    monkeypatch.setattr(pm_conviction, "_market_view_enrichment", lambda _mv: {})
    monkeypatch.setattr(decision_context, "prompt_summary", lambda **_kwargs: calls.append("decision_context"))
    payload = _payload(bot_mcp)
    assert calls == []
    assert payload["regime_status"] == "absent"
    assert "failed_sources" not in payload


@pytest.mark.parametrize("value", [None, {}])
def test_optional_absence_is_healthy(bot_mcp, tmp_path, monkeypatch, value):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    _write_regime(tmp_path)
    _wire_payloads(monkeypatch, value, value)
    payload = _payload(bot_mcp)
    assert payload["quad"] == "Q1"
    assert "read_status" not in payload
    assert "market_view" not in payload and "decision_context" not in payload


@pytest.mark.parametrize("value", [False, 0, [], ""])
def test_invalid_market_mapping_preserves_decision_context(bot_mcp, tmp_path, monkeypatch, value):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    _write_regime(tmp_path)
    _, decision = _healthy_context()
    _wire_payloads(monkeypatch, value, decision)
    payload = _payload(bot_mcp)
    assert payload["quad"] == "Q1"
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["market_view"]
    assert "market_view" not in payload
    assert payload["decision_context"]["publication"] == decision["publication"]


@pytest.mark.parametrize("value", [False, {}, "", [False]])
def test_invalid_plane_collection_preserves_other_context(bot_mcp, tmp_path, monkeypatch, value):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    _write_regime(tmp_path)
    market, decision = _healthy_context()
    market["plane_summaries"] = value
    _wire_payloads(monkeypatch, market, decision)
    payload = _payload(bot_mcp)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["market_view"]
    assert payload["quad"] == "Q1"
    assert payload["decision_context"]["governor"] == decision["governor"]


@pytest.mark.parametrize("value", [False, [], 0, ""])
def test_invalid_plane_freshness_does_not_become_unknown_healthy(bot_mcp, tmp_path, monkeypatch, value):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    _write_regime(tmp_path)
    market, decision = _healthy_context()
    market["plane_summaries"][0]["freshness"] = value
    _wire_payloads(monkeypatch, market, decision)
    payload = _payload(bot_mcp)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["market_view"]
    assert "market_view" not in payload
    assert payload["decision_context"]["publication"] == decision["publication"]


@pytest.mark.parametrize("value", [False, 0, [], ""])
def test_invalid_decision_mapping_preserves_market_view(bot_mcp, tmp_path, monkeypatch, value):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    _write_regime(tmp_path)
    market, _ = _healthy_context()
    _wire_payloads(monkeypatch, market, value)
    payload = _payload(bot_mcp)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["decision_context"]
    assert payload["quad"] == "Q1"
    assert payload["market_view"]["publication"] == market["publication"]
    assert "decision_context" not in payload


@pytest.mark.parametrize("field,value", [("liquidity", False), ("quality", []), ("market_driver", 0)])
def test_invalid_nested_decision_mapping_preserves_market_view(bot_mcp, tmp_path, monkeypatch, field, value):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    _write_regime(tmp_path)
    market, decision = _healthy_context()
    if field == "quality":
        decision["liquidity"]["quality"] = value
    else:
        decision[field] = value
    _wire_payloads(monkeypatch, market, decision)
    payload = _payload(bot_mcp)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["decision_context"]
    assert payload["market_view"]["publication"] == market["publication"]
    assert "decision_context" not in payload


@pytest.mark.parametrize("component", ["market_view", "decision_context"])
def test_cyclic_optional_payload_cannot_poison_core_or_sibling(bot_mcp, tmp_path, monkeypatch, component):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    _write_regime(tmp_path)
    market, decision = _healthy_context()
    cycle = {}
    cycle["self"] = cycle
    if component == "market_view":
        market["market_view_brief"] = cycle
    else:
        decision["risk"] = cycle
    _wire_payloads(monkeypatch, market, decision)
    payload = _payload(bot_mcp)
    assert payload["quad"] == "Q1"
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == [component]
    assert component not in payload
    sibling = "decision_context" if component == "market_view" else "market_view"
    assert payload[sibling]["publication"] == decision["publication"]


def test_publication_join_and_source_clocks_survive_projection(bot_mcp, tmp_path, monkeypatch):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    _write_regime(tmp_path)
    market, decision = _healthy_context()
    calls = []
    _wire_payloads(monkeypatch, market, decision, calls)
    payload = _payload(bot_mcp)
    assert calls == [{"expected_publication": market["publication"]}]
    assert payload["market_view"]["plane_summaries"] == [{
        "name": "risk_radar", "direction": "risk_off", "status": "advisory",
        "asof": "2026-08-07", "stale": True, "age_sessions": 30,
    }]
    assert payload["decision_context"]["publication"] == decision["publication"]
    assert payload["decision_context"]["serving_freshness"] == decision["serving_freshness"]
    assert payload["decision_context"]["liquidity"] == {
        "quantity_overlay": "neutral", "quality_label": "mixed", "quality_asof": "2026-09-16",
    }
    assert "read_status" not in payload


def test_typed_withdrawn_assessment_is_preserved_as_useful_context(bot_mcp, tmp_path, monkeypatch):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    _write_regime(tmp_path)
    market, decision = _healthy_context()
    market["serving_freshness"]["unavailable_reason"] = "publication_expired"
    decision["data_quality"] = {"degrade_reasons": ["consumer_publication_changed_during_read"]}
    decision["liquidity"] = None
    decision["market_driver"] = None
    _wire_payloads(monkeypatch, market, decision)
    payload = _payload(bot_mcp)
    assert payload["market_view"]["serving_freshness"]["current_confirmation_available"] is False
    assert payload["market_view"]["serving_freshness"]["unavailable_reason"] == "publication_expired"
    assert payload["decision_context"]["serving_freshness"]["current_assessment_available"] is False
    assert payload["decision_context"]["governor"] == decision["governor"]
    assert payload["decision_context"]["data_quality"] == decision["data_quality"]
    assert payload["decision_context"]["hard_label"] is None
    assert "failed_sources" not in payload and "read_status" not in payload
