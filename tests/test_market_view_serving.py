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
    from html.parser import HTMLParser
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
    class InlineScripts(HTMLParser):
        def __init__(self):
            super().__init__()
            self.active = False
            self.parts = []
            self.scripts = []

        def handle_starttag(self, tag, attrs):
            if tag == "script":
                self.active = not any(name == "src" for name, _ in attrs)
                self.parts = []

        def handle_data(self, data):
            if self.active:
                self.parts.append(data)

        def handle_endtag(self, tag):
            if tag == "script" and self.active:
                self.scripts.append("".join(self.parts))
                self.active = False

    parser = InlineScripts()
    parser.feed(html)
    parser.close()
    assert parser.scripts, "The shipped page has no inline renderer"
    script = parser.scripts[-1]
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


# The active reasoning consumers must not bypass the serving eligibility boundary.
def _install_publication(monkeypatch, tmp_path, published):
    from brain import decision_context as DC, pm_conviction as PM
    view_path = tmp_path / "market_view.json"
    context_path = tmp_path / "decision_context.json"
    view_path.write_text(json.dumps(published))
    monkeypatch.setattr(PM, "_MARKET_VIEW_PATH", view_path, raising=False)
    monkeypatch.setattr(DC, "_MARKET_VIEW_PATH", view_path)
    monkeypatch.setattr(DC, "_LATEST_PATH", context_path)
    return view_path, context_path


def test_shared_current_reader_withdraws_expired_confirmation(monkeypatch, tmp_path):
    from brain import pm_conviction as PM
    published = _published({n: _plane(asof=OLD) for n in MV._VALIDATED_PLANES}, asof=OLD)
    view_path, _ = _install_publication(monkeypatch, tmp_path, published)
    before = view_path.read_bytes()
    current = PM._read_market_view(now=NOW)
    enrichment = PM._market_view_enrichment(current)
    assert "CONFIRM the" not in enrichment["label_vs_planes_line"]
    assert "unavailable" in enrichment["label_vs_planes_line"]
    assert enrichment["serving_freshness"]["current_confirmation_available"] is False
    assert enrichment["publication"]["asof"] == OLD
    assert all(row["status"] == "advisory" for row in enrichment["plane_summaries"])
    assert view_path.read_bytes() == before


def test_autonomous_brief_cannot_repeat_expired_confirmation(monkeypatch, tmp_path):
    from bot import autonomous
    from brain import decision_context as DC, macro_risk, pm_conviction as PM
    published = _published({n: _plane(asof=OLD) for n in MV._VALIDATED_PLANES}, asof=OLD)
    _install_publication(monkeypatch, tmp_path, published)
    reader = PM._read_market_view
    monkeypatch.setattr(PM, "_read_market_view", lambda: reader(now=NOW))
    monkeypatch.setattr(autonomous, "_read_regime", lambda: {"quad": "Q1", "date": FRESH})
    monkeypatch.setattr(MV._rf, "frame", lambda *a, **k: {})
    monkeypatch.setattr(MV._rf, "cycles", lambda *a, **k: {})
    monkeypatch.setattr(macro_risk, "risk_state", lambda *a, **k: {})
    monkeypatch.setattr(DC, "prompt_summary", lambda *a, **k: {})
    brief = autonomous._regime_brief()
    assert "PERCEPTION LAYER" in brief
    assert "confirmation unavailable" in brief
    assert "CONFIRM the" not in brief
    assert "does not establish recovery" in brief


def test_current_mcp_retains_source_date_and_unavailability(monkeypatch, tmp_path):
    import asyncio
    from brain import bot_mcp, decision_context as DC, pm_conviction as PM
    published = _published({n: _plane(asof=OLD) for n in MV._VALIDATED_PLANES}, asof=OLD)
    _install_publication(monkeypatch, tmp_path, published)
    reader = PM._read_market_view
    monkeypatch.setattr(PM, "_read_market_view", lambda: reader(now=NOW))
    monkeypatch.setattr(bot_mcp, "_V", tmp_path)
    monkeypatch.setattr(DC, "prompt_summary", lambda *a, **k: {})
    result = asyncio.run(bot_mcp.get_regime.handler({}))
    payload = json.loads(result["content"][0]["text"])
    view = payload["market_view"]
    assert view["serving_freshness"]["current_confirmation_available"] is False
    radar = next(p for p in view["plane_summaries"] if p["name"] == "risk_radar")
    assert radar["asof"] == OLD
    assert radar["stale"] is True
    assert radar["status"] == "advisory"
    assert "CONFIRM the" not in view["label_vs_planes_line"]


def _paired_context(published):
    from brain import decision_context as DC
    return DC.assemble(
        {"date": published["asof"], "quad": "Q1", "quad_name": "Goldilocks",
         "confidence": 0.9},
        published, neural_web={}, seq=published["seq"],
        built_at=published["built_at"],
    )


def test_live_typed_summary_withdraws_expired_parallel_claims(monkeypatch, tmp_path):
    from brain import decision_context as DC
    published = _published({n: _plane(asof=OLD) for n in MV._VALIDATED_PLANES}, asof=OLD)
    view_path, context_path = _install_publication(monkeypatch, tmp_path, published)
    ctx = _paired_context(published)
    context_path.write_text(json.dumps(ctx))
    before = (view_path.read_bytes(), context_path.read_bytes())
    current = DC.prompt_summary(now=NOW)
    assert current["serving_freshness"]["current_assessment_available"] is False
    assert current["governor"]["relationship"] == "unavailable"
    assert current["governor"]["net_tilt"] is None
    assert current["hard_label"] is None
    assert current["neural_web_contexts"] is None
    assert (view_path.read_bytes(), context_path.read_bytes()) == before
    # Explicit artifact formatting remains point-in-time; historical records are not rewritten.
    historical = DC.prompt_summary(ctx)
    assert historical["governor"]["confirmed"] is True
    assert ctx["governor"]["confirmed"] is True


