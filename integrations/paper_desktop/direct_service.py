"""Private, inert Business deployment of the existing guarded Paper stdio server.

This is an installation/launchd adapter, not another Paper gateway, permission,
retry or lifecycle owner. Stage and probe need no credentials. Bind and activate
only during the separate attended workspace/tunnel enrollment. No command here
creates a tunnel, changes a ChatGPT account, loads launchd, or edits Paper.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import plistlib
import re
import shlex
import stat
import subprocess
import sys

SCHEMA_V2 = "mastermind.paper_direct_install.v2"
SCHEMA_V3 = "mastermind.paper_direct_install.v3"
SCHEMA_V4 = "mastermind.paper_direct_install.v4"
SCHEMA = SCHEMA_V2  # legacy/default when no seat_id is supplied
BINDING_SCHEMA_V1 = "mastermind.paper_direct_binding.v1"
BINDING_SCHEMA_V2 = "mastermind.paper_direct_binding.v2"
BINDING_SCHEMA_V3 = "mastermind.paper_direct_binding.v3"
BINDING_SCHEMA = BINDING_SCHEMA_V1
LABEL = "com.mastermind.paper-direct.business"
SDK_VERSION = "1.30.0"
SOURCE_FILES = ("bridge.py", "prepare.py", "mcp_server.py", "requirements-mcp.txt", "direct_service.py")
STATIC_FILES = {"ENROLLMENT.md", "app-definition.json", f"service/{LABEL}.plist"}
EXPECTED_FILES = {f"runtime/{name}" for name in SOURCE_FILES} | STATIC_FILES
PATH_VALUE = "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin"
TUNNEL_RE = re.compile(r"tunnel_[A-Za-z0-9_-]{8,120}")
SEAT_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")
WORKSPACE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{2,150}")
ORG_RE = re.compile(r"org-[A-Za-z0-9_-]{8,150}")


class Refusal(RuntimeError):
    """A fixed, secret-free operator error. No upstream payload is interpolated."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def clean_env(env: dict) -> dict:
    # tunnel-client flags > environment > profile. Never inherit another seat's
    # tunnel/key/MCP command, a Python injection path, or an ambient proxy.
    out = {key: env[key] for key in ("HOME", "USER", "LOGNAME", "TMPDIR") if key in env}
    out["PATH"] = PATH_VALUE
    return out


def _path(value: Path) -> Path:
    value = Path(value).expanduser()
    if ".." in value.parts:
        raise Refusal("PARENT_TRAVERSAL")
    value = value.absolute()
    current = Path(value.anchor)
    for part in value.parts[1:]:
        current /= part
        if current.is_symlink():
            raise Refusal("SYMLINK_PATH")
    return value


def _private_dir(path: Path, *, create: bool = False) -> None:
    _path(path)
    if create and not path.exists():
        if not path.parent.exists():
            _private_dir(path.parent, create=True)
        path.mkdir(mode=0o700)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise Refusal("PRIVATE_DIRECTORY_REQUIRED")


def _read(path: Path, *, limit: int = 2 * 1024 * 1024) -> bytes:
    _path(path)
    # Inspect the opened descriptor before wrapping or reading it. A FIFO must
    # not stall setup waiting for a writer before the regular-file check runs.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or info.st_mode & 0o077):
            raise Refusal("PRIVATE_FILE_REQUIRED")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise Refusal("FILE_TOO_LARGE")
        return data
    finally:
        os.close(fd)


def _write(path: Path, data: bytes) -> None:
    _private_dir(path.parent, create=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _json(path: Path) -> dict:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise Refusal("DUPLICATE_JSON_KEY")
            value[key] = item
        return value
    try:
        value = json.loads(_read(path), object_pairs_hook=unique)
    except (ValueError, UnicodeError) as exc:
        raise Refusal("INVALID_MANIFEST") from exc
    if not isinstance(value, dict):
        raise Refusal("INVALID_MANIFEST")
    return value


def _binary(path: Path) -> dict:
    path = _path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid not in {0, os.getuid()}
                or info.st_mode & 0o022 or not os.access(path, os.X_OK)):
            raise Refusal("EXECUTABLE_REQUIRED")
        h = hashlib.sha256()
        with os.fdopen(fd, "rb", closefd=False) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(chunk)
    finally:
        os.close(fd)
    return {"path": str(path), "sha256": h.hexdigest()}


