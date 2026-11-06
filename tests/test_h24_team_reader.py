"""Authenticated H24 consumer proof; all keys, sockets and Runtime are fixtures.

Exercise the additive reader through the actual Workspace HTTP, Unix custody,
Runtime result and acceptance owners. No live enrollment or service is used.
"""
import asyncio
import copy
import hashlib
import os
from contextlib import asynccontextmanager

import httpx
import pytest

from common import executive_workspace_mission_result_contract as pair_contract
from common.executive_workspace_contract import MAX_RESPONSE_BYTES
from control_plane.executive_service import CeoIngressAppBinding, ExecutiveControlService
from integrations.business_mcp_auth.contracts import subject_digest
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.contract import (
    MEMBER_BINDINGS_SCHEMA, principal_frame, workspace_authorizers,
)
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from integrations.secretary_team_access.client import SecretaryAccessClient
from integrations.secretary_team_access.mission import LOCAL_FRESHNESS_GUARD_SECONDS, _parse_utc
from integrations.secretary_team_access.team_projection import SCHEMA, render_operator_text
from integrations.secretary_team_access.team_reader import SecretaryTeamReader
from tests.test_executive_ceo_ingress import _FakeGrounding, _FakeSupervisor, _config
from tests.test_h24_team_projection import SELECTION, actual_acceptance, actual_pair, card, fixture_mission
from tests.test_product_acceptance_basis_continuity import restamp
from tests.test_product_acceptance_read_projection import case
from tests.test_product_acceptance_workspace_read import provider
from tests.test_secretary_team_access_http import _signed_client
from tests.test_secretary_team_mission_http import MEMBERS, _selection, transport
from tests.test_workspace_mission_result_http import app_transport
from tests.test_workspace_mission_result_service import mission_owner
from tests.test_workspace_read_app import (
    ISSUER, NOW, _authenticator, _workspace_policy, _workspace_token, rsa_key,
)
from tests.test_workspace_read_socket import short_socket_root
from tests.test_workspace_read_service import STAMP as SOURCE_STAMP


def reader(http, selection, *, clock=lambda: _parse_utc(SOURCE_STAMP) + 1):
    return SecretaryTeamReader(SecretaryAccessClient(
        **selection, workspace=http, clock=clock))


def reference(pair):
    return next(r for r in pair["mission"]["result_refs"]["refs"]
                if r["job_id"] == pair["selection"]["job_id"])


@asynccontextmanager
async def mock_reader(handler, *, selection=SELECTION, clock=None):
    if clock is None:
        clock = lambda: _parse_utc(fixture_mission()["generated_at"]) + 1
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
            base_url="https://host.invalid", follow_redirects=False) as http:
        sdk = SecretaryAccessClient(**selection, workspace=http, clock=clock)
        yield SecretaryTeamReader(sdk), sdk, http


