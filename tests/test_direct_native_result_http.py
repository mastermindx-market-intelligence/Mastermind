"""Real signed-token HTTP qualification; private transport is inert/mocked.

These checks do not qualify a Runtime result or consumption Event. The joined
owner fixture, separately, must supply real Supervisor retained evidence.
"""
import unittest
import dataclasses
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from cryptography.hazmat.primitives.asymmetric import rsa

from common import direct_native_result_contract as c
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.mastermind_executive_app.direct_native import DirectNativeResultClient
from integrations.mastermind_executive_app.gateway import CeoIngressClient, CeoIngressResponse, TRANSPORT_SENT_OK, TRANSPORT_SENT_UNKNOWN
from integrations.mastermind_executive_app.os_transport import OsExecutiveTransportApp
from tests import test_mastermind_executive_app_asgi as auth_fixture


class AuditSink:
    def __init__(self): self.events = []
    def emit(self, event): self.events.append(event)


async def unused_inner(_scope, _receive, _send):
    raise AssertionError("direct request entered another App operation")


class DirectResultHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.clock = auth_fixture.NOW
        policy = auth_fixture._submit_policy()
        authenticator = JwtAuthenticator(policy=policy, jwks_cache=auth_fixture._FakeJwksCache(self.key))
        self.client = CeoIngressClient()
        self.owner = OsExecutiveTransportApp(unused_inner,
            submit_verifier=MastermindTokenVerifier(authenticator=authenticator, policy=policy,
                now=lambda: self.clock, audit_sink=AuditSink()), submit_authenticator=authenticator,
            clock=lambda: self.clock,
            direct_result_client=DirectNativeResultClient("/fixture/ceo-ingress.sock", self.client))
        self.body = dict(work_ref="WS:H2", job_id="JOB-h2", attempt_id="ATT-h2")
        self.payload = dict(summary="Findings", current_state="Complete", completed_steps=[], next_actions=[])
        self.headers = {"host": "mcp.mastermind-x.com", "authorization": "Bearer " + auth_fixture._submit_token(self.key)}
        self.result = c.available(self.body, self.payload, "a" * 64, dict(state="UNCONSUMED", receipt_digest=None))

    async def post(self, path, body, *, headers=None):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.owner),
                                     base_url="https://mcp.mastermind-x.com") as http:
            return await http.post(path, json=body, headers=self.headers if headers is None else headers)

    async def test_normal_factory_mounts_direct_routes_with_its_actual_client(self):
        from tests import test_mastermind_os_executive_transport as mounted_fixture
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = dataclasses.replace(auth_fixture._real_app_settings(self.key,
                mastermind_root=root / "mastermind", macro_root=root / "macro",
                ceo_ingress_socket_path=root / "ceo.sock"), read_from_ceo_ingress=True)
            app = mounted_fixture._v3_app(settings)
            actual = app.os_transport._direct_result_client.client
            self.assertIs(type(actual), CeoIngressClient)
            with patch.object(actual, "send_frame", new=AsyncMock(return_value=CeoIngressResponse(
                    transport=TRANSPORT_SENT_OK, ok=True, result=self.result))) as send:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                        base_url="https://mcp.mastermind-x.com") as http:
                    response = await http.post(c.RESULT_PATH, json=self.body, headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), self.result)
            self.assertEqual(send.await_count, 1)

    async def test_actual_signed_principal_supplies_only_private_scope(self):
        with patch.object(self.client, "send_frame", new=AsyncMock(return_value=CeoIngressResponse(
                transport=TRANSPORT_SENT_OK, ok=True, result=self.result))) as send:
            response = await self.post(c.RESULT_PATH, self.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.result)
        self.assertEqual(send.await_count, 1)
        frame = send.await_args.args[1]
        self.assertEqual(set(frame), set(self.body) | {"schema", "operation", "principal_scope"})
        c.hex_digest(frame["principal_scope"])
        self.assertEqual(frame["operation"], "result")
        self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_original_context_does_not_enter_direct_transport(self):
        with patch.object(self.client, "send_frame", new=AsyncMock(side_effect=AssertionError("direct call"))) as send:
            response = await self.post("/os/executive/context", {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(send.await_count, 0)
        self.assertNotEqual(response.json().get("schema"), c.SCHEMA)

    async def test_invalid_auth_and_caller_identity_injection_never_forward(self):
        with patch.object(self.client, "send_frame", new=AsyncMock(side_effect=AssertionError("forwarded"))) as send:
            denied = await self.post(c.RESULT_PATH, self.body, headers={"host": "mcp.mastermind-x.com"})
            injected = await self.post(c.RESULT_PATH, dict(self.body, principal_scope="b" * 64))
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(injected.status_code, 400)
        self.assertEqual(send.await_count, 0)

    async def test_null_attempt_discovers_only_same_actual_job(self):
        with patch.object(self.client, "send_frame", new=AsyncMock(return_value=CeoIngressResponse(
                transport=TRANSPORT_SENT_OK, ok=True, result=self.result))) as send:
            response = await self.post(c.RESULT_PATH, dict(self.body, attempt_id=None))
        self.assertEqual(response.json()["selection"], self.body)
        self.assertIsNone(send.await_args.args[1]["attempt_id"])

    async def test_wrong_job_reply_is_not_disclosed(self):
        wrong = dict(self.result, selection=dict(self.body, job_id="JOB-other"))
        with patch.object(self.client, "send_frame", new=AsyncMock(return_value=CeoIngressResponse(
                transport=TRANSPORT_SENT_OK, ok=True, result=wrong))):
            response = await self.post(c.RESULT_PATH, self.body)
        self.assertEqual(response.status_code, 503)
        self.assertIsNone(response.json()["result"])

    async def test_explicit_consume_is_distinct_and_lost_reply_has_no_false_ack(self):
        request = dict(self.body, operation_key="consume-h2", result_digest="a" * 64)
        with patch.object(self.client, "send_frame", new=AsyncMock(return_value=CeoIngressResponse(
                transport=TRANSPORT_SENT_UNKNOWN))) as send:
            response = await self.post(c.CONSUME_PATH, request)
        self.assertEqual(send.await_count, 1)
        self.assertEqual(send.await_args.args[1]["operation"], "consume")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["reason_codes"], ["EFFECT_UNKNOWN"])
        self.assertIsNone(response.json()["consumption"])

    async def test_late_expiry_withholds_completed_consumption_reply(self):
        consumed = dict(self.result, consumption=dict(state="CONSUMED", receipt_digest="d" * 64))
        async def late(*_):
            self.clock += 3600
            return CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=True, result=consumed)
        with patch.object(self.client, "send_frame", new=AsyncMock(side_effect=late)) as send:
            response = await self.post(c.CONSUME_PATH, dict(self.body,
                operation_key="consume-h2", result_digest="a" * 64))
        self.assertEqual(send.await_count, 1)
        self.assertEqual(response.status_code, 202)
        self.assertIsNone(response.json()["consumption"])

    async def test_bad_consume_digest_and_null_attempt_never_forward(self):
        with patch.object(self.client, "send_frame", new=AsyncMock(side_effect=AssertionError("forwarded"))) as send:
            for request in (dict(self.body, operation_key="consume-h2", result_digest="wrong"),
                    dict(self.body, attempt_id=None, operation_key="consume-h2", result_digest="a" * 64)):
                response = await self.post(c.CONSUME_PATH, request)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(send.await_count, 0)


if __name__ == "__main__":
    unittest.main()
