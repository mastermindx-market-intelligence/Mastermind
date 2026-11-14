"""MMOS V1 E2E: Hermes handoff -> Executive admission -> Capacity Fabric
placement -> t3-native adapter launch -> seal -> execution return.

DONE_WHEN 2 + 5 (Director C2, T3_HANDOFF_V2 §3).  Everything here drives
the REAL Executive runtime (real SQLite in tmp_path) and the REAL t3
adapter (Director A3's public API); only the native port, the return
transport and the GitHub evidence port are in-memory fakes.

What is honestly composed (recorded because the runtime seam is absent):
``control_plane/child_request_execution_composition.py`` bridges
child-request admission (an admission-ledger Job) to the placement Job
``claim_job`` requires — the two lanes are separate in the runtime today.

Proven in this module:
  * exactly ONE native launch per handoff; the persisted binding's
    ``operation_key``/``caller_namespace`` are what the adapter sent;
  * NM-14: replay mints no second Job/launch; different digest under the
    same triple is a typed CHILD_REQUEST_DIGEST_CONFLICT; concurrent
    compositions are atomic (events UNIQUE command id arbitrates);
  * NM-07: admission succeeded but the UI timed out -> receipt lookup by
    triple, same Job, never a duplicate;
  * NM-15: #2329 shell shapes stay refused through the claim->launch path
    (armed guard), even with a valid claimed binding projected;
  * no Executive admission -> no launch: the adapter fails closed without
    a broker binding, and the armed shell path refuses without one;
  * the sealed result returns to the ORIGINAL requester via the Hermes
    deliverer with acceptance pinned to ``not_accepted``, exactly one
    delivery receipt per attempt (an events row, schema digest unchanged);
  * v1.2 sparse original-requester block: v1/v1.1 digests byte-identical,
    present block participates (requester swap under one triple conflicts).
"""
from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from control_plane.child_execution_contracts import (
    CHILD_EXECUTION_REQUEST_SCHEMA_V1_1,
    CHILD_EXECUTION_REQUEST_SCHEMA_V1_2,
    ChildExecutionRequest,
    OriginalRequesterBinding,
)
from control_plane.child_request_admission import admission_command_id
from control_plane.child_request_execution_composition import (
    compose_child_execution,
    placement_command_id,
)
from control_plane.executive_placement_authority import (
    HostObservation,
    PlacementObservations,
    SharedQuotaObservation,
)
from control_plane.executive_runtime import (
    _NORMALIZED_V7_SCHEMA_DIGEST,
    _normalized_schema_digest,
    AttemptStatus,
    JobStatus,
    Runtime,
    StateConflict,
)
from control_plane.execution_return_wiring import (
    execution_return_receipt_command_id,
    install_execution_return_seam,
)
from control_plane.fabric_placement_policy import PLACEMENT_INTENT_SCHEMA
from control_plane.model_router import ModelRouter, WorkRequest
from control_plane.t3_execution_adapter import (
    T3_REQUEST_NAMESPACE,
    T3ExecutionAdapter,
    _namespace_principal,
    derive_t3_client_request_id,
    t3_request_namespace,
)
from control_plane.worker_adapter import bind_reviewed_adapter, construct_reviewed_adapter
from control_plane.worker_execution_contract import WorkerLaunchSpec
from tests.test_t3_adapter_durability import CountingT3Port

from control_plane.t3_execution_adapter import SQLiteT3AdapterStateStore as _Store

NOW = 1_800_000_000_000
REVISION = "registry-rev-1"
QUOTA = "glm:chairman-max"

#: v1.1 fixture digest pinned BEFORE the v1.2 extension (computed under
#: unmodified code): the extension must never change a v1/v1.1 digest.
V1_1_REQUEST_DIGEST_PIN = (
    "ab61aae30704e1366dd77bd8c40ed59409234b6df4efa4592fac4625137b1da9"
)
from tests.test_rev5_contracts_v1_1 import (  # noqa: E402
    V1_REQUEST_DIGEST_PIN,
    _v1_1_request,
    _v1_request,
)


