"""Pinned native lifecycle bodies, actual adapter/SDK, explicit service edges.

These component proofs execute original Hermes discovery, collector, manager,
agent initialization, resolver, adoption, prefetch and prompt composition.
The model, profile config, plugin manager and remote MCP service are controlled
edges. They do not prove an installed enrollment, provider dispatch or efficacy.
"""
from __future__ import annotations

import ast
import asyncio
import contextlib
from contextvars import ContextVar
from dataclasses import replace
import copy
import hashlib
import json
import logging
from pathlib import Path
import sys
import threading
from types import SimpleNamespace, MethodType
from typing import Any, Optional

import pytest

from integrations.hermes_harness import native_executive_consumer as consumer
from integrations.hermes_harness.native_byok import render_qualified_native_byok
from integrations.hermes_harness.tests.test_native_agentos_context import (
    actual_result, context_document, decoded_fixture, sdk_result)
from integrations.hermes_harness.tests.test_native_executive_consumer import _McpLoop, _Owner, _Session
from integrations.hermes_runtime import native_agentos_memory as memory
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.tests.test_native_request_observation import module, native

FIXTURES = Path(__file__).parent / "fixtures/agentos_memory"
MANIFEST = json.loads((FIXTURES / "provenance.json").read_text())
ROOT = Path(__file__).resolve().parents[3]



def privacy_selection():
    return {"kind": memory.PRIVACY_DERIVATION_KIND, "base_sha": memory.DERIVATION_BASE,
        "patch_sha256": memory.PRIVACY_DERIVATION_PATCH, "source_root": "/opt/hermes/privacy-pristine"}


def privacy_receipt(vendor):
    return {"kind": memory.PRIVACY_DERIVATION_KIND, "base_sha": memory.DERIVATION_BASE,
        "patch_sha256": memory.PRIVACY_DERIVATION_PATCH,
        "postimages": dict(memory.PRIVACY_DERIVATION_POSTIMAGES),
        "license_sha256": memory.PRIVACY_LICENSE_SHA256, "vendor_root": str(vendor)}


def edge(monkeypatch, name, **values):
    result = module(monkeypatch, name, **values)
    parent, _, attr = name.rpartition(".")
    if parent in sys.modules:
        monkeypatch.setattr(sys.modules[parent], attr, result, raising=False)
    return result


def source(monkeypatch, vendor, path, *, names=None, methods=None, values=None):
    """Execute selected pinned ASTs (or full module), at the qualified origin."""
    item = MANIFEST["files"][path]
    data = (FIXTURES / item["fixture"]).read_bytes()
    assert len(data) == item["bytes"]
    assert hashlib.sha256(data).hexdigest() == item["sha256"]
    assert hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == item["git_blob"]
    target = vendor / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    name = path.removesuffix("/__init__.py").removesuffix(".py").replace("/", ".")
    namespace = dict(__file__=str(target), **(values or {}))
    if path.endswith("/__init__.py"):
        namespace["__path__"] = [str(target.parent)]
    result = edge(monkeypatch, name, **namespace)
    tree = ast.parse(data, filename=str(target))
    if names is not None:
        selected = []
        for node in tree.body:
            if getattr(node, "name", None) in names:
                if isinstance(node, ast.ClassDef) and methods:
                    node.body = [child for child in node.body if getattr(child, "name", None) in methods]
                selected.append(node)
        assert {node.name for node in selected} == set(names)
        future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
        tree = ast.fix_missing_locations(ast.Module(body=[future, *selected], type_ignores=[]))
    exec(compile(tree, str(target), "exec"), vars(result))
    return result


