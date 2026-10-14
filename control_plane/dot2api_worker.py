"""Executive WorkerExecutionAdapter for an OpenAI Dot via Dot2API.

Dot2API is provider substrate only. Executive OS remains the canonical owner of
Job/Attempt/Worker/Event lifecycle, claims, retries, cancellation policy,
acceptance, and recovery. This adapter is deliberately READ/RESEARCH-only.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
import pwd
import re
import signal
import stat
import subprocess
import sys
import urllib.parse
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from control_plane.codex_worker import (
    LaunchValidationError,
    ProcessIdentityError,
    ProcessInspector as LocalProcessInspector,
    ResultValidationError,
    _assert_binary_unchanged,
    _canonical_sha256,
    _create_private_file,
    _ensure_private_directory,
    _ensure_run_directory,
    _git_changed_paths,
    _git_snapshot,
    _path_identity,
    _read_limited,
    _sha256_path,
    _utc_now,
    validate_json_schema,
    validate_secret_canary_verdict,
)
from control_plane.worker_execution_contract import (
    LAUNCH_ATTESTATION_SCHEMA_VERSION,
    BinaryAttestation,
    CancelReceipt,
    CollectionReceipt,
    LaunchAttestation,
    ProcessInspector,
    ValidationReceipt,
    WorkerLaunchSpec,
    WorkerProcessRef,
    WorkerRecoveryBinding,
    WorkerResult,
    WorkerRunStatus,
)
from common.dot2api_client import (
    Dot2ApiClient,
    Dot2ApiClientError,
    Dot2ApiEffectUnknown,
    Dot2ApiProtocolError,
    Dot2ApiTask,
)

ADAPTER_ID = "dot2api"
_MAX_SCHEMA = 512 * 1024
_MAX_PROMPT = 64 * 1024
_MAX_LOG = 4 * 1024 * 1024
_MAX_RESULT = 1024 * 1024
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class Dot2ApiWorkerError(RuntimeError):
    """A known Dot2API worker refusal or transport failure."""


class Dot2ApiWorkerEffectUnknown(Dot2ApiWorkerError):
    """Provider I/O may have begun; caller must reconcile before replay."""

    effect_unknown = True


@dataclasses.dataclass
class _Run:
    spec: WorkerLaunchSpec
    ref: WorkerProcessRef
    process: asyncio.subprocess.Process | None
    baseline: Any
    provider_path: Path
    result_path: Path
    launch_attestation: LaunchAttestation
    cancel_reason: str | None = None
    receipt: CollectionReceipt | None = None


def _attest_python(path: Path) -> BinaryAttestation:
    try:
        lexical = path.lstat()
        real = path.resolve(strict=True)
        info = real.stat()
    except OSError as exc:
        raise Dot2ApiWorkerError("Dot2API transport Python is unavailable") from exc
    if (
        stat.S_ISLNK(lexical.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or not os.access(real, os.X_OK)
    ):
        raise Dot2ApiWorkerError(
            "Dot2API transport Python is not an executable regular file"
        )
    try:
        completed = subprocess.run(
            [str(real), "--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env={
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "LANG": "C",
                "LC_ALL": "C",
            },
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise Dot2ApiWorkerError(
            "Dot2API transport Python version probe failed"
        ) from exc
    text = ((completed.stdout or "") + (completed.stderr or "")).strip()
    match = re.search(r"Python\s+(\d+\.\d+\.\d+)", text)
    if completed.returncode != 0 or match is None:
        raise Dot2ApiWorkerError("Dot2API transport Python version is unavailable")
    digest = hashlib.sha256()
    with real.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return BinaryAttestation(
        path=str(path),
        real_path=str(real),
        version=match.group(1),
        sha256=digest.hexdigest(),
        team_identifier=None,
        size=int(info.st_size),
        device=int(info.st_dev),
        inode=int(info.st_ino),
        mode=stat.S_IMODE(info.st_mode),
        uid=int(info.st_uid),
        gid=int(info.st_gid),
        mtime_ns=int(info.st_mtime_ns),
    )


def _write_private_json(path: Path, value: Any) -> None:
    try:
        raw = (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError):
        raise LaunchValidationError("Dot2API transport input is not JSON") from None
    if not raw or len(raw) > 128 * 1024:
        raise LaunchValidationError(
            "Dot2API transport input is outside the 128 KiB bound"
        )
    fd = _create_private_file(path)
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_json(path: Path, maximum: int) -> dict[str, Any]:
    raw = _read_limited(path, maximum)
    try:
        value = Dot2ApiClient._decode(raw)
    except Dot2ApiProtocolError:
        raise ResultValidationError("Dot2API durable JSON is invalid") from None
    if type(value) is not dict:
        raise ResultValidationError("Dot2API durable JSON must be an object")
    return value


def _reply_text(result: Any) -> str:
    if isinstance(result, Mapping):
        for key in ("content", "text", "output"):
            value = result.get(key)
            if type(value) is str:
                return value
    if type(result) is str:
        return result
    raise ResultValidationError("Dot2API completed task has no text reply")


class Dot2ApiWorkerAdapter:
    """READ/RESEARCH-only Executive worker backed by one Dot2API service."""

    adapter_id = ADAPTER_ID

    def __init__(
        self,
        base_url: str,
        *,
        credential_loader: Callable[[], str],
        queue: str = "dot",
        python_path: str | os.PathLike[str] = sys.executable,
        transport_script: str | os.PathLike[str] | None = None,
        inspector: ProcessInspector | None = None,
        submission_timeout_seconds: float = 20.0,
        poll_seconds: float = 1.0,
        client_factory: Callable[..., Dot2ApiClient] = Dot2ApiClient,
    ) -> None:
        if not callable(credential_loader) or not callable(client_factory):
            raise TypeError("Dot2API credential/client factories must be callable")
        if type(queue) is not str or _ID.fullmatch(queue) is None:
            raise ValueError("Dot2API queue is invalid")
        if not 2 <= float(submission_timeout_seconds) <= 120:
            raise ValueError("Dot2API submission timeout is invalid")
        if not 0.2 <= float(poll_seconds) <= 30:
            raise ValueError("Dot2API poll interval is invalid")

        self.base_url = Dot2ApiClient(
            base_url, token_loader=lambda: "constructor-probe"
        ).base_url
        if (urllib.parse.urlsplit(self.base_url).hostname or "").lower() not in {
            "127.0.0.1", "::1", "localhost"
        }:
            raise ValueError("Dot2API worker provider origin must be loopback")
        self.credential_loader = credential_loader
        self.queue = queue
        self.submission_timeout_seconds = float(submission_timeout_seconds)
        self.poll_seconds = float(poll_seconds)
        self.client_factory = client_factory
        try:
            canonical_python = Path(python_path).resolve(strict=True)
        except OSError as exc:
            raise Dot2ApiWorkerError(
                "Dot2API transport Python is unavailable"
            ) from exc
        self.binary = _attest_python(canonical_python)

        default_script = (
            Path(__file__).resolve().parents[1]
            / "ops"
            / "executive_os"
            / "dot2api_transport_worker.py"
        )
        requested_script = (
            Path(transport_script) if transport_script is not None else default_script
        )
        try:
            lexical = requested_script.lstat()
            self.transport_script = requested_script.resolve(strict=True)
            info = self.transport_script.stat()
        except OSError as exc:
            raise Dot2ApiWorkerError(
                "Dot2API transport worker is unavailable"
            ) from exc
        if (
            stat.S_ISLNK(lexical.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) & 0o022
        ):
            raise Dot2ApiWorkerError(
                "Dot2API transport worker is not immutable enough"
            )
        self.transport_sha256 = _sha256_path(
            self.transport_script, max_bytes=1024 * 1024
        )
        self._transport_identity = (
            int(info.st_dev), int(info.st_ino), int(info.st_size),
            stat.S_IMODE(info.st_mode), int(info.st_uid), int(info.st_gid),
            int(info.st_mtime_ns),
        )
        self.inspector = inspector or LocalProcessInspector()
        self._runs: dict[str, _Run] = {}
        self._unbound: dict[str, asyncio.subprocess.Process] = {}


    def _assert_transport_unchanged(self) -> None:
        try:
            info = self.transport_script.lstat()
        except OSError as exc:
            raise Dot2ApiWorkerError(
                "Dot2API transport worker disappeared before launch"
            ) from exc
        actual = (
            int(info.st_dev), int(info.st_ino), int(info.st_size),
            stat.S_IMODE(info.st_mode), int(info.st_uid), int(info.st_gid),
            int(info.st_mtime_ns),
        )
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) & 0o022
            or actual != self._transport_identity
            or _sha256_path(self.transport_script, max_bytes=1024 * 1024)
            != self.transport_sha256
        ):
            raise Dot2ApiWorkerError(
                "Dot2API transport worker changed before launch"
            )

    def _client(self) -> Dot2ApiClient:
        return self.client_factory(
            self.base_url,
            token_loader=self.credential_loader,
            timeout_seconds=15.0,
        )

    @staticmethod
    def _validate_read_only(spec: WorkerLaunchSpec) -> None:
        if not isinstance(spec, WorkerLaunchSpec):
            raise LaunchValidationError("Dot2API requires WorkerLaunchSpec")
        authorities = set(spec.authorities)
        if (
            "READ" not in authorities
            or not authorities <= {"READ", "RESEARCH"}
            or spec.authority is not None
        ):
            raise LaunchValidationError("Dot2API worker is READ/RESEARCH-only")
        if spec.allowed_artifact_paths:
            raise LaunchValidationError(
                "Dot2API worker cannot publish workspace artifacts"
            )
        encoded = spec.prompt.encode("utf-8")
        if not encoded or len(encoded) > _MAX_PROMPT:
            raise LaunchValidationError(
                "Dot2API prompt is outside the 64 KiB bound"
            )

    def _validate_spec(self, spec: WorkerLaunchSpec):
        self._validate_read_only(spec)
        workspace = Path(spec.workspace_path).resolve(strict=True)
        run_dir = _ensure_run_directory(
            Path(spec.run_dir), shared_gid=spec.shared_run_gid
        )
        logs = _ensure_private_directory(run_dir / "logs")
        output = _ensure_private_directory(run_dir / "output")
        inputs = (run_dir / "input").resolve(strict=True)
        schema_path = Path(spec.result_schema_path).resolve(strict=True)
        try:
            schema_path.relative_to(inputs)
        except ValueError:
            raise LaunchValidationError(
                "Dot2API schema escapes the run input directory"
            ) from None
        schema_raw = _read_limited(schema_path, _MAX_SCHEMA)
        try:
            schema = json.loads(schema_raw.decode("utf-8", errors="strict"))
        except (UnicodeError, json.JSONDecodeError):
            raise LaunchValidationError("Dot2API result schema is invalid") from None
        if type(schema) is not dict:
            raise LaunchValidationError("Dot2API result schema must be an object")
        baseline = _git_snapshot(workspace, require_clean=True)
        if (
            spec.expected_base_sha is not None
            and baseline.head != spec.expected_base_sha.lower()
        ):
            raise LaunchValidationError(
                "Dot2API workspace HEAD differs from expected base"
            )
        return workspace, run_dir, logs, output, schema, baseline

    def _messages(
        self, spec: WorkerLaunchSpec, schema: Mapping[str, Any]
    ) -> list[dict[str, str]]:
        schema_text = json.dumps(
            schema,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        system = (
            "You are a bounded Mastermind Executive worker. This Attempt is READ-only. "
            "Do not claim to edit files, run commands, publish, send messages, or create "
            "external side effects. Return ONLY one JSON object, with no Markdown fences "
            "or commentary, that validates against this JSON Schema:\n"
            + schema_text
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": spec.prompt},
        ]
        raw = json.dumps(
            messages, ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
        if len(raw) > 120 * 1024:
            raise LaunchValidationError(
                "Dot2API conversation exceeds the provider request bound"
            )
        return messages

    @staticmethod
    def _idempotency(spec: WorkerLaunchSpec) -> str:
        material = (
            spec.job_id + "\0" + spec.run_id + "\0" + spec.worker_id
        ).encode("utf-8")
        return "mmx-" + hashlib.sha256(material).hexdigest()

    def _attestation(
        self,
        *,
        spec: WorkerLaunchSpec,
        workspace: Path,
        baseline: Any,
        ref: WorkerProcessRef,
        observed_user: str | None,
        environment: Mapping[str, str],
        argv: Sequence[str],
        canary_verdict: Mapping[str, Any],
    ) -> LaunchAttestation:
        return LaunchAttestation(
            schema_version=LAUNCH_ATTESTATION_SCHEMA_VERSION,
            created_at=_utc_now(),
            executable_path=self.binary.real_path,
            binary=self.binary,
            rendered_argv=tuple(argv),
            environment_keys=tuple(sorted(environment)),
            permission_profile_sha256=_canonical_sha256(
                {
                    "workspace": "read_only",
                    "provider_transport": "dot2api_task_api",
                    "provider_mutation_retries": 0,
                    "provider_max_attempts": 1,
                    "external_dot_tools": "not_granted_by_mastermind",
                    "transport_script_sha256": self.transport_sha256,
                }
            ),
            prompt_sha256=hashlib.sha256(
                spec.prompt.encode("utf-8")
            ).hexdigest(),
            expected_base_sha=spec.expected_base_sha,
            observed_base_sha=baseline.head,
            workspace_identity={
                **_path_identity(workspace),
                "git_head": baseline.head,
            },
            worker_identity={
                "requested_user": spec.worker_user,
                "observed_user": observed_user,
                "expected_uid": spec.expected_worker_uid,
                "expected_gid": spec.expected_worker_gid,
                "effective_uid": ref.effective_uid,
                "effective_gid": ref.effective_gid,
                "real_uid": ref.real_uid,
                "real_gid": ref.real_gid,
                "transport_script_sha256": self.transport_sha256,
            },
            provider_home_identity={
                "kind": "remote_dot2api",
                "base_url_sha256": hashlib.sha256(
                    self.base_url.encode("utf-8")
                ).hexdigest(),
                "queue_sha256": hashlib.sha256(
                    self.queue.encode("utf-8")
                ).hexdigest(),
            },
            secret_canary_verdict=dict(canary_verdict),
            launch_nonce=ref.launch_nonce,
            process_identity={
                "pid": ref.pid,
                "pgid": ref.pgid,
                "session_id": ref.session_id,
                "start_identity": ref.process_start_identity,
                "boot_id": ref.boot_session_id,
                "effective_uid": ref.effective_uid,
                "effective_gid": ref.effective_gid,
                "real_uid": ref.real_uid,
                "real_gid": ref.real_gid,
            },
            isolation_manifest_sha256=spec.isolation_manifest_sha256,
        )

    async def start(self, spec: WorkerLaunchSpec) -> WorkerProcessRef:
        (
            workspace,
            run_dir,
            logs,
            output,
            schema,
            baseline,
        ) = self._validate_spec(spec)
        canary_verdict = validate_secret_canary_verdict(
            spec.secret_canary_verdict,
            require_passed=bool(spec.require_secret_canary),
        )
        _assert_binary_unchanged(self.binary)
        self._assert_transport_unchanged()

        provider_path = output / "provider-binding.json"
        result_path = output / "result.json"
        input_path = run_dir / "input" / "dot2api-request.json"
        stdout_path = logs / "stdout.jsonl"
        stderr_path = logs / "stderr.log"
        ttl = max(60, min(2_592_000, int(spec.timeout_seconds) + 120))

        _write_private_json(
            input_path,
            {
                "base_url": self.base_url,
                "queue": self.queue,
                "idempotency_key": self._idempotency(spec),
                "messages": self._messages(spec, schema),
                "ttl_seconds": ttl,
                "max_attempts": 1,
                "poll_seconds": self.poll_seconds,
                "poll_deadline_seconds": max(
                    60.0,
                    min(
                        float(ttl),
                        float(spec.timeout_seconds)
                        + float(spec.cancel_grace_seconds)
                        + 30.0,
                    ),
                ),
            },
        )
        stdout_fd = _create_private_file(stdout_path)
        try:
            stderr_fd = _create_private_file(stderr_path)
        except BaseException:
            os.close(stdout_fd)
            raise

        token = self.credential_loader()
        if (
            type(token) is not str
            or not token.strip()
            or len(token) > 4096
            or any(ch in token for ch in "\r\n\x00")
        ):
            os.close(stdout_fd)
            os.close(stderr_fd)
            raise LaunchValidationError("Dot2API credential is unavailable")

        environment = {
            "HOME": "/var/empty",
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "MMX_DOT2API_TOKEN": token.strip(),
        }
        argv = (
            self.binary.real_path,
            str(self.transport_script),
            "--input",
            str(input_path),
            "--provider",
            str(provider_path),
            "--result",
            str(result_path),
        )

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=subprocess.DEVNULL,
                stdout=stdout_fd,
                stderr=stderr_fd,
                cwd=str(workspace),
                env=environment,
                start_new_session=True,
            )
        finally:
            os.close(stdout_fd)
            os.close(stderr_fd)

        self._unbound[spec.run_id] = process
        observed = self.inspector.inspect(process.pid)
        if observed.pgid != process.pid or observed.session_id != process.pid:
            raise ProcessIdentityError(
                "Dot2API transport did not become its own process group/session"
            )
        if (
            spec.expected_worker_uid is not None
            and observed.effective_uid != int(spec.expected_worker_uid)
        ):
            raise ProcessIdentityError(
                "Dot2API transport effective UID does not match worker"
            )
        if (
            spec.expected_worker_gid is not None
            and observed.effective_gid != int(spec.expected_worker_gid)
        ):
            raise ProcessIdentityError(
                "Dot2API transport effective GID does not match worker"
            )

        deadline = (
            asyncio.get_running_loop().time() + self.submission_timeout_seconds
        )
        binding: dict[str, Any] | None = None
        while asyncio.get_running_loop().time() < deadline:
            if provider_path.exists() and provider_path.stat().st_size:
                binding = _read_json(provider_path, 64 * 1024)
                break
            if process.returncode is not None:
                break
            await asyncio.sleep(0.05)
        if (
            binding is None
            and provider_path.exists()
            and provider_path.stat().st_size
        ):
            binding = _read_json(provider_path, 64 * 1024)

        if binding is None:
            raise Dot2ApiWorkerEffectUnknown(
                "Dot2API submission outcome is unknown"
            )
        if binding.get("schema") != "mastermind.dot2api.provider_binding/v1":
            raise Dot2ApiWorkerEffectUnknown(
                "Dot2API submission binding is malformed"
            )
        if binding.get("ok") is not True:
            code = str(binding.get("code") or "DOT2API_SUBMISSION_REFUSED")
            if binding.get("effect") == "NO_EFFECT":
                raise Dot2ApiWorkerError(code)
            raise Dot2ApiWorkerEffectUnknown(code)

        task_id = binding.get("task_id")
        if type(task_id) is not str or _ID.fullmatch(task_id) is None:
            raise Dot2ApiWorkerEffectUnknown(
                "Dot2API submission task identity is invalid"
            )

        ref = WorkerProcessRef(
            run_id=spec.run_id,
            pid=process.pid,
            pgid=observed.pgid,
            process_start_identity=observed.start_identity,
            boot_session_id=self.inspector.boot_session_id(),
            launch_nonce=uuid.uuid4().hex,
            provider_session_id=task_id,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            result_path=str(result_path),
            started_at=_utc_now(),
            binary=self.binary,
            base_sha=baseline.head,
            session_id=observed.session_id,
            effective_uid=observed.effective_uid,
            effective_gid=observed.effective_gid,
            real_uid=observed.real_uid,
            real_gid=observed.real_gid,
        )
        try:
            observed_user = pwd.getpwuid(observed.effective_uid).pw_name
        except KeyError:
            observed_user = None
        attestation = self._attestation(
            spec=spec,
            workspace=workspace,
            baseline=baseline,
            ref=ref,
            observed_user=observed_user,
            environment=environment,
            argv=argv,
            canary_verdict=canary_verdict,
        )
        self._runs[spec.run_id] = _Run(
            spec=spec,
            ref=ref,
            process=process,
            baseline=baseline,
            provider_path=provider_path,
            result_path=result_path,
            launch_attestation=attestation,
        )
        self._unbound.pop(spec.run_id, None)
        return ref

    async def cleanup_unbound_run(self, run_id: str) -> Mapping[str, Any]:
        process = self._unbound.pop(run_id, None)
        if process is not None and process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except TimeoutError:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                await process.wait()
        raise Dot2ApiWorkerEffectUnknown(
            "unbound Dot2API start cannot prove the provider task absent"
        )

    def _run(self, ref: WorkerProcessRef) -> _Run:
        run = self._runs.get(ref.run_id)
        if run is None or run.ref != ref:
            raise Dot2ApiWorkerError(
                "Dot2API process reference is not owned by this adapter"
            )
        return run

    def launch_attestation(self, ref: WorkerProcessRef) -> LaunchAttestation:
        return self._run(ref).launch_attestation

    async def status(self, ref: WorkerProcessRef) -> WorkerRunStatus:
        run = self._run(ref)
        if run.receipt is not None:
            return run.receipt.result.status
        try:
            task = await asyncio.to_thread(
                self._client().get_task, str(ref.provider_session_id),
                expected_queue=self.queue, expected_max_attempts=1,
            )
        except Dot2ApiClientError as exc:
            raise Dot2ApiWorkerError(exc.code) from exc
        return {
            "queued": WorkerRunStatus.RUNNING,
            "running": WorkerRunStatus.RUNNING,
            "completed": WorkerRunStatus.SUCCEEDED,
            "failed": WorkerRunStatus.FAILED,
            "cancelled": WorkerRunStatus.CANCELLED,
            "expired": WorkerRunStatus.TIMED_OUT,
        }[task.status]

    async def cancel(
        self, ref: WorkerProcessRef, reason: str
    ) -> CancelReceipt:
        run = self._run(ref)
        reason = str(reason).strip()
        if not reason:
            raise LaunchValidationError(
                "Dot2API cancellation reason is required"
            )
        if run.cancel_reason is not None and run.cancel_reason != reason:
            raise Dot2ApiWorkerError(
                "Dot2API cancellation already has a different reason"
            )
        requested_reason = reason[:1000]
        try:
            task = await asyncio.to_thread(
                self._client().cancel_task,
                str(ref.provider_session_id),
                reason=requested_reason,
                expected_queue=self.queue,
                expected_max_attempts=1,
            )
        except Dot2ApiEffectUnknown as exc:
            raise Dot2ApiWorkerEffectUnknown(exc.code) from exc
        except Dot2ApiClientError as exc:
            if exc.status != 409:
                raise Dot2ApiWorkerError(exc.code) from exc
            task = await asyncio.to_thread(
                self._client().get_task, str(ref.provider_session_id),
                expected_queue=self.queue, expected_max_attempts=1,
            )
            if not task.terminal:
                raise Dot2ApiWorkerError(exc.code) from exc
        process = run.process
        already_exited = process is None or process.returncode is not None
        signal_sent = False
        escalated = False
        if task.status != "cancelled":
            # The provider terminal state won the race. Keep the carrier alive
            # long enough to persist that exact result; cancellation must not
            # relabel or destroy a completed/failed/expired task.
            return CancelReceipt(
                run_id=ref.run_id,
                reason=requested_reason,
                signal_sent=False,
                escalated_to_sigkill=False,
                already_exited=already_exited,
                finished_at=_utc_now(),
            )
        run.cancel_reason = requested_reason
        if process is not None and process.returncode is None:
            try:
                os.killpg(ref.pgid, signal.SIGTERM)
                signal_sent = True
                await asyncio.wait_for(process.wait(), timeout=2)
            except TimeoutError:
                os.killpg(ref.pgid, signal.SIGKILL)
                escalated = True
                await process.wait()
            except ProcessLookupError:
                already_exited = True
        return CancelReceipt(
            run_id=ref.run_id,
            reason=requested_reason,
            signal_sent=signal_sent,
            escalated_to_sigkill=escalated,
            already_exited=already_exited,
            finished_at=_utc_now(),
        )

    async def _terminal_task(
        self, ref: WorkerProcessRef, timeout: float
    ) -> Dot2ApiTask:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            try:
                task = await asyncio.to_thread(
                    self._client().get_task,
                    str(ref.provider_session_id),
                    expected_queue=self.queue,
                    expected_max_attempts=1,
                )
            except Dot2ApiProtocolError as exc:
                raise Dot2ApiWorkerError(exc.code) from exc
            except Dot2ApiClientError as exc:
                if asyncio.get_running_loop().time() >= deadline:
                    raise Dot2ApiWorkerError(
                        "DOT2API_STATUS_UNAVAILABLE"
                    ) from exc
                await asyncio.sleep(self.poll_seconds)
                continue
            if task.terminal:
                return task
            if asyncio.get_running_loop().time() >= deadline:
                await self.cancel(ref, "Executive worker timeout")
                return await asyncio.to_thread(
                    self._client().get_task,
                    str(ref.provider_session_id),
                    expected_queue=self.queue,
                    expected_max_attempts=1,
                )
            await asyncio.sleep(self.poll_seconds)

    async def collect_result(
        self, ref: WorkerProcessRef
    ) -> CollectionReceipt:
        run = self._run(ref)
        if run.receipt is not None:
            return run.receipt

        task = await self._terminal_task(
            ref, max(1.0, float(run.spec.timeout_seconds))
        )
        process = run.process
        exit_code = process.returncode if process is not None else None
        if process is not None and process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except TimeoutError:
                try:
                    os.killpg(ref.pgid, signal.SIGTERM)
                    await asyncio.wait_for(process.wait(), timeout=2)
                except TimeoutError:
                    os.killpg(ref.pgid, signal.SIGKILL)
                    await process.wait()
            exit_code = process.returncode

        workspace = Path(run.spec.workspace_path).resolve(strict=True)
        after = _git_snapshot(workspace, require_clean=False)
        changed = _git_changed_paths(workspace)
        status = WorkerRunStatus.FAILED
        output: dict[str, Any] | None = None
        error = task.error
        result_hash: str | None = None

        if (
            after.head != run.baseline.head
            or after.status != run.baseline.status
            or changed
        ):
            status = WorkerRunStatus.INVALID_RESULT
            error = (
                "read-only Dot2API worker workspace changed during execution"
            )
        elif run.cancel_reason or task.status == "cancelled":
            status = WorkerRunStatus.CANCELLED
            error = error or (
                "cancelled: " + (run.cancel_reason or "provider cancellation")
            )
        elif task.status == "expired":
            status = WorkerRunStatus.TIMED_OUT
            error = error or "Dot2API task expired"
        elif task.status == "failed":
            status = WorkerRunStatus.FAILED
            error = error or "Dot2API task failed"
        elif task.status == "completed":
            try:
                content = _reply_text(task.result)
                if len(content.encode("utf-8")) > _MAX_RESULT:
                    raise ResultValidationError(
                        "Dot2API reply exceeds the 1 MiB result bound"
                    )
                try:
                    decoded = Dot2ApiClient._decode(content.encode("utf-8"))
                except Dot2ApiProtocolError as exc:
                    raise ResultValidationError(
                        "Dot2API reply is not strict JSON"
                    ) from exc
                if type(decoded) is not dict:
                    raise ResultValidationError(
                        "Dot2API reply must be one JSON object"
                    )
                schema_raw = _read_limited(
                    Path(run.spec.result_schema_path), _MAX_SCHEMA
                )
                schema = json.loads(
                    schema_raw.decode("utf-8", errors="strict")
                )
                validate_json_schema(decoded, schema)
                output = decoded
                result_hash = hashlib.sha256(
                    json.dumps(
                        decoded,
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                        allow_nan=False,
                    ).encode("utf-8")
                ).hexdigest()
                status = WorkerRunStatus.SUCCEEDED
                error = None
            except (
                ValueError,
                TypeError,
                UnicodeError,
                json.JSONDecodeError,
                ResultValidationError,
            ) as exc:
                status = WorkerRunStatus.INVALID_RESULT
                error = f"{type(exc).__name__}: {exc}"[:3000]

        if not run.result_path.exists():
            _write_private_json(
                run.result_path,
                {
                    "schema": "mastermind.dot2api.transport_result/v1",
                    "task_id": task.id,
                    "status": task.status,
                    "result": task.result,
                    "error": task.error,
                    "attempts": task.attempts,
                    "max_attempts": task.max_attempts,
                    "revision": task.revision,
                    "created_at": task.created_at,
                    "updated_at": task.updated_at,
                    "expires_at": task.expires_at,
                },
            )

        worker_result = WorkerResult(
            job_id=run.spec.job_id,
            run_id=run.spec.run_id,
            worker_id=run.spec.worker_id,
            status=status,
            structured_output=output,
            artifact_manifest=(),
            git_manifest={
                "base_sha": run.baseline.head,
                "head_sha": after.head,
                "status_sha256": hashlib.sha256(after.status).hexdigest(),
                "changed_paths": list(changed),
            },
            usage={
                "task_attempts": task.attempts,
                "task_revision": task.revision,
                "provider_token_usage_known": 0,
            },
            provider_session_id=task.id,
            exit_code=exit_code,
            started_at=ref.started_at,
            finished_at=_utc_now(),
            error=error,
        )
        receipt = CollectionReceipt(
            process_ref=dataclasses.replace(
                ref, provider_session_id=task.id
            ),
            result=worker_result,
            stdout_sha256=_sha256_path(
                Path(ref.stdout_path), max_bytes=_MAX_LOG
            ),
            stderr_sha256=_sha256_path(
                Path(ref.stderr_path), max_bytes=_MAX_LOG
            ),
            result_sha256=result_hash,
        )
        run.receipt = receipt
        return receipt

    def reattach(
        self, spec: WorkerLaunchSpec, binding: WorkerRecoveryBinding
    ) -> WorkerProcessRef:
        if (
            not isinstance(binding, WorkerRecoveryBinding)
            or binding.adapter_id != self.adapter_id
        ):
            raise Dot2ApiWorkerError("Dot2API recovery binding is invalid")
        recovered = binding.recover_launch_spec(type(spec))
        if recovered != spec:
            raise Dot2ApiWorkerError(
                "Dot2API recovery launch specification drifted"
            )
        ref = binding.process_ref
        if (
            type(ref.provider_session_id) is not str
            or _ID.fullmatch(ref.provider_session_id) is None
        ):
            raise Dot2ApiWorkerError(
                "Dot2API recovery lacks provider task identity"
            )

        (
            workspace,
            _run_dir,
            _logs,
            output,
            _schema,
            baseline,
        ) = self._validate_spec(spec)
        if baseline.head != ref.base_sha:
            raise Dot2ApiWorkerError(
                "Dot2API recovery workspace base drifted"
            )

        canary_verdict = validate_secret_canary_verdict(
            spec.secret_canary_verdict,
            require_passed=bool(spec.require_secret_canary),
        )
        _assert_binary_unchanged(self.binary)
        self._assert_transport_unchanged()
        attestation = self._attestation(
            spec=spec,
            workspace=workspace,
            baseline=baseline,
            ref=ref,
            observed_user=None,
            environment={},
            argv=(),
            canary_verdict=canary_verdict,
        )
        self._runs[spec.run_id] = _Run(
            spec=spec,
            ref=ref,
            process=None,
            baseline=baseline,
            provider_path=output / "provider-binding.json",
            result_path=Path(ref.result_path),
            launch_attestation=attestation,
        )
        return ref

    async def run_validation_argv(
        self,
        spec: WorkerLaunchSpec,
        argv: Sequence[str],
        *,
        timeout_seconds: float = 300.0,
    ) -> ValidationReceipt:
        raise Dot2ApiWorkerError(
            "Dot2API workers do not execute validation commands"
        )


__all__ = [
    "ADAPTER_ID",
    "Dot2ApiWorkerAdapter",
    "Dot2ApiWorkerEffectUnknown",
    "Dot2ApiWorkerError",
]
