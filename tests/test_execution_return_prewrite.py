"""Original-return qualification at the real broker prewrite boundary.

The Executive SQLite transaction and broker framing implementation are real.
Native admissions and the socket peer are disposable in-memory fixtures; no
installed service, grant, provider, or live message is used by these tests.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from control_plane.execution_return_wiring import (
    EXECUTION_RETURN_DELIVERY_EVENT,
    EXECUTION_RETURN_INTENT_EVENT,
    EXECUTION_RETURN_RECONCILED_EVENT,
    EXECUTION_RETURN_REFUSED_EVENT,
    ExecutionReturnWiring,
    GitHubEvidenceSource,
    execution_return_intent_command_id,
    execution_return_receipt_command_id,
)
from control_plane.executive_runtime import Runtime, RuntimeStore
from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
from control_plane.remote_worker_transport import (
    BrokerTransportBinding,
    TransportEffect,
    TransportError,
    build_secretary_response,
    decode_secretary_request,
    encode_frame,
)
from integrations.session_bridge.hermes_native_return import (
    HermesExecutionReturnDeliverer,
    SecretaryNativeSendTransport,
)

JOB = "JOB-return-qualification"
ATTEMPT = "ATT-return-qualification"
SESSION = "sess-return-qualification"
NAMESPACE = "mastermind.control_plane.t3_execution_adapter/v1:hermes-eng-seat-1"
NATIVE_SCHEMA = "mastermind.hermes_secretary_native_control/v1"


def native_digest(text):
    return hashlib.sha256(json.dumps(
        {"text": text, "finite": True}, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode("utf-8")).hexdigest()


def native_binding():
    return {"schema": "mastermind.session_bridge.hermes_secretary_binding.v1",
            "profile_id": "qualification", "session_id": SESSION,
            "principal_id": "return-fixture"}


def native_target():
    return {**{k: v for k, v in native_binding().items() if k != "schema"},
            "instance_id": "fixture-instance", "authority_epoch": 1,
            "revision": 0, "execution_generation": 0}


@pytest.fixture
def sealed(tmp_path):
    runtime = Runtime.at(tmp_path / "executive")
    runtime.workers.register_worker(
        "return-worker", provider="fixture", account_label="disposable",
        worker_type="fixture", capabilities=["coding"], quota_classes=["return-test"])
    result = json.dumps({"summary": "Sealed result → original conversation", "artifacts": ["result.txt"]})
    # Seed terminal fixtures, not an admitted execution. Real foreign keys,
    # event constraints, transaction ownership and uniqueness remain enabled.
    with runtime.store.transaction() as connection:
        connection.execute("""
            INSERT INTO jobs(job_id,objective,department,status,assigned_worker_id,
                assigned_quota_class,current_attempt_id,authority_level,branch,
                constraints_json,requested_authorities_json,authority_policy_hash,
                result_json,available_at_ms,created_at_ms,updated_at_ms,root_job_id)
            VALUES(?, 'Return qualification','engineering','COMPLETED','return-worker',
                'return-test',?,'A0','t3/return-qualification','{}','[]',?,?,1,1,1,?)
        """, (JOB, ATTEMPT, "0" * 64, result, JOB))
        connection.execute("""
            INSERT INTO attempts(attempt_id,job_id,attempt_number,worker_id,quota_class,
                status,fence_generation,authority_policy_hash,lease_owner,lease_expires_at_ms,
                heartbeat_at_ms,result_json,started_at_ms,finished_at_ms,created_at_ms,updated_at_ms)
            VALUES(?,?,1,'return-worker','return-test','COMPLETED',1,?,'fixture',1,1,?,1,2,1,2)
        """, (ATTEMPT, JOB, "0" * 64, result))
        runtime.store.append_event(
            connection, aggregate_type="job", aggregate_id=JOB, event_type="JOB_CREATED", job_id=JOB,
            payload={"provenance": {"original_requester": {
                "teammate_id": "hermes-engineering", "conversation_id": SESSION,
                "project_id": "proj-return-qualification"},
                "child_request": {"command_id": "return-child-1"}}}, command_id="return-job-fixture")
        runtime.store.append_event(
            connection, aggregate_type="attempt", aggregate_id=ATTEMPT,
            event_type="JOB_CLAIMED", job_id=JOB, attempt_id=ATTEMPT,
            payload={"execution_binding": {"runtime_kind": "t3-native"}},
            command_id="return-claim-fixture")
    return runtime.store, runtime.jobs.get_job(JOB)


class NativeOwner:
    def __init__(self, store):
        self.store = store
        self.operations = []
        self.admissions = {}
        self.requests = {}
        self.lock = threading.Lock()
        self.drop_submit_reply = False
        self.read_result = None

    def receive(self, request):
        with self.lock:
            operation = request["operation"]
            if operation == "submit":
                original = self.store.get_event_by_command_id(execution_return_intent_command_id(ATTEMPT))
                assert original is not None, "frame reached native owner without committed intent"
                assert original.payload["native"]["request"] == request
                submission = request["submission_id"]
                self.requests[submission] = request
                self.admissions[submission] = {
                    "admission_id": "adm-original", "ref": {"profile_id": "qualification", "session_id": SESSION},
                    "sequence": 1, "status": "queued", "outcome": None,
                    "authority_epoch": 1, "execution_generation": None,
                }
                result = {"schema": NATIVE_SCHEMA, "status": "ADMITTED",
                          "admission": self.admissions[submission]}
            elif operation == "read_original":
                assert set(request) == {"operation", "session_id", "submission_id", "input_sha256"}
                submission = request["submission_id"]
                prior = self.requests.get(submission)
                if self.read_result is not None:
                    result = self.read_result
                elif (prior is not None and request["session_id"] == SESSION
                      and request["input_sha256"] == native_digest(prior["text"])):
                    result = {"schema": NATIVE_SCHEMA, "status": "OBSERVED",
                              "admission": self.admissions[submission]}
                else:
                    result = {"schema": NATIVE_SCHEMA, "status": "EFFECT_UNKNOWN"}
            else:
                raise AssertionError("return recovery must not observe, select or create a session")
            self.operations.append(operation)
            return result


class _Reader:
    def __init__(self):
        self.data = b""
        self.drop = False

    async def readexactly(self, count):
        if self.drop:
            raise asyncio.IncompleteReadError(b"", count)
        answer, self.data = self.data[:count], self.data[count:]
        return answer


class _Writer:
    def __init__(self, owner, reader):
        self.owner, self.reader = owner, reader

    def write(self, frame):
        wire = decode_secretary_request(frame[4:])
        result = self.owner.receive(wire["request"])
        response = build_secretary_response(wire, outcome="ok", result=result)
        self.reader.data = encode_frame(json.dumps(response, sort_keys=True, separators=(",", ":")).encode())
        if wire["request"]["operation"] == "submit" and self.owner.drop_submit_reply:
            self.owner.drop_submit_reply = False
            self.reader.drop = True

    async def drain(self):
        pass

    def close(self):
        pass


class GuardError(Exception):
    code = "binding_unavailable"


class NativeSession:
    """The session guard seam around the real broker request implementation."""

    def __init__(self, client):
        self.client = client
        self.submit_checks = 0
        self.submit_guard = None
        self.binding_available = True
        self.after_submit = None

    def require_binding(self, binding):
        if not self.binding_available or binding != native_binding():
            raise GuardError("original binding unavailable")

    def require_submit(self, binding):
        self.submit_checks += 1
        self.require_binding(binding)
        if self.submit_guard is not None:
            self.submit_guard(self.submit_checks)

    async def request(self, binding, native_request, *, before_write=None):
        self.require_binding(binding)
        result = await self.client.request_secretary(native_request, before_write=before_write)
        if native_request["operation"] == "submit" and self.after_submit is not None:
            self.after_submit()
        self.require_binding(binding)
        return result


def native_session(tmp_path, owner, *, barrier=None):
    certificate = tmp_path / "unused-test-certificate"
    certificate.write_text("not used: the socket peer is injected")
    transport = BrokerTransportBinding(
        endpoint=("localhost", 443), ca_path=certificate, client_cert_path=certificate,
        client_key_path=certificate, expected_server_fingerprint="a" * 64, timeout_seconds=5)
    client = RemoteWorkerBrokerClient.for_secretary_conversation(
        transport, host_ref="host-" + "1" * 64, root_id=JOB, session_id=SESSION,
        expected_host_binding_sha256="2" * 64, expected_implementation_sha="3" * 40)
    first = True

    async def connect():
        nonlocal first
        if first and barrier is not None:
            first = False
            barrier.wait(timeout=5)
        reader = _Reader()
        return reader, _Writer(owner, reader)

    client._open_connection = connect
    client._server_pin_matches = lambda writer: True
    return NativeSession(client)


def wiring(store, session, *, github=None, target=None):
    adapter = SimpleNamespace(
        launch_receipt=lambda run: SimpleNamespace(request_namespace=NAMESPACE),
        result_ledger_entry=lambda run: SimpleNamespace(result_ref="result.txt", thread_id="thread-original"))
    deliverer = HermesExecutionReturnDeliverer(
        SecretaryNativeSendTransport(session, native_binding(), target=target or native_target()))
    return ExecutionReturnWiring(store=store, deliverer=deliverer, t3_adapter=adapter, github=github)


def return_events(store):
    return [event for event in store.list_events(job_id=JOB)
            if event.event_type.startswith("EXECUTION_RETURN_")]


def fresh_store(store):
    return RuntimeStore(store.root, create=False, existing_writable=True)


def test_real_client_requires_prewrite_before_any_frame(sealed, tmp_path):
    store, job = sealed
    owner = NativeOwner(store)
    session = native_session(tmp_path, owner)
    with pytest.raises(TransportError) as error:
        asyncio.run(session.client.request_secretary({
            "operation": "submit", "target": native_target(), "submission_id": "submission-1", "text": "finite"}))
    assert error.value.code == "before_write_required"
    assert error.value.classification is TransportEffect.NO_EFFECT
    assert owner.operations == []


def test_real_frame_follows_committed_intent_and_retains_not_accepted(sealed, tmp_path):
    store, job = sealed
    owner = NativeOwner(store)
    session = native_session(tmp_path, owner)
    seam = wiring(store, session)
    receipt = seam.deliver(job=job, status=job.status)
    assert receipt["state"] == "delivered"
    assert owner.operations == ["submit"]
    assert session.submit_checks == 3
    events = return_events(store)
    assert [e.event_type for e in events] == [EXECUTION_RETURN_INTENT_EVENT, EXECUTION_RETURN_DELIVERY_EVENT]
    original = events[0].payload
    assert original["record"]["acceptance"] == "not_accepted"
    assert original["native"]["input_sha256"] == native_digest(original["native"]["request"]["text"])
    assert seam.deliver(job=job, status=job.status) == receipt
    assert owner.operations == ["submit"]


def test_two_independent_wirings_have_one_submit_at_transaction_boundary(sealed, tmp_path):
    store, job = sealed
    owner = NativeOwner(store)
    barrier = threading.Barrier(2)
    sessions = [native_session(tmp_path, owner, barrier=barrier) for _ in range(2)]
    seams = [wiring(fresh_store(store), session) for session in sessions]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(seam.deliver, job=job, status=job.status) for seam in seams]
        receipts = [future.result(timeout=10) for future in futures]
    assert all(receipt is not None and receipt["state"] != "refused" for receipt in receipts)
    assert owner.operations.count("submit") == 1
    assert len([e for e in return_events(store) if e.event_type == EXECUTION_RETURN_INTENT_EVENT]) == 1
    assert len([e for e in return_events(store) if e.event_type == EXECUTION_RETURN_DELIVERY_EVENT]) == 1
    final = wiring(fresh_store(store), native_session(tmp_path, owner)).deliver(job=job, status=job.status)
    assert final["state"] == "delivered"
    assert owner.operations.count("submit") == 1


class SimulatedProcessCrash(BaseException):
    pass


def test_crash_after_intent_before_write_never_resubmits_even_when_original_absent(sealed, tmp_path, monkeypatch):
    store, job = sealed
    owner = NativeOwner(store)
    transaction = store.transaction

    @contextmanager
    def crash_after_intent_commit():
        with transaction() as connection:
            yield connection
        if store.get_event_by_command_id(execution_return_intent_command_id(ATTEMPT)) is not None:
            raise SimulatedProcessCrash()

    monkeypatch.setattr(store, "transaction", crash_after_intent_commit)
    with pytest.raises(SimulatedProcessCrash):
        wiring(store, native_session(tmp_path, owner)).deliver(job=job, status=job.status)
    assert [e.event_type for e in return_events(store)] == [EXECUTION_RETURN_INTENT_EVENT]
    assert owner.operations == []
    for _ in range(3):
        receipt = wiring(fresh_store(store), native_session(tmp_path, owner)).deliver(job=job, status=job.status)
        assert receipt["state"] == "unknown"
    assert owner.operations == ["read_original"] * 3
    assert len(return_events(store)) == 2  # no event growth for unchanged unknown reads


def test_lost_reply_recovers_original_and_keeps_first_receipt_immutable(sealed, tmp_path):
    store, job = sealed
    owner = NativeOwner(store)
    owner.drop_submit_reply = True
    first = wiring(store, native_session(tmp_path, owner)).deliver(job=job, status=job.status)
    assert first["state"] == "unknown"
    original_event = store.get_event_by_command_id(execution_return_intent_command_id(ATTEMPT))
    first_receipt = store.get_event_by_command_id(execution_return_receipt_command_id(ATTEMPT))
    session = native_session(tmp_path, owner)
    session.submit_guard = lambda count: pytest.fail("recovery must not require submit authority")
    receipt = wiring(fresh_store(store), session).deliver(job=job, status=job.status)
    assert receipt["state"] == "delivered" and receipt["transport_ref"] == "adm-original"
    assert owner.operations == ["submit", "read_original"]
    assert store.get_event_by_command_id(execution_return_receipt_command_id(ATTEMPT)) == first_receipt
    assert store.get_event_by_command_id(execution_return_intent_command_id(ATTEMPT)) == original_event
    assert [e.event_type for e in return_events(store)] == [
        EXECUTION_RETURN_INTENT_EVENT, EXECUTION_RETURN_DELIVERY_EVENT, EXECUTION_RETURN_RECONCILED_EVENT]
    assert wiring(fresh_store(store), session).deliver(job=job, status=job.status) == receipt
    assert owner.operations == ["submit", "read_original"]


def test_receipt_persistence_failure_is_not_a_clean_refusal_and_recovers(sealed, tmp_path, monkeypatch):
    store, job = sealed
    owner = NativeOwner(store)
    append = store.append_event

    def fail_receipt(connection, **kwargs):
        if kwargs["event_type"] == EXECUTION_RETURN_DELIVERY_EVENT:
            raise OSError("simulated receipt persistence failure")
        return append(connection, **kwargs)

    monkeypatch.setattr(store, "append_event", fail_receipt)
    assert wiring(store, native_session(tmp_path, owner)).deliver(job=job, status=job.status) is None
    assert [e.event_type for e in return_events(store)] == [EXECUTION_RETURN_INTENT_EVENT]
    receipt = wiring(fresh_store(store), native_session(tmp_path, owner)).deliver(job=job, status=job.status)
    assert receipt["state"] == "delivered"
    assert owner.operations == ["submit", "read_original"]
    assert all(e.event_type != EXECUTION_RETURN_REFUSED_EVENT for e in return_events(store))


def test_intent_commit_failure_produces_no_frame(sealed, tmp_path, monkeypatch):
    store, job = sealed
    owner = NativeOwner(store)
    append = store.append_event

    def fail_intent(connection, **kwargs):
        if kwargs["event_type"] == EXECUTION_RETURN_INTENT_EVENT:
            raise OSError("simulated intent write failure")
        return append(connection, **kwargs)

    monkeypatch.setattr(store, "append_event", fail_intent)
    receipt = wiring(store, native_session(tmp_path, owner)).deliver(job=job, status=job.status)
    assert receipt["state"] == "refused"
    assert owner.operations == []
    assert store.get_event_by_command_id(execution_return_intent_command_id(ATTEMPT)) is None


def test_lost_commit_reply_recovers_original_without_false_clean_refusal(sealed, tmp_path, monkeypatch):
    store, job = sealed
    owner = NativeOwner(store)
    transaction = store.transaction
    lost = False

    @contextmanager
    def lose_intent_commit_reply():
        nonlocal lost
        with transaction() as connection:
            yield connection
        if not lost and store.get_event_by_command_id(execution_return_intent_command_id(ATTEMPT)) is not None:
            lost = True
            raise OSError("commit succeeded, callback did not receive its result")

    monkeypatch.setattr(store, "transaction", lose_intent_commit_reply)
    receipt = wiring(store, native_session(tmp_path, owner)).deliver(job=job, status=job.status)
    assert receipt["state"] == "unknown" and receipt["refusal_code"] is None
    assert owner.operations == ["read_original"]
    assert [e.event_type for e in return_events(store)] == [EXECUTION_RETURN_INTENT_EVENT, EXECUTION_RETURN_DELIVERY_EVENT]
    assert wiring(fresh_store(store), native_session(tmp_path, owner)).deliver(job=job, status=job.status)["state"] == "unknown"
    assert owner.operations == ["read_original", "read_original"]


def test_revoked_submit_guard_after_intent_cannot_write_or_resend(sealed, tmp_path):
    store, job = sealed
    owner = NativeOwner(store)
    session = native_session(tmp_path, owner)

    def revoke(count):
        if count == 3:
            raise GuardError("submit grant changed after durable intent")

    session.submit_guard = revoke
    receipt = wiring(store, session).deliver(job=job, status=job.status)
    assert receipt["state"] == "refused"  # the real broker proves this frame was not written
    assert owner.operations == []
    assert store.get_event_by_command_id(execution_return_intent_command_id(ATTEMPT)) is not None
    assert wiring(fresh_store(store), native_session(tmp_path, owner)).deliver(job=job, status=job.status) == receipt
    assert owner.operations == []


def test_post_send_binding_failure_remains_unknown(sealed, tmp_path):
    store, job = sealed
    owner = NativeOwner(store)
    session = native_session(tmp_path, owner)
    session.after_submit = lambda: setattr(session, "binding_available", False)
    receipt = wiring(store, session).deliver(job=job, status=job.status)
    assert receipt["state"] == "unknown"
    assert owner.operations == ["submit"]
    assert wiring(fresh_store(store), native_session(tmp_path, owner)).deliver(job=job, status=job.status)["state"] == "delivered"


def test_changed_github_evidence_is_not_reprojected_during_recovery(sealed, tmp_path):
    store, job = sealed
    owner = NativeOwner(store)
    owner.drop_submit_reply = True

    class Evidence:
        reads = 0
        changed = False

        def pr_view(self, repository, branch):
            self.reads += 1
            return {"number": 2338, "headRefName": branch, "url": "https://github.com/example/repo/pull/2338",
                    "state": "MERGED" if self.changed else "OPEN",
                    "mergedAt": "2026-11-10T00:00:00Z" if self.changed else None}

        def pr_checks(self, repository, number):
            return [{"name": "ci", "conclusion": "success" if self.changed else "failure"}]

    evidence = Evidence()
    github = GitHubEvidenceSource(repository="example/repo", port=evidence)
    first = wiring(store, native_session(tmp_path, owner), github=github).deliver(job=job, status=job.status)
    intent = store.get_event_by_command_id(execution_return_intent_command_id(ATTEMPT)).payload
    evidence.changed = True
    changed_target = {**native_target(), "revision": 17, "execution_generation": 3}
    receipt = wiring(fresh_store(store), native_session(tmp_path, owner), github=github,
                     target=changed_target).deliver(job=job, status=job.status)
    assert evidence.reads == 1
    assert receipt["state"] == "delivered" and receipt["return_digest"] == first["return_digest"]
    assert store.get_event_by_command_id(execution_return_intent_command_id(ATTEMPT)).payload == intent
    assert owner.operations == ["submit", "read_original"]


@pytest.mark.parametrize("read_result", [
    {"schema": NATIVE_SCHEMA, "status": "EFFECT_UNKNOWN"},
    {"schema": NATIVE_SCHEMA, "status": "REFUSED", "reason": "NATIVE_SECRETARY_ORIGINAL_MISMATCH"},
    {"schema": NATIVE_SCHEMA, "status": "OBSERVED", "admission": {
        "admission_id": "adm-foreign", "ref": {"profile_id": "qualification", "session_id": "foreign"},
        "sequence": 1, "status": "queued", "authority_epoch": 1}},
])
def test_missing_or_mismatched_original_never_becomes_delivered_or_resubmitted(sealed, tmp_path, read_result):
    store, job = sealed
    owner = NativeOwner(store)
    owner.drop_submit_reply = True
    assert wiring(store, native_session(tmp_path, owner)).deliver(job=job, status=job.status)["state"] == "unknown"
    owner.read_result = read_result
    for _ in range(2):
        receipt = wiring(fresh_store(store), native_session(tmp_path, owner)).deliver(job=job, status=job.status)
        assert receipt["state"] == "unknown" and receipt["refusal_code"] is None
    assert owner.operations == ["submit", "read_original", "read_original"]
    assert len(return_events(store)) == 2


def test_missing_launch_binding_is_diagnostic_without_fabricated_receipt(sealed, tmp_path):
    store, job = sealed
    owner = NativeOwner(store)
    deliverer = HermesExecutionReturnDeliverer(
        SecretaryNativeSendTransport(native_session(tmp_path, owner), native_binding(), target=native_target()))
    assert ExecutionReturnWiring(store=store, deliverer=deliverer).deliver(job=job, status=job.status) is None
    events = return_events(store)
    assert len(events) == 1 and events[0].event_type == EXECUTION_RETURN_REFUSED_EVENT
    assert events[0].payload["refusal_code"] == "ORIGINAL_BINDING_MISSING"
    assert "delivery" not in events[0].payload
    assert owner.operations == []


def test_receipt_with_foreign_intent_digest_cannot_claim_delivery(sealed, tmp_path, monkeypatch):
    store, job = sealed
    owner = NativeOwner(store)
    assert wiring(store, native_session(tmp_path, owner)).deliver(job=job, status=job.status)["state"] == "delivered"
    read = store.get_event_by_command_id

    def corrupt_receipt(command, **kwargs):
        event = read(command, **kwargs)
        if command == execution_return_receipt_command_id(ATTEMPT):
            event.payload["intent_digest"] = "f" * 64
        return event

    monkeypatch.setattr(store, "get_event_by_command_id", corrupt_receipt)
    assert wiring(store, native_session(tmp_path, owner)).deliver(job=job, status=job.status) is None
    assert owner.operations == ["submit"]
