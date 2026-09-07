"""Hermetic authenticated MCP-to-descriptor composition proof.

Each assertion names the shortcut it detects: a callback in place of the
descriptor port, an inline executor, cross-wired project output, omitted
post-await binding/auth fences, or model-selected authority fields.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
import pathlib
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from integrations.business_mcp_auth.contracts import load_resource_policy, subject_digest
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.workbench_read_mcp.app import ProjectReadRefused, ReadCaller, create_authenticated_read_server
from integrations.workbench_read_mcp import app as app_module
from integrations.workbench_read_mcp.observer import ReadScope
from integrations.workbench_read_mcp.read_port import ProjectReadBinding, create_descriptor_read_port
from integrations.workbench_read_mcp import observer as observer_module
from integrations.workbench_read_mcp import read_port as read_port_module
from integrations.business_mcp_auth import mcp_adapter as adapter_module

ISSUER = "https://identity.workbench.example"
RESOURCE = "https://workbench.example/mcp"
SCOPE = "workbench.read"
CLIENT_REF = hashlib.sha256((ISSUER + "\nclient\nfixture-client").encode("utf-8")).hexdigest()
DEFAULT_TOKEN = object()
OUTPUT = {"type": "object", "required": ["status", "project_ref", "content", "file_sha256"],
          "properties": {"status": {"const": "OK"}, "project_ref": {"type": "string"},
                         "content": {"type": "string"}, "file_sha256": {"type": "string"}}}


class _Keys:
    def __init__(self, jwk): self.jwk = jwk
    async def key_for(self, kid):
        if kid != "fixture-key": raise ValueError("unknown fixture key")
        return self.jwk


class _Audit:
    def __init__(self): self.events, self.fail, self.fail_after = [], False, None
    def emit(self, event):
        if self.fail or (self.fail_after is not None and len(self.events) >= self.fail_after):
            raise RuntimeError("private audit failure")
        self.events.append(dataclasses.asdict(event))


class FullCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mmx-full-composition-")
        self.root = pathlib.Path(self.temp.name); self.clock = int(time.time()); self.closed = False
        self.subjects = {u: subject_digest(issuer=ISSUER, subject=u) for u in ("alpha-user", "beta-user")}
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())); jwk.update(kid="fixture-key", alg="RS256", use="sig")
        policy = load_resource_policy({"schema":"mastermind.business_mcp_auth_policy.v1", "policy_id":"fixture.workbench.read", "resource":RESOURCE, "resource_metadata_url":RESOURCE+"/.well-known/oauth-protected-resource/mcp", "issuer":ISSUER, "authorization_servers":[ISSUER], "jwks_uri":ISSUER+"/jwks", "required_scopes":[SCOPE], "allowed_subject_digests":sorted(self.subjects.values()), "allowed_algorithms":["RS256"], "clock_skew_seconds":0, "max_token_lifetime_seconds":3600, "jwks_cache_ttl_seconds":60, "unknown_kid_refresh_cooldown_seconds":1, "fetch_failure_backoff_seconds":1})
        self.policy = policy; self.audit = _Audit(); self.auth = JwtAuthenticator(policy=policy, jwks_cache=_Keys(jwk))
        self.io_calls = self.executed_operations = self.resolve_calls = 0
        self.active = True; self.mode = "normal"; self.admission_limit = 1
        self.return_transform = lambda result: result
        self.cancellation_drains = 0
        self.outstanding = self.max_outstanding = 0; self.worker_threads = set()
        self.admitted = asyncio.Event(); self.release = asyncio.Event()
        self.both_admitted = asyncio.Event(); self.barrier_count = 0
        self.fds = []; self.bindings = {}
        for project, user in (("alpha", "alpha-user"), ("beta", "beta-user")):
            directory = self.root / project; directory.mkdir(); (directory / "sentinel.txt").write_text(f"{project} sentinel\n", encoding="utf-8")
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY); self.fds.append(fd); stat = os.fstat(fd)
            # Defect target: a manually readable client_id must never be used as
            # the verifier's pseudonymous client projection.
            caller = ReadCaller(self.subjects[user], CLIENT_REF, RESOURCE, (SCOPE,), self.clock + 600)
            scope = ReadScope(fd, stat.st_dev, stat.st_ino, f"ctx-{project}", f"owner-{project}", "g1", ("sentinel.txt",), (self.clock + 500) * 1000, "a" * 40)
            self.bindings[(caller.subject_digest, project)] = ProjectReadBinding(caller, project, scope)
        def resolve(caller, project):
            self.resolve_calls += 1
            if not self.active: raise ProjectReadRefused()
            return self.bindings.get((caller.subject_digest, project))
        async def run_io(operation):
            if self.mode == "reject-admission" or self.outstanding >= self.admission_limit:
                raise RuntimeError("fixture bounded-executor rejection")
            self.io_calls += 1; self.outstanding += 1; self.max_outstanding = max(self.max_outstanding, self.outstanding)
            try:
                if self.mode == "block-after-admission":
                    self.admitted.set()
                    await self.release.wait()
                if self.mode == "concurrent-barrier":
                    self.barrier_count += 1
                    if self.barrier_count == 2: self.both_admitted.set()
                    await self.release.wait()
                if self.mode == "revoke-queued": self.active = False
                if self.mode == "change-queued":
                    key = (self.subjects["alpha-user"], "alpha"); binding = self.bindings[key]
                    self.bindings[key] = dataclasses.replace(binding, scope=dataclasses.replace(binding.scope, generation="g2"))
                def execute():
                    self.worker_threads.add(threading.get_ident())
                    self.executed_operations += 1
                    return operation()
                worker = asyncio.create_task(asyncio.to_thread(execute))
                try:
                    result = await asyncio.shield(worker)
                except asyncio.CancelledError:
                    # The admitted kernel operation owns its descriptor until it
                    # finishes. Drain it exactly once before releasing fixture
                    # resources, then preserve the caller's cancellation.
                    self.cancellation_drains += 1
                    await asyncio.shield(worker)
                    raise
                if self.mode == "revoke-after": self.active = False
                if self.mode == "auth-policy-change-after":
                    self.auth._policy = dataclasses.replace(self.policy, policy_id="fixture.policy.drift")
                if self.mode == "change-after":
                    key = (self.subjects["alpha-user"], "alpha"); binding = self.bindings[key]
                    self.bindings[key] = dataclasses.replace(binding, scope=dataclasses.replace(binding.scope, generation="g2"))
                return self.return_transform(result)
            finally:
                self.outstanding -= 1
        self.port = create_descriptor_read_port(resolve_binding=resolve, clock_ms=lambda: self.clock * 1000, run_io=run_io)
        self.server = create_authenticated_read_server(authenticator=self.auth, policy=policy, now=lambda: self.clock, audit_sink=self.audit, read_port=self.port, output_schema=OUTPUT, allowed_hosts=("127.0.0.1", "127.0.0.1:*"))
        self.app = self.server.streamable_http_app(); self.ready = asyncio.Event(); self.stop = asyncio.Event()
        async def lifespan():
            async with self.app.router.lifespan_context(self.app): self.ready.set(); await self.stop.wait()
        self.life = asyncio.create_task(lifespan()); await asyncio.wait_for(self.ready.wait(), 5)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://127.0.0.1")

    async def asyncTearDown(self):
        await self.client.aclose(); self.stop.set(); await asyncio.wait_for(self.life, 5)
        for fd in self.fds: os.close(fd)
        self.temp.cleanup(); self.closed = True
        self.assertEqual(self.outstanding, 0, "fixture bounded executor must drain before descriptor closure")

    def token(self, user="alpha-user", **patch):
        payload = {"iss":ISSUER, "sub":user, "aud":RESOURCE, "iat":self.clock-1, "exp":self.clock+600, "scope":SCOPE, "client_id":"fixture-client"}; payload.update(patch)
        return jwt.encode(payload, self.pem, algorithm="RS256", headers={"kid":"fixture-key"})

    async def rpc(self, method, params=None, token=None):
        headers = {"Accept":"application/json, text/event-stream", "MCP-Protocol-Version":"2025-03-26"}
        if token: headers["Authorization"] = "Bearer " + token
        return await self.client.post("/mcp", headers=headers, json={"jsonrpc":"2.0", "id":1, "method":method, "params":params or {}})

    async def call(self, token=DEFAULT_TOKEN, project="alpha", **extra):
        arguments = {"project_ref":project, "relative_path":"sentinel.txt", **extra}
        # Defect target: an omitted bearer token must not be replaced by the
        # fixture's default credential when exercising the real MCP boundary.
        selected_token = self.token() if token is DEFAULT_TOKEN else token
        return await self.rpc("tools/call", {"name":"read_project_file", "arguments":arguments}, selected_token)

    def result(self, response):
        self.assertEqual(response.status_code, 200, response.text[:300]); return response.json()["result"]

    def successful_data(self, result):
        """Accept the SDK's structured form while preserving a precise fallback diagnostic."""
        self.assertFalse(result.get("isError", False), result)
        if "structuredContent" in result:
            return result["structuredContent"]
        self.assertEqual(result.get("content", [{}])[0].get("type"), "text", result)
        return json.loads(result["content"][0]["text"])

    async def one_off_call(self, port, *, arguments=None):
        """Run an isolated real FastMCP app without a listener or shared state."""
        server = create_authenticated_read_server(
            authenticator=self.auth, policy=self.policy, now=lambda: self.clock,
            audit_sink=self.audit, read_port=port, output_schema=OUTPUT,
            allowed_hosts=("127.0.0.1", "127.0.0.1:*"),
        )
        app = server.streamable_http_app(); ready = asyncio.Event(); stop = asyncio.Event()
        async def lifespan():
            async with app.router.lifespan_context(app):
                ready.set()
                await stop.wait()
        life = asyncio.create_task(lifespan())
        await asyncio.wait_for(ready.wait(), 5)
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1")
        try:
            response = await client.post(
                "/mcp",
                headers={"Accept":"application/json, text/event-stream", "MCP-Protocol-Version":"2025-03-26",
                         "Authorization":"Bearer " + self.token()},
                json={"jsonrpc":"2.0", "id":1, "method":"tools/call",
                      "params":{"name":"read_project_file", "arguments":arguments or {"project_ref":"alpha", "relative_path":"sentinel.txt"}}},
            )
            return self.result(response)
        finally:
            await client.aclose(); stop.set(); await asyncio.wait_for(life, 5)

    async def test_real_sdk_initialize_list_and_descriptor_result(self):
        # Detects a fake callback replacing create_descriptor_read_port or an inline executor.
        self.assertIn("serverInfo", self.result(await self.rpc("initialize", {"protocolVersion":"2025-03-26", "capabilities":{}, "clientInfo":{"name":"full","version":"1"}}, self.token())))
        tools = self.result(await self.rpc("tools/list", token=self.token()))["tools"]
        self.assertEqual([tool["name"] for tool in tools], ["read_project_file"])
        self.assertTrue(tools[0]["annotations"]["readOnlyHint"])
        self.assertFalse(tools[0]["annotations"]["destructiveHint"])
        body = self.successful_data(self.result(await self.call()))
        # Detects a callback returning invented bytes, metadata, or cursor fields.
        self.assertEqual(body["content"], "alpha sentinel\n"); self.assertEqual(body["project_ref"], "alpha")
        self.assertEqual(body["file_sha256"], hashlib.sha256(b"alpha sentinel\n").hexdigest())
        self.assertEqual((body["context_ref"], body["owner_ref"], body["generation"]), ("ctx-alpha", "owner-alpha", "g1"))
        self.assertEqual(body["committed_head"], "a" * 40)
        self.assertEqual((body["line_start"], body["line_end"], body["total_lines"], body["next_line"]), (0, 1, 1, None))
        self.assertEqual((self.io_calls, self.executed_operations), (1, 1))
        audit = json.dumps(self.audit.events)
        self.assertNotIn("alpha-user", audit); self.assertNotIn(self.token(), audit)

    async def test_auth_project_and_model_authority_refusals_precede_io(self):
        # Detects auth/binding shortcuts and acceptance of model-selected root/principal/policy fields.
        damaged = self.token().split("."); damaged[-1] = ("A" if damaged[-1][0] != "A" else "B") + damaged[-1][1:]
        for token, project, extra, may_resolve in (
            (None, "alpha", {}, False), (".".join(damaged), "alpha", {}, False),
            (self.token("unknown-subject"), "alpha", {}, False), (self.token(aud="https://wrong.example/mcp"), "alpha", {}, False),
            (self.token(scope="workbench.write"), "alpha", {}, False), (self.token(exp=self.clock - 1), "alpha", {}, False),
            (self.token("beta-user"), "alpha", {}, True), (self.token(), "alpha", {"root":"/", "principal":"forged", "policy":"forged", "owner_ref":"forged", "generation":"forged"}, False),
        ):
            with self.subTest(project=project, extra=extra):
                before = (self.io_calls, self.resolve_calls)
                response = await self.call(token, project, **extra)
                self.assertTrue(response.status_code == 401 or self.result(response).get("isError"))
                self.assertEqual(self.io_calls, before[0])
                if not may_resolve: self.assertEqual(self.resolve_calls, before[1])
        self.assertEqual(self.io_calls, 0)

    async def test_concurrent_selected_roots_and_postawait_revocation_withhold_content(self):
        # Detects cross-wiring beta into alpha and omission of the post-await binding fence.
        self.admission_limit = 2
        alpha, beta = await asyncio.gather(self.call(self.token("alpha-user"), "alpha"), self.call(self.token("beta-user"), "beta"))
        self.assertEqual(self.successful_data(self.result(alpha))["content"], "alpha sentinel\n")
        self.assertEqual(self.successful_data(self.result(beta))["content"], "beta sentinel\n")
        self.mode = "revoke-after"; refused = self.result(await self.call())
        self.assertTrue(refused["isError"]); self.assertNotIn("alpha sentinel", json.dumps(refused))

    async def test_binding_stages_postawait_auth_and_reverse_overlap_are_closed(self):
        """Defect targets: omitted pre-I/O/current-binding/app-auth rechecks and serial cross-root execution."""
        self.active = False
        pre = self.result(await self.call())
        self.assertTrue(pre["isError"]); self.assertEqual((self.io_calls, self.executed_operations), (0, 0))
        self.assertGreater(self.resolve_calls, 0, "binding must be consulted before admission")
        self.active = True
        for mode in ("revoke-queued", "change-queued"):
            self.mode = mode
            refused = self.result(await self.call())
            self.assertTrue(refused["isError"], mode); self.assertNotIn("alpha sentinel", json.dumps(refused))
            self.active = True
            key = (self.subjects["alpha-user"], "alpha"); binding = self.bindings[key]
            self.bindings[key] = dataclasses.replace(binding, scope=dataclasses.replace(binding.scope, generation="g1"))
        self.mode = "change-after"
        refused = self.result(await self.call())
        self.assertTrue(refused["isError"]); self.assertNotIn("alpha sentinel", json.dumps(refused))
        key = (self.subjects["alpha-user"], "alpha"); binding = self.bindings[key]
        self.bindings[key] = dataclasses.replace(binding, scope=dataclasses.replace(binding.scope, generation="g1"))
        self.mode = "normal"
        original_verify = adapter_module.MastermindTokenVerifier.verify_token
        calls = 0
        async def post_port_refusal(verifier, token):
            nonlocal calls
            calls += 1
            return await original_verify(verifier, token) if calls == 1 else None
        with patch.object(adapter_module.MastermindTokenVerifier, "verify_token", post_port_refusal):
            auth_changed = self.result(await self.call())
        self.assertTrue(auth_changed["isError"]); self.assertNotIn("alpha sentinel", json.dumps(auth_changed))
        self.admission_limit = 2; self.mode = "concurrent-barrier"; self.release.clear()
        alpha = asyncio.create_task(self.call(self.token("alpha-user"), "alpha"))
        beta = asyncio.create_task(self.call(self.token("beta-user"), "beta"))
        await asyncio.wait_for(self.both_admitted.wait(), 5)
        self.release.set()
        # Reverse await order proves each response retains its subject-selected identity.
        beta_result, alpha_result = await beta, await alpha
        for response, project, content in ((alpha_result, "alpha", "alpha sentinel\n"), (beta_result, "beta", "beta sentinel\n")):
            body = self.successful_data(self.result(response))
            self.assertEqual((body["project_ref"], body["content"], body["context_ref"], body["owner_ref"], body["generation"]),
                             (project, content, f"ctx-{project}", f"owner-{project}", "g1"))
        self.assertEqual(self.max_outstanding, 2)

    async def test_matching_postread_auth_baseline_and_guard_result_bypass(self):
        """The same signed request must be withheld after real post-read policy drift."""
        signed_token = self.token()
        original_verify = adapter_module.MastermindTokenVerifier.verify_token
        original_policy, original_mode = self.auth.policy, self.mode
        drifted_policy = adapter_module.validate_resource_policy(dataclasses.replace(
            self.policy, allowed_subject_digests=(self.subjects["beta-user"],),
        ))

        def assert_withheld(result):
            self.assertTrue(result["isError"], "POST_READ_AUTH_WITHHELD")
            self.assertEqual(json.loads(result["content"][0]["text"]),
                             {"code": "AUTHENTICATION_CHANGED"})
            self.assertNotIn("alpha sentinel", json.dumps(result))

        async def run_case(*, bypass):
            state = {"completed": False, "verifier": None, "access": None,
                     "initial": 0, "post_read": 0, "bypassed": 0,
                     "refused": False, "events": []}
            before_io = (self.io_calls, self.executed_operations)
            self.auth._policy = original_policy
            self.mode = "normal"

            async def observed_then_drift(caller, request):
                state["events"].append("port_enter")
                observed = await self.port(caller, request)
                state["events"].append("port_complete")
                self.auth._policy = drifted_policy
                state["completed"] = True
                state["events"].append("policy_flip")
                return observed

            async def phase_verifier(verifier, token):
                if (state["completed"] and token == signed_token
                        and verifier is state["verifier"]):
                    state["post_read"] += 1
                    state["events"].append("post_read")
                    if bypass:
                        state["bypassed"] += 1
                        return state["access"]
                    access = await original_verify(verifier, token)
                    state["refused"] = access is None
                    return access
                access = await original_verify(verifier, token)
                if (not state["completed"] and token == signed_token
                        and access is not None):
                    state["initial"] += 1
                    state["verifier"], state["access"] = verifier, access
                    state["events"].append("initial_verified")
                return access

            try:
                with patch.object(self, "token", return_value=signed_token), \
                     patch.object(adapter_module.MastermindTokenVerifier,
                                  "verify_token", phase_verifier):
                    result = await self.one_off_call(observed_then_drift)
            finally:
                self.auth._policy = original_policy
                self.mode = original_mode

            # Transport, genuine initial auth and mutation reachability are not
            # allowed to masquerade as the expected discriminator failure.
            self.assertIs(type(result["isError"]), bool)
            self.assertEqual(result["content"][0]["type"], "text")
            json.loads(result["content"][0]["text"])
            self.assertGreater(state["initial"], 0)
            self.assertEqual(state["access"].token, signed_token)
            self.assertEqual(state["access"].subject, self.subjects["alpha-user"])
            self.assertTrue(state["completed"])
            self.assertEqual(state["post_read"], 1)
            self.assertEqual(state["bypassed"], int(bypass))
            self.assertEqual(state["refused"], not bypass)
            self.assertLess(state["events"].index("initial_verified"),
                            state["events"].index("port_enter"))
            self.assertLess(state["events"].index("port_complete"),
                            state["events"].index("policy_flip"))
            self.assertLess(state["events"].index("policy_flip"),
                            state["events"].index("post_read"))
            self.assertEqual((self.io_calls - before_io[0],
                              self.executed_operations - before_io[1]), (1, 1))
            self.assertEqual(self.outstanding, 0)
            self.assertIs(self.auth.policy, original_policy)
            self.assertIs(adapter_module.MastermindTokenVerifier.verify_token,
                          original_verify)
            return result

        intact = await run_case(bypass=False)
        assert_withheld(intact)
        mutant = await run_case(bypass=True)
        self.assertFalse(mutant["isError"])
        self.assertEqual(self.successful_data(mutant)["content"], "alpha sentinel\n")
        with self.assertRaisesRegex(AssertionError, "POST_READ_AUTH_WITHHELD"):
            assert_withheld(mutant)

    async def test_complete_descriptor_fields_pagination_and_return_mutations_withhold(self):
        """Defect targets: port result-field, range, cursor, byte, and app-output fences."""
        path = self.root / "alpha" / "sentinel.txt"
        path.write_text("α first\nsecond\nthird\n", encoding="utf-8")
        valid = self.successful_data(self.result(await self.call(line_start=1, line_count=1)))
        self.assertEqual(valid["content"], "second\n")
        self.assertEqual((valid["line_start"], valid["line_end"], valid["total_lines"], valid["next_line"], valid["truncated"]), (1, 2, 3, 2, True))
        self.assertEqual(valid["content_bytes"], len("second\n".encode()))
        for field, value in (
            ("context_ref", "wrong"), ("owner_ref", "wrong"), ("generation", "wrong"),
            ("committed_head", "b" * 40), ("relative_path", "other.txt"), ("project_ref", "beta"),
            ("line_start", 0), ("line_end", 3), ("total_lines", 1), ("content_bytes", 0),
            ("truncated", False), ("next_line", None), ("content", "wrong\n"),
        ):
            with self.subTest(field=field):
                self.return_transform = lambda result, f=field, v=value: {**result, f: v}
                refused = self.result(await self.call(line_start=1, line_count=1))
                self.assertTrue(refused["isError"]); self.assertNotIn("second", json.dumps(refused))
        for transform in (lambda _r: None, lambda _r: [], lambda r: {key: value for key, value in r.items() if key != "context_ref"}):
            self.return_transform = transform
            refused = self.result(await self.call())
            self.assertTrue(refused["isError"])
        self.return_transform = lambda result: result

    async def test_each_model_authority_field_audit_and_postread_audit_boundary(self):
        """Defect targets: bundled-extra acceptance, skipped resolver/audit, and post-read audit leakage."""
        for field in ("root", "principal", "policy", "owner_ref", "generation", "arbitrary_unknown"):
            with self.subTest(field=field):
                before_io, before_resolve = self.io_calls, self.resolve_calls
                response = await self.call(**{field: "forged"})
                self.assertTrue(self.result(response)["isError"])
                self.assertEqual((self.io_calls, self.resolve_calls), (before_io, before_resolve))
        accepted = self.successful_data(self.result(await self.call()))
        self.assertEqual(accepted["project_ref"], "alpha")
        self.assertTrue(self.audit.events, "accepted composition must emit audit evidence")
        self.assertTrue(any(event["accepted"] and event["code"] == "accepted" for event in self.audit.events))
        self.audit.fail = True
        denied = await self.call()
        self.assertEqual(denied.status_code, 401)
        self.assertNotIn("alpha sentinel", denied.text)
        audit_text = json.dumps(self.audit.events)
        self.assertNotIn("alpha-user", audit_text); self.assertNotIn(self.temp.name, audit_text); self.assertNotIn(self.token(), audit_text)
        self.audit.fail = False
        # The first verifier audit succeeds; fail the second verifier audit after
        # the real descriptor result returns while binding remains unchanged.
        before = (self.io_calls, self.executed_operations, self.resolve_calls)
        self.audit.fail_after = len(self.audit.events) + 1
        postread = self.result(await self.call())
        self.audit.fail_after = None
        self.assertTrue(postread["isError"]); self.assertNotIn("alpha sentinel", json.dumps(postread))
        self.assertEqual(json.loads(postread["content"][0]["text"]), {"code": "AUTHENTICATION_CHANGED"})
        self.assertEqual((self.io_calls, self.executed_operations), (before[0] + 1, before[1] + 1))
        self.assertGreater(self.resolve_calls, before[2])
        self.assertTrue(all(set(event) == {"schema", "policy_id", "code", "accepted"} for event in self.audit.events))

    async def test_authenticated_observer_races_withhold_and_close_descriptors(self):
        """Defect targets: observer-hook bypass, source swap disclosure, and root-identity drift."""
        original_observe = observer_module.observe_file
        opened, closed = [], []
        real_open, real_close, real_dup = observer_module.os.open, observer_module.os.close, observer_module.os.dup
        def tracked_open(*args, **kwargs):
            fd = real_open(*args, **kwargs); opened.append(fd); return fd
        def tracked_close(fd):
            closed.append(fd); return real_close(fd)
        def tracked_dup(fd):
            duplicate = real_dup(fd); opened.append(duplicate); return duplicate
        def source_changed(arguments, resolve_scope, *, clock_ms):
            return original_observe(arguments, resolve_scope, clock_ms=clock_ms,
                                    _before_final=lambda: (self.root / "alpha" / "sentinel.txt").write_text("changed\n"))
        with patch.object(read_port_module, "observe_file", source_changed), \
             patch.object(observer_module.os, "open", side_effect=tracked_open), \
             patch.object(observer_module.os, "dup", side_effect=tracked_dup), \
             patch.object(observer_module.os, "close", side_effect=tracked_close):
            changed = self.result(await self.call())
        self.assertTrue(changed["isError"]); self.assertNotIn("alpha sentinel", json.dumps(changed))
        self.assertEqual(sorted(opened), sorted(closed), "all observer descriptors close on authenticated refusal")
        # Restore a known source then change the selected binding at observer's final fence.
        (self.root / "alpha" / "sentinel.txt").write_text("alpha sentinel\n", encoding="utf-8")
        saved_fd = []
        def retained_fd_replaced(arguments, resolve_scope, *, clock_ms):
            def replace_owned_fd():
                # Keep ProjectReadBinding unchanged. Replace only the owned
                # descriptor behind its numeric root_fd; observer's final fstat
                # must catch that retained-identity drift.
                key = (self.subjects["alpha-user"], "alpha"); original_fd = self.bindings[key].scope.root_fd
                saved_fd.append(os.dup(original_fd))
                replacement = os.open(self.root / "beta", os.O_RDONLY | os.O_DIRECTORY)
                try: os.dup2(replacement, original_fd)
                finally: os.close(replacement)
            return original_observe(arguments, resolve_scope, clock_ms=clock_ms, _before_final=replace_owned_fd)
        try:
            with patch.object(read_port_module, "observe_file", retained_fd_replaced):
                root_refused = self.result(await self.call())
        finally:
            original_fd = self.bindings[(self.subjects["alpha-user"], "alpha")].scope.root_fd
            if saved_fd:
                try: os.dup2(saved_fd[0], original_fd)
                finally: os.close(saved_fd[0])
        self.assertTrue(root_refused["isError"]); self.assertNotIn("alpha sentinel", json.dumps(root_refused))
        scope = self.bindings[(self.subjects["alpha-user"], "alpha")].scope
        restored = os.fstat(scope.root_fd)
        self.assertEqual((restored.st_dev, restored.st_ino), (scope.root_device, scope.root_inode))

    async def test_five_actual_boundary_bypasses_fail_their_baseline_discriminators(self):
        """M1–M5: each bypass is served by an isolated real MCP app after its intact baseline passes."""
        async def baseline_then(mutated_port, assertion, *, arguments=None):
            baseline = await self.one_off_call(self.port, arguments=arguments)
            assertion(self.successful_data(baseline))
            mutated = await self.one_off_call(mutated_port, arguments=arguments)
            self.assertFalse(mutated["isError"], "mutant transport must succeed before named discriminator")
            mutated_body = self.successful_data(mutated)
            with self.assertRaisesRegex(AssertionError, "M[13]_DISCRIMINATOR"):
                assertion(mutated_body)

        # M1 bypasses descriptor-port registration: context identity discriminator catches it.
        async def callback_bypass(_caller, _request):
            return {"status": "OK", "project_ref": "alpha", "content": "forged\n", "file_sha256": "0" * 64}
        await baseline_then(callback_bypass, lambda body: self.assertIn("context_ref", body, "M1_DISCRIMINATOR"))
        # M2 bypasses off-thread executor admission while retaining the real descriptor operation.
        observed_threads = []
        async def inline(operation):
            observed_threads.append(threading.get_ident())
            return operation()
        inline_port = create_descriptor_read_port(
            resolve_binding=lambda caller, project: self.bindings.get((caller.subject_digest, project)),
            clock_ms=lambda: self.clock * 1000, run_io=inline,
        )
        baseline = await self.one_off_call(self.port)
        self.assertNotEqual(next(iter(self.worker_threads)), threading.get_ident())
        mutated = await self.one_off_call(inline_port)
        self.assertFalse(mutated["isError"])
        with self.assertRaises(AssertionError): self.assertNotEqual(observed_threads[0], threading.get_ident())
        # M3 bypasses selected-result identity checking and leaks beta under alpha's label.
        beta = await self.port(self.bindings[(self.subjects["beta-user"], "beta")].caller, {"project_ref":"beta", "relative_path":"sentinel.txt"})
        async def crosswire_bypass(_caller, _request): return {**beta, "project_ref":"alpha"}
        await baseline_then(crosswire_bypass, lambda body: self.assertEqual(body["content"], "alpha sentinel\n", "M3_DISCRIMINATOR"))
        # M4 bypasses post-await binding revalidation after a real descriptor observation.
        alpha = await self.port(self.bindings[(self.subjects["alpha-user"], "alpha")].caller, {"project_ref":"alpha", "relative_path":"sentinel.txt"})
        async def binding_bypass(_caller, _request):
            self.active = False
            return alpha
        baseline = await self.one_off_call(self.port); self.assertFalse(baseline["isError"])
        bypassed = await self.one_off_call(binding_bypass)
        with self.assertRaises(AssertionError): self.assertTrue(bypassed["isError"])
        self.active = True
        # M5 bypasses the closed authority schema and maps a model root to beta bytes.
        widened = {**app_module.INPUT_SCHEMA, "properties": {**app_module.INPUT_SCHEMA["properties"], "root": {"type":"string"}}, "additionalProperties": False}
        async def root_bypass(_caller, _request): return {**beta, "project_ref":"alpha"}
        with patch.object(app_module, "INPUT_SCHEMA", widened):
            baseline = await self.one_off_call(self.port); self.assertEqual(self.successful_data(baseline)["content"], "alpha sentinel\n")
            bypassed = await self.one_off_call(root_bypass, arguments={"project_ref":"alpha", "relative_path":"sentinel.txt", "root":"beta"})
        with self.assertRaises(AssertionError): self.assertEqual(self.successful_data(bypassed)["content"], "alpha sentinel\n")

    async def test_matching_m4_m5_adverse_baselines_discriminate_only_the_bypassed_guard(self):
        """M4/M5 use identical adverse inputs for intact and altered real-MCP wiring."""
        # M4 intact port under the revoke-after schedule withholds its real observation.
        self.mode = "revoke-after"
        intact = self.result(await self.call())
        self.assertTrue(intact["isError"]); self.assertNotIn("alpha sentinel", json.dumps(intact))
        self.active = True; self.mode = "normal"
        caller = self.bindings[(self.subjects["alpha-user"], "alpha")].caller
        observed = await self.port(caller, {"project_ref":"alpha", "relative_path":"sentinel.txt"})
        async def omit_postawait_binding(_caller, _request):
            self.active = False
            return observed
        mutant = await self.one_off_call(omit_postawait_binding)
        self.assertFalse(mutant["isError"], "mutant must reach successful transport before discriminator")
        with self.assertRaises(AssertionError): self.assertTrue(mutant["isError"])
        self.active = True
        # M5 intact closed schema refuses exactly root=beta before resolver/I/O.
        before = (self.resolve_calls, self.io_calls)
        intact_root = self.result(await self.call(root="beta"))
        self.assertTrue(intact_root["isError"]); self.assertEqual((self.resolve_calls, self.io_calls), before)
        widened = {**app_module.INPUT_SCHEMA, "properties": {**app_module.INPUT_SCHEMA["properties"], "root": {"type":"string"}}, "additionalProperties": False}
        beta_caller = self.bindings[(self.subjects["beta-user"], "beta")].caller
        async def root_selects_actual_beta(_caller, request):
            selected = await self.port(beta_caller, {"project_ref": request["root"], "relative_path": request["relative_path"]})
            return {**selected, "project_ref": "alpha"}
        with patch.object(app_module, "INPUT_SCHEMA", widened):
            mutant_root = await self.one_off_call(root_selects_actual_beta, arguments={"project_ref":"alpha", "relative_path":"sentinel.txt", "root":"beta"})
        self.assertFalse(mutant_root["isError"], "permitted-root mutant must reach the selected observer result")
        # Same discriminator as the intact root=beta baseline: forbidden root
        # selection must refuse before any resolver or descriptor operation.
        with self.assertRaises(AssertionError):
            self.assertEqual((self.resolve_calls, self.io_calls), before)
        with self.assertRaises(AssertionError):
            self.assertEqual(self.successful_data(mutant_root)["content"], "alpha sentinel\n")

    async def test_negative_controls_reject_fake_port_inline_executor_crosswire_and_bad_result(self):
        # Control 1: replacing the descriptor port with the old callback makes a
        # real MCP call succeed without descriptor context, so the positive
        # context assertion intentionally fails.
        async def old_callback(_caller, _request):
            return {"status":"OK", "project_ref":"alpha", "content":"forged", "file_sha256":"0" * 64}
        fake = await self.one_off_call(old_callback)
        with self.assertRaises(AssertionError, msg="M1 fake callback must fail descriptor-context assertion"):
            self.assertIn("context_ref", self.successful_data(fake))
        # Control 2: an awaitable but inline executor makes a real descriptor
        # observation succeed while the bounded-submission assertion fails.
        caller = ReadCaller(self.subjects["alpha-user"], CLIENT_REF, RESOURCE, (SCOPE,), self.clock + 600)
        inline = {"submissions": 0}
        async def inline_executor(operation):
            inline["submissions"] += 1
            return operation()
        inline_port = create_descriptor_read_port(resolve_binding=lambda actual, project: self.bindings.get((actual.subject_digest, project)), clock_ms=lambda: self.clock * 1000, run_io=inline_executor)
        self.assertFalse((await self.one_off_call(inline_port))["isError"])
        with self.assertRaises(AssertionError, msg="M2 inline executor must fail bounded-submission assertion"):
            self.assertEqual(inline["submissions"], 0)
        # Control 3: beta's descriptor result cannot be relabeled as alpha; the
        # checked selected binding context withholds it through a real MCP call.
        beta = await self.port(self.bindings[(self.subjects["beta-user"], "beta")].caller, {"project_ref":"beta", "relative_path":"sentinel.txt"})
        async def crosswired(_operation): return {**beta, "project_ref":"alpha"}
        alpha_port = create_descriptor_read_port(resolve_binding=lambda caller, project: self.bindings.get((caller.subject_digest, project)), clock_ms=lambda: self.clock * 1000, run_io=crosswired)
        crosswire = await self.one_off_call(alpha_port)
        with self.assertRaises(AssertionError, msg="M3 cross-wire must fail successful alpha assertion"):
            self.assertFalse(crosswire["isError"])
        # Control 4: omitting the port's post-await binding check exposes a real
        # alpha result after revocation; the required withholding assertion fails.
        alpha = await self.port(caller, {"project_ref":"alpha", "relative_path":"sentinel.txt"})
        async def unfenced(_caller, _request):
            self.active = False
            return alpha
        unfenced_result = await self.one_off_call(unfenced)
        with self.assertRaises(AssertionError, msg="M4 omitted post-await fence must fail withholding assertion"):
            self.assertTrue(unfenced_result["isError"])
        self.active = True
        # Control 5: a temporary widened schema plus root-selecting callback
        # returns beta bytes under alpha's label; alpha-byte assertion fails.
        mutated_schema = {**app_module.INPUT_SCHEMA, "properties": {**app_module.INPUT_SCHEMA["properties"], "root": {"type":"string"}}, "additionalProperties": False}
        async def root_selecting(_caller, _request):
            return {**beta, "project_ref":"alpha"}
        with patch.object(app_module, "INPUT_SCHEMA", mutated_schema):
            model_selected = await self.one_off_call(root_selecting, arguments={"project_ref":"alpha", "relative_path":"sentinel.txt", "root":"beta"})
        with self.assertRaises(AssertionError, msg="M5 model-selected root must fail alpha-byte assertion"):
            self.assertEqual(self.successful_data(model_selected)["content"], "alpha sentinel\n")
        # Result consistency control: a bad caller preimage never escapes content.
        bad = self.result(await self.call(project="alpha", expected_sha256="0" * 64))
        self.assertTrue(bad["isError"]); self.assertNotIn("alpha sentinel", json.dumps(bad))

    async def test_bounded_executor_and_audit_fail_closed_without_private_payload(self):
        # Detects fallback execution after admission rejection and audit exceptions
        # that leak a verified descriptor payload.
        self.mode = "reject-admission"; refused = self.result(await self.call())
        self.assertTrue(refused["isError"]); self.assertEqual(self.executed_operations, 0)
        self.assertNotIn("alpha sentinel", json.dumps(refused))
        self.mode = "normal"; self.audit.fail = True
        audited = await self.call()
        self.assertEqual(audited.status_code, 401)
        self.assertEqual(self.executed_operations, 0)

    async def test_cancellation_and_observer_refusals_close_without_retry(self):
        # Detects automatic retry/fallback after a bounded executor await is
        # cancelled, plus bypassing the retained-descriptor observer for an
        # undeclared path or symlink.
        caller = self.bindings[(self.subjects["alpha-user"], "alpha")].caller
        # Queued direct-port cancellation drops its admitted slot before worker start.
        self.mode = "block-after-admission"; self.admitted.clear(); self.release.clear()
        queued = asyncio.create_task(self.port(caller, {"project_ref":"alpha", "relative_path":"sentinel.txt"}))
        await asyncio.wait_for(self.admitted.wait(), 5); queued.cancel()
        with self.assertRaises(asyncio.CancelledError): await queued
        self.assertEqual((self.executed_operations, self.outstanding), (0, 0))
        # Hold one queued slot and prove a second port request is rejected rather
        # than queued, retried, or started beyond the finite admission limit.
        self.admitted.clear(); saturated = asyncio.create_task(self.port(caller, {"project_ref":"alpha", "relative_path":"sentinel.txt"}))
        await asyncio.wait_for(self.admitted.wait(), 5)
        with self.assertRaises(ProjectReadRefused):
            await self.port(caller, {"project_ref":"alpha", "relative_path":"sentinel.txt"})
        self.assertEqual((self.io_calls, self.executed_operations, self.outstanding), (2, 0, 1))
        saturated.cancel()
        with self.assertRaises(asyncio.CancelledError): await saturated
        self.assertEqual(self.outstanding, 0)
        # Hold inside the real observer, cancel its active await, then release
        # the one worker and prove the cancellation-drain branch completed.
        self.mode = "normal"; entered = threading.Event(); release_worker = threading.Event()
        original_observe = observer_module.observe_file
        def held_observe(arguments, resolve_scope, *, clock_ms):
            return original_observe(arguments, resolve_scope, clock_ms=clock_ms,
                _before_file_open=lambda: (entered.set(), release_worker.wait(5)))
        with patch.object(read_port_module, "observe_file", held_observe):
            pending = asyncio.create_task(self.port(caller, {"project_ref":"alpha", "relative_path":"sentinel.txt"}))
            self.assertTrue(await asyncio.to_thread(entered.wait, 5))
            self.assertEqual((self.executed_operations, self.outstanding), (1, 1))
            pending.cancel(); release_worker.set()
            with self.assertRaises(asyncio.CancelledError): await pending
        for _ in range(50):
            if self.outstanding == 0: break
            await asyncio.sleep(0.02)
        # Cancellation is not a claim about kernel I/O: the already admitted
        # operation may finish. It proves only that the app made no second
        # submission or hidden retry.
        self.assertEqual((self.io_calls, self.executed_operations, self.outstanding), (3, 1, 0))
        self.assertEqual(self.cancellation_drains, 1)
        self.assertTrue(self.worker_threads, "operation must run off the event-loop thread")
        self.mode = "normal"
        alpha_key = (self.subjects["alpha-user"], "alpha")
        binding = self.bindings[alpha_key]
        link = self.root / "alpha" / "outside-link.txt"
        os.symlink(self.root / "beta" / "sentinel.txt", link)
        self.bindings[alpha_key] = dataclasses.replace(
            binding, scope=dataclasses.replace(binding.scope, allowed_paths=("sentinel.txt", "outside-link.txt")),
        )
        for path in ("undeclared.txt", "outside-link.txt"):
            with self.subTest(path=path):
                refused = self.result(await self.call(relative_path=path))
                self.assertTrue(refused["isError"])
                self.assertNotIn("beta sentinel", json.dumps(refused))

    async def test_output_schema_failure_withholds_real_descriptor_payload(self):
        # Detects app-level output-schema bypass after an otherwise valid
        # descriptor result returns from the port.
        impossible = {**OUTPUT, "required": [*OUTPUT["required"], "fixture_schema_field"]}
        server = create_authenticated_read_server(
            authenticator=self.auth, policy=self.policy, now=lambda: self.clock,
            audit_sink=self.audit, read_port=self.port, output_schema=impossible,
            allowed_hosts=("127.0.0.1", "127.0.0.1:*"),
        )
        app = server.streamable_http_app(); ready = asyncio.Event(); stop = asyncio.Event()
        async def lifespan():
            async with app.router.lifespan_context(app):
                ready.set()
                await stop.wait()
        life = asyncio.create_task(lifespan())
        await asyncio.wait_for(ready.wait(), 5)
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1")
        try:
            response = await client.post(
                "/mcp",
                headers={"Accept":"application/json, text/event-stream", "MCP-Protocol-Version":"2025-03-26",
                         "Authorization":"Bearer " + self.token()},
                json={"jsonrpc":"2.0", "id":1, "method":"tools/call",
                      "params":{"name":"read_project_file", "arguments":{"project_ref":"alpha", "relative_path":"sentinel.txt"}}},
            )
            refused = self.result(response)
            self.assertTrue(refused["isError"])
            self.assertNotIn("alpha sentinel", json.dumps(refused))
        finally:
            await client.aclose()
            stop.set()
            await asyncio.wait_for(life, 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
