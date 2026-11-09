"""Session-entry Brain intelligence must distinguish absent artifacts from failed evidence."""
from __future__ import annotations

import asyncio
import builtins
import importlib
import json
import sys
import types
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


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def _break(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ broken secret token=do-not-return")


def _wire_intake(monkeypatch, *, fail=False):
    from brain import intake

    if fail:
        def explode(*_args, **_kwargs):
            raise RuntimeError("secret /Users/private/intake api_key=do-not-return")
        monkeypatch.setattr(intake, "build", explode)
    else:
        monkeypatch.setattr(intake, "build", lambda limit=20: {
            "as_of": "2026-09-17",
            "macro_context": {"quad": "Q1"},
            "candidates": [{"ticker": "AAPL", "score": 9}],
        })


def _briefing_payload():
    return {
        "as_of": "2026-09-17",
        "macro_context": {"quad": "Q1"},
        "n_actionable": 1,
        "n_divergences": 0,
        "priority_queue": [{"ticker": "AAPL", "score": 9}],
        "divergences": [],
        "how_to_use": "start here",
    }


def _hub_payload():
    return {
        "as_of": "2026-09-17",
        "macro_context": {"quad": "Q1"},
        "desks": {"news": {"live": True}},
        "counts": {"command": 1},
        "n_actionable": 1,
        "command": [{"ticker": "AAPL", "name": "Apple", "composite_conviction": 80, "flags": []}],
        "divergence_alerts": {"early_edge": [], "crowded_top": []},
        "sector_heat": [{"etf": "XLK"}],
        "how_to_use": "rank then inspect",
    }


def test_missing_briefing_composes_live_without_degradation(bot_mcp, tmp_path, monkeypatch):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path / "vendor")
    _wire_intake(monkeypatch)

    payload = json.loads(_text(asyncio.run(bot_mcp.get_daily_briefing.handler({"top": 5}))))
    assert payload["priority_queue"] == [{"ticker": "AAPL", "score": 9}]
    assert "Composed live" in payload["note"]
    assert "read_status" not in payload


def test_corrupt_briefing_can_use_healthy_mirror_but_stays_partial(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "intelligence" / "briefing.json")
    _write_json(vendor / "data" / "intelligence" / "briefing.json", _briefing_payload())

    raw = _text(asyncio.run(bot_mcp.get_daily_briefing.handler({"top": 5})))
    payload = json.loads(raw)
    assert payload["priority_queue"][0]["ticker"] == "AAPL"
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["briefing"]
    assert "secret" not in raw and "do-not-return" not in raw


def test_empty_briefing_artifact_falls_back_live_as_partial(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_json(vendor / "site" / "intelligence" / "briefing.json", {})
    _wire_intake(monkeypatch)

    payload = json.loads(_text(asyncio.run(bot_mcp.get_daily_briefing.handler({}))))
    assert payload["priority_queue"][0]["ticker"] == "AAPL"
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["briefing"]


def test_briefing_wrong_queue_shape_preserves_other_fields_as_partial(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    payload = _briefing_payload()
    payload["priority_queue"] = {"AAPL": 9}
    _write_json(vendor / "site" / "intelligence" / "briefing.json", payload)

    out = json.loads(_text(asyncio.run(bot_mcp.get_daily_briefing.handler({}))))
    assert out["as_of"] == "2026-09-17"
    assert out["priority_queue"] is None
    assert out["read_status"] == "partial"
    assert out["failed_sources"] == ["briefing"]


def test_missing_briefing_plus_failed_live_composition_is_unavailable(bot_mcp, tmp_path, monkeypatch):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path / "vendor")
    _wire_intake(monkeypatch, fail=True)

    raw = _text(asyncio.run(bot_mcp.get_daily_briefing.handler({})))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "daily_briefing_unavailable"
    assert payload["failed_sources"] == ["intake"]
    assert payload["priority_queue"] is None
    assert "secret" not in raw and "api_key" not in raw


def test_missing_hub_keeps_existing_not_built_message(bot_mcp, tmp_path, monkeypatch):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path / "vendor")

    text = _text(asyncio.run(bot_mcp.get_intel_hub.handler({})))
    assert text == "intel hub not built yet (site/intel_hub/hub.json absent — ships in the daily build)."


