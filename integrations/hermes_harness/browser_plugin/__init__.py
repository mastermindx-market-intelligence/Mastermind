"""Native Hermes registration for the existing Mastermind browser transport.

PluginContext owns registration, profile scope and unload. The fixed subprocess
imports an exact source closure without inheriting provider secrets or paths.
No daemon, browser launcher, registry, queue, permission grant or retry is added.
"""
from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import stat
import subprocess

TOOL_NAME = "mmx_browser"
TOOLSET = "mastermind_browser"
RUNTIME_SCHEMA = "mastermind.hermes_browser.local_runtime/v1"
MAX_BYTES = 65536
READ_ACTIONS = frozenset({"browsers", "status", "tabs", "snapshot", "screenshot", "diagnostics"})
SOURCE_FILES = frozenset({
    "integrations/__init__.py", "integrations/hermes_harness/__init__.py",
    "integrations/hermes_harness/browser_bridge.py", "integrations/hermes_harness/browser_tool_schema.json",
    "integrations/chairman_surfaces/__init__.py", "integrations/chairman_surfaces/web_sol_client.py",
    "integrations/chairman_surfaces/web_sol_instance.py", "integrations/chairman_surfaces/web_sol_protocol.py",
    "integrations/chairman_surfaces/web_sol_browser_protocol.py", "integrations/chairman_surfaces/web_sol_census_protocol.py",
    "integrations/chairman_surfaces/web_sol_native_host.py", "integrations/chairman_surfaces/_web_sol_native_host_impl.py",
    "control_plane/__init__.py", "control_plane/surface_bindings.py",
})
_BOOT = ('import runpy,sys;root,bindings,profile=sys.argv[1:];sys.path.insert(0,root);'
         'sys.argv=["mmx_browser","--bindings",bindings,"--profile",profile];'
         'runpy.run_module("integrations.hermes_harness.browser_bridge",run_name="__main__")')


class NativeBrowserError(RuntimeError):
    pass


@dataclass(frozen=True)
class Runtime:
    release_commit: str
    source_root: str
    python_executable: str
    profile_home: str
    bindings_path: str
    source_files: tuple[tuple[str, str], ...]
    descriptor_path: str
    descriptor_sha256: str


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


def _decode(raw):
    return json.loads(raw, object_pairs_hook=_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))


