"""Unavailable overnight observations must never be relabelled as calm."""
from __future__ import annotations

import asyncio
import importlib
import json
import sys
import types
import builtins
from contextlib import contextmanager

import pytest


def _body(resp):
    return json.loads(resp.body)


def test_http_successful_calm_remains_calm(monkeypatch):
    from app import web
    from data_layer import overnight

    monkeypatch.setattr(
        overnight,
        "tape",
        lambda **_kwargs: {"groups": {}, "risk": {"state": "calm", "reasons": []}, "live": True},
    )
    payload = _body(web.api_overnight_tape())
    assert payload["risk"]["state"] == "calm"
    assert payload["live"] is True
    assert "overnight_status" not in payload


def test_http_failure_is_unavailable_not_calm_and_secret_safe(monkeypatch):
    from app import web
    from data_layer import overnight

    monkeypatch.setattr(
        overnight,
        "tape",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("secret /Users/private/overnight api_key=bad")),
    )
    response = web.api_overnight_tape()
    payload = _body(response)

    assert payload == {
        "overnight_status": "unavailable",
        "groups": None,
        "risk": None,
        "live": False,
        "error": "overnight_tape_unavailable",
    }
    raw = response.body.decode()
    assert "secret" not in raw and "/Users/private" not in raw and "api_key" not in raw


@contextmanager
def _bot_mcp_with_fake_sdk(monkeypatch):
    import brain

    missing = object()
    previous_module = sys.modules.get("brain.bot_mcp", missing)
    previous_attribute = vars(brain).get("bot_mcp", missing)
    fake = types.ModuleType("claude_agent_sdk")

    class ToolWrap:
        def __init__(self, name, handler, description, input_schema):
            self.name = name
            self.handler = handler
            self.description = description
            self.input_schema = input_schema

    def tool(name, description, schema):
        def decorate(handler):
            return ToolWrap(name, handler, description, schema)
        return decorate

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


@pytest.fixture(autouse=True)
def private_tape_cache(monkeypatch):
    from data_layer import overnight

    monkeypatch.setattr(overnight, "_cache", None)
    monkeypatch.setattr(overnight, "_cache_ts", 0.0)


def test_mcp_failure_is_closed_unavailable_not_exception_text(bot_mcp, monkeypatch):
    from data_layer import overnight

    monkeypatch.setattr(
        overnight,
        "tape",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("secret /Users/private/tape token=bad")),
    )
    out = asyncio.run(bot_mcp.get_overnight_tape.handler({}))
    payload = json.loads(out["content"][0]["text"])

    assert payload == {
        "overnight_status": "unavailable",
        "risk": None,
        "groups": None,
        "live": False,
        "error": "overnight_tape_unavailable",
        "note": "overnight tape unavailable",
    }
    raw = out["content"][0]["text"]
    assert "secret" not in raw and "/Users/private" not in raw and "token=bad" not in raw


def _call_surface(surface, bot_mcp):
    if surface == "http":
        from app import web
        response = web.api_overnight_tape()
        assert response.status_code == 200
        return json.loads(response.body)
    result = asyncio.run(bot_mcp.get_overnight_tape.handler({}))
    return json.loads(result["content"][0]["text"])


