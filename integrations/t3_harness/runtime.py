"""Thin process-local T3 consumer of the installed Mastermind browser bridge.

T3CODE_THREAD_ID is native process attribution, NOT authentication. The existing
OS user, native browser host, selected profile and extension site grants remain
the authorization owners. No credentials, listener, retry or routing plane.
"""
from __future__ import annotations

import asyncio
import base64
import copy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import secrets
import stat
from typing import Any

from integrations.session_bridge.project_task_context import load_context, PlanContextError
from integrations.session_bridge.long_horizon_guidance import compact_context

SCHEMA = "mastermind.t3_harness.local_runtime/v1"
SOURCE_FILES = frozenset({
    "integrations/__init__.py", "integrations/session_bridge/__init__.py",
    "integrations/session_bridge/project_task_context.py", "integrations/session_bridge/long_horizon_guidance.py",
    "integrations/t3_harness/__init__.py", "integrations/t3_harness/runtime.py", "integrations/t3_harness/server.py", "integrations/t3_harness/native_launch.py",
})
BROWSER_FILES = frozenset({
    "control_plane/__init__.py", "control_plane/surface_bindings.py",
    "integrations/__init__.py", "integrations/chairman_surfaces/__init__.py",
    "integrations/chairman_surfaces/_web_sol_native_host_impl.py",
    "integrations/chairman_surfaces/web_sol_browser_protocol.py",
    "integrations/chairman_surfaces/web_sol_census_protocol.py",
    "integrations/chairman_surfaces/web_sol_client.py", "integrations/chairman_surfaces/web_sol_instance.py",
    "integrations/chairman_surfaces/web_sol_native_host.py", "integrations/chairman_surfaces/web_sol_protocol.py",
    "integrations/hermes_harness/__init__.py", "integrations/hermes_harness/browser_bridge.py",
    "integrations/hermes_harness/browser_routes.py", "integrations/hermes_harness/browser_tool_schema.json",
})
READ_ACTIONS = frozenset({"browsers", "hosts", "status", "tabs", "snapshot", "screenshot", "capture",
                          "diagnostics", "frames", "accessibility", "dom", "locate", "events", "network",
                          "response_body", "downloads", "result", "cdp_status"})
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:%/-]{0,511}\Z")
_BOOT = ('import runpy,sys;root,bindings,namespace,local=sys.argv[1:];sys.path.insert(0,root);'
         'sys.argv=["mmx_browser","--bindings",bindings,"--profile",namespace]+(["--local-only"] if local=="1" else []);'
         'runpy.run_module("integrations.hermes_harness.browser_bridge",run_name="__main__")')


class HarnessError(ValueError):
    """Fixed non-sensitive contract code; never carry raw subprocess diagnostics."""


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise HarnessError("DUPLICATE_JSON_KEY")
        out[key] = value
    return out


def decode(raw: bytes) -> dict:
    value = json.loads(raw, object_pairs_hook=_pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(HarnessError("NONFINITE_JSON")))
    if type(value) is not dict:
        raise HarnessError("OBJECT_REQUIRED")
    return value


