"""Capacity Fabric reads real H2 projections through the signed Workspace path.

All accounts, paths, clocks and credentials below are disposable test fixtures.
These are source/transport proofs, never installed capacity or provider proof.
"""
import asyncio
import copy
import json
from dataclasses import replace
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from common import workspace_capacity_fabric_contract as wire
from control_plane import workspace_capacity_fabric as projection
from control_plane.workspace_read_service import WorkspaceReadService
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.contract import BINDINGS_SCHEMA, principal_frame, workspace_authorizers
from ops.native_fabric.grok47.quota_billing.quota_remote import (
    ProviderQuotaState, account_quota_view,
)
from tests import test_workspace_admitted_plan_read as transport_suite
from tests.test_workspace_admitted_plan_read import plan_owner
from tests.test_workspace_read_app import NOW, _authenticator, _workspace_token, rsa_key
from tests.test_workspace_read_socket import short_socket_root

ROUTE = "/workspace/resources/fabric/current"


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def fixture_inputs(now=NOW):
    """WO-09's row shape plus actual pure H2 account_quota_view output."""
    preview = dict(schema=projection.PREVIEW_SCHEMA, as_of=iso(now - 10), expires_at=iso(now + 890),
        registry_revision="fixture-registry-a", authority="NONE_PREVIEW_ONLY", live_admission=False,
        production_armed=False, claim_time_revalidation_required=True, resources=[],
        projection={"path": "/private/owner/registry.json"},
        producer={"source_config": {"owner_ext_root": "/private/owner"}})
    views = {}
    for provider, balances in (("glm", (70, 11)), ("go", (90, 82, 0)), ("minimax", (None, None))):
        ref = provider + ":fixture-account"
        row = dict(shared_quota_resource_ref=ref, provider_ref=provider, pool_ref=provider,
            registry_revision=preview["registry_revision"], observed_at=preview["as_of"], expires_at=preview["expires_at"],
            readiness_state="ready", configured_concurrency_cap=4, configured_cap_basis="accounts_yaml_per_account_cap", active_slots=1, reserved_slots=0,
            cooldown_until=None, reason_codes=[], admission_eligibility=True,
            remaining_quota=None, remaining_quota_basis=None, quota_knowledge="unknown", quota_source=None,
            quota_observed_at=None, reset_at=None)
        preview["resources"].append(row)
        states = [ProviderQuotaState(provider=provider, account="fixture-account", window=window,
            used=None, cap=None, remaining_pct=pct, reset_at=iso(now + 3600),
            source="PROVIDER_AUTHORITATIVE", observed_at=iso(now - 30), confidence=0.98,
            detail="synthetic test observation", config_generation="fixture-config-a",
            account_generation="fixture-account-a", allowance_scope=provider + ":fixture-allowance",
            endpoint="https://provider.example.test")
            for window, pct in zip(("5h", "weekly", "monthly"), balances) if pct is not None]
        views[ref] = account_quota_view(provider, "fixture-account", states,
            config_generation="fixture-config-a", endpoint="https://provider.example.test",
            allowance_scope=provider + ":fixture-allowance", account_generation="fixture-account-a", now_ts=now)
    return preview, views


def fixture_binding(preview, views):
    return dict(registry_revision=preview["registry_revision"], consumer_revision="fixture-consumer-a",
        accounts={ref: {**{key: view[key] for key in ("config_generation", "account_generation", "allowance_scope", "endpoint")}, "broker_scope": ref}
                  for ref, view in views.items()})


def projected(preview=None, views=None, **kwargs):
    if preview is None:
        preview, views = fixture_inputs()
    return projection.project_capacity_fabric(preview, binding=kwargs.pop("binding", fixture_binding(preview, views)), account_views=views, now=NOW, **kwargs)


def installed_source(tmp_path, *, now=lambda: NOW):
    preview, views = fixture_inputs()
    path = tmp_path / "owner-preview.json"
    path.write_text(json.dumps(preview))
    return projection.ExistingCapacityFabricSource(path, account_views=lambda refs: views,
        current_revision=lambda: fixture_binding(preview, views), now=now), preview, views


