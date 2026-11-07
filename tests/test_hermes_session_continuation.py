"""Pure native Secretary continuation contracts; no Runtime, no live proof.

Every assertion here exercises the immutable request/recovery projection
only. Nothing in this module writes an Event, opens a native transport or
claims a deployment or product acceptance.
"""
import copy
import hashlib
import json

import pytest

from control_plane import native_continuation as nc
from control_plane.executive_runtime import Event
from integrations.hermes_runtime.native_session_control import (
    input_digest as native_owner_input_digest,
)

BINDING = {
    "schema": nc.HERMES_BINDING_SCHEMA,
    "composition_sha256": "a" * 64,
    "host_ref": "host-" + "b" * 64,
    "root_id": "hermes-prod-01",
    "root_job_id": "JOB-042",
    "work_ref": "WS:NATIVE-SECRETARY",
    "session_id": "session-01",
    "profile_id": "/home/hermes/profile",
    "principal_id": "uid:1000",
    "expected_host_binding_sha256": "c" * 64,
    "expected_implementation_sha": "d" * 40,
}

NATIVE_TARGET = {
    "profile_id": "/home/hermes/profile",
    "session_id": "session-01",
    "principal_id": "uid:1000",
    "instance_id": "instance-01",
    "authority_epoch": 3,
    "revision": 7,
    "execution_generation": 2,
}

PRINCIPAL = {
    "policy_id": "office-submit",
    "issuer_digest": "e" * 64,
    "resource": "https://executive.test/mcp",
    "subject_digest": "f" * 64,
    "client_ref": "1" * 64,
}

INSTRUCTION = "Read and return the bounded finding."
STOP_CONDITION = "Return one finding."


def root_event(event_id=7, job_id="JOB-042"):
    return Event(event_id=event_id, aggregate_type="job", aggregate_id=job_id,
                 sequence=1, event_type="JOB_CREATED",
                 command_id="job-created:" + job_id, actor="executive",
                 job_id=job_id, attempt_id=None, worker_id=None, quota_class=None,
                 payload={"objective": "Native Secretary"},
                 created_at="2026-11-05T00:00:00Z")


def build_request(*, binding=None, native_target=None, principal=None,
                  root=None, instruction=INSTRUCTION, stop_condition=STOP_CONDITION):
    binding = dict(BINDING) if binding is None else binding
    native_target = dict(NATIVE_TARGET) if native_target is None else native_target
    principal = dict(PRINCIPAL) if principal is None else principal
    root = root_event() if root is None else root
    target = nc.build_hermes_continuation_target(
        binding=binding, root_event=root, native_target=native_target)
    return nc.build_hermes_continuation_request(
        principal=principal, binding=binding, root_event=root,
        native_target=native_target,
        arguments={"target_ref": target["target_ref"], "instruction": instruction,
                   "stop_condition": stop_condition,
                   "operation_key": target["continuation_operation_key"]})


def request_event(payload, *, event_id=11, aggregate_id=None, command_id=None,
                  job_id="JOB-042", attempt_id=None, worker_id=None,
                  event_type=None, sequence=1):
    request_key = nc._request_key(payload["operation_key"])
    return Event(event_id=event_id, aggregate_type="session_bridge_continue",
                 aggregate_id=aggregate_id or request_key, sequence=sequence,
                 event_type=event_type or nc._EVENT,
                 command_id=command_id or (nc._PREFIX + request_key),
                 actor=nc._ACTOR, job_id=job_id, attempt_id=attempt_id,
                 worker_id=worker_id, quota_class=None, payload=payload,
                 created_at="2026-11-05T00:00:01Z")


def identity(principal=None):
    principal = dict(PRINCIPAL) if principal is None else principal
    return tuple(principal[key] for key in nc._IDENTITY)


# ---------------------------------------------------------------------------
# Binding, target and request derivation
# ---------------------------------------------------------------------------

