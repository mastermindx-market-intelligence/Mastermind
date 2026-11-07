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
import tempfile
import unittest
from unittest.mock import patch


def qualify(args):
    from owner_source_support import COMPOSED_OWNER_COMMIT, CURRENT_OWNER_COMMIT, OWNER_COMMIT
    source_context = ("committed_attended_auto" if args.composed_owner_source else
                      "committed_current" if args.current_owner_source else
                      "historical_proposal" if args.source_support_proposal else
                      "historical_fixture")
    uses_source_flags = args.composed_owner_source or args.current_owner_source or args.source_support_proposal
    roots = {name: Path(getattr(args, name)).resolve()
             for name in ("adapter_root", "macro_root", "native_owner_root", "hermes_root")}
    candidate = subprocess.run(
        ["git", "-c", "gc.auto=0", "-C", str(roots["adapter_root"]), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, timeout=10,
    ).stdout.strip()
    expected = {
        "adapter_root": candidate,
        "macro_root": (COMPOSED_OWNER_COMMIT if args.composed_owner_source else
                       CURRENT_OWNER_COMMIT if args.current_owner_source else OWNER_COMMIT),
        "native_owner_root": candidate,
        "hermes_root": "1c0cd667746d3395fe9e1b6c74f8f85952486f18",
    }
    for name, sha in expected.items():
        actual = subprocess.run(["git", "-c", "gc.auto=0", "-C", str(roots[name]), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=10).stdout.strip()
        if actual != sha:
            raise RuntimeError("Qualification source differs: " + name)
        subprocess.run(["git", "-c", "gc.auto=0", "-C", str(roots[name]), "diff", "--exit-code", "HEAD", "--"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=10)
    support, committed_source = None, None
    if args.source_support_proposal:
        from owner_source_support import prepare, qualify_unit
        support = prepare(roots["macro_root"], roots["adapter_root"], args.proposal_directory)
        support["unit_qualification"] = qualify_unit(args.proposal_directory, sys.executable)
        roots["macro_root"] = args.proposal_directory
    elif args.current_owner_source or args.composed_owner_source:
        from owner_source_support import prepare_current
        committed_source = prepare_current(
            roots["macro_root"], roots["adapter_root"], args.proposal_directory,
            composed=args.composed_owner_source)
        roots["macro_root"] = args.proposal_directory
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
        route_mode = "fixed"
        service_lane = "hermes-secretary"
        service_mode = "hermes_secretary_fabric"
        workload = "site_interactive"
        credential_ref = "HERMES_SECRETARY_FABRIC_APPLICATION_TOKEN"
        profile_id = "mmsecretary"
        fixed_transport = "native_go_hermes_secretary_v1"
        automatic_transport = "native_fabric_hermes_secretary_auto_v1"

        def setUp(self):
            super().setUp()
            self.grant.update(principal_id=self.service_lane, grant_id="fixture-hermes",
                credential_ref=self.credential_ref, workloads=[self.workload],
                admission_root="service:" + self.service_lane, accounts=["account-a"])
            self.save()
            self.physical_before = json.loads(self.accounts.read_bytes())["providers"]
            scoped = self.route_mode != "fixed"
            route_scope = {"schema": "mastermind.application_route_scope.v1", "pools": ["go"]}
            selection = {}
            if scoped:
                from test_application_registered_pool_selection import RegisteredPoolFixture, _policy_document
                from go_lease_gateway import ApplicationSelectionProfile
                import pick
                import pool_ledger
                self.policy_path = self.directory / "pools.yaml"
                self.policy_path.write_text(json.dumps(_policy_document()))
                ledger_path = self.directory / "ledger.jsonl"
                ledger_path.write_text("")
                for module, name, value in ((pick, "POOLS_YAML", str(self.policy_path)),
                                           (pool_ledger, "LEDGER_PATH", str(ledger_path))):
                    guard = patch.object(module, name, value)
                    guard.start()
                    self.addCleanup(guard.stop)
                profile = ApplicationSelectionProfile(source_generation="a" * 64,
                    ingress_digest=hashlib.sha256(Path(self.go.__file__).read_bytes()).hexdigest(),
                    account_profile=self.router.accounts_path)
                self.gateway = self.new_gateway(application_selection_profile=profile)
                purpose = RegisteredPoolFixture.purpose_for(self, "go")
                purpose["task"]["needs"] = ["tools"]
                selection = {"selection_purpose": self.go.ApplicationSelectionPurpose(purpose),
                    "route_scope": self.go.ApplicationRouteScope(route_scope)}
            # Reuse the original physical Router/gateway/Broker, with a Hermes
            # service binding in the disposable owner. The prior fixture
            # listener remains unused and retains its own cleanup callback.
            self.service = self.go.ApplicationServiceBinding(self.service_lane, "vps",
                self.workload, self.credential_ref, SERVICE_TOKEN, **selection)
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
            transport_id = self.automatic_transport if scoped else self.fixed_transport
            original = factory_owner._APPLICATION_FABRIC_TRANSPORTS[transport_id]
            if not uses_source_flags:
                self.assertFalse(original.qualified or original.application_allowed)
                fixture_support = {"qualified": True, "application_allowed": True}
            else:
                self.assertTrue(original.qualified and original.application_allowed)
                fixture_support = {}  # Consume the candidate's real source flags.
            qualified = replace(original, base_url=f"http://127.0.0.1:{self.server.server_port}/v1",
                model=None if scoped else "fixture-model", **fixture_support)
            held = patch.dict(factory_owner._APPLICATION_FABRIC_TRANSPORTS, {transport_id: qualified})
            held.start()
            self.addCleanup(held.stop)
            row = {name: getattr(qualified, name) for name in factory_owner._APPLICATION_IDENTITY_FIELDS}
            row.update(transport_id=transport_id, enabled=True, application_allowed=True,
                qualification=factory_owner.PROFILE_QUALIFIED_CANARY,
                qualification_ref="fixture:original-owner-conversation", qualified_until=time.time() + 300)
            if scoped:
                row["route_scope"] = route_scope
            document["application_fabric_modes"] = {self.service_mode: row}
            # Fixture only: `secret_ref` is an env-var NAME, never a token
            # value; SERVICE_TOKEN is injected via os.environ below and must
            # never reach disk — asserted here so a fixture change that
            # breaks that guarantee fails loudly instead of silently.
            rendered = json.dumps(document)
            assert SERVICE_TOKEN not in rendered
            # codeql[py/clear-text-storage-sensitive-data]
            (config / "provider_production_modes.v1.json").write_text(rendered)  # lgtm[py/clear-text-storage-sensitive-data]
            rendered_manifest = json.dumps({"capabilities": [{
                "capability_id": qualified.capability_id, "secret_ref": qualified.secret_ref,
                "kill_state": "active", "allowed_lanes": [self.service_lane]}]})
            assert SERVICE_TOKEN not in rendered_manifest
            # codeql[py/clear-text-storage-sensitive-data]
            (config / "capability_manifest.yml").write_text(rendered_manifest)  # lgtm[py/clear-text-storage-sensitive-data]
            # Runtime env wiring only — in-memory process env for the fixture
            # harness; the token value never reaches disk (asserted above).
            environment = patch.dict(os.environ, {qualified.secret_ref: SERVICE_TOKEN,  # lgtm[py/clear-text-storage-sensitive-data]
                "MM_PROVIDER_WORKLOAD_PROFILE": self.workload})
            environment.start()
            self.addCleanup(environment.stop)
            factory = factory_owner.make_application_fabric_factory(mode_id="shared_fabric",
                lane=self.service_lane, root=self.config_root, service_mode_id=self.service_mode,
                workload_cfg={"workload_profile": self.workload, "provider_order": ["fabric"]})
            if self.route_mode == "exact":
                factory = factory.with_requested_model("fixture-model")
            # Inspect outside native middleware so a fixture authority error
            # remains a useful qualification failure instead of a masked
            # missing-host-binding response. This performs no admission.
            inspected = factory.inspect()
            if scoped:
                self.assertEqual(inspected["schema"], "mastermind.fabric_application_inspection.v3"
                                 if self.route_mode == "exact" else "mastermind.fabric_application_inspection.v2")
                self.assertEqual(inspected["requested_model"], "fixture-model" if self.route_mode == "exact" else None)
            else:
                self.assertEqual(inspected["model"], "fixture-model")
            factory = factory.with_inspection(inspected)
            self.native_model = ("fixture-model" if self.route_mode == "exact" else
                                 "mastermind-fabric/auto" if scoped else "host-selection")
            self.binding = None
            self.native_calls = []
            self.binding_errors = []
            self.owner_results = []

            def resolve(call):
                self.native_calls.append(call)
                if self.binding is None:
                    try:
                        self.binding = ApplicationBinding.from_factory(factory, profile_id=self.profile_id,
                            operation_id="hermes-owner-proof", session_id=call.session_id, turn_id=call.turn_id,
                            requested_model=self.native_model, authorized=lambda current: current.session_id == call.session_id,
                            prior_admission_possible=False, strict_model=None if self.route_mode == "auto" else "fixture-model",
                            automatic=scoped, strict_pool="go" if scoped else None, max_output_tokens=256)
                        original_create = self.binding._owner.messages.create
                        def observed_create(**kwargs):
                            response = original_create(**kwargs)
                            self.owner_results.append(response)
                            return response
                        self.binding._owner.messages.create = observed_create
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
            self.native = create_primary_agent(model=self.native_model, session_id="hermes-owner-session",
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
            self.assertEqual({r["principal_id"] for r in requests}, {self.service_lane})
            self.assertEqual({r["turn_id"] for r in requests}, {self.binding.operation_id})
            for row, call, sent in zip(requests, self.native_calls, self.posts):
                self.assertEqual(row["request_id"], self.binding.request_id(call))
                payload = json.loads(sent[1])
                self.assertEqual(payload["model"], "fixture-model")
                if self.route_mode == "auto":
                    payload["model"] = None
                envelope = json.dumps({"path": "/v1/chat/completions", "payload": payload},
                    sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
                self.assertEqual(row["request_digest"], hashlib.sha256(envelope).hexdigest())
                if self.route_mode != "auto":
                    self.assertIsNone(row["routed_request_digest"])
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
            self.assertEqual(len(self.owner_results), 2)
            if self.route_mode != "fixed":
                self.assertEqual(self.native.model, self.native_model)
                self.assertEqual(self.binding.model, "fixture-model" if self.route_mode == "exact" else None)
                for response in self.owner_results:
                    observed = response.application_observation.document
                    route = observed["routing"]
                    self.assertEqual(route["pool"], "go")
                    self.assertEqual(route["selected_model"], observed["serving_model"])
                    if self.route_mode == "exact":
                        self.assertEqual(route["requested_model"], self.native.model)
                        self.assertEqual(route["schema"], "mastermind.fabric_application_route.v2")
                        self.assertIsNone(route["routed_request_digest"])
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
                    HermesApplicationClient().create(model=self.native_model,
                        messages=[{"role": "user", "content": "retry"}], max_tokens=256)
            payload = json.loads(self.posts[-1][1])
            if self.route_mode == "auto":
                payload["model"] = None
            headers = ({} if self.route_mode == "fixed" else
                       {"X-MM-Application-Route-Scope-Digest": self.service.route_scope.digest})
            status, body, _ = self.request(turn=self.binding.operation_id,
                step=self.binding.request_id(last), payload=payload, headers=headers)
            self.assertEqual(status, 409)
            self.assertTrue(body["application"]["effect_unknown"])
            self.assertEqual((len(self.posts), len(self.executed), len(self.usage_rows())), (2, 1, 1))

    class AutoOwnerConversation(OriginalOwnerConversation):
        route_mode = "auto"

    class ExactOwnerConversation(OriginalOwnerConversation):
        route_mode = "exact"

    class MetaOwnerConversation(OriginalOwnerConversation):
        service_lane = "hermes-meta-ceo"
        service_mode = "hermes_meta_fabric"
        credential_ref = "HERMES_META_FABRIC_APPLICATION_TOKEN"
        profile_id = "mmmeta"
        fixed_transport = "native_go_hermes_meta_v1"
        automatic_transport = "native_fabric_hermes_meta_auto_v1"

    class MetaAutoOwnerConversation(MetaOwnerConversation):
        route_mode = "auto"

    class MetaExactOwnerConversation(MetaOwnerConversation):
        route_mode = "exact"

    class AttendedOwnerConversation(OriginalOwnerConversation):
        # Existing factory/handler/Broker with a distinct disposable service.
        # Runtime application data remains unenrolled in every source context.
        service_lane = "hermes-attended"
        service_mode = "hermes_attended_fabric"
        workload = "hermes_attended"
        credential_ref = "HERMES_ATTENDED_FABRIC_APPLICATION_TOKEN"
        profile_id = "attended"
        fixed_transport = "native_go_hermes_attended_v1"

    class AttendedAutoOwnerConversation(AttendedOwnerConversation):
        route_mode = "auto"
        automatic_transport = "native_fabric_hermes_attended_auto_v1"

    class AttendedExactOwnerConversation(AttendedAutoOwnerConversation):
        route_mode = "exact"

    contexts = (OriginalOwnerConversation, AutoOwnerConversation, ExactOwnerConversation,
                AttendedOwnerConversation, MetaOwnerConversation,
                MetaAutoOwnerConversation, MetaExactOwnerConversation)
    if args.composed_owner_source:
        contexts += (AttendedAutoOwnerConversation, AttendedExactOwnerConversation)
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls)
                              for cls in contexts)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"sources": expected, "source_context": source_context,
        "source_support_proposal": support, "committed_owner_source": committed_source,
        "fixture_overrides_source_flags": not uses_source_flags, "tests_run": result.testsRun,
        "network_counter_scope": "native_conversation_process_after_source_preparation",
        "failures": len(result.failures), "errors": len(result.errors), "skips": len(result.skipped),
        "blocked_external_connections": len(blocked), "provider_sdk_constructions": len(constructed),
        "real_application_handler": True, "real_broker": True, "provider_is_fixture": True,
        "live_provider_acceptance": False, "monetary_acceptance": False}), flush=True)
    return 0 if (result.wasSuccessful() and result.testsRun == (27 if args.composed_owner_source else 21) and not result.skipped
                 and not blocked and not constructed) else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter-root", required=True)
    parser.add_argument("--macro-root", required=True)
    parser.add_argument("--native-owner-root", required=True)
    parser.add_argument("--hermes-root", required=True)
    context = parser.add_mutually_exclusive_group()
    context.add_argument("--source-support-proposal", action="store_true")
    context.add_argument("--current-owner-source", action="store_true")
    context.add_argument("--composed-owner-source", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="hermes-owner-support-") as temporary:
        args.proposal_directory = Path(temporary) / "macro"
        return qualify(args)


if __name__ == "__main__":
    raise SystemExit(main())