def sdk_distributions(python: Path | None = None) -> dict:
    """Capture versions from the selected isolated interpreter, not operator pip."""
    command = [str(python or sys.executable), "-I", "-c",
               "import importlib.metadata as m,json; "
               "print(json.dumps({d.metadata['Name'].lower().replace('_','-'):d.version "
               "for d in m.distributions()},sort_keys=True))"]
    result = subprocess.run(command, env=clean_env(dict(os.environ)), capture_output=True,
                            timeout=20, check=False)
    if result.returncode or len(result.stdout) > 256 * 1024:
        raise Refusal("SDK_INVENTORY_UNAVAILABLE")
    try:
        value = json.loads(result.stdout)
    except ValueError as exc:
        raise Refusal("SDK_INVENTORY_INVALID") from exc
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise Refusal("SDK_INVENTORY_INVALID")
    return value


def verify_sdk(root: Path) -> None:
    receipt = verify(root)
    if sdk_distributions(Path(receipt["python"]["path"])) != receipt["sdk_distributions"]:
        raise Refusal("SDK_DEPENDENCIES_CHANGED")


def _seat_id(value: str) -> str:
    if not isinstance(value, str) or not SEAT_RE.fullmatch(value):
        raise Refusal("SEAT_ID_REQUIRED")
    return value


def _host_ref(value: str) -> str:
    if type(value) is not str or not re.fullmatch(r"host-[0-9a-f]{64}", value):
        raise Refusal("HOST_REFERENCE_REQUIRED")
    return value


def execution_binding(receipt: dict) -> dict | None:
    """Consume a configured fleet ref; create neither host identity nor authority.

    Deployment must reconcile this ref with the existing fleet owner. The service
    ref is a content-derived snapshot namespace, not a lease or replay token.
    Never put paths, credentials, or caller-selected destinations in the result.
    """
    if receipt.get("schema") != SCHEMA_V4:
        return None
    return {
        "schema": "mastermind.paper_execution_binding.v1",
        "host_ref": _host_ref(receipt.get("host_ref")),
        "service_ref": digest(_json_bytes({
            "root": receipt["root"], "seat_id": receipt["seat_id"],
            "source_revision": receipt["source_revision"], "files": receipt["files"]})),
        "runtime_revision": receipt["source_revision"],
        "bridge_sha256": receipt["files"]["runtime/bridge.py"],
    }


def service_label(receipt: dict) -> str:
    if receipt.get("schema") in {SCHEMA_V3, SCHEMA_V4}:
        return f"{LABEL}.{_seat_id(receipt.get('seat_id'))}"
    return LABEL


def service_file(receipt: dict) -> str:
    return f"service/{service_label(receipt)}.plist"


def expected_files(receipt: dict) -> set[str]:
    return {f"runtime/{name}" for name in SOURCE_FILES} | {"ENROLLMENT.md", "app-definition.json", service_file(receipt)}


def service_owner(receipt: dict) -> Path:
    base = Path.home() / ".local/state/mastermind-paper/direct-business"
    if receipt.get("schema") in {SCHEMA_V3, SCHEMA_V4}:
        return base / "seats" / _seat_id(receipt.get("seat_id"))
    return base


def _tools(write: bool, prepare: bool = False) -> list[str]:
    return sorted(["paper_catalog", "paper_inspect", "paper_read"]
                  + (["paper_edit"] if write else []) + (["paper_prepare"] if prepare else []))