@pytest.fixture
def lifecycle(native, decoded_fixture, monkeypatch):
    publication, sdk, produced = decoded_fixture
    cfg = {"memory": {"provider": "agentos", "memory_enabled": False, "user_profile_enabled": False},
           "plugins": {"enabled": [consumer.CONSUMER_PLUGIN_NAME]}}
    manager = SimpleNamespace(scope_key=str(native.home), _plugins={}, _discovery_lock=threading.RLock(),
                              _drop_fallback_hooks=lambda *_: None)
    class PluginContext:
        def __init__(self, manifest, manager):
            self._manager, self.manifest = manager, manifest
    edge(monkeypatch, "hermes_cli.plugins", get_plugin_manager=lambda: manager,
         PluginContext=PluginContext, PluginManifest=SimpleNamespace)
    edge(monkeypatch, "hermes_cli.plugins_ledger", _hook_source_of=lambda name, mod: (name, mod.__file__))
    edge(monkeypatch, "hermes_cli.profiles", get_active_profile_name=lambda: "mmsecretary")
    def cfg_get(value, *keys, default=None):
        for key in keys:
            if type(value) is not dict:
                return default
            value = value.get(key, default)
        return value
    edge(monkeypatch, "hermes_cli.config", load_config=lambda: cfg, load_config_readonly=lambda: cfg, cfg_get=cfg_get)
    home_override = ContextVar("fixture_home", default=None)
    edge(monkeypatch, "hermes_constants", get_hermes_home=lambda: Path(home_override.get() or native.home),
         get_hermes_home_override=home_override.get, set_hermes_home_override=home_override.set,
         reset_hermes_home_override=home_override.reset,
         hermes_home_key=lambda home=None: str(Path(home or home_override.get() or native.home).resolve()))
    edge(monkeypatch, "agent.secret_scope", is_multiplex_active=lambda: False, current_secret_scope_home=lambda: None)
    edge(monkeypatch, "agent.safe_worker_policy", safe_worker_enabled=lambda: False)
    edge(monkeypatch, "agent.memory_manager_tools", inject_memory_provider_tools=lambda agent: None,
         memory_provider_tools_enabled=lambda *_: False, memory_provider_tools_exposed=lambda *_: False,
         normalize_tool_schema=lambda schema: schema)
    monkeypatch.setattr(sys.modules["agent.redact"], "redact_for_egress", lambda value: value, raising=False)
    edge(monkeypatch, "agent.skill_commands", extract_user_instruction_from_skill_message=lambda text: text)
    for name in ("tools", "plugins"):
        edge(monkeypatch, name, __path__=[str(native.vendor / name)])
    spill = edge(monkeypatch, "tools.hook_output_spill", get_spill_config=lambda: {"max_chars": 10000},
                 spill_if_oversized=lambda text, **_: text)
    edge(monkeypatch, "tools.registry", tool_error=lambda text: json.dumps({"error": text}))
    edge(monkeypatch, "toolsets", _HERMES_CORE_TOOLS={"clarify", "memory", "delegate_task"})
    source(monkeypatch, native.vendor, "agent/memory_provider.py")
    fences = source(monkeypatch, native.vendor, "agent/memory_context.py")
    source(monkeypatch, native.vendor, "agent/memory_caller_scope.py")
    source(monkeypatch, native.vendor, "agent/memory_manager.py")
    source(monkeypatch, native.vendor, "plugins/plugin_loader.py")
    source(monkeypatch, native.vendor, "plugins/memory/__init__.py")
    source(monkeypatch, native.vendor, "hermes_cli/plugin_isolation.py")
    source(monkeypatch, native.vendor, "tools/thread_context.py")
    stores = []
    def memory_store(**kwargs):
        stores.append(kwargs)
        raise AssertionError("Agent OS composition must not construct independent file memory")
    source(monkeypatch, native.vendor, "tools/memory_tool.py",
           names={"get_builtin_memory_config", "get_builtin_memory_store_flags"},
           values={"logger": logging.getLogger(__name__), "MemoryStore": memory_store,
                   "is_truthy_value": lambda value, default=True: default if value is None else bool(value)})
    agent_init = source(monkeypatch, native.vendor, "agent/agent_init.py",
        names={"_init_memory", "_memory_provider_init_kwargs"},
        values={"suppress": contextlib.suppress, "get_hermes_home": lambda: native.home,
            "_GATEWAY_IDENTITY_PARAMS": (), "_ra": lambda: SimpleNamespace(logger=logging.getLogger(__name__)),
            "is_core_memory_provider": lambda name: name in (None, "", "builtin"),
            "_unavailable_warning_key": str, "_warned_unavailable_providers": set(),
            "_warn_memory_provider_unavailable": lambda *_a, **_k: None})
    edge(monkeypatch, "gateway.session_authorities", active_authority=lambda runner: native.authority)
    edge(monkeypatch, "gateway.session_worker_construct", session_prefill=lambda *_: None)
    monkeypatch.setattr(sys.modules["gateway.run"], "_checkpoint_agent_kwargs", lambda cfg: {}, raising=False)
    execution = source(monkeypatch, native.vendor, "gateway/session_execution.py",
        names={"GatewaySessionAgentMixin"}, methods={"_resolve_turn_agent", "_build_fresh_agent"},
        values={"api_runtime_locked": lambda: None, "logger": logging.getLogger(__name__)})
    edge(monkeypatch, "gateway.run_turn_progress", local_viewer_turn=lambda turn: False)
    monkeypatch.setattr(sys.modules["gateway.session_api_turn"], "wire_api_observers", lambda *_: None, raising=False)
    monkeypatch.setattr(sys.modules["gateway.session_surface"], "arm_surface_turn", lambda *_a, **_k: None, raising=False)
    turns = source(monkeypatch, native.vendor, "gateway/run_turn_runner.py", names={"TurnRunner"},
        methods={"_merge_turn_request_overrides", "_wire_turn_agent_callbacks"},
        values={"GatewayTurnProgressMixin": type("ProgressEdge", (), {}),
                "GatewaySessionAgentMixin": execution.GatewaySessionAgentMixin})
    monkeypatch.setattr(sys.modules["agent.conversation_loop"], "_clone_message_for_send", copy.deepcopy, raising=False)
    edge(monkeypatch, "agent.agent_runtime_helpers", fill_empty_non_final_wire_payload=lambda *_a, **_k: None)
    replay = edge(monkeypatch, "agent.replay_cleanup", canonicalize_replay_history=lambda rows, **_: rows)
    edge(monkeypatch, "agent.image_replay", replay_for_agent=lambda *_: None)
    edge(monkeypatch, "agent.anthropic_thinking_replay", apply_rejected_thinking_suppression=lambda *_: None)
    turn_context = source(monkeypatch, native.vendor, "agent/turn_context.py",
        names={"_memory_query_text", "_memory_turn_start_and_prefetch", "build_api_messages",
               "compose_multimodal_context_part", "compose_user_api_content"},
        values={"suppress": contextlib.suppress, "build_memory_context_block": fences.build_memory_context_block,
                "flatten_message_text": lambda value: value if isinstance(value, str) else " ".join(
                    part.get("text", "") for part in value if type(part) is dict),
                "is_trivial_prompt": lambda value: len(value.strip()) < 5,
                "PERSISTENCE_ONLY_MESSAGE_FIELDS": {"_row_id", "timestamp", "display_content"},
                "reanchor_current_turn_user_idx": lambda rows, user: len(rows) - 1})
    document = context_document(produced["frame"] if "frame" in produced else None,
                                produced["coo"]["binding"]["binding"])
    # Use the already validated compiler result's exact context identities.
    document.update({name: getattr(publication, name) for name in (
        "work_ref", "principal_binding_digest", "mission_authority_ref", "authority_generation_digest",
        "capability_profile_digest")})
    publication = consumer.publication_from_document(document)
    slot = consumer.install_consumer_slot(manager, consumer.ConsumerSlot(owner="a" * 40,
        profile_id="mmsecretary", source=consumer.CONSUMER_PLUGIN_SOURCE,
        plugin_id=consumer.CONSUMER_PLUGIN_NAME, publication=publication))
    slot.package_path = str(ROOT / "integrations/hermes_harness/native_selected_child_plugin")
    slot.package_check = lambda: True  # Held source importer is tested at its own boundary.
    slot.import_current = lambda: True
    native.launch.owner.root = ROOT
    # Explicit retained release-owner edge, not an installed host grant.
    native.launch.recipe = {"executive_consumer": document, "vendor_root": str(native.vendor),
        "vendor_derivation": privacy_selection()}
    native.launch.derivation = privacy_receipt(native.vendor)
    factory = memory.install_native_agentos_memory(native.launch, native.vendor, native.home, native.binding)
    loop = _McpLoop()
    session = _Session(results=[sdk] * 20)
    server = _Owner(session)
    connection_ok = [True]
    factory.configure(session_id="session-1", instance_id="instance-1", authority_epoch=2,
        server=server, session=session, loop=loop.loop, currentness=lambda: connection_ok[0],
        connection_current=lambda: connection_ok[0] and server.session is session)
    # The real service qualification is a separate tested boundary. This edge
    # supplies only its retained, current result, never an installed grant.
    slot.context_registration = PluginContext(None, manager)
    slot.loader_record = SimpleNamespace(enabled=True, error=None)
    manager._plugins[consumer.CONSUMER_PLUGIN_NAME] = slot.loader_record
    slot.load_outcome = "CONTEXT_REGISTERED"
    runner = native.runner
    runner._prefill_messages = None
    runner._service_tier = None
    runner._session_db = None
    runner._agent_config_signature = lambda *_a, **_k: "config"
    runner._extract_cache_busting_config = lambda *_: ()
    runner._apply_fallback_chain_to_agent = lambda *_: None
    runner._refresh_fallback_model = lambda: None
    runner._consume_pending_turn_sidecar_notes = lambda *_: None
    runner._get_tools_prompt = lambda *_: None
    agents, native_managers = [], []
    def build_agent(**kwargs):
        agent = SimpleNamespace(**kwargs)
        agent._session_db, agent.session_cwd = None, None
        agent._emit_startup_warning = agent._emit_status = lambda *_: None
        agent._user_turn_count, agent._current_turn_timestamp = 1, 123.0
        agent._current_turn_id = "turn-" + str(len(agents) + 1)
        agent.tools = []
        agent._copy_reasoning_content_for_api = lambda *_: None
        agent._should_sanitize_tool_calls = lambda: False
        agent_init._init_memory(agent, cfg, False, "api")
        agents.append(agent)
        if agent._memory_manager is not None:
            native_managers.append(agent._memory_manager)
        return agent
    out = SimpleNamespace(native=native, factory=factory, slot=slot, manager=manager, cfg=cfg,
        session=session, server=server, loop=loop, connection_ok=connection_ok, stores=stores,
        agents=agents, turn_context=turn_context, spill=spill, replay=replay, sdk=sdk)
    def turn_for(ref, row, *, cached=None):
        turn = turns.TurnRunner()
        source_edge = SimpleNamespace(platform="api", user_id="user", user_id_alt=None, user_name=None,
            chat_id="chat", chat_name=None, chat_type="private", thread_id=None)
        ctx = SimpleNamespace(source=source_edge, user_config=cfg, enabled_toolsets=["clarify"],
            disabled_toolsets=["memory"], session_id="physical-" + ref.session_id, session_key=ref.session_id,
            AIAgent=build_agent, progress_callback=None, native_tool_start_callback=None, voice_ack_callback=None,
            _voice_ack_guild=[None], _native_slack_task_cards=False, native_tool_complete_callback=None,
            _step_callback_sync=lambda *_: None, _hooks_ref=SimpleNamespace(loaded_hooks=False),
            _status_callback_sync=None, _event_callback_sync=None, voice_turn=False, _status_adapter=None,
            run_generation=row["generation"], _thinking_enabled=False, mute_notification_reply=False,
            agent_holder=[None], tools_holder=[None], process_task_id=None, process_baseline=None)
        turn._ctx, turn._runner = ctx, runner
        turn._approval_owner = (native.authority, ref.session_id, row["generation"])
        turn._skip_context_files = lambda *_: True
        turn._cached_sid_is_dead = lambda *_: (None, False)
        turn._current_message_count = lambda: 0
        turn._lookup_cached_agent = lambda *_: SimpleNamespace(agent=cached, reused=cached is not None, evicted=None)
        for name in ("combined_tool_start_callback", "combined_tool_complete_callback", "_notice_callback_sync",
                     "_local_notice_callback_sync", "_local_notice_clear_callback_sync", "_clarify_callback_sync",
                     "_attach_session_title_callback"):
            setattr(turn, name, lambda *_: None)
        turn._make_bg_review_callbacks = lambda: (None, None)
        return turn
    out.turn_for = turn_for
    yield out
    for provider_manager in native_managers:
        provider_manager.shutdown_all()
    loop.close()


