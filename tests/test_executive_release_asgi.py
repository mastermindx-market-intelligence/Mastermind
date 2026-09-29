"""Real JWT -> real Unix Control -> real broker handlers -> canonical Runtime.

Root/service qualification and enrolled policy/key observations are explicitly
synthetic. These tests neither activate production nor substitute for A2's
installed same-UID process-instance proof.
"""
import asyncio
import copy
import dataclasses
import hashlib
import os

import pytest

from control_plane.executive_authority import ReleaseControllerPolicy
from control_plane import executive_release_consumer as consumer
from control_plane.executive_service import ExecutiveControlService, CeoIngressAppBinding
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.mastermind_executive_app import app as app_module
from integrations.mastermind_executive_app import release_admission
from integrations.mastermind_executive_app.gateway import (
    make_jwt_authenticators, CeoIngressClient, CeoIngressResponse, TRANSPORT_SENT_OK,
)
from tests import test_mastermind_executive_app_asgi as web
from tests.test_executive_release_consumer import installed, inputs, approve_arguments, counts
from tests.test_executive_release_controller_policy import source

rsa_key = web.rsa_key
other_rsa_key = web.other_rsa_key
short_socket_root = web.short_socket_root


def test_authenticated_vertical_and_rotated_token_replay(installed, rsa_key, other_rsa_key,
                                                        tmp_path, short_socket_root, monkeypatch):
    async def exercise():
        settings = dataclasses.replace(web._real_app_settings(rsa_key,
            mastermind_root=tmp_path, macro_root=tmp_path,
            ceo_ingress_socket_path=short_socket_root / "release.sock"),
            read_from_ceo_ingress=True, clock=lambda: installed["now"][0] // 1000)
        installed["now"][0] = web.NOW * 1000
        token = web._submit_token(rsa_key)
        _, verifier = make_jwt_authenticators(settings.policies, jwks_cache=settings.jwks_cache)
        verified = await verifier.verify_authorization_header("Bearer " + token, now=web.NOW)
        principal = principal_projection(verified)
        prior = installed["states"][0]
        policy_fields = {
            "schema": "mastermind.executive_release_controller_policy/v1",
            "policy_id": principal.policy_id, "generation": 1, "enabled": True,
            "issuer_digest": principal.issuer_digest,
            "resource_digest": hashlib.sha256(principal.resource.encode()).hexdigest(),
            "subject_digests": [principal.subject_digest], "client_refs": [principal.client_ref],
            "required_scopes": list(principal.scopes), "actions": [prior.effect["action"]],
            "target_refs": [prior.target_ref], "installer_profile_digests": [prior.effect["installer_profile_digest"]],
            "source_policy_modes": [prior.effect["source_policy_mode"]],
            "max_approval_lifetime_seconds": 300, "confirmation_requirement": "delegated",
        }
        policy = ReleaseControllerPolicy.from_bytes(source(policy_fields))
        installed["states"][0] = dataclasses.replace(prior, policy=policy,
            preconditions={**prior.preconditions, "authority_policy_hash": policy.sha256})
        class NoReads:
            def observe(self):
                pytest.fail("release calls do not need a separate read backend")
            async def call(self, *args):
                pytest.fail("release calls must not route through the read gateway")
            async def aclose(self):
                pass
        readers = NoReads()
        service = ExecutiveControlService(web._service_config(tmp_path, socket_root=short_socket_root),
            supervisor_factory=lambda _: web._NoExecutionSupervisor(), service_state="READY",
            ceo_ingress_socket_path=settings.ceo_ingress_socket_path,
            ceo_ingress_peer_uid=os.geteuid() + 1000, ceo_ingress_grounding_provider=readers,
            ceo_ingress_armed=False, ceo_ingress_app_binding=CeoIngressAppBinding(
                peer_uid=os.geteuid(), armed=False, grounding_provider=readers, read_provider=readers))
        frames = []
        original_send = CeoIngressClient.send_frame
        async def observe_send(self, path, frame):
            frames.append(frame)
            return await original_send(self, path, frame)
        monkeypatch.setattr(CeoIngressClient, "send_frame", observe_send)
        app = app_module.create_release_control_app(settings)
        await service.start()
        try:
            before = counts(service.runtime)
            async with web._async_client(app) as http:
                args = approve_arguments(installed)
                url = "/v1/tools/approve_release_transition"
                # Signature, scope and expiry failure happen before transport.
                for denied_token in (None, web._read_token(rsa_key), web._submit_token(other_rsa_key),
                                     web._submit_token(rsa_key, iat=web.NOW-800, exp=web.NOW-100)):
                    headers = {} if denied_token is None else {"Authorization": "Bearer " + denied_token}
                    denied = await http.post(url, json={"arguments": args}, headers=headers)
                    assert denied.status_code in (401, 403), denied.json()
                assert not frames
                headers = {"Authorization": "Bearer " + token}
                for malformed in ('{"arguments":{},"arguments":{}}', '{"arguments":{},"principal":{}}'):
                    denied = await http.post(url, content=malformed, headers=headers)
                    assert denied.status_code == 400
                assert not frames
                response = await http.post(url, json={"arguments": args}, headers=headers)
                approved = response.json()
                assert response.status_code == 200 and approved["ok"] is True, approved
                assert len(frames) == 1 and frames[0]["principal"]["subject_digest"] == principal.subject_digest
                assert "jti_digest" not in frames[0]["principal"] and token not in str(frames[0])
                installed["now"][0] += 1000
                rotated = web._submit_token(rsa_key, iat=web.NOW+1, nbf=web.NOW+1,
                                            exp=web.NOW+301, jti="rotated-test-jti")
                headers = {"Authorization": "Bearer " + rotated}
                replay = await http.post(url, json={"arguments": args}, headers=headers)
                assert replay.json() == approved
                prepared = await http.post("/v1/tools/prepare_release_transition", headers=headers,
                    json={"arguments": {"operation_key": args["operation_key"],
                                         "approved_transition_ref": approved["approved_transition_ref"]}})
                assert prepared.json()["ok"] is True, prepared.json()
                commit = await http.post("/v1/tools/commit_prepared_release_transition", headers=headers,
                    json={"arguments": {"prepared_token": prepared.json()["prepared_token"]}})
                assert commit.json()["error"]["code"] == "RELEASE_COMMIT_DISARMED"
                history = await http.post("/v1/tools/reconcile_release_transition", headers=headers,
                    json={"arguments": {"operation_key": args["operation_key"]}})
                assert history.json()["approval"]["approved_transition_ref"] == approved["approved_transition_ref"]
                assert history.json()["broker_status"]["state"] == "NOT_FOUND"
            assert counts(service.runtime) == (before[0]+1, before[1], before[2])
            assert installed["root_broker"]._executor.calls == []
            assert all(pid == os.getpid() for _, pid in installed["peer_calls"])
        finally:
            await app.aclose()
            await service.close()
    asyncio.run(exercise())


def test_existing_web_profile_does_not_acquire_release_routes(rsa_key, tmp_path, short_socket_root):
    settings = dataclasses.replace(web._real_app_settings(rsa_key, mastermind_root=tmp_path,
        macro_root=tmp_path, ceo_ingress_socket_path=short_socket_root / "absent.sock"),
        read_from_ceo_ingress=True)
    async def exercise():
        app = app_module.create_web_ceo_v2_app(settings)
        try:
            async with web._async_client(app) as http:
                result = await http.post("/v1/tools/approve_release_transition",
                    headers={"Authorization": "Bearer " + web._submit_token(rsa_key)}, json={"arguments": {}})
                assert result.status_code == 404
        finally:
            await app.aclose()
    asyncio.run(exercise())


@pytest.mark.parametrize("operation", ["approve_release_transition", "prepare_release_transition",
                                     "reconcile_release_transition", "commit_prepared_release_transition"])
def test_closed_responses_preserve_valid_values_and_refuse_leaks(installed, monkeypatch, operation):
    args = approve_arguments(installed)
    approved = installed["call"]("approve_release_transition", args)
    arguments = {
        "approve_release_transition": args,
        "prepare_release_transition": {"operation_key": args["operation_key"],
                                       "approved_transition_ref": approved["approved_transition_ref"]},
        "reconcile_release_transition": {"operation_key": args["operation_key"]},
        "commit_prepared_release_transition": {"prepared_token": "inert"},
    }[operation]
    original = installed["call"](operation, arguments)
    monkeypatch.setattr(release_admission, "principal_projection", lambda _: installed["principal"])
    class Transport:
        def __init__(self, result):
            self.result, self.calls = result, 0
        async def send_frame(self, *args):
            self.calls += 1
            return CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=True, result=self.result)
    def send(value):
        channel = Transport(value)
        result = asyncio.run(release_admission.compose_release_admission(operation=operation,
            arguments=arguments, principal=object(), client=channel, socket_path="unused"))
        assert channel.calls == 1
        return result
    assert send(original) == original
    variants = [{**original, "private_debug": "PRIVATE_SENTINEL"},
                {**original, "operation": "wrong"},
                {"schema": original["schema"], "operation": operation, "ok": False,
                 "error": {"code": "PRIVATE_SENTINEL"}}]
    if operation == "approve_release_transition":
        variants += [{k: v for k, v in original.items() if k != "approved_transition_ref"},
                     {**original, "approved_transition_ref": "wrong"},
                     {**original, "approval_evidence_digest": {"secret": "PRIVATE_SENTINEL"}}]
    elif operation == "prepare_release_transition":
        variants += [{**original, "prepared_token": {}}, {**original, "expires_at_ms": True},
                     {**original, "preview": {**original["preview"], "private": "PRIVATE_SENTINEL"}},
                     {**original, "preview": {**original["preview"], "target_ref": "bad"}}]
    elif operation == "reconcile_release_transition":
        foreign = copy.deepcopy(original)
        foreign["approval"]["principal_projection"]["subject_digest"] = "f" * 64
        variants += [foreign, {**original, "approval": None},
                     {**original, "broker_status": {**original["broker_status"], "request_id": "wrong"}},
                     {**original, "broker_status": {**original["broker_status"], "private": "PRIVATE_SENTINEL"}}]
    else:
        variants += [{**original, "ok": True}]
    for value in variants:
        answer = send(value)
        assert answer == {"ok": False, "error": {"code": "RELEASE_RESPONSE_UNKNOWN"},
                          "effect": "EFFECT_UNKNOWN"}


