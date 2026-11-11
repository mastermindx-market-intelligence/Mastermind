"""Audit #14 closeout — the t3-native production composition.

Proves the ONE composition composes the SQLite adapter store, the MCP tool
port and the supervisor's real pre-ACK recovery binding:

* store placement follows the Executive's own database rule (sibling in the
  Executive data dir) and DISCLOSES the per-checkout default in a typed
  basis field when no installed layout is configured;
* an absent token file is a typed unenrolled result, never an exception;
* a present token attests ``client:<sid>`` and binds the transport to the
  SAME token (Authorization header evidence);
* a claimed t3-native route launches through the composed adapter inside the
  existing mixed-owner launch path and persists the pre-ACK
  ``WorkerRecoveryBinding`` exactly where other adapters get theirs;
* a crash before the RUNNING transition leaves that binding durable, and a
  restarted composition recovers through ``reattach`` with ZERO native
  launches.
"""
from __future__ import annotations

import asyncio
import base64
import dataclasses
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from control_plane.t3_native_composition import (
    COMPOSITION_COMPOSED,
    COMPOSITION_ENROLLMENT_BROKEN,
    COMPOSITION_NOT_ENROLLED,
    STORE_BASIS_CHECKOUT_DEFAULT,
    STORE_BASIS_EXECUTIVE_DATA_DIR,
    T3_LAUNCH_ARGUMENTS_FILE_ENV,
    T3_MCP_ACCESS_TOKEN_FILE_ENV,
    T3McpHttpTransport,
    T3NativeCompositionError,
    T3NativeProcessController,
    SupervisorBoundaryT3Adapter,
    compose_t3_native_adapter,
    compose_t3_native_owners_for_service,
    compose_t3_native_supervisor_owners,
    compose_t3_native_supervisor,
    resolve_t3_access_token_file,
    resolve_t3_adapter_store_placement,
)
from control_plane.executive_runtime import AttemptStatus, Runtime
from control_plane.executive_supervisor import (
    ExecutiveSupervisor,
    ProcessPresence,
    ReconcileStatus,
)
from control_plane.mixed_worker_supervisor import MixedExecutionOwnerSupervisor
from control_plane.t3_execution_adapter import (
    SQLiteT3AdapterStateStore,
    T3McpTransportError,
)
from tests.test_t3_adapter_durability import CountingT3Port
from tests.test_t3_execution_adapter import FakeInspector

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ROUTES = _REPO_ROOT / "config" / "executive_worker_routes.json"