def exercise(lifecycle, *, admission="admission-1", generation=3, cached=None,
             before_adopt=None, before_prefetch=None, before_build=None, after_build=None, rows=None, text="use my current mission"):
    l, n = lifecycle, lifecycle.native
    ref, row, _ = n.claim(admission=admission, generation=generation)
    n.authority.adopted.pop(ref.session_id, None)  # Original wire callback must perform adoption.
    route = {"model": "fixture-model", "runtime": {}}
    result = {}
    def execute():
        turn = l.turn_for(ref, row, cached=cached)
        agent, reused = turn._resolve_turn_agent(route, "api", "", 3, None, {})
        result.update(agent=agent, reused=reused)
        assert agent._memory_store is None and not agent._memory_enabled and not agent._user_profile_enabled
        if before_adopt:
            before_adopt(agent)
        turn._wire_turn_agent_callbacks(agent, route, None, None, None, False)
        if before_prefetch:
            before_prefetch(agent)
        context = l.turn_context._memory_turn_start_and_prefetch(agent, text)
        result["context"] = context
        messages = copy.deepcopy(rows) if rows is not None else [{"role": "user", "content": text}]
        if before_build:
            before_build(agent, context, messages)
        built = l.turn_context.build_api_messages(agent, messages, current_turn_user_idx=len(messages) - 1,
            ext_prefetch_cache=context, plugin_user_context="", moa_config=None, active_system_prompt="system")
        result.update(built=built, live_readback=l.factory.readback())
        if after_build:
            after_build(agent, context, messages, built)
        return "component response"
    async def handle(event):
        return await n.runner._run_in_executor_with_context(execute)
    n.runner._handle_message = handle
    result["response"] = asyncio.run(n.finite.execute_finite_admission(n.authority, ref, row))
    result["settled_readback"] = l.factory.readback()
    return result


def test_native_lifecycle_attaches_actual_provider_and_observes_current_prompt(lifecycle):
    l = lifecycle
    cold = l.factory.readback()
    assert cold["context"]["factory_registered"] is True
    assert cold["context"]["provider_installed"] is False
    assert cold["context"]["last_delivery"] is None and cold["selected_child"] is None
    assert l.session.calls == []
    def before_adopt(agent):
        provider = agent._memory_manager.get_provider("agentos")
        assert provider.prefetch("unadopted", session_id=agent.session_id) == ""
        assert l.session.calls == []
    result = exercise(l, before_adopt=before_adopt)
    assert result["response"] == "component response"
    assert len(l.session.calls) == 1
    assert l.session.calls[0] == ("executive_agentos_context", {"work_ref": l.slot.publication.work_ref})
    assert l.stores == [] and l.slot.startup is None and l.slot.registration is None
    live = result["live_readback"]["context"]
    assert live["provider_installed"] is True and live["readiness"]["state"] == "READY"
    assert live["last_delivery"]["prompt"]["boundary"] == "build_api_messages"
    assert live["last_delivery"]["admission_id"] == "admission-1"
    assert "<memory-context>" in result["built"][0][-1]["content"]
    settled = result["settled_readback"]["context"]
    assert settled["provider_installed"] is False and settled["active_claim"] is None and settled["snapshot"] is None
    assert settled["last_delivery"] == live["last_delivery"]
    assert memory.validate_consumer_readback(result["settled_readback"], publication=l.slot.publication,
        expected_binding=result["settled_readback"]["binding"]) == result["settled_readback"]


