#!/usr/bin/env python3
"""Readiness launcher for the pinned Rakazo topology journey.

This placement prepares source and reports readiness. It admits the immutable
public donor pin before any donor evaluation, closes the child environment,
and derives an attempt-owned runner. It does not start the topology.

The donor is elie222/rakazo at c5e66e010ee3f3166d2ad216f928a75a0b9a2218
(Apache-2.0). A shared Docker daemon is not qualified by project name. The
admitted daemon id set in this file is empty, so the launcher returns
READINESS_BLOCKED and runs nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "receipt.schema.json"
PATCH_PATH = HERE / "topology.patch"
OVERRIDE_PATH = HERE / "offline.compose.yaml"
GIT = "/usr/bin/git"
DOCKER = "/usr/bin/docker"
DONOR_URL = "https://github.com/elie222/rakazo.git"
DONOR_COMMIT = "c5e66e010ee3f3166d2ad216f928a75a0b9a2218"
PATCH_SHA256 = "8e232c2024465066d33b255939b1a56d0cc46050d95efac1f39c3875a11e7712"
OVERRIDE_SHA256 = "bcb336b929cb6f7ba54645916afdef806eaa0c258e56ce8880b90c7b8983ef42"
UPSTREAM_TOPOLOGY_SHA256 = "1af4e4dd296c54aa23093c747bf4840b695f5da5877e659ea5f95af9a002dd74"
UPSTREAM_COMPOSE_SHA256 = "ca4297bda99a2bd2f1ba06a964e8a7572bbb9f7671ea3b9375f03572015252de"
DERIVED_TOPOLOGY_SHA256 = "ad2ad95e36510021f54e58013bd05aa07ee02e6bd329f01fc2df7452cc540ee3"
DERIVED_COMPOSE_SHA256 = "3e8e12ff5acd30a326d630f20c0660803532bb29f84da1508bf3bf815f82681c"
LOG_MAX_BYTES = 8192
EXECUTION_AUTHORIZED = False
ADMITTED_DAEMON_IDS: frozenset[str] = frozenset()
PROJECT_RE = re.compile(r"^mmx-rakazo-journey-[0-9a-f]{32}$")
NODE_CANDIDATES = ("/usr/bin/node", "/usr/local/bin/node", "/exec-daemon/node")
PNPM_CANDIDATES = ("/usr/bin/pnpm", "/usr/local/bin/pnpm")
DONOR_APP_IMAGE = "rakazo/app:topology"
DONOR_COMPUTER_IMAGE = "rakazo/computer:topology"
DONOR_PNPM = "9.15.0"
SHARED_DOCKER_ENDPOINTS = frozenset({
    "unix:///var/run/docker.sock",
    "npipe:////./pipe/docker_engine",
})
DEADLINES_SECONDS = {
    "overall": 180,
    "fetch": 90,
    "admit": 30,
    "derive": 20,
    "daemon_probe": 15,
    "toolchain_probe": 15,
    "hash_manifest": 10,
    "owned_cleanup": 20,
    "reap": 2,
    "execution": 900,
}
# Byte sizes of the pinned required blobs. The binary capture ceiling is the
# largest of those objects (pnpm-lock.yaml, 817721 bytes).
PINNED_BLOB_BYTES = {
    "packages/testkit/src/cli/topology.ts": 15316,
    "infra/compose/docker-compose.topology.yml": 6661,
    "package.json": 2880,
    "pnpm-lock.yaml": 817721,
    "pnpm-workspace.yaml": 93,
}
BINARY_OBJECT_CEILING = max(PINNED_BLOB_BYTES.values())
TRUNCATION_MARKER = "\n[truncated]"
MANIFEST_KEYS = (
    "config_manifest_sha256",
    "cache_manifest_sha256",
    "tmp_manifest_sha256",
    "source_manifest_sha256",
    "staging_manifest_sha256",
)
MANIFEST_MAX_FILES = 20000
MANIFEST_MAX_BYTES = 128 * 1024 * 1024
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
REQUIRED_BLOBS = {
    "packages/testkit/src/cli/topology.ts": {
        "git_blob": "6e56619314d78fecc1e3425a7b83d93ebd7bb190",
        "sha256": UPSTREAM_TOPOLOGY_SHA256,
    },
    "infra/compose/docker-compose.topology.yml": {
        "git_blob": "ae71f3743242b7a69b90198b59d907f9f5a3b9f6",
        "sha256": UPSTREAM_COMPOSE_SHA256,
    },
    "package.json": {
        "git_blob": "3f7685b6d87c4e269166c3bc22484eab1ca01b39",
        "sha256": "9f8c7ab2bd4ba6b50f5a66fc78bea92ed39a8c0154b3e96070eeb8b6013b740a",
    },
    "pnpm-lock.yaml": {
        "git_blob": "b7d840b21e81727a743dcc98134f05642e05cb40",
        "sha256": "6387f7a0e8783c8a01085dea0edeb718569e3a18443fc1d0fa75a47498931573",
    },
    "pnpm-workspace.yaml": {
        "git_blob": "f124691fa90eca20e1bbdfd4563af4c31594bfb3",
        "sha256": "25178b418b7047d388fd11f88a537d6a93cd10cc5bf1f5c26a8f1c8b57da6fc7",
    },
}
TOPOLOGY_REL = "packages/testkit/src/cli/topology.ts"
COMPOSE_REL = "infra/compose/docker-compose.topology.yml"
UPSTREAM_ASSERTIONS = (
    "topology-recovery-ok\\n",
    "run was not left queued while worker was stopped",
    "worker did not complete queued run",
    "unexpected sandbox file content",
    "Docker computer did not remain running",
    "Docker computer did not expose a screen",
    "expected one isolated computer network",
    "expected one computer peer",
    "isolated peer is not a managed computer",
    "computer hardening is incomplete",
    "unexpected isolated screen peers",
    "topology API did not become healthy",
    'body.jobs === "graphile"',
    'body.runtime === "scripted"',
    'body.sandbox === "docker"',
    "Graphile worker did not become ready",
    '"message":"worker ready"',
    "signup failed",
    "bots/remove",
    "notes/result.txt",
    'compose(["stop", "worker"])',
    'compose(["start", "worker"])',
)
COMPOSE_ASSERTIONS = (
    "127.0.0.1:${TOPOLOGY_API_PORT:-3199}:3100",
    "POSTGRES_USER: rakazo",
    "AGENT_RUNTIME: scripted",
    "WAKEUP_DRIVER: graphile",
    "SANDBOX_PROVIDER: docker",
    "${MMX_ADMITTED_DOCKER_SOCKET:?admitted-isolated-docker-socket-required}:/var/run/docker.sock",
)
FORBIDDEN_ARGV = frozenset({
    "compose", "pull", "build", "up", "prune", "rmi", "kill", "rm",
    "create", "start", "run", "exec", "checkout", "reset", "clean",
    "rebase", "push", "merge",
})
GIT_CONFIG_ARGS = (
    "-c", "core.fsmonitor=false",
    "-c", "core.untrackedCache=false",
    "-c", "core.hooksPath=/dev/null",
    "-c", "core.attributesFile=/dev/null",
    "-c", "core.excludesFile=/dev/null",
    "-c", "diff.external=",
    "-c", "filter.lfs.required=false",
    "-c", "filter.lfs.clean=",
    "-c", "filter.lfs.smudge=",
    "-c", "filter.lfs.process=",
    "-c", "credential.helper=",
    "-c", "protocol.allow=user",
    "-c", "protocol.https.allow=always",
    "-c", "protocol.file.allow=never",
    "-c", "protocol.ssh.allow=never",
)
ALLOWED_ENV_KEYS = frozenset({
    "PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ",
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM",
    "GIT_CONFIG_COUNT", "GIT_NO_REPLACE_OBJECTS", "GIT_ATTR_NOSYSTEM",
    "GIT_OPTIONAL_LOCKS", "GIT_NO_LAZY_FETCH", "GIT_TERMINAL_PROMPT",
    "GIT_PAGER", "GIT_EDITOR", "GIT_SEQUENCE_EDITOR", "GIT_ASKPASS",
    "GIT_SSH", "GIT_SSH_COMMAND", "SSH_ASKPASS",
    "NPM_CONFIG_USERCONFIG", "NPM_CONFIG_GLOBALCONFIG", "NPM_CONFIG_CACHE",
    "NPM_CONFIG_IGNORE_SCRIPTS", "npm_config_userconfig",
    "npm_config_globalconfig", "npm_config_cache", "npm_config_ignore_scripts",
    "PNPM_HOME", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "DOCKER_CONFIG",
    "PYTHONNOUSERSITE", "PYTHONSAFEPATH", "PYTHONDONTWRITEBYTECODE",
})
_LITERAL_SECRETS = (
    "topology-only-password",
    "topology-only-runtime-password",
    "topology-only-auth-secret-at-least-32-characters",
    "topology-only-supervisor-token-at-least-32-characters",
    "topology-only-encryption-key-at-least-32-characters",
    "topology-only-screen-proxy-secret-at-least-32-characters",
)
_SECRET_RE = re.compile(
    r"(?i)\b(token|secret|password|api[_-]?key|authorization)\b(\s*[:=]\s*)(\S+)"
)
_ENV_DUMP = (
    "import json,os,sys; "
    "json.dump({key: os.environ.get(key) for key in sorted(os.environ)}, sys.stdout)"
)
PLANNED_COMMAND = (
    "pnpm", "test:topology", "--", "--mmx-attempt", "<not-written>",
)
Spawn = Callable[..., "CommandRecord"]


class Refusal(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class OwnedRoot:
    path: Path
    token: str


@dataclass(frozen=True)
class CommandRecord:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    uncertain: bool
    stdout_bytes: bytes | None = None
    capture_refusal: str | None = None


class AttemptBudget:
    """One monotonic overall budget. Phase caps never restart it."""

    def __init__(self, *, now: Callable[[], float] | None = None, overall: float | None = None) -> None:
        self._now = now or time.monotonic
        self.started = self._now()
        self.overall = float(DEADLINES_SECONDS["overall"] if overall is None else overall)
        self.exhausted_phase: str | None = None
        self.uncertain = False
        self.blocked: str | None = None

    def elapsed(self) -> float:
        return self._now() - self.started

    def remaining(self) -> float:
        return self.overall - self.elapsed()

    def schedulable(self) -> float:
        return self.remaining() - float(DEADLINES_SECONDS["owned_cleanup"])

    def take(self, phase: str) -> float:
        if phase == "execution":
            raise Refusal("execution_not_authorized_for_initial_placement")
        reserve_phase = phase in {"owned_cleanup", "reap"}
        if self.blocked and not (self.blocked == "deadline_exhausted" and reserve_phase):
            raise Refusal(self.blocked)
        if phase not in DEADLINES_SECONDS:
            raise Refusal("deadline_exhausted")
        cap = float(DEADLINES_SECONDS[phase])
        left = self.remaining() if reserve_phase else self.schedulable()
        if left <= 0 or cap <= 0:
            if self.exhausted_phase is None:
                self.exhausted_phase = phase
            self.blocked = "deadline_exhausted"
            raise Refusal("deadline_exhausted")
        return min(cap, left)

    def mark_uncertain(self) -> None:
        self.uncertain = True
        self.blocked = "uncertain_child"

    def facts(self) -> dict[str, object]:
        return {
            "elapsed_seconds": self.elapsed(),
            "remaining_seconds": self.remaining(),
            "exhausted_phase": self.exhausted_phase,
            "cleanup_reserve_seconds": DEADLINES_SECONDS["owned_cleanup"],
            "reap_reserve_seconds": DEADLINES_SECONDS["reap"],
            "hash_budget_seconds": DEADLINES_SECONDS["hash_manifest"],
        }


@dataclass(frozen=True)
class DaemonObservation:
    source: str
    synthetic: bool
    binary: str | None
    endpoint: str | None
    daemon_id: str | None
    socket_present: bool
    metadata_complete: bool
    detail: str
    project_name: str | None = None


def assert_closed_env(env: Mapping[str, str]) -> None:
    if set(env) != ALLOWED_ENV_KEYS or env.get("PATH") != "/usr/bin:/bin":
        raise Refusal("environment_not_closed")
    if env.get("GIT_CONFIG_COUNT") != "0":
        raise Refusal("environment_not_closed")
    if "DOCKER_HOST" in env or "NODE_OPTIONS" in env:
        raise Refusal("environment_not_closed")
    for key, value in env.items():
        if "\0" in key or "\0" in value:
            raise Refusal("environment_not_closed")


def build_closed_env(owned: OwnedRoot) -> dict[str, str]:
    root = owned.path
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(root / "home"),
        "TMPDIR": str(root / "tmp"),
        "LANG": "C",
        "LC_ALL": "C",
        "TZ": "UTC",
        "GIT_CONFIG_GLOBAL": str(root / "config" / "gitconfig"),
        "GIT_CONFIG_SYSTEM": str(root / "config" / "gitconfig-system"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_COUNT": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_PAGER": "cat",
        "GIT_EDITOR": "/usr/bin/false",
        "GIT_SEQUENCE_EDITOR": "/usr/bin/false",
        "GIT_ASKPASS": "/usr/bin/false",
        "GIT_SSH": "/usr/bin/false",
        "GIT_SSH_COMMAND": "/usr/bin/false",
        "SSH_ASKPASS": "/usr/bin/false",
        "NPM_CONFIG_USERCONFIG": str(root / "config" / "npmrc"),
        "NPM_CONFIG_GLOBALCONFIG": str(root / "config" / "npmrc-global"),
        "NPM_CONFIG_CACHE": str(root / "cache" / "npm"),
        "NPM_CONFIG_IGNORE_SCRIPTS": "true",
        "npm_config_userconfig": str(root / "config" / "npmrc"),
        "npm_config_globalconfig": str(root / "config" / "npmrc-global"),
        "npm_config_cache": str(root / "cache" / "npm"),
        "npm_config_ignore_scripts": "true",
        "PNPM_HOME": str(root / "cache" / "pnpm"),
        "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_CONFIG_HOME": str(root / "config"),
        "DOCKER_CONFIG": str(root / "config" / "docker"),
        "PYTHONNOUSERSITE": "1",
        "PYTHONSAFEPATH": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    assert_closed_env(env)
    return env


def assert_readiness_argv(argv: Sequence[str]) -> None:
    for item in argv:
        if item in FORBIDDEN_ARGV or item.startswith("--prune"):
            raise Refusal("readiness_forbids_topology_execution")


def redact(text: str, *, truncated: bool = False) -> str:
    """Redact, then fit the text plus a truncation marker inside the log cap."""
    cleaned = _SECRET_RE.sub(r"\1\2[redacted]", text)
    for literal in _LITERAL_SECRETS:
        cleaned = cleaned.replace(literal, "[redacted]")
    raw = cleaned.encode("utf-8", errors="replace")
    marker = TRUNCATION_MARKER.encode("utf-8")
    if not truncated and len(raw) <= LOG_MAX_BYTES:
        return cleaned
    room = LOG_MAX_BYTES - len(marker)
    clipped = raw[:room]
    text_out = clipped.decode("utf-8", errors="ignore")
    while text_out and len(text_out.encode("utf-8")) + len(marker) > LOG_MAX_BYTES:
        text_out = text_out[:-1]
    return text_out + TRUNCATION_MARKER


def _group_gone(pid: int) -> bool:
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return False


def _reap_owned_group(proc: subprocess.Popen[bytes], seconds: float) -> tuple[bool, int]:
    """SIGKILL and wait only for this process group. False means uncertain."""
    pid = proc.pid
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        return False, -1
    for stream in (proc.stdin, proc.stdout, proc.stderr):
        if stream is not None:
            try:
                stream.close()
            except OSError:
                return False, -1
    try:
        code = proc.wait(timeout=max(0.0, seconds))
    except (subprocess.TimeoutExpired, OSError):
        return False, -1
    if not _group_gone(pid):
        return False, code if code is not None else -1
    return True, code if code is not None else -1


def _read_capped(fd: int, buf: bytearray, *, binary: bool, ceiling: int) -> tuple[bool, bool]:
    """Read into buf up to ceiling. Returns (eof, overflow). Overflow is not stored."""
    room = ceiling - len(buf)
    if room <= 0:
        try:
            extra = os.read(fd, 1)
        except BlockingIOError:
            return False, False
        except OSError:
            return True, False
        return (not extra), bool(extra)
    try:
        chunk = os.read(fd, min(65536, room))
    except BlockingIOError:
        return False, False
    except OSError:
        return True, False
    if not chunk:
        return True, False
    buf += chunk
    return False, False


def default_spawn(
    argv: Sequence[str],
    *,
    env: Mapping[str, str],
    cwd: Path | None,
    timeout: float,
    binary: bool = False,
    stdin_bytes: bytes | None = None,
    budget: AttemptBudget | None = None,
) -> CommandRecord:
    """Stream child output with a hard ceiling. Do not buffer via communicate()."""
    assert_closed_env(env)
    assert_readiness_argv(tuple(argv))
    proc = subprocess.Popen(
        list(argv),
        cwd=None if cwd is None else str(cwd),
        env=dict(env),
        stdin=subprocess.PIPE if stdin_bytes is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    assert proc.stdout is not None and proc.stderr is not None
    out_buf = bytearray()
    err_buf = bytearray()
    out_fd = proc.stdout.fileno()
    err_fd = proc.stderr.fileno()
    os.set_blocking(out_fd, False)
    os.set_blocking(err_fd, False)
    stdin_fd = None
    stdin_pos = 0
    stdin_view = memoryview(stdin_bytes) if stdin_bytes else None
    if proc.stdin is not None and stdin_view is not None:
        stdin_fd = proc.stdin.fileno()
        os.set_blocking(stdin_fd, False)
    elif proc.stdin is not None:
        proc.stdin.close()
    out_open = True
    err_open = True
    binary_overflow = False
    out_capped = False
    err_capped = False
    timed_out = False
    deadline = time.monotonic() + max(0.0, float(timeout))
    text_ceiling = LOG_MAX_BYTES
    out_ceiling = BINARY_OBJECT_CEILING if binary else text_ceiling
    while out_open or err_open or stdin_fd is not None:
        if time.monotonic() >= deadline:
            timed_out = True
            break
        readable = [fd for fd, open_ in ((out_fd, out_open), (err_fd, err_open)) if open_]
        writable = [stdin_fd] if stdin_fd is not None else []
        if not readable and not writable:
            break
        wait = max(0.0, deadline - time.monotonic())
        ready_r, ready_w, _ = select.select(readable, writable, [], min(0.05, wait))
        if stdin_fd is not None and stdin_fd in ready_w and stdin_view is not None:
            try:
                written = os.write(stdin_fd, stdin_view[stdin_pos:stdin_pos + 65536])
            except BlockingIOError:
                written = 0
            except OSError:
                written = 0
                stdin_fd = None
            stdin_pos += written
            if stdin_view is not None and stdin_pos >= len(stdin_view):
                if proc.stdin is not None:
                    proc.stdin.close()
                stdin_fd = None
        if out_fd in ready_r and out_open:
            eof, overflow = _read_capped(out_fd, out_buf, binary=binary, ceiling=out_ceiling)
            if overflow:
                if binary:
                    binary_overflow = True
                else:
                    out_capped = True
                break
            if eof:
                out_open = False
        if err_fd in ready_r and err_open:
            eof, overflow = _read_capped(err_fd, err_buf, binary=False, ceiling=text_ceiling)
            if overflow:
                err_capped = True
                break
            if eof:
                err_open = False
        if proc.poll() is not None and not ready_r and not ready_w and not out_open and not err_open:
            break
    if proc.poll() is None and not timed_out and not binary_overflow and not out_capped and not err_capped:
        try:
            proc.wait(timeout=min(1.0, max(0.05, float(timeout))))
        except subprocess.TimeoutExpired:
            timed_out = True
    capture_refusal = "binary_capture_exceeded" if binary_overflow else None
    uncertain = False
    must_stop = timed_out or binary_overflow or out_capped or err_capped or proc.poll() is None or not _group_gone(proc.pid)
    if must_stop:
        if budget is None:
            reap_seconds = float(DEADLINES_SECONDS["reap"])
        else:
            reap_seconds = min(float(DEADLINES_SECONDS["reap"]), max(0.0, budget.remaining()))
        reaped, code = _reap_owned_group(proc, reap_seconds)
        uncertain = not reaped
        returncode = code
    else:
        returncode = proc.returncode if proc.returncode is not None else 0
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is not None and not stream.closed:
                stream.close()
    if binary_overflow:
        out_buf.clear()
    stdout_text = ""
    if not binary:
        stdout_text = redact(bytes(out_buf).decode("utf-8", errors="replace"), truncated=out_capped)
    stderr_text = redact(bytes(err_buf).decode("utf-8", errors="replace"), truncated=err_capped)
    if len(stdout_text.encode("utf-8")) > LOG_MAX_BYTES:
        stdout_text = redact(stdout_text, truncated=True)
    if len(stderr_text.encode("utf-8")) > LOG_MAX_BYTES:
        stderr_text = redact(stderr_text, truncated=True)
    kept = bytes(out_buf) if binary and not binary_overflow else None
    return CommandRecord(
        tuple(argv),
        returncode,
        stdout_text,
        stderr_text,
        timed_out,
        uncertain,
        kept,
        capture_refusal,
    )


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def create_owned_root() -> OwnedRoot:
    path = Path(tempfile.mkdtemp(prefix="mmx-rakazo-journey-"))
    try:
        if path.is_symlink() or path.resolve() != path:
            raise Refusal("owned_root_unresolved")
        token = secrets.token_hex(32)
        os.chmod(path, 0o700)
        for name in (
            "config", "config/docker", "cache", "cache/npm", "cache/pnpm",
            "tmp", "home", "staging", "source",
        ):
            directory = path / name
            directory.mkdir(parents=True, exist_ok=True)
            os.chmod(directory, 0o700)
        _write(path / ".mmx-owned", token + "\n")
        _write(
            path / "config" / "gitconfig",
            """[core]
	hooksPath = /dev/null
	fsmonitor =
	attributesFile = /dev/null
	excludesFile = /dev/null
