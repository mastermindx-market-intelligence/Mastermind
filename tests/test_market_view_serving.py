"""Persisted Market View must lose eligibility as time passes, without new evidence."""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import market_view as MV

NOW = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
FRESH = "2026-10-19"
OLD = "2026-08-07"


def _plane(direction="risk_on", *, asof=FRESH, status="validated", stale=False):
    return {
        "reading": "Published observation",
        "direction": direction,
        "magnitude": 0.2,
        "freshness": {"asof": asof, "age_sessions": 1, "stale": stale},
        "confidence": 0.8,
        "status": status,
        "source_contract": "fixture/observation",
        "raw": {"present": True, "artifact_present": True, "signal_active": True},
    }


def _published(planes=None, *, asof=FRESH):
    supplied = planes if planes is not None else {
        "risk_radar": _plane(),
        "mtf_signals": _plane(),
        "cycles": _plane(),
    }
    rows = {name: MV._absent_record("fixture/missing") for name in MV.PLANE_ORDER}
    rows.update(supplied)
    tilt = MV._net_posture_tilt(rows)
    label = MV._label_vs_planes("risk_on", tilt, rows)
    return {
        "schema_version": "market_view.v1", "region": "us", "asof": asof,
        "built_at": "2026-10-19T23:00:00+00:00", "seq": 9,
        "planes": rows, "net_posture_tilt": tilt, "coverage": 1.0,
        "coherence": MV._coherence(rows), "disagreements": MV._disagreements(rows),
        "label_vs_planes": label, "posture_floor_defense": label["conflict"],
        "assembly": {"degraded": False, "degrade_reasons": []},
        "budget_ref": {"historical_fixture": True},
        "brief": MV._brief(rows, label, tilt, None),
    }


@pytest.fixture(autouse=True)
def _doctrine(monkeypatch):
    monkeypatch.setattr(MV, "_cfg", lambda: {"stale_after_trading_days": 5})


def _project(published, now=NOW):
    return MV.serving_view(published, now=now)


def test_old_confirmed_artifact_expires_without_mutating_publication():
    published = _published({name: _plane(asof=OLD) for name in MV._VALIDATED_PLANES},
                           asof=OLD)
    original = copy.deepcopy(published)
    served = _project(published)
    assert served["planes"]["risk_radar"]["freshness"]["age_sessions"] > 40
    assert served["planes"]["risk_radar"]["freshness"]["stale"] is True
    assert served["planes"]["risk_radar"]["status"] == "advisory"
    assert served["net_posture_tilt"]["direction"] is None
    assert served["net_posture_tilt"]["contributors"] == []
    assert served["label_vs_planes"]["confirmed"] is False
    assert served["coherence"] is None
    assert served["assembly"]["fresh"] == 0
    assert served["assembly"]["validated"] == 0
    assert served["serving_freshness"]["checked_at"] == NOW.isoformat()
    assert published == original
    for key in ("asof", "built_at", "seq", "budget_ref"):
        assert served[key] == original[key]
    assert "confirms the regime label" not in served["brief"]["what_changed"]


@pytest.mark.parametrize("directions", [
    ("risk_off", "risk_on", None),
    ("risk_off", "risk_off", "risk_on"),
])
def test_expiring_dissent_cannot_manufacture_risk_on(directions):
    rows = {}
    for name, direction in zip(("risk_radar", "mtf_signals", "cycles"), directions):
        if direction is not None:
            rows[name] = _plane(direction, asof=OLD if direction == "risk_off" else FRESH)
    published = _published(rows)
    assert published["net_posture_tilt"]["direction"] in ("neutral", "risk_off")
    served = _project(published)
    assert served["net_posture_tilt"]["direction"] is None
    assert served["net_posture_tilt"]["n_validated"] == 0
    assert served["assembly"]["eligible_validated"] == 1
    assert served["assembly"]["aggregate_available"] is False
    assert served["coherence"] is None
    assert served["disagreements"] == published["disagreements"]
    assert served["serving_freshness"]["disagreements_scope"] == "as_published"


def test_intact_published_inference_is_preserved_exactly():
    published = _published()
    served = _project(published)
    assert served["net_posture_tilt"] == published["net_posture_tilt"]
    assert served["coherence"] == published["coherence"]
    assert served["label_vs_planes"] == published["label_vs_planes"]
    assert served["assembly"]["eligible_validated"] == 3
    assert served["assembly"]["aggregate_available"] is True


