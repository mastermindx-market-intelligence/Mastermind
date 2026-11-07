"""One native admission or one original-result read for primary acceptance.

Run from the original owner's qualified source/interpreter after its release,
primary APPLICATION enrollment, account and funding predicates hold. This
command does not create those predicates or declare live acceptance. It uses
the existing same-UID native client, never another agent, provider client,
broker, session, journal, retry loop or enrollment operation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys


SCHEMA = "mastermind.hermes_primary_native_acceptance/v1"
ROLE = "mmsecretary"
MAX_DOCUMENT_BYTES = 96 * 1024
MAX_PROMPT_BYTES = 16 * 1024
IDENTITY_KEYS = ("agent_session_id", "task_id", "turn_id", "api_request_id",
                 "tool_call_id", "tool_name")
ADMISSION_KEYS = {"admission_id", "ref", "sequence", "status", "outcome",
                  "authority_epoch", "execution_generation"}
TERMINAL_EXTENSIONS = {"terminal_metadata", "request_observation", "request_observation_error"}
TERMINAL_REPORTED = {"completed", "failed", "partial", "interrupted",
    "response_transformed", "response_previewed", "response_reused",
    "session_id", "model", "requested_model", "provider", "turn_exit_reason", "api_calls"}


class EvidenceRefusal(ValueError):
    pass


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _text(value):
    if (type(value) is not str or not 1 <= len(value.encode("utf-8")) <= 1024
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise EvidenceRefusal("invalid identity")
    return value


def _digest(value):
    if type(value) is not str or re.fullmatch("[0-9a-f]{64}", value) is None:
        raise EvidenceRefusal("invalid digest")
    return value


def emit(document):
    """Emit bounded evidence for capture by the existing result owner."""
    data = _canonical(document)
    if len(data) > MAX_DOCUMENT_BYTES:
        raise EvidenceRefusal("evidence limit")
    sys.stdout.write(data.decode("utf-8") + "\n")
    sys.stdout.flush()


def _report(mode, identity, *, attempted=False, status="NOT_ATTEMPTED", **fields):
    return {"schema": SCHEMA, "mode": mode, "original": dict(identity),
            "native_submit_attempted": attempted, "status": status,
            "provider_dispatch_proven": False, "model_identity_verified": False,
            "account_and_budget_verified": False, "live_acceptance": False,
            **fields}


def inspect_existing(client, sdk, *, implementation_sha, enrollment_request_id):
    """Inspect existing enrollment and current target; never enroll or restore."""
    result = client.inspect_enrollment(implementation_sha, enrollment_request_id)
    result = sdk.validate_enrollment_result(result, implementation_sha=implementation_sha,
        request_id=enrollment_request_id, profile_id=str(client.home),
        principal_id=f"uid:{os.getuid()}", role=ROLE)
    if result["status"] != "ENROLLED":
        raise EvidenceRefusal("existing enrollment unavailable")
    enrolled = result["target"]
    observed = client.observe(enrolled["session_id"])
    if (type(observed) is not dict
            or set(observed) != {"schema", "status", "target"}
            or observed.get("schema") != sdk.conversation_contract(ROLE).native_schema
            or observed.get("status") != "TARGET"):
        raise EvidenceRefusal("target unavailable")
    target = sdk.validate_target(observed["target"])
    if target != enrolled:
        raise EvidenceRefusal("target changed")
    return target


def _admission(value, sdk, client, identity):
    if type(value) is not dict or set(value) != ADMISSION_KEYS:
        raise EvidenceRefusal("invalid admission envelope")
    # Reuse the incumbent receipt validator, including the original session.
    result = sdk._admission(value, client.home, identity["session_id"])
    expected = identity.get("admission_id")
    if expected is not None and result["admission_id"] != expected:
        raise EvidenceRefusal("original admission changed")
    return result


def _refusal_envelope(result):
    if set(result) not in ({"schema", "status"}, {"schema", "status", "reason"}):
        raise EvidenceRefusal("invalid refusal envelope")
    if "reason" in result and (type(result["reason"]) is not str
            or re.fullmatch("[A-Z][A-Z0-9_]{0,63}", result["reason"]) is None):
        raise EvidenceRefusal("invalid refusal reason")


def submit_once(client, sdk, *, implementation_sha, enrollment_request_id,
                submission_id, text, writer=emit):
    """One explicitly new submission. Later invocations must read-original."""
    submission_id = _text(submission_id)
    digest = sdk.input_digest(text)
    target = inspect_existing(client, sdk, implementation_sha=implementation_sha,
                              enrollment_request_id=enrollment_request_id)
    identity = {"session_id": target["session_id"], "submission_id": submission_id,
                "input_sha256": digest}
    # Emit the recovery identity before the attempt. Flush is not a durable
    # receipt. PREPARED alone never proves nonexecution: use read-original.
    writer(_report("submit-once", identity, status="PREPARED", target=target,
                   original_read_required_if_interrupted=True))
    try:
        result = client.submit(target, submission_id, text)
        if (type(result) is not dict
                or result.get("schema") != sdk.conversation_contract(ROLE).native_schema
                or type(result.get("status")) is not str
                or result["status"] not in {"ADMITTED", "REFUSED", "NOT_SUBMITTED", "EFFECT_UNKNOWN"}):
            raise EvidenceRefusal("unusable admission response")
        status, fields = result["status"], {}
        if status == "ADMITTED":
            if set(result) != {"schema", "status", "admission"}:
                raise EvidenceRefusal("invalid admission result")
            fields["admission"] = _admission(result["admission"], sdk, client, identity)
            identity["admission_id"] = fields["admission"]["admission_id"]
        else:
            _refusal_envelope(result)
    except BaseException:
        # Includes interrupted response and all parsing after possible write.
        # No exception, unknown receipt or malformed refusal permits a retry.
        status, fields = "EFFECT_UNKNOWN", {}
    report = _report("submit-once", identity, attempted=True, status=status, **fields)
    writer(report)
    return report


def application_request_id(admission_id, identity):
    """Derived wire correlation only; this creates no request or authority."""
    material = [_text(admission_id)] + [_text(identity[key]) for key in
        ("agent_session_id", "task_id", "turn_id", "api_request_id")]
    return "hermes:" + hashlib.sha256(json.dumps(material, ensure_ascii=False,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def native_tool_evidence(observation, *, expected_tool, admission_id):
    """Describe native callbacks without inventing Fabric or history evidence."""
    empty = {"native_callback_and_commit_observed": False,
             "later_native_request_observed": False,
             "tool_history_content_verified": False}
    if (type(observation) is not dict or observation.get("errors") != []
            or any(observation.get(key) is not False for key in
                   ("overflow", "tool_overflow", "metadata_overflow"))):
        return empty
    executions, commits = observation.get("executions"), observation.get("commits")
    if type(executions) is not list or len(executions) != 1 or type(commits) is not list or len(commits) != 1:
        return empty
    execution, commit = executions[0], commits[0]
    if type(execution) is not dict or type(commit) is not dict:
        return empty
    identity = execution.get("identity")
    if (type(identity) is not dict or set(identity) != set(IDENTITY_KEYS)
            or identity.get("tool_name") != expected_tool or commit.get("identity") != identity
            or execution.get("invalid_fields") != [] or commit.get("invalid_fields") != []
            or execution.get("state") != "returned" or commit.get("state") != "commit_tuple_returned"
            or commit.get("blocked") is not False or commit.get("is_error") is not False
            or commit.get("reported_effect_disposition") not in (None, "none")
            or commit.get("correlation") != {"status": "unique_identity_match",
                "execution_sequence": execution.get("sequence")}):
        return empty
    for key in IDENTITY_KEYS:
        _text(identity[key])
    if (type(execution.get("sequence")) is not int or type(commit.get("sequence")) is not int
            or not 0 < execution["sequence"] < commit["sequence"]):
        return empty
    report = {**empty, "native_callback_and_commit_observed": True,
              "tool_identity": dict(identity)}
    requests = observation.get("observations")
    if type(requests) is not list:
        return report
    matching = [i for i, row in enumerate(requests) if type(row) is dict
        and row.get("invalid_fields", []) == [] and all(
        row.get(key) == identity[key] for key in ("agent_session_id", "turn_id", "api_request_id"))]
    if len(matching) != 1:
        return report
    report["application_correlation"] = {
        "source": "derived_from_native_identity", "verified": False,
        "operation_id": admission_id, "request_id": application_request_id(admission_id, identity)}
    report["later_native_request_observed"] = any(
        type(row) is dict and row.get("invalid_fields", []) == []
        and row.get("agent_session_id") == identity["agent_session_id"]
        and row.get("turn_id") == identity["turn_id"]
        and type(row.get("api_request_id")) is str
        and row["api_request_id"] != identity["api_request_id"]
        for row in requests[matching[0] + 1:])
    return report


def _terminal_metadata(value, sdk, answer):
    """Validate with the native projector; never expose model labels as proof."""
    if (type(value) is not dict or set(value) != {
            "schema", "reported", "invalid_fields", "output", "model_identity_verified"}
            or value["schema"] != "mastermind.hermes_native_terminal_metadata/v1"
            or value["model_identity_verified"] is not False):
        raise EvidenceRefusal("invalid terminal metadata")
    reported, invalid = value["reported"], value["invalid_fields"]
    if (type(reported) is not dict or not set(reported) <= TERMINAL_REPORTED
            or type(invalid) is not list or len(invalid) > len(TERMINAL_REPORTED)
            or any(type(key) is not str or key not in TERMINAL_REPORTED for key in invalid)
            or len(set(invalid)) != len(invalid) or set(invalid) & set(reported)):
        raise EvidenceRefusal("invalid reported metadata")
    projected = sdk._terminal_metadata(reported, answer)
    output = value["output"]
    if (projected["reported"] != reported or projected["invalid_fields"]
            or projected["output"] != output
            or output is not None and (type(output) is not dict
                or set(output) != {"stage", "sha256", "utf8_bytes"}
                or type(output["utf8_bytes"]) is not int)):
        raise EvidenceRefusal("terminal metadata differs from original answer")


def read_original(client, sdk, *, session_id, submission_id, input_sha256,
                  admission_id=None, expected_tool, writer=emit):
    """One read after any owner renewal; never inspect new enrollment or submit."""
    identity = {"session_id": _text(session_id), "submission_id": _text(submission_id),
                "input_sha256": _digest(input_sha256)}
    if admission_id is not None:
        identity["admission_id"] = _text(admission_id)
    expected_tool = _text(expected_tool)
    try:
        result = client.read_original(**identity)
    except Exception:
        report = _report("read-original", identity, status="READ_UNAVAILABLE")
        writer(report)
        return report
    if (type(result) is not dict
            or result.get("schema") != sdk.conversation_contract(ROLE).native_schema
            or type(result.get("status")) is not str
            or result["status"] not in {"OBSERVED", "EFFECT_UNKNOWN", "UNAVAILABLE"}):
        raise EvidenceRefusal("original result unavailable")
    fields = {}
    if result["status"] == "OBSERVED":
        receipt = _admission(result.get("admission"), sdk, client, identity)
        keys = {"schema", "status", "admission"}
        extensions = TERMINAL_EXTENSIONS & result.keys()
        if "answer" in result:
            keys |= {"answer", "successful"}
        keys |= extensions
        if (set(result) != keys
                or (extensions or "answer" in result) and receipt["status"] != "terminal"
                or {"request_observation", "request_observation_error"} <= result.keys()):
            raise EvidenceRefusal("invalid original result envelope")
        identity["admission_id"] = receipt["admission_id"]
        fields["admission"] = receipt
        answer = result.get("answer")
        if "answer" in result:
            if (type(answer) is not str or type(result["successful"]) is not bool
                    or any(ord(c) < 32 and c not in "\n\r\t" for c in answer)):
                raise EvidenceRefusal("invalid original answer")
            data = answer.encode("utf-8")
            if len(data) > sdk.MAX_ANSWER_BYTES:
                raise EvidenceRefusal("answer limit")
            fields["answer"] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
            fields["successful"] = result["successful"]
        if "terminal_metadata" in result:
            _terminal_metadata(result["terminal_metadata"], sdk, answer)
        if "request_observation" in result:
            observation = sdk._request_observation(result["request_observation"], receipt=receipt, role=ROLE)
            fields["request_observation_sha256"] = hashlib.sha256(_canonical(observation)).hexdigest()
            fields["native_tool"] = native_tool_evidence(observation,
                expected_tool=expected_tool, admission_id=receipt["admission_id"])
        elif "request_observation_error" in result:
            if result["request_observation_error"] != "INVALID_RETAINED_OBSERVATION":
                raise EvidenceRefusal("invalid observation error")
            fields["native_observation_unavailable"] = True
    else:
        _refusal_envelope(result)
    report = _report("read-original", identity, status=result["status"], **fields)
    writer(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--expected-pid", type=int, required=True)
    commands = parser.add_subparsers(dest="mode", required=True)
    inspect = commands.add_parser("inspect", help="Read existing native enrollment and target")
    submit = commands.add_parser("submit-once", help="One explicitly new original native admission")
    for command in (inspect, submit):
        command.add_argument("--implementation-sha", required=True)
        command.add_argument("--enrollment-request-id", required=True)
    submit.add_argument("--submission-id", required=True)
    submit.add_argument("--prompt-file", type=Path, required=True)
    read = commands.add_parser("read-original", help="Read one original identity; never resubmit")
    read.add_argument("--session-id", required=True)
    read.add_argument("--submission-id", required=True)
    read.add_argument("--input-sha256", required=True)
    read.add_argument("--admission-id")
    read.add_argument("--expected-tool", required=True)
    args = parser.parse_args(argv)
    # Use the original qualified import environment; do not synthesize roots.
    from integrations.hermes_runtime import native_session_control as sdk
    client = sdk.NativeSecretaryClient(args.home, expected_pid=args.expected_pid, role=ROLE)
    if args.mode == "inspect":
        target = inspect_existing(client, sdk, implementation_sha=args.implementation_sha,
                                  enrollment_request_id=args.enrollment_request_id)
        emit(_report("inspect", {}, status="ENROLLED", target=target))
        return 0
    if args.mode == "submit-once":
        with args.prompt_file.open("rb") as stream:
            data = stream.read(MAX_PROMPT_BYTES + 1)
        if len(data) > MAX_PROMPT_BYTES:
            raise EvidenceRefusal("prompt limit")
        report = submit_once(client, sdk, implementation_sha=args.implementation_sha,
            enrollment_request_id=args.enrollment_request_id, submission_id=args.submission_id,
            text=data.decode("utf-8"))
        return 0 if report["status"] == "ADMITTED" else 3
    report = read_original(client, sdk, session_id=args.session_id,
        submission_id=args.submission_id, input_sha256=args.input_sha256,
        admission_id=args.admission_id, expected_tool=args.expected_tool)
    return 0 if report["status"] == "OBSERVED" else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # Could include failed evidence output after admission. Never label
        # this generic error as nonexecution or permission to submit again.
        emit({"schema": SCHEMA, "status": "INCOMPLETE", "live_acceptance": False,
              "recovery": "read-original if submission was attempted or interrupted"})
        raise SystemExit(2) from None
