"""Adopt Agent OS context through Hermes's actual native memory lifecycle.

The existing request-observation scope references the original native claim;
it is never an authority substitute. The same ConsumerSlot retains the
factory, actual provider and bounded delivery evidence. No second session,
memory store, scheduler, retry, credential or connection owner is introduced.
"""
from __future__ import annotations

import hashlib
import importlib
import inspect
import json
from pathlib import Path
from types import ModuleType

from ops.executive_os.native_gateway_sources import (
    DERIVATION_BASE, PRIVACY_DERIVATION_KIND, PRIVACY_DERIVATION_PATCH,
    PRIVACY_DERIVATION_POSTIMAGES, PRIVACY_LICENSE_SHA256,
    WORKSPACE_OAUTH_DERIVATION_KIND, WORKSPACE_OAUTH_DERIVATION_PATCH,
    WORKSPACE_OAUTH_DERIVATION_POSTIMAGES)

from integrations.hermes_harness.agentos_memory_provider import (
    AgentOsBinding, AgentOsHostPorts, AgentOsRefusal, create_provider)
from integrations.hermes_harness.native_agentos_context import NativeAgentOsContextRead
from integrations.hermes_harness.native_executive_consumer import (
    CONSUMER_PLUGIN_NAME, CONSUMER_SLOT_ATTRIBUTE, ConsumerSlot,
    ExecutiveContextConsumerPublication, _canonical, publication_from_document, validate_consumer_publication)
from .errors import RuntimeRefusal
from . import native_request_observation as observation

READBACK_SCHEMA = "mastermind.hermes_native_consumer_readback/v2"
CURRENT_READBACK_SCHEMA = "mastermind.hermes_native_consumer_readback/v3"
_CLAIM_ATTRIBUTE = "_mmx_agentos_memory_claim"
_INSTANCE_ATTRIBUTE = "_mmx_agentos_memory_instance"
_PACKAGE_MODULE = "integrations.hermes_harness.native_selected_child_plugin"
SOURCE_SHA256 = {
    "agent/agent_init.py": "eea2233a2b6cd536fca891dc3436a8dd55c1e69f0ad54a5aa6cf8fa58a3c7e08",
    "agent/memory_provider.py": "ac81dcf489c698891f0edebfe26845a75c50d2bde77ec3be8d7938a85c79f1fc",
    "agent/memory_manager.py": "88027d7ae6ee27b5abbd266619a8fbf37a561465acc1a30e0bb27954ea6f8657",
    "agent/memory_context.py": "3ed4a7bb2d7b5d8394e204c911c7983e4e1804a797083fffc87a071767b3851f",
    "agent/memory_caller_scope.py": "e8924a95d756f0235071a0276763bffdaa7fdf5cef68eda589f7f46939a872a6",
    "agent/turn_context.py": "89df9b4ad047d3efff4b3d3514cc4a6eef2ac05d6add105e1e4b354bee4191fa",
    "plugins/memory/__init__.py": "166663beca1203abceffccca25c283af953a590955863a911f5d94b769725b2d",
    "plugins/plugin_loader.py": "b4d4e730df8d8163e45d4fb9dd305f61a1c6fb724ed4c3c7768eac880abba320",
    "gateway/session_execution.py": "7c1e294795003b329cc9639fe27e9b8b8fdfbd9b1e3106fcfbd6c8e06f670a60",
    "gateway/run_turn_runner.py": "72baf0ba84f2a3a542e4fd0294733b4d038feecdccfda7e58bbcb48e222dfa43",
    "hermes_cli/plugin_isolation.py": "808f055dd182d5118b1ef187abdf632a3871557a7decd652951af0de0c53eb2c",
    "tools/thread_context.py": "4e1d7118141ed5ea0f4de6989ef346750941ba7b7b273a22ef0c1bb50a720e0e",
}


def _refuse(code="NATIVE_AGENTOS_MEMORY_UNAVAILABLE"):
    raise RuntimeRefusal(code)


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _plain_strings(value):
    return type(value) is dict and all(type(item) is str for item in value.values())


def _privacy_receipt_equal(value, expected):
    return (type(value) is dict and set(value) == set(expected)
            and _plain_strings(value.get("postimages"))
            and all(type(value[key]) is str for key in expected if key != "postimages")
            and value == expected)


