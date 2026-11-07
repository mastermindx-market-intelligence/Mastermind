"""Native subprocess owner for a fixed, reviewed ACP stdio profile.

This module owns only one provider subprocess generation and its byte streams.
Executive OS and the common broker still own admission/lifecycle; AcpWorkerAdapter
owns ACP semantics/result normalization.  Provider selection, credentials and
route activation are fixed outside WorkerLaunchSpec at trusted construction.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from control_plane.codex_worker import (
    ProcessInspector as LocalProcessInspector,
    _MAX_SCHEMA_BYTES,
    _assert_binary_unchanged,
    _create_private_file,
    _ensure_run_directory,
    _git_snapshot,
    _is_relative_to,
    _read_limited,
    _utc_now,
)
from control_plane.worker_execution_contract import (
    BinaryAttestation,
    CancelReceipt,
    ProcessInspector,
    WorkerLaunchSpec,
    WorkerProcessRef,
)
from integrations.acp_worker.adapter import AcpProcessCompletion, AcpRunResources
from integrations.acp_worker.process_resource import (
    AcpNativeProcessError, NativeProcessResource, bounded_argv, bounded_environment, identity_matches,
)
from integrations.acp_worker.turn import _nonfinite, _object_pairs
from integrations.acp_worker.tool_admission import AcpAdmissionChannel, AcpNativeToolGate, FD_ENV

_ENV_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
_PROFILE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_DEFAULT_STDOUT_LIMIT = 32 * 1024 * 1024
_DEFAULT_STDERR_LIMIT = 4 * 1024 * 1024

EnvironmentLoader = Callable[[], Mapping[str, str]]
LaunchArgvBuilder = Callable[[WorkerLaunchSpec, Path, Path], Sequence[str]]
AttemptOverlayBuilder = Callable[[WorkerLaunchSpec, Path, Path], Mapping[str, Any]]


@dataclasses.dataclass(frozen=True)
class AcpNativeProfile:
    """Immutable executable/argv identity; never selected by a Job payload."""

    profile_id: str
    binary: BinaryAttestation
    argv: tuple[str, ...]
    stdout_limit_bytes: int = _DEFAULT_STDOUT_LIMIT
    stderr_limit_bytes: int = _DEFAULT_STDERR_LIMIT
    private_startup: bool = False
    allowed_environment_keys: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "argv", tuple(self.argv))
        if _PROFILE_ID.fullmatch(self.profile_id) is None:
            raise ValueError("invalid ACP native profile id")
        if not self.argv or self.argv[0] != self.binary.real_path:
            raise ValueError("ACP argv must start with the attested executable")
        if len(self.argv) > 64:
            raise ValueError("ACP argv exceeds reviewed ceiling")
        for arg in self.argv:
            if not isinstance(arg, str) or not arg or "\x00" in arg or "\n" in arg or "\r" in arg:
                raise ValueError("ACP argv contains an invalid argument")
        for value in (self.stdout_limit_bytes, self.stderr_limit_bytes):
            if type(value) is not int or not 1024 <= value <= 64 * 1024 * 1024:
                raise ValueError("ACP capture limit is outside reviewed bounds")
        if type(self.private_startup) is not bool:
            raise ValueError("ACP private startup must be a boolean")
        keys = self.allowed_environment_keys
        if self.private_startup != (keys is not None):
            raise ValueError("ACP private startup requires a fixed environment ceiling")
        if keys is not None:
            if isinstance(keys, str):
                raise ValueError("ACP environment ceiling must be a sequence of keys")
            keys = tuple(keys)
            if (len(keys) > 128
                    or any(not isinstance(key, str) or _ENV_KEY.fullmatch(key) is None for key in keys)
                    or len(set(keys)) != len(keys)
                    or {"HOME", "TMPDIR", FD_ENV}.intersection(keys)):
                raise ValueError("ACP environment ceiling is invalid or contains owner-reserved keys")
            object.__setattr__(self, "allowed_environment_keys", keys)


@dataclasses.dataclass
class _NativeRun:
    spec: WorkerLaunchSpec
    resource: NativeProcessResource
    ref: WorkerProcessRef
    launch_attestation: Mapping[str, Any]
    finish_task: asyncio.Task[AcpProcessCompletion] | None = None
    finish_reason: str | None = None
    admission_channel: AcpAdmissionChannel | None = None

    @property
    def stdout_task(self):
        return self.resource.stdout_task

    @property
    def stderr_task(self):
        return self.resource.stderr_task


class AcpNativeProcessOwner:
    """Open and settle one exact ACP subprocess without creating a new lifecycle."""

    def __init__(
        self,
        profile: AcpNativeProfile,
        *,
        environment_loader: EnvironmentLoader,
        inspector: ProcessInspector | None = None,
        tool_gate: AcpNativeToolGate | None = None,
        launch_argv_builder: LaunchArgvBuilder | None = None,
        attempt_overlay_builder: AttemptOverlayBuilder | None = None,
    ) -> None:
        if not callable(environment_loader):
            raise ValueError("ACP environment loader is required")
        if launch_argv_builder is not None and not callable(launch_argv_builder):
            raise ValueError("ACP launch argv builder must be callable")
        if attempt_overlay_builder is not None and (
            not callable(attempt_overlay_builder)
            or tool_gate is None or not profile.private_startup
            or launch_argv_builder is None
        ):
            raise ValueError("ACP Attempt overlay requires fixed private governed startup")
        if tool_gate is not None:
            if not isinstance(tool_gate, AcpNativeToolGate) or not profile.private_startup:
                raise ValueError("ACP tool gate requires reviewed private startup")
            if (
                launch_argv_builder is None
                and (
                    len(profile.argv) < 2
                    or profile.argv[1] not in {p for p, _ in tool_gate.artifacts}
                )
            ):
                raise ValueError("ACP tool bootstrap is outside the fixed artifact closure")
        self.tool_gate = tool_gate
        self.profile = profile
        self.environment_loader = environment_loader
        self.launch_argv_builder = launch_argv_builder
        self.attempt_overlay_builder = attempt_overlay_builder
        self.inspector = inspector or LocalProcessInspector()
        self._runs: dict[str, _NativeRun] = {}
        self._active: str | None = None
        # A failed post-spawn admission still owns its exact physical resource.
        # Keep it here until settlement, without minting an admitted Worker ref.
        self._opening: NativeProcessResource | None = None

    @staticmethod
    def _environment(loader: EnvironmentLoader) -> dict[str, str]:
        return bounded_environment(loader())

    def _launch_argv(
        self,
        spec: WorkerLaunchSpec,
        workspace: Path,
        run_dir: Path,
    ) -> tuple[str, ...]:
        raw = (
            self.profile.argv
            if self.launch_argv_builder is None
            else self.launch_argv_builder(spec, workspace, run_dir)
        )
        return bounded_argv(self.profile.binary, raw)

    @staticmethod
    def _schema(spec: WorkerLaunchSpec) -> Any:
        try:
            raw = _read_limited(spec.result_schema_path, _MAX_SCHEMA_BYTES)
            value = json.loads(raw, object_pairs_hook=_object_pairs, parse_constant=_nonfinite)
        except Exception:
            raise AcpNativeProcessError("ACP native result schema changed or is invalid") from None
        if not isinstance(value, (dict, bool)):
            raise AcpNativeProcessError("ACP native result schema root is invalid")
        return value

    def _startup(
        self, run_dir: Path, workspace: Path, env: dict[str, str],
    ) -> tuple[Path, Mapping[str, Any] | None]:
        """Isolate startup configuration, not OS filesystem/network authority.

        These directories belong to the existing run and cannot be supplied by
        the Job or reused from a prior launch. The trusted profile owns the
        loader-key ceiling; the native owner alone supplies HOME and TMPDIR.
        """
        if not self.profile.private_startup:
            return workspace, None
        if set(env).difference(self.profile.allowed_environment_keys or ()):
            raise AcpNativeProcessError("ACP environment exceeds the fixed startup ceiling")
        startup = run_dir / "startup"
        home, scratch = startup / "home", startup / "tmp"
        env["HOME"], env["TMPDIR"] = str(home), str(scratch)
        # Owner-supplied values still count toward the existing final size and
        # key ceilings. Validate before creating any startup artifacts.
        self._environment(lambda: env)
        try:
            # Refuse an existing directory or symlink instead of inheriting
            # configuration left by an earlier or foreign process.
            for directory in (startup, home, scratch):
                directory.mkdir(mode=0o700, exist_ok=False)
        except OSError:
            raise AcpNativeProcessError("ACP private startup directory is not fresh") from None
        directories = {}
        for name, directory in (("cwd", startup), ("home", home), ("tmp", scratch)):
            info = directory.stat()
            directories[name] = {
                "path": str(directory), "device": info.st_dev, "inode": info.st_ino,
                "uid": info.st_uid, "gid": info.st_gid, "mode": info.st_mode & 0o7777,
            }
        return startup, {
            "schema_version": "mastermind.acp_private_startup/v1",
            "directories": directories,
            "allowed_loader_keys": sorted(self.profile.allowed_environment_keys or ()),
            "os_sandbox_proven": False,
        }

    def _identity_matches(self, ref: WorkerProcessRef) -> bool:
        return identity_matches(self.inspector, ref)

    async def open_run(self, spec: WorkerLaunchSpec) -> AcpRunResources:
        if self._active is not None or self._opening is not None or spec.run_id in self._runs:
            raise AcpNativeProcessError("ACP native owner already has active or known work")
        _assert_binary_unchanged(self.profile.binary)
        workspace = Path(spec.workspace_path).resolve(strict=True)
        run_dir = _ensure_run_directory(
            Path(spec.run_dir),
            shared_gid=(int(spec.shared_run_gid) if spec.shared_run_gid is not None else None),
        )
        if _is_relative_to(run_dir, workspace) or _is_relative_to(workspace, run_dir):
            raise AcpNativeProcessError("ACP run directory overlaps the workspace")
        baseline = _git_snapshot(workspace, require_clean=True)
        if spec.expected_base_sha is None or baseline.head != spec.expected_base_sha:
            raise AcpNativeProcessError("ACP workspace base is not exactly bound")
        if spec.expected_worker_uid is not None and os.geteuid() != int(spec.expected_worker_uid):
            raise AcpNativeProcessError("ACP native worker uid does not match admission")
        if spec.expected_worker_gid is not None and os.getegid() != int(spec.expected_worker_gid):
            raise AcpNativeProcessError("ACP native worker gid does not match admission")
        schema = self._schema(spec)
        argv = self._launch_argv(spec, workspace, run_dir)
        env = self._environment(self.environment_loader)
        startup_cwd, startup_attestation = self._startup(run_dir, workspace, env)
        logs = run_dir / "logs"
        output = run_dir / "output"
        stdout_path = logs / "acp-stdout.ndjson"
        stderr_path = logs / "acp-stderr.log"
        result_path = output / "result.json"
        resource: NativeProcessResource | None = None
        admission_channel: AcpAdmissionChannel | None = None
        try:
            logs.mkdir(mode=0o700, exist_ok=True)
            output.mkdir(mode=0o700, exist_ok=True)
            result_fd = _create_private_file(result_path)
            os.close(result_fd)
            pass_fds: tuple[int, ...] = ()
            if FD_ENV in env:
                raise AcpNativeProcessError("ACP attestation descriptor is owner-reserved")
            if self.tool_gate is not None:
                self.tool_gate.verify_artifacts()
                overlay = (
                    self.attempt_overlay_builder(spec, workspace, run_dir)
                    if self.attempt_overlay_builder is not None else None
                )
                admission_channel = AcpAdmissionChannel(
                    self.tool_gate, spec=spec if overlay is not None else None,
                    attempt_overlay=overlay,
                )
                pass_fds = (admission_channel.child.fileno(),)
                env[FD_ENV] = str(pass_fds[0])
                env = self._environment(lambda: env)

            async def close_admission() -> None:
                if admission_channel is not None:
                    await admission_channel.close()

            resource = await NativeProcessResource.open(
                binary=self.profile.binary, argv=argv, environment=env, cwd=startup_cwd,
                stdout_path=stdout_path, stderr_path=stderr_path,
                stdout_limit_bytes=self.profile.stdout_limit_bytes,
                stderr_limit_bytes=self.profile.stderr_limit_bytes,
                settle_seconds=spec.cancel_grace_seconds, inspector=self.inspector,
                pass_fds=pass_fds, close_hook=close_admission,
            )
            self._opening = resource
            observed = resource.identity
            ref = WorkerProcessRef(
                run_id=spec.run_id, pid=observed.pid, pgid=observed.pgid,
                process_start_identity=observed.process_start_identity,
                boot_session_id=observed.boot_session_id,
                launch_nonce=hashlib.sha256(os.urandom(32)).hexdigest()[:32],
                provider_session_id=None, stdout_path=str(stdout_path), stderr_path=str(stderr_path),
                result_path=str(result_path), started_at=_utc_now(), binary=self.profile.binary,
                base_sha=baseline.head, session_id=observed.session_id,
                effective_uid=observed.effective_uid, effective_gid=observed.effective_gid,
                real_uid=observed.real_uid, real_gid=observed.real_gid,
            )
            if spec.expected_worker_uid is not None and ref.effective_uid != int(spec.expected_worker_uid):
                raise AcpNativeProcessError("ACP child effective uid does not match admission")
            if spec.expected_worker_gid is not None and ref.effective_gid != int(spec.expected_worker_gid):
                raise AcpNativeProcessError("ACP child effective gid does not match admission")
            if admission_channel is not None:
                await admission_channel.start(spec, ref, self._identity_matches)
            argv_digest = hashlib.sha256(
                json.dumps(argv, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            ).hexdigest()
            attestation = {
                "schema_version": "mastermind.acp_native_launch/v1",
                "profile_id": self.profile.profile_id,
                "binary_sha256": self.profile.binary.sha256,
                "binary_version": self.profile.binary.version,
                "argv_sha256": argv_digest,
                "rendered_argv": list(argv),
                "environment_keys": sorted(env),
                "credential_values_persisted": False,
                "process_identity": {
                    "pid": ref.pid,
                    "pgid": ref.pgid,
                    "session_id": ref.session_id,
                    "start_identity": ref.process_start_identity,
                    "boot_id": ref.boot_session_id,
                    "effective_uid": ref.effective_uid,
                    "effective_gid": ref.effective_gid,
                },
            }
            if startup_attestation is not None:
                attestation["private_startup"] = startup_attestation
            run = _NativeRun(spec, resource, ref, attestation, admission_channel=admission_channel)
            self._runs[spec.run_id] = run
            self._active = spec.run_id
            self._opening = None
        except BaseException:
            if resource is not None:
                physical = await resource.finish("startup failed")
                if physical.settled:
                    self._opening = None
            elif admission_channel is not None:
                try:
                    await asyncio.wait_for(admission_channel.close(), timeout=1)
                except Exception:
                    admission_channel.close_unstarted()
            raise

        async def finish(reason: str | None) -> AcpProcessCompletion:
            return await self._finish(run, reason)

        return AcpRunResources(ref, resource.writer, resource.reader, attestation, schema, finish,
                               admission_channel.prepare_prompt if admission_channel is not None else None)

    async def _finish(self, run: _NativeRun, reason: str | None) -> AcpProcessCompletion:
        normalized = reason.strip() if isinstance(reason, str) else None
        if reason is not None and not normalized:
            raise AcpNativeProcessError("ACP native cancellation reason is invalid")
        if run.finish_task is None:
            run.finish_reason = normalized
            run.finish_task = asyncio.create_task(self._finish_once(run, normalized))
        elif run.finish_reason != normalized:
            raise AcpNativeProcessError("ACP native finish was already bound to another reason")
        return await asyncio.shield(run.finish_task)

    async def _finish_once(self, run: _NativeRun, reason: str | None) -> AcpProcessCompletion:
        physical = await run.resource.finish(reason)
        cancellation = None
        if reason is not None:
            cancellation = CancelReceipt(
                run.ref.run_id, reason, physical.signal_sent, physical.escalated,
                physical.already_exited, physical.finished_at,
            )
        if physical.settled and self._active == run.ref.run_id:
            self._active = None
        empty = hashlib.sha256(b"").hexdigest()
        return AcpProcessCompletion(
            process_ref=run.ref, exit_code=physical.exit_code, finished_at=physical.finished_at,
            stdout_sha256=physical.stdout.sha256 if physical.stdout is not None else empty,
            stderr_sha256=physical.stderr.sha256 if physical.stderr is not None else empty,
            settled=physical.settled, cancellation=cancellation,
        )


__all__ = [
    "AcpNativeProcessError",
    "AcpNativeProcessOwner",
    "AcpNativeProfile",
    "EnvironmentLoader",
    "LaunchArgvBuilder",
]
