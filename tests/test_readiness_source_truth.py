from __future__ import annotations

import json


def _wire(tmp_path, monkeypatch):
    from portfolio import readiness as r
    from portfolio import predictions as p
    monkeypatch.setattr(r, "_ROOT", tmp_path)
    monkeypatch.setattr(r, "_STATE", tmp_path / "data" / "shadow" / "readiness_state.json")
    monkeypatch.setattr(r, "_ALERTS", tmp_path / "data" / "shadow" / "readiness_alerts.jsonl")
    monkeypatch.setattr(p, "_load_ledger", lambda: [])
    return r, p


def test_missing_sources_remain_legitimate_not_ready(tmp_path, monkeypatch):
    r, _ = _wire(tmp_path, monkeypatch)
    payload = r.status()

    assert payload["flags"]["calibration_forge"] is False
    assert payload["flags"]["calibration_sentinel"] is False
    assert payload["flags"]["prediction_xsec"] is False
    assert payload["flags"]["shadow_forward"] is False
    assert "read_status" not in payload
    assert "failed_sources" not in payload


def test_corrupt_calibration_is_unknown_not_cold_start(tmp_path, monkeypatch):
    r, _ = _wire(tmp_path, monkeypatch)
    path = tmp_path / "data" / "brain" / "calibration.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken calibration evidence\n", encoding="utf-8")

    payload = r.status()

    assert payload["flags"]["calibration_forge"] is None
    assert payload["flags"]["calibration_sentinel"] is None
    assert payload["detail"]["calibration_forge"]["n"] is None
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["calibration"]


def test_prediction_ledger_failure_is_unknown_not_below_threshold(tmp_path, monkeypatch):
    r, p = _wire(tmp_path, monkeypatch)

    def explode():
        raise RuntimeError("secret prediction ledger failure")

    monkeypatch.setattr(p, "_load_ledger", explode)
    payload = r.status()

    assert payload["flags"]["prediction_xsec"] is None
    assert payload["detail"]["prediction_xsec"]["independent_clusters"] is None
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["prediction_xsec"]


def test_corrupt_shadow_leaderboard_is_unknown_not_zero_resolved(tmp_path, monkeypatch):
    r, _ = _wire(tmp_path, monkeypatch)
    path = tmp_path / "data" / "shadow" / "leaderboard.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[\"wrong-shape\"]", encoding="utf-8")

    payload = r.status()

    assert payload["flags"]["shadow_forward"] is None
    assert payload["detail"]["shadow_forward"]["max_resolved"] is None
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["shadow_forward"]


def test_all_readiness_sources_failed_is_typed_unavailable(tmp_path, monkeypatch):
    r, p = _wire(tmp_path, monkeypatch)
    cal = tmp_path / "data" / "brain" / "calibration.json"
    cal.parent.mkdir(parents=True, exist_ok=True)
    cal.write_text("{broken\n", encoding="utf-8")
    lb = tmp_path / "data" / "shadow" / "leaderboard.json"
    lb.parent.mkdir(parents=True, exist_ok=True)
    lb.write_text("{broken\n", encoding="utf-8")
    monkeypatch.setattr(p, "_load_ledger", lambda: (_ for _ in ()).throw(RuntimeError("no ledger")))

    payload = r.status()

    assert payload["read_status"] == "unavailable"
    assert payload["failed_sources"] == ["calibration", "prediction_xsec", "shadow_forward"]
    assert all(value is None for value in payload["flags"].values())


def test_unknown_source_cannot_mint_readiness_crossing(tmp_path, monkeypatch):
    r, _ = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(r, "status", lambda: {
        "flags": {"prediction_xsec": None, "shadow_forward": True},
        "detail": {},
        "read_status": "partial",
        "failed_sources": ["prediction_xsec"],
    })

    result = r.check_and_record("2026-09-18")

    assert result["new"] == ["shadow_forward"]
    rows = r.alerts()
    assert [row["flag"] for row in rows] == ["shadow_forward"]
