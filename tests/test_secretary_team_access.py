"""Secretary SDK contract: exact owner paths, original intent identity, no replay."""
from __future__ import annotations

import asyncio
import copy
import json

import httpx
import pytest

from control_plane.coo_principal_request import (
    normalize_principal_request, principal_request_ref,
)
from control_plane.principal_ruling_target import PrincipalRulingTarget
from integrations.secretary_team_access.client import (
    SecretaryAccessClient, _strict_json,
)
from integrations.secretary_team_access.projection import (
    summarize_native_catalog, summarize_native_status,
)

WORK = "WS:ONE"
ROOT = "JOB-1"
RUN = "ATT-" + "a" * 32
OBLIGATION = "WAKE-" + "a" * 32


def paid_status():
    return {
        "schema": "mastermind.fabric_task_status.v1",
        "run_id": RUN, "root_id": ROOT, "parent_run_id": ROOT,
        "state": "TERMINAL", "rc": 0, "signal": "ok",
        "result_available": True, "result_bytes": 123, "accepted": True,
        "accepted_by": "reviewer", "acceptance_state": "ACCEPTED",
        "acceptance_reason": "VALIDATED_OUTCOME",
    }


def catalog():
    return {
        "schema": "mastermind.attended_fabric_catalog.v1",
        "availability": "PARTIAL", "observed_at": "2026-11-05T10:00:00Z",
        "source": {
            "owner": "ATTENDED_FABRIC", "observation_kind": "CONTROLLER_STATUS_SNAPSHOT",
            "revision": "a" * 64, "scope": "EXACT_RUN_SET", "atomic": False,
            "time_basis": "LOCAL_READ",
        },
        "coverage": {
            "returned_count": 1, "candidate_count": None,
            "omitted_count": None, "scan_complete": False,
            "status_complete": True,
        },
        "items": [{"run_id": RUN, "controller_modified_at": None,
                   "status": paid_status(), "reason_code": None}],
        "reason_codes": ["ROWS_OMITTED"],
    }


def business():
    return {
        "workstream": WORK, "operation_key": "secretary-sdk-test-001",
        "objective": "Inspect the already selected mission and produce a bounded report",
        "department": "engineering", "priority": 2,
        "execution_profile": "research_only",
    }


def response_for_request(req):
    normalized = normalize_principal_request(business(), expected_work_ref=WORK)
    expected = principal_request_ref(normalized)
    return {
        "ok": True, "status": "accepted", "request_ref": expected,
        "receipt": {"request_ref": expected, "accepted": True, "dispatched": False,
                    "job_id": "JOB-42", "status": "QUEUED"},
    }


def authenticated(handler, *, token="role-a"):
    return httpx.AsyncClient(base_url="https://owner.test",
                             transport=httpx.MockTransport(handler),
                             headers={"authorization": "Bearer " + token},
                             follow_redirects=False)


def client(workspace, *, coo=None, ruling=None, target=None):
    return SecretaryAccessClient(work_ref=WORK, root_job_id=ROOT,
                                 workspace=workspace, coo=coo, ruling=ruling,
                                 ruling_target=target, clock=lambda: 1793872800.0)


def test_native_summary_is_bounded_partial_and_churn_stable():
    first = summarize_native_catalog(catalog())
    assert first["availability"] == "PARTIAL"
    assert first["full_fleet"] is False and first["scan_complete"] is False
    assert first["unseen_population"] == "UNKNOWN"
    changed_at = catalog()
    changed_at["observed_at"] = "2026-11-05T10:02:00Z"
    same = summarize_native_catalog(changed_at, previous_fingerprint=first["fingerprint"])
    assert same["changed"] is False and same["items"] == []
    assert same["omitted_detail_count"] == 1
    update = catalog()
    update["items"][0]["status"]["accepted"] = False
    update["items"][0]["status"]["accepted_by"] = None
    update["items"][0]["status"]["acceptance_state"] = "NOT_ACCEPTED"
    update["items"][0]["status"]["acceptance_reason"] = "NO_OUTCOME"
    assert summarize_native_catalog(update, previous_fingerprint=first["fingerprint"])["changed"] is True
    with pytest.raises(ValueError):
        summarize_native_catalog(catalog(), limit=33)
    with pytest.raises(ValueError):
        summarize_native_catalog(catalog(), previous_fingerprint="not-a-digest")


