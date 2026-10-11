"""Opt-in host routing within the existing guarded Paper stdio service.

Routes are immutable installation projections of existing fleet host/SSH bindings,
not a host registry or an authorization source. No listener, queue, persistent
session, credential copy, retry, implicit placement, or automatic failover exists.
Only a configured host reference crosses the public MCP interface. SSH launches
that host's verified direct_service serve command; it never starts a second tunnel.
"""

import asyncio
from contextlib import asynccontextmanager
import copy
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import stat
from datetime import timedelta

SCHEMA = "mastermind.paper_host_routes.v1"
HOST = re.compile(r"host-[0-9a-f]{64}")
HEX64 = re.compile(r"[0-9a-f]{64}")
MAX_ROUTES = 8
MAX_REQUEST = 512 * 1024
MAX_RESPONSE = 24 * 1024 * 1024
TOOL_NAMES = frozenset({"paper_inspect", "paper_catalog", "paper_read", "paper_prepare", "paper_edit"})
MODIFYING = frozenset({"paper_prepare", "paper_edit"})
TAILNETS = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))


class RouteError(ValueError):
    """Secret-free refusal code, never a raw SSH or SDK exception."""


def _require(ok, code="HOST_ROUTES_INVALID"):
    if not ok: raise RouteError(code)


def _scope(value):
    keys = {"schema", "host_ref", "service_ref", "runtime_revision", "bridge_sha256"}
    _require(type(value) is dict and set(value) == keys)
    _require(value["schema"] == "mastermind.paper_execution_binding.v1")
    for key, pattern in (("host_ref", HOST), ("service_ref", HEX64),
                         ("runtime_revision", re.compile(r"[0-9a-f]{40}")), ("bridge_sha256", HEX64)):
        _require(type(value[key]) is str and pattern.fullmatch(value[key]) is not None)
    return copy.deepcopy(value)


def _path(value):
    # These operator-supplied paths are never public tool arguments. A restricted
    # alphabet plus shlex quoting prevents remote-shell interpolation as defense in depth.
    _require(type(value) is str and len(value) <= 1024 and
             re.fullmatch(r"/[A-Za-z0-9_./ -]+", value) is not None)
    _require(all(part not in {".", ".."} for part in value.split("/")))
    _require(str(Path(value)) == value and value != "/")
    return value