def test_two_signed_principals_read_team_and_atomic_result_without_events(
        mission_owner, rsa_key, tmp_path, short_socket_root):
    owner = mission_owner
    selected = _selection(owner)

    async def exercise():
        async with transport(owner, rsa_key, tmp_path, short_socket_root) as (http, tokens, slots):
            async with _signed_client(http, tokens[MEMBERS[0]]) as a_http:
                async with _signed_client(http, tokens[MEMBERS[1]]) as b_http:
                    seen = []
                    async def observe(request):
                        seen.append((request.method, request.url.path, dict(request.url.params)))
                    a_http.event_hooks["request"] = [observe]
                    a, b = reader(a_http, selected), reader(b_http, selected)
                    events = owner["writer"].events.list_events()
                    # ObservationNamespace deliberately owns one read at a time.
                    # Keep this real custody test sequential; concurrent reader
                    # projections are covered separately without changing it.
                    first, second = await a.read_team(), await b.read_team()
                    assert first["schema"] == second["schema"] == SCHEMA
                    assert first["fingerprint"] == second["fingerprint"]
                    assert first["cards"], (first["currentness"]["owner_state"],
                        first["currentness"]["reason_codes"], first["coverage"]["children_state"])
                    assert first["cards"] == second["cards"] and first["cards"]
                    job = owner["selection"]["job_id"]
                    row = card(first, job)
                    assert row["result"]["state"] == "REFERENCE_ONLY"
                    ref = row["result"]["reference"]

                    qualified = await a.read_result(ref, previous_fingerprint=first["fingerprint"])
                    assert qualified["changed"] is True
                    result = card(qualified, job)
                    assert result["result"]["state"] == "AVAILABLE"
                    assert result["result"]["review"]["verdict"] == "reject"
                    assert result["result"]["consumption"] == "UNPROVEN"
                    assert result["product_acceptance"]["accepted"] is None
                    assert result["decision_needed"] is True
                    assert "Review rejection" in result["display_actions"]
                    assert qualified["display_only"] is True
                    assert qualified["attention"]["dispatch_permitted"] is False

                    same = await a.read_result(ref, previous_fingerprint=qualified["fingerprint"])
                    peer = await b.read_result(ref)
                    assert same["fingerprint"] == peer["fingerprint"] == qualified["fingerprint"]
                    assert same["changed"] is False and same["cards"] == qualified["cards"]
                    assert same["attention"]["reasoning_wake_recommended"] is False
                    assert "review reject" in render_operator_text(same)
                    assert seen == [
                        ("GET", "/workspace/mission/v3/current", selected),
                        ("GET", "/workspace/mission-result/current", owner["selection"]),
                        ("GET", "/workspace/mission-result/current", owner["selection"]),
                    ]

                    slots["profiles"][MEMBERS[0]]["enabled"] = False
                    for read in (a.read_team, lambda: a.read_result(ref),
                                 lambda: a.read_acceptance("asd-mcp-" + "a" * 32)):
                        refused = await read()
                        assert refused["state"] == "REFUSED"
                        assert refused["reason_code"] == "access_denied"
                        assert "cards" not in refused and "fingerprint" not in refused
                    survivor = await b.read_result(ref)
                    assert survivor["fingerprint"] == qualified["fingerprint"]
                    assert owner["writer"].events.list_events() == events
    asyncio.run(exercise())


def test_signed_mission_mid_read_revocation_releases_no_cards(
        mission_owner, rsa_key, tmp_path, short_socket_root):
    changed = []
    def revoke(slots):
        changed.append(True)
        slots["profiles"][MEMBERS[0]]["binding"]["permission_digest"] = "c" * 64

    async def exercise():
        async with transport(mission_owner, rsa_key, tmp_path, short_socket_root,
                             mid_read=revoke) as (http, tokens, _):
            async with _signed_client(http, tokens[MEMBERS[0]]) as enrolled:
                value = await reader(enrolled, _selection(mission_owner)).read_team()
                assert value["state"] == "REFUSED" and value["reason_code"] == "access_denied"
                assert "mission_workspace" not in repr(value) and "cards" not in value
        assert changed == [True]
    asyncio.run(exercise())


@pytest.mark.parametrize("gate", ["control", "app"])
def test_signed_compound_result_revocation_at_each_release_gate(
        mission_owner, rsa_key, tmp_path, short_socket_root, gate):
    ref = reference(actual_pair(mission_owner))
    changed = []
    def revoke(slots):
        changed.append(True)
        slots["profiles"]["web"]["binding"]["permission_digest"] = "b" * 64

    async def exercise():
        kwargs = {"after_control" if gate == "control" else "after_app": revoke}
        async with app_transport(mission_owner, rsa_key, tmp_path, short_socket_root,
                                 **kwargs) as (http, token, *_):
            async with _signed_client(http, token) as enrolled:
                value = await reader(enrolled, _selection(mission_owner)).read_result(ref)
                assert value["state"] == "REFUSED" and value["reason_code"] == "access_denied"
                assert "cards" not in value and "role_result" not in repr(value)
        assert changed == [True]
    asyncio.run(exercise())


