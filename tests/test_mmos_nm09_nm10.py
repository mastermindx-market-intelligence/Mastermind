"""MMOS V1 negative-matrix rows NM-09/NM-10 — admission/execution layer (L5).

NM-09 ("429/quota — WAIT/UNKNOWN/REFUSED, no silent cross-account fallback
after a possible effect"): the free observation layers are already proven
(``test_provider_quota_observation``, ``test_mmos_negative_matrix``).  What
this module pins is the REMAINING admission/execution gap: after a launch
whose outcome is UNKNOWN (the native effect may exist upstream), a
replacement request naming a DIFFERENT provider/route is never silently
admitted, a DIFFERENT OAuth principal never acquires the run, and the
original stays recoverable by its deterministic idempotency key alone.

NM-10 ("update_paused/drain — no service restart to evade"):
``update_paused`` is a gateway-owned switch that exists nowhere in this
repository, so the live proof is LIVE_ONLY.  What source CAN prove is the
closest law: the native-continuity vocabulary cannot even EXPRESS a
restart/reconnect/remake/resubmit/relaunch, and a native read outage
surfaces as typed failures while the adapter never re-launches, replays or
rebinds to a second thread to evade it.
"""
from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path

import pytest

from control_plane.child_execution_contracts import ExecutionBinding
from control_plane.child_request_execution_composition import compose_child_execution
from control_plane.t3_execution_adapter import (
    SQLiteT3AdapterStateStore,
    T3ExecutionAdapter,
    T3ExecutionAdapterError,
    T3LaunchClaimConflictError,
    T3LaunchEffectUnknownError,
    T3NamespaceAttestationError,
    T3UnknownOutcomeError,
    derive_t3_client_request_id,
    t3_request_namespace,
)
from integrations.session_bridge import hermes_native_continuity as continuity
from tests.test_mmos_admission_to_t3_native_e2e import (
    E2E_PRINCIPAL,
    RecordingT3Port,
    _build_adapter,
    _handoff_request,
    _launch_spec,
    _observations,
    _placement_intent,
    _runtime,
    _t3_spec,
    _t3_worker,
)
from tests.test_t3_adapter_durability import CountingT3Port, _pre_ack_ref
from tests.test_t3_execution_adapter import (
    FakeInspector,
    _binding,
    _clock,
    _launch_spec as _durability_launch_spec,
    _recovery_binding,
)


def _claimed_handoff(tmp_path, key: str):
    """Compose + claim one t3-native handoff through the REAL runtime seams.

    Returns (runtime, composed, attempt_id, binding, key) with the launch not
    yet started — the shared prefix of both NM-09 tests.
    """
    runtime, _ = _runtime(tmp_path)
    _t3_worker(runtime)
    request = _handoff_request(key)
    composed = compose_child_execution(
        runtime, request=request, spec=_t3_spec(request))
    assert composed.admission.state == "ADMITTED"
    lease = runtime.attempts.claim_job(
        composed.placement_job.job_id,
        placement_observations=_observations(),
        fabric_placement_intent=_placement_intent(request),
    )
    assert lease is not None
    attempt_id = lease.attempt.attempt_id
    binding = ExecutionBinding.from_dict(
        runtime.attempts.execution_binding(attempt_id))
    return runtime, composed, attempt_id, binding, derive_t3_client_request_id(
        binding)


def _launchable_spec(attempt_id: str, job_id: str, tmp_path):
    """The e2e launch spec with a REAL run_dir (a recovery binding writes
    its prompt file there)."""
    run_dir = Path(tmp_path) / "run"
    (run_dir / "input").mkdir(parents=True, exist_ok=True)
    return dataclasses.replace(
        _launch_spec(attempt_id, job_id), run_dir=run_dir)


def _child_request_creations(runtime) -> list:
    return [e for e in runtime.store.list_events(
        command_id_prefix="child-request:") if e.event_type == "JOB_CREATED"]


def _child_placement_creations(runtime) -> list:
    return [e for e in runtime.store.list_events(
        command_id_prefix="child-placement:") if e.event_type == "JOB_CREATED"]


# ---------------------------------------------------------------------------
# NM-09 (1) — effect unknown, then a different-route replacement: no second Job
# ---------------------------------------------------------------------------


