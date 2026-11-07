"""Pinned native CLI/gateway composition, with real SQLite admission and fixture inference."""
from contextlib import ExitStack, nullcontext
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch

import test_owner_integration as fixtures
from engine.fabric_inference_client import FabricInferenceClient, NATIVE_PROTOCOL
from integrations.hermes_application_fabric.client import ApplicationBinding
from integrations.hermes_application_fabric.native import PROVIDER, register_native_provider
from integrations.hermes_application_fabric import gateway_plugin


class GatewayBoundTests(unittest.TestCase):
    def setUp(self):
        fixtures.OwnerLoopbackTests.setUp(self)
        from hermes_constants import get_hermes_home
        from hermes_state import SessionDB
        from hermes_state_runtime import begin_runtime_epoch
        from gateway.config import Platform
        from gateway.session_authority import SessionAuthority, LiveSession
        from gateway.turn_context import TurnContext
        from run_agent import AIAgent
        from hermes_cli.plugins import PluginContext, PluginManifest, _delivery_manager
        self.temp = tempfile.TemporaryDirectory(dir=get_hermes_home())
        self.db = SessionDB(Path(self.temp.name) / "state.db")
        self.db.create_session("session-1", "cli")
        self.runner = N(_draining=False, _refresh_fallback_model=lambda: None,
            _service_tier=None, _session_db=None, _prefill_messages=None,
            _provider_routing={}, _pre_agent_fallback_notice=None,
            _resolve_session_reasoning_config=lambda **_: {},
            _resolve_session_service_tier=lambda **_: None)
        self.authority = SessionAuthority(self.runner, profile_id=str(get_hermes_home()),
            instance_id="gateway-fixture", db=self.db,
            epoch=begin_runtime_epoch(self.db, instance_id="gateway-fixture"))
        self.runner.session_authority = self.authority
        self.source = N(platform=Platform.LOCAL, user_id="fixture-user", user_id_alt=None,
            user_name="Fixture", chat_id="fixture-chat", chat_name=None, chat_type="dm", thread_id=None)
        self.live = LiveSession(self.source, "fixture-route")
        self.authority.sessions["session-1"] = self.live
        self.ctx = TurnContext(source=self.source, session_id="session-1",
            session_key="fixture-route", AIAgent=AIAgent, user_config={}, enabled_toolsets=[],
            disabled_toolsets=None, _run_still_current=lambda: True)
        self.route = {"model": "model-1", "runtime": {"provider": PROVIDER,
            "requested_provider": PROVIDER, "api_mode": "chat_completions",
            "api_key": None, "base_url": None}}
        self.sequence = 0
        self.admit()
        self.registrations = []
        context = PluginContext(PluginManifest(name="mmx-gateway-fixture"), _delivery_manager())
        for method in ("register_hook", "register_middleware", "on_unload"):
            original = getattr(context, method)
            def tracked(*args, _original=original, **kwargs):
                handle = _original(*args, **kwargs)
                self.registrations.append(handle)
                return handle
            setattr(context, method, tracked)
        self.host = gateway_plugin.register(context)
        register_native_provider()
        self.bind_calls = []

    def tearDown(self):
        self.host.dispose()
        for handle in reversed(self.registrations):
            handle.dispose()
        self.db.close()
        self.temp.cleanup()
        fixtures.OwnerLoopbackTests.tearDown(self)

    def admit(self):
        from hermes_state_runtime import admit_session_input, claim_session_input
        from gateway.session_contract import SessionRef
        self.sequence += 1
        admit_session_input(self.db, epoch=self.authority.epoch, principal_id="fixture-user",
            session_id="session-1", request_id=f"input-{self.sequence}", payload={"text": "Fixture"})
        self.row = claim_session_input(self.db, epoch=self.authority.epoch, session_id="session-1")
        with patch.object(self.authority, "_publish_pending"):
            self.authority._stamp_claim(SessionRef(self.authority.profile_id, "session-1"),
                                       self.live, self.row)

    def settle(self):
        from hermes_state_runtime import settle_session_input
        settle_session_input(self.db, epoch=self.authority.epoch, admission_id=self.row["admission_id"],
            generation=self.row["generation"], outcome="completed")
        self.authority.executing.pop("session-1", None)

    def bind_fixture(self, factory, **kwargs):
        self.bind_calls.append(kwargs)
        self.owner = FabricInferenceClient(base_url=f"http://127.0.0.1:{self.server.server_port}/v1",
            proxy_token="t" * 40, model="model-1", protocol=NATIVE_PROTOCOL,
            operation_id=kwargs["operation_id"])
        self.binding = object.__new__(ApplicationBinding)
        self.binding._owner = self.owner
        self.binding.operation_id = kwargs["operation_id"]
        self.binding.session_id, self.binding.turn_id = kwargs["session_id"], kwargs["turn_id"]
        self.binding.model, self.binding.requested_model = "model-1", kwargs["requested_model"]
        self.binding._authorized = kwargs["authorized"]
        return self.binding

    def owner_fixture(self):
        stack = ExitStack()
        stack.enter_context(patch.object(gateway_plugin, "_original_factory", return_value=object()))
        stack.enter_context(patch.object(ApplicationBinding, "from_factory", side_effect=self.bind_fixture))
        return stack

    def native_agent(self, tools=None):
        from gateway.session_execution import GatewaySessionAgentMixin
        holder = GatewaySessionAgentMixin()
        holder._ctx, holder._runner = self.ctx, self.runner
        self.ctx.enabled_toolsets = tools or []
        policy = N(verbose=False, ignore_rules=True, pass_session_id=False, run_budget_seconds=None)
        with patch("gateway.session_policy.policy_for_source", return_value=policy), \
             patch("gateway.session_worker_construct.session_prefill", return_value=None):
            return holder._build_fresh_agent(self.route, "local", None, 3, {}, {}, True)

    def scope(self):
        from gateway.session_provider_context import provider_turn_scope
        return provider_turn_scope(self.runner, self.ctx, self.route)

    def test_cli_resolves_registered_keyless_provider_without_placeholder(self):
        from hermes_cli.cli_agent_setup_mixin import CLIAgentSetupMixin
        from hermes_cli.runtime_provider import resolve_runtime_provider
        cli = N(requested_provider=PROVIDER, _explicit_api_key=None, _explicit_base_url=None,
            model="model-1", provider=PROVIDER, api_mode="chat_completions", api_key=None,
            base_url=None, acp_command=None, acp_args=[], agent=None,
            _normalize_model_for_provider=lambda _: False)
        with patch("hermes_cli.runtime_provider._get_model_config", return_value={}):
            runtime = resolve_runtime_provider(requested=PROVIDER, target_model="model-1")
            self.assertIsNone(runtime["api_key"])
            self.assertIsNone(runtime["base_url"])
            self.assertTrue(CLIAgentSetupMixin._ensure_runtime_credentials(cli))
            self.assertEqual(CLIAgentSetupMixin._probe_runtime_credentials(cli), (True, None))
        self.assertEqual((cli.api_key, cli.base_url), (None, None))
        self.assertEqual(self.calls, [])

    def test_ordinary_missing_credentials_still_refuse(self):
        from hermes_cli.cli_agent_setup_mixin import CLIAgentSetupMixin
        cli = N(requested_provider="openrouter", _explicit_api_key=None, _explicit_base_url=None)
        with patch("hermes_cli.runtime_provider._get_model_config", return_value={}):
            self.assertFalse(CLIAgentSetupMixin._probe_runtime_credentials(cli)[0])
        self.assertEqual(self.calls, [])

    def test_fabric_endpoint_or_key_override_refuses_before_factory(self):
        from hermes_cli.runtime_provider import resolve_runtime_provider
        for options in ({"explicit_api_key": "fixture-not-a-secret"},
                        {"explicit_base_url": "http://127.0.0.1:9/v1"}):
            with patch("hermes_cli.runtime_provider._get_model_config", return_value={}):
                with self.assertRaises(RuntimeError):
                    resolve_runtime_provider(requested=PROVIDER, **options)
        self.assertEqual(self.bind_calls, [])

    def test_native_admission_drives_primary_inference_and_once_only_close(self):
        from run_agent import AIAgent
        with self.owner_fixture(), self.scope():
            agent = self.native_agent()
            result = agent.run_conversation("Reply with fixture result.", task_id="session-1")
            self.assertEqual(result["final_response"], "Result 世界")
            self.assertEqual(self.closed, 0)
        self.assertIs(self.ctx.AIAgent, AIAgent)
        self.assertEqual((len(self.bind_calls), len(self.calls), self.closed), (1, 1, 1))
        self.assertEqual(self.bind_calls[0]["operation_id"], self.row["admission_id"])
        self.assertEqual(self.calls[0]["turn_id"], self.row["admission_id"])
        with self.assertRaisesRegex(Exception, "provider_turn_recovery_required"):
            with self.scope():
                self.fail("A closed admission was reconstructed")

    def test_current_native_stop_blocks_followup_without_another_model_call(self):
        with self.owner_fixture(), self.scope():
            agent = self.native_agent()
            self.assertEqual(agent.run_conversation("First.", task_id="session-1")["final_response"], "Result 世界")
            self.authority.pending_stops["session-1"] = self.row["generation"]
            result = agent.run_conversation("Late.", task_id="session-1")
            self.assertNotEqual(result.get("final_response"), "Result 世界")
        self.assertEqual(len(self.calls), 1)

    def test_binding_failure_latches_across_plugin_replacement_and_model_change(self):
        from integrations.hermes_application_fabric.errors import HermesFabricError
        with patch.object(gateway_plugin, "_original_factory",
                          side_effect=HermesFabricError("hermes_fabric_role_unqualified")) as factory:
            with self.assertRaises(HermesFabricError):
                with self.scope():
                    self.fail("Unqualified owner entered")
            self.host.dispose()
            self.route["model"] = "different-model"
            with self.assertRaisesRegex(Exception, "provider_turn_recovery_required"):
                with self.scope():
                    self.fail("Provider/model replacement retried admission")
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(self.calls, [])

    def test_new_native_admission_invalidates_old_binding(self):
        from gateway.session_provider_context import AdmittedProviderTurn
        old = self.authority.bind_provider_turn(self.ctx)
        self.settle()
        self.admit()
        self.assertFalse(old.current())
        new = self.authority.bind_provider_turn(self.ctx)
        self.assertIs(type(new), AdmittedProviderTurn)
        self.assertNotEqual(old.operation_id, new.operation_id)
        self.assertTrue(new.current())

    def test_atomic_consumption_has_one_winner(self):
        barrier = threading.Barrier(2)
        def claim():
            barrier.wait(timeout=5)
            try:
                return self.authority.bind_provider_turn(self.ctx).operation_id
            except Exception as exc:
                return str(exc)
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = list(pool.map(lambda _: claim(), range(2)))
        self.assertCountEqual([a, b], [self.row["admission_id"], "provider_turn_recovery_required"])

    def test_zero_or_multiple_contexts_refuse_without_entry(self):
        for returned in ([], [nullcontext(), nullcontext()]):
            if self.live.host_provider_claim is not None:
                self.settle()
                self.admit()
            with patch("hermes_cli.plugins.invoke_hook", return_value=returned):
                with self.assertRaisesRegex(Exception, "provider_turn_binding_required"):
                    with self.scope():
                        self.fail("Missing or ambiguous binding entered")
        self.assertEqual(self.calls, [])

    def test_native_restart_unknown_row_cannot_be_reopened(self):
        from hermes_state_runtime import begin_runtime_epoch, recover_session_inputs, claim_session_input
        epoch = begin_runtime_epoch(self.db, instance_id="replacement-fixture")
        recover_session_inputs(self.db, epoch=epoch)
        with self.assertRaisesRegex(Exception, "unknown_execution"):
            claim_session_input(self.db, epoch=epoch, session_id="session-1")
        self.authority.epoch = epoch
        with self.assertRaisesRegex(Exception, "stale_generation"):
            with self.scope():
                self.fail("Unknown native execution reopened")
        self.assertEqual(self.calls, [])

    def test_real_turn_runner_enters_hook_before_constructor_and_closes_on_error(self):
        from gateway.run_turn_runner import TurnRunner
        class EndFixture(Exception):
            pass
        self.runner._resolve_session_agent_runtime = lambda **_: ("model-1", self.route["runtime"])
        self.runner._resolve_turn_agent_config = lambda *_: self.route
        tr = TurnRunner(self.runner, self.ctx)
        def execute(*_, **__):
            result = self.native_agent().run_conversation("Fixture.", task_id="session-1")
            self.assertEqual(result["final_response"], "Result 世界")
            self.assertEqual(self.closed, 0)
            raise EndFixture()
        with self.owner_fixture(), \
             patch("gateway.session_policy.policy_for_source", return_value=None), \
             patch.object(tr, "_combined_ephemeral_prompt", return_value=None), \
             patch.object(tr, "_setup_stream_consumer", return_value=(None, None, None, False)), \
             patch.object(tr, "_resolve_turn_agent", side_effect=execute):
            with self.assertRaises(EndFixture):
                tr.run_sync()
        self.assertEqual((len(self.calls), self.closed), (1, 1))


if __name__ == "__main__":
    unittest.main()
