"""Both native roles through the real signed BFF and pure Runtime producers.

The private peer is inert. These cases prove source composition, not a live
provider, installed session, publication, enrollment or production acceptance.
"""
import copy
import hashlib
import json

import pytest
from control_plane import native_continuation as nc
from integrations.session_bridge.hermes_native import public_result, validate_public_result
from tests.test_hermes_session_continuation import (
    BINDING, NATIVE_TARGET, build_request, root_event, request_event,
)
from tests.test_mastermind_os_session_transport import (
    make_app, request, auth_fixture, rsa_key, NOW, WORK, ROOT, TARGET,
)


def material(kind):
    family = nc.hermes_family(kind)
    binding = {**BINDING, "schema": family.binding_schema,
               "work_ref": WORK, "root_job_id": ROOT}
    root = root_event(job_id=ROOT)
    target = nc.build_hermes_continuation_target(
        binding=binding, root_event=root, native_target=NATIVE_TARGET)
    source = build_request(binding=binding, root=root)
    event = request_event(source, job_id=ROOT)
    admission = dict(admission_id="original-native-admission",
        ref={k: binding[k] for k in ("profile_id", "session_id")},
        sequence=1, status="queued", outcome=None,
        authority_epoch=3, execution_generation=None)
    queued = public_result(event, source, commit_started=True,
        native_result=dict(schema=family.native_schema, status="ADMITTED", admission=admission))
    terminal = public_result(event, source, commit_started=True,
        native_result=dict(schema=family.native_schema, status="OBSERVED",
            admission={**admission, "status": "terminal", "outcome": "completed",
                       "execution_generation": 2},
            answer="Original " + kind + " answer.", successful=True))
    return dict(kind=kind, family=family, target=target, queued=queued, terminal=terminal,
        selection=dict(work_ref=WORK, root_job_id=ROOT, target_kind=kind),
        arguments=dict(target_ref=target["target_ref"],
            operation_key=target["continuation_operation_key"],
            instruction="Read the original answer.", stop_condition="Return the finding."))


@pytest.fixture(params=nc.HERMES_KINDS)
def native(request):
    return material(request.param)


def test_explicit_role_context_one_send_and_original_read(rsa_key, native):
    app, peer, _, _ = make_app(rsa_key)
    peer.rows, peer.send_result, peer.reply_result = (
        [native["target"]], native["queued"], native["terminal"])
    token = auth_fixture._submit_token(rsa_key)
    status, context = request(app, token, payload={"selection": native["selection"]})
    assert status == 200 and context["data"]["target"] == native["target"]
    assert context["data"]["selection"] == native["selection"]
    assert peer.calls[-1]["arguments"] == {"kind": native["kind"]}
    status, sent = request(app, token, "send", {"arguments": native["arguments"]})
    assert status == 200 and sent["data"] == native["queued"]
    assert peer.calls[-1]["arguments"] == native["arguments"]
    assert len(peer.calls[-1]["arguments"]) == 4
    peer.rows = []  # The original read must not need a present target.
    status, reply = request(app, auth_fixture._read_token(rsa_key), "reply",
        {"arguments": {"operation_key": native["arguments"]["operation_key"]}})
    assert status == 200 and reply["data"] == native["terminal"]
    assert reply["data"]["parent_consumed"] is False
    assert [c["tool"] for c in peer.calls] == [
        "session_targets", "session_send", "session_reply_read"]


@pytest.mark.parametrize("variant,state", [
    ("absent", "UNAVAILABLE"), ("foreign", "UNAVAILABLE"), ("multiple", "AMBIGUOUS")])
def test_role_context_does_not_guess_or_fall_back(rsa_key, native, variant, state):
    app, peer, _, _ = make_app(rsa_key)
    if variant == "absent":
        peer.rows = []
    elif variant == "foreign":
        other = material("hermes_meta" if native["kind"] == "hermes_secretary" else "hermes_secretary")
        peer.rows = [other["target"], {**native["target"], "work_ref": "WS:OTHER"}]
    else:
        row = dict(native["target"])
        row["target_ref"] = native["kind"] + ":" + "f" * 64
        row["generation"] = "f" * 24
        row["continuation_operation_key"] = nc._hermes_operation_key(row["target_ref"])
        peer.rows = [native["target"], row]
    status, body = request(app, auth_fixture._submit_token(rsa_key),
                           payload={"selection": native["selection"]})
    assert status == 200 and body["data"]["selection_state"] == state
    assert body["data"]["target"] is None and body["data"]["capabilities"]["send"] is False
    assert [c["arguments"] for c in peer.calls] == [{"kind": native["kind"]}]


def test_wrong_family_operation_domain_is_not_a_native_target(rsa_key, native):
    app, peer, _, _ = make_app(rsa_key)
    other = nc.hermes_family("hermes_meta" if native["kind"] == "hermes_secretary" else "hermes_secretary")
    encoded = json.dumps(dict(schema=other.operation_schema,
        target_ref=native["target"]["target_ref"]), sort_keys=True, separators=(",", ":")).encode()
    peer.rows = [{**native["target"], "continuation_operation_key":
                  "session-continue-" + hashlib.sha256(encoded).hexdigest()}]
    status, body = request(app, auth_fixture._read_token(rsa_key),
                           payload={"selection": native["selection"]})
    assert status == 503 and body["effect"] == "NONE" and body["data"] is None
    assert len(peer.calls) == 1


