"""Real Runtime validator with explicitly synthetic remote owner observations."""
import copy
import dataclasses
import datetime as dt
import hashlib
import json
from pathlib import Path

import pytest

from control_plane.broker_assignment_seal import digest
from control_plane.executive_runtime import (
    REMOTE_LAUNCH_IDENTITY_KEY, REMOTE_LAUNCH_IDENTITY_SCHEMA, StateConflict,
    _dialogue_source_from_root_creation, _sealed_worker_result_payload,
)


def fabric_fixture(tmp_path):
    from tests.test_executive_terminal_return import completed_sealed_worker_fixture
    from tests.test_fabric_cleanup_contract import example, _canonical
    from tests.test_executive_fabric_adapter import physical
    from control_plane.worker_execution_contract import WorkerRecoveryBinding
    runtime, row, terminal, original_spec, original_ref = completed_sealed_worker_fixture(
        tmp_path, include_launch=True, with_commission=True)
    terminal = copy.deepcopy(terminal)
    metadata = json.loads(row["launch_metadata_json"])
    prompt_path = Path(original_spec.run_dir) / "input" / "worker-prompt.txt"
    metadata["worker_recovery_binding"] = WorkerRecoveryBinding.bind(
        adapter_id="attended-fabric", spec=original_spec, process_ref=original_ref,
        prompt_path=prompt_path).to_dict()
    recovery = metadata["worker_recovery_binding"]
    recovery["adapter_id"] = "attended-fabric"
    spec = recovery["launch_spec"]["fields"]
    ref = recovery["process_ref"]
    evidence = terminal["result_evidence"]
    assignment = evidence["assignment_seal_receipt"]
    control_uid = ref["effective_uid"] + 1
    assignment["control_uid"] = control_uid
    for label, boundary in assignment["paths"].items():
        boundary["before"]["uid"] = boundary["after"]["uid"] = control_uid
        for entry in spec["isolation_manifest"]["entries"]:
            if entry["disposition"] == "CURRENT_" + label.upper():
                entry["identity"] = copy.deepcopy(boundary["before"])
    spec["isolation_manifest_sha256"] = digest(spec["isolation_manifest"])
    attestation = metadata["launch_attestation"]
    attestation["workspace_identity"]["uid"] = control_uid
    attestation["isolation_manifest_sha256"] = spec["isolation_manifest_sha256"]
    metadata["launch_attestation_sha256"] = digest(attestation)
    recovery["launch_spec_sha256"] = digest({**spec,
        "prompt_sha256": recovery["launch_spec"]["prompt_sha256"]})
    with runtime.store.read() as con:
        root_id = con.execute("SELECT root_job_id FROM jobs WHERE job_id=?", (row["job_id"],)).fetchone()[0]
        source = _dialogue_source_from_root_creation(con, root_job_id=root_id)
    binding = {"root_id": root_id, "job_id": row["job_id"], "attempt_id": row["attempt_id"],
        "effective_grant_digest": row["effective_grant_digest"],
        "commission_sha256": source.commission_ref.content_sha256}
    route = dataclasses.replace(physical(), worker_id=row["worker_id"],
        worker_uid=ref["effective_uid"], worker_gid=ref["effective_gid"])
    request_spec = copy.deepcopy(spec)
    request_spec["prompt"] = Path(recovery["launch_spec"]["prompt_path"]).read_text()
    if not request_spec.get("subscription_canary_claim"):
        request_spec.pop("subscription_canary_claim", None)
    launch = {"physical_binding_sha256": route.digest, "request": {
        "binding": binding, "physical_binding_sha256": route.digest,
        "launch_spec": request_spec, "validation_commands": metadata["validation_argv"]}}
    metadata[REMOTE_LAUNCH_IDENTITY_KEY] = {"schema_version": REMOTE_LAUNCH_IDENTITY_SCHEMA,
                                         "sha256": digest(launch)}
    row["launch_metadata_json"] = json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    sample = example.__wrapped__()
    lane = json.loads(sample["lane_receipt_bytes"])
    started = dt.datetime.fromisoformat(ref["started_at"].replace("Z", "+00:00"))
    ended = (started + dt.timedelta(seconds=1)).isoformat()
    observed = (started + dt.timedelta(seconds=2)).isoformat()
    lane.update(label=row["attempt_id"], pid=ref["pid"], pgid=ref["pgid"],
                started_at=ref["started_at"], ended_at=ended)
    raw = _canonical(lane) + b"\n"
    group = sample["receipt"]
    group.update(binding=binding, physical_binding_sha256=route.digest,
        process_identity={"host_ref": route.host_ref, "boot_session_id": ref["boot_session_id"],
            "pid": ref["pid"], "pgid": ref["pgid"], "session_id": ref["session_id"],
            "process_start_identity": ref["process_start_identity"]},
        lane_started_at=ref["started_at"], lane_receipt_sha256=hashlib.sha256(_canonical(lane)).hexdigest(),
        lane_receipt_bytes_sha256=hashlib.sha256(raw).hexdigest())
    for name, operation in (("collection_receipt", "collection"), ("validation_receipts", "validation")):
        receipt = evidence[name]
        receipt.pop("uid_sweep")
        receipt["fabric_cleanup"] = {"schema_version": "mastermind.executive_fabric_cleanup_evidence/v1",
            "operation": operation, "observed_at": observed,
            "worker_uid": ref["effective_uid"], "worker_gid": ref["effective_gid"],
            "receipt": copy.deepcopy(group), "lane_receipt_utf8": raw.decode()}
        evidence[name + "_digest"] = digest(receipt)
    snapshot = {"schema_version": "mastermind.worker_assignment_seal_prepare/v1",
        "run_id": row["attempt_id"], "job_id": row["job_id"], "worker_id": row["worker_id"],
        "effective_grant_digest": row["effective_grant_digest"], "process_ref": ref,
        "paths": {k: copy.deepcopy(v["before"]) for k, v in assignment["paths"].items()},
        "uid_sweep": copy.deepcopy(assignment["uid_sweep"])}
    observation = {"schema_version": "mastermind.worker_assignment_seal_commit/v1",
        "snapshot": snapshot, "snapshot_sha256": digest(snapshot),
        "control_seal": {k: v for k, v in assignment.items() if k not in {
            "attempt_id", "job_id", "uid_sweep", "effective_grant_digest"}},
        "worker_denial": {k: {"open": "EACCES", "traverse": "EACCES", "list": "EACCES"}
                          for k in ("workspace", "run")}}
    evidence.update(schema_version="mastermind.fabric_sealed_worker_result_evidence/v1",
        launch_identity=launch, physical_binding=dataclasses.asdict(route),
        remote_assignment_observation=observation,
        remote_assignment_observation_digest=digest(observation),
        assignment_seal_receipt_digest=digest(assignment))
    terminal["validation_receipt_digest"] = evidence["validation_receipts_digest"]
    terminal["terminal_evidence_digest"] = digest({k: v for k, v in terminal.items() if k != "terminal_evidence_digest"})
    # Fixture-only SQL: validator compares the exact canonical stored terminal.
    with runtime.store.transaction() as con:
        con.execute("UPDATE jobs SET result_json=? WHERE job_id=?", (json.dumps(terminal, sort_keys=True, separators=(",", ":"), ensure_ascii=False), row["job_id"]))
    return runtime, row, terminal