def test_corrupt_hub_is_unavailable_not_not_built(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "intel_hub" / "hub.json")

    raw = _text(asyncio.run(bot_mcp.get_intel_hub.handler({})))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "intel_hub_unavailable"
    assert payload["failed_sources"] == ["intel_hub"]
    assert payload["command"] is None
    assert "not built yet" not in raw and "secret" not in raw


def test_corrupt_hub_primary_uses_fallback_but_stays_partial(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "intel_hub" / "hub.json")
    _write_json(vendor / "data" / "intel_hub" / "hub.json", _hub_payload())

    payload = json.loads(_text(asyncio.run(bot_mcp.get_intel_hub.handler({}))))
    assert payload["command"][0]["ticker"] == "AAPL"
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["intel_hub"]


def test_hub_wrong_command_shape_cannot_claim_ticker_has_no_signal(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    payload = _hub_payload()
    payload["command"] = {"AAPL": {"score": 80}}
    _write_json(vendor / "site" / "intel_hub" / "hub.json", payload)

    raw = _text(asyncio.run(bot_mcp.get_intel_hub.handler({"ticker": "MSFT"})))
    out = json.loads(raw)
    assert out["ticker"] == "MSFT"
    assert out["dossier"] is None
    assert out["read_status"] == "partial"
    assert out["failed_sources"] == ["intel_hub"]
    assert "no cross-desk signal today" not in raw


def test_hub_healthy_command_absence_keeps_existing_no_signal_message(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_json(vendor / "site" / "intel_hub" / "hub.json", _hub_payload())

    text = _text(asyncio.run(bot_mcp.get_intel_hub.handler({"ticker": "MSFT"})))
    assert text == "MSFT not in the intel-hub command (no cross-desk signal today)."


def _vendor(bot_mcp, monkeypatch, tmp_path):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    return vendor


def _call(bot_mcp, name, args=None):
    return _text(asyncio.run(getattr(bot_mcp, name).handler(args or {})))


@pytest.mark.parametrize("kind", ["missing", "null"])
def test_published_briefing_requires_a_known_queue(bot_mcp, monkeypatch, tmp_path, kind):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    briefing = _briefing_payload()
    if kind == "missing":
        briefing.pop("priority_queue")
    else:
        briefing["priority_queue"] = None
    _write_json(vendor / "site" / "intelligence" / "briefing.json", briefing)
    payload = json.loads(_call(bot_mcp, "get_daily_briefing"))
    assert payload["priority_queue"] is None
    assert payload["as_of"] == briefing["as_of"]
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["briefing"]


def test_explicit_empty_published_queue_is_complete(bot_mcp, monkeypatch, tmp_path):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    briefing = _briefing_payload()
    briefing.update({"priority_queue": [], "n_actionable": 0})
    _write_json(vendor / "site" / "intelligence" / "briefing.json", briefing)
    payload = json.loads(_call(bot_mcp, "get_daily_briefing"))
    assert payload["priority_queue"] == [] and payload["n_actionable"] == 0
    assert "read_status" not in payload


def test_published_briefing_preserves_limit_and_projection(bot_mcp, monkeypatch, tmp_path):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    briefing = _briefing_payload()
    briefing["priority_queue"] += [{"ticker": "MSFT"}, {"ticker": "NVDA"}]
    _write_json(vendor / "site" / "intelligence" / "briefing.json", briefing)
    payload = json.loads(_call(bot_mcp, "get_daily_briefing", {"top": 2}))
    assert payload == {**briefing, "priority_queue": briefing["priority_queue"][:2]}


@pytest.mark.parametrize("value", [None, [], {}, {"candidates": None}, {"candidates": {}}])
def test_live_briefing_requires_a_list_of_candidates(bot_mcp, monkeypatch, tmp_path, value):
    _vendor(bot_mcp, monkeypatch, tmp_path)
    from brain import intake
    monkeypatch.setattr(intake, "build", lambda limit: value)
    payload = json.loads(_call(bot_mcp, "get_daily_briefing"))
    assert payload["priority_queue"] is None
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "daily_briefing_unavailable"
    assert payload["failed_sources"] == ["intake"]


def test_live_briefing_retains_candidate_authority_and_producer_note(bot_mcp, monkeypatch, tmp_path):
    _vendor(bot_mcp, monkeypatch, tmp_path)
    from brain import intake
    row = {
        "ticker": "AAPL", "score": 9, "candidacy_score": 0,
        "n_sources": 0, "n_observed_sources": 1,
        "source_qualification": {"sizing_authority": False},
    }
    note = "Context-only research remains inspectable and does not confer sizing authority."
    limits = []
    def build(limit):
        limits.append(limit)
        return {"as_of": "2026-11-07", "macro_context": {"quad": "Q1"},
                "n_universe": 1, "candidates": [row], "note": note}
    monkeypatch.setattr(intake, "build", build)
    payload = json.loads(_call(bot_mcp, "get_daily_briefing", {"top": 3}))
    assert limits == [3]
    assert payload["priority_queue"] == [row]
    assert payload["intake_note"] == note
    assert "Composed live" in payload["note"]
    assert "read_status" not in payload


def test_empty_live_queue_is_healthy(bot_mcp, monkeypatch, tmp_path):
    _vendor(bot_mcp, monkeypatch, tmp_path)
    from brain import intake
    monkeypatch.setattr(intake, "build", lambda limit: {"candidates": []})
    payload = json.loads(_call(bot_mcp, "get_daily_briefing"))
    assert payload["priority_queue"] == []
    assert "read_status" not in payload


@pytest.mark.parametrize("failure", ["top", "import", "serialization", "corrupt_and_serialization"])
def test_briefing_setup_and_output_failures_are_closed(bot_mcp, monkeypatch, tmp_path, failure):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    _wire_intake(monkeypatch)
    args = {}
    if failure == "top":
        args["top"] = "secret /Users/private api_key=do-not-return"
    elif failure == "import":
        real_import = builtins.__import__
        def unavailable(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "brain" and "intake" in (fromlist or ()):
                raise ImportError("secret /Users/private api_key=do-not-return")
            return real_import(name, globals, locals, fromlist, level)
        monkeypatch.setattr(builtins, "__import__", unavailable)
    else:
        from brain import intake
        cyclic = []
        cyclic.append(cyclic)
        monkeypatch.setattr(intake, "build", lambda limit: {"candidates": cyclic})
        if failure == "corrupt_and_serialization":
            _break(vendor / "site" / "intelligence" / "briefing.json")
    raw = _call(bot_mcp, "get_daily_briefing", args)
    payload = json.loads(raw)
    expected_sources = ["briefing"] if failure == "top" else (
        ["briefing", "intake"] if failure == "corrupt_and_serialization" else ["intake"]
    )
    assert payload == {
        "as_of": None, "macro_context": None, "priority_queue": None,
        "read_status": "unavailable", "error": "daily_briefing_unavailable",
        "failed_sources": expected_sources,
    }
    assert "secret" not in raw and "/Users/private" not in raw and "api_key" not in raw


@pytest.mark.parametrize("kind", ["missing", "null"])
def test_missing_command_census_cannot_prove_ticker_absence(bot_mcp, monkeypatch, tmp_path, kind):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    hub = _hub_payload()
    if kind == "missing":
        hub.pop("command")
    else:
        hub["command"] = None
    _write_json(vendor / "site" / "intel_hub" / "hub.json", hub)
    overview = json.loads(_call(bot_mcp, "get_intel_hub"))
    raw = _call(bot_mcp, "get_intel_hub", {"ticker": "msft"})
    lookup = json.loads(raw)
    assert overview["command"] is None and overview["read_status"] == "partial"
    assert lookup["ticker"] == "MSFT" and lookup["dossier"] is None
    assert lookup["read_status"] == "partial"
    assert lookup["failed_sources"] == ["intel_hub"]
    assert "no cross-desk signal today" not in raw


def test_explicit_empty_command_is_a_complete_census(bot_mcp, monkeypatch, tmp_path):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    hub = _hub_payload()
    hub.update({"command": [], "n_actionable": 0, "sector_heat": None})
    _write_json(vendor / "site" / "intel_hub" / "hub.json", hub)
    payload = json.loads(_call(bot_mcp, "get_intel_hub"))
    assert payload["command"] == [] and payload["n_actionable"] == 0
    assert payload["sector_heat"] == [] and "read_status" not in payload
    assert _call(bot_mcp, "get_intel_hub", {"ticker": "msft"}) == (
        "MSFT not in the intel-hub command (no cross-desk signal today)."
    )


@pytest.mark.parametrize("bad_row", [
    None, 7, {}, {"ticker": None}, {"ticker": 42},
    {"ticker": []}, {"ticker": ""}, {"ticker": "   "},
])
def test_invalid_command_rows_preserve_known_dossier_and_unknown_absence(
    bot_mcp, monkeypatch, tmp_path, bad_row,
):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    hub = _hub_payload()
    good = hub["command"][0]
    hub["command"] = [bad_row, good]
    _write_json(vendor / "site" / "intel_hub" / "hub.json", hub)
    overview = json.loads(_call(bot_mcp, "get_intel_hub"))
    known = json.loads(_call(bot_mcp, "get_intel_hub", {"ticker": "aapl"}))
    unknown_raw = _call(bot_mcp, "get_intel_hub", {"ticker": "MSFT"})
    unknown = json.loads(unknown_raw)
    assert overview["command"] == [good]
    assert overview["read_status"] == "partial"
    assert known["ticker"] == "AAPL" and known["composite_conviction"] == 80
    assert known["read_status"] == "partial" and known["failed_sources"] == ["intel_hub"]
    assert unknown["dossier"] is None and unknown["read_status"] == "partial"
    assert "no cross-desk signal today" not in unknown_raw


@pytest.mark.parametrize("ticker", [42, [], {}, False, "   "])
def test_malformed_hub_query_is_closed(bot_mcp, monkeypatch, tmp_path, ticker):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    _write_json(vendor / "site" / "intel_hub" / "hub.json", _hub_payload())
    payload = json.loads(_call(bot_mcp, "get_intel_hub", {"ticker": ticker}))
    assert payload == {
        "read_status": "unavailable", "error": "intel_hub_unavailable",
        "failed_sources": ["intel_hub"], "command": None,
    }


def test_invalid_hub_limit_is_closed(bot_mcp, monkeypatch, tmp_path):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    _write_json(vendor / "site" / "intel_hub" / "hub.json", _hub_payload())
    raw = _call(bot_mcp, "get_intel_hub", {"top": "secret api_key=do-not-return"})
    payload = json.loads(raw)
    assert payload["command"] is None and payload["read_status"] == "unavailable"
    assert payload["error"] == "intel_hub_unavailable"
    assert "secret" not in raw and "api_key" not in raw


def test_valid_dossier_query_preserves_existing_limit_independence(bot_mcp, monkeypatch, tmp_path):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    _write_json(vendor / "site" / "intel_hub" / "hub.json", _hub_payload())
    payload = json.loads(_call(bot_mcp, "get_intel_hub", {"ticker": "aapl", "top": "unused"}))
    assert payload["ticker"] == "AAPL" and payload["composite_conviction"] == 80
    assert "read_status" not in payload


@pytest.mark.parametrize("kind", ["missing", "null"])
def test_optional_divergences_and_sectors_keep_healthy_semantics(bot_mcp, monkeypatch, tmp_path, kind):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    briefing = _briefing_payload()
    hub = _hub_payload()
    for payload, key in ((briefing, "divergences"), (hub, "sector_heat")):
        if kind == "missing":
            payload.pop(key)
        else:
            payload[key] = None
    _write_json(vendor / "site" / "intelligence" / "briefing.json", briefing)
    _write_json(vendor / "site" / "intel_hub" / "hub.json", hub)
    b = json.loads(_call(bot_mcp, "get_daily_briefing"))
    h = json.loads(_call(bot_mcp, "get_intel_hub"))
    assert b["divergences"] is None and b["priority_queue"] == briefing["priority_queue"]
    assert h["sector_heat"] == [] and h["command"] == hub["command"]
    assert "read_status" not in b and "read_status" not in h


@pytest.mark.parametrize("sector", [0, False, {}, ["bad", {"etf": "XLK"}]])
def test_malformed_sector_evidence_retains_known_command(bot_mcp, monkeypatch, tmp_path, sector):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    hub = _hub_payload()
    hub["sector_heat"] = sector
    _write_json(vendor / "site" / "intel_hub" / "hub.json", hub)
    payload = json.loads(_call(bot_mcp, "get_intel_hub"))
    assert payload["command"] == hub["command"]
    assert payload["sector_heat"] == ([{"etf": "XLK"}] if isinstance(sector, list) else None)
    assert payload["read_status"] == "partial" and payload["failed_sources"] == ["intel_hub"]
