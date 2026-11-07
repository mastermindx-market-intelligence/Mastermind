"""Pinned native GatewayRunner entry inside the existing Hermes supervisor.

This owns no daemon, session, ticket, queue or retry. The installer publishes a
real ``hermes`` launcher; native main retains its normal process recognition,
profile selection, SessionAuthority, mailbox recovery and shutdown. The API
uses the fixed role-local address; Secretary operations extend the existing
private control socket with one closed verb. Vendor classes remain unchanged.
"""
from __future__ import annotations

import hashlib
import importlib
import os
from pathlib import Path
import stat
import sys

from .constants import PINNED_UPSTREAM_SHA
from .egress import ROLE_PROXY_HOST
from .errors import RuntimeRefusal

BACKEND = "native-session-authority"
RUN_API_SHA256 = "77628713200032a963bf8c7882edcf0945e3c1343787f608050d5bcbc24735af"
_CAPABILITIES = frozenset({"session-authority-v1", "durable-admission-v1", "event-replay-v1"})


def _digest(path: Path, *, maximum: int = 64 * 1024 * 1024) -> str:
    with path.open("rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_size > maximum
                or info.st_uid not in {0, os.geteuid()} or info.st_mode & 0o022):
            raise RuntimeRefusal("NATIVE_ENTRY_SOURCE_UNQUALIFIED")
        data = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    if len(data) > maximum or (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
                              info.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size,
                                                    after.st_mtime_ns, after.st_ctime_ns):
        raise RuntimeRefusal("NATIVE_ENTRY_SOURCE_CHANGED")
    return hashlib.sha256(data).hexdigest()


def _selection(role: str, host: str, port: int) -> None:
    if (role not in ROLE_PROXY_HOST or host != ROLE_PROXY_HOST[role]
            or type(port) is not int or not 1024 <= port <= 65535):
        raise RuntimeRefusal("NATIVE_GATEWAY_SELECTION_UNQUALIFIED")


def _vendor_module(name: str, root: Path):
    module = importlib.import_module(name)
    origin = getattr(module, "__file__", None)
    expected = root.joinpath(*name.split(".")).with_suffix(".py")
    if origin is None or Path(origin).resolve() != expected:
        raise RuntimeRefusal("NATIVE_MODULE_ORIGIN_MISMATCH")
    return module


def bind_native_api(module, *, vendor: Path, role_home: Path, role: str,
                    host: str, port: int, implementation_sha: str | None = None,
                    session_enrollment: dict | None = None,
                    consumer_transition=None, request_observation=None) -> None:
    _selection(role, host, port)
    if getattr(module, "_mmx_role_api_bound", False):
        raise RuntimeRefusal("NATIVE_API_ALREADY_BOUND")
    original = module.start_gateway_api
    if _digest(vendor / "gateway/run_api.py", maximum=128 * 1024) != RUN_API_SHA256:
        raise RuntimeRefusal("NATIVE_API_SOURCE_MISMATCH")

    async def start_role_gateway_api(runner):
        # Closed signature: callers cannot override either bound address.
        authority = getattr(runner, "session_authority", None)
        descriptor = getattr(runner, "session_runtime_descriptor", None)
        if (authority is None or str(getattr(authority, "profile_id", "")) != str(role_home)
                or type(descriptor) is not dict
                or not descriptor.get("instance_id")
                or getattr(authority, "instance_id", None) != descriptor["instance_id"]
                or getattr(authority, "epoch", None) != descriptor.get("authority_epoch")
                or getattr(runner.config, "multiplex_profiles", False)):
            raise RuntimeRefusal("NATIVE_PROFILE_AUTHORITY_MISMATCH")
        from .native_session_control import install_private_control
        options = {"implementation_sha": implementation_sha,
                   "session_enrollment": session_enrollment}
        if consumer_transition is not None:
            options["consumer_transition"] = consumer_transition
        if request_observation is not None:
            request_observation.bind_authority(runner)
        install_private_control(runner, role_home, role, **options)
        return await original(runner, host=host, port=port)

    module.start_gateway_api = start_role_gateway_api
    module._mmx_role_api_bound = True


