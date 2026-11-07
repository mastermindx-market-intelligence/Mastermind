"""Single-name Brain research reads must distinguish coverage absence from failed evidence."""
from __future__ import annotations

import asyncio
import importlib
import json
import sys
import types
from contextlib import contextmanager
from pathlib import Path

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


def test_genuine_coverage_absence_keeps_existing_messages(bot_mcp, tmp_path, monkeypatch):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path / "vendor")

    assert _text(asyncio.run(bot_mcp.get_fundamentals.handler({"ticker": "ZZZZ"}))) == (
        "no stock file for ZZZZ (covered: S&P 1500 + crypto; ships in the Pages artifact)."
    )
    assert _text(asyncio.run(bot_mcp.get_options.handler({"ticker": "ZZZZ"}))) == (
        "no options/GEX file for ZZZZ (only the ~liquid options universe is covered)."
    )
    assert _text(asyncio.run(bot_mcp.get_anticipation.handler({"ticker": "ZZZZ"}))) == (
        "no anticipation file for ZZZZ (only the curated forward-signal watchlist is covered)."
    )


def test_corrupt_fundamentals_are_unavailable_and_secret_safe(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "stockdata" / "AAPL.json")

    raw = _text(asyncio.run(bot_mcp.get_fundamentals.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload == {
        "ticker": "AAPL",
        "read_status": "unavailable",
        "error": "ticker_fundamentals_unavailable",
        "failed_sources": ["fundamentals"],
    }
    assert "secret" not in raw and "do-not-return" not in raw


def test_wrong_fundamental_section_is_partial_and_keeps_healthy_sections(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_json(vendor / "site" / "stockdata" / "AAPL.json", {
        "name": "Apple",
        "sector": "Technology",
        "asof": "2026-09-17",
        "valuation": ["wrong-shape"],
        "financials": {"roe": 0.31, "net_margin": 0.25},
        "conviction": {"score": 81, "band": "high"},
    })

    payload = json.loads(_text(asyncio.run(bot_mcp.get_fundamentals.handler({"ticker": "AAPL"}))))
    assert payload["name"] == "Apple"
    assert payload["valuation"] is None
    assert payload["financials"]["roe"] == 0.31
    assert payload["conviction"]["score"] == 81
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["fundamentals"]


def test_corrupt_options_are_unavailable_not_uncovered(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "gex" / "AAPL.json")

    raw = _text(asyncio.run(bot_mcp.get_options.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "ticker_options_unavailable"
    assert payload["failed_sources"] == ["options"]
    assert "liquid options universe" not in raw


def test_wrong_options_meta_is_partial_and_keeps_healthy_summary(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_json(vendor / "site" / "gex" / "AAPL.json", {
        "meta": "wrong-shape",
        "summary": {"spot": 250.0, "regime": "long"},
        "expected_move": {"daily_pct": 1.3},
        "vol_hole": {"state": "compressed"},
    })

    payload = json.loads(_text(asyncio.run(bot_mcp.get_options.handler({"ticker": "AAPL"}))))
    assert payload["asof"] is None
    assert payload["summary"]["spot"] == 250.0
    assert payload["expected_move"]["daily_pct"] == 1.3
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["options"]


def test_corrupt_anticipation_is_unavailable_not_uncovered(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "anticipationdata" / "AAPL.json")

    raw = _text(asyncio.run(bot_mcp.get_anticipation.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "ticker_anticipation_unavailable"
    assert payload["failed_sources"] == ["anticipation"]
    assert "curated forward-signal watchlist" not in raw


def test_empty_existing_anticipation_is_failed_evidence(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_json(vendor / "site" / "anticipationdata" / "AAPL.json", {})

    payload = json.loads(_text(asyncio.run(bot_mcp.get_anticipation.handler({"ticker": "AAPL"}))))
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "ticker_anticipation_unavailable"


def test_healthy_single_name_research_keeps_existing_shapes(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_json(vendor / "site" / "stockdata" / "AAPL.json", {
        "name": "Apple", "sector": "Technology", "asof": "2026-09-17",
        "valuation": {"forward_pe": 30.0}, "financials": {"roe": 0.31},
    })
    _write_json(vendor / "site" / "gex" / "AAPL.json", {
        "meta": {"asof": "2026-09-17"}, "summary": {"spot": 250.0},
        "expected_move": {"daily_pct": 1.2}, "vol_hole": {"state": "normal"},
    })
    _write_json(vendor / "site" / "anticipationdata" / "AAPL.json", {
        "name": "Apple", "group": "mega-cap", "as_of": "2026-09-17",
        "anticipation_index": 0.6, "direction_trust": "high",
    })

    fundamentals = json.loads(_text(asyncio.run(bot_mcp.get_fundamentals.handler({"ticker": "AAPL"}))))
    options = json.loads(_text(asyncio.run(bot_mcp.get_options.handler({"ticker": "AAPL"}))))
    anticipation = json.loads(_text(asyncio.run(bot_mcp.get_anticipation.handler({"ticker": "AAPL"}))))
    assert fundamentals["valuation"]["forward_pe"] == 30.0 and "read_status" not in fundamentals
    assert options["summary"]["spot"] == 250.0 and "read_status" not in options
    assert anticipation["anticipation_index"] == 0.6 and "read_status" not in anticipation


_READERS = [
    ("get_fundamentals", "stockdata", "fundamentals"),
    ("get_options", "gex", "options"),
    ("get_anticipation", "anticipationdata", "anticipation"),
]


def _vendor(bot_mcp, monkeypatch, tmp_path):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    return vendor


def _unavailable(bot_mcp, handler, source, ticker="AAPL", expected_ticker="AAPL"):
    raw = _text(asyncio.run(getattr(bot_mcp, handler).handler({"ticker": ticker})))
    assert json.loads(raw) == {
        "ticker": expected_ticker,
        "read_status": "unavailable",
        "error": f"ticker_{source}_unavailable",
        "failed_sources": [source],
    }
    assert "private-secret" not in raw
    return raw


@pytest.mark.parametrize("handler,family,source", [
    ("get_fundamentals", "stockdata", "fundamentals"),
    ("get_options", "gex", "options"),
    ("get_anticipation", "anticipationdata", "anticipation"),
])
def test_ticker_parent_path_cannot_read_another_artifact(bot_mcp, monkeypatch, tmp_path, handler, family, source):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    (vendor / "site" / family).mkdir(parents=True)
    escaped = vendor / "site" / "ESCAPE.json"
    _write_json(escaped, {
        "name": "private-secret",
        "meta": {"asof": "private-secret"},
        "anticipation_index": "private-secret",
    })
    original_read = Path.read_text
    reads = []

    def watched_read(path, *args, **kwargs):
        if path.resolve() == escaped:
            reads.append(path)
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", watched_read)
    _unavailable(bot_mcp, handler, source, ticker="../ESCAPE", expected_ticker=None)
    assert reads == []


@pytest.mark.parametrize("ticker", [None, False, 0, 42, {}, ["AAPL"], ""])
def test_invalid_ticker_value_is_closed_before_file_reads(bot_mcp, monkeypatch, tmp_path, ticker):
    _vendor(bot_mcp, monkeypatch, tmp_path)
    reads = []

    def forbidden_read(path, *args, **kwargs):
        reads.append(path)
        raise AssertionError("invalid ticker reached a file read")

    monkeypatch.setattr(Path, "read_text", forbidden_read)
    for handler, _family, source in _READERS:
        _unavailable(bot_mcp, handler, source, ticker=ticker, expected_ticker=None)
    assert reads == []


@pytest.mark.parametrize("ticker", ["/ABSOLUTE", r"..\ESCAPE", "bad\0ticker"])
def test_ticker_separator_or_nul_is_closed_before_reads(bot_mcp, monkeypatch, tmp_path, ticker):
    _vendor(bot_mcp, monkeypatch, tmp_path)
    reads = []

    def forbidden_read(path, *args, **kwargs):
        reads.append(path)
        raise AssertionError("invalid ticker reached a file read")

    monkeypatch.setattr(Path, "read_text", forbidden_read)
    for handler, _family, source in _READERS:
        _unavailable(bot_mcp, handler, source, ticker=ticker, expected_ticker=None)
    assert reads == []


@pytest.mark.parametrize("ticker", ["BRK.B", "BTC-USD", "_INDEX", "^GSPC"])
def test_existing_symbol_filename_conventions_remain_compatible(bot_mcp, monkeypatch, tmp_path, ticker):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    for handler, family, _source in _READERS:
        _write_json(vendor / "site" / family / f"{ticker}.json", {
            "name": ticker,
            "meta": {"asof": "2026-09-17"},
            "summary": {"spot": 250.0},
            "valuation": {"forward_pe": 30.0},
            "anticipation_index": 0.6,
        })
        payload = json.loads(_text(asyncio.run(getattr(bot_mcp, handler).handler({"ticker": ticker.lower()}))))
        assert payload["ticker"] == ticker
        assert "read_status" not in payload
        if handler == "get_fundamentals":
            assert payload["valuation"]["forward_pe"] == 30.0
        elif handler == "get_options":
            assert payload["summary"]["spot"] == 250.0
        else:
            assert payload["anticipation_index"] == 0.6


@pytest.mark.parametrize("handler,family,source", [
    ("get_fundamentals", "stockdata", "fundamentals"),
    ("get_options", "gex", "options"),
    ("get_anticipation", "anticipationdata", "anticipation"),
])
def test_existing_null_is_not_coverage_absence(bot_mcp, monkeypatch, tmp_path, handler, family, source):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    _write_json(vendor / "site" / family / "AAPL.json", None)
    _unavailable(bot_mcp, handler, source)


@pytest.mark.parametrize("value", [False, 0, [], {}])
def test_existing_wrong_top_level_shapes_are_unavailable(bot_mcp, monkeypatch, tmp_path, value):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    for handler, family, source in _READERS:
        _write_json(vendor / "site" / family / "AAPL.json", value)
        _unavailable(bot_mcp, handler, source)


@pytest.mark.parametrize("case", ["dangling", "unreadable"])
def test_single_name_storage_failure_is_not_uncovered(bot_mcp, monkeypatch, tmp_path, case):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    for handler, family, source in _READERS:
        path = vendor / "site" / family / "AAPL.json"
        path.parent.mkdir(parents=True)
        if case == "dangling":
            path.symlink_to(path.parent / "missing-target.json")
        else:
            path.write_text('{"private-secret": true}', encoding="utf-8")
            path.chmod(0)
        try:
            if case == "unreadable":
                with pytest.raises(PermissionError):
                    path.read_text()
            _unavailable(bot_mcp, handler, source)
        finally:
            if case == "unreadable":
                path.chmod(0o600)


def test_readable_artifact_is_not_suppressed_by_exists_observation(bot_mcp, monkeypatch, tmp_path):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    paths = []
    for _handler, family, _source in _READERS:
        path = vendor / "site" / family / "AAPL.json"
        _write_json(path, {
            "name": "Apple", "summary": {"spot": 250.0},
            "valuation": {"forward_pe": 30.0}, "anticipation_index": 0.6,
        })
        paths.append(path)
    original_exists = Path.exists

    def unavailable_exists(path, *args, **kwargs):
        if path in paths:
            return False
        return original_exists(path, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", unavailable_exists)
    for handler, _family, _source in _READERS:
        payload = json.loads(_text(asyncio.run(getattr(bot_mcp, handler).handler({"ticker": "AAPL"}))))
        assert payload["ticker"] == "AAPL"
        assert "read_status" not in payload


@pytest.mark.parametrize("kind", ["absent", "null"])
def test_optional_sections_preserve_healthy_default_projections(bot_mcp, monkeypatch, tmp_path, kind):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    fundamental = {"name": "Apple", "financials": {"roe": 0.31}}
    options = {"summary": {"spot": 250.0}}
    if kind == "null":
        fundamental["valuation"] = None
        options.update({"meta": None, "expected_move": None, "vol_hole": None})
    _write_json(vendor / "site" / "stockdata" / "AAPL.json", fundamental)
    _write_json(vendor / "site" / "gex" / "AAPL.json", options)
    f = json.loads(_text(asyncio.run(bot_mcp.get_fundamentals.handler({"ticker": "AAPL"}))))
    o = json.loads(_text(asyncio.run(bot_mcp.get_options.handler({"ticker": "AAPL"}))))
    assert f["valuation"] == {} and f["financials"]["roe"] == 0.31
    assert o["asof"] is None and o["summary"]["spot"] == 250.0
    assert o["expected_move"] == {} and o["vol_hole"] == {}
    assert "read_status" not in f and "read_status" not in o


@pytest.mark.parametrize("value", [False, 0, [], ""])
def test_malformed_falsy_sections_are_partial_without_losing_healthy_fields(bot_mcp, monkeypatch, tmp_path, value):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    _write_json(vendor / "site" / "stockdata" / "AAPL.json", {
        "name": "Apple", "valuation": value, "financials": {"roe": 0.31},
    })
    _write_json(vendor / "site" / "gex" / "AAPL.json", {
        "meta": value, "summary": {"spot": 250.0}, "expected_move": {"daily_pct": 1.2},
    })
    f = json.loads(_text(asyncio.run(bot_mcp.get_fundamentals.handler({"ticker": "AAPL"}))))
    o = json.loads(_text(asyncio.run(bot_mcp.get_options.handler({"ticker": "AAPL"}))))
    assert f["valuation"] is None and f["financials"]["roe"] == 0.31
    assert f["read_status"] == "partial" and f["failed_sources"] == ["fundamentals"]
    assert o["asof"] is None and o["summary"]["spot"] == 250.0
    assert o["expected_move"]["daily_pct"] == 1.2
    assert o["read_status"] == "partial" and o["failed_sources"] == ["options"]