def test_native_status_preserves_execution_acceptance():
    value = summarize_native_status(paid_status(), root_id=ROOT, run_id=RUN)
    assert value["status"]["accepted"] is True
    assert value["status"]["state"] == "TERMINAL"
    assert value["execution_is_not_acceptance"] is True
    with pytest.raises(ValueError):
        summarize_native_status(paid_status(), root_id="foreign", run_id=RUN)


@pytest.mark.parametrize("raw", [
    b'{"ok":true,"ok":false}', b'{"x":NaN}',
    b'{"a":' + b"[" * 35 + b"0" + b"]" * 35 + b"}",
])
def test_strict_json_refuses_duplicate_nonfinite_depth(raw):
    with pytest.raises(ValueError):
        _strict_json(raw)


def test_two_principals_native_read_has_no_credential_or_host_parameter():
    observed = []

    def handler(request):
        observed.append((request.method, request.url.path, request.headers.get("authorization")))
        assert request.method == "GET"
        return httpx.Response(200, json=catalog())

    async def exercise():
        async with authenticated(handler, token="role-a") as a, authenticated(handler, token="role-b") as b:
            sa, sb = client(a), client(b)
            one, two = await sa.read_native_catalog(), await sb.read_native_catalog()
            assert one["fingerprint"] == two["fingerprint"]
            assert "role-" not in json.dumps(one)
    asyncio.run(exercise())
    assert observed == [
        ("GET", "/workspace/fabric/catalog/current", "Bearer role-a"),
        ("GET", "/workspace/fabric/catalog/current", "Bearer role-b"),
    ]


def test_status_selector_is_exact_and_no_native_credential_sharing():
    paths = []

    def handler(request):
        paths.append(str(request.url))
        return httpx.Response(200, json=paid_status())

    async def exercise():
        async with authenticated(handler) as http:
            sdk = client(http)
            result = await sdk.read_native_status(root_id=ROOT, run_id=RUN)
            assert result["status"]["result_bytes"] == 123
            with pytest.raises(ValueError):
                await sdk.read_native_status(root_id=ROOT, run_id="../secret")
    asyncio.run(exercise())
    assert paths == ["https://owner.test/workspace/fabric/status/current?root_id=JOB-1&run_id=" + RUN]


def test_http_refusal_and_malformed_mission_fail_closed():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(403, json={"ok": False,
                                            "error": {"code": "access_denied",
                                                      "message": "PRIVATE_SECRET"}})

    async def exercise():
        async with authenticated(handler) as http:
            out = await client(http).read_mission()
            assert out["state"] == "REFUSED"
            assert out["reason_code"] == "access_denied"
            assert "PRIVATE_SECRET" not in repr(out)
    asyncio.run(exercise())
    assert calls == ["/workspace/mission/v3/current"]


def test_mandate_projection_does_not_grant_action():
    def handler(request):
        assert request.url.path == "/v1/tools/executive_mandate"
        assert json.loads(request.content) == {"arguments": {"work_ref": WORK}}
        return httpx.Response(200, json={
            "ok": True, "data": {
                "schema": "mastermind.coo_principal_mandate.v1",
                "mission": {"work_ref": WORK, "root_job_id": ROOT},
                "new_effect_gate": "FENCED_UNQUALIFIED_MISSION",
                "decision_posture": "READ_RECOMMEND_ONLY",
                "reason_codes": ["source_unavailable"],
                "principal": {"secret": "DO_NOT_COPY"},
            }
        })

    async def exercise():
        async with authenticated(handler) as w, authenticated(handler) as c:
            result = await client(w, coo=c).mandate()
            assert result["new_effect_gate"] == "FENCED_UNQUALIFIED_MISSION"
            assert result["state"] == "OBSERVED"
            assert "DO_NOT_COPY" not in repr(result)
    asyncio.run(exercise())


def test_submit_one_attempt_preserves_req_ref_and_no_dispatch_claim():
    seen = []

    def handler(request):
        seen.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json=response_for_request(request))

    async def exercise():
        async with authenticated(handler) as w, authenticated(handler) as c:
            result = await client(w, coo=c).submit_intent(business())
            assert result["state"] == "ADMISSION_ACCEPTED"
            assert result["job_id"] == "JOB-42"
            assert result["dispatched"] is False
            assert result["replay_authorized"] is False
    asyncio.run(exercise())
    assert len(seen) == 1
    assert seen[0][0] == "/v1/tools/submit_principal_intent"
    assert seen[0][1]["arguments"]["attempt_limit"] == 2


