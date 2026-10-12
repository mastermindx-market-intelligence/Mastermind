"""Original remote ownership never becomes a local process or absence claim."""
import dataclasses

import pytest

from control_plane.executive_supervisor import ProcessPresence
from control_plane.executive_worker_broker import BrokerProtocolError, BrokerStateError
from control_plane.fabric_cleanup_transport import stamp
from test_executive_fabric_adapter_fencing import started, adopt


def test_current_owner_presence_is_status_only(tmp_path, monkeypatch):
    runtime, lease, adapter, spec, ref, client = started(tmp_path, monkeypatch)
    assert adapter.process_controller is adapter
    assert adapter.requires_recovery_lease is True
    assert adapter.presence(lease.attempt) is ProcessPresence.LIVE
    assert client.calls == ["start", "status"]
    assert adapter.expected_worker_uid(lease.attempt) == ref.effective_uid


@pytest.mark.parametrize("state", ["SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT", "MISSING"])
def test_terminal_or_missing_status_does_not_prove_absence(tmp_path, monkeypatch, state):
    runtime, lease, adapter, spec, ref, client = started(tmp_path, monkeypatch)
    original = client.request_sync
    def response(*args, **kwargs):
        result = original(*args, **kwargs)
        result["run"]["status"] = state
        return result
    monkeypatch.setattr(client, "request_sync", response)
    assert adapter.presence(lease.attempt) is ProcessPresence.UNKNOWN
    assert adapter.absence_verified(lease.attempt) is False


@pytest.mark.parametrize("during", [False, True])
def test_presence_fenced_across_takeover(tmp_path, monkeypatch, during):
    runtime, lease, adapter, spec, ref, client = started(tmp_path, monkeypatch)
    if during:
        client.during_request = lambda: adopt(runtime, lease)
    else:
        adopt(runtime, lease)
    assert adapter.presence(lease.attempt) is ProcessPresence.UNKNOWN
    assert client.calls == (["start", "status"] if during else ["start"])


def test_cleanup_expectation_binds_original_principal_and_remote_generation(tmp_path, monkeypatch):
    runtime, lease, adapter, spec, ref, client = started(tmp_path, monkeypatch)
    expected = adapter.fabric_cleanup_expectation(ref)
    assert expected["binding"] == client.retained["binding"]
    assert expected["physical_binding_sha256"] == client.retained["physical_binding_sha256"]
    assert expected["worker_uid"] == ref.effective_uid != 501
    assert expected["process_identity"]["pid"] == ref.pid
    assert expected["process_identity"]["boot_session_id"] == ref.boot_session_id
    with pytest.raises(BrokerStateError):
        adapter.fabric_cleanup_expectation(dataclasses.replace(ref, pid=ref.pid + 1))


def test_unavailable_owner_cleanup_and_containment_are_never_synthesized(tmp_path, monkeypatch):
    runtime, lease, adapter, spec, ref, client = started(tmp_path, monkeypatch)
    observed_after = stamp(ref.started_at)
    assert observed_after > 0
    def unavailable(operation, payload):
        assert operation == "status"
        assert payload["cleanup_query"]["observed_after"] == observed_after
        client.calls.append(operation)
        raise BrokerStateError("FABRIC_CLEANUP_UNAVAILABLE")
    monkeypatch.setattr(client, "response", unavailable)
    with pytest.raises(ValueError, match="invalid cleanup observation floor"):
        adapter.fabric_cleanup_receipt(ref, operation="terminal", observed_after=0)
    assert client.calls == ["start"]
    with pytest.raises(BrokerStateError, match="FABRIC_CLEANUP_UNAVAILABLE"):
        adapter.fabric_cleanup_receipt(ref, operation="terminal", observed_after=observed_after)
    with pytest.raises(BrokerStateError, match="FABRIC_CLEANUP_UNAVAILABLE"):
        adapter.fabric_cleanup_receipt_readback(ref, operation="terminal")
    with pytest.raises(BrokerStateError, match="FABRIC_CONTAINMENT_UNAVAILABLE"):
        adapter.terminate(lease.attempt)
    assert adapter.absence_verified(lease.attempt) is False
    assert client.calls == ["start", "status"]


def test_plain_run_status_is_not_cleanup_evidence(tmp_path, monkeypatch):
    runtime, lease, adapter, spec, ref, client = started(tmp_path, monkeypatch)
    with pytest.raises(BrokerProtocolError, match="cleanup response query changed"):
        adapter.fabric_cleanup_receipt(
            ref, operation="terminal", observed_after=stamp(ref.started_at),
        )
    with pytest.raises(BrokerStateError, match="FABRIC_CLEANUP_UNAVAILABLE"):
        adapter.fabric_cleanup_receipt_readback(ref, operation="terminal")
    assert adapter.absence_verified(lease.attempt) is False
    assert client.calls == ["start", "status"]