def test_binding_rejects_an_incomplete_or_overloaded_projection():
    for mutation in (
        {"schema": "mastermind.session_bridge.hermes_secretary_binding.v2"},
        {"composition_sha256": "A" * 64},
        {"expected_host_binding_sha256": "c" * 63},
        {"expected_implementation_sha": "d" * 41},
        {"host_ref": "host-" + "b" * 63},
        {"root_id": "bad root"},
        {"root_job_id": "TASK-042"},
        {"work_ref": "NATIVE-SECRETARY"},
        {"session_id": ""},
        {"profile_id": "profile\x00id"},
        {"principal_id": "u" * 1025},
    ):
        binding = {**BINDING, **mutation}
        with pytest.raises(ValueError):
            nc.build_hermes_continuation_target(
                binding=binding, root_event=root_event(),
                native_target=NATIVE_TARGET)


def test_binding_keeps_distinct_owners_without_requiring_unequal_labels():
    binding = {**BINDING, "root_id": "JOB-042"}
    target = nc.build_hermes_continuation_target(
        binding=binding, root_event=root_event(), native_target=NATIVE_TARGET)
    assert target["root_job_id"] == "JOB-042"


def test_binding_rejects_a_transport_or_secret_shaped_projection():
    binding = {**BINDING, "endpoint": "https://hermes.test/socket"}
    with pytest.raises(ValueError):
        nc.build_hermes_continuation_target(
            binding=binding, root_event=root_event(), native_target=NATIVE_TARGET)


def test_target_requires_the_actual_selected_root_created_event():
    with pytest.raises(ValueError):
        nc.build_hermes_continuation_target(
            binding=BINDING, root_event=root_event(job_id="JOB-099"),
            native_target=NATIVE_TARGET)
    with pytest.raises(ValueError):
        nc.build_hermes_continuation_target(
            binding=BINDING, root_event=root_event(event_id=0),
            native_target=NATIVE_TARGET)
    not_created = root_event()
    object.__setattr__(not_created, "event_type", "JOB_UPDATED")
    with pytest.raises(ValueError):
        nc.build_hermes_continuation_target(
            binding=BINDING, root_event=not_created, native_target=NATIVE_TARGET)


def test_target_projection_is_the_closed_seven_field_shape():
    target = nc.build_hermes_continuation_target(
        binding=BINDING, root_event=root_event(), native_target=NATIVE_TARGET)
    assert set(target) == {"kind", "target_ref", "generation", "addressable",
                            "continuation_operation_key", "work_ref", "root_job_id"}
    assert target["kind"] == "hermes_secretary"
    assert target["addressable"] is True
    assert target["work_ref"] == "WS:NATIVE-SECRETARY"
    assert target["root_job_id"] == "JOB-042"
    assert target["target_ref"].startswith("hermes_secretary:")
    assert len(target["target_ref"].split(":", 1)[1]) == 64
    assert len(target["generation"]) == 24
    assert target["continuation_operation_key"].startswith("session-continue-")


def test_target_requires_the_native_target_to_match_the_binding():
    for field in ("profile_id", "session_id", "principal_id"):
        native_target = {**NATIVE_TARGET, field: "other"}
        with pytest.raises(ValueError):
            nc.build_hermes_continuation_target(
                binding=BINDING, root_event=root_event(), native_target=native_target)


def test_native_target_counters_reject_bool_and_negative_values():
    for mutation in ({"authority_epoch": 0}, {"revision": -1},
                     {"execution_generation": -1}, {"authority_epoch": True},
                     {"revision": False}):
        native_target = {**NATIVE_TARGET, **mutation}
        with pytest.raises(ValueError):
            nc.build_hermes_continuation_target(
                binding=BINDING, root_event=root_event(),
                native_target=native_target)


def test_target_derivation_excludes_the_office_policy_id():
    """The trusted READ/SEND pair must derive the same target."""
    read_principal = {**PRINCIPAL, "policy_id": "office-read"}
    submit = nc.build_hermes_continuation_target(
        binding=BINDING, root_event=root_event(), native_target=NATIVE_TARGET)
    other = nc.build_hermes_continuation_target(
        binding=BINDING, root_event=root_event(), native_target=NATIVE_TARGET)
    assert submit["target_ref"] == other["target_ref"]
    request = build_request()
    paired = build_request(principal=read_principal)
    assert paired["target_ref"] == request["target_ref"]
    assert paired["operation_key"] == request["operation_key"]
    assert paired["read_ref"] == request["read_ref"]
    assert paired["principal"] == read_principal


