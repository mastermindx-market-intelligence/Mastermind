"""Real Runtime proof for the unarmed original-run ACP currentness controller.

Profile ids and digests below are an inert local fixture copied from the
incumbent capability registry into a test-owned Runtime. They do not install,
arm, or select a live source.
"""
from __future__ import annotations

import inspect
import json
from types import SimpleNamespace

import pytest

from common.acp_continuing_authority_contract import (
    MAX_REQUEST_BYTES,
    SCHEMA,
    AcpContinuingAuthorityContractError,
)
from control_plane.acp_current_authority import OriginalAcpRunController
from control_plane.executive_agent_capabilities import (
    CapabilityPolicyError,
    ExecutionCapabilityRegistry,
)
from control_plane.executive_authority import AuthorityPolicyError, ExecutiveAuthorityPolicy
from control_plane.executive_runtime import AttemptLease, JobPayload, Runtime
from control_plane.worker_execution_contract import (
    BinaryAttestation,
    WorkerLaunchSpec,
    WorkerProcessRef,
)

PROFILE_ID = "worker.acp.providerfree.readonly.v1"
SENTINEL = "LEASE-TOKEN-SENTINEL-DO-NOT-LEAK"


def _process(attempt_id: str, *, pid: int = 4242, base_sha: str = "c" * 40) -> WorkerProcessRef:
    binary = BinaryAttestation(
        path="/usr/bin/false", real_path="/usr/bin/false", version="0",
        sha256="ab" * 32, team_identifier=None, size=1, device=1, inode=1,
        mode=0o755, uid=1, gid=1, mtime_ns=1,
    )
    return WorkerProcessRef(
        run_id=attempt_id, pid=pid, pgid=pid, process_start_identity="start-1",
        boot_session_id="boot-1", launch_nonce="nonce-1", provider_session_id=None,
        stdout_path="/tmp/out", stderr_path="/tmp/err", result_path="/tmp/result",
        started_at="2026-10-25T00:00:00Z", binary=binary, base_sha=base_sha,
    )


def _world(tmp_path, *, profile_id: str = PROFILE_ID, model: str = "fixture-model"):
    registry = ExecutionCapabilityRegistry.load()
    profile = registry.resolve(profile_id)
    clock = [1_800_000_000_000]
    runtime = Runtime.at(tmp_path / "runtime", clock=lambda: clock[0])
    # Inert fixture: registry facts copied into this test database only.
    metadata = {
        "execution_profile_id": profile.profile_id,
        "execution_profile_digest": profile.profile_digest,
        "capability_policy_version": registry.policy_version,
        "capability_policy_digest": registry.policy_digest,
        "adapter_id": "acp-agent",
    }
    runtime.workers.register_worker(
        "acp-01", provider="codex", account_label="inert-acp-currentness-fixture",
        worker_type="acp-agent", capabilities=["research"],
        quota_classes={"acp-readonly": {
            "capabilities": ["research"], "model": model, "effort": "xhigh",
            "cost_class": "standard", "metadata": metadata,
        }},
    )
    job = runtime.jobs.create_job(
        "ACP currentness observation fixture",
        requested_authorities=["READ", "RESEARCH"],
        constraints={
            "provider": "codex", "model": model, "effort": "xhigh",
            "cost_class": "standard", "eligible_quota_classes": ["acp-readonly"],
            "required_capabilities": ["research"], **metadata,
        },
    )
    lease = runtime.attempts.claim_job(
        job.job_id, worker_id="acp-01", quota_class="acp-readonly"
    )
    assert lease is not None
    spec = WorkerLaunchSpec(
        run_id=lease.attempt.attempt_id, job_id=lease.attempt.job_id,
        worker_id=lease.attempt.worker_id, workspace_path=tmp_path / "ws",
        run_dir=tmp_path / "run", prompt="observe",
        result_schema_path=tmp_path / "schema.json",
        authorities=("READ", "RESEARCH"), model=model,
        expected_base_sha="c" * 40,
    )
    return SimpleNamespace(
        runtime=runtime, lease=lease, spec=spec, clock=clock, registry=registry,
        profile=profile, tmp=tmp_path, metadata=metadata,
    )