def test_nondirectional_advisory_expiry_does_not_erase_intact_consensus():
    published = _published()
    published["planes"]["group_flow"] = _plane(None, asof=OLD, status="advisory")
    served = _project(published)
    assert served["net_posture_tilt"] == published["net_posture_tilt"]
    assert served["coherence"] == published["coherence"]
    assert served["planes"]["group_flow"]["freshness"]["stale"] is True


def test_expired_label_cannot_confirm_current_constituents():
    published = _published(asof=OLD)
    served = _project(published)
    assert served["net_posture_tilt"] == published["net_posture_tilt"]
    assert served["label_vs_planes"]["relationship"] == "unavailable"
    assert served["label_vs_planes"]["label_direction"] is None
    assert served["serving_freshness"]["published_label_direction"] == "risk_on"


@pytest.mark.parametrize("bad_date", [None, "invalid", "2026-10-21", "2026-10-19T23:00:00Z"])
def test_unknown_invalid_future_or_non_date_input_cannot_sign(bad_date):
    published = _published({"risk_radar": _plane(asof=bad_date)})
    served = _project(published)
    assert served["planes"]["risk_radar"]["freshness"]["stale"] is True
    assert served["net_posture_tilt"]["direction"] is None


def test_future_date_does_not_become_validated_when_clock_catches_up():
    published = _published({"risk_radar": _plane(asof="2026-10-21",
                                                status="advisory", stale=True)})
    later = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
    served = _project(published, later)
    assert served["planes"]["risk_radar"]["status"] == "advisory"
    assert served["net_posture_tilt"]["direction"] is None


def test_advisory_only_plane_cannot_claim_validation():
    published = _published({"neural_web": _plane(status="validated")})
    served = _project(published)
    assert served["planes"]["neural_web"]["status"] == "advisory"
    assert served["net_posture_tilt"]["contributors"] == []


@pytest.mark.parametrize("corruption", ["missing", "wrong_member", "wrong_tilt", "wrong_count"])
def test_unverifiable_published_membership_is_not_reconstructed(corruption):
    published = _published()
    tilt = published["net_posture_tilt"]
    if corruption == "missing":
        tilt.pop("contributors")
    elif corruption == "wrong_member":
        tilt["contributors"] = ["risk_radar"]
    elif corruption == "wrong_tilt":
        tilt["tilt"] = -1.0
    else:
        tilt["n_validated"] = 99
    served = _project(published)
    assert served["net_posture_tilt"]["direction"] is None
    assert served["serving_freshness"]["consensus_reason"] == "published_consensus_inconsistent"


def test_expired_conflict_is_not_reported_as_recovery():
    published = _published({"risk_radar": _plane("risk_off", asof=OLD)})
    assert published["label_vs_planes"]["conflict"] is True
    served = _project(published)
    brief = " ".join(served["brief"].values())
    for forbidden in ("OPENED", "CLOSED", "RESOLVED", "risk has cleared"):
        assert forbidden not in brief
    assert "does not establish recovery" in brief
    assert served["serving_freshness"]["published_posture_floor_defense"] is True


