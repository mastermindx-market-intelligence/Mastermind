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
import re
import socket
from collections.abc import Callable
from pathlib import Path

from control_plane.worker_execution_contract import WorkerLaunchSpec, WorkerProcessRef

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_LIMIT = 32768
FD_ENV = "MMX_ACP_ATTEST_FD"


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
    def __init__(self, gate: AcpNativeToolGate) -> None:
        self.gate = gate
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
        self.child.close()
        reader, self.writer = await asyncio.open_connection(sock=self.parent, limit=_LIMIT)
        self.spec, self.ref, self.identity_matches = spec, ref, identity_matches
        self.seed = {
            "schema": "mastermind.acp_tools_ready/v1",
            "run_id": spec.run_id, "job_id": spec.job_id, "worker_id": spec.worker_id,
            "launch_nonce": ref.launch_nonce, "pid": ref.pid, "base_sha": ref.base_sha,
            "projection_sha256": self.gate.projection_sha256,
            "artifact_sha256": self.gate.artifact_sha256,
            "admitted_tools": [dataclasses.asdict(t) for t in self.gate.tools],
        }
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
            if (json.dumps(value, sort_keys=True, separators=(",", ":"))
                    != json.dumps({**self.seed, "ready": True}, sort_keys=True, separators=(",", ":"))
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