def test_request_payload_is_the_closed_projection_without_a_legacy_carrier():
    payload = build_request()
    assert set(payload) == {
        "schema", "principal", "work_ref", "root_job_id", "root_event_id",
        "root_event_sha256", "target_ref", "target_generation", "operation_key",
        "binding", "binding_sha256", "input", "input_sha256", "native_request",
        "native_request_sha256", "native_input_sha256", "read_ref"}
    assert payload["schema"] == nc.HERMES_REQUEST_SCHEMA
    for legacy in ("job_id", "attempt_id", "worker_id", "epoch", "context",
                   "carrier", "thread_ts", "request_message_key", "generation"):
        assert legacy not in payload
    assert set(payload["input"]) == {"instruction", "stop_condition"}
    assert set(payload["native_request"]) == {"operation", "target", "submission_id", "text"}
    assert payload["native_request"]["operation"] == "submit"
    assert set(payload["native_request"]["target"]) == set(NATIVE_TARGET)


def test_request_derivation_matches_the_declared_material():
    payload = build_request()
    root = root_event()
    material = {"schema": nc.HERMES_TARGET_SCHEMA, "binding": BINDING,
                "root_event_id": root.event_id,
                "root_event_sha256": nc._digest(root.to_dict()),
                "native_target": NATIVE_TARGET}
    digest = nc._digest(material)
    assert payload["target_ref"] == "hermes_secretary:" + digest
    assert payload["target_generation"] == digest[:24]
    assert payload["operation_key"] == "session-continue-" + nc._digest(
        {"schema": nc.HERMES_OPERATION_SCHEMA, "target_ref": payload["target_ref"]})
    request_key = nc._request_key(payload["operation_key"])
    assert payload["read_ref"] == "session-reply-" + request_key
    assert payload["native_request"]["submission_id"] == "session-secretary-" + request_key
    assert payload["binding_sha256"] == nc._digest(BINDING)
    assert payload["input_sha256"] == nc._digest(
        {"instruction": INSTRUCTION, "stop_condition": STOP_CONDITION})
    assert payload["native_request_sha256"] == nc._digest(payload["native_request"])
    assert payload["root_event_sha256"] == nc._digest(root.to_dict())


def test_deterministic_prompt_is_exact():
    payload = build_request()
    expected = ("Instruction:\n" + INSTRUCTION + "\n\nCompletion condition:\n"
                + STOP_CONDITION)
    assert payload["native_request"]["text"] == expected


