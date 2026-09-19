from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_after(path: str, anchor: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    position = text.find(anchor)
    if position < 0:
        raise SystemExit(f"{path}: anchor not found: {anchor!r}")
    head, tail = text[:position], text[position:]
    count = tail.count(old)
    if count != 1:
        raise SystemExit(
            f"{path}: expected one post-anchor replacement, found {count}"
        )
    target.write_text(head + tail.replace(old, new, 1), encoding="utf-8")


replace_once(
    "control_plane/codex_worker.py",
    "from datetime import datetime, timezone\n",
    "from datetime import datetime, timezone\nfrom enum import Enum\n",
)
replace_once(
    "control_plane/codex_worker.py",
    "    WorkerLaunchSpec,\n    WorkerProcessRef,\n",
    "    WorkerLaunchSpec,\n"
    "    WorkerProcessRef,\n"
    "    WorkerRecoveryBinding,\n"
    "    WorkerRecoveryContractError,\n"
    "    worker_launch_spec_sha256,\n",
)
replace_once(
    "control_plane/codex_worker.py",
    "def _utc_now() -> str:\n",
    r'''class _RecoveredPresence(str, Enum):
    LIVE = "LIVE"
    ABSENT = "ABSENT"
    RESIDUAL_GROUP = "RESIDUAL_GROUP"
    IDENTITY_CHANGED = "IDENTITY_CHANGED"
    BOOT_CHANGED = "BOOT_CHANGED"
    UNKNOWN = "UNKNOWN"


@dataclasses.dataclass
class _RecoveredRunState:
    spec: LaunchSpec
    ref: ProcessRef
    parser: _JSONLState
    baseline: _GitSnapshot
    monitor_task: asyncio.Task[None] | None = None
    termination_lock: asyncio.Lock = dataclasses.field(default_factory=asyncio.Lock)
    status: WorkerRunStatus = WorkerRunStatus.RUNNING
    stream_errors: list[str] = dataclasses.field(default_factory=list)
    cancel_reason: str | None = None
    timed_out: bool = False
    escalated: bool = False
    finished_at: str | None = None
    receipt: CollectionReceipt | None = None
    cancel_receipt: CancelReceipt | None = None
    signal_sent: bool = False
    sigkill_sent: bool = False


_RunStateLike = _RunState | _RecoveredRunState


def _utc_now() -> str:
''',
)
replace_once(
    "control_plane/codex_worker.py",
    "def _process_group_exists(pgid: int) -> bool:\n",
    r'''async def _tail_durable_stream(
    path: Path,
    *,
    fd: int,
    name: str,
    maximum: int,
    line_maximum: int | None,
    parser: _JSONLState | None,
    state: _RunState,
) -> None:
    """Observe a child-written regular file while retaining one owned descriptor."""

    total = 0
    line_buffer = bytearray()
    accepting = True
    try:
        with path.open("rb", buffering=0) as reader:
            while True:
                chunk = reader.read(64 * 1024)
                if not chunk:
                    if state.process_wait_task.done():
                        break
                    await asyncio.sleep(0.01)
                    continue
                total += len(chunk)
                if accepting and total > maximum:
                    accepting = False
                    state.stream_errors.append(
                        f"{name} exceeded {maximum} bytes"
                    )
                    state.violation.set()
                if parser is None or not accepting:
                    continue
                line_buffer.extend(chunk)
                while True:
                    newline = line_buffer.find(b"\n")
                    if newline < 0:
                        break
                    line = bytes(line_buffer[:newline])
                    del line_buffer[: newline + 1]
                    if line_maximum is not None and len(line) > line_maximum:
                        state.stream_errors.append(
                            f"{name} JSONL line exceeded {line_maximum} bytes"
                        )
                        state.violation.set()
                    else:
                        parser.consume(line)
                if line_maximum is not None and len(line_buffer) > line_maximum:
                    state.stream_errors.append(
                        f"{name} JSONL line exceeded {line_maximum} bytes"
                    )
                    state.violation.set()
                    accepting = False
        if parser is not None and accepting and line_buffer:
            if line_maximum is not None and len(line_buffer) > line_maximum:
                state.stream_errors.append(
                    f"{name} JSONL line exceeded {line_maximum} bytes"
                )
                state.violation.set()
            else:
                parser.consume(bytes(line_buffer))
    except Exception as exc:  # noqa: BLE001 - invalid-result evidence
        state.stream_errors.append(
            f"{name} durable stream failure: {type(exc).__name__}: {exc}"
        )
        state.violation.set()
    finally:
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _bound_durable_log(path: Path, *, maximum: int, name: str) -> bool:
    """Restore the bounded-log contract after direct child writes."""

    try:
        info = path.lstat()
    except OSError as exc:
        raise ResultValidationError(f"durable {name} is unavailable") from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) & 0o077
    ):
        raise ResultValidationError(
            f"durable {name} is not a private single-link regular file"
        )
    if info.st_size <= maximum:
        return False
    flags = (
        os.O_RDWR
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = os.open(path, flags)
    try:
        observed = os.fstat(descriptor)
        if (observed.st_dev, observed.st_ino) != (info.st_dev, info.st_ino):
            raise ResultValidationError(f"durable {name} identity changed")
        os.ftruncate(descriptor, maximum)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return True


def _replay_durable_jsonl(path: Path) -> _JSONLState:
    try:
        info = path.lstat()
    except OSError as exc:
        raise ResultValidationError("durable stdout is unavailable") from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) & 0o077
        or info.st_size > _MAX_STDOUT_BYTES
    ):
        raise ResultValidationError(
            "durable stdout is not a private bounded regular file"
        )
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ResultValidationError("durable stdout is unavailable") from exc
    if len(raw) != info.st_size:
        raise ResultValidationError("durable stdout changed while reading")
    parser = _JSONLState()
    for line in raw.splitlines():
        if len(line) > _MAX_JSONL_LINE_BYTES:
            raise ResultValidationError(
                f"stdout JSONL line exceeded {_MAX_JSONL_LINE_BYTES} bytes"
            )
        parser.consume(line)
    return parser


def _process_group_exists(pgid: int) -> bool:
''',
)
replace_once(
    "control_plane/codex_worker.py",
    r'''async def _wait_for_process_group_exit(pgid: int, *, timeout: float = 2.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while _process_group_exists(pgid):
        if asyncio.get_running_loop().time() >= deadline:
            return False
        await asyncio.sleep(0.02)
    return True
''',
    r'''async def _wait_for_process_group_exit(pgid: int, *, timeout: float = 2.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        try:
            exists = _process_group_exists(pgid)
        except ProcessIdentityError:
            if asyncio.get_running_loop().time() >= deadline:
                raise
            await asyncio.sleep(0.02)
            continue
        if not exists:
            return True
        if asyncio.get_running_loop().time() >= deadline:
            return False
        await asyncio.sleep(0.02)
    return True
''',
)
replace_once(
    "control_plane/codex_worker.py",
    "        self._runs: dict[str, _RunState] = {}\n",
    "        self._runs: dict[str, _RunStateLike] = {}\n",
)

start_anchor = "    async def start(self, spec: LaunchSpec) -> ProcessRef:\n"
replace_after(
    "control_plane/codex_worker.py",
    start_anchor,
    "                stdout=asyncio.subprocess.PIPE,\n"
    "                stderr=asyncio.subprocess.PIPE,\n",
    "                stdout=stdout_fd,\n                stderr=stderr_fd,\n",
)
replace_after(
    "control_plane/codex_worker.py",
    start_anchor,
    "        if process.stdin is None or process.stdout is None or process.stderr is None:\n",
    "        if process.stdin is None:\n",
)
replace_after(
    "control_plane/codex_worker.py",
    start_anchor,
    '                CodexWorkerError("Codex process pipes were not created"),\n',
    '                CodexWorkerError("Codex process stdin pipe was not created"),\n',
)
replace_after(
    "control_plane/codex_worker.py",
    start_anchor,
    r'''        state.stdout_task = asyncio.create_task(_pump_stream(
            process.stdout,
            fd=stdout_fd,
            name="stdout",
            maximum=_MAX_STDOUT_BYTES,
            line_maximum=_MAX_JSONL_LINE_BYTES,
            parser=parser,
            state=state,
        ))
        state.stderr_task = asyncio.create_task(_pump_stream(
            process.stderr,
            fd=stderr_fd,
            name="stderr",
            maximum=_MAX_STDERR_BYTES,
            line_maximum=None,
            parser=None,
            state=state,
        ))
''',
    r'''        state.stdout_task = asyncio.create_task(_tail_durable_stream(
            stdout_path,
            fd=stdout_fd,
            name="stdout",
            maximum=_MAX_STDOUT_BYTES,
            line_maximum=_MAX_JSONL_LINE_BYTES,
            parser=parser,
            state=state,
        ))
        state.stderr_task = asyncio.create_task(_tail_durable_stream(
            stderr_path,
            fd=stderr_fd,
            name="stderr",
            maximum=_MAX_STDERR_BYTES,
            line_maximum=None,
            parser=None,
            state=state,
        ))
''',
)

replace_once(
    "control_plane/codex_worker.py",
    "    def launch_attestation(self, ref: ProcessRef) -> LaunchAttestation:\n",
    r'''    @staticmethod
    def _group_presence_for_recovery(pgid: int) -> _RecoveredPresence:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return _RecoveredPresence.ABSENT
        except (PermissionError, OSError):
            return _RecoveredPresence.UNKNOWN
        return _RecoveredPresence.LIVE

    def _observe_recovered_ref(self, ref: ProcessRef) -> _RecoveredPresence:
        try:
            boot = self.inspector.boot_session_id()
        except Exception:
            return _RecoveredPresence.UNKNOWN
        if boot != ref.boot_session_id:
            return _RecoveredPresence.BOOT_CHANGED
        try:
            observed = self.inspector.inspect(ref.pid)
        except ProcessIdentityError:
            try:
                os.kill(ref.pid, 0)
            except ProcessLookupError:
                group = self._group_presence_for_recovery(ref.pgid)
                if group is _RecoveredPresence.ABSENT:
                    return _RecoveredPresence.ABSENT
                if group is _RecoveredPresence.LIVE:
                    return _RecoveredPresence.RESIDUAL_GROUP
                return _RecoveredPresence.UNKNOWN
            except (PermissionError, OSError):
                return _RecoveredPresence.UNKNOWN
            return _RecoveredPresence.UNKNOWN
        except Exception:
            return _RecoveredPresence.UNKNOWN
        expected = {
            "start_identity": ref.process_start_identity,
            "pgid": ref.pgid,
            "session_id": ref.session_id,
            "effective_uid": ref.effective_uid,
            "effective_gid": ref.effective_gid,
            "real_uid": ref.real_uid,
            "real_gid": ref.real_gid,
        }
        if any(
            value is None or getattr(observed, name, None) != value
            for name, value in expected.items()
        ):
            return _RecoveredPresence.IDENTITY_CHANGED
        if (
            self._group_presence_for_recovery(ref.pgid)
            is not _RecoveredPresence.LIVE
        ):
            return _RecoveredPresence.UNKNOWN
        return _RecoveredPresence.LIVE

    @staticmethod
    def _recovery_presence_error(
        presence: _RecoveredPresence,
    ) -> ProcessIdentityError:
        messages = {
            _RecoveredPresence.RESIDUAL_GROUP: (
                "recovered worker leader is absent while its process group remains live"
            ),
            _RecoveredPresence.IDENTITY_CHANGED: (
                "recovered worker process identity changed"
            ),
            _RecoveredPresence.BOOT_CHANGED: (
                "recovered worker boot identity changed"
            ),
            _RecoveredPresence.UNKNOWN: (
                "recovered worker process identity is unreadable or contradictory"
            ),
        }
        return ProcessIdentityError(
            messages.get(presence, "recovered worker identity is invalid")
        )

    def reattach(
        self, spec: LaunchSpec, binding: WorkerRecoveryBinding
    ) -> ProcessRef:
        if binding.adapter_id != self.adapter_id:
            raise ProcessIdentityError(
                "recovery binding adapter identity changed"
            )
        try:
            recovered_spec = binding.recover_launch_spec(type(spec))
        except WorkerRecoveryContractError as exc:
            raise ProcessIdentityError(str(exc)) from exc
        if (
            recovered_spec != spec
            or worker_launch_spec_sha256(spec) != binding.launch_spec_sha256
        ):
            raise ProcessIdentityError(
                "recovery launch specification changed"
            )
        ref = binding.process_ref
        expected_paths = (
            Path(spec.run_dir) / "logs" / "stdout.jsonl",
            Path(spec.run_dir) / "logs" / "stderr.log",
            Path(spec.run_dir) / "output" / "result.json",
        )
        observed_paths = tuple(
            Path(value)
            for value in (ref.stdout_path, ref.stderr_path, ref.result_path)
        )
        if tuple(path.resolve(strict=False) for path in observed_paths) != tuple(
            path.resolve(strict=False) for path in expected_paths
        ):
            raise ProcessIdentityError("recovery result coordinates changed")
        if ref.binary != self.binary or (
            spec.expected_base_sha is not None
            and ref.base_sha != spec.expected_base_sha
        ):
            raise ProcessIdentityError(
                "recovery binary or base identity changed"
            )
        existing = self._runs.get(ref.run_id)
        if existing is not None:
            if (
                isinstance(existing, _RecoveredRunState)
                and existing.ref == ref
                and existing.spec == spec
            ):
                return ref
            raise ProcessIdentityError(
                "run is already bound to another execution"
            )
        presence = self._observe_recovered_ref(ref)
        if presence not in {
            _RecoveredPresence.LIVE,
            _RecoveredPresence.ABSENT,
        }:
            raise self._recovery_presence_error(presence)
        self._runs[ref.run_id] = _RecoveredRunState(
            spec=spec,
            ref=ref,
            parser=_JSONLState(),
            baseline=_GitSnapshot(ref.base_sha, b""),
        )
        return ref

    async def _monitor_recovered(self, state: _RecoveredRunState) -> None:
        try:
            started = datetime.fromisoformat(
                state.ref.started_at.replace("Z", "+00:00")
            )
            if started.tzinfo is None:
                raise ValueError("missing timezone")
        except ValueError as exc:
            raise ProcessIdentityError(
                "recovered worker start timestamp is invalid"
            ) from exc
        elapsed = max(
            0.0,
            (
                datetime.now(timezone.utc)
                - started.astimezone(timezone.utc)
            ).total_seconds(),
        )
        deadline = asyncio.get_running_loop().time() + max(
            0.0, float(state.spec.timeout_seconds) - elapsed
        )
        while True:
            presence = self._observe_recovered_ref(state.ref)
            if presence is _RecoveredPresence.ABSENT:
                state.finished_at = state.finished_at or _utc_now()
                return
            if presence is not _RecoveredPresence.LIVE:
                raise self._recovery_presence_error(presence)
            if asyncio.get_running_loop().time() >= deadline:
                state.timed_out = True
                await self._terminate_recovered(state)
                state.finished_at = state.finished_at or _utc_now()
                return
            await asyncio.sleep(0.05)

    def _ensure_recovered_monitor(
        self, state: _RecoveredRunState
    ) -> asyncio.Task[None]:
        if state.monitor_task is None:
            state.monitor_task = asyncio.create_task(
                self._monitor_recovered(state)
            )
        return state.monitor_task

    async def _wait_recovered_absence(
        self, state: _RecoveredRunState, *, timeout: float
    ) -> _RecoveredPresence:
        deadline = asyncio.get_running_loop().time() + max(0.0, timeout)
        while True:
            presence = self._observe_recovered_ref(state.ref)
            if presence is not _RecoveredPresence.LIVE:
                return presence
            if asyncio.get_running_loop().time() >= deadline:
                return presence
            await asyncio.sleep(0.02)

    @staticmethod
    def _signal_recovered_group(
        state: _RecoveredRunState, value: signal.Signals
    ) -> bool:
        try:
            os.killpg(state.ref.pgid, value)
        except ProcessLookupError:
            return False
        except OSError as exc:
            raise ProcessIdentityError(
                f"recovered worker signal failed: {type(exc).__name__}"
            ) from exc
        return True

    async def _terminate_recovered(
        self, state: _RecoveredRunState
    ) -> tuple[bool, bool, bool]:
        async with state.termination_lock:
            presence = self._observe_recovered_ref(state.ref)
            if presence is _RecoveredPresence.ABSENT:
                return (
                    state.signal_sent,
                    state.sigkill_sent,
                    not state.signal_sent,
                )
            if presence is not _RecoveredPresence.LIVE:
                raise self._recovery_presence_error(presence)
            if not state.signal_sent:
                if self._signal_recovered_group(state, signal.SIGTERM):
                    state.signal_sent = True
                else:
                    presence = self._observe_recovered_ref(state.ref)
                    if presence is _RecoveredPresence.ABSENT:
                        return False, False, True
                    raise self._recovery_presence_error(presence)
            presence = await self._wait_recovered_absence(
                state,
                timeout=float(state.spec.cancel_grace_seconds),
            )
            if presence is _RecoveredPresence.ABSENT:
                return state.signal_sent, False, False
            if presence not in {
                _RecoveredPresence.LIVE,
                _RecoveredPresence.RESIDUAL_GROUP,
            }:
                raise self._recovery_presence_error(presence)
            if not state.sigkill_sent:
                if (
                    presence is _RecoveredPresence.LIVE
                    and self._observe_recovered_ref(state.ref)
                    is not _RecoveredPresence.LIVE
                ):
                    raise ProcessIdentityError(
                        "recovered worker identity changed before SIGKILL"
                    )
                if self._signal_recovered_group(state, signal.SIGKILL):
                    state.signal_sent = True
                    state.sigkill_sent = True
                    state.escalated = True
            presence = await self._wait_recovered_absence(
                state,
                timeout=_LOCAL_TRANSPORT_FINALIZATION_SECONDS,
            )
            if presence is not _RecoveredPresence.ABSENT:
                if presence is _RecoveredPresence.LIVE:
                    raise ProcessIdentityError(
                        "recovered worker process group survived SIGKILL"
                    )
                raise self._recovery_presence_error(presence)
            return state.signal_sent, state.sigkill_sent, False

    async def _cancel_recovered(
        self, state: _RecoveredRunState, reason: str
    ) -> CancelReceipt:
        if state.cancel_receipt is not None:
            return state.cancel_receipt
        state.cancel_reason = reason[:1000]
        state.status = WorkerRunStatus.CANCELLING

        async def transaction() -> CancelReceipt:
            sent, escalated, already_exited = await self._terminate_recovered(
                state
            )
            await self._ensure_recovered_monitor(state)
            receipt = CancelReceipt(
                run_id=state.ref.run_id,
                reason=state.cancel_reason or reason,
                signal_sent=sent,
                escalated_to_sigkill=escalated,
                already_exited=already_exited,
                finished_at=state.finished_at or _utc_now(),
            )
            state.cancel_receipt = receipt
            return receipt

        task = asyncio.create_task(transaction())
        pending: asyncio.CancelledError | None = None
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError as exc:
                pending = pending or exc
        try:
            receipt = task.result()
        except BaseException as exc:
            if pending is not None:
                pending.add_note(str(exc))
                raise pending from exc
            raise
        if pending is not None:
            raise pending
        return receipt

    def launch_attestation(self, ref: ProcessRef) -> LaunchAttestation:
''',
)
replace_once(
    "control_plane/codex_worker.py",
    r'''        return self._state_for(ref).launch_attestation

    def _state_for(self, ref: ProcessRef) -> _RunState:
        state = self._runs.get(ref.run_id)
''',
    r'''        state = self._state_for(ref)
        if isinstance(state, _RecoveredRunState):
            raise ProcessIdentityError(
                "launch attestation belongs to the durable recovery binding"
            )
        return state.launch_attestation

    def _state_for(self, ref: ProcessRef) -> _RunStateLike:
        state = self._runs.get(ref.run_id)
''',
)
replace_once(
    "control_plane/codex_worker.py",
    r'''    async def status(self, ref: ProcessRef) -> WorkerRunStatus:
        state = self._state_for(ref)
        if state.receipt is not None:
            return state.receipt.result.status
        if state.monitor_task is not None and state.monitor_task.done():
            # Collection performs the terminal validation; until then a clean
            # process exit is not allowed to masquerade as success.
            return WorkerRunStatus.CANCELLING if state.cancel_reason else WorkerRunStatus.RUNNING
        return state.status
''',
    r'''    async def status(self, ref: ProcessRef) -> WorkerRunStatus:
        state = self._state_for(ref)
        if state.receipt is not None:
            return state.receipt.result.status
        if isinstance(state, _RecoveredRunState):
            presence = self._observe_recovered_ref(ref)
            if presence not in {
                _RecoveredPresence.LIVE,
                _RecoveredPresence.ABSENT,
            }:
                raise self._recovery_presence_error(presence)
            return (
                WorkerRunStatus.CANCELLING
                if state.cancel_reason
                else WorkerRunStatus.RUNNING
            )
        if state.monitor_task is not None and state.monitor_task.done():
            # Collection performs the terminal validation; until then a clean
            # process exit is not allowed to masquerade as success.
            return WorkerRunStatus.CANCELLING if state.cancel_reason else WorkerRunStatus.RUNNING
        return state.status
''',
)
replace_once(
    "control_plane/codex_worker.py",
    r'''        reason = str(reason).strip()
        if not reason:
            raise LaunchValidationError("cancellation reason is required")
        state.cancel_reason = reason[:1000]
''',
    r'''        reason = str(reason).strip()
        if not reason:
            raise LaunchValidationError("cancellation reason is required")
        if isinstance(state, _RecoveredRunState):
            return await self._cancel_recovered(state, reason)
        state.cancel_reason = reason[:1000]
''',
)
replace_once(
    "control_plane/codex_worker.py",
    r'''    async def collect_result(self, ref: ProcessRef) -> CollectionReceipt:
        state = self._state_for(ref)
        if state.receipt is not None:
            return state.receipt
        if state.monitor_task is None:
            raise CodexWorkerError("run monitor was not started")
        await state.monitor_task
        finished_at = state.finished_at or _utc_now()
        exit_code = state.process.returncode
        status_value = WorkerRunStatus.FAILED
''',
    r'''    async def collect_result(self, ref: ProcessRef) -> CollectionReceipt:
        state = self._state_for(ref)
        if state.receipt is not None:
            return state.receipt
        if isinstance(state, _RecoveredRunState):
            await self._ensure_recovered_monitor(state)
            exit_code = None
        else:
            if state.monitor_task is None:
                raise CodexWorkerError("run monitor was not started")
            await state.monitor_task
            exit_code = state.process.returncode
        finished_at = state.finished_at or _utc_now()
        stdout_path = Path(ref.stdout_path)
        stderr_path = Path(ref.stderr_path)
        if _bound_durable_log(
            stdout_path,
            maximum=_MAX_STDOUT_BYTES,
            name="stdout",
        ):
            marker = f"stdout exceeded {_MAX_STDOUT_BYTES} bytes"
            if marker not in state.stream_errors:
                state.stream_errors.append(marker)
        if _bound_durable_log(
            stderr_path,
            maximum=_MAX_STDERR_BYTES,
            name="stderr",
        ):
            marker = f"stderr exceeded {_MAX_STDERR_BYTES} bytes"
            if marker not in state.stream_errors:
                state.stream_errors.append(marker)
        try:
            state.parser = _replay_durable_jsonl(stdout_path)
        except ResultValidationError as exc:
            state.parser = _JSONLState()
            message = str(exc)[:3000]
            if message not in state.stream_errors:
                state.stream_errors.append(message)
        status_value = WorkerRunStatus.FAILED
''',
)
replace_once(
    "control_plane/codex_worker.py",
    "            if not state.finalization.group_proven_absent:\n"
    "                self._validate_process_ref_after_exit(state)\n",
    "            if (\n"
    "                isinstance(state, _RunState)\n"
    "                and not state.finalization.group_proven_absent\n"
    "            ):\n"
    "                self._validate_process_ref_after_exit(state)\n",
)
replace_once(
    "control_plane/codex_worker.py",
    "            elif exit_code != 0:\n",
    "            elif exit_code is not None and exit_code != 0:\n",
)
replace_once(
    "control_plane/codex_worker.py",
    '    "WorkerRunStatus",\n',
    '    "WorkerRunStatus",\n    "WorkerRecoveryBinding",\n',
)
