"""Connected child + admitted Runtime capability are both required."""
from dataclasses import asdict, replace
import socket

import pytest

from control_plane import company_consultation_peer_identity as lineage
from control_plane import executive_peer_identity as peer
from control_plane.codex_worker import ProcessIdentity
from control_plane.executive_process_identity import _ProcessInstanceObservation
from control_plane.executive_runtime import (
    ActiveMcpCapabilityBindingFacts, ActiveOperatorBindingFacts, Runtime, StateConflict,
)
from control_plane.operator_harness_contract import CapabilityIdentity, ObservedCapabilityIdentity
from integrations import company_consultation_host_authorization as host


@pytest.fixture
def connected(tmp_path, monkeypatch):
    left, right = socket.socketpair()
    kernel = peer._KernelObservation(b"K" * 32, 451, 200, 20, peer._descriptor_identity(left))
    monkeypatch.setattr(peer, "_observe_socket", lambda _: kernel)
    processes = {
        200: ProcessIdentity("child-start", 100, 100, 451, 451, 451, 451, 100),
        100: ProcessIdentity("parent-start", 100, 100, 451, 451, 451, 451, 50),
    }
    instances = {
        200: _ProcessInstanceObservation(2000, 20, 1000, 10),
        100: _ProcessInstanceObservation(1000, 10, 500, 5),
    }
    class Inspector:
        def inspect(self, pid):
            return processes[pid]
        def boot_session_id(self):
            return "boot"
    monkeypatch.setattr(lineage, "_observe_process_instance", instances.__getitem__)
    capability = CapabilityIdentity(
        name=host.COMPANY_MCP_CONFIG_NAME, kind="mcp_server", harness_binary_digest="a" * 64,
        tool_schema_digest=host.COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
        mcp_server_identity=host.COMPANY_CONSULTATION_SERVER_IDENTITY,
        mcp_server_version=host.COMPANY_CONSULTATION_SERVER_VERSION,
        mcp_auth_status="unsupported",
    )
    raw = asdict(capability)
    raw.pop("harness_binary_digest")
    facts = ActiveMcpCapabilityBindingFacts(
        binding=ActiveOperatorBindingFacts(
            attempt_id="ATT-abc", session_epoch_id="epoch", generation_number=1,
            provider_session_id="provider-session", provider="openai-codex",
            account_label="account", owner_seat="coo", job_id="JOB-001", worker_id="worker",
            process_generation_id="generation", pid=100, pgid=100,
            process_start_identity="parent-start", boot_id="boot",
            admitted_unique_id=1000, admitted_pidversion=10,
        ), requested_capability=capability, observed_capability=ObservedCapabilityIdentity(**raw),
        requested_profile_digest="b" * 64, observed_attestation_digest="c" * 64,
    )
    state = {"facts": facts, "calls": [], "instances": instances, "processes": processes}
    runtime = Runtime.at(tmp_path / "runtime")
    def project(_self, pid, **kwargs):
        state["calls"].append((pid, kwargs))
        return state["facts"]
    monkeypatch.setattr(Runtime, "current_harness_mcp_binding_for_parent_pid", project)
    state["args"] = dict(runtime=runtime, peer=peer.capture_peer_identity(left),
                         worker_uid=451, inspector=Inspector())
    try:
        yield state
    finally:
        left.close()
        right.close()


def test_authority_uses_fixed_host_grant_and_fresh_projection(connected):
    authority = host.CompanyCallerAuthority(**connected["args"])
    assert authority.revalidate() == connected["facts"]
    assert len(connected["calls"]) == 4
    assert all(pid == 100 and kwargs == dict(
        config_name=host.COMPANY_MCP_CONFIG_NAME,
        server_identity=host.COMPANY_CONSULTATION_SERVER_IDENTITY,
        server_version=host.COMPANY_CONSULTATION_SERVER_VERSION,
        tool_schema_digest=host.COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
        auth_status="unsupported",
    ) for pid, kwargs in connected["calls"])


def test_wrong_uid_refuses_before_runtime_lookup(connected):
    with pytest.raises(StateConflict):
        host.CompanyCallerAuthority(**(connected["args"] | {"worker_uid": 452}))
    assert connected["calls"] == []


def test_fabricated_peer_cannot_supply_even_matching_uid(connected):
    fake = object.__new__(peer.PeerIdentity)
    with pytest.raises(peer.PeerIdentityError, match="PROVENANCE"):
        host.CompanyCallerAuthority(**(connected["args"] | {"peer": fake}))
    assert connected["calls"] == []


@pytest.mark.parametrize("field,value", [
    ("attempt_id", "ATT-new"), ("session_epoch_id", "new-epoch"),
    ("generation_number", 2), ("provider_session_id", "new-session"),
    ("job_id", "JOB-002"), ("worker_id", "new-worker"),
    ("process_generation_id", "new-generation"),
])
def test_runtime_rotation_after_capture_never_rebinds_request(connected, field, value):
    authority = host.CompanyCallerAuthority(**connected["args"])
    connected["facts"] = replace(connected["facts"], binding=replace(
        connected["facts"].binding, **{field: value}))
    with pytest.raises(StateConflict, match="authority changed"):
        authority.revalidate()


@pytest.mark.parametrize("field", ["requested_profile_digest", "observed_attestation_digest"])
def test_capability_rotation_after_capture_refuses(connected, field):
    authority = host.CompanyCallerAuthority(**connected["args"])
    connected["facts"] = replace(connected["facts"], **{field: "d" * 64})
    with pytest.raises(StateConflict, match="authority changed"):
        authority.revalidate()


def test_exec_before_new_child_is_not_readmitted(connected):
    authority = host.CompanyCallerAuthority(**connected["args"])
    connected["instances"][100] = replace(connected["instances"][100], pidversion=11)
    connected["instances"][200] = replace(connected["instances"][200], parent_pidversion=11)
    with pytest.raises(peer.PeerIdentityError, match="MISMATCH"):
        authority.revalidate()


def test_missing_admitted_instance_pair_refuses(connected):
    connected["facts"] = replace(connected["facts"], binding=replace(
        connected["facts"].binding, admitted_unique_id=None, admitted_pidversion=None))
    with pytest.raises(peer.PeerIdentityError, match="IDENTITY_REQUIRED"):
        host.CompanyCallerAuthority(**connected["args"])


def test_rotation_between_runtime_and_kernel_reads_refuses(connected, monkeypatch):
    original = Runtime.current_harness_mcp_binding_for_parent_pid
    def rotating(self, pid, **kwargs):
        result = original(self, pid, **kwargs)
        connected["facts"] = replace(result, requested_profile_digest="e" * 64)
        return result
    monkeypatch.setattr(Runtime, "current_harness_mcp_binding_for_parent_pid", rotating)
    with pytest.raises(StateConflict, match="writer or capability changed"):
        host.CompanyCallerAuthority(**connected["args"])


def test_closed_request_cannot_be_reused(connected):
    authority = host.CompanyCallerAuthority(**connected["args"])
    calls = len(connected["calls"])
    authority.close()
    authority.close()
    with pytest.raises(StateConflict, match="closed"):
        authority.revalidate()
    assert len(connected["calls"]) == calls


@pytest.mark.parametrize("uid", [0, -1, True, "451", None])
def test_invalid_installed_uid_refuses(connected, uid):
    with pytest.raises(ValueError):
        host.CompanyCallerAuthority(**(connected["args"] | {"worker_uid": uid}))
    assert connected["calls"] == []