def test_native_input_digest_matches_the_native_owner_for_non_ascii():
    instruction = "Décision finale — arrêter le cycle."
    stop_condition = "Arrêt après un seul constat."
    payload = build_request(instruction=instruction, stop_condition=stop_condition)
    text = payload["native_request"]["text"]
    assert payload["native_input_sha256"] == native_owner_input_digest(text)
    # The ASCII canonical digest is not the native owner's digest.
    assert payload["native_input_sha256"] != nc._digest({"text": text, "finite": True})
    assert payload["native_input_sha256"] == hashlib.sha256(json.dumps(
        {"text": text, "finite": True}, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def test_request_rejects_a_mismatched_target_or_operation():
    payload = build_request()
    root = root_event()
    target = nc.build_hermes_continuation_target(
        binding=BINDING, root_event=root, native_target=NATIVE_TARGET)
    for mutation in ({"target_ref": "hermes_secretary:" + "0" * 64},
                     {"operation_key": "session-continue-" + "0" * 64}):
        arguments = {"target_ref": target["target_ref"], "instruction": INSTRUCTION,
                     "stop_condition": STOP_CONDITION,
                     "operation_key": target["continuation_operation_key"]}
        arguments.update(mutation)
        with pytest.raises(ValueError):
            nc.build_hermes_continuation_request(
                principal=PRINCIPAL, binding=BINDING, root_event=root,
                native_target=NATIVE_TARGET, arguments=arguments)
    with pytest.raises(ValueError):
        nc.build_hermes_continuation_request(
            principal=PRINCIPAL, binding=BINDING, root_event=root,
            native_target=NATIVE_TARGET,
            arguments={"target_ref": target["target_ref"], "instruction": INSTRUCTION,
                       "stop_condition": STOP_CONDITION})


def test_request_rejects_an_unclosed_argument_projection():
    root = root_event()
    target = nc.build_hermes_continuation_target(
        binding=BINDING, root_event=root, native_target=NATIVE_TARGET)
    arguments = {"target_ref": target["target_ref"], "instruction": INSTRUCTION,
                 "stop_condition": STOP_CONDITION,
                 "operation_key": target["continuation_operation_key"]}
    with pytest.raises(ValueError):
        nc.build_hermes_continuation_request(
            principal=PRINCIPAL, binding=BINDING, root_event=root,
            native_target=NATIVE_TARGET, arguments={**arguments, "extra": "no"})


@pytest.mark.parametrize("mutation", [
    {"instruction": ""},
    {"instruction": "   "},
    {"instruction": "x" * 701},
    {"stop_condition": ""},
    {"stop_condition": "y" * 701},
])
def test_request_rejects_a_blank_or_oversized_instruction(mutation):
    with pytest.raises(ValueError):
        build_request(**mutation)


# ---------------------------------------------------------------------------
# Validation of a stored payload
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mutation", [
    {"target_ref": "hermes_secretary:" + "0" * 64},
    {"target_generation": "0" * 24},
    {"operation_key": "session-continue-" + "0" * 64},
    {"read_ref": "session-reply-" + "0" * 64},
    {"binding_sha256": "0" * 64},
    {"input_sha256": "0" * 64},
    {"native_request_sha256": "0" * 64},
    {"native_input_sha256": "0" * 64},
    {"root_event_sha256": "0" * 64},
    {"root_event_id": 0},
    {"work_ref": "WS:OTHER"},
    {"root_job_id": "JOB-099"},
])
def test_validation_rejects_a_tampered_payload(mutation):
    payload = {**build_request(), **mutation}
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_request(payload)


def test_validation_rejects_a_tampered_nested_binding_or_input():
    payload = build_request()
    binding = {**payload["binding"], "host_ref": "host-" + "0" * 64}
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_request({**payload, "binding": binding})
    native = {**payload["native_request"], "text": payload["native_request"]["text"] + "!"}
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_request({**payload, "native_request": native})
    source = {**payload["input"], "instruction": "Changed instruction."}
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_request({**payload, "input": source})


def test_validation_rejects_an_unclosed_payload():
    payload = build_request()
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_request({**payload, "extra": "no"})
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_request({k: v for k, v in payload.items()
                                                 if k != "read_ref"})


def test_validation_returns_a_detached_payload():
    payload = build_request()
    validated = nc.validate_hermes_continuation_request(payload)
    payload["binding"]["root_id"] = "tampered"
    payload["input"]["instruction"] = "tampered"
    payload["native_request"]["text"] = "tampered"
    payload["principal"]["policy_id"] = "tampered"
    assert validated["binding"]["root_id"] == "hermes-prod-01"
    assert validated["input"]["instruction"] == INSTRUCTION
    assert validated["native_request"]["text"].startswith("Instruction:")
    assert validated["principal"]["policy_id"] == "office-submit"
    assert validated is not payload


# ---------------------------------------------------------------------------
# Request Event and principal filter
# ---------------------------------------------------------------------------

def test_request_event_requires_the_closed_event_shape():
    payload = build_request()
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_request_event(
            request_event(payload, attempt_id="attempt-01"),
            original_principals=(identity(),))
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_request_event(
            request_event(payload, worker_id="worker-01"),
            original_principals=(identity(),))
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_request_event(
            request_event(payload, job_id="JOB-099"),
            original_principals=(identity(),))
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_request_event(
            request_event(payload, event_type="SESSION_BRIDGE_OTHER"),
            original_principals=(identity(),))
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_request_event(
            request_event(payload, aggregate_id="other"),
            original_principals=(identity(),))
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_request_event(
            request_event(payload, command_id="other"),
            original_principals=(identity(),))
    assert nc.validate_hermes_continuation_request_event(
        request_event(payload), original_principals=(identity(),))["schema"] == (
            nc.HERMES_REQUEST_SCHEMA)