@asynccontextmanager
async def acceptance_transport(runtime, owner, selected, rsa_key, tmp_path, socket_root,
                               *, after_read=None):
    """Actual acceptance custody chain with two independently sealed test grants."""
    policy = _workspace_policy(allowed_subject_digests=sorted(
        subject_digest(issuer=ISSUER, subject=s) for s in MEMBERS))
    auth = _authenticator(rsa_key, policy=policy)
    tokens = {s: _workspace_token(rsa_key, sub=s) for s in MEMBERS}
    principals = {s: await auth.verify_token(tokens[s], now=NOW) for s in MEMBERS}
    slots = {"schema": MEMBER_BINDINGS_SCHEMA, "primary_profile": MEMBERS[0],
             "profiles": {s: {"enabled": True, "binding": dict(principal_frame(principals[s]),
                 permission_digest=hashlib.sha256(s.encode()).hexdigest())} for s in MEMBERS}}
    app_auth, control_auth = workspace_authorizers(policy=policy, load_bindings=lambda: slots)

    def factory(actual):
        assert actual is runtime
        bound = service._namespace_custody.bound_runtime(actual)
        value, _, _ = provider(tmp_path, actual, owner.reader, selected, bound,
                               authorize=control_auth)
        if after_read:
            original = value._read_mission_v4
            def wrapped(frame):
                result = original(frame)
                after_read(slots)
                return result
            value._read_mission_v4 = wrapped
        return value

    service = ExecutiveControlService(
        _config(tmp_path, socket_root=socket_root, runtime_root=runtime.store.root),
        runtime_factory=lambda _: runtime, supervisor_factory=lambda _: _FakeSupervisor(),
        ceo_ingress_socket_path=socket_root / "ceo.sock",
        ceo_ingress_peer_uid=os.geteuid() + 1000, ceo_ingress_grounding_provider=_FakeGrounding(),
        ceo_ingress_app_binding=CeoIngressAppBinding(peer_uid=os.geteuid(), armed=False,
            grounding_provider=_FakeGrounding(), workspace_read_provider_factory=factory))
    await service.start()
    try:
        app = create_workspace_app(WorkspaceAppConfig(authenticator=auth, now=lambda: NOW,
            authorize_principal=app_auth, client=CeoIngressWorkspaceClient(service.ceo_ingress_socket_path)))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                base_url="https://mcp.mastermind-x.com", follow_redirects=False) as http:
            yield http, tokens, slots
    finally:
        await service.close()


@pytest.mark.parametrize("state", ["accepted", "pending_parent", "missing_consumption", "corrected_source"])
def test_signed_acceptance_read_uses_original_parent_receipt_and_independent_grants(
        tmp_path, monkeypatch, short_socket_root, rsa_key, state):
    with case(tmp_path, monkeypatch, complete=state != "pending_parent",
              consume=state != "missing_consumption") as (runtime, owner, target, basis, selected, _):
        if state == "corrected_source":
            basis.entry["current_intent_revision"] = "corrected-direction"
            restamp(basis.entry)

        async def exercise():
            async with acceptance_transport(runtime, owner, selected, rsa_key, tmp_path,
                                            short_socket_root) as (http, tokens, slots):
                async with _signed_client(http, tokens[MEMBERS[0]]) as a_http:
                    async with _signed_client(http, tokens[MEMBERS[1]]) as b_http:
                        fixed = {k: selected[k] for k in ("work_ref", "root_job_id")}
                        key = selected["request_message_key"]
                        a, b = reader(a_http, fixed), reader(b_http, fixed)
                        events = runtime.events.list_events()
                        first, second = await a.read_acceptance(key), await b.read_acceptance(key)
                        assert first["schema"] == second["schema"] == SCHEMA
                        assert first["fingerprint"] == second["fingerprint"]
                        if state == "accepted":
                            assert first["acceptance"]["state"] == "ACCEPTED"
                            assert card(first, target.job_id)["product_acceptance"] == {
                                "state": "ACCEPTED", "accepted": True, "current": True}
                            assert card(first, target.job_id)["result"]["consumption"] == "PROVEN_BY_ACCEPTANCE_OWNER"
                            aged = await reader(a_http, fixed, clock=lambda: _parse_utc(SOURCE_STAMP) +
                                LOCAL_FRESHNESS_GUARD_SECONDS + 1).read_acceptance(key)
                            assert aged["currentness"]["state"] == "HISTORICAL"
                            assert card(aged, target.job_id)["product_acceptance"]["current"] is False
                            assert card(aged, target.job_id)["decision_needed"] is None
                        else:
                            reason = {"pending_parent": "PARENT_RETURN_UNVERIFIED",
                                "missing_consumption": "PARENT_CONSUMPTION_UNPROVEN",
                                "corrected_source": "SOURCE_CHANGED"}[state]
                            assert first["acceptance"]["state"] == "UNAVAILABLE"
                            assert first["acceptance"]["reason_codes"] == [reason]
                            assert all(c["product_acceptance"]["accepted"] is None for c in first["cards"])
                        slots["profiles"][MEMBERS[0]]["enabled"] = False
                        denied = await a.read_acceptance(key, previous_fingerprint=first["fingerprint"])
                        assert denied["state"] == "REFUSED" and "cards" not in denied
                        survivor = await b.read_acceptance(key, previous_fingerprint=second["fingerprint"])
                        assert survivor["changed"] is False and survivor["cards"]
                        assert runtime.events.list_events() == events
        asyncio.run(exercise())