def _privacy_derivation(launch, vendor, *, publication=None):
    """Require the existing held owner's verified receipt, never mint a grant."""
    selected = launch.recipe.get("vendor_derivation")
    if publication is not None and type(publication) is not ExecutiveContextConsumerPublication:
        _refuse("NATIVE_AGENTOS_PRIVACY_DERIVATION_REQUIRED")
    current = publication is not None and publication.workspace_principal is not None
    expected = {"kind": WORKSPACE_OAUTH_DERIVATION_KIND if current else PRIVACY_DERIVATION_KIND,
        "base_sha": DERIVATION_BASE,
        "patch_sha256": WORKSPACE_OAUTH_DERIVATION_PATCH if current else PRIVACY_DERIVATION_PATCH,
        "postimages": dict(WORKSPACE_OAUTH_DERIVATION_POSTIMAGES if current else PRIVACY_DERIVATION_POSTIMAGES),
        "license_sha256": PRIVACY_LICENSE_SHA256, "vendor_root": str(vendor)}
    if (not _plain_strings(selected)
            or set(selected) != {"kind", "base_sha", "patch_sha256", "source_root"}
            or any(selected[key] != expected[key] for key in ("kind", "base_sha", "patch_sha256"))
            or type(selected["source_root"]) is not str or not Path(selected["source_root"]).is_absolute()
            or launch.recipe.get("vendor_root") != str(vendor)
            or not _privacy_receipt_equal(getattr(launch, "derivation", None), expected)):
        _refuse("NATIVE_AGENTOS_PRIVACY_DERIVATION_REQUIRED")
    return dict(selected), expected


def _function(module, name, cls=None):
    value = getattr(module if cls is None else cls, name, None)
    if (not inspect.isfunction(value) or value.__globals__ is not vars(module)
            or value.__module__ != module.__name__
            or Path(value.__code__.co_filename).resolve() != Path(module.__file__).resolve()
            or inspect.iscoroutinefunction(value)):
        _refuse("NATIVE_AGENTOS_MEMORY_SEAM_CHANGED")
    return value


class _Claim:
    """Transient delivery state for an existing native claim, never a grant."""
    def __init__(self, factory, scope, turn):
        self.factory, self.scope, self.turn = factory, scope, turn
        self.agent = self.instance = None
        self.loading = True
        self.collector_loading = False
        self.loader_module = None
        self.failed = False
        self.barrier_entered = False
        self.returned = None
        self.manager_return = None
        self.prompt = None

    def current(self, *, adopted=False):
        scope, factory = self.scope, self.factory
        return (not self.failed and not scope.closed and scope.binding is factory.observation
                and getattr(scope, _CLAIM_ATTRIBUTE, None) is self and scope.current()
                and scope.session_id == factory.session_id
                and scope.instance_id == factory.instance_id and scope.epoch == factory.authority_epoch
                and factory.registered_current()
                and (not adopted or (self.agent is not None and scope.adopted(self.agent))))

    def identity(self):
        return {"admission_id": self.scope.admission_id,
                "execution_generation": self.scope.generation,
                "agent_session_id": self.agent.session_id}


class _Instance:
    """Ports attached to the actual provider in the actual native manager."""
    def __init__(self, factory, claim):
        self.factory, self.claim = factory, claim
        self.provider = self.agent = self.manager = None
        self.original_prefetch = None

    def resolve(self, session_id, **context):
        claim = self.claim
        if (observation._current.get() is not claim.scope or not claim.current()
                or (self.agent is not None and session_id != self.agent.session_id)):
            raise AgentOsRefusal("AGENTOS_BINDING_UNAVAILABLE")
        publication = self.factory.publication
        generation = _sha(_canonical({**(claim.identity() if claim.agent is not None else {
            "admission_id": claim.scope.admission_id, "execution_generation": claim.scope.generation,
            "agent_session_id": session_id}), "instance_id": claim.scope.instance_id,
            "authority_epoch": claim.scope.epoch,
            "mission_generation": publication.authority_generation_digest}))
        return AgentOsBinding(session_id, publication.session.role, self.factory.slot.profile_id,
            str(self.factory.role_home), publication.work_ref, None, generation,
            publication.context.max_context_bytes)

    def current_generation(self, binding):
        claim = self.claim
        if (not claim.current(adopted=True) or self.agent is not claim.agent
                or self.manager is None or getattr(self.agent, "_memory_manager", None) is not self.manager
                or type(self.manager) is not self.factory.memory_manager_class
                or self.manager.get_provider("agentos") is not self.provider
                or getattr(self.provider, _INSTANCE_ATTRIBUTE, None) is not self
                or getattr(self.provider.prefetch, "__self__", None) is not self
                or getattr(self.provider.prefetch, "__func__", None) is not _Instance.prefetch
                or binding.session_id != self.agent.session_id
                or binding.workstream != self.factory.slot.publication.work_ref):
            return None
        # The provider epoch/immutable binding separately excludes old reads.
        expected = _sha(_canonical({**claim.identity(), "instance_id": claim.scope.instance_id,
            "authority_epoch": claim.scope.epoch,
            "mission_generation": self.factory.publication.authority_generation_digest}))
        return expected

    def binding_current(self, binding):
        return self.current_generation(binding) == binding.generation

    def prefetch(self, query, *, session_id=""):
        claim = self.claim
        binding, epoch = self.provider._binding, self.provider._epoch
        if (observation._current.get() is not claim.scope or binding is None
                or not claim.current(adopted=True)):
            return ""
        text = self.original_prefetch(query, session_id=session_id)
        if (not text or self.claim is not claim or observation._current.get() is not claim.scope
                or self.provider._binding is not binding or self.provider._epoch != epoch
                or not claim.current(adopted=True)):
            return ""
        snapshot = self.provider.context_observation()
        if snapshot is None or _sha(text.encode("utf-8")) != snapshot["rendered_context_sha256"]:
            return ""
        claim.returned = {**claim.identity(), "bundle_sha256": snapshot["bundle_sha256"],
            "receipt_sha256": snapshot["receipt_sha256"],
            "prefetch_context_sha256": snapshot["rendered_context_sha256"],
            "prefetch_context_bytes": snapshot["rendered_context_bytes"], "prompt": None}
        self.factory.last_delivery = dict(claim.returned)
        return text


