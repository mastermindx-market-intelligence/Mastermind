"""Recovery is an opt-in extension, not a breaking change to adapter/v1."""
from __future__ import annotations
import control_plane.worker_adapter as wa


class LegacyAdapter:
    adapter_id = "codex-cli"
    inspector = object()
    async def start(self, spec): ...
    async def status(self, ref): ...
    async def collect_result(self, ref): ...
    async def cancel(self, ref, reason): ...
    async def run_validation_argv(self, spec, argv, *, timeout_seconds=300.0): ...


class RecoverableAdapter(LegacyAdapter):
    def reattach(self, spec, binding): ...


def test_worker_v1_keeps_legacy_adapters_compatible():
    assert isinstance(LegacyAdapter(), wa.WorkerExecutionAdapter)


def test_worker_recovery_is_a_separate_optional_capability():
    recovery = getattr(wa, "RecoverableWorkerExecutionAdapter", None)
    assert recovery is not None
    assert not isinstance(LegacyAdapter(), recovery)
    assert isinstance(RecoverableAdapter(), recovery)
    assert isinstance(RecoverableAdapter(), wa.WorkerExecutionAdapter)


def test_optional_recovery_never_weakens_the_common_floor():
    class ReattachOnly:
        def reattach(self, spec, binding): ...
    assert not isinstance(ReattachOnly(), wa.WorkerExecutionAdapter)
    recovery = getattr(wa, "RecoverableWorkerExecutionAdapter", None)
    assert recovery is not None
    assert not isinstance(ReattachOnly(), recovery)


def test_current_claude_adapter_keeps_v1_compatibility_without_recovery():
    from control_plane.claude_subscription_worker import ClaudeSubscriptionWorkerAdapter

    adapter = object.__new__(ClaudeSubscriptionWorkerAdapter)
    adapter.inspector = object()
    assert isinstance(adapter, wa.WorkerExecutionAdapter)
    assert not isinstance(adapter, wa.RecoverableWorkerExecutionAdapter)