def native_git_environment(vendor: Path) -> dict[str, str]:
    """Trust only the already-qualified root-owned checkout in this process.

    Native version_info uses plain Git to attest its own code. A distinct role
    UID needs one exact safe.directory. No global configuration is changed;
    optional index refresh writes and ambient system/user Git config are off.
    """
    return {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "safe.directory",
        "GIT_CONFIG_VALUE_0": str(vendor),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
    }


def prepare_vendor(vendor: Path) -> None:
    """Select the installed vendor for native imports, never ambient modules."""
    vendor = vendor.resolve(strict=True)
    if _digest(vendor / "gateway/run_api.py", maximum=128 * 1024) != RUN_API_SHA256:
        raise RuntimeRefusal("NATIVE_API_SOURCE_MISMATCH")
    for name in ("gateway", "hermes_cli"):
        loaded = sys.modules.get(name)
        if loaded is not None:
            expected = vendor / name / "__init__.py"
            if Path(getattr(loaded, "__file__", "")).resolve() != expected:
                raise RuntimeRefusal("NATIVE_MODULE_ORIGIN_MISMATCH")
    if str(vendor) not in sys.path:
        raise RuntimeRefusal("NATIVE_IMPORT_ROOT_NOT_QUALIFIED")



def _bind_consumer_provider_imports(launch, vendor: Path) -> None:
    """Constrain native provider imports before CLI/config import can discover.

    Keep native bundled/legacy providers and their original registry. Exclude
    role-home and pip provider code through the existing two native hooks.
    """
    if launch.recipe.get("executive_consumer") is None:
        return
    launch.check()
    providers = importlib.import_module("providers")
    package = vendor / "providers"
    bundled = vendor / "plugins/model-providers"
    if (Path(getattr(providers, "__file__", "")).resolve() != package / "__init__.py"
            or tuple(str(Path(path).resolve()) for path in getattr(providers, "__path__", ()))
               != (str(package),)
            or getattr(providers, "_BUNDLED_PLUGINS_DIR", None) != bundled
            or getattr(providers, "_discovered", None) is not False
            or getattr(providers, "_discovering", None) is not False
            or any(getattr(providers, name, None) != {}
                   for name in ("_REGISTRY", "_ALIASES", "_SOURCES", "_HOME_LAYERS"))
            or hasattr(providers, "_mmx_provider_import_owner")):
        raise RuntimeRefusal("NATIVE_PROVIDER_IMPORT_BOUNDARY_UNAVAILABLE")
    original_directory_import = providers._import_plugin_dir
    if (not callable(original_directory_import)
            or not callable(getattr(providers, "_discover_entry_point_providers", None))):
        raise RuntimeRefusal("NATIVE_PROVIDER_IMPORT_BOUNDARY_UNAVAILABLE")
    launch.check()

    def import_directory(plugin_dir, source, *, home_key=""):
        if source != "bundled" or home_key != "":
            return None
        launch.check()
        candidate = Path(plugin_dir)
        if (not candidate.is_absolute() or candidate.parent != bundled
                or candidate.is_symlink() or not candidate.is_dir()
                or candidate.resolve(strict=True) != candidate
                or bundled.resolve(strict=True) != bundled):
            raise RuntimeRefusal("NATIVE_PROVIDER_SOURCE_UNQUALIFIED")
        result = original_directory_import(candidate, source, home_key=home_key)
        launch.check()
        return result

    def exclude_entry_points():
        launch.check()
        return None

    # Native discovery remains lazy. No flags, registries or aliases are reset.
    providers._import_plugin_dir = import_directory
    providers._discover_entry_point_providers = exclude_entry_points
    providers._mmx_provider_import_owner = launch


def _consumer_trust_gate(publication):
    """The incumbent MCP trust gate, consulted before a model-facing call."""
    from integrations.hermes_delegate.policy import TOOL_NAME

    def gate(tool_name=TOOL_NAME, booked=None, arguments=None) -> str | None:
        try:
            from tools.mcp_tool_handlers import _trust_gate_check
        except Exception:
            return "NATIVE_CONSUMER_TRUST_GATE_UNAVAILABLE"
        try:
            return _trust_gate_check(publication.mcp.server, tool_name,
                                     [] if booked is None else booked, {} if arguments is None else arguments)
        except Exception:
            return "NATIVE_CONSUMER_TRUST_GATE_UNAVAILABLE"

    return gate


