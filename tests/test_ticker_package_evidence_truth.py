"""Ticker deep-dive evidence must distinguish absence from unreadable sources."""
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


def _wire_lenses(monkeypatch, *, fail: bool = False):
    from portfolio import lenses

    if fail:
        def explode(*_args, **_kwargs):
            raise RuntimeError("secret /Users/private/lenses token=do-not-return")
        monkeypatch.setattr(lenses, "decision_matrix", explode)
    else:
        monkeypatch.setattr(lenses, "decision_matrix", lambda *_args, **_kwargs: {})
        monkeypatch.setattr(
            lenses,
            "synthesize",
            lambda _matrix: {"divergences": [], "confluence": 0.0, "vetoes": []},
        )


_DEFAULT_ROWS = object()


def _wire_intake(monkeypatch, rows=_DEFAULT_ROWS, *, fail: bool = False):
    from brain import intake

    if fail:
        def explode(*_args, **_kwargs):
            raise RuntimeError("secret /Users/private/intake api_key=do-not-return")
        monkeypatch.setattr(intake, "queue", explode)
    else:
        monkeypatch.setattr(intake, "queue", lambda _limit=60: [] if rows is _DEFAULT_ROWS else rows)


def _write_intel(root: Path, ticker: str = "AAPL") -> None:
    path = root / "site" / "intelligence" / "by_ticker.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"tickers": {ticker: {"ticker": ticker, "brain_summary": "healthy"}}}))


def test_genuine_absence_keeps_existing_not_flagged_message(bot_mcp, tmp_path, monkeypatch):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path / "vendor")
    _wire_lenses(monkeypatch)
    _wire_intake(monkeypatch)

    text = _text(asyncio.run(bot_mcp.get_ticker_package.handler({"ticker": "ZZZZ"})))
    assert text == "no per-ticker intelligence for ZZZZ in the inspected artifacts or first 60 intake candidates."


