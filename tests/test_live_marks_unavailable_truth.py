"""Truthful degradation for live-mark preview failures."""
from __future__ import annotations

import json
from pathlib import Path


def _closed_session() -> dict:
    return {
        "venue": "US", "market": "NYSE", "timezone": "America/New_York",
        "is_open": False, "state": "post_close", "trading_day": True,
        "holiday": False, "as_of": "2026-09-16T17:00:00-04:00",
        "next_open": "2026-09-17T09:30:00-04:00", "poll_after_seconds": 59405,
    }


def test_live_marks_failure_is_unavailable_not_empty_and_secret_safe(monkeypatch) -> None:
    from app import web
    from portfolio import market_sessions

    monkeypatch.setattr(market_sessions, "status_for_portfolio", lambda _pid: _closed_session())
    monkeypatch.setattr(
        web,
        "_account_tickers",
        lambda _pid: (_ for _ in ()).throw(RuntimeError("secret live-feed detail")),
    )

    response = web.api_live_marks("autonomous")
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert payload["error"] == "live_marks_unavailable"
    assert payload["positions"] == []
    assert payload["performance"] == {}
    assert payload["pricing"] == {
        "priced_positions": None,
        "total_positions": None,
        "complete": False,
    }
    assert "secret live-feed detail" not in response.body.decode("utf-8")


def test_live_marks_ui_preserves_snapshot_and_names_unavailable_state() -> None:
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()

    assert "Live marks unavailable" in html
    assert "live_marks_unavailable" in html
    assert "if (data.error)" in html
    assert "keeping the last portfolio snapshot" in html