def test_request_event_rejects_a_foreign_or_missing_principal_filter():
    payload = build_request()
    event = request_event(payload)
    foreign = {**PRINCIPAL, "subject_digest": "9" * 64}
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_request_event(
            event, original_principals=(identity(foreign),))
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_request_event(
            event, original_principals=None)
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_request_event(
            event, original_principals=())
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_request_event(
            event, original_principals=(identity(), identity()))
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_request_event(
            event, original_principals=(identity()[:2],))


def test_request_event_accepts_the_trusted_read_submit_pair():
    payload = build_request()
    event = request_event(payload)
    read = {**PRINCIPAL, "policy_id": "office-read"}
    validated = nc.validate_hermes_continuation_request_event(
        event, original_principals=(identity(), identity(read)))
    assert validated["principal"]["policy_id"] == "office-submit"
    # The pair must not differ in any identity field other than policy_id.
    unrelated = {**PRINCIPAL, "policy_id": "office-read", "client_ref": "2" * 64}
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_request_event(
            event, original_principals=(identity(), identity(unrelated)))


# ---------------------------------------------------------------------------
# Commit fact
# ---------------------------------------------------------------------------

def test_commit_requires_an_exact_native_submission():
    payload = build_request()
    event = request_event(payload)
    commit = nc.build_hermes_continuation_commit(
        event, operation_name="submit", native_request=payload["native_request"])
    assert set(commit) == {
        "schema", "request_event_id", "request_event_sha256", "operation_key",
        "read_ref", "binding_sha256", "native_request_sha256", "native_input_sha256",
        "submission_id"}
    assert commit["schema"] == nc.HERMES_COMMIT_SCHEMA
    assert commit["request_event_id"] == event.event_id
    assert commit["request_event_sha256"] == nc._digest(event.to_dict())
    assert commit["submission_id"] == payload["native_request"]["submission_id"]
    assert nc.validate_hermes_continuation_commit(commit, request_event=event) == commit


def test_commit_refuses_a_changed_native_submission_or_operation():
    payload = build_request()
    event = request_event(payload)
    with pytest.raises(ValueError):
        nc.build_hermes_continuation_commit(
            event, operation_name="read_original",
            native_request=payload["native_request"])
    changed = {**payload["native_request"], "text": payload["native_request"]["text"] + "!"}
    with pytest.raises(ValueError):
        nc.build_hermes_continuation_commit(
            event, operation_name="submit", native_request=changed)


def test_commit_validation_rejects_a_broken_join():
    payload = build_request()
    event = request_event(payload)
    commit = nc.build_hermes_continuation_commit(
        event, operation_name="submit", native_request=payload["native_request"])
    for mutation in ({"request_event_id": event.event_id + 1},
                     {"request_event_sha256": "0" * 64},
                     {"operation_key": "session-continue-" + "0" * 64},
                     {"read_ref": "session-reply-" + "0" * 64},
                     {"binding_sha256": "0" * 64},
                     {"native_request_sha256": "0" * 64},
                     {"native_input_sha256": "0" * 64},
                     {"submission_id": "session-secretary-" + "0" * 64},
                     {"schema": "mastermind.session_bridge.hermes_secretary_commit.v2"}):
        with pytest.raises(ValueError):
            nc.validate_hermes_continuation_commit({**commit, **mutation},
                                                   request_event=event)
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_commit({**commit, "extra": "no"},
                                               request_event=event)


# ---------------------------------------------------------------------------
# Commit evidence over the request aggregate
# ---------------------------------------------------------------------------