def test_cached_agent_new_admission_rebinds_original_provider_and_refreshes(lifecycle):
    first = exercise(lifecycle)
    agent = first["agent"]
    provider = agent._memory_manager.get_provider("agentos")
    first_binding = provider._binding
    second = exercise(lifecycle, admission="admission-2", generation=4, cached=agent)
    assert second["reused"] is True and second["agent"] is agent
    assert agent._memory_manager.get_provider("agentos") is provider
    assert provider._binding.generation != first_binding.generation
    assert len(lifecycle.session.calls) == 2
    assert second["live_readback"]["context"]["last_delivery"]["admission_id"] == "admission-2"


def test_late_native_boundary_tracks_physical_session_rotation(lifecycle):
    result = exercise(lifecycle, before_prefetch=lambda agent: setattr(agent, "session_id", "physical-rotated"))
    live = result["live_readback"]["context"]
    assert live["active_claim"]["agent_session_id"] == "physical-rotated"
    assert live["last_delivery"]["agent_session_id"] == "physical-rotated"
    assert len(lifecycle.session.calls) == 1


@pytest.mark.parametrize("change", ["generation", "manager", "provider", "connection", "expired", "wrapper"])
def test_delivery_refuses_stale_claim_or_replaced_original_attachment(lifecycle, change):
    def drift(agent, context, messages):
        if change == "generation":
            lifecycle.native.rows["session-1"]["generation"] += 1
        elif change == "manager":
            agent._memory_manager = object()
        elif change == "provider":
            agent._memory_manager._providers = []
        elif change == "connection":
            lifecycle.server.session = object()
        elif change == "expired":
            provider = agent._memory_manager.get_provider("agentos")
            provider._clock = lambda: float("inf")
        else:
            provider = agent._memory_manager.get_provider("agentos")
            provider.prefetch = lambda *_a, **_k: context
    with pytest.raises(RuntimeRefusal):
        exercise(lifecycle, before_build=drift)
    assert len(lifecycle.session.calls) == 1
    assert lifecycle.factory.last_delivery["prompt"] is None


@pytest.mark.parametrize("change", ["disabled", "isolation"])
def test_native_loader_preserves_disabled_and_isolation_policy(lifecycle, change):
    if change == "disabled":
        lifecycle.cfg["plugins"]["disabled"] = [consumer.CONSUMER_PLUGIN_NAME]
    else:
        lifecycle.cfg["plugins"]["isolation"] = "host"
    with pytest.raises(RuntimeRefusal):
        exercise(lifecycle)
    assert lifecycle.session.calls == [] and lifecycle.factory.last_delivery is None


def test_current_prompt_observation_does_not_borrow_historical_sidecar(lifecycle):
    first = exercise(lifecycle)
    previous = first["built"][0][-1]["content"]
    def replace_current(agent, context, rows):
        rows[-1]["api_content"] = "current sidecar without the adopted context"
    result = exercise(lifecycle, admission="admission-2", generation=4, cached=first["agent"],
        rows=[{"role": "user", "content": "past", "api_content": previous},
              {"role": "assistant", "content": "past reply"}, {"role": "user", "content": "present"}],
        before_build=replace_current)
    assert result["live_readback"]["context"]["last_delivery"]["prompt"] is None
    assert previous in [row["content"] for row in result["built"][0]]


def test_prompt_observation_survives_canonical_prefix_removal(lifecycle):
    lifecycle.replay.canonicalize_replay_history = lambda rows, **_: []
    result = exercise(lifecycle, rows=[{"role": "user", "content": "obsolete"},
        {"role": "assistant", "content": "obsolete"}, {"role": "user", "content": "current"}])
    assert len(result["built"][0]) == 2
    assert result["live_readback"]["context"]["last_delivery"]["prompt"] is not None


def test_native_manager_spill_is_not_misreported_as_full_prompt_delivery(lifecycle):
    lifecycle.spill.spill_if_oversized = lambda text, **_: "bounded spill reference"
    # The manager imports this edge at module load, as the actual owner does.
    lifecycle.factory.modules["agent.memory_manager"].spill_if_oversized = lifecycle.spill.spill_if_oversized
    result = exercise(lifecycle)
    live = result["live_readback"]["context"]
    assert live["last_delivery"]["prefetch_context_bytes"] > 0
    assert live["last_delivery"]["prompt"] is None
    assert "bounded spill reference" in result["built"][0][-1]["content"]


def test_trivial_native_prompt_does_not_invent_injection(lifecycle):
    result = exercise(lifecycle, text="hi")
    assert len(lifecycle.session.calls) == 1  # Required context remains qualified.
    assert result["live_readback"]["context"]["readiness"]["state"] == "READY"
    assert result["context"] == ""
    assert result["live_readback"]["context"]["last_delivery"] is None


def test_source_pins_match_complete_attributed_donor_fixtures():
    for path, digest in memory.SOURCE_SHA256.items():
        item = MANIFEST["files"][path]
        assert item["sha256"] == digest
        assert hashlib.sha256((FIXTURES / item["fixture"]).read_bytes()).hexdigest() == digest
    assert MANIFEST["license"] == "MIT"


def test_fixture_source_audit_parses_docstrings_and_keeps_identity_guard():
    from tests.test_ceo_submit_armed_composition import _d8_frozen_source_diff, _scan_added_identity_diff
    # Complete pinned source snapshots are archive data, matching the accepted
    # request_observation .py.source convention. They remain subject to the
    # ordinary changed-source gate; also audit every original logical Python
    # source here, including a live identity-literal refusal canary.
    for item in MANIFEST["files"].values():
        assert item["fixture"].endswith(".py.source")
        path = "integrations/hermes_runtime/tests/fixtures/agentos_memory/" + item["fixture"].removesuffix(".source")
        text = (FIXTURES / item["fixture"]).read_text()
        assert _scan_added_identity_diff(_d8_frozen_source_diff(path, text), source_postimages={path: text}) == [], path
        archive = str((FIXTURES / item["fixture"]).relative_to(ROOT))
        assert _scan_added_identity_diff(_d8_frozen_source_diff(archive, text), source_postimages={archive: text}) == [], archive
        changed = text + "\nnew_peer_uid = 471\n"
        assert "471" in _scan_added_identity_diff(_d8_frozen_source_diff(path, changed), source_postimages={path: changed}), path
        assert "471" in _scan_added_identity_diff(_d8_frozen_source_diff(archive, changed), source_postimages={archive: changed}), archive


@pytest.mark.parametrize("when", ["before_resolve", "before_build"])
def test_slot_publication_cannot_retarget_original_factory(lifecycle, when):
    def replace_publication(*_):
        lifecycle.slot.publication = replace(lifecycle.slot.publication, work_ref="WS:FOREIGN")
    if when == "before_resolve":
        replace_publication()
    with pytest.raises(RuntimeRefusal):
        exercise(lifecycle, before_build=replace_publication if when == "before_build" else None)
    assert len(lifecycle.session.calls) == (1 if when == "before_build" else 0)