class NativeAgentOsMemoryFactory:
    """Qualified loader composition retained by the original ConsumerSlot."""
    def __init__(self, launch, role_home, slot, request_observation, modules, privacy):
        self.launch, self.role_home, self.slot = launch, role_home, slot
        self.observation, self.modules = request_observation, modules
        # Detached values from the already verified release owner. Cheap claim
        # and loader guards compare them without filesystem I/O or new grants.
        self.privacy_selection, self.privacy_receipt = privacy
        self.document = validate_consumer_publication(launch.recipe["executive_consumer"])
        self.publication = slot.publication
        if self.publication != publication_from_document(self.document):
            _refuse("NATIVE_AGENTOS_PUBLICATION_CHANGED")
        self.publication_sha256 = _sha(_canonical(self.document))
        self.session_id = self.instance_id = self.authority_epoch = None
        self.connection = self.rpc_current = None
        self.connection_current = None
        self.wrappers = []
        self.last_instance = self.last_delivery = None
        self.memory_manager_class = modules["agent.memory_manager"].MemoryManager
        self.collector_class = modules["plugins.memory"]._ProviderCollector

    def local_current(self):
        try:
            slot = self.slot
            return (slot.memory_factory is self and slot.manager is not None
                and slot.publication is self.publication
                and callable(slot.import_current) and slot.import_current() is True
                and getattr(slot.manager, CONSUMER_SLOT_ATTRIBUTE, None) is slot
                and str(slot.manager.scope_key) == str(self.role_home) == str(slot.scope)
                and not self.launch.owner.closed and not self.launch.closure.closed
                and _plain_strings(self.launch.recipe.get("vendor_derivation"))
                and self.launch.recipe["vendor_derivation"] == self.privacy_selection
                and self.launch.recipe.get("vendor_root") == self.privacy_receipt["vendor_root"]
                and _privacy_receipt_equal(self.launch.derivation, self.privacy_receipt)
                and self.launch.recipe["executive_consumer"] == self.document
                and (self.connection_current is None or self.connection_current() is True)
                and all(getattr(owner, name, None) is wrapper for owner, name, wrapper in self.wrappers))
        except Exception:
            return False

    def configure(self, *, session_id, instance_id, authority_epoch, server, session, loop,
                  currentness, connection_current):
        identity = (session_id, instance_id, authority_epoch, server, session, loop)
        if self.connection is not None:
            _refuse("NATIVE_AGENTOS_ORIGINAL_FACTORY_RETAINED")
        if (not observation._text(session_id) or not observation._text(instance_id)
                or not observation._integer(authority_epoch) or authority_epoch < 1
                or not callable(currentness) or not callable(connection_current) or not self.local_current()):
            _refuse()
        self.session_id, self.instance_id, self.authority_epoch = identity[:3]
        self.connection, self.rpc_current = identity[3:], currentness
        self.connection_current = connection_current

    def loader_ready(self):
        return self.connection is not None and self.local_current()

    def registered_current(self):
        slot = self.slot
        loaded = getattr(slot.manager, "_plugins", {}).get(CONSUMER_PLUGIN_NAME)
        return (self.loader_ready() and slot.context_registration is not None
            and getattr(slot.context_registration, "_manager", None) is slot.manager
            and slot.load_outcome in {"REGISTERED", "CONTEXT_REGISTERED"}
            and slot.registration_error is None and loaded is not None and loaded is slot.loader_record
            and getattr(loaded, "enabled", None) is True and getattr(loaded, "error", None) is None)

    def current_claim(self):
        scope = observation._current.get()
        claim = getattr(scope, _CLAIM_ATTRIBUTE, None)
        if type(claim) is not _Claim or claim.factory is not self or not claim.current():
            _refuse("NATIVE_AGENTOS_CLAIM_UNAVAILABLE")
        return claim

    def register_provider(self, collector):
        from hermes_cli.plugins_ledger import _hook_source_of
        claim = self.current_claim()
        if (type(collector) is not self.collector_class or collector.name != CONSUMER_PLUGIN_NAME
                or collector.provider is not None or not claim.loading or not claim.collector_loading
                or claim.loader_module is None or claim.instance is not None
                or collector._hook_source != _hook_source_of(CONSUMER_PLUGIN_NAME, claim.loader_module)
                or not self.loader_ready() or self.slot.context_registration is None
                or collector._plugin_context()._manager is not self.slot.manager):
            _refuse("NATIVE_AGENTOS_ORIGINAL_PROVIDER_RETAINED")
        self.slot.package_check()
        instance = _Instance(self, claim)
        # Retain before any native collector registration can partially succeed.
        claim.instance = instance
        server, session, loop = self.connection
        reader = NativeAgentOsContextRead(publication=self.publication,
            server=server, session=session, loop=loop, currentness=self.rpc_current,
            binding_current=instance.binding_current)
        provider = create_provider(ports=AgentOsHostPorts(instance, instance), remote_reader=reader,
            freshness_seconds=self.publication.context.freshness_seconds,
            upstream_module=self.modules["agent.memory_provider"], allow_missing_base=False)
        instance.provider = provider
        instance.original_prefetch = provider.prefetch
        provider.prefetch = instance.prefetch
        setattr(provider, _INSTANCE_ATTRIBUTE, instance)
        collector.register_memory_provider(provider)
        return provider

    def bind_agent(self, claim, agent):
        manager = getattr(agent, "_memory_manager", None)
        if type(manager) is not self.memory_manager_class:
            _refuse("NATIVE_AGENTOS_PROVIDER_NOT_INSTALLED")
        provider = manager.get_provider("agentos")
        instance = getattr(provider, _INSTANCE_ATTRIBUTE, None)
        if (type(instance) is not _Instance or instance.factory is not self
                or instance.provider is not provider or (claim.instance is not None and claim.instance is not instance)
                or not claim.current() or (instance.agent is not None and instance.agent is not agent)):
            _refuse("NATIVE_AGENTOS_PROVIDER_NOT_INSTALLED")
        claim.agent, claim.instance = agent, instance
        instance.claim, instance.agent, instance.manager = claim, agent, manager
        setattr(agent, _INSTANCE_ATTRIBUTE, instance)
        # Even a cached same-physical-session agent belongs to a new admission.
        # The incumbent provider epoch discards old/pending material on rebind.
        provider.on_session_switch(agent.session_id)
        if provider._binding is None or provider._binding.session_id != agent.session_id:
            _refuse("NATIVE_AGENTOS_BINDING_UNAVAILABLE")
        self.last_instance = instance

    def prepare_turn(self, agent):
        claim = self.current_claim()
        instance = claim.instance
        if (claim.agent is not agent or type(instance) is not _Instance
                or not claim.current(adopted=True) or claim.barrier_entered):
            _refuse("NATIVE_AGENTOS_CLAIM_UNAVAILABLE")
        claim.barrier_entered = True
        provider = instance.provider
        # Compaction/recovery can rotate the physical session after adoption.
        if provider._binding is None or provider._binding.session_id != agent.session_id:
            provider.on_session_switch(agent.session_id)
        self.launch.check()
        self.require_generation(claim)
        provider.prepare_context()
        status = provider.wait_context(31.0)
        if (status["state"] != "READY" or not claim.current(adopted=True)
                or provider.context_observation() is None):
            claim.failed = True  # Late completion cannot deliver into this claim.
            _refuse("NATIVE_AGENTOS_REQUIRED_CONTEXT_UNAVAILABLE")
        return claim

    def require_generation(self, claim):
        # The native generation owner reads storage off the event lock, on the
        # native turn executor. Cheap background/readiness guards do not do I/O.
        try:
            claim.scope.authority.check_approval_generation(claim.scope.session_id, claim.scope.generation)
        except Exception:
            claim.failed = True
            _refuse("NATIVE_AGENTOS_CLAIM_UNAVAILABLE")

    def require_snapshot(self, claim, agent):
        """Join the current attachment and freshness at every delivery boundary."""
        instance = claim.instance
        provider = instance.provider if type(instance) is _Instance else None
        binding = getattr(provider, "_binding", None)
        if (claim.agent is not agent or not claim.current(adopted=True)
                or binding is None or not instance.binding_current(binding)
                or provider.context_observation() is None):
            claim.failed = True
            _refuse("NATIVE_AGENTOS_REQUIRED_CONTEXT_UNAVAILABLE")
        self.require_generation(claim)

    def owns_agent(self, agent):
        # This marker confers no authority. It prevents an already bound agent
        # from silently becoming an unscoped auxiliary after context/manager loss.
        attached = getattr(agent, _INSTANCE_ATTRIBUTE, None)
        if type(attached) is _Instance and attached.factory is self:
            return True
        manager = getattr(agent, "_memory_manager", None)
        if type(manager) is self.memory_manager_class:
            attached = getattr(manager.get_provider("agentos"), _INSTANCE_ATTRIBUTE, None)
            return type(attached) is _Instance and attached.factory is self
        return False

    def note_prompt(self, claim, agent, messages, result, *, current_turn_user_idx, ext_prefetch_cache):
        """Observe the actual current user row, never a historical match."""
        returned = claim.returned
        if (returned is None or not claim.current(adopted=True) or claim.agent is not agent
                or claim.manager_return != returned["prefetch_context_sha256"]
                or type(ext_prefetch_cache) is not str or not ext_prefetch_cache
                or _sha(ext_prefetch_cache.encode("utf-8")) != returned["prefetch_context_sha256"]
                or type(current_turn_user_idx) is not int
                or not 0 <= current_turn_user_idx < len(messages)
                or messages[current_turn_user_idx].get("role") != "user"):
            return
        api_messages, effective_system = result
        if type(api_messages) is not list:
            return
        # The native builder may canonicalize/drop historical prefix rows.
        # Its current-turn suffix remains one-for-one, with optional system
        # prefix insertion. Count backward from that suffix, not the old index.
        suffix = messages[current_turn_user_idx:]
        index = len(api_messages) - len(suffix)
        if (not 0 <= index < len(api_messages) or api_messages[index].get("role") != "user"
                or [row.get("role") for row in api_messages[index:]] != [row.get("role") for row in suffix]):
            return
        block = self.modules["agent.memory_context"].build_memory_context_block(ext_prefetch_cache)
        content = api_messages[index].get("content")
        pieces = ([content] if type(content) is str else [item.get("text") for item in content
            if type(item) is dict and item.get("type") == "text"] if type(content) is list else [])
        if not block or not any(type(piece) is str and block in piece for piece in pieces):
            return
        # Bound digest work through the existing original-request observer.
        digest = observation._content_digest({"messages": api_messages})["content_sha256"]
        turn_id = getattr(agent, "_current_turn_id", None)
        if not observation._text(turn_id):
            return
        prompt = {"boundary": "build_api_messages", "turn_id": turn_id,
                  "context_block_sha256": _sha(block.encode("utf-8")), "api_messages_sha256": digest}
        claim.prompt = prompt
        claim.returned = {**returned, "prompt": prompt}
        self.last_delivery = dict(claim.returned)

    def readback(self):
        """Observe existing owners only; never prepare or invoke prefetch."""
        if not self.registered_current():
            _refuse("NATIVE_AGENTOS_FACTORY_UNAVAILABLE")
        self.launch.check()
        instance = self.last_instance
        claim = None if instance is None else instance.claim
        provider = None if instance is None else instance.provider
        binding = None if provider is None else provider._binding
        epoch = None if provider is None else provider._epoch
        installed = (type(instance) is _Instance and claim.factory is self
            and not claim.scope.closed and claim.scope.current() and claim.scope.adopted(instance.agent)
            and instance.agent is claim.agent and type(instance.manager) is self.memory_manager_class
            and getattr(instance.agent, "_memory_manager", None) is instance.manager
            and instance.manager.get_provider("agentos") is instance.provider
            and getattr(instance.provider, _INSTANCE_ATTRIBUTE, None) is instance)
        identity = claim.identity() if installed else None
        readiness = provider.readiness() if installed else None
        snapshot = provider.context_observation() if installed else None
        context = {"provider": "agentos", "source_mode": self.publication.context.source_mode,
            "factory_registered": True, "provider_installed": installed,
            "readiness": None if readiness is None else {
                "state": readiness["state"], "reason": readiness["reason"]},
            "active_claim": identity,
            "snapshot": snapshot,
            "last_delivery": None if self.last_delivery is None else json.loads(_canonical(self.last_delivery))}
        if (not self.registered_current() or self.last_instance is not instance
                or (instance is not None and (instance.claim is not claim or instance.provider is not provider
                    or provider._binding is not binding or provider._epoch != epoch))
                or (installed and (claim.identity() != identity or claim.scope.closed
                    or not claim.scope.current() or not claim.scope.adopted(instance.agent)
                    or getattr(instance.agent, "_memory_manager", None) is not instance.manager
                    or instance.manager.get_provider("agentos") is not provider
                    or (readiness["state"] == "READY") != (snapshot is not None)))):
            _refuse("NATIVE_AGENTOS_FACTORY_UNAVAILABLE")
        return {"schema": CURRENT_READBACK_SCHEMA if self.publication.workspace_principal is not None else READBACK_SCHEMA,
            "binding": {
            "implementation_sha": self.slot.owner, "publication_sha256": self.publication_sha256,
            "profile_id": str(self.role_home), "instance_id": self.instance_id,
            "authority_epoch": self.authority_epoch,
            "enrollment_request_id": self.slot.publication.session.request_id,
            "principal_id": self.slot.publication.session.principal_id, "session_id": self.session_id},
            "context": context, "selected_child": None}