async def _qualify_consumer(runner, document, role_home: Path, launch, *,
                            manager, slot, manifest, package_check) -> None:
    """One finite qualification while the existing gateway loop remains free."""
    import asyncio
    import contextvars
    from integrations.hermes_harness.native_executive_consumer import (
        CONSUMER_SLOT_ATTRIBUTE, capture_native_mcp_owner, install_native_consumer,
        publication_from_document, _consume_future_result)
    from .native_session_control import current_runtime_owner, read_enrolled_session
    from hermes_cli.plugins import get_plugin_manager
    publication = publication_from_document(document)
    owner = launch.owner.root.name
    owner_loop = asyncio.get_running_loop()
    owner_context = contextvars.copy_context()
    enrollment = read_enrolled_session(
        runner, role_home, owner, publication.session.request_id, publication.session.principal_id,
        role=publication.session.role)
    if enrollment["status"] != "ENROLLED":
        slot.qualification_outcome = "UNBOUND"
        return
    target = enrollment["target"]
    identity_keys = ("profile_id", "principal_id", "session_id", "instance_id", "authority_epoch")
    original_identity = tuple(target.get(key) for key in identity_keys)
    original_route = enrollment["route"]
    if (target["profile_id"] != str(role_home)
            or target["principal_id"] != publication.session.principal_id):
        raise RuntimeRefusal("NATIVE_CONSUMER_SESSION_MISMATCH")
    server, session, loop, mcp_current = capture_native_mcp_owner(publication, include_guard=True)

    def inspect_original():
        launch.check()
        if (current_runtime_owner() != owner or get_plugin_manager() is not manager
                or getattr(manager, CONSUMER_SLOT_ATTRIBUTE, None) is not slot
                or manager.scope_key != slot.scope or str(slot.scope) != str(role_home)
                or publication_from_document(launch.recipe["executive_consumer"]) != publication
                or getattr(runner, "_draining", True)):
            return False
        descriptor = runner.session_runtime_descriptor
        if (descriptor.get("state") != "ready"
                or descriptor.get("instance_id") != target["instance_id"]
                or descriptor.get("authority_epoch") != target["authority_epoch"]):
            return False
        observed = read_enrolled_session(
            runner, role_home, owner, publication.session.request_id, publication.session.principal_id,
        role=publication.session.role)
        return (observed["status"] == "ENROLLED"
                and tuple(observed["target"].get(key) for key in identity_keys) == original_identity
                and observed["route"] == original_route and package_check() is True)

    async def inspect_on_owner():
        return inspect_original()

    def session_guard():
        try:
            if not owner_loop.is_running() or not mcp_current():
                return False
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                current_loop = None
            if current_loop is owner_loop:
                valid = inspect_original()
            else:
                coroutine = inspect_on_owner()
                try:
                    future = owner_context.copy().run(
                        asyncio.run_coroutine_threadsafe, coroutine, owner_loop)
                except Exception:
                    coroutine.close()
                    return False
                try:
                    valid = future.result(timeout=5.0)
                except Exception:
                    # Read only, no cancellation/reconnect/replacement.
                    future.add_done_callback(_consume_future_result)
                    return False
            return valid is True and mcp_current()
        except Exception:
            return False

    from integrations.hermes_harness.native_executive_consumer import ExecutiveContextConsumerPublication
    if type(publication) is ExecutiveContextConsumerPublication:
        from .native_agentos_memory import NativeAgentOsMemoryFactory
        if type(slot.memory_factory) is not NativeAgentOsMemoryFactory:
            raise RuntimeRefusal("NATIVE_AGENTOS_FACTORY_UNAVAILABLE")
        slot.memory_factory.configure(session_id=target["session_id"],
            instance_id=target["instance_id"], authority_epoch=target["authority_epoch"],
            server=server, session=session, loop=loop, currentness=session_guard,
            connection_current=mcp_current)

    # The C28 sync contract is retained. Its finite worker uses the incumbent
    # executor; it cannot block the gateway loop needed by original enrollment.
    worker = asyncio.create_task(asyncio.to_thread(
        install_native_consumer, manager=manager, publication=publication, owner=owner,
        profile_id=slot.profile_id, session_id=target["session_id"],
        instance_id=target["instance_id"], authority_epoch=target["authority_epoch"],
        route=original_route, server=server, session=session, loop=loop,
        trust_gate=_consumer_trust_gate(publication), session_guard=session_guard,
        manifest=manifest, package_check=package_check))
    slot.qualification_worker = worker

    def settled(completed):
        try:
            original_slot = completed.result()
            if original_slot is not slot:
                slot.qualification_outcome = "ORIGINAL_SLOT_MISMATCH"
            else:
                slot.qualification_outcome = slot.load_outcome
        except BaseException:
            slot.qualification_outcome = (
                slot.load_outcome if slot.load_attempted else "UNBOUND")
    worker.add_done_callback(settled)
    # Cancelling this observer cannot cancel the underlying native load thread.
    # The slot retains that original worker and prevents a second attempt.
    await asyncio.shield(worker)