def _command(root: Path, receipt: dict, action: str) -> list[str]:
    command = [receipt["python"]["path"], "-I", str(root / "runtime/direct_service.py"), action, "--root", str(root)]
    if receipt.get("schema") == SCHEMA_V4:
        command += ["--host-ref", _host_ref(receipt.get("host_ref"))]
    return command


def _plist(root: Path, receipt: dict) -> bytes:
    return plistlib.dumps({
        "Label": service_label(receipt),
        "ProgramArguments": _command(root, receipt, "launch"),
        "WorkingDirectory": str(root),
        "EnvironmentVariables": {"HOME": str(Path.home()), "PATH": PATH_VALUE},
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 30,
        "Umask": 0o077,
        "ProcessType": "Background",
        "StandardOutPath": str(root / "logs/tunnel.stdout.log"),
        "StandardErrorPath": str(root / "logs/tunnel.stderr.log"),
    }, sort_keys=True)


def _enrollment() -> bytes:
    return b"""# Mastermind Paper: Business enrollment (last, attended step)

STAGED_NOT_ENROLLED. No tunnel was created, bound or started by staging.
Seat-aware v3 bundles use one transport singleton and launchd label per ChatGPT seat while
all seats share bridge.py's per-OS-user Paper desktop mutex. This is not a second Paper plane.
The selected tool surface is recorded in INSTALLATION.json. Optional paper_prepare
binds one exact existing file through Paper's explicit `fileId` API, never a host helper,
URL, path, or raw open_file transition. Paper must already be running. A fresh active-context
snapshot and stable operation ID are required; prepare returns the exact target snapshot used
by the subsequent target-bound edit. Multiple admitted sessions/hosts may modify the same
fileId, including the same page. Coordinate by board/artboard/node target and re-read/re-plan
known overlap; the per-OS-user desktop mutex is a local call guard, not a document lease.

1. Verify the existing Chairman-created tunnel ID and exact Business workspace
   association in OpenAI's admin surface. Check for an existing Paper app/client.
   Reuse the existing tunnel; do not substitute another seat's tunnel or key.
2. Use a runtime key whose principal has Tunnels Read + Use. Never put an admin
   key in the daemon. A legacy/single-seat bundle may store it locally as
   secrets/runtime-key, private mode 0600. A seat-aware v3 binding may instead
   reference one existing owner-private runtime-key file with --runtime-key-file;
   the key stays in place and only its path is recorded. Do not paste keys into
   Git, logs, this document, command arguments, or a plugin archive.
3. Run bind --root BUNDLE --tunnel-id EXACT_ID. New seat-aware bundles do not invent
   a backend workspace ID that the local tunnel runtime does not use; if an exact workspace
   ID is independently known it may be recorded with --workspace-id. Legacy v2 bundles keep
   their historical workspace-ID requirement. Binding is local configuration, not access proof.
4. Run doctor --root BUNDLE. Review exact results; this contacts OpenAI and
   requires the runtime key. A successful doctor alone is not a working app.
5. After the canonical route decision and required release checks are accepted,
   install this bundle's service/com.mastermind.paper-direct.business.plist in
   the existing user LaunchAgents owner and bootstrap it exactly once. Never
   run both an unsupervised client and launchd for this logical service.
6. In the Business workspace, enable developer mode as owner/admin, add the
   private Mastermind Paper app, select Connection: Tunnel and the existing ID.
   No portable Plugin Creator tunnel-binding schema is asserted by this bundle.
7. A fresh ChatGPT session must discover exactly the configured tools, inspect
   the approved scratch file, read its catalog, perform ONE bounded edit with
   exact fileId/snapshot/operation ID, then reconcile/read/screenshot/JSX through
   the SAME app. Record actual confirmation behavior. Never replay an unknown
   effect. Compare representative behavior with Studio Direct without claiming
   to bypass safety or hiding writes behind read annotations.
8. Verify restart/reconnect and that Paper and health listeners remain loopback.
   Retire Studio Direct's primary Paper-Web designation only at accepted cutover.

Model Pro reasoning mode is not the personal Pro subscription. This build targets
Business; account association, login, confirmations and installation are separate
human/admin boundaries. Source tests and local stdio listing are not PROVEN_LIVE.
"""