def test_serving_never_calls_builder_or_live_inputs(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("A serving projection must not execute a producer or live-input reader")
    for name in ("build", "view", "_budget_ref", "_read_prev_latest"):
        monkeypatch.setattr(MV, name, forbidden)
    monkeypatch.setattr(MV._rf, "_read_raw", forbidden)
    assert _project(_published())["seq"] == 9


def test_actual_route_reassesses_even_with_response_cache_enabled(tmp_path, monkeypatch):
    from app import response_cache, web
    path = tmp_path / "market_view" / "latest.json"
    path.parent.mkdir()
    published = _published()
    path.write_text(json.dumps(published))
    original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(web, "_data", lambda: tmp_path)
    monkeypatch.setenv("MASTERMIND_RESP_CACHE_TTL", "86400")
    clock = [NOW]
    actual = MV.serving_view
    monkeypatch.setattr(MV, "serving_view", lambda value: actual(value, now=clock[0]))
    app = FastAPI()
    app.include_router(web.router)
    response_cache.clear()
    response_cache.install(app)
    client = TestClient(app)
    first = client.get("/api/market_view")
    assert first.status_code == 200
    assert first.json()["label_vs_planes"]["confirmed"] is True
    clock[0] = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    second = client.get("/api/market_view")
    assert second.status_code == 200
    assert second.json()["net_posture_tilt"]["direction"] is None
    assert second.json()["label_vs_planes"]["confirmed"] is False
    assert second.headers.get("x-mm-cache") is None
    assert "no-store" in second.headers["cache-control"]
    assert len(response_cache._CACHE) == 0
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original_hash
    assert second.json()["built_at"] == published["built_at"]
    assert second.json()["seq"] == 9



def test_rotation_pairs_are_captured_with_the_published_source(tmp_path, monkeypatch):
    tensor_path = tmp_path / "rotation_tensor.json"
    pairs = [{"pair": "XLU/XLK", "velocity": 1.2}]
    tensor_path.write_text(json.dumps({
        "as_of": FRESH, "asof_by_plane": {"yahoo": FRESH},
        "headline_episode": {"direction": "defensive"},
        "rs_velocity": {"top_pairs": pairs},
    }))
    monkeypatch.setattr(MV, "_ROTATION_TENSOR_PATH", tensor_path)
    published_plane = MV._adapt_rotation_tensor()
    tensor_path.write_text(json.dumps({
        "as_of": "2026-10-20", "rs_velocity": {"top_pairs": [{"pair": "NEW/INPUT"}]},
    }))
    served = _project(_published({"rotation_tensor": published_plane}))
    assert served["planes"]["rotation_tensor"]["raw"]["top_pairs"] == pairs
    assert served["planes"]["rotation_tensor"]["freshness"]["asof"] == FRESH
    assert served["planes"]["rotation_tensor"]["raw"]["asof_by_plane"] == {"yahoo": FRESH}


@pytest.mark.parametrize("embedded", [False, True])
def test_route_never_splices_current_rotation_into_a_publication(tmp_path, monkeypatch, embedded):
    from app import web
    path = tmp_path / "market_view" / "latest.json"
    path.parent.mkdir()
    row = _plane("risk_off", asof=OLD, status="advisory")
    pairs = [{"pair": "OLD/PAIR"}]
    if embedded:
        row["raw"]["top_pairs"] = pairs
    published = _published({"rotation_tensor": row}, asof=OLD)
    path.write_text(json.dumps(published))
    (path.parent / "rotation_tensor.json").write_text(json.dumps({
        "as_of": FRESH, "rs_velocity": {"top_pairs": [{"pair": "NEW/PAIR"}]},
    }))
    monkeypatch.setattr(web, "_data", lambda: tmp_path)
    response = json.loads(web.api_market_view().body)
    raw = response["planes"]["rotation_tensor"]["raw"]
    assert raw.get("top_pairs") == (pairs if embedded else None)
    assert response["planes"]["rotation_tensor"]["freshness"]["asof"] == OLD



@pytest.mark.parametrize("case", ["fresh", "expired", "mixed"])
def test_page_renderer_keeps_expired_evidence_unavailable(case):
    # Execute the shipped renderer with synthetic API data. This verifies output
    # semantics independently of a browser login; it is not a visual browser test.
    import re
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to exercise the actual page renderer")
    if case == "expired":
        published = _published({n: _plane(asof=OLD) for n in MV._VALIDATED_PLANES},
                               asof=OLD)
    elif case == "mixed":
        published = _published({"risk_radar": _plane("risk_off", asof=OLD),
                                "mtf_signals": _plane("risk_on")})
    else:
        published = _published()
    served = _project(published)
    html = (Path(__file__).resolve().parents[1] / "app/static/market_view.html").read_text()
    script = re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)[-1]
    harness = """
const vm = require('node:vm');
const fs = require('node:fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const nodes = {'mv-root': {innerHTML: ''}, 'mv-sub': {textContent: ''}};
vm.runInNewContext(input.script, {
  document: {getElementById: id => nodes[id]},
  fetch: () => Promise.resolve({ok: true, json: () => Promise.resolve(input.view)})
});
setImmediate(() => process.stdout.write(JSON.stringify(nodes)));
"""
    result = subprocess.run([node, "-e", harness],
                            input=json.dumps({"script": script, "view": served}),
                            text=True, capture_output=True, check=True, timeout=10)
    rendered = json.loads(result.stdout)
    body = rendered["mv-root"]["innerHTML"]
    subtitle = rendered["mv-sub"]["textContent"]
    assert published["built_at"] in subtitle
    assert published["asof"] in subtitle
    assert "seq 9" in subtitle
    assert "freshness checked " + NOW.isoformat() in subtitle
    if case == "fresh":
        assert "LABEL vs PLANES — CONFIRMED" in body
        assert "CURRENT CONFIRMATION UNAVAILABLE" not in body
    else:
        assert "CURRENT CONFIRMATION UNAVAILABLE" in body
        assert "LABEL vs PLANES — CONFIRMED" not in body
        assert "Contributors: none" in body
        assert "does not establish recovery" in body
        assert '<span class="pill none">—</span> <span class="num">—</span>' in body
        assert "stale</span>" in body
    if case == "mixed":
        assert 'Eligible planes:</span> <span class="v"><span class="num">1</span>' in body



