"""Offline contract examples; these fixtures attest no host or live cleanup."""
import copy
import hashlib
import importlib
import json

import pytest


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


@pytest.fixture
def example():
    """Mirror lane_runtime's full record; all identities are inert test values."""
    binding = dict(root_id="root-1", job_id="JOB-1", attempt_id="ATT-1",
                   effective_grant_digest="a" * 64, commission_sha256="b" * 64)
    identity = dict(host_ref="fixture-host", boot_session_id="boot-1", pid=100,
                    pgid=100, session_id=100, process_start_identity="ticks:200")
    lane = dict(schema="mastermind.local_owned_process_receipt.v1", label="ATT-1",
                pid=100, pgid=100, started_at="2026-10-11T10:00:00+00:00",
                ended_at="2026-10-11T10:00:10+00:00", returncode=0, timed_out=False,
                nice_requested=None, nice_applied=False, stdout_bytes=10,
                stderr_bytes=0, stdout_truncated=False, stderr_truncated=False,
                runtime_failure_code=None,
                cleanup=dict(status="not_needed", reason="normal_completion",
                             sigterm_sent=False, sigkill_sent=False,
                             identity_verified=True, census_proven=True,
                             residual_count=0, error_code=None,
                             stdout_capture_complete=True, stderr_capture_complete=True,
                             stdin_delivery_complete=True, stdout_capture_error=None,
                             stderr_capture_error=None, stdin_delivery_error=None))
    raw = _canonical(lane) + b"\n"
    receipt = dict(schema_version="mastermind.fabric_process_group_cleanup/v1",
                   binding=copy.deepcopy(binding), physical_binding_sha256="c" * 64,
                   process_identity=copy.deepcopy(identity),
                   lane_started_at=lane["started_at"],
                   lane_receipt_sha256=hashlib.sha256(_canonical(lane)).hexdigest(),
                   lane_receipt_bytes_sha256=hashlib.sha256(raw).hexdigest(),
                   capture_complete=True, cleanup_verified=True, uncertainty=None)
    return dict(receipt=receipt, expected_binding=binding,
                expected_physical_binding_sha256="c" * 64,
                expected_process_identity=identity, lane_receipt_bytes=raw)


def _validate(example):
    owner = importlib.import_module("control_plane.fabric_cleanup_contract")
    return owner.validate_fabric_cleanup_receipt(**example)


def _refuses(example):
    owner = importlib.import_module("control_plane.fabric_cleanup_contract")
    with pytest.raises(owner.FabricCleanupContractError):
        _validate(example)


def _replace_lane(example, edit):
    lane = json.loads(example["lane_receipt_bytes"])
    edit(lane)
    raw = _canonical(lane) + b"\n"
    example["lane_receipt_bytes"] = raw
    example["receipt"]["lane_receipt_sha256"] = hashlib.sha256(_canonical(lane)).hexdigest()
    example["receipt"]["lane_receipt_bytes_sha256"] = hashlib.sha256(raw).hexdigest()


def test_verified_group_cleanup_never_claims_dedicated_user_isolation(example):
    evidence = _validate(example)
    assert evidence.capability == "same_run_process_group_cleanup"
    assert evidence.dedicated_user_isolation is False
    assert evidence.lane_receipt_sha256 == example["receipt"]["lane_receipt_sha256"]
    assert evidence.attempt_id == "ATT-1"


@pytest.mark.parametrize("field,value", [
    ("root_id", "other-root"), ("job_id", "JOB-2"), ("attempt_id", "ATT-2"),
    ("effective_grant_digest", "d" * 64), ("commission_sha256", "e" * 64),
])
def test_foreign_parent_attempt_grant_or_commission_is_refused(example, field, value):
    example["receipt"]["binding"][field] = value
    _refuses(example)


@pytest.mark.parametrize("field,value", [
    ("host_ref", "other-host"), ("boot_session_id", "boot-2"),
    ("pid", 101), ("pgid", 101), ("session_id", 101),
    ("process_start_identity", "ticks:201"),
])
def test_foreign_host_generation_and_reused_pid_are_refused(example, field, value):
    # Same PID with a changed boot/start generation must not inherit cleanup.
    example["receipt"]["process_identity"][field] = value
    _refuses(example)


@pytest.mark.parametrize("field,value", [
    ("physical_binding_sha256", "d" * 64), ("lane_started_at", "2026-10-11T11:00:00+00:00"),
    ("capture_complete", False), ("capture_complete", 1),
    ("cleanup_verified", False), ("cleanup_verified", 1),
    ("uncertainty", "EFFECT_UNKNOWN"), ("uncertainty", False),
    ("lane_receipt_sha256", "e" * 64), ("lane_receipt_bytes_sha256", "f" * 64),
    ("schema_version", "mastermind.dedicated_uid_sweep/v1"),
])
def test_ambiguous_or_wrongly_bound_envelope_is_refused(example, field, value):
    example["receipt"][field] = value
    _refuses(example)


@pytest.mark.parametrize("field,value", [
    ("status", "residual_processes"), ("status", "process_census_unproven"),
    ("status", "identity_mismatch_direct_only"), ("identity_verified", False),
    ("census_proven", False), ("census_proven", 1), ("residual_count", 1),
    ("residual_count", False), ("residual_count", None),
    ("error_code", "permission_denied"), ("stdout_capture_complete", False),
    ("stderr_capture_complete", False), ("stdin_delivery_complete", False),
    ("stdout_capture_error", "pipe_open"), ("stderr_capture_error", "pipe_open"),
    ("stdin_delivery_error", "broken_pipe"),
])
def test_lane_cleanup_and_capture_uncertainty_is_refused(example, field, value):
    _replace_lane(example, lambda lane: lane["cleanup"].update({field: value}))
    _refuses(example)