def test_actual_h2_windows_keep_monthly_zero_and_missing_usage_distinct():
    body = projected()
    assert wire.validate_result(body) is body
    glm, go, minimax = body["resources"]
    assert [w["remaining_pct"] for w in glm["windows"]] == [70, 11, None]
    assert [w["required"] for w in glm["windows"]] == [True, True, False]
    assert glm["pressure"] == "LOW_ALLOWANCE"
    assert [w["remaining_pct"] for w in go["windows"]] == [90, 82, 0]
    assert go["windows"][2]["state"] == "EXHAUSTED" and go["pressure"] == "LIMIT_REACHED"
    assert all(w["remaining_pct"] is None for w in minimax["windows"])
    assert minimax["pressure"] == "UNKNOWN"
    assert body["expires_at"] == iso(NOW + 570)
    assert body["admission_authorized"] is False
    assert all(c["runtime_state"] == "NOT_OBSERVED" for c in body["consumers"])
    assert body["consumers"][2]["source_state"] == "SPEC_ONLY"
    assert set(body["recommendations"]) == {"UPDATE_USAGE", "CONSERVE_ALLOWANCE", "WAIT_FOR_RESET", "MEASURE_DEMAND"}
    assert "/private" not in json.dumps(body) and "source_config" not in json.dumps(body)


def test_frontend_fixture_is_the_exact_public_projection_of_incumbent_h2():
    fixture = Path(__file__).resolve().parents[1] / "app/mastermind_os/src/resources/fixtures/capacity-fabric-owner-read.json"
    assert json.loads(fixture.read_text()) == projected()


@pytest.mark.parametrize("mutation", ["expired", "future", "reset", "refresh_failed", "generation", "foreign_account", "duplicate", "non_authoritative"])
def test_one_unqualified_window_cannot_be_hidden_by_another_fresh_window(mutation):
    preview, views = fixture_inputs()
    view = views["go:fixture-account"]
    weekly = view["windows"][1]
    if mutation == "expired": weekly["observed_at"] = iso(NOW - 600)
    elif mutation == "future": weekly["observed_at"] = iso(NOW + 1)
    elif mutation == "reset": weekly["reset_at"] = iso(NOW)
    elif mutation == "refresh_failed": view["refresh_error"] = "REFRESH_FAILED"
    elif mutation == "generation": view["windows"][1].update(ready=False, reason="CONFIG_GENERATION_UNQUALIFIED")
    elif mutation == "foreign_account": view["account"] = "another-account"
    elif mutation == "duplicate": view["windows"].append(copy.deepcopy(weekly))
    else: weekly["source"] = "LOCAL_ESTIMATE"
    body = projected(preview, views)
    account = body["resources"][1]
    assert account["windows"][1]["remaining_pct"] is None
    assert account["pressure"] != "HEADROOM_RECORDED"
    assert body["admission_authorized"] is False


def test_same_qualified_allowance_is_not_added_and_conflicting_readings_are_withdrawn():
    preview, views = fixture_inputs()
    alias = copy.deepcopy(preview["resources"][0])
    alias["shared_quota_resource_ref"] = "glm:fixture-alias"
    preview["resources"].append(alias)
    alias_view = copy.deepcopy(views["glm:fixture-account"])
    alias_view["account"] = "fixture-alias"
    views[alias["shared_quota_resource_ref"]] = alias_view
    body = projected(preview, views)
    assert body["resources"][0]["allowance_scope"] == body["resources"][-1]["allowance_scope"]
    assert "total_remaining" not in body
    alias_view["windows"][0]["remaining_pct"] = 75
    body = projected(preview, views)
    for row in (body["resources"][0], body["resources"][-1]):
        assert row["pressure"] == "UNKNOWN"
        assert all(w["remaining_pct"] is None for w in row["windows"])
        assert "SHARED_ALLOWANCE_CONFLICT" in row["reason_codes"]