[diff]
	external =
[filter "lfs"]
	required = false
	clean =
	smudge =
	process =
[credential]
	helper =
[protocol]
	allow = user
[protocol "https"]
	allow = always
[protocol "file"]
	allow = never
[protocol "ssh"]
	allow = never
[init]
	defaultBranch = master
""",
        )
        _write(path / "config" / "gitconfig-system", "")
        npmrc = "ignore-scripts=true\nfund=false\naudit=false\n"
        _write(path / "config" / "npmrc", npmrc)
        _write(path / "config" / "npmrc-global", npmrc)
        _write(path / "config" / "docker" / "config.json", "{}\n")
        return OwnedRoot(path, token)
    except OSError:
        shutil.rmtree(path, ignore_errors=True)
        raise


def _marker_ok(owned: OwnedRoot) -> bool:
    path = owned.path
    if not owned.token or path.is_symlink() or not path.is_dir():
        return False
    try:
        if path.resolve() != path:
            return False
    except OSError:
        return False
    if path.parent != Path(tempfile.gettempdir()):
        return False
    if not path.name.startswith("mmx-rakazo-journey-"):
        return False
    marker = path / ".mmx-owned"
    if not marker.is_file() or marker.is_symlink():
        return False
    try:
        return marker.read_text(encoding="utf-8").strip() == owned.token
    except OSError:
        return False


def remove_owned_root(owned: OwnedRoot) -> str:
    if not _marker_ok(owned):
        return "REFUSED"
    try:
        shutil.rmtree(owned.path)
    except OSError:
        return "UNKNOWN"
    if owned.path.exists():
        return "UNKNOWN"
    return "REMOVED"


def directory_manifest_sha256(
    root: Path,
    budget: AttemptBudget,
    *,
    max_files: int = MANIFEST_MAX_FILES,
    max_bytes: int = MANIFEST_MAX_BYTES,
) -> str:
    """Hash an owned directory without following symlinks or walking off the clock."""
    lines: list[str] = []
    files = 0
    total = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        if budget.remaining() <= 0:
            budget.exhausted_phase = budget.exhausted_phase or "hash_manifest"
            budget.blocked = "deadline_exhausted"
            raise Refusal("deadline_exhausted")
        kept: list[str] = []
        for name in sorted(dirnames):
            candidate = Path(dirpath) / name
            if candidate.is_symlink():
                raise Refusal("symlink_in_owned_root")
            kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.is_symlink():
                raise Refusal("symlink_in_owned_root")
            files += 1
            if files > max_files:
                raise Refusal("manifest_bound_exceeded")
            data = path.read_bytes()
            total += len(data)
            if total > max_bytes:
                raise Refusal("manifest_bound_exceeded")
            rel = path.relative_to(root).as_posix()
            digest = hashlib.sha256(data).hexdigest()
            mode = oct(path.stat().st_mode & 0o777)
            lines.append(f"{rel}\0{mode}\0{digest}")
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _invoke(
    spawn: Spawn,
    argv: Sequence[str],
    *,
    phase: str,
    budget: AttemptBudget | None,
    **kwargs: object,
) -> CommandRecord:
    """Cap this command by the remaining overall budget. Do not restart it."""
    if budget is None:
        kwargs.setdefault("timeout", float(DEADLINES_SECONDS[phase]))
    else:
        kwargs["timeout"] = budget.take(phase)
        kwargs["budget"] = budget
    record = spawn(argv, **kwargs)
    if not isinstance(record, CommandRecord):
        raise Refusal("spawn_contract")
    if budget is not None and record.uncertain:
        budget.mark_uncertain()
        raise Refusal("uncertain_child")
    if record.capture_refusal:
        raise Refusal(record.capture_refusal)
    return record


def validate_git_dir(path: Path) -> Path:
    if not path.is_absolute() or any(part == ".." for part in path.parts):
        raise Refusal("relative_object_store" if not path.is_absolute() else "path_traversal")
    if path.is_symlink():
        raise Refusal("symlink_path_refused")
    try:
        if path.resolve() != path:
            raise Refusal("symlink_path_refused")
    except OSError as exc:
        raise Refusal("object_store_unreadable") from exc
    if not path.is_dir():
        raise Refusal("object_store_not_directory")
    return path


def git_argv(git_dir: Path | None, *args: str) -> list[str]:
    argv = [GIT, "--no-replace-objects", *GIT_CONFIG_ARGS]
    if git_dir is not None:
        argv.append(f"--git-dir={git_dir}")
    argv.extend(args)
    return argv


def _failed(record: CommandRecord) -> bool:
    return record.returncode != 0 or record.timed_out or record.uncertain


def _git_text(
    spawn: Spawn, env: Mapping[str, str], cwd: Path, git_dir: Path | None,
    args: Sequence[str], timeout: float, stdin_bytes: bytes | None = None,
    budget: AttemptBudget | None = None,
) -> str:
    del timeout
    record = _invoke(
        spawn, git_argv(git_dir, *args), phase="admit", budget=budget,
        env=env, cwd=cwd, binary=False, stdin_bytes=stdin_bytes,
    )
    if _failed(record):
        raise Refusal("git_command_failed")
    return record.stdout.strip()


def _git_bytes(
    spawn: Spawn, env: Mapping[str, str], cwd: Path, git_dir: Path,
    args: Sequence[str], budget: AttemptBudget | None = None,
) -> bytes:
    record = _invoke(
        spawn, git_argv(git_dir, *args), phase="admit", budget=budget,
        env=env, cwd=cwd, binary=True, stdin_bytes=None,
    )
    if _failed(record) or record.stdout_bytes is None:
        raise Refusal("git_command_failed")
    return record.stdout_bytes


def admit_source(
    git_dir: Path,
    *,
    owned: OwnedRoot,
    env: Mapping[str, str],
    spawn: Spawn,
    budget: AttemptBudget | None = None,
) -> dict[str, bytes]:
    """Verify immutable donor objects. A caller checkout is not adopted."""
    git_dir = validate_git_dir(git_dir)
    cwd = owned.path / "tmp"

    def _text(git: Path | None, args: Sequence[str], stdin_bytes: bytes | None = None) -> str:
        return _git_text(spawn, env, cwd, git, args, 0, stdin_bytes, budget)

    def _bytes(git: Path, args: Sequence[str]) -> bytes:
        return _git_bytes(spawn, env, cwd, git, args, budget)

    try:
        commit = _text(git_dir, ("rev-parse", f"{DONOR_COMMIT}^{{commit}}"))
    except Refusal as exc:
        if exc.reason in {"uncertain_child", "deadline_exhausted", "binary_capture_exceeded"}:
            raise
        raise Refusal("pin_not_present") from exc
    if commit != DONOR_COMMIT:
        raise Refusal("pin_mismatch")
    blobs: dict[str, bytes] = {}
    identities: dict[str, dict[str, str]] = {}
    for rel, expected in REQUIRED_BLOBS.items():
        try:
            blob = _text(git_dir, ("rev-parse", f"{DONOR_COMMIT}:{rel}"))
        except Refusal as exc:
            if exc.reason in {"uncertain_child", "deadline_exhausted", "binary_capture_exceeded"}:
                raise
            raise Refusal("blob_mismatch") from exc
        if blob != expected["git_blob"]:
            raise Refusal("blob_mismatch")
        data = _bytes(git_dir, ("cat-file", "blob", blob))
        if len(data) != PINNED_BLOB_BYTES[rel] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
            raise Refusal("byte_mismatch")
        hashed = _text(None, ("hash-object", "--no-filters", "--stdin"), data)
        if hashed != expected["git_blob"]:
            raise Refusal("filter_or_replace_mismatch")
        destination = owned.path / "source" / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        blobs[rel] = data
        identities[rel] = {"git_blob": blob, "sha256": expected["sha256"]}
    blobs["__identities__"] = json.dumps(identities, sort_keys=True).encode("utf-8")
    return blobs


def _assert_override_contract(text: str) -> None:
    if "image: rakazo/" in text or ":topology" in text:
        raise Refusal("override_contract_mismatch")
    try:
        api = text.split("\n  api:\n", 1)[1].split("\n  web:\n", 1)[0]
        worker = text.split("\n  worker:\n", 1)[1]
    except IndexError as exc:
        raise Refusal("override_contract_mismatch") from exc
    for block in (api, worker):
        if 'RAKAZO_LIVE_MODEL_CATALOG: "off"' not in block:
            raise Refusal("override_contract_mismatch")
        if "AGENT_RUNTIME: scripted" not in block or "WAKEUP_DRIVER: graphile" not in block:
            raise Refusal("override_contract_mismatch")
        if "SANDBOX_PROVIDER: docker" not in block:
            raise Refusal("override_contract_mismatch")


def _assert_derived(topology: str, compose: str) -> None:
    missing = [item for item in UPSTREAM_ASSERTIONS if item not in topology]
    if missing or "process.env" in topology:
        raise Refusal("upstream_assertion_removed")
    if any(item not in compose for item in COMPOSE_ASSERTIONS):
        raise Refusal("upstream_assertion_removed")
    if "      - /var/run/docker.sock:/var/run/docker.sock\n" in compose:
        raise Refusal("shared_docker_socket_retained")


def derive_runner(
    blobs: Mapping[str, bytes],
    *,
    owned: OwnedRoot,
    env: Mapping[str, str],
    spawn: Spawn,
    patch_bytes: bytes | None = None,
    override_bytes: bytes | None = None,
    budget: AttemptBudget | None = None,
) -> dict[str, str]:
    """Apply the reviewed patch only after the pinned bytes match."""
    patch = PATCH_PATH.read_bytes() if patch_bytes is None else patch_bytes
    override = OVERRIDE_PATH.read_bytes() if override_bytes is None else override_bytes
    if hashlib.sha256(patch).hexdigest() != PATCH_SHA256:
        raise Refusal("patch_hash_mismatch")
    if hashlib.sha256(override).hexdigest() != OVERRIDE_SHA256:
        raise Refusal("override_hash_mismatch")
    _assert_override_contract(override.decode("utf-8"))
    topology = blobs[TOPOLOGY_REL]
    compose = blobs[COMPOSE_REL]
    if hashlib.sha256(topology).hexdigest() != UPSTREAM_TOPOLOGY_SHA256:
        raise Refusal("source_anchor_mismatch")
    if hashlib.sha256(compose).hexdigest() != UPSTREAM_COMPOSE_SHA256:
        raise Refusal("source_anchor_mismatch")
    staging = owned.path / "staging"
    topo_path = staging / TOPOLOGY_REL
    compose_path = staging / COMPOSE_REL
    topo_path.parent.mkdir(parents=True, exist_ok=True)
    compose_path.parent.mkdir(parents=True, exist_ok=True)
    topo_path.write_bytes(topology)
    compose_path.write_bytes(compose)
    patch_path = owned.path / "config" / "topology.patch"
    patch_path.write_bytes(patch)
    (staging / "offline.compose.yaml").write_bytes(override)
    applied = _invoke(
        spawn,
        git_argv(None, "apply", "--unidiff-zero", "--whitespace=nowarn", str(patch_path)),
        phase="derive", budget=budget,
        env=env, cwd=staging, binary=False, stdin_bytes=None,
    )
    if _failed(applied):
        raise Refusal("source_anchor_mismatch")
    derived_topology = topo_path.read_bytes()
    derived_compose = compose_path.read_bytes()
    if hashlib.sha256(derived_topology).hexdigest() != DERIVED_TOPOLOGY_SHA256:
        raise Refusal("derived_hash_mismatch")
    if hashlib.sha256(derived_compose).hexdigest() != DERIVED_COMPOSE_SHA256:
        raise Refusal("derived_hash_mismatch")
    _assert_derived(derived_topology.decode("utf-8"), derived_compose.decode("utf-8"))
    return {
        "patch_sha256": PATCH_SHA256,
        "override_sha256": OVERRIDE_SHA256,
        "derived_topology_sha256": DERIVED_TOPOLOGY_SHA256,
        "derived_compose_sha256": DERIVED_COMPOSE_SHA256,
    }


def fetch_donor(
    owned: OwnedRoot, env: Mapping[str, str], spawn: Spawn, budget: AttemptBudget | None = None,
) -> Path:
    repo = owned.path / "source" / "donor.git"
    cwd = owned.path / "tmp"
    init = _invoke(
        spawn, git_argv(None, "init", "--bare", str(repo)),
        phase="fetch", budget=budget, env=env, cwd=cwd, binary=False, stdin_bytes=None,
    )
    if _failed(init):
        raise Refusal("fetch_failed")
    fetched = _invoke(
        spawn,
        git_argv(
            repo, "fetch", "--depth=1", "--no-tags", "--no-recurse-submodules",
            DONOR_URL, DONOR_COMMIT,
        ),
        phase="fetch", budget=budget, env=env, cwd=cwd, binary=False, stdin_bytes=None,
    )
    if _failed(fetched):
        raise Refusal("fetch_failed")
    return repo


def endpoint_from_context(text: str) -> str | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, list):
        if len(payload) != 1 or not isinstance(payload[0], dict):
            return None
        payload = payload[0]
    if not isinstance(payload, dict):
        return None
    endpoints = payload.get("Endpoints")
    if not isinstance(endpoints, dict):
        return None
    docker = endpoints.get("docker")
    if not isinstance(docker, dict):
        return None
    host = docker.get("Host")
    return host if isinstance(host, str) else None


def qualify_observation(obs: DaemonObservation) -> dict[str, object]:
    """Project name is ignored. Synthetic fixtures and caller strings do not admit."""
    verdict: dict[str, object] = {
        "state": "UNQUALIFIED",
        "synthetic": obs.synthetic,
        "binary": obs.binary,
        "endpoint": obs.endpoint,
        "daemon_id": obs.daemon_id,
        "socket_present": obs.socket_present,
        "admitted_daemon_ids": [],
        "project_name_qualifies_shared_daemon": False,
        "reason": "docker_binary_absent",
    }
    if obs.synthetic:
        verdict["reason"] = "synthetic_fixture_is_not_daemon_authority"
        return verdict
    if obs.source == "absent" or obs.binary != DOCKER:
        verdict["reason"] = "docker_binary_absent" if obs.source == "absent" else "docker_binary_not_exact"
        return verdict
    if not obs.metadata_complete:
        verdict["reason"] = "daemon_metadata_unreadable"
        return verdict
    endpoint = obs.endpoint or ""
    if endpoint in SHARED_DOCKER_ENDPOINTS or endpoint == "":
        verdict["reason"] = "shared_default_socket"
        return verdict
    if endpoint.startswith(("tcp:", "ssh:", "http:", "https:")):
        verdict["reason"] = "remote_context_refused"
        return verdict
    if obs.daemon_id not in ADMITTED_DAEMON_IDS:
        verdict["reason"] = "daemon_id_not_admitted"
        return verdict
    verdict["reason"] = "daemon_id_not_admitted"
    return verdict


def _exact_executable(path: str) -> bool:
    candidate = Path(path)
    return candidate.is_file() and not candidate.is_symlink() and os.access(candidate, os.X_OK)


def probe_daemon(
    env: Mapping[str, str], spawn: Spawn, cwd: Path, budget: AttemptBudget | None = None,
) -> dict[str, object]:
    socket_present = Path("/var/run/docker.sock").exists() or Path("/run/docker.sock").exists()
    if not _exact_executable(DOCKER):
        return qualify_observation(DaemonObservation(
            "absent", False, None, None, None, socket_present, False, "docker_binary_absent",
        ))
    info = _invoke(
        spawn, [DOCKER, "info", "--format", "{{.ID}}"],
        phase="daemon_probe", budget=budget, env=env, cwd=cwd, binary=False, stdin_bytes=None,
    )
    context = _invoke(
        spawn, [DOCKER, "context", "inspect"],
        phase="daemon_probe", budget=budget, env=env, cwd=cwd, binary=False, stdin_bytes=None,
    )
    complete = not _failed(info) and not _failed(context) and bool(info.stdout.strip())
    endpoint = endpoint_from_context(context.stdout) if complete else None
    if endpoint is None:
        complete = False
    return qualify_observation(DaemonObservation(
        "local-binary", False, DOCKER, endpoint, info.stdout.strip() or None,
        socket_present, complete, "probed",
    ))


def node_satisfies(version: str | None) -> bool:
    if version is None:
        return False
    match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", version.strip())
    if match is None:
        return False
    major, minor, patch = (int(item) for item in match.groups())
    if major == 22:
        return (minor, patch) >= (22, 2)
    if major == 24:
        return True
    return major >= 26


def _first_version(
    candidates: Sequence[str],
    env: Mapping[str, str],
    spawn: Spawn,
    cwd: Path,
    budget: AttemptBudget | None = None,
) -> tuple[str | None, str | None]:
    for candidate in candidates:
        if not _exact_executable(candidate):
            continue
        record = _invoke(
            spawn, [candidate, "--version"],
            phase="toolchain_probe", budget=budget, env=env, cwd=cwd, binary=False, stdin_bytes=None,
        )
        if _failed(record):
            continue
        line = record.stdout.strip().splitlines()
        if not line:
            continue
        return candidate, line[0].strip()
    return None, None


def probe_toolchain(
    env: Mapping[str, str], spawn: Spawn, cwd: Path, budget: AttemptBudget | None = None,
) -> dict[str, object]:
    git_state: dict[str, object] = {"path": GIT, "version": None, "state": "ABSENT"}
    if _exact_executable(GIT):
        record = _invoke(
            spawn, [GIT, "--version"],
            phase="toolchain_probe", budget=budget, env=env, cwd=cwd, binary=False, stdin_bytes=None,
        )
        if not _failed(record) and record.stdout.strip():
            git_state = {"path": GIT, "version": record.stdout.strip().splitlines()[0], "state": "OBSERVED"}
    node_path, node_version = _first_version(NODE_CANDIDATES, env, spawn, cwd, budget)
    pnpm_path, pnpm_version = _first_version(PNPM_CANDIDATES, env, spawn, cwd, budget)
    pnpm_state = "ABSENT"
    if pnpm_version == DONOR_PNPM:
        pnpm_state = "EXACT"
    elif pnpm_version is not None:
        pnpm_state = "MISMATCH"
    return {
        "git": git_state,
        "node": {
            "path": node_path,
            "version": node_version,
            "state": "OBSERVED" if node_version else "ABSENT",
            "satisfies_donor_engine": node_satisfies(node_version),
        },
        "pnpm": {
            "path": pnpm_path,
            "version": pnpm_version,
            "required": DONOR_PNPM,
            "state": pnpm_state,
        },
        "adopted_for_execution": False,
    }


def new_identity() -> dict[str, object]:
    attempt = secrets.token_hex(16)
    project = f"mmx-rakazo-journey-{attempt}"
    app_image = f"mmx-rakazo-journey/app:{attempt}"
    computer_image = f"mmx-rakazo-journey/computer:{attempt}"
    if not PROJECT_RE.fullmatch(project):
        raise Refusal("identity_collision")
    if app_image in {DONOR_APP_IMAGE, DONOR_COMPUTER_IMAGE} or computer_image.startswith("rakazo/"):
        raise Refusal("identity_collision")
    return {
        "project": project,
        "app_image": app_image,
        "computer_image": computer_image,
        "docker_resources_created": False,
    }


def classify_cleanup(
    *,
    exit_code: int | None,
    before: Sequence[str] | None,
    after: Sequence[str] | None,
    observation_present: bool,
    owned_project_only: bool,
) -> str:
    """Exit zero without a before/after observation stays UNKNOWN."""
    if exit_code is None and not observation_present:
        return "NOT_RUN"
    if not observation_present or before is None or after is None:
        return "UNKNOWN"
    if not owned_project_only:
        return "REFUSED"
    if exit_code != 0 or list(after) != []:
        return "UNKNOWN"
    return "CORROBORATED"


def _attempt_images(attempt: str) -> tuple[str, str]:
    return (
        f"mmx-rakazo-journey/app:{attempt}",
        f"mmx-rakazo-journey/computer:{attempt}",
    )


def plan_owned_cleanup(project: str, images: Sequence[str]) -> tuple[tuple[str, ...], ...]:
    """Name the future cleanup of this attempt's two images.

    Matching those names is not daemon admission. The admitted id set stays
    empty, and this planner is not spawned during readiness.
    """
    if not PROJECT_RE.fullmatch(project):
        raise Refusal("unowned_project")
    attempt = project[len("mmx-rakazo-journey-"):]
    expected = _attempt_images(attempt)
    for image in images:
        if image in {DONOR_APP_IMAGE, DONOR_COMPUTER_IMAGE} or image.startswith("rakazo/") or image.endswith(":topology"):
            raise Refusal("donor_image_tag")
    if tuple(images) != expected:
        raise Refusal("unowned_image")
    commands = [
        (DOCKER, "compose", "--project-name", project, "down", "--volumes", "--remove-orphans"),
        (DOCKER, "image", "rm", expected[0]),
        (DOCKER, "image", "rm", expected[1]),
    ]
    for argv in commands:
        if "prune" in argv or "system" in argv:
            raise Refusal("host_prune_forbidden")
    return tuple(tuple(item) for item in commands)


def execute_journey() -> dict[str, object]:
    """Initial placement cannot open this gate, including via a caller flag."""
    if EXECUTION_AUTHORIZED or ADMITTED_DAEMON_IDS:
        raise Refusal("execution_gate_inconsistent")
    return {
        "state": "NOT_RUN",
        "authorized": False,
        "spawned": False,
        "reason": "execution_not_authorized_for_initial_placement",
        "planned_command": list(PLANNED_COMMAND),
    }


def _hash_cause(key: str) -> str:
    return key.replace("_sha256", "_cause")


def _unavailable_hashes(cause: str) -> dict[str, str | None]:
    hashes: dict[str, str | None] = {
        "patch_sha256": PATCH_SHA256,
        "override_sha256": OVERRIDE_SHA256,
    }
    for key in MANIFEST_KEYS:
        hashes[key] = None
        hashes[_hash_cause(key)] = cause
    return hashes


def _manifests_measured(hashes: Mapping[str, object]) -> bool:
    for key in MANIFEST_KEYS:
        value = hashes.get(key)
        cause = hashes.get(_hash_cause(key))
        if not isinstance(value, str) or len(value) != 64 or cause is not None:
            return False
    return True


def _owned_hashes(owned: OwnedRoot, budget: AttemptBudget) -> dict[str, str | None]:
    hashes: dict[str, str | None] = {
        "patch_sha256": PATCH_SHA256,
        "override_sha256": OVERRIDE_SHA256,
    }
    mapping = {
        "config_manifest_sha256": owned.path / "config",
        "cache_manifest_sha256": owned.path / "cache",
        "tmp_manifest_sha256": owned.path / "tmp",
        "source_manifest_sha256": owned.path / "source",
        "staging_manifest_sha256": owned.path / "staging",
    }
    for key, directory in mapping.items():
        try:
            budget.take("hash_manifest")
            hashes[key] = directory_manifest_sha256(directory, budget)
            hashes[_hash_cause(key)] = None
        except Refusal as exc:
            hashes[key] = None
            hashes[_hash_cause(key)] = exc.reason
        except OSError:
            hashes[key] = None
            hashes[_hash_cause(key)] = "manifest_unreadable"
    return hashes


def _command_public(record: CommandRecord) -> dict[str, object]:
    return {
        "argv": list(record.argv),
        "returncode": record.returncode,
        "timed_out": record.timed_out,
        "uncertain": record.uncertain,
        "stdout": record.stdout,
        "stderr": record.stderr,
    }


def build_receipt(
    *,
    source_state: str,
    source_reason: str,
    blobs: dict[str, dict[str, str]],
    derivation_state: str,
    derivation_reason: str,
    assertions: bool | None,
    derived: dict[str, str],
    identity: dict[str, object],
    daemon: dict[str, object],
    toolchain: dict[str, object],
    env_keys: Sequence[str],
    owned_root: str,
    hashes: Mapping[str, str | None],
    commands: Sequence[CommandRecord],
    notes: Sequence[str],
    budget: AttemptBudget | None = None,
    evidence_complete: bool | None = None,
) -> dict[str, object]:
    measured = _manifests_measured(hashes) if evidence_complete is None else evidence_complete
    prepared = source_state == "ADMITTED" and derivation_state == "PREPARED" and measured
    if source_state == "REFUSED" or derivation_state == "REFUSED":
        source_phase = "REFUSED"
    elif prepared:
        source_phase = "SOURCE_PREPARED"
    else:
        source_phase = "NOT_PREPARED"
    execution = execute_journey()
    receipt: dict[str, object] = {
        "schema_version": 1,
        "status": "READINESS_BLOCKED",
        "task": "HC-P1B.T2",
        "placement": "SOURCE_PREPARATION_AND_READINESS_ONLY",
        "source_phase": source_phase,
        "donor": {
            "repository": DONOR_URL,
            "commit": DONOR_COMMIT,
            "license": "Apache-2.0",
        },
        "source": {"state": source_state, "reason": source_reason, "blobs": blobs},
        "derivation": {
            "state": derivation_state,
            "reason": derivation_reason,
            "upstream_assertions_preserved": assertions,
            **derived,
        },
        "identity": identity,
        "daemon": daemon,
        "toolchain": toolchain,
        "environment": {
            "sealed_before_child": True,
            "inherited_caller_environment": False,
            "keys": list(env_keys),
        },
        "execution": execution,
        "cleanup": {
            "resource_cleanup": "NOT_RUN",
            "owned_root": owned_root,
            "exit_zero_is_clean_receipt": False,
            "host_prune": False,
            "absence_of_log_is_absence_of_effects": False,
        },
        "hashes": hashes,
        "limits": {
            "deadlines_seconds": dict(DEADLINES_SECONDS),
            "log_max_bytes": LOG_MAX_BYTES,
            "execution_armed": False,
            "automatic_retry": False,
            "notes": list(notes),
            "budget": (budget or AttemptBudget(now=lambda: 0.0, overall=0.0)).facts() if budget is not None else {
                "elapsed_seconds": None,
                "remaining_seconds": None,
                "exhausted_phase": None,
                "cleanup_reserve_seconds": DEADLINES_SECONDS["owned_cleanup"],
                "reap_reserve_seconds": DEADLINES_SECONDS["reap"],
                "hash_budget_seconds": DEADLINES_SECONDS["hash_manifest"],
            },
        },
        "commands": [_command_public(item) for item in commands],
    }
    return receipt


def _validate(instance: object, schema: object, path: str, errors: list[str]) -> None:
    if schema is False:
        errors.append(path or "$")
        return
    if schema is True or not isinstance(schema, dict):
        return
    if "allOf" in schema:
        for index, subschema in enumerate(schema["allOf"]):
            _validate(instance, subschema, f"{path}/allOf/{index}", errors)
    if "if" in schema:
        probe: list[str] = []
        _validate(instance, schema["if"], path, probe)
        if not probe:
            _validate(instance, schema.get("then", True), path, errors)
    expected = schema.get("type")
    if expected is not None and not _type_ok(instance, expected):
        errors.append(f"{path}: type")
        return
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: const")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: enum")
    if isinstance(instance, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                errors.append(f"{path}: missing {key}")
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in properties:
                    errors.append(f"{path}: extra {key}")
        for key, subschema in properties.items():
            if key in instance:
                _validate(instance[key], subschema, f"{path}/{key}", errors)
    if isinstance(instance, list):
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: maxItems")
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(instance):
                _validate(item, item_schema, f"{path}/{index}", errors)


def _type_ok(instance: object, expected: object) -> bool:
    kinds = expected if isinstance(expected, list) else [expected]
    for kind in kinds:
        if kind == "object" and isinstance(instance, dict):
            return True
        if kind == "array" and isinstance(instance, list):
            return True
        if kind == "string" and isinstance(instance, str):
            return True
        if kind == "boolean" and isinstance(instance, bool):
            return True
        if kind == "integer" and isinstance(instance, int) and not isinstance(instance, bool):
            return True
        if kind == "number" and isinstance(instance, (int, float)) and not isinstance(instance, bool):
            return True
        if kind == "null" and instance is None:
            return True
    return False


def schema_errors(instance: object) -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors: list[str] = []
    _validate(instance, schema, "$", errors)
    return errors


def receipt_problems(receipt: Mapping[str, object]) -> list[str]:
    problems = schema_errors(receipt)
    if receipt.get("status") != "READINESS_BLOCKED":
        problems.append("status")
    execution = receipt.get("execution")
    if not isinstance(execution, dict) or execution.get("spawned") is not False:
        problems.append("execution")
    daemon = receipt.get("daemon")
    if not isinstance(daemon, dict) or daemon.get("state") != "UNQUALIFIED":
        problems.append("daemon")
    if not isinstance(daemon, dict) or daemon.get("admitted_daemon_ids") != []:
        problems.append("admitted_daemon_ids")
    if receipt.get("source_phase") == "SOURCE_PREPARED":
        hashes = receipt.get("hashes")
        if not isinstance(hashes, dict) or not _manifests_measured(hashes):
            problems.append("source_phase")
    commands = receipt.get("commands")
    if isinstance(commands, list):
        for command in commands:
            if not isinstance(command, dict):
                continue
            for field in ("stdout", "stderr"):
                text = command.get(field)
                if isinstance(text, str) and len(text.encode("utf-8")) > LOG_MAX_BYTES:
                    problems.append("log_bound")
    return problems


def _empty_toolchain() -> dict[str, object]:
    return {
        "git": {"path": GIT, "version": None, "state": "ABSENT"},
        "node": {"path": None, "version": None, "state": "ABSENT", "satisfies_donor_engine": False},
        "pnpm": {"path": None, "version": None, "required": DONOR_PNPM, "state": "ABSENT"},
        "adopted_for_execution": False,
    }


def run_readiness(
    *,
    object_store: Path | None = None,
    environ: dict[str, str] | None = None,
    seal_process: bool = False,
    spawn: Spawn | None = None,
    retain_owned: bool = False,
    now: Callable[[], float] | None = None,
    allocate_root: Callable[[], OwnedRoot] | None = None,
) -> dict[str, object]:
    budget = AttemptBudget(now=now)
    owned: OwnedRoot | None = None
    records: list[CommandRecord] = []
    source_state = "NOT_ATTEMPTED"
    source_reason = ""
    derivation_state = "NOT_PREPARED"
    derivation_reason = ""
    assertions: bool | None = None
    blobs: dict[str, dict[str, str]] = {}
    derived: dict[str, str] = {}
    daemon = qualify_observation(DaemonObservation(
        "absent", False, None, None, None, False, False, "not_probed",
    ))
    toolchain = _empty_toolchain()
    env: dict[str, str] = {}
    hashes: dict[str, str | None] = _unavailable_hashes("not_measured")
    stage = "setup"
    uncertain = False
    stop_reason = ""

    def recorded(argv: Sequence[str], **kwargs: object) -> CommandRecord:
        assert_readiness_argv(tuple(argv))
        if len(records) >= 48:
            raise Refusal("command_budget_exceeded")
        if budget.uncertain or budget.blocked == "uncertain_child":
            raise Refusal("uncertain_child")
        fn = spawn or default_spawn
        record = fn(argv, **kwargs)
        if not isinstance(record, CommandRecord):
            raise Refusal("spawn_contract")
        records.append(record)
        return record

    def _note_refusal(exc: Refusal) -> None:
        nonlocal source_state, source_reason, derivation_state, derivation_reason, uncertain, stop_reason
        if exc.reason == "uncertain_child":
            uncertain = True
            budget.mark_uncertain()
            stop_reason = "uncertain_child"
            if source_state != "ADMITTED":
                source_state = "REFUSED"
                source_reason = "uncertain_child"
            elif derivation_state != "PREPARED":
                derivation_state = "REFUSED"
                derivation_reason = "uncertain_child"
            return
        if exc.reason == "deadline_exhausted":
            stop_reason = "deadline_exhausted"
            if stage in {"setup", "fetch", "admit"} and source_state != "ADMITTED":
                source_state = "REFUSED"
                source_reason = exc.reason
            elif stage == "derive" and derivation_state != "PREPARED":
                derivation_state = "REFUSED"
                derivation_reason = exc.reason
            return
        if stage in {"setup", "fetch", "admit"} and source_state != "ADMITTED":
            source_state = "REFUSED"
            source_reason = exc.reason
        elif stage == "derive" and derivation_state != "PREPARED":
            derivation_state = "REFUSED"
            derivation_reason = exc.reason
        else:
            stop_reason = exc.reason

    try:
        try:
            owned = (allocate_root or create_owned_root)()
        except OSError as exc:
            stop_reason = type(exc).__name__
            source_state = "REFUSED"
            source_reason = "operational_failure"
            hashes = _unavailable_hashes(stop_reason)
        else:
            env = build_closed_env(owned)
            if seal_process:
                os.environ.clear()
                os.environ.update(env)
            if environ is not None:
                environ.clear()
                environ.update(env)
            try:
                if object_store is None:
                    stage = "fetch"
                    git_dir = fetch_donor(owned, env, recorded, budget)
                else:
                    stage = "admit"
                    git_dir = validate_git_dir(object_store)
                stage = "admit"
                admitted = admit_source(git_dir, owned=owned, env=env, spawn=recorded, budget=budget)
                source_state = "ADMITTED"
                blobs = json.loads(admitted.pop("__identities__").decode("utf-8"))
                stage = "derive"
                derived = derive_runner(admitted, owned=owned, env=env, spawn=recorded, budget=budget)
                derivation_state = "PREPARED"
                assertions = True
                if not budget.blocked:
                    stage = "probe"
                    daemon = probe_daemon(env, recorded, owned.path / "tmp", budget)
                    toolchain = probe_toolchain(env, recorded, owned.path / "tmp", budget)
            except Refusal as exc:
                _note_refusal(exc)
            except OSError as exc:
                stop_reason = type(exc).__name__
                if source_state != "ADMITTED":
                    source_state = "REFUSED"
                    source_reason = "operational_failure"
                elif derivation_state != "PREPARED":
                    derivation_state = "REFUSED"
                    derivation_reason = "operational_failure"
            if owned is not None and not uncertain and budget.blocked != "uncertain_child":
                stage = "hash"
                try:
                    hashes = _owned_hashes(owned, budget)
                except Refusal as exc:
                    _note_refusal(exc)
                    hashes = _unavailable_hashes(exc.reason)
            elif uncertain or budget.blocked == "uncertain_child":
                hashes = _unavailable_hashes("uncertain_child")
    except OSError as exc:
        stop_reason = type(exc).__name__
        source_state = "REFUSED"
        source_reason = "operational_failure"
        hashes = _unavailable_hashes(stop_reason)

    identity = new_identity()
    notes = [
        "Admitted isolated daemon id set is empty.",
        "A project name does not qualify a shared Docker daemon.",
        "Lexical image tags are not daemon admission.",
        "Topology execution is not authorized in this placement.",
        "Automatic retry is not allowed.",
        "Process exit zero is not a clean-resource receipt.",
    ]
    if source_reason:
        notes.append(f"source: {source_reason}")
    if derivation_reason:
        notes.append(f"derivation: {derivation_reason}")
    if stop_reason:
        notes.append(stop_reason)
    if budget.exhausted_phase and "deadline_exhausted" not in notes:
        notes.append("deadline_exhausted")
    for key in MANIFEST_KEYS:
        cause = hashes.get(_hash_cause(key))
        if isinstance(cause, str) and cause not in notes:
            notes.append(cause)
    notes.append(f"daemon: {daemon.get('reason')}")
    pnpm = toolchain.get("pnpm")
    if isinstance(pnpm, dict) and pnpm.get("state") != "EXACT":
        notes.append("Donor pnpm 9.15.0 is not adopted; this placement does not install it.")
    node = toolchain.get("node")
    if isinstance(node, dict) and node.get("state") == "OBSERVED" and not node.get("satisfies_donor_engine"):
        notes.append("Observed node does not satisfy the donor engine range.")
    if not env:
        env = {key: "" for key in sorted(ALLOWED_ENV_KEYS)}
    receipt = build_receipt(
        source_state=source_state,
        source_reason=source_reason,
        blobs=blobs,
        derivation_state=derivation_state,
        derivation_reason=derivation_reason,
        assertions=assertions,
        derived=derived,
        identity=identity,
        daemon=daemon,
        toolchain=toolchain,
        env_keys=sorted(env),
        owned_root="UNKNOWN",
        hashes=hashes,
        commands=records,
        notes=notes,
        budget=budget,
    )
    if uncertain or budget.uncertain:
        owned_state = "UNKNOWN"
    elif owned is None:
        owned_state = "UNKNOWN"
    elif retain_owned:
        owned_state = "RETAINED"
    else:
        owned_state = remove_owned_root(owned)
    cleanup = receipt["cleanup"]
    if isinstance(cleanup, dict):
        cleanup["owned_root"] = owned_state
    return receipt


def probe_first_child() -> int:
    owned = create_owned_root()
    try:
        env = build_closed_env(owned)
        os.environ.clear()
        os.environ.update(env)
        record = default_spawn(
            [sys.executable, "-I", "-c", _ENV_DUMP],
            env=env, cwd=owned.path / "tmp",
            timeout=float(DEADLINES_SECONDS["toolchain_probe"]),
            binary=False, stdin_bytes=None,
        )
        sys.stdout.write(record.stdout)
        if not record.stdout.endswith("\n"):
            sys.stdout.write("\n")
        return 0 if record.returncode == 0 and not record.timed_out and not record.uncertain else 1
    finally:
        remove_owned_root(owned)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rakazo_reference_journey")
    parser.add_argument("command", choices=("readiness", "probe-first-child"))
    parser.add_argument("--object-store")
    args = parser.parse_args(None if argv is None else list(argv))
    if args.command == "probe-first-child":
        return probe_first_child()
    store = Path(args.object_store) if args.object_store else None
    try:
        receipt = run_readiness(object_store=store, seal_process=True)
    except OSError as exc:
        receipt = build_receipt(
            source_state="REFUSED",
            source_reason="operational_failure",
            blobs={},
            derivation_state="NOT_PREPARED",
            derivation_reason="",
            assertions=None,
            derived={},
            identity=new_identity(),
            daemon=qualify_observation(DaemonObservation(
                "absent", False, None, None, None, False, False, type(exc).__name__,
            )),
            toolchain=_empty_toolchain(),
            env_keys=sorted(ALLOWED_ENV_KEYS),
            owned_root="UNKNOWN",
            hashes=_unavailable_hashes(type(exc).__name__),
            commands=(),
            notes=[type(exc).__name__, "Topology execution is not authorized in this placement."],
        )
    except Refusal as exc:
        receipt = build_receipt(
            source_state="REFUSED",
            source_reason=exc.reason,
            blobs={},
            derivation_state="NOT_PREPARED",
            derivation_reason="",
            assertions=None,
            derived={},
            identity=new_identity(),
            daemon=qualify_observation(DaemonObservation(
                "absent", False, None, None, None, False, False, exc.reason,
            )),
            toolchain=_empty_toolchain(),
            env_keys=sorted(ALLOWED_ENV_KEYS),
            owned_root="UNKNOWN",
            hashes=_unavailable_hashes(exc.reason),
            commands=(),
            notes=[exc.reason, "Topology execution is not authorized in this placement."],
        )
    json.dump(receipt, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if not receipt_problems(receipt) else 1


if __name__ == "__main__":
    sys.exit(main())