def test_lost_postcommit_readback_reconciles_without_second_event(installed, monkeypatch,
                                                               tmp_path, short_socket_root):
    monkeypatch.setattr(release_admission, "principal_projection", lambda _: installed["principal"])
    original = consumer.ReleaseControlConsumer._read
    lost = []
    def lose_first(self, key):
        record = original(self, key)
        if record is not None and not lost:
            lost.append(True)
            return None
        return record
    monkeypatch.setattr(consumer.ReleaseControlConsumer, "_read", lose_first)
    class NoReads:
        def observe(self):
            pytest.fail("unexpected read route")
        async def call(self, *args):
            pytest.fail("unexpected read route")
        async def aclose(self):
            pass
    async def exercise():
        readers = NoReads()
        path = short_socket_root / "lost.sock"
        service = ExecutiveControlService(web._service_config(tmp_path, socket_root=short_socket_root),
            supervisor_factory=lambda _: web._NoExecutionSupervisor(), service_state="READY",
            ceo_ingress_socket_path=path, ceo_ingress_peer_uid=os.geteuid() + 1000,
            ceo_ingress_grounding_provider=readers, ceo_ingress_armed=False,
            ceo_ingress_app_binding=CeoIngressAppBinding(peer_uid=os.geteuid(), armed=False,
                grounding_provider=readers, read_provider=readers))
        await service.start()
        try:
            before = counts(service.runtime)
            args = approve_arguments(installed)
            async def send(operation, arguments):
                return await release_admission.compose_release_admission(operation=operation,
                    arguments=arguments, principal=object(), client=CeoIngressClient(), socket_path=path)
            result = await send("approve_release_transition", args)
            assert lost and result["effect"] == "EFFECT_UNKNOWN"
            assert result["error"]["code"] == "RELEASE_APPROVAL_READBACK_UNKNOWN"
            after = (before[0] + 1, before[1], before[2])
            assert counts(service.runtime) == after
            recovered = await send("reconcile_release_transition", {"operation_key": args["operation_key"]})
            assert recovered["ok"] is True and recovered["approval"]["operation_key"] == args["operation_key"]
            assert recovered["broker_status"]["state"] == "NOT_FOUND"
            assert counts(service.runtime) == after
            assert installed["root_broker"]._executor.calls == []
        finally:
            await service.close()
    asyncio.run(exercise())


