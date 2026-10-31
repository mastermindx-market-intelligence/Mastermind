"""Tests for the bot's MCP tool surface — the read + write-back armament for Claude.

These exercise the tools DIRECTLY (no Claude auth needed), proving the armament works:
Claude's reads return real dashboard data and its actions write to the app's review queue.
"""
import asyncio
import json
from pathlib import Path

import bot  # noqa: F401
import pytest

from brain import bot_mcp, cli_bridge

_ROOT = Path(__file__).resolve().parent.parent


def _text(result: dict) -> str:
    return result["content"][0]["text"]


def test_read_tools_return_real_data():
    reg = json.loads(_text(asyncio.run(bot_mcp.get_regime.handler({}))))
    if reg.get("quad") is None:
        pytest.skip("live vendor/macro regime data is unavailable in this worktree")
    assert reg["quad"] in {"Q1", "Q2", "Q3", "Q4"}          # live regime
    themes = json.loads(_text(asyncio.run(bot_mcp.get_themes.handler({"region": "us"}))))
    assert isinstance(themes["themes"], list) and themes["themes"]


def test_read_signal_is_allowlisted():
    denied = _text(asyncio.run(bot_mcp.read_signal.handler({"path": "/etc/passwd"})))
    assert "DENIED" in denied


def test_action_tools_write_to_review_queue(tmp_path, monkeypatch):
    # isolate writes to a temp dir — the action handlers persist real files, and
    # without this the suite would spam stub notes/proposals into the live data feed.
    monkeypatch.setattr(bot_mcp, "_ROOT", tmp_path)
    monkeypatch.setattr(bot_mcp, "_RESEARCH", tmp_path / "data" / "research")
    monkeypatch.setattr(bot_mcp, "_PROPOSALS", tmp_path / "data" / "brain" / "proposals.jsonl")

    note = _text(asyncio.run(bot_mcp.save_research_note.handler(
        {"title": "AI power bottleneck", "body": "Compute is migrating to electricity.",
         "tickers": ["NVDA", "VST"]})))
    assert "research note" in note and (tmp_path / "data" / "research" / "notes").exists()

    prop = _text(asyncio.run(bot_mcp.propose_thesis.handler(
        {"subject": "VST", "lean": "add", "conviction": "medium",
         "thesis": "Power demand from AI data centers", "horizon_d": 60})))
    assert "review queue" in prop and "NOT executed" in prop
    rows = (tmp_path / "data" / "brain" / "proposals.jsonl").read_text().strip().splitlines()
    assert json.loads(rows[-1])["subject"] == "VST"


def test_server_and_allowlist_build():
    srv = bot_mcp.build_server()
    assert srv is not None
    allowed = bot_mcp.armed_allowed_tools()
    assert "mcp__bot__get_regime" in allowed and "WebSearch" in allowed
    assert "mcp__bot__propose_thesis" in allowed


def test_json_transport_compaction_remains_valid_json():
    result = bot_mcp._json(
        {
            "rows": [
                {"rank": rank, "detail": "x" * 1_000}
                for rank in range(100)
            ],
            "status": "ok",
        }
    )
    text = _text(result)
    parsed = json.loads(text)

    assert len(text) <= 8_000
    assert parsed["status"] == "ok"
    assert parsed["_transport_truncated"] is True
    assert parsed["rows"]


def test_subscription_env_strips_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    env = cli_bridge._subscription_env()
    assert "ANTHROPIC_API_KEY" not in env                   # subscription, not metered API


def test_intake_tools_registered_and_callable():
    # the Phase-6 intake / transmission tools must be armed
    allowed = bot_mcp.armed_allowed_tools()
    for name in ("get_daily_briefing", "get_intake_candidates", "get_ticker_package"):
        assert f"mcp__bot__{name}" in allowed

    # get_daily_briefing — macro frame + ranked queue (composes live from the intake funnel
    # when briefing.json isn't vendored yet; must never error)
    brief = json.loads(_text(asyncio.run(bot_mcp.get_daily_briefing.handler({"top": 5}))))
    assert "macro_context" in brief
    assert "priority_queue" in brief and isinstance(brief["priority_queue"], list)

    # get_intake_candidates — unified queue with provenance; tiers split on request
    cand = json.loads(_text(asyncio.run(bot_mcp.get_intake_candidates.handler({"limit": 8, "tiers": True}))))
    assert "candidates" in cand and isinstance(cand["candidates"], list)
    assert "salience" in cand and {"act", "watch", "divergent"} <= set(cand["salience"])
    for c in cand["candidates"]:
        assert "ticker" in c and "score" in c and "sources" in c    # provenance present