def _session_token(sid: str = "sess-compose-1") -> str:
    """A donor-shaped MCP client bearer token (claims.signature)."""
    claims = {
        "kind": "session",
        "sub": "mcp-client",
        "sid": sid,
        "method": "bearer-access-token",
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(claims).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return f"{encoded}.sig"


# --- store placement ----------------------------------------------------------


def test_placement_is_a_sibling_of_the_executives_actual_database(tmp_path):
    runtime = Runtime.at(tmp_path)
    placement = resolve_t3_adapter_store_placement(runtime)
    assert placement.basis == STORE_BASIS_EXECUTIVE_DATA_DIR
    assert placement.path.name == "t3_adapter_state.sqlite3"
    assert placement.path.parent == runtime.store.path.parent
    assert placement.path != runtime.store.path


def test_placement_accepts_an_installed_layout_root_without_a_live_runtime():
    placement = resolve_t3_adapter_store_placement(
        None, runtime_root="/var/db/mastermind-executive/control/db"
    )
    assert placement.basis == STORE_BASIS_EXECUTIVE_DATA_DIR
    assert str(placement.path) == (
        "/var/db/mastermind-executive/control/db/data/control_plane/"
        "t3_adapter_state.sqlite3"
    )


def test_placement_without_an_installed_layout_discloses_the_checkout_default():
    placement = resolve_t3_adapter_store_placement(None)
    # The per-checkout default is what makes the re-audit R1 no-row recovery
    # window reachable — the composition must SAY it is on it.
    assert placement.basis == STORE_BASIS_CHECKOUT_DEFAULT
    assert placement.path.name == "t3_adapter_state.sqlite3"
    assert placement.path != placement.path.parent / "executive.sqlite3"


def test_placement_never_names_the_executive_file(tmp_path):
    runtime = Runtime.at(tmp_path)
    placement = resolve_t3_adapter_store_placement(runtime)
    assert placement.path != runtime.store.path
    assert placement.path.name != "executive.sqlite3"
    # The store itself (already pinned by the durability tests) refuses the
    # Executive file if a caller ever hands it in explicitly.
    with pytest.raises(Exception):
        SQLiteT3AdapterStateStore(runtime.store.path)


# --- token resolution ---------------------------------------------------------


def test_absent_token_file_is_a_typed_unenrolled_result(tmp_path):
    runtime = Runtime.at(tmp_path)
    composition = compose_t3_native_adapter(
        runtime, inspector=FakeInspector(), environ={}
    )
    assert composition.status == COMPOSITION_NOT_ENROLLED
    assert composition.adapter is None
    assert not composition.composed
    assert T3_MCP_ACCESS_TOKEN_FILE_ENV in composition.reason


def test_empty_token_file_is_a_typed_broken_enrollment(tmp_path):
    # Review #3 (B1): a CONFIGURED-but-empty token file is a broken
    # enrollment (a visible fault in that lane), not a quiet unenrolled.
    token_file = tmp_path / "empty-token"
    token_file.write_text("   \n", encoding="utf-8")
    composition = compose_t3_native_adapter(
        Runtime.at(tmp_path),
        inspector=FakeInspector(),
        token_file=token_file,
        environ={},
    )
    assert composition.status == COMPOSITION_ENROLLMENT_BROKEN
    assert not composition.composed
    assert composition.adapter is None
    assert "empty" in composition.reason


def test_missing_token_file_is_a_typed_broken_enrollment(tmp_path):
    composition = compose_t3_native_adapter(
        Runtime.at(tmp_path),
        inspector=FakeInspector(),
        token_file=tmp_path / "absent-token",
        environ={},
    )
    assert composition.status == COMPOSITION_ENROLLMENT_BROKEN
    assert "unreadable" in composition.reason


def test_token_file_resolution_prefers_explicit_then_environment(tmp_path):
    explicit = tmp_path / "explicit-token"
    assert resolve_t3_access_token_file(explicit) == explicit
    env_file = tmp_path / "env-token"
    resolved = resolve_t3_access_token_file(
        None, environ={T3_MCP_ACCESS_TOKEN_FILE_ENV: str(env_file)}
    )
    assert resolved == env_file
    assert resolve_t3_access_token_file(None, environ={}) is None


# --- launch arguments (G1: canary deviation "launch arguments ride the
# --- port_factory seam; the default composition passed none") ------------------


def _write_launch_arguments(
    tmp_path, payload=None, *, name="t3-launch-arguments.json"
) -> Path:
    """Write a launch-arguments file (the canary's exact shape by default)."""
    if payload is None:
        payload = {
            "projectId": "bc18d268-d100-484a-8952-3ce2b0b0a66b",
            "workspaceStrategy": {
                "type": "worktree",
                "branch": "t3/mmos-l1-canary-eaacc05d",
                "baseRef": "master",
                "startFromOrigin": True,
            },
        }
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _enrolled_runtime(tmp_path):
    runtime = Runtime.at(tmp_path)
    token_file = tmp_path / "t3-token"
    token_file.write_text(_session_token("sess-launch-args"), encoding="utf-8")
    return runtime, token_file


def test_launch_arguments_file_resolution_prefers_explicit_then_environment(tmp_path):
    from control_plane.t3_native_composition import (
        resolve_t3_launch_arguments_file,
    )

    explicit = tmp_path / "explicit-args.json"
    assert resolve_t3_launch_arguments_file(explicit) == explicit
    env_file = tmp_path / "env-args.json"
    resolved = resolve_t3_launch_arguments_file(
        None, environ={T3_LAUNCH_ARGUMENTS_FILE_ENV: str(env_file)}
    )
    assert resolved == env_file
    assert resolve_t3_launch_arguments_file(None, environ={}) is None


def test_absent_launch_arguments_file_is_a_typed_broken_enrollment(tmp_path):
    # G1 fail-closed law: an ENROLLED host (valid token) whose composition
    # would build the port with NO launch arguments can never satisfy T3's
    # required projectId/workspaceStrategy — refuse at composition, never
    # launch a port whose every launch fails upstream.
    runtime, token_file = _enrolled_runtime(tmp_path)
    composition = compose_t3_native_adapter(
        runtime,
        inspector=FakeInspector(),
        token_file=token_file,
        state_store=SQLiteT3AdapterStateStore(tmp_path / "state.sqlite3"),
        environ={},
    )
    assert composition.status == COMPOSITION_ENROLLMENT_BROKEN
    assert not composition.composed
    assert composition.adapter is None
    assert T3_LAUNCH_ARGUMENTS_FILE_ENV in composition.reason


def test_missing_launch_arguments_file_is_a_typed_broken_enrollment(tmp_path):
    runtime, token_file = _enrolled_runtime(tmp_path)
    absent = tmp_path / "absent-args.json"
    composition = compose_t3_native_adapter(
        runtime,
        inspector=FakeInspector(),
        token_file=token_file,
        launch_arguments_file=absent,
        state_store=SQLiteT3AdapterStateStore(tmp_path / "state.sqlite3"),
        environ={},
    )
    assert composition.status == COMPOSITION_ENROLLMENT_BROKEN
    assert "unreadable" in composition.reason


def test_malformed_launch_arguments_file_is_a_typed_broken_enrollment(tmp_path):
    runtime, token_file = _enrolled_runtime(tmp_path)
    for label, raw in (
        ("not json", "{projectId: unquoted}"),
        ("not an object", '["projectId"]'),
        ("empty object", "{}"),
        ("blank projectId", '{"projectId": "  "}'),
        ("workspaceStrategy not an object", '{"workspaceStrategy": "worktree"}'),
    ):
        bad = tmp_path / f"bad-args-{abs(hash(label))}.json"
        bad.write_text(raw, encoding="utf-8")
        composition = compose_t3_native_adapter(
            runtime,
            inspector=FakeInspector(),
            token_file=token_file,
            launch_arguments_file=bad,
            state_store=SQLiteT3AdapterStateStore(
                tmp_path / f"state-{abs(hash(label))}.sqlite3"
            ),
            environ={},
        )
        assert composition.status == COMPOSITION_ENROLLMENT_BROKEN
        assert not composition.composed
        assert composition.adapter is None


def test_extra_key_launch_arguments_file_is_refused(tmp_path):
    runtime, token_file = _enrolled_runtime(tmp_path)
    extra = _write_launch_arguments(
        tmp_path,
        {"projectId": "p-1", "zone": "us-east"},  # 'zone' is not in the schema
    )
    composition = compose_t3_native_adapter(
        runtime,
        inspector=FakeInspector(),
        token_file=token_file,
        launch_arguments_file=extra,
        state_store=SQLiteT3AdapterStateStore(tmp_path / "state.sqlite3"),
        environ={},
    )
    assert composition.status == COMPOSITION_ENROLLMENT_BROKEN
    assert "zone" in composition.reason


def test_launch_arguments_environmentId_is_refused(tmp_path):
    # The port already refuses environmentId at launch; a CONFIGURED file
    # carrying it fails visibly at composition, before any owner exists.
    runtime, token_file = _enrolled_runtime(tmp_path)
    env_id = _write_launch_arguments(
        tmp_path,
        {"projectId": "p-1", "environmentId": "5f4cd5f0-e3df-407d-af02"},
    )
    composition = compose_t3_native_adapter(
        runtime,
        inspector=FakeInspector(),
        token_file=token_file,
        launch_arguments_file=env_id,
        state_store=SQLiteT3AdapterStateStore(tmp_path / "state.sqlite3"),
        environ={},
    )
    assert composition.status == COMPOSITION_ENROLLMENT_BROKEN
    assert "environmentId" in composition.reason


def test_valid_launch_arguments_file_composes_and_the_port_carries_them(tmp_path):
    runtime, token_file = _enrolled_runtime(tmp_path)
    launch_arguments_file = _write_launch_arguments(tmp_path)
    args = json.loads(launch_arguments_file.read_text(encoding="utf-8"))
    recording: dict[str, RecordingTransport] = {}

    def transport_factory(url, access_token):
        transport = RecordingTransport(url, access_token)
        recording["transport"] = transport
        return transport

    composition = compose_t3_native_adapter(
        runtime,
        inspector=FakeInspector(),
        token_file=token_file,
        launch_arguments_file=launch_arguments_file,
        transport_factory=transport_factory,
        state_store=SQLiteT3AdapterStateStore(tmp_path / "state.sqlite3"),
        environ={},
    )
    assert composition.status == COMPOSITION_COMPOSED
    assert composition.composed
    port = composition.adapter._port
    # The port carries the file's arguments on its own launch_arguments seam
    # — the SAME seam the canary proved live through port_factory.
    assert port._launch_arguments == args


def test_launch_arguments_env_var_threads_through_the_service_seam(tmp_path):
    # compose_t3_native_owners_for_service configures the whole lane from
    # the environment: token file + launch arguments file, paths only.
    from control_plane.t3_native_composition import (
        T3_LAUNCH_ARGUMENTS_FILE_ENV,
    )

    runtime, _job_id, _workspace, _observations = _t3_runtime_and_job(tmp_path)
    primary = _primary_owner(runtime, tmp_path)
    token_file = tmp_path / "t3-token"
    token_file.write_text(_session_token("sess-service-seam"), encoding="utf-8")
    launch_arguments_file = _write_launch_arguments(tmp_path)
    owners = compose_t3_native_owners_for_service(
        primary,
        runtime,
        runs_root=tmp_path / "runs",
        isolation_roots=(tmp_path / "workspaces", tmp_path / "runs"),
        environ={
            T3_MCP_ACCESS_TOKEN_FILE_ENV: str(token_file),
            T3_LAUNCH_ARGUMENTS_FILE_ENV: str(launch_arguments_file),
        },
    )
    assert set(owners) == {_T3_WORKER_ID}


def test_service_seam_without_launch_arguments_composes_no_owner(tmp_path, caplog):
    # The installed Executive configures this lane env-only: an enrolled
    # token with NO launch arguments file is a VISIBLE broken enrollment at
    # startup (fail-closed for this lane alone), never a half-composed port.
    runtime, _job_id, _workspace, _observations = _t3_runtime_and_job(tmp_path)
    primary = _primary_owner(runtime, tmp_path)
    token_file = tmp_path / "t3-token"
    token_file.write_text(_session_token("sess-service-seam-2"), encoding="utf-8")
    with caplog.at_level(
        logging.ERROR, logger="control_plane.t3_native_composition"
    ):
        owners = compose_t3_native_owners_for_service(
            primary,
            runtime,
            runs_root=tmp_path / "runs",
            isolation_roots=(tmp_path / "workspaces", tmp_path / "runs"),
            environ={T3_MCP_ACCESS_TOKEN_FILE_ENV: str(token_file)},
        )
    assert owners == {}
    assert any(
        T3_LAUNCH_ARGUMENTS_FILE_ENV in record.message
        for record in caplog.records
    )


# --- configured-but-broken enrollment (review #3 B1) ---------------------------


def test_malformed_token_file_is_a_typed_broken_enrollment_not_a_crash(tmp_path):
    # The review #3 probe: 'garbage-no-dot' (no claims separator) and 'a.b'
    # (unparsable claims) previously raised T3NamespaceAttestationError out
    # of the composition INTO the service seam, taking the paid/plain/fabric
    # lanes down together.  Now: typed, fail-closed, token never echoed.
    for malformed in ("garbage-no-dot", "a.b"):
        token_file = tmp_path / "bad-token"
        token_file.write_text(malformed, encoding="utf-8")
        composition = compose_t3_native_adapter(
            Runtime.at(tmp_path),
            inspector=FakeInspector(),
            token_file=token_file,
            environ={},
        )
        assert composition.status == COMPOSITION_ENROLLMENT_BROKEN
        assert not composition.composed
        assert composition.adapter is None
        assert "attest" in composition.reason
        assert malformed not in composition.reason  # no token material echoed


def test_non_utf8_token_file_is_a_typed_broken_enrollment_not_a_crash(tmp_path):
    # Review #4 F2: the read path caught only OSError, so bytes that are not
    # UTF-8 raised UnicodeDecodeError straight into the service seam.
    token_file = tmp_path / "binary-token"
    token_file.write_bytes(b"\xff\xfe garbage")
    composition = compose_t3_native_adapter(
        Runtime.at(tmp_path), inspector=FakeInspector(),
        token_file=token_file, environ={},
    )
    assert composition.status == COMPOSITION_ENROLLMENT_BROKEN
    assert not composition.composed and composition.adapter is None
    assert "UnicodeDecodeError" in composition.reason
    assert "garbage" not in composition.reason


def test_service_seam_surfaces_a_broken_enrollment_and_never_raises(tmp_path, caplog):
    runtime, _job_id, _workspace, _observations = _t3_runtime_and_job(tmp_path)
    primary = _primary_owner(runtime, tmp_path)
    bad = tmp_path / "bad-token"
    bad.write_text("garbage-no-dot", encoding="utf-8")
    with caplog.at_level(
        logging.ERROR, logger="control_plane.t3_native_composition"
    ):
        owners = compose_t3_native_owners_for_service(
            primary,
            runtime,
            runs_root=tmp_path / "runs",
            isolation_roots=(tmp_path / "workspaces", tmp_path / "runs"),
            environ={T3_MCP_ACCESS_TOKEN_FILE_ENV: str(bad)},
        )
    # No exception into _service_from_config; the other lanes keep their
    # owners; the reason is VISIBLE at startup, not discarded.
    assert owners == {}
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors, "a broken enrollment must surface visibly at startup"
    assert any("broken" in record.message for record in errors)
    assert any("attest" in record.message for record in errors)
    assert all("garbage-no-dot" not in record.message for record in errors)


def test_service_seam_surfaces_an_empty_token_file_reason(tmp_path, caplog):
    runtime, _job_id, _workspace, _observations = _t3_runtime_and_job(tmp_path)
    primary = _primary_owner(runtime, tmp_path)
    empty = tmp_path / "empty-token"
    empty.write_text("\n", encoding="utf-8")
    with caplog.at_level(
        logging.ERROR, logger="control_plane.t3_native_composition"
    ):
        owners = compose_t3_native_owners_for_service(
            primary,
            runtime,
            runs_root=tmp_path / "runs",
            isolation_roots=(tmp_path / "workspaces", tmp_path / "runs"),
            environ={T3_MCP_ACCESS_TOKEN_FILE_ENV: str(empty)},
        )
    assert owners == {}
    assert any("empty" in record.message for record in caplog.records)


def test_unenrolled_service_seam_never_touches_a_stand_in_primary(tmp_path):
    # Review #3 (B1 MAJOR): 16 existing tests' stand-in supervisors carry no
    # ``.inspector``; the seam must resolve enrollment FIRST and never read
    # a primary attribute on an unenrolled host.
    runtime, _job_id, _workspace, _observations = _t3_runtime_and_job(tmp_path)
    probe = SimpleNamespace(runtime=runtime)  # no .inspector, no .instance_id
    owners = compose_t3_native_owners_for_service(
        probe,
        runtime,
        runs_root=tmp_path / "runs",
        isolation_roots=(tmp_path / "workspaces", tmp_path / "runs"),
        environ={},
    )
    assert owners == {}


# --- attestation + transport share ONE token ----------------------------------


class RecordingTransport:
    """Fake transport that records the authorization it would send."""

    def __init__(self, url: str, token: str) -> None:
        self.url = url
        self.token = token
        self.sent_authorization: list[str] = []

    def call_tool(self, name, arguments):
        self.sent_authorization.append(f"Bearer {self.token}")
        return {"threadId": "thr-x", "runId": "t3run-x"}


def test_present_token_attests_namespace_and_binds_the_same_token(tmp_path):
    runtime = Runtime.at(tmp_path)
    token_file = tmp_path / "t3-token"
    token = _session_token("sess-compose-1")
    token_file.write_text(token + "\n", encoding="utf-8")
    # G1: the default port path REQUIRES launch arguments (t3_thread_launch
    # needs projectId/workspaceStrategy); this token/transport-binding probe
    # supplies a valid file so composition reaches the port.
    launch_arguments_file = _write_launch_arguments(tmp_path)
    recording: dict[str, RecordingTransport] = {}

    def transport_factory(url, access_token):
        transport = RecordingTransport(url, access_token)
        recording["transport"] = transport
        return transport

    composition = compose_t3_native_adapter(
        runtime,
        inspector=FakeInspector(),
        token_file=token_file,
        launch_arguments_file=launch_arguments_file,
        transport_factory=transport_factory,
        state_store=SQLiteT3AdapterStateStore(tmp_path / "state.sqlite3"),
        environ={},
    )
    assert composition.status == COMPOSITION_COMPOSED
    assert composition.composed
    # The port attests the token's session id, not a label.
    assert composition.upstream_namespace == "client:sess-compose-1"
    # The transport sends EXACTLY the token the port attested (M2): the
    # port's transport callable is the recording transport's bound method.
    transport = recording["transport"]
    assert transport.token == token
    port = composition.adapter._port
    assert port._call_tool.__self__ is transport


def test_real_transport_sends_the_file_token_as_bearer_authorization(tmp_path):
    """The real stdlib transport against a live local MCP HTTP endpoint."""
    token = _session_token("sess-http-1")
    token_file = tmp_path / "t3-token"
    token_file.write_text(token, encoding="utf-8")
    seen: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - http.server API
            seen["authorization"] = self.headers.get("Authorization", "")
            body = json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"structuredContent": {"threadId": "thr-1"}},
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # silence the test server
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        transport = T3McpHttpTransport(
            f"http://127.0.0.1:{server.server_address[1]}/mcp", token
        )
        reply = transport.call_tool("t3_thread_launch", {"clientRequestId": "k"})
        assert reply == {"threadId": "thr-1"}
        assert seen["authorization"] == f"Bearer {token}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