def test_nm09_effect_unknown_then_different_route_is_refused_no_second_job(
    tmp_path,
):
    runtime, composed, attempt_id, _binding_obj, key = _claimed_handoff(
        tmp_path, "nm09-child-1")

    # The launch lands in the effect-unknown zone: the port minted the native
    # thread upstream, then lost the reply.  The effect may exist.
    port = RecordingT3Port()
    port.lose_ack = True
    adapter = _build_adapter(tmp_path, runtime, port)
    spec = _launchable_spec(attempt_id, composed.placement_job.job_id, tmp_path)
    with pytest.raises(T3LaunchEffectUnknownError) as caught:
        asyncio.run(adapter.start(spec))
    assert caught.value.client_request_id == key
    assert isinstance(caught.value.__cause__, T3UnknownOutcomeError)
    assert port.launch_count == 1  # the possibly-existing effect

    # The original stays recoverable BY KEY: the launch intent (deterministic
    # idempotency key + principal-qualified namespace) is still persisted.
    intent = adapter.launch_intent(attempt_id)
    assert intent is not None
    assert intent.client_request_id == key
    assert intent.request_namespace == t3_request_namespace(E2E_PRINCIPAL)

    # The replacement: the SAME idempotency triple, but a route naming a
    # DIFFERENT provider/pool/adapter.  It is never silently admitted —
    # admission reconciles to the original record and the placement Job is
    # already claimed, so there is no second claim or launch lane at all.
    replacement_spec = dict(_t3_spec(_handoff_request("nm09-child-1")))
    replacement_spec["route"] = {
        "provider_ref": "anthropic", "pool_ref": "claude-max",
        "adapter_id": "claude-cli",
    }
    replacement = compose_child_execution(
        runtime, request=_handoff_request("nm09-child-1"),
        spec=replacement_spec)
    assert replacement.admission.state == "REPLAY"
    assert replacement.admission.job_id == composed.admission.job_id
    assert replacement.placement_created is False
    assert replacement.placement_job.job_id == composed.placement_job.job_id
    assert replacement.ready_to_claim is False
    # The surviving placement Job still carries the ORIGINAL route: the
    # different provider never overwrote the admitted execution.
    assert (replacement.placement_job.constraints["child_placement"]["route"]
            ["provider_ref"] == "codex")

    # Exactly one admission Job and one placement Job, forever.
    assert len(_child_request_creations(runtime)) == 1
    assert len(_child_placement_creations(runtime)) == 1

    # No second native launch exists.
    assert port.launch_count == 1
    assert [env.client_request_id for env in port.envelopes] == [key]

    # The honest recovery: the SAME principal replays the SAME key and gets
    # the ORIGINAL thread — a replay, never a fresh launch.
    recovery_port = RecordingT3Port()  # same principal, same native owner
    recovery_port.receipts_by_key.update(port.receipts_by_key)
    recovery_adapter = _build_adapter(tmp_path, runtime, recovery_port)
    recovered = asyncio.run(recovery_adapter.reattach(
        spec, _recovery_binding(spec, _pre_ack_ref(spec, key))))
    assert recovered.provider_session_id == port.receipts_by_key[key].thread_id
    assert recovery_port.launch_count == 0
    assert recovery_port.replay_count == 1
    assert recovery_port.envelopes == []
    assert port.launch_count == 1  # the only launch, ever


# ---------------------------------------------------------------------------
# NM-09 (2) — the adapter never switches account, even effect-unknown
# ---------------------------------------------------------------------------


def test_nm09_effect_unknown_never_switches_account_at_the_adapter(tmp_path):
    runtime, composed, attempt_id, _binding_obj, key = _claimed_handoff(
        tmp_path, "nm09-child-2")

    port_a = RecordingT3Port()
    port_a.lose_ack = True
    adapter_a = _build_adapter(tmp_path, runtime, port_a)
    spec = _launchable_spec(attempt_id, composed.placement_job.job_id, tmp_path)
    with pytest.raises(T3LaunchEffectUnknownError):
        asyncio.run(adapter_a.start(spec))
    assert port_a.launch_count == 1

    # A DIFFERENT OAuth client tries to take the run over: start is refused
    # on the persisted launch claim BEFORE any native call — never a second
    # launch under another account.
    port_b = RecordingT3Port(principal="oauth-client-nm09-b")
    adapter_b = _build_adapter(tmp_path, runtime, port_b)  # same durable store
    with pytest.raises(T3LaunchClaimConflictError):
        asyncio.run(adapter_b.start(spec))
    assert port_b.launch_count == 0
    assert port_b.replay_count == 0
    assert port_b.envelopes == []

    # The namespace-continuity half: recovery under the other principal is
    # refused typed, before any replay.
    with pytest.raises(T3NamespaceAttestationError) as caught:
        asyncio.run(adapter_b.reattach(
            spec, _recovery_binding(spec, _pre_ack_ref(spec, key))))
    assert caught.value.reason == "PRINCIPAL_MISMATCH"
    assert port_b.replay_count == 0

    # The effect-unknown zone still belongs to the ORIGINAL principal's
    # idempotency identity — B's attempts overwrote nothing.
    intent = adapter_b.launch_intent(attempt_id)
    assert intent is not None
    assert intent.client_request_id == key
    assert intent.request_namespace == t3_request_namespace(E2E_PRINCIPAL)