def stage(destination: Path, *, python: Path, tunnel_client: Path,
          source_revision: str, allow_write: bool = False, allow_prepare: bool = False,
          seat_id: str | None = None, host_ref: str | None = None) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", source_revision):
        raise Refusal("SOURCE_REVISION_REQUIRED")
    if type(allow_write) is not bool or type(allow_prepare) is not bool:
        raise Refusal("WRITE_FLAG_REQUIRED")
    if seat_id is not None:
        seat_id = _seat_id(seat_id)
    if host_ref is not None:
        _host_ref(host_ref)
        if seat_id is None:
            raise Refusal("HOST_BINDING_REQUIRES_SEAT")
    root = _path(destination)
    if root.exists() or root.is_symlink():
        raise Refusal("DESTINATION_EXISTS")
    receipt = {
        "schema": SCHEMA_V4 if host_ref is not None else (SCHEMA_V3 if seat_id is not None else SCHEMA_V2),
        "state": "STAGED_NOT_ENROLLED", "root": str(root),
        "source_revision": source_revision, "target_plan": "Business",
        "allow_write": allow_write, "allow_prepare": allow_prepare,
        "tools": _tools(allow_write, allow_prepare),
        "python": _binary(python), "tunnel_client": _binary(tunnel_client),
        "sdk_required": f"mcp=={SDK_VERSION}", "sdk_distributions": sdk_distributions(python),
        "production_acceptance": False,
        "service_loaded": False, "account_modified": False,
    }
    if seat_id is not None:
        receipt["seat_id"] = seat_id
    if host_ref is not None:
        receipt["host_ref"] = host_ref
    source = Path(__file__).resolve().parent
    files = {f"runtime/{name}": (source / name).read_bytes() for name in SOURCE_FILES}
    files[service_file(receipt)] = _plist(root, receipt)
    files["ENROLLMENT.md"] = _enrollment()
    files["app-definition.json"] = _json_bytes({
        "name": "Mastermind Paper", "visibility": "PRIVATE", "target_plan": "Business",
        "connection": "Secure MCP Tunnel", "tools": receipt["tools"],
        "enrollment_state": "NOT_ENROLLED", "tunnel_id": None, "workspace_id": None,
        "seat_id": receipt.get("seat_id"),
        "purpose": "Guarded Paper design inspection, screenshots, JSX and explicitly approved edits.",
        "not_a_plugin_creator_manifest": True,
    })
    _private_dir(root, create=True)
    for name in ("runtime", "service", "logs", "state", "secrets"):
        _private_dir(root / name, create=True)
    for name, data in files.items():
        _write(root / name, data)
    receipt["files"] = {name: digest(data) for name, data in files.items()}
    # Last write is the complete staging receipt. Partial staging is never resumed
    # or overwritten implicitly; inspect and reconcile that exact directory.
    _write(root / "INSTALLATION.json", _json_bytes(receipt))
    verify(root)
    return receipt