# --- transport hardening (review #3 B1): initialize / redirect / proxy --------


class _FakeUpstream:
    """A local MCP HTTP endpoint recording every request it serves."""

    def __init__(self, handler_cls) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}/mcp"

    def close(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)


def test_transport_initializes_once_before_the_first_tool_call(tmp_path):
    """Review #3 B1: initialize() is never called by the donor clients'
    contract — the transport itself opens the session lazily, exactly once,
    BEFORE the first tools/call (call-order proof against a fake upstream)."""
    seen: dict[str, list] = {"methods": [], "authorizations": []}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - http.server API
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
            seen["methods"].append(payload.get("method"))
            seen["authorizations"].append(self.headers.get("Authorization"))
            if payload.get("method") == "initialize":
                body = json.dumps({
                    "jsonrpc": "2.0", "id": payload.get("id"),
                    "result": {"protocolVersion": "2025-03-26"},
                }).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Mcp-Session-Id", "sess-transport-1")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if payload.get("method") == "notifications/initialized":
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = json.dumps({
                "jsonrpc": "2.0", "id": payload.get("id"),
                "result": {"structuredContent": {"threadId": "thr-init"}},
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # silence the test server
            return

    upstream = _FakeUpstream(Handler)
    try:
        transport = T3McpHttpTransport(upstream.url, _session_token("sess-x"))
        reply = transport.call_tool("t3_thread_launch", {"clientRequestId": "k"})
        assert reply == {"threadId": "thr-init"}
        # The session handshake PRECEDES the first tool call, exactly once:
        assert seen["methods"] == [
            "initialize", "notifications/initialized", "tools/call",
        ]
        # A second tool call does NOT re-initialize (the session persists).
        transport.call_tool("t3_thread_read", {"runId": "r"})
        assert seen["methods"].count("initialize") == 1
        assert seen["methods"][-1] == "tools/call"
    finally:
        upstream.close()


def test_transport_refuses_redirects_and_never_resends_the_bearer(tmp_path):
    """A 3xx is a typed transport error; the redirect target is NEVER
    requested, so the bearer header is never resent off-origin."""
    seen: dict[str, list] = {"paths": []}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - http.server API
            seen["paths"].append(self.path)
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self.send_response(302)
            self.send_header("Location", "/attacker-sink")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):  # silence the test server
            return

    upstream = _FakeUpstream(Handler)
    try:
        transport = T3McpHttpTransport(upstream.url, _session_token("sess-x"))
        with pytest.raises(T3McpTransportError) as caught:
            transport.call_tool("t3_thread_launch", {"clientRequestId": "k"})
        assert caught.value.http_status == 302
        assert "redirect" in str(caught.value)
        # Only the original endpoint was ever contacted.
        assert seen["paths"] == ["/mcp"]
    finally:
        upstream.close()


def test_transport_ignores_environment_proxies(tmp_path):
    """A hostile/dead http_proxy in the environment must not reroute the
    bearer: the opener is built with NO proxies at all."""
    seen: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - http.server API
            seen["authorization"] = self.headers.get("Authorization", "")
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
            if payload.get("method") == "initialize":
                body = json.dumps({
                    "jsonrpc": "2.0", "id": payload.get("id"),
                    "result": {"protocolVersion": "2025-03-26"},
                }).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if payload.get("method") == "notifications/initialized":
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = json.dumps({
                "jsonrpc": "2.0", "id": payload.get("id"),
                "result": {"structuredContent": {"ok": True}},
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # silence the test server
            return

    upstream = _FakeUpstream(Handler)
    token = _session_token("sess-proxy")
    dead_proxy = "http://127.0.0.1:9/"
    try:
        with mock.patch.dict(os.environ, {
            "http_proxy": dead_proxy, "HTTP_PROXY": dead_proxy,
            "https_proxy": dead_proxy, "HTTPS_PROXY": dead_proxy,
            "all_proxy": dead_proxy, "ALL_PROXY": dead_proxy,
        }):
            transport = T3McpHttpTransport(upstream.url, token)
            reply = transport.call_tool("t3_thread_read", {"runId": "r"})
        # Direct delivery: had the environment proxy been honoured the
        # request would have failed to connect to the dead proxy instead.
        assert reply == {"ok": True}
        assert seen["authorization"] == f"Bearer {token}"
    finally:
        upstream.close()





# --- route row proposal loads through the REAL router -------------------------


def _proposal_row() -> dict:
    """Parse the verbatim row out of the proposal document itself."""
    text = (
        _REPO_ROOT / "integrations/mmos/T3_NATIVE_ROUTE_ROW_PROPOSAL.md"
    ).read_text(encoding="utf-8")
    fence = text.index("```json")
    start = text.index("\n", fence) + 1
    end = text.index("```", start)
    # The fence carries the row as a `"t3": {...}` member; wrap to parse.
    return json.loads("{" + text[start:end] + "}")["t3"]


def test_route_row_proposal_loads_through_the_real_router(tmp_path):
    from control_plane.model_router import ModelRouter

    live_before = _ROUTES.read_bytes()
    live = json.loads(live_before)
    # R5 landed the approved staged row (disabled): the live file carries it.
    assert live["providers"]["t3"] == _proposal_row()
    merged = json.loads(json.dumps(live))
    merged["providers"]["t3"] = _proposal_row()
    proposed = tmp_path / "executive_worker_routes.json"
    proposed.write_text(json.dumps(merged), encoding="utf-8")

    router = ModelRouter.load(proposed)
    provider = router.providers["t3"]
    assert provider.adapter_id == "t3-native"
    assert provider.enabled is False
    assert provider.autonomous_allowed is False
    # The live protected file was never written.
    assert _ROUTES.read_bytes() == live_before


# --- supervisor composition: launch + pre-ACK binding --------------------------

_T3_WORKER_ID = "t3-canary-01"


def _t3_runtime_and_job(tmp_path: Path):
    """A child-placement Job claimed on a t3-native route (the only claim
    shape whose ExecutionBinding carries the v1.1 native join), with the
    worktree/validation fields the supervisor launch path requires."""
    from tests.test_executive_claim_job_placement_authority import (
        QUOTA, REVISION, Clock, _observations, _request,
    )

    runtime = Runtime.at(tmp_path, clock=Clock(), lease_seconds=60)
    runtime.workers.register_worker(
        _T3_WORKER_ID,
        provider="t3",
        account_label="mcp-bearer-session",
        worker_type="t3-native",
        capabilities=["code"],
        quota_classes={
            "default": {
                "capabilities": ["code"],
                "metadata": {"adapter_id": "t3-native"},
            }
        },
        metadata={"host_id": "ubuntu0"},
    )
    workspace = tmp_path / "workspaces" / "t3-workspace"
    workspace.mkdir(mode=0o700, parents=True)
    spec = {
        "child_execution_request": _request("t3-compose-child").to_dict(),
        "effective_complexity": "C1_ROUTINE_BOUNDED",
        "registry_revision": REVISION,
        "route": {"provider_ref": "t3", "pool_ref": "glm",
                  "adapter_id": "t3-native"},
        "shared_quota_resource_refs": [QUOTA],
        "root_concurrency_limit": 32,
    }
    job = runtime.jobs.create_job(
        "Compose the t3-native worker through the Executive launch path",
        worktree=str(workspace.resolve()),
        requested_authorities=["READ", "RESEARCH", "WRITE_BRANCH", "RUN_TESTS"],
        allowed_write_paths=["research/proof.md"],
        validation_commands=[["/usr/bin/true"]],
        constraints={"child_placement": spec},
        attempt_limit=3,
    )
    return runtime, job.job_id, workspace, _observations()


def _claim_t3_route(runtime: Runtime, job_id: str, observations):
    lease = runtime.attempts.claim_job(
        job_id, placement_observations=observations
    )
    assert lease is not None, "the t3-native route must claim worker capacity"
    from control_plane.child_execution_contracts import ExecutionBinding
    binding = ExecutionBinding.from_dict(
        runtime.attempts.execution_binding(lease.attempt.attempt_id)
    )
    assert binding.runtime_kind == "t3-native"
    return lease


def _primary_owner(runtime: Runtime, tmp_path: Path):
    """A primary owner over the supervisor-test FakeAdapter (unchanged path)."""
    from tests.test_executive_supervisor import FakeAdapter, FakeInspector as SupFakeInspector
    from tests.test_executive_supervisor import FakeProcessController

    inspector = SupFakeInspector()
    adapter = FakeAdapter(inspector)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir(mode=0o700, exist_ok=True)
    adapter.provider_home = codex_home
    supervisor = ExecutiveSupervisor(
        runtime,
        adapter,  # type: ignore[arg-type]
        runs_root=tmp_path / "runs",
        isolation_roots=(tmp_path / "workspaces", tmp_path / "runs"),
        heartbeat_interval_seconds=0.01,
        inspector=inspector,
        process_controller=FakeProcessController(inspector),
        instance_id="composition-fixture",
    )
    return supervisor


def _compose_mixed(runtime, tmp_path, primary, port, *, state_path=None):
    """The production shape: mixed owners with the t3-native owner composed."""
    token_file = tmp_path / "t3-token"
    token_file.write_text(_session_token("sess-supervisor"), encoding="utf-8")
    state_path = state_path or (tmp_path / "t3_adapter_state.sqlite3")
    composition = compose_t3_native_adapter(
        runtime,
        inspector=FakeInspector(),
        token_file=token_file,
        port_factory=lambda _token: port,
        state_store=SQLiteT3AdapterStateStore(state_path),
        environ={},
    )
    assert composition.composed
    t3_owners = compose_t3_native_supervisor_owners(
        primary,
        composition,
        runs_root=tmp_path / "runs",
        isolation_roots=(tmp_path / "workspaces", tmp_path / "runs"),
    )
    assert set(t3_owners) == {_T3_WORKER_ID}
    return MixedExecutionOwnerSupervisor(
        primary, {"primary-codex": primary, **t3_owners}
    ), composition


def test_claimed_t3_route_launches_and_persists_the_pre_ack_binding(tmp_path):
    runtime, job_id, _workspace, observations = _t3_runtime_and_job(tmp_path)
    primary = _primary_owner(runtime, tmp_path)
    port = CountingT3Port(principal="oauth-client-compose")
    mixed, composition = _compose_mixed(runtime, tmp_path, primary, port)
    lease = _claim_t3_route(runtime, job_id, observations)

    # The production launch path: mixed-owner selection + the supervisor's
    # own _start_claimed_job (what start_job/start_cycle_job funnel into).
    async def launch():
        return await mixed._start(
            mixed._select(lease.attempt), job_id, lease, None
        )

    active = asyncio.run(launch())

    # The composed adapter really launched through the mixed owners map.
    assert port.launch_count == 1
    minted_thread = port.receipts_by_key[
        active.process_ref.launch_nonce
    ].thread_id
    assert active.process_ref.provider_session_id == minted_thread
    assert composition.adapter.launch_receipt(active.lease.attempt.attempt_id)

    # The binding is bound to adapter t3-native and persisted by the
    # supervisor BEFORE the RUNNING transition — the audit #14 producer.
    attempt = runtime.attempts.get_attempt(active.lease.attempt.attempt_id)
    assert attempt is not None
    assert attempt.status in (AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED)
    raw = attempt.launch_metadata.get("worker_recovery_binding")
    assert isinstance(raw, dict)
    assert raw["adapter_id"] == "t3-native"
    # the binding's launch_spec carries the durable prompt coordinates
    prompt_path = raw["launch_spec"]["prompt_path"]
    assert prompt_path.endswith("worker-prompt.txt")
    assert Path(prompt_path).read_bytes()  # the durable prompt exists
    assert raw["launch_spec"]["prompt_sha256"]
    # routing metadata carries the composed adapter identity
    assert attempt.launch_metadata["routing"]["adapter_id"] == "t3-native"


def test_unenrolled_host_composes_no_owner_and_leaves_the_map_unchanged(tmp_path):
    runtime, _job_id, _workspace, _observations = _t3_runtime_and_job(tmp_path)
    primary = _primary_owner(runtime, tmp_path)
    composition = compose_t3_native_adapter(
        runtime, inspector=FakeInspector(), environ={}
    )
    assert not composition.composed
    owners = compose_t3_native_supervisor_owners(
        primary,
        composition,
        runs_root=tmp_path / "runs",
        isolation_roots=(tmp_path / "workspaces", tmp_path / "runs"),
    )
    assert owners == {}


def test_crash_before_the_running_ack_recovers_with_zero_native_launches(tmp_path):
    runtime, job_id, _workspace, observations = _t3_runtime_and_job(tmp_path)
    primary = _primary_owner(runtime, tmp_path)
    port = CountingT3Port(principal="oauth-client-compose")
    state_path = tmp_path / "t3_adapter_state.sqlite3"
    mixed, _ = _compose_mixed(runtime, tmp_path, primary, port,
                              state_path=state_path)
    lease = _claim_t3_route(runtime, job_id, observations)

    # Crash the control service AFTER the binding was persisted by
    # record_process but BEFORE the RUNNING transition (the ACK). SystemExit
    # escapes the supervisor's Exception containment exactly like a kill.
    with mock.patch.object(
        runtime.attempts, "mark_running", side_effect=SystemExit(9)
    ):
        with pytest.raises(SystemExit):
            asyncio.run(mixed._start(
                mixed._select(lease.attempt), job_id, lease, None
            ))

    attempt_id = lease.attempt.attempt_id
    crashed = runtime.attempts.get_attempt(attempt_id)
    assert crashed is not None
    assert crashed.launch_metadata.get("worker_recovery_binding"), (
        "the pre-ACK recovery binding must be durable"
    )
    assert crashed.status is AttemptStatus.CLAIMED  # never reached RUNNING
    raw = crashed.launch_metadata["worker_recovery_binding"]
    assert raw["adapter_id"] == "t3-native"
    assert port.launch_count == 1  # the native thread exists upstream

    # A RESTARTED composition: fresh adapter over the same SQLite store, a
    # FRESH port (no shared state), same mixed owners shape.
    port2 = CountingT3Port(principal="oauth-client-compose")
    mixed2, _ = _compose_mixed(runtime, tmp_path, primary, port2,
                               state_path=state_path)

    receipts = mixed2.reconcile_restart()

    # T4c attack F1(a) (15f769d6c): the crashed launcher's lease is still
    # LIVE at restart, and a live lease's owner may be a live finisher
    # collecting and heartbeating — reconcile defers rather than fencing;
    # only the engine's own lease expiry proves the claimant lost its
    # rights.  Nothing native happens while deferring.
    assert [r.status for r in receipts] == [ReconcileStatus.AWAITING_LEASE_EXPIRY]
    assert port2.launch_count == 0  # ZERO native launches while deferring
    assert port2.replay_count == 0
    assert port2.reads == []
    assert mixed2.take_recovered_runs() == ()

    runtime.store.clock.value += 61_000  # past the 60s lease
    receipts = mixed2.reconcile_restart()

    assert [r.status for r in receipts] == [ReconcileStatus.TERMINAL_RECOVERED]
    assert port2.launch_count == 0  # ZERO native launches on recovery
    assert port2.replay_count == 0
    assert port2.reads == []
    recovered = mixed2.take_recovered_runs()
    assert len(recovered) == 1
    assert recovered[0].process_ref.provider_session_id == (
        port.receipts_by_key[next(iter(port.receipts_by_key))].thread_id
    )
    # SAME execution: the recovered ref carries the original idempotency key.
    assert (
        recovered[0].process_ref.launch_nonce
        == crashed.launch_metadata["worker_recovery_binding"]["process_ref"][
            "launch_nonce"
        ]
    )
    after = runtime.attempts.get_attempt(attempt_id)
    assert after.status in (AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED)


def test_remote_native_process_controller_never_signals(tmp_path):
    runtime, job_id, _workspace, observations = _t3_runtime_and_job(tmp_path)
    primary = _primary_owner(runtime, tmp_path)
    port = CountingT3Port(principal="oauth-client-compose")
    mixed, _ = _compose_mixed(runtime, tmp_path, primary, port)
    lease = _claim_t3_route(runtime, job_id, observations)
    active = asyncio.run(mixed._start(
        mixed._select(lease.attempt), job_id, lease, None
    ))
    attempt = runtime.attempts.get_attempt(active.lease.attempt.attempt_id)

    controller = T3NativeProcessController()
    assert controller.presence(attempt) is ProcessPresence.TERMINAL_OWNED
    unbound = mock.Mock()
    unbound.launch_metadata = {}
    assert controller.presence(unbound) is ProcessPresence.UNKNOWN
    assert controller.absence_verified(attempt) is False
    from control_plane.executive_supervisor import SupervisorError
    with pytest.raises(SupervisorError):
        controller.terminate(attempt)


def test_supervisor_composition_requires_a_composed_adapter(tmp_path):
    runtime, _job_id, _workspace, _observations = _t3_runtime_and_job(tmp_path)
    primary = _primary_owner(runtime, tmp_path)
    composition = compose_t3_native_adapter(
        runtime, inspector=FakeInspector(), environ={}
    )
    with pytest.raises(T3NativeCompositionError):
        compose_t3_native_supervisor(
            primary,
            composition,
            runs_root=tmp_path / "runs",
            isolation_roots=(tmp_path / "workspaces", tmp_path / "runs"),
        )


# --- supervisor-boundary bridge: recovery identity (review #3 B2) --------------


def _launch_coordinates(tmp_path):
    """Launch one t3-native attempt through the composed mixed owners and
    return ``(inner adapter, genuine recovery binding, run id)``."""
    runtime, job_id, _workspace, observations = _t3_runtime_and_job(tmp_path)
    primary = _primary_owner(runtime, tmp_path)
    port = CountingT3Port(principal="oauth-client-compose")
    mixed, composition = _compose_mixed(runtime, tmp_path, primary, port)
    lease = _claim_t3_route(runtime, job_id, observations)
    active = asyncio.run(
        mixed._start(mixed._select(lease.attempt), job_id, lease, None)
    )
    attempt = runtime.attempts.get_attempt(active.lease.attempt.attempt_id)
    assert attempt is not None
    from control_plane.worker_execution_contract import WorkerRecoveryBinding
    binding = WorkerRecoveryBinding.from_dict(
        attempt.launch_metadata["worker_recovery_binding"]
    )
    spec = SimpleNamespace(run_id=active.lease.attempt.attempt_id)
    return composition.adapter, binding, spec


def test_bridge_reattach_refuses_a_forged_binding_before_the_inner_adapter_runs(
    tmp_path,
):
    """Review #3 (B2 MAJOR): the bridge used to substitute the retained ref
    into the binding unconditionally, so the inner adapter's "retained ref
    differs from the recovery binding" check compared the retained ref to
    ITSELF and a forged ``thread-FOREIGN``/``foreign-key`` binding was
    ACCEPTED.  Now the supervisor-supplied binding must BE the twin of the
    retained ref before anything is substituted, and the inner adapter is
    never called for a forged one."""
    inner, binding, spec = _launch_coordinates(tmp_path)
    retained = inner.retained_original_ref(spec.run_id)
    assert retained is not None
    bridge = SupervisorBoundaryT3Adapter(inner)
    # Sanity: the genuine persisted binding carries the twin shape.
    assert bridge._twin(retained) == binding.process_ref

    forged = dataclasses.replace(
        binding,
        process_ref=dataclasses.replace(
            binding.process_ref,
            provider_session_id="thread-FOREIGN",
            launch_nonce="foreign-key",
        ),
    )
    with mock.patch.object(
        inner,
        "reattach",
        side_effect=AssertionError("inner reattach must never run"),
    ):
        with pytest.raises(T3NativeCompositionError) as caught:
            bridge.reattach(spec, forged)
    assert "refusing to swap executions" in str(caught.value)


def test_bridge_reattach_refuses_entry_from_a_running_event_loop(tmp_path):
    """The sync bridge drives the inner coroutine on a private one-shot
    loop; entering it from a running loop is a typed refusal (the supervisor
    surfaces it as LIVE_QUARANTINED), never a nested-loop attempt."""
    inner, binding, spec = _launch_coordinates(tmp_path)
    bridge = SupervisorBoundaryT3Adapter(inner)

    async def on_loop():
        return bridge.reattach(spec, binding)

    with mock.patch.object(
        inner,
        "reattach",
        side_effect=AssertionError("inner reattach must never run"),
    ):
        with pytest.raises(T3NativeCompositionError) as caught:
            asyncio.run(on_loop())
    assert "running event loop" in str(caught.value)


# --- L1B3-2 / L1B3-3: launch-arguments source precedence --------------------


def test_explicit_launch_arguments_win_over_the_ambient_env_var(tmp_path):
    # L1B3-2 (HIGH): on a host where MASTERMIND_T3_LAUNCH_ARGUMENTS_FILE is
    # set (the standard deployment shape), a caller's explicit
    # launch_arguments mapping must compose — the ambient env var is not
    # consulted, cannot manufacture a both-sources refusal, and cannot
    # shadow the explicit arguments with the file's content.
    runtime, token_file = _enrolled_runtime(tmp_path)
    # The env-named file carries DIFFERENT arguments and is even valid: the
    # explicit mapping must win on content, not just on admission.
    ambient = _write_launch_arguments(
        tmp_path,
        {"projectId": "ambient-project"},
        name="ambient-args.json",
    )
    explicit = {"projectId": "explicit-project"}
    composition = compose_t3_native_adapter(
        runtime,
        inspector=FakeInspector(),
        token_file=token_file,
        launch_arguments=explicit,
        transport_factory=lambda url, token: RecordingTransport(url, token),
        state_store=SQLiteT3AdapterStateStore(tmp_path / "state.sqlite3"),
        environ={T3_LAUNCH_ARGUMENTS_FILE_ENV: str(ambient)},
    )
    assert composition.status == COMPOSITION_COMPOSED
    assert composition.composed
    port = composition.adapter._port
    assert port._launch_arguments == {"projectId": "explicit-project"}


def test_ambient_launch_arguments_env_var_is_never_consulted_for_explicit_args(
    tmp_path,
):
    # The L1B3-2 failure shape sharpened: the ambient env var may name a
    # MISSING or MALFORMED file — still no refusal, because it is never
    # read when the caller passed an explicit mapping.
    runtime, token_file = _enrolled_runtime(tmp_path)
    for label, env_value in (
        ("missing file", str(tmp_path / "absent-args.json")),
        ("malformed file", str(_write_launch_arguments(
            tmp_path, {"projectId": "  "}, name="blank-args.json",
        ))),
    ):
        composition = compose_t3_native_adapter(
            runtime,
            inspector=FakeInspector(),
            token_file=token_file,
            launch_arguments={"projectId": "explicit-project"},
            state_store=SQLiteT3AdapterStateStore(
                tmp_path / f"state-{label.replace(' ', '-')}.sqlite3"
            ),
            environ={T3_LAUNCH_ARGUMENTS_FILE_ENV: env_value},
        )
        assert composition.status == COMPOSITION_COMPOSED, label


def test_both_explicit_launch_argument_sources_are_refused(tmp_path):
    # The both-sources refusal fires ONLY on the EXPLICIT call (both
    # launch_arguments and launch_arguments_file passed by the caller) —
    # zero coverage before L1B3-2.
    runtime, token_file = _enrolled_runtime(tmp_path)
    launch_arguments_file = _write_launch_arguments(tmp_path)
    composition = compose_t3_native_adapter(
        runtime,
        inspector=FakeInspector(),
        token_file=token_file,
        launch_arguments={"projectId": "explicit-project"},
        launch_arguments_file=launch_arguments_file,
        state_store=SQLiteT3AdapterStateStore(tmp_path / "state.sqlite3"),
        environ={},
    )
    assert composition.status == COMPOSITION_ENROLLMENT_BROKEN
    assert not composition.composed
    assert composition.adapter is None
    assert "launch_arguments" in composition.reason
    assert "launch_arguments_file" in composition.reason


def test_port_factory_ignores_the_ambient_launch_arguments_env_var(tmp_path):
    # L1B3-3 (MEDIUM): a port_factory caller owns port construction (launch
    # arguments ride the factory), so the env-named file is neither required
    # nor read, validated and then silently dropped — even a MALFORMED
    # env-named file must not refuse the composition.
    runtime, token_file = _enrolled_runtime(tmp_path)
    malformed = _write_launch_arguments(
        tmp_path, {"projectId": "  "}, name="malformed-args.json"
    )
    composition = compose_t3_native_adapter(
        runtime,
        inspector=FakeInspector(),
        token_file=token_file,
        port_factory=lambda _token: CountingT3Port(
            principal="oauth-client-compose"
        ),
        state_store=SQLiteT3AdapterStateStore(tmp_path / "state.sqlite3"),
        environ={T3_LAUNCH_ARGUMENTS_FILE_ENV: str(malformed)},
    )
    assert composition.status == COMPOSITION_COMPOSED
    assert composition.composed


def test_port_factory_with_explicit_launch_arguments_is_refused(tmp_path):
    # L1B3-3: no caller combines port_factory with an explicit
    # launch-arguments source (the canary rides arguments inside its own
    # factory), so the contradictory combination is a typed refusal at
    # composition time — never validated and then silently dropped.
    runtime, token_file = _enrolled_runtime(tmp_path)
    with pytest.raises(T3NativeCompositionError) as caught:
        compose_t3_native_adapter(
            runtime,
            inspector=FakeInspector(),
            token_file=token_file,
            port_factory=lambda _token: CountingT3Port(
                principal="oauth-client-compose"
            ),
            launch_arguments={"projectId": "explicit-project"},
            state_store=SQLiteT3AdapterStateStore(tmp_path / "state.sqlite3"),
            environ={},
        )
    assert "port_factory" in str(caught.value)
    # The explicit file source is the same contradictory combination.
    launch_arguments_file = _write_launch_arguments(tmp_path)
    with pytest.raises(T3NativeCompositionError) as caught:
        compose_t3_native_adapter(
            runtime,
            inspector=FakeInspector(),
            token_file=token_file,
            port_factory=lambda _token: CountingT3Port(
                principal="oauth-client-compose"
            ),
            launch_arguments_file=launch_arguments_file,
            state_store=SQLiteT3AdapterStateStore(tmp_path / "state.sqlite3"),
            environ={},
        )
    assert "port_factory" in str(caught.value)


def test_launch_arguments_provider_instance_is_admitted_and_kept_off_the_wire(tmp_path):
    # Lead review L1: the host names the T3 provider instance serving the
    # claimed model; the port holds it for modelSelection, never top-level.
    runtime, token_file = _enrolled_runtime(tmp_path)
    path = _write_launch_arguments(
        tmp_path, {"projectId": "p-1", "providerInstanceId": "capacity_fabric"})
    composition = compose_t3_native_adapter(
        runtime, inspector=FakeInspector(), token_file=token_file,
        launch_arguments_file=path,
        transport_factory=lambda url, token: RecordingTransport(url, token),
        state_store=SQLiteT3AdapterStateStore(tmp_path / "state.sqlite3"),
        environ={},
    )
    assert composition.status == COMPOSITION_COMPOSED
    port = composition.adapter._port
    assert port._launch_arguments == {"projectId": "p-1"}
    assert port._provider_instance_id == "capacity_fabric"


def test_launch_arguments_blank_provider_instance_is_refused(tmp_path):
    runtime, token_file = _enrolled_runtime(tmp_path)
    path = _write_launch_arguments(
        tmp_path, {"projectId": "p-1", "providerInstanceId": " "})
    composition = compose_t3_native_adapter(
        runtime, inspector=FakeInspector(), token_file=token_file,
        launch_arguments_file=path,
        state_store=SQLiteT3AdapterStateStore(tmp_path / "state.sqlite3"),
        environ={},
    )
    assert composition.status == COMPOSITION_ENROLLMENT_BROKEN
    assert "providerInstanceId" in composition.reason