class Clock:
    def __init__(self, value: int = NOW) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value


def _adapter_clock() -> datetime:
    return datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)


class FakeInspector:
    def boot_session_id(self) -> str:
        return "boot-e2e"

    def identity(self, pid: int) -> tuple[str, int]:
        return (f"identity-{pid}", pid)

    def inspect(self, pid: int) -> object:
        return {"pid": pid}


E2E_PRINCIPAL = "oauth-client-e2e"


class RecordingT3Port(CountingT3Port):
    """CountingT3Port that attests a principal (the reviewed adapter refuses
    an unattested port before any native call) and records every launch
    envelope verbatim."""

    def __init__(self, principal: str = E2E_PRINCIPAL) -> None:
        super().__init__(principal)
        self.envelopes: list = []

    async def launch_thread(self, envelope):
        self.envelopes.append(envelope)
        return await super().launch_thread(envelope)


class FakeReturnTransport:
    """In-memory HermesReturnTransport: records sends, optional failure."""

    def __init__(self, fail: Exception | None = None) -> None:
        self.sends: list[dict[str, str]] = []
        self.fail = fail

    async def send(self, *, conversation_id: str, submission_id: str,
                   text: str) -> str:
        self.sends.append({
            "conversation_id": conversation_id,
            "submission_id": submission_id,
            "text": text,
        })
        if self.fail is not None:
            raise self.fail
        return f"native-ref-{len(self.sends)}"


class FakeGitHubPort:
    def __init__(self, view=None, checks=None) -> None:
        self.view = view
        self.checks = checks
        self.view_calls = 0
        self.checks_calls = 0

    def pr_view(self, repository: str, branch: str):
        self.view_calls += 1
        return self.view

    def pr_checks(self, repository: str, pr_number: int):
        self.checks_calls += 1
        return self.checks


def _runtime(tmp_path) -> tuple[Runtime, Clock]:
    clock = Clock()
    return Runtime.at(tmp_path, clock=clock, lease_seconds=60), clock


def _t3_worker(runtime: Runtime) -> None:
    runtime.workers.register_worker(
        "worker-t3", provider="codex", account_label="acct-t3",
        worker_type="mock", capabilities=["code"],
        quota_classes={"default": {"capabilities": ["code"],
                                   "metadata": {"adapter_id": "t3-native"}}},
        metadata={"host_id": "ubuntu0"},
    )


def _handoff_request(key: str = "e2e-child-1") -> ChildExecutionRequest:
    """The v1.2 Hermes/T3-originated coding handoff envelope."""
    return ChildExecutionRequest(
        root_ref="hermes-root-1", immediate_parent_run_ref="hermes-run-7",
        logical_child_key=key, task_kind="code",
        requested_complexity="C1_ROUTINE_BOUNDED",
        brief_ref="mem://brief-e2e", fallback_mode="shared",
        runtime_preference="t3-native",
        original_requester=OriginalRequesterBinding(
            teammate_id="hermes-tm-42", conversation_id="conv-7",
            project_id="proj-mm", carrier_kind="hermes_teammate"),
    )


def _t3_spec(request: ChildExecutionRequest) -> dict:
    return {
        "child_execution_request": request.to_dict(),
        "effective_complexity": "C1_ROUTINE_BOUNDED",
        "registry_revision": REVISION,
        "route": {
            "provider_ref": "codex", "pool_ref": "glm",
            "adapter_id": "t3-native",
        },
        "shared_quota_resource_refs": [QUOTA],
        "root_concurrency_limit": 32,
    }


def _observations() -> PlacementObservations:
    return PlacementObservations(
        registry_revision=REVISION, observed_at_ms=NOW,
        hosts={"ubuntu0": HostObservation(
            host_id="ubuntu0", boot_id="boot-ubuntu0", eligible_slots=1,
            observed_at_ms=NOW)},
        shared_quota={QUOTA: SharedQuotaObservation(
            resource_ref=QUOTA, per_account_cap=4, external_active_leases=0)},
    )


