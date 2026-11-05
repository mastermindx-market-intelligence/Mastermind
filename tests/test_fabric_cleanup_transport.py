"""Inert original-owner storage and real Runtime fence; no host attestation."""
import asyncio
import copy
import dataclasses
import hashlib
import json
import time

import pytest

from control_plane import fabric_cleanup_transport as transport
from control_plane.executive_worker_broker import BrokerStateError
from test_executive_fabric_adapter import _fixture, result, physical
import test_executive_fabric_bridge_broker as bridge_fixture
from test_fabric_cleanup_contract import example, _canonical


@pytest.fixture
def bound(tmp_path, monkeypatch, example):
    class Owner:
        calls = None
        query_damage = None
        package_damage = None
        state = "SUCCEEDED"
        fail_readback = False
        def __init__(self):
            self.calls = []
            self.reads = 0
        async def execute(self, operation, query):
            assert operation == "status"
            self.calls.append(copy.deepcopy(query))
            common = dict(adapter_id="attended-fabric", binding=p["binding"],
                          physical_binding_sha256=physical().digest)
            if "cleanup_query" not in query:
                return dict(common, run=dict(run_id=ref.run_id, status=self.state,
                                             process_ref=dataclasses.asdict(ref)))
            selected = query["cleanup_query"]
            if self.fail_readback and selected["readback_sha256"] is not None:
                raise RuntimeError("inert original owner readback unavailable")
            # Two actual storage reads, not the requested digest echoed as proof.
            self.reads += 1
            package = json.loads(path.read_text())
            if self.package_damage:
                self.package_damage(package, self.reads)
            sha = transport.digest(selected)
            return dict(common, cleanup=package,
                        cleanup_query_sha256="0" * 64 if self.query_damage else sha)

    owner = Owner()
    service = bridge_fixture.broker(tmp_path, monkeypatch, owner)
    class Client:
        async def request(self, operation, payload, **_kwargs):
            if operation == "start":
                started = result(payload)
                started["process_ref"]["run_id"] = payload["binding"]["attempt_id"]
                return started
            response = await service.execute(bridge_fixture.envelope(operation, payload),
                peer=bridge_fixture.PeerCredentials(uid=450, gid=450))
            return response["result"]
    runtime, job, lease, adapter, spec, p = _fixture(tmp_path, monkeypatch, Client())
    ref = asyncio.run(adapter.start(spec, lease=lease))
    lane = json.loads(example["lane_receipt_bytes"])
    lane.update(pid=ref.pid, pgid=ref.pgid, started_at=ref.started_at)
    raw = _canonical(lane) + b"\n"
    receipt = example["receipt"]
    receipt.update(binding=p["binding"], physical_binding_sha256=physical().digest,
        process_identity={**{key:getattr(ref,key) for key in
            ("pid","pgid","session_id","boot_session_id","process_start_identity")},
            "host_ref":physical().host_ref}, lane_started_at=ref.started_at,
        lane_receipt_sha256=hashlib.sha256(_canonical(lane)).hexdigest(),
        lane_receipt_bytes_sha256=hashlib.sha256(raw).hexdigest())
    package = dict(schema_version="mastermind.executive_fabric_cleanup_evidence/v1",
        operation="terminal", observed_at="2026-10-11T10:01:00Z", worker_uid=1001,
        worker_gid=1001, receipt=receipt, lane_receipt_utf8=raw.decode())
    path = tmp_path / "original-cleanup.json"
    path.write_text(json.dumps(package))
    return runtime, lease, adapter, ref, owner, path, service


def prime(bound, scope="terminal"):
    _, _, adapter, ref, _, _, _ = bound
    return asyncio.run(adapter.prepare_fabric_cleanup(ref, operation=scope,
        observed_after=transport.stamp(ref.started_at)))


def test_two_original_reads_feed_sync_readers_without_revocation(bound):
    _, _, adapter, ref, owner, path, _ = bound
    prime(bound)
    package = adapter.fabric_cleanup_receipt(ref, operation="terminal",
        observed_after=transport.stamp(ref.started_at))
    assert owner.reads == 2
    assert package == adapter.fabric_cleanup_receipt_readback(ref, operation="terminal")
    assert package == json.loads(path.read_text())
    package["receipt"]["cleanup_verified"] = False
    assert adapter.fabric_cleanup_receipt_readback(ref, operation="terminal")["receipt"]["cleanup_verified"] is True
    assert not adapter.absence_verified(bound[0].attempts.get_attempt(ref.run_id))
    assert all("sweep" not in str(call) and "seal" not in str(call) for call in owner.calls)


