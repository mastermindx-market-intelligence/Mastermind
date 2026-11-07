"""Native Secretary continuation over the real bounded Runtime readers.

These tests exercise the existing Runtime read owners with a stored native
Secretary request Event. They are source/library proofs only: no native
provider turn, no installed SessionBridge, no Office integration and no
product acceptance is claimed here.
"""
import hashlib
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane import executive_runtime as er
from control_plane import native_continuation as nc
from control_plane.executive_runtime import Runtime
from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.session_bridge import runtime_return as module
from integrations.session_bridge.runtime_owner import (
    RuntimeFabricTarget, RuntimeFabricTargetProjector, RuntimeCodexTargetProjector,
)
from test_workspace_agent_runtime_binding import physical, source, target

NATIVE_SESSION = "11111111-2222-4444-8888-999999999999"

BINDING = {
    "schema": nc.HERMES_BINDING_SCHEMA,
    "composition_sha256": "a" * 64,
    "host_ref": "host-" + "b" * 64,
    "root_id": "hermes-prod-01",
    "root_job_id": "JOB-001",
    "work_ref": "WS:WORKSPACE-AGENT-PROGRAM",
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

OFFICE_ISSUER = "https://auth.test/"

OFFICE_PRINCIPAL = {
    "policy_id": "office-submit",
    "issuer_digest": hashlib.sha256(OFFICE_ISSUER.encode("utf-8")).hexdigest(),
    "resource": "https://executive.test/mcp",
    "subject_digest": "f" * 64,
    "client_ref": "1" * 64,
}


def identity(principal=None):
    principal = OFFICE_PRINCIPAL if principal is None else principal
    return tuple(principal[key] for key in nc._IDENTITY)


class Service:
    """No Dialogue carrier is exercised by these reader proofs."""

    def __init__(self):
        self.calls = []

    async def __call__(self, path, payload, *, before_write=None):
        self.calls.append(payload)
        return {"ok": True, "result": {"messages": [], "historical_messages": [],
                                       "mutated_count": 0}}


@pytest.fixture(params=nc.HERMES_KINDS)
def runtime(tmp_path, monkeypatch, request):
    """One real Runtime with one legacy and one native continuation request."""
    store = Runtime.at(tmp_path / "runtime")
    store.workers.register_worker("worker-01", provider="codex", account_label="test",
                                  worker_type="codex", quota_classes=["default"])
    job = store.jobs.create_job("Native Secretary bounded continuation")
    lease = store.attempts.claim_job(job.job_id, worker_id="worker-01",
                                     quota_class="default")
    epoch = target(root_job_id=job.job_id, job_id=job.job_id,
                   attempt_id=lease.attempt.attempt_id,
                   harness_provider_session_id=NATIVE_SESSION)
    original = RuntimeFabricTarget(
        target_ref="fabric_attempt:" + "1" * 64, operation_key="exec-job-001",
        epoch=epoch, source=source(),
        physical=physical(root_job_id=job.job_id, job_id=job.job_id,
                          attempt_id=lease.attempt.attempt_id,
                          operation_key="exec-job-001"), generation="g1")
    fabric = RuntimeFabricTargetProjector(store)
    monkeypatch.setattr(fabric, "resolve",
                        lambda ref: original if ref == original.target_ref else None)
    codex = RuntimeCodexTargetProjector(fabric, owner_configured=lambda: True)
    facts = SimpleNamespace(job_id=job.job_id, worker_id=epoch.worker_id,
        attempt_id=lease.attempt.attempt_id, session_epoch_id=epoch.harness_session_epoch_id,
        generation_number=epoch.harness_generation_number,
        provider_session_id=NATIVE_SESSION, process_generation_id="process-01")
    monkeypatch.setattr(Runtime, "current_harness_binding_source", lambda *a, **k: facts)
    monkeypatch.setattr(module, "_read_current_target", lambda *a: epoch)
    monkeypatch.setattr(module, "_read_dialogue_source", lambda *a: source())
    owner = module.RuntimeSessionReturn(store, fabric=fabric, codex=codex,
        socket_path=Path("/private/tmp/native-secretary.sock"), service_call=Service())
    binding = codex.resolve("codex:" + "1" * 64).reply_binding()
    now = int(time.time())
    principal = VerifiedPrincipal(policy_id=OFFICE_PRINCIPAL["policy_id"],
        issuer=OFFICE_ISSUER,
        issuer_digest=OFFICE_PRINCIPAL["issuer_digest"],
        resource=OFFICE_PRINCIPAL["resource"],
        subject_digest=OFFICE_PRINCIPAL["subject_digest"],
        client_ref=OFFICE_PRINCIPAL["client_ref"],
        scopes=("mastermind.executive.read", "mastermind.executive.intent.submit"),
        issued_at=now - 10, expires_at=now + 3600, jti_digest=None)
    legacy_args = dict(target_ref=binding.target_ref,
                       operation_key=binding.continuation_operation_key,
                       instruction="Read and return the bounded finding.",
                       stop_condition="Return one finding.")
    legacy_ref = owner.bind_request(principal_projection(principal), legacy_args)
    root = store.store.unique_root_created_event(job.job_id)
    family = nc.hermes_family(request.param)
    native_binding = {**BINDING, "root_job_id": job.job_id, "schema": family.binding_schema}
    native_target = nc.build_hermes_continuation_target(
        binding=native_binding, root_event=root, native_target=NATIVE_TARGET)
    native_payload = nc.build_hermes_continuation_request(
        principal=OFFICE_PRINCIPAL, binding=native_binding, root_event=root,
        native_target=NATIVE_TARGET,
        arguments={"target_ref": native_target["target_ref"],
                   "instruction": "Read and return the bounded finding.",
                   "stop_condition": "Return one finding.",
                   "operation_key": native_target["continuation_operation_key"]})
    request_key = nc._request_key(native_payload["operation_key"])
    with store.store.transaction() as connection:
        store.store.append_event(
            connection, aggregate_type="session_bridge_continue",
            aggregate_id=request_key, event_type=nc._EVENT, actor=nc._ACTOR,
            job_id=native_payload["root_job_id"], attempt_id=None, worker_id=None,
            payload=native_payload,
            command_id=nc._PREFIX + request_key)
    return SimpleNamespace(runtime=store, owner=owner, job=job, root=root, family=family,
                            legacy_ref=legacy_ref, native_ref=native_payload["read_ref"],
                            native_payload=native_payload, native_target=native_target,
                            request_key=request_key, binding=native_binding)


def capture_sql(monkeypatch):
    """Record every bounded loader statement of one observation."""
    statements = []
    original = er._BoundedRoleResultLoader.execute

    def execute(self, sql, parameters=()):
        statements.append((" ".join(str(sql).split()), parameters))
        return original(self, sql, parameters)

    monkeypatch.setattr(er._BoundedRoleResultLoader, "execute", execute)
    return statements


def event_count(runtime):
    with runtime.store.read() as connection:
        return connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]