def _placement_intent(request: ChildExecutionRequest) -> dict:
    return {
        "schema": PLACEMENT_INTENT_SCHEMA,
        "root_run_id": request.root_ref,
        "immediate_parent_run_id": request.immediate_parent_run_ref,
        "logical_child_id": request.logical_child_key,
        "operation_id": f"e2e-op-{request.logical_child_key}",
        "actor_role": "child",
        "runtime_kind": "t3-native",
        "preferred_host": "ubuntu0",
    }


def _launch_spec(attempt_id: str, job_id: str) -> WorkerLaunchSpec:
    return WorkerLaunchSpec(
        run_id=attempt_id, job_id=job_id, worker_id="worker-t3",
        workspace_path=Path("/tmp/mmos-e2e-ws"),
        run_dir=Path(f"/tmp/mmos-e2e-run-{attempt_id}"),
        prompt="implement the handoff mission",
        result_schema_path=Path("/tmp/mmos-e2e-run/schema.json"),
    )


def _build_adapter(tmp_path, runtime: Runtime, port):
    def binding_source(spec: WorkerLaunchSpec):
        raw = runtime.attempts.execution_binding(spec.run_id)
        if raw is None:
            return None
        from control_plane.child_execution_contracts import ExecutionBinding
        return ExecutionBinding.from_dict(raw)

    adapter = construct_reviewed_adapter(
        "t3-native", port, binding_source, FakeInspector(),
        clock=_adapter_clock,
        state_store=_Store(Path(tmp_path) / "t3_adapter_state.sqlite3"),
    )
    bind_reviewed_adapter(adapter, "t3-native")
    return adapter


def _delivery_events(runtime: Runtime, attempt_id: str):
    return [
        e for e in runtime.store.list_events(
            command_id_prefix=execution_return_receipt_command_id(attempt_id))
        if e.attempt_id == attempt_id
    ]


def _run_handoff_to_seal(tmp_path, *, transport=None, github=None):
    """The full E2E path, shared by the main test and its variants.

    Returns a namespace with every intermediate artifact.
    """
    runtime, _ = _runtime(tmp_path)
    _t3_worker(runtime)
    request = _handoff_request()

    # Model Router: the real policy explains source eligibility for the
    # handoff's class (never observed price or live placement).
    router = ModelRouter.load()
    explanation = router.explain_route(WorkRequest(
        task_kind="implementation", effective_complexity="C1_ROUTINE_BOUNDED"))
    eligible = [row for row in explanation["aliases"]
                if row["source_disposition"] in (
                    "FIRST_LAWFUL_TIER", "LATER_SUITABILITY_TIER")]

    composed = compose_child_execution(
        runtime, request=request, spec=_t3_spec(request),
        branch="t3/e2e-admission-return")
    job = runtime.jobs.get_job(composed.placement_job.job_id)

    lease = runtime.attempts.claim_job(
        composed.placement_job.job_id,
        placement_observations=_observations(),
        fabric_placement_intent=_placement_intent(request),
    )
    assert lease is not None
    attempt_id = lease.attempt.attempt_id
    from control_plane.child_execution_contracts import ExecutionBinding
    binding = ExecutionBinding.from_dict(
        runtime.attempts.execution_binding(attempt_id))

    port = RecordingT3Port()
    adapter = _build_adapter(tmp_path, runtime, port)
    transport = transport if transport is not None else FakeReturnTransport()
    from control_plane.execution_return_wiring import GitHubEvidenceSource
    github = github if github is not None else GitHubEvidenceSource(
        repository="acme/mastermind",
        port=FakeGitHubPort(
            view={"number": 2329, "url": "https://github.com/acme/mastermind/pull/2329",
                  "state": "open", "mergedAt": None},
            checks=[{"name": "ci", "conclusion": "success"},
                    {"name": "lint", "conclusion": "skipped"}],
        ),
    )
    install_execution_return_seam(
        runtime, deliverer=__import__(
            "integrations.session_bridge.hermes_native_return",
            fromlist=["HermesExecutionReturnDeliverer"],
        ).HermesExecutionReturnDeliverer(transport),
        github=github, t3_adapter=adapter)

    spec = _launch_spec(attempt_id, composed.placement_job.job_id)
    ref = asyncio.run(adapter.start(spec))
    port.status_by_thread[ref.provider_session_id] = "succeeded"
    collection = asyncio.run(adapter.collect_result(ref))

    sealed = runtime.attempts.complete_attempt(
        attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        payload={
            "summary": "handoff implemented; tests green",
            "artifacts": ["mem://result-e2e"],
        },
    )
    return type("E2E", (), {
        "runtime": runtime, "request": request, "composed": composed,
        "admission": composed.admission, "job": job,
        "placement_job": composed.placement_job, "lease": lease,
        "attempt_id": attempt_id, "binding": binding, "port": port,
        "adapter": adapter, "transport": transport, "ref": ref,
        "collection": collection, "sealed": sealed,
        "eligible_aliases": eligible, "explanation": explanation,
    })()