@pytest.mark.parametrize("when", ["before_prefetch", "before_build"])
def test_owned_agent_cannot_fall_through_after_losing_scope(lifecycle, when):
    def lose_scope(*_):
        memory.observation._current.set(None)
    with pytest.raises(RuntimeRefusal):
        exercise(lifecycle, **{when: lose_scope})
    assert len(lifecycle.session.calls) == (1 if when == "before_build" else 0)


def test_post_builder_recheck_withholds_claim_on_replacement(lifecycle):
    def replay(rows, **_):
        lifecycle.connection_ok[0] = False
        return rows
    lifecycle.replay.canonicalize_replay_history = replay
    with pytest.raises(RuntimeRefusal):
        exercise(lifecycle)
    assert lifecycle.factory.last_delivery["prompt"] is None


@pytest.mark.parametrize("change", ["expiry", "physical_rotation"])
def test_expiry_between_api_iterations_does_not_reuse_turn_cache(lifecycle, change):
    def next_iteration(agent, context, rows, built):
        provider = agent._memory_manager.get_provider("agentos")
        if change == "expiry":
            provider._clock = lambda: float("inf")
        else:
            agent.session_id = "physical-later-compaction"
        with pytest.raises(RuntimeRefusal):
            lifecycle.turn_context.build_api_messages(agent, rows, current_turn_user_idx=0,
                ext_prefetch_cache=context, plugin_user_context="", moa_config=None, active_system_prompt="system")
    exercise(lifecycle, after_build=next_iteration)
    assert len(lifecycle.session.calls) == 1


def test_required_read_timeout_retains_original_pending_and_withholds_late_result(lifecycle):
    entered, release = threading.Event(), threading.Event()
    provider_box = []
    async def original_call(name, arguments):
        lifecycle.session.calls.append((name, arguments))
        entered.set()
        assert await asyncio.to_thread(release.wait, 3)
        return lifecycle.sdk
    lifecycle.session.call_tool = original_call
    def deadline_edge(agent):
        provider = agent._memory_manager.get_provider("agentos")
        provider_box.append(provider)
        original = provider.wait_context
        provider.wait_context = lambda _timeout: original(0.02)
    try:
        with pytest.raises(RuntimeRefusal, match="NATIVE_AGENTOS_REQUIRED_CONTEXT_UNAVAILABLE"):
            exercise(lifecycle, before_prefetch=deadline_edge)
        assert entered.is_set() and len(lifecycle.session.calls) == 1
        provider = provider_box[0]
        assert provider._pending == 1
        assert lifecycle.factory.last_instance.claim.failed is True
    finally:
        release.set()
    with provider._changed:
        assert provider._changed.wait_for(lambda: provider._pending == 0, timeout=3)
    assert provider.context_observation() is None and lifecycle.factory.last_delivery is None
    assert len(lifecycle.session.calls) == 1


def test_late_native_prefetch_worker_cannot_borrow_next_admission(lifecycle):
    entered, release = threading.Event(), threading.Event()
    threads = []
    def install_late_prefetch(agent):
        provider = agent._memory_manager.get_provider("agentos")
        instance = getattr(provider, memory._INSTANCE_ATTRIBUTE)
        original = instance.original_prefetch
        first = [True]
        def delayed(query, *, session_id=""):
            if first[0]:
                first[0] = False
                entered.set()
                assert release.wait(3)
            return original(query, session_id=session_id)
        instance.original_prefetch = delayed
        # Run the exact original manager timeout/gate, with a short test bound.
        agent._memory_manager._external_prefetch_timeout = 0.01
        # Observe late return outside the native hook without changing the
        # wrapper identity that the real provider's guard requires.
        original_spawn = lifecycle.factory.modules["agent.memory_manager"].spawn_context_thread
        def observe_spawn(target, **kwargs):
            thread = original_spawn(target, **kwargs)
            threads.append(thread)
            return thread
        lifecycle.factory.modules["agent.memory_manager"].spawn_context_thread = observe_spawn
    try:
        first = exercise(lifecycle, before_prefetch=install_late_prefetch)
        assert entered.is_set() and first["context"] == ""
        assert first["live_readback"]["context"]["last_delivery"] is None
        def settle_old(agent, context, rows, built):
            current = copy.deepcopy(lifecycle.factory.last_delivery)
            release.set()
            threads[0].join(2)
            assert not threads[0].is_alive()
            assert lifecycle.factory.last_delivery == current
        second = exercise(lifecycle, admission="admission-2", generation=4, cached=first["agent"],
                          after_build=settle_old)
        assert second["live_readback"]["context"]["last_delivery"]["admission_id"] == "admission-2"
        assert second["live_readback"]["context"]["last_delivery"]["prompt"] is not None
    finally:
        release.set()
        for thread in threads:
            thread.join(2)
    assert len(lifecycle.session.calls) == 2


def test_v2_config_uses_agentos_without_parallel_file_memories(tmp_path):
    from integrations.hermes_harness.stack import compose_profile
    from integrations.hermes_harness.tests.test_native_executive_consumer import publication_document
    from integrations.hermes_steward.config_guard import _load_unique_yaml
    profile = replace(compose_profile("mmsecretary", state_dir=tmp_path / "state",
        secrets_file=tmp_path / "uncreated.env"), tool_allowlist=frozenset({"clarify"}))
    old = consumer.publication_from_document(publication_document())
    new = consumer.publication_from_document(context_document())
    before = _load_unique_yaml(render_qualified_native_byok(profile, old).encode())
    after = _load_unique_yaml(render_qualified_native_byok(profile, new).encode())
    assert "memory" not in before
    assert after.pop("memory") == {"provider": "agentos", "memory_enabled": False, "user_profile_enabled": False}
    assert after == before