@pytest.mark.parametrize("operation", ["context", "send", "reply"])
def test_unsupported_older_peer_never_selects_another_role(rsa_key, native, operation):
    app, peer, _, _ = make_app(rsa_key)
    peer.error = "session_unavailable"
    payload = ({"selection": native["selection"]} if operation == "context" else
        {"arguments": native["arguments"]} if operation == "send" else
        {"arguments": {"operation_key": native["arguments"]["operation_key"]}})
    status, body = request(app, auth_fixture._submit_token(rsa_key), operation, payload)
    assert body["data"] is None
    assert body["effect"] == ("NONE" if operation == "context" else "UNKNOWN")
    assert len(peer.calls) == 1
    assert peer.calls[0]["tool"] == {
        "context": "session_targets", "send": "session_send", "reply": "session_reply_read"}[operation]


@pytest.mark.parametrize("operation", ["send", "reply"])
def test_other_valid_native_family_cannot_answer_the_original(rsa_key, native, operation):
    app, peer, _, _ = make_app(rsa_key)
    other = material("hermes_meta" if native["kind"] == "hermes_secretary" else "hermes_secretary")
    assert validate_public_result(other["terminal"]) == other["terminal"]
    peer.send_result = peer.reply_result = other["terminal"]
    payload = {"arguments": native["arguments"] if operation == "send" else
               {"operation_key": native["arguments"]["operation_key"]}}
    status, body = request(app, auth_fixture._submit_token(rsa_key), operation, payload)
    assert status == 202 and body["effect"] == "UNKNOWN" and body["data"] is None
    assert body["operation_key"] == native["arguments"]["operation_key"]
    assert len(peer.calls) == 1


@pytest.mark.parametrize("schema", [None, [], {}, "unknown"])
def test_malformed_native_result_schema_stays_unknown(rsa_key, native, schema):
    app, peer, _, _ = make_app(rsa_key)
    peer.reply_result = {**native["terminal"], "schema": schema}
    status, body = request(app, auth_fixture._read_token(rsa_key), "reply",
        {"arguments": {"operation_key": native["arguments"]["operation_key"]}})
    assert status == 202 and body["effect"] == "UNKNOWN" and body["data"] is None
    assert [c["tool"] for c in peer.calls] == ["session_reply_read"]


def test_valid_native_result_still_must_match_the_exact_send_target(rsa_key, native):
    app, peer, _, _ = make_app(rsa_key)
    peer.send_result = native["queued"]
    assert validate_public_result(peer.send_result) == peer.send_result
    arguments = {**native["arguments"], "target_ref": native["kind"] + ":" + "f" * 64}
    status, body = request(app, auth_fixture._submit_token(rsa_key), "send", {"arguments": arguments})
    assert status == 202 and body["effect"] == "UNKNOWN" and body["data"] is None
    assert len(peer.calls) == 1 and peer.calls[0]["arguments"] == arguments


@pytest.mark.parametrize("operation", ["send", "reply"])
def test_actual_authority_expiry_after_native_call_withholds_data(rsa_key, native, operation):
    app, peer, clock, _ = make_app(rsa_key)
    peer.send_result, peer.reply_result = native["queued"], native["terminal"]
    peer.after = lambda: clock.__setitem__(0, NOW + 400)
    payload = {"arguments": native["arguments"] if operation == "send" else
               {"operation_key": native["arguments"]["operation_key"]}}
    status, body = request(app, auth_fixture._submit_token(rsa_key), operation, payload)
    assert body["effect"] == "UNKNOWN" and body["data"] is None
    assert body["operation_key"] == native["arguments"]["operation_key"]
    assert len(peer.calls) == 1


def test_one_original_reference_page_keeps_fabric_and_both_native_families(rsa_key):
    app, peer, _, _ = make_app(rsa_key)
    for event_id, kind in [(11, "hermes_secretary"), (10, "hermes_meta")]:
        n = material(kind)
        result = n["terminal"]
        peer.references_result["references"].append(dict(
            read_ref=result["read_ref"], operation_key=result["operation_key"],
            request_ref=result["request_ref"], request_revision=result["request_revision"],
            request_event_id=event_id, requested_at="2026-10-18T00:00:01Z",
            work_ref=WORK, root_job_id=ROOT, target_ref=result["target_ref"], reference_only=True))
    status, body = request(app, auth_fixture._read_token(rsa_key), "references",
                           {"arguments": {"work_ref": WORK}})
    assert status == 200 and len(body["data"]["references"]) == 3
    assert {r["target_ref"].split(":")[0] for r in body["data"]["references"]} == {
        "fabric_attempt", "hermes_secretary", "hermes_meta"}
    assert [c["tool"] for c in peer.calls] == ["session_reply_references"]