@pytest.mark.parametrize("field,value", [
    ("pid", 101), ("pgid", 101), ("stdout_truncated", True),
    ("stderr_truncated", True), ("runtime_failure_code", "owned_stream_not_closed"),
    ("ended_at", "2026-10-11T09:00:00+00:00"), ("started_at", "missing"),
    ("returncode", None), ("stdout_bytes", -1),
])
def test_even_rehashed_lane_record_cannot_hide_incomplete_evidence(example, field, value):
    _replace_lane(example, lambda lane: lane.update({field: value}))
    _refuses(example)


@pytest.mark.parametrize("raw", [b"", b"{}\n", b"{\"pid\":1}", b"\xff\n", b"{}\n{}\n"])
def test_missing_truncated_or_nonrecord_bytes_are_refused(example, raw):
    example["lane_receipt_bytes"] = raw
    example["receipt"]["lane_receipt_bytes_sha256"] = hashlib.sha256(raw).hexdigest()
    _refuses(example)


def test_duplicate_keys_do_not_erase_residuals(example):
    raw = example["lane_receipt_bytes"].replace(b'"residual_count":0',
                                              b'"residual_count":1,"residual_count":0')
    example["lane_receipt_bytes"] = raw
    example["receipt"]["lane_receipt_bytes_sha256"] = hashlib.sha256(raw).hexdigest()
    _refuses(example)


@pytest.mark.parametrize("target,field", [("receipt", "uncertainty"),
    ("binding", "effective_grant_digest"), ("identity", "process_start_identity")])
def test_missing_lineage_or_generation_evidence_is_refused(example, target, field):
    value = example["receipt"] if target == "receipt" else example["receipt"][
        "binding" if target == "binding" else "process_identity"]
    del value[field]
    _refuses(example)


def test_unknown_envelope_claim_cannot_promote_group_to_uid_sweep(example):
    example["receipt"]["dedicated_user_isolation"] = True
    _refuses(example)


def test_nonleader_group_does_not_borrow_another_session(example):
    example["expected_process_identity"]["pgid"] = 99
    example["receipt"]["process_identity"]["pgid"] = 99
    _replace_lane(example, lambda lane: lane.update(pgid=99))
    _refuses(example)


def test_proven_termination_and_nonzero_exit_can_still_prove_cleanup(example):
    def terminated(lane):
        lane.update(returncode=124, timed_out=True)
        lane["cleanup"].update(status="terminated", reason="timeout", session_id=100,
                               sigterm_sent=True, sigterm_member_count=1,
                               sigkill_member_count=0)
    _replace_lane(example, terminated)
    assert _validate(example).dedicated_user_isolation is False


def test_terminated_session_must_match_same_launch(example):
    _replace_lane(example, lambda lane: lane["cleanup"].update(
        status="terminated", session_id=101, sigterm_member_count=1,
        sigkill_member_count=0))
    _refuses(example)


def test_source_record_bound_is_enforced_before_parsing(example):
    example["lane_receipt_bytes"] = b" " * (64 * 1024 + 1)
    _refuses(example)


@pytest.mark.parametrize("status", [[], {}, 1, None])
def test_malformed_cleanup_status_is_a_closed_refusal(example, status):
    _replace_lane(example, lambda lane: lane["cleanup"].update(status=status))
    _refuses(example)


@pytest.mark.parametrize("container,field", [("lane", "cleanup"),
    ("lane", "stdout_truncated"), ("cleanup", "stdout_capture_complete"),
    ("cleanup", "census_proven")])
def test_omitted_lane_fields_never_default_to_complete(example, container, field):
    def omit(lane):
        del (lane if container == "lane" else lane["cleanup"])[field]
    _replace_lane(example, omit)
    _refuses(example)


@pytest.mark.parametrize("field,value", [("pid", True), ("pid", 0),
    ("process_start_identity", ""), ("boot_session_id", ""), ("host_ref", "")])
def test_matching_but_invalid_launch_identity_cannot_self_attest(example, field, value):
    example["receipt"]["process_identity"][field] = value
    example["expected_process_identity"][field] = value
    _refuses(example)


def test_same_pid_and_receipt_cannot_be_rebound_to_later_expected_generation(example):
    example["expected_process_identity"]["process_start_identity"] = "ticks:999"
    _refuses(example)


def test_raw_byte_digest_does_not_replace_canonical_record_digest(example):
    # Reformatting preserves the canonical record, but original bytes remain bound.
    raw = json.dumps(json.loads(example["lane_receipt_bytes"]), sort_keys=True).encode() + b"\n"
    example["lane_receipt_bytes"] = raw
    _refuses(example)


@pytest.mark.parametrize("requested,applied", [(10, True), (10, False), (None, False)])
def test_actual_lane_runtime_boolean_nice_application_is_compatible(example, requested, applied):
    _replace_lane(example, lambda lane: lane.update(nice_requested=requested, nice_applied=applied))
    assert _validate(example).capability == "same_run_process_group_cleanup"


@pytest.mark.parametrize("requested,applied", [(10, 1), (10, None), (10, "true"),
                                              (None, True), (True, True), (20, True)])
def test_malformed_nice_application_is_not_producer_evidence(example, requested, applied):
    _replace_lane(example, lambda lane: lane.update(nice_requested=requested, nice_applied=applied))
    _refuses(example)