def _tailnet_address(value):
    _require(type(value) is str and len(value) <= 253)
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        _require(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*\.ts\.net", value) is not None)
    else:
        _require(any(address in network for network in TAILNETS if address.version == network.version))


def validate_routes(value, local_host_ref):
    _require(type(local_host_ref) is str and HOST.fullmatch(local_host_ref) is not None)
    _require(type(value) is dict and set(value) == {"schema", "routes"} and value["schema"] == SCHEMA)
    routes = value["routes"]
    _require(type(routes) is list and 1 <= len(routes) <= MAX_ROUTES)
    seen = {local_host_ref}
    for route in routes:
        _require(type(route) is dict and set(route) == {"host_ref", "label", "execution_binding", "tool_schema_sha256", "ssh"})
        ref = route["host_ref"]
        _require(type(ref) is str and HOST.fullmatch(ref) is not None and ref not in seen)
        seen.add(ref)
        _require(type(route["label"]) is str and 1 <= len(route["label"]) <= 64 and
                 all(32 <= ord(char) < 127 for char in route["label"]))
        _require(_scope(route["execution_binding"])["host_ref"] == ref)
        _require(type(route["tool_schema_sha256"]) is str and HEX64.fullmatch(route["tool_schema_sha256"]) is not None)
        ssh = route["ssh"]
        keys = {"hostname", "username", "port", "identity_file", "known_hosts_file", "known_hosts_sha256", "python_path", "runtime_root"}
        _require(type(ssh) is dict and set(ssh) == keys)
        _tailnet_address(ssh["hostname"])
        _require(type(ssh["username"]) is str and re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", ssh["username"]) is not None)
        _require(type(ssh["port"]) is int and 1 <= ssh["port"] <= 65535)
        for key in ("identity_file", "known_hosts_file", "python_path", "runtime_root"): _path(ssh[key])
        _require(type(ssh["known_hosts_sha256"]) is str and HEX64.fullmatch(ssh["known_hosts_sha256"]) is not None)
    try:
        raw = json.dumps(value, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        raise RouteError("HOST_ROUTES_INVALID") from None
    _require(len(raw.encode()) <= 32768)
    return copy.deepcopy(value)


def _private_file(path, expected_sha256=None):
    path = Path(path)
    try:
        # No symlink in a local binding path, including its parent directories.
        for component in (path, *path.parents):
            _require(not stat.S_ISLNK(component.lstat().st_mode), "SSH_BINDING_UNSAFE")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            _require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
                     and before.st_nlink == 1 and not before.st_mode & 0o077, "SSH_BINDING_UNSAFE")
            # Private key bytes are never read here; SSH alone consumes that existing key.
            if expected_sha256 is not None:
                _require(0 < before.st_size <= 1024 * 1024, "SSH_BINDING_UNSAFE")
                data = bytearray()
                while len(data) <= 1024 * 1024:
                    chunk = os.read(fd, 65536)
                    if not chunk: break
                    data.extend(chunk)
                after = os.fstat(fd)
                identity = lambda row: (row.st_dev, row.st_ino, row.st_mode, row.st_size, row.st_mtime_ns, row.st_ctime_ns)
                _require(identity(before) == identity(after) and len(data) == before.st_size,
                         "SSH_BINDING_CHANGED")
                _require(hashlib.sha256(data).hexdigest() == expected_sha256, "SSH_BINDING_CHANGED")
        finally:
            os.close(fd)
    except RouteError:
        raise
    except (OSError, ValueError):
        raise RouteError("SSH_BINDING_UNAVAILABLE") from None


def ssh_command(route, *, verify_files=True):
    ssh = route["ssh"]
    if verify_files:
        _private_file(ssh["identity_file"])
        _private_file(ssh["known_hosts_file"], ssh["known_hosts_sha256"])
    options = ["BatchMode=yes", "StrictHostKeyChecking=yes", "IdentitiesOnly=yes",
               "IdentityAgent=none", "ForwardAgent=no", "ForwardX11=no",
               "ClearAllForwardings=yes", "PermitLocalCommand=no", "RequestTTY=no",
               "ControlMaster=no", "ControlPath=none", "ProxyCommand=none", "ProxyJump=none",
               "CanonicalizeHostname=no", "UpdateHostKeys=no", "ConnectionAttempts=1",
               "ConnectTimeout=5", "NumberOfPasswordPrompts=0", "PasswordAuthentication=no",
               "KbdInteractiveAuthentication=no", "GlobalKnownHostsFile=/dev/null",
               "UserKnownHostsFile=" + json.dumps(ssh["known_hosts_file"])]
    remote = shlex.join([ssh["python_path"], "-I", ssh["runtime_root"] + "/runtime/direct_service.py",
                        "serve", "--root", ssh["runtime_root"], "--host-ref", route["host_ref"]])
    argv = ["/usr/bin/ssh", "-T", "-F", "/dev/null"]
    for option in options: argv.extend(["-o", option])
    return argv + ["-i", ssh["identity_file"], "-p", str(ssh["port"]),
                   "-l", ssh["username"], "--", ssh["hostname"], remote]


@asynccontextmanager
async def ssh_session(route):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    argv = ssh_command(route)
    parameters = StdioServerParameters(command=argv[0], args=argv[1:],
                                       env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home())})
    # Diagnostics are typed, not arbitrary stderr that may contain local paths or sensitive data.
    with open(os.devnull, "w") as errors:
        async with stdio_client(parameters, errlog=errors) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=30)) as client:
                yield client


def schema_digest(tools):
    return hashlib.sha256((json.dumps(tools.model_dump(mode="json"), indent=2,
                                      sort_keys=True, allow_nan=False) + "\n").encode()).hexdigest()


