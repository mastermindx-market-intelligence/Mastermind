"""Pin ADAPTER_DESCRIPTORS implemented=True to the reviewed set.

Every implemented=True entry must be one of the adapters pinned in this file.
A new True requires expanding this pin and documenting, in this docstring,
the existing real-turn receipt path (BUILT_NOT_PROVEN -> PROVEN_LIVE).
The one PR1794 source-only addition is explicitly recorded below; it does not
create a general substitute for other adapters' required receipt paths. Updating
only the descriptor table, without expanding this pin and documenting that
status here, must fail CI.

Master-implemented set (read from origin/master:control_plane/worker_adapter.py
ADAPTER_DESCRIPTORS on 2026-09-13):
    - codex-cli

PR1794 source-implementation addition (BUILT_NOT_PROVEN; this records a source
implementation only and is NOT a master merge, NOT runtime activation, and NOT
an R1/live receipt):
    - canonical-paid-fabric: exact class CanonicalPaidFabricWorkerAdapter
      exists in the source tree for sealed-input READ/RESEARCH subjects; no
      native/tools/write or absent physical qualification admission is
      implied.

WO-10 source-implementation addition (BUILT_NOT_PROVEN; MMOS V1 Rev 4 §S3.D,
stacked on feat/mmos-v1-shared-contracts):
    - hermes-native: exact class HermesWorkerAdapter exists in the source tree
      and implements the WorkerExecutionAdapter floor plus reattach.  This is
      NOT a master merge, NOT runtime activation, and NOT an R1/live receipt.
      The adapter is BUILT but UNSELECTED until the incumbent runtime selects
      it (Rev 4 l.253 honest-behavior table); registering the descriptor
      selects nothing, and no routing policy may bind a live worker through
      this id before that selection.  The proven-live receipt path remains:
      a real-turn receipt through the selected incumbent runtime.

Receipt path for a PROVEN_LIVE entry: attach the real-turn receipt ruling R5
requires and move the corresponding catalog rows off SPEC_ONLY in the same
change. There is no such receipt for claude-compatible-subscription, and no
R1/live receipt exists for canonical-paid-fabric either.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from control_plane.child_execution_contracts import (
    C2_COMPLEX_BOUNDED,
    ExecutionBinding,
)
from control_plane.hermes_worker_adapter import (
    HermesWorkerAdapter,
    HermesWorkerAdapterError,
    NativeCancelOutcome,
)
from control_plane.worker_adapter import (
    ADAPTER_DESCRIPTORS,
    RecoverableWorkerExecutionAdapter,
    WorkerExecutionAdapter,
    adapter_descriptor,
    adapter_implementation,
    bind_reviewed_adapter,
    construct_reviewed_adapter,
)
from control_plane.worker_execution_contract import (
    BinaryAttestation,
    CancelReceipt,
    CollectionReceipt,
    ProcessInspector,
    ValidationReceipt,
    WorkerLaunchSpec,
    WorkerProcessRef,
    WorkerRecoveryBinding,
    WorkerResult,
    WorkerRunStatus,
)


# "codex-cli" is named explicitly from origin/master's implemented=True rows.
# "canonical-paid-fabric" is the PR1794 source-implementation entry documented
# above (BUILT_NOT_PROVEN). "hermes-native" is the WO-10 source-implementation
# entry documented above (BUILT_NOT_PROVEN; built but unselected). Do not add
# a name here unless this docstring records the receipt path or
# source-implementation status that authorizes it.
MASTER_IMPLEMENTED_ADAPTER_IDS = frozenset(
    {"codex-cli", "canonical-paid-fabric", "hermes-native"}
)


def test_implemented_true_requires_master_set_or_documented_receipt_path() -> None:
    implemented = frozenset(
        adapter_id
        for adapter_id, descriptor in ADAPTER_DESCRIPTORS.items()
        if descriptor.implemented is True
    )
    assert implemented == MASTER_IMPLEMENTED_ADAPTER_IDS


# =============================================================================
# WO-10 — HermesWorkerAdapter (built but unselected)
# =============================================================================

_HEX64 = "a" * 64
_LEASE_FUTURE = "2099-01-01T00:00:00Z"
_LEASE_PAST = "2000-01-01T00:00:00Z"


def _binary() -> BinaryAttestation:
    return BinaryAttestation(
        path="/usr/local/bin/hermes", real_path="/usr/local/bin/hermes",
        version="1.0.0", sha256=_HEX64, team_identifier=None,
        size=1024, device=1, inode=2, mode=0o755, uid=501, gid=20, mtime_ns=3,
    )


def _process_ref(run_id: str, pid: int = 4242) -> WorkerProcessRef:
    return WorkerProcessRef(
        run_id=run_id, pid=pid, pgid=pid,
        process_start_identity=f"identity-{run_id}",
        boot_session_id="boot-1", launch_nonce=f"nonce-{run_id}",
        provider_session_id=None,
        stdout_path=f"/var/lib/mastermind/runs/{run_id}/stdout",
        stderr_path=f"/var/lib/mastermind/runs/{run_id}/stderr",
        result_path=f"/var/lib/mastermind/runs/{run_id}/result.json",
        started_at="2026-11-08T12:00:00Z", binary=_binary(), base_sha="b" * 40,
    )


def _launch_spec(run_id: str = "run-1", worker_id: str = "workers/12",
                 prompt: str = "do the work",
                 run_dir: Path = Path("/tmp/mmos-run")) -> WorkerLaunchSpec:
    return WorkerLaunchSpec(
        run_id=run_id, job_id="jobs/77", worker_id=worker_id,
        workspace_path=Path("/tmp/mmos-ws"), run_dir=run_dir,
        prompt=prompt, result_schema_path=Path("/tmp/mmos-run/input/schema.json"),
    )


def _binding(**overrides) -> ExecutionBinding:
    kwargs = dict(
        root_run_ref="root-1", immediate_parent_run_ref="parent-7",
        logical_child_key="child-a", request_digest=_HEX64,
        effective_complexity=C2_COMPLEX_BOUNDED, adapter_id="hermes-native",
        worker_id="workers/12", fence_counter=7, lease_expiry=_LEASE_FUTURE,
    )
    kwargs.update(overrides)
    return ExecutionBinding(**kwargs)


class FakeInspector(ProcessInspector):
    """Minimal ProcessInspector stand-in for the native session owner."""

    def boot_session_id(self) -> str:
        return "boot-1"

    def identity(self, pid: int) -> tuple[str, int]:
        return (f"identity-run-1", pid)

    def inspect(self, pid: int) -> object:
        return {"pid": pid}


class FakeNativeRunner:
    """In-memory HermesNativeRunnerPort owned by the tests."""

    def __init__(self) -> None:
        self.launches: list[WorkerLaunchSpec] = []
        self.terminations: list[tuple[str, str]] = []
        self.collections: list[str] = []
        self.validations: list[tuple[WorkerLaunchSpec, tuple[str, ...]]] = []
        self.refs: dict[str, WorkerProcessRef] = {}
        self.state_by_run: dict[str, WorkerRunStatus] = {}
        self.known_runs: set[str] = set()
        self.settle_immediately = False
        self.collect_receipt_run: str | None = None

    async def launch(self, spec: WorkerLaunchSpec) -> WorkerProcessRef:
        self.launches.append(spec)
        ref = _process_ref(spec.run_id)
        self.refs[spec.run_id] = ref
        self.state_by_run[spec.run_id] = WorkerRunStatus.RUNNING
        self.known_runs.add(spec.run_id)
        return ref

    async def native_state(self, ref: WorkerProcessRef) -> WorkerRunStatus:
        return self.state_by_run[ref.run_id]

    async def collect(self, ref: WorkerProcessRef) -> CollectionReceipt:
        run_id = self.collect_receipt_run or ref.run_id
        self.collections.append(ref.run_id)
        return CollectionReceipt(
            process_ref=_process_ref(run_id),
            result=WorkerResult(
                job_id="jobs/77", run_id=run_id, worker_id="workers/12",
                status=WorkerRunStatus.SUCCEEDED, structured_output=None,
                artifact_manifest=(), git_manifest={}, usage={},
                provider_session_id=None, exit_code=0,
                started_at="2026-11-08T12:00:00Z",
                finished_at="2026-11-08T12:01:00Z", error=None,
            ),
            stdout_sha256=_HEX64, stderr_sha256=_HEX64, result_sha256=_HEX64,
        )

    async def terminate(
        self, ref: WorkerProcessRef, reason: str
    ) -> NativeCancelOutcome:
        self.terminations.append((ref.run_id, reason))
        if self.settle_immediately:
            self.state_by_run[ref.run_id] = WorkerRunStatus.CANCELLED
        return NativeCancelOutcome(
            requested=True,
            settled=self.settle_immediately,
            already_exited=False,
            escalated_to_sigkill=False,
            finished_at="2026-11-08T12:02:00Z",
        )

    async def validate_argv(
        self, spec: WorkerLaunchSpec, argv: tuple[str, ...], *,
        timeout_seconds: float = 300.0,
    ) -> ValidationReceipt:
        self.validations.append((spec, argv))
        return ValidationReceipt(
            argv=argv, exit_code=0, stdout_sha256=_HEX64, stdout_size=1,
            stderr_sha256=_HEX64, stderr_size=0, timed_out=False, error=None,
        )

    def knows_execution(self, ref: WorkerProcessRef) -> bool:
        return ref.run_id in self.known_runs


def _adapter(
    runner: FakeNativeRunner | None = None,
    binding=None,
    binding_error: Exception | None = None,
):
    runner = runner or FakeNativeRunner()

    def binding_source(spec: WorkerLaunchSpec):
        if binding_error is not None:
            raise binding_error
        return binding

    adapter = HermesWorkerAdapter(
        runner, binding_source, FakeInspector(),
    )
    return adapter, runner


class HermesNativeDescriptorTests(unittest.TestCase):
    def test_descriptor_is_registered_resolvable_and_documented(self) -> None:
        descriptor = adapter_descriptor("hermes-native")
        self.assertTrue(descriptor.implemented)
        self.assertEqual(descriptor.adapter_id, "hermes-native")
        implementation = adapter_implementation("hermes-native")
        self.assertIs(implementation, HermesWorkerAdapter)
        self.assertEqual(implementation.adapter_id, "hermes-native")

    def test_constructed_adapter_binds_and_satisfies_protocols(self) -> None:
        runner = FakeNativeRunner()
        adapter = construct_reviewed_adapter(
            "hermes-native", runner, lambda spec: None, FakeInspector()
        )
        self.assertIsInstance(adapter, WorkerExecutionAdapter)
        self.assertIsInstance(adapter, RecoverableWorkerExecutionAdapter)
        descriptor = bind_reviewed_adapter(adapter, "hermes-native")
        self.assertTrue(descriptor.implemented)


class HermesStartTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_refused_without_valid_execution_binding(self) -> None:
        cases = [
            ("no binding", None),
            ("wrong type", object()),
            ("other adapter", _binding(adapter_id="codex-cli")),
            ("worker mismatch", _binding(worker_id="workers/99")),
            ("empty worker", _binding(worker_id="")),
            ("expired lease", _binding(lease_expiry=_LEASE_PAST)),
            ("malformed lease", _binding(lease_expiry="not-a-time")),
        ]
        for label, binding in cases:
            with self.subTest(label):
                adapter, runner = _adapter(binding=binding)
                with self.assertRaises(HermesWorkerAdapterError):
                    await adapter.start(_launch_spec())
                self.assertEqual(runner.launches, [])

    async def test_start_refused_when_binding_source_raises(self) -> None:
        adapter, runner = _adapter(binding_error=RuntimeError("broker down"))
        with self.assertRaises(HermesWorkerAdapterError):
            await adapter.start(_launch_spec())
        self.assertEqual(runner.launches, [])

    async def test_start_retains_original_native_ref_before_ack(self) -> None:
        adapter, runner = _adapter(binding=_binding())
        spec = _launch_spec(run_dir=_recovery_run_dir())
        ref = await adapter.start(spec)
        self.assertEqual(runner.launches, [spec])
        # The ACK returns exactly the original native ref from the owner.
        self.assertIs(ref, runner.refs[spec.run_id])
        # Retention is observable before any later operation: status and
        # reattach both resolve to the same original object.
        self.assertEqual(await adapter.status(ref), WorkerRunStatus.RUNNING)
        self.assertIs(adapter.reattach(spec, _recovery_binding(spec, ref)), ref)

    async def test_start_refuses_duplicate_run_and_native_identity_mismatch(
        self,
    ) -> None:
        adapter, runner = _adapter(binding=_binding())
        spec = _launch_spec()
        await adapter.start(spec)
        with self.assertRaises(HermesWorkerAdapterError):
            await adapter.start(spec)
        self.assertEqual(len(runner.launches), 1)


class HermesStatusCollectTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_reports_actual_native_state(self) -> None:
        adapter, runner = _adapter(binding=_binding())
        ref = await adapter.start(_launch_spec())
        runner.state_by_run[ref.run_id] = WorkerRunStatus.SUCCEEDED
        self.assertEqual(await adapter.status(ref), WorkerRunStatus.SUCCEEDED)

    async def test_collect_result_reads_original_retained_execution(self) -> None:
        adapter, runner = _adapter(binding=_binding())
        ref = await adapter.start(_launch_spec())
        receipt = await adapter.collect_result(ref)
        self.assertEqual(receipt.process_ref.run_id, ref.run_id)
        self.assertEqual(runner.collections, [ref.run_id])
        # A result minted for a different run is a replacement: refused.
        runner.collect_receipt_run = "run-other"
        with self.assertRaises(HermesWorkerAdapterError):
            await adapter.collect_result(ref)

    async def test_unknown_or_swapped_refs_are_refused(self) -> None:
        adapter, _ = _adapter(binding=_binding())
        unknown = _process_ref("run-unknown")
        for op in (
            lambda: adapter.status(unknown),
            lambda: adapter.collect_result(unknown),
            lambda: adapter.cancel(unknown, "stop"),
        ):
            with self.assertRaises(HermesWorkerAdapterError):
                await op()


class HermesCancelTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_reports_requested_versus_settled(self) -> None:
        adapter, runner = _adapter(binding=_binding())
        ref = await adapter.start(_launch_spec())
        receipt = await adapter.cancel(ref, "superseded")
        self.assertIsInstance(receipt, CancelReceipt)
        self.assertTrue(receipt.signal_sent)
        # Requested, NOT yet settled.
        report = adapter.cancel_report(ref.run_id)
        self.assertIsNotNone(report)
        self.assertTrue(report.requested)
        self.assertFalse(report.settled)
        self.assertIsNone(report.settled_at)
        self.assertEqual(
            await adapter.status(ref), WorkerRunStatus.CANCELLING
        )
        # The native side settles; only then does the report and status.
        runner.state_by_run[ref.run_id] = WorkerRunStatus.CANCELLED
        self.assertEqual(await adapter.status(ref), WorkerRunStatus.CANCELLED)
        report = adapter.cancel_report(ref.run_id)
        self.assertTrue(report.settled)
        self.assertEqual(report.settled_state, "CANCELLED")
        self.assertIsNotNone(report.settled_at)

    async def test_cancel_settled_immediately_when_owner_confirms(self) -> None:
        adapter, runner = _adapter(binding=_binding())
        ref = await adapter.start(_launch_spec())
        runner.settle_immediately = True
        await adapter.cancel(ref, "duplicate")
        report = adapter.cancel_report(ref.run_id)
        self.assertTrue(report.requested)
        self.assertTrue(report.settled)

    async def test_cancel_requires_nonempty_reason(self) -> None:
        adapter, _ = _adapter(binding=_binding())
        ref = await adapter.start(_launch_spec())
        with self.assertRaises(HermesWorkerAdapterError):
            await adapter.cancel(ref, "  ")


class HermesValidationArgvTests(unittest.IsolatedAsyncioTestCase):
    async def test_preserves_explicitly_authorized_command_contract(self) -> None:
        adapter, runner = _adapter(binding=_binding())
        receipt = await adapter.run_validation_argv(
            _launch_spec(), ["hermes", "--version"]
        )
        self.assertEqual(receipt.exit_code, 0)
        self.assertEqual(runner.validations[-1][1], ("hermes", "--version"))

    async def test_refuses_unauthorized_argv(self) -> None:
        adapter, runner = _adapter(binding=_binding())
        for bad in ([], ["ok", 5], "hermes --version"):
            with self.subTest(repr(bad)):
                with self.assertRaises(HermesWorkerAdapterError):
                    await adapter.run_validation_argv(_launch_spec(), bad)
        with self.assertRaises(HermesWorkerAdapterError):
            await adapter.run_validation_argv(
                _launch_spec(), ["hermes"], timeout_seconds=0
            )
        self.assertEqual(runner.validations, [])


class HermesReattachTests(unittest.IsolatedAsyncioTestCase):
    async def test_reattach_returns_the_same_original_ref(self) -> None:
        adapter, runner = _adapter(binding=_binding())
        spec = _launch_spec(run_dir=_recovery_run_dir())
        ref = await adapter.start(spec)
        binding = _recovery_binding(spec, ref)
        reattached = adapter.reattach(spec, binding)
        self.assertIs(reattached, ref)
        # Never created a replacement: exactly one launch ever happened.
        self.assertEqual(len(runner.launches), 1)
        self.assertEqual(runner.terminations, [])

    async def test_reattach_after_restart_adopts_original_never_replaces(
        self,
    ) -> None:
        runner = FakeNativeRunner()

        def binding_source(spec):
            return _binding()

        first = HermesWorkerAdapter(runner, binding_source, FakeInspector())
        spec = _launch_spec(run_dir=_recovery_run_dir())
        ref = await first.start(spec)
        binding = _recovery_binding(spec, ref)
        # Coordinator restart: a fresh adapter instance, same native owner.
        second = HermesWorkerAdapter(runner, binding_source, FakeInspector())
        reattached = second.reattach(spec, binding)
        self.assertEqual(reattached, ref)
        self.assertEqual(len(runner.launches), 1)

    async def test_reattach_refuses_unknown_execution_instead_of_replacing(
        self,
    ) -> None:
        runner = FakeNativeRunner()

        def binding_source(spec):
            return _binding()

        first = HermesWorkerAdapter(runner, binding_source, FakeInspector())
        spec = _launch_spec(run_dir=_recovery_run_dir())
        ref = await first.start(spec)
        binding = _recovery_binding(spec, ref)
        runner.known_runs.discard(ref.run_id)
        second = HermesWorkerAdapter(runner, binding_source, FakeInspector())
        with self.assertRaises(HermesWorkerAdapterError):
            second.reattach(spec, binding)
        self.assertEqual(len(runner.launches), 1)

    async def test_reattach_refuses_foreign_or_drifted_bindings(self) -> None:
        adapter, runner = _adapter(binding=_binding())
        spec = _launch_spec(run_dir=_recovery_run_dir())
        ref = await adapter.start(spec)
        foreign = _recovery_binding(spec, ref)
        object.__setattr__(foreign, "adapter_id", "codex-cli")
        with self.assertRaises(HermesWorkerAdapterError):
            adapter.reattach(spec, foreign)
        drifted = _recovery_binding(
            _launch_spec(prompt="a different task", run_dir=_recovery_run_dir()),
            ref, name="prompt2.txt",
        )
        with self.assertRaises(HermesWorkerAdapterError):
            adapter.reattach(spec, drifted)
        other_run = _recovery_binding(spec, ref)
        object.__setattr__(
            other_run, "process_ref", _process_ref("run-other")
        )
        with self.assertRaises(HermesWorkerAdapterError):
            adapter.reattach(spec, other_run)
        with self.assertRaises(HermesWorkerAdapterError):
            adapter.reattach(spec, object())
        self.assertEqual(len(runner.launches), 1)


def _recovery_run_dir() -> Path:
    import tempfile

    run_dir = Path(tempfile.mkdtemp(prefix="mmos-wo10-recovery-"))
    (run_dir / "input").mkdir()
    return run_dir


def _recovery_binding(
    spec: WorkerLaunchSpec, ref: WorkerProcessRef, name: str = "prompt.txt"
) -> WorkerRecoveryBinding:
    """Build a real WorkerRecoveryBinding over a private prompt file."""

    import os

    prompt_path = spec.run_dir / "input" / name
    prompt_path.write_bytes(spec.prompt.encode("utf-8"))
    os.chmod(prompt_path, 0o600)
    return WorkerRecoveryBinding.bind(
        adapter_id="hermes-native", spec=spec, process_ref=ref,
        prompt_path=prompt_path,
    )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