@pytest.fixture
def general_loader(lifecycle, monkeypatch):
    from integrations.hermes_runtime import native_gateway_entry as entry
    from integrations.hermes_harness import native_selected_child_plugin as plugin
    l, calls = lifecycle, []
    edge(monkeypatch, "hermes_cli.plugins_manifest", requires_hermes_error=lambda _: None)
    plugins = sys.modules["hermes_cli.plugins"]
    plugins._PLUGINS_DEBUG = False
    plugins.LoadedPlugin = lambda **kwargs: SimpleNamespace(**kwargs, enabled=False, error=None, module=None)
    selected = {"_load_plugin", "_load_plugin_scoped", "_load_directory_module", "_policy_module_name",
                "_runs_in_plugin_host", "_directory_module_name"}
    loader = source(monkeypatch, l.native.vendor, "hermes_cli/plugins_loader.py",
        names={"PluginLoaderMixin"}, methods=selected, values={
            "Path": Path, "types": __import__("types"), "sys": sys, "hashlib": hashlib,
            "logger": logging.getLogger(__name__), "manifest_key": lambda manifest: manifest.key,
            "_plugin_home_scope": lambda _: contextlib.nullcontext(), "_load_error_text": str,
            "run_with_load_deadline": lambda key, ctx, fn: (calls.append("deadline"), fn())[1],
            "_NS_PARENT": "hermes_plugins", "_MODULE_NAMESPACE_LOCK": threading.Lock(), "_BARE_MODULE_SCOPE": {}})
    manager, slot = l.manager, l.slot
    for name in selected:
        setattr(manager, name, MethodType(getattr(loader.PluginLoaderMixin, name), manager))
    manager.home_path = l.native.home
    manager._registration_order = []
    manager._predeclared_modules = {}
    manager._predeclared_tools = {}
    manager._track_tool_override_policy = lambda manifest, name: calls.append(("policy", name))
    manager._register_declared_locales = lambda *_: None
    manager._is_manifest_only_language_pack = lambda _: False
    manager._attribute_registrations = lambda *_: None
    manager._dispose_registrations = manager._forget_registrations = manager._remove_plugin_subscriptions = lambda *_: None
    monkeypatch.setattr(plugin, "register", lambda ctx: calls.append(("register", ctx._manager)))
    manifest = SimpleNamespace(name=consumer.CONSUMER_PLUGIN_NAME, key=consumer.CONSUMER_PLUGIN_NAME,
        source="user", path=slot.package_path, portable=False, kind="directory")
    slot.import_current = None
    slot.load_attempted = slot.loader_entered = True
    slot.load_outcome = "LOAD_PENDING"
    require = entry._install_held_consumer_import(l.native.vendor, manager, slot, manifest,
                                                 Path(slot.package_path), slot.package_check)
    return SimpleNamespace(l=l, manifest=manifest, require=require, calls=calls, plugin=plugin)


def test_general_native_loader_uses_held_module_and_matching_policy_namespace(general_loader):
    g = general_loader
    g.require(g.manifest)
    g.l.manager._load_plugin(g.manifest)
    loaded = g.l.manager._plugins[consumer.CONSUMER_PLUGIN_NAME]
    assert loaded.enabled is True and loaded.error is None and loaded.module is g.plugin
    assert g.calls == [("policy", "integrations.hermes_harness.native_selected_child_plugin"),
                       "deadline", ("register", g.l.manager)]
    assert g.l.slot.import_current() is True


@pytest.mark.parametrize("change", ["host", "predeclared", "manifest", "directory_seam", "policy_seam", "publication"])
def test_general_loader_rejects_unheld_import_paths(general_loader, change):
    g = general_loader
    candidate = g.manifest
    if change == "host":
        g.l.cfg["plugins"]["isolation"] = "host"
    elif change == "predeclared":
        g.l.manager._predeclared_modules[consumer.CONSUMER_PLUGIN_NAME] = object()
    elif change == "manifest":
        candidate = copy.copy(candidate)
    elif change == "directory_seam":
        g.l.manager._load_directory_module = lambda *_a, **_k: g.plugin
    elif change == "policy_seam":
        g.l.manager._policy_module_name = lambda *_: "forged"
    else:
        g.l.slot.publication = replace(g.l.slot.publication, work_ref="WS:FOREIGN")
    with pytest.raises(RuntimeRefusal):
        g.require(candidate)
    assert g.calls == []


def test_readback_refuses_claim_replacement_between_readiness_and_snapshot(lifecycle, monkeypatch):
    def race(agent, context, rows, built):
        provider = agent._memory_manager.get_provider("agentos")
        instance = getattr(provider, memory._INSTANCE_ATTRIBUTE)
        original = provider.readiness
        def replace_claim():
            result = original()
            instance.claim = copy.copy(instance.claim)
            return result
        with monkeypatch.context() as patch:
            patch.setattr(provider, "readiness", replace_claim)
            with pytest.raises(RuntimeRefusal, match="NATIVE_AGENTOS_FACTORY_UNAVAILABLE"):
                lifecycle.factory.readback()
    exercise(lifecycle, after_build=race)


def enrollment_edge(lifecycle):
    l = lifecycle
    return {"status": "ENROLLED", "target": {"profile_id": str(l.native.home),
        "principal_id": l.slot.publication.session.principal_id, "session_id": "session-1",
        "instance_id": "instance-1", "authority_epoch": 2, "revision": 1, "execution_generation": 3}}


@pytest.mark.parametrize("late_change", [False, True])
def test_private_capability_reader_joins_original_enrollment_without_acquiring_context(lifecycle, monkeypatch, late_change):
    from integrations.hermes_runtime import native_session_control as control
    l = lifecycle
    l.native.runner.session_runtime_descriptor["state"] = "ready"
    monkeypatch.setattr(control, "current_runtime_owner", lambda: l.slot.owner)
    calls = []
    def enrolled(runner, home, owner, request, principal, *, role):
        calls.append((request, principal, role))
        value = enrollment_edge(l)
        if late_change and len(calls) > 1:
            value["target"]["revision"] += 1
        return value
    monkeypatch.setattr(control, "read_enrolled_session", enrolled)
    if late_change:
        with pytest.raises(RuntimeRefusal):
            control._consumer_capabilities(l.native.runner, l.native.home)
    else:
        value = control._consumer_capabilities(l.native.runner, l.native.home)
        assert value["context"]["factory_registered"] is True
        assert value["context"]["provider_installed"] is False
        assert value["selected_child"] is None
    assert len(calls) == 2 and l.session.calls == []


@pytest.mark.parametrize("change", ["extra", "ready_without_provider", "snapshot_without_ready", "fake_child", "wrong_owner", "oversize"])
def test_closed_readback_never_upgrades_unproved_stages(lifecycle, change):
    l = lifecycle
    value = l.factory.readback()
    expected = copy.deepcopy(value["binding"])
    if change == "extra":
        value["context"]["provider_dispatch_proven"] = True
    elif change == "ready_without_provider":
        value["context"]["readiness"] = {"state": "READY", "reason": None}
    elif change == "snapshot_without_ready":
        value["context"]["snapshot"] = {}
    elif change == "fake_child":
        value["selected_child"] = {"job_id": "invented"}
    elif change == "wrong_owner":
        value["binding"]["instance_id"] = "replacement"
    else:
        value["context"]["last_delivery"] = {"text": "x" * 20000}
    with pytest.raises(RuntimeRefusal):
        memory.validate_consumer_readback(value, publication=l.slot.publication, expected_binding=expected)