def encode(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def _absolute(value: Any) -> Path:
    if type(value) is not str or not value or "\x00" in value or not Path(value).is_absolute():
        raise HarnessError("ABSOLUTE_INSTALL_PATH_REQUIRED")
    return Path(value)


def safe_bytes(path: Path, maximum: int = 2 * 1024 * 1024) -> bytes:
    if not hasattr(os, "O_NOFOLLOW"):
        raise HarnessError("NATIVE_FILE_CONTRACT_UNAVAILABLE")
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_size > maximum
                or before.st_uid != os.getuid() or before.st_mode & 0o022):
            raise HarnessError("SOURCE_FILE_UNSAFE")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(maximum + 1)
        after = os.fstat(fd)
        if (len(raw) > maximum or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise HarnessError("SOURCE_FILE_CHANGED")
        return raw
    finally:
        os.close(fd)


def _closure(root: Path, files: Any, expected: frozenset[str]) -> None:
    if root.is_symlink() or not root.is_dir() or type(files) is not dict or set(files) != expected:
        raise HarnessError("SOURCE_CLOSURE_INVALID")
    for relative, digest in files.items():
        if type(digest) is not str or _HEX.fullmatch(digest) is None:
            raise HarnessError("SOURCE_DIGEST_INVALID")
        current = root
        for part in PurePosixPath(relative).parts:
            current /= part
            if current.is_symlink():
                raise HarnessError("SOURCE_SYMLINK_REFUSED")
        if hashlib.sha256(safe_bytes(current)).hexdigest() != digest:
            raise HarnessError("SOURCE_DIGEST_MISMATCH")


def failure(reason: str, request_ref=None, *, possible: bool = False, read: bool = False) -> dict:
    return {"state": ("UNAVAILABLE" if read else "EFFECT_UNKNOWN") if possible else "REFUSED",
            "reason": reason, "request_ref": request_ref, "retry_allowed": False,
            "business_outcome_verified": False}


def read_configuration(path: str, expected_sha256: str, environment=None) -> tuple[dict, str]:
    if type(expected_sha256) is not str or _HEX.fullmatch(expected_sha256) is None:
        raise HarnessError("CONFIG_DIGEST_REQUIRED")
    raw = safe_bytes(_absolute(path), 65536)
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise HarnessError("CONFIG_CHANGED")
    config = decode(raw)
    keys = {"schema", "source_root", "source_files", "browser_descriptor", "browser_descriptor_sha256",
            "namespace", "local_browser_only", "session_bindings"}
    if set(config) - {"peekaboo"} != keys or config.get("schema") != SCHEMA:
        raise HarnessError("CONFIG_SCHEMA_INVALID")
    if (type(config["namespace"]) is not str or _ID.fullmatch(config["namespace"]) is None
            or not config["namespace"].startswith("t3:") or type(config["local_browser_only"]) is not bool):
        raise HarnessError("NATIVE_NAMESPACE_INVALID")
    bindings = config["session_bindings"]
    if type(bindings) is not dict or len(bindings) > 128:
        raise HarnessError("SESSION_BINDINGS_INVALID")
    for sid, binding in bindings.items():
        if (type(sid) is not str or _ID.fullmatch(sid) is None or type(binding) is not dict
                or set(binding) != {"workspace_root", "plan_path", "workstream", "plan_contract_sha256"}):
            raise HarnessError("SESSION_BINDING_INVALID")
        _absolute(binding["workspace_root"])
        if any(type(v) is not str or not v or len(v.encode()) > 4096 for v in binding.values()):
            raise HarnessError("SESSION_BINDING_INVALID")
        if _HEX.fullmatch(binding["plan_contract_sha256"]) is None:
            raise HarnessError("PLAN_CONTRACT_INVALID")
    if _absolute(config["source_root"]).resolve() != Path(__file__).resolve().parents[2]:
        raise HarnessError("LOADED_SOURCE_ROOT_MISMATCH")
    _closure(_absolute(config["source_root"]), config["source_files"], SOURCE_FILES)
    sid = (os.environ if environment is None else environment).get("T3CODE_THREAD_ID")
    if type(sid) is not str or _ID.fullmatch(sid) is None or len(sid) > 256:
        raise HarnessError("NATIVE_T3_THREAD_CONTEXT_MISSING")
    return config, sid


@dataclass(frozen=True)
class Runtime:
    config_path: Path
    config_sha256: str
    thread_id: str
    config: dict
    browser: dict
    browser_schema: dict

    @classmethod
    def load(cls, path: str, expected_sha256: str, environment: dict[str, str] | None = None):
        config, sid = read_configuration(path, expected_sha256, environment)
        descriptor = safe_bytes(_absolute(config["browser_descriptor"]), 65536)
        if hashlib.sha256(descriptor).hexdigest() != config["browser_descriptor_sha256"]:
            raise HarnessError("BROWSER_DEPLOYMENT_CHANGED")
        browser = decode(descriptor)
        required = {"schema", "release_commit", "source_root", "source_files", "python_executable",
                    "profile_home", "bindings_path"}
        if (not required <= set(browser) or set(browser) - required - {"artifact_root", "host_ref", "upload_roots"}
                or browser.get("schema") != "mastermind.hermes_browser.local_runtime/v1"):
            raise HarnessError("BROWSER_DEPLOYMENT_INVALID")
        if not re.fullmatch(r"[0-9a-f]{40}", browser.get("release_commit", "")):
            raise HarnessError("BROWSER_RELEASE_INVALID")
        uploads = browser.get("upload_roots", [])
        if type(uploads) is not list or len(uploads) > 32:
            raise HarnessError("BROWSER_UPLOAD_ROOTS_INVALID")
        for root in uploads:
            _absolute(root)
        _closure(_absolute(browser["source_root"]), browser["source_files"], BROWSER_FILES)
        for key in ("python_executable", "profile_home", "bindings_path"):
            _absolute(browser[key])
        if not os.access(browser["python_executable"], os.X_OK):
            raise HarnessError("BROWSER_INTERPRETER_UNAVAILABLE")
        schema = decode(safe_bytes(Path(browser["source_root"]) / "integrations/hermes_harness/browser_tool_schema.json", 32768))
        if schema.get("name") != "mmx_browser" or type(schema.get("parameters")) is not dict:
            raise HarnessError("BROWSER_TOOL_SCHEMA_INVALID")
        return cls(Path(path), expected_sha256, sid, config, browser, schema)

    def current(self) -> bool:
        try:
            fresh = Runtime.load(str(self.config_path), self.config_sha256, {"T3CODE_THREAD_ID": self.thread_id})
            return fresh.config == self.config and fresh.browser == self.browser and fresh.browser_schema == self.browser_schema
        except (OSError, ValueError, TypeError, RecursionError):
            return False

    def project_context(self, arguments: Any) -> dict:
        if type(arguments) is not dict or arguments:
            return failure("CLOSED_EMPTY_ARGUMENTS_REQUIRED")
        if not self.current():
            return failure("INSTALL_BINDING_CHANGED")
        binding = self.config["session_bindings"].get(self.thread_id)
        if binding is None:
            return {"state": "UNBOUND", "reason": "EXACT_THREAD_PLAN_BINDING_REQUIRED", "execution_authority": False}
        try:
            value = load_context(workspace_root=Path(binding["workspace_root"]), relative_path=binding["plan_path"],
                                 expected_contract_sha256=binding["plan_contract_sha256"], workstream=binding["workstream"], context_detail="frontier")
            result = compact_context(value)
            if not self.current():
                return failure("INSTALL_BINDING_CHANGED")
            return {"state": "OBSERVED", "native_thread_id": self.thread_id, "project": result,
                    "native_action": "NONE", "mission_accepted": False}
        except (PlanContextError, OSError, ValueError, TypeError):
            return failure("PROJECT_SOURCE_UNAVAILABLE")

    async def browser_call(self, arguments: Any, *, exchange=None) -> dict:
        if type(arguments) is not dict or len(encode(arguments)) > 30000:
            return failure("BROWSER_ARGUMENTS_INVALID")
        if not self.current():
            return failure("INSTALL_BINDING_CHANGED")
        # Never accept native identity, credentials, runtime paths or a caller
        # operation id in tool arguments. The exact native bridge validates the
        # rest of the schema and permission/connection/document/reference state.
        if set(arguments) - set(self.browser_schema["parameters"].get("properties", {})):
            return failure("BROWSER_ARGUMENTS_INVALID")
        action = arguments.get("action")
        if type(action) is not str or action not in self.browser_schema["parameters"]["properties"]["action"]["enum"]:
            return failure("BROWSER_ACTION_INVALID")
        operation = "hermes-browser-" + secrets.token_hex(16)  # incumbent wire grammar, not Hermes identity
        nonce = secrets.token_hex(24)
        request_ref = {"operation_key": operation, "nonce": nonce, "action": action,
                       "browser_id": arguments.get("browser_id"), "connection_id": arguments.get("connection_id")}
        envelope = {"session_id": self.thread_id, "arguments": copy.deepcopy(arguments),
                    "operation_key": operation, "nonce": nonce}
        read = action in READ_ACTIONS
        try:
            output = await (exchange or self._exchange)(envelope)
            if type(output) is not dict or len(encode(output)) > 1024 * 1024:
                raise HarnessError("BROWSER_OUTPUT_INVALID")
            if output.get("state") not in {"REFUSED", "UNAVAILABLE", "EFFECT_UNKNOWN", "RECEIPT", "OBSERVED"}:
                raise HarnessError("BROWSER_OUTPUT_INVALID")
            receipt = output.get("receipt")
            if output.get("state") == "RECEIPT" and (type(receipt) is not dict
                    or receipt.get("action") != action or receipt.get("operation_key") != operation
                    or receipt.get("nonce") != nonce):
                raise HarnessError("BROWSER_RECEIPT_MISMATCH")
            if not self.current():
                return failure("INSTALL_CHANGED_DURING_CALL", request_ref, possible=True, read=read)
            return {**output, "t3_request_ref": request_ref, "caller_attribution": "NATIVE_PROCESS_ENV_NOT_AUTHENTICATION"}
        except asyncio.CancelledError:
            # No replay. Native host retains the operation; caller cancellation
            # is not proof the browser action was cancelled or did not execute.
            raise
        except (OSError, ValueError, TypeError, RecursionError, asyncio.TimeoutError):
            return failure("BROWSER_ORIGINAL_EFFECT_REQUIRES_RECONCILIATION", request_ref, possible=True, read=read)

    async def _exchange(self, envelope: dict) -> dict:
        args = [self.browser["python_executable"], "-I", "-B", "-c", _BOOT,
                self.browser["source_root"], self.browser["bindings_path"], self.config["namespace"],
                "1" if self.config["local_browser_only"] else "0"]
        env = {"HOME": pwd.getpwuid(os.getuid()).pw_dir, "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
               "PYTHONDONTWRITEBYTECODE": "1",
               "MMX_BROWSER_UPLOAD_ROOTS": encode(self.browser.get("upload_roots", [])).decode()}
        process = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env, limit=65536)
        async def collect(stream, limit):
            chunks, size = [], 0
            while data := await stream.read(65536):
                size += len(data)
                if size > limit:
                    raise HarnessError("BROWSER_OUTPUT_OVER_BUDGET")
                chunks.append(data)
            return b"".join(chunks)
        try:
            async with asyncio.timeout(60):
                process.stdin.write(encode(envelope)); await process.stdin.drain(); process.stdin.close()
                stdout, _ = await asyncio.gather(collect(process.stdout, 1024 * 1024), collect(process.stderr, 32768))
                if await process.wait() != 0:
                    raise HarnessError("BROWSER_PROCESS_FAILED")
                return decode(stdout)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()


def present(output: dict) -> tuple[dict, list[dict]]:
    """Preserve real images as MCP content, not base64 hidden in prose."""
    value = copy.deepcopy(output)
    receipt = value.get("receipt")
    attachments = []
    if type(receipt) is dict and receipt.get("status") == "OK" and receipt.get("action") in {"screenshot", "capture", "pdf"}:
        data = receipt.get("data")
        if type(data) is not dict or type(data.get("base64")) is not str or len(data["base64"]) > 700000:
            raise HarnessError("BROWSER_ATTACHMENT_INVALID")
        mime = data.get("mime_type")
        magic = {"image/jpeg": b"\xff\xd8", "image/png": b"\x89PNG\r\n\x1a\n", "application/pdf": b"%PDF-"}
        if mime not in magic or not base64.b64decode(data["base64"], validate=True).startswith(magic[mime]):
            raise HarnessError("BROWSER_ATTACHMENT_INVALID")
        attachments.append({"mime_type": mime, "data": data["base64"]})
        receipt["data"] = {k: v for k, v in data.items() if k != "base64"}
        receipt["data"]["attachment_returned"] = True
    return value, attachments