_GENERAL_PLUGIN_LOADER_SHA256 = "9a22216f26382407ccd155796afd3d42b8186a5ba717c95865c37f4ca4cd1a3f"
_PLUGIN_ISOLATION_SHA256 = "808f055dd182d5118b1ef187abdf632a3871557a7decd652951af0de0c53eb2c"
_HELD_CONSUMER_MODULE = "integrations.hermes_harness.native_selected_child_plugin"


def _install_held_consumer_import(vendor, manager, slot, manifest, package, package_check):
    """Keep original PluginManager gates/ledger; use the held source importer."""
    import inspect
    from integrations.hermes_harness.native_executive_consumer import CONSUMER_PLUGIN_NAME, CONSUMER_SLOT_ATTRIBUTE
    loader = _vendor_module("hermes_cli.plugins_loader", vendor)
    isolation = _vendor_module("hermes_cli.plugin_isolation", vendor)
    for path, digest in (("hermes_cli/plugins_loader.py", _GENERAL_PLUGIN_LOADER_SHA256),
                         ("hermes_cli/plugin_isolation.py", _PLUGIN_ISOLATION_SHA256)):
        if _digest(vendor / path, maximum=128 * 1024) != digest:
            raise RuntimeRefusal("NATIVE_CONSUMER_LOADER_SOURCE_MISMATCH")
    originals = {}
    for name in ("_load_plugin", "_load_plugin_scoped", "_load_directory_module", "_policy_module_name",
                 "_runs_in_plugin_host"):
        method = getattr(manager, name, None)
        fn = getattr(method, "__func__", None)
        if (not inspect.ismethod(method) or method.__self__ is not manager
                or fn is not getattr(loader.PluginLoaderMixin, name, None)
                or fn.__globals__ is not vars(loader) or fn.__module__ != loader.__name__
                or Path(fn.__code__.co_filename).resolve() != Path(loader.__file__).resolve()):
            raise RuntimeRefusal("NATIVE_CONSUMER_LOADER_SEAM_CHANGED")
        originals[name] = method
    publication = slot.publication

    def reserved(candidate):
        return (getattr(candidate, "name", None) == CONSUMER_PLUGIN_NAME
                or getattr(candidate, "key", None) == CONSUMER_PLUGIN_NAME)

    def current():
        return (getattr(manager, CONSUMER_SLOT_ATTRIBUTE, None) is slot
            and slot.manager is manager and slot.publication is publication
            and manager.scope_key == slot.scope
            and manager._load_directory_module is directory_module
            and manager._policy_module_name is policy_module_name
            and getattr(manager, "_load_plugin_scoped", None) == originals["_load_plugin_scoped"]
            and getattr(manager, "_runs_in_plugin_host", None) == originals["_runs_in_plugin_host"])

    def require_load(candidate):
        if (candidate is not manifest or not current() or not slot.load_attempted
                or not slot.loader_entered or slot.load_outcome != "LOAD_PENDING"
                or getattr(candidate, "source", None) != "user"
                or str(getattr(candidate, "path", "")) != str(package)
                or getattr(candidate, "portable", False)
                or isolation.in_process_import_refusal("Mastermind native consumer", source="user") is not None
                or originals["_runs_in_plugin_host"](candidate)
                or type(getattr(manager, "_predeclared_modules", None)) is not dict
                or CONSUMER_PLUGIN_NAME in manager._predeclared_modules):
            raise RuntimeRefusal("NATIVE_CONSUMER_HELD_IMPORT_UNAVAILABLE")
        package_check()

    def policy_module_name(candidate):
        if not reserved(candidate):
            return originals["_policy_module_name"](candidate)
        require_load(candidate)
        # The original registry policy lease must name the module that really
        # owns callbacks; a synthetic alias would fail to cover the held module.
        return _HELD_CONSUMER_MODULE

    def directory_module(candidate, *, module_name=None):
        if not reserved(candidate):
            return originals["_load_directory_module"](candidate, module_name=module_name)
        require_load(candidate)
        if module_name != _HELD_CONSUMER_MODULE:
            raise RuntimeRefusal("NATIVE_CONSUMER_HELD_IMPORT_UNAVAILABLE")
        module = importlib.import_module(_HELD_CONSUMER_MODULE)
        if Path(module.__file__) != package / "__init__.py":
            raise RuntimeRefusal("NATIVE_CONSUMER_PLUGIN_PACKAGE_MISMATCH")
        require_load(candidate)
        return module

    if slot.import_current is not None:
        raise RuntimeRefusal("NATIVE_CONSUMER_ORIGINAL_IMPORT_RETAINED")
    manager._policy_module_name, manager._load_directory_module = policy_module_name, directory_module
    slot.import_current = current
    return require_load


