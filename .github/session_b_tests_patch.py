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


def append_once(path: str, marker: str, payload: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if marker in text:
        return
    target.write_text(text.rstrip() + "\n\n" + payload.strip() + "\n", encoding="utf-8")


replace_once(
    "tests/test_executive_codex_worker.py",
    "from control_plane import codex_worker as cw\n",
    "from control_plane import codex_worker as cw\n"
    "from control_plane import worker_execution_contract as wec\n",
)
replace_once(
    "tests/test_executive_codex_worker.py",
    "import sys\nimport time\n",
    "import sys\nimport threading\nimport time\n",
)

append_once(
    "tests/test_worker_execution_contract.py",
    "test_worker_recovery_binding_round_trips_exact_launch_spec",
    r'''
def test_worker_recovery_binding_round_trips_exact_launch_spec(tmp_path: Path) -> None:
    prompt_path = tmp_path / "run" / "input" / "worker-prompt.txt"
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_text("bounded recovery prompt", encoding="utf-8")
    prompt_path.chmod(0o600)
    spec = _spec(
        tmp_path,
        run_dir=tmp_path / "run",
        prompt="bounded recovery prompt",
        authorities=("READ", "RUN_TESTS"),
        allowed_artifact_paths=("research/proof.md",),
        isolation_manifest={"schema_version": "fixture", "entries": []},
        isolation_manifest_sha256="1" * 64,
        secret_canary_verdict={"schema_version": "fixture", "passed": True},
    )
    process = WorkerProcessRef(
        run_id=spec.run_id,
        pid=41,
        pgid=41,
        process_start_identity="start-41",
        boot_session_id="boot-fixture",
        launch_nonce="nonce-fixture",
        provider_session_id=None,
        stdout_path=str(tmp_path / "run" / "logs" / "stdout.jsonl"),
        stderr_path=str(tmp_path / "run" / "logs" / "stderr.log"),
        result_path=str(tmp_path / "run" / "output" / "result.json"),
        started_at="2026-09-18T00:00:00+00:00",
        binary=_binary(),
        base_sha="c" * 40,
        session_id=41,
        effective_uid=501,
        effective_gid=20,
        real_uid=501,
        real_gid=20,
    )
    binding = worker_execution_contract.WorkerRecoveryBinding.bind(
        adapter_id="codex-cli",
        spec=spec,
        process_ref=process,
        prompt_path=prompt_path,
    )
    restored = worker_execution_contract.WorkerRecoveryBinding.from_dict(
        binding.to_dict()
    )
    assert restored.process_ref == process
    assert restored.recover_launch_spec() == spec
    assert restored.launch_spec_sha256 == (
        worker_execution_contract.worker_launch_spec_sha256(spec)
    )
    assert restored.collection_contract_version == (
        worker_execution_contract.DURABLE_COLLECTION_CONTRACT_VERSION
    )
    assert "bounded recovery prompt" not in repr(restored)


def test_worker_recovery_binding_refuses_prompt_or_identity_drift(tmp_path: Path) -> None:
    prompt_path = tmp_path / "run" / "input" / "worker-prompt.txt"
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_text("original prompt", encoding="utf-8")
    prompt_path.chmod(0o600)
    spec = _spec(tmp_path, run_dir=tmp_path / "run", prompt="original prompt")
    process = WorkerProcessRef(
        run_id=spec.run_id,
        pid=52,
        pgid=52,
        process_start_identity="start-52",
        boot_session_id="boot-fixture",
        launch_nonce="nonce-fixture",
        provider_session_id=None,
        stdout_path=str(tmp_path / "run" / "logs" / "stdout.jsonl"),
        stderr_path=str(tmp_path / "run" / "logs" / "stderr.log"),
        result_path=str(tmp_path / "run" / "output" / "result.json"),
        started_at="2026-09-18T00:00:00+00:00",
        binary=_binary(),
        base_sha="c" * 40,
    )
    binding = worker_execution_contract.WorkerRecoveryBinding.bind(
        adapter_id="codex-cli",
        spec=spec,
        process_ref=process,
        prompt_path=prompt_path,
    )
    prompt_path.write_text("changed prompt", encoding="utf-8")
    with pytest.raises(
        worker_execution_contract.WorkerRecoveryContractError,
        match="prompt digest",
    ):
        binding.recover_launch_spec()
    changed = binding.to_dict()
    changed["process_ref"]["run_id"] = "different-run"
    with pytest.raises(
        worker_execution_contract.WorkerRecoveryContractError,
        match="run identity",
    ):
        worker_execution_contract.WorkerRecoveryBinding.from_dict(changed)


def test_worker_adapter_protocol_requires_synchronous_reattach() -> None:
    class MissingReattach:
        adapter_id = "fixture"
        inspector = _SyntheticInspector()

        async def start(self, spec):
            raise NotImplementedError

        async def status(self, ref):
            raise NotImplementedError

        async def collect_result(self, ref):
            raise NotImplementedError

        async def cancel(self, ref, reason):
            raise NotImplementedError

        async def run_validation_argv(self, spec, argv, *, timeout_seconds=300.0):
            raise NotImplementedError

    class Complete(MissingReattach):
        def reattach(self, spec, binding):
            return binding.process_ref

    assert not isinstance(MissingReattach(), worker_adapter.WorkerExecutionAdapter)
    assert isinstance(Complete(), worker_adapter.WorkerExecutionAdapter)
''',
)

append_once(
    "tests/test_executive_codex_worker.py",
    "test_worker_launch_binds_stdout_and_stderr_to_durable_files",
    r'''
def test_worker_launch_binds_stdout_and_stderr_to_durable_files(
    tmp_path: Path,
) -> None:
    async def exercise() -> tuple[cw.CollectionReceipt, bool, bool]:
        adapter, spec, _workspace_path, _run_dir = _fixture(tmp_path)
        ref = await adapter.start(spec)
        state = adapter._runs[spec.run_id]
        direct_stdout = state.process.stdout is None
        direct_stderr = state.process.stderr is None
        return await adapter.collect_result(ref), direct_stdout, direct_stderr

    receipt, direct_stdout, direct_stderr = asyncio.run(exercise())
    assert direct_stdout is True
    assert direct_stderr is True
    assert receipt.result.status is cw.WorkerRunStatus.SUCCEEDED


def test_reattach_replays_terminal_result_without_provider_start(
    tmp_path: Path,
) -> None:
    adapter, spec, _workspace_path, run_dir = _fixture(tmp_path)
    prompt_path = run_dir / "input" / "worker-prompt.txt"
    prompt_path.write_text(spec.prompt, encoding="utf-8")
    prompt_path.chmod(0o600)
    logs = run_dir / "logs"
    output = run_dir / "output"
    logs.mkdir(mode=0o700)
    output.mkdir(mode=0o700)
    result = {
        "run_id": spec.run_id,
        "job_id": spec.job_id,
        "worker_id": spec.worker_id,
        "status": "COMPLETED",
        "summary": "recovered durable result",
        "artifacts": [],
    }
    events = (
        {"type": "thread.started", "thread_id": "thread-recovered"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {
                "type": "agent_message",
                "text": json.dumps(result, sort_keys=True),
            },
        },
        {
            "type": "turn.completed",
            "usage": {"input_tokens": 13, "output_tokens": 8},
        },
    )
    stdout = logs / "stdout.jsonl"
    stderr = logs / "stderr.log"
    result_path = output / "result.json"
    stdout.write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )
    stderr.write_bytes(b"")
    result_path.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
    for path in (stdout, stderr, result_path):
        path.chmod(0o600)
    ref = cw.ProcessRef(
        run_id=spec.run_id,
        pid=987654,
        pgid=987654,
        process_start_identity="absent-start",
        boot_session_id="boot-recovered",
        launch_nonce="nonce-recovered",
        provider_session_id=None,
        stdout_path=str(stdout),
        stderr_path=str(stderr),
        result_path=str(result_path),
        started_at="2026-09-18T00:00:00+00:00",
        binary=adapter.binary,
        base_sha=spec.expected_base_sha or "",
        session_id=987654,
        effective_uid=os.geteuid(),
        effective_gid=os.getegid(),
        real_uid=os.getuid(),
        real_gid=os.getgid(),
    )

    class AbsentInspector:
        def boot_session_id(self) -> str:
            return ref.boot_session_id

        def identity(self, _pid: int):
            raise cw.ProcessIdentityError("fixture process is absent")

        def inspect(self, _pid: int):
            raise cw.ProcessIdentityError("fixture process is absent")

    adapter.inspector = AbsentInspector()
    binding = wec.WorkerRecoveryBinding.bind(
        adapter_id=adapter.adapter_id,
        spec=spec,
        process_ref=ref,
        prompt_path=prompt_path,
    )
    recovered_ref = adapter.reattach(spec, binding)
    receipt = asyncio.run(adapter.collect_result(recovered_ref))
    assert recovered_ref == ref
    assert receipt.result.status is cw.WorkerRunStatus.SUCCEEDED
    assert receipt.result.provider_session_id == "thread-recovered"
    assert receipt.result.usage == {"input_tokens": 13, "output_tokens": 8}
    assert receipt.result.structured_output["summary"] == "recovered durable result"


def _live_recovery_fixture(
    tmp_path: Path,
    *,
    argv: tuple[str, ...] = ("/bin/sleep", "60"),
) -> tuple[cw.CodexWorkerAdapter, cw.LaunchSpec, wec.WorkerRecoveryBinding, subprocess.Popen]:
    adapter, spec, _workspace_path, run_dir = _fixture(tmp_path)
    prompt_path = run_dir / "input" / "worker-prompt.txt"
    prompt_path.write_text(spec.prompt, encoding="utf-8")
    prompt_path.chmod(0o600)
    logs = run_dir / "logs"
    output = run_dir / "output"
    logs.mkdir(mode=0o700)
    output.mkdir(mode=0o700)
    stdout = logs / "stdout.jsonl"
    stderr = logs / "stderr.log"
    result = output / "result.json"
    for path in (stdout, stderr, result):
        path.write_bytes(b"")
        path.chmod(0o600)
    process = subprocess.Popen(argv, start_new_session=True)
    observed = adapter.inspector.inspect(process.pid)
    ref = cw.ProcessRef(
        run_id=spec.run_id,
        pid=process.pid,
        pgid=observed.pgid,
        process_start_identity=observed.start_identity,
        boot_session_id=adapter.inspector.boot_session_id(),
        launch_nonce="nonce-live-recovery",
        provider_session_id=None,
        stdout_path=str(stdout),
        stderr_path=str(stderr),
        result_path=str(result),
        started_at=cw._utc_now(),
        binary=adapter.binary,
        base_sha=spec.expected_base_sha or "",
        session_id=observed.session_id,
        effective_uid=observed.effective_uid,
        effective_gid=observed.effective_gid,
        real_uid=observed.real_uid,
        real_gid=observed.real_gid,
    )
    binding = wec.WorkerRecoveryBinding.bind(
        adapter_id=adapter.adapter_id,
        spec=spec,
        process_ref=ref,
        prompt_path=prompt_path,
    )
    threading.Thread(target=process.wait, daemon=True).start()
    return adapter, spec, binding, process


def test_recovered_cancel_reports_graceful_exact_absence_without_sigkill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, spec, binding, process = _live_recovery_fixture(tmp_path)
    original_killpg = cw.os.killpg
    signals: list[int] = []

    def traced_killpg(pgid: int, value: int) -> None:
        if value != 0:
            signals.append(value)
        original_killpg(pgid, value)

    monkeypatch.setattr(cw.os, "killpg", traced_killpg)
    try:
        time.sleep(0.1)
        ref = adapter.reattach(spec, binding)
        receipt = asyncio.run(adapter.cancel(ref, "restart cancellation"))
        process.wait(timeout=2)
    finally:
        monkeypatch.setattr(cw.os, "killpg", original_killpg)
        if process.poll() is None:
            original_killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)
    assert receipt.signal_sent is True
    assert receipt.escalated_to_sigkill is False
    assert receipt.already_exited is False
    assert signals == [signal.SIGTERM]


def test_recovered_cancel_escalates_only_the_verified_residual_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ready = tmp_path / "residual.ready"
    child_program = (
        "import pathlib,signal,sys,time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "pathlib.Path(sys.argv[1]).write_text('ready'); time.sleep(60)"
    )
    program = (
        "import os,subprocess,sys,time; "
        "subprocess.Popen(['/usr/bin/python3','-c',sys.argv[2],sys.argv[1]]); "
        "[(time.sleep(0.01)) for _ in range(500) if not os.path.exists(sys.argv[1])]; "
        "time.sleep(60)"
    )
    adapter, spec, binding, process = _live_recovery_fixture(
        tmp_path,
        argv=("/usr/bin/python3", "-c", program, str(ready), child_program),
    )
    original_killpg = cw.os.killpg
    signals: list[int] = []

    def traced_killpg(pgid: int, value: int) -> None:
        if value != 0:
            signals.append(value)
        original_killpg(pgid, value)

    monkeypatch.setattr(cw.os, "killpg", traced_killpg)
    try:
        for _ in range(200):
            if ready.exists():
                break
            time.sleep(0.01)
        assert ready.exists()
        ref = adapter.reattach(spec, binding)
        receipt = asyncio.run(adapter.cancel(ref, "restart cancellation"))
        process.wait(timeout=2)
    finally:
        monkeypatch.setattr(cw.os, "killpg", original_killpg)
        try:
            original_killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        if process.poll() is None:
            process.wait(timeout=2)
    assert receipt.signal_sent is True
    assert receipt.escalated_to_sigkill is True
    assert receipt.already_exited is False
    assert signals == [signal.SIGTERM, signal.SIGKILL]


def test_duplicate_reattach_is_idempotent_for_the_same_execution(tmp_path: Path) -> None:
    adapter, spec, binding, process = _live_recovery_fixture(tmp_path)
    try:
        first = adapter.reattach(spec, binding)
        second = adapter.reattach(spec, binding)
        assert first == second == binding.process_ref
        receipt = asyncio.run(adapter.cancel(first, "fixture cleanup"))
        assert receipt.signal_sent is True
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=2)
''',
)

# The direct-file collector no longer has an asyncio pipe transport to force-retire.
replace_once(
    "tests/test_executive_codex_worker.py",
    '        assert "forced local retirement" in (receipt.result.error or "")\n',
    '        assert "expected one thread.started" in (receipt.result.error or "")\n',
)

# Preserve exact process/session ownership in the supervisor fixture.
replace_once(
    "tests/test_executive_supervisor.py",
    '''            started_at="2026-08-11T00:00:00+00:00",\n            binary=binary,\n            base_sha="b" * 40,\n        )\n''',
    '''            started_at="2026-08-11T00:00:00+00:00",\n            binary=binary,\n            base_sha="b" * 40,\n            session_id=self.inspector.pid,\n            effective_uid=os.geteuid(),\n            effective_gid=os.getegid(),\n            real_uid=os.geteuid(),\n            real_gid=os.getegid(),\n        )\n''',
)

append_once(
    "tests/test_executive_supervisor.py",
    "test_restart_adopts_and_reattaches_live_worker_without_terminating_or_restarting",
    r'''
class RestartCapableFakeAdapter(FakeAdapter):
    adapter_id = "codex-cli"

    def __init__(self, inspector: FakeInspector, **kwargs) -> None:
        super().__init__(inspector, **kwargs)
        self.start_calls = 0
        self.reattach_calls: list[tuple[object, object]] = []

    async def start(self, spec):
        self.start_calls += 1
        return await super().start(spec)

    def reattach(self, spec, binding):
        recovered = binding.recover_launch_spec()
        assert recovered == spec
        self.spec = spec
        self.ref = binding.process_ref
        self.reattach_calls.append((spec, binding))
        return self.ref

    async def collect_result(self, ref):
        self.inspector.live = False
        return await super().collect_result(ref)


def test_restart_adopts_and_reattaches_live_worker_without_terminating_or_restarting(
    tmp_path: Path,
) -> None:
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    inspector = FakeInspector()
    first_adapter = RestartCapableFakeAdapter(inspector)
    active = asyncio.run(_supervisor(runtime, tmp_path, first_adapter).start_job(job_id))
    original_fence = active.lease.attempt.fence_generation
    reopened = Runtime.at(tmp_path, lease_seconds=30)
    second_adapter = RestartCapableFakeAdapter(inspector)
    restarted = _supervisor(reopened, tmp_path, second_adapter)
    outcomes = restarted.reconcile_restart(requeue_lost=False)
    assert [outcome.status for outcome in outcomes] == [ReconcileStatus.LIVE_RECOVERED]
    assert restarted.process_controller.terminated_attempt_ids == []
    assert second_adapter.start_calls == 0
    assert len(second_adapter.reattach_calls) == 1
    pending = restarted.take_recovered_runs()
    assert len(pending) == 1
    assert restarted.take_recovered_runs() == ()
    adopted = reopened.attempts.get_attempt(active.lease.attempt.attempt_id)
    assert adopted is not None
    assert adopted.status is AttemptStatus.CHECKPOINTED
    assert adopted.fence_generation == original_fence + 1
    receipt = asyncio.run(restarted.finish_job(pending[0]))
    assert receipt.job.status is JobStatus.COMPLETED
    assert receipt.attempt.status is AttemptStatus.COMPLETED
    assert second_adapter.start_calls == 0


def test_restart_recovers_terminal_result_race_instead_of_marking_attempt_lost(
    tmp_path: Path,
) -> None:
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    inspector = FakeInspector()
    first_adapter = RestartCapableFakeAdapter(inspector)
    active = asyncio.run(_supervisor(runtime, tmp_path, first_adapter).start_job(job_id))
    inspector.live = False
    reopened = Runtime.at(tmp_path, lease_seconds=30)
    second_adapter = RestartCapableFakeAdapter(inspector)
    restarted = _supervisor(reopened, tmp_path, second_adapter)
    outcomes = restarted.reconcile_restart(requeue_lost=False)
    assert [outcome.status for outcome in outcomes] == [
        ReconcileStatus.TERMINAL_RECOVERED
    ]
    assert restarted.process_controller.terminated_attempt_ids == []
    pending = restarted.take_recovered_runs()
    assert len(pending) == 1
    receipt = asyncio.run(restarted.finish_job(pending[0]))
    assert receipt.job.status is JobStatus.COMPLETED
    assert receipt.attempt.status is AttemptStatus.COMPLETED
    assert second_adapter.start_calls == 0


def test_restart_live_worker_with_expired_lease_is_quarantined_without_signal(
    tmp_path: Path,
) -> None:
    now = [1_800_000_000_000]
    clock = lambda: now[0]
    runtime, job_id, _workspace = _runtime_and_job(
        tmp_path, clock=clock, lease_seconds=1
    )
    inspector = FakeInspector()
    active = asyncio.run(
        _supervisor(runtime, tmp_path, RestartCapableFakeAdapter(inspector)).start_job(
            job_id
        )
    )
    now[0] += 2_000
    reopened = Runtime.at(tmp_path, clock=clock, lease_seconds=1)
    restarted = _supervisor(
        reopened, tmp_path, RestartCapableFakeAdapter(inspector)
    )
    outcomes = restarted.reconcile_restart(requeue_lost=False)
    assert [outcome.status for outcome in outcomes] == [
        ReconcileStatus.LEASE_EXPIRED_QUARANTINED
    ]
    assert restarted.process_controller.terminated_attempt_ids == []
    assert restarted.take_recovered_runs() == ()
    persisted = reopened.attempts.get_attempt(active.lease.attempt.attempt_id)
    assert persisted is not None and persisted.status is AttemptStatus.CHECKPOINTED


def test_restart_cancel_pending_preserves_same_attempt_and_terminalizes_cancelled(
    tmp_path: Path,
) -> None:
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    inspector = FakeInspector()
    active = asyncio.run(
        _supervisor(runtime, tmp_path, RestartCapableFakeAdapter(inspector)).start_job(
            job_id
        )
    )
    runtime.jobs.cancel_job(job_id)
    reopened = Runtime.at(tmp_path, lease_seconds=30)
    restarted = _supervisor(
        reopened, tmp_path, RestartCapableFakeAdapter(inspector)
    )
    outcomes = restarted.reconcile_restart(requeue_lost=False)
    assert outcomes[0].status is ReconcileStatus.LIVE_RECOVERED
    pending = restarted.take_recovered_runs()
    receipt = asyncio.run(restarted.finish_job(pending[0]))
    assert receipt.attempt.attempt_id == active.lease.attempt.attempt_id
    assert receipt.attempt.status is AttemptStatus.CANCELLED
    assert receipt.job.status is JobStatus.CANCELLED


def test_duplicate_restart_reconcile_does_not_reattach_twice(tmp_path: Path) -> None:
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    inspector = FakeInspector()
    asyncio.run(
        _supervisor(runtime, tmp_path, RestartCapableFakeAdapter(inspector)).start_job(
            job_id
        )
    )
    reopened = Runtime.at(tmp_path, lease_seconds=30)
    adapter = RestartCapableFakeAdapter(inspector)
    restarted = _supervisor(reopened, tmp_path, adapter)
    assert restarted.reconcile_restart(requeue_lost=False)[0].status is (
        ReconcileStatus.LIVE_RECOVERED
    )
    assert restarted.reconcile_restart(requeue_lost=False)[0].status is (
        ReconcileStatus.ALREADY_RECOVERED
    )
    assert len(adapter.reattach_calls) == 1


def test_identity_controller_treats_boot_or_pid_reuse_as_unknown(tmp_path: Path) -> None:
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    inspector = FakeInspector()
    active = asyncio.run(
        _supervisor(runtime, tmp_path, RestartCapableFakeAdapter(inspector)).start_job(
            job_id
        )
    )
    attempt = runtime.attempts.get_attempt(active.lease.attempt.attempt_id)
    assert attempt is not None
    controller = IdentitySafeProcessController(inspector)
    inspector.boot_id = "changed-boot"
    assert controller.presence(attempt) is ProcessPresence.UNKNOWN
    inspector.boot_id = attempt.boot_id or ""
    inspector.start_identity = "reused-pid-start"
    assert controller.presence(attempt) is ProcessPresence.UNKNOWN
''',
)

append_once(
    "tests/test_executive_worker_broker.py",
    "test_remote_adapter_reattaches_exact_broker_run_without_starting_again",
    r'''
def test_remote_adapter_reattaches_exact_broker_run_without_starting_again(
    tmp_path: Path,
) -> None:
    broker, adapter, _sweeper, _peer, spec_value = _fixture(tmp_path)
    from control_plane.executive_worker_broker import (
        _jsonable,
        _launch_spec_from_wire,
    )
    from control_plane.worker_execution_contract import WorkerRecoveryBinding

    spec = _launch_spec_from_wire(spec_value, broker.policy)
    ref = asyncio.run(adapter.start(spec))
    prompt_path = Path(spec.run_dir) / "input" / "worker-prompt.txt"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(spec.prompt, encoding="utf-8")
    prompt_path.chmod(0o600)
    binding = WorkerRecoveryBinding.bind(
        adapter_id="codex-cli",
        spec=spec,
        process_ref=ref,
        prompt_path=prompt_path,
    )

    class Client:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        def request_sync(self, operation, payload):
            self.calls.append((operation, payload))
            assert operation == "status"
            assert payload == {"run_id": ref.run_id}
            return {
                "run": {
                    "status": "RUNNING",
                    "process_ref": _jsonable(ref),
                }
            }

    client = Client()
    remote = RemoteCodexWorkerAdapter(client)  # type: ignore[arg-type]
    recovered = remote.reattach(spec, binding)
    repeated = remote.reattach(spec, binding)
    assert recovered == repeated == ref
    assert remote._refs[ref.run_id] == ref
    assert remote._specs[ref.run_id] == spec
    assert client.calls == [("status", {"run_id": ref.run_id})]
''',
)

append_once(
    "tests/test_executive_service.py",
    "test_service_schedules_recovered_runs_through_existing_dispatch_registry",
    r'''
def test_service_schedules_recovered_runs_through_existing_dispatch_registry() -> None:
    async def scenario() -> None:
        attempt = type(
            "AttemptFixture",
            (),
            {"attempt_id": "ATT-recovered", "job_id": "JOB-recovered"},
        )()
        active = type(
            "ActiveFixture",
            (),
            {"lease": type("LeaseFixture", (), {"attempt": attempt})()},
        )()

        class Supervisor:
            def __init__(self) -> None:
                self.values = [active]
                self.finished: list[object] = []

            def take_recovered_runs(self):
                values = tuple(self.values)
                self.values.clear()
                return values

            async def finish_job(self, value):
                self.finished.append(value)

        supervisor = Supervisor()
        service = object.__new__(es_mod.ExecutiveControlService)
        service.supervisor = supervisor
        service._dispatch_tasks = {}
        service._dispatch_errors = {}
        service._service_state = "READY"

        async def no_projection(_job_id, *, expected_attempt_id):
            assert expected_attempt_id == "ATT-recovered"

        service._project_terminal_return = no_projection
        await service._schedule_recovered_runs()
        tasks = tuple(service._dispatch_tasks.values())
        assert len(tasks) == 1
        await asyncio.gather(*tasks)
        assert supervisor.finished == [active]
        assert service._dispatch_tasks == {}

    asyncio.run(scenario())
''',
)
