"""Isolated, one-shot Claude Code CLI process adapter for the Executive OS.

This module binds the hardened, provider-free ``control_plane.claude_cli_protocol``
falsifier to the provider-neutral :class:`control_plane.worker_adapter.WorkerExecutionAdapter`
contract.  It owns provider-process mechanics only: it does not claim jobs,
decide authority, create workspaces, commit Git changes, retry work, or
promote an output to an Executive result.

Every credential-shaped surface is refused by construction:

* the compiled command is produced only by ``compile_claude_cli_command``,
  which is never called with caller-supplied flags or a caller environment;
* the process environment is the protocol's own closed tuple -- this module
  never reads ``os.environ`` and never merges ambient state into it;
* ``ClaudeCliRunner.run`` is always invoked with an explicit ``fake_controls``
  mapping, so ``FAKE_ONLY_EFFECT_CEILING`` continues to refuse anything but
  the one committed fake executable;
* one adapter instance starts at most one run, matching
  :class:`control_plane.claude_cli_protocol.ClaudeCliRunner`'s own one-shot
  refusal -- there is no retry, resume, fallback, or account rotation here.

No ``ANTHROPIC_*``/``CLAUDE_*`` credential, token, or Keychain path is read,
constructed, or forwarded anywhere in this module.
"""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import functools
import hashlib
import json
import os
import platform
import re
import signal
import stat
import subprocess
import threading
import uuid
import weakref
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence

from control_plane import claude_cli_protocol as _protocol
from control_plane.claude_cli_protocol import (
    ClaudeCliCommand,
    ClaudeCliInvocationPolicy,
    ClaudeCliProcessIdentity,
    ClaudeCliProtocolError,
    ClaudeCliRunReceipt,
    ClaudeCliRunner,
    ClaudeCliVersion,
    compile_claude_cli_command,
)
from control_plane.worker_execution_contract import (
    BinaryAttestation,
    CancelReceipt,
    CollectionReceipt,
    ValidationReceipt,
    WorkerLaunchSpec,
    WorkerProcessRef,
    WorkerResult,
    WorkerRunStatus,
)


LaunchSpec = WorkerLaunchSpec
ProcessRef = WorkerProcessRef

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_EVIDENCE_RELATIVE_PATH = "pf1/claude_worker_evidence.txt"
_MAX_PROMPT_EVIDENCE_BYTES = 65_536
_MAX_VALIDATION_ARGV_BYTES = 64 * 1024
_MAX_VALIDATION_STDOUT_BYTES = 4 * 1024 * 1024
_MAX_VALIDATION_STDERR_BYTES = 1 * 1024 * 1024
_MAX_STRUCTURED_OUTPUT_BYTES = 1 * 1024 * 1024
_MAX_RESULT_SCHEMA_BYTES = 1 * 1024 * 1024
_SHELL_EXECUTABLE_NAMES = frozenset({"bash", "csh", "dash", "fish", "ksh", "sh", "tcsh", "zsh"})
_VALIDATION_SAFE_ENVIRONMENT = (
    ("PATH", "/usr/bin:/bin"),
    ("LANG", "C.UTF-8"),
    ("LC_ALL", "C.UTF-8"),
)
_SECRET_SHAPED_MARKERS = (
    "sk-ant-",
    "anthropic_api_key",
    "anthropic_auth_token",
    "claude_code_oauth_token",
    "setup-token",
    "-----begin private key-----",
    "-----begin openssh private key-----",
)
_DEFAULT_MAX_STDOUT_BYTES = 1_048_576
_DEFAULT_MAX_STDERR_BYTES = 4_096
_DEFAULT_MAX_LINE_BYTES = 131_072
_DEFAULT_MAX_EVENTS = 64
_DEFAULT_MAX_JSON_DEPTH = 16
_DEFAULT_MAX_JSON_STRING_BYTES = 65_536
_DEFAULT_MAX_JSON_COLLECTION_ITEMS = 256
_SESSION_NAMESPACE = uuid.UUID("b3ba8f6c-6e9a-4b7e-9b7e-6c1c1a6f6a4d")


