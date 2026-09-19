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


replace_once(
    "control_plane/executive_supervisor.py",
    "from enum import Enum\n",
    "from datetime import datetime\nfrom enum import Enum\n",
)
replace_once(
    "control_plane/executive_supervisor.py",
    "    WorkerLaunchSpec,\n    WorkerProcessRef,\n    WorkerRunStatus,\n",
    "    WorkerLaunchSpec,\n"
    "    WorkerProcessRef,\n"
    "    WorkerRecoveryBinding,\n"
    "    WorkerRecoveryContractError,\n"
    "    WorkerRunStatus,\n",
)
replace_once(
    "control_plane/executive_supervisor.py",
    '    OPERATOR_RECOVERED = "OPERATOR_RECOVERED"\n',
    '    OPERATOR_RECOVERED = "OPERATOR_RECOVERED"\n'
    '    LIVE_RECOVERED = "LIVE_RECOVERED"\n'
    '    TERMINAL_RECOVERED = "TERMINAL_RECOVERED"\n'
    '    ALREADY_RECOVERED = "ALREADY_RECOVERED"\n'
    '    LEASE_EXPIRED_QUARANTINED = "LEASE_EXPIRED_QUARANTINED"\n'
    '    STALE_FENCE_QUARANTINED = "STALE_FENCE_QUARANTINED"\n',
)
replace_once(
    "control_plane/executive_supervisor.py",
    "            if self.inspector.boot_session_id() != attempt.boot_id:\n"
    "                return ProcessPresence.ABSENT\n",
    "            if self.inspector.boot_session_id() != attempt.boot_id:\n"
    "                return ProcessPresence.UNKNOWN\n",
)
replace_once(
    "control_plane/executive_supervisor.py",
    "        if identity != attempt.process_start_identity or pgid != attempt.pgid:\n"
    "            return ProcessPresence.ABSENT\n",
    "        if identity != attempt.process_start_identity or pgid != attempt.pgid:\n"
    "            return ProcessPresence.UNKNOWN\n",
)
replace_once(
    "control_plane/executive_supervisor.py",
    "    assignment_seal_receipt_path: str | None = None\n\n"
    "    def to_dict(self) -> dict[str, Any]:\n",
    "    assignment_seal_receipt_path: str | None = None\n"
    "    error: str | None = None\n\n"
    "    def to_dict(self) -> dict[str, Any]:\n",
)
replace_once(
    "control_plane/executive_supervisor.py",
    "def _payload_from_output(output: Mapping[str, Any]) -> JobPayload:\n",
    r'''def _write_private_recovery_prompt(path: Path, prompt: str) -> None:
    payload = prompt.encode("utf-8")
    if not payload or len(payload) > 1024 * 1024:
        raise SupervisorError(
            "worker recovery prompt is empty or exceeds one MiB"
        )
    try:
        parent = path.parent.lstat()
    except OSError as exc:
        raise SupervisorError(
            "worker recovery prompt directory is unavailable"
        ) from exc
    if (
        stat.S_ISLNK(parent.st_mode)
        or not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.geteuid()
    ):
        raise SupervisorError(
            "worker recovery prompt directory is not control-owned"
        )
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError(
                    "short write while persisting worker recovery prompt"
                )
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory = os.open(
        path.parent,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _payload_from_output(output: Mapping[str, Any]) -> JobPayload:
''',
)
replace_once(
    "control_plane/executive_supervisor.py",
    '        self.instance_id = instance_id or f"supervisor-{uuid4().hex}"\n',
    '        self.instance_id = instance_id or f"supervisor-{uuid4().hex}"\n'
    '        self._recovered_runs: dict[str, ActiveRun] = {}\n'
    '        self._recovered_attempt_ids: set[str] = set()\n',
)
replace_once(
    "control_plane/executive_supervisor.py",
    "        process_ref: WorkerProcessRef,\n"
    "        effective_grant: Mapping[str, Any] | None = None,\n"
    "    ) -> dict[str, Any]:\n",
    "        process_ref: WorkerProcessRef,\n"
    "        effective_grant: Mapping[str, Any] | None = None,\n"
    "        recovery_prompt_path: Path | None = None,\n"
    "    ) -> dict[str, Any]:\n",
)
replace_once(
    "control_plane/executive_supervisor.py",
    r'''        if effective_grant is not None:
            result["effective_grant_digest"] = lease.attempt.effective_grant_digest
            result["write_paths"] = list(effective_grant["write_paths"])
            result["validation_argv"] = list(effective_grant["validation_argv"])
        return result
''',
    r'''        if effective_grant is not None:
            result["effective_grant_digest"] = lease.attempt.effective_grant_digest
            result["write_paths"] = list(effective_grant["write_paths"])
            result["validation_argv"] = list(effective_grant["validation_argv"])
        reattach = getattr(self.adapter, "reattach", None)
        if callable(reattach):
            if recovery_prompt_path is None:
                raise SupervisorError(
                    "recoverable worker launch has no durable prompt"
                )
            try:
                binding = WorkerRecoveryBinding.bind(
                    adapter_id=str(getattr(self.adapter, "adapter_id", "")),
                    spec=spec,
                    process_ref=process_ref,
                    prompt_path=recovery_prompt_path,
                )
            except WorkerRecoveryContractError as exc:
                raise SupervisorError(
                    f"worker recovery binding failed: {exc}"
                ) from exc
            result["worker_recovery_binding"] = binding.to_dict()
        return result
''',
)
replace_once(
    "control_plane/executive_supervisor.py",
    r'''            spec = self._launch_spec(job, lease, schema_path, effective_grant)
            start_invoked = True
            process_ref = await self.adapter.start(spec)
''',
    r'''            spec = self._launch_spec(job, lease, schema_path, effective_grant)
            recovery_prompt_path = schema_path.parent / "worker-prompt.txt"
            _write_private_recovery_prompt(recovery_prompt_path, spec.prompt)
            start_invoked = True
            process_ref = await self.adapter.start(spec)
''',
)
replace_once(
    "control_plane/executive_supervisor.py",
    "                process_ref=process_ref,\n"
    "                effective_grant=effective_grant,\n"
    "            )\n",
    "                process_ref=process_ref,\n"
    "                effective_grant=effective_grant,\n"
    "                recovery_prompt_path=recovery_prompt_path,\n"
    "            )\n",
)
replace_once(
    "control_plane/executive_supervisor.py",
    "    def _maybe_requeue(self, job_id: str) -> bool:\n",
    r'''    def take_recovered_runs(self) -> tuple[ActiveRun, ...]:
        """Return each process-local recovered finisher exactly once."""

        values = tuple(self._recovered_runs.values())
        self._recovered_runs.clear()
        return values

    def _attempt_lease_expired(self, attempt: Attempt) -> bool:
        try:
            expiry = datetime.fromisoformat(
                attempt.lease_expires_at.replace("Z", "+00:00")
            )
            if expiry.tzinfo is None:
                raise ValueError("missing timezone")
        except ValueError as exc:
            raise SupervisorError(
                "attempt lease expiry is malformed"
            ) from exc
        return int(expiry.timestamp() * 1000) <= int(
            self.runtime.store.now_ms()
        )

    @staticmethod
    def _process_ref_matches_attempt(
        ref: WorkerProcessRef, attempt: Attempt
    ) -> bool:
        return (
            ref.run_id == attempt.attempt_id
            and ref.pid == attempt.pid
            and ref.pgid == attempt.pgid
            and ref.process_start_identity == attempt.process_start_identity
            and ref.boot_session_id == attempt.boot_id
            and ref.provider_session_id == attempt.provider_session_id
            and ref.stdout_path == attempt.stdout_path
            and ref.stderr_path == attempt.stderr_path
            and ref.result_path == attempt.result_path
        )

    def _validated_recovery_binding(
        self, attempt: Attempt
    ) -> tuple[
        WorkerRecoveryBinding,
        WorkerLaunchSpec,
        Mapping[str, Any] | None,
    ]:
        raw = attempt.launch_metadata.get("worker_recovery_binding")
        if not isinstance(raw, Mapping):
            raise SupervisorError(
                "attempt has no durable worker recovery binding"
            )
        try:
            binding = WorkerRecoveryBinding.from_dict(raw)
            fields = binding.launch_spec.get("fields")
            spec_type = (
                OrchestrationLaunchSpec
                if isinstance(fields, Mapping)
                and "effective_grant_digest" in fields
                else WorkerLaunchSpec
            )
            spec = binding.recover_launch_spec(spec_type)
        except WorkerRecoveryContractError as exc:
            raise SupervisorError(
                f"worker recovery binding is invalid: {exc}"
            ) from exc
        if not self._process_ref_matches_attempt(
            binding.process_ref, attempt
        ):
            raise SupervisorError(
                "worker recovery binding differs from durable Attempt identity"
            )
        job = self._job(attempt.job_id)
        effective_grant = self._effective_grant(job, attempt)
        expected_authorities = tuple(
            effective_grant["authorities"]
            if effective_grant is not None
            else job.requested_authorities
        )
        expected_paths = tuple(
            effective_grant["write_paths"]
            if effective_grant is not None
            else job.allowed_write_paths
        )
        if (
            spec.run_id != attempt.attempt_id
            or spec.job_id != attempt.job_id
            or spec.worker_id != attempt.worker_id
            or not job.worktree
            or Path(spec.workspace_path).resolve(strict=False)
            != Path(job.worktree).resolve(strict=False)
            or Path(spec.run_dir).resolve(strict=False)
            != self._run_dir(attempt.attempt_id).resolve(strict=False)
            or Path(spec.result_schema_path).resolve(strict=False)
            != (
                self._run_dir(attempt.attempt_id)
                / "input"
                / "worker-result.schema.json"
            ).resolve(strict=False)
            or tuple(spec.authorities) != expected_authorities
            or tuple(spec.allowed_artifact_paths) != expected_paths
            or spec.expected_base_sha
            != (str(job.constraints.get("base_sha") or "") or None)
        ):
            raise SupervisorError(
                "worker recovery launch contract differs from durable Job"
            )
        if effective_grant is not None and (
            not isinstance(spec, OrchestrationLaunchSpec)
            or spec.effective_grant_digest
            != attempt.effective_grant_digest
        ):
            raise SupervisorError(
                "worker recovery orchestration grant changed"
            )
        attestation = attempt.launch_metadata.get("launch_attestation")
        identity = (
            attestation.get("process_identity")
            if isinstance(attestation, Mapping)
            else None
        )
        if not isinstance(identity, Mapping) or any(
            identity.get(key) != value
            for key, value in {
                "pid": binding.process_ref.pid,
                "pgid": binding.process_ref.pgid,
                "session_id": binding.process_ref.session_id,
                "start_identity": binding.process_ref.process_start_identity,
                "boot_id": binding.process_ref.boot_session_id,
                "effective_uid": binding.process_ref.effective_uid,
                "effective_gid": binding.process_ref.effective_gid,
                "real_uid": binding.process_ref.real_uid,
                "real_gid": binding.process_ref.real_gid,
            }.items()
        ):
            raise SupervisorError(
                "worker recovery binding differs from launch attestation"
            )
        return binding, spec, effective_grant

    def _normalise_recovered_lease(
        self, lease: AttemptLease
    ) -> AttemptLease:
        attempt = lease.attempt
        if attempt.status is AttemptStatus.CLAIMED:
            self.runtime.attempts.mark_running(
                attempt.attempt_id,
                fence_generation=attempt.fence_generation,
                lease_token=lease.lease_token,
                required_launch_attestation_schema=(
                    _codex_worker_contract()[1]
                    if self.require_complete_launch_attestation
                    else None
                ),
            )
            current = self.runtime.attempts.get_attempt(attempt.attempt_id)
            if current is None:
                raise SupervisorError(
                    "recovered Attempt disappeared after RUNNING transition"
                )
            attempt = current
        if attempt.status is AttemptStatus.RUNNING:
            self.runtime.attempts.checkpoint_attempt(
                attempt.attempt_id,
                fence_generation=attempt.fence_generation,
                lease_token=lease.lease_token,
                payload=JobPayload(
                    summary="Authorized worker ownership recovered",
                    completed_steps=[
                        "exact durable process and launch identity reattached"
                    ],
                    current_state=(
                        "existing worker execution remains under Executive ownership"
                    ),
                    next_actions=[
                        "collect and validate the original provider result"
                    ],
                ),
            )
            current = self.runtime.attempts.get_attempt(attempt.attempt_id)
            if current is None:
                raise SupervisorError(
                    "recovered Attempt disappeared after checkpoint"
                )
            attempt = current
        return AttemptLease(
            attempt=attempt,
            lease_token=lease.lease_token,
        )

    def _recover_existing_attempt(
        self,
        attempt: Attempt,
        *,
        presence: ProcessPresence,
    ) -> ReconcileReceipt:
        process_was_live = presence is ProcessPresence.LIVE
        if attempt.attempt_id in self._recovered_attempt_ids:
            return ReconcileReceipt(
                attempt_id=attempt.attempt_id,
                job_id=attempt.job_id,
                status=ReconcileStatus.ALREADY_RECOVERED,
                process_was_live=process_was_live,
            )
        if self._attempt_lease_expired(attempt):
            return ReconcileReceipt(
                attempt_id=attempt.attempt_id,
                job_id=attempt.job_id,
                status=ReconcileStatus.LEASE_EXPIRED_QUARANTINED,
                process_was_live=process_was_live,
                error=(
                    "live or terminal execution has an expired lease; "
                    "Runtime-owner reconciliation required"
                ),
            )
        try:
            binding, spec, effective_grant = (
                self._validated_recovery_binding(attempt)
            )
        except SupervisorError as exc:
            return ReconcileReceipt(
                attempt_id=attempt.attempt_id,
                job_id=attempt.job_id,
                status=ReconcileStatus.LIVE_QUARANTINED,
                process_was_live=process_was_live,
                error=str(exc)[:1000],
            )
        try:
            adopted = self.runtime.attempts.adopt_attempt(
                attempt.attempt_id,
                expected_fence_generation=attempt.fence_generation,
                lease_owner=self.instance_id,
            )
        except StateConflict as exc:
            current = self.runtime.attempts.get_attempt(attempt.attempt_id)
            if (
                current is None
                or current.status not in _ACTIVE_ATTEMPT_STATUSES
            ):
                return ReconcileReceipt(
                    attempt_id=attempt.attempt_id,
                    job_id=attempt.job_id,
                    status=ReconcileStatus.ALREADY_RECOVERED,
                    process_was_live=process_was_live,
                )
            return ReconcileReceipt(
                attempt_id=attempt.attempt_id,
                job_id=attempt.job_id,
                status=ReconcileStatus.STALE_FENCE_QUARANTINED,
                process_was_live=process_was_live,
                error=str(exc)[:1000],
            )
        try:
            adopted = self._normalise_recovered_lease(adopted)
            ref = self.adapter.reattach(spec, binding)
        except Exception as exc:
            return ReconcileReceipt(
                attempt_id=attempt.attempt_id,
                job_id=attempt.job_id,
                status=ReconcileStatus.LIVE_QUARANTINED,
                process_was_live=process_was_live,
                error=f"{type(exc).__name__}: {str(exc)[:900]}",
            )
        active = ActiveRun(
            lease=adopted,
            process_ref=ref,
            launch_spec=spec,
            effective_grant=effective_grant,
        )
        self._recovered_runs[attempt.attempt_id] = active
        self._recovered_attempt_ids.add(attempt.attempt_id)
        return ReconcileReceipt(
            attempt_id=attempt.attempt_id,
            job_id=attempt.job_id,
            status=(
                ReconcileStatus.LIVE_RECOVERED
                if process_was_live
                else ReconcileStatus.TERMINAL_RECOVERED
            ),
            process_was_live=process_was_live,
        )

    def _maybe_requeue(self, job_id: str) -> bool:
''',
)
replace_once(
    "control_plane/executive_supervisor.py",
    r'''            presence = self.process_controller.presence(attempt)
            process_was_live = presence is ProcessPresence.LIVE
            uid_sweep: Mapping[str, Any] | None = None
            if process_was_live:
''',
    r'''            presence = self.process_controller.presence(attempt)
            process_was_live = presence is ProcessPresence.LIVE
            uid_sweep: Mapping[str, Any] | None = None
            recovery_raw = attempt.launch_metadata.get(
                "worker_recovery_binding"
            )
            if (
                presence in {ProcessPresence.LIVE, ProcessPresence.ABSENT}
                and isinstance(recovery_raw, Mapping)
            ):
                if (
                    presence is ProcessPresence.ABSENT
                    and not self.process_controller.absence_verified(attempt)
                ):
                    presence = ProcessPresence.UNKNOWN
                else:
                    outcomes.append(
                        self._recover_existing_attempt(
                            attempt,
                            presence=presence,
                        )
                    )
                    continue
            if process_was_live:
''',
)