def commit_event(payload, event, *, event_id=12, sequence=2):
    body = nc.build_hermes_continuation_commit(
        event, operation_name="submit", native_request=payload["native_request"])
    return Event(event_id=event_id, aggregate_type="session_bridge_continue",
                 aggregate_id=event.aggregate_id, sequence=sequence,
                 event_type="SESSION_BRIDGE_CONTINUE_COMMIT_STARTED",
                 command_id="session-bridge-continue-commit:" + event.aggregate_id,
                 actor=nc._ACTOR, job_id=event.job_id, attempt_id=None, worker_id=None,
                 quota_class=None, payload=body,
                 created_at="2026-11-05T00:00:02Z")


def test_commit_evidence_returns_none_for_a_request_only_aggregate():
    payload = build_request()
    event = request_event(payload)
    assert nc.hermes_continuation_commit_evidence(event, (event,), None, None) is None


def test_commit_evidence_selects_the_single_matching_commit():
    payload = build_request()
    event = request_event(payload)
    commit = commit_event(payload, event)
    assert nc.hermes_continuation_commit_evidence(
        event, (event, commit), commit, None) == commit


def test_commit_evidence_refuses_a_disagreeing_global_index():
    payload = build_request()
    event = request_event(payload)
    commit = commit_event(payload, event)
    with pytest.raises(ValueError):
        nc.hermes_continuation_commit_evidence(event, (event, commit), None, None)
    with pytest.raises(ValueError):
        nc.hermes_continuation_commit_evidence(event, (event,), commit, None)


def test_commit_evidence_refuses_a_legacy_native_reply_commit():
    payload = build_request()
    event = request_event(payload)
    legacy = Event(event_id=13, aggregate_type="session_bridge_continue",
                   aggregate_id=event.aggregate_id, sequence=2,
                   event_type="SESSION_BRIDGE_NATIVE_REPLY_COMMIT_STARTED",
                   command_id="session-bridge-native-reply-commit:" + event.aggregate_id,
                   actor=nc._ACTOR, job_id=event.job_id, attempt_id=None, worker_id=None,
                   quota_class=None, payload={"legacy": True},
                   created_at="2026-11-05T00:00:02Z")
    with pytest.raises(ValueError):
        nc.hermes_continuation_commit_evidence(event, (event, legacy), None, None)
    with pytest.raises(ValueError):
        nc.hermes_continuation_commit_evidence(event, (event,), None, legacy)


def test_commit_evidence_refuses_an_unrelated_aggregate_member():
    payload = build_request()
    event = request_event(payload)
    noise = Event(event_id=14, aggregate_type="session_bridge_continue",
                  aggregate_id=event.aggregate_id, sequence=2,
                  event_type="SESSION_BRIDGE_OTHER", command_id="other",
                  actor=nc._ACTOR, job_id=event.job_id, attempt_id=None, worker_id=None,
                  quota_class=None, payload={"noise": True},
                  created_at="2026-11-05T00:00:02Z")
    with pytest.raises(ValueError):
        nc.hermes_continuation_commit_evidence(event, (event, noise), None, None)


def test_commit_evidence_refuses_a_duplicate_or_missing_request():
    payload = build_request()
    event = request_event(payload)
    other = request_event(payload, event_id=15)
    with pytest.raises(ValueError):
        nc.hermes_continuation_commit_evidence(event, (event, other), None, None)
    with pytest.raises(ValueError):
        nc.hermes_continuation_commit_evidence(event, (), None, None)


def test_commit_evidence_refuses_a_commit_before_its_request():
    payload = build_request()
    event = request_event(payload)
    commit = commit_event(payload, event, sequence=1)
    with pytest.raises(ValueError):
        nc.hermes_continuation_commit_evidence(event, (commit, event), commit, None)


def test_commit_evidence_refuses_a_commit_with_a_legacy_attempt_carrier():
    payload = build_request()
    event = request_event(payload)
    commit = commit_event(payload, event)
    object.__setattr__(commit, "attempt_id", "attempt-01")
    with pytest.raises(ValueError):
        nc.hermes_continuation_commit_evidence(event, (event, commit), commit, None)


# ---------------------------------------------------------------------------
# Native read request projection
# ---------------------------------------------------------------------------

def test_read_request_projects_the_native_owner_parameters():
    payload = build_request()
    request = nc.hermes_continuation_read_request(payload)
    assert request == {"operation": "read_original",
                       "session_id": BINDING["session_id"],
                       "submission_id": payload["native_request"]["submission_id"],
                       "input_sha256": payload["native_input_sha256"]}


