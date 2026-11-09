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
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import pytest

from control_plane.t3_native_composition import (
    COMPOSITION_COMPOSED,
    COMPOSITION_NOT_ENROLLED,
    STORE_BASIS_CHECKOUT_DEFAULT,
    STORE_BASIS_EXECUTIVE_DATA_DIR,
    T3_MCP_ACCESS_TOKEN_FILE_ENV,
    T3McpHttpTransport,
    T3NativeCompositionError,
    T3NativeProcessController,
    compose_t3_native_adapter,
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
from control_plane.t3_execution_adapter import SQLiteT3AdapterStateStore
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


def test_empty_token_file_is_typed_not_enrolled(tmp_path):
    token_file = tmp_path / "empty-token"
    token_file.write_text("   \n", encoding="utf-8")
    composition = compose_t3_native_adapter(
        Runtime.at(tmp_path),
        inspector=FakeInspector(),
        token_file=token_file,
        environ={},
    )
    assert composition.status == COMPOSITION_NOT_ENROLLED
    assert "empty" in composition.reason


def test_missing_token_file_is_typed_not_enrolled(tmp_path):
    composition = compose_t3_native_adapter(
        Runtime.at(tmp_path),
        inspector=FakeInspector(),
        token_file=tmp_path / "absent-token",
        environ={},
    )
    assert composition.status == COMPOSITION_NOT_ENROLLED


def test_token_file_resolution_prefers_explicit_then_environment(tmp_path):
    explicit = tmp_path / "explicit-token"
    assert resolve_t3_access_token_file(explicit) == explicit
    env_file = tmp_path / "env-token"
    resolved = resolve_t3_access_token_file(
        None, environ={T3_MCP_ACCESS_TOKEN_FILE_ENV: str(env_file)}
    )
    assert resolved == env_file
    assert resolve_t3_access_token_file(None, environ={}) is None


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
    recording: dict[str, RecordingTransport] = {}

    def transport_factory(url, access_token):
        transport = RecordingTransport(url, access_token)
        recording["transport"] = transport
        return transport

    composition = compose_t3_native_adapter(
        runtime,
        inspector=FakeInspector(),
        token_file=token_file,
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
    assert "t3" not in live["providers"]  # the live file stays untouched
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