def test_lost_mutation_response_preserves_original_ref_without_retry():
    seen = []

    def handler(request):
        seen.append(request.url.path)
        raise httpx.ReadError("PRIVATE_CANARY")

    async def exercise():
        async with authenticated(handler) as w, authenticated(handler) as c:
            result = await client(w, coo=c).submit_intent(business())
            assert result["state"] == "EFFECT_UNKNOWN"
            assert result["request_ref"].startswith("req-coo-")
            assert "PRIVATE_CANARY" not in repr(result)
            assert result["replay_authorized"] is False
    asyncio.run(exercise())
    assert seen == ["/v1/tools/submit_principal_intent"]


def test_malformed_or_mismatched_submit_reply_remains_unknown():
    for payload in (
        {"ok": True, "status": "accepted", "request_ref": "req-coo-" + "f" * 32},
        {"ok": True, "status": "effect_unknown"},
    ):
        seen = []

        def handler(request):
            seen.append(request.url.path)
            return httpx.Response(200, json=payload)

        async def exercise():
            async with authenticated(handler) as w, authenticated(handler) as c:
                outcome = await client(w, coo=c).submit_intent(business())
                assert outcome["state"] == "EFFECT_UNKNOWN"
        asyncio.run(exercise())
        assert seen == ["/v1/tools/submit_principal_intent"]


def test_reconcile_original_id_never_resubmits():
    selected = principal_request_ref(normalize_principal_request(business(),
                                                                 expected_work_ref=WORK))
    calls = []

    def handler(request):
        calls.append(request.url.path)
        assert json.loads(request.content)["arguments"] == {
            "work_ref": WORK, "request_ref": selected}
        return httpx.Response(200, json={"status": "effect_unknown",
                                         "request_ref": selected})

    async def exercise():
        async with authenticated(handler) as w, authenticated(handler) as c:
            outcome = await client(w, coo=c).reconcile_intent(selected)
            assert outcome["state"] == "EFFECT_UNKNOWN"
            assert outcome["request_ref"] == selected
    asyncio.run(exercise())
    assert calls == ["/v1/tools/principal_intent_status"]


def ruling_arguments():
    return {"authority_class": "WITHIN_COMMISSION", "selected_option": "opt-continue",
            "decision": "continue the existing work", "rationale": "current evidence",
            "evidence_refs": ["https://github.com/example/repo/pull/1"]}


def test_host_bound_ruling_mcp_uses_original_arguments_and_obligation():
    observed = []

    def handler(request):
        assert request.url.path == "/mcp/principal-ruling"
        posted = json.loads(request.content)
        observed.append(posted)
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": 1,
            "result": {"isError": False, "content": [{
                "type": "text", "text": json.dumps({
                    "schema": "mastermind.principal_ruling_forward.v1",
                    "ok": True, "obligation_id": OBLIGATION,
                    "transport": "sent_ok", "result": {"ok": True,
                    "data": {"ruling": "recorded"}},
                }),
            }]},
        })

    async def exercise():
        async with authenticated(handler) as w, authenticated(handler) as r:
            sdk = client(w, ruling=r,
                         target=PrincipalRulingTarget(WORK, OBLIGATION, "coo-host"))
            result = await sdk.rule(ruling_arguments())
            assert result["state"] == "RECORDED"
            assert result["obligation_id"] == OBLIGATION
    asyncio.run(exercise())
    assert len(observed) == 1
    assert observed[0]["params"]["arguments"] == ruling_arguments()
    assert "obligation_id" not in observed[0]["params"]


def test_ruling_lost_response_retains_host_obligation_without_retry():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        raise httpx.ReadError("PRIVATE_CANARY")

    async def exercise():
        async with authenticated(handler) as w, authenticated(handler) as r:
            sdk = client(w, ruling=r,
                         target=PrincipalRulingTarget(WORK, OBLIGATION, "coo-host"))
            result = await sdk.rule(ruling_arguments())
            assert result["state"] == "EFFECT_UNKNOWN"
            assert result["obligation_id"] == OBLIGATION
            assert "PRIVATE_CANARY" not in repr(result)
    asyncio.run(exercise())
    assert calls == ["/mcp/principal-ruling"]


