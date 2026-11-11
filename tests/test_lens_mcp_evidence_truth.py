"""Lens MCP wrappers must fail closed without hiding the engine's legitimate degraded states."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import importlib
import json
import sys
import types

import pytest


_ABSENT = object()


@contextmanager
def _load_bot_mcp_with_fake_sdk(monkeypatch):
    import brain

    prior_module = sys.modules.get("brain.bot_mcp", _ABSENT)
    prior_attribute = vars(brain).get("bot_mcp", _ABSENT)
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
    with monkeypatch.context() as patch:
        patch.setitem(sys.modules, "claude_agent_sdk", fake)
        sys.modules.pop("brain.bot_mcp", None)
        if "bot_mcp" in vars(brain):
            delattr(brain, "bot_mcp")
        try:
            yield importlib.import_module("brain.bot_mcp")
        finally:
            if prior_module is _ABSENT:
                sys.modules.pop("brain.bot_mcp", None)
            else:
                sys.modules["brain.bot_mcp"] = prior_module
            if prior_attribute is _ABSENT:
                if "bot_mcp" in vars(brain):
                    delattr(brain, "bot_mcp")
            else:
                brain.bot_mcp = prior_attribute


@pytest.fixture
def bot_mcp(monkeypatch):
    with _load_bot_mcp_with_fake_sdk(monkeypatch) as module:
        yield module


def _payload(result):
    return json.loads(result["content"][0]["text"])


def test_decision_matrix_exception_is_closed_unavailable(monkeypatch, bot_mcp):
    from portfolio import lenses
    def explode(*_args, **_kwargs):
        raise RuntimeError("secret /Users/private/lens token=do-not-return")
    monkeypatch.setattr(lenses,"full",explode)
    payload=_payload(asyncio.run(bot_mcp.get_decision_matrix.handler({"subject":"AAPL","kind":"name"})))
    assert payload == {
        "subject":"AAPL","read_status":"unavailable","error":"decision_matrix_unavailable",
        "failed_sources":["decision_matrix"]
    }


def test_decision_matrix_wrong_shape_is_unavailable(monkeypatch, bot_mcp):
    from portfolio import lenses
    monkeypatch.setattr(lenses,"full",lambda *_args,**_kwargs: ["wrong"])
    payload=_payload(asyncio.run(bot_mcp.get_decision_matrix.handler({"subject":"AAPL"})))
    assert payload["error"] == "decision_matrix_unavailable"
    assert payload["read_status"] == "unavailable"


def test_decision_matrix_empty_mapping_is_unavailable(monkeypatch, bot_mcp):
    from portfolio import lenses
    monkeypatch.setattr(lenses,"full",lambda *_args,**_kwargs: {})
    payload=_payload(asyncio.run(bot_mcp.get_decision_matrix.handler({"subject":"AAPL"})))
    assert payload["error"] == "decision_matrix_unavailable"
    assert payload["failed_sources"] == ["decision_matrix"]


def test_legitimate_degraded_matrix_passes_through(monkeypatch, bot_mcp):
    from portfolio import lenses
    expected={"subject":"AAPL","data_degraded":True,"synthesis":{"size_authority":"insufficient_data"},"rows":[]}
    monkeypatch.setattr(lenses,"full",lambda *_args,**_kwargs: expected)
    payload=_payload(asyncio.run(bot_mcp.get_decision_matrix.handler({"subject":"AAPL"})))
    assert payload == expected


def test_divergence_matrix_exception_is_closed_unavailable(monkeypatch, bot_mcp):
    from portfolio import lenses
    def explode(*_args, **_kwargs):
        raise RuntimeError("secret /Users/private/matrix api_key=do-not-return")
    monkeypatch.setattr(lenses,"decision_matrix",explode)
    payload=_payload(asyncio.run(bot_mcp.get_divergences.handler({"subject":"AAPL"})))
    assert payload["error"] == "divergence_synthesis_unavailable"
    assert payload["failed_sources"] == ["decision_matrix"]


def test_divergence_malformed_matrix_is_matrix_failure(monkeypatch, bot_mcp):
    from portfolio import lenses
    monkeypatch.setattr(lenses,"decision_matrix",lambda *_args,**_kwargs:{})
    payload=_payload(asyncio.run(bot_mcp.get_divergences.handler({"subject":"AAPL"})))
    assert payload["error"] == "divergence_synthesis_unavailable"
    assert payload["failed_sources"] == ["decision_matrix"]


def test_divergence_synthesis_exception_is_closed_unavailable(monkeypatch, bot_mcp):
    from portfolio import lenses
    monkeypatch.setattr(lenses,"decision_matrix",lambda *_args,**_kwargs:{"rows":[]})
    def explode(_matrix):
        raise RuntimeError("secret synthesis token=do-not-return")
    monkeypatch.setattr(lenses,"synthesize",explode)
    payload=_payload(asyncio.run(bot_mcp.get_divergences.handler({"subject":"AAPL"})))
    assert payload["error"] == "divergence_synthesis_unavailable"
    assert payload["failed_sources"] == ["divergence_synthesis"]


def test_divergence_wrong_shape_is_unavailable(monkeypatch, bot_mcp):
    from portfolio import lenses
    monkeypatch.setattr(lenses,"decision_matrix",lambda *_args,**_kwargs:{"rows":[]})
    monkeypatch.setattr(lenses,"synthesize",lambda _matrix:{"divergences":[]})
    payload=_payload(asyncio.run(bot_mcp.get_divergences.handler({"subject":"AAPL"})))
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "divergence_synthesis_unavailable"


def test_healthy_divergence_shape_is_unchanged(monkeypatch, bot_mcp):
    from portfolio import lenses
    monkeypatch.setattr(lenses,"decision_matrix",lambda *_args,**_kwargs:{"rows":[]})
    monkeypatch.setattr(lenses,"synthesize",lambda _matrix:{"divergences":[{"pattern":"early_edge"}],"confluence":0.4,"vetoes":[]})
    payload=_payload(asyncio.run(bot_mcp.get_divergences.handler({"subject":"AAPL"})))
    assert payload == {"divergences":[{"pattern":"early_edge"}],"confluence":0.4,"vetoes":[]}


@pytest.mark.parametrize("confluence", [
    pytest.param("0.4", id="string"),
    pytest.param(False, id="boolean"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="positive-infinity"),
    pytest.param(float("-inf"), id="negative-infinity"),
])
def test_invalid_confluence_is_closed_synthesis_failure(monkeypatch, bot_mcp, confluence):
    from portfolio import lenses

    monkeypatch.setattr(lenses, "decision_matrix", lambda *_args, **_kwargs: {"rows": []})
    monkeypatch.setattr(lenses, "synthesize", lambda _matrix: {
        "divergences": [], "confluence": confluence, "vetoes": [],
    })

    payload = _payload(asyncio.run(bot_mcp.get_divergences.handler({"subject": "AAPL"})))
    assert payload == {
        "subject": "AAPL", "read_status": "unavailable",
        "error": "divergence_synthesis_unavailable",
        "failed_sources": ["divergence_synthesis"],
    }
    json.dumps(payload, allow_nan=False)


def test_zero_confluence_keeps_healthy_shape(monkeypatch, bot_mcp):
    from portfolio import lenses

    expected = {"divergences": [], "confluence": 0, "vetoes": []}
    monkeypatch.setattr(lenses, "decision_matrix", lambda *_args, **_kwargs: {"rows": []})
    monkeypatch.setattr(lenses, "synthesize", lambda _matrix: expected)

    assert _payload(asyncio.run(bot_mcp.get_divergences.handler({"subject": "AAPL"}))) == expected


def test_matrix_serialization_failure_is_closed(monkeypatch, bot_mcp):
    from portfolio import lenses

    malformed = {"rows": [], "synthesis": {}}
    malformed["cycle"] = malformed
    monkeypatch.setattr(lenses, "full", lambda *_args, **_kwargs: malformed)

    payload = _payload(asyncio.run(bot_mcp.get_decision_matrix.handler({"subject": "AAPL"})))
    assert payload == {
        "subject": "AAPL", "read_status": "unavailable",
        "error": "decision_matrix_unavailable", "failed_sources": ["decision_matrix"],
    }


def test_divergence_serialization_failure_is_closed(monkeypatch, bot_mcp):
    from portfolio import lenses

    cyclic = []
    cyclic.append(cyclic)
    monkeypatch.setattr(lenses, "decision_matrix", lambda *_args, **_kwargs: {"rows": []})
    monkeypatch.setattr(lenses, "synthesize", lambda _matrix: {
        "divergences": cyclic, "confluence": 0.4, "vetoes": [],
    })

    payload = _payload(asyncio.run(bot_mcp.get_divergences.handler({"subject": "AAPL"})))
    assert payload == {
        "subject": "AAPL", "read_status": "unavailable",
        "error": "divergence_synthesis_unavailable",
        "failed_sources": ["divergence_synthesis"],
    }


@pytest.mark.parametrize("present", [False, True], ids=["originally-absent", "originally-present"])
def test_sdk_fixture_restores_both_module_and_package_identity(monkeypatch, present):
    import brain

    prior_module = types.ModuleType("prior_brain_bot_mcp")
    prior_attribute = object()
    if present:
        monkeypatch.setitem(sys.modules, "brain.bot_mcp", prior_module)
        monkeypatch.setattr(brain, "bot_mcp", prior_attribute, raising=False)
    else:
        monkeypatch.delitem(sys.modules, "brain.bot_mcp", raising=False)
        monkeypatch.delattr(brain, "bot_mcp", raising=False)
    prior_sdk = sys.modules.get("claude_agent_sdk", _ABSENT)

    with _load_bot_mcp_with_fake_sdk(monkeypatch) as active:
        assert sys.modules["brain.bot_mcp"] is active
        assert brain.bot_mcp is active
        assert active is not prior_module

    if present:
        assert sys.modules["brain.bot_mcp"] is prior_module
        assert brain.bot_mcp is prior_attribute
    else:
        assert "brain.bot_mcp" not in sys.modules
        assert "bot_mcp" not in vars(brain)
    assert sys.modules.get("claude_agent_sdk", _ABSENT) is prior_sdk


def test_real_empty_row_synthesis_remains_insufficient_data(monkeypatch, bot_mcp):
    from portfolio import lenses

    monkeypatch.setattr(lenses, "_LENS_WEIGHTS_CACHE", {})
    monkeypatch.setattr(lenses, "decision_matrix", lambda *_args, **_kwargs: {
        "subject": "AAPL", "kind": "name", "rows": [],
    })
    expected = lenses.full("AAPL")
    assert expected["synthesis"]["data_degraded"] is True
    assert expected["synthesis"]["size_authority"] == "insufficient_data"

    matrix = _payload(asyncio.run(bot_mcp.get_decision_matrix.handler({"subject": "AAPL"})))
    assert matrix == expected
    divergences = _payload(asyncio.run(bot_mcp.get_divergences.handler({"subject": "AAPL"})))
    assert divergences == {key: expected["synthesis"][key] for key in ("divergences", "confluence", "vetoes")}
