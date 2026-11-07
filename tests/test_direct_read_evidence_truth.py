"""Direct/live Brain reads must be closed, secret-safe, and non-speculative on failure."""
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


def test_quote_transport_failure_is_closed_and_secret_safe(bot_mcp, monkeypatch):
    from data_layer import polygon

    def explode(_tickers):
        raise RuntimeError("secret /Users/private/polygon api_key=do-not-return")

    monkeypatch.setattr(polygon, "quotes", explode)
    raw = _text(asyncio.run(bot_mcp.get_quote.handler({"tickers": ["AAPL"]})))
    payload = json.loads(raw)
    assert payload == {
        "read_status": "unavailable",
        "error": "live_quotes_unavailable",
        "failed_sources": ["quotes"],
        "quotes": None,
    }
    assert "secret" not in raw and "/Users/private" not in raw and "api_key" not in raw


def test_quote_wrong_shape_is_unavailable(bot_mcp, monkeypatch):
    from data_layer import polygon
    monkeypatch.setattr(polygon, "quotes", lambda _tickers: [250.0])

    payload = json.loads(_text(asyncio.run(bot_mcp.get_quote.handler({"tickers": ["AAPL"]}))))
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "live_quotes_unavailable"
    assert payload["quotes"] is None


def test_all_null_quotes_do_not_claim_provider_outage(bot_mcp, monkeypatch):
    from data_layer import polygon
    monkeypatch.setattr(polygon, "quotes", lambda _tickers: {"AAPL": None})

    text = _text(asyncio.run(bot_mcp.get_quote.handler({"tickers": ["AAPL"]})))
    assert text == "no live quotes returned for the requested tickers."
    assert "offline" not in text.lower() and "api key" not in text.lower()


def test_healthy_quotes_keep_existing_payload(bot_mcp, monkeypatch):
    from data_layer import polygon
    monkeypatch.setattr(polygon, "quotes", lambda _tickers: {"AAPL": 250.0, "MSFT": None})

    payload = json.loads(_text(asyncio.run(bot_mcp.get_quote.handler({"tickers": ["AAPL", "MSFT"]}))))
    assert payload["quotes"] == {"AAPL": 250.0, "MSFT": None}
    assert "read_status" not in payload


def test_read_signal_missing_does_not_disclose_absolute_allowed_path(bot_mcp, tmp_path, monkeypatch):
    allowed = tmp_path / "vendor" / "macro" / "site"
    allowed.mkdir(parents=True)
    monkeypatch.setattr(bot_mcp, "_ROOT", tmp_path)
    monkeypatch.setattr(bot_mcp, "_READ_ROOTS", [allowed])
    monkeypatch.setattr(bot_mcp, "_DENY_ROOTS", [])

    target = allowed / "signals" / "missing.json"
    text = _text(asyncio.run(bot_mcp.read_signal.handler({"path": str(target)})))
    assert text == "not found: requested signal path"
    assert str(tmp_path) not in text


def test_read_signal_corrupt_json_is_closed_and_secret_safe(bot_mcp, tmp_path, monkeypatch):
    allowed = tmp_path / "vendor" / "macro" / "site"
    target = allowed / "signals" / "bad.json"
    target.parent.mkdir(parents=True)
    target.write_text("{ broken secret token=do-not-return")
    monkeypatch.setattr(bot_mcp, "_ROOT", tmp_path)
    monkeypatch.setattr(bot_mcp, "_READ_ROOTS", [allowed])
    monkeypatch.setattr(bot_mcp, "_DENY_ROOTS", [])

    raw = _text(asyncio.run(bot_mcp.read_signal.handler({"path": str(target)})))
    payload = json.loads(raw)
    assert payload == {
        "read_status": "unavailable",
        "error": "signal_read_unavailable",
        "failed_sources": ["signal"],
    }
    assert "secret" not in raw and "do-not-return" not in raw and str(tmp_path) not in raw


def test_read_signal_valid_json_is_unchanged(bot_mcp, tmp_path, monkeypatch):
    allowed = tmp_path / "vendor" / "macro" / "site"
    target = allowed / "signals" / "ok.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"schema": "signal.v1", "value": 7}))
    monkeypatch.setattr(bot_mcp, "_ROOT", tmp_path)
    monkeypatch.setattr(bot_mcp, "_READ_ROOTS", [allowed])
    monkeypatch.setattr(bot_mcp, "_DENY_ROOTS", [])

    payload = json.loads(_text(asyncio.run(bot_mcp.read_signal.handler({"path": str(target)}))))
    assert payload == {"schema": "signal.v1", "value": 7}


def _signal_root(monkeypatch, bot_mcp, tmp_path):
    allowed = tmp_path / "data"
    allowed.mkdir()
    monkeypatch.setattr(bot_mcp, "_ROOT", tmp_path)
    monkeypatch.setattr(bot_mcp, "_READ_ROOTS", [allowed])
    monkeypatch.setattr(bot_mcp, "_DENY_ROOTS", [])
    monkeypatch.setattr(bot_mcp, "_LEAK_AUDIT", tmp_path / "denied.jsonl")
    return allowed


def _unavailable_signal(bot_mcp, target):
    raw = _text(asyncio.run(bot_mcp.read_signal.handler({"path": str(target)})))
    assert json.loads(raw) == {
        "read_status": "unavailable",
        "error": "signal_read_unavailable",
        "failed_sources": ["signal"],
    }
    assert str(target) not in raw and "private-secret" not in raw
    return raw