# ---------------------------------------------------------------------------
# NM-10 (3) — the continuation vocabulary cannot express a restart
# ---------------------------------------------------------------------------

#: What the closed continuation vocabulary may offer, at most.  A fresh
#: ``send`` is expressible ONLY from IDLE (asserted below); ``recover`` only
#: for EFFECT_UNKNOWN with a durable pending pointer.
_ALLOWED_OPERATIONS = {"recover", "read", "status", "send"}

#: Words an evasion of update_paused/drain would need — and that no
#: continuation key or value may name.
_BANNED_TOKENS = ("restart", "reconnect", "remake", "resubmit", "relaunch")

_PENDING = {
    "operation_key": "op-key-original", "session_id": "sess-1",
    "request_id": "req-1",
}


def _classified_states():
    """Every state the classifier can produce for the error codes, native
    statuses, admission projections, pending shapes and session snapshots
    the module itself handles, each paired with its permitted continuations."""
    busy = ["NATIVE_SESSION_BUSY", "NATIVE_PROMPT_PENDING", "NATIVE_BUSY"]
    viewer = ["NATIVE_CLIENT_INTERRUPTED", "NATIVE_CLIENT_UNAVAILABLE",
              "NATIVE_PIPE_UNAVAILABLE", "NATIVE_PLATFORM_UNAVAILABLE"]
    auth = ["AUTHENTICATION_CHANGED", "NATIVE_AUTH_NOT_DISPATCHED"]
    unknown = ["NATIVE_GATEWAY_STOPPED", "PROVIDER_FENCED", "lowercase", ""]
    pairs: list = []

    def collect(state):
        pairs.append((state, continuity.permitted_continuations(state)))

    for code in busy + viewer + auth + unknown:
        for value in (code, 429):  # a non-string code is handled, not crashed
            collect(continuity.classify_error_code(value))
            collect(continuity.classify_error_code(value, pending=_PENDING))
            collect(continuity.classify_native_continuity(None, error_code=value))
            collect(continuity.classify_native_continuity(
                None, error_code=value, pending=_PENDING))
    admissions = [
        None, "not-a-dict", {}, {"status": "bogus"},
        {"status": "queued", "session_id": "s", "admission_id": "a"},
        {"status": "started"}, {"status": "unknown"},
        {"status": "terminal", "outcome": "succeeded", "session_id": "s"},
        {"status": "terminal", "outcome": "failed", "session_id": "s"},
    ]
    failure_reasons = [
        None, "runtime_offline", "provider_quota_limit",
        "provider_rate_limit", "not_a_reason",
    ]
    for status in sorted(continuity.NATIVE_STATUSES):
        for admission in admissions:
            for reason in failure_reasons:
                collect(continuity.classify_native_continuity(
                    status, admission=admission, failure_reason=reason))
        collect(continuity.classify_native_continuity(
            status, pending=_PENDING))
    sessions = [
        None, "not-a-dict", {},
        {"session_id": "s", "running": True},
        {"session_id": "s", "running": False},
        {"session_id": "s", "prompts_pending": True},
        {"session_id": "s", "pending": []},
        {"session_id": "s", "pending": [{"admission_id": "a", "status": "queued"}]},
    ]
    for session in sessions:
        collect(continuity.classify_native_continuity(None, session=session))
    return pairs


def _assert_names_no_evasion_verb(row: dict) -> None:
    for name, value in row.items():
        blob = f"{name}={value}".lower()
        for token in _BANNED_TOKENS:
            assert token not in blob, (token, row)