# --- 1. the full E2E path -------------------------------------------------------


def test_e2e_admission_to_t3_native_launch_seal_and_return(tmp_path):
    e2e = _run_handoff_to_seal(tmp_path)

    # Placement provenance: Model Router explained real source eligibility.
    assert e2e.eligible_aliases, "real routing policy must serve C1 code work"

    # Admission: ADMITTED, exactly one admission Job, v1.2 block persisted.
    assert e2e.admission.state == "ADMITTED"
    assert e2e.admission.job_id
    creations = [
        e for e in e2e.runtime.store.list_events(
            command_id_prefix="child-request:")
        if e.event_type == "JOB_CREATED"
    ]
    assert len(creations) == 1
    admission_payload = creations[0].payload["provenance"]
    assert admission_payload["child_request"]["schema"] == "ChildExecutionRequest.v1"
    assert admission_payload["original_requester"] == {
        "teammate_id": "hermes-tm-42", "conversation_id": "conv-7",
        "project_id": "proj-mm", "carrier_kind": "hermes_teammate",
    }

    # Claim: C's v1.1 join — t3-native binding with the deterministic
    # native idempotency key; the claim stamps NO namespace (the claim
    # transaction knows no OAuth principal — REVIEW_C_E_OPUS A2).
    assert e2e.binding.runtime_kind == "t3-native"
    assert e2e.binding.caller_namespace == ""
    assert e2e.binding.operation_key == derive_t3_client_request_id(e2e.binding)

    # Launch: EXACTLY ONE native launch, and the envelope the adapter sent
    # carries the binding's persisted operation key verbatim and the
    # PORT-attested principal as the namespace suffix under the pinned base.
    assert e2e.port.launch_count == 1
    assert len(e2e.port.envelopes) == 1
    envelope = e2e.port.envelopes[0]
    assert envelope.client_request_id == e2e.binding.operation_key
    assert envelope.request_namespace == t3_request_namespace(E2E_PRINCIPAL)
    assert _namespace_principal(envelope.request_namespace) == E2E_PRINCIPAL
    assert envelope.request_namespace.count(T3_REQUEST_NAMESPACE) == 1

    # Seal + return: delivered once to the ORIGINAL conversation, receipt
    # durable as an events row, acceptance honestly not_accepted.
    assert e2e.sealed.status is JobStatus.COMPLETED
    assert len(e2e.transport.sends) == 1
    send = e2e.transport.sends[0]
    assert send["conversation_id"] == "conv-7"
    record = json.loads(send["text"])
    assert record["schema"] == "mastermind.execution_return/v1"
    assert record["acceptance"] == "not_accepted"
    assert record["stage"] == "checks_green"  # PR open, all checks concluded
    assert record["github"]["merge_state"] == "not_merged"  # open PR, unmerged
    # The returned namespace is the one the adapter PERSISTED at launch
    # (port-attested), never the claim's empty caller_namespace.
    assert record["original_requester"]["authenticated_namespace"] == (
        envelope.request_namespace)
    assert record["attempt"]["t3_thread_id"] == e2e.ref.provider_session_id
    assert record["attempt"]["seal_digest"]

    events = _delivery_events(e2e.runtime, e2e.attempt_id)
    assert len(events) == 1
    assert events[0].event_type == "EXECUTION_RETURN_DELIVERY"
    assert events[0].payload["delivery"]["state"] == "delivered"
    assert events[0].payload["stage"] == "checks_green"

    # The T3 result reference was ledgered BEFORE company acceptance.
    entry = e2e.adapter.result_ledger_entry(e2e.ref.run_id)
    assert entry is not None and entry.result_ref

    # Schema digest unchanged: the receipt is an events ROW, not a schema
    # change — the normalized V7 digest still matches exactly.
    with e2e.runtime.store.read() as connection:
        assert _normalized_schema_digest(connection) == _NORMALIZED_V7_SCHEMA_DIGEST