def _install_consumer_seam(launch, vendor: Path, role_home: Path, *, gateway=True):
    """Fence the exact held package before discovery, then use native events."""
    import asyncio
    from integrations.hermes_harness.native_executive_consumer import (
        CONSUMER_PLUGIN_NAME, CONSUMER_PLUGIN_SOURCE, CONSUMER_SLOT_ATTRIBUTE,
        ConsumerSlot, held_plugin_package_digest, install_consumer_slot,
        publication_from_document, selected_child_publication, validate_consumer_publication)
    raw = launch.recipe.get("executive_consumer")
    if raw is None:
        return None
    document = validate_consumer_publication(raw)
    publication = publication_from_document(document)
    owner = launch.owner.root.name
    package = launch.owner.root / "integrations/hermes_harness" / CONSUMER_PLUGIN_NAME

    def package_check():
        launch.check()
        if (publication_from_document(launch.recipe["executive_consumer"]) != publication
                or held_plugin_package_digest(launch.owner) != publication.plugin.digest):
            raise RuntimeRefusal("NATIVE_CONSUMER_PLUGIN_PACKAGE_MISMATCH")
        launch.check()
        return True

    # This occurs before native discovery and before any plugin module import.
    package_check()
    from hermes_cli.plugins import get_plugin_manager
    from hermes_cli.plugins_manifest import PluginManifest
    from hermes_cli.profiles import get_active_profile_name
    manager = get_plugin_manager()
    if str(manager.scope_key) != str(role_home):
        raise RuntimeRefusal("NATIVE_CONSUMER_PROFILE_SCOPE_MISMATCH")
    slot = install_consumer_slot(manager, ConsumerSlot(
        owner=owner, profile_id=get_active_profile_name(), source=CONSUMER_PLUGIN_SOURCE,
        plugin_id=CONSUMER_PLUGIN_NAME, publication=publication))
    from common.coo_discovery_contract import TOOLS as discovery_tools
    provided = [] if selected_child_publication(publication) is None else ["mmx_delegate"]
    if getattr(publication, "discovery", False):
        provided.extend(discovery_tools)
    manifest = PluginManifest(
        name=CONSUMER_PLUGIN_NAME, version="1.0.0", source=CONSUMER_PLUGIN_SOURCE,
        path=str(package), provides_tools=provided, key=CONSUMER_PLUGIN_NAME)
    if slot.package_path is not None:
        raise RuntimeRefusal("NATIVE_CONSUMER_LOADER_ALREADY_BOUND")
    slot.package_path, slot.package_check = str(package), package_check
    original_load = manager._load_plugin
    require_held_import = _install_held_consumer_import(vendor, manager, slot, manifest, package, package_check)

    def load_plugin(candidate):
        if (getattr(candidate, "name", None) != CONSUMER_PLUGIN_NAME
                and getattr(candidate, "key", None) != CONSUMER_PLUGIN_NAME):
            return original_load(candidate)
        package_check()
        if (getattr(manager, CONSUMER_SLOT_ATTRIBUTE, None) is not slot
                or manager.scope_key != slot.scope
                or getattr(candidate, "source", None) != CONSUMER_PLUGIN_SOURCE
                or str(getattr(candidate, "path", "")) != str(package)):
            raise RuntimeRefusal("NATIVE_CONSUMER_PLUGIN_PACKAGE_MISMATCH")
        # Native census/unbound discovery cannot import a role-owned substitute
        # or start registration. Only the held qualified load gets one admission.
        with slot._lock:
            if slot.delegate_binding is None and not (
                    slot.memory_factory is not None and slot.memory_factory.loader_ready()):
                return None
            if (candidate is not manifest or not slot.load_attempted
                    or slot.loader_entered or slot.load_outcome != "LOAD_PENDING"):
                raise RuntimeRefusal("NATIVE_CONSUMER_ORIGINAL_LOAD_RETAINED")
            slot.loader_entered = True
        require_held_import(candidate)
        package_check()
        return original_load(candidate)

    manager._load_plugin = load_plugin
    import contextvars
    profile_context = contextvars.copy_context()
    if not gateway:
        return None

    def transition(runner):
        if slot.load_attempted:
            return
        if any(task is not None and not task.done()
               for task in (slot.qualification_task, slot.qualification_worker)):
            return
        from .native_session_control import read_enrolled_session
        observed = read_enrolled_session(
            runner, role_home, owner, publication.session.request_id,
            publication.session.principal_id, role=publication.session.role)
        target = observed["target"] or {}
        key = (observed["status"], target.get("session_id"), target.get("instance_id"),
               target.get("authority_epoch"), observed["route"])
        if key == slot.qualification_key:
            return
        slot.qualification_key = key
        if observed["status"] != "ENROLLED":
            slot.qualification_outcome = "UNBOUND"
            return
        loop = asyncio.get_running_loop()
        slot.qualification_outcome = "QUALIFYING"
        slot.qualification_task = loop.create_task(_qualify_consumer(
            runner, document, role_home, launch, manager=manager, slot=slot,
            manifest=manifest, package_check=package_check), context=profile_context.copy())
        def observe(completed):
            try:
                completed.result()
            except BaseException:
                if slot.qualification_worker is None:
                    slot.qualification_outcome = "UNBOUND"
        slot.qualification_task.add_done_callback(observe)

    runtime = _vendor_module("gateway.run_runtime", vendor)
    original_ready = runtime.publish_gateway_runtime_ready
    def publish_gateway_runtime_ready(runner):
        result = original_ready(runner)
        try:
            transition(runner)
        except Exception:
            # Native readiness and enrollment retain their own actual result.
            slot.qualification_outcome = "UNBOUND"
        return result
    runtime.publish_gateway_runtime_ready = publish_gateway_runtime_ready
    return transition



