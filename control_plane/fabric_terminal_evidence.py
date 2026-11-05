"""Pure terminal join of original Fabric evidence; no effect or admission owner.

Per-phase process-group cleanup stays distinct from the final dedicated-UID
sweep and Control seal. Expected identity must come from durable Runtime state.
This validator authenticates no producer and performs no IO.
"""
from __future__ import annotations

from datetime import datetime
import json
import re

from control_plane.broker_assignment_seal import digest, validate_control_seal
from control_plane.executive_worker_broker import uid_sweep_receipt_is_passing
from control_plane.fabric_cleanup_contract import validate_fabric_cleanup_receipt

SCHEMA = "mastermind.fabric_sealed_worker_result_evidence/v1"
_FIELDS = {"schema_version", "collection_receipt", "collection_receipt_digest",
    "validation_receipts", "validation_receipts_digest", "assignment_seal_receipt",
    "assignment_seal_receipt_digest", "remote_assignment_observation",
    "remote_assignment_observation_digest", "launch_identity", "physical_binding"}


def _require(condition):
    if not condition:
        raise ValueError("invalid_original_fabric_terminal_evidence")


def _shape(value, fields):
    _require(type(value) is dict and set(value) == fields)
    return value


def _time(value):
    _require(type(value) is str)
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require(stamp.tzinfo is not None)
    return stamp.timestamp()


def validate_fabric_terminal_evidence(evidence, *, expected_binding,
        expected_process_ref, expected_worker_id, expected_host_ref,
        expected_launch_identity_sha256, expected_manifest):
    """Raise ValueError on incomplete, foreign, or internally inconsistent evidence."""
    try:
        _validate(evidence, expected_binding, expected_process_ref, expected_worker_id,
                  expected_host_ref, expected_launch_identity_sha256, expected_manifest)
    except (KeyError, TypeError, ValueError, RuntimeError, OverflowError) as exc:
        raise ValueError("invalid_original_fabric_terminal_evidence") from exc