# --- 2. NM-14: replay never mints a second Job or launch -----------------------


def test_nm14_replayed_handoff_never_mints_a_second_job_or_launch(tmp_path):
    e2e = _run_handoff_to_seal(tmp_path)
    runtime, request = e2e.runtime, e2e.request

    replay = compose_child_execution(
        runtime, request=request, spec=_t3_spec(request))
    assert replay.admission.state == "REPLAY"
    assert replay.admission.job_id == e2e.admission.job_id
    assert replay.placement_created is False
    assert replay.placement_job.job_id == e2e.placement_job.job_id
    # The placement Job is sealed: the supervisor must not claim again.
    assert replay.ready_to_claim is False

    placement_creations = [
        e for e in runtime.store.list_events(
            command_id_prefix="child-placement:")
        if e.event_type == "JOB_CREATED"
    ]
    assert len(placement_creations) == 1
    assert e2e.port.launch_count == 1  # still exactly one native launch
    assert len(e2e.transport.sends) == 1  # and exactly one return delivery


# --- 3. NM-14: different digest under the same triple is a typed conflict ------


def test_nm14_different_digest_same_triple_is_typed_conflict(tmp_path):
    runtime, _ = _runtime(tmp_path)
    _t3_worker(runtime)
    request = _handoff_request()
    composed = compose_child_execution(
        runtime, request=request, spec=_t3_spec(request))
    assert composed.admission.state == "ADMITTED"

    # Same idempotency triple, DIFFERENT semantic content (different brief).
    drifted = ChildExecutionRequest(
        root_ref=request.root_ref,
        immediate_parent_run_ref=request.immediate_parent_run_ref,
        logical_child_key=request.logical_child_key,
        task_kind="code", requested_complexity="C1_ROUTINE_BOUNDED",
        brief_ref="mem://brief-DIFFERENT", fallback_mode="shared",
        runtime_preference="t3-native",
        original_requester=OriginalRequesterBinding(
            teammate_id="hermes-tm-42", conversation_id="conv-7",
            project_id="proj-mm", carrier_kind="hermes_teammate"),
    )
    assert drifted.is_idempotency_conflict(request)
    with pytest.raises(StateConflict, match="CHILD_REQUEST_DIGEST_CONFLICT"):
        compose_child_execution(runtime, request=drifted, spec=_t3_spec(drifted))

    # Still exactly one admission Job and one placement Job.
    assert len([e for e in runtime.store.list_events(
        command_id_prefix="child-request:")
        if e.event_type == "JOB_CREATED"]) == 1
    assert len([e for e in runtime.store.list_events(
        command_id_prefix="child-placement:")
        if e.event_type == "JOB_CREATED"]) == 1


# --- 4. NM-14: concurrent compositions are atomic (one Job) --------------------


