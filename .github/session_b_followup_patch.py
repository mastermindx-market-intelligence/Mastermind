from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"{path}: expected one replacement for {old[:120]!r}, found {count}"
        )
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_once(path: str, marker: str, payload: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if marker in text:
        return
    target.write_text(text.rstrip() + "\n\n" + payload.strip() + "\n", encoding="utf-8")


# ----- Production source: replay-safe receipts and truthful terminalization -----
replace_once(
    "control_plane/executive_supervisor.py",
    "def _write_private_recovery_prompt(path: Path, prompt: str) -> None:\n",
    r'''def _write_or_verify_private_json(
    path: Path,
    value: Any,
    *,
    name: str,
) -> None:
    """Create one receipt or accept only its exact private durable replay."""

    material = _jsonable(value)
    try:
        _write_private_json(path, material)
        return
    except FileExistsError:
        pass
    try:
        info = path.lstat()
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise SupervisorError(f"existing {name} cannot be verified") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) & 0o077
        or existing != material
    ):
        raise SupervisorError(f"existing {name} identity or payload drifted")


def _write_private_recovery_prompt(path: Path, prompt: str) -> None:
''',
)
replace_once(
    "control_plane/executive_supervisor.py",
    "        _write_private_json(path, payload)\n        return path\n\n"
    "    @staticmethod\n    def _read_private_receipt",
    "        _write_or_verify_private_json(\n"
    "            path, payload, name=\"collection receipt\"\n"
    "        )\n"
    "        return path\n\n"
    "    @staticmethod\n    def _read_private_receipt",
)
replace_once(
    "control_plane/executive_supervisor.py",
    "        _write_private_json(path, payload)\n        return path\n\n"
    "    async def _run_supervisor_validations",
    "        _write_or_verify_private_json(\n"
    "            path, payload, name=\"supervisor validation receipt\"\n"
    "        )\n"
    "        return path\n\n"
    "    async def _run_supervisor_validations",
)
replace_once(
    "control_plane/executive_supervisor.py",
    r'''        if receipt.result.exit_code is None:
            raise SupervisorError("Codex process has no terminal exit code")
        self.runtime.attempts.record_process_exit(
            attempt.attempt_id,
            fence_generation=fence,
            lease_token=token,
            exit_code=receipt.result.exit_code,
            result_path=receipt.process_ref.result_path,
            provider_session_id=receipt.result.provider_session_id,
        )
''',
    r'''        if receipt.result.exit_code is None:
            raise SupervisorError(
                "recovered local worker has no truthful durable OS exit code; "
                "the original Attempt remains quarantined"
            )
        current_attempt = self.runtime.attempts.get_attempt(attempt.attempt_id)
        if current_attempt is None:
            raise SupervisorError("terminal Attempt disappeared before exit evidence")
        if current_attempt.exit_code is None:
            self.runtime.attempts.record_process_exit(
                attempt.attempt_id,
                fence_generation=fence,
                lease_token=token,
                exit_code=receipt.result.exit_code,
                result_path=receipt.process_ref.result_path,
                provider_session_id=receipt.result.provider_session_id,
            )
        elif (
            int(current_attempt.exit_code) != int(receipt.result.exit_code)
            or current_attempt.result_path != receipt.process_ref.result_path
            or current_attempt.provider_session_id
            != receipt.result.provider_session_id
        ):
            raise SupervisorError(
                "persisted process-exit evidence differs from recovered collection"
            )
''',
)
replace_once(
    "control_plane/executive_supervisor.py",
    r'''    def reconcile_restart(self, *, requeue_lost: bool = True) -> list[ReconcileReceipt]:
        """Inspect durable nonterminal attempts after a supervisor restart.

        A live local child cannot be reconstructed because the in-memory JSONL
        parser was lost.  It is identity-safely terminated and verified absent
        before any fence rotation, cancellation acknowledgement, LOST state, or
        requeue.  Ambiguous and provider-only identities remain quarantined.
        """
''',
    r'''    def reconcile_restart(self, *, requeue_lost: bool = True) -> list[ReconcileReceipt]:
        """Recover exact sealed workers or quarantine uncertainty after restart.

        A durable recovery binding adopts the original Job/Attempt and existing
        provider execution without another start. Healthy legacy executions
        lacking that binding remain active and quarantined; cancellation is the
        only path that may identity-safely terminate one during reconciliation.
        """
''',
)
replace_once(
    "control_plane/executive_supervisor.py",
    r'''                    )
                    continue
            if process_was_live:
                self.process_controller.terminate(attempt)
''',
    r'''                    )
                    continue
            if (
                process_was_live
                and not isinstance(recovery_raw, Mapping)
                and attempt.status is not AttemptStatus.CANCEL_REQUESTED
            ):
                expired = self._attempt_lease_expired(attempt)
                outcomes.append(
                    ReconcileReceipt(
                        attempt_id=attempt.attempt_id,
                        job_id=attempt.job_id,
                        status=(
                            ReconcileStatus.LEASE_EXPIRED_QUARANTINED
                            if expired
                            else ReconcileStatus.LIVE_QUARANTINED
                        ),
                        process_was_live=True,
                        error=(
                            "healthy legacy worker has no durable recovery binding; "
                            "refusing to signal or replace the original execution"
                        ),
                    )
                )
                continue
            if process_was_live:
                self.process_controller.terminate(attempt)
''',
)

# ----- Existing restart tests now encode quarantine, not supervisor-caused loss -----
replace_once(
    "tests/test_executive_supervisor.py",
    "import asyncio\n",
    "import asyncio\nimport dataclasses\n",
)
replace_once(
    "tests/test_executive_supervisor.py",
    "from control_plane.ceo_intent import INTENT_SCHEMA_V2, submit_intent\n",
    "from control_plane.ceo_intent import INTENT_SCHEMA_V2, submit_intent\n"
    "import control_plane.executive_supervisor as supervisor_module\n",
)
replace_once(
    "tests/test_executive_supervisor.py",
    r'''def test_restart_live_process_is_terminated_verified_absent_then_lost_and_requeued(
    tmp_path: Path,
):
''',
    r'''def test_restart_live_legacy_process_is_quarantined_without_signal(
    tmp_path: Path,
):
''',
)
replace_once(
    "tests/test_executive_supervisor.py",
    r'''    assert [item.status for item in outcomes] == [ReconcileStatus.MISSING_LOST]
    assert outcomes[0].process_was_live is True
    reconciliation_evidence = Path(outcomes[0].uid_sweep_receipt_path or "")
    assert reconciliation_evidence.is_file()
    assert stat.S_IMODE(reconciliation_evidence.stat().st_mode) == 0o600
    reconciliation_payload = json.loads(
        reconciliation_evidence.read_text(encoding="utf-8")
    )
    assert reconciliation_payload["uid_sweep"]["passed"] is True
    assert "lease_token" not in reconciliation_evidence.read_text(encoding="utf-8")
    assert restarted.process_controller.terminated_attempt_ids == [
        active.lease.attempt.attempt_id
    ]
    attempt = reopened.attempts.get_attempt(active.lease.attempt.attempt_id)
    job = reopened.jobs.get_job(job_id)
    assert attempt is not None and attempt.status is AttemptStatus.LOST
    assert job is not None and job.status is JobStatus.LOST
''',
    r'''    assert [item.status for item in outcomes] == [
        ReconcileStatus.LIVE_QUARANTINED
    ]
    assert outcomes[0].process_was_live is True
    assert outcomes[0].uid_sweep_receipt_path is None
    assert restarted.process_controller.terminated_attempt_ids == []
    attempt = reopened.attempts.get_attempt(active.lease.attempt.attempt_id)
    job = reopened.jobs.get_job(job_id)
    assert attempt is not None and attempt.status is AttemptStatus.CHECKPOINTED
    assert job is not None and job.status is JobStatus.CHECKPOINTED
''',
)
replace_once(
    "tests/test_executive_supervisor.py",
    "def test_restart_expired_live_process_is_terminated_before_expiry_requeue(tmp_path: Path):\n",
    "def test_restart_expired_live_legacy_process_is_quarantined_without_signal(\n"
    "    tmp_path: Path,\n"
    "):\n",
)
replace_once(
    "tests/test_executive_supervisor.py",
    r'''    assert [item.status for item in outcomes] == [ReconcileStatus.EXPIRED_LOST]
    assert outcomes[0].process_was_live is True
    assert restarted.process_controller.terminated_attempt_ids == [
        active.lease.attempt.attempt_id
    ]
    attempt = reopened.attempts.get_attempt(active.lease.attempt.attempt_id)
    assert attempt is not None and attempt.status is AttemptStatus.LOST
''',
    r'''    assert [item.status for item in outcomes] == [
        ReconcileStatus.LEASE_EXPIRED_QUARANTINED
    ]
    assert outcomes[0].process_was_live is True
    assert restarted.process_controller.terminated_attempt_ids == []
    attempt = reopened.attempts.get_attempt(active.lease.attempt.attempt_id)
    job = reopened.jobs.get_job(job_id)
    assert attempt is not None and attempt.status is AttemptStatus.CHECKPOINTED
    assert job is not None and job.status is JobStatus.CHECKPOINTED
''',
)

append_once(
    "tests/test_executive_supervisor.py",
    "test_restart_recovers_immediately_after_process_identity_persistence",
    r'''
async def _persist_recoverable_launch_boundary(
    supervisor: ExecutiveSupervisor,
    adapter: RestartCapableFakeAdapter,
    job_id: str,
    *,
    mark_running: bool,
) -> AttemptLease:
    lease = supervisor.runtime.broker.claim(
        job_id,
        lease_owner=supervisor.instance_id,
    )
    assert lease is not None
    job = supervisor._job(job_id)
    effective_grant = supervisor._effective_grant(job, lease.attempt)
    schema_path = supervisor._write_schema(
        supervisor._run_dir(lease.attempt.attempt_id),
        job=job,
        attempt=lease.attempt,
        effective_grant=effective_grant,
    )
    spec = supervisor._launch_spec(
        job,
        lease,
        schema_path,
        effective_grant,
    )
    prompt_path = schema_path.parent / "worker-prompt.txt"
    supervisor_module._write_private_recovery_prompt(prompt_path, spec.prompt)
    process_ref = await adapter.start(spec)
    metadata = supervisor._launch_metadata(
        job=job,
        lease=lease,
        spec=spec,
        process_ref=process_ref,
        effective_grant=effective_grant,
        recovery_prompt_path=prompt_path,
    )
    supervisor.runtime.attempts.record_process(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        pid=process_ref.pid,
        pgid=process_ref.pgid,
        process_start_identity=process_ref.process_start_identity,
        boot_id=process_ref.boot_session_id,
        provider_session_id=process_ref.provider_session_id,
        stdout_path=process_ref.stdout_path,
        stderr_path=process_ref.stderr_path,
        result_path=process_ref.result_path,
        launch_metadata=metadata,
    )
    if mark_running:
        supervisor.runtime.attempts.mark_running(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )
    return lease


def test_restart_recovers_immediately_after_process_identity_persistence(
    tmp_path: Path,
) -> None:
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    inspector = FakeInspector()
    first_adapter = RestartCapableFakeAdapter(inspector)
    first = _supervisor(runtime, tmp_path, first_adapter)
    lease = asyncio.run(
        _persist_recoverable_launch_boundary(
            first,
            first_adapter,
            job_id,
            mark_running=False,
        )
    )
    persisted = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    assert persisted is not None and persisted.status is AttemptStatus.CLAIMED

    reopened = Runtime.at(tmp_path, lease_seconds=30)
    second_adapter = RestartCapableFakeAdapter(inspector)
    restarted = _supervisor(reopened, tmp_path, second_adapter)
    outcomes = restarted.reconcile_restart(requeue_lost=False)

    assert outcomes[0].status is ReconcileStatus.LIVE_RECOVERED
    recovered = reopened.attempts.get_attempt(lease.attempt.attempt_id)
    assert recovered is not None and recovered.status is AttemptStatus.CHECKPOINTED
    assert len(second_adapter.reattach_calls) == 1
    assert second_adapter.start_calls == 0
    receipt = asyncio.run(restarted.finish_job(restarted.take_recovered_runs()[0]))
    assert receipt.attempt.status is AttemptStatus.COMPLETED


def test_restart_recovers_after_running_before_checkpoint_or_heartbeat(
    tmp_path: Path,
) -> None:
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    inspector = FakeInspector()
    first_adapter = RestartCapableFakeAdapter(inspector)
    first = _supervisor(runtime, tmp_path, first_adapter)
    lease = asyncio.run(
        _persist_recoverable_launch_boundary(
            first,
            first_adapter,
            job_id,
            mark_running=True,
        )
    )
    persisted = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    assert persisted is not None and persisted.status is AttemptStatus.RUNNING

    reopened = Runtime.at(tmp_path, lease_seconds=30)
    second_adapter = RestartCapableFakeAdapter(inspector)
    restarted = _supervisor(reopened, tmp_path, second_adapter)
    outcomes = restarted.reconcile_restart(requeue_lost=False)

    assert outcomes[0].status is ReconcileStatus.LIVE_RECOVERED
    recovered = reopened.attempts.get_attempt(lease.attempt.attempt_id)
    assert recovered is not None and recovered.status is AttemptStatus.CHECKPOINTED
    assert len(second_adapter.reattach_calls) == 1
    receipt = asyncio.run(restarted.finish_job(restarted.take_recovered_runs()[0]))
    assert receipt.attempt.status is AttemptStatus.COMPLETED


def test_restart_stale_fence_quarantines_without_signal_or_second_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    inspector = FakeInspector()
    asyncio.run(
        _supervisor(
            runtime,
            tmp_path,
            RestartCapableFakeAdapter(inspector),
        ).start_job(job_id)
    )
    reopened = Runtime.at(tmp_path, lease_seconds=30)
    adapter = RestartCapableFakeAdapter(inspector)
    restarted = _supervisor(reopened, tmp_path, adapter)

    def stale(*_args, **_kwargs):
        raise StateConflict("fixture stale adoption fence")

    monkeypatch.setattr(reopened.attempts, "adopt_attempt", stale)
    outcomes = restarted.reconcile_restart(requeue_lost=False)

    assert outcomes[0].status is ReconcileStatus.STALE_FENCE_QUARANTINED
    assert restarted.process_controller.terminated_attempt_ids == []
    assert adapter.start_calls == 0
    assert adapter.reattach_calls == []


def test_identity_controller_treats_reused_pgid_as_unknown(tmp_path: Path) -> None:
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    inspector = FakeInspector()
    active = asyncio.run(
        _supervisor(runtime, tmp_path, FakeAdapter(inspector)).start_job(job_id)
    )
    attempt = runtime.attempts.get_attempt(active.lease.attempt.attempt_id)
    assert attempt is not None

    class ReusedGroupInspector(FakeInspector):
        def identity(self, pid: int) -> tuple[str, int]:
            assert pid == self.pid
            return self.start_identity, self.pid + 9

    reused = ReusedGroupInspector()
    reused.pid = inspector.pid
    reused.start_identity = inspector.start_identity
    reused.boot_id = inspector.boot_id
    assert IdentitySafeProcessController(reused).presence(attempt) is (
        ProcessPresence.UNKNOWN
    )


def test_collection_and_validation_receipts_are_exactly_replayable(
    tmp_path: Path,
) -> None:
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    adapter = RestartCapableFakeAdapter(FakeInspector())
    supervisor = _supervisor(runtime, tmp_path, adapter)
    active = asyncio.run(supervisor.start_job(job_id))
    collection = asyncio.run(adapter.collect_result(active.process_ref))

    first_collection = supervisor._persist_collection(active, collection)
    second_collection = supervisor._persist_collection(active, collection)
    assert first_collection == second_collection

    validation = ValidationReceipt(
        argv=("/usr/bin/true",),
        exit_code=0,
        stdout_sha256="0" * 64,
        stdout_size=0,
        stderr_sha256="0" * 64,
        stderr_size=0,
        timed_out=False,
        error=None,
    )
    first_validation = supervisor._persist_validations(active, (validation,))
    second_validation = supervisor._persist_validations(active, (validation,))
    assert first_validation == second_validation

    first_collection.write_text("{}\n", encoding="utf-8")
    with pytest.raises(SupervisorError, match="collection receipt.*drifted"):
        supervisor._persist_collection(active, collection)


def test_terminalization_reuses_identical_recorded_process_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    adapter = RestartCapableFakeAdapter(FakeInspector())
    supervisor = _supervisor(runtime, tmp_path, adapter)
    active = asyncio.run(supervisor.start_job(job_id))
    runtime.attempts.record_process_exit(
        active.lease.attempt.attempt_id,
        fence_generation=active.lease.attempt.fence_generation,
        lease_token=active.lease.lease_token,
        exit_code=0,
        result_path=active.process_ref.result_path,
        provider_session_id="thread-fixture",
    )

    def duplicate_forbidden(*_args, **_kwargs):
        raise AssertionError("identical process exit must not be recorded twice")

    monkeypatch.setattr(
        runtime.attempts,
        "record_process_exit",
        duplicate_forbidden,
    )
    receipt = asyncio.run(supervisor.finish_job(active))
    assert receipt.attempt.status is AttemptStatus.COMPLETED


def test_terminalization_refuses_drifted_recorded_process_exit(
    tmp_path: Path,
) -> None:
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    adapter = RestartCapableFakeAdapter(FakeInspector())
    supervisor = _supervisor(runtime, tmp_path, adapter)
    active = asyncio.run(supervisor.start_job(job_id))
    runtime.attempts.record_process_exit(
        active.lease.attempt.attempt_id,
        fence_generation=active.lease.attempt.fence_generation,
        lease_token=active.lease.lease_token,
        exit_code=7,
        result_path=active.process_ref.result_path,
        provider_session_id="thread-fixture",
    )
    with pytest.raises(SupervisorError, match="exit evidence differs"):
        asyncio.run(supervisor.finish_job(active))
    persisted = runtime.attempts.get_attempt(active.lease.attempt.attempt_id)
    assert persisted is not None and persisted.status is AttemptStatus.CHECKPOINTED
    assert persisted.exit_code == 7


class UnknownExitRestartAdapter(RestartCapableFakeAdapter):
    async def collect_result(self, ref):
        receipt = await super().collect_result(ref)
        return dataclasses.replace(
            receipt,
            result=dataclasses.replace(receipt.result, exit_code=None),
        )


def test_local_orphan_without_truthful_exit_code_remains_quarantined(
    tmp_path: Path,
) -> None:
    runtime, job_id, _workspace = _runtime_and_job(tmp_path)
    inspector = FakeInspector()
    asyncio.run(
        _supervisor(
            runtime,
            tmp_path,
            RestartCapableFakeAdapter(inspector),
        ).start_job(job_id)
    )
    reopened = Runtime.at(tmp_path, lease_seconds=30)
    restarted = _supervisor(
        reopened,
        tmp_path,
        UnknownExitRestartAdapter(inspector),
    )
    outcomes = restarted.reconcile_restart(requeue_lost=False)
    assert outcomes[0].status is ReconcileStatus.LIVE_RECOVERED
    active = restarted.take_recovered_runs()[0]

    with pytest.raises(
        SupervisorError,
        match="no truthful durable OS exit code",
    ):
        asyncio.run(restarted.finish_job(active))

    persisted = reopened.attempts.get_attempt(active.lease.attempt.attempt_id)
    job = reopened.jobs.get_job(job_id)
    assert persisted is not None and persisted.status is AttemptStatus.CHECKPOINTED
    assert persisted.exit_code is None
    assert job is not None and job.status is JobStatus.CHECKPOINTED
''',
)