def test_ticker_package_degrades_cleanly():
    # a name with no dashboard coverage degrades to a plain message, never raises
    out = _text(asyncio.run(bot_mcp.get_ticker_package.handler({"ticker": "ZZZZ"})))
    assert "ZZZZ" in out


def test_intel_hub_tool(tmp_path, monkeypatch):
    # armed + degrades cleanly when hub.json absent
    assert "mcp__bot__get_intel_hub" in bot_mcp.armed_allowed_tools()
    monkeypatch.setattr(bot_mcp, "_V", tmp_path / "novendor")
    assert "not built yet" in _text(asyncio.run(bot_mcp.get_intel_hub.handler({})))

    # with a hub.json present: command pull (no ticker) + single-dossier pull (ticker)
    hub = {"as_of": "2026-06-21", "macro_context": {"regime": "Goldilocks"},
           "desks": {"policy": {"live": True}}, "counts": {"theme_wide": 3},
           "n_actionable": 2, "divergence_alerts": {"early_edge": [], "crowded_top": []},
           "sector_heat": [{"etf": "XLK", "mean_conviction": 31.6}],
           "how_to_use": "read macro first",
           "command": [{"ticker": "NVDA", "name": "Nvidia", "composite_conviction": 100,
                        "lean": 1, "n_confirm": 5, "flags": ["confirmed_trend", "theme_wide"],
                        "read": "5 desks agree", "peers": ["DELL", "MSFT"], "falsifier": None}]}
    site = tmp_path / "novendor" / "site" / "intel_hub"
    site.mkdir(parents=True)
    (site / "hub.json").write_text(json.dumps(hub))

    full = json.loads(_text(asyncio.run(bot_mcp.get_intel_hub.handler({"top": 5}))))
    assert full["macro_context"]["regime"] == "Goldilocks"
    assert full["command"][0]["ticker"] == "NVDA" and "theme_wide" in full["command"][0]["flags"]
    assert "sector_heat" in full and "counts" in full

    one = json.loads(_text(asyncio.run(bot_mcp.get_intel_hub.handler({"ticker": "nvda"}))))
    assert one["ticker"] == "NVDA" and one["composite_conviction"] == 100
    assert "ZZZZ not in" in _text(asyncio.run(bot_mcp.get_intel_hub.handler({"ticker": "ZZZZ"})))


# --- D2 boundary freshness (news estate 2026-10-31) -------------------------------------------
def _write_vendored(root, rel, payload):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload))


_NEWS_REC = {"n_recent": 3, "sentiment_lean": "pos", "n_pos": 2, "n_neg": 0,
             "baskets": ["ai"], "sectors": ["tech"], "is_mag7": True,
             "top": [{"title": "t", "source": "Reuters", "url": "u", "summary": "s",
                      "sentiment": "pos", "date": "2026-10-30",
                      "item_id": "massive:reuters.com:abc123",
                      "published_utc": "2026-10-30T14:05:00+00:00"}]}


def test_get_news_carries_freshness_and_evidence_grade(tmp_path, monkeypatch):
    """T5: a found ticker carries the vendored file's clocks; existing keys stay unchanged."""
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    _write_vendored(tmp_path, "site/news/by_ticker.json", {
        "schema": "news_flow.v1", "is_context_only": True, "asof": "2026-10-31",
        "source_asof": "2026-10-30T22:00:00+00:00", "source_asof_basis": "financial_news.fetched_at",
        "retained_from_previous_build": True, "retained_reason": "candidate_darker_than_existing",
        "tickers": {"NVDA": _NEWS_REC}})
    out = json.loads(_text(asyncio.run(bot_mcp.get_news.handler({"ticker": "nvda"}))))
    assert {"ticker", "news", "note"} <= set(out)
    assert out["ticker"] == "NVDA" and out["news"]["n_recent"] == 3
    assert out["evidence_grade"] == "vendored_snapshot"
    assert out["freshness"] == {
        "asof": "2026-10-31", "source_asof": "2026-10-30T22:00:00+00:00",
        "retained_from_previous_build": True, "generated_utc": None,
        "basis": "vendored_macro_file", "source_file": "site/news/by_ticker.json"}
    assert "missing_reason" not in out and "fallback" not in out
    # a pre-D2 producer file (no source clock) reports null, never an invented clock
    _write_vendored(tmp_path, "site/news/by_ticker.json", {
        "schema": "news_flow.v1", "asof": "2026-10-29", "tickers": {"NVDA": _NEWS_REC}})
    old = json.loads(_text(asyncio.run(bot_mcp.get_news.handler({"ticker": "NVDA"}))))
    assert old["freshness"]["asof"] == "2026-10-29"
    assert old["freshness"]["source_asof"] is None
    assert old["freshness"]["retained_from_previous_build"] is None
    # an absent ticker keeps the existing plain-text contract
    assert "no news-flow signal for ZZZZ" in _text(
        asyncio.run(bot_mcp.get_news.handler({"ticker": "ZZZZ"})))