def test_preview_eligibility_does_not_override_cooldown_or_configured_slots():
    preview, views = fixture_inputs()
    preview["resources"][0]["cooldown_until"] = iso(NOW + 30)
    preview["resources"][2]["active_slots"] = 4
    body = projected(preview, views)
    assert body["resources"][0]["preview_eligible"] is True
    assert body["resources"][0]["pressure"] == "COOLDOWN"
    assert body["resources"][2]["pressure"] == "SLOTS_OCCUPIED"
    assert body["admission_authorized"] is False


@pytest.mark.parametrize("age,expected", [(30, 98), (600, None), (-1, None)])
def test_scalar_estimate_has_its_own_freshness_and_never_fills_windows(age, expected):
    preview, views = fixture_inputs()
    row = preview["resources"][2]
    row.update(remaining_quota=98, remaining_quota_basis="percent_of_window_remaining",
        quota_source="bailian_inline_7d_local_reconstruction", quota_knowledge="observed", quota_observed_at=iso(NOW - age))
    public = projected(preview, views)["resources"][2]
    assert public["single_window_remaining_pct"] == expected
    assert public["single_window_source"] == "LOCAL_ESTIMATE"
    assert all(w["remaining_pct"] is None for w in public["windows"])
    assert public["pressure"] == "UNKNOWN"


@pytest.mark.parametrize("case", ["expired", "future", "mixed_registry", "duplicate_ref", "authority", "boolean_clock", "nan_clock"])
def test_projection_refuses_unqualified_snapshot(case):
    preview, views = fixture_inputs()
    now = NOW
    if case == "expired": now += 900
    elif case == "future": now -= 20
    elif case == "mixed_registry": preview["resources"][0]["registry_revision"] = "different"
    elif case == "duplicate_ref": preview["resources"].append(preview["resources"][0])
    elif case == "authority": preview["live_admission"] = True
    elif case == "boolean_clock": now = True
    else: now = float("nan")
    with pytest.raises(projection.CapacitySourceError):
        projection.project_capacity_fabric(preview, binding=fixture_binding(preview, views), account_views=views, now=now)


def test_consumer_status_requires_current_existing_owner_receipt():
    evidence = dict(runtime_state="RESULT_PROVEN", source_revision="fixture-consumer-a", evidence_ref="fixture:runtime:receipt-1",
        observed_at=iso(NOW - 60), expires_at=iso(NOW + 50))
    body = projected(consumer_views={"hermes": evidence})
    assert body["consumers"][0]["runtime_state"] == "RESULT_PROVEN"
    assert body["expires_at"] == evidence["expires_at"]
    evidence["expires_at"] = iso(NOW)
    assert projected(consumer_views={"hermes": evidence})["consumers"][0]["runtime_state"] == "NOT_OBSERVED"


def test_read_only_source_rechecks_original_artifact_and_generation(tmp_path):
    source, preview, views = installed_source(tmp_path)
    before = source.preview_path.read_bytes(), source.preview_path.stat().st_mtime_ns, set(tmp_path.iterdir())
    assert source.read()["result"]["availability"] == "AVAILABLE"
    assert before == (source.preview_path.read_bytes(), source.preview_path.stat().st_mtime_ns, set(tmp_path.iterdir()))
    binding = fixture_binding(preview, views)
    revisions = iter((binding, {**binding, "registry_revision": "replacement"}))
    changed = replace(source, current_revision=lambda: next(revisions))
    assert changed.read() == wire.unavailable("SOURCE_CHANGED")
    def changing(refs):
        preview["resources"][0]["active_slots"] = 2
        source.preview_path.write_text(json.dumps(preview))
        return views
    assert replace(source, account_views=changing).read() == wire.unavailable("SOURCE_CHANGED")