def _json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result, "BACKEND_RECEIPT_INVALID")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(RouteError("BACKEND_RECEIPT_INVALID")))


def checked_result(result, route, *, name=None, arguments=None):
    try:
        _require(len(result.model_dump_json().encode()) <= MAX_RESPONSE, "BACKEND_RESULT_TOO_LARGE")
        _require(result.content and result.content[0].type == "text", "BACKEND_RECEIPT_INVALID")
        payload = _json(result.content[0].text)
        _require(type(payload) is dict and payload.get("execution_binding") == route["execution_binding"],
                 "BACKEND_IDENTITY_MISMATCH")
        if name in MODIFYING and payload.get("state") in {
                "APPLIED_RESPONSE_OBSERVED", "EFFECT_UNKNOWN", "PAPER_READY", "PAPER_READY_READ_ONLY"}:
            _require(type(arguments) is dict and payload.get("operation_id") == arguments.get("operation_id")
                     and isinstance(payload.get("operation_id"), str), "BACKEND_OPERATION_MISMATCH")
        if name == "paper_prepare" and payload.get("state") in {"PAPER_READY", "PAPER_READY_READ_ONLY"}:
            _require(payload.get("file_id") == arguments.get("file_id"), "BACKEND_FILE_MISMATCH")
    except RouteError:
        raise
    except (AttributeError, TypeError, ValueError, RecursionError):
        raise RouteError("BACKEND_RECEIPT_INVALID") from None
    return payload


def typed_result(value, *, error=False):
    from mcp.types import CallToolResult, TextContent
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(value))], isError=error)


class HostRouter:
    def __init__(self, routes, local_binding, local_call, *, allow_write=False, allow_prepare=False,
                 connect=ssh_session):
        self.local_binding = _scope(local_binding)
        self.routes = {item["host_ref"]: item for item in
                       validate_routes(routes, self.local_binding["host_ref"])["routes"]}
        self.local_call, self.connect = local_call, connect
        self.allowed = {"paper_inspect", "paper_catalog", "paper_read"}
        if allow_write: self.allowed.add("paper_edit")
        if allow_prepare: self.allowed.add("paper_prepare")

    def hosts(self):
        return typed_result({"state": "CONFIGURED_NOT_PROBED", "automatic_failover": False,
            "default_host_ref": self.local_binding["host_ref"],
            "hosts": [{"host_ref": self.local_binding["host_ref"], "label": "Local Paper host",
                       "transport": "local", "readiness": "NOT_PROBED"}] +
                     [{"host_ref": ref, "label": route["label"], "transport": "ssh",
                       "readiness": "NOT_PROBED"} for ref, route in sorted(self.routes.items())]})

    async def call(self, name, arguments, host_ref=None):
        selected = self.local_binding["host_ref"] if host_ref is None else host_ref
        dispatched, observed, route = False, None, None
        operation_id = arguments.get("operation_id") if type(arguments) is dict else None
        try:
            _require(name in self.allowed, "TOOL_NOT_ALLOWED")
            _require(type(arguments) is dict and len(json.dumps(arguments, allow_nan=False).encode()) <= MAX_REQUEST,
                     "INVALID_ARGUMENTS")
            _require(type(selected) is str and HOST.fullmatch(selected) is not None, "HOST_NOT_CONFIGURED")
            if selected == self.local_binding["host_ref"]:
                route = {"host_ref": selected, "execution_binding": self.local_binding}
                # The local backend may have dispatched an edit before it raises.
                # Conservative classification is required on a missing reply.
                dispatched = True
                result = await self.local_call(name, copy.deepcopy(arguments))
                checked_result(result, route, name=name, arguments=arguments)
                observed = result
                return observed
            _require(selected in self.routes, "HOST_NOT_CONFIGURED")
            route = self.routes[selected]
            from anyio import fail_after
            with fail_after(60):
                async with self.connect(copy.deepcopy(route)) as client:
                    hello = await client.initialize()
                    _require(hello.serverInfo.name == "mastermind-paper", "BACKEND_SERVER_MISMATCH")
                    tools = await client.list_tools()
                    _require(schema_digest(tools) == route["tool_schema_sha256"], "BACKEND_SCHEMA_CHANGED")
                    _require(name in {tool.name for tool in tools.tools}, "TOOL_NOT_AVAILABLE")
                    if name != "paper_inspect":
                        inspection = await client.call_tool("paper_inspect", {})
                        payload = checked_result(inspection, route)
                        if name in MODIFYING:
                            _require(not inspection.isError and payload.get("state") == "CONNECTED"
                                     and (payload.get("document") or {}).get("write_binding_ready") is True,
                                     "BACKEND_NOT_READY")
                    # Set before the await: a broken reply never licenses another send.
                    dispatched = True
                    result = await client.call_tool(name, copy.deepcopy(arguments))
                    checked_result(result, route, name=name, arguments=arguments)
                    observed = result
            return observed
        except (Exception, asyncio.CancelledError) as exc:
            # A valid observed receipt survives a later transport-cleanup failure.
            if observed is not None: return observed
            unknown = dispatched and name in MODIFYING
            code = str(exc) if isinstance(exc, RouteError) else "HOST_TRANSPORT_FAILED"
            value = {"state": "EFFECT_UNKNOWN" if unknown else code,
                     "reason": "REMOTE_RESPONSE_NOT_VERIFIED" if unknown else code,
                     "effect_state": "EFFECT_UNKNOWN" if unknown else "EFFECT_NONE",
                     "retry_allowed": False, "automatic_failover": False,
                     "operation_id": operation_id if isinstance(operation_id, str) and len(operation_id) <= 120 else None}
            if route is not None:
                value["requested_host_ref"] = route["host_ref"]
                value["expected_execution_binding"] = copy.deepcopy(route["execution_binding"])
            return typed_result(value, error=True)