# ---------------------------------------------------------------------------
# Original request
# ---------------------------------------------------------------------------

def test_native_original_request_is_readable_with_a_valid_principal(runtime):
    with runtime.runtime.observe_bounded_read() as observation:
        event, value = observation.read_session_original_request_bounded(
            read_ref=runtime.native_ref,
            original_principals=(identity(),))
    assert event.event_type == nc._EVENT
    assert event.attempt_id is None and event.worker_id is None
    assert event.job_id == runtime.native_payload["root_job_id"]
    assert value == runtime.native_payload
    assert value["schema"] == runtime.family.request_schema


def test_native_original_request_refuses_a_foreign_or_missing_principal(runtime, monkeypatch):
    foreign = {**OFFICE_PRINCIPAL, "subject_digest": "9" * 64}
    statements = capture_sql(monkeypatch)
    with runtime.runtime.observe_bounded_read() as observation:
        with pytest.raises(er.RuntimeReadUnavailable):
            observation.read_session_original_request_bounded(
                read_ref=runtime.native_ref,
                original_principals=(identity(foreign),))
    assert not [item for item in statements if "JOB_CREATED" in item[0]]
    statements.clear()
    with runtime.runtime.observe_bounded_read() as observation:
        with pytest.raises(er.RuntimeReadUnavailable):
            observation.read_session_original_request_bounded(
                read_ref=runtime.native_ref)
    assert not [item for item in statements if "JOB_CREATED" in item[0]]
    statements.clear()
    with runtime.runtime.observe_bounded_read() as observation:
        with pytest.raises(er.RuntimeReadUnavailable):
            observation.read_session_original_request_bounded(
                read_ref=runtime.native_ref, original_principals=())
    assert not [item for item in statements if "JOB_CREATED" in item[0]]


def test_native_original_request_accepts_the_trusted_read_submit_pair(runtime):
    read_principal = {**OFFICE_PRINCIPAL, "policy_id": "office-read"}
    with runtime.runtime.observe_bounded_read() as observation:
        event, value = observation.read_session_original_request_bounded(
            read_ref=runtime.native_ref,
            original_principals=(identity(), identity(read_principal)))
    assert value["principal"]["policy_id"] == "office-submit"