def test_get_intelligence_labels_primary_and_legacy_fallback(tmp_path, monkeypatch):
    """T6: the unified read is graded vendored_snapshot; the standalone-feed composition is
    labelled legacy_fallback with its reason and the news file's clocks."""
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    _write_vendored(tmp_path, "site/intelligence/by_ticker.json", {
        "schema": "intelligence.v1", "is_context_only": True, "as_of": "2026-10-31",
        "generated_utc": "2026-10-31T06:10:00+00:00",
        "tickers": {"NVDA": {"ticker": "NVDA", "news": _NEWS_REC, "alt": None,
                             "has_news": True, "has_alt": False}}})
    _write_vendored(tmp_path, "site/news/by_ticker.json", {
        "schema": "news_flow.v1", "asof": "2026-10-31",
        "source_asof": "2026-10-31T05:00:00+00:00", "retained_from_previous_build": False,
        "tickers": {"AMD": _NEWS_REC}})
    _write_vendored(tmp_path, "site/altdata/mastermind.json", {
        "as_of": "2026-10-30", "signals": [{"ticker": "AMD", "signal_score": 61}]})

    primary = json.loads(_text(asyncio.run(bot_mcp.get_intelligence.handler({"ticker": "NVDA"}))))
    assert primary["has_news"] is True and "note" in primary
    assert primary["evidence_grade"] == "vendored_snapshot"
    assert primary["freshness"]["asof"] == "2026-10-31"
    assert primary["freshness"]["generated_utc"] == "2026-10-31T06:10:00+00:00"
    assert primary["freshness"]["source_file"] == "site/intelligence/by_ticker.json"
    assert primary["freshness"]["basis"] == "vendored_macro_file"
    assert "missing_reason" not in primary and "fallback" not in primary

    legacy = json.loads(_text(asyncio.run(bot_mcp.get_intelligence.handler({"ticker": "AMD"}))))
    assert legacy["has_news"] is True and legacy["has_alt"] is True
    assert legacy["missing_reason"] == "ticker_absent_in_vendored_file"
    assert legacy["fallback"] == "standalone_news_and_altdata_feeds"
    assert legacy["evidence_grade"] == "legacy_fallback"
    assert legacy["freshness"]["source_file"] == "site/news/by_ticker.json"
    assert legacy["freshness"]["source_asof"] == "2026-10-31T05:00:00+00:00"
    assert legacy["freshness"]["retained_from_previous_build"] is False
    assert legacy["alt_freshness"]["asof"] == "2026-10-30"


def test_freshness_survives_transport_compaction(tmp_path, monkeypatch):
    """T6b: the 8k transport budget never drops the freshness block or the grade."""
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    wide = dict(_NEWS_REC, top=[dict(_NEWS_REC["top"][0], summary="x" * 3000) for _ in range(40)])
    _write_vendored(tmp_path, "site/news/by_ticker.json", {
        "asof": "2026-10-31", "source_asof": "2026-10-31T05:00:00+00:00",
        "tickers": {"NVDA": wide}})
    out = json.loads(_text(asyncio.run(bot_mcp.get_news.handler({"ticker": "NVDA"}))))
    assert out["_transport_truncated"] is True
    assert out["freshness"]["source_asof"] == "2026-10-31T05:00:00+00:00"
    assert out["evidence_grade"] == "vendored_snapshot"
    tiny = json.loads(_text(bot_mcp._json({"freshness": {"asof": "2026-10-31"}, "evidence_grade": "g",
                                            **{f"k{i}": {"v": "y" * 200} for i in range(400)}})))
    assert tiny["freshness"] == {"asof": "2026-10-31"} and tiny["evidence_grade"] == "g"