def register_memory_provider(ctx):
    """Only the real native memory collector, reached in the held load scope."""
    from hermes_cli.plugins import get_plugin_manager
    slot = getattr(get_plugin_manager(), CONSUMER_SLOT_ATTRIBUTE, None)
    if not isinstance(slot, ConsumerSlot) or type(slot.memory_factory) is not NativeAgentOsMemoryFactory:
        _refuse()
    return slot.memory_factory.register_provider(ctx)


def validate_consumer_readback(value, *, publication, expected_binding):
    """Closed observation at the existing private serving-process boundary.

    This validates observed stages, not a grant or an efficacy conclusion.
    Historical delivery remains separate from the current claim/snapshot.
    """
    from integrations.hermes_harness.agentos_memory_provider import PROVIDER_CODES, OWNER_CODES
    from integrations.hermes_harness.native_executive_consumer import selected_child_publication
    def shape(item, keys):
        if type(item) is not dict or set(item) != set(keys):
            _refuse("NATIVE_AGENTOS_READBACK_INVALID")
    def digest(item):
        return type(item) is str and len(item) == 64 and all(ch in "0123456789abcdef" for ch in item)
    def claim(item):
        shape(item, ("admission_id", "execution_generation", "agent_session_id"))
        if (not observation._text(item["admission_id"]) or not observation._text(item["agent_session_id"])
                or not observation._integer(item["execution_generation"]) or item["execution_generation"] < 1):
            _refuse("NATIVE_AGENTOS_READBACK_INVALID")
    if type(publication) is not ExecutiveContextConsumerPublication:
        _refuse("NATIVE_AGENTOS_READBACK_INVALID")
    shape(value, ("schema", "binding", "context", "selected_child"))
    shape(value["binding"], ("implementation_sha", "publication_sha256", "profile_id", "instance_id",
        "authority_epoch", "enrollment_request_id", "principal_id", "session_id"))
    expected_schema = CURRENT_READBACK_SCHEMA if publication.workspace_principal is not None else READBACK_SCHEMA
    if (value["schema"] != expected_schema or value["binding"] != expected_binding
            or not observation._integer(value["binding"]["authority_epoch"])
            or value["binding"]["authority_epoch"] < 1):
        _refuse("NATIVE_AGENTOS_READBACK_INVALID")
    context = value["context"]
    shape(context, ("provider", "source_mode", "factory_registered", "provider_installed",
                    "readiness", "active_claim", "snapshot", "last_delivery"))
    if (context["provider"] != "agentos" or context["source_mode"] != publication.context.source_mode
            or context["factory_registered"] is not True or type(context["provider_installed"]) is not bool):
        _refuse("NATIVE_AGENTOS_READBACK_INVALID")
    if not context["provider_installed"]:
        if any(context[key] is not None for key in ("readiness", "active_claim", "snapshot")):
            _refuse("NATIVE_AGENTOS_READBACK_INVALID")
    else:
        claim(context["active_claim"])
        shape(context["readiness"], ("state", "reason"))
        state, reason = context["readiness"]["state"], context["readiness"]["reason"]
        if (state not in {"UNBOUND", "PENDING", "READY", "UNAVAILABLE", "CLOSED"}
                or (reason is not None and (type(reason) is not str or reason not in PROVIDER_CODES | OWNER_CODES))
                or (state == "READY" and reason is not None)):
            _refuse("NATIVE_AGENTOS_READBACK_INVALID")
        snapshot = context["snapshot"]
        if (state == "READY") != (snapshot is not None):
            _refuse("NATIVE_AGENTOS_READBACK_INVALID")
        if snapshot is not None:
            shape(snapshot, ("bundle_sha256", "receipt_sha256", "rendered_context_sha256",
                             "rendered_context_bytes", "remaining_ms"))
            if (any(not digest(snapshot[key]) for key in (
                    "bundle_sha256", "receipt_sha256", "rendered_context_sha256"))
                    or type(snapshot["rendered_context_bytes"]) is not int
                    or not 0 < snapshot["rendered_context_bytes"] <= publication.context.max_context_bytes
                    or type(snapshot["remaining_ms"]) is not int
                    or not 0 <= snapshot["remaining_ms"] <= int(publication.context.freshness_seconds * 1000)):
                _refuse("NATIVE_AGENTOS_READBACK_INVALID")
    delivery = context["last_delivery"]
    if delivery is not None:
        shape(delivery, ("admission_id", "execution_generation", "agent_session_id", "bundle_sha256",
            "receipt_sha256", "prefetch_context_sha256", "prefetch_context_bytes", "prompt"))
        claim({key: delivery[key] for key in ("admission_id", "execution_generation", "agent_session_id")})
        if (any(not digest(delivery[key]) for key in (
                "bundle_sha256", "receipt_sha256", "prefetch_context_sha256"))
                or type(delivery["prefetch_context_bytes"]) is not int
                or not 0 < delivery["prefetch_context_bytes"] <= publication.context.max_context_bytes):
            _refuse("NATIVE_AGENTOS_READBACK_INVALID")
        prompt = delivery["prompt"]
        if prompt is not None:
            shape(prompt, ("boundary", "turn_id", "context_block_sha256", "api_messages_sha256"))
            if (prompt["boundary"] != "build_api_messages" or not observation._text(prompt["turn_id"])
                    or not digest(prompt["context_block_sha256"]) or not digest(prompt["api_messages_sha256"])):
                _refuse("NATIVE_AGENTOS_READBACK_INVALID")
    if (selected_child_publication(publication) is None) != (value["selected_child"] is None):
        _refuse("NATIVE_AGENTOS_READBACK_INVALID")
    if value["selected_child"] is not None and type(value["selected_child"]) is not dict:
        _refuse("NATIVE_AGENTOS_READBACK_INVALID")
    try:
        raw = _canonical(value)
        if len(raw) > 16 * 1024:
            _refuse("NATIVE_AGENTOS_READBACK_INVALID")
        return json.loads(raw)
    except (ValueError, TypeError, UnicodeError):
        _refuse("NATIVE_AGENTOS_READBACK_INVALID")


