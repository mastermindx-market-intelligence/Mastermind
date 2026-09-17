"""Calibration/outcome-ledger failures must remain unavailable, never 'still building'."""
from __future__ import annotations

import json
from pathlib import Path


def test_outcome_ledger_failure_is_unknown_and_secret_safe(monkeypatch):
    from app import web
    from brain import outcome_ledger

    monkeypatch.setattr(
        outcome_ledger,
        "summary",
        lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/outcomes.jsonl")),
    )

    payload = json.loads(web.api_outcome_ledger().body)

    assert payload["ledger_status"] == "unavailable"
    assert payload["error"] == "outcome_ledger_unavailable"
    assert payload["summary"] is None
    assert payload["reliability_curve"] is None
    assert payload["lens_edge"] is None
    assert payload["lens_weights"] is None
    assert payload["records"] is None
    assert "secret" not in json.dumps(payload).lower()
    assert "/Users/private" not in json.dumps(payload)


def test_calibration_ui_distinguishes_unavailable_from_building():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()

    ensure_start = html.index("function _ensureCalibration()")
    ensure_end = html.index("// ── CALIBRATION", ensure_start)
    ensure = html[ensure_start:ensure_end]
    assert "_calibrationUnavailable()" in ensure
    assert "outcome_ledger_unavailable" in ensure

    render_start = html.index("function renderCalibrationPage()")
    render_end = html.index("// ── DESK page", render_start)
    render = html[render_start:render_end]
    assert "ledger_status === 'unavailable'" in render
    assert "Calibration data unavailable" in render
    assert render.index("ledger_status === 'unavailable'") < render.index("var building =")