def test_signed_acceptance_mid_read_revocation_discards_accepted_material(
        tmp_path, monkeypatch, short_socket_root, rsa_key):
    with case(tmp_path, monkeypatch) as (runtime, owner, _, _, selected, _):
        changed = []
        def revoke(slots):
            changed.append(True)
            slots["profiles"][MEMBERS[0]]["binding"]["permission_digest"] = "d" * 64

        async def exercise():
            async with acceptance_transport(runtime, owner, selected, rsa_key, tmp_path,
                    short_socket_root, after_read=revoke) as (http, tokens, _):
                async with _signed_client(http, tokens[MEMBERS[0]]) as enrolled:
                    fixed = {k: selected[k] for k in ("work_ref", "root_job_id")}
                    value = await reader(enrolled, fixed).read_acceptance(selected["request_message_key"])
                    assert value["state"] == "REFUSED" and value["reason_code"] == "access_denied"
                    assert "receipt" not in repr(value) and "cards" not in value
            assert changed == [True]
        asyncio.run(exercise())


@pytest.mark.parametrize("options", [
    {"limit": -1}, {"limit": 33}, {"limit": True}, {"limit": 1.5},
    {"previous_fingerprint": "x" * 64}, {"previous_fingerprint": []},
    {"suppress_unchanged_details": 1},
])
def test_display_options_refuse_before_io_for_every_read(options):
    ref = {"root_job_id": "JOB-1", "job_id": "JOB-2", "attempt_id": "ATT-" + "a" * 32,
           "result_envelope_digest": "b" * 64, "orchestration_role": "work", "validation": "UNVALIDATED"}
    def no_request(_):
        pytest.fail("invalid display options reached transport")
    async def exercise():
        async with mock_reader(no_request) as (team, _, _):
            for read in (team.read_team, lambda **kw: team.read_result(ref, **kw),
                         lambda **kw: team.read_acceptance("asd-mcp-" + "c" * 32, **kw)):
                with pytest.raises(ValueError):
                    await read(**options)
    asyncio.run(exercise())


@pytest.mark.parametrize("change", [
    {"root_job_id": "JOB-OTHER"}, {"work_ref": "WS:OTHER"}, {"job_id": "bad"},
    {"attempt_id": "ATT-wrong"}, {"result_envelope_digest": "bad"},
    {"validation": "VALIDATED"}, {"orchestration_role": "admin"}, {"orchestration_role": []},
    {"Authorization": "caller-controlled"},
])
def test_result_selector_refuses_before_io(change):
    ref = {"root_job_id": "JOB-1", "job_id": "JOB-2", "attempt_id": "ATT-" + "a" * 32,
           "result_envelope_digest": "b" * 64, "orchestration_role": "work", "validation": "UNVALIDATED"}
    ref.update(change)
    async def exercise():
        async with mock_reader(lambda _: pytest.fail("invalid reference sent")) as (team, _, _):
            with pytest.raises(ValueError):
                await team.read_result(ref)
    asyncio.run(exercise())


