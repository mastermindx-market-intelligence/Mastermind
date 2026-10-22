"""Inert regression coverage for direct entry and non-replayed DISARM closeout."""
from pathlib import Path
import subprocess
import sys

import pytest

from ops.executive_os import autonomy_control as owner
from tests.test_executive_autonomy_control import FakeTransactionHost, NOW, SHA, _arm_request


def test_isolated_direct_entry_uses_the_publishers_canonical_owner_classes():
    # Run the actual file in the wrapper's isolated interpreter mode. Intercept
    # main before its first instruction: no privilege/config/service call runs.
    script = r'''
import pathlib, runpy, sys
path = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(path.parents[2]))
from ops.executive_os import autonomy_control as owner
from ops.executive_os import control_observation as publisher
seen = []
class SourceReached(Exception): pass
def source(sha):
    seen.append(sha)
    raise SourceReached()
publisher._source = source
def intercept(frame, event, arg):
    if event == 'call' and frame.f_code.co_name == 'main' and pathlib.Path(frame.f_code.co_filename).resolve() == path:
        sys.settrace(None)
        namespace = frame.f_globals
        host = namespace['ProductionTransactionHost']()
        config = namespace['ConfigEvidence']('c'*64, 'd'*64, {}, {}, b'{}', b'{}')
        candidate = namespace['CandidateConfigs']({}, {}, b'{}', b'{}', 'c'*64, 'd'*64)
        tx = namespace['TransactionContext']('autonomy-'+'1'*12, 'a'*40, config, candidate, None)
        host._active_transaction = tx
        host._transaction_owner_fd = 123  # Inert sentinel; never read or closed.
        try:
            publisher._publish_for_transaction(host, tx)
        except SourceReached:
            pass
        except owner.TransactionEffectUnknown:
            pass
        assert seen == ['a'*40], 'direct entry failed canonical publication type guard'
        assert type(host) is owner.ProductionTransactionHost
        assert type(tx) is owner.TransactionContext
        print('CANONICAL_MAIN_GUARD_REACHED_WITHOUT_HOST_EFFECTS')
        raise SystemExit(0)
    return intercept
sys.settrace(intercept)
runpy.run_path(str(path), run_name='__main__')
raise AssertionError('main was not invoked')
'''
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", script, str(Path(owner.__file__).resolve())],
        text=True, capture_output=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "CANONICAL_MAIN_GUARD_REACHED_WITHOUT_HOST_EFFECTS"


@pytest.mark.parametrize("failure", [owner.TransactionEffectUnknown, OSError])
def test_disarm_completion_failure_never_enters_rollback_or_republishes(failure):
    host = FakeTransactionHost()
    host.existing_disarm = lambda *args, **kwargs: None
    calls = []
    original_stop = host.stop_services

    def stop(sha):
        calls.append("stop")
        original_stop(sha)

    def complete(tx):
        calls.append("complete")
        # Model acknowledgement loss after publication or during final cleanup.
        raise failure()

    def rollback(*args):
        calls.append("rollback")
        raise AssertionError("uncertain closeout must not rewrite configs/receipt")

    host.stop_services = stop
    host.complete_transaction = complete
    host.rollback_disarmed = rollback
    with pytest.raises(owner.TransactionEffectUnknown):
        owner.execute_disarm(host, SHA, now=NOW)
    assert calls == ["stop", "complete"]
    assert host.marker is True
    assert host.receipt["state"] == "DISARMED"
    assert host.receipt["transaction_id"] == "autonomy-deadbeefcafe"
    assert host.services == "STOPPED"
    assert host.transaction_calls == ["lock", "candidates", "validated", "worker", "control", "receipt"]


def test_disarm_unknown_before_closeout_does_not_rollback():
    host = FakeTransactionHost()
    host.existing_disarm = lambda *args, **kwargs: None
    calls = []

    def receipt(*args):
        calls.append("receipt")
        raise owner.TransactionEffectUnknown()

    host.write_autonomy_receipt = receipt
    host.rollback_disarmed = lambda *args: calls.append("rollback")
    host.complete_transaction = lambda *args: calls.append("complete")
    with pytest.raises(owner.TransactionEffectUnknown):
        owner.execute_disarm(host, SHA, now=NOW)
    assert calls == ["receipt"]
    assert host.marker is True


def test_disarm_known_prepublication_failure_retains_existing_rollback():
    host = FakeTransactionHost(fail_after="validated")
    host.existing_disarm = lambda *args, **kwargs: None
    with pytest.raises(owner.ArmTransactionError, match="disarm_recovered"):
        owner.execute_disarm(host, SHA, now=NOW)
    assert host.marker is False
    assert host.receipt["state"] == "DISARMED"


@pytest.mark.parametrize('verb', ['arm', 'disarm'])
def test_cleanup_error_after_publication_preserves_boundary_and_never_republishes(verb):
    host = FakeTransactionHost()
    host.existing_disarm = lambda *a, **kw: None
    state = dict(phase='LOCKED', writes=0, sealed=None, rollback=0, stops=0)
    def stop(sha):
        state['stops'] += 1
        host.services = 'STOPPED'
    def complete(tx):
        state['phase'] = 'CONTROL_OBSERVATION_PUBLICATION_STARTED'
        state['writes'] += 1
        state['sealed'] = tx.candidates.control_sha256
        raise OSError('cleanup acknowledgement lost after successful publication')
    def rollback(tx, receipt):
        state['rollback'] += 1
        state['phase'] = 'RECEIPT_REPLACED'
        complete(tx)
    host.stop_services = stop
    host.complete_transaction = complete
    host.rollback_disarmed = rollback
    with pytest.raises(owner.TransactionEffectUnknown):
        if verb == 'arm':
            owner.execute_arm(host, _arm_request(), now=NOW)
        else:
            owner.execute_disarm(host, SHA, now=NOW)
    assert state['phase'] == 'CONTROL_OBSERVATION_PUBLICATION_STARTED'
    assert state['writes'] == 1
    assert state['sealed'] == owner.sha256_bytes(owner.encode_config(host.control_config))
    assert state['rollback'] == 0
    assert state['stops'] == (0 if verb == 'arm' else 1)
    assert host.marker is True