def install_native_agentos_memory(launch, vendor: Path, role_home: Path, request_observation):
    """Bind once, before native startup/discovery, to the held optional v2 slot."""
    from hermes_cli.plugins import get_plugin_manager
    from .native_gateway_entry import _digest, _vendor_module
    slot = getattr(get_plugin_manager(), CONSUMER_SLOT_ATTRIBUTE, None)
    if not isinstance(slot, ConsumerSlot) or type(slot.publication) is not ExecutiveContextConsumerPublication:
        return None
    if slot.memory_factory is not None:
        _refuse("NATIVE_AGENTOS_FACTORY_ALREADY_BOUND")
    privacy = _privacy_derivation(launch, vendor, publication=slot.publication)
    modules = {}
    for path, expected in SOURCE_SHA256.items():
        if _digest(vendor / path, maximum=256 * 1024) != expected:
            _refuse("NATIVE_AGENTOS_MEMORY_SOURCE_MISMATCH")
        name = path.removesuffix("/__init__.py").removesuffix(".py").replace("/", ".")
        # Package origin is __init__.py, not the simple-module helper's .py path.
        if path.endswith("/__init__.py"):
            module = importlib.import_module(name)
            if Path(getattr(module, "__file__", "")).resolve() != (vendor / path).resolve():
                _refuse("NATIVE_AGENTOS_MEMORY_SOURCE_MISMATCH")
        else:
            module = _vendor_module(name, vendor)
        if type(module) is not ModuleType:
            _refuse("NATIVE_AGENTOS_MEMORY_SEAM_CHANGED")
        modules[name] = module
    memory, execution, turns = modules["plugins.memory"], modules["gateway.session_execution"], modules["gateway.run_turn_runner"]
    turn_context, isolation = modules["agent.turn_context"], modules["hermes_cli.plugin_isolation"]
    resolve = _function(execution, "_resolve_turn_agent", execution.GatewaySessionAgentMixin)
    wire_callbacks = _function(turns, "_wire_turn_agent_callbacks", turns.TurnRunner)
    load = _function(memory, "load_memory_provider")
    find = _function(memory, "find_provider_dir")
    package_load = _function(memory, "_load_package")
    prefetch = _function(turn_context, "_memory_turn_start_and_prefetch")
    build_messages = _function(turn_context, "build_api_messages")
    _function(modules["agent.agent_init"], "_init_memory")
    factory = NativeAgentOsMemoryFactory(launch, role_home, slot, request_observation, modules, privacy)
    package = Path(slot.package_path)

    def find_provider(name):
        if name != "agentos":
            return find(name)
        slot.package_check()
        return package

    def held_package(provider_dir, name):
        if Path(provider_dir) != package:
            return package_load(provider_dir, name)
        if (name != CONSUMER_PLUGIN_NAME or isolation.in_process_import_refusal(
                "Mastermind adopted context", source="user") is not None):
            _refuse("NATIVE_AGENTOS_MEMORY_ISOLATION_REFUSED")
        slot.package_check()
        # Reuse the existing held first-party source importer. Explicit native
        # spec_from_file_location would bypass it and could consume .pyc or an
        # unlisted sibling. Original native collector/lifecycle remains intact.
        module = importlib.import_module(_PACKAGE_MODULE)
        if Path(module.__file__) != package / "__init__.py":
            _refuse("NATIVE_AGENTOS_MEMORY_SOURCE_MISMATCH")
        slot.package_check()
        claim = factory.current_claim()
        if not claim.collector_loading or claim.loader_module is not None:
            _refuse("NATIVE_AGENTOS_ORIGINAL_PROVIDER_RETAINED")
        claim.loader_module = module
        return module

    def load_provider(name, *, register_skills=None):
        if name != "agentos":
            return load(name, register_skills=register_skills)
        claim = factory.current_claim()
        if (not claim.loading or not factory.loader_ready() or isolation.in_process_import_refusal(
                "Mastermind adopted context", source="user") is not None):
            _refuse("NATIVE_AGENTOS_MEMORY_ISOLATION_REFUSED")
        if claim.collector_loading or claim.loader_module is not None:
            _refuse("NATIVE_AGENTOS_ORIGINAL_PROVIDER_RETAINED")
        claim.collector_loading = True
        try:
            result = load(name, register_skills=register_skills)
        finally:
            claim.collector_loading = False
        if claim.instance is None or result is not claim.instance.provider:
            # Do not enter the native download/migration fallback for a missing
            # sealed provider, and retain a partially registered original.
            _refuse("NATIVE_AGENTOS_PROVIDER_NOT_INSTALLED")
        return result

    def resolve_agent(turn, *args, **kwargs):
        scope = observation._current.get()
        if (scope is None or scope.binding is not request_observation
                or not scope.current() or scope.closed or scope.session_id != factory.session_id
                or getattr(turn, "_approval_owner", None) != (scope.authority, scope.session_id, scope.generation)
                or getattr(scope, _CLAIM_ATTRIBUTE, None) is not None):
            _refuse("NATIVE_AGENTOS_CLAIM_UNAVAILABLE")
        claim = _Claim(factory, scope, turn)
        setattr(scope, _CLAIM_ATTRIBUTE, claim)
        try:
            result = resolve(turn, *args, **kwargs)
            factory.bind_agent(claim, result[0])
            return result
        except BaseException:
            claim.failed = True
            raise
        finally:
            claim.loading = False

    def wire_agent(turn, agent, *args, **kwargs):
        result = wire_callbacks(turn, agent, *args, **kwargs)
        claim = factory.current_claim()
        if claim.turn is not turn or claim.agent is not agent or not claim.current(adopted=True):
            claim.failed = True
            _refuse("NATIVE_AGENTOS_ADOPTION_UNAVAILABLE")
        return result

    def prefetch_turn(agent, original_user_message, turn_author=None):
        if not factory.owns_agent(agent):
            return prefetch(agent, original_user_message, turn_author)
        claim = factory.prepare_turn(agent)
        result = prefetch(agent, original_user_message, turn_author)
        if not claim.current(adopted=True):
            claim.failed = True
            _refuse("NATIVE_AGENTOS_CLAIM_UNAVAILABLE")
        if type(result) is str and result:
            claim.manager_return = _sha(result.encode("utf-8"))
        return result

    def api_messages(agent, messages, **kwargs):
        if not factory.owns_agent(agent):
            return build_messages(agent, messages, **kwargs)
        claim = factory.current_claim()
        if claim.agent is not agent or not claim.current(adopted=True) or not claim.barrier_entered:
            _refuse("NATIVE_AGENTOS_CLAIM_UNAVAILABLE")
        factory.require_snapshot(claim, agent)
        result = build_messages(agent, messages, **kwargs)
        factory.require_snapshot(claim, agent)
        try:
            factory.note_prompt(claim, agent, messages, result,
                current_turn_user_idx=kwargs["current_turn_user_idx"],
                ext_prefetch_cache=kwargs["ext_prefetch_cache"])
        except Exception:
            pass  # Observation failure cannot invent a native request failure.
        return result

    wrappers = [(memory, "find_provider_dir", find_provider), (memory, "_load_package", held_package),
        (memory, "load_memory_provider", load_provider),
        (execution.GatewaySessionAgentMixin, "_resolve_turn_agent", resolve_agent),
        (turns.TurnRunner, "_wire_turn_agent_callbacks", wire_agent),
        (turn_context, "_memory_turn_start_and_prefetch", prefetch_turn),
        (turn_context, "build_api_messages", api_messages)]
    launch.check()
    if _privacy_derivation(launch, vendor, publication=slot.publication) != privacy:
        _refuse("NATIVE_AGENTOS_PRIVACY_DERIVATION_REQUIRED")
    slot.memory_factory = factory
    factory.wrappers = wrappers
    for owner, name, wrapper in wrappers:
        setattr(owner, name, wrapper)
    return factory