class ClaudeWorkerError(RuntimeError):
    """Base class for fail-closed Claude adapter errors."""


class LaunchValidationError(ClaudeWorkerError):
    """The launch specification, private configuration, or output is unsafe."""


class BinaryAttestationError(ClaudeWorkerError):
    """The configured Claude binary failed attestation or drifted."""


class ProcessIdentityError(ClaudeWorkerError):
    """A ``WorkerProcessRef`` does not match the run this adapter started."""


class ResultValidationError(ClaudeWorkerError):
    """Provider output did not satisfy the local result contract."""


class SecondStartRefused(ClaudeWorkerError):
    """One adapter instance may start at most one run."""


class IdentityTimeoutError(ClaudeWorkerError):
    """The proven process identity did not arrive within the bounded wait."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _looks_secret_shaped(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in _SECRET_SHAPED_MARKERS)


def _validate_structured_output(output: Any, schema: Mapping[str, Any] | None) -> dict[str, Any]:
    """Bounded, provider-neutral structured-output check.

    This is deliberately not a general JSON Schema engine.  It enforces the
    properties this adapter's discriminators require: the output must be a
    bounded JSON object, satisfy any ``required``/``additionalProperties``
    constraint the caller's schema declares, and contain no secret-shaped
    key or value anywhere in it.
    """

    encoded = json.dumps(output, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) > _MAX_STRUCTURED_OUTPUT_BYTES:
        raise ResultValidationError("structured output exceeds the byte ceiling")
    if not isinstance(output, dict):
        raise ResultValidationError("structured output must be a JSON object")
    schema = schema if isinstance(schema, Mapping) else {}
    required = schema.get("required")
    properties = schema.get("properties")
    additional_allowed = True
    if "additionalProperties" in schema:
        additional_allowed = bool(schema["additionalProperties"])
    if isinstance(required, (list, tuple)):
        missing = [key for key in required if key not in output]
        if missing:
            raise ResultValidationError(f"structured output missing required keys: {missing}")
    if isinstance(properties, Mapping) and not additional_allowed:
        extra = sorted(set(output) - set(properties))
        if extra:
            raise ResultValidationError(f"structured output has unapproved keys: {extra}")
    for key, value in output.items():
        if not isinstance(key, str) or _looks_secret_shaped(key):
            raise ResultValidationError(f"structured output key is secret-shaped: {key!r}")
        if isinstance(value, str) and _looks_secret_shaped(value):
            raise ResultValidationError("structured output value is secret-shaped")
    return output


def _create_private_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(str(path), flags, 0o600)
    except FileExistsError as exc:
        raise LaunchValidationError(f"run output already exists: {path}") from exc
    os.close(descriptor)


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(65_536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


class ProcessInspector:
    """Boot-scoped OS identity source; not itself an attestation mechanism.

    ``identity``/``inspect`` reuse the same ``ps``-based attestation the
    protocol layer's identity seam already proves (``_process_identity``)
    rather than duplicating a second, possibly-divergent implementation.
    """

    def boot_session_id(self) -> str:
        if platform.system() == "Darwin":
            try:
                completed = subprocess.run(
                    ["/usr/sbin/sysctl", "-n", "kern.bootsessionuuid"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    env={"PATH": "/usr/sbin:/usr/bin:/bin"},
                    timeout=1.0,
                    text=True,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError):
                completed = None
            if completed is not None and completed.returncode == 0 and completed.stdout.strip():
                return completed.stdout.strip()
        return f"claude-adapter-{os.getpid()}"

    def identity(self, pid: int) -> tuple[str, int]:
        observed = _protocol._process_identity(pid)
        if observed is None:
            raise ProcessIdentityError(f"cannot resolve process identity for pid {pid}")
        _, _, pgid, start_token = observed
        return start_token, pgid

    def inspect(self, pid: int) -> tuple[str, int]:
        return self.identity(pid)


@dataclasses.dataclass
class _RunState:
    spec: LaunchSpec
    ref: ProcessRef
    future: "asyncio.Future[ClaudeCliRunReceipt]"
    cancel_event: threading.Event
    command: ClaudeCliCommand
    evidence_sha256: str
    result_schema: Any
    stdout_path: Path
    stderr_path: Path
    result_path: Path
    finished_at: str | None = None
    receipt: CollectionReceipt | None = None


_CONSTRUCTED_CLAUDE_ADAPTERS: "weakref.WeakSet[ClaudeCodeWorkerAdapter]" = weakref.WeakSet()


class ClaudeCodeWorkerAdapter:
    """One-shot, provider-free Claude Code CLI process adapter.

    All provider-private configuration -- the exact binary, allowed version
    set, exact model id, bounded max turns, isolated home/tmp roots,
    timeouts, and the fake-only control mapping -- is fixed at construction.
    ``WorkerLaunchSpec`` supplies only the provider-neutral job/run/worker
    identity, workspace, prompt, and result schema; it is never inspected
    for a model, tool, or flag override.
    """

    adapter_id = "claude-code"

    def __init__(
        self,
        binary_path: str | os.PathLike[str],
        *,
        isolated_home: str | os.PathLike[str],
        isolated_tmp: str | os.PathLike[str],
        model: str,
        version: str | ClaudeCliVersion,
        allowed_versions: frozenset[ClaudeCliVersion] | None = None,
        max_turns: int = 1,
        api_timeout_ms: int = 60_000,
        idle_timeout_seconds: float = 30.0,
        absolute_timeout_seconds: float = 120.0,
        terminate_grace_seconds: float = 2.0,
        max_stdout_bytes: int = _DEFAULT_MAX_STDOUT_BYTES,
        max_stderr_bytes: int = _DEFAULT_MAX_STDERR_BYTES,
        max_line_bytes: int = _DEFAULT_MAX_LINE_BYTES,
        max_events: int = _DEFAULT_MAX_EVENTS,
        max_json_depth: int = _DEFAULT_MAX_JSON_DEPTH,
        max_json_string_bytes: int = _DEFAULT_MAX_JSON_STRING_BYTES,
        max_json_collection_items: int = _DEFAULT_MAX_JSON_COLLECTION_ITEMS,
        fake_controls: Mapping[str, str] | None = None,
        identity_timeout_seconds: float = 10.0,
        inspector: Any | None = None,
        runner_factory: Callable[[], ClaudeCliRunner] | None = None,
    ) -> None:
        if int(max_turns) != 1:
            raise LaunchValidationError("PF1-F0 supports exactly one Claude CLI turn")
        path = Path(binary_path)
        if not path.is_absolute():
            raise BinaryAttestationError("Claude binary path must be absolute")
        try:
            resolved = path.resolve(strict=True)
            info = resolved.lstat()
            data = resolved.read_bytes()
        except OSError as exc:
            raise BinaryAttestationError("Claude binary is unavailable") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or not os.access(resolved, os.X_OK):
            raise BinaryAttestationError("Claude binary must be a real executable file")
        self._binary_path = path
        self._binary_baseline = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "device": info.st_dev,
            "inode": info.st_ino,
            "uid": info.st_uid,
            "mode": info.st_mode,
            "size": info.st_size,
            "mtime_ns": info.st_mtime_ns,
        }

        home = Path(isolated_home)
        tmp = Path(isolated_tmp)
        for label, candidate in (("isolated home", home), ("isolated tmp", tmp)):
            if not candidate.is_absolute():
                raise LaunchValidationError(f"{label} must be an absolute path")
            candidate_info = candidate.resolve(strict=True).lstat()
            if stat.S_ISLNK(candidate_info.st_mode) or not stat.S_ISDIR(candidate_info.st_mode):
                raise LaunchValidationError(f"{label} must be a real directory")
        self._isolated_home = home.resolve(strict=True)
        self._isolated_tmp = tmp.resolve(strict=True)

        self._model = str(model)
        self._version = version if isinstance(version, ClaudeCliVersion) else ClaudeCliVersion.parse(str(version))
        self._allowed_versions = allowed_versions
        if self._allowed_versions is not None and self._version not in self._allowed_versions:
            raise LaunchValidationError("configured Claude CLI version is not allowlisted")
        self._max_turns = int(max_turns)
        self._api_timeout_ms = int(api_timeout_ms)
        self._idle_timeout_seconds = float(idle_timeout_seconds)
        self._absolute_timeout_seconds = float(absolute_timeout_seconds)
        self._terminate_grace_seconds = float(terminate_grace_seconds)
        self._max_stdout_bytes = int(max_stdout_bytes)
        self._max_stderr_bytes = int(max_stderr_bytes)
        self._max_line_bytes = int(max_line_bytes)
        self._max_events = int(max_events)
        self._max_json_depth = int(max_json_depth)
        self._max_json_string_bytes = int(max_json_string_bytes)
        self._max_json_collection_items = int(max_json_collection_items)
        self._fake_controls_template: dict[str, str] = dict(fake_controls or {"MMX_FAKE_CLAUDE_SCENARIO": "ok"})
        self._identity_timeout_seconds = float(identity_timeout_seconds)
        self.inspector = inspector or ProcessInspector()
        self._runner_factory: Callable[[], ClaudeCliRunner] = runner_factory or ClaudeCliRunner

        self._lock = threading.Lock()
        self._started = False
        self._state: _RunState | None = None
        _CONSTRUCTED_CLAUDE_ADAPTERS.add(self)

    # -- construction-time attestation kept live at start() -------------

    def _assert_binary_unchanged(self) -> None:
        try:
            resolved = self._binary_path.resolve(strict=True)
            info = resolved.lstat()
            data = resolved.read_bytes()
        except OSError as exc:
            raise BinaryAttestationError("Claude binary became unavailable") from exc
        sha256 = hashlib.sha256(data).hexdigest()
        baseline = self._binary_baseline
        if (
            sha256 != baseline["sha256"]
            or info.st_dev != baseline["device"]
            or info.st_ino != baseline["inode"]
            or info.st_uid != baseline["uid"]
            or info.st_mode != baseline["mode"]
            or info.st_size != baseline["size"]
            or info.st_mtime_ns != baseline["mtime_ns"]
        ):
            raise BinaryAttestationError(
                "Claude binary identity drifted since adapter construction"
            )

    # -- WorkerExecutionAdapter -------------------------------------------------

    async def start(self, spec: LaunchSpec) -> ProcessRef:
        with self._lock:
            if self._started:
                raise SecondStartRefused(
                    "ClaudeCodeWorkerAdapter instance already started a run"
                )
            self._started = True

        for field_name in ("run_id", "job_id", "worker_id"):
            value = getattr(spec, field_name)
            if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
                raise LaunchValidationError(f"invalid {field_name}")

        self._assert_binary_unchanged()

        workspace_lexical = Path(spec.workspace_path)
        if not workspace_lexical.is_absolute():
            raise LaunchValidationError("workspace path must be absolute")
        workspace_info = workspace_lexical.lstat()
        if stat.S_ISLNK(workspace_info.st_mode) or not stat.S_ISDIR(workspace_info.st_mode):
            raise LaunchValidationError("workspace must be a real directory")
        workspace = workspace_lexical.resolve(strict=True)

        run_dir_lexical = Path(spec.run_dir)
        if not run_dir_lexical.is_absolute():
            raise LaunchValidationError("run_dir must be absolute")
        run_dir_lexical.mkdir(parents=True, exist_ok=True, mode=0o700)
        run_dir = run_dir_lexical.resolve(strict=True)

        schema_path = Path(spec.result_schema_path)
        if not schema_path.is_absolute():
            raise LaunchValidationError("result schema path must be absolute")
        schema_path = schema_path.resolve(strict=True)
        schema_bytes = schema_path.read_bytes()
        if len(schema_bytes) > _MAX_RESULT_SCHEMA_BYTES:
            raise LaunchValidationError("result schema exceeds one MiB")
        try:
            schema = json.loads(schema_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LaunchValidationError(f"result schema is invalid JSON: {exc}") from exc

        if not isinstance(spec.prompt, str) or not spec.prompt:
            raise LaunchValidationError("prompt is required")
        evidence_bytes = spec.prompt.encode("utf-8")
        if len(evidence_bytes) > _MAX_PROMPT_EVIDENCE_BYTES:
            raise LaunchValidationError("prompt exceeds the sealed evidence bound")
        evidence_path = workspace.joinpath(*PurePosixPath(_EVIDENCE_RELATIVE_PATH).parts)
        evidence_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(str(evidence_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, evidence_bytes)
        finally:
            os.close(fd)
        evidence_sha256 = hashlib.sha256(evidence_bytes).hexdigest()

        # The frozen protocol only ever accepts a prompt canonically derived
        # from the sealed evidence file -- this adapter never constructs an
        # arbitrary prompt of its own.
        prompt = _protocol._derived_prompt(_EVIDENCE_RELATIVE_PATH, evidence_sha256)
        expected_result_sha256 = hashlib.sha256(
            _protocol._derived_result(evidence_sha256).encode("utf-8")
        ).hexdigest()

        session_id = str(uuid.uuid5(_SESSION_NAMESPACE, f"claude-code:{spec.run_id}"))

        policy = ClaudeCliInvocationPolicy(
            binary=self._binary_path,
            version=self._version,
            model=self._model,
            session_id=session_id,
            prompt=prompt,
            working_directory=workspace,
            isolated_home=self._isolated_home,
            isolated_tmp=self._isolated_tmp,
            evidence_relative_path=_EVIDENCE_RELATIVE_PATH,
            expected_result_sha256=expected_result_sha256,
            api_timeout_ms=self._api_timeout_ms,
            idle_timeout_seconds=self._idle_timeout_seconds,
            absolute_timeout_seconds=self._absolute_timeout_seconds,
            terminate_grace_seconds=self._terminate_grace_seconds,
            max_stdout_bytes=self._max_stdout_bytes,
            max_stderr_bytes=self._max_stderr_bytes,
            max_line_bytes=self._max_line_bytes,
            max_events=self._max_events,
            max_json_depth=self._max_json_depth,
            max_json_string_bytes=self._max_json_string_bytes,
            max_json_collection_items=self._max_json_collection_items,
        )
        try:
            # Never pass requested_flags or caller_environment: the compiler
            # refuses both by design, and this call site must never try.
            command = compile_claude_cli_command(policy)
        except ClaudeCliProtocolError as exc:
            raise LaunchValidationError(f"{exc.code}: {exc}") from exc

        if self._allowed_versions is not None and command.version not in self._allowed_versions:
            raise LaunchValidationError("compiled Claude CLI version is not allowlisted")

        run_dir_state_path = run_dir / "claude_fake_state.json"
        if run_dir_state_path.exists():
            raise LaunchValidationError(f"fake control state path already exists: {run_dir_state_path}")
        fake_controls = dict(self._fake_controls_template)
        fake_controls["MMX_FAKE_CLAUDE_STATE_FILE"] = str(run_dir_state_path)
        fake_controls.setdefault("MMX_FAKE_CLAUDE_VERSION", str(command.version))

        stdout_path = run_dir / "logs" / "claude_receipt.jsonl"
        stderr_path = run_dir / "logs" / "claude_stderr.log"
        result_path = run_dir / "output" / "result.json"
        _create_private_file(stdout_path)
        _create_private_file(stderr_path)
        _create_private_file(result_path)

        cancel_event = threading.Event()
        identity_event = threading.Event()
        identity_box: list[ClaudeCliProcessIdentity] = []

        def _sink(identity: ClaudeCliProcessIdentity) -> None:
            identity_box.append(identity)
            identity_event.set()

        runner = self._runner_factory()
        loop = asyncio.get_running_loop()
        run_future = loop.run_in_executor(
            None,
            functools.partial(
                runner.run,
                command,
                cancel_event=cancel_event,
                fake_controls=fake_controls,
                identity_sink=_sink,
            ),
        )
        identity_wait_future = loop.run_in_executor(
            None, identity_event.wait, self._identity_timeout_seconds
        )
        await asyncio.wait(
            {run_future, identity_wait_future}, return_when=asyncio.FIRST_COMPLETED
        )

        if not identity_event.is_set():
            # Either the bounded wait timed out, or the run finished/failed
            # before ever proving its identity.  Either way this must fail
            # closed and must never return a fabricated ProcessRef.
            cancel_event.set()
            if run_future.done():
                early_exception = run_future.exception()
                if early_exception is not None:
                    raise LaunchValidationError(
                        f"Claude CLI run failed before identity was attested: {early_exception}"
                    ) from early_exception
            with contextlib.suppress(BaseException):
                await run_future
            raise IdentityTimeoutError(
                "Claude CLI process identity was not attested within the bounded wait"
            )

        identity = identity_box[0]
        if not isinstance(identity, ClaudeCliProcessIdentity) or identity.pid <= 1 or identity.pgid <= 1:
            cancel_event.set()
            with contextlib.suppress(BaseException):
                await run_future
            raise IdentityTimeoutError("Claude CLI process identity is invalid")

        try:
            os_session_id: int | None = os.getsid(identity.pid)
        except OSError:
            os_session_id = None

        resolved_binary = Path(command.argv[0]).resolve(strict=True)
        binary_stat = resolved_binary.stat()
        binary = BinaryAttestation(
            path=str(self._binary_path),
            real_path=str(resolved_binary),
            version=str(command.version),
            sha256=command.binary_sha256,
            team_identifier=None,
            size=command.binary_size,
            device=command.binary_device,
            inode=command.binary_inode,
            mode=command.binary_mode,
            uid=command.binary_uid,
            gid=binary_stat.st_gid,
            mtime_ns=command.binary_mtime_ns,
        )

        ref = WorkerProcessRef(
            run_id=spec.run_id,
            pid=identity.pid,
            pgid=identity.pgid,
            process_start_identity=identity.start_identity,
            boot_session_id=self.inspector.boot_session_id(),
            launch_nonce=uuid.uuid4().hex,
            provider_session_id=None,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            result_path=str(result_path),
            started_at=identity.started_at,
            binary=binary,
            base_sha=spec.expected_base_sha or "",
            session_id=os_session_id,
        )

        state = _RunState(
            spec=spec,
            ref=ref,
            future=run_future,
            cancel_event=cancel_event,
            command=command,
            evidence_sha256=evidence_sha256,
            result_schema=schema,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            result_path=result_path,
        )
        self._state = state

        def _record_finished(_future: "asyncio.Future[ClaudeCliRunReceipt]") -> None:
            if state.finished_at is None:
                state.finished_at = _utc_now()

        run_future.add_done_callback(_record_finished)
        return ref

    def _state_for(self, ref: ProcessRef) -> _RunState:
        state = self._state
        if state is None or state.ref != ref:
            raise ProcessIdentityError("unknown or altered ProcessRef")
        return state

    @staticmethod
    def _status_for_code(code: str) -> WorkerRunStatus:
        if code in {"CANCELLED_BEFORE_START", "CANCELLED_AFTER_START"}:
            return WorkerRunStatus.CANCELLED
        if code in {"ABSOLUTE_TIMEOUT", "IDLE_TIMEOUT"}:
            return WorkerRunStatus.TIMED_OUT
        return WorkerRunStatus.FAILED

    async def status(self, ref: ProcessRef) -> WorkerRunStatus:
        state = self._state_for(ref)
        if state.receipt is not None:
            return state.receipt.result.status
        if not state.future.done():
            return WorkerRunStatus.CANCELLING if state.cancel_event.is_set() else WorkerRunStatus.RUNNING
        exc = state.future.exception()
        if exc is None:
            return WorkerRunStatus.SUCCEEDED
        if isinstance(exc, ClaudeCliProtocolError):
            return self._status_for_code(exc.code)
        return WorkerRunStatus.FAILED

    async def collect_result(self, ref: ProcessRef) -> CollectionReceipt:
        state = self._state_for(ref)
        if state.receipt is not None:
            return state.receipt
        try:
            run_receipt = await state.future
        except ClaudeCliProtocolError as exc:
            receipt = self._build_failure_receipt(state, exc)
        else:
            receipt = self._build_success_receipt(state, run_receipt)
        state.receipt = receipt
        return receipt

    def _build_failure_receipt(
        self, state: _RunState, exc: ClaudeCliProtocolError
    ) -> CollectionReceipt:
        status = self._status_for_code(exc.code)
        finished_at = state.finished_at or _utc_now()
        empty_sha = hashlib.sha256(b"").hexdigest()
        result = WorkerResult(
            job_id=state.spec.job_id,
            run_id=state.spec.run_id,
            worker_id=state.spec.worker_id,
            status=status,
            structured_output=None,
            artifact_manifest=(),
            git_manifest={},
            usage={},
            provider_session_id=None,
            exit_code=None,
            started_at=state.ref.started_at,
            finished_at=finished_at,
            error=f"{exc.code}: {exc}"[:3000],
        )
        return CollectionReceipt(
            process_ref=state.ref,
            result=result,
            stdout_sha256=empty_sha,
            stderr_sha256=empty_sha,
            result_sha256=None,
        )

    def _build_success_receipt(
        self, state: _RunState, receipt: ClaudeCliRunReceipt
    ) -> CollectionReceipt:
        finished_at = state.finished_at or _utc_now()
        structured_output = json.loads(_protocol._derived_result(state.evidence_sha256))
        empty_sha = hashlib.sha256(b"").hexdigest()
        # ``state.ref`` is never mutated after start(): it is the stable
        # identity every subsequent status()/collect_result()/cancel() call
        # is checked against.  Only the *returned* receipt's process_ref
        # carries the now-known provider_session_id.
        ref = dataclasses.replace(state.ref, provider_session_id=receipt.session_id)
        try:
            validated = _validate_structured_output(structured_output, state.result_schema)
        except ResultValidationError as exc:
            result = WorkerResult(
                job_id=state.spec.job_id,
                run_id=state.spec.run_id,
                worker_id=state.spec.worker_id,
                status=WorkerRunStatus.INVALID_RESULT,
                structured_output=None,
                artifact_manifest=(),
                git_manifest={},
                usage={},
                provider_session_id=receipt.session_id,
                exit_code=receipt.returncode,
                started_at=ref.started_at,
                finished_at=finished_at,
                error=str(exc)[:3000],
            )
            self._write_receipt_files(state, receipt, structured_output=None)
            return CollectionReceipt(
                process_ref=ref,
                result=result,
                stdout_sha256=_sha256_path(state.stdout_path),
                stderr_sha256=empty_sha,
                result_sha256=None,
            )

        usage = {
            "input_tokens": receipt.input_tokens,
            "output_tokens": receipt.output_tokens,
            "cache_creation_input_tokens": receipt.cache_creation_input_tokens,
            "cache_read_input_tokens": receipt.cache_read_input_tokens,
            "cost_microusd": receipt.cost_microusd,
        }
        result = WorkerResult(
            job_id=state.spec.job_id,
            run_id=state.spec.run_id,
            worker_id=state.spec.worker_id,
            status=WorkerRunStatus.SUCCEEDED,
            structured_output=validated,
            artifact_manifest=(),
            git_manifest={},
            usage=usage,
            provider_session_id=receipt.session_id,
            exit_code=receipt.returncode,
            started_at=ref.started_at,
            finished_at=finished_at,
            error=None,
        )
        self._write_receipt_files(state, receipt, structured_output=validated)
        return CollectionReceipt(
            process_ref=ref,
            result=result,
            stdout_sha256=_sha256_path(state.stdout_path),
            stderr_sha256=empty_sha,
            result_sha256=receipt.result_sha256,
        )

    @staticmethod
    def _write_receipt_files(
        state: _RunState,
        receipt: ClaudeCliRunReceipt,
        *,
        structured_output: Mapping[str, Any] | None,
    ) -> None:
        # The protocol layer discards raw provider bytes by design (only
        # digests/counts survive) so the "stdout" record here is the
        # receipt's own bounded, secret-free dict -- never fabricated
        # provider output.
        with open(state.stdout_path, "wb") as handle:
            handle.write(
                json.dumps(receipt.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
            )
            handle.write(b"\n")
        if structured_output is not None:
            with open(state.result_path, "wb") as handle:
                handle.write(
                    json.dumps(structured_output, sort_keys=True, separators=(",", ":")).encode(
                        "utf-8"
                    )
                )

    async def cancel(self, ref: ProcessRef, reason: str) -> CancelReceipt:
        state = self._state_for(ref)
        reason_text = str(reason).strip()
        if not reason_text:
            raise LaunchValidationError("cancellation reason is required")
        already_exited = state.future.done()
        state.cancel_event.set()
        cleanup = None
        try:
            run_receipt = await state.future
            cleanup = run_receipt.cleanup
        except ClaudeCliProtocolError as exc:
            cleanup = exc.cleanup
        except BaseException:
            cleanup = None
        signal_sent = bool(cleanup is not None and (cleanup.term_sent or cleanup.kill_sent))
        escalated = bool(cleanup is not None and cleanup.kill_sent)
        finished_at = state.finished_at or _utc_now()
        return CancelReceipt(
            run_id=ref.run_id,
            reason=reason_text[:1000],
            signal_sent=signal_sent,
            escalated_to_sigkill=escalated,
            already_exited=already_exited,
            finished_at=finished_at,
        )

    async def run_validation_argv(
        self,
        spec: LaunchSpec,
        argv: Sequence[str],
        *,
        timeout_seconds: float = 300.0,
    ) -> ValidationReceipt:
        """Run one declared argv directly, without auth, in a closed environment.

        This never touches the configured Claude binary, a credential, or a
        model/provider session.  The child environment is always this
        module's own fixed, minimal tuple -- ambient state is never read or
        forwarded.
        """

        if isinstance(argv, (str, bytes)) or not isinstance(argv, Sequence):
            raise LaunchValidationError("validation command must be an argv sequence")
        exact_argv = tuple(argv)
        if not exact_argv or any(
            not isinstance(value, str) or not value or "\x00" in value for value in exact_argv
        ):
            raise LaunchValidationError(
                "validation argv must contain non-empty strings without NUL bytes"
            )
        if sum(len(value.encode("utf-8")) + 1 for value in exact_argv) > _MAX_VALIDATION_ARGV_BYTES:
            raise LaunchValidationError("validation argv exceeds 64 KiB")
        executable_name = PurePosixPath(exact_argv[0]).name.lower()
        if executable_name in _SHELL_EXECUTABLE_NAMES:
            raise LaunchValidationError("validation argv may not invoke a shell")
        timeout = float(timeout_seconds)
        if not 0.1 <= timeout <= 3600:
            raise LaunchValidationError("validation timeout is out of bounds")

        workspace_lexical = Path(spec.workspace_path)
        if not workspace_lexical.is_absolute():
            raise LaunchValidationError("workspace path must be absolute")
        workspace = workspace_lexical.resolve(strict=True)

        environment = dict(_VALIDATION_SAFE_ENVIRONMENT)
        process = await asyncio.create_subprocess_exec(
            *exact_argv,
            cwd=str(workspace),
            env=environment,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        timed_out = False
        error: str | None = None
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            timed_out = True
            error = f"validation timed out after {timeout:g}s"
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
            stdout_bytes, stderr_bytes = b"", b""
        stdout_bytes = stdout_bytes[:_MAX_VALIDATION_STDOUT_BYTES]
        stderr_bytes = stderr_bytes[:_MAX_VALIDATION_STDERR_BYTES]
        return ValidationReceipt(
            argv=exact_argv,
            exit_code=process.returncode,
            stdout_sha256=hashlib.sha256(stdout_bytes).hexdigest(),
            stdout_size=len(stdout_bytes),
            stderr_sha256=hashlib.sha256(stderr_bytes).hexdigest(),
            stderr_size=len(stderr_bytes),
            timed_out=timed_out,
            error=error,
        )


__all__ = [
    "BinaryAttestationError",
    "ClaudeCodeWorkerAdapter",
    "ClaudeWorkerError",
    "IdentityTimeoutError",
    "LaunchSpec",
    "LaunchValidationError",
    "ProcessIdentityError",
    "ProcessInspector",
    "ProcessRef",
    "ResultValidationError",
    "SecondStartRefused",
]