def test_lens_failure_is_partial_secret_safe_and_keeps_healthy_evidence(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_intel(vendor)
    _wire_lenses(monkeypatch, fail=True)
    _wire_intake(monkeypatch, [{"ticker": "AAPL", "score": 8, "sources": ["briefing"]}])

    raw = _text(asyncio.run(bot_mcp.get_ticker_package.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["lenses"]
    assert payload["intelligence"]["brain_summary"] == "healthy"
    assert payload["intake"]["ticker"] == "AAPL"
    assert payload["lenses"] == {
        "read_status": "unavailable",
        "error": "ticker_package_lenses_unavailable",
    }
    assert "secret" not in raw and "/Users/private" not in raw and "do-not-return" not in raw


def test_intake_failure_cannot_be_reported_as_not_flagged(bot_mcp, tmp_path, monkeypatch):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path / "vendor")
    _wire_lenses(monkeypatch)
    _wire_intake(monkeypatch, fail=True)

    raw = _text(asyncio.run(bot_mcp.get_ticker_package.handler({"ticker": "ZZZZ"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["intake"]
    assert payload["intake"] is None
    assert "not flagged by any dashboard engine" not in raw
    assert "secret" not in raw and "api_key" not in raw


def test_corrupt_intelligence_store_is_partial_not_no_coverage(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    path = vendor / "site" / "intelligence" / "by_ticker.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ definitely not json")
    _wire_lenses(monkeypatch)
    _wire_intake(monkeypatch)

    raw = _text(asyncio.run(bot_mcp.get_ticker_package.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["intelligence"]
    assert payload["intelligence"] is None
    assert "not flagged by any dashboard engine" not in raw


def test_all_ticker_package_sources_failed_is_unavailable(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    path = vendor / "site" / "intelligence" / "by_ticker.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ definitely not json")
    _wire_lenses(monkeypatch, fail=True)
    _wire_intake(monkeypatch, fail=True)

    raw = _text(asyncio.run(bot_mcp.get_ticker_package.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "ticker_package_unavailable"
    assert payload["failed_sources"] == ["intelligence", "lenses", "intake"]
    assert payload["intelligence"] is None and payload["intake"] is None
    assert "secret" not in raw and "/Users/private" not in raw and "do-not-return" not in raw


def test_wrong_shape_intelligence_store_is_partial_not_exception(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    path = vendor / "site" / "intelligence" / "by_ticker.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[]")
    _wire_lenses(monkeypatch)
    _wire_intake(monkeypatch)

    raw = _text(asyncio.run(bot_mcp.get_ticker_package.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["intelligence"]
    assert payload["intelligence"] is None


def test_corrupt_primary_can_use_healthy_fallback_but_stays_partial(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    primary = vendor / "site" / "intelligence" / "by_ticker.json"
    primary.parent.mkdir(parents=True, exist_ok=True)
    primary.write_text("{ broken")
    fallback = vendor / "data" / "intelligence" / "by_ticker.json"
    fallback.parent.mkdir(parents=True, exist_ok=True)
    fallback.write_text(json.dumps({"tickers": {"AAPL": {"brain_summary": "fallback-ok"}}}))
    _wire_lenses(monkeypatch)
    _wire_intake(monkeypatch)

    raw = _text(asyncio.run(bot_mcp.get_ticker_package.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["intelligence"]
    assert payload["intelligence"]["brain_summary"] == "fallback-ok"


def _prepare(bot_mcp, root, monkeypatch, *, intel=True):
    monkeypatch.setattr(bot_mcp, "_V", root)
    if intel:
        _write_intel(root)
    _wire_lenses(monkeypatch)
    _wire_intake(monkeypatch)


def _payload(bot_mcp, ticker="AAPL"):
    return json.loads(_text(asyncio.run(bot_mcp.get_ticker_package.handler({"ticker": ticker}))))


def _write_payload(root, relative, value):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


def _wire_synthesis(monkeypatch, value):
    from portfolio import lenses

    monkeypatch.setattr(lenses, "decision_matrix", lambda *_a, **_k: {})
    monkeypatch.setattr(lenses, "synthesize", lambda _matrix: value)


@pytest.mark.parametrize("value", [None, [], False, 0])
def test_invalid_intelligence_document_cannot_establish_absence(bot_mcp, tmp_path, monkeypatch, value):
    _prepare(bot_mcp, tmp_path, monkeypatch, intel=False)
    _write_payload(tmp_path, "site/intelligence/by_ticker.json", value)
    payload = _payload(bot_mcp)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["intelligence"]
    assert payload["intelligence"] is None


@pytest.mark.parametrize("value", [False, [], 0, ""])
def test_invalid_nested_ticker_store_remains_unknown(bot_mcp, tmp_path, monkeypatch, value):
    _prepare(bot_mcp, tmp_path, monkeypatch, intel=False)
    _write_payload(tmp_path, "site/intelligence/by_ticker.json", {"tickers": value})
    payload = _payload(bot_mcp)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["intelligence"]
    assert payload["intelligence"] is None


@pytest.mark.parametrize("value", [None, [], False])
def test_present_invalid_ticker_record_is_not_no_coverage(bot_mcp, tmp_path, monkeypatch, value):
    _prepare(bot_mcp, tmp_path, monkeypatch, intel=False)
    _write_payload(tmp_path, "site/intelligence/by_ticker.json", {"tickers": {"AAPL": value}})
    payload = _payload(bot_mcp)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["intelligence"]
    assert payload["intelligence"] is None


def test_present_empty_ticker_record_is_preserved(bot_mcp, tmp_path, monkeypatch):
    _prepare(bot_mcp, tmp_path, monkeypatch, intel=False)
    _write_payload(tmp_path, "site/intelligence/by_ticker.json", {"tickers": {"AAPL": {}}})
    payload = _payload(bot_mcp)
    assert payload["intelligence"] == {}
    assert "read_status" not in payload and "failed_sources" not in payload


@pytest.mark.parametrize("value", [None, {}, []])
def test_invalid_lens_mapping_is_closed_without_discarding_intelligence(bot_mcp, tmp_path, monkeypatch, value):
    _prepare(bot_mcp, tmp_path, monkeypatch)
    _wire_synthesis(monkeypatch, value)
    payload = _payload(bot_mcp)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["lenses"]
    assert payload["intelligence"]["brain_summary"] == "healthy"
    assert payload["lenses"] == {"read_status": "unavailable", "error": "ticker_package_lenses_unavailable"}


@pytest.mark.parametrize("value", [None, False, float("nan")])
def test_invalid_confluence_cannot_be_published_as_numeric_evidence(bot_mcp, tmp_path, monkeypatch, value):
    _prepare(bot_mcp, tmp_path, monkeypatch)
    _wire_synthesis(monkeypatch, {"confluence": value, "divergences": [], "vetoes": []})
    payload = _payload(bot_mcp)
    assert payload["failed_sources"] == ["lenses"]
    assert payload["lenses"]["read_status"] == "unavailable"
    assert payload["intelligence"]["brain_summary"] == "healthy"


@pytest.mark.parametrize("field,value", [("divergences", False), ("vetoes", {}), ("vetoes", None)])
def test_invalid_lens_evidence_lists_are_unavailable(bot_mcp, tmp_path, monkeypatch, field, value):
    _prepare(bot_mcp, tmp_path, monkeypatch)
    synthesis = {"confluence": 0.0, "divergences": [], "vetoes": []}
    synthesis[field] = value
    _wire_synthesis(monkeypatch, synthesis)
    payload = _payload(bot_mcp)
    assert payload["failed_sources"] == ["lenses"]
    assert payload["read_status"] == "partial"
    assert payload["lenses"]["read_status"] == "unavailable"


@pytest.mark.parametrize("field,value", [("data_degraded", 0), ("n_scored", True), ("size_authority", None)])
def test_invalid_producer_qualifiers_are_not_silently_dropped(bot_mcp, tmp_path, monkeypatch, field, value):
    _prepare(bot_mcp, tmp_path, monkeypatch)
    synthesis = {"confluence": 0.0, "divergences": [], "vetoes": [], field: value}
    _wire_synthesis(monkeypatch, synthesis)
    payload = _payload(bot_mcp)
    assert payload["failed_sources"] == ["lenses"]
    assert payload["intelligence"]["brain_summary"] == "healthy"
    assert payload["lenses"]["error"] == "ticker_package_lenses_unavailable"


@pytest.mark.parametrize("value", [None, False, {}])
def test_invalid_intake_census_is_not_ordinary_absence(bot_mcp, tmp_path, monkeypatch, value):
    _prepare(bot_mcp, tmp_path, monkeypatch)
    _wire_intake(monkeypatch, value)
    payload = _payload(bot_mcp)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["intake"]
    assert payload["intake"] is None
    assert payload["intelligence"]["brain_summary"] == "healthy"


def test_malformed_intake_rows_keep_valid_full_provenance(bot_mcp, tmp_path, monkeypatch):
    _prepare(bot_mcp, tmp_path, monkeypatch)
    row = {
        "ticker": "AAPL", "candidacy_score": 8.2, "n_sources": 3, "n_observed_sources": 2,
        "source_qualification": {"observed": ["briefing", "flow"], "seeded": ["static"]},
        "sources": ["briefing", "flow", "static"],
    }
    _wire_intake(monkeypatch, [None, {"ticker": 9}, row, {}, {"ticker": ""}])
    payload = _payload(bot_mcp)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["intake"]
    assert payload["intake"] == row
    assert payload["intelligence"]["brain_summary"] == "healthy"


def test_intake_identifier_normalization_preserves_original_row(bot_mcp, tmp_path, monkeypatch):
    _prepare(bot_mcp, tmp_path, monkeypatch)
    row = {"ticker": "aapl", "candidacy_score": 2, "source_qualification": {"coverage": "bounded"}}
    _wire_intake(monkeypatch, [row])
    payload = _payload(bot_mcp)
    assert payload["intake"] == row
    assert "read_status" not in payload


def test_usable_mirror_with_two_failed_families_is_partial(bot_mcp, tmp_path, monkeypatch):
    _prepare(bot_mcp, tmp_path, monkeypatch)
    primary = tmp_path / "site/intelligence/by_ticker.json"
    primary.write_text("{ broken")
    _write_payload(tmp_path, "data/intelligence/by_ticker.json", {"tickers": {"AAPL": {"brain_summary": "mirror"}}})
    _wire_lenses(monkeypatch, fail=True)
    _wire_intake(monkeypatch, fail=True)
    payload = _payload(bot_mcp)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["intelligence", "lenses", "intake"]
    assert payload["intelligence"] == {"brain_summary": "mirror"}
    assert "error" not in payload


@pytest.mark.parametrize("mode", ["directory", "dangling", "permission", "exists_false"])
def test_intelligence_file_boundary_preserves_read_failure_truth(bot_mcp, tmp_path, monkeypatch, mode):
    _prepare(bot_mcp, tmp_path, monkeypatch)
    path = tmp_path / "site/intelligence/by_ticker.json"
    if mode == "directory":
        path.unlink()
        path.mkdir()
    elif mode == "dangling":
        path.unlink()
        path.symlink_to(tmp_path / "missing-intelligence-target")
    elif mode == "permission":
        original = Path.read_text

        def read_text(candidate, *args, **kwargs):
            if candidate == path:
                raise PermissionError("private intelligence secret token=do-not-return")
            return original(candidate, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", read_text)
    else:
        original = Path.exists
        monkeypatch.setattr(Path, "exists", lambda candidate: False if candidate == path else original(candidate))
    raw = _text(asyncio.run(bot_mcp.get_ticker_package.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    if mode == "exists_false":
        assert payload["intelligence"]["brain_summary"] == "healthy"
        assert "read_status" not in payload
    else:
        assert payload["read_status"] == "partial"
        assert payload["failed_sources"] == ["intelligence"]
    assert "private intelligence" not in raw and "do-not-return" not in raw


def test_valid_primary_without_ticker_does_not_borrow_mirror(bot_mcp, tmp_path, monkeypatch):
    _prepare(bot_mcp, tmp_path, monkeypatch, intel=False)
    _write_payload(tmp_path, "site/intelligence/by_ticker.json", {"tickers": {"MSFT": {}}})
    _write_payload(tmp_path, "data/intelligence/by_ticker.json", {"tickers": {"AAPL": {"brain_summary": "old mirror"}}})
    row = {"ticker": "AAPL", "source_qualification": {"coverage": "queue window"}}
    _wire_intake(monkeypatch, [row])
    payload = _payload(bot_mcp)
    assert payload["intelligence"] is None
    assert payload["intake"] == row
    assert "read_status" not in payload


@pytest.mark.parametrize("veto", [False, True])
def test_real_degraded_synthesis_preserves_numeric_evidence_and_producer_authority(bot_mcp, tmp_path, monkeypatch, veto):
    from portfolio import lenses

    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    _wire_intake(monkeypatch)
    rows = [
        {"lens": "conviction", "direction": "neutral", "value": {"stockdata_present": False}},
        {"lens": "altdata_flow", "direction": "bull", "value": {}},
    ]
    if veto:
        rows.append({"lens": "extension", "direction": "bear", "value": {"parabolic": True}})
    monkeypatch.setattr(lenses, "_LENS_WEIGHTS_CACHE", {})
    monkeypatch.setattr(lenses, "decision_matrix", lambda *_a, **_k: {"rows": rows})
    payload = _payload(bot_mcp)
    assert payload["read_status"] == "partial"
    assert payload["degraded_sources"] == ["lenses"]
    assert "failed_sources" not in payload
    assert payload["lenses"]["data_degraded"] is True
    assert payload["lenses"]["stockdata_present"] is False
    assert payload["lenses"]["n_scored"] == (2 if veto else 1)
    assert payload["lenses"]["confluence"] == (0.0 if veto else 1.0)
    assert payload["lenses"]["size_authority"] == ("blocked" if veto else "insufficient_data")
    assert payload["lenses"]["thin_evidence"] is True
    assert ("parabolic" in payload["lenses"]["vetoes"]) is veto
    assert payload["intelligence"] is None and payload["intake"] is None


def test_real_healthy_lens_evidence_is_retained_without_intelligence_or_intake_row(bot_mcp, tmp_path, monkeypatch):
    from portfolio import lenses

    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    _wire_intake(monkeypatch)
    matrix = {"rows": [
        {"lens": "trend", "direction": "bull", "value": {}},
        {"lens": "flows_13f", "direction": "bull", "value": {}},
    ]}
    monkeypatch.setattr(lenses, "_LENS_WEIGHTS_CACHE", {})
    monkeypatch.setattr(lenses, "decision_matrix", lambda *_a, **_k: matrix)
    payload = _payload(bot_mcp)
    assert payload["lenses"]["data_degraded"] is False
    assert payload["lenses"]["stockdata_present"] is True
    assert payload["lenses"]["n_scored"] == 2
    assert payload["lenses"]["confluence"] == 1.0
    assert "read_status" not in payload
    assert "complete upstream coverage" in payload["note"]
    assert payload["intelligence"] is None and payload["intake"] is None


def test_healthy_projection_keeps_full_intake_row(bot_mcp, tmp_path, monkeypatch):
    _prepare(bot_mcp, tmp_path, monkeypatch)
    row = {"ticker": "AAPL", "candidacy_score": 8, "n_observed_sources": 2, "source_qualification": {"observed": ["one", "two"]}}
    _wire_intake(monkeypatch, [row])
    payload = _payload(bot_mcp)
    assert payload["intelligence"]["brain_summary"] == "healthy"
    assert payload["lenses"] == {"confluence": 0.0, "divergences": [], "vetoes": []}
    assert payload["intake"] == row
    assert "read_status" not in payload and "failed_sources" not in payload


@pytest.mark.parametrize("component", ["lenses", "intake"])
def test_cyclic_producer_payload_does_not_lose_intelligence(bot_mcp, tmp_path, monkeypatch, component):
    _prepare(bot_mcp, tmp_path, monkeypatch)
    cycle = {}
    cycle["self"] = cycle
    if component == "lenses":
        _wire_synthesis(monkeypatch, {"confluence": 0.0, "divergences": [cycle], "vetoes": []})
    else:
        _wire_intake(monkeypatch, [{"ticker": "AAPL", "source_qualification": cycle}])
    payload = _payload(bot_mcp)
    assert payload["intelligence"]["brain_summary"] == "healthy"
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == [component]
    if component == "lenses":
        assert payload["lenses"]["error"] == "ticker_package_lenses_unavailable"
    else:
        assert payload["intake"] is None


@pytest.mark.parametrize("ticker", [None, "", 0, "../../private", "A/B", "A\\B", "A\u0000B"])
def test_invalid_query_stops_before_artifact_or_producer_access(bot_mcp, tmp_path, monkeypatch, ticker):
    from brain import intake
    from portfolio import lenses

    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    calls = []
    monkeypatch.setattr(bot_mcp, "_read_ticker_feed_checked", lambda *_a, **_k: calls.append("intelligence"))
    monkeypatch.setattr(lenses, "decision_matrix", lambda *_a, **_k: calls.append("lenses"))
    monkeypatch.setattr(intake, "queue", lambda *_a, **_k: calls.append("intake"))
    payload = json.loads(_text(asyncio.run(bot_mcp.get_ticker_package.handler({"ticker": ticker}))))
    assert calls == []
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "ticker_package_unavailable"


def test_explicit_empty_intelligence_mapping_keeps_bounded_absence(bot_mcp, tmp_path, monkeypatch):
    _prepare(bot_mcp, tmp_path, monkeypatch, intel=False)
    _write_payload(tmp_path, "site/intelligence/by_ticker.json", {})
    raw = _text(asyncio.run(bot_mcp.get_ticker_package.handler({"ticker": "AAPL"})))
    assert raw == "no per-ticker intelligence for AAPL in the inspected artifacts or first 60 intake candidates."
    assert "not flagged by any dashboard engine" not in raw