def test_supervisor_separates_context_history_active_provider_and_delegation(lifecycle):
    from integrations.hermes_harness.stack import compose_profile
    from integrations.hermes_runtime.supervisor import ServiceRuntime
    l = lifecycle
    result = exercise(l)
    profile = replace(compose_profile("mmsecretary", state_dir=l.native.home / "state",
        secrets_file=l.native.home / "uncreated.env"), gateway_backend="native-session-authority")
    launch = SimpleNamespace(recipe=l.native.launch.recipe, owner=SimpleNamespace(root=Path("/") / l.slot.owner))
    runtime = ServiceRuntime(profile, SimpleNamespace(), Path("/unexecuted-hermes"), native_launch=launch)
    runtime._native_home = l.native.home
    runtime._child = SimpleNamespace(pid=123, poll=lambda: None)
    runtime.child_pid = 123
    runtime._backend_ready = True
    observed = [result["settled_readback"]]
    runtime._observe_consumer_extension = lambda pid: (observed[0], enrollment_edge(l)["target"])
    status, health = runtime.health_snapshot()
    assert status == 200 and health["native_extension_proved"] is False
    assert health["native_context_factory_registered"] is True
    assert health["native_context_provider_installed"] is False and health["native_context_ready"] is False
    assert health["native_context_delivery_observed"] is True and health["native_context_prompt_observed"] is True
    assert health["provider_authenticated"] is False and health["native_model_turn_verified"] is False
    observed[0] = copy.deepcopy(observed[0])
    observed[0]["binding"]["publication_sha256"] = "f" * 64
    _, health = runtime.health_snapshot()
    assert not any(value for key, value in health.items() if key.startswith("native_context_"))
    runtime._backend_ready = False
    _, health = runtime.health_snapshot()
    assert health["native_extension_proved"] is False
    assert not any(value for key, value in health.items() if key.startswith("native_context_"))


@pytest.mark.parametrize("role", ["mmsecretary", "mmmeta"])
@pytest.mark.parametrize("mode", ["prepare", "runtime"])
def test_v2_isolated_installation_qualifies_through_original_held_entry(role, mode):
    from tests.test_hermes_consumer_bootstrap import run_isolated
    from integrations.hermes_runtime.tests.test_native_meta_enrollment import installation
    document = installation(role, consumer=True)
    native = next(row for row in document["roles"] if row["role"] == role)["native_gateway"]
    publication = context_document()
    publication["session"] = native["executive_consumer"]["session"]
    native["executive_consumer"] = publication
    native["vendor_derivation"] = privacy_selection()
    result = run_isolated(document, mode=mode)
    assert result["outcome"] == "RuntimeError:C57_QUALIFIED_BEFORE_EFFECT"
    assert result["closed"] and result["effect_boundary_loaded"] and result["consumer_loaded"]
    assert result["first_party_after"] == []


@pytest.mark.parametrize("change", ["absent_selection", "absent_receipt", "kind", "base_sha",
    "patch_sha256", "postimages", "license_sha256", "vendor_root", "extra_receipt",
    "receipt_type", "postimages_type"])
def test_v2_refuses_missing_or_wrong_privacy_proof_before_registration(lifecycle, monkeypatch, change):
    l = lifecycle
    l.slot.memory_factory = None
    if change == "absent_selection":
        l.native.launch.recipe.pop("vendor_derivation")
    elif change == "absent_receipt":
        l.native.launch.derivation = None
    elif change == "postimages":
        l.native.launch.derivation["postimages"]["agent/agent_init.py"] = "0" * 64
    elif change in {"receipt_type", "postimages_type"}:
        class FalseReceipt:
            def __eq__(self, other):
                return True
        if change == "receipt_type":
            l.native.launch.derivation = FalseReceipt()
        else:
            l.native.launch.derivation["postimages"] = FalseReceipt()
    else:
        l.native.launch.derivation[change] = "different"
    def unexpected_import(*_):
        raise AssertionError("receipt refusal must precede donor imports")
    monkeypatch.setattr(memory.importlib, "import_module", unexpected_import)
    with pytest.raises(RuntimeRefusal, match="PRIVACY_DERIVATION_REQUIRED"):
        memory.install_native_agentos_memory(l.native.launch, l.native.vendor, l.native.home, l.native.binding)
    assert l.slot.memory_factory is None and l.session.calls == []


@pytest.mark.parametrize("path", ["agent/agent_init.py", "agent/memory_caller_scope.py"])
def test_v2_refuses_original_vulnerable_bytes_despite_claimed_receipt(lifecycle, path):
    from tests.test_hermes_diagnostic_privacy import privacy_sources
    l = lifecycle
    l.slot.memory_factory = None
    (l.native.vendor / path).write_bytes(privacy_sources("upstream")[path])
    with pytest.raises(RuntimeRefusal, match="MEMORY_SOURCE_MISMATCH"):
        memory.install_native_agentos_memory(l.native.launch, l.native.vendor, l.native.home, l.native.binding)
    assert l.slot.memory_factory is None and l.session.calls == []


@pytest.mark.parametrize("when", ["before_resolve", "before_build"])
@pytest.mark.parametrize("change", ["selection", "postimages", "license", "vendor"])
def test_privacy_proof_drift_invalidates_original_claim(lifecycle, when, change):
    def drift(*_):
        launch = lifecycle.native.launch
        if change == "selection":
            launch.recipe["vendor_derivation"]["source_root"] = "/opt/hermes/replacement"
        elif change == "postimages":
            launch.derivation["postimages"]["agent/agent_init.py"] = "0" * 64
        elif change == "license":
            launch.derivation["license_sha256"] = "0" * 64
        else:
            launch.recipe["vendor_root"] = "/opt/hermes/replacement"
    if when == "before_resolve":
        drift()
    with pytest.raises(RuntimeRefusal):
        exercise(lifecycle, before_build=drift if when == "before_build" else None)
    assert len(lifecycle.session.calls) == (1 if when == "before_build" else 0)
    assert lifecycle.factory.last_delivery is None or lifecycle.factory.last_delivery["prompt"] is None


@pytest.mark.parametrize("deferred", [False, True])
@pytest.mark.parametrize("kind", [None, "computer_env_guard"])
def test_context_v2_recipe_requires_privacy_at_existing_release_boundary(deferred, kind):
    from ops.executive_os import release_manifest
    from integrations.hermes_runtime.tests.test_native_meta_enrollment import installation
    document = installation("mmsecretary", consumer=True)
    native = next(row for row in document["roles"] if row["role"] == "mmsecretary")["native_gateway"]
    publication = context_document()
    publication["session"] = native["executive_consumer"]["session"]
    native["executive_consumer"] = publication
    if kind is not None:
        native["vendor_derivation"] = {**privacy_selection(), "kind": kind,
            "patch_sha256": "d17af87e60a1f92a52ef446ad393ce2841c876a28e2ae0580bc7e6db09d6721f"}
    with pytest.raises(release_manifest.ReleaseManifestError, match="requires diagnostic privacy"):
        release_manifest.validate_hermes_runtime_installation(document, _defer_consumer=deferred)