@pytest.mark.parametrize("key", [None, "", "asd-principal-" + "a" * 32, "asd-mcp-" + "A" * 32, {"key": "x"}])
def test_acceptance_selector_refuses_before_io(key):
    async def exercise():
        async with mock_reader(lambda _: pytest.fail("invalid key sent")) as (team, _, _):
            with pytest.raises(ValueError):
                await team.read_acceptance(key)
    asyncio.run(exercise())


@pytest.mark.parametrize("defect", ["wrong_selection", "changed_role", "source_mismatch", "unavailable"])
def test_atomic_result_response_matches_exact_request_or_discards_both(mission_owner, defect):
    pair = actual_pair(mission_owner)
    ref = reference(pair)
    body = copy.deepcopy(pair)
    if defect == "wrong_selection":
        body["selection"]["result_envelope_digest"] = "e" * 64
    elif defect == "changed_role":
        ref = {**ref, "orchestration_role": "work"}
    elif defect == "source_mismatch":
        body["role_result"]["source_observation"]["control_room"]["document_digest"] = "e" * 64
    else:
        body = pair_contract.unavailable_body(pair["selection"], "SOURCE_CHANGED")
    seen = []
    def respond(request):
        seen.append(request.url.path)
        return httpx.Response(200, json=body)
    async def exercise():
        async with mock_reader(respond, selection=_selection(mission_owner), clock=lambda: NOW) as (team, _, _):
            value = await team.read_result(ref)
            assert value["state"] == "UNAVAILABLE" and "cards" not in value
            if defect == "unavailable":
                assert value["source_reason_codes"] == ["SOURCE_CHANGED"]
            assert seen == ["/workspace/mission-result/current"]
    asyncio.run(exercise())


def test_acceptance_response_cannot_supply_its_own_request_key(tmp_path, monkeypatch):
    body, selected, _ = actual_acceptance(tmp_path, monkeypatch)
    foreign_key = "asd-mcp-" + "f" * 32
    assert foreign_key != selected["request_message_key"]
    seen = []
    def respond(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=body)
    async def exercise():
        fixed = {k: selected[k] for k in ("work_ref", "root_job_id")}
        async with mock_reader(respond, selection=fixed) as (team, _, _):
            value = await team.read_acceptance(foreign_key)
            assert value["state"] == "UNAVAILABLE" and "cards" not in value
            assert value["reason_code"] == "invalid_owner_document"
            assert seen == [{**fixed, "request_message_key": foreign_key}]
    asyncio.run(exercise())


@pytest.mark.parametrize("defect", ["redirect", "server_error", "refused", "accepted_status", "duplicate", "nonfinite", "oversized"])
def test_transport_failure_never_falls_back_or_reuses_cards(defect):
    seen = []
    def respond(request):
        seen.append(request.url.path)
        if len(seen) == 1:
            return httpx.Response(200, json=fixture_mission())
        if defect == "redirect":
            return httpx.Response(307, headers={"location": "https://foreign.invalid/steal"})
        if defect in ("server_error", "refused"):
            return httpx.Response(503 if defect == "server_error" else 403,
                                  json={"error": {"code": "access_denied"}})
        if defect == "accepted_status":
            return httpx.Response(202, json=fixture_mission())
        raw = {"duplicate": b'{"schema": 1, "schema": 2}', "nonfinite": b'{"x": NaN}',
               "oversized": b" " * (MAX_RESPONSE_BYTES + 1)}[defect]
        return httpx.Response(200, content=raw)
    async def exercise():
        async with mock_reader(respond) as (team, _, _):
            first = await team.read_team()
            assert first["cards"]
            failure = await team.read_team(previous_fingerprint=first["fingerprint"])
            assert failure["state"] == ("REFUSED" if defect == "refused" else "UNAVAILABLE")
            assert "cards" not in failure and "fingerprint" not in failure
            assert len(seen) == 2 and set(seen) == {"/workspace/mission/v3/current"}
    asyncio.run(exercise())