def _request(controller: OriginalAcpRunController, **overrides) -> bytes:
    attempt = controller._lease.attempt
    body = {
        "schema": SCHEMA,
        "phase": "startup",
        "invocation_id": "inv-original-1",
        "raw_tool": "workspace.read",
        "argument_digest": "a" * 64,
        "request_digest": "b" * 64,
        "original_identity": {
            "job_id": attempt.job_id,
            "attempt_id": attempt.attempt_id,
            "worker_id": attempt.worker_id,
            "quota_class": attempt.quota_class,
            "fence_generation": attempt.fence_generation,
        },
        "child_correlation": {
            "connection_id": "child-conn-1",
            "catalog_digest": "c" * 64,
            "definition_digest": "d" * 64,
        },
    }
    for key, value in overrides.items():
        if key in {"original_identity", "child_correlation"} and isinstance(value, dict):
            body[key].update(value)
        else:
            body[key] = value
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


def _ownership(runtime: Runtime, attempt_id: str):
    with runtime.store.read() as connection:
        attempt = dict(connection.execute(
            """SELECT attempt_id, job_id, worker_id, quota_class, lease_token,
                      fence_generation, version, heartbeat_at_ms, lease_expires_at_ms,
                      status, pid FROM attempts WHERE attempt_id=?""",
            (attempt_id,),
        ).fetchone())
        job = dict(connection.execute(
            """SELECT current_attempt_id, assigned_worker_id, assigned_quota_class, status
               FROM jobs WHERE job_id=?""",
            (attempt["job_id"],),
        ).fetchone())
        quota = dict(connection.execute(
            """SELECT held_attempt_id, status, fence_counter FROM worker_quota_classes
               WHERE worker_id=? AND quota_class=?""",
            (attempt["worker_id"], attempt["quota_class"]),
        ).fetchone())
        events = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    return attempt, job, quota, events


def _record(world, pid: int = 4242):
    lease = world.lease
    return world.runtime.attempts.record_process(
        lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token, pid=pid, pgid=pid,
        process_start_identity="start-1", boot_id="boot-1",
    )


def _text(value) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def test_fresh_current_then_fence_revocation_does_not_adopt_replacement(tmp_path):
    world = _world(tmp_path)
    controller = OriginalAcpRunController(world.runtime, world.lease, world.spec)
    before = _ownership(world.runtime, world.lease.attempt.attempt_id)
    first = controller.observe(_request(controller))
    world.clock[0] += 1
    second = controller.observe(_request(controller, phase="discovery"))
    assert first["disposition"] == "CURRENT"
    assert second["disposition"] == "CURRENT"
    assert second["observed_at_ms"] == first["observed_at_ms"] + 1
    assert first["dispatch_authorized"] is False and second["dispatch_authorized"] is False
    assert first["reason_code"] == "OK"
    assert first["controller_observed"]["lease"]["state"] == "CURRENT"
    assert first["controller_observed"]["realm"]["auth_realm"] == world.profile.auth_realm
    mcp = first["controller_observed"]["mcp_grant"]["grants"]
    assert mcp and mcp[0]["grant_digest"] != first["controller_observed"]["orchestration_grant"]["effective_grant_digest"]
    assert "effective_grant_digest" not in mcp[0]
    _record(world, pid=4242)
    adopted = world.runtime.attempts.adopt_attempt(
        world.lease.attempt.attempt_id,
        expected_fence_generation=world.lease.attempt.fence_generation,
        lease_owner="replacement-owner",
    )
    refused = controller.observe(_request(controller))
    assert refused["disposition"] == "NOT_CURRENT"
    assert refused["reason_code"] == "RUNTIME_NOT_CURRENT"
    assert refused["dispatch_authorized"] is False
    assert refused["subject"]["attempt_id"] == world.lease.attempt.attempt_id
    assert refused["subject"]["fence_generation"] == world.lease.attempt.fence_generation
    assert refused["subject"]["fence_generation"] != adopted.attempt.fence_generation
    after = _ownership(world.runtime, world.lease.attempt.attempt_id)
    assert after[0]["fence_generation"] == adopted.attempt.fence_generation
    assert before[3] != after[3]  # adopt/record wrote events; observation itself is checked below