def test_nm14_concurrent_composition_is_atomic_one_job(tmp_path):
    runtime, _ = _runtime(tmp_path)
    _t3_worker(runtime)
    request = _handoff_request()
    barrier = threading.Barrier(3)
    outcomes: list = []
    errors: list = []

    def submit() -> None:
        barrier.wait()
        try:
            outcomes.append(compose_child_execution(
                runtime, request=request, spec=_t3_spec(request)))
        except Exception as exc:  # noqa: BLE001 — recorded, asserted below
            errors.append(exc)

    threads = [threading.Thread(target=submit) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(outcomes) == 2
    job_ids = {o.placement_job.job_id for o in outcomes}
    admission_ids = {o.admission.job_id for o in outcomes}
    assert len(job_ids) == 1  # exactly one placement Job survives
    assert len(admission_ids) == 1
    states = sorted(o.admission.state for o in outcomes)
    assert states == ["ADMITTED", "REPLAY"]  # the loser reconciled, no retry


# --- 5. no Executive admission -> no launch ------------------------------------


def test_no_admission_no_launch_adapter_fails_closed(tmp_path):
    runtime, _ = _runtime(tmp_path)
    port = RecordingT3Port()

    def no_binding(spec: WorkerLaunchSpec):
        return None  # no Executive claim ever happened for this launch

    adapter = construct_reviewed_adapter(
        "t3-native", port, no_binding, FakeInspector(),
        clock=_adapter_clock,
        state_store=_Store(Path(tmp_path) / "t3_state.sqlite3"),
    )
    bind_reviewed_adapter(adapter, "t3-native")
    with pytest.raises(Exception, match="no current broker ExecutionBinding"):
        asyncio.run(adapter.start(_launch_spec("attempt-unadmitted", "job-x")))
    assert port.launch_count == 0  # nothing reached the native port


def test_no_admission_shell_launch_refused_without_binding(
    tmp_path, monkeypatch, capsys,
):
    """The armed shell path is the other half of the same law: a paid
    wrapper launch without the placement authority's projected binding is
    refused before any launch."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops"
                            / "executive_os"))
    try:
        import provider_orchestrator_guard as guard
    finally:
        sys.path.pop(0)
    monkeypatch.setenv("MASTERMIND_SHARED_PLACEMENT", "1")
    monkeypatch.delenv("POOL_EXECUTION_BINDING", raising=False)
    command = "pool run glm bounded /tmp/packet.txt /repo glm-5.3"
    with pytest.raises(SystemExit):
        guard.guard_fabric_launch(command, command)
    output = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "missing binding" in output["permissionDecisionReason"]


# --- 6. NM-07: admission succeeded but the UI timed out ------------------------


def test_nm07_admission_ui_timeout_receipt_lookup_no_duplicate(tmp_path):
    runtime, _ = _runtime(tmp_path)
    _t3_worker(runtime)
    request = _handoff_request()

    first = compose_child_execution(
        runtime, request=request, spec=_t3_spec(request))
    assert first.admission.state == "ADMITTED"
    # ... the reply is lost before the Hermes UI sees it (timeout) ...

    # Receipt lookup by triple: the deterministic command id recovers the
    # original admission WITHOUT minting anything.
    command_id = admission_command_id(request)
    event = runtime.store.get_event_by_command_id(command_id)
    assert event is not None and event.event_type == "JOB_CREATED"
    recovered = runtime.jobs.get_job(str(event.job_id))
    assert recovered is not None
    assert recovered.job_id == first.admission.job_id

    # The caller retries the same handoff: REPLAY, same handles, one Job.
    retry = compose_child_execution(
        runtime, request=request, spec=_t3_spec(request))
    assert retry.admission.state == "REPLAY"
    assert retry.admission.job_id == first.admission.job_id
    assert retry.placement_job.job_id == first.placement_job.job_id
    with runtime.store.read() as connection:
        jobs = connection.execute(
            "SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert jobs == 2  # one admission Job + one placement Job, nothing else
    assert runtime.jobs.get_job(first.admission.job_id).attempt_count == 0


# --- 7. NM-15: #2329 shell shapes refused through claim -> launch --------------


def _claimed_binding_json(tmp_path) -> str:
    """A REAL binding claimed through the placement authority (armed guard
    consumer: the shell launch step of the claim->launch path)."""
    runtime, _ = _runtime(tmp_path)
    _t3_worker(runtime)
    request = _handoff_request()
    composed = compose_child_execution(
        runtime, request=request, spec=_t3_spec(request))
    lease = runtime.attempts.claim_job(
        composed.placement_job.job_id,
        placement_observations=_observations(),
        fabric_placement_intent=_placement_intent(request))
    assert lease is not None
    return json.dumps(
        runtime.attempts.execution_binding(lease.attempt.attempt_id))


@pytest.mark.parametrize("shape", [
    # interpreter one-liner carrying the wrapper (REVIEW_2329 B-1)
    'python3 -c \'print("prep"); pool run glm bounded /tmp/packet.txt /repo glm-5.3\'',
    # normalization-equivalent variant: extra whitespace + case (M-A/M-B)
    'python3  -C  "POOL   RUN  glm  bounded /tmp/packet.txt /repo glm-5.3"',
    # computed command word standing in for the wrapper
    'P=pool; $P run glm bounded /tmp/packet.txt /repo glm-5.3',
])
def test_nm15_shell_shapes_refused_with_a_valid_claimed_binding(
    tmp_path, monkeypatch, capsys, shape,
):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops"
                            / "executive_os"))
    try:
        import provider_orchestrator_guard as guard
    finally:
        sys.path.pop(0)
    monkeypatch.setenv("MASTERMIND_SHARED_PLACEMENT", "1")
    # The session carries a VALID binding claimed moments ago: the #2329
    # shapes are still refused STRUCTURALLY, before any binding check.
    monkeypatch.setenv("POOL_EXECUTION_BINDING", _claimed_binding_json(tmp_path))
    with pytest.raises(SystemExit):
        guard.guard_fabric_launch(shape, shape)
    output = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    reason = output["permissionDecisionReason"]
    assert ("unobservable launch" in reason
            or "unaccounted descendant" in reason), reason


def test_nm15_lawful_direct_shape_reaches_the_binding_gate(
    tmp_path, monkeypatch, capsys,
):
    """Precedence proof: the direct wrapper shape is NOT structurally
    refused — it proceeds into binding law, so the refusals above were
    structural and this one is a binding check.

    Recorded integration gap (fail-closed, not patched in this lane): the
    guard's restated binding law accepts only the ``ExecutionBinding.v1``
    schema label, while the runtime's C v1.1 join labels a claimed
    t3-native binding ``ExecutionBinding.v1.1`` — so a REAL claimed
    binding is refused here on its schema label.  That refusal belongs to
    the guard owner (Rev5 v1.1 acceptance), not to this lane; what this
    test proves is the precedence: structural shapes die structurally,
    the lawful shape dies in binding law, never the reverse.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops"
                            / "executive_os"))
    try:
        import provider_orchestrator_guard as guard
    finally:
        sys.path.pop(0)
    monkeypatch.setenv("MASTERMIND_SHARED_PLACEMENT", "1")
    monkeypatch.setenv("POOL_EXECUTION_BINDING", _claimed_binding_json(tmp_path))
    command = "pool run glm bounded /tmp/packet.txt /repo glm-5.3"
    with pytest.raises(SystemExit):
        guard.guard_fabric_launch(command, command)
    output = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    reason = output["permissionDecisionReason"]
    assert "unobservable launch" not in reason
    assert ("binding" in reason.lower()
            or "receipt" in reason.lower()), reason
    # The real claimed binding's v1.1 label is admitted by the guard's shape
    # law (allowlist landed with the r6 review); the lawful shape therefore
    # reaches binding law proper and is refused for the honest reason that
    # this test environment has no owner placement-receipt channel — never
    # for the schema label, and never as "unobservable launch".
    assert "schema must be" not in reason
    assert "placement" in reason.lower() and "receipt" in reason.lower()


