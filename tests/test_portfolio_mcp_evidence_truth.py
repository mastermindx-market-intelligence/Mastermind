"""The Brain own-book MCP read must distinguish first-run absence from unreadable state."""
from __future__ import annotations

import asyncio
import importlib
import json
import sys
import types


def _load_bot_mcp_with_fake_sdk(monkeypatch):
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
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)
    sys.modules.pop("brain.bot_mcp", None)
    return importlib.import_module("brain.bot_mcp")


def _text(result: dict) -> str:
    return result["content"][0]["text"]


def _wire_registry(monkeypatch, root, *, get_fail=False, active_fail=False, path_fail=False):
    from portfolio import registry

    monkeypatch.setattr(registry, "DASHBOARD_DEFAULT_ID", "autonomous")
    if path_fail:
        def fail_path(_pid):
            raise RuntimeError("secret /Users/private/registry token=do-not-return")
        monkeypatch.setattr(registry, "data_dir", fail_path)
    else:
        monkeypatch.setattr(registry, "data_dir", lambda _pid: root)

    if get_fail:
        def fail_get(_pid):
            raise RuntimeError("secret /Users/private/meta api_key=do-not-return")
        monkeypatch.setattr(registry, "get", fail_get)
    else:
        monkeypatch.setattr(registry, "get", lambda _pid: {"status": "active"})

    if active_fail:
        def fail_active(_pid):
            raise RuntimeError("secret /Users/private/active credential=do-not-return")
        monkeypatch.setattr(registry, "is_active", fail_active)
    else:
        monkeypatch.setattr(registry, "is_active", lambda _pid: True)


def _write_latest(root, payload):
    root.mkdir(parents=True, exist_ok=True)
    (root / "latest.json").write_text(json.dumps(payload))


def test_genuine_missing_book_keeps_existing_no_book_state(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    _wire_registry(monkeypatch, tmp_path / "book")

    payload = json.loads(_text(asyncio.run(bot_mcp.get_portfolio.handler({}))))
    assert payload == {"status": "no book yet", "portfolio_id": "autonomous"}


def test_corrupt_book_is_unavailable_not_no_book(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    root = tmp_path / "book"
    _wire_registry(monkeypatch, root)
    root.mkdir(parents=True)
    (root / "latest.json").write_text("{ broken secret token=do-not-return")

    raw = _text(asyncio.run(bot_mcp.get_portfolio.handler({})))
    payload = json.loads(raw)
    assert payload == {
        "portfolio_id": "autonomous",
        "read_status": "unavailable",
        "error": "portfolio_book_unavailable",
        "failed_sources": ["portfolio_book"],
    }
    assert "broken" not in raw and "secret" not in raw and "do-not-return" not in raw


def test_wrong_shape_book_is_unavailable_not_first_run(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    root = tmp_path / "book"
    _wire_registry(monkeypatch, root)
    _write_latest(root, [])

    payload = json.loads(_text(asyncio.run(bot_mcp.get_portfolio.handler({}))))
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "portfolio_book_unavailable"
    assert payload["failed_sources"] == ["portfolio_book"]


def test_registry_path_failure_is_closed_unavailable(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    _wire_registry(monkeypatch, tmp_path / "book", path_fail=True)

    raw = _text(asyncio.run(bot_mcp.get_portfolio.handler({})))
    payload = json.loads(raw)
    assert payload == {
        "portfolio_id": "autonomous",
        "read_status": "unavailable",
        "error": "portfolio_registry_unavailable",
        "failed_sources": ["portfolio_registry"],
    }
    assert "secret" not in raw and "token=" not in raw


def test_registry_metadata_failure_preserves_healthy_book_as_partial(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    root = tmp_path / "book"
    _wire_registry(monkeypatch, root, get_fail=True)
    _write_latest(root, {"as_of": "2026-09-17", "positions": [{"ticker": "AAPL"}]})

    raw = _text(asyncio.run(bot_mcp.get_portfolio.handler({})))
    payload = json.loads(raw)
    assert payload["as_of"] == "2026-09-17"
    assert payload["positions"] == [{"ticker": "AAPL"}]
    assert payload["portfolio_id"] == "autonomous"
    assert payload["active"] is None and payload["lifecycle"] is None
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["portfolio_registry"]
    assert "secret" not in raw and "api_key" not in raw


def test_active_status_failure_preserves_healthy_book_as_partial(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    root = tmp_path / "book"
    _wire_registry(monkeypatch, root, active_fail=True)
    _write_latest(root, {"as_of": "2026-09-17", "positions": []})

    payload = json.loads(_text(asyncio.run(bot_mcp.get_portfolio.handler({}))))
    assert payload["as_of"] == "2026-09-17"
    assert payload["active"] is None
    assert payload["lifecycle"] == "active"
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["portfolio_registry"]


def test_healthy_book_keeps_existing_success_shape(tmp_path, monkeypatch):
    bot_mcp = _load_bot_mcp_with_fake_sdk(monkeypatch)
    root = tmp_path / "book"
    _wire_registry(monkeypatch, root)
    _write_latest(root, {"as_of": "2026-09-17", "positions": [{"ticker": "AAPL"}]})

    payload = json.loads(_text(asyncio.run(bot_mcp.get_portfolio.handler({}))))
    assert payload["as_of"] == "2026-09-17"
    assert payload["portfolio_id"] == "autonomous"
    assert payload["active"] is True
    assert payload["lifecycle"] == "active"
    assert "read_status" not in payload and "failed_sources" not in payload
