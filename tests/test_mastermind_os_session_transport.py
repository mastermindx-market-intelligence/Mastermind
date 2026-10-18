"""Signed-JWT ASGI tests; the real bridge client uses only an injected peer.

No socket, provider, grant, live Runtime, or browser is contacted. Public
results are checked independently against the pinned canonical owner shapes.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from tests import test_mastermind_executive_app_asgi as auth_fixture
from tests.test_session_bridge_runtime_return import setup
from common.session_bridge_private_contract import private_result
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.mastermind_executive_app.gateway import TRANSPORT_SENT_OK, TRANSPORT_NOT_SENT
from integrations.session_bridge.installed import InstalledSessionBridgeClient

rsa_key = auth_fixture.rsa_key
NOW = auth_fixture.NOW
ROOT = "JOB-100"
WORK = "WS:WORKSPACE-AGENT-PROGRAM"
KEY = "session-continue-" + "b" * 64
TARGET = "fabric_attempt:" + "a" * 64
SELECTION = {"work_ref": WORK, "root_job_id": ROOT}
ARGS = {"target_ref": TARGET, "instruction": "Read the existing result.",
        "stop_condition": "Stop after reporting it.", "operation_key": KEY}


def message_key(kind, key=KEY):
    prefix = "asd-dot-continue-" if kind == "continue" else "asd-native-reply-"
    material = f"mastermind.session_bridge.{kind}.v1\n{key}"
    return prefix + hashlib.sha256(material.encode()).hexdigest()[:40]


def row(**updates):
    value = {"target_ref": TARGET, "kind": "fabric_attempt", "generation": "a" * 24,
             "addressable": True, "continuation_operation_key": KEY,
             "work_ref": WORK, "root_job_id": ROOT}
    value.update(updates)
    return value


def committed(action="POSTED"):
    return {"target_ref": TARGET, "reply_committed": True,
            "carrier": {"reply_committed": True, "action": action,
                        "message_key": message_key("continue"), "fingerprint": "d" * 64,
                        "thread_ts": "1800000000.000001"},
            "attention": {"state": "UNAVAILABLE"}, "read_ref": "opaque-original-read"}


def reply():
    return {"schema": "mastermind.native_reply_read.v1", "read_ref": "opaque-original-read",
            "request_ref": "opaque-original-request", "in_reply_to": message_key("continue"),
            "message_key": message_key("native_reply"), "fingerprint": "e" * 64,
            "text": "The original durable reply.", "next_step": "Review the result.",
            "primary_ts": "1800000000.000002", "reply_committed": True,
            "parent_consumed": False, "operation_key": KEY}


class Audit:
    def __init__(self):
        self.events = []
        self.fail = False

    def emit(self, event):
        self.events.append(event)
        if self.fail:
            raise RuntimeError("PRIVATE-AUDIT-DIAGNOSTIC")


class Peer:
    def __init__(self):
        self.calls = []
        self.rows = [row()]
        self.send_result = committed()
        self.reply_result = reply()
        self.references_result = {
            "schema": "mastermind.session_reply_references.v1",
            "status": "COMPLETE", "next_cursor": None, "high_water": 12,
            "references": [{"read_ref": "session-reply-" + "a" * 64,
                            "operation_key": KEY,
                            "request_ref": "session-bridge-continue:" + "a" * 64,
                            "request_event_id": 12,
                            "request_revision": "c" * 64,
                            "requested_at": "2026-10-18T00:00:00Z",
                            "work_ref": WORK, "root_job_id": ROOT,
                            "target_ref": TARGET, "reference_only": True}],
        }
        self.error = None
        self.transport = TRANSPORT_SENT_OK
        self.after = lambda: None

    async def send_frame(self, path, frame):
        self.calls.append(copy.deepcopy(frame))
        self.after()
        tool = frame["tool"]
        if self.error is not None:
            result = private_result(tool, code=self.error, message="PRIVATE-BACKEND-DIAGNOSTIC")
        else:
            data = {"session_targets": self.rows, "session_send": self.send_result,
                    "session_reply_read": self.reply_result,
                    "session_reply_references": self.references_result}[tool]
            result = private_result(tool, data=copy.deepcopy(data))
        return SimpleNamespace(transport=self.transport, ok=True, result=result)


def make_app(rsa_key, *, app_class=None, policies=None, modify_kwargs=lambda kwargs: None):
    if app_class is None:
        from integrations.mastermind_executive_app.os_session_transport import OsSessionTransportApp
        app_class = OsSessionTransportApp
    clock = [NOW]
    audit = Audit()
    pairs = []
    for policy in policies or (auth_fixture._read_policy(), auth_fixture._submit_policy()):
        authenticator = JwtAuthenticator(policy=policy, jwks_cache=auth_fixture._FakeJwksCache(rsa_key))
        verifier = MastermindTokenVerifier(authenticator=authenticator, policy=policy,
                                           now=lambda: clock[0], audit_sink=audit)
        pairs.append((verifier, authenticator))
    peer = Peer()
    bridge = InstalledSessionBridgeClient("/no-live-session-test.sock", client=peer)
    kwargs = {"read_verifier": pairs[0][0], "read_authenticator": pairs[0][1],
              "submit_verifier": pairs[1][0], "submit_authenticator": pairs[1][1],
              "clock": lambda: clock[0]}
    modify_kwargs(kwargs)
    return app_class(bridge, **kwargs), peer, clock, audit


def request(app, token, operation="context", payload=None, *, raw_body=None,
            header_changes=(), scheme="https", method="POST", raw_path=None,
            query=b"", on_receive=lambda: None, frames=None, scope_changes=None):
    path = "/os/executive/session/" + operation
    if payload is None:
        payload = ({"selection": SELECTION} if operation == "context" else
                   {"arguments": ARGS if operation == "send" else {"operation_key": KEY}})
    body = json.dumps(payload).encode() if raw_body is None else raw_body
    headers = [(b"host", b"mcp.mastermind-x.com"), (b"content-type", b"application/json"),
               (b"authorization", ("Bearer " + token).encode())]
    for name, value in header_changes:
        if value is None:
            headers = [(k, v) for k, v in headers if k != name]
        else:
            headers.append((name, value))
    events = []
    pending = iter(frames) if frames is not None else None

    async def receive():
        on_receive()
        return next(pending) if pending is not None else {"type": "http.request", "body": body}

    async def send(event):
        events.append(event)

    scope = {"type": "http", "asgi": {"version": "3.0"}, "method": method,
             "scheme": scheme, "path": path, "raw_path": raw_path or path.encode(),
             "query_string": query, "headers": headers}
    scope.update(scope_changes or {})
    asyncio.run(app(scope, receive, send))
    assert len([e for e in events if e["type"] == "http.response.start"]) == 1
    start = events[0]
    data = b"".join(e.get("body", b"") for e in events[1:])
    assert len(data) <= 262144
    hs = dict(start["headers"])
    assert hs[b"cache-control"] == b"no-store"
    assert hs[b"referrer-policy"] == b"no-referrer"
    assert hs[b"x-content-type-options"] == b"nosniff"
    assert b"PRIVATE-" not in data and token.encode() not in data
    parsed = json.loads(data) if data else None
    if parsed is not None:
        assert set(parsed) == {"schema", "operation", "ok", "effect", "operation_key", "data", "error"}
        assert parsed["schema"] == "mastermind.os.executive.session_result.v1"
        assert parsed["operation"] == operation
    return start["status"], parsed


@pytest.mark.parametrize("submit", [False, True])
def test_context_exact_selected_target_and_real_authority(rsa_key, submit):
    app, peer, _, _ = make_app(rsa_key)
    token = (auth_fixture._submit_token if submit else auth_fixture._read_token)(rsa_key)
    status, result = request(app, token)
    assert status == 200 and result["ok"] and result["effect"] == "NONE"
    data = result["data"]
    assert set(data) == {"schema", "principal_scope", "verified_expiry", "selection",
                         "selection_state", "target", "capabilities"}
    assert data["selection_state"] == "RESOLVED" and data["target"] == row()
    assert data["selection"] == SELECTION and data["verified_expiry"] == NOW + 300
    assert data["capabilities"] == {"send": submit, "reply_read": True, "stop": False}
    assert len(peer.calls) == 1 and peer.calls[0]["arguments"] == {"kind": "fabric_attempt"}
    assert peer.calls[0]["principal"]["policy_id"] == ("bsc-e1-test-submit" if submit else "bsc-e1-test-read")


@pytest.mark.parametrize("rows,state", [([], "UNAVAILABLE"),
    ([row(root_job_id="JOB-foreign")], "UNAVAILABLE"),
    ([row(work_ref="WS:OTHER")], "UNAVAILABLE"),
    ([row(), row(target_ref="fabric_attempt:" + "c" * 64, generation="c" * 24,
                 continuation_operation_key="session-continue-" + "c" * 64)], "AMBIGUOUS")])
def test_selection_never_guesses_from_zero_foreign_or_multiple_rows(rsa_key, rows, state):
    app, peer, _, _ = make_app(rsa_key)
    peer.rows = rows
    status, result = request(app, auth_fixture._submit_token(rsa_key))
    assert status == 200 and result["data"]["selection_state"] == state
    assert result["data"]["target"] is None and not result["data"]["capabilities"]["send"]


@pytest.mark.parametrize("rows", [[row(), row()], [row(generation="c" * 24)],
    [row(kind="codex")], [row(addressable=1)], [row(extra="private")],
    [row(work_ref="bad")], [row(root_job_id="bad")], [row()] * 257,
    [row(), row(target_ref="fabric_attempt:" + "c" * 64, generation="c" * 24)]])
def test_bad_target_projection_fails_closed(rsa_key, rows):
    app, peer, _, _ = make_app(rsa_key)
    peer.rows = rows
    status, result = request(app, auth_fixture._read_token(rsa_key))
    assert status == 503 and result["effect"] == "NONE" and result["data"] is None


@pytest.mark.parametrize("action", ["POSTED", "RECOVERED", "DUPLICATE"])
def test_send_accepts_exact_canonical_committed_actions_without_attention_claim(rsa_key, action):
    app, peer, _, _ = make_app(rsa_key)
    peer.send_result = committed(action)
    status, result = request(app, auth_fixture._submit_token(rsa_key), "send")
    assert status == 200 and result["effect"] == "CONTINUATION_COMMITTED"
    assert result["operation_key"] == KEY and result["data"] == committed(action)
    assert len(peer.calls) == 1 and peer.calls[0]["arguments"] == ARGS


@pytest.mark.parametrize("change", [
    lambda r: r.update(target_ref="fabric_attempt:" + "f" * 64),
    lambda r: r.update(reply_committed=False),
    lambda r: r["carrier"].update(action="CREATED"),
    lambda r: r["carrier"].update(message_key="foreign"),
    lambda r: r["carrier"].update(fingerprint="bad"),
    lambda r: r["attention"].update(state="DELIVERED"),
    lambda r: r.update(extra="private"),
])
def test_malformed_or_foreign_commit_is_unknown(rsa_key, change):
    app, peer, _, _ = make_app(rsa_key)
    change(peer.send_result)
    status, result = request(app, auth_fixture._submit_token(rsa_key), "send")
    assert status == 202 and result["effect"] == "UNKNOWN" and result["operation_key"] == KEY
    assert result["data"] is None and len(peer.calls) == 1


@pytest.mark.parametrize("code", ["backend_unavailable", "native_target_stale", "permission_refused", "reply_unavailable", "effect_unknown"])
def test_entered_private_send_errors_never_infer_absence(rsa_key, code):
    app, peer, _, _ = make_app(rsa_key)
    peer.error = code
    status, result = request(app, auth_fixture._submit_token(rsa_key), "send")
    assert status == 202 and result["effect"] == "UNKNOWN" and result["operation_key"] == KEY
    assert result["error"]["code"] == "effect_unknown" and len(peer.calls) == 1


def test_not_sent_private_error_remains_conservative_after_entering_bridge(rsa_key):
    app, peer, _, _ = make_app(rsa_key)
    peer.transport = TRANSPORT_NOT_SENT
    status, result = request(app, auth_fixture._submit_token(rsa_key), "send")
    assert status == 202 and result["effect"] == "UNKNOWN"


@pytest.mark.parametrize("stage", ["before", "after"])
@pytest.mark.parametrize("operation", ["context", "send", "reply"])
def test_expiry_across_await_preserves_effect_boundary(rsa_key, stage, operation):
    app, peer, clock, _ = make_app(rsa_key)
    expire = lambda: clock.__setitem__(0, NOW + 400)
    if stage == "after":
        peer.after = expire
    status, result = request(app, auth_fixture._submit_token(rsa_key), operation,
                            on_receive=expire if stage == "before" else lambda: None)
    assert result["ok"] is False and result["data"] is None
    assert result["effect"] == ("UNKNOWN" if operation == "reply" or
                                (operation == "send" and stage == "after") else "NONE")
    assert len(peer.calls) == (1 if stage == "after" else 0)


@pytest.mark.parametrize("operation", ["context", "send", "reply"])
def test_audit_failure_closes_before_private_call(rsa_key, operation):
    app, peer, _, audit = make_app(rsa_key)
    audit.fail = True
    status, result = request(app, auth_fixture._submit_token(rsa_key), operation)
    assert status in (401, 403) and not peer.calls
    assert result["effect"] == ("UNKNOWN" if operation == "reply" else "NONE")


def test_verified_read_only_token_recovers_submit_policy_request_across_private_bridge(
    rsa_key, setup, monkeypatch,
):
    """Real JWT policy pairs -> private frame -> Runtime provenance -> Dialogue read."""
    import time
    from pathlib import Path

    from integrations.business_mcp_auth.principal_projection import principal_projection
    from integrations.mastermind_executive_app.gateway import AppPolicies
    from common.session_bridge_private_contract import PRIVATE_SCHEMA
    from integrations.session_bridge.installed import (
        InstalledSessionBridgeProvider, principal_frame)
    from integrations.session_bridge.native_read import NativeReplyReader
    from integrations.session_bridge.runtime_return import RuntimeSessionReturn
    from tests.test_session_bridge_runtime_return import populate

    s = setup
    app, peer, clock, _ = make_app(rsa_key)
    now = int(time.time())
    monkeypatch.setattr(auth_fixture, "NOW", now)
    clock[0] = now
    # The stored request must be admitted under the actual authenticated SEND
    # policy identity, not a fabricated policy alias.
    send_token = auth_fixture._submit_token(rsa_key)
    submit_principal = asyncio.run(
        app._submit_pair[1].verify_token(send_token, now=now))
    s.principal = submit_principal
    s.projection = principal_projection(submit_principal)
    # This is host-owned policy pairing, not an attribute supplied by the
    # caller's private principal frame.
    s.owner = RuntimeSessionReturn(
        s.runtime, fabric=s.owner.fabric, codex=s.owner.codex,
        socket_path=s.owner.socket_path, service_call=s.service,
        authorized_policies=AppPolicies(
            read=app._read_pair[1].policy,
            submit=app._submit_pair[1].policy))
    read_ref = populate(s)
    before = [e.to_dict() for e in s.runtime.events.list_events(job_id=s.epoch.job_id)]
    s.enabled[0] = False
    s.service.calls.clear()

    def no_effect(*_):
        raise AssertionError("reply recovery cannot submit or rediscover targets")

    reader = NativeReplyReader(s.owner,
        socket_path=Path("/private/tmp/verified-policy-transition.sock"),
        service_call=s.service, projected_principal=True)
    provider = InstalledSessionBridgeProvider(
        target_projector=no_effect, reply_handler=no_effect,
        summon_handler=no_effect, reply_read_handler=reader)
    frames = []

    async def send_frame(_path, frame):
        frames.append(copy.deepcopy(frame))
        return SimpleNamespace(transport=TRANSPORT_SENT_OK, ok=True,
                               result=await provider.handle_frame(frame))

    peer.send_frame = send_frame
    read_token = auth_fixture._read_token(rsa_key)
    status, recovered = request(app, read_token, "reply",
        {"arguments": {"operation_key": s.args["operation_key"]}})
    assert status == 200 and recovered["ok"]
    assert recovered["operation_key"] == s.args["operation_key"]
    assert recovered["data"]["read_ref"] == read_ref
    assert recovered["data"]["text"] == "The bounded finding is confirmed."
    assert recovered["data"]["parent_consumed"] is False
    assert [x["tool"] for x in frames] == ["session_reply_read"]
    assert frames[0]["principal"]["policy_id"] == "bsc-e1-test-read"
    assert s.service.calls and all(c["operation"] == "read_thread" for c in s.service.calls)

    # A separately valid, signed READ policy for the same subject/resource
    # must NOT claim this operation unless it is the approved counterpart.
    other_policy = auth_fixture._read_policy(policy_id="unpaired-read-policy")
    other_auth = JwtAuthenticator(
        policy=other_policy, jwks_cache=auth_fixture._FakeJwksCache(rsa_key))
    other_principal = asyncio.run(other_auth.verify_token(read_token, now=now))
    previous_reads = len(s.service.calls)
    foreign = asyncio.run(provider.handle_frame({
        "schema": PRIVATE_SCHEMA, "tool": "session_reply_read",
        "principal": principal_frame(other_principal),
        "arguments": {"operation_key": s.args["operation_key"]}}))
    assert foreign["ok"] is False and foreign["error"]["code"] == "reply_unavailable"
    assert len(s.service.calls) == previous_reads

    denied_status, denied = request(app, read_token, "send")
    assert denied_status in (401, 403) and not denied["ok"]
    assert len(frames) == 1
    revoked = auth_fixture._token(rsa_key, scope="")
    revoked_status, revoked_result = request(app, revoked, "reply",
        {"arguments": {"operation_key": s.args["operation_key"]}})
    assert revoked_status in (401, 403) and not revoked_result["ok"]
    assert len(frames) == 1

    # A READ credential that expires during the awaited private carrier read
    # must never release a reply body, even if the backend found the answer.
    s.service.on_read = lambda: clock.__setitem__(0, now + 400)
    withheld_status, withheld = request(app, read_token, "reply",
        {"arguments": {"operation_key": s.args["operation_key"]}})
    assert withheld_status == 202 and not withheld["ok"]
    assert withheld["effect"] == "UNKNOWN" and withheld["data"] is None
    assert len(frames) == 2 and frames[-1]["tool"] == "session_reply_read"
    assert [e.to_dict() for e in s.runtime.events.list_events(job_id=s.epoch.job_id)] == before


def test_read_only_token_cannot_send(rsa_key):
    app, peer, _, _ = make_app(rsa_key)
    status, result = request(app, auth_fixture._read_token(rsa_key), "send")
    assert status in (401, 403) and result["effect"] == "NONE" and not peer.calls


@pytest.mark.parametrize("submit", [False, True])
def test_same_key_reply_recovery_does_not_rediscover_or_send(rsa_key, submit):
    app, peer, _, _ = make_app(rsa_key)
    peer.rows = []  # Current target disappearance does not erase committed recovery.
    token = (auth_fixture._submit_token if submit else auth_fixture._read_token)(rsa_key)
    status, result = request(app, token, "reply")
    assert status == 200 and result["data"] == reply()
    assert result["effect"] == "CONTINUATION_COMMITTED" and result["operation_key"] == KEY
    assert [c["tool"] for c in peer.calls] == ["session_reply_read"]
    assert peer.calls[0]["arguments"] == {"operation_key": KEY}


@pytest.mark.parametrize("change", [
    lambda r: r.update(operation_key="session-continue-" + "f" * 64),
    lambda r: r.update(in_reply_to="foreign"),
    lambda r: r.update(message_key="foreign"),
    lambda r: r.update(parent_consumed=True),
    lambda r: r.update(text="x" * 20000),
    lambda r: r.update(next_step="🧪" * 3000),
])
def test_foreign_malformed_or_oversized_reply_preserves_unknown(rsa_key, change):
    app, peer, _, _ = make_app(rsa_key)
    change(peer.reply_result)
    status, result = request(app, auth_fixture._read_token(rsa_key), "reply")
    assert status == 202 and result["effect"] == "UNKNOWN" and result["operation_key"] == KEY


def test_reply_unavailable_is_not_absence_or_retry_permission(rsa_key):
    app, peer, _, _ = make_app(rsa_key)
    peer.error = "reply_unavailable"
    status, result = request(app, auth_fixture._read_token(rsa_key), "reply")
    assert status == 202 and result["effect"] == "UNKNOWN"
    assert result["operation_key"] == KEY and len(peer.calls) == 1


@pytest.mark.parametrize("change", [{"target_ref": "codex:other"}, {"operation_key": "invented"},
    {"instruction": "x" * 701}, {"stop_condition": " "}, {"scope_change": False}])
def test_invalid_send_arguments_never_enter_bridge(rsa_key, change):
    app, peer, _, _ = make_app(rsa_key)
    status, result = request(app, auth_fixture._submit_token(rsa_key), "send",
                            {"arguments": {**ARGS, **change}})
    assert status == 400 and result["effect"] == "NONE" and not peer.calls


@pytest.mark.parametrize("body", [b'{"selection":{},"selection":{}}', b'NaN', b'[]', b'{' + b'x' * 65536])
def test_bad_or_oversized_body_is_refused(rsa_key, body):
    app, peer, _, _ = make_app(rsa_key)
    status, result = request(app, auth_fixture._read_token(rsa_key), raw_body=body)
    assert status == 400 and result["effect"] == "NONE" and not peer.calls


@pytest.mark.parametrize("changes", [[(b"host", b"foreign")], [(b"origin", b"https://foreign")],
    [(b"origin", b"https://mcp.mastermind-x.com")] * 2,
    [(b"content-type", b"application/json")], [(b"content-encoding", b"gzip")],
    [(b"authorization", b"Bearer duplicate")]])
def test_transport_header_fences_precede_private_effect(rsa_key, changes):
    app, peer, _, _ = make_app(rsa_key)
    status, result = request(app, auth_fixture._submit_token(rsa_key), "send", header_changes=changes)
    assert status in (400, 403) and result["effect"] == "NONE" and not peer.calls


@pytest.mark.parametrize("kwargs", [{"operation": "stop"}, {"scheme": "http"},
    {"method": "GET"}, {"query": b"x=1"}, {"raw_path": b"/os/executive/session/%63ontext"}])
def test_no_stop_or_alternate_route(rsa_key, kwargs):
    app, peer, _, _ = make_app(rsa_key)
    status, _ = request(app, auth_fixture._read_token(rsa_key), **kwargs)
    assert status == 404 and not peer.calls


def test_frame_budget_stops_before_private_call(rsa_key):
    app, peer, _, _ = make_app(rsa_key)
    frames = [{"type": "http.request", "body": b" ", "more_body": True}] * 33
    status, result = request(app, auth_fixture._read_token(rsa_key), frames=frames)
    assert status == 400 and not peer.calls


@pytest.mark.parametrize("operation", ["context", "send", "reply"])
def test_audit_failure_after_private_call_withholds_receipt(rsa_key, operation):
    app, peer, _, audit = make_app(rsa_key)
    peer.after = lambda: setattr(audit, "fail", True)
    status, result = request(app, auth_fixture._submit_token(rsa_key), operation)
    assert result["ok"] is False and result["data"] is None
    assert result["effect"] == ("NONE" if operation == "context" else "UNKNOWN")
    assert len(peer.calls) == 1


@pytest.mark.parametrize("claims", [{"sub": "foreign-subject"}, {"aud": "https://foreign.example/mcp"},
                                     {"iss": "https://foreign.example"}, {"exp": NOW - 100}])
def test_foreign_or_expired_signed_identity_never_falls_back_to_authority(rsa_key, claims):
    app, peer, _, _ = make_app(rsa_key)
    status, result = request(app, auth_fixture._submit_token(rsa_key, **claims), "send")
    assert status == 401 and result["effect"] == "NONE" and not peer.calls


def test_context_consumes_real_runtime_projection_fields(rsa_key):
    from tests.test_session_bridge_runtime_owner import projector
    owner, _ = projector()
    target = owner.list_targets()[0]
    app, peer, _, _ = make_app(rsa_key)
    peer.rows = [target.public_projection()]
    selection = {"work_ref": target.source.work_ref, "root_job_id": target.epoch.root_job_id}
    status, result = request(app, auth_fixture._submit_token(rsa_key), payload={"selection": selection})
    assert status == 200 and result["data"]["target"] == target.public_projection()


def test_instruction_boundary_preserves_exact_text_and_no_cancel_field(rsa_key):
    app, peer, _, _ = make_app(rsa_key)
    args = {**ARGS, "instruction": " " + "🧪" * 698 + " ", "stop_condition": " Stop. "}
    status, result = request(app, auth_fixture._submit_token(rsa_key), "send", {"arguments": args})
    assert status == 200 and peer.calls[0]["arguments"] == args


@pytest.mark.parametrize("selection", [{}, {**SELECTION, "target_ref": TARGET},
                                        {**SELECTION, "root_job_id": "latest"}])
def test_invalid_selection_has_no_private_call(rsa_key, selection):
    app, peer, _, _ = make_app(rsa_key)
    status, result = request(app, auth_fixture._read_token(rsa_key), payload={"selection": selection})
    assert status == 400 and not peer.calls


def test_cancellation_is_not_translated_into_absence(rsa_key):
    app, peer, _, _ = make_app(rsa_key)
    def cancel():
        raise asyncio.CancelledError()
    peer.after = cancel
    with pytest.raises(asyncio.CancelledError):
        request(app, auth_fixture._submit_token(rsa_key), "send")
    assert len(peer.calls) == 1


@pytest.mark.parametrize("field", ["read_verifier", "submit_verifier", "read_authenticator", "submit_authenticator"])
def test_nominal_auth_dependencies_are_required(rsa_key, field):
    with pytest.raises((TypeError, ValueError)):
        make_app(rsa_key, modify_kwargs=lambda kw: kw.__setitem__(field, SimpleNamespace()))


def test_constructor_rejects_split_audited_and_authenticator_policy_identity(rsa_key):
    foreign = JwtAuthenticator(policy=auth_fixture._submit_policy(policy_id="different-policy"),
                               jwks_cache=auth_fixture._FakeJwksCache(rsa_key))
    with pytest.raises((TypeError, ValueError)):
        make_app(rsa_key, modify_kwargs=lambda kw: kw.__setitem__("submit_authenticator", foreign))


def test_constructor_rejects_cross_resource_policy_pair(rsa_key):
    foreign_resource = "https://foreign.example/mcp"
    foreign = auth_fixture._submit_policy(resource=foreign_resource,
        resource_metadata_url=foreign_resource + "/.well-known/oauth-protected-resource")
    with pytest.raises((TypeError, ValueError)):
        make_app(rsa_key, policies=(auth_fixture._read_policy(), foreign))


def test_constructor_rejects_expanded_read_scope_policy(rsa_key):
    expanded = auth_fixture._read_policy(required_scopes=[auth_fixture.READ_SCOPE, "workspace.read"])
    with pytest.raises((TypeError, ValueError)):
        make_app(rsa_key, policies=(expanded, auth_fixture._submit_policy()))


@pytest.mark.parametrize("operation", ["context", "send", "reply"])
@pytest.mark.parametrize("expire_on_call", [4, 6])
def test_expiry_during_authenticator_await_is_rechecked_before_release(rsa_key, operation, expire_on_call, monkeypatch):
    app, peer, clock, _ = make_app(rsa_key)
    authenticator = app._submit_pair[1]
    original = authenticator.verify_token
    calls = 0

    async def delayed(token, *, now):
        nonlocal calls
        calls += 1
        principal = await original(token, now=now)
        if calls == expire_on_call:
            clock[0] = NOW + 400
        return principal

    monkeypatch.setattr(authenticator, "verify_token", delayed)
    status, result = request(app, auth_fixture._submit_token(rsa_key), operation)
    assert result["ok"] is False and result["data"] is None
    assert result["effect"] == ("UNKNOWN" if operation == "reply" or
                                (operation == "send" and expire_on_call == 6) else "NONE")
    assert len(peer.calls) == (0 if expire_on_call == 4 else 1)


@pytest.mark.parametrize("operation", ["context", "send", "reply"])
def test_deep_json_body_has_closed_failure_before_private_effect(rsa_key, operation):
    app, peer, _, _ = make_app(rsa_key)
    raw = b'{"x":' + b'[' * 1500 + b'0' + b']' * 1500 + b'}'
    status, result = request(app, auth_fixture._submit_token(rsa_key), operation, raw_body=raw)
    assert status == 400 and not peer.calls
    assert result["effect"] == ("UNKNOWN" if operation == "reply" else "NONE")


@pytest.mark.parametrize("operation", ["context", "send", "reply"])
def test_receive_exception_has_closed_failure_before_private_effect(rsa_key, operation):
    app, peer, _, _ = make_app(rsa_key)
    def disconnected():
        raise RuntimeError("PRIVATE-RECEIVE-DIAGNOSTIC")
    status, result = request(app, auth_fixture._submit_token(rsa_key), operation, on_receive=disconnected)
    assert status == 400 and not peer.calls
    assert result["effect"] == ("UNKNOWN" if operation == "reply" else "NONE")


@pytest.mark.parametrize("change,retained", [
    ({"operation_key": "invented"}, None),
    ({"target_ref": "codex:other"}, KEY),
])
def test_review_invalid_send_retains_only_canonical_original_key(rsa_key, change, retained):
    app, peer, _, _ = make_app(rsa_key)
    status, result = request(app, auth_fixture._submit_token(rsa_key), "send",
                            {"arguments": {**ARGS, **change}})
    assert status == 400 and result["effect"] == "NONE" and not peer.calls
    assert result["operation_key"] == retained


@pytest.mark.parametrize("operation", ["context", "send", "reply"])
@pytest.mark.parametrize("headers", [
    [(b"host", b"mcp.mastermind-x.com"), (b"malformed",)],
    [(b"host", b"mcp.mastermind-x.com"),
     (b"content-type", b"application/json"), (b"authorization", "Bearer x")],
    [("host", b"mcp.mastermind-x.com")],
    [(b"host", b"mcp.mastermind-x.com"), (b"content-type", 17),
     (b"authorization", b"Bearer x")],
    {"host": b"mcp.mastermind-x.com"},
])
def test_review_malformed_host_headers_refuse_before_auth_or_effect(rsa_key, operation, headers):
    app, peer, _, audit = make_app(rsa_key)
    status, result = request(app, auth_fixture._submit_token(rsa_key), operation,
                            scope_changes={"headers": headers})
    assert status == 403 and result["error"]["code"] == "transport_refused"
    assert result["effect"] == ("UNKNOWN" if operation == "reply" else "NONE")
    assert not peer.calls and not audit.events


@pytest.mark.parametrize("path", [["/os/executive/session/send"], {"path": "send"}])
def test_review_unhashable_host_path_is_unrecognized(rsa_key, path):
    app, peer, _, audit = make_app(rsa_key)
    status, result = request(app, auth_fixture._submit_token(rsa_key), "send",
                            scope_changes={"path": path})
    assert status == 404 and result is None and not peer.calls and not audit.events


@pytest.mark.parametrize("scope_type", ["lifespan", "websocket"])
def test_review_http_leaf_does_not_consume_host_owned_non_http_scope(rsa_key, scope_type):
    app, peer, _, audit = make_app(rsa_key)
    async def forbidden(*args):
        pytest.fail("HTTP leaf must not own host lifespan or websocket delivery")
    asyncio.run(app({"type": scope_type}, forbidden, forbidden))
    assert not peer.calls and not audit.events


def test_review_committed_continuation_preserves_unknown_attention(rsa_key):
    app, peer, _, _ = make_app(rsa_key)
    peer.send_result["attention"] = {"state": "EFFECT_UNKNOWN"}
    status, result = request(app, auth_fixture._submit_token(rsa_key), "send")
    assert status == 200 and result["effect"] == "CONTINUATION_COMMITTED"
    assert result["data"]["attention"] == {"state": "EFFECT_UNKNOWN"}
    assert len(peer.calls) == 1


def test_review_constructor_rejects_same_authenticator_with_split_audited_policy(rsa_key):
    def split_policy(kwargs):
        kwargs["submit_verifier"]._policy = auth_fixture._submit_policy(policy_id="different-policy")
    with pytest.raises(ValueError, match="one composition"):
        make_app(rsa_key, modify_kwargs=split_policy)



@pytest.mark.parametrize("submit", [False, True])
def test_read_only_original_references_authenticated_no_send(rsa_key, submit):
    app, peer, _, _ = make_app(rsa_key)
    token = (auth_fixture._submit_token(rsa_key) if submit
             else auth_fixture._read_token(rsa_key))
    status, result = request(
        app, token, "references",
        {"arguments": {"work_ref": WORK, "root_job_id": ROOT}})
    assert status == 200 and result["effect"] == "NONE"
    assert result["operation"] == "references" and result["operation_key"] is None
    assert result["data"]["references"] == peer.references_result["references"]
    assert result["data"]["references"][0]["reference_only"] is True
    assert len(peer.calls) == 1
    assert peer.calls[0]["tool"] == "session_reply_references"
    assert peer.calls[0]["arguments"] == {"work_ref": WORK, "root_job_id": ROOT}
    assert peer.calls[0]["principal"]["policy_id"] == (
        "bsc-e1-test-submit" if submit else "bsc-e1-test-read")


@pytest.mark.parametrize("arguments", [
    {}, {"work_ref": "bad"}, {"work_ref": WORK, "root_job_id": "bad"},
    {"work_ref": WORK, "page_size": True},
    {"work_ref": WORK, "page_size": 33},
    {"work_ref": WORK, "unknown": "value"},
])
def test_original_reference_http_validation_before_private_effect(rsa_key, arguments):
    app, peer, _, _ = make_app(rsa_key)
    status, result = request(app, auth_fixture._read_token(rsa_key),
                             "references", {"arguments": arguments})
    assert status == 400 and result["effect"] == "NONE"
    assert result["data"] is None and not peer.calls


def test_original_references_foreign_projection_is_withheld(rsa_key):
    app, peer, _, _ = make_app(rsa_key)
    peer.references_result["references"][0]["work_ref"] = "WS:FOREIGN"
    status, result = request(
        app, auth_fixture._read_token(rsa_key), "references",
        {"arguments": {"work_ref": WORK}})
    assert status == 503 and result["effect"] == "NONE"
    assert result["data"] is None
    assert len(peer.calls) == 1 and peer.calls[0]["tool"] == "session_reply_references"