def test_read_request_omits_an_unknown_admission_id():
    payload = build_request()
    request = nc.hermes_continuation_read_request(payload, admission_id=None)
    assert "admission_id" not in request
    supplied = nc.hermes_continuation_read_request(payload, admission_id="adm-01")
    assert supplied["admission_id"] == "adm-01"


def test_read_request_refuses_an_invalid_admission_id():
    payload = build_request()
    for admission_id in ("", "adm\x00id", "a" * 1025):
        with pytest.raises(ValueError):
            nc.hermes_continuation_read_request(payload, admission_id=admission_id)


def test_read_request_refuses_an_unvalidated_request():
    payload = build_request()
    with pytest.raises(ValueError):
        nc.hermes_continuation_read_request({**payload, "read_ref": "session-reply-" + "0" * 64})


def test_payload_survives_a_copy_without_sharing_state():
    payload = copy.deepcopy(build_request())
    validated = nc.validate_hermes_continuation_request(payload)
    assert validated == payload


@pytest.mark.parametrize("job_id", ["JOB-1", "JOB-42", "JOB-123456789"])
def test_native_binding_uses_incumbent_root_admission_identifiers(job_id):
    target = nc.build_hermes_continuation_target(
        binding={**BINDING, "root_job_id": job_id},
        root_event=root_event(job_id=job_id), native_target=NATIVE_TARGET)
    assert target["root_job_id"] == job_id


@pytest.mark.parametrize("mutation", [
    {"root_job_id": "JOB-1234567890"}, {"root_job_id": "JOB-"},
    {"work_ref": "WS:secretary"}, {"work_ref": "WS:S"},
])
def test_native_binding_rejects_noncanonical_responsibility(mutation):
    with pytest.raises(ValueError):
        nc.build_hermes_continuation_target(
            binding={**BINDING, **mutation}, root_event=root_event(),
            native_target=NATIVE_TARGET)


@pytest.mark.parametrize("mutation", [
    {"event_id": True}, {"event_id": 0}, {"sequence": 1.0}, {"sequence": 2},
    {"quota_class": "paid"}, {"actor": "other"}, {"aggregate_type": "other"},
])
def test_every_commit_helper_validates_actual_request_metadata(mutation):
    from dataclasses import replace
    original = request_event(build_request())
    valid_commit = nc.build_hermes_continuation_commit(
        original, operation_name="submit", native_request=original.payload["native_request"])
    changed = replace(original, **mutation)
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_request_event(
            changed, original_principals=(identity(),))
    with pytest.raises(ValueError):
        nc.build_hermes_continuation_commit(
            changed, operation_name="submit", native_request=changed.payload["native_request"])
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_commit(valid_commit, request_event=changed)
    with pytest.raises(ValueError):
        nc.hermes_continuation_commit_evidence(changed, (changed,), None, None)


@pytest.mark.parametrize("mutation", [
    {"event_id": True}, {"event_id": 11}, {"event_id": 10},
    {"sequence": 2.0}, {"sequence": 3}, {"quota_class": "paid"},
])
def test_commit_fact_has_actual_identity_and_exact_closed_sequence(mutation):
    from dataclasses import replace
    original = request_event(build_request())
    payload = nc.build_hermes_continuation_commit(
        original, operation_name="submit", native_request=original.payload["native_request"])
    changed = replace(commit_event(original.payload, original), **mutation)
    with pytest.raises(ValueError):
        nc.hermes_continuation_commit_evidence(
            original, (original, changed), changed, None)


def test_global_index_requires_canonical_evidence_not_permissive_scalar_equality():
    from dataclasses import replace
    original = request_event(build_request())
    payload = nc.build_hermes_continuation_commit(
        original, operation_name="submit", native_request=original.payload["native_request"])
    commit = commit_event(original.payload, original)
    indexed = replace(commit, sequence=2.0)
    assert indexed.to_dict() == commit.to_dict()
    with pytest.raises(ValueError):
        nc.hermes_continuation_commit_evidence(
            original, (original, commit), indexed, None)