def verify(root: Path) -> dict:
    root = _path(root)
    _private_dir(root)
    receipt = _json(root / "INSTALLATION.json")
    schema = receipt.get("schema")
    if (schema not in {SCHEMA_V2, SCHEMA_V3, SCHEMA_V4} or receipt.get("root") != str(root)
            or receipt.get("target_plan") != "Business"
            or receipt.get("state") != "STAGED_NOT_ENROLLED"
            or receipt.get("production_acceptance") is not False
            or receipt.get("service_loaded") is not False
            or receipt.get("account_modified") is not False
            or receipt.get("sdk_required") != f"mcp=={SDK_VERSION}"
            or not isinstance(receipt.get("sdk_distributions"), dict)
            or type(receipt.get("allow_write")) is not bool
            or type(receipt.get("allow_prepare")) is not bool
            or receipt.get("tools") != _tools(receipt["allow_write"], receipt["allow_prepare"])
            or not re.fullmatch(r"[0-9a-f]{40}", str(receipt.get("source_revision", "")))
            or not isinstance(receipt.get("files"), dict)
            or set(receipt["files"]) != expected_files(receipt)):
        raise Refusal("INVALID_MANIFEST")
    if schema in {SCHEMA_V3, SCHEMA_V4}:
        _seat_id(receipt.get("seat_id"))
    if schema == SCHEMA_V4:
        _host_ref(receipt.get("host_ref"))
    elif "host_ref" in receipt:
        raise Refusal("INVALID_MANIFEST")
    for name in ("runtime", "service", "logs", "state", "secrets"):
        _private_dir(root / name)
    for name, expected in receipt["files"].items():
        if digest(_read(root / name)) != expected:
            raise Refusal("HASH_MISMATCH")
    for name in ("python", "tunnel_client"):
        observed = receipt.get(name)
        if not isinstance(observed, dict) or set(observed) != {"path", "sha256"}:
            raise Refusal("INVALID_MANIFEST")
        if _binary(Path(observed["path"])) != observed:
            raise Refusal("BINARY_CHANGED")
    if _read(root / service_file(receipt)) != _plist(root, receipt):
        raise Refusal("SERVICE_TEMPLATE_CHANGED")
    return receipt


def profile_text(root: Path, tunnel_id: str, organization_id: str | None = None,
                 runtime_key_file: Path | None = None) -> str:
    if not isinstance(tunnel_id, str) or not TUNNEL_RE.fullmatch(tunnel_id):
        raise Refusal("TUNNEL_ID_REQUIRED")
    if organization_id is not None and (not isinstance(organization_id, str) or not ORG_RE.fullmatch(organization_id)):
        raise Refusal("ORGANIZATION_ID_REQUIRED")
    root = _path(root)
    receipt = verify(root)
    key_path = _path(runtime_key_file) if runtime_key_file is not None else root / "secrets/runtime-key"
    q = json.dumps
    return (
        "config_version: 1\ncontrol_plane:\n  base_url: \"https://api.openai.com\"\n"
        f"  tunnel_id: {q(tunnel_id)}\n"
        + (f"  organization_id: {q(organization_id)}\n" if organization_id is not None else "")
        + f"  api_key: {q('file:' + str(key_path))}\n"
        "health:\n  listen_addr: \"127.0.0.1:0\"\n"
        f"  url_file: {q(str(root / 'state/health.url'))}\n"
        "admin_ui:\n  open_browser: false\nlog:\n  level: info\n  format: json\n"
        "mcp:\n  max_concurrent_requests: 1\n  stdio_send_initialized_notification: true\n"
        f"  commands:\n    - channel: main\n      command: {q(shlex.join(_command(root, receipt, 'serve')))}\n"
    )


def _verify_runtime_key_path(key: Path) -> Path:
    key = _path(key)
    if not key.exists() and not key.is_symlink():
        raise Refusal("RUNTIME_KEY_MISSING")
    value = _read(key, limit=4096).strip()
    if value.startswith(b"sk-admin-"):
        raise Refusal("ADMIN_KEY_NOT_RUNTIME")
    if not value or any(char <= 32 or char >= 127 for char in value):
        raise Refusal("INVALID_RUNTIME_KEY")
    return key