# --- 8. v1.2 sparse block digest compatibility ---------------------------------


def test_v1_and_v1_1_digest_pins_survive_the_v1_2_extension():
    assert _v1_request().request_digest == V1_REQUEST_DIGEST_PIN
    assert _v1_1_request().request_digest == V1_1_REQUEST_DIGEST_PIN
    # Absent v1.2 block: the key is not even serialized.
    assert "original_requester" not in _v1_request().to_dict()
    assert "original_requester" not in _v1_1_request().to_dict()
    assert _v1_1_request().schema == CHILD_EXECUTION_REQUEST_SCHEMA_V1_1


def test_v1_2_block_participates_in_digest_and_labels_the_schema():
    core = dict(
        root_ref="root-1", immediate_parent_run_ref="parent-1",
        logical_child_key="child-a", task_kind="code",
        requested_complexity="C2_COMPLEX_BOUNDED",
        brief_ref="mem://b1", fallback_mode="shared",
    )
    bare = ChildExecutionRequest(**core)
    with_block = ChildExecutionRequest(
        original_requester=OriginalRequesterBinding(
            teammate_id="tm-1", conversation_id="conv-9", project_id="proj-3"),
        **core,
    )
    assert bare.request_digest == _v1_request_variant_digest(core)
    assert with_block.schema == CHILD_EXECUTION_REQUEST_SCHEMA_V1_2
    assert with_block.request_digest != bare.request_digest
    rebuilt = ChildExecutionRequest.from_dict(
        json.loads(json.dumps(with_block.to_dict())))
    assert rebuilt == with_block
    assert rebuilt.schema == CHILD_EXECUTION_REQUEST_SCHEMA_V1_2
    # A requester swap under the same triple is a conflict, never a retry.
    swapped = ChildExecutionRequest(
        original_requester=OriginalRequesterBinding(
            teammate_id="tm-OTHER", conversation_id="conv-9", project_id="proj-3"),
        **core,
    )
    assert with_block.is_idempotency_conflict(swapped)
    assert not with_block.is_idempotent_retry(swapped)