def _validate(evidence, binding, ref, worker, host, launch_sha, manifest):
    _shape(evidence, _FIELDS)
    _require(evidence["schema_version"] == SCHEMA)
    _shape(binding, {"root_id", "job_id", "attempt_id", "effective_grant_digest", "commission_sha256"})
    _require(type(host) is str and bool(host) and type(worker) is str and bool(worker))
    _require(type(launch_sha) is str and re.fullmatch(r"[0-9a-f]{64}", launch_sha) is not None)
    launch = _shape(evidence["launch_identity"], {"physical_binding_sha256", "request"})
    _require(digest(launch) == launch_sha)
    request = launch["request"]
    _require(type(request) is dict and set(request) in (
        {"binding", "physical_binding_sha256", "launch_spec", "validation_commands"},
        {"binding", "physical_binding_sha256", "launch_spec", "validation_commands", "control_recovery"}))
    physical = evidence["physical_binding"]
    _require(type(physical) is dict and digest(physical) == launch["physical_binding_sha256"])
    _require(physical["host_ref"] == host and physical["worker_id"] == worker
        and physical["worker_uid"] == ref["effective_uid"]
        and physical["worker_gid"] == ref["effective_gid"])
    _require(request["binding"] == binding
        and request["physical_binding_sha256"] == launch["physical_binding_sha256"])
    spec = request["launch_spec"]
    _require(spec["run_id"] == binding["attempt_id"] and spec["job_id"] == binding["job_id"]
        and spec["worker_id"] == worker and spec["effective_grant_digest"] == binding["effective_grant_digest"])
    identity = {"host_ref": host, **{k: ref[k] for k in (
        "boot_session_id", "pid", "pgid", "session_id", "process_start_identity")}}
    for name, operation, keys in (
        ("collection_receipt", "collection", {"schema_version", "collection", "fabric_cleanup", "effective_grant_digest"}),
        ("validation_receipts", "validation", {"attempt_id", "job_id", "commands", "fabric_cleanup", "effective_grant_digest"}),
    ):
        empty_validation = (operation == "validation"
            and request["validation_commands"] == []
            and type(evidence[name]) is dict
            and evidence[name].get("commands") == []
            and "fabric_cleanup" not in evidence[name])
        receipt = _shape(evidence[name], keys - {"fabric_cleanup"} if empty_validation else keys)
        _require(digest(receipt) == evidence[name + "_digest"]
            and receipt["effective_grant_digest"] == binding["effective_grant_digest"])
        if operation == "collection":
            _require(receipt["schema_version"] == "mastermind.executive_collection_evidence/v1")
        else:
            _require(receipt["attempt_id"] == binding["attempt_id"] and receipt["job_id"] == binding["job_id"])
        if empty_validation:
            continue
        package = _shape(receipt["fabric_cleanup"], {"schema_version", "operation", "observed_at",
            "worker_uid", "worker_gid", "receipt", "lane_receipt_utf8"})
        _require(package["schema_version"] == "mastermind.executive_fabric_cleanup_evidence/v1"
            and package["operation"] == operation
            and type(package["worker_uid"]) is int and package["worker_uid"] == ref["effective_uid"]
            and type(package["worker_gid"]) is int and package["worker_gid"] == ref["effective_gid"]
            and type(package["lane_receipt_utf8"]) is str)
        raw = package["lane_receipt_utf8"].encode("utf-8")
        validate_fabric_cleanup_receipt(package["receipt"], expected_binding=binding,
            expected_physical_binding_sha256=launch["physical_binding_sha256"],
            expected_process_identity=identity, lane_receipt_bytes=raw)
        _require(_time(package["observed_at"]) >= _time(ref["started_at"])
            and _time(package["observed_at"]) >= _time(json.loads(raw)["ended_at"]))
    observation = _shape(evidence["remote_assignment_observation"], {
        "schema_version", "snapshot", "snapshot_sha256", "control_seal", "worker_denial"})
    _require(observation["schema_version"] == "mastermind.worker_assignment_seal_commit/v1"
        and digest(observation) == evidence["remote_assignment_observation_digest"])
    snapshot = _shape(observation["snapshot"], {"schema_version", "run_id", "job_id", "worker_id",
        "effective_grant_digest", "process_ref", "paths", "uid_sweep"})
    _require(snapshot["schema_version"] == "mastermind.worker_assignment_seal_prepare/v1"
        and digest(snapshot) == observation["snapshot_sha256"]
        and snapshot["run_id"] == binding["attempt_id"] and snapshot["job_id"] == binding["job_id"]
        and snapshot["worker_id"] == worker and snapshot["effective_grant_digest"] == binding["effective_grant_digest"]
        and digest(snapshot["process_ref"]) == digest(ref))
    sweep = snapshot["uid_sweep"]
    _require(uid_sweep_receipt_is_passing(sweep) and type(sweep.get("worker_uid")) is int
        and sweep["worker_uid"] == ref["effective_uid"])
    entries = [item for item in manifest["entries"]
               if item["disposition"] in {"CURRENT_WORKSPACE", "CURRENT_RUN"}]
    _require(len(entries) == 2 and len({item["disposition"] for item in entries}) == 2)
    expected_paths = {item["disposition"].removeprefix("CURRENT_").lower(): item["identity"] for item in entries}
    paths = _shape(snapshot["paths"], {"workspace", "run"})
    for label, original in expected_paths.items():
        current = _shape(paths[label], set(original))
        _require(all(type(current[key]) is type(original[key]) and current[key] == original[key]
                     for key in original if key != "mtime_ns"))
    control_uid = expected_paths["run"]["uid"]
    _require(type(control_uid) is int and control_uid != ref["effective_uid"]
        and expected_paths["workspace"]["uid"] == control_uid)
    validate_control_seal(snapshot, observation["control_seal"], control_uid)
    _require(observation["worker_denial"] == {
        label: {"open": "EACCES", "traverse": "EACCES", "list": "EACCES"} for label in ("workspace", "run")})
    assignment = {**observation["control_seal"], "attempt_id": binding["attempt_id"],
        "job_id": binding["job_id"], "effective_grant_digest": binding["effective_grant_digest"], "uid_sweep": sweep}
    _require(digest(evidence["assignment_seal_receipt"]) == digest(assignment)
        and evidence["assignment_seal_receipt_digest"] == digest(assignment))