def test_native_original_request_refuses_a_tampered_root(runtime):
    with runtime.runtime.store.transaction() as connection:
        runtime.runtime.store.append_event(
            connection, aggregate_type="test", aggregate_id="duplicate-root",
            event_type="JOB_CREATED", job_id=runtime.job.job_id,
            command_id="test-native-duplicate-root", payload={"duplicate": True})
    with runtime.runtime.observe_bounded_read() as observation:
        with pytest.raises(er.RuntimeReadUnavailable):
            observation.read_session_original_request_bounded(
                read_ref=runtime.native_ref, original_principals=(identity(),))


def test_legacy_original_request_keeps_its_own_reader_behavior(runtime):
    with runtime.runtime.observe_bounded_read() as observation:
        event, value = observation.read_session_original_request_bounded(
            read_ref=runtime.legacy_ref)
    assert value["schema"] == nc._SCHEMA
    assert value["job_id"] == runtime.job.job_id


# ---------------------------------------------------------------------------
# Reply evidence
# ---------------------------------------------------------------------------

def test_native_reply_evidence_returns_the_closed_five_field_shape(runtime):
    with runtime.runtime.observe_bounded_read() as observation:
        result = observation.read_session_reply_evidence_bounded(
            read_ref=runtime.native_ref, original_principals=(identity(),))
    assert len(result) == 5
    event, value, aggregate, indexed_commit, indexed_native = result
    assert event.event_id > 0
    assert value["schema"] == runtime.family.request_schema
    assert len(aggregate) == 1 and aggregate[0].event_type == nc._EVENT
    assert indexed_commit is None
    assert indexed_native is None


def test_native_reply_evidence_selects_the_native_commit(runtime):
    payload = runtime.native_payload
    body = nc.build_hermes_continuation_commit(
        runtime.runtime.events.get_event_by_command_id(nc._PREFIX + runtime.request_key),
        operation_name="submit", native_request=payload["native_request"])
    with runtime.runtime.store.transaction() as connection:
        runtime.runtime.store.append_event(
            connection, aggregate_type="session_bridge_continue",
            aggregate_id=runtime.request_key,
            event_type="SESSION_BRIDGE_CONTINUE_COMMIT_STARTED", actor=nc._ACTOR,
            job_id=payload["root_job_id"], attempt_id=None, worker_id=None,
            payload=body,
            command_id="session-bridge-continue-commit:" + runtime.request_key)
    with runtime.runtime.observe_bounded_read() as observation:
        event, value, aggregate, indexed_commit, indexed_native = (
            observation.read_session_reply_evidence_bounded(
                read_ref=runtime.native_ref, original_principals=(identity(),)))
    assert indexed_commit is not None
    assert indexed_commit.event_type == "SESSION_BRIDGE_CONTINUE_COMMIT_STARTED"
    assert indexed_native is None
    assert len(aggregate) == 2


def test_native_reply_evidence_refuses_a_foreign_global_commit(runtime):
    """A commit Event on another aggregate is never this request's commit."""
    payload = runtime.native_payload
    body = nc.build_hermes_continuation_commit(
        runtime.runtime.events.get_event_by_command_id(nc._PREFIX + runtime.request_key),
        operation_name="submit", native_request=payload["native_request"])
    with runtime.runtime.store.transaction() as connection:
        runtime.runtime.store.append_event(
            connection, aggregate_type="session_bridge_continue",
            aggregate_id="foreign-aggregate",
            event_type="SESSION_BRIDGE_CONTINUE_COMMIT_STARTED", actor=nc._ACTOR,
            job_id=payload["root_job_id"], attempt_id=None, worker_id=None,
            payload=body,
            command_id="session-bridge-continue-commit:foreign-aggregate")
    with runtime.runtime.observe_bounded_read() as observation:
        event, value, aggregate, indexed_commit, indexed_native = (
            observation.read_session_reply_evidence_bounded(
                read_ref=runtime.native_ref, original_principals=(identity(),)))
    assert indexed_commit is None
    assert indexed_native is None


def test_native_reply_evidence_refuses_a_legacy_native_reply_index(runtime):
    payload = runtime.native_payload
    with runtime.runtime.store.transaction() as connection:
        runtime.runtime.store.append_event(
            connection, aggregate_type="session_bridge_continue",
            aggregate_id=runtime.request_key,
            event_type="SESSION_BRIDGE_NATIVE_REPLY_COMMIT_STARTED", actor=nc._ACTOR,
            job_id=payload["root_job_id"], attempt_id=None, worker_id=None,
            payload={"legacy": True},
            command_id="session-bridge-native-reply-commit:" + runtime.request_key)
    with runtime.runtime.observe_bounded_read() as observation:
        with pytest.raises(er.RuntimeReadUnavailable):
            observation.read_session_reply_evidence_bounded(
                read_ref=runtime.native_ref, original_principals=(identity(),))


