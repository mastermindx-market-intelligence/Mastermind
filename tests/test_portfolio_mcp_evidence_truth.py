"""The Brain own-book MCP read must distinguish first-run absence from unreadable state."""
from __future__ import annotations

import asyncio
import builtins
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


def test_genuine_missing_book_keeps_existing_no_book_state(bot_mcp, tmp_path, monkeypatch):
    _wire_registry(monkeypatch, tmp_path / "book")

    payload = json.loads(_text(asyncio.run(bot_mcp.get_portfolio.handler({}))))
    assert payload == {"status": "no book yet", "portfolio_id": "autonomous"}


def test_corrupt_book_is_unavailable_not_no_book(bot_mcp, tmp_path, monkeypatch):
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


def test_wrong_shape_book_is_unavailable_not_first_run(bot_mcp, tmp_path, monkeypatch):
    root = tmp_path / "book"
    _wire_registry(monkeypatch, root)
    _write_latest(root, [])

    payload = json.loads(_text(asyncio.run(bot_mcp.get_portfolio.handler({}))))
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "portfolio_book_unavailable"
    assert payload["failed_sources"] == ["portfolio_book"]


def test_registry_path_failure_is_closed_unavailable(bot_mcp, tmp_path, monkeypatch):
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


def test_registry_metadata_failure_preserves_healthy_book_as_partial(bot_mcp, tmp_path, monkeypatch):
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


def test_active_status_failure_preserves_healthy_book_as_partial(bot_mcp, tmp_path, monkeypatch):
    root = tmp_path / "book"
    _wire_registry(monkeypatch, root, active_fail=True)
    _write_latest(root, {"as_of": "2026-09-17", "positions": []})

    payload = json.loads(_text(asyncio.run(bot_mcp.get_portfolio.handler({}))))
    assert payload["as_of"] == "2026-09-17"
    assert payload["active"] is None
    assert payload["lifecycle"] == "active"
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["portfolio_registry"]


def test_healthy_book_keeps_existing_success_shape(bot_mcp, tmp_path, monkeypatch):
    root = tmp_path / "book"
    _wire_registry(monkeypatch, root)
    _write_latest(root, {"as_of": "2026-09-17", "positions": [{"ticker": "AAPL"}]})

    payload = json.loads(_text(asyncio.run(bot_mcp.get_portfolio.handler({}))))
    assert payload["as_of"] == "2026-09-17"
    assert payload["portfolio_id"] == "autonomous"
    assert payload["active"] is True
    assert payload["lifecycle"] == "active"
    assert "read_status" not in payload and "failed_sources" not in payload


def _payload(bot_mcp):
    return json.loads(_text(asyncio.run(bot_mcp.get_portfolio.handler({}))))


def test_valid_empty_book_preserves_no_book_contract(bot_mcp, monkeypatch, tmp_path):
    root = tmp_path / "book"
    _wire_registry(monkeypatch, root)
    _write_latest(root, {})
    assert _payload(bot_mcp) == {"status": "no book yet", "portfolio_id": "autonomous"}


def test_no_book_does_not_require_registry_metadata(bot_mcp, monkeypatch, tmp_path):
    root = tmp_path / "book"
    _wire_registry(monkeypatch, root, get_fail=True)
    _write_latest(root, {})
    assert _payload(bot_mcp) == {"status": "no book yet", "portfolio_id": "autonomous"}