def test_observation_does_not_mutate_original_lease_or_ownership(tmp_path):
    world = _world(tmp_path)
    controller = OriginalAcpRunController(world.runtime, world.lease, world.spec)
    before = _ownership(world.runtime, world.lease.attempt.attempt_id)
    observation = controller.observe(_request(controller))
    after = _ownership(world.runtime, world.lease.attempt.attempt_id)
    assert observation["disposition"] == "CURRENT"
    assert before[0] == after[0]
    assert before[1] == after[1]
    assert before[2] == after[2]
    assert before[3] == after[3]


def test_replacement_attempt_is_not_adopted(tmp_path):
    world = _world(tmp_path)
    controller = OriginalAcpRunController(world.runtime, world.lease, world.spec)
    assert controller.observe(_request(controller))["disposition"] == "CURRENT"
    world.runtime.attempts.fail_attempt(
        world.lease.attempt.attempt_id,
        fence_generation=world.lease.attempt.fence_generation,
        lease_token=world.lease.lease_token,
        payload=JobPayload(summary="original attempt revoked"),
    )
    replacement = world.runtime.jobs.create_job(
        "replacement attempt",
        requested_authorities=["READ", "RESEARCH"],
        constraints={
            "provider": "codex", "model": "fixture-model", "effort": "xhigh",
            "cost_class": "standard", "eligible_quota_classes": ["acp-readonly"],
            "required_capabilities": ["research"], **world.metadata,
        },
    )
    other = world.runtime.attempts.claim_job(
        replacement.job_id, worker_id="acp-01", quota_class="acp-readonly"
    )
    assert other is not None
    world.runtime.attempts.record_process(
        other.attempt.attempt_id, fence_generation=other.attempt.fence_generation,
        lease_token=other.lease_token, pid=99991, pgid=99991,
        process_start_identity="other-start", boot_id="other-boot",
    )
    refused = controller.observe(_request(controller))
    encoded = _text(refused)
    assert refused["disposition"] == "NOT_CURRENT"
    assert refused["subject"]["attempt_id"] == world.lease.attempt.attempt_id
    assert other.attempt.attempt_id not in encoded
    assert replacement.job_id not in encoded
    assert "99991" not in encoded


def test_runtime_law_refusals(tmp_path):
    world = _world(tmp_path)
    controller = OriginalAcpRunController(world.runtime, world.lease, world.spec)
    assert controller.observe(_request(controller))["disposition"] == "CURRENT"

    sentinel_lease = AttemptLease(attempt=world.lease.attempt, lease_token=SENTINEL)
    wrong = OriginalAcpRunController(world.runtime, sentinel_lease, world.spec)
    wrong_result = wrong.observe(_request(wrong))
    assert wrong_result["disposition"] == "NOT_CURRENT"
    assert wrong_result["reason_code"] == "RUNTIME_NOT_CURRENT"
    blob = _text(wrong_result) + repr(wrong) + repr(wrong_result) + str(wrong)
    assert SENTINEL not in blob
    assert world.lease.lease_token not in blob

    world.clock[0] += 60_000
    expired = controller.observe(_request(controller))
    assert expired["disposition"] == "NOT_CURRENT"
    assert expired["reason_code"] == "RUNTIME_NOT_CURRENT"
    world.clock[0] -= 60_000

    with world.runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE worker_quota_classes SET fence_counter=fence_counter+1 WHERE worker_id='acp-01'"
        )
    drifted = controller.observe(_request(controller))
    assert drifted["reason_code"] == "RUNTIME_NOT_CURRENT"
    with world.runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE worker_quota_classes SET fence_counter=fence_counter-1 WHERE worker_id='acp-01'"
        )
    assert controller.observe(_request(controller))["disposition"] == "CURRENT"

    with world.runtime.store.transaction() as connection:
        connection.execute(
            """UPDATE worker_quota_classes
               SET held_attempt_id=NULL, status='AVAILABLE' WHERE worker_id='acp-01'"""
        )
    unlinked = controller.observe(_request(controller))
    assert unlinked["disposition"] == "NOT_CURRENT"
    assert unlinked["reason_code"] == "RUNTIME_NOT_CURRENT"