def test_legacy_reply_evidence_keeps_its_own_reader_behavior(runtime):
    with runtime.runtime.observe_bounded_read() as observation:
        event, value, aggregate, indexed_commit, indexed_native = (
            observation.read_session_reply_evidence_bounded(read_ref=runtime.legacy_ref))
    assert value["schema"] == nc._SCHEMA
    assert len(aggregate) == 1


# ---------------------------------------------------------------------------
# Live writer
# ---------------------------------------------------------------------------

def test_native_live_writer_is_refused_before_any_writer_query(runtime, monkeypatch):
    statements = capture_sql(monkeypatch)
    with runtime.runtime.observe_bounded_read() as observation:
        with pytest.raises(er.RuntimeReadUnavailable):
            observation.read_session_live_writer_bounded(
                read_ref=runtime.native_ref, original_principals=(identity(),))
    for forbidden in ("attempts", "FROM jobs", "workers", "worker_quota_classes",
                      "harness_session_epochs"):
        assert not [item for item in statements if forbidden in item[0]], forbidden


def test_native_live_writer_never_synthesizes_a_legacy_writer_tuple(runtime):
    with runtime.runtime.observe_bounded_read() as observation:
        with pytest.raises(er.RuntimeReadUnavailable) as error:
            observation.read_session_live_writer_bounded(
                read_ref=runtime.native_ref, original_principals=(identity(),))
    assert "live writer" in str(error.value)


# ---------------------------------------------------------------------------
# Reference pages
# ---------------------------------------------------------------------------

def test_native_request_only_reference_is_discoverable_without_a_commit(runtime):
    with runtime.runtime.observe_bounded_read() as observation:
        high_water, position, rows = observation.read_session_reply_references_bounded(
            work_ref="WS:WORKSPACE-AGENT-PROGRAM", root_job_id=None,
            original_principals=(identity(),), high_water=None,
            before_event_id=None, page_size=32)
    assert high_water > 0
    assert position is not None
    native = [row for row in rows if row["read_ref"] == runtime.native_ref]
    assert len(native) == 1
    row = native[0]
    assert set(row) == {"read_ref", "operation_key", "request_ref", "request_event_id",
                         "request_revision", "requested_at", "work_ref", "root_job_id",
                         "target_ref", "reference_only"}
    assert row["reference_only"] is True
    assert row["operation_key"] == runtime.native_payload["operation_key"]
    assert row["work_ref"] == "WS:WORKSPACE-AGENT-PROGRAM"
    assert row["root_job_id"] == runtime.native_payload["root_job_id"]
    assert row["target_ref"] == runtime.native_payload["target_ref"]
    assert row["request_ref"] == nc._PREFIX + runtime.request_key
    assert row["request_revision"] == nc._digest(
        runtime.runtime.events.get_event_by_command_id(
            nc._PREFIX + runtime.request_key).to_dict())


def test_reference_page_keeps_the_legacy_and_native_filters(runtime):
    with runtime.runtime.observe_bounded_read() as observation:
        high_water, position, rows = observation.read_session_reply_references_bounded(
            work_ref="WS:WORKSPACE-AGENT-PROGRAM", root_job_id=None,
            original_principals=(identity(),), high_water=None,
            before_event_id=None, page_size=32)
    assert {row["read_ref"] for row in rows} == {runtime.legacy_ref, runtime.native_ref}


def test_reference_page_never_reads_a_foreign_responsibility(runtime, monkeypatch):
    foreign = {**OFFICE_PRINCIPAL, "subject_digest": "9" * 64}
    statements = capture_sql(monkeypatch)
    with runtime.runtime.observe_bounded_read() as observation:
        high_water, position, rows = observation.read_session_reply_references_bounded(
            work_ref="WS:WORKSPACE-AGENT-PROGRAM", root_job_id=None,
            original_principals=(identity(foreign),), high_water=None,
            before_event_id=None, page_size=32)
    assert rows == ()
    assert not [item for item in statements if "JOB_CREATED" in item[0]]