def test_live_typed_summary_preserves_fresh_intact_pair(monkeypatch, tmp_path):
    from brain import decision_context as DC
    published = _published()
    _, context_path = _install_publication(monkeypatch, tmp_path, published)
    ctx = _paired_context(published)
    context_path.write_text(json.dumps(ctx))
    current = DC.prompt_summary(now=NOW)
    assert current["serving_freshness"]["current_assessment_available"] is True
    assert current["governor"] == ctx["governor"]
    assert current["hard_label"] == ctx["regime"]["hard_label"]
    assert current["publication"]["seq"] == published["seq"]


@pytest.mark.parametrize("change", ["sequence", "asof", "governor", "missing_view"])
def test_typed_summary_refuses_unpaired_or_inconsistent_claims(monkeypatch, tmp_path, change):
    from brain import decision_context as DC
    published = _published()
    view_path, context_path = _install_publication(monkeypatch, tmp_path, published)
    ctx = _paired_context(published)
    if change == "sequence":
        ctx["seq"] += 1
    elif change == "asof":
        ctx["market_asof"] = "2026-10-16"
    elif change == "governor":
        ctx["governor"]["confirmed"] = False
    else:
        view_path.unlink()
    context_path.write_text(json.dumps(ctx))
    current = DC.prompt_summary(now=NOW)
    assert current["serving_freshness"]["current_assessment_available"] is False
    assert current["governor"]["relationship"] == "unavailable"
    assert current["governor"]["confirmed"] is False
    assert current["probabilistic_state"] is None


def test_typed_summary_cannot_turn_expired_dissent_into_confirmation(monkeypatch, tmp_path):
    from brain import decision_context as DC
    published = _published({
        "risk_radar": _plane("risk_off", asof=OLD),
        "mtf_signals": _plane("risk_on"),
    })
    _, context_path = _install_publication(monkeypatch, tmp_path, published)
    ctx = _paired_context(published)
    assert ctx["governor"]["relationship"] == "unconfirmed"
    context_path.write_text(json.dumps(ctx))
    current = DC.prompt_summary(now=NOW)
    assert current["governor"]["relationship"] == "unavailable"
    assert current["governor"]["confirmed"] is False
    assert current["governor"]["net_tilt"] is None


def test_typed_summary_withdraws_expired_neural_context(monkeypatch, tmp_path):
    from brain import decision_context as DC
    published = _published()
    _, context_path = _install_publication(monkeypatch, tmp_path, published)
    ctx = _paired_context(published)
    ctx["neural_web"] = {
        "lobe_health": {"theme_rotation": {"asof": OLD, "stale": False, "age_days": 1}},
        "health_summary": {"fresh": 1, "stale": 0, "unknown": 0},
        "contexts": {"theme_rotation": {"leadership_state": "confirmed"}},
    }
    context_path.write_text(json.dumps(ctx))
    current = DC.prompt_summary(now=NOW)
    assert current["serving_freshness"]["current_assessment_available"] is False
    assert current["neural_web_contexts"] is None
    assert "neural_context_expired" in current["data_quality"]["degrade_reasons"]


@pytest.mark.parametrize("payload", [None, "not-json", "[]", '{"schema_version": "unknown"}'])
def test_missing_or_malformed_current_reader_is_explicitly_unavailable(monkeypatch, tmp_path, payload):
    from brain import pm_conviction as PM
    path = tmp_path / "view.json"
    monkeypatch.setattr(PM, "_MARKET_VIEW_PATH", path)
    if payload is not None:
        path.write_text(payload)
    view = PM._read_market_view(now=NOW)
    enrichment = PM._market_view_enrichment(view)
    assert "unavailable" in enrichment["label_vs_planes_line"]
    assert enrichment["serving_freshness"]["current_confirmation_available"] is False
    assert "release existing protection" in enrichment["market_view_brief"]["posture_implication"]


def test_reader_generation_change_withholds_typed_context(monkeypatch, tmp_path):
    from brain import decision_context as DC
    published = _published()
    _, context_path = _install_publication(monkeypatch, tmp_path, published)
    context_path.write_text(json.dumps(_paired_context(published)))
    earlier = {key: published[key] for key in ("asof", "seq", "built_at")}
    earlier["seq"] -= 1
    current = DC.prompt_summary(now=NOW, expected_publication=earlier)
    assert current["governor"]["relationship"] == "unavailable"
    assert "consumer_publication_changed_during_read" in current["data_quality"]["degrade_reasons"]


@pytest.mark.parametrize("health", [
    {}, {"theme_rotation": {"asof": FRESH, "stale": True}},
    {"theme_rotation": {"asof": FRESH, "stale": False, "future_dated": True}},
    {"theme_rotation": {"asof": None, "stale": False}},
])
def test_typed_neural_context_needs_original_fresh_eligible_health(monkeypatch, tmp_path, health):
    from brain import decision_context as DC
    published = _published()
    _, context_path = _install_publication(monkeypatch, tmp_path, published)
    ctx = _paired_context(published)
    ctx["neural_web"] = {
        "lobe_health": health, "contexts": {"theme_rotation": {"leadership_state": "confirmed"}},
    }
    context_path.write_text(json.dumps(ctx))
    current = DC.prompt_summary(now=NOW)
    assert current["serving_freshness"]["current_assessment_available"] is False
    assert current["neural_web_contexts"] is None