def test_unbound_controls_do_not_send():
    def deny(_request):
        raise AssertionError("unbound control must not send")
    async def exercise():
        async with authenticated(deny) as w:
            sdk = client(w)
            assert (await sdk.mandate())["state"] == "UNBOUND"
            assert (await sdk.submit_intent(business()))["state"] == "UNBOUND"
            assert (await sdk.rule(ruling_arguments()))["state"] == "UNBOUND"
    asyncio.run(exercise())


def test_invalid_business_fields_are_refused_before_send():
    sent = []
    def handler(request):
        sent.append(request.url.path)
        return httpx.Response(200, json={})
    bad = dict(business())
    bad["provider"] = "override"
    async def exercise():
        async with authenticated(handler) as w, authenticated(handler) as c:
            with pytest.raises(ValueError):
                await client(w, coo=c).submit_intent(bad)
    asyncio.run(exercise())
    assert sent == []


def test_http_redirects_cannot_retarget_credentialed_sdk():
    async def exercise():
        async with httpx.AsyncClient(base_url="https://owner.test",
                                     follow_redirects=True) as bad:
            with pytest.raises(ValueError, match="no_redirects"):
                client(bad)
    asyncio.run(exercise())


def test_ambiguous_accepted_202_never_promotes_admission():
    calls = []
    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(202, json=response_for_request(request))
    async def exercise():
        async with authenticated(handler) as w, authenticated(handler) as c:
            outcome = await client(w, coo=c).submit_intent(business())
            assert outcome["state"] == "EFFECT_UNKNOWN"
            assert outcome["replay_authorized"] is False
    asyncio.run(exercise())
    assert calls == ["/v1/tools/submit_principal_intent"]


def test_malformed_public_receipt_job_id_never_exposes_secret():
    def handler(request):
        result = response_for_request(request)
        result["receipt"]["job_id"] = "BEARER PRIVATE_SECRET"
        return httpx.Response(200, json=result)
    async def exercise():
        async with authenticated(handler) as w, authenticated(handler) as c:
            out = await client(w, coo=c).submit_intent(business())
            assert out["state"] == "EFFECT_UNKNOWN"
            assert "PRIVATE_SECRET" not in repr(out)
    asyncio.run(exercise())


def test_native_malformed_acceptance_never_becomes_true():
    altered = paid_status()
    altered["accepted"] = True
    altered["acceptance_state"] = "UNVERIFIED"
    def handler(_request):
        return httpx.Response(200, json=altered)
    async def exercise():
        async with authenticated(handler) as w:
            out = await client(w).read_native_status(root_id=ROOT, run_id=RUN)
            assert out["state"] == "UNAVAILABLE"
    asyncio.run(exercise())


def test_duplicate_json_reply_never_promotes_submit():
    sends = []
    def handler(request):
        sends.append(request.url.path)
        return httpx.Response(200, content=b'{"status":"accepted","status":"accepted"}')
    async def exercise():
        async with authenticated(handler) as w, authenticated(handler) as c:
            out = await client(w, coo=c).submit_intent(business())
            assert out["state"] == "EFFECT_UNKNOWN"
    asyncio.run(exercise())
    assert sends == ["/v1/tools/submit_principal_intent"]


def test_mismatched_ruling_target_does_not_claim_recorded():
    sends = []
    def handler(request):
        sends.append(request.url.path)
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": 1, "result": {
                "content": [{"type": "text", "text": json.dumps({
                    "schema": "mastermind.principal_ruling_forward.v1",
                    "ok": True, "obligation_id": "WAKE-" + "b" * 32,
                    "transport": "sent_ok", "result": {"ok": True},
                })}],
            },
        })
    async def exercise():
        async with authenticated(handler) as w, authenticated(handler) as r:
            out = await client(w, ruling=r, target=PrincipalRulingTarget(
                WORK, OBLIGATION, "coo-host")).rule(ruling_arguments())
            assert out["state"] == "EFFECT_UNKNOWN"
            assert out["obligation_id"] == OBLIGATION
    asyncio.run(exercise())
    assert sends == ["/mcp/principal-ruling"]


def test_submit_cancel_retains_original_identity():
    calls = []
    def handler(request):
        calls.append(request.url.path)
        raise asyncio.CancelledError()
    async def exercise():
        async with authenticated(handler) as w, authenticated(handler) as c:
            out = await client(w, coo=c).submit_intent(business())
            assert out["state"] == "EFFECT_UNKNOWN"
            assert out["request_ref"].startswith("req-coo-")
            assert out["replay_authorized"] is False
    asyncio.run(exercise())
    assert calls == ["/v1/tools/submit_principal_intent"]