def test_unchanged_can_expand_cards_without_reasoning_wake_or_cached_view():
    seen = []
    def respond(request):
        seen.append(request)
        return httpx.Response(200, json=fixture_mission(partial=True))
    async def exercise():
        async with mock_reader(respond) as (team, _, _):
            first = await team.read_team(limit=1)
            expanded = await team.read_team(limit=8, previous_fingerprint=first["fingerprint"])
            quiet = await team.read_team(previous_fingerprint=first["fingerprint"], suppress_unchanged_details=True)
            assert len(expanded["cards"]) > len(first["cards"]) == 1
            assert expanded["changed"] is False and expanded["attention"]["reasoning_wake_recommended"] is False
            assert quiet["cards"] == [] and quiet["coverage"]["unjoined_job_count"] == 2
            assert quiet["coverage"]["unseen_population"] == "UNKNOWN"
            assert len(seen) == 3
    asyncio.run(exercise())


@pytest.mark.parametrize("when", ["before", "during"])
@pytest.mark.parametrize("change", ["selection", "client"])
def test_host_rebinding_withholds_inflight_or_future_view(when, change):
    seen, state = [], {}
    def mutate():
        if change == "selection":
            state["sdk"].selection["work_ref"] = "WS:OTHER"
        else:
            state["sdk"]._workspace = state["replacement"]
    async def respond(request):
        seen.append(request)
        if when == "during":
            mutate()
        return httpx.Response(200, json=fixture_mission())
    async def exercise():
        async with httpx.AsyncClient(base_url="https://other.invalid") as replacement:
            async with mock_reader(respond) as (team, sdk, _):
                state.update(sdk=sdk, replacement=replacement)
                if when == "before":
                    mutate()
                value = await team.read_team()
                assert value["state"] == "REFUSED" and value["reason_code"] == "host_binding_changed"
                assert "cards" not in value and len(seen) == (when == "during")
    asyncio.run(exercise())


def test_reference_is_detached_before_await(mission_owner):
    pair = actual_pair(mission_owner)
    ref = reference(copy.deepcopy(pair))
    async def respond(_):
        ref["job_id"] = "JOB-OTHER"
        return httpx.Response(200, json=pair)
    async def exercise():
        async with mock_reader(respond, selection=_selection(mission_owner), clock=lambda: NOW) as (team, _, _):
            value = await team.read_result(ref)
            assert card(value, pair["selection"]["job_id"])["result"]["state"] == "AVAILABLE"
    asyncio.run(exercise())


def test_concurrent_reader_projections_are_deterministic_and_detached():
    async def exercise():
        all_started = asyncio.Event()
        started = []
        async def respond(request):
            started.append(request)
            if len(started) == 16:
                all_started.set()
            await asyncio.wait_for(all_started.wait(), timeout=2)
            return httpx.Response(200, json=fixture_mission())
        async with mock_reader(respond) as (team, _, _):
            views = await asyncio.gather(*(team.read_team() for _ in range(16)))
            assert len(started) == 16
            assert all(view == views[0] for view in views)
            views[0]["cards"][0]["display_actions"].clear()
            assert views[-1]["cards"][0]["display_actions"] == ["Inspect evidence"]
    asyncio.run(exercise())


def test_read_cancellation_propagates_without_retry_or_partial_view():
    seen = []
    async def cancel(request):
        seen.append(request)
        raise asyncio.CancelledError()
    async def exercise():
        async with mock_reader(cancel) as (team, _, _):
            with pytest.raises(asyncio.CancelledError):
                await team.read_team()
            assert len(seen) == 1
    asyncio.run(exercise())