@pytest.mark.parametrize("state", [
    "NOT_FOUND", "STARTED", "PUBLISHED", "BROKER_RESTART_PENDING", "RECOVERING",
    "SUCCEEDED", "ROLLED_BACK", "FAILED_NOT_APPLIED",
])
def test_both_transport_validators_admit_only_qualified_terminal_or_absent_shapes(installed, state):
    from tests.test_executive_release_consumer import typed_history
    from control_plane import executive_release_ingress as ingress
    from integrations.executive_mcp import release_control
    args = approve_arguments(installed)
    installed["call"]("approve_release_transition", args)
    approval = installed["control"]._read(args["operation_key"])
    value = {"schema": ingress.RESPONSE_SCHEMA, "operation": "reconcile_release_transition", "ok": True,
             "approval": approval.to_dict(), "broker_status": typed_history(approval, state)}
    kwargs = {"operation": value["operation"], "arguments": {"operation_key": args["operation_key"]},
              "principal": installed["principal"]}
    before = counts(installed["runtime"])
    if state in {"NOT_FOUND", "SUCCEEDED", "ROLLED_BACK", "FAILED_NOT_APPLIED"}:
        assert release_admission._closed_result(value, **kwargs) == value
        assert release_control.valid_release_result(value, value["operation"], kwargs["arguments"], 200)
    else:
        with pytest.raises(ValueError):
            release_admission._closed_result(value, **kwargs)
        assert not release_control.valid_release_result(value, value["operation"], kwargs["arguments"], 200)
    assert counts(installed["runtime"]) == before