def run(launch, argv: list[str]) -> int:
    """Enter native main only through the actual held release capability."""
    from .profile import load_profile
    from .supervisor import expected_disabled_mcp

    role = launch.row["role"]
    state = Path(launch.row["state_dir"])
    profile = load_profile(state / "current/profile.yaml")
    launch.qualify(profile, state / "current/bin/hermes")
    # Re-establish the actual role boundary in this fresh process before any
    # native or provider import. An out-of-service direct invocation refuses.
    from .system_service import assert_root_service_cgroup, assert_role_network_profile
    from .role_isolation import assert_role_credential_isolation
    from .tcp_sandbox import enforce_role_tcp_ports
    assert_root_service_cgroup(role)
    assert_role_network_profile(profile)
    assert_role_credential_isolation(profile)
    enforce_role_tcp_ports(profile)
    consumer_document = launch.recipe.get("executive_consumer")
    if consumer_document is None:
        expected_disabled_mcp(profile)
    else:
        expected_disabled_mcp(profile, consumer_document)
    _selection(role, profile.gateway_host, profile.backend_port)
    gateway_args = ["-p", role, "gateway", "run", "--external-supervisor"]
    tools_args = ["-p", role, "tools", "list", "--platform", "cli"]
    if argv not in (gateway_args, tools_args):
        raise RuntimeRefusal("NATIVE_ENTRY_COMMAND_REFUSED")
    is_gateway = argv == gateway_args
    home = profile.hermes_home.resolve(strict=True)
    if Path(os.environ.get("HERMES_HOME", "")).resolve() != home:
        raise RuntimeRefusal("NATIVE_PROFILE_HOME_MISMATCH")
    vendor = Path(launch.recipe["vendor_root"])
    if any(os.environ.get(key) != value for key, value in native_git_environment(vendor).items()):
        raise RuntimeRefusal("NATIVE_GIT_SELECTION_MISMATCH")
    prepare_vendor(vendor)
    # Pinned hermes_bootstrap patches this loaded module directly; otherwise
    # it inserts its own import finder ahead of the held source/YAML owners.
    # Load only from the already verified dependency closure, after role
    # isolation, preserving the native socket patch and exact finder order.
    importlib.import_module("urllib3.util.connection")
    launch.check()
    # Preserve the real recognized launcher and command before the native
    # module applies its profile selector at import time.
    sys.argv[:] = [str(launch.launcher), *argv]
    _bind_consumer_provider_imports(launch, vendor)
    native_main = _vendor_module("hermes_cli.main", vendor)
    constants = _vendor_module("hermes_constants", vendor)
    role_home = home / "profiles" / role
    if (native_main.explicit_cli_profile() != role
            or constants.get_process_hermes_home().resolve() != role_home):
        raise RuntimeRefusal("NATIVE_PROFILE_HOME_MISMATCH")
    consumer_transition = _install_consumer_seam(
        launch, vendor, role_home, gateway=is_gateway)
    if is_gateway:
        # The one held-release owner identity of this process. It is bound
        # exactly once and is what the plugin loader checks the consumer slot
        # against.
        from .native_session_control import install_runtime_owner
        install_runtime_owner(launch.owner.root.name)
        from .native_request_observation import install_request_observation
        request_observation = install_request_observation(launch, vendor, role_home, role)
        from .native_agentos_memory import install_native_agentos_memory
        install_native_agentos_memory(launch, vendor, role_home, request_observation)
        api = _vendor_module("gateway.run_api", vendor)
        bind_native_api(api, vendor=vendor, role_home=role_home, role=role,
                        host=profile.gateway_host, port=profile.backend_port,
                        implementation_sha=launch.owner.root.name,
                        session_enrollment=launch.recipe.get("session_enrollment"),
                        consumer_transition=consumer_transition,
                        request_observation=request_observation)
    launch.check()
    result = native_main.main()
    return result if type(result) is int else 0


def native_ready(*, vendor: Path, home: Path, host: str, port: int, pid: int) -> bool:
    """One authenticated native control observation; never start an owner."""
    try:
        prepare_vendor(vendor)
        discovery = _vendor_module("hermes_cli.gateway_runtime_discovery", vendor)
        runtime = _vendor_module("hermes_cli.gateway_runtime", vendor)
        payload = discovery.query_identify(home, timeout=0.25)
        observed = runtime._endpoint(payload, home)
        endpoint = observed.endpoint
        return (type(payload) is dict and type(payload.get("pid")) is int
                and payload["pid"] == pid and payload.get("hermes_home") == str(home)
                and observed.state == "ready" and endpoint is not None
                and endpoint.profile_id == str(home)
                and endpoint.code_sha == PINNED_UPSTREAM_SHA
                and type(endpoint.authority_epoch) is int and endpoint.authority_epoch > 0
                and bool(endpoint.instance_id) and endpoint.runtime_protocol == 1
                and endpoint.supervisor == "external"
                and endpoint.api_origin == f"http://{host}:{port}"
                and _CAPABILITIES <= endpoint.capabilities)
    except (OSError, ValueError, TypeError, AttributeError, RuntimeRefusal):
        return False
