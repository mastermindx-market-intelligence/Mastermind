"""Primary inference inside the incumbent native GatewayRunner lifecycle.

Only the existing LiveSession retains the original capability. Native admission,
history, tools, approval, result persistence and unknown-input recovery remain
with Hermes; APPLICATION credentials, routing and settlement remain with Fabric.
"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar, copy_context
from dataclasses import dataclass, field
from pathlib import Path
import threading

from .client import ApplicationBinding, HermesApplicationClient, NativeCall
from .errors import HermesFabricError
from .native import PROVIDER, create_primary_agent, execution_middleware, register_native_provider
from .publication import ROLE_RELATIONS, held_package_digest, publication_from_document

_CAPABILITY = "_mmx_primary_application_capability"
_HOST = "_mmx_primary_application_host"
_TURN = ContextVar("mastermind_hermes_primary_native_turn", default=None)


def _refuse(code="hermes_fabric_native_claim_unqualified", *, unknown=False):
    raise HermesFabricError(code, effect_unknown=unknown)


def _consume(future):
    try:
        future.result()
    except BaseException:
        pass


def _agent_route(agent, publication):
    if (getattr(agent, "provider", None) != PROVIDER
            or getattr(agent, "model", None) != publication.model
            or getattr(agent, "api_mode", None) != "chat_completions"
            or getattr(agent, "api_key", None) not in (None, "")
            or getattr(agent, "base_url", None) not in (None, "")
            or getattr(agent, "credential_pool", None) is not None
            or getattr(agent, "_credential_pool", None) is not None
            or getattr(agent, "_fallback_chain", None)
            or getattr(agent, "_fallback_activated", False)
            or type(getattr(agent, "client", None)) is not HermesApplicationClient):
        _refuse("hermes_fabric_native_route_changed")


@dataclass
class _OriginalCapability:
    host: object
    authority: object
    live: object
    logical_session_id: str
    generation: int
    admission_id: str
    command_request_id: str
    epoch: int
    target_identity: tuple
    route: object
    ctx: object
    factory: object
    agent: object = None
    binding: ApplicationBinding | None = None
    bind_attempted: bool = False
    retired: bool = False
    lock: object = field(default_factory=threading.Lock, repr=False)

    def close(self):
        with self.lock:
            self.retired = True
            original = self.binding
        # The existing owner marks itself closed before its bounded close I/O.
        # Its retained result is not proof of cancellation or lease release.
        return original.close() if original is not None else None

    def resolve(self, call):
        if not self.authorized(call):
            _refuse()
        with self.lock:
            if self.retired:
                _refuse("hermes_fabric_original_turn_retired", unknown=True)
            if self.binding is None:
                if self.bind_attempted:
                    _refuse("hermes_fabric_original_recovery_required", unknown=True)
                self.bind_attempted = True
                self.binding = ApplicationBinding.from_factory(self.factory,
                    profile_id=self.host.publication.role, operation_id=self.admission_id,
                    session_id=call.session_id, turn_id=call.turn_id,
                    requested_model=self.host.publication.model,
                    strict_model=(self.host.publication.strict_model if self.host.publication.automatic
                                  else self.host.publication.model),
                    automatic=self.host.publication.automatic, strict_pool=self.host.publication.strict_pool,
                    prior_admission_possible=False, authorized=self.authorized,
                    max_output_tokens=self.host.publication.max_tokens)
            return self.binding

    def authorized(self, call):
        if type(call) is not NativeCall or self.retired:
            return False
        try:
            # inspect is credential-free and rechecks current APPLICATION
            # capability, expiry, workload and the frozen transport identity.
            self.factory.inspect()
            return self.host.on_owner(lambda: self.host.inspect_claim(self, call)) is True
        except Exception:
            return False


class _NativeHost:
    def __init__(self, runner, launch, role_home, document, manager):
        self.runner, self.launch, self.role_home = runner, launch, role_home
        self.publication = publication_from_document(document)
        self.manager = manager
        self.loop = asyncio.get_running_loop()
        self.context = copy_context()
        self.middleware = None

    def check(self):
        from hermes_cli.plugins import get_plugin_manager
        from integrations.hermes_runtime.native_session_control import current_runtime_owner
        self.launch.check()
        if (getattr(self.runner, _HOST, None) is not self
                or get_plugin_manager() is not self.manager
                or str(self.manager.scope_key) != str(self.role_home)
                or publication_from_document(self.launch.recipe["primary_application"]) != self.publication
                or held_package_digest(self.launch.owner) != self.publication.package_sha256
                or current_runtime_owner() != self.launch.owner.root.name
                or getattr(self.runner, "_draining", True)
                or self.middleware not in self.manager._middleware.get("llm_execution", ())):
            _refuse("hermes_fabric_host_changed")
        descriptor = self.runner.session_runtime_descriptor
        authority = self.runner.session_authority
        if (descriptor.get("state") != "ready" or getattr(authority, "retired", True)
                or str(authority.profile_id) != str(self.role_home)
                or authority.instance_id != descriptor.get("instance_id")
                or authority.epoch != descriptor.get("authority_epoch")):
            _refuse("hermes_fabric_native_owner_changed")

    def on_owner(self, read):
        if not self.loop.is_running():
            return False
        try:
            if asyncio.get_running_loop() is self.loop:
                return read()
        except RuntimeError:
            pass
        async def inspect():
            return read()
        coroutine = inspect()
        try:
            future = self.context.copy().run(asyncio.run_coroutine_threadsafe, coroutine, self.loop)
        except BaseException:
            coroutine.close()
            return False
        try:
            return future.result(timeout=5.0)
        except Exception:
            # Read-only timeout. The original read may finish; no replacement
            # owner or inference is created and no authority is manufactured.
            future.add_done_callback(_consume)
            return False

    def enrollment(self):
        from integrations.hermes_runtime.native_session_control import read_enrolled_session
        p = self.publication
        observed = read_enrolled_session(self.runner, self.role_home, self.launch.owner.root.name,
            p.enrollment_request_id, p.principal_id, role=p.role)
        if observed["status"] != "ENROLLED":
            _refuse("hermes_fabric_session_not_enrolled")
        return observed

    @staticmethod
    def identity(target):
        return tuple(target[key] for key in
            ("profile_id", "principal_id", "session_id", "instance_id", "authority_epoch"))

    def inspect_claim(self, cap, call=None):
        from gateway.session_authorities import active_authority, admission_owner
        from hermes_state_runtime import get_session_admission
        self.check()
        enrolled = self.enrollment()
        authority, sid = cap.authority, cap.logical_session_id
        row = get_session_admission(authority.db, admission_id=cap.admission_id)
        if (active_authority(self.runner) is not authority
                or self.runner.session_authority is not authority
                or authority.sessions.get(sid) is not cap.live
                or getattr(cap.live, _CAPABILITY, None) is not cap
                or self.identity(enrolled["target"]) != cap.target_identity
                or enrolled["route"] != cap.route or row is None
                or row.get("admission_id") != cap.admission_id
                or row.get("request_id") != cap.command_request_id
                or row.get("principal_id") != self.publication.principal_id
                or row.get("target_session_id") != sid or row.get("intent") != "queue"
                or row.get("status") != "started" or row.get("owner_epoch") != cap.epoch
                or row.get("generation") != cap.generation or authority.epoch != cap.epoch
                or authority.executing.get(sid) != cap.generation
                or cap.live.event_stream.execution != {"authority_epoch": cap.epoch,
                    "execution_generation": cap.generation, "admission_id": cap.admission_id}
                or cap.ctx._run_still_current() is not True or cap.retired):
            return False
        if call is not None:
            agent = cap.agent
            if (agent is None or authority.adopted.get(sid) != (cap.generation, agent)
                    or cap.ctx.agent_holder[0] is not agent
                    or call.session_id != getattr(agent, "session_id", None)
                    or call.task_id != getattr(agent, "_current_task_id", None)
                    or call.turn_id != getattr(agent, "_current_turn_id", None)
                    or call.api_request_id != getattr(agent, "_current_api_request_id", None)
                    or call.task_id != cap.ctx.session_id
                    or admission_owner(authority, call.session_id) != sid):
                return False
            _agent_route(agent, self.publication)
        return True

    def capture(self, ctx, turn):
        from gateway.session_authorities import active_authority, admission_owner
        from hermes_state_runtime import get_session_admission
        from engine.provider_production_modes import make_application_fabric_factory
        self.check()
        enrolled = self.enrollment()
        authority = active_authority(self.runner)
        sid = enrolled["target"]["session_id"]
        live = authority.sessions.get(sid)
        source = ctx.source
        row = get_session_admission(authority.db, admission_id=ctx.inbound_message_id)
        if (live is None or getattr(source.platform, "value", source.platform) != "local"
                or source.chat_id != sid or source.user_id != self.publication.principal_id
                or row is None or row.get("status") != "started" or row.get("intent") != "queue"
                or admission_owner(authority, ctx.session_id) != sid
                or turn._approval_owner != (authority, sid, row.get("generation"))):
            _refuse()
        previous = getattr(live, _CAPABILITY, None)
        if previous is not None:
            if type(previous) is not _OriginalCapability:
                _refuse("hermes_fabric_original_capability_conflict", unknown=True)
            if previous.admission_id == row["admission_id"]:
                # A duplicated builder is never authorization to replay input.
                _refuse("hermes_fabric_original_recovery_required", unknown=True)
            old = get_session_admission(authority.db, admission_id=previous.admission_id)
            original = previous.binding._owner if previous.binding is not None else None
            result = original._close_result if original is not None else None
            settled = (original is None and not previous.bind_attempted) or (
                original is not None and original._active is False and original._uncertain is False
                and type(result) is dict and result.get("effect_unknown") is False
                and ((result.get("disposition") == "closed" and result.get("closed") is True)
                     or (result.get("disposition") == "local_only"
                         and original._admission_possible is False
                         and result.get("attempted") is False)))
            if (not previous.retired or old is None or old.get("status") != "terminal" or not settled):
                _refuse("hermes_fabric_previous_effect_unresolved", unknown=True)
        lane, service, _, _ = ROLE_RELATIONS[self.publication.role]
        factory = make_application_fabric_factory(mode_id="shared_fabric", lane=lane,
            service_mode_id=service, root=Path(self.publication.macro_root),
            workload_cfg={"workload_profile": "site_interactive", "provider_order": ["fabric"],
                          "client_timeout_s": 90.0})
        if self.publication.strict_model is not None:
            factory = factory.with_requested_model(self.publication.strict_model)
        factory = factory.with_inspection(factory.inspect())
        cap = _OriginalCapability(self, authority, live, sid, row["generation"],
            row["admission_id"], row["request_id"], row["owner_epoch"],
            self.identity(enrolled["target"]), enrolled["route"], ctx, factory)
        setattr(live, _CAPABILITY, cap)
        setattr(ctx, _CAPABILITY, cap)
        if not self.inspect_claim(cap):
            cap.retired = True
            _refuse()
        return cap


def install_native_host(runner, *, launch, role_home, document):
    """Install once before the existing gateway accepts any admitted turn."""
    from hermes_cli.plugins import PluginContext, get_plugin_manager
    from hermes_cli.plugins_manifest import PluginManifest
    from .publication import qualify_installation
    if getattr(runner, _HOST, None) is not None:
        _refuse("hermes_fabric_host_already_installed")
    publication = qualify_installation(document, role=launch.row["role"],
        enrollment=launch.recipe["session_enrollment"], import_roots=launch.recipe["import_roots"],
        principal_id="uid:" + str(launch.row["uid"]))
    if held_package_digest(launch.owner) != publication.package_sha256:
        _refuse("hermes_fabric_package_unqualified")
    launch.check()
    # The existing NativeSourceClosure owns the complete Macro import/config
    # inventory. Verify the loaded owners resolve inside that exact held root.
    from engine import provider_production_modes, fabric_inference_client
    for name, module in (("provider_production_modes", provider_production_modes),
                         ("fabric_inference_client", fabric_inference_client)):
        if Path(module.__file__).resolve() != Path(publication.macro_root) / "engine" / (name + ".py"):
            _refuse("hermes_fabric_application_source_unqualified")
    manager = get_plugin_manager()
    if str(manager.scope_key) != str(role_home) or PROVIDER in manager._plugins:
        _refuse("hermes_fabric_plugin_scope_conflict")
    register_native_provider()
    host = _NativeHost(runner, launch, role_home, document, manager)
    setattr(runner, _HOST, host)

    def resolve(call):
        cap = _TURN.get()
        if type(cap) is not _OriginalCapability or cap.host is not host:
            _refuse()
        return cap.resolve(call)

    plugin = PluginContext(PluginManifest(name=PROVIDER, version="1.0.0",
        source="mastermind-held-primary", path=str(Path(__file__).parent), key=PROVIDER), manager)
    host.middleware = execution_middleware(resolve)
    host.registration = plugin.register_middleware("llm_execution", host.middleware)
    build = runner._run_agent_build_turn_context
    cleanup = runner._run_agent_cleanup_turn_tasks

    def runtime(*, source=None, session_key=None, user_config=None, fallback=True):
        cap = _TURN.get()
        if (type(cap) is not _OriginalCapability or cap.host is not host
                or source is not cap.ctx.source or session_key != cap.ctx.session_key
                or not host.on_owner(lambda: host.inspect_claim(cap))):
            _refuse()
        runner._pre_agent_fallback_notice = None
        return publication.model, {"provider": PROVIDER, "requested_provider": PROVIDER,
            "api_mode": "chat_completions", "api_key": None, "base_url": None,
            "credential_pool": None, "command": None, "args": [],
            "max_tokens": publication.max_tokens, "capabilities": {}}

    def constructor(*, model, **options):
        required = {"provider": PROVIDER, "requested_provider": PROVIDER,
                    "api_mode": "chat_completions"}
        if model != publication.model or any(options.get(k) != v for k, v in required.items()):
            _refuse("hermes_fabric_native_route_changed")
        for key in required:
            options.pop(key)
        for key in ("api_key", "base_url", "credential_pool", "command", "acp_command"):
            if options.pop(key, None) not in (None, ""):
                _refuse("hermes_fabric_native_route_changed")
        for key in ("args", "acp_args", "fallback_model"):
            if options.pop(key, None) not in (None, [], {}):
                _refuse("hermes_fabric_native_route_changed")
        if options.get("max_tokens") != publication.max_tokens:
            _refuse("hermes_fabric_native_output_bound_changed")
        agent = create_primary_agent(model=model, **options)
        _agent_route(agent, publication)
        return agent

    def build_turn(disp, AIAgent, *, message, source, session_key, run_generation, **turn_params):
        ctx, turn, adapter = build(disp, constructor, message=message, source=source,
            session_key=session_key, run_generation=run_generation, **turn_params)
        cap = host.capture(ctx, turn)
        run = turn.run_sync
        converse = turn._run_conversation_with_approval

        def conversation(agent, *args, **kwargs):
            _agent_route(agent, publication)
            cap.agent = agent
            if not host.on_owner(lambda: host.inspect_claim(cap)):
                _refuse()
            return converse(agent, *args, **kwargs)

        def run_sync():
            token = _TURN.set(cap)
            try:
                return run()
            finally:
                cap.close()
                _TURN.reset(token)

        turn._run_conversation_with_approval = conversation
        turn.run_sync = run_sync
        return ctx, turn, adapter

    async def cleanup_turn(ctx, **kwargs):
        cap = getattr(ctx, _CAPABILITY, None)
        try:
            if type(cap) is _OriginalCapability and cap.host is host:
                await asyncio.to_thread(cap.close)
        finally:
            await cleanup(ctx, **kwargs)

    runner._resolve_session_agent_runtime = runtime
    runner._run_agent_build_turn_context = build_turn
    runner._run_agent_cleanup_turn_tasks = cleanup_turn
    return host
