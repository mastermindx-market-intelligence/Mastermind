"""Neither dashboard nor model-tool may publish unqualified live risk claims.

All input is synthetic; a claimed source receipt without host admission
cannot be promoted into an actionable observation or a misleading UI badge.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest

from tests.test_overnight_source_admission import synthetic


def forged_live_source():
    return synthetic(datetime.now(timezone.utc),change=-2.0)


def test_unqualified_forged_live_packet_is_downgraded_before_dashboard(monkeypatch):
    from app import web
    from data_layer import overnight
    monkeypatch.setattr(overnight,"tape",forged_live_source)
    response=web.api_overnight_tape()
    payload=json.loads(response.body)
    assert response.status_code==200
    assert payload["live"] is False
    assert payload["risk"]["state"]=="unknown"
    assert payload["source_quality"]["risk_qualified"] is False
    assert payload["groups"]=={}


def test_unqualified_forged_live_packet_is_downgraded_before_model_tool(monkeypatch):
    pytest.importorskip("claude_agent_sdk")
    from brain import bot_mcp
    from data_layer import overnight
    monkeypatch.setattr(overnight,"tape",forged_live_source)
    output=asyncio.run(bot_mcp.get_overnight_tape.handler({}))
    payload=json.loads(output["content"][0]["text"])
    assert payload["live"] is False
    assert payload["risk"]["state"]=="unknown"
    assert payload["source_quality"]["risk_qualified"] is False
    assert payload["groups"]=={}


def test_genuine_daily_historical_orientation_preserved_but_not_as_live(monkeypatch):
    from data_layer import overnight
    from app import web
    daily={
        "as_of": "2026-10-15T04:00:00+00:00",
        "as_of_kind": "retrieved_at_not_source_observed_at",
        "live": False, "n_symbols": 1,
        "groups": {"us_futures": [
            {"ticker":"ES=F","name":"S&P 500 fut","change_pct":-2.0}
        ]},
        "risk": overnight.risk_read({}),
        "source_quality": {"classification":"EOD_NOT_LIVE",
                           "source":"yahoo_daily_history",
                           "interval":"1d", "risk_qualified":False},
    }
    monkeypatch.setattr(overnight,"tape",lambda: daily)
    response=web.api_overnight_tape()
    output=json.loads(response.body)
    assert output["live"] is False
    assert output["source_quality"]["classification"]=="EOD_NOT_LIVE"
    assert output["risk"]["state"]=="unknown"
    assert output["groups"]["us_futures"][0]["change_pct"]==-2.0


def test_synthetic_host_verified_live_projection_remains_usable(monkeypatch):
    pytest.importorskip("claude_agent_sdk")
    from data_layer import overnight
    from app import web
    from brain import bot_mcp

    packet=synthetic(datetime.now(timezone.utc),change=-2.0)
    monkeypatch.setattr(overnight, "_host_live_source_admitted", lambda _: True)
    monkeypatch.setattr(overnight, "tape", lambda: packet)
    assert overnight.qualifies_live_risk(packet)
    public=overnight.public_tape(packet)
    assert public["live"] is True
    assert public["risk"]["state"] == "stressed"
    assert json.loads(web.api_overnight_tape().body)["live"] is True
    model=asyncio.run(bot_mcp.get_overnight_tape.handler({}))
    assert json.loads(model["content"][0]["text"])["risk"]["state"]=="stressed"


def test_unqualified_historical_public_projection_sanitizes_corrupt_rows():
    from data_layer import overnight

    daily={
        "as_of":"2026-10-15T04:00:00+00:00",
        "as_of_kind":"retrieved_at_not_source_observed_at",
        "live":False,
        "groups":{"us_futures":[
            {"ticker":"ES=F","name":"forged display","change_pct":-2.0,"price":5200.0},
            {"ticker":"NQ=F","change_pct":float("nan")},
            {"ticker":["not-a-ticker"],"change_pct":-2.0},
        ]},
        "risk":{"state":"stressed"},
        "source_quality":{
            "classification":"EOD_NOT_LIVE",
            "source":"yahoo_daily_history",
            "interval":"1d","risk_qualified":False,
        },
    }
    projected=overnight.public_tape(daily)
    assert projected["live"] is False
    assert projected["risk"]["state"]=="unknown"
    assert projected["groups"]["us_futures"]==[{
        "ticker":"ES=F","name":"S&P 500 fut",
        "price":5200.0,"change_pct":-2.0,
    }]
    assert projected["n_symbols"]==1
