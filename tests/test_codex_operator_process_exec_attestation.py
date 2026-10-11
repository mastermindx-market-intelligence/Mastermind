"""Exact kernel-incarnation behavior through legitimate launcher exec.

This is a pure failure/allow contract; no subprocess or provider is launched.
"""
import pytest

from control_plane.codex_operator_adapter import CodexAdapterError, CodexOperatorAdapter
from control_plane.operator_harness_contract import AdapterFailureClass


@pytest.mark.parametrize("launched,initialized", [
    ((12345, 1), (12345, 7)),  # same process, valid shebang/exec evolution
    ((12345, 7), (12345, 7)),
    (None, None),              # unchanged non-Darwin legacy behavior
])
def test_initialized_process_preserves_kernel_incarnation(launched, initialized):
    CodexOperatorAdapter._require_same_initialized_incarnation(
        launched, initialized
    )


@pytest.mark.parametrize("launched,initialized", [
    ((12345, 1), (67890, 1)),  # recycled PID / process substitution
    ((12345, 1), None),        # lost previously attested identity
    (None, (12345, 1)),        # unexpected identity appearance
])
def test_initialized_process_refuses_unproven_or_changed_incarnation(
    launched, initialized
):
    with pytest.raises(CodexAdapterError) as err:
        CodexOperatorAdapter._require_same_initialized_incarnation(
            launched, initialized
        )
    assert err.value.failure_class is AdapterFailureClass.PROCESS_CRASH
    assert err.value.effect_unknown is True


def test_post_initialize_exec_version_drift_still_refuses():
    """Startup exec tolerance never extends to a running accepted session."""
    from control_plane.executive_process_identity import _ProcessInstanceObservation
    from control_plane.operator_harness_contract import ProcessIdentityObservation

    adapter = object.__new__(CodexOperatorAdapter)
    expected = ProcessIdentityObservation(
        pid=123, pgid=123,
        process_start_identity="Thu Jan  1 00:00:00 1970", boot_id="boot-1"
    )
    adapter.process_identity_observer = lambda _pid: expected
    adapter.process_instance_observer = lambda _pid: _ProcessInstanceObservation(
        unique_id=33, pidversion=8
    )
    with pytest.raises(CodexAdapterError) as err:
        adapter._require_process_continuity(expected, (33, 7))
    assert err.value.failure_class is AdapterFailureClass.PROCESS_CRASH
    assert err.value.effect_unknown is True
