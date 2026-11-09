"""Pinned native CLI/gateway composition, with real SQLite admission and fixture inference."""
from contextlib import ExitStack, contextmanager, nullcontext
from dataclasses import replace
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import shutil
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch

import test_owner_integration as fixtures
from engine.fabric_inference_client import FabricInferenceClient, NATIVE_PROTOCOL
from integrations.hermes_application_fabric.client import ApplicationBinding
from integrations.hermes_application_fabric.native import PROVIDER, register_native_provider
from integrations.hermes_application_fabric import gateway_plugin


class FixtureSourceOwner:
    """Only the installed-source boundary is doubled in native loopback tests."""
    def __init__(self):
        self.references = 0
        self.closed = False
        self.current = True

    def check(self):
        if self.closed or not self.current:
            from integrations.hermes_application_fabric.errors import HermesFabricError
            raise HermesFabricError("hermes_fabric_source_unavailable")

    def close(self):
        self.closed = True

    def factory(self):
        raise AssertionError("native loopback must select its explicit owner fixture")


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
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        token = set_hermes_home_override(self.temp.name)
        self.addCleanup(reset_hermes_home_override, token)
        provider = Path(self.temp.name) / "plugins/mastermind-fabric"
        shutil.copytree(Path(gateway_plugin.__file__).parent / "model_provider", provider)
        (Path(self.temp.name) / "config.yaml").write_text("plugins:\n  enabled: [mastermind-fabric]\n")
        from providers import refresh_bound_home
        refresh_bound_home()
        from integrations.hermes_application_fabric.source_context import _SourceLease
        self.source_owners = []
        def open_fixture_sources(**_):
            source = FixtureSourceOwner()
            self.source_owners.append(source)
            return _SourceLease(source)
        source_patch = patch.object(gateway_plugin, "open_attended_source_context", side_effect=open_fixture_sources)
        source_patch.start()
        self.addCleanup(source_patch.stop)
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
        self.route = {"model": "model-1", "source": "host_bound", "runtime": {"provider": PROVIDER,
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
        self.bind_calls = []

    def tearDown(self):
        self.host.dispose()
        for handle in reversed(self.registrations):
            handle.dispose()
        self.db.close()
        from hermes_logging import release_profile_log_handlers
        release_profile_log_handlers(self.temp.name)
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
        self.binding.automatic = False
        self.binding._max_output_tokens = 4096
        self.binding._authorized = kwargs["authorized"]
        return self.binding

    @contextmanager
    def owner_fixture(self, *, automatic=False):
        with ExitStack() as stack:
            if automatic:
                # The real factory/client use only this disposable enrollment.
                # Source permission and account responses remain fixtures.
                from engine import provider_production_modes as owner
                source = Path(owner.__file__).resolve().parents[1]
                config_root = Path(self.temp.name) / "owner"
                config = config_root / "config"
                config.mkdir(parents=True, exist_ok=True)
                (config / "provider_workloads.v1.json").write_bytes(
                    (source / "config/provider_workloads.v1.json").read_bytes())
                transport_id = "native_fabric_hermes_attended_auto_v1"
                original = owner._APPLICATION_FABRIC_TRANSPORTS[transport_id]
                self.assertTrue(original.qualified and original.application_allowed)
                qualified = replace(original,
                    base_url=f"http://127.0.0.1:{self.server.server_port}/v1")
                # This public enrollment identity names the environment slot;
                # the disposable credential value remains in patch.dict below.
                reference_name = "HERMES_ATTENDED_FABRIC_APPLICATION_TOKEN"
                self.assertEqual(qualified.secret_ref, reference_name)
                stack.enter_context(patch.dict(owner._APPLICATION_FABRIC_TRANSPORTS,
                                               {transport_id: qualified}))
                row = {key: getattr(qualified, key) for key in owner._APPLICATION_IDENTITY_FIELDS}
                row.update(transport_id=transport_id, enabled=True, application_allowed=True,
                    qualification=owner.PROFILE_QUALIFIED_CANARY,
                    qualification_ref="fixture:attended-auto", qualified_until=time.time() + 300,
                    route_scope={"schema": "mastermind.application_route_scope.v1", "pools": ["go"]})
                document = json.loads((source / "config/provider_production_modes.v1.json").read_text())
                self.assertEqual(document["application_fabric_modes"], {})
                document["application_fabric_modes"] = {"hermes_attended_fabric": row}
                rendered = json.dumps(document)
                self.assertNotIn("t" * 40, rendered)
                (config / "provider_production_modes.v1.json").write_text(rendered)
                capability_document = json.dumps({"capabilities": [{
                    "capability_id": qualified.capability_id, "secret_ref": reference_name,
                    "kill_state": "active", "allowed_lanes": ["hermes-attended"]}]})
                self.assertNotIn("t" * 40, capability_document)
                (config / "capability_manifest.yml").write_text(capability_document)
                stack.enter_context(patch.dict(os.environ,
                    {qualified.secret_ref: "t" * 40, "MM_PROVIDER_WORKLOAD_PROFILE": "hermes_attended"}))
                factory = owner.make_application_fabric_factory(mode_id="shared_fabric",
                    lane="hermes-attended", root=config_root, service_mode_id="hermes_attended_fabric",
                    workload_cfg={"workload_profile": "hermes_attended", "provider_order": ["fabric"]})
                observed = (factory if self.route["model"] == f"{PROVIDER}/auto"
                            else factory.with_requested_model(self.route["model"]))
                self.auto_inspection = observed.inspect()
                stack.enter_context(patch.object(gateway_plugin, "_original_factory", return_value=factory))
            else:
                stack.enter_context(patch.object(gateway_plugin, "_original_factory",
                                                return_value=N(inspect=lambda: {"model": "model-1"})))
                stack.enter_context(patch.object(ApplicationBinding, "from_factory",
                                                side_effect=self.bind_fixture))
            yield

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
        from hermes_cli.models import static_catalog, get_default_model_for_provider
        self.assertIn(f"{PROVIDER}/auto", static_catalog(PROVIDER))
        self.assertEqual(get_default_model_for_provider(PROVIDER), f"{PROVIDER}/auto")
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

    def test_actual_resolver_projection_scope_and_constructor_preserve_one_admission(self):
        from gateway.run import _runtime_agent_kwargs
        from gateway.run_turn_prepare import GatewayTurnPrepareMixin
        from hermes_cli.runtime_provider import resolve_runtime_provider
        from run_agent import AIAgent
        with patch("hermes_cli.runtime_provider._get_model_config", return_value={}):
            resolved = resolve_runtime_provider(requested=PROVIDER, target_model="model-1")
        self.assertEqual(resolved["source"], "host_bound")
        projected = _runtime_agent_kwargs(resolved)
        self.route = GatewayTurnPrepareMixin._resolve_turn_agent_config(
            self.runner, "Read the fixture.", "model-1", projected)
        self.assertEqual(self.route["source"], "host_bound")
        self.assertNotIn("source", self.route["runtime"])
        with self.owner_fixture(), self.scope():
            native = self.native_agent()
            result = native.run_conversation("Reply with the fixture result.", task_id="session-1")
            self.assertEqual(result.get("final_response"), "Result 世界")
        self.assertIs(self.ctx.AIAgent, AIAgent)
        self.assertEqual(len(self.bind_calls), 1)
        self.assertEqual(self.bind_calls[0]["operation_id"], self.row["admission_id"])
        self.assertEqual((len(self.calls), self.closed), (1, 1))
        self.assertTrue(self.calls[0]["authenticated"])

    def test_role_host_route_does_not_consume_attended_claim_or_constructor(self):
        from gateway.run import _runtime_agent_kwargs
        from gateway.run_turn_prepare import GatewayTurnPrepareMixin
        original_constructor = self.ctx.AIAgent
        role_runtime = dict(self.route["runtime"])
        projected = _runtime_agent_kwargs(role_runtime)
        self.route = GatewayTurnPrepareMixin._resolve_turn_agent_config(
            self.runner, "Role fixture.", "model-1", projected)
        self.assertNotIn("source", self.route)
        with patch.object(gateway_plugin, "_original_factory") as factory, self.scope():
            self.assertIs(self.ctx.AIAgent, original_constructor)
            self.assertIsNone(self.live.host_provider_claim)
        factory.assert_not_called()
        self.assertEqual(self.calls, [])

    def test_marked_non_host_bound_runtime_refuses_before_claim_or_factory(self):
        from hermes_state_runtime import RuntimeStoreError
        self.route["runtime"]["provider"] = "openrouter"
        self.route["runtime"]["requested_provider"] = "openrouter"
        with patch.object(gateway_plugin, "_original_factory") as factory:
            with self.assertRaises(RuntimeStoreError):
                with self.scope():
                    self.fail("Invalid marked runtime entered provider scope")
        self.assertIsNone(self.live.host_provider_claim)
        factory.assert_not_called()
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

    def test_native_auto_uses_original_factory_and_actual_served_model(self):
        self.route["model"] = f"{PROVIDER}/auto"
        with self.owner_fixture(automatic=True), self.scope():
            agent = self.native_agent()
            result = agent.run_conversation("Reply with fixture result.", task_id="session-1")
            self.assertEqual(result["final_response"], "Result 世界")
            binding = self.host._scope.get()._binding
            self.assertTrue(binding.automatic)
            self.assertIsNone(binding.model)
            observation = binding._owner.application_observation.document
            self.assertEqual(observation["routing"]["selected_model"], "model-1")
        self.assertEqual(len(self.calls), 1)
        self.assertIsNone(self.calls[0]["payload"]["model"])
        self.assertEqual(self.calls[0]["turn_id"], self.row["admission_id"])
        self.assertEqual(self.closed, 1)

    def test_native_exact_model_uses_the_enrolled_auto_scope(self):
        with self.owner_fixture(automatic=True), self.scope():
            result = self.native_agent().run_conversation("Reply with fixture result.", task_id="session-1")
            self.assertEqual(result["final_response"], "Result 世界")
            binding = self.host._scope.get()._binding
            self.assertTrue(binding.automatic)
            self.assertEqual(binding.model, "model-1")
            routing = binding._owner.application_observation.document["routing"]
            self.assertEqual((routing["requested_model"], routing["selected_model"]), ("model-1",) * 2)
        self.assertEqual(self.calls[0]["payload"]["model"], "model-1")
        self.assertEqual((len(self.calls), self.closed), (1, 1))

    def test_new_auto_turn_can_change_model_with_a_new_original_admission(self):
        self.route["model"] = f"{PROVIDER}/auto"
        models, operations = [], []
        with self.owner_fixture(automatic=True):
            for model in ("model-1", "model-2"):
                self.serving_model = model
                with self.scope():
                    result = self.native_agent().run_conversation("Reply with fixture result.", task_id="session-1")
                    self.assertEqual(result["final_response"], "Result 世界")
                    binding = self.host._scope.get()._binding
                    models.append(binding._owner.application_observation.document["routing"]["selected_model"])
                    operations.append(binding.operation_id)
                if model == "model-1":
                    self.settle()
                    self.admit()
        self.assertEqual(models, ["model-1", "model-2"])
        self.assertEqual(len(set(operations)), 2)
        self.assertEqual([call["turn_id"] for call in self.calls], operations)
        self.assertTrue(all(call["payload"]["model"] is None for call in self.calls))
        self.assertEqual(self.closed, 2)

    def test_native_auto_label_cannot_enable_a_fixed_owner(self):
        self.route["model"] = f"{PROVIDER}/auto"
        with self.owner_fixture(), self.assertRaisesRegex(Exception, "hermes_fabric_auto_owner_required"):
            with self.scope():
                self.fail("A native model label granted AUTO enrollment")
        self.assertEqual(self.bind_calls, [])
        self.assertEqual(self.calls, [])

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


    def test_agent_construction_preserves_the_home_profile_and_catalog(self):
        from providers import bound_profile_resolver
        profile = bound_profile_resolver()(PROVIDER)[0]
        catalog = profile.picker_catalog
        with self.owner_fixture(), self.scope():
            self.native_agent()
            self.native_agent()
        self.assertIs(bound_profile_resolver()(PROVIDER)[0], profile)
        self.assertIs(profile.picker_catalog, catalog)
        self.assertEqual(self.calls, [])

    def test_catalog_is_home_scoped_and_native_unload_restores_its_slot(self):
        from providers import bound_profile_resolver
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        profile = bound_profile_resolver()(PROVIDER)[0]
        catalog = profile.picker_catalog
        with self.owner_fixture():
            self.assertEqual(catalog(), ["model-1"])
            token = set_hermes_home_override(Path(self.temp.name) / "another-home")
            try:
                self.assertEqual(catalog(), [])
            finally:
                reset_hermes_home_override(token)
        self.registrations[-1].dispose()
        self.assertIsNone(profile.picker_catalog)
        self.assertEqual(catalog(), [])
        self.assertTrue(self.source_owners[0].closed)
        self.assertEqual(self.calls, [])

    def test_source_change_revokes_followup_and_preserves_original_close(self):
        with self.owner_fixture(), self.scope():
            agent = self.native_agent()
            self.assertEqual(agent.run_conversation("First.", task_id="session-1")["final_response"], "Result 世界")
            self.source_owners[0].current = False
            result = agent.run_conversation("Late.", task_id="session-1")
            self.assertNotEqual(result.get("final_response"), "Result 世界")
        self.assertEqual((len(self.calls), self.closed), (1, 1))

    def test_native_plugin_loader_registers_and_unloads_real_entrypoint(self):
        from hermes_cli.plugins import PluginManager
        from hermes_cli.plugins_manifest import parse_manifest_file, manifest_key
        from hermes_constants import get_hermes_home
        directory = Path(gateway_plugin.__file__).parent / "gateway_plugin_entry"
        manifest = parse_manifest_file(directory / "plugin.yaml", directory, "user", "")
        self.assertIsNotNone(manifest)
        self.assertEqual(set(manifest.python_dependencies), {"jsonschema==4.26.0", "PyYAML==6.0.3"})
        manager = PluginManager(scope_key=str(get_hermes_home()))
        try:
            manager._load_plugin(manifest)
            loaded = manager._plugins[manifest_key(manifest)]
            self.assertIsNone(loaded.error)
            self.assertEqual(len(manager._hooks.get("provide_gateway_turn_context", [])), 1)
            self.assertEqual(len(manager._middleware.get("llm_execution", [])), 1)
        finally:
            manager.unload(manifest)
        self.assertFalse(manager._hooks.get("provide_gateway_turn_context"))
        self.assertFalse(manager._middleware.get("llm_execution"))


if __name__ == "__main__":
    unittest.main()