def test_offline_worker_and_operator_harness_use_runtime_laws(tmp_path):
    world = _world(tmp_path)
    controller = OriginalAcpRunController(world.runtime, world.lease, world.spec)
    world.runtime.workers.set_worker_status("acp-01", "OFFLINE")
    offline = controller.observe(_request(controller))
    assert offline["disposition"] == "NOT_CURRENT"
    assert offline["reason_code"] == "RUNTIME_NOT_CURRENT"
    assert offline["dispatch_authorized"] is False

    from test_ohf_p1b_runtime import _lease, _profile
    runtime, lease = _lease(tmp_path / "ohf")
    runtime.operator_harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token, requested=_profile(lease),
    )
    spec = WorkerLaunchSpec(
        run_id=lease.attempt.attempt_id, job_id=lease.attempt.job_id,
        worker_id=lease.attempt.worker_id, workspace_path=tmp_path / "ohf-ws",
        run_dir=tmp_path / "ohf-run", prompt="observe",
        result_schema_path=tmp_path / "ohf-schema.json", model="test-model",
    )
    harness = OriginalAcpRunController(runtime, lease, spec)
    calls = {"leased": 0, "snapshot": 0}
    original_leased = runtime.attempts._leased_row
    original_snapshot = runtime.attempts.current_authority_snapshot

    def leased(*args, **kwargs):
        calls["leased"] += 1
        return original_leased(*args, **kwargs)

    def snapshot(*args, **kwargs):
        calls["snapshot"] += 1
        return original_snapshot(*args, **kwargs)

    runtime.attempts._leased_row = leased
    runtime.attempts.current_authority_snapshot = snapshot
    refused = harness.observe(_request(harness))
    assert calls == {"leased": 1, "snapshot": 1}
    assert refused["disposition"] == "NOT_CURRENT"
    assert refused["reason_code"] == "RUNTIME_NOT_CURRENT"
    assert lease.lease_token not in _text(refused)


def test_claimed_dispatch_running_startup_and_session_fail_closed(tmp_path):
    world = _world(tmp_path)
    process = _process(world.lease.attempt.attempt_id)
    controller = OriginalAcpRunController(
        world.runtime, world.lease, world.spec, process_ref=process
    )
    claimed_dispatch = controller.observe(_request(controller, phase="dispatch"))
    assert claimed_dispatch["disposition"] == "NOT_CURRENT"
    assert claimed_dispatch["reason_code"] == "RUNTIME_NOT_CURRENT"
    assert claimed_dispatch["dispatch_authorized"] is False

    _record(world, pid=4242)
    world.runtime.attempts.mark_running(
        world.lease.attempt.attempt_id,
        fence_generation=world.lease.attempt.fence_generation,
        lease_token=world.lease.lease_token,
    )
    startup = controller.observe(_request(controller, phase="startup"))
    assert startup["disposition"] == "NOT_CURRENT"
    assert startup["reason_code"] == "RUNTIME_NOT_CURRENT"

    dispatch = controller.observe(_request(controller, phase="dispatch"))
    assert dispatch["disposition"] == "NOT_CURRENT"
    assert dispatch["reason_code"] == "SESSION_ASSOCIATION_ABSENT"
    assert dispatch["dispatch_authorized"] is False
    assert dispatch["controller_observed"]["process"]["state"] == "CURRENT"
    assert dispatch["controller_observed"]["process"]["attests_liveness"] is False
    assert dispatch["controller_observed"]["session_association"]["attests_session"] is False
    assert dispatch["expected_bindings"]["session_model"] is None
    assert dispatch["expected_bindings"]["attests_process_liveness"] is False

    world.runtime.attempts.checkpoint_attempt(
        world.lease.attempt.attempt_id,
        fence_generation=world.lease.attempt.fence_generation,
        lease_token=world.lease.lease_token,
        payload={"summary": "launch checkpoint", "current_state": "running"},
    )
    checkpointed = controller.observe(_request(controller, phase="dispatch"))
    assert checkpointed["controller_observed"]["attempt_status"]["status"] == "CHECKPOINTED"
    assert checkpointed["disposition"] == "NOT_CURRENT"
    assert checkpointed["dispatch_authorized"] is False