def bind(root: Path, tunnel_id: str, workspace_id: str | None = None, organization_id: str | None = None,
         runtime_key_file: Path | None = None) -> dict:
    root = _path(root)
    receipt = verify(root)
    if organization_id is not None and (not isinstance(organization_id, str) or not ORG_RE.fullmatch(organization_id)):
        raise Refusal("ORGANIZATION_ID_REQUIRED")
    external_key = None
    if runtime_key_file is not None:
        if receipt.get("schema") not in {SCHEMA_V3, SCHEMA_V4}:
            raise Refusal("RUNTIME_KEY_REFERENCE_UNSUPPORTED")
        external_key = _verify_runtime_key_path(Path(runtime_key_file))
    profile = profile_text(root, tunnel_id, organization_id, external_key)
    connection = root / "connection"
    if connection.exists() or connection.is_symlink():
        raise Refusal("BINDING_EXISTS")
    if receipt.get("schema") == SCHEMA_V2:
        if not isinstance(workspace_id, str) or not WORKSPACE_RE.fullmatch(workspace_id):
            raise Refusal("WORKSPACE_ID_REQUIRED")
        value = {"schema": BINDING_SCHEMA_V1, "state": "BOUND_NOT_ACTIVATED",
                 "tunnel_id": tunnel_id, "workspace_id": workspace_id,
                 "target_plan": "Business", "workspace_access_verified": False}
    else:
        if workspace_id is not None and (not isinstance(workspace_id, str) or not WORKSPACE_RE.fullmatch(workspace_id)):
            raise Refusal("WORKSPACE_ID_REQUIRED")
        value = {"schema": BINDING_SCHEMA_V3 if external_key is not None else BINDING_SCHEMA_V2,
                 "state": "BOUND_NOT_ACTIVATED",
                 "seat_id": _seat_id(receipt.get("seat_id")), "tunnel_id": tunnel_id,
                 "workspace_id": workspace_id, "organization_id": organization_id,
                 "target_plan": "Business", "workspace_access_verified": False}
        if external_key is not None:
            value["runtime_key_file"] = str(external_key)
    _private_dir(connection, create=True)
    _write(connection / "profile.yaml", profile.encode())
    _write(connection / "BINDING.json", _json_bytes(value))
    verify_binding(root)
    return value


def verify_binding(root: Path) -> dict:
    root = _path(root)
    receipt = verify(root)
    if not (root / "connection").exists():
        raise Refusal("BINDING_REQUIRED")
    _private_dir(root / "connection")
    value = _json(root / "connection/BINDING.json")
    schema = value.get("schema")
    if value.get("target_plan") != "Business" or not TUNNEL_RE.fullmatch(str(value.get("tunnel_id", ""))):
        raise Refusal("INVALID_BINDING")
    if schema == BINDING_SCHEMA_V1:
        if receipt.get("schema") != SCHEMA_V2 or not WORKSPACE_RE.fullmatch(str(value.get("workspace_id", ""))):
            raise Refusal("INVALID_BINDING")
    elif schema in {BINDING_SCHEMA_V2, BINDING_SCHEMA_V3}:
        if receipt.get("schema") not in {SCHEMA_V3, SCHEMA_V4} or value.get("seat_id") != receipt.get("seat_id"):
            raise Refusal("INVALID_BINDING")
        workspace_id = value.get("workspace_id")
        if workspace_id is not None and not WORKSPACE_RE.fullmatch(str(workspace_id)):
            raise Refusal("INVALID_BINDING")
        organization_id = value.get("organization_id")
        if organization_id is not None and not ORG_RE.fullmatch(str(organization_id)):
            raise Refusal("INVALID_BINDING")
        if schema == BINDING_SCHEMA_V3:
            raw_key = value.get("runtime_key_file")
            if not isinstance(raw_key, str) or not raw_key:
                raise Refusal("INVALID_BINDING")
            _verify_runtime_key_path(Path(raw_key))
        elif "runtime_key_file" in value:
            raise Refusal("INVALID_BINDING")
    else:
        raise Refusal("INVALID_BINDING")
    runtime_key_file = Path(value["runtime_key_file"]) if schema == BINDING_SCHEMA_V3 else None
    if _read(root / "connection/profile.yaml") != profile_text(root, value.get("tunnel_id"), value.get("organization_id"), runtime_key_file).encode():
        raise Refusal("PROFILE_CHANGED")
    return value


