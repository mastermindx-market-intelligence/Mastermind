"""Pinned Hermes -> original APPLICATION factory/client/handler/Broker proof.

Only the external provider and qualification inputs are synthetic. The existing
owner's HTTP fixture supplies its real Router, GoLeaseGateway and Broker/SQLite.
No installed owner, real account or production credential is read or changed.
This is source composition evidence, not live or monetary acceptance.
"""
from pathlib import Path
import argparse
from dataclasses import replace
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import unittest
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter-root", required=True)
    parser.add_argument("--macro-root", required=True)
    parser.add_argument("--native-owner-root", required=True)
    parser.add_argument("--hermes-root", required=True)
    args = parser.parse_args()
    roots = {name: Path(value).resolve() for name, value in vars(args).items()}
    expected = {
        "macro_root": "6612f6aba4ac431d38432b500ed5c5d66122f1d0",
        "native_owner_root": "f5c4a2365e4ec83bb5de92e7e64213264ada9324",
        "hermes_root": "1c0cd667746d3395fe9e1b6c74f8f85952486f18",
    }
    for name, sha in expected.items():
        actual = subprocess.run(["git", "-C", str(roots[name]), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=10).stdout.strip()
        if actual != sha:
            raise RuntimeError("Qualification source differs: " + name)
        subprocess.run(["git", "-C", str(roots[name]), "diff", "--exit-code", "HEAD", "--"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=10)
    owner_tests = roots["native_owner_root"] / "ops/native_fabric/quota_continuity/tests"
    sys.path[:0] = [str(roots["adapter_root"]), str(roots["macro_root"]),
                   str(owner_tests), str(roots["hermes_root"])]
    sys.dont_write_bytecode = True
    blocked, constructed = [], []
    original_connect, original_lookup = socket.socket.connect, socket.getaddrinfo

    def local_connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and address[0] != "127.0.0.1":
            blocked.append("connect")
            raise AssertionError("External network disabled in owner composition")
        return original_connect(sock, address)

    def local_lookup(host, *args, **kwargs):
        if host != "127.0.0.1":
            blocked.append("lookup")
            raise AssertionError("External lookup disabled in owner composition")
        return original_lookup(host, *args, **kwargs)

    def forbidden_sdk(*_, **__):
        constructed.append("provider-sdk")
        raise AssertionError("Provider SDK construction disabled in owner composition")

    socket.socket.connect, socket.getaddrinfo = local_connect, local_lookup
    import openai
    openai.OpenAI = openai.AsyncOpenAI = forbidden_sdk
    from test_go_application_handler_composition import NativeApplicationHTTPFixture, SERVICE_TOKEN
    from engine import provider_production_modes as factory_owner
    from integrations.hermes_application_fabric.client import (
        ApplicationBinding, HermesApplicationClient, NativeCall, call_scope,
    )
    from integrations.hermes_application_fabric.errors import HermesFabricError
    from integrations.hermes_application_fabric.native import (
        create_primary_agent, execution_middleware, register_native_provider,
    )

    class OriginalOwnerConversation(NativeApplicationHTTPFixture):
        def setUp(self):
            super().setUp()
            self.grant.update(principal_id="hermes-secretary", grant_id="fixture-hermes",
                credential_ref="HERMES_SECRETARY_FABRIC_APPLICATION_TOKEN",
                admission_root="service:hermes-secretary", accounts=["account-a"])
            self.save()
            self.physical_before = json.loads(self.accounts.read_bytes())["providers"]
            # Reuse the original physical Router/gateway/Broker, with a Hermes
            # service binding in the disposable owner. The prior fixture
            # listener remains unused and retains its own cleanup callback.
            self.service = self.go.ApplicationServiceBinding("hermes-secretary", "vps",
                "site_interactive", "HERMES_SECRETARY_FABRIC_APPLICATION_TOKEN", SERVICE_TOKEN)
            self.server = self.go.make_server(self.router, lease_gateway=self.gateway,
                application_services=(self.service,))
            self._serve(self.server)
            self.config_root = self.directory / "macro-qualification"
            config = self.config_root / "config"
            config.mkdir(parents=True)
            (config / "provider_workloads.v1.json").write_bytes(
                (roots["macro_root"] / "config/provider_workloads.v1.json").read_bytes())
            document = json.loads((roots["macro_root"] / "config/provider_production_modes.v1.json").read_bytes())
            self.assertEqual(document["application_fabric_modes"], {})
            transport_id = "native_go_hermes_secretary_v1"
            original = factory_owner._APPLICATION_FABRIC_TRANSPORTS[transport_id]
            self.assertFalse(original.qualified or original.application_allowed)
            qualified = replace(original, base_url=f"http://127.0.0.1:{self.server.server_port}/v1",
                model="fixture-model", qualified=True, application_allowed=True)
            held = patch.dict(factory_owner._APPLICATION_FABRIC_TRANSPORTS, {transport_id: qualified})
            held.start()
            self.addCleanup(held.stop)
            row = {name: getattr(qualified, name) for name in factory_owner._APPLICATION_IDENTITY_FIELDS}
            row.update(transport_id=transport_id, enabled=True, application_allowed=True,
                qualification=factory_owner.PROFILE_QUALIFIED_CANARY,
                qualification_ref="fixture:original-owner-conversation", qualified_until=time.time() + 300)
            document["application_fabric_modes"] = {"hermes_secretary_fabric": row}
            (config / "provider_production_modes.v1.json").write_text(json.dumps(document))
            (config / "capability_manifest.yml").write_text(json.dumps({"capabilities": [{
                "capability_id": qualified.capability_id, "secret_ref": qualified.secret_ref,
                "kill_state": "active", "allowed_lanes": ["hermes-secretary"]}]}))
            environment = patch.dict(os.environ, {qualified.secret_ref: SERVICE_TOKEN,
                "MM_PROVIDER_WORKLOAD_PROFILE": "site_interactive"})
            environment.start()
            self.addCleanup(environment.stop)
            factory = factory_owner.make_application_fabric_factory(mode_id="shared_fabric",
                lane="hermes-secretary", root=self.config_root, service_mode_id="hermes_secretary_fabric",
                workload_cfg={"workload_profile": "site_interactive", "provider_order": ["fabric"]})
            # Inspect outside native middleware so a fixture authority error
            # remains a useful qualification failure instead of a masked
            # missing-host-binding response. This performs no admission.
            self.assertEqual(factory.inspect()["model"], "fixture-model")
            self.binding = None
            self.native_calls = []
            self.binding_errors = []

            def resolve(call):
                self.native_calls.append(call)
                if self.binding is None:
                    try:
                        self.binding = ApplicationBinding.from_factory(factory, profile_id="mmsecretary",
                            operation_id="hermes-owner-proof", session_id=call.session_id, turn_id=call.turn_id,
                            requested_model="host-selection", authorized=lambda current: current.session_id == call.session_id,
                            prior_admission_possible=False, strict_model="fixture-model", max_output_tokens=256)
                    except Exception as error:
                        self.binding_errors.append((type(error).__name__, getattr(error, "code", None)))
                        raise
                return self.binding

            register_native_provider()
            from hermes_cli.plugins import _delivery_manager
            manager = _delivery_manager()
            middleware = execution_middleware(resolve)
            manager._middleware.setdefault("llm_execution", []).append(middleware)
            self.addCleanup(lambda: manager._middleware["llm_execution"].remove(middleware))
            self.executed = []
            from tools.registry import registry

            def read_value(arguments, **_):
                self.executed.append(arguments)
                return json.dumps({"value": arguments["value"]})

            registry.register(name="mmx_owner_fixture_read", toolset="mmx_owner_fixture_tools",
                schema={"name": "mmx_owner_fixture_read", "description": "Read the immutable fixture value.",
                    "parameters": {"type": "object", "properties": {"value": {"type": "string"}},
                                   "required": ["value"]}}, handler=read_value)
            self.native = create_primary_agent(model="host-selection", session_id="hermes-owner-session",
                enabled_toolsets=["mmx_owner_fixture_tools"], quiet_mode=True, skip_memory=True,
                skip_background_review=True, skip_context_files=True, load_soul_identity=False,
                save_trajectories=False, max_iterations=3, max_tokens=256)
            self.assertIs(type(self.native.client), HermesApplicationClient)
            self.assertIn(self.native.api_key, (None, ""))
            self.partial_followup = False

            def provider_reply():
                first = len(self.posts) == 1
                message = {"role": "assistant", "content": "Original owner result"}
                if first:
                    message.update(content=None, tool_calls=[{"id": "original-tool", "type": "function",
                        "function": {"name": "tool_call", "arguments": json.dumps({"calls": [{
                            "name": "mmx_owner_fixture_read", "arguments": {"value": "immutable value"}}]})}}])
                self.response = {"id": "original-provider-result", "model": "fixture-model",
                    "choices": [{"index": 0, "message": message,
                                 "finish_reason": "tool_calls" if first else "stop"}],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 7}}
                self.partial = self.partial_followup and not first

            self.on_upstream = provider_reply

        def conversation(self):
            result = self.native.run_conversation("Read the immutable fixture once and report it.",
                                                 task_id="original-owner-conversation")
            self.assertEqual(self.binding_errors, [])
            return result

        def assert_original_requests(self, count):
            requests = self.rows("application_requests")
            self.assertEqual(len(requests), count)
            self.assertEqual({r["principal_id"] for r in requests}, {"hermes-secretary"})
            self.assertEqual({r["turn_id"] for r in requests}, {self.binding.operation_id})
            for row, call, sent in zip(requests, self.native_calls, self.posts):
                self.assertEqual(row["request_id"], self.binding.request_id(call))
                envelope = json.dumps({"path": "/v1/chat/completions", "payload": json.loads(sent[1])},
                    sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
                self.assertEqual(row["request_digest"], hashlib.sha256(envelope).hexdigest())
            self.assertEqual(len(self.rows("leases")), 1)
            self.assertEqual(self.rows("application_turns")[0]["account"], "account-a")
            self.assertEqual(json.loads(self.accounts.read_bytes())["providers"], self.physical_before)
            self.assertEqual(self.executed, [{"value": "immutable value"}])

        def test_native_tool_conversation_through_original_application_owners(self):
            result = self.conversation()
            self.assertEqual(result.get("final_response"), "Original owner result")
            self.assertEqual(len(self.posts), 2)
            self.assert_original_requests(2)
            self.assertEqual([row["state"] for row in self.rows("application_requests")], ["terminal", "terminal"])
            self.assertEqual([post[2] for post in self.posts], ["Bearer fixture-provider-a"] * 2)
            history = json.loads(self.posts[1][1])["messages"]
            self.assertEqual((history[-1]["role"], history[-1]["tool_call_id"]), ("tool", "original-tool"))
            self.assertIn("immutable value", history[-1]["content"])
            for request in self.rows("application_requests"):
                self.assertEqual(json.loads(request["terminal_receipt"])["usage"], {"input_tokens": 11, "output_tokens": 7})
            self.assertEqual(len(self.usage_rows()), 2)
            self.assertTrue(all(row["model"] == "fixture-model" and row["input"] == 11
                and row["output"] == 7 and row["est_usd"] is None for row in self.usage_rows()))
            self.binding.close()
            self.assertEqual(self.rows("leases")[0]["state"], "released")

        def test_original_step_limit_refuses_followup_before_provider_dispatch(self):
            self.grant["max_steps"] = 1
            self.save()
            result = self.conversation()
            self.assertNotEqual(result.get("final_response"), "Original owner result")
            self.assertEqual(len(self.posts), 1)
            self.assert_original_requests(1)
            self.assertEqual(len(self.native_calls), 2)
            self.assertEqual(len(self.usage_rows()), 1)

        def test_unknown_followup_retains_original_lease_without_replay(self):
            self.partial_followup = True
            result = self.conversation()
            self.assertNotEqual(result.get("final_response"), "Original owner result")
            self.assertEqual(len(self.posts), 2)
            self.assert_original_requests(2)
            self.assertEqual([r["state"] for r in self.rows("application_requests")], ["terminal", "unknown"])
            self.assertEqual(len(self.usage_rows()), 1)
            self.assertIn(self.rows("leases")[0]["state"], ("held", "rented"))
            last = self.native_calls[-1]
            with call_scope(self.binding, NativeCall(last.session_id, last.task_id, last.turn_id, "replacement")):
                with self.assertRaises(HermesFabricError):
                    HermesApplicationClient().create(model="host-selection",
                        messages=[{"role": "user", "content": "retry"}], max_tokens=256)
            status, body, _ = self.request(turn=self.binding.operation_id,
                step=self.binding.request_id(last), payload=json.loads(self.posts[-1][1]))
            self.assertEqual(status, 409)
            self.assertTrue(body["application"]["effect_unknown"])
            self.assertEqual((len(self.posts), len(self.executed), len(self.usage_rows())), (2, 1, 1))

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(OriginalOwnerConversation)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"sources": expected, "tests_run": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors), "skips": len(result.skipped),
        "blocked_external_connections": len(blocked), "provider_sdk_constructions": len(constructed),
        "real_application_handler": True, "real_broker": True, "provider_is_fixture": True,
        "live_provider_acceptance": False, "monetary_acceptance": False}), flush=True)
    return 0 if (result.wasSuccessful() and result.testsRun == 3 and not result.skipped
                 and not blocked and not constructed) else 1


if __name__ == "__main__":
    raise SystemExit(main())