def test_process_profile_model_and_realm_mismatches_fail_closed(tmp_path):
    world = _world(tmp_path)
    process = _process(world.lease.attempt.attempt_id, pid=4242)
    controller = OriginalAcpRunController(
        world.runtime, world.lease, world.spec, process_ref=process
    )
    _record(world, pid=4242)
    assert controller.observe(_request(controller))["controller_observed"]["process"]["state"] == "CURRENT"
    with world.runtime.store.transaction() as connection:
        connection.execute("UPDATE attempts SET pid=5252, pgid=5252 WHERE attempt_id=?", (world.lease.attempt.attempt_id,))
    changed = controller.observe(_request(controller))
    assert changed["disposition"] == "NOT_CURRENT"
    assert changed["reason_code"] == "PROCESS_NOT_CURRENT"
    assert changed["expected_bindings"]["process"]["pid"] == 4242
    assert controller._process_ref.pid == 4242
    assert "5252" not in _text(changed["expected_bindings"])

    with world.runtime.store.transaction() as connection:
        connection.execute("UPDATE attempts SET pid=4242, pgid=4242 WHERE attempt_id=?", (world.lease.attempt.attempt_id,))
        connection.execute(
            "UPDATE worker_quota_classes SET model='other-model' WHERE worker_id='acp-01'"
        )
    model = controller.observe(_request(controller))
    assert model["disposition"] == "NOT_CURRENT"
    assert model["reason_code"] == "MODEL_NOT_CURRENT"
    assert model["expected_bindings"]["model"] == "fixture-model"
    with world.runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE worker_quota_classes SET model='fixture-model' WHERE worker_id='acp-01'"
        )

    replacement_digest = "e" * 64
    with world.runtime.store.transaction() as connection:
        row = connection.execute("SELECT constraints_json FROM jobs WHERE job_id=?", (world.lease.attempt.job_id,)).fetchone()
        constraints = json.loads(row[0])
        constraints["execution_profile_digest"] = replacement_digest
        connection.execute(
            "UPDATE jobs SET constraints_json=? WHERE job_id=?",
            (json.dumps(constraints), world.lease.attempt.job_id),
        )
        quota = connection.execute(
            "SELECT metadata_json FROM worker_quota_classes WHERE worker_id='acp-01'"
        ).fetchone()
        metadata = json.loads(quota[0])
        metadata["execution_profile_digest"] = replacement_digest
        connection.execute(
            "UPDATE worker_quota_classes SET metadata_json=? WHERE worker_id='acp-01'",
            (json.dumps(metadata),),
        )
    drifted = controller.observe(_request(controller))
    encoded = _text(drifted)
    assert drifted["disposition"] == "NOT_CURRENT"
    assert drifted["controller_observed"]["profile"]["state"] == "NOT_CURRENT"
    assert drifted["expected_bindings"]["profile_digest"] == world.profile.profile_digest
    assert replacement_digest not in encoded
    assert drifted["controller_observed"]["profile"].get("profile_digest") is None

    # Enabled non-ACP registry profile. Paid GLM identity is a separate claim law
    # and is not a substitute for this realm refusal.
    foreign = _world(
        tmp_path / "foreign-realm",
        profile_id="operator.appserver.readonly.v1",
        model="fixture-model",
    )
    foreign_controller = OriginalAcpRunController(foreign.runtime, foreign.lease, foreign.spec)
    realm = foreign_controller.observe(_request(foreign_controller))
    assert realm["disposition"] == "NOT_CURRENT"
    assert realm["controller_observed"]["realm"]["state"] == "NOT_CURRENT"
    assert realm["controller_observed"]["realm"].get("auth_realm") is None
    assert realm["dispatch_authorized"] is False