def _v1_request_variant_digest(core: dict) -> str:
    """The digest of the same core content WITHOUT the v1.2 block — pinned
    by construction (a fresh request built from the same fields)."""
    return ChildExecutionRequest(**core).request_digest


def test_v1_2_missing_required_requester_field_is_refused():
    with pytest.raises(ValueError, match="teammate_id"):
        OriginalRequesterBinding(
            teammate_id="", conversation_id="conv-9", project_id="proj-3")
    with pytest.raises(ValueError, match="carrier_kind"):
        OriginalRequesterBinding(
            teammate_id="tm-1", conversation_id="conv-9", project_id="proj-3",
            carrier_kind="  ")


# --- 9. unknown GitHub evidence keeps the stage honest -------------------------


def test_unknown_github_evidence_keeps_the_stage_honest(tmp_path):
    e2e = _run_handoff_to_seal(
        tmp_path, github=__import__(
            "control_plane.execution_return_wiring", fromlist=["GitHubEvidenceSource"]
        ).GitHubEvidenceSource(
            repository="acme/mastermind", port=FakeGitHubPort(view=None)))
    record = json.loads(e2e.transport.sends[0]["text"])
    # No PR evidence observed: the stage stops at branch evidence, never
    # claims checks or merge, and every unobserved field is honest.
    assert record["github"]["pr_number"] is None
    assert record["github"]["checks"] is None
    assert record["github"]["merge_state"] == "unknown"
    assert record["stage"] == "branch_pushed"


# --- 10. delivery failure: honest refused receipt, no second send --------------


def test_delivery_failure_records_honest_refused_receipt(tmp_path):
    transport = FakeReturnTransport(fail=RuntimeError("native session down"))
    e2e = _run_handoff_to_seal(tmp_path, transport=transport)

    # The seal completed; the delivery is honestly refused, once.
    assert e2e.sealed.status is JobStatus.COMPLETED
    assert len(transport.sends) == 1
    events = _delivery_events(e2e.runtime, e2e.attempt_id)
    assert len(events) == 1
    assert events[0].payload["delivery"]["state"] == "refused"
    assert events[0].payload["delivery"]["refusal_code"] == "TRANSPORT_REFUSED"

    # No retry loop: re-invoking the seam short-circuits on the durable
    # receipt — the transport saw exactly one send, forever.
    from control_plane.executive_runtime import AttemptStatus
    e2e.runtime.attempts._execution_return_seam(
        job=e2e.sealed, status=AttemptStatus.COMPLETED)
    assert len(transport.sends) == 1
    assert len(_delivery_events(e2e.runtime, e2e.attempt_id)) == 1
