"""Existing-parent enrollment: canonical SQLite, mocked host boundary only.

These tests do not attest a real Desktop host. Removing a validation or the
transactional writer check must admit the corresponding rejected case.
"""
from contextlib import contextmanager
from dataclasses import replace
import importlib
import json
import os
from types import SimpleNamespace

import pytest
from control_plane.executive_runtime import StateConflict
from control_plane.operator_harness_contract import OperationId, ProcessIdentityObservation
from test_ohf_p1b_runtime import _lease, _profile, _attestation
from control_plane.executive_runtime import Runtime
from control_plane.ceo_intent import INTENT_SCHEMA_V2, submit_intent
from control_plane.executive_orchestration_principal import OperatorPrincipalObservation

ROOT = "01a11e90-4b5d-7f53-b966-8aaaad38701f"
TURN = "01a129f5-53f9-7110-88ec-90ef1e94d680"


def setup_enrollment(tmp_path, monkeypatch):
    module = importlib.import_module("control_plane.native_desktop_parent")
    # Real canonical grant machinery in a fixture only: no live parent is created.
    runtime = Runtime.at(tmp_path)
    runtime.workers.register_worker("worker-a", provider="codex", account_label="worker-a@company",
        worker_type="mock", capabilities=["read", "research"], quota_classes={"default": {
            "provider": "codex", "capabilities": ["read", "research"], "cost_class": "small"}})
    receipt = submit_intent(runtime, {"schema": INTENT_SCHEMA_V2, "intent_id": "CEO-DESKTOP-FIXTURE",
        "actor": "ceo-sol", "objective": "Existing parent enrollment source fixture",
        "department": "executive-infrastructure", "priority": 9,
        "grounding": {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40},
        "execution_contract": {"requested_authorities": ["READ"], "attempt_limit": 2},
        "intent_kind": "executive_coo_cycle", "business_impact": "material"})
    root = runtime.jobs.get_job(receipt["job_id"])
    planner = runtime.jobs.create_cycle_planner(root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0")
    lease = runtime.attempts.dispatch_cycle_job(planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1", worker_id="worker-a")
    profile = _profile(lease)
    runtime.operator_harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token, requested=profile)
    with runtime.store.read() as connection:
        row = connection.execute("SELECT * FROM attempts WHERE attempt_id=?",
                                 (lease.attempt.attempt_id,)).fetchone()
        job = connection.execute("SELECT * FROM jobs WHERE job_id=?", (row["job_id"],)).fetchone()
        snapshot = module.DesktopParentObservation(
            root_thread_id=ROOT, thread_id=ROOT, turn_id=TURN,
            thread_status="active", turn_status="inProgress", parent_thread_id=None,
            forked_from_id=None, can_accept_direct_input=True,
            process=ProcessIdentityObservation(2101, 2101, "desktop-start", "boot"),
            root_job_id=job["root_job_id"], attempt_id=row["attempt_id"],
            worker_id=row["worker_id"], requested_profile_digest=row["requested_execution_profile_digest"],
            authority_policy_hash=row["authority_policy_hash"],
            effective_grant_digest=row["effective_grant_digest"],
            placement_snapshot_digest=row["placement_snapshot_digest"])
    state = {"observation": snapshot, "held": False, "captures": 0}
    connection_instance = object()
    def authenticate(peer, binding):
        state["captures"] += 1
        return SimpleNamespace(real_boot_id="boot", audit_identity_digest="a" * 64,
            service_label="desktop-host", installed_release="b" * 40,
            config_digest="c" * 64, connection_instance=connection_instance)
    monkeypatch.setattr(module, "require_installed_service_peer", authenticate)
    @contextmanager
    def writer_fence():
        assert not state["held"]
        state["held"] = True
        try: yield
        finally:
            state["held"] = False
            if state.pop("lose_response_once", False):
                raise OSError("fixture response lost after transaction commit")
    def observe():
        assert state["held"]
        return state["observation"]
    owner = module._bind_desktop_parent_owner(peer=object(), installed_binding=object(),
                                             writer_fence=writer_fence, observe=observe)
    def enroll(op="ohf-op:desktop-parent:first", **overrides):
        kwargs = dict(attempt_id=lease.attempt.attempt_id,
                      fence_generation=lease.attempt.fence_generation,
                      lease_token=lease.lease_token, operation_id=OperationId(op),
                      expected_root_thread_id=ROOT, expected_turn_id=TURN, owner=owner)
        kwargs.update(overrides)
        return runtime.operator_harness.enroll_existing_desktop_parent(**kwargs)
    return module, runtime, lease, profile, state, owner, enroll


def counts(runtime):
    with runtime.store.read() as connection:
        return tuple(connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                     for table in ("jobs", "attempts", "events", "harness_session_epochs", "process_generations"))


def test_enrollment_preserves_original_identity_without_start_or_new_job(tmp_path, monkeypatch):
    module, runtime, lease, profile, state, owner, enroll = setup_enrollment(tmp_path, monkeypatch)
    before = counts(runtime)
    epoch, generation = enroll()
    after = counts(runtime)
    assert after[:2] == before[:2]
    assert after[3:] == (1, 1)
    with runtime.store.read() as connection:
        e = connection.execute("SELECT * FROM harness_session_epochs").fetchone()
        g = connection.execute("SELECT * FROM process_generations").fetchone()
        events = [json.loads(r[0]) for r in connection.execute(
            "SELECT payload_json FROM events WHERE aggregate_type='operator_operation'")]
    assert e["provider_session_id"] == ROOT
    assert g["pid"] == 2101 and g["process_start_identity"] == "desktop-start"
    assert g["executive_writer_held"] == 1
    assert {e["operation_kind"] for e in events} == {"enroll_existing_desktop_parent"}
    assert not state["held"]
    assert state["captures"] >= 2
    assert enroll() == (epoch, generation)
    assert counts(runtime) == after


@pytest.mark.parametrize("changes", [
    {"thread_id": "01a00000-0000-7000-8000-000000000001"},
    {"root_thread_id": "01a00000-0000-7000-8000-000000000001"},
    {"turn_id": "stale-turn"}, {"thread_status": "notLoaded"},
    {"turn_status": "completed"}, {"can_accept_direct_input": None}, {"can_accept_direct_input": False},
    {"parent_thread_id": ROOT}, {"forked_from_id": ROOT},
    {"attempt_id": "different-attempt"}, {"worker_id": "different-worker"},
    {"root_job_id": "different-root"}, {"requested_profile_digest": "f" * 64},
    {"authority_policy_hash": "f" * 64},
    {"effective_grant_digest": "f" * 64}, {"placement_snapshot_digest": "f" * 64},
    {"process": ProcessIdentityObservation(True, 2101, "desktop-start", "boot")},
    {"process": ProcessIdentityObservation(2101, 2101, "desktop-start", "another-boot")},
    {"process": ProcessIdentityObservation(0, 2101, "desktop-start", "boot")},
])
def test_bad_host_or_grant_has_no_runtime_mutation(tmp_path, monkeypatch, changes):
    _, runtime, _, _, state, _, enroll = setup_enrollment(tmp_path, monkeypatch)
    state["observation"] = replace(state["observation"], **changes)
    before = counts(runtime)
    with pytest.raises(StateConflict): enroll()
    assert counts(runtime) == before


def test_caller_cannot_supply_a_dict_as_host_authority(tmp_path, monkeypatch):
    _, runtime, _, _, _, _, enroll = setup_enrollment(tmp_path, monkeypatch)
    before = counts(runtime)
    with pytest.raises(StateConflict): enroll(owner={"authenticated": True, "root": ROOT})
    assert counts(runtime) == before


def test_wrong_attempt_lease_has_no_mutation(tmp_path, monkeypatch):
    _, runtime, _, _, _, _, enroll = setup_enrollment(tmp_path, monkeypatch)
    before = counts(runtime)
    with pytest.raises(StateConflict): enroll(lease_token="wrong-token")
    assert counts(runtime) == before


def test_new_operation_cannot_reenroll_bound_session(tmp_path, monkeypatch):
    _, runtime, _, _, _, _, enroll = setup_enrollment(tmp_path, monkeypatch)
    enroll()
    before = counts(runtime)
    with pytest.raises(StateConflict): enroll(op="ohf-op:desktop-parent:replacement")
    assert counts(runtime) == before


def test_host_turn_changes_before_commit_roll_back_entire_enrollment(tmp_path, monkeypatch):
    module, runtime, _, _, state, owner, enroll = setup_enrollment(tmp_path, monkeypatch)
    original = runtime.store.append_event
    def append(*args, **kwargs):
        result = original(*args, **kwargs)
        if kwargs.get("aggregate_type") == "operator_operation":
            state["observation"] = replace(state["observation"], turn_id="changed-turn")
        return result
    monkeypatch.setattr(runtime.store, "append_event", append)
    before = counts(runtime)
    with pytest.raises(StateConflict): enroll()
    assert counts(runtime) == before


def test_disconnected_authenticated_host_has_no_mutation(tmp_path, monkeypatch):
    module, runtime, _, _, state, owner, enroll = setup_enrollment(tmp_path, monkeypatch)
    def refused(*args):
        raise module.PeerIdentityError("PEER_CONNECTION_CLOSED")
    monkeypatch.setattr(module, "require_installed_service_peer", refused)
    before = counts(runtime)
    with pytest.raises(StateConflict): enroll()
    assert counts(runtime) == before


@pytest.mark.parametrize("kind", ["graceful_stop", "cancel", "resume", "turn"])
def test_existing_parent_cannot_be_controlled_as_launched_worker(tmp_path, monkeypatch, kind):
    _, runtime, lease, _, _, _, enroll = setup_enrollment(tmp_path, monkeypatch)
    epoch, generation = enroll()
    auth = dict(fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token)
    before = counts(runtime)
    with pytest.raises(StateConflict, match="Desktop parent lifecycle"):
        if kind == "resume":
            runtime.operator_harness.reserve_same_epoch_resume(epoch=epoch, old_generation=generation,
                operation_id=OperationId("ohf-op:forbidden-resume"), **auth)
        elif kind == "turn":
            runtime.operator_harness.reserve_turn(epoch=epoch, generation=generation,
                operation_id=OperationId("ohf-op:forbidden-turn"), **auth)
        else:
            runtime.operator_harness.reserve_generation_operation(generation=generation,
                operation_id=OperationId("ohf-op:forbidden-control"), operation_kind=kind, **auth)
    assert counts(runtime) == before


def test_tampered_applied_receipt_cannot_replay(tmp_path, monkeypatch):
    _, runtime, _, _, _, _, enroll = setup_enrollment(tmp_path, monkeypatch)
    enroll()
    with runtime.store.transaction() as connection:
        # Corrupted-database fixture; production immutable-event triggers are unchanged.
        connection.execute("DROP TRIGGER events_are_immutable_update")
        changed = connection.execute("UPDATE events SET payload_json='{}' WHERE event_type='OPERATOR_OPERATION_APPLIED' "
                           "AND aggregate_type='operator_operation'")
        assert changed.rowcount == 1
    before = counts(runtime)
    with pytest.raises(StateConflict): enroll()
    assert counts(runtime) == before


def test_unregistered_opaque_owner_is_not_authority(tmp_path, monkeypatch):
    module, runtime, _, _, _, _, enroll = setup_enrollment(tmp_path, monkeypatch)
    forged = object.__new__(module._DesktopParentOwner)
    before = counts(runtime)
    with pytest.raises(StateConflict): enroll(owner=forged)
    assert counts(runtime) == before



def seal_parent_attestation(runtime, lease, profile, generation):
    principal = OperatorPrincipalObservation(
        attempt_id=lease.attempt.attempt_id, worker_id=lease.attempt.worker_id,
        process_generation_id=generation.process_generation_id, provider_session_id=ROOT,
        process_identity={"pid":2101,"pgid":2101,"process_start_identity":"desktop-start","boot_id":"boot"},
        os_principal_name="fixture-principal", os_principal_uid=os.getuid(),
        provider_home_identity={"path":"/tmp/desktop-fixture-home","device":1,"inode":2,
            "uid":os.getuid(),"gid":os.getgid(),"mode":0o700}, observed_at_ms=runtime.store.now_ms())
    runtime.operator_harness.seal_attestation(generation=generation,
        fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
        requested=profile, attestation=_attestation(profile), principal_observation=principal)


def test_canonical_binding_accepts_enrollment_only_after_attestation(tmp_path, monkeypatch):
    _, runtime, lease, profile, _, _, enroll = setup_enrollment(tmp_path, monkeypatch)
    epoch, generation = enroll()
    with pytest.raises(StateConflict):
        runtime.current_harness_binding_source(lease.attempt.attempt_id)
    seal_parent_attestation(runtime, lease, profile, generation)
    binding = runtime.current_harness_binding_source(lease.attempt.attempt_id)
    assert binding.provider_session_id == ROOT
    assert binding.process_generation_id == generation.process_generation_id
    assert binding.pid == 2101
    with runtime.store.read() as connection:
        events = [json.loads(r[0]) for r in connection.execute(
            "SELECT payload_json FROM events WHERE aggregate_type='operator_operation'")]
    assert {r["operation_kind"] for r in events} == {"enroll_existing_desktop_parent"}



def test_lost_response_recovers_same_enrollment_without_second_write(tmp_path, monkeypatch):
    _, runtime, lease, _, state, _, enroll = setup_enrollment(tmp_path, monkeypatch)
    # The owner context raises after the inner SQLite transaction has committed.
    state["lose_response_once"] = True
    with pytest.raises(OSError, match="response lost"):
        enroll()
    committed = counts(runtime)
    assert committed[3:] == (1, 1)
    epoch, generation = enroll()
    assert epoch.attempt_id == lease.attempt.attempt_id
    assert counts(runtime) == committed


@pytest.mark.parametrize("field,value", [("turn_id","new-turn"),
    ("process", ProcessIdentityObservation(2102,2102,"new-process","boot"))])
def test_host_changes_during_transaction_roll_back(tmp_path, monkeypatch, field, value):
    _, runtime, _, _, state, _, enroll = setup_enrollment(tmp_path, monkeypatch)
    original = runtime.store.append_event
    def append(*args, **kwargs):
        result = original(*args, **kwargs)
        if kwargs.get("aggregate_type") == "operator_operation":
            state["observation"] = replace(state["observation"], **{field:value})
        return result
    monkeypatch.setattr(runtime.store,"append_event",append)
    before=counts(runtime)
    with pytest.raises(StateConflict): enroll()
    assert counts(runtime)==before


def test_peer_changes_during_transaction_roll_back(tmp_path, monkeypatch):
    module, runtime, _, _, state, _, enroll = setup_enrollment(tmp_path, monkeypatch)
    original_auth = module.require_installed_service_peer
    original_append = runtime.store.append_event
    def authenticate(*args):
        peer = original_auth(*args)
        if state.get("drift"): peer.config_digest = "f"*64
        return peer
    def append(*args, **kwargs):
        value = original_append(*args, **kwargs)
        if kwargs.get("aggregate_type") == "operator_operation": state["drift"] = True
        return value
    monkeypatch.setattr(module, "require_installed_service_peer", authenticate)
    monkeypatch.setattr(runtime.store, "append_event", append)
    before=counts(runtime)
    with pytest.raises(StateConflict): enroll()
    assert counts(runtime)==before


@pytest.mark.parametrize("target", ["receipt", "grant", "principal"])
def test_binding_refuses_corrupt_canonical_evidence(tmp_path, monkeypatch, target):
    _, runtime, lease, profile, _, _, enroll = setup_enrollment(tmp_path, monkeypatch)
    _, generation = enroll()
    seal_parent_attestation(runtime, lease, profile, generation)
    with runtime.store.transaction() as connection:
        if target == "receipt":
            connection.execute("DROP TRIGGER events_are_immutable_update")
            changed=connection.execute("UPDATE events SET actor='forged-owner' "
                "WHERE event_type='OPERATOR_OPERATION_APPLIED'")
        else:
            connection.execute("DROP TRIGGER attempts_orchestration_pairs_immutable")
            column = "effective_grant_digest" if target == "grant" else "execution_principal_snapshot_digest"
            changed=connection.execute("UPDATE attempts SET " + column + "=? WHERE attempt_id=?",
                ("f"*64,lease.attempt.attempt_id))
        assert changed.rowcount == 1
    with pytest.raises(StateConflict): runtime.current_harness_binding_source(lease.attempt.attempt_id)


def test_lease_expiring_during_host_revalidation_rolls_back(tmp_path, monkeypatch):
    _, runtime, lease, _, _, _, enroll = setup_enrollment(tmp_path, monkeypatch)
    with runtime.store.read() as connection:
        expiry = connection.execute('SELECT lease_expires_at_ms FROM attempts WHERE attempt_id=?',
            (lease.attempt.attempt_id,)).fetchone()[0]
    original_append = runtime.store.append_event
    def append(*args, **kwargs):
        result = original_append(*args, **kwargs)
        if kwargs.get('aggregate_type') == 'operator_operation':
            monkeypatch.setattr(runtime.store, 'now_ms', lambda: expiry + 1)
        return result
    monkeypatch.setattr(runtime.store, 'append_event', append)
    before=counts(runtime)
    with pytest.raises(StateConflict): enroll()
    assert counts(runtime)==before