def test_policy_and_unknown_failures_are_unavailable_without_prior_positive(tmp_path, monkeypatch):
    world = _world(tmp_path)
    controller = OriginalAcpRunController(world.runtime, world.lease, world.spec)
    assert controller.observe(_request(controller))["disposition"] == "CURRENT"
    calls = {"n": 0}
    original = world.runtime.attempts._leased_row

    def wrapped(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(world.runtime.attempts, "_leased_row", wrapped)

    def unavailable(path=None):
        raise AuthorityPolicyError("policy unavailable")

    monkeypatch.setattr(ExecutiveAuthorityPolicy, "load", classmethod(lambda cls, path=None: unavailable()))
    failed = controller.observe(_request(controller))
    assert calls["n"] == 1
    assert failed["disposition"] == "UNAVAILABLE"
    assert failed["reason_code"] == "AUTHORITY_UNAVAILABLE"
    assert failed["dispatch_authorized"] is False
    assert failed["controller_observed"]["lease"]["state"] == "CURRENT"
    monkeypatch.undo()

    def explode(path=None, source_root=None):
        raise RuntimeError("synthetic registry failure")

    monkeypatch.setattr(ExecutionCapabilityRegistry, "load", classmethod(lambda cls, path=None, source_root=None: explode()))
    unknown = controller.observe(_request(controller))
    assert unknown["disposition"] == "UNAVAILABLE"
    assert unknown["reason_code"] == "OWNER_UNAVAILABLE"
    assert "synthetic registry failure" not in _text(unknown)


def test_bounds_duplicates_and_crossed_correlation_fail_before_runtime(tmp_path):
    world = _world(tmp_path)
    controller = OriginalAcpRunController(world.runtime, world.lease, world.spec)
    calls = {"n": 0}
    original = world.runtime.attempts._leased_row

    def wrapped(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    world.runtime.attempts._leased_row = wrapped
    before = _ownership(world.runtime, world.lease.attempt.attempt_id)[3]

    def refuse(raw: bytes, code: str) -> None:
        with pytest.raises(AcpContinuingAuthorityContractError) as caught:
            controller.observe(raw)
        assert caught.value.code == code
        assert SENTINEL not in str(caught.value)
        assert world.lease.lease_token not in repr(caught.value)

    duplicate = _request(controller).replace(b'"schema":"' + SCHEMA.encode() + b'"', b'"schema":"x","schema":"y"', 1)
    refuse(duplicate, "DUPLICATE_KEY")
    refuse(_request(controller).replace(b'"fence_generation":1', b'"fence_generation":NaN'), "NONFINITE")
    refuse(_request(controller).replace(b'"fence_generation":1', b'"fence_generation":1e2'), "NONFINITE")
    refuse(_request(controller)[:-1] + b',"permission_ttl":1}', "UNKNOWN_FIELD")
    refuse(_request(controller)[:-1] + b',"already_current":true}', "UNKNOWN_FIELD")
    nested = _request(controller).replace(b'"connection_id":"child-conn-1"', b'"connection_id":{"id":"child-conn-1"}')
    refuse(nested, "NESTING_REFUSED")
    refuse(_request(controller).replace(b'"argument_digest":"' + b"a" * 64 + b'"', b'"argument_digest":["a"]'), "COLLECTION_REFUSED")
    refuse(b"{" + b" " * (MAX_REQUEST_BYTES + 1), "FRAME_TOO_LARGE")
    long_tool = _request(controller).replace(b'"raw_tool":"workspace.read"', b'"raw_tool":"' + b"t" * 300 + b'"')
    refuse(long_tool, "LENGTH_EXCEEDED")
    refuse(_request(controller).replace(b'"invocation_id":"inv-original-1",', b""), "MISSING_FIELD")
    refuse(_request(controller).replace(b'"fence_generation":1', b'"fence_generation":true'), "TYPE_INVALID")
    refuse(_request(controller).replace(b'"fence_generation":1', b'"fence_generation":0'), "RANGE_REFUSED")
    token_body = _request(controller).replace(b"inv-original-1", SENTINEL.encode())
    sentinel_controller = OriginalAcpRunController(
        world.runtime, AttemptLease(attempt=world.lease.attempt, lease_token=SENTINEL), world.spec
    )
    refuse_token = token_body
    with pytest.raises(AcpContinuingAuthorityContractError) as caught:
        sentinel_controller.observe(refuse_token)
    assert caught.value.code == "TOKEN_REJECTED"
    assert SENTINEL not in str(caught.value) and SENTINEL not in repr(caught.value)
    refuse(_request(controller, original_identity={"worker_id": "other-worker"}), "CORRELATION_MISMATCH")
    refuse(_request(controller, original_identity={"fence_generation": 99}), "CORRELATION_MISMATCH")
    refuse(_request(controller, original_identity={"job_id": "JOB-999"}), "CORRELATION_MISMATCH")
    assert calls["n"] == 0
    assert _ownership(world.runtime, world.lease.attempt.attempt_id)[3] == before


def test_child_correlation_never_becomes_liveness(tmp_path):
    world = _world(tmp_path)
    controller = OriginalAcpRunController(world.runtime, world.lease, world.spec)
    observation = controller.observe(_request(controller))
    encoded_observed = _text(observation["controller_observed"])
    assert observation["child_correlation"]["category"] == "child_supplied"
    assert observation["child_correlation"]["attests_liveness"] is False
    assert observation["child_correlation"]["attests_connection"] is False
    assert observation["child_correlation"]["attests_observation"] is False
    assert observation["child_correlation"]["reported_fence_generation"] == world.lease.attempt.fence_generation
    assert "child-conn-1" not in encoded_observed
    assert observation["dispatch_authorized"] is False
    assert observation["evidence_scope"] == "controller_evidence_only"
    assert "native_process_liveness" in observation["unverified_joins"]
    assert world.lease.lease_token not in _text(observation)
    assert world.lease.lease_token not in repr(controller)


def test_constructor_keeps_fixed_selectors(tmp_path):
    world = _world(tmp_path)
    parameters = inspect.signature(OriginalAcpRunController.__init__).parameters
    assert set(parameters) == {"self", "runtime", "lease", "spec", "process_ref"}
    assert inspect.signature(OriginalAcpRunController.observe).parameters.keys() == {"self", "raw"}
    foreign = WorkerLaunchSpec(
        run_id="ATT-" + "0" * 32, job_id="JOB-999", worker_id="other-worker",
        workspace_path=world.tmp / "ws", run_dir=world.tmp / "run", prompt="x",
        result_schema_path=world.tmp / "schema.json",
    )
    with pytest.raises(AcpContinuingAuthorityContractError) as caught:
        OriginalAcpRunController(world.runtime, world.lease, foreign)
    assert caught.value.code == "ATTACHMENT_IDENTITY_MISMATCH"
    with pytest.raises(AcpContinuingAuthorityContractError) as caught:
        OriginalAcpRunController(object(), world.lease, world.spec)
    assert caught.value.code == "ATTACHMENT_INVALID"
    wrong_process = _process("ATT-" + "1" * 32)
    with pytest.raises(AcpContinuingAuthorityContractError) as caught:
        OriginalAcpRunController(
            world.runtime, world.lease, world.spec, process_ref=wrong_process
        )
    assert caught.value.code == "ATTACHMENT_IDENTITY_MISMATCH"


def test_registry_refusal_is_not_a_positive_cache(tmp_path, monkeypatch):
    world = _world(tmp_path)
    controller = OriginalAcpRunController(world.runtime, world.lease, world.spec)
    first = controller.observe(_request(controller))
    assert first["disposition"] == "CURRENT"

    def unreadable(path=None, source_root=None):
        raise CapabilityPolicyError("capability policy is unreadable")

    monkeypatch.setattr(
        ExecutionCapabilityRegistry, "load",
        classmethod(lambda cls, path=None, source_root=None: unreadable()),
    )
    second = controller.observe(_request(controller))
    assert second["disposition"] == "UNAVAILABLE"
    assert second["reason_code"] == "SOURCE_UNAVAILABLE"
    assert second is not first
    assert second["controller_observed"]["profile"]["state"] == "UNAVAILABLE"