# Provider-neutral remote adapter reconstructs only its local facade.
replace_once(
    "control_plane/executive_worker_broker.py",
    "    WorkerProcessRef,\n",
    "    WorkerProcessRef,\n"
    "    WorkerRecoveryBinding,\n"
    "    WorkerRecoveryContractError,\n",
)
replace_once(
    "control_plane/executive_worker_broker.py",
    "    def launch_attestation(self, ref: WorkerProcessRef) -> Mapping[str, Any]:\n",
    r'''    def reattach(
        self,
        spec: WorkerLaunchSpec,
        binding: WorkerRecoveryBinding,
    ) -> WorkerProcessRef:
        """Rebind one exact broker-owned run without invoking provider start."""

        if binding.adapter_id != self.adapter_id:
            raise BrokerStateError(
                "remote recovery adapter identity changed"
            )
        try:
            recovered_spec = binding.recover_launch_spec(type(spec))
        except WorkerRecoveryContractError as exc:
            raise BrokerStateError(str(exc)) from exc
        if recovered_spec != spec:
            raise BrokerStateError(
                "remote recovery launch specification changed"
            )
        ref = binding.process_ref
        existing = self._refs.get(ref.run_id)
        if existing is not None:
            if existing == ref and self._specs.get(ref.run_id) == spec:
                return ref
            raise BrokerStateError(
                "remote run is already bound to another execution"
            )
        result = self.client.request_sync(
            "status",
            {"run_id": ref.run_id},
        )
        run = _mapping(result.get("run"), field="run status")
        observed = _process_ref_from_json(run.get("process_ref"))
        if observed != ref:
            raise BrokerProtocolError(
                "remote recovery status changed immutable process identity"
            )
        status = run.get("status")
        allowed = {
            item.value for item in WorkerRunStatus
        } | {"COLLECTED", "ERROR"}
        if status not in allowed:
            raise BrokerProtocolError(
                "remote recovery status is invalid"
            )
        self._refs[ref.run_id] = ref
        self._specs[ref.run_id] = spec
        return ref

    def launch_attestation(self, ref: WorkerProcessRef) -> Mapping[str, Any]:
''',
)