def test_real_runtime_accepts_truthful_finite_fabric_variant(tmp_path):
    runtime, row, terminal = fabric_fixture(tmp_path)
    with runtime.store.read() as con:
        assert _sealed_worker_result_payload(con, row, expected_role="plan", terminal_payload=terminal)


@pytest.mark.parametrize("remove_pin", [False, True])
def test_remote_launch_cannot_select_local_terminal_validation(tmp_path, remove_pin):
    runtime, row, terminal = fabric_fixture(tmp_path)
    evidence = terminal["result_evidence"]
    evidence["schema_version"] = "mastermind.sealed_worker_result_evidence/v1"
    for key in ("remote_assignment_observation", "remote_assignment_observation_digest",
                "launch_identity", "physical_binding"):
        evidence.pop(key)
    for name in ("collection_receipt", "validation_receipts"):
        evidence[name].pop("fabric_cleanup")
        evidence[name]["uid_sweep"] = copy.deepcopy(evidence["assignment_seal_receipt"]["uid_sweep"])
        evidence[name + "_digest"] = digest(evidence[name])
    terminal["validation_receipt_digest"] = evidence["validation_receipts_digest"]
    terminal["terminal_evidence_digest"] = digest({
        k: v for k, v in terminal.items() if k != "terminal_evidence_digest"})
    if remove_pin:
        metadata = json.loads(row["launch_metadata_json"])
        metadata.pop(REMOTE_LAUNCH_IDENTITY_KEY)
        row["launch_metadata_json"] = json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    with runtime.store.transaction() as con:
        con.execute("UPDATE jobs SET result_json=? WHERE job_id=?", (
            json.dumps(terminal, sort_keys=True, separators=(",", ":"), ensure_ascii=False), row["job_id"]))
    with runtime.store.read() as con:
        with pytest.raises(StateConflict):
            _sealed_worker_result_payload(con, row, expected_role="plan", terminal_payload=terminal)


