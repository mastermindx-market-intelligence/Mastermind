"""Installed account-profile composition of the existing native T3 CLI owner.

This is a typed consumer of native authorization and linked environments. Profiles
are access bounds on the incumbent authenticated gateway, not another credential,
thread, fleet, admission, or subscription database. The native CLI owns its own
short-lived authentication; no token is read or synthesized here.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
from pathlib import PurePosixPath
import re
import stat
import time
from typing import Any, Callable

from .t3_cli_transport import T3NativeCliTransport, _decode
from .t3_dot_tools import TOOLS, MAX_BYTES
from .t3_native_client import Scope, T3NativeClient, Rejected, Unavailable, Conflict
from .t3_web_client import CliInvocation, CliResult

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,255}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = {"schema", "principal_key", "connection_id", "native_command", "t3_home",
           "local_environment_id", "environments", "operations", "delete_thread_ids", "timeout_seconds"}
_NAMES = frozenset(tool["name"] for tool in TOOLS)


def _id(value):
    if type(value) is not str or not _ID.fullmatch(value):
        raise ValueError("Exact native identity required")
    return value


def _path(value):
    if (type(value) is not str or not value or len(value) > 4096
            or not PurePosixPath(value).is_absolute() or ".." in PurePosixPath(value).parts
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ValueError("Host-owned absolute path required")
    return value


def validate_profile(value: dict) -> dict:
    if type(value) is not dict or set(value) != _FIELDS or value["schema"] != "mastermind.t3_dot_native_profile.v1":
        raise ValueError("Closed installed T3 profile required")
    _id(value["principal_key"]); _id(value["connection_id"]); _id(value["local_environment_id"])
    if not value["principal_key"].startswith("p:tunnel:"):
        raise ValueError("Exact existing private-tunnel principal required")
    command = value["native_command"]
    if type(command) is not list or len(command) not in (1, 2):
        raise ValueError("Qualified native command required")
    for part in command:
        _path(part)
    # The existing transport owns exact native-command qualification.
    T3NativeCliTransport(tuple(command), lambda invocation: None)
    _path(value["t3_home"])
    if type(value["timeout_seconds"]) is not int or not 5 <= value["timeout_seconds"] <= 90:
        raise ValueError("Bounded native invocation budget required")
    envs = value["environments"]
    if type(envs) is not list or not 1 <= len(envs) <= 32:
        raise ValueError("Bounded existing-environment scope required")
    seen = set()
    for row in envs:
        if type(row) is not dict or set(row) != {"environment_id", "project_ids"}:
            raise ValueError("Closed native environment scope required")
        ident = _id(row["environment_id"])
        if ident in seen:
            raise ValueError("Ambiguous native environment scope")
        seen.add(ident)
        projects = row["project_ids"]
        if type(projects) is not list or not 1 <= len(projects) <= 128:
            raise ValueError("Exact allowed native projects required; no wildcard")
        for project in projects:
            _id(project)
        if len(set(projects)) != len(projects):
            raise ValueError("Duplicate native project scope")
    if value["local_environment_id"] not in seen:
        raise ValueError("Original local environment must be retained")
    operations = value["operations"]
    if (type(operations) is not list or not operations or any(type(x) is not str or x not in _NAMES for x in operations)
            or len(operations) != len(set(operations))):
        raise ValueError("Closed typed operation allowlist required")
    deleted = value["delete_thread_ids"]
    if type(deleted) is not list or len(deleted) > 64:
        raise ValueError("Bounded explicit tombstone target list required")
    for item in deleted:
        _id(item)
    if len(deleted) != len(set(deleted)):
        raise ValueError("Duplicate tombstone target")
    return json.loads(json.dumps(value, allow_nan=False))


def read_profile(path: str, expected_sha256: str) -> dict:
    _path(path)
    if type(expected_sha256) is not str or not _SHA.fullmatch(expected_sha256):
        raise ValueError("Installed profile digest required")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o022 or not 1 <= info.st_size <= 65536):
            raise ValueError("Profile must be a bounded owner-controlled regular file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(65537)
        if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), expected_sha256):
            raise Conflict("Installed native profile changed")
        return validate_profile(_decode(raw.decode("utf-8"), 65536))
    finally:
        os.close(fd)


class BoundedNativeRunner:
    """One owned native helper per invocation, no shell/retry/detached worker.

    On timeout only this helper is stopped. Native inference may have started;
    the existing client's modifying-effect guard retains that uncertainty.
    last_effect is returned with failures for original-target reconciliation.
    """
    def __init__(self, profile: dict):
        self.profile = validate_profile(profile)
        self.deadline = time.monotonic() + profile["timeout_seconds"]
        self.last_effect: dict | None = None

    async def __call__(self, invocation: CliInvocation) -> CliResult:
        if type(invocation) is not CliInvocation:
            raise ValueError("Typed native invocation required")
        command = tuple(self.profile["native_command"])
        argv = tuple(invocation.argv)
        if argv[:len(command)] != command:
            raise Rejected("capability_denied")
        suffix = argv[len(command):]
        native = len(suffix) >= 5 and suffix[:3] == ("--log-level", "error", "thread") and suffix[3] in {"native", "native-catalog"}
        environment_list = suffix == ("--log-level", "error", "environment", "list", "--json")
        if not native and not environment_list:
            raise Rejected("unsupported_operation")
        stdin = invocation.stdin or ""
        raw = stdin.encode("utf-8")
        if len(raw) > MAX_BYTES:
            raise ValueError("Native stdin exceeds bounded contract")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise Unavailable("Native observation budget exhausted")
        self.last_effect = {"pid": None, "command_sha256": hashlib.sha256(json.dumps(argv).encode()).hexdigest(),
                            "stdin_sha256": hashlib.sha256(raw).hexdigest(), "helper_state": "NOT_STARTED"}
        env = {"HOME": os.environ.get("HOME", ""), "PATH": "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin",
               "TMPDIR": os.environ.get("TMPDIR", "/tmp"), "T3CODE_HOME": self.profile["t3_home"],
               "NO_COLOR": "1"}
        process = await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env, limit=65536)
        self.last_effect.update(pid=process.pid, helper_state="STARTED")
        async def bounded(stream, limit):
            data = bytearray()
            while True:
                chunk = await stream.read(65536)
                if not chunk:
                    return bytes(data)
                if len(data) + len(chunk) > limit:
                    raise Unavailable("Native helper output exceeds limit")
                data.extend(chunk)
        async def exchange():
            process.stdin.write(raw)
            await process.stdin.drain()
            process.stdin.close()
            out, _ = await asyncio.gather(bounded(process.stdout, 2 * 1024 * 1024),
                                          bounded(process.stderr, 65536))
            code = await process.wait()
            return CliResult(code, out.decode("utf-8"), "")
        try:
            result = await asyncio.wait_for(exchange(), timeout=remaining)
            self.last_effect["helper_state"] = "EXITED"
            self.last_effect["returncode"] = result.returncode
            return result
        except BaseException:
            # Never infer native task cancellation from a helper's exit.
            self.last_effect["helper_state"] = "RETURN_UNQUALIFIED"
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=2)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
            raise


class NativeDotFleetOwner:
    def __init__(self, profile: dict, *, runner: Callable | None = None,
                 current_profile: Callable | None = None):
        self.profile = validate_profile(profile)
        self.current_profile = current_profile
        self.runner = runner if runner is not None else BoundedNativeRunner(self.profile)
        self.transport = T3NativeCliTransport(tuple(self.profile["native_command"]), self.runner)
        self._local = None
        self._scopes = {row["environment_id"]: frozenset(row["project_ids"]) for row in self.profile["environments"]}

    async def authorize(self, principal, *, operation, environment_id, project_id, thread_id, arguments):
        if self.current_profile is not None and self.current_profile() != self.profile:
            raise Rejected("capability_denied")
        if type(principal) is not str or not hmac.compare_digest(principal, self.profile["principal_key"]):
            raise Rejected("capability_denied")
        if operation not in self.profile["operations"]:
            raise Rejected("capability_denied")
        if environment_id is not None and environment_id not in self._scopes:
            raise Rejected("capability_denied")
        if project_id is not None and project_id not in self._scopes.get(environment_id, ()):
            raise Rejected("capability_denied")
        if operation == "t3_thread_delete" and thread_id not in self.profile["delete_thread_ids"]:
            raise Rejected("capability_denied")

    async def _connect(self):
        if self._local is None:
            env = self.profile["local_environment_id"]
            project = next(row["project_ids"][0] for row in self.profile["environments"] if row["environment_id"] == env)
            scope = Scope(self.profile["connection_id"], env, project)
            self._local = await self.transport.connect(scope)
        return self._local

    async def _environment(self, environment_id):
        local = await self._connect()
        args = {} if environment_id == local.scope.environment_id else {"environmentId": environment_id}
        value = await self.transport.call_tool("t3_environment_read", args)
        body = value.get("structuredContent")
        if value.get("isError") is not None and value.get("isError") is not False:
            code = body.get("code") if type(body) is dict else None
            if code in {"capability_denied", "environment_not_found", "authorization_failed"}:
                raise Rejected("capability_denied")
            raise Unavailable("Selected native environment did not answer")
        if type(body) is not dict or body.get("environmentId") != environment_id:
            raise Conflict("Selected native environment identity changed")
        return body

    async def environments(self, principal):
        local = await self._environment(self.profile["local_environment_id"])
        invocation = CliInvocation((*self.profile["native_command"], "--log-level", "error", "environment", "list", "--json"), None)
        response = await self.runner(invocation)
        if type(response) is not CliResult or response.returncode != 0 or len(response.stdout.encode()) > MAX_BYTES:
            raise Unavailable("Native linked-environment projection unavailable")
        # Native environment list has an array root; preserve its native owner.
        wrapped = _decode('{"rows":' + response.stdout.strip() + '}', MAX_BYTES + 16)
        links = wrapped["rows"]
        if type(links) is not list or len(links) > 128:
            raise Unavailable("Native linked-environment catalog malformed")
        rows = [{"environment_id": local["environmentId"], "label": local.get("label"),
                 "server_version": local.get("serverVersion"), "status": "reachable", "local": True}]
        seen = {local["environmentId"]}
        for link in links:
            if type(link) is not dict:
                raise Unavailable("Malformed native environment link")
            ident = _id(link.get("environmentId"))
            if ident in seen:
                raise Unavailable("Ambiguous native environment link")
            seen.add(ident)
            if ident not in self._scopes:
                continue
            rows.append({"environment_id": ident, "label": link.get("label"), "status": link.get("status", "unknown"),
                         "access": link.get("access"), "expires_at": link.get("expiresAt"), "local": False})
        for ident in self._scopes:
            if ident not in seen:
                rows.append({"environment_id": ident, "status": "not_linked", "local": False})
        return {"environments": rows, "source": "native_t3_environment_links", "execution_admission": "NOT_OBSERVED"}

    async def projects(self, principal, environment_id, *, cursor=0, limit=20):
        await self._environment(environment_id)
        props = self.transport._schemas["t3_project_list"]["properties"]
        args = {}
        if "environmentId" in props:
            args["environmentId"] = environment_id
        elif environment_id != self.profile["local_environment_id"]:
            raise Unavailable("Native remote project routing is unavailable")
        if "cursor" in props:
            args["cursor"] = cursor
        if "limit" in props:
            args["limit"] = limit
        raw = await self.transport.call_tool("t3_project_list", args)
        body = raw.get("structuredContent")
        if ((raw.get("isError") is not None and raw.get("isError") is not False)
                or type(body) is not dict or type(body.get("projects")) is not list):
            raise Unavailable("Native project catalog unavailable")
        if len(body["projects"]) > 256:
            raise Unavailable("Native project catalog exceeds bound")
        rows, seen = [], set()
        for row in body["projects"]:
            if type(row) is not dict:
                raise Unavailable("Malformed native project")
            ident = _id(row.get("projectId"))
            if ident in seen:
                raise Unavailable("Duplicate native project")
            seen.add(ident)
            if ident in self._scopes[environment_id]:
                rows.append(row)
        nxt = body.get("nextCursor")
        if nxt is not None and (type(nxt) is not int or nxt <= cursor):
            raise Unavailable("Native project pagination did not advance")
        if "cursor" not in props:
            # Locally page one bounded native read; never truncate silently.
            selected = rows[cursor:cursor + limit]
            nxt = cursor + limit if cursor + limit < len(rows) else None
        else:
            selected = rows
        return {"environment_id": environment_id, "projects": selected, "next_cursor": nxt,
                "source": "native_t3_projects", "authorization_filtered": True,
                "pagination": "native" if "cursor" in props else "bounded_projection"}

    async def client(self, principal, environment_id, project_id):
        await self._environment(environment_id)
        scope = Scope(self.profile["connection_id"], environment_id, project_id)
        return T3NativeClient(scope, self.transport.call_tool, self.transport._schemas)