def _safe_bytes(path, maximum=1048576):
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
    if not hasattr(os, "O_NOFOLLOW"):
        raise NativeBrowserError("NATIVE_FILE_CONTRACT_UNAVAILABLE")
    fd = os.open(path, flags | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_size > maximum
                or before.st_uid != os.getuid() or before.st_mode & 0o022):
            raise NativeBrowserError("NATIVE_SOURCE_UNSAFE")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(maximum + 1)
        after = os.fstat(fd)
        if (len(raw) > maximum or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise NativeBrowserError("NATIVE_SOURCE_CHANGED")
        return raw
    finally:
        os.close(fd)


def verify_sources(binding):
    try:
        if hashlib.sha256(_safe_bytes(Path(binding.descriptor_path), MAX_BYTES)).hexdigest() != binding.descriptor_sha256:
            return False
        root = Path(binding.source_root)
        if root.is_symlink():
            return False
        return all(hashlib.sha256(_safe_bytes(root / path)).hexdigest() == sha for path, sha in binding.source_files)
    except (OSError, NativeBrowserError):
        return False


def load_runtime():
    path = Path(__file__).with_name("_runtime.json")
    try:
        raw = _safe_bytes(path, MAX_BYTES)
        data = _decode(raw)
        fields = {"schema", "release_commit", "source_root", "python_executable", "profile_home", "bindings_path", "source_files"}
        if type(data) is not dict or set(data) != fields or data["schema"] != RUNTIME_SCHEMA:
            raise ValueError("descriptor")
        if type(data["release_commit"]) is not str or re.fullmatch(r"[0-9a-f]{40}", data["release_commit"]) is None:
            raise ValueError("revision")
        for key in ("source_root", "python_executable", "profile_home", "bindings_path"):
            if type(data[key]) is not str or not Path(data[key]).is_absolute() or "\x00" in data[key]:
                raise ValueError("path")
        files = data["source_files"]
        if type(files) is not dict or set(files) != SOURCE_FILES:
            raise ValueError("closure")
        if any(type(v) is not str or re.fullmatch(r"[0-9a-f]{64}", v) is None for v in files.values()):
            raise ValueError("digest")
        if not os.access(data["python_executable"], os.X_OK):
            raise ValueError("interpreter")
        binding = Runtime(data["release_commit"], data["source_root"], data["python_executable"],
            data["profile_home"], data["bindings_path"], tuple(sorted(files.items())), str(path), hashlib.sha256(raw).hexdigest())
        if not verify_sources(binding):
            raise ValueError("source")
        return binding
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise NativeBrowserError("NATIVE_DESCRIPTOR_INVALID") from None


def _failure(reason, request_ref=None, *, possible=False, read=False):
    return json.dumps({"state": ("UNAVAILABLE" if read else "EFFECT_UNKNOWN") if possible else "REFUSED",
                       "reason": reason, "request_ref": request_ref, "retry_allowed": False}, separators=(",", ":"))


def _present(out):
    """Use the installed Hermes multimodal tool-result contract, without a file."""
    receipt = out.get("receipt")
    if (type(receipt) is dict and receipt.get("action") == "screenshot" and receipt.get("status") == "OK"
            and type(receipt.get("data")) is dict):
        data = receipt["data"]
        encoded = data.get("base64")
        if (data.get("mime_type") != "image/jpeg" or type(encoded) is not str or len(encoded) > 45000
                or not base64.b64decode(encoded, validate=True).startswith(b"\xff\xd8")):
            raise ValueError("image")
        receipt["data"] = {"mime_type": "image/jpeg", "scope": "selected tab viewport", "image_attached": True}
        summary = json.dumps(out, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        return {"_multimodal": True, "text_summary": summary,
                "content": [{"type": "text", "text": summary},
                            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + encoded}}]}
    return json.dumps(out, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def register(ctx):
    from tools.registry import registry
    from registration_lifecycle import replacement_coordinator
    import hermes_constants

    binding = load_runtime()
    scope = getattr(getattr(ctx, "_manager", None), "scope_key", None)
    if type(scope) is not str or Path(scope).resolve() != Path(binding.profile_home).resolve():
        raise NativeBrowserError("NATIVE_PROFILE_MISMATCH")
    schema = _decode(_safe_bytes(Path(binding.source_root) / "integrations/hermes_harness/browser_tool_schema.json", 16384))
    if type(schema) is not dict or schema.get("name") != TOOL_NAME:
        raise NativeBrowserError("NATIVE_SCHEMA_INVALID")

    def current():
        try:
            if Path(hermes_constants.get_hermes_home()).resolve() != Path(binding.profile_home).resolve():
                return False
            entry = registry.snapshot_registration(TOOL_NAME, scope=scope)
            return entry is not None and entry.handler is handler and verify_sources(binding)
        except Exception:
            return False

    def handler(arguments, *, session_id=None, task_id=None):
        try:
            if type(arguments) is not dict or type(arguments.get("action")) is not str or arguments["action"] not in schema["parameters"]["properties"]["action"]["enum"]:
                return _failure("NATIVE_REQUEST_INVALID")
            if type(session_id) is not str or not 1 <= len(session_id) <= 256:
                return _failure("NATIVE_SESSION_UNBOUND")
            operation, nonce = "hermes-browser-" + secrets.token_hex(16), secrets.token_hex(24)
            request_ref = {"operation_key": operation, "nonce": nonce, "action": arguments["action"],
                "browser_id": arguments.get("browser_id"), "connection_id": arguments.get("connection_id")}
            raw = json.dumps({"session_id": session_id, "arguments": arguments, "operation_key": operation,
                "nonce": nonce}, allow_nan=False, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if len(raw) > 32768:
                return _failure("NATIVE_REQUEST_INVALID")
            if not current():
                return _failure("NATIVE_REGISTRATION_STALE")
        except (ValueError, TypeError, RecursionError, UnicodeError):
            return _failure("NATIVE_REQUEST_INVALID")
        read = arguments["action"] in READ_ACTIONS
        try:
            process = subprocess.run([binding.python_executable, "-I", "-B", "-c", _BOOT,
                binding.source_root, binding.bindings_path, binding.profile_home],
                input=raw, capture_output=True, timeout=28, cwd=binding.source_root,
                env={"PATH": "/usr/bin:/bin", "HOME": pwd.getpwuid(os.getuid()).pw_dir,
                     "HERMES_HOME": binding.profile_home, "LANG": "C.UTF-8"}, check=False)
        except subprocess.TimeoutExpired:
            return _failure("NATIVE_LOCAL_TIMEOUT", request_ref, possible=True, read=read)
        except OSError:
            return _failure("NATIVE_LOCAL_UNAVAILABLE", request_ref)
        try:
            if not current():
                return _failure("NATIVE_REGISTRATION_CHANGED", request_ref, possible=True, read=read)
            if process.returncode != 0 or process.stderr or len(process.stdout) > MAX_BYTES:
                raise ValueError("output")
            out = _decode(process.stdout)
            if type(out) is not dict or out.get("state") not in {"RECEIPT", "OBSERVED", "REFUSED", "EFFECT_UNKNOWN"}:
                raise ValueError("output")
            if out["state"] == "RECEIPT":
                receipt = out.get("receipt")
                expected_session = hashlib.sha256((binding.profile_home + "\0" + session_id).encode()).hexdigest()
                if (type(receipt) is not dict or receipt.get("schema") != "mastermind.web_sol_browser_receipt.v1"
                        or any(receipt.get(k) != v for k, v in (("operation_key", operation), ("nonce", nonce),
                            ("action", arguments["action"]), ("adapter_instance_id", arguments.get("browser_id")), ("session_id", expected_session)))):
                    raise ValueError("identity")
            out["bridge_release_commit"] = binding.release_commit
            return _present(out)
        except (ValueError, TypeError, RecursionError, UnicodeError, KeyError):
            return _failure("NATIVE_LOCAL_OUTPUT_INVALID", request_ref, possible=True, read=read)

    with replacement_coordinator.transaction():
        if registry.get_entry(TOOL_NAME, scope=scope) is not None:
            raise NativeBrowserError("NATIVE_TOOL_COLLISION")
        try:
            handle = ctx.register_tool(name=TOOL_NAME, toolset=TOOLSET, schema=schema, handler=handler,
                                       description=schema["description"])
        except Exception:
            raise NativeBrowserError("NATIVE_REGISTRATION_EFFECT_UNKNOWN") from None
        if handle is None:
            raise NativeBrowserError("NATIVE_TOOL_NOT_REGISTERED")
        try:
            entry = registry.snapshot_registration(TOOL_NAME, scope=scope)
            if entry is None or entry.handler is not handler or entry.schema != schema or entry.toolset != TOOLSET:
                raise ValueError("readback")
        except Exception:
            try:
                handle.dispose()
            except Exception:
                raise NativeBrowserError("NATIVE_TOOL_ROLLBACK_UNKNOWN") from None
            raise NativeBrowserError("NATIVE_TOOL_READBACK_FAILED") from None
        return handle