def test_fabric_pin_cannot_bind_a_local_recovery_adapter(tmp_path):
    runtime, row, terminal = fabric_fixture(tmp_path)
    metadata = json.loads(row["launch_metadata_json"])
    metadata["worker_recovery_binding"]["adapter_id"] = "local"
    row["launch_metadata_json"] = json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    with runtime.store.read() as con:
        with pytest.raises(StateConflict):
            _sealed_worker_result_payload(con, row, expected_role="plan", terminal_payload=terminal)


@pytest.mark.parametrize("adapter_id", ["attempt-bound-remote-worker", "local", None])
def test_ordinary_mh1_remote_pin_requires_compatible_recovery(tmp_path, adapter_id):
    from tests.test_executive_terminal_return import completed_sealed_worker_fixture
    from control_plane.worker_execution_contract import WorkerRecoveryBinding
    runtime, row, terminal, spec, ref = completed_sealed_worker_fixture(tmp_path, include_launch=True)
    metadata = json.loads(row["launch_metadata_json"])
    if adapter_id is not None:
        metadata["worker_recovery_binding"] = WorkerRecoveryBinding.bind(
            adapter_id=adapter_id, spec=spec, process_ref=ref,
            prompt_path=spec.run_dir / "input" / "worker-prompt.txt").to_dict()
    else:
        metadata.pop("worker_recovery_binding", None)
    metadata[REMOTE_LAUNCH_IDENTITY_KEY] = {
        "schema_version": REMOTE_LAUNCH_IDENTITY_SCHEMA, "sha256": "1" * 64}
    row["launch_metadata_json"] = json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    with runtime.store.read() as con:
        if adapter_id == "attempt-bound-remote-worker":
            assert _sealed_worker_result_payload(con, row, expected_role="plan", terminal_payload=terminal)
        else:
            with pytest.raises(StateConflict, match="terminal regime differs from durable launch"):
                _sealed_worker_result_payload(con, row, expected_role="plan", terminal_payload=terminal)


