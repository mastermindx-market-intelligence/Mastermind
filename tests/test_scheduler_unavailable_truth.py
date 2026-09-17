"""Scheduler health outages stay distinct from a successful empty health read."""
from __future__ import annotations

import json
from pathlib import Path


def _body(resp):
    return json.loads(resp.body)


def test_scheduler_successful_empty_read_remains_available(monkeypatch):
    from app import web
    import app.scheduler as scheduler

    monkeypatch.setattr(scheduler, "scheduler_health", lambda: [])
    payload = _body(web.api_scheduler())
    assert payload == {"scheduler_status": "available", "jobs": []}


def test_scheduler_failure_is_unavailable_not_empty_and_secret_safe(monkeypatch):
    from app import web
    import app.scheduler as scheduler

    monkeypatch.setattr(
        scheduler,
        "scheduler_health",
        lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/run_events.jsonl token=bad")),
    )
    response = web.api_scheduler()
    payload = _body(response)
    assert payload == {
        "scheduler_status": "unavailable",
        "jobs": None,
        "error": "scheduler_health_unavailable",
    }
    raw = response.body.decode()
    assert "secret" not in raw and "/Users/private" not in raw and "token=bad" not in raw


def test_scheduler_ui_consumes_unavailable_before_no_jobs():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()
    start = html.index("function renderDeskScheduler()")
    end = html.index("function renderDeskStrategist()", start)
    block = html[start:end]

    assert "d.scheduler_status === 'unavailable'" in block
    assert "d.status === 'unavailable'" in block
    assert block.index("d.scheduler_status === 'unavailable'") < block.index("!(d.jobs || []).length")
    assert "Scheduler health unavailable" in block
    assert "No scheduler jobs reported" in block
