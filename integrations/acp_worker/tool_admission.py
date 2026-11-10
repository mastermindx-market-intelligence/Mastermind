"""Private owner evidence for observing already-governed ACP tools.

This is not a grant issuer. The existing tool/profile owner must enforce the
projection and live dispatch binding. Only a trusted native composition can
construct this channel; no Job or ACP field configures it.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import math
import re
import socket
import time
from collections.abc import Callable, Mapping
from pathlib import Path

from control_plane.worker_execution_contract import WorkerLaunchSpec, WorkerProcessRef

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_LIMIT = 32768
FD_ENV = "MMX_ACP_ATTEST_FD"
_ACP_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_ACP_ATTEMPT_ENV = frozenset({
    "MMX_ACP_WORKSPACE_PATH", "MMX_ACP_WORKSPACE_BASE_SHA",
    "MMX_ACP_RUN_ID", "MMX_ACP_JOB_ID", "MMX_ACP_WORKER_ID",
    "MMX_ACP_DEADLINE_MS",
})


def _sealed_attempt_overlay(spec: WorkerLaunchSpec, raw: Mapping) -> dict:
    """Verify a trusted factory's per-Attempt snapshot before native spawn.

    This is existing ACP readiness socket input, never an env var, credential,
    tool grant or separate transport. Revalidate scope against the exact spec
    even if a caller supplies a plausible but foreign overlay.
    """
    try:
        if not isinstance(raw, Mapping) or set(raw) != {"cwd", "env"}:
            raise ValueError("ACP Attempt channel overlay shape refused")
        cwd, env = raw["cwd"], raw["env"]
        if not isinstance(cwd, str) or not isinstance(env, Mapping):
            raise ValueError("ACP Attempt channel overlay values refused")
        if set(env) != _ACP_ATTEMPT_ENV:
            raise ValueError("ACP Attempt channel environment ceiling refused")
        if any(not isinstance(value, str) or not value
               or len(value.encode("utf-8")) > 4096
               or any(c in value for c in ("\x00", "\r", "\n"))
               for value in env.values()):
            raise ValueError("ACP Attempt channel environment value refused")
        path = Path(cwd)
        if not path.is_absolute() or path == Path("/") or path.resolve(strict=True) != path:
            raise ValueError("ACP Attempt channel workspace refused")
        if path != Path(spec.workspace_path).resolve(strict=True):
            raise ValueError("ACP Attempt channel foreign workspace refused")
        if (env["MMX_ACP_WORKSPACE_PATH"] != cwd
                or env["MMX_ACP_WORKSPACE_BASE_SHA"] != spec.expected_base_sha
                or env["MMX_ACP_RUN_ID"] != spec.run_id
                or env["MMX_ACP_JOB_ID"] != spec.job_id
                or env["MMX_ACP_WORKER_ID"] != spec.worker_id
                or not isinstance(spec.expected_base_sha, str)
                or not _ACP_SHA40.fullmatch(spec.expected_base_sha)
                or any(_NAME.fullmatch(env[key]) is None for key in (
                    "MMX_ACP_RUN_ID", "MMX_ACP_JOB_ID", "MMX_ACP_WORKER_ID"
                ))):
            raise ValueError("ACP Attempt channel identity refused")
        scopes = set(spec.authorities)
        if spec.authority is not None:
            scopes.add(str(spec.authority).strip().upper())
        if not scopes or not scopes.issubset({"READ", "RESEARCH"}):
            raise ValueError("ACP Attempt channel write authority refused")
        deadline_text = env["MMX_ACP_DEADLINE_MS"]
        if not deadline_text.isascii() or not deadline_text.isdecimal():
            raise ValueError("ACP Attempt channel deadline refused")
        deadline = int(deadline_text, 10)
        now_ms = int(time.time() * 1000)
        if (str(deadline) != deadline_text or deadline <= now_ms
                or deadline > 8_640_000_000_000_000
                or not isinstance(spec.timeout_seconds, (int, float))
                or isinstance(spec.timeout_seconds, bool)
                or not math.isfinite(spec.timeout_seconds)
                or not 0 < spec.timeout_seconds <= 86_400
                or deadline - now_ms > int(spec.timeout_seconds * 1000)):
            raise ValueError("ACP Attempt channel deadline refused")
        return {"cwd": cwd, "env": {key: env[key] for key in sorted(_ACP_ATTEMPT_ENV)}}
    except (OSError, RuntimeError, TypeError, OverflowError, UnicodeError, AttributeError, KeyError) as exc:
        raise ValueError("ACP Attempt channel overlay refused") from exc


@dataclasses.dataclass(frozen=True)
class AcpObservedTool:
    name: str
    contract_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _NAME.fullmatch(self.name):
            raise ValueError("invalid ACP observed tool name")
        if not isinstance(self.contract_sha256, str) or not _SHA.fullmatch(self.contract_sha256):
            raise ValueError("invalid ACP observed tool contract")


def _tools(value: tuple[AcpObservedTool, ...]) -> tuple[AcpObservedTool, ...]:
    result = tuple(value)
    if (not 1 <= len(result) <= 16 or any(not isinstance(t, AcpObservedTool) for t in result)
            or len({t.name for t in result}) != len(result)):
        raise ValueError("invalid ACP observed tool ceiling")
    return result


@dataclasses.dataclass(frozen=True)
class AcpToolAdmission:
    process_ref: WorkerProcessRef
    job_id: str
    worker_id: str
    session_id: str
    model: str
    projection_sha256: str
    artifact_sha256: str
    tools: tuple[AcpObservedTool, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "tools", _tools(self.tools))
        for value in (self.projection_sha256, self.artifact_sha256):
            if not isinstance(value, str) or not _SHA.fullmatch(value):
                raise ValueError("invalid ACP tool admission digest")
        if not isinstance(self.process_ref, WorkerProcessRef):
            raise ValueError("invalid ACP admission process")
        for value in (self.job_id, self.worker_id, self.session_id, self.model):
            if not isinstance(value, str) or not value or len(value) > 128:
                raise ValueError("invalid ACP admission binding")

    def matches(self, spec: WorkerLaunchSpec, ref: WorkerProcessRef,
                session_id: str, model: str) -> bool:
        return (self.process_ref == ref and self.process_ref.run_id == spec.run_id
                and self.job_id == spec.job_id and self.worker_id == spec.worker_id
                and self.session_id == session_id and self.model == model == spec.model
                and self.process_ref.base_sha == spec.expected_base_sha)


@dataclasses.dataclass(frozen=True)
class AcpNativeToolGate:
    """Fixed, reviewed host composition; absent by default and never wire-fed.

    Artifacts bind the trusted bootstrap and its grant-profile closure. This
    same-principal source check is not OS confinement or a hostile-writer fence.
    The projection digest identifies the incumbent owner's immutable grant.
    """
    projection_sha256: str
    artifact_sha256: str
    tools: tuple[AcpObservedTool, ...]
    artifacts: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "tools", _tools(self.tools))
        object.__setattr__(self, "artifacts", tuple(tuple(row) for row in self.artifacts))
        if not 1 <= len(self.artifacts) <= 16:
            raise ValueError("ACP tool gate requires a bounded artifact closure")
        for digest in (self.projection_sha256, self.artifact_sha256):
            if not isinstance(digest, str) or not _SHA.fullmatch(digest):
                raise ValueError("invalid ACP gate digest")
        for path, digest in self.artifacts:
            if not Path(path).is_absolute() or not _SHA.fullmatch(digest):
                raise ValueError("invalid ACP gate artifact")
        if self.artifact_sha256 not in {digest for _, digest in self.artifacts}:
            raise ValueError("ACP grant artifact is not in the fixed closure")

    def verify_artifacts(self) -> None:
        for path, expected in self.artifacts:
            value = Path(path)
            if value.is_symlink() or not value.is_file():
                raise ValueError("ACP tool artifact is not a direct file")
            digest = hashlib.sha256()
            with value.open("rb") as handle:
                for chunk in iter(lambda: handle.read(65536), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected:
                raise ValueError("ACP tool artifact changed")


class AcpAdmissionChannel:
    """One inherited socket owned/settled by AcpNativeProcessOwner.

    The trusted child sends readiness only after grant discovery. Parent ACK
    precedes session publication; the standard ACP session/model handshake then
    binds that single mount to the one admitted turn before its prompt.
    """
    def __init__(
        self,
        gate: AcpNativeToolGate,
        *,
        spec: WorkerLaunchSpec | None = None,
        attempt_overlay: Mapping | None = None,
    ) -> None:
        self.gate = gate
        if (spec is None) != (attempt_overlay is None):
            raise ValueError("ACP Attempt channel requires exact spec and overlay")
        self.attempt_spec = spec
        self.attempt_overlay = (
            _sealed_attempt_overlay(spec, attempt_overlay)
            if spec is not None and attempt_overlay is not None else None
        )
        self.parent, self.child = socket.socketpair()
        self.parent.setblocking(False)
        self.writer: asyncio.StreamWriter | None = None
        self.task: asyncio.Task[None] | None = None
        self.close_task: asyncio.Task[None] | None = None
        self.used = False

    def close_unstarted(self) -> None:
        self.parent.close()
        self.child.close()

    async def start(self, spec: WorkerLaunchSpec, ref: WorkerProcessRef,
                    identity_matches: Callable[[WorkerProcessRef], bool]) -> None:
        if self.attempt_spec is not None:
            if spec != self.attempt_spec:
                raise ValueError("ACP Attempt channel changed before readiness")
            # A pending process cannot borrow a now-expired overlay; this
            # explicit refusal leaves the incumbent owner to settle the child.
            _sealed_attempt_overlay(spec, self.attempt_overlay)
        self.child.close()
        reader, self.writer = await asyncio.open_connection(sock=self.parent, limit=_LIMIT)
        self.spec, self.ref, self.identity_matches = spec, ref, identity_matches
        self.seed = {
            "schema": "mastermind.acp_tools_ready/v2" if self.attempt_overlay else "mastermind.acp_tools_ready/v1",
            "run_id": spec.run_id, "job_id": spec.job_id, "worker_id": spec.worker_id,
            "launch_nonce": ref.launch_nonce, "pid": ref.pid, "base_sha": ref.base_sha,
            "projection_sha256": self.gate.projection_sha256,
            "artifact_sha256": self.gate.artifact_sha256,
            "admitted_tools": [dataclasses.asdict(t) for t in self.gate.tools],
        }
        if self.attempt_overlay is not None:
            # Native readiness v2 carries the *existing* immutable packet on
            # the single inherited socket, never on ambient env/argv/stdout.
            self.seed["attempt_overlay"] = self.attempt_overlay
        frame = json.dumps(self.seed, separators=(",", ":")).encode() + b"\n"
        if len(frame) > _LIMIT:
            raise ValueError("ACP readiness seed exceeds limit")
        self.writer.write(frame)
        await self.writer.drain()

        async def observe() -> None:
            # Strict one-message protocol. Equality includes every nonce/identity
            # field; duplicate JSON keys and nonfinite values are refused.
            from integrations.acp_worker.turn import _nonfinite, _object_pairs
            line = await reader.readline()
            if not line.endswith(b"\n") or len(line) > _LIMIT:
                raise ValueError("ACP readiness frame refused")
            value = json.loads(line, object_pairs_hook=_object_pairs, parse_constant=_nonfinite)
            expected_reply = {**self.seed, "ready": True}
            if self.attempt_overlay is not None:
                # A v1 child echo must NOT accidentally qualify the new v2
                # payload: require independent parsing/hashing by the child.
                expected_reply["attempt_overlay_sha256"] = hashlib.sha256(
                    json.dumps(self.attempt_overlay, sort_keys=True,
                               separators=(",", ":"), ensure_ascii=True).encode()
                ).hexdigest()
            if (json.dumps(value, sort_keys=True, separators=(",", ":"))
                    != json.dumps(expected_reply, sort_keys=True, separators=(",", ":"))
                    or not identity_matches(ref)):
                raise ValueError("ACP readiness identity refused")
            self.gate.verify_artifacts()
            self.writer.write(b'{"accepted":true}\n')
            await self.writer.drain()
            # Stop the one-shot evidence transport; no later message can replace
            # or revoke this receipt. Live revocation stays with the grant owner.

        async def observe_and_close() -> None:
            try:
                await observe()
            finally:
                await self._close_writer()

        self.task = asyncio.create_task(observe_and_close())
        self.task.add_done_callback(lambda t: None if t.cancelled() else t.exception())

    async def prepare_prompt(self, session_id: str, model: str) -> AcpToolAdmission:
        if self.used or self.task is None:
            raise ValueError("ACP readiness is absent or already consumed")
        self.used = True
        await asyncio.shield(self.task)
        if not self.identity_matches(self.ref):
            raise ValueError("ACP ready process generation changed")
        self.gate.verify_artifacts()
        return AcpToolAdmission(self.ref, self.spec.job_id, self.spec.worker_id,
                                session_id, model, self.gate.projection_sha256,
                                self.gate.artifact_sha256, self.gate.tools)

    async def close(self) -> None:
        if self.task is not None:
            if not self.task.done():
                self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        try:
            await self._close_writer()
        finally:
            self.close_unstarted()

    async def _close_writer(self) -> None:
        if self.writer is None:
            return
        if self.close_task is None:
            async def close_once() -> None:
                self.writer.close()
                await self.writer.wait_closed()
            self.close_task = asyncio.create_task(close_once())
            self.close_task.add_done_callback(lambda t: None if t.cancelled() else t.exception())
        # A cancelled waiter cannot erase a failed or still-running close. All
        # subsequent owners observe the same completion, including its failure.
        await asyncio.shield(self.close_task)