def test_reference_page_applies_the_root_filter_before_the_root_read(runtime, monkeypatch):
    statements = capture_sql(monkeypatch)
    with runtime.runtime.observe_bounded_read() as observation:
        high_water, position, rows = observation.read_session_reply_references_bounded(
            work_ref="WS:WORKSPACE-AGENT-PROGRAM", root_job_id="JOB-999",
            original_principals=(identity(),), high_water=None,
            before_event_id=None, page_size=32)
    assert rows == ()
    assert not [item for item in statements if "JOB_CREATED" in item[0]]


def test_reference_page_keeps_its_candidate_and_window_limits(runtime):
    with runtime.runtime.observe_bounded_read() as observation:
        high_water, position, rows = observation.read_session_reply_references_bounded(
            work_ref="WS:WORKSPACE-AGENT-PROGRAM", root_job_id=None,
            original_principals=(identity(),), high_water=None,
            before_event_id=None, page_size=1)
    assert len(rows) == 1
    assert rows[0]["read_ref"] in {runtime.legacy_ref, runtime.native_ref}


def test_reference_page_rejects_an_invalid_selector(runtime):
    with runtime.runtime.observe_bounded_read() as observation:
        with pytest.raises(er.RuntimeReadUnavailable):
            observation.read_session_reply_references_bounded(
                work_ref="WS:WORKSPACE-AGENT-PROGRAM", root_job_id=None,
                original_principals=(), high_water=None,
                before_event_id=None, page_size=32)


# ---------------------------------------------------------------------------
# Effect freedom
# ---------------------------------------------------------------------------

def test_the_native_readers_never_write_durable_state(runtime):
    before = event_count(runtime.runtime)
    with runtime.runtime.observe_bounded_read() as observation:
        observation.read_session_original_request_bounded(
            read_ref=runtime.native_ref, original_principals=(identity(),))
    with runtime.runtime.observe_bounded_read() as observation:
        observation.read_session_reply_evidence_bounded(
            read_ref=runtime.native_ref, original_principals=(identity(),))
    with runtime.runtime.observe_bounded_read() as observation:
        observation.read_session_reply_references_bounded(
            work_ref="WS:WORKSPACE-AGENT-PROGRAM", root_job_id=None,
            original_principals=(identity(),), high_water=None,
            before_event_id=None, page_size=32)
    assert event_count(runtime.runtime) == before


def test_the_native_readers_require_an_explicit_principal_filter(runtime):
    """The legacy-compatible None never opens the native schema."""
    with runtime.runtime.observe_bounded_read() as observation:
        with pytest.raises(er.RuntimeReadUnavailable):
            observation.read_session_reply_evidence_bounded(
                read_ref=runtime.native_ref)
    with runtime.runtime.observe_bounded_read() as observation:
        with pytest.raises(er.RuntimeReadUnavailable):
            observation.read_session_live_writer_bounded(read_ref=runtime.native_ref)

def test_one_history_page_keeps_legacy_secretary_and_meta_originals(runtime):
    other = nc.hermes_family("hermes_meta" if runtime.family.kind == "hermes_secretary"
                             else "hermes_secretary")
    binding = dict(runtime.binding, schema=other.binding_schema)
    target = nc.build_hermes_continuation_target(
        binding=binding, root_event=runtime.root, native_target=NATIVE_TARGET)
    payload = nc.build_hermes_continuation_request(
        principal=OFFICE_PRINCIPAL, binding=binding, root_event=runtime.root,
        native_target=NATIVE_TARGET, arguments={
            "target_ref": target["target_ref"], "operation_key": target["continuation_operation_key"],
            "instruction": "Read the other exact role.", "stop_condition": "Return its original answer."})
    key = nc._request_key(payload["operation_key"])
    with runtime.runtime.store.transaction() as connection:
        runtime.runtime.store.append_event(
            connection, aggregate_type="session_bridge_continue", aggregate_id=key,
            event_type=nc._EVENT, actor=nc._ACTOR, job_id=runtime.job.job_id,
            attempt_id=None, worker_id=None, payload=payload, command_id=nc._PREFIX + key)
    with runtime.runtime.observe_bounded_read() as observation:
        _, _, rows = observation.read_session_reply_references_bounded(
            work_ref="WS:WORKSPACE-AGENT-PROGRAM", root_job_id=runtime.job.job_id,
            original_principals=(identity(),), high_water=None,
            before_event_id=None, page_size=32)
    _ = observation.receipt
    assert {row["read_ref"] for row in rows} == {
        runtime.legacy_ref, runtime.native_ref, payload["read_ref"]}
    assert {row["target_ref"].split(":", 1)[0] for row in rows} == {
        "codex", "hermes_secretary", "hermes_meta"}
    assert all(row["reference_only"] is True for row in rows)