def verify_runtime_key(root: Path) -> None:
    root = _path(root)
    key = root / "secrets/runtime-key"
    binding_path = root / "connection/BINDING.json"
    if binding_path.exists() and not binding_path.is_symlink():
        value = _json(binding_path)
        if value.get("schema") == BINDING_SCHEMA_V3:
            key = Path(value.get("runtime_key_file", ""))
    _verify_runtime_key_path(key)


@contextlib.contextmanager
def service_lock(root: Path):
    """Transport singleton only. Paper's desktop mutex remains the write owner."""
    root = _path(root)
    _private_dir(root, create=True)
    fd = os.open(root / "tunnel.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or info.st_mode & 0o077):
            raise Refusal("PRIVATE_FILE_REQUIRED")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Refusal("ALREADY_RUNNING") from exc
        yield fd
    finally:
        os.close(fd)


def _sdk() -> None:
    try:
        version = importlib.metadata.version("mcp")
    except importlib.metadata.PackageNotFoundError as exc:
        raise Refusal("MCP_SDK_REQUIRED") from exc
    if version != SDK_VERSION:
        raise Refusal("MCP_SDK_VERSION_CHANGED")


def require_running_python(receipt: dict) -> None:
    # Checking the selected interpreter's inventory is not evidence that this
    # process is using it. Reject a same-version but different environment.
    if Path(sys.executable).resolve() != Path(receipt["python"]["path"]):
        raise Refusal("RUNTIME_INTERPRETER_MISMATCH")


def serve(root: Path) -> None:
    receipt = verify(root)
    require_running_python(receipt)
    verify_sdk(root)
    _sdk()
    environment = clean_env(dict(os.environ))
    os.environ.clear()
    os.environ.update(environment)
    sys.path.insert(0, str(root / "runtime"))
    from mcp_server import build_server
    build_server(receipt["allow_write"], receipt["allow_prepare"],
                 execution_binding=execution_binding(receipt)).run(transport="stdio")


async def probe(root: Path) -> dict:
    """Real stdio initialize/tools-list; deliberately no Paper application call."""
    receipt = verify(root)
    require_running_python(receipt)
    verify_sdk(root)
    _sdk()
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    command = _command(root, receipt, "serve")
    async with stdio_client(StdioServerParameters(command=command[0], args=command[1:],
                                                 env=clean_env(dict(os.environ)))) as (reader, writer):
        async with ClientSession(reader, writer) as client:
            hello = await client.initialize()
            tools = await client.list_tools()
            if sorted(tool.name for tool in tools.tools) != receipt["tools"]:
                raise Refusal("TOOL_SURFACE_CHANGED")
            for tool in tools.tools:
                editing = tool.name == "paper_edit"
                annotations = tool.annotations
                if (annotations is None or annotations.readOnlyHint != (tool.name not in {"paper_edit", "paper_prepare"})
                        or annotations.destructiveHint != editing
                        or annotations.idempotentHint != (not editing)
                        or annotations.openWorldHint != editing):
                    raise Refusal("TOOL_ANNOTATIONS_CHANGED")
            wire = tools.model_dump(mode="json")
            return {"state": "LOCAL_STDIO_PROVEN", "paper_called": False,
                    "chatgpt_enrolled": False, "production_acceptance": False,
                    "server": hello.serverInfo.model_dump(mode="json"), "tools": receipt["tools"],
                    "schema_sha256": digest(_json_bytes(wire)), "catalog": wire}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["stage", "verify", "bind", "doctor", "run", "launch", "serve", "probe"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--python", type=Path)
    parser.add_argument("--tunnel-client", type=Path)
    parser.add_argument("--source-revision")
    parser.add_argument("--allow-write", action="store_true")
    parser.add_argument("--allow-prepare", action="store_true")
    parser.add_argument("--seat-id")
    parser.add_argument("--host-ref", help="Existing fleet host reference; configuration is not host attestation")
    parser.add_argument("--tunnel-id")
    parser.add_argument("--workspace-id")
    parser.add_argument("--organization-id")
    parser.add_argument("--runtime-key-file", type=Path)
    args = parser.parse_args()
    try:
        root = _path(args.root)
        if args.action != "stage" and args.host_ref is not None:
            installed = verify(root)
            if (installed.get("schema") != SCHEMA_V4
                    or _host_ref(args.host_ref) != installed.get("host_ref")):
                raise Refusal("HOST_BINDING_MISMATCH")
        if args.action == "stage":
            if not (args.python and args.tunnel_client and args.source_revision):
                raise Refusal("STAGE_ARGUMENTS_REQUIRED")
            value = stage(root, python=args.python, tunnel_client=args.tunnel_client,
                          source_revision=args.source_revision, allow_write=args.allow_write,
                          allow_prepare=args.allow_prepare, seat_id=args.seat_id, host_ref=args.host_ref)
        elif args.action == "bind":
            value = bind(root, args.tunnel_id, args.workspace_id, args.organization_id, args.runtime_key_file)
        elif args.action == "serve":
            serve(root)
            return 0
        elif args.action == "probe":
            value = asyncio.run(asyncio.wait_for(probe(root), timeout=30))
        elif args.action in {"doctor", "run", "launch"}:
            receipt = verify(root)
            require_running_python(receipt)
            verify_binding(root)
            verify_runtime_key(root)
            verify_sdk(root)
            _sdk()
            executable = receipt["tunnel_client"]["path"]
            command = [executable, "doctor" if args.action == "doctor" else "run",
                       "--profile-file", str(root / "connection/profile.yaml")]
            if args.action == "doctor":
                command += ["--json", "--explain"]
                os.execve(executable, command, clean_env(dict(os.environ)))
            # One transport singleton per ChatGPT seat; all seats still share
            # bridge.py's fixed per-OS-user Paper desktop mutex.
            owner = service_owner(receipt)
            with service_lock(owner) as fd:
                os.set_inheritable(fd, True)
                if args.action == "run":
                    os.execve(executable, command, clean_env(dict(os.environ)))
                # launchd uses KeepAlive SuccessfulExit=false so local/preflight
                # refusals can return zero and remain stopped. Once the real
                # tunnel client has started, however, any later return means the
                # transport is no longer serving. Normalize even a clean child
                # exit to a nonzero supervisor status so launchd restarts the
                # same seat service instead of silently leaving it offline.
                child = subprocess.run(command, env=clean_env(dict(os.environ)), check=False)
                print(json.dumps({
                    "state": "TUNNEL_CLIENT_EXITED",
                    "child_returncode": child.returncode,
                    "retry_allowed": True,
                    "execution_state": "STOPPED",
                    "automatic_restart_allowed": True,
                }), file=sys.stderr)
                return 75
            return 0
        else:
            value = verify(root)
        print(json.dumps(value, indent=2, sort_keys=True))
        return 0
    except Refusal as exc:
        value = {"state": str(exc), "retry_allowed": False}
        if args.action == "launch":
            # launchd uses SuccessfulExit=false. A permanent local gate must
            # stay stopped, not be retried forever. Zero is supervisor control,
            # NOT tunnel readiness: retain the refusal and explicit non-start.
            value.update(execution_state="NOT_STARTED", automatic_restart_allowed=False)
        print(json.dumps(value), file=sys.stderr)
        return 0 if args.action == "launch" else 2
    except Exception as exc:
        # Neither malformed local input nor an upstream library exception may
        # print credentials, profile bodies, or unrelated account environments.
        value = {"state": "LOCAL_FAILURE", "error_type": type(exc).__name__, "retry_allowed": False}
        if args.action == "launch":
            # All returning exceptions are before successful exec; no tunnel
            # client started. Surface the failure and require operator repair.
            value.update(execution_state="NOT_STARTED", automatic_restart_allowed=False)
        print(json.dumps(value), file=sys.stderr)
        return 0 if args.action == "launch" else 2


if __name__ == "__main__":
    raise SystemExit(main())
