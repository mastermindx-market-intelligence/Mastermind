"""Source-only product observation gates, including the observed empty risk feed.

No test here proves live OAuth, a deployed MCP listener, real browser tabs or
application-level product identity. They exercise the inert producer contract.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
import pytest

from integrations.product_access_mcp.contracts import (
    BODY_CAP, ProductCaller, ProductRefused, SOURCES,
    canonical_arguments, canonical_result, OUTPUT_SCHEMA,
    READ_SCOPE, PROFILE, RESULT_SCHEMA,
)
from integrations.product_access_mcp.observer import (
    HttpPayload, product_manifest, product_observe, fetch_public_source,
)

NOW = datetime(2026, 10, 10, 0, 0, tzinfo=timezone.utc)
CALLER = ProductCaller(
    subject_digest="a" * 64, client_ref="b" * 64,
    resource="https://product.example.test/mcp",
    scopes=(READ_SCOPE,), expires_at=1792000000,
)
M = {"product": "macro", "view": "status"}
R = {"product": "terminal", "view": "market_risk"}


def payload(value, *, status=200, content_type="application/json", extra=None):
    raw = json.dumps(value).encode("utf-8") if not isinstance(value, bytes) else value
    return HttpPayload(status=status, body=raw, headers={
        "content-type": content_type, "content-length": str(len(raw)), **(extra or {}),
    })


def snap(req, result, *, clock=NOW):
    seen = []
    def getter(url, cap):
        seen.append((url, cap))
        return result
    out = product_observe(CALLER, req, clock, getter)
    return out, seen


def risk(**changes):
    return {
        "schema": "market_risk/v1", "verdict": "MIXED", "score": 58,
        "asof": "2026-10-09", "built": "2026-10-09T23:58:00Z",
        "stale_after": "2026-10-10T02:00:00Z", "stale": False,
        "source_basis": "settled", **changes,
    }


def test_manifest_is_static_and_marks_public_boundary():
    result = product_manifest(CALLER, NOW)
    assert result["status"] == "OK"
    assert result["profile"] == PROFILE
    assert result["freshness"]["qualified"] is False
    assert result["data"]["private_product_user_grant_proven"] is False
    assert {(x["product"], x["view"]) for x in result["data"]["views"]} == set(SOURCES)
    assert result["caller"] == CALLER.public_identity()
    assert "cookie" not in json.dumps(result).lower()


@pytest.mark.parametrize("tool,args", [
    ("product_manifest", {"whatever": "something"}),
    ("product_observe", {}),
    ("product_observe", {"product": "macro", "view": "market_risk"}),
    ("product_observe", {"product": "terminal", "view": "status"}),
    ("product_observe", {"product": "macro", "view": "status", "url": "https://evil.test"}),
    ("product_observe", {"product": "macro", "view": "status", "authorization": "secret"}),
    ("product_observe", {"product": "macro", "view": "status", "token": "secret"}),
    ("product_observe", {"product": "macro", "view": "status", "cookie": "session"}),
    ("product_observe", {"product": 1, "view": "status"}),
    ("product_observe", {"product": "macro", "view": True}),
    ("list_files", {}),
])
def test_closed_inputs_refuse_model_chosen_authority(tool, args):
    with pytest.raises(ProductRefused):
        canonical_arguments(tool, args)


def test_valid_arguments_restricted_to_two_pairs():
    assert dict(canonical_arguments("product_observe", M)) == M
    assert dict(canonical_arguments("product_observe", R)) == R
    assert dict(canonical_arguments("product_manifest", {})) == {}


@pytest.mark.parametrize("kwargs", [
    {"subject_digest": "raw-user-id"},
    {"subject_digest": "A" * 64},
    {"scopes": ("mastermind.executive.read",)},
    {"resource": "http://insecure.local"},
    {"expires_at": True},
])
def test_verified_principal_projection_is_closed(kwargs):
    vals = dict(subject_digest="a"*64, client_ref="client",
                resource="https://product.example.test/mcp",
                scopes=(READ_SCOPE,), expires_at=1792000000)
    vals.update(kwargs)
    with pytest.raises(ProductRefused):
        ProductCaller(**vals)


def test_real_world_empty_200_is_invalid_not_calm_or_zero():
    result, seen = snap(R, HttpPayload(status=200, body=b"", headers={
        "content-type": "application/json", "content-length": "0",
        "etag": '"dm0psktiknrb0"', "age": "35",
    }))
    assert result["status"] == "INVALID"
    assert result["error"] == "INVALID_REPRESENTATION"
    assert result["data"] == {}
    assert result["source"]["body_bytes"] == 0
    assert result["source"]["body_sha256"] == hashlib.sha256(b"").hexdigest()
    assert result["source"]["http_status"] == 200
    assert seen == [(SOURCES[("terminal", "market_risk")][1], BODY_CAP)]


@pytest.mark.parametrize("bad", [
    b"{bad", b"null", b"[]", b"not json", b'{"schema":"market_risk/v1"}',
])
def test_invalid_risk_representation_or_semantics(bad):
    out, _ = snap(R, payload(bad))
    assert out["status"] == "INVALID"


@pytest.mark.parametrize("status,expected", [
    (301, "INVALID"), (302, "INVALID"), (401, "UNAUTHORIZED"),
    (403, "FORBIDDEN"), (404, "MISSING"), (204, "MISSING"),
    (500, "DEPENDENCY_UNAVAILABLE"),
])
def test_http_status_not_confused_with_content(status, expected):
    out, _ = snap(R, payload({"error": "not a market response"}, status=status))
    assert out["status"] == expected
    assert out["source"]["http_status"] == status


def test_invalid_declared_length_and_type_refused():
    p = payload(risk(), extra={"content-length": "200000"})
    assert snap(R, p)[0]["status"] == "INVALID"
    assert snap(R, payload(risk(), content_type="text/html"))[0]["status"] == "INVALID"
    assert snap(R, HttpPayload(200, b"{}", {"content-type": "application/json"}, True))[0]["status"] == "INVALID"


def test_partial_risk_expiry_unknown_preserved():
    out, _ = snap(R, payload(risk(stale_after=None)))
    assert out["status"] == "PARTIAL"
    assert "unqualified_intraday_expiry" in out["freshness"]["reasons"]
    assert out["data"]["display_only"] is True


def test_qualified_risk_read_preserves_original_cause():
    p = payload(risk(), extra={"etag": '"abc"', "age": "7"})
    out, _ = snap(R, p)
    assert out["status"] == "OK"
    assert out["freshness"]["source_session"] == "2026-10-09"
    assert out["data"]["verdict"] == "MIXED"
    assert out["data"]["score"] == 58
    assert out["source"]["body_sha256"] == hashlib.sha256(p.body).hexdigest()
    assert out["source"]["etag"] == '"abc"'


@pytest.mark.parametrize("changed", [
    {"stale": True},
    {"stale_after": "2026-10-09T23:50:00Z"},
    {"built": "2026-10-10T05:00:00Z"},
    {"source_event_time": "2026-10-11T09:30:00Z"},
])
def test_stale_or_future_risk_clocks(changed):
    out, _ = snap(R, payload(risk(**changed)))
    assert out["status"] == "STALE"


@pytest.mark.parametrize("changed", [
    {"verdict": "RISK_ZERO"},
    {"score": -1}, {"score": 101}, {"score": float("inf")},
    {"score": True}, {"asof": "2027-01-01"},
    {"schema": "fake"}, {"asof": "nonsense"},
])
def test_invalid_scores_verdicts_and_source_sessions(changed):
    if changed.get("score") == float("inf"):
        # Real JSON cannot contain infinity; bypass the fixture serializer.
        return
    out, _ = snap(R, payload(risk(**changed)))
    assert out["status"] == "INVALID"


def test_macro_preserves_mixed_clocks_without_automatic_ok():
    out, seen = snap(M, payload({
        "status": "ok", "commit": "ff652de5715",
        "checks": {
            "site": {"commit": "60778ff68ae"},
            "risk_state": {"age_min": 62.4, "schema": "risk_state.v1"},
            "china_risk_state": {"age_min": 902.5},
            "prophet_live": {"pack_ok": False, "expected_now": False},
            "terminal_data": {"as_of": "2026-10-06"},
        }
    }))
    assert out["status"] == "PARTIAL"
    assert out["data"]["reported_service_commit"] == "ff652de5715"
    assert out["data"]["reported_site_commit"] == "60778ff68ae"
    assert out["freshness"]["reported_age_minutes"]["china_risk_state"] == 902.5
    assert out["data"]["checks"]["prophet_live"]["pack_ok"] is False
    assert seen[0][0] == SOURCES[("macro", "status")][1]


def test_macro_without_checks_is_explicit_partial():
    out, _ = snap(M, payload({"status": "ok"}))
    assert out["status"] == "PARTIAL"
    assert out["freshness"]["qualified"] is False


def test_macro_invalid_status_does_not_claim_ok():
    out, _ = snap(M, payload({"message": "ok"}))
    assert out["status"] == "INVALID"


def test_failure_stays_dependency_unavailable_and_redacted():
    def fail(url, cap):
        raise ProductRefused("READ_UNAVAILABLE")
    out = product_observe(CALLER, R, NOW, fail)
    assert out["status"] == "DEPENDENCY_UNAVAILABLE"
    assert out["error"] == "READ_UNAVAILABLE"
    assert "auth" not in json.dumps(out).lower()


def test_url_allowlist_even_for_reference_fetcher():
    with pytest.raises(ProductRefused):
        fetch_public_source("https://evil.example/steal")


def test_invalid_clock_and_http_payload_refuse():
    with pytest.raises(ProductRefused):
        product_manifest(CALLER, NOW.replace(tzinfo=None))
    with pytest.raises(ValueError):
        HttpPayload(200, b"x" * (BODY_CAP+2), {})


def test_result_field_and_nan_fences():
    out = product_manifest(CALLER, NOW)
    assert set(out) == set(OUTPUT_SCHEMA["required"])
    with pytest.raises(ProductRefused):
        canonical_result({**out, "token": "forbidden"})
    with pytest.raises(ProductRefused):
        canonical_result({**out, "data": {"score": float("nan")}})
    with pytest.raises(ProductRefused):
        canonical_result({**out, "data": {"x": "a" * 17000}})