@pytest.mark.parametrize("case", ["duplicate_key", "nan", "link", "missing", "oversized"])
def test_file_reader_has_closed_failure_without_private_path_leak(tmp_path, case):
    path = tmp_path / "private-preview.json"
    if case == "duplicate_key": path.write_text('{"schema":"a","schema":"b"}')
    elif case == "nan": path.write_text('{"value":NaN}')
    elif case == "link":
        other = tmp_path / "target.json"; other.write_text("{}"); path.symlink_to(other)
    elif case == "oversized": path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
    source = projection.ExistingCapacityFabricSource(path, current_revision=lambda: dict(registry_revision="fixture", accounts={}, consumer_revision=None), now=lambda: NOW)
    assert source.read() == wire.unavailable()


def test_callbacks_require_original_owner_generation_fence(tmp_path):
    with pytest.raises(ValueError, match="original_owner_generation_required"):
        projection.ExistingCapacityFabricSource(tmp_path / "preview.json", account_views=lambda _: {})


@pytest.mark.parametrize("case", ["registry", "configuration", "account", "scope", "endpoint"])
def test_stable_but_wrong_current_owner_binding_never_qualifies_cached_windows(tmp_path, case):
    source, preview, views = installed_source(tmp_path)
    binding = fixture_binding(preview, views)
    if case == "registry":
        binding["registry_revision"] = "current-registry"
    else:
        key = {"configuration": "config_generation", "account": "account_generation", "scope": "allowance_scope", "endpoint": "endpoint"}[case]
        binding["accounts"]["glm:fixture-account"][key] = "current-value"
    result = replace(source, current_revision=lambda: binding).read()
    if case == "registry":
        assert result == wire.unavailable("SOURCE_CHANGED")
    else:
        row = result["result"]["resources"][0]
        assert row["pressure"] == "UNKNOWN"
        assert all(w["remaining_pct"] is None for w in row["windows"])


def test_pool_cap_and_unattributed_broker_scope_never_mean_account_has_free_slots():
    preview, views = fixture_inputs()
    preview["resources"][0].update(configured_cap_basis="pools_yaml_concurrent", active_slots=0, reserved_slots=7)
    binding = fixture_binding(preview, views)
    binding["accounts"]["glm:fixture-account"]["broker_scope"] = "declared:shared-allowance"
    body = projected(preview, views, binding=binding)
    row = body["resources"][0]
    assert row["configured_cap_basis"] == "POOL"
    assert row["active"] is None and row["queued"] == 7
    assert "reserved" not in row
    assert "REVIEW_QUEUE" in body["recommendations"]


@pytest.mark.parametrize("case", ["window_lifetime", "window_reset", "consumer_lifetime", "future_consumer"])
def test_public_contract_refuses_evidence_that_expires_before_response(case):
    body = projected()
    if case == "window_lifetime": body["resources"][0]["windows"][0]["observed_at"] = iso(NOW - 599)
    elif case == "window_reset": body["resources"][0]["windows"][0]["reset_at"] = iso(NOW + 1)
    else:
        body["consumers"][0].update(runtime_state="RESULT_PROVEN", evidence_ref="fixture:receipt",
            observed_at=iso(NOW + 1 if case == "future_consumer" else NOW - 900))
    with pytest.raises(ValueError):
        wire.validate_result(body, now=NOW)


@asynccontextmanager
async def in_process_transport(owner, key, tmp_path, socket_root, *, after_app=None):
    """Actual signed HTTP and Workspace dispatcher; no claim of Unix proof."""
    auth = _authenticator(key)
    token = _workspace_token(key)
    principal = await auth.verify_authorization_header("Bearer " + token, now=NOW)
    slots = {"schema": BINDINGS_SCHEMA, "profiles": {
        "web": {"enabled": True, "binding": dict(principal_frame(principal), permission_digest="a" * 64)},
        "mac": {"enabled": False, "binding": None}}}
    app_auth, control_auth = workspace_authorizers(policy=auth.policy, load_bindings=lambda: slots)
    clock, seen = [NOW], {"factory": 0}
    class Client:
        async def request(self, frame):
            seen["factory"] += 1
            result = await transport_suite.service(owner, authorize=control_auth).handle_frame(frame)
            if after_app:
                after_app(slots, clock)
            return result
    app = create_workspace_app(WorkspaceAppConfig(authenticator=auth, now=lambda: clock[0],
        authorize_principal=app_auth, client=Client()))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://mcp.mastermind-x.com") as http:
        yield http, token, slots, seen


