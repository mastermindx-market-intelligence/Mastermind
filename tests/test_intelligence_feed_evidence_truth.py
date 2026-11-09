"""News/alt-data/unified Brain reads must distinguish absence from unreadable evidence."""
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


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def _break(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ broken json")


def test_genuine_absence_keeps_existing_no_signal_messages(bot_mcp, tmp_path, monkeypatch):
    monkeypatch.setattr(bot_mcp, "_V", tmp_path / "vendor")

    assert _text(asyncio.run(bot_mcp.get_news.handler({"ticker": "ZZZZ"}))) == (
        "no news-flow signal for ZZZZ — not covered by the macro news surface."
    )
    assert _text(asyncio.run(bot_mcp.get_altdata.handler({"ticker": "ZZZZ"}))) == (
        "no alt-data signal for ZZZZ — not flagged by any political/insider/contract channel."
    )
    assert _text(asyncio.run(bot_mcp.get_intelligence.handler({"ticker": "ZZZZ"}))) == (
        "no news or alt-data intelligence for ZZZZ."
    )


def test_news_corrupt_source_is_unavailable_not_no_coverage(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "news" / "by_ticker.json")

    raw = _text(asyncio.run(bot_mcp.get_news.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "ticker_news_unavailable"
    assert payload["failed_sources"] == ["news"]
    assert payload["news"] is None
    assert "not covered" not in raw and "broken json" not in raw


def test_news_bad_primary_uses_healthy_fallback_but_stays_partial(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "news" / "by_ticker.json")
    _write_json(
        vendor / "data" / "news" / "by_ticker.json",
        {"tickers": {"AAPL": {"headline_count": 4, "sentiment": "positive"}}},
    )

    payload = json.loads(_text(asyncio.run(bot_mcp.get_news.handler({"ticker": "AAPL"}))))
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["news"]
    assert payload["news"]["headline_count"] == 4


def test_altdata_flow_failure_preserves_healthy_graph_as_partial(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "altdata" / "by_ticker.json")
    _write_json(
        vendor / "site" / "altdata" / "latent.json",
        {"watch": [{"ticker": "AAPL", "themes": [{"en": "AI power"}], "note": "graph"}], "mismatches": []},
    )

    payload = json.loads(_text(asyncio.run(bot_mcp.get_altdata.handler({"ticker": "AAPL"}))))
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["altdata_flow"]
    assert payload["flow"] is None
    assert payload["latent_graph"]["themes"] == ["AI power"]


def test_altdata_graph_failure_preserves_healthy_flow_as_partial(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _write_json(
        vendor / "site" / "altdata" / "by_ticker.json",
        {"tickers": {"AAPL": {"signal_score": 77}}},
    )
    _break(vendor / "site" / "altdata" / "latent.json")

    payload = json.loads(_text(asyncio.run(bot_mcp.get_altdata.handler({"ticker": "AAPL"}))))
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["altdata_graph"]
    assert payload["flow"]["signal_score"] == 77
    assert payload["latent_graph"] is None


def test_altdata_all_source_failures_are_unavailable(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "altdata" / "by_ticker.json")
    _break(vendor / "site" / "altdata" / "latent.json")

    raw = _text(asyncio.run(bot_mcp.get_altdata.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "ticker_altdata_unavailable"
    assert payload["failed_sources"] == ["altdata_flow", "altdata_graph"]
    assert "broken json" not in raw


def test_unified_intelligence_failure_can_fall_back_to_news_as_partial(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "intelligence" / "by_ticker.json")
    _write_json(
        vendor / "site" / "news" / "by_ticker.json",
        {"tickers": {"AAPL": {"headline_count": 2}}},
    )

    payload = json.loads(_text(asyncio.run(bot_mcp.get_intelligence.handler({"ticker": "AAPL"}))))
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["unified_intelligence"]
    assert payload["news"]["headline_count"] == 2
    assert payload["alt"] is None


def test_news_fallback_failure_cannot_become_no_intelligence(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "news" / "by_ticker.json")

    raw = _text(asyncio.run(bot_mcp.get_intelligence.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["news"]
    assert "no news or alt-data intelligence" not in raw


def test_all_unified_intelligence_sources_failed_is_unavailable(bot_mcp, tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    _break(vendor / "site" / "intelligence" / "by_ticker.json")
    _break(vendor / "site" / "news" / "by_ticker.json")
    _break(vendor / "site" / "altdata" / "mastermind.json")

    raw = _text(asyncio.run(bot_mcp.get_intelligence.handler({"ticker": "AAPL"})))
    payload = json.loads(raw)
    assert payload["read_status"] == "unavailable"
    assert payload["error"] == "ticker_intelligence_unavailable"
    assert payload["failed_sources"] == ["unified_intelligence", "news", "altdata"]
    assert "broken json" not in raw


def _vendor(bot_mcp, monkeypatch, tmp_path):
    vendor = tmp_path / "vendor"
    monkeypatch.setattr(bot_mcp, "_V", vendor)
    return vendor


def _call(bot_mcp, handler, ticker="AAPL"):
    return _text(asyncio.run(getattr(bot_mcp, handler).handler({"ticker": ticker})))


def _feed(ticker="AAPL", **clocks):
    return {**clocks, "tickers": {ticker: {"headline_count": 4}}}


@pytest.mark.parametrize("family,handler", [
    ("news", "get_news"), ("intelligence", "get_intelligence"),
])
@pytest.mark.parametrize("first_kind", [
    "missing", "empty", "corrupt", "bad_tickers", "bad_record", "null_record",
])
def test_selected_feed_mirror_preserves_its_own_clocks(
    bot_mcp, monkeypatch, tmp_path, family, handler, first_kind,
):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    first = vendor / "site" / family / "by_ticker.json"
    if first_kind == "empty":
        _write_json(first, {})
    elif first_kind == "corrupt":
        _break(first)
    elif first_kind == "bad_tickers":
        _write_json(first, {"asof": "unusable-primary", "tickers": []})
    elif first_kind in ("bad_record", "null_record"):
        _write_json(first, {"asof": "unusable-primary", "tickers": {"AAPL": [] if first_kind == "bad_record" else None}})
    expected = _feed(
        asof="2026-11-07T12:00:00Z", source_asof="2026-11-06",
        generated_utc="2026-11-07T12:05:00Z", retained_from_previous_build=True,
    )
    _write_json(vendor / "data" / family / "by_ticker.json", expected)
    payload = json.loads(_call(bot_mcp, handler))
    record = payload["news"] if family == "news" else payload
    assert record["headline_count"] == 4
    assert payload["freshness"]["source_file"] == f"data/{family}/by_ticker.json"
    for key in ("asof", "source_asof", "generated_utc", "retained_from_previous_build"):
        assert payload["freshness"][key] == expected[key]
    assert payload["evidence_grade"] == "vendored_snapshot"
    if first_kind in ("missing", "empty"):
        assert "read_status" not in payload
    else:
        assert payload["read_status"] == "partial"
        assert payload["failed_sources"] == (["news"] if family == "news" else ["unified_intelligence"])


@pytest.mark.parametrize("family,handler", [
    ("news", "get_news"), ("intelligence", "get_intelligence"),
])
def test_valid_primary_ticker_absence_does_not_search_lower_mirror(
    bot_mcp, monkeypatch, tmp_path, family, handler,
):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    _write_json(vendor / "site" / family / "by_ticker.json", _feed("MSFT"))
    later = vendor / "data" / family / "by_ticker.json"
    _write_json(later, _feed())
    reads = []
    real_read = Path.read_text
    def track(path, *args, **kwargs):
        reads.append(path)
        return real_read(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", track)
    raw = _call(bot_mcp, handler)
    assert raw.startswith("no news")
    assert later not in reads


def test_failed_news_primary_with_readable_empty_mirror_is_partial(bot_mcp, monkeypatch, tmp_path):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    _break(vendor / "site" / "news" / "by_ticker.json")
    _write_json(vendor / "data" / "news" / "by_ticker.json", {})
    payload = json.loads(_call(bot_mcp, "get_news"))
    assert payload["news"] is None and payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["news"] and "error" not in payload
    assert payload["freshness"]["source_file"] == "data/news/by_ticker.json"
    assert payload["freshness"]["asof"] is None


@pytest.mark.parametrize("value", [None, [], 0, False, "", "bad"])
def test_nonmapping_news_is_unavailable_with_unknown_clocks(bot_mcp, monkeypatch, tmp_path, value):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    _write_json(vendor / "site" / "news" / "by_ticker.json", value)
    payload = json.loads(_call(bot_mcp, "get_news"))
    assert payload["read_status"] == "unavailable" and payload["news"] is None
    assert payload["error"] == "ticker_news_unavailable"
    assert payload["freshness"]["source_file"] is None
    assert payload["freshness"]["asof"] is None


@pytest.mark.parametrize("kind", ["dangling", "unreadable", "directory"])
def test_failed_news_file_keeps_healthy_mirror_partial(bot_mcp, monkeypatch, tmp_path, kind):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    first = vendor / "site" / "news" / "by_ticker.json"
    first.parent.mkdir(parents=True)
    if kind == "dangling":
        first.symlink_to(first.parent / "missing-target.json")
    elif kind == "directory":
        first.mkdir()
    else:
        first.write_text(json.dumps(_feed(asof="unusable-primary")))
        first.chmod(0)
    _write_json(vendor / "data" / "news" / "by_ticker.json", _feed(asof="mirror-clock"))
    try:
        if kind == "unreadable":
            with pytest.raises(PermissionError):
                first.read_text()
        payload = json.loads(_call(bot_mcp, "get_news"))
        assert payload["news"]["headline_count"] == 4
        assert payload["read_status"] == "partial" and payload["failed_sources"] == ["news"]
        assert payload["freshness"]["asof"] == "mirror-clock"
        assert payload["freshness"]["source_file"] == "data/news/by_ticker.json"
    finally:
        if kind == "unreadable":
            first.chmod(0o600)


def test_news_read_precedes_unreliable_exists_observation(bot_mcp, monkeypatch, tmp_path):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    first = vendor / "site" / "news" / "by_ticker.json"
    _write_json(first, _feed(asof="selected-clock"))
    real_exists = Path.exists
    def unavailable_exists(path, *args, **kwargs):
        if path == first:
            return False
        return real_exists(path, *args, **kwargs)
    monkeypatch.setattr(Path, "exists", unavailable_exists)
    payload = json.loads(_call(bot_mcp, "get_news"))
    assert payload["news"]["headline_count"] == 4
    assert payload["freshness"]["asof"] == "selected-clock" and "read_status" not in payload


@pytest.mark.parametrize("ticker", [None, 42, False, [], "", "   "])
def test_malformed_feed_query_is_closed_before_artifact_reads(bot_mcp, monkeypatch, tmp_path, ticker):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    reads = []
    real_read = Path.read_text
    def track(path, *args, **kwargs):
        if vendor in path.parents:
            reads.append(path)
        return real_read(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", track)
    for handler, error in (
        ("get_news", "ticker_news_unavailable"),
        ("get_altdata", "ticker_altdata_unavailable"),
        ("get_intelligence", "ticker_intelligence_unavailable"),
    ):
        payload = json.loads(_call(bot_mcp, handler, ticker))
        assert payload["ticker"] is None and payload["read_status"] == "unavailable"
        assert payload["error"] == error
    assert reads == []


@pytest.mark.parametrize("ticker", [None, 42, [], {}, "", "   "])
def test_bad_watch_identifier_keeps_known_graph_and_unknown_absence(
    bot_mcp, monkeypatch, tmp_path, ticker,
):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    _write_json(vendor / "site" / "altdata" / "by_ticker.json", {"tickers": {"AAPL": {"signal_score": 77}}})
    _write_json(vendor / "site" / "altdata" / "latent.json", {
        "watch": [{"ticker": ticker}, {"ticker": "AAPL", "themes": [{"en": "AI power"}]}],
        "mismatches": [],
    })
    known = json.loads(_call(bot_mcp, "get_altdata"))
    unknown = json.loads(_call(bot_mcp, "get_altdata", "ZZZZ"))
    assert known["flow"]["signal_score"] == 77 and known["latent_graph"]["themes"] == ["AI power"]
    assert known["read_status"] == "partial" and known["failed_sources"] == ["altdata_graph"]
    assert unknown["latent_graph"] is None and unknown["read_status"] == "partial"


@pytest.mark.parametrize("field,value", [
    ("themes", False), ("themes", 0), ("themes", ""), ("themes", {}),
    ("top_holder", False), ("top_holder", 0), ("top_holder", ""), ("top_holder", []),
])
def test_malformed_falsy_graph_fields_preserve_healthy_siblings(
    bot_mcp, monkeypatch, tmp_path, field, value,
):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    row = {"ticker": "AAPL", "themes": [{"en": "AI"}], "top_holder": {"owner": "Known"}}
    row[field] = value
    _write_json(vendor / "site" / "altdata" / "latent.json", {"watch": [row]})
    payload = json.loads(_call(bot_mcp, "get_altdata"))
    assert payload["read_status"] == "partial" and payload["failed_sources"] == ["altdata_graph"]
    if field == "themes":
        assert payload["latent_graph"]["themes"] == [] and payload["latent_graph"]["top_holder"] == "Known"
    else:
        assert payload["latent_graph"]["themes"] == ["AI"] and payload["latent_graph"]["top_holder"] is None


@pytest.mark.parametrize("kind", ["missing", "null", "empty"])
def test_optional_graph_fields_keep_healthy_empty_semantics(bot_mcp, monkeypatch, tmp_path, kind):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    row = {"ticker": "AAPL"}
    if kind == "null":
        row.update({"themes": None, "top_holder": None})
    elif kind == "empty":
        row.update({"themes": [], "top_holder": {}})
    _write_json(vendor / "site" / "altdata" / "latent.json", {"watch": [row]})
    payload = json.loads(_call(bot_mcp, "get_altdata"))
    assert payload["latent_graph"]["themes"] == [] and payload["latent_graph"]["top_holder"] is None
    assert "read_status" not in payload


def test_bad_theme_row_does_not_discard_valid_theme(bot_mcp, monkeypatch, tmp_path):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    _write_json(vendor / "site" / "altdata" / "latent.json", {
        "watch": [{"ticker": "AAPL", "themes": ["bad", {"en": "AI"}, None]}],
    })
    payload = json.loads(_call(bot_mcp, "get_altdata"))
    assert payload["latent_graph"]["themes"] == ["AI"]
    assert payload["read_status"] == "partial" and payload["failed_sources"] == ["altdata_graph"]


@pytest.mark.parametrize("bad", [42, [], False])
def test_mismatch_preserves_other_matching_identifier(bot_mcp, monkeypatch, tmp_path, bad):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    _write_json(vendor / "site" / "altdata" / "latent.json", {
        "mismatches": [{"entity_ticker": "AAPL", "repointed_ticker": bad, "note": "known side"}],
    })
    payload = json.loads(_call(bot_mcp, "get_altdata"))
    assert payload["label_mismatch"]["entity_ticker"] == "AAPL"
    assert payload["read_status"] == "partial" and payload["failed_sources"] == ["altdata_graph"]


def test_identifierless_mismatch_keeps_census_incomplete(bot_mcp, monkeypatch, tmp_path):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    _write_json(vendor / "site" / "altdata" / "latent.json", {
        "mismatches": [{}, {"entity_ticker": "AAPL"}],
    })
    payload = json.loads(_call(bot_mcp, "get_altdata"))
    assert payload["label_mismatch"]["entity_ticker"] == "AAPL"
    assert payload["read_status"] == "partial"


@pytest.mark.parametrize("ticker", [42, [], None])
def test_bad_signal_identifier_preserves_news_and_known_alt(bot_mcp, monkeypatch, tmp_path, ticker):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    _write_json(vendor / "site" / "news" / "by_ticker.json", _feed(asof="news-clock"))
    _write_json(vendor / "site" / "altdata" / "mastermind.json", {
        "asof": "alt-clock", "signals": [{"ticker": ticker}, {"ticker": "AAPL", "score": 77}],
    })
    payload = json.loads(_call(bot_mcp, "get_intelligence"))
    assert payload["news"]["headline_count"] == 4 and payload["alt"]["score"] == 77
    assert payload["read_status"] == "partial" and payload["failed_sources"] == ["altdata"]
    assert payload["freshness"]["asof"] == "news-clock"
    assert payload["alt_freshness"]["asof"] == "alt-clock"


@pytest.mark.parametrize("kind", ["missing", "valid_absent", "failed", "invalid_shape"])
def test_fallback_labels_distinguish_absent_failed_and_missing_ticker_sources(
    bot_mcp, monkeypatch, tmp_path, kind,
):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    unified = vendor / "site" / "intelligence" / "by_ticker.json"
    if kind == "valid_absent":
        _write_json(unified, _feed("MSFT", asof="unified-clock"))
    elif kind == "failed":
        _break(unified)
    elif kind == "invalid_shape":
        _write_json(unified, {"asof": "unusable-primary", "tickers": []})
    _write_json(vendor / "data" / "news" / "by_ticker.json", _feed(asof="news-mirror-clock"))
    _write_json(vendor / "site" / "altdata" / "mastermind.json", {
        "asof": "alt-clock", "signals": [{"ticker": "AAPL", "score": 77}],
    })
    payload = json.loads(_call(bot_mcp, "get_intelligence"))
    assert payload["news"]["headline_count"] == 4 and payload["alt"]["score"] == 77
    assert payload["freshness"]["source_file"] == "data/news/by_ticker.json"
    assert payload["freshness"]["asof"] == "news-mirror-clock"
    assert payload["alt_freshness"]["source_file"] == "site/altdata/mastermind.json"
    assert payload["alt_freshness"]["asof"] == "alt-clock"
    assert payload["fallback"] == "standalone_news_and_altdata_feeds"
    assert payload["evidence_grade"] == "legacy_fallback"
    if kind in ("failed", "invalid_shape"):
        assert payload["missing_reason"] == "unified_intelligence_incomplete"
        assert payload["read_status"] == "partial" and payload["failed_sources"] == ["unified_intelligence"]
    else:
        assert payload["missing_reason"] == (
            "ticker_absent_in_vendored_file" if kind == "valid_absent" else "unified_artifact_absent"
        )
        assert "read_status" not in payload


@pytest.mark.parametrize("record", [{}, None])
def test_present_empty_record_is_valid_but_null_record_is_unknown(bot_mcp, monkeypatch, tmp_path, record):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    _write_json(vendor / "site" / "news" / "by_ticker.json", {"tickers": {"AAPL": record}})
    payload = json.loads(_call(bot_mcp, "get_news"))
    if record is None:
        assert payload["read_status"] == "unavailable" and payload["news"] is None
    else:
        assert payload["news"] == {} and "read_status" not in payload


@pytest.mark.parametrize("ticker", ["BRK.B", "BTC/USD"])
def test_feed_identifiers_keep_existing_lookup_without_filename_constraints(bot_mcp, monkeypatch, tmp_path, ticker):
    vendor = _vendor(bot_mcp, monkeypatch, tmp_path)
    _write_json(vendor / "site" / "news" / "by_ticker.json", _feed(ticker))
    payload = json.loads(_call(bot_mcp, "get_news", ticker.lower()))
    assert payload["ticker"] == ticker and payload["news"]["headline_count"] == 4
    assert "read_status" not in payload