def _fake_feed(monkeypatch, mode):
    from data_layer import overnight
    import pandas as pd

    calls = []
    if mode == "missing_provider":
        previous = builtins.__import__

        def missing(name, *args, **kwargs):
            if name == "yfinance":
                calls.append(mode)
                raise ImportError("secret provider import /Users/private token=bad")
            return previous(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", missing)
        return calls

    fake = types.ModuleType("yfinance")

    def download(symbols, **kwargs):
        calls.append((list(symbols), dict(kwargs)))
        assert symbols == overnight.ALL_SYMBOLS
        assert kwargs == {"period": "5d", "progress": False,
                          "auto_adjust": False, "threads": False}
        if mode == "download_failure":
            raise RuntimeError("secret /Users/private/feed api_key=bad")
        if mode == "missing_close":
            return {}
        if mode == "empty":
            return {"Close": pd.DataFrame()}
        if mode == "unknown_only":
            return {"Close": pd.DataFrame({"NOT_IN_TAPE": [100.0, 101.0]})}
        if mode == "fx_crypto":
            return {"Close": pd.DataFrame({"JPY=X": [140.0, 141.0],
                                          "BTC-USD": [50000.0, 50500.0]})}
        last = {"calm": 100.2, "elevated": 99.3, "stressed": 98.0}[mode]
        return {"Close": pd.DataFrame({"ES=F": [100.0, last], "^VIX": [20.0, 20.0]})}

    fake.download = download
    monkeypatch.setitem(sys.modules, "yfinance", fake)
    return calls


@pytest.mark.parametrize("surface", ["http", "mcp"])
@pytest.mark.parametrize("kind", ["calm", "stressed", "degraded"])
def test_existing_successful_tape_payloads_pass_through(surface, kind, bot_mcp, monkeypatch):
    from data_layer import overnight

    payload = {"as_of": "2026-11-07T00:00:00+00:00",
               "groups": {"crypto": [{"ticker": "BTC-USD", "price": 50000.0,
                                       "change_pct": None}]},
               "risk": {"state": "stressed" if kind == "stressed" else "calm",
                        "reasons": ["observed"]},
               "n_symbols": 1, "live": kind != "degraded"}

    def tape(**_kwargs):
        return payload

    monkeypatch.setattr(overnight, "tape", tape)
    assert _call_surface(surface, bot_mcp) == payload


@pytest.mark.parametrize("surface", ["http", "mcp"])
@pytest.mark.parametrize("mode", [
    "missing_provider", "download_failure", "missing_close", "empty", "unknown_only",
])
def test_actual_owner_observation_free_results_are_unavailable(surface, mode, bot_mcp, monkeypatch):
    from data_layer import overnight

    calls = _fake_feed(monkeypatch, mode)
    payload = _call_surface(surface, bot_mcp)
    assert payload["overnight_status"] == "unavailable"
    assert payload["risk"] is None and payload["groups"] is None
    assert payload["live"] is False
    assert payload["error"] == "overnight_tape_unavailable"
    assert isinstance(payload["as_of"], str) and payload["as_of"]
    assert payload["n_symbols"] == (1 if mode == "unknown_only" else 0)
    assert len(calls) == 1
    assert "secret" not in json.dumps(payload) and "api_key" not in json.dumps(payload)
    assert overnight._cache["groups"] is not None
    assert "overnight_status" not in overnight._cache


@pytest.mark.parametrize("surface", ["http", "mcp"])
@pytest.mark.parametrize("risk", ["calm", "elevated", "stressed"])
def test_actual_owner_observed_risk_policy_is_preserved(surface, risk, bot_mcp, monkeypatch):
    calls = _fake_feed(monkeypatch, risk)
    payload = _call_surface(surface, bot_mcp)
    assert payload["live"] is True and payload["n_symbols"] == 2
    assert payload["risk"]["state"] == risk
    assert payload["groups"]["us_futures"][0]["ticker"] == "ES=F"
    assert payload["groups"]["vol"][0]["ticker"] == "^VIX"
    assert "overnight_status" not in payload and "error" not in payload
    assert len(calls) == 1


@pytest.mark.parametrize("surface", ["http", "mcp"])
def test_actual_owner_partial_fx_crypto_observations_are_not_discarded(surface, bot_mcp, monkeypatch):
    calls = _fake_feed(monkeypatch, "fx_crypto")
    payload = _call_surface(surface, bot_mcp)
    assert payload["live"] is True and payload["n_symbols"] == 2
    assert payload["groups"]["fx_rates"][0]["ticker"] == "JPY=X"
    assert payload["groups"]["crypto"][0]["ticker"] == "BTC-USD"
    assert payload["risk"]["state"] == "calm"
    assert payload["risk"]["reasons"] == ["no live tape"]
    assert "overnight_status" not in payload and len(calls) == 1


@pytest.mark.parametrize("surface", ["http", "mcp"])
def test_strict_cached_view_does_not_refetch_or_poison_default_cache(surface, bot_mcp, monkeypatch):
    from data_layer import overnight

    calls = _fake_feed(monkeypatch, "empty")
    raw = overnight.tape(force=True)
    raw_bytes = json.dumps(raw, sort_keys=True)
    timestamp = overnight._cache_ts
    assert raw["risk"]["state"] == "calm" and raw["live"] is False
    payload = _call_surface(surface, bot_mcp)
    assert payload["overnight_status"] == "unavailable" and payload["risk"] is None
    assert payload["as_of"] == raw["as_of"] and payload["n_symbols"] == raw["n_symbols"]
    assert overnight._cache is raw and overnight._cache_ts == timestamp
    assert json.dumps(raw, sort_keys=True) == raw_bytes
    assert overnight.tape() is raw and len(calls) == 1


def test_default_tape_watch_and_brief_policy_remain_unchanged(monkeypatch):
    from data_layer import overnight

    calls = _fake_feed(monkeypatch, "download_failure")
    payload = overnight.tape()
    assert payload["risk"]["state"] == "calm" and payload["live"] is False
    assert "overnight_status" not in payload
    assert overnight.is_material(payload) is False
    assert overnight.brief(payload) == "Overnight tape unavailable (live feed down)."
    assert len(calls) == 1


_MISSING = object()


def _sdk_state():
    import brain
    return (sys.modules.get("claude_agent_sdk", _MISSING),
            sys.modules.get("brain.bot_mcp", _MISSING),
            vars(brain).get("bot_mcp", _MISSING))


def _set_prior_sdk_state(patch, present):
    import brain
    if present:
        patch.setitem(sys.modules, "claude_agent_sdk", types.ModuleType("prior_sdk"))
        patch.setitem(sys.modules, "brain.bot_mcp", types.ModuleType("prior_bot"))
        patch.setattr(brain, "bot_mcp", object(), raising=False)
    else:
        patch.delitem(sys.modules, "claude_agent_sdk", raising=False)
        patch.delitem(sys.modules, "brain.bot_mcp", raising=False)
        patch.delattr(brain, "bot_mcp", raising=False)


@pytest.mark.parametrize("present", [False, True])
@pytest.mark.parametrize("raise_inside", [False, True])
def test_sdk_fixture_restores_exact_prior_entries_on_exit(monkeypatch, present, raise_inside):
    with monkeypatch.context() as scenario:
        _set_prior_sdk_state(scenario, present)
        before = _sdk_state()
        if raise_inside:
            with pytest.raises(RuntimeError, match="controlled exit"):
                with _bot_mcp_with_fake_sdk(monkeypatch):
                    raise RuntimeError("controlled exit")
        else:
            with _bot_mcp_with_fake_sdk(monkeypatch) as module:
                assert module.get_overnight_tape.name == "get_overnight_tape"
        after = _sdk_state()
        assert all(left is right for left, right in zip(before, after))


@pytest.mark.parametrize("present", [False, True])
def test_sdk_fixture_restores_exact_prior_entries_after_import_failure(monkeypatch, present):
    with monkeypatch.context() as scenario:
        _set_prior_sdk_state(scenario, present)
        before = _sdk_state()
        original = importlib.import_module

        def fail_import(name, *args, **kwargs):
            if name == "brain.bot_mcp":
                raise RuntimeError("controlled import failure")
            return original(name, *args, **kwargs)

        scenario.setattr(importlib, "import_module", fail_import)
        with pytest.raises(RuntimeError, match="controlled import failure"):
            with _bot_mcp_with_fake_sdk(monkeypatch):
                pytest.fail("import should not reach the context body")
        after = _sdk_state()
        assert all(left is right for left, right in zip(before, after))


def test_overnight_tool_keeps_its_existing_catalog_contract(bot_mcp):
    catalog = bot_mcp.inference_tool_catalog()
    entry = next(row for row in catalog
                 if row["name"] == "mcp__bot__get_overnight_tape")
    assert entry["description"] == bot_mcp.get_overnight_tape.description
    assert entry["input_schema"] == {
        "type": "object", "properties": {}, "additionalProperties": False,
    }
    assert bot_mcp.get_overnight_tape in bot_mcp._READ
    assert bot_mcp.get_overnight_tape not in bot_mcp._ACTION


@pytest.mark.parametrize("mode", ["empty", "calm"])
def test_registered_overnight_route_uses_actual_owner_availability(monkeypatch, mode):
    import httpx
    from fastapi import FastAPI
    from app import web

    calls = _fake_feed(monkeypatch, mode)
    app = FastAPI()
    app.include_router(web.router)

    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                    base_url="http://qualification.invalid") as client:
            return await client.get("/api/overnight-tape")

    response = asyncio.run(request())
    assert response.status_code == 200
    payload = response.json()
    if mode == "empty":
        assert payload["overnight_status"] == "unavailable"
        assert payload["groups"] is None and payload["risk"] is None
    else:
        assert payload["live"] is True and payload["risk"]["state"] == "calm"
        assert "overnight_status" not in payload
    assert len(calls) == 1


def test_http_encoding_failure_is_closed_unavailable(monkeypatch):
    from app import web
    from data_layer import overnight

    monkeypatch.setattr(overnight, "tape", lambda **_kwargs: {"price": float("nan")})
    payload = _body(web.api_overnight_tape())
    assert payload == {
        "overnight_status": "unavailable", "groups": None, "risk": None,
        "live": False, "error": "overnight_tape_unavailable",
    }
