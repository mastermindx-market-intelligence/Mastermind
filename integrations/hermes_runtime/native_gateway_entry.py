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
                    session_enrollment: dict | None = None) -> None:
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
        install_private_control(runner, role_home, role,
                                implementation_sha=implementation_sha,
                                session_enrollment=session_enrollment)
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


def _consumer_trust_gate(publication):
    """The incumbent MCP trust gate, consulted before a model-facing call."""
    from integrations.hermes_delegate.policy import TOOL_NAME

    def gate() -> str | None:
        try:
            from tools.mcp_tool_handlers import _trust_gate_check
        except Exception:
            return "NATIVE_CONSUMER_TRUST_GATE_UNAVAILABLE"
        try:
            return _trust_gate_check(publication.mcp.server, TOOL_NAME, [], {})
        except Exception:
            return "NATIVE_CONSUMER_TRUST_GATE_UNAVAILABLE"

    return gate


def _qualify_consumer(runner, document, role_home: Path, launch) -> None:
    """Qualify the ready process, the target and the authenticated connection.

    Nothing here is fabricated. The enrollment is read through the incumbent
    bounded reader, the MCP owner is the live same-profile connection, and the
    mandate and the one harmless status read are the real calls. Any refusal
    leaves the consumer unbound and the extension hold untouched.
    """
    from integrations.hermes_harness.native_executive_consumer import (
        capture_native_mcp_owner,
        install_native_consumer,
        publication_from_document,
    )
    from .native_session_control import current_runtime_owner, read_enrolled_session

    publication = publication_from_document(document)
    owner = current_runtime_owner()
    if not owner:
        return
    # The ACTUAL per-profile plugin manager of this role, and the profile the
    # upstream owner resolves for it.
    from hermes_cli.plugins import get_plugin_manager
    from hermes_cli.profiles import get_active_profile_name
    manager = get_plugin_manager()
    profile_id = get_active_profile_name()
    # The real discovery sweep. It proves the unbound load: without a
    # qualified startup the plugin registers nothing.
    manager.discover_and_load()
    # The original enrolled native session. It is never created here.
    principal = publication.session.principal_id
    enrollment = read_enrolled_session(runner, role_home, launch.owner.root.name,
                                       publication.session.request_id, principal)
    if enrollment["status"] != "ENROLLED":
        return
    target = enrollment["target"]
    if target["profile_id"] != str(role_home) or target["principal_id"] != principal:
        return
    server, session, loop = capture_native_mcp_owner(publication)
    install_native_consumer(
        manager=manager, publication=publication, owner=owner, profile_id=profile_id,
        session_id=target["session_id"], instance_id=target["instance_id"],
        authority_epoch=target["authority_epoch"], route=enrollment["route"],
        server=server, session=session, loop=loop,
        trust_gate=_consumer_trust_gate(publication))


def _install_consumer_seam(launch, vendor: Path, role_home: Path) -> None:
    """Bind the optional native consumer to the existing genuine-ready seam.

    The publication is optional. Without a qualified publication nothing is
    installed, no plugin is loaded, and the default stays disarmed. The seam
    runs after the upstream owner published the genuine ready state; it never
    fabricates readiness and it never qualifies the enrolled session before
    the gateway is ready.
    """
    publication = launch.recipe.get("executive_consumer")
    if publication is None:
        return
    from integrations.hermes_harness.native_executive_consumer import (
        validate_consumer_publication,
    )
    document = validate_consumer_publication(publication)
    runtime = _vendor_module("gateway.run_runtime", vendor)
    original = runtime.publish_gateway_runtime_ready

    def publish_gateway_runtime_ready(runner):
        result = original(runner)
        try:
            _qualify_consumer(runner, document, role_home, launch)
        except Exception:
            # An unqualified consumer never takes the gateway down, never
            # clears the extension hold and never registers a tool.
            pass
        return result

    runtime.publish_gateway_runtime_ready = publish_gateway_runtime_ready


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
    expected_disabled_mcp(profile, launch.recipe.get("executive_consumer"))
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
    native_main = _vendor_module("hermes_cli.main", vendor)
    constants = _vendor_module("hermes_constants", vendor)
    role_home = home / "profiles" / role
    if (native_main.explicit_cli_profile() != role
            or constants.get_process_hermes_home().resolve() != role_home):
        raise RuntimeRefusal("NATIVE_PROFILE_HOME_MISMATCH")
    if is_gateway:
        # The one held-release owner identity of this process. It is bound
        # exactly once and is what the plugin loader checks the consumer slot
        # against.
        from .native_session_control import install_runtime_owner
        install_runtime_owner(launch.owner.root.name)
        api = _vendor_module("gateway.run_api", vendor)
        bind_native_api(api, vendor=vendor, role_home=role_home, role=role,
                        host=profile.gateway_host, port=profile.backend_port,
                        implementation_sha=launch.owner.root.name,
                        session_enrollment=launch.recipe.get("session_enrollment"))
        _install_consumer_seam(launch, vendor, role_home)
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
