"""Actual HTTP/auth -> native valuation -> scenario response, synthetic inputs only."""
from __future__ import annotations

import ast
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth, portfolio_scenarios as api
from portfolio import global_scenario_account, instrument_policy, paper_account
from tests.test_global_scenario_account import inputs, digest

TOKEN = "synthetic-test-only-no-real-credential"
HEADERS = {"Authorization": "Bearer " + TOKEN}
NOW = datetime(2026, 11, 5, 22, 0, 1, tzinfo=timezone.utc)


def payload():
    return {"schema": api.REQUEST_SCHEMA, **inputs()}


@pytest.fixture(autouse=True)
def isolated_owners(monkeypatch):
    monkeypatch.setenv("MASTERMIND_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("MASTERMIND_VPS_AUTHORITATIVE", "1")
    monkeypatch.setenv("MASTERMIND_SERVE_ONLY", "0")
    monkeypatch.setattr(api, "_now", lambda: NOW)
    auth._operator_limiter.reset()
    auth._llm_limiter.reset()
    def forbidden(*args, **kwargs):
        raise AssertionError("scenario HTTP request must not access or mutate an account")
    for name in ("_load_account", "_save_account", "mark", "rebalance"):
        monkeypatch.setattr(paper_account, name, forbidden)
    monkeypatch.setattr(instrument_policy, "classify_instrument", lambda pid, key: {
        "ticker": key, "kind": "common_stock", "verified": True,
        "status": "synthetic-positive-identity", "market": pid})
    yield
    auth._operator_limiter.reset()
    auth._llm_limiter.reset()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(api.router)
    auth.install(app)
    return TestClient(app)


def test_actual_http_to_native_valuation_to_net_comparison(client, monkeypatch):
    native = Mock(wraps=paper_account.valuation)
    monkeypatch.setattr(paper_account, "valuation", native)
    r = client.post(api.PATH, json=payload(), headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "AVAILABLE" and native.call_count == 1
    alternatives = {row["alternative_id"]: row for row in body["result"]["comparison"]["alternatives"]}
    assert alternatives["hold"]["scenario_results"][0]["net_return"] == pytest.approx(-.0596)
    assert alternatives["cash"]["scenario_results"][0]["net_return"] == pytest.approx(.00064)
    assert alternatives["rotation"]["one_time_cost_fraction"] == pytest.approx(.00036)
    assert body["analysis_as_of"] == "2026-11-05T22:00:00Z"
    assert body["received_at"] == "2026-11-05T22:00:01Z"
    assert body["input_basis"] == "operator_supplied_snapshot"
    for key in ("account_ownership_verified", "historical_original_availability_proven",
                "live_account_read", "account_mutation"):
        assert body[key] is False
    assert all(v is False for v in body["authority"].values())
    assert all(v is False for v in body["result"]["authority"].values())
    assert "shares" not in r.text and "avg_cost" not in r.text and TOKEN not in r.text


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer incorrect"}, {"Authorization": "Basic x"}])
def test_unauthorized_fails_before_private_input_or_computation(client, monkeypatch, headers):
    compute = Mock(side_effect=AssertionError("must not execute"))
    monkeypatch.setattr(global_scenario_account, "compare_account", compute)
    r = client.post(api.PATH, json=payload(), headers=headers)
    assert r.status_code == 401
    assert compute.call_count == 0 and "account_sha256" not in r.text


def test_missing_authoritative_credential_fails_closed(client, monkeypatch):
    monkeypatch.delenv("MASTERMIND_AUTH_TOKEN")
    r = client.post(api.PATH, json=payload())
    assert r.status_code == 503
    assert r.json()["error"] == "operator_auth_misconfigured"


def test_read_mirror_does_not_offer_private_computation(client, monkeypatch):
    monkeypatch.setenv("MASTERMIND_SERVE_ONLY", "1")
    assert client.post(api.PATH, json=payload(), headers=HEADERS).status_code == 403


def test_get_is_not_a_public_compute_or_snapshot_read(client):
    assert client.get(api.PATH).status_code == 405


def test_trailing_slash_redirect_cannot_bypass_operator_auth(client):
    assert client.post(api.PATH + "/", json=payload(), follow_redirects=True).status_code == 401


def test_existing_non_llm_rate_limit_applies(client, monkeypatch):
    monkeypatch.setattr(auth._operator_limiter.__class__, "consume", lambda self: 13.0)
    from control_plane import run_events
    monkeypatch.setattr(run_events, "append", lambda row: None)
    r = client.post(api.PATH, json=payload(), headers=HEADERS)
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 13


def test_response_is_private_uncached_and_not_indexable(client):
    r = client.post(api.PATH, json=payload(), headers=HEADERS)
    assert r.headers["cache-control"] == "private, no-store"
    assert r.headers["pragma"] == "no-cache"
    assert r.headers["x-robots-tag"] == "noindex, noarchive"


def test_input_is_not_mutated_and_values_not_written(client):
    data = payload(); before = copy.deepcopy(data)
    assert client.post(api.PATH, json=data, headers=HEADERS).status_code == 200
    assert data == before


@pytest.mark.parametrize("raw", [b'{"schema":', b'{"schema":"x","schema":"y"}',
                                 b'{"number":NaN}', b'{"number":Infinity}', b'\xff'])
def test_invalid_duplicate_or_nonfinite_json_has_no_reflected_input(client, raw):
    r = client.post(api.PATH, content=raw, headers={**HEADERS, "Content-Type": "application/json"})
    assert r.status_code == 400
    assert r.json()["reasons"] == ["invalid_json"]
    assert r.json()["result"] is None


def test_wrong_media_type(client):
    r = client.post(api.PATH, content="not-json", headers=HEADERS)
    assert r.status_code == 415


@pytest.mark.parametrize("change", [lambda d: d.update(schema="other/v1"),
                                    lambda d: d.update(write_account=True),
                                    lambda d: d.pop("snapshot")])
def test_closed_request_contract(client, change):
    x = payload(); change(x)
    r = client.post(api.PATH, json=x, headers=HEADERS)
    assert r.status_code == 422 and r.json()["reasons"] == ["request_contract_invalid"]


def test_request_size_is_bounded_even_with_false_content_length(client):
    body = b' ' * (api.MAX_BODY_BYTES + 1)
    r = client.post(api.PATH, content=body, headers={**HEADERS, "Content-Type": "application/json", "Content-Length": "1"})
    assert r.status_code == 413


def test_declared_large_body_rejected_without_computing(client):
    r = client.post(api.PATH, content=b'{}', headers={**HEADERS, "Content-Type": "application/json", "Content-Length": str(api.MAX_BODY_BYTES + 1)})
    assert r.status_code == 413


def test_nested_json_complexity_is_bounded(client):
    nested = []
    for _ in range(api.MAX_DEPTH + 2): nested = [nested]
    x = payload(); x["account"]["extra"] = nested
    assert client.post(api.PATH, json=x, headers=HEADERS).status_code == 413


@pytest.mark.parametrize("at", ["2026-11-05T22:00:02Z", "2026-11-05", "2026-11-05T22:00:00"])
def test_future_or_naive_analysis_clock_rejected(client, at):
    x = payload(); x["as_of"] = at
    r = client.post(api.PATH, json=x, headers=HEADERS)
    assert r.status_code == 422 and r.json()["reasons"] == ["invalid_or_future_as_of"]


def test_correction_revision_mismatch_abstains_not_autofixes(client):
    x = payload(); x["account"]["cash"] = 500
    r = client.post(api.PATH, json=x, headers=HEADERS)
    assert r.status_code == 200 and r.json()["status"] == "UNAVAILABLE"
    assert r.json()["result"]["reasons"] == ["account_revision_mismatch"]


def test_explicit_cash_only_account_works_over_http(client):
    x = payload(); x["account"]["positions"] = {}; x["prices"] = {}; x["price_evidence"] = {}
    x["snapshot"]["account_sha256"] = digest(x["account"]); x["universe"] = []
    x["alternatives"] = [x["alternatives"][1]]; x["scenarios"][0]["returns"] = {}
    r = client.post(api.PATH, json=x, headers=HEADERS)
    assert r.status_code == 200 and r.json()["status"] == "AVAILABLE"
    assert r.json()["result"]["held_positions"] == 0


def test_computation_input_error_does_not_leak_secret_or_account(client, monkeypatch):
    def bad(**kwargs): raise ValueError("private-account SECRET /private/file")
    monkeypatch.setattr(global_scenario_account, "compare_account", bad)
    r = client.post(api.PATH, json=payload(), headers=HEADERS)
    assert r.status_code == 422 and "SECRET" not in r.text and "/private/file" not in r.text


def test_router_registered_in_existing_app_and_operator_tier():
    # The actual app mount is proven below. The audited executable root is
    # SHA-pinned; only its existing web router may introduce this additive API.
    import hashlib
    from tests.executive_fabric_release_identity_review import REVIEWED_FILES
    root = Path(__file__).resolve().parents[1]
    main_source = (root / "app/main.py").read_text()
    assert hashlib.sha256(main_source.encode()).hexdigest() == REVIEWED_FILES["app/main.py"]["sha256"]
    def includes(source, expression):
        return any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and node.func.attr == "include_router" and node.args
                   and ast.unparse(node.args[0]) == expression
                   for node in ast.walk(ast.parse(source)))
    assert includes(main_source, "web.router")
    assert includes((root / "app/web.py").read_text(), "_portfolio_scenarios.router")
    assert api.PATH in auth._NON_LLM_OPERATOR_PATHS and api.PATH not in auth._LLM_OPERATOR_PATHS


def test_http_reports_net_difference_against_actual_hold_not_caller_label(client):
    x = payload()
    x["alternatives"] = [dict(x["alternatives"][1], alternative_id="hold")]
    response = client.post(api.PATH, json=x, headers=HEADERS)
    assert response.status_code == 200
    comparison = response.json()["result"]["comparison"]
    assert comparison["hold_baseline"]["source"] == "unchanged_supplied_book"
    assert comparison["hold_baseline"]["one_time_cost_fraction"] == 0
    pair = comparison["alternatives"][0]["relative_to_hold"]["scenarios"][0]
    assert pair["hold_net_return"] == pytest.approx(-.0596)
    assert pair["candidate_net_return"] == pytest.approx(.00064)
    assert pair["net_return_delta"] == pytest.approx(.06024)
    assert comparison["alternatives"][0]["alternative_id"] == "hold"
    assert "recommended" not in response.text


def test_http_keeps_violating_alternative_ineligible_despite_favorable_scenario(client):
    x = payload(); x["mandate"]["constraints"]["max_turnover_fraction"] = .1
    response = client.post(api.PATH, json=x, headers=HEADERS)
    assert response.status_code == 200
    comparison = response.json()["result"]["comparison"]
    cash = next(a for a in comparison["alternatives"] if a["alternative_id"] == "cash")
    assert cash["status"] == "INELIGIBLE" and "turnover_ceiling" in cash["constraints_breached"]
    assert cash["relative_to_hold"]["scenarios"][0]["net_return_delta"] > 0
    assert all(value is False for value in comparison["authority"].values())


def test_actual_application_mount_uses_same_auth_and_api_without_startup(monkeypatch):
    # TestClient without its lifespan context exercises the REAL app middleware
    # and registered route, while never booting scheduler/jobs/runtime writers.
    # The isolated source workspace intentionally has no vendored Macro engine.
    # Stub only that external bootstrap path, not app composition/auth/valuation.
    import sys
    import types
    deps = types.ModuleType("app.deps")
    deps.data_dir = lambda: "/unused-synthetic-data-root"
    monkeypatch.setitem(sys.modules, "app.deps", deps)
    from app import main, scheduler
    monkeypatch.setattr(scheduler, "start", Mock(side_effect=AssertionError("no scheduler during route proof")))
    transport = TestClient(main.app)
    refused = transport.post(api.PATH, json=payload())
    assert refused.status_code == 401
    accepted = transport.post(api.PATH, json=payload(), headers=HEADERS)
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "AVAILABLE"
    assert accepted.json()["result"]["comparison"]["hold_baseline"]["source"] == "unchanged_supplied_book"
    assert accepted.headers["cache-control"] == "private, no-store"
    scheduler.start.assert_not_called()
    transport.close()