# Existing dispatch registry owns every recovered finisher.
replace_once(
    "control_plane/executive_service.py",
    "    async def _replay_terminal_returns_on_startup(self) -> None:\n",
    r'''    @staticmethod
    def _reconciliation_requires_quarantine(values: list[Any]) -> bool:
        blocked = {
            "IDENTITY_AMBIGUOUS",
            "LIVE_QUARANTINED",
            "LEASE_EXPIRED_QUARANTINED",
            "STALE_FENCE_QUARANTINED",
        }
        for value in values:
            status = getattr(value, "status", None)
            rendered = getattr(status, "value", status)
            if rendered in blocked:
                return True
        return False

    async def _schedule_recovered_runs(self) -> None:
        supervisor = self._require_supervisor()
        take = getattr(supervisor, "take_recovered_runs", None)
        if not callable(take):
            return
        for active in take():
            lease = getattr(active, "lease", None)
            attempt = getattr(lease, "attempt", None)
            job_id = getattr(attempt, "job_id", None)
            attempt_id = getattr(attempt, "attempt_id", None)
            if not isinstance(job_id, str) or not isinstance(
                attempt_id, str
            ):
                self._service_state = "QUARANTINED"
                raise ServiceError(
                    "recovered worker has no exact Job/Attempt identity"
                )
            existing = self._dispatch_tasks.get(job_id)
            if existing is not None and not existing.done():
                self._service_state = "QUARANTINED"
                raise ServiceError(
                    "recovered worker conflicts with an existing finisher"
                )
            task = asyncio.create_task(
                self._finish_dispatched(job_id, active),
                name=f"executive-recovered-finish-{job_id}",
            )
            self._dispatch_tasks[job_id] = task

    async def _replay_terminal_returns_on_startup(self) -> None:
''',
)
replace_once(
    "control_plane/executive_service.py",
    r'''        self._startup_reconciliation = await asyncio.to_thread(
            supervisor.reconcile_restart,
            requeue_lost=False,
        )
        # Activation is the first moment this bootstrap-quarantined instance
''',
    r'''        self._startup_reconciliation = await asyncio.to_thread(
            supervisor.reconcile_restart,
            requeue_lost=False,
        )
        await self._schedule_recovered_runs()
        if self._reconciliation_requires_quarantine(
            self._startup_reconciliation
        ):
            self._service_state = "QUARANTINED"
            raise StateConflict(
                "Executive restart reconciliation was quarantined"
            )
        # Activation is the first moment this bootstrap-quarantined instance
''',
)
replace_once(
    "control_plane/executive_service.py",
    r'''                if self.operator_supervisor is not None:
                    self._startup_reconciliation.extend(
                        await asyncio.to_thread(
                            self.operator_supervisor.reconcile_restart,
                            requeue_lost=False,
                        )
                    )
                await self._replay_terminal_returns_on_startup()
''',
    r'''                if self.operator_supervisor is not None:
                    self._startup_reconciliation.extend(
                        await asyncio.to_thread(
                            self.operator_supervisor.reconcile_restart,
                            requeue_lost=False,
                        )
                    )
                await self._schedule_recovered_runs()
                if self._reconciliation_requires_quarantine(
                    self._startup_reconciliation
                ):
                    self._service_state = "QUARANTINED"
                await self._replay_terminal_returns_on_startup()
''',
)
replace_once(
    "control_plane/executive_service.py",
    "            if self.config.coo_autonomy_armed:\n"
    "                self._coo_shutdown_event = asyncio.Event()\n",
    "            if (\n"
    "                self.config.coo_autonomy_armed\n"
    "                and self._service_state == \"READY\"\n"
    "            ):\n"
    "                self._coo_shutdown_event = asyncio.Event()\n",
)
replace_once(
    "control_plane/executive_service.py",
    r'''            for job_id, task in list(self._dispatch_tasks.items()):
                if task.done():
                    continue
                try:
''',
    r'''            for job_id, task in list(self._dispatch_tasks.items()):
                if task.done():
                    continue
                if task.get_name().startswith(
                    "executive-recovered-finish-"
                ):
                    # A service restart relinquishes only the in-memory
                    # collector. The exact worker remains owned by its durable
                    # Attempt and will be reattached by the replacement.
                    continue
                try:
''',
)