def test_nm10_continuation_vocabulary_has_no_restart_or_reconnect():
    pairs = _classified_states()
    assert pairs  # the walk classified real inputs
    assert {state["state"] for state, _ in pairs} <= continuity.STATES

    operations: set = set()
    for state, continuations in pairs:
        for row in continuations:
            assert isinstance(row, dict)
            operations.add(row["operation"])
            _assert_names_no_evasion_verb(row)
        if state["state"] != continuity.IDLE:
            # A fresh send is expressible ONLY from IDLE: no outage, pause or
            # unknown state offers a way around it by sending anew.
            assert all(row["operation"] != "send" for row in continuations), state
    assert operations <= _ALLOWED_OPERATIONS
    # The mutation vocabulary is exactly: recover the ORIGINAL operation key
    # (EFFECT_UNKNOWN), or a fresh send from IDLE — nothing else exists.
    assert operations - {"read", "status"} <= {"recover", "send"}

    # The heart of NM-09/NM-10 at this layer: an effect-unknown mutation is
    # recoverable ONLY by its original key, idempotently.
    effect_unknown = continuity.classify_native_continuity(
        "EFFECT_UNKNOWN", pending=_PENDING)
    assert effect_unknown["state"] == continuity.EFFECT_UNKNOWN
    rows = continuity.permitted_continuations(effect_unknown)
    assert len(rows) == 1
    assert rows[0]["operation"] == "recover"
    assert rows[0]["operation_key"] == "op-key-original"
    assert rows[0]["idempotent"] is True
    assert continuity.fresh_send_allowed(effect_unknown) is False

    # A quota/rate limit offers exactly a read — never a retry, never a
    # switch of account/provider.
    limited = continuity.classify_native_continuity(
        "OBSERVED",
        admission={"status": "terminal", "outcome": "failed"},
        failure_reason="provider_quota_limit")
    assert limited["state"] == continuity.MODEL_LIMITED
    assert [row["operation"] for row in
            continuity.permitted_continuations(limited)] == ["read"]


# ---------------------------------------------------------------------------
# NM-10 (4) — a read outage is typed failures, never a relaunch/rebind
# ---------------------------------------------------------------------------


class _OutageReadPort(CountingT3Port):
    """CountingT3Port whose reads enter an outage on demand: the attempted
    read is recorded first, then the typed unknown-outcome error is raised."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.read_failure: Exception | None = None

    async def read_thread(self, thread_id, run_id, cursor):
        read = await super().read_thread(thread_id, run_id, cursor)
        if self.read_failure is not None:
            raise self.read_failure
        return read


def test_nm10_outage_produces_typed_errors_and_never_relaunches(tmp_path):
    store = SQLiteT3AdapterStateStore(Path(tmp_path) / "nm10_state.sqlite3")
    port = _OutageReadPort(principal="oauth-client-A")
    adapter = T3ExecutionAdapter(
        port, lambda spec: _binding(), FakeInspector(),
        clock=_clock, state_store=store)
    spec = _durability_launch_spec()
    ref = asyncio.run(adapter.start(spec))
    original_thread = ref.provider_session_id
    original_key = derive_t3_client_request_id(_binding())
    assert port.launch_count == 1

    # A read outage: every status observation is a TYPED failure (never a
    # silent success), and the adapter never re-launches, never replays and
    # never rebinds to a second thread to evade it.
    port.read_failure = T3UnknownOutcomeError("read outcome unknown (outage)")
    for _ in range(5):
        with pytest.raises(T3ExecutionAdapterError) as caught:
            asyncio.run(adapter.status(ref))
        assert "unknown" in str(caught.value)

    assert port.launch_count == 1
    assert port.replay_count == 0
    # Every attempted read still targeted the ORIGINAL thread.
    assert port.reads and {t for t, _run, _cur in port.reads} == {original_thread}
    # No second thread id was ever minted, adopted or retained.
    assert set(port.receipts_by_key) == {original_key}
    assert [r.thread_id for r in port.receipts_by_key.values()] == [original_thread]
    assert store.run_ids() == (spec.run_id,)
    retained = adapter.retained_original_ref(spec.run_id)
    assert retained is not None and retained.provider_session_id == original_thread
    # Failed reads never advanced the cursor (no silent progress).
    assert adapter.read_cursor(spec.run_id) == ""