@pytest.mark.parametrize("mutation", [
    {"aggregate_type": "other"}, {"aggregate_id": "JOB-999"},
    {"sequence": 2}, {"sequence": True}, {"attempt_id": "attempt"},
    {"worker_id": "worker"}, {"quota_class": "paid"},
])
def test_native_root_is_actual_first_job_event_without_worker_carriers(mutation):
    from dataclasses import replace
    with pytest.raises(ValueError):
        nc.build_hermes_continuation_target(
            binding=BINDING, root_event=replace(root_event(), **mutation),
            native_target=NATIVE_TARGET)

@pytest.mark.parametrize("kind", nc.HERMES_KINDS)
def test_each_role_round_trips_on_the_same_original_event_owner(kind):
    family = nc.hermes_family(kind)
    binding = dict(BINDING, schema=family.binding_schema)
    payload = build_request(binding=binding)
    assert payload["schema"] == family.request_schema
    assert payload["target_ref"].startswith(family.target_prefix)
    assert payload["native_request"]["submission_id"].startswith(family.submission_prefix)
    assert nc.validate_hermes_continuation_request(payload) == payload
    event = request_event(payload)
    commit = nc.build_hermes_continuation_commit(
        event, operation_name="submit", native_request=payload["native_request"])
    assert commit["schema"] == family.commit_schema
    assert nc.validate_hermes_continuation_commit(commit, request_event=event) == commit
    assert nc.hermes_continuation_read_request(payload)["submission_id"] == payload["native_request"]["submission_id"]


def test_meta_domain_is_distinct_even_when_native_labels_and_input_match():
    secretary = build_request()
    meta = build_request(binding=dict(BINDING, schema=nc.hermes_family("hermes_meta").binding_schema))
    for field in ("schema", "target_ref", "target_generation", "operation_key", "binding_sha256",
                  "native_request_sha256", "read_ref"):
        assert secretary[field] != meta[field]
    assert secretary["native_input_sha256"] == meta["native_input_sha256"]
    assert secretary["native_request"]["submission_id"] != meta["native_request"]["submission_id"]


@pytest.mark.parametrize("kind", nc.HERMES_KINDS)
@pytest.mark.parametrize("fault", ["request-schema", "binding-schema", "target-prefix",
                                  "submission-prefix", "operation-domain", "commit-schema"])
def test_recomputed_cross_role_swaps_never_validate(kind, fault):
    family = nc.hermes_family(kind)
    other = nc.hermes_family("hermes_meta" if kind == "hermes_secretary" else "hermes_secretary")
    payload = build_request(binding=dict(BINDING, schema=family.binding_schema))
    event = request_event(copy.deepcopy(payload))
    if fault == "commit-schema":
        commit = nc.build_hermes_continuation_commit(
            event, operation_name="submit", native_request=payload["native_request"])
        commit["schema"] = other.commit_schema
        with pytest.raises(ValueError):
            nc.validate_hermes_continuation_commit(commit, request_event=event)
        return
    if fault == "request-schema":
        payload["schema"] = other.request_schema
    elif fault == "binding-schema":
        payload["binding"]["schema"] = other.binding_schema
        payload["binding_sha256"] = nc._digest(payload["binding"])
    elif fault == "target-prefix":
        payload["target_ref"] = other.target_prefix + payload["target_ref"].split(":", 1)[1]
    elif fault == "submission-prefix":
        payload["native_request"]["submission_id"] = other.submission_prefix + nc._request_key(payload["operation_key"])
        payload["native_request_sha256"] = nc._digest(payload["native_request"])
    else:
        payload["operation_key"] = "session-continue-" + nc._digest(
            {"schema": other.operation_schema, "target_ref": payload["target_ref"]})
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_request(payload)


@pytest.mark.parametrize("schema", [None, True, [], "mastermind.session_bridge.hermes_meta_request.v2"])
def test_unknown_stored_schema_has_no_secretary_default(schema):
    payload = build_request()
    payload["schema"] = schema
    with pytest.raises(ValueError):
        nc.validate_hermes_continuation_request(payload)