def test_quote_import_failure_is_closed(bot_mcp, monkeypatch):
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "data_layer" and "polygon" in fromlist:
            raise ImportError("private-secret provider setup")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    raw = _text(asyncio.run(bot_mcp.get_quote.handler({"tickers": ["AAPL"]})))
    assert json.loads(raw) == {
        "read_status": "unavailable",
        "error": "live_quotes_unavailable",
        "failed_sources": ["quotes"],
        "quotes": None,
    }
    assert "private-secret" not in raw


def test_quote_serialization_failure_is_closed(bot_mcp, monkeypatch):
    from data_layer import polygon

    circular = {}
    circular["AAPL"] = circular
    monkeypatch.setattr(polygon, "quotes", lambda _tickers: circular)
    raw = _text(asyncio.run(bot_mcp.get_quote.handler({"tickers": ["AAPL"]})))
    assert json.loads(raw) == {
        "read_status": "unavailable",
        "error": "live_quotes_unavailable",
        "failed_sources": ["quotes"],
        "quotes": None,
    }


@pytest.mark.parametrize("case", [
    "dangling_leaf", "dangling_parent", "unreadable_leaf",
    "unreadable_parent", "regular_file_parent", "invalid_utf8",
])
def test_signal_storage_failure_is_not_missing(bot_mcp, monkeypatch, tmp_path, case):
    allowed = _signal_root(monkeypatch, bot_mcp, tmp_path)
    target = allowed / "signal.json"
    restore = None
    if case == "dangling_leaf":
        target.symlink_to(allowed / "missing-target.json")
    elif case == "dangling_parent":
        parent = allowed / "linked"
        parent.symlink_to(allowed / "missing-directory", target_is_directory=True)
        target = parent / "signal.json"
    elif case == "unreadable_leaf":
        target.write_text('{"private-secret": true}', encoding="utf-8")
        target.chmod(0)
        restore = (target, 0o600)
    elif case == "unreadable_parent":
        parent = allowed / "restricted"
        parent.mkdir()
        target = parent / "signal.json"
        target.write_text('{"private-secret": true}', encoding="utf-8")
        parent.chmod(0)
        restore = (parent, 0o700)
    elif case == "regular_file_parent":
        parent = allowed / "regular-file"
        parent.write_text("private-secret", encoding="utf-8")
        target = parent / "signal.json"
    else:
        target.write_bytes(b'{"value": "\xff"}')
    try:
        if case in {"unreadable_leaf", "unreadable_parent"}:
            with pytest.raises(PermissionError):
                target.read_text()
        _unavailable_signal(bot_mcp, target)
    finally:
        if restore:
            restore[0].chmod(restore[1])


def test_signal_failed_absence_inspection_is_unavailable(bot_mcp, monkeypatch, tmp_path):
    allowed = _signal_root(monkeypatch, bot_mcp, tmp_path)
    target = allowed / "missing.json"
    original_lstat = Path.lstat

    def failed_lstat(path, *args, **kwargs):
        if path == target:
            raise PermissionError("private-secret absence inspection")
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", failed_lstat)
    _unavailable_signal(bot_mcp, target)


def test_signal_entry_appeared_after_read_is_not_missing(bot_mcp, monkeypatch, tmp_path):
    allowed = _signal_root(monkeypatch, bot_mcp, tmp_path)
    target = allowed / "appeared.json"
    original_read = Path.read_text
    reads = []

    def appeared_read(path, *args, **kwargs):
        if path == target:
            reads.append(path)
            target.write_text('{"private-secret": true}', encoding="utf-8")
            raise FileNotFoundError("private-secret original read")
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", appeared_read)
    _unavailable_signal(bot_mcp, target)
    assert reads == [target]
    assert target.is_file()


def test_signal_resolution_failure_is_closed(bot_mcp, monkeypatch, tmp_path):
    allowed = _signal_root(monkeypatch, bot_mcp, tmp_path)
    target = allowed / "signal.json"
    original_resolve = Path.resolve

    def failed_resolve(path, *args, **kwargs):
        if path == target:
            raise OSError("private-secret path resolution")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", failed_resolve)
    _unavailable_signal(bot_mcp, target)


def test_signal_json_null_is_valid_content(bot_mcp, monkeypatch, tmp_path):
    allowed = _signal_root(monkeypatch, bot_mcp, tmp_path)
    target = allowed / "null.json"
    target.write_text("null", encoding="utf-8")
    raw = _text(asyncio.run(bot_mcp.read_signal.handler({"path": str(target)})))
    assert json.loads(raw) is None


@pytest.mark.parametrize("denied_kind", ["outside", "book"])
def test_signal_denied_symlink_never_reads_content(bot_mcp, monkeypatch, tmp_path, denied_kind):
    allowed = _signal_root(monkeypatch, bot_mcp, tmp_path)
    target_root = tmp_path / "outside" if denied_kind == "outside" else allowed / "portfolio"
    target_root.mkdir()
    target = target_root / "secret.json"
    target.write_text('{"private-secret": true}', encoding="utf-8")
    link = allowed / "signal.json"
    link.symlink_to(target)
    if denied_kind == "book":
        monkeypatch.setattr(bot_mcp, "_DENY_ROOTS", [target_root])
    original_read = Path.read_text
    content_reads = []

    def watched_read(path, *args, **kwargs):
        if path in (target, link):
            content_reads.append(path)
            raise AssertionError("denied source content must not be read")
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", watched_read)
    raw = _text(asyncio.run(bot_mcp.read_signal.handler({"path": str(link)})))
    assert "DENIED" in raw and "private-secret" not in raw
    assert content_reads == []
    if denied_kind == "book":
        audit = tmp_path / "denied.jsonl"
        rows = [json.loads(line) for line in audit.read_text().splitlines()]
        assert rows[-1]["denied_path"] == str(target)