def test_expiry_preserves_historical_defensive_floor_without_current_authority():
    published = _published({"risk_radar": _plane("risk_off", asof=OLD)})
    served = _project(published)
    assert served["posture_floor_defense"] is True
    assert served["serving_freshness"]["posture_floor_defense_scope"] == "as_published"
    assert served["serving_freshness"]["current_posture_floor_available"] is False


@pytest.mark.parametrize("corruption", [
    "confirmed", "relationship", "conflict", "magnitude", "dissenting_planes", "missing",
])
def test_inconsistent_original_comparison_cannot_gain_confirmation(corruption):
    published = _published()
    if corruption == "missing":
        published["label_vs_planes"].pop("confirmed")
    else:
        published["label_vs_planes"][corruption] = {
            "confirmed": False, "relationship": "unconfirmed", "conflict": True,
            "magnitude": 0.0, "dissenting_planes": ["risk_radar"],
        }[corruption]
    served = _project(published)
    assert served["label_vs_planes"]["confirmed"] is False
    assert served["serving_freshness"]["current_confirmation_available"] is False
    assert served["serving_freshness"]["label_reason"] == "published_label_comparison_inconsistent"


def test_inconsistent_published_floor_is_not_asserted_as_current():
    published = _published()
    published["posture_floor_defense"] = True
    served = _project(published)
    assert served["posture_floor_defense"] is True
    assert served["serving_freshness"]["current_posture_floor_available"] is False
    assert served["serving_freshness"]["label_reason"] == "published_posture_floor_inconsistent"


@pytest.mark.parametrize("coherence", [1.0, None, float("nan"), "0.5", True])
def test_unverifiable_original_coherence_is_withheld_not_repaired(coherence):
    published = _published({"risk_radar": _plane("risk_off"),
                            "mtf_signals": _plane("risk_on")})
    assert published["coherence"] == 0.5
    published["coherence"] = coherence
    served = _project(published)
    assert served["coherence"] is None
    assert served["serving_freshness"]["coherence_reason"] == "published_coherence_inconsistent"


def test_verified_balanced_coherence_is_preserved_until_cohort_erodes():
    published = _published({"risk_radar": _plane("risk_off"),
                            "mtf_signals": _plane("risk_on")})
    assert _project(published)["coherence"] == 0.5
    published["planes"]["risk_radar"]["freshness"]["asof"] = OLD
    assert _project(published)["coherence"] is None



def test_unknown_plane_cannot_keep_a_validation_badge():
    published = _published()
    published["planes"]["unknown_future_plane"] = _plane(asof=OLD, status="validated")
    served = _project(published)
    row = served["planes"]["unknown_future_plane"]
    assert row["reading"] == "Published observation"
    assert row["status"] == "advisory"
    assert row["freshness"]["stale"] is True
    assert "unknown_future_plane" not in served["net_posture_tilt"]["contributors"]



@pytest.mark.parametrize("field", ["tilt", "n_validated"])
def test_boolean_cannot_impersonate_a_published_numeric_aggregate(field):
    published = _published({"risk_radar": _plane()})
    published["net_posture_tilt"][field] = True
    assert _project(published)["net_posture_tilt"]["direction"] is None


@pytest.mark.parametrize("field,value", [("confirmed", 1), ("conflict", 0), ("magnitude", True)])
def test_comparison_fields_require_their_declared_types(field, value):
    published = _published()
    published["label_vs_planes"][field] = value
    served = _project(published)
    assert served["label_vs_planes"]["confirmed"] is False
    assert served["serving_freshness"]["label_reason"] == "published_label_comparison_inconsistent"