@pytest.mark.parametrize("failure", ["import", "default_id", "invalid_path"])
def test_registry_setup_failures_are_closed_before_book_read(bot_mcp, monkeypatch, tmp_path, failure):
    from portfolio import registry
    _wire_registry(monkeypatch, tmp_path / "book")
    reads = []
    original_read = Path.read_text
    def track(path, *args, **kwargs):
        if path.name == "latest.json":
            reads.append(path)
        return original_read(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", track)
    if failure == "import":
        real_import = builtins.__import__
        def unavailable(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "portfolio" and "registry" in (fromlist or ()):
                raise ImportError("secret /Users/private token=do-not-return")
            return real_import(name, globals, locals, fromlist, level)
        monkeypatch.setattr(builtins, "__import__", unavailable)
    elif failure == "default_id":
        monkeypatch.delattr(registry, "DASHBOARD_DEFAULT_ID")
    else:
        monkeypatch.setattr(registry, "data_dir", lambda _pid: None)
    raw = _text(asyncio.run(bot_mcp.get_portfolio.handler({})))
    payload = json.loads(raw)
    assert payload == {
        "portfolio_id": "autonomous" if failure == "invalid_path" else None,
        "read_status": "unavailable", "error": "portfolio_registry_unavailable",
        "failed_sources": ["portfolio_registry"],
    }
    assert reads == []
    assert "secret" not in raw and "/Users/private" not in raw and "token=" not in raw


@pytest.mark.parametrize("value", [None, 0, False, "", ["row"], "book"])
def test_nonmapping_books_are_unavailable(bot_mcp, monkeypatch, tmp_path, value):
    root = tmp_path / "book"
    _wire_registry(monkeypatch, root)
    _write_latest(root, value)
    assert _payload(bot_mcp) == {
        "portfolio_id": "autonomous", "read_status": "unavailable",
        "error": "portfolio_book_unavailable", "failed_sources": ["portfolio_book"],
    }


@pytest.mark.parametrize("kind", ["dangling", "unreadable", "directory"])
def test_failed_book_files_are_not_first_run_absence(bot_mcp, monkeypatch, tmp_path, kind):
    root = tmp_path / "book"
    root.mkdir()
    _wire_registry(monkeypatch, root)
    path = root / "latest.json"
    if kind == "dangling":
        path.symlink_to(root / "missing-target.json")
    elif kind == "directory":
        path.mkdir()
    else:
        _write_latest(root, {"positions": [{"ticker": "AAPL"}]})
        path.chmod(0)
    try:
        if kind == "unreadable":
            with pytest.raises(PermissionError):
                path.read_text()
        payload = _payload(bot_mcp)
        assert payload["read_status"] == "unavailable"
        assert payload["error"] == "portfolio_book_unavailable"
        assert payload["failed_sources"] == ["portfolio_book"]
        assert "status" not in payload
    finally:
        if kind == "unreadable":
            path.chmod(0o600)


def test_book_read_is_not_suppressed_by_exists_observation(bot_mcp, monkeypatch, tmp_path):
    root = tmp_path / "book"
    _wire_registry(monkeypatch, root)
    _write_latest(root, {"positions": [{"ticker": "AAPL"}]})
    path = root / "latest.json"
    real_exists = Path.exists
    def unavailable_exists(target, *args, **kwargs):
        if target == path:
            return False
        return real_exists(target, *args, **kwargs)
    monkeypatch.setattr(Path, "exists", unavailable_exists)
    payload = _payload(bot_mcp)
    assert payload["positions"] == [{"ticker": "AAPL"}]
    assert payload["active"] is True and "read_status" not in payload


@pytest.mark.parametrize("metadata", [None, [], False, 0])
def test_invalid_metadata_preserves_book_as_partial(bot_mcp, monkeypatch, tmp_path, metadata):
    from portfolio import registry
    root = tmp_path / "book"
    _wire_registry(monkeypatch, root)
    _write_latest(root, {"as_of": "2026-11-07", "positions": [{"ticker": "AAPL"}]})
    monkeypatch.setattr(registry, "get", lambda _pid: metadata)
    payload = _payload(bot_mcp)
    assert payload["positions"] == [{"ticker": "AAPL"}] and payload["as_of"] == "2026-11-07"
    assert payload["active"] is None and payload["lifecycle"] is None
    assert payload["read_status"] == "partial" and payload["failed_sources"] == ["portfolio_registry"]


@pytest.mark.parametrize("active", [None, 0, "true"])
def test_invalid_active_status_preserves_known_lifecycle(bot_mcp, monkeypatch, tmp_path, active):
    from portfolio import registry
    root = tmp_path / "book"
    _wire_registry(monkeypatch, root)
    _write_latest(root, {"positions": []})
    monkeypatch.setattr(registry, "is_active", lambda _pid: active)
    payload = _payload(bot_mcp)
    assert payload["positions"] == [] and payload["active"] is None
    assert payload["lifecycle"] == "active"
    assert payload["read_status"] == "partial" and payload["failed_sources"] == ["portfolio_registry"]


def test_inactive_book_preserves_false_without_degradation(bot_mcp, monkeypatch, tmp_path):
    from portfolio import registry
    root = tmp_path / "book"
    _wire_registry(monkeypatch, root)
    _write_latest(root, {"positions": []})
    monkeypatch.setattr(registry, "get", lambda _pid: {"status": "archived"})
    monkeypatch.setattr(registry, "is_active", lambda _pid: False)
    payload = _payload(bot_mcp)
    assert payload["active"] is False and payload["lifecycle"] == "archived"
    assert "read_status" not in payload


def test_registry_identity_overrides_book_and_request_identifiers(bot_mcp, monkeypatch, tmp_path):
    from portfolio import registry
    root = tmp_path / "book"
    _wire_registry(monkeypatch, root)
    _write_latest(root, {
        "portfolio_id": "flagship", "active": False, "lifecycle": "archived",
        "positions": [{"ticker": "AAPL"}],
    })
    selected = []
    def data_dir(pid):
        selected.append(pid)
        return root
    monkeypatch.setattr(registry, "data_dir", data_dir)
    payload = json.loads(_text(asyncio.run(bot_mcp.get_portfolio.handler({"portfolio_id": "flagship"}))))
    assert selected == ["autonomous"] and payload["portfolio_id"] == "autonomous"
    assert payload["positions"] == [{"ticker": "AAPL"}]
    assert payload["active"] is True and payload["lifecycle"] == "active"


def test_empty_mapping_requires_explicit_reader_opt_in(bot_mcp, tmp_path):
    path = tmp_path / "empty.json"
    path.write_text("{}")
    assert bot_mcp._read_first_nonempty_mapping_checked((path,)) == (None, True)
    assert bot_mcp._read_first_nonempty_mapping_checked((path,), allow_empty=True) == ({}, False)


def test_empty_fallback_retains_prior_read_failure(bot_mcp, tmp_path):
    first = tmp_path / "failed.json"
    first.write_text("{ secret")
    empty = tmp_path / "empty.json"
    empty.write_text("{}")
    assert bot_mcp._read_first_nonempty_mapping_checked((first, empty), allow_empty=True) == ({}, True)


def test_opted_in_empty_primary_is_the_selected_mapping(bot_mcp, monkeypatch, tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text("{}")
    fallback = tmp_path / "later.json"
    fallback.write_text('{"later": true}')
    reads = []
    real_read = Path.read_text
    def track(path, *args, **kwargs):
        reads.append(path)
        return real_read(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", track)
    assert bot_mcp._read_first_nonempty_mapping_checked((empty, fallback), allow_empty=True) == ({}, False)
    assert reads == [empty]