@pytest.mark.parametrize("mutation", ["p2", "full_fingerprint", "admission", "receipt", "extra"])
def test_both_transport_validators_reject_unqualified_terminal_evidence(installed, mutation):
    from tests.test_executive_release_consumer import typed_history
    from control_plane import executive_release_ingress as ingress
    from integrations.executive_mcp import release_control
    args = approve_arguments(installed)
    installed["call"]("approve_release_transition", args)
    approval = installed["control"]._read(args["operation_key"])
    status = typed_history(approval, "SUCCEEDED")
    if mutation == "p2":
        status = {"request_id": status["request_id"], "status": "SUCCEEDED", "exit_code": 0}
    elif mutation == "full_fingerprint":
        status["request_fingerprint"] = status["request_fingerprint"][:48] + "f" * 16
    elif mutation == "admission":
        status["admission"]["maintenance_sequence"] += 1
    elif mutation == "receipt":
        status["terminal_receipt"]["after"]["release_commit"] = "f" * 40
    else:
        status["private_debug"] = "PRIVATE_SENTINEL"
    value = {"schema": ingress.RESPONSE_SCHEMA, "operation": "reconcile_release_transition", "ok": True,
             "approval": approval.to_dict(), "broker_status": status}
    arguments = {"operation_key": args["operation_key"]}
    with pytest.raises(ValueError):
        release_admission._closed_result(value, operation=value["operation"], arguments=arguments,
                                         principal=installed["principal"])
    assert not release_control.valid_release_result(value, value["operation"], arguments, 200)