@pytest.fixture(params=["asgi", "unix"])
def bridge(request):
    return in_process_transport if request.param == "asgi" else transport_suite.transport


@pytest.fixture
def composed(tmp_path, monkeypatch):
    source, _, _ = installed_source(tmp_path)
    def service(owner, authorize=lambda _: True):
        return WorkspaceReadService(cache=owner["cache"], runtime=owner["writer"], authorize=authorize,
            armed={}, runtime_identity={"db_present": True}, capacity_fabric_source=source,
            bounded_runtime=lambda actual: owner["reader"] if actual is owner["writer"] else pytest.fail("wrong owner"))
    monkeypatch.setattr(transport_suite, "service", service)
    return source


def test_signed_http_original_dispatch_and_h2_read_without_runtime_or_provider_effects(
        composed, plan_owner, rsa_key, tmp_path, short_socket_root, bridge):
    async def run():
        async with bridge(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, slots, seen, *_):
            before = plan_owner["namespace"].entries, composed.preview_path.read_bytes()
            response = await http.get(ROUTE, headers={"Authorization": "Bearer " + token})
            assert response.status_code == 200, response.text
            assert response.json() == composed.read()["result"]
            assert response.headers["cache-control"] == "no-store"
            assert seen["factory"] == 1
            assert before == (plan_owner["namespace"].entries, composed.preview_path.read_bytes())
    asyncio.run(run())


@pytest.mark.parametrize("case", ["missing_auth", "foreign_scope", "query", "body", "post", "encoded_route"])
def test_fixed_authenticated_read_rejects_caller_sources_before_factory(
        composed, plan_owner, rsa_key, tmp_path, short_socket_root, case, bridge):
    async def run():
        async with bridge(plan_owner, rsa_key, tmp_path, short_socket_root) as (http, token, slots, seen, *_):
            method, path = "GET", ROUTE
            kwargs = {"headers": {"Authorization": "Bearer " + token}}
            if case == "missing_auth": kwargs["headers"] = {}
            elif case == "foreign_scope": kwargs["headers"]["Authorization"] = "Bearer " + _workspace_token(rsa_key, scope="mastermind.executive.read")
            elif case == "query": kwargs["params"] = {"path": "/private/another.json"}
            elif case == "body": kwargs["content"] = b'{"path":"private"}'
            elif case == "post": method = "POST"
            else: path = "/workspace/resources/%66abric/current"
            response = await http.request(method, path, **kwargs)
            assert response.status_code in (400, 401, 403, 404, 405), response.text
            assert seen["factory"] == 0
    asyncio.run(run())


@pytest.mark.parametrize("case", ["disabled", "permission_changed", "expired", "source_expired"])
def test_http_release_rechecks_auth_and_capacity_expiry(
        composed, plan_owner, rsa_key, tmp_path, short_socket_root, case, bridge):
    def after(slots, clock):
        if case == "disabled": slots["profiles"]["web"]["enabled"] = False
        elif case == "permission_changed": slots["profiles"]["web"]["binding"]["permission_digest"] = "b" * 64
        elif case == "source_expired": clock[0] += 600
        else: clock[0] += 86400
    async def run():
        async with bridge(plan_owner, rsa_key, tmp_path, short_socket_root, after_app=after) as (http, token, *_):
            response = await http.get(ROUTE, headers={"Authorization": "Bearer " + token})
            # Auth expiry may precede the capacity expiry in this signed fixture.
            assert response.status_code in (403, 503)
            assert "fixture-account" not in response.text
    asyncio.run(run())