def test_privacy_drift_at_final_custody_check_refuses_wrapper_publication(lifecycle, monkeypatch):
    l = lifecycle
    l.slot.memory_factory = None
    before = [(owner, name, getattr(owner, name)) for owner, name, _ in l.factory.wrappers]
    # The previous fixture composition owns these wrappers. This test isolates
    # the final publication boundary; source/seam qualification is tested above.
    monkeypatch.setattr(memory, "_function", lambda module, name, cls=None:
                        getattr(module if cls is None else cls, name))
    def change_at_check():
        l.native.launch.derivation["postimages"]["agent/agent_init.py"] = "0" * 64
    l.native.launch.check = change_at_check
    with pytest.raises(RuntimeRefusal, match="PRIVACY_DERIVATION_REQUIRED"):
        memory.install_native_agentos_memory(l.native.launch, l.native.vendor, l.native.home, l.native.binding)
    assert l.slot.memory_factory is None and l.session.calls == []
    assert all(getattr(owner, name) is original for owner, name, original in before)


def test_cheap_privacy_currentness_uses_detached_receipt_without_filesystem_reads(lifecycle, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("cheap readiness cannot qualify source again")
    monkeypatch.setattr(Path, "resolve", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    lifecycle.native.launch.check = forbidden
    assert lifecycle.factory.local_current()
    lifecycle.native.launch.derivation["postimages"]["agent/agent_init.py"] = "0" * 64
    assert not lifecycle.factory.local_current()
    assert lifecycle.factory.privacy_receipt["postimages"] == memory.PRIVACY_DERIVATION_POSTIMAGES


@pytest.mark.parametrize("intent", ["pause", "cancel", "reprioritize", "resume"])
@pytest.mark.parametrize("reuse", [True, False], ids=["cached_agent", "fresh_agent"])
def test_authored_steering_reaches_current_native_prompt_without_losing_frontier(
        lifecycle, actual_result, intent, reuse):
    """Two real compiler results, not model compliance or runtime-effect proof."""
    import yaml
    from common import coo_agentos_context_contract as wire
    from tests.test_installed_agentos_context import commit, write_record
    l = lifecycle
    frame, _, owner = actual_result
    publication_before = copy.deepcopy(l.factory.document)
    authored = yaml.safe_load(owner["record"].read_text().split("---", 2)[1])
    objective = authored["objective"]
    frontier = [(wave["id"], wave["title"], wave.get("depends_on", []))
                for wave in authored["waves"]]
    warning = "Original effect remains EFFECT_UNKNOWN; reconcile its original carrier; do not replay."
    authored["waves"][0]["next_action"] = warning
    authored["next_action"] = "Continue the original source qualification, then deliver the result."
    wait = {"kind": "external_action", "review_after": "2026-11-08",
            "condition": "The existing owner supplies the scoped continuation decision."}
    if intent == "resume":
        authored["waves"][0]["wait"] = dict(wait)

    def compile_revision(record):
        write_record(owner["record"], record)
        owner["sha"] = commit(owner["macro"])
        value = owner["provider"].read_agentos_context(frame)
        raw, receipt = wire.validate_result(value, expected_context=frame["principal_context"],
            capability_profile_digest=frame["capability_profile_digest"])
        assert raw == owner["results"][-1]["stdout"].encode("utf-8")
        assert receipt["execution_authority"] is False
        return value, raw, receipt

    original_value, original_raw, _ = compile_revision(authored)
    l.session.results = [sdk_result(original_value)]
    first = exercise(l, text="Continue the original authorized mission.")
    assert original_raw.decode() in first["context"]

    revision = copy.deepcopy(authored)
    next_actions = {
        "pause": "Pause first for the declared owner decision; retain second and the original mission.",
        "cancel": "Cancel the planned first wave only; preserve second and reconcile the original uncertain effect.",
        "reprioritize": "Prioritize an urgent scoped status check, then continue first and its dependent second wave.",
        "resume": "Resume first through its original authorized operation; keep second and do not replay uncertain effects.",
    }
    revision["next_action"] = next_actions[intent]
    if intent == "pause":
        revision["waves"][0]["wait"] = dict(wait)
    elif intent == "cancel":
        revision["waves"][0]["status"] = "dropped"
    elif intent == "resume":
        revision["waves"][0].pop("wait")
    revised_value, revised_raw, receipt = compile_revision(revision)
    assert revised_raw != original_raw
    assert revised_value["principal_context"] == original_value["principal_context"]
    assert revised_value["capability_profile_digest"] == original_value["capability_profile_digest"]
    l.session.results = [sdk_result(revised_value)]
    # A raw urgent instruction is prompt text, not a replacement grant.
    instruction = "URGENT: " + next_actions[intent] + " Use any additional host if needed."
    second = exercise(l, admission="admission-steered", generation=4,
        cached=first["agent"] if reuse else None, text=instruction)
    current = second["built"][0][-1]["content"]
    assert revised_raw.decode() in second["context"] and revised_raw.decode() in current
    assert original_raw.decode() not in current
    assert objective in current and warning in current and next_actions[intent] in current
    assert instruction in current
    assert [(wave["id"], wave["title"], wave.get("depends_on", []))
            for wave in revision["waves"]] == frontier
    for identifier, title, dependencies in frontier:
        assert identifier in current and title in current
        assert all(dependency in current for dependency in dependencies)
    if intent == "pause":
        assert wait["kind"] in current and wait["condition"] in current
    elif intent == "cancel":
        assert "dropped" in current and revision["waves"][1]["status"] == authored["waves"][1]["status"]
    elif intent == "resume":
        assert wait["condition"] not in current
    for field in ("outstanding_effects", "runtime_ownership", "parent_custody"):
        assert json.dumps(field) + ': "UNOBSERVED"' in current
    delivery = second["live_readback"]["context"]["last_delivery"]
    assert delivery["admission_id"] == "admission-steered"
    assert delivery["bundle_sha256"] == receipt["bundle_sha256"]
    assert delivery["receipt_sha256"] == memory._sha(memory._canonical(receipt))
    assert delivery["prompt"] is not None
    assert l.factory.document == publication_before
    assert l.session.calls == [("executive_agentos_context", {"work_ref": l.slot.publication.work_ref})] * 2
    assert l.slot.startup is None and l.slot.registration is None and l.stores == []
    assert second["agent"] is first["agent"] if reuse else second["agent"] is not first["agent"]