@pytest.mark.parametrize("mutation", ["pin", "physical", "denial", "phase", "sweep", "ref_boolean_alias"])
def test_real_runtime_rejects_fabric_identity_or_evidence_mutation(tmp_path, mutation):
    runtime, row, terminal = fabric_fixture(tmp_path)
    evidence = terminal["result_evidence"]
    if mutation == "pin":
        evidence["launch_identity"]["request"]["binding"]["root_id"] = "foreign"
    elif mutation == "physical":
        evidence["physical_binding"]["host_ref"] = "foreign"
    elif mutation == "phase":
        evidence["collection_receipt"]["fabric_cleanup"]["operation"] = "validation"
        evidence["collection_receipt_digest"] = digest(evidence["collection_receipt"])
    else:
        observation = evidence["remote_assignment_observation"]
        if mutation == "ref_boolean_alias":
            observation["snapshot"]["process_ref"]["binary"]["size"] = True
            observation["snapshot_sha256"] = digest(observation["snapshot"])
        elif mutation == "denial":
            observation["worker_denial"]["run"]["open"] = "ENOENT"
        else:
            observation["snapshot"]["uid_sweep"]["worker_uid"] += 1
            observation["snapshot_sha256"] = digest(observation["snapshot"])
        evidence["remote_assignment_observation_digest"] = digest(observation)
    with runtime.store.read() as con:
        with pytest.raises(StateConflict, match="Fabric terminal evidence failed original-owner validation"):
            _sealed_worker_result_payload(con, row, expected_role="plan", terminal_payload=terminal)


def _without_empty_validation_cleanup(runtime, terminal):
    evidence = terminal["result_evidence"]
    assert evidence["validation_receipts"]["commands"] == []
    assert evidence["launch_identity"]["request"]["validation_commands"] == []
    evidence["validation_receipts"].pop("fabric_cleanup")
    evidence["validation_receipts_digest"] = digest(evidence["validation_receipts"])
    terminal["validation_receipt_digest"] = evidence["validation_receipts_digest"]
    _save_fixture_terminal(runtime, terminal)


def _save_fixture_terminal(runtime, terminal):
    terminal["terminal_evidence_digest"] = digest({
        k: v for k, v in terminal.items() if k != "terminal_evidence_digest"})
    with runtime.store.transaction() as con:
        con.execute("UPDATE jobs SET result_json=? WHERE job_id=?", (
            json.dumps(terminal, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
            terminal["result_evidence"]["validation_receipts"]["job_id"]))


def test_real_runtime_empty_validation_does_not_require_nonexistent_process_evidence(tmp_path):
    runtime, row, terminal = fabric_fixture(tmp_path)
    _without_empty_validation_cleanup(runtime, terminal)
    with runtime.store.read() as con:
        assert _sealed_worker_result_payload(con, row, expected_role="plan", terminal_payload=terminal)


@pytest.mark.parametrize("mutation", ["commands", "launch_commands", "collection_cleanup"])
def test_empty_validation_exception_cannot_hide_other_missing_evidence(tmp_path, mutation):
    runtime, row, terminal = fabric_fixture(tmp_path)
    _without_empty_validation_cleanup(runtime, terminal)
    evidence = terminal["result_evidence"]
    if mutation == "commands":
        evidence["validation_receipts"]["commands"] = [{"argv": ["/usr/bin/true"]}]
        evidence["validation_receipts_digest"] = digest(evidence["validation_receipts"])
        terminal["validation_receipt_digest"] = evidence["validation_receipts_digest"]
    elif mutation == "launch_commands":
        evidence["launch_identity"]["request"]["validation_commands"] = [["/usr/bin/true"]]
        metadata = json.loads(row["launch_metadata_json"])
        metadata[REMOTE_LAUNCH_IDENTITY_KEY]["sha256"] = digest(evidence["launch_identity"])
        row["launch_metadata_json"] = json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    else:
        evidence["collection_receipt"].pop("fabric_cleanup")
        evidence["collection_receipt_digest"] = digest(evidence["collection_receipt"])
    _save_fixture_terminal(runtime, terminal)
    with runtime.store.read() as con:
        with pytest.raises(StateConflict):
            _sealed_worker_result_payload(con, row, expected_role="plan", terminal_payload=terminal)
