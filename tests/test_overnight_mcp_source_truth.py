"""Read-only model tool cannot misrepresent historical Yahoo bars as live tape.

No provider is called; the normal existing SDK tool handler is invoked with a
fully stubbed tape. Secret-bearing exceptions must not reach model context.
"""
from __future__ import annotations

import asyncio
import json

import pytest


@pytest.fixture
def tool():
    pytest.importorskip("claude_agent_sdk")
    from brain import bot_mcp
    return bot_mcp.get_overnight_tape


def _read(tool):
    result = asyncio.run(tool.handler({}))
    return json.loads(result["content"][0]["text"])


def test_tool_description_does_not_claim_daily_bars_are_live(tool):
    description = tool.description.lower()
    assert "not a verified live overnight quote" in description
    assert "daily closes" in description
    assert "risk is unknown" in description
    assert "position for the open" not in description
    assert "what's moving right now" not in description


def test_tool_retains_uncertainty_and_original_nonlive_indicator(tool, monkeypatch):
    from data_layer import overnight as source
    source_response = {
        "as_of": "2026-10-15T02:00:00+00:00",
        "as_of_kind": "retrieved_at_not_source_observed_at",
        "live": False,
        "groups": {"us_futures": [{"ticker": "ES=F", "change_pct": -3.7}]},
        "risk": {"state": "unknown",
                 "reasons": ["no qualified overnight risk signals"]},
        "source_quality": {"classification": "EOD_NOT_LIVE",
                           "source": "yahoo_daily_history",
                           "interval": "1d",
                           "risk_qualified": False},
    }
    monkeypatch.setattr(source, "tape", lambda: source_response)
    received = _read(tool)
    assert received["live"] is False
    assert received["risk"]["state"] == "unknown"
    assert received["source_quality"]["classification"] == "EOD_NOT_LIVE"
    assert received["groups"]["us_futures"][0]["change_pct"] == -3.7


def test_model_tool_static_error_does_not_expose_secrets_or_fake_calm(tool, monkeypatch):
    from data_layer import overnight as source
    token_like = "SECRET_TEST_TOKEN_DONT_LEAK"

    def fail():
        raise RuntimeError("External service private configuration " + token_like)

    monkeypatch.setattr(source, "tape", fail)
    received = _read(tool)
    assert received["error"] == "overnight_source_unavailable"
    assert received["live"] is False
    assert received["risk"]["state"] == "unknown"
    assert received["groups"] == {}
    assert token_like not in json.dumps(received)


@pytest.mark.parametrize("book", ["autonomous", "heavyweight"])
def test_risk_governor_never_advertises_daily_closes_as_live_intraday(
    monkeypatch, book,
):
    from brain import risk_lens
    monkeypatch.setenv("MASTERMIND_RISK_GOVERNOR", "1")
    persona = risk_lens.govern_persona("BASE", book)
    assert persona.startswith("BASE")
    assert "get_overnight_tape" in persona
    assert "DAILY" in persona or "daily" in persona
    assert "not a live" in persona or "not a confirmed live" in persona
    assert "independent risk evidence" in persona.lower() or "source clocks" in persona.lower()


def test_governor_briefing_does_not_claim_unqualified_macro_evidence_live():
    from brain import risk_lens
    payload = risk_lens._format_briefing({
        "posture": "CAUTION",
        "source": "heuristic",
        "evidence": ["synthetic close-to-close only"],
    })
    assert "Risk evidence (source clocks and freshness must be verified):" in payload
    assert "Live risk tape:" not in payload
