"""The canary bridge reads real Runtime claims without lifecycle writes."""
from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from control_plane.executive_runtime import Runtime, WorkerStatus
from control_plane import model_router as router
from control_plane import subscription_canary_admission as admission
from control_plane import codex_provider_realm as realm
from control_plane.executive_worker_broker import PeerCredentials
from control_plane.worker_execution_contract import WorkerLaunchSpec


BINDING = "minimax-token-plan.codex-responses"


@pytest.fixture
def claimed(tmp_path, monkeypatch):
    clock = [1790553600000]
    runtime = Runtime.at(tmp_path / "runtime", clock=lambda: clock[0])
    runtime.workers.register_worker(
        "minimax-01", provider="minimax", account_label="assigned", worker_type="codex-cli",
        quota_classes={"minimax-canary": {
            "capabilities": ["read"], "model": "MiniMax-M3", "metadata": {
                "subscription_canary_realm": {"binding_id": BINDING, "config_sha256": "a" * 64, "generation": 2},
            },
        }},
    )
    job = runtime.jobs.create_job(
        "Read one bounded canary", requested_authorities=["READ"],
        constraints={"provider": "minimax", "required_capabilities": ["read"],
                     "eligible_quota_classes": ["minimax-canary"]},
    )
    lease = runtime.attempts.claim_job(job.job_id, worker_id="minimax-01", quota_class="minimax-canary")
    assert lease is not None
    monkeypatch.setattr(admission, "_claim_now_ms", lambda: clock[0])
    return runtime, lease, clock


def observe(claimed):
    runtime, lease, _ = claimed
    return router.observe_subscription_canary_claim(runtime, attempt_id=lease.attempt.attempt_id, binding_id=BINDING)


def test_real_claim_observation_is_secret_free_and_does_not_write(claimed):
    runtime, lease, _ = claimed
    before = runtime.store.snapshot()
    value = observe(claimed)
    assert value["capacity_state"] == "BUSY"
    assert value["run_id"] == value["held_attempt_id"] == value["current_attempt_id"] == lease.attempt.attempt_id
    assert value["capacity_generation"] == value["fence_generation"] == lease.attempt.fence_generation
    assert value["expires_at_ms"] - value["issued_at_ms"] == 15000
    assert lease.lease_token not in json.dumps(value)
    assert "lease_owner" not in value
    assert runtime.store.snapshot() == before


def test_expired_actual_lease_refuses(claimed):
    _, _, clock = claimed
    clock[0] += 86400 * 1000
    with pytest.raises(router.RoutingPolicyError):
        observe(claimed)


def test_missing_attempt_and_wrong_binding_refuse(claimed):
    runtime, lease, _ = claimed
    with pytest.raises(router.RoutingPolicyError):
        router.observe_subscription_canary_claim(runtime, attempt_id="missing", binding_id=BINDING)
    with pytest.raises(router.RoutingPolicyError):
        router.observe_subscription_canary_claim(runtime, attempt_id=lease.attempt.attempt_id,
                                                binding_id="alibaba-token-plan.claude-code-anthropic")


@pytest.fixture
def broker(claimed, tmp_path, monkeypatch):
    value = observe(claimed)
    local = {key: value[key] for key in ("worker_id", "binding_id", "profile_id", "adapter_id",
                                       "realm_config_sha256", "realm_generation", "catalog_digest")}
    local["control_uid"] = 450
    owner = realm.SubscriptionRealmOwner(tmp_path / "worker.json", "a" * 64, realm._SUBSCRIPTION_REALM_OWNER_SEAL)
    monkeypatch.setattr(realm.SubscriptionRealmOwner, "observe", lambda self: local.copy())
    spec = WorkerLaunchSpec(
        run_id=value["run_id"], job_id=value["job_id"], worker_id=value["worker_id"],
        workspace_path=tmp_path / "work", run_dir=tmp_path / "run", prompt="Read the source.",
        result_schema_path=tmp_path / "schema.json", authorities=("READ",), model=value["model"],
    )
    return value, owner, PeerCredentials(uid=450, gid=450), spec, local


def seal(broker):
    value, owner, peer, spec, _ = broker
    return admission.seal_broker_subscription_canary_admission(value, realm_owner=owner, peer=peer, spec=spec)


def test_broker_seals_only_exact_peer_launch_and_rechecks(broker):
    proof = seal(broker)
    assert proof.observation_digest == broker[0]["observation_digest"]
    assert admission.verify_broker_subscription_canary_admission(proof, spec=broker[3]) is proof
    with pytest.raises(admission.CanaryAdmissionError):
        admission.verify_broker_subscription_canary_admission(broker[0], spec=broker[3])
    with pytest.raises(admission.CanaryAdmissionError):
        admission.verify_broker_subscription_canary_admission(proof, spec=dataclasses.replace(broker[3], prompt="different"))


def test_wrong_peer_or_serialized_peer_refuses(broker):
    value, owner, _, spec, _ = broker
    for peer in (PeerCredentials(uid=501, gid=20), {"uid": 450, "gid": 450}):
        with pytest.raises(admission.CanaryAdmissionError):
            admission.seal_broker_subscription_canary_admission(value, realm_owner=owner, peer=peer, spec=spec)


@pytest.mark.parametrize("field,value", [
    ("run_id", "other"), ("held_attempt_id", "other"), ("capacity_state", "AVAILABLE"),
    ("fence_generation", True), ("realm_generation", 99), ("realm_config_sha256", "b" * 64),
    ("catalog_digest", "b" * 64), ("issued_at_ms", 1790553600001),
    ("expires_at_ms", 1790553620000), ("execution_mode", "autonomous"),
])
def test_even_rehashed_inconsistent_peer_payload_refuses(broker, field, value):
    packet, owner, peer, spec, _ = broker
    packet = dict(packet, **{field: value})
    packet["observation_digest"] = admission._seal_digest({key: item for key, item in packet.items() if key != "observation_digest"})
    with pytest.raises(admission.CanaryAdmissionError):
        admission.seal_broker_subscription_canary_admission(packet, realm_owner=owner, peer=peer, spec=spec)


def test_wire_mutation_cannot_change_already_sealed_launch(broker):
    proof = seal(broker)
    broker[0]["model"] = "other"
    assert proof.model == "MiniMax-M3"
    admission.verify_broker_subscription_canary_admission(proof, spec=broker[3])


def test_local_realm_revocation_and_expiry_refuse(broker, claimed):
    proof = seal(broker)
    broker[4]["realm_generation"] += 1
    with pytest.raises(admission.CanaryAdmissionError):
        admission.verify_broker_subscription_canary_admission(proof, spec=broker[3])
    broker[4]["realm_generation"] -= 1
    claimed[2][0] += 15000
    with pytest.raises(admission.CanaryAdmissionError):
        admission.verify_broker_subscription_canary_admission(proof, spec=broker[3])