@pytest.mark.parametrize("damage", [
    lambda p,n: p["receipt"]["binding"].update(root_id="foreign"),
    lambda p,n: p["receipt"]["binding"].update(effective_grant_digest="0"*64),
    lambda p,n: p["receipt"]["process_identity"].update(boot_session_id="new-boot"),
    lambda p,n: p.update(worker_uid=501),
    lambda p,n: p.update(operation="validation"),
    lambda p,n: p.update(observed_at="2026-10-11T09:00:00Z"),
    lambda p,n: p.update(observed_at="2099-01-01T00:00:00Z"),
    lambda p,n: p["receipt"].update(uncertainty="EFFECT_UNKNOWN"),
    lambda p,n: p.update(lane_receipt_utf8=p["lane_receipt_utf8"]+" "),
    lambda p,n: p.update(extra=True),
])
def test_foreign_incomplete_or_uncertain_evidence_never_enters_cache(bound, damage):
    bound[4].package_damage = damage
    with pytest.raises(Exception): prime(bound)
    assert bound[2]._cleanup_pairs == {}


def test_independent_readback_failure_does_not_publish_first_read(bound):
    bound[4].fail_readback = True
    with pytest.raises(Exception): prime(bound)
    assert bound[4].reads == 1
    assert bound[2]._cleanup_pairs == {}


def test_restamped_second_record_is_not_an_independent_same_record_readback(bound):
    bound[4].package_damage = lambda p,n: p.update(observed_at="2026-10-11T10:02:00Z") if n == 2 else None
    with pytest.raises(Exception): prime(bound)
    assert bound[4].reads == 2
    assert bound[2]._cleanup_pairs == {}


@pytest.mark.parametrize("state", ["RUNNING", "STARTING", "CANCELLING"])
def test_live_status_cannot_supply_terminal_cleanup(bound, state):
    bound[4].state = state
    with pytest.raises(Exception): prime(bound)
    assert bound[4].reads == 0


def test_query_echo_mismatch_refuses(bound):
    bound[4].query_damage = True
    with pytest.raises(Exception): prime(bound)
    assert bound[2]._cleanup_pairs == {}


def test_missing_async_prime_does_not_block_loop_or_synthesize_readback(bound):
    async def check():
        with pytest.raises(BrokerStateError, match="not primed"):
            bound[2].fabric_cleanup_receipt(bound[3], operation="terminal",
                observed_after=transport.stamp(bound[3].started_at))
    asyncio.run(check())
    assert bound[4].reads == 0


def test_restart_observation_cannot_reuse_old_record(bound):
    prime(bound)
    with pytest.raises(Exception):
        bound[2].fabric_cleanup_receipt(bound[3], operation="restart_absence", observed_after=time.time())
    assert (bound[3].run_id, "restart_absence") not in bound[2]._cleanup_pairs


def test_lease_loss_between_reads_cannot_publish_cleanup(bound, monkeypatch):
    runtime, lease, adapter, ref, owner, _, _ = bound
    original = owner.execute
    async def moved(operation, payload):
        result = await original(operation, payload)
        if "cleanup_query" in payload:
            monkeypatch.setattr(adapter, "_validate_lease", lambda _: (_ for _ in ()).throw(BrokerStateError("lease moved")))
        return result
    owner.execute = moved
    with pytest.raises(BrokerStateError, match="lease moved"): prime(bound)
    assert owner.reads == 1
    assert adapter._cleanup_pairs == {}


def test_new_validation_evicts_cached_terminal_even_if_request_fails(bound):
    prime(bound)
    async def failed():
        with pytest.raises(Exception):
            await bound[2]._request(bound[3], "validate", argv=["not-allowed"], timeout_seconds=1)
    asyncio.run(failed())
    assert bound[2]._cleanup_pairs == {}


def test_wrong_peer_cannot_retrieve_cleanup(bound):
    query = bound[2]._cleanup_query(bound[3], "terminal", transport.stamp(bound[3].started_at))
    request = bridge_fixture.envelope("status", dict(binding=bound[2]._known(bound[3])[1]["binding"],
        physical_binding_sha256=physical().digest, run_id=bound[3].run_id, cleanup_query=query))
    with pytest.raises(Exception, match="PeerAuthorizationError"):
        bridge_fixture.execute(bound[6], request, uid=501)
    assert bound[4].calls == []


def test_supervisor_primes_inside_event_loop_without_synchronous_transport(bound, tmp_path):
    from types import SimpleNamespace
    from control_plane.executive_supervisor import ExecutiveSupervisor, CleanupPolicy
    runtime, lease, adapter, ref, owner, _, _ = bound
    supervisor = ExecutiveSupervisor(runtime, adapter, runs_root=tmp_path / "runs",
        require_complete_launch_attestation=True, cleanup_policy=CleanupPolicy.FABRIC_PROCESS_GROUP)
    active = SimpleNamespace(lease=lease, process_ref=ref)
    async def check():
        await supervisor._prepare_fabric_cleanup(active, operation="terminal")
        assert adapter.fabric_cleanup_receipt(ref, operation="terminal",
            observed_after=transport.stamp(ref.started_at))["operation"] == "terminal"
    asyncio.run(check())
    assert owner.reads == 2
