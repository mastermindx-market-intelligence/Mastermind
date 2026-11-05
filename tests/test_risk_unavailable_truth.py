"""Risk-report unavailability must not look like a successful zero-breach assessment."""
from __future__ import annotations

import json


def test_active_risk_failure_is_secret_safe_and_evidence_unknown(monkeypatch):
    from app import web
    from portfolio import safety

    monkeypatch.setattr(
        safety,
        "load_safety",
        lambda _pid: (_ for _ in ()).throw(RuntimeError("secret /Users/private/risk-cache")),
    )

    payload = json.loads(web.api_risk("autonomous").body)

    assert payload["error"] == "risk_unavailable"
    assert payload["report_status"] == "unavailable"
    assert payload["safety_score"] is None
    assert payload["metrics"] is None
    assert payload["subscores"] is None
    assert payload["breaches"] is None
    assert payload["caveats"] is None
    assert payload["note"] == "Safety report unavailable."
    encoded = json.dumps(payload)
    assert "secret" not in encoded
    assert "/Users/private" not in encoded


def test_missing_archived_snapshot_is_explicitly_unavailable(tmp_path, monkeypatch):
    from app import web
    from portfolio import registry, safety

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    monkeypatch.setattr(
        safety,
        "compute_safety",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not compute")),
    )
    monkeypatch.setattr(
        safety,
        "persist",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not persist")),
    )

    payload = json.loads(web.api_risk("etf", recompute=True).body)

    assert payload["archived"] is True
    assert payload["snapshot_only"] is True
    assert payload["report_status"] == "unavailable"
    assert payload["error"] == "archived_risk_unavailable"
    assert payload["metrics"] is None
    assert payload["subscores"] is None
    assert payload["breaches"] is None
    assert payload["caveats"] is None
