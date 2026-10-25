"""Native Link transport tests use real child processes and Unix sockets.

The pytest process stands in for the enrolled Chrome parent. This qualifies the
transport predicate, not Chrome's actual installed launch topology.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
import json
import os
import select
import socket
import subprocess
import sys
import tempfile
import threading
import time

import pytest

from control_plane.codex_worker import ProcessInspector, ProcessIdentityError
from integrations.mastermind_browser_link.native_bridge import load_enrollment, require_peer_uid
from integrations.mastermind_browser_link.native_channel import (
    COMMAND_SCHEMA, HELLO_SCHEMA, INVENTORY_SCHEMA, RESULT_SCHEMA,
    Deadline, LinkEnrollment, LinkProtocolError, NativeHostError,
    read_frame, write_frame, validate_command, validate_inventory, validate_result,
)
from integrations.mastermind_browser_link.tool_contract import (
    ACTION_TOOL, INVENTORY_TOOL, READ_TOOL, LINK_TOOL_SCHEMA_DIGEST,
)
from integrations.workbench_browser_mcp import link_session as module
from integrations.workbench_browser_mcp.link_session import BrowserLinkSession
from integrations.workbench_browser_mcp.relay import BrowserRelayError, BrowserRequestRefused

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = "a" * 32
INSTANCE = "b" * 64


def until(predicate):
    end = time.monotonic() + 4
    while not predicate():
        if time.monotonic() >= end:
            raise AssertionError("condition did not complete")
        time.sleep(0.01)


def send(stream, value):
    write_frame(stream, value, deadline=Deadline(time.monotonic() + 4))


def receive(stream):
    return read_frame(stream, deadline=Deadline(time.monotonic() + 4))


class Peer:
    def __init__(self, enrollment, config, generation="generation-1"):
        self.generation = generation
        self.process = subprocess.Popen(
            [sys.executable, "-I", "-S", str(ROOT / "scripts/mastermind_browser_link_native_host.py"),
             "--config", str(config), f"chrome-extension://{enrollment.extension_id}/"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            bufsize=0,
        )
        self.hello = {"schema": HELLO_SCHEMA, "protocol_version": 2,
                      "extension_id": enrollment.extension_id, "instance_ref": enrollment.instance_id,
                      "connection_generation": generation}
        self.write_gate = threading.Lock()

    def send(self, value):
        with self.write_gate:
            send(self.process.stdin, value)

    def receive(self):
        return receive(self.process.stdout)

    def ready(self):
        self.send(self.hello)
        reply = self.receive()
        assert reply == {"schema": "mastermind.browser_link.ready.v2",
                         "connection_generation": self.generation}

    def result(self, command, effect="APPLIED", status="completed", **extra):
        self.send({"schema": RESULT_SCHEMA, "request_id": command["request_id"],
                   "connection_generation": self.generation,
                   "status": status, "effect": effect, **extra})

    def close(self):
        if not self.process.stdin.closed:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=6)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=2)
        self.process.stdout.close()
        self.process.stderr.close()


@contextmanager
def connected(*, timeout=1.5, instance=INSTANCE):
    # Darwin's Unix path limit is 103 bytes.
    with tempfile.TemporaryDirectory(prefix="mmx-link-", dir="/tmp") as directory:
        parent = Path(directory)
        parent.chmod(0o700)
        enrollment = LinkEnrollment(EXTENSION, instance, parent / "native.sock")
        config = parent / "enrollment.json"
        config.write_text(json.dumps(enrollment.document()))
        config.chmod(0o600)
        chrome = ProcessInspector().inspect(os.getpid())
        session = BrowserLinkSession(
            enrollment=enrollment, chrome_pid=os.getpid(),
            chrome_start_identity=chrome.start_identity, holder_ref="resource-holder",
            timeout_seconds=timeout,
        )
        receipt = session.start()
        assert receipt.tool_schema_digest == LINK_TOOL_SCHEMA_DIGEST
        peer = Peer(enrollment, config)
        try:
            peer.ready()
            until(lambda: session._active is not None)
            yield session, peer, config
        finally:
            session.close()
            peer.close()
        assert not enrollment.socket_path.exists()


def arguments(tab=7, generation="generation-1", command="scroll"):
    return {"target": {"connection_generation": generation, "tab_id": tab,
                       "consent_id": f"consent-{tab}", "document_revision": 0},
            "expires_at_ms": int(time.time() * 1000) + 20_000,
            "command": command,
            "args": {"delta_x": 0, "delta_y": 100} if command == "scroll" else {}}


def test_real_kernel_uid_check():
    left, right = socket.socketpair()
    with left, right:
        require_peer_uid(left, os.geteuid())
        with pytest.raises(LinkProtocolError):
            require_peer_uid(left, os.geteuid() + 1)


def test_correlated_inventory_and_distinct_tabs_can_be_in_flight():
    with connected() as (session, peer, _), ThreadPoolExecutor(3) as pool:
        inventory = pool.submit(session.call_with_identity, "observe-1", INVENTORY_TOOL, {})
        query = peer.receive()
        peer.send({"schema": INVENTORY_SCHEMA, "connection_generation": peer.generation,
                   "shared_tabs": []})  # advisory push cannot complete the observation
        assert not inventory.done()
        peer.send({"schema": INVENTORY_SCHEMA, "connection_generation": peer.generation,
                   "request_id": query["request_id"], "shared_tabs": []})
        assert inventory.result(timeout=3)["structuredContent"]["instance_id"] == INSTANCE
        first = pool.submit(session.call_with_identity, "action-1", ACTION_TOOL, arguments(7))
        second = pool.submit(session.call_with_identity, "action-2", ACTION_TOOL, arguments(8))
        commands = [peer.receive(), peer.receive()]
        assert {item["tab_id"] for item in commands} == {7, 8}
        assert {item["request_id"] for item in commands} == {"action-1", "action-2"}
        assert len({item["writer"]["fence"] for item in commands}) == 2
        with pytest.raises(BrowserRequestRefused):
            session.call_with_identity("action-3", ACTION_TOOL, arguments(7))
        for command in reversed(commands):
            peer.result(command)
        assert first.result(timeout=3)["structuredContent"]["effect_state"] == "APPLIED"
        assert second.result(timeout=3)["structuredContent"]["effect_state"] == "APPLIED"


def test_duplicate_id_never_dispatches_or_claims_no_effect():
    with connected() as (session, peer, _), ThreadPoolExecutor(1) as pool:
        future = pool.submit(session.call_with_identity, "original", ACTION_TOOL, arguments())
        command = peer.receive()
        with pytest.raises(BrowserRelayError) as pending:
            session.call_with_identity("original", ACTION_TOOL, arguments())
        assert not isinstance(pending.value, BrowserRequestRefused)
        peer.result(command)
        assert future.result(timeout=3)["structuredContent"]["effect_state"] == "APPLIED"
        with pytest.raises(BrowserRelayError) as completed:
            session.call_with_identity("original", ACTION_TOOL, arguments())
        assert not isinstance(completed.value, BrowserRequestRefused)
        assert not select.select([peer.process.stdout], [], [], 0.05)[0]


@pytest.mark.parametrize("ending", ["eof", "contradiction"])
def test_first_qualified_receipt_survives_disconnect_and_conflict(monkeypatch, ending):
    release_waiter = threading.Event()
    class HeldEvent:
        def __init__(self):
            self.received = threading.Event()
        def set(self):
            self.received.set()
        def wait(self, timeout):
            completed = self.received.wait(timeout)
            assert release_waiter.wait(5)
            return completed
    original = module._Pending
    monkeypatch.setattr(module, "_Pending", lambda kind, tab_id: original(kind, tab_id, event=HeldEvent()))
    with connected() as (session, peer, _), ThreadPoolExecutor(1) as pool:
        future = pool.submit(session.call_with_identity, "receipt", ACTION_TOOL, arguments())
        command = peer.receive()
        peer.result(command)
        until(lambda: next(iter(session._active.pending.values())).result is not None)
        if ending == "eof":
            peer.process.stdin.close()
        else:
            peer.result(command, effect="NOT_APPLIED", status="refused", code="CONTRADICTION")
        until(lambda: session._active is None)
        release_waiter.set()
        assert future.result(timeout=3)["structuredContent"]["effect_state"] == "APPLIED"


def test_lost_reply_is_unknown_and_tab_is_not_redispatched():
    with connected(timeout=0.2) as (session, peer, _), ThreadPoolExecutor(1) as pool:
        future = pool.submit(session.call_with_identity, "lost", ACTION_TOOL, arguments())
        command = peer.receive()
        assert command["request_id"] == "lost"
        with pytest.raises(BrowserRelayError) as lost:
            future.result(timeout=3)
        assert not isinstance(lost.value, BrowserRequestRefused)
        with pytest.raises(BrowserRequestRefused):
            session.call_with_identity("new-id", ACTION_TOOL, arguments())
        assert not select.select([peer.process.stdout], [], [], 0.05)[0]


def test_partial_frame_failure_retires_generation(monkeypatch):
    with connected() as (session, peer, _):
        actual = module.write_frame
        def fail(channel, value, **kwargs):
            if value["schema"] == COMMAND_SCHEMA:
                channel.write(b"\x08")
                raise NativeHostError("synthetic partial write")
            return actual(channel, value, **kwargs)
        monkeypatch.setattr(module, "write_frame", fail)
        with pytest.raises(BrowserRelayError) as failed:
            session.call_with_identity("partial", ACTION_TOOL, arguments())
        assert not isinstance(failed.value, BrowserRequestRefused)
        assert session._active is None
        with pytest.raises(BrowserRequestRefused):
            session.call_with_identity("later", ACTION_TOOL, arguments(8))


def test_peer_identity_loss_before_dispatch_is_bounded_refusal(monkeypatch):
    with connected() as (session, peer, _):
        def changed(*_args, **_kwargs):
            raise ProcessIdentityError("synthetic identity loss")
        monkeypatch.setattr(session, "_peer_current", changed)
        with pytest.raises(BrowserRequestRefused):
            session.call_with_identity("identity-lost", ACTION_TOOL, arguments())
        assert session._active is None


def test_second_native_peer_cannot_preempt_active_profile():
    with connected() as (session, peer, config):
        other = Peer(session.enrollment, config, generation="competing")
        try:
            other.send(other.hello)
            assert other.process.wait(timeout=5) == 65
            assert session._active.generation == peer.generation
        finally:
            other.close()


def test_same_extension_id_different_profile_enrollments_stay_distinct():
    with connected(instance="b" * 64) as (one, _p1, _), connected(instance="c" * 64) as (two, _p2, _):
        assert one.enrollment.extension_id == two.enrollment.extension_id
        assert one.enrollment.socket_path != two.enrollment.socket_path
        assert one.enrollment.instance_id != two.enrollment.instance_id
        with pytest.raises(BrowserRequestRefused):
            one.call_with_identity("stale-generation", ACTION_TOOL, arguments(generation="old"))


def test_enrollment_rejects_symlink_or_unsafe_mode(tmp_path):
    tmp_path.chmod(0o700)
    enrollment = LinkEnrollment(EXTENSION, INSTANCE, Path("/tmp/native.sock"))
    config = tmp_path / "config"
    config.write_text(json.dumps(enrollment.document()))
    config.chmod(0o600)
    assert load_enrollment(config) == enrollment
    alias = tmp_path / "alias"
    alias.symlink_to(config)
    with pytest.raises(LinkProtocolError):
        load_enrollment(alias)
    config.chmod(0o644)
    with pytest.raises(LinkProtocolError):
        load_enrollment(config)


@pytest.mark.parametrize("effect,status", [("NOT_APPLIED", "completed"), ("APPLIED", "refused")])
def test_invalid_mutation_effect_never_becomes_success(effect, status):
    with connected() as (session, peer, _), ThreadPoolExecutor(1) as pool:
        future = pool.submit(session.call_with_identity, "invalid-effect", ACTION_TOOL, arguments())
        command = peer.receive()
        peer.result(command, effect=effect, status=status)
        with pytest.raises(BrowserRelayError) as failed:
            future.result(timeout=3)
        assert not isinstance(failed.value, BrowserRequestRefused)


@pytest.mark.parametrize("value", [[], {}, None, False])
def test_malformed_closed_enums_refuse_without_unhashable_exception(value):
    with pytest.raises(LinkProtocolError):
        validate_result({"schema": RESULT_SCHEMA, "request_id": "x", "connection_generation": "g",
                         "status": value, "effect": "APPLIED"}, "g")
    with pytest.raises(LinkProtocolError):
        validate_inventory({"schema": INVENTORY_SCHEMA, "connection_generation": "g", "shared_tabs": [
            {"tab_id": 1, "origin": "https://example.test", "consent_id": "c", "document_revision": 0, "state": value, "allow_create": False}
        ]}, "g")


def test_old_native_protocol_cannot_qualify_a_creation_capable_connection():
    from integrations.mastermind_browser_link.native_channel import validate_hello
    enrollment = LinkEnrollment(EXTENSION, INSTANCE, Path("/tmp/fixture/native.sock"))
    hello = {"schema": HELLO_SCHEMA, "protocol_version": 2, "extension_id": EXTENSION,
             "instance_ref": INSTANCE, "connection_generation": "generation"}
    assert validate_hello(hello, enrollment) == hello
    for changed in ({**hello, "protocol_version": 1},
                    {**hello, "schema": "mastermind.browser_link.hello.v1"},
                    {**hello, "protocol_version": True}):
        with pytest.raises(LinkProtocolError):
            validate_hello(changed, enrollment)


def test_inventory_v2_requires_explicit_creation_permission():
    row = {"tab_id": 7, "origin": "https://example.test", "consent_id": "consent",
           "document_revision": 0, "state": "shared"}
    with pytest.raises(LinkProtocolError):
        validate_inventory({"schema": INVENTORY_SCHEMA, "connection_generation": "g", "shared_tabs": [row]}, "g")