def register_tools(server, router):
    from mcp.types import ToolAnnotations, CallToolResult
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

    @server.tool(annotations=read)
    async def paper_hosts() -> CallToolResult:
        """List configured Paper hosts, not live readiness or new access grants. No host is contacted."""
        return router.hosts()

    @server.tool(annotations=read)
    async def paper_inspect(host_ref: str | None = None) -> CallToolResult:
        """Inspect one configured host. Omit host_ref only for the fixed local default; never automatic failover."""
        return await router.call("paper_inspect", {}, host_ref)

    @server.tool(annotations=read)
    async def paper_catalog(host_ref: str | None = None) -> CallToolResult:
        """Read the selected host's guarded tool catalog. Use a host_ref returned by paper_hosts."""
        return await router.call("paper_catalog", {}, host_ref)

    @server.tool(annotations=read)
    async def paper_read(tool: str, arguments: dict, expected_snapshot: str | None = None,
                         host_ref: str | None = None) -> CallToolResult:
        """Read the exact Paper target on one configured host. No URL, command or credential selection."""
        return await router.call("paper_read", {"tool": tool, "arguments": arguments,
                                "expected_snapshot": expected_snapshot}, host_ref)

    if "paper_prepare" in router.allowed:
        @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                                idempotentHint=True, openWorldHint=False))
        async def paper_prepare(file_id: str, expected_snapshot: str, operation_id: str,
                                host_ref: str | None = None) -> CallToolResult:
            """Bind an existing file on the selected host without changing UI focus. Keep the same host for its edit."""
            return await router.call("paper_prepare", {"file_id": file_id, "expected_snapshot": expected_snapshot,
                                    "operation_id": operation_id}, host_ref)

    if "paper_edit" in router.allowed:
        @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                                                idempotentHint=False, openWorldHint=True))
        async def paper_edit(tool: str, arguments: dict, expected_snapshot: str, operation_id: str,
                             host_ref: str | None = None) -> CallToolResult:
            """Edit one approved target with that host's fresh snapshot. Never replay or change hosts on EFFECT_UNKNOWN."""
            return await router.call("paper_edit", {"tool": tool, "arguments": arguments,
                                    "expected_snapshot": expected_snapshot, "operation_id": operation_id}, host_ref)
