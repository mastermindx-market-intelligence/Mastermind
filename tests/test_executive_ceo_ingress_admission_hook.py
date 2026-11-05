"""control_plane.executive_ceo_ingress — optional host admission callback.

A4 early component: the keyword-only ``admission_guard`` host-composition
parameter on ``handle_frame``/``_handle_submit``/``_handle_submit_v2``/
``_handle_normalized_submit``.  Every test here drives the ACTUAL
``handle_frame`` entrypoint over a REAL ``Runtime`` on ephemeral SQLite with
the REAL canonical ``ceo_intent.submit_intent`` sink.  The only sink
instrumentation is :class:`_SinkProbe` — a narrow counting wrapper that
delegates to the real callable — so no positive is ever produced from a
mocked success DTO, and read-only fixtures/helpers are reused from
``tests/test_executive_ceo_ingress.py`` (grounding, frames, literals) and
``tests/test_executive_os_phase1fc.py`` (strict-v2 host binding/placement
union).

Required-case mapping (commission "Genuine tests and output"):

1. v1 + automated v2 fresh requests, guard sees the trusted normalized
   envelope exactly once, genuine canonical Job, ``dispatched=False`` —
   ``test_v1_fresh_submit_*``, ``test_v2_fresh_submit_*``.
2. strict-v2 with actual execution/dialogue binding: two grounding
   observations and source re-observation precede the guard, then one sink
   call; moved grounding/source fails before guard and sink —
   ``test_strict_v2_guard_runs_*``, ``test_strict_v2_moved_*``.
3. omitted guard preserves legacy v1/v2 receipts, closed-schema rejection,
   conflict/error mapping, one-root concurrent identical admission —
   ``test_omitted_guard_*``.
4. guard refusal/exception, non-callable, non-None return: no sink call,
   identical Jobs/Attempts/events/quota rows, sanitized fixed
   ``backend_refused`` classification — ``test_guard_refusal_*``.
5. exact replay bypasses the guard and unavailable current providers and
   returns the same durable root; changed-content replay retains conflict;
   a permissive guard cannot flip a denied replay into a second admission —
   ``test_exact_replay_*``, ``test_changed_content_replay_*``.
6. mutating the detached callback copy (top-level and nested) cannot alter
   the submitted envelope or its canonical fingerprint; a returned
   replacement mapping refuses rather than selecting a new intent —
   ``test_detached_copy_mutation_*``, ``test_replacement_mapping_refuses``.
7. status/state frames never invoke the guard; a caller-supplied
   ``admission_guard`` field still fails the existing closed schema before
   any business effect — ``test_status_and_state_*``,
   ``test_caller_supplied_guard_field_fails_closed_schema_*``.

RED discipline: on the predecessor every guard test fails through
``_guard_kwargs`` with an explicit behavioural AssertionError — the missing
host admission parameter means no admission-callback behaviour is observable
at all — not through a bare absent-keyword ``TypeError``, and never through
an import/setup error.  The one-off predecessor probe that documents the old
path admitting fresh submissions with no callback position is recorded
separately in the evidence bundle, not in this module.
"""
from __future__ import annotations

import asyncio
import copy
import inspect
import json
from typing import Any

import pytest

from control_plane import ceo_intent
from control_plane import executive_ceo_ingress as ceo_ingress
from control_plane import executive_hot_state as hot_state
from control_plane.executive_runtime import Runtime
from tests import test_executive_ceo_ingress as pr_a
from tests import test_executive_os_phase1fc as phase1fc

WORKSTREAM = "WS:EXECUTIVE-OS"

#: The fixed, reviewed wire text of the EXISTING ``backend_refused``
#: classification — the only text a guard refusal may ever surface.
FIXED_BACKEND_REFUSED_MESSAGE = (
    "Executive CEO ingress backend refused the request"
)

#: Sentinel private content a hostile/broken callback tries to leak; the
#: assertions must prove it never reaches the refusal classification.
CALLBACK_PRIVATE_TEXT = "/host/secret/credential-token-0123456789"


def _dialogue_source(commit: str = "c" * 40) -> dict[str, Any]:
    """Trusted strict-v2 host admission source (armed-composition shape)."""

    return {
        "schema_version": "mastermind.executive_dialogue_source/v1",
        "work_ref": WORKSTREAM,
        "commission_ref": {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "commit": commit,
            "path": "docs/commissions/executive-terminal-return.md",
            "content_sha256": "d" * 64,
        },
        "watch_mode": "turn_watch_v1",
    }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _guard_kwargs(guard: Any) -> dict[str, Any]:
    """Return ``{"admission_guard": guard}`` or fail behaviourally.

    On the predecessor this raises an AssertionError naming the missing
    behaviour (no admission-callback position exists, so no guard law is
    observable).  That is this module's meaningful behavioural RED; a bare
    ``TypeError`` from an absent keyword proves nothing about behaviour and
    an import/setup failure proves nothing at all.
    """

    for name in (
        "handle_frame",
        "_handle_submit",
        "_handle_submit_v2",
        "_handle_normalized_submit",
    ):
        parameters = inspect.signature(getattr(ceo_ingress, name)).parameters
        if "admission_guard" not in parameters:
            raise AssertionError(
                f"behavioural predecessor RED: {name} has no admission_guard "
                "parameter, so the optional host admission callback — and "
                "every guard law this module pins — is not observable"
            )
    return {"admission_guard": guard}


class _RecordingGuard:
    """A real host-side admission callback.

    Snapshots each received envelope before any configured behaviour so
    tests can pin exactly what the guard saw.  Success is ``None`` (the
    configured verdict is returned verbatim otherwise, including non-None).
    """

    def __init__(self, *, verdict: Any = None, error: BaseException | None = None):
        self.calls: list[Any] = []
        self._verdict = verdict
        self._error = error

    def __call__(self, envelope: Any) -> Any:
        self.calls.append(copy.deepcopy(envelope))
        if self._error is not None:
            raise self._error
        return self._verdict

    @property
    def invocations(self) -> int:
        return len(self.calls)


class _SinkProbe:
    """Narrow instrumentation around the REAL canonical sink callable.

    Counts and snapshots every call, then delegates unchanged to
    ``ceo_intent.submit_intent``; it never substitutes a result.
    """

    def __init__(self) -> None:
        self._real = ceo_intent.submit_intent
        self.payloads: list[Any] = []
        self.kwargs: list[dict[str, Any]] = []

    def __call__(self, runtime: Any, payload: Any, **kwargs: Any) -> Any:
        self.payloads.append(copy.deepcopy(payload))
        self.kwargs.append(dict(kwargs))
        return self._real(runtime, payload, **kwargs)

    @property
    def calls(self) -> int:
        return len(self.payloads)


@pytest.fixture
def sink_probe(monkeypatch: pytest.MonkeyPatch) -> _SinkProbe:
    probe = _SinkProbe()
    monkeypatch.setattr(ceo_ingress.ceo_intent, "submit_intent", probe)
    return probe


@pytest.fixture
def runtime(tmp_path: Any) -> Runtime:
    return Runtime.at(tmp_path / "runtime")


def _workspace_root(tmp_path: Any) -> str:
    return str(tmp_path / "workspaces")


def _v1_frame(**extra_top: Any) -> dict[str, Any]:
    return json.loads(
        pr_a._submit_bytes(
            observed_grounding=pr_a.GROUNDING_A,
            request=pr_a._research_request(),
            **extra_top,
        )
    )


def _v2_frame(**overrides: Any) -> dict[str, Any]:
    return json.loads(pr_a._submit_v2_bytes(**overrides))


def _strict_v2_frame() -> dict[str, Any]:
    return _v2_frame(
        request=pr_a._automated_research_request(workstream=WORKSTREAM)
    )


def _runtime_snapshot(runtime: Runtime) -> dict[str, Any]:
    """Durable admission-visible state: Jobs, Attempts, events and the
    registered worker rows carrying the store's quota-class material."""

    return {
        "jobs": [job.to_dict() for job in runtime.jobs.list_jobs()],
        "attempts": [
            attempt.to_dict() for attempt in runtime.attempts.list_attempts()
        ],
        "events": [event.to_dict() for event in runtime.events.list_events()],
        "workers": [worker.to_dict() for worker in runtime.workers.list_workers()],
    }


def _admission_events(runtime: Runtime) -> list[dict[str, Any]]:
    """Job-aggregate events — the durable trace one admission can create."""

    return [
        event.to_dict()
        for event in runtime.events.list_events()
        if event.aggregate_type == "job"
    ]


# ===========================================================================
# interface law — the host parameter itself
# ===========================================================================


def test_admission_guard_is_a_keyword_only_none_default_host_parameter():
    for name in (
        "handle_frame",
        "_handle_submit",
        "_handle_submit_v2",
        "_handle_normalized_submit",
    ):
        parameters = inspect.signature(getattr(ceo_ingress, name)).parameters
        assert "admission_guard" in parameters, name
        parameter = parameters["admission_guard"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, name
        assert parameter.default is None, name


# ===========================================================================
# required case 1 — both public submit schema branches, fresh path
# ===========================================================================


def test_v1_fresh_submit_shows_guard_the_trusted_envelope_once_and_creates_canonical_job(
    runtime: Runtime, tmp_path: Any, sink_probe: _SinkProbe
):
    guard = _RecordingGuard()

    receipt = pr_a.run(
        ceo_ingress.handle_frame(
            _v1_frame(),
            runtime=runtime,
            grounding_provider=pr_a._FakeGrounding(),
            workspace_root=_workspace_root(tmp_path),
            **_guard_kwargs(guard),
        )
    )

    assert guard.invocations == 1
    seen = guard.calls[0]
    assert isinstance(seen, dict)
    assert seen["intent_id"] == pr_a.LITERAL_SLACK_INTENT_ID
    assert seen["schema"] == ceo_intent.INTENT_SCHEMA
    # Fingerprint-compatible: the canonical fingerprint of exactly what the
    # guard saw is the durable fingerprint the sink records.
    assert receipt["fingerprint"] == ceo_intent.intent_fingerprint(seen)
    assert receipt["schema"] == ceo_intent.RECEIPT_SCHEMA
    assert receipt["intent_id"] == pr_a.LITERAL_SLACK_INTENT_ID
    assert receipt["dispatched"] is False
    assert receipt["duplicate"] is False
    assert receipt["status"] == "QUEUED"
    assert sink_probe.calls == 1
    job = runtime.jobs.get_job(receipt["job_id"])
    assert job is not None
    assert job.objective == pr_a._research_request()["objective"]
    assert job.requested_authorities == ["READ", "RESEARCH"]


def test_v2_fresh_submit_shows_guard_the_trusted_envelope_once_and_creates_canonical_job(
    runtime: Runtime, tmp_path: Any, sink_probe: _SinkProbe
):
    guard = _RecordingGuard()

    receipt = pr_a.run(
        ceo_ingress.handle_frame(
            _v2_frame(),
            runtime=runtime,
            grounding_provider=pr_a._FakeGrounding(),
            workspace_root=_workspace_root(tmp_path),
            service_state="READY",
            ceo_ingress_armed=True,
            **_guard_kwargs(guard),
        )
    )

    assert guard.invocations == 1
    seen = guard.calls[0]
    assert seen["intent_id"] == pr_a.LITERAL_AUTOMATED_INTENT_ID
    assert receipt["fingerprint"] == ceo_intent.intent_fingerprint(seen)
    assert receipt["intent_id"] == pr_a.LITERAL_AUTOMATED_INTENT_ID
    assert receipt["dispatched"] is False
    assert sink_probe.calls == 1
    assert len(runtime.jobs.list_jobs()) == 1


# ===========================================================================
# required case 2 — strict-v2 host binding, ordering, moved-input failures
# ===========================================================================


class _OrderingGrounding:
    """Delegate to the existing fixture provider while logging call order."""

    def __init__(self, sequence: list[dict[str, str]], log: list[str]):
        self._inner = pr_a._FakeGrounding(sequence)
        self._log = log

    @property
    def calls(self) -> int:
        return self._inner.calls

    def observe(self) -> dict[str, str]:
        self._log.append("grounding")
        return self._inner.observe()


def _strict_v2_submission(
    runtime: Runtime,
    tmp_path: Any,
    *,
    guard: Any = None,
    log: list[str] | None = None,
    grounding_sequence: list[dict[str, str]] | None = None,
    source_commits: tuple[str, str] = ("c" * 40, "c" * 40),
) -> Any:
    """Compose one strict-v2 automated submission exactly as the armed host
    does (Phase 1F-C binding fixtures), returning the pending coroutine."""

    order: list[str] = log if log is not None else []
    grounding = _OrderingGrounding(
        grounding_sequence or [pr_a.GROUNDING_A], order
    )
    binding = phase1fc._v3_execution_binding()
    source_calls: list[int] = []

    def execution_binding_provider() -> dict[str, Any]:
        order.append("binding")
        return copy.deepcopy(binding)

    def dialogue_source_provider(intent_id: str, work_ref: str):
        order.append("source")
        source_calls.append(1)
        index = min(len(source_calls), len(source_commits)) - 1
        return _dialogue_source(source_commits[index])

    phase1fc._register_placement_union(runtime)
    kwargs: dict[str, Any] = {
        "runtime": runtime,
        "grounding_provider": grounding,
        "workspace_root": _workspace_root(tmp_path),
        "service_state": "READY",
        "ceo_ingress_armed": True,
        "strict_v2_admission": True,
        "execution_binding_provider": execution_binding_provider,
        "dialogue_source_provider": dialogue_source_provider,
    }
    if guard is not None:
        kwargs.update(_guard_kwargs(guard))
    return ceo_ingress.handle_frame(_strict_v2_frame(), **kwargs)


def test_strict_v2_guard_runs_after_reobservations_and_before_the_one_sink_call(
    runtime: Runtime, tmp_path: Any, sink_probe: _SinkProbe
):
    order: list[str] = []

    class _LoggingGuard(_RecordingGuard):
        def __call__(self, envelope: Any) -> Any:
            order.append("guard")
            return super().__call__(envelope)

    guard = _LoggingGuard()

    receipt = pr_a.run(
        _strict_v2_submission(runtime, tmp_path, guard=guard, log=order)
    )

    # Two grounding observations and the dialogue-source re-observation
    # strictly precede the guard; exactly one sink call follows it.
    assert order == [
        "grounding",
        "binding",
        "source",
        "grounding",
        "source",
        "guard",
    ]
    assert sink_probe.calls == 1
    seen = guard.calls[0]
    assert seen["schema"] == ceo_intent.INTENT_SCHEMA_V2
    assert seen["intent_kind"] == "executive_coo_cycle"
    assert seen["business_impact"] == "routine"
    assert seen["intent_id"] == pr_a.LITERAL_AUTOMATED_INTENT_ID
    assert seen["workstream"] == WORKSTREAM
    assert receipt["schema"] == ceo_intent.RECEIPT_SCHEMA_V2
    assert receipt["fingerprint"] == ceo_intent.intent_fingerprint(seen)
    assert receipt["dispatched"] is False
    job = runtime.jobs.get_job(receipt["job_id"])
    assert job is not None
    assert job.orchestration_role == "aggregation"
    assert sink_probe.kwargs[0]["require_dialogue_source"] is True
    # ``_submit`` hands the sink the source's canonical dict form.
    assert sink_probe.kwargs[0]["dialogue_source"] == _dialogue_source()
    assert sink_probe.kwargs[0]["execution_binding"] == phase1fc._v3_execution_binding()


def test_strict_v2_moved_grounding_fails_before_guard_and_sink(
    runtime: Runtime, tmp_path: Any, sink_probe: _SinkProbe
):
    guard = _RecordingGuard()

    with pytest.raises(ceo_ingress.CeoIngressError) as raised:
        pr_a.run(
            _strict_v2_submission(
                runtime,
                tmp_path,
                guard=guard,
                grounding_sequence=[pr_a.GROUNDING_A, pr_a.GROUNDING_B],
            )
        )

    assert raised.value.code == "grounding_changed"
    assert guard.invocations == 0
    assert sink_probe.calls == 0
    assert runtime.jobs.list_jobs() == []
    # Worker registration (fixture composition) writes its own events; the
    # admission-scope claim is that NO job/admission event was durably created.
    assert _admission_events(runtime) == []


def test_strict_v2_moved_source_fails_before_guard_and_sink(
    runtime: Runtime, tmp_path: Any, sink_probe: _SinkProbe
):
    guard = _RecordingGuard()

    with pytest.raises(ceo_ingress.CeoIngressError) as raised:
        pr_a.run(
            _strict_v2_submission(
                runtime,
                tmp_path,
                guard=guard,
                source_commits=("c" * 40, "e" * 40),
            )
        )

    assert raised.value.code == "operation_conflict"
    assert guard.invocations == 0
    assert sink_probe.calls == 0
    assert runtime.jobs.list_jobs() == []
    assert _admission_events(runtime) == []


# ===========================================================================
# required case 3 — omitted guard preserves every existing behaviour
# ===========================================================================


def test_omitted_guard_preserves_legacy_v1_receipt_and_closed_schema(
    runtime: Runtime, tmp_path: Any, sink_probe: _SinkProbe
):
    receipt = pr_a.run(
        ceo_ingress.handle_frame(
            _v1_frame(),
            runtime=runtime,
            grounding_provider=pr_a._FakeGrounding(),
            workspace_root=_workspace_root(tmp_path),
        )
    )
    assert sink_probe.calls == 1
    assert receipt["schema"] == ceo_intent.RECEIPT_SCHEMA
    assert receipt["accepted"] is True
    assert receipt["dispatched"] is False
    assert receipt["duplicate"] is False
    assert receipt["authority"]["requested"] == ["READ", "RESEARCH"]

    # admission_guard is host composition only: a frame carrying it as a
    # top-level key still fails the exact closed-schema check.
    with pytest.raises(ceo_ingress.CeoIngressError) as raised:
        pr_a.run(
            ceo_ingress.handle_frame(
                _v1_frame(admission_guard="smuggled"),
                runtime=runtime,
                grounding_provider=pr_a._FakeGrounding(),
                workspace_root=_workspace_root(tmp_path),
            )
        )
    assert raised.value.code == "invalid_input"
    assert len(runtime.jobs.list_jobs()) == 1


def test_omitted_guard_preserves_v2_conflict_and_changed_grounding_mapping(
    runtime: Runtime, tmp_path: Any
):
    armed = {
        "runtime": runtime,
        "grounding_provider": pr_a._FakeGrounding(),
        "workspace_root": _workspace_root(tmp_path),
        "service_state": "READY",
        "ceo_ingress_armed": True,
    }
    first = pr_a.run(ceo_ingress.handle_frame(_v2_frame(), **armed))
    assert first["dispatched"] is False

    with pytest.raises(ceo_ingress.CeoIngressError) as raised:
        pr_a.run(
            ceo_ingress.handle_frame(
                _v2_frame(
                    request=pr_a._automated_research_request(
                        objective="A materially different automated objective."
                    )
                ),
                **armed,
            )
        )
    assert raised.value.code == "operation_conflict"
    assert len(runtime.jobs.list_jobs()) == 1

    # A NEW request_ref is a genuinely fresh identity, so the moved trusted
    # grounding is observed and refused before any sink call.
    moved = pr_a._FakeGrounding(sequence=[pr_a.GROUNDING_A, pr_a.GROUNDING_B])
    with pytest.raises(ceo_ingress.CeoIngressError) as raised_again:
        pr_a.run(
            ceo_ingress.handle_frame(
                _v2_frame(
                    request_ref="req-chairman-ceo-20260829-002",
                    request=pr_a._automated_research_request(
                        objective="Another distinct fresh objective."
                    ),
                ),
                runtime=runtime,
                grounding_provider=moved,
                workspace_root=_workspace_root(tmp_path),
                service_state="READY",
                ceo_ingress_armed=True,
            )
        )
    assert raised_again.value.code == "grounding_changed"
    assert len(runtime.jobs.list_jobs()) == 1


def test_omitted_guard_preserves_one_root_concurrent_identical_admission(
    runtime: Runtime, tmp_path: Any
):
    async def both() -> tuple[dict[str, Any], dict[str, Any]]:
        return await asyncio.gather(
            ceo_ingress.handle_frame(
                _v2_frame(),
                runtime=runtime,
                grounding_provider=pr_a._FakeGrounding(),
                workspace_root=_workspace_root(tmp_path),
                service_state="READY",
                ceo_ingress_armed=True,
            ),
            ceo_ingress.handle_frame(
                _v2_frame(),
                runtime=runtime,
                grounding_provider=pr_a._FakeGrounding(),
                workspace_root=_workspace_root(tmp_path),
                service_state="READY",
                ceo_ingress_armed=True,
            ),
        )

    first, second = pr_a.run(both())
    canonical_first = dict(first)
    canonical_second = dict(second)
    canonical_first.pop("duplicate")
    canonical_second.pop("duplicate")
    assert canonical_first == canonical_second
    assert sorted([first["duplicate"], second["duplicate"]]) == [False, True]
    assert len(runtime.jobs.list_jobs()) == 1


# ===========================================================================
# required case 4 — refusal family: sanitized, zero sink, zero effect
# ===========================================================================


def _assert_sanitized_backend_refused(excinfo: pytest.ExceptionInfo[Any]) -> None:
    error = excinfo.value
    assert error.code == "backend_refused"
    assert error.message == FIXED_BACKEND_REFUSED_MESSAGE
    # The fixed classification is the whole wire-facing surface: the hostile
    # callback's private text appears neither in the message nor in the
    # rendered exception, and no new error code is introduced.
    assert CALLBACK_PRIVATE_TEXT not in error.message
    assert CALLBACK_PRIVATE_TEXT not in str(error)


def test_guard_exception_refuses_sanitized_with_zero_sink_and_zero_effect(
    runtime: Runtime, tmp_path: Any, sink_probe: _SinkProbe
):
    before = _runtime_snapshot(runtime)
    guard = _RecordingGuard(error=RuntimeError(f"callback blew up {CALLBACK_PRIVATE_TEXT}"))

    with pytest.raises(ceo_ingress.CeoIngressError) as raised:
        pr_a.run(
            ceo_ingress.handle_frame(
                _v1_frame(),
                runtime=runtime,
                grounding_provider=pr_a._FakeGrounding(),
                workspace_root=_workspace_root(tmp_path),
                **_guard_kwargs(guard),
            )
        )

    _assert_sanitized_backend_refused(raised)
    assert guard.invocations == 1
    assert sink_probe.calls == 0
    assert _runtime_snapshot(runtime) == before


def test_guard_non_none_mapping_return_refuses_with_zero_sink_and_zero_effect(
    runtime: Runtime, tmp_path: Any, sink_probe: _SinkProbe
):
    before = _runtime_snapshot(runtime)
    guard = _RecordingGuard(verdict={"dispatched": False, "ok": True})

    with pytest.raises(ceo_ingress.CeoIngressError) as raised:
        pr_a.run(
            ceo_ingress.handle_frame(
                _v1_frame(),
                runtime=runtime,
                grounding_provider=pr_a._FakeGrounding(),
                workspace_root=_workspace_root(tmp_path),
                **_guard_kwargs(guard),
            )
        )

    _assert_sanitized_backend_refused(raised)
    assert guard.invocations == 1
    assert sink_probe.calls == 0
    assert _runtime_snapshot(runtime) == before


def test_guard_non_none_scalar_return_refuses_with_zero_sink_and_zero_effect(
    runtime: Runtime, tmp_path: Any, sink_probe: _SinkProbe
):
    before = _runtime_snapshot(runtime)
    guard = _RecordingGuard(verdict="denied")

    with pytest.raises(ceo_ingress.CeoIngressError) as raised:
        pr_a.run(
            ceo_ingress.handle_frame(
                _v2_frame(),
                runtime=runtime,
                grounding_provider=pr_a._FakeGrounding(),
                workspace_root=_workspace_root(tmp_path),
                service_state="READY",
                ceo_ingress_armed=True,
                **_guard_kwargs(guard),
            )
        )

    _assert_sanitized_backend_refused(raised)
    assert guard.invocations == 1
    assert sink_probe.calls == 0
    assert _runtime_snapshot(runtime) == before


def test_non_callable_guard_refuses_with_zero_sink_and_zero_effect(
    runtime: Runtime, tmp_path: Any, sink_probe: _SinkProbe
):
    before = _runtime_snapshot(runtime)

    with pytest.raises(ceo_ingress.CeoIngressError) as raised:
        pr_a.run(
            ceo_ingress.handle_frame(
                _v1_frame(),
                runtime=runtime,
                grounding_provider=pr_a._FakeGrounding(),
                workspace_root=_workspace_root(tmp_path),
                **_guard_kwargs(object()),
            )
        )

    _assert_sanitized_backend_refused(raised)
    assert sink_probe.calls == 0
    assert _runtime_snapshot(runtime) == before


def test_guard_refusal_leaves_no_trace_and_later_admission_still_succeeds(
    runtime: Runtime, tmp_path: Any, sink_probe: _SinkProbe
):
    refusing = _RecordingGuard(error=RuntimeError("first attempt denied"))
    with pytest.raises(ceo_ingress.CeoIngressError) as raised:
        pr_a.run(
            ceo_ingress.handle_frame(
                _v1_frame(),
                runtime=runtime,
                grounding_provider=pr_a._FakeGrounding(),
                workspace_root=_workspace_root(tmp_path),
                **_guard_kwargs(refusing),
            )
        )
    assert raised.value.code == "backend_refused"
    assert runtime.jobs.list_jobs() == []

    # The refused attempt created nothing, so the SAME request is still a
    # fresh admission afterwards — not a replay, not a second root.
    receipt = pr_a.run(
        ceo_ingress.handle_frame(
            _v1_frame(),
            runtime=runtime,
            grounding_provider=pr_a._FakeGrounding(),
            workspace_root=_workspace_root(tmp_path),
        )
    )
    assert receipt["duplicate"] is False
    assert receipt["dispatched"] is False
    assert len(runtime.jobs.list_jobs()) == 1
    assert sink_probe.calls == 1


# ===========================================================================
# required case 5 — exact replay bypasses the guard entirely
# ===========================================================================


def test_exact_replay_bypasses_refusing_guard_and_unavailable_providers(
    runtime: Runtime, tmp_path: Any, sink_probe: _SinkProbe
):
    admitting = _RecordingGuard()
    first = pr_a.run(
        _strict_v2_submission(runtime, tmp_path, guard=admitting)
    )
    assert admitting.invocations == 1
    assert first["duplicate"] is False

    # Same exact command, but now everything current is unavailable/hostile:
    # the guard refuses, the grounding provider would raise, and no dialogue
    # source provider is offered.  Durable replay must return the same root
    # without consulting any of them.
    def _forbidden_binding() -> dict[str, Any]:
        raise AssertionError("replay must not rebind execution")

    refusing = _RecordingGuard(error=RuntimeError("replay must bypass me"))
    broken_grounding = pr_a._FakeGrounding(
        error=AssertionError("replay must not observe current grounding")
    )
    second = pr_a.run(
        ceo_ingress.handle_frame(
            _strict_v2_frame(),
            runtime=runtime,
            grounding_provider=broken_grounding,
            workspace_root=_workspace_root(tmp_path),
            service_state="READY",
            ceo_ingress_armed=True,
            strict_v2_admission=True,
            execution_binding_provider=_forbidden_binding,
            dialogue_source_provider=None,
            **_guard_kwargs(refusing),
        )
    )

    assert refusing.invocations == 0
    assert broken_grounding.calls == 0
    assert second["duplicate"] is True
    assert second["intent_id"] == first["intent_id"]
    assert second["job_id"] == first["job_id"]
    assert second["fingerprint"] == first["fingerprint"]
    assert second["dispatched"] is False
    assert len(runtime.jobs.list_jobs()) == 1
    # The replay re-entered the one canonical sink exactly once more, and no
    # fresh sink material (binding/source) was demanded of the host.
    assert sink_probe.calls == 2
    assert "execution_binding" not in sink_probe.kwargs[1]
    assert "dialogue_source" not in sink_probe.kwargs[1]


def test_changed_content_replay_retains_conflict_even_with_permissive_guard(
    runtime: Runtime, tmp_path: Any, sink_probe: _SinkProbe
):
    permissive = _RecordingGuard()
    first = pr_a.run(
        ceo_ingress.handle_frame(
            _v1_frame(),
            runtime=runtime,
            grounding_provider=pr_a._FakeGrounding(),
            workspace_root=_workspace_root(tmp_path),
            **_guard_kwargs(permissive),
        )
    )
    assert permissive.invocations == 1

    # A permissive guard cannot turn a denied (changed-content) replay into a
    # second admission: the conflict law fires before any guard could matter.
    with pytest.raises(ceo_ingress.CeoIngressError) as raised:
        pr_a.run(
            ceo_ingress.handle_frame(
                json.loads(
                    pr_a._submit_bytes(
                        observed_grounding=pr_a.GROUNDING_A,
                        request=pr_a._research_request(
                            objective="A rewritten objective under the same id."
                        ),
                    )
                ),
                runtime=runtime,
                grounding_provider=pr_a._FakeGrounding(),
                workspace_root=_workspace_root(tmp_path),
                **_guard_kwargs(permissive),
            )
        )
    assert raised.value.code == "operation_conflict"
    assert permissive.invocations == 1
    assert len(runtime.jobs.list_jobs()) == 1
    job = runtime.jobs.get_job(first["job_id"])
    assert job is not None
    assert job.objective == pr_a._research_request()["objective"]


# ===========================================================================
# required case 6 — detached-copy isolation and replacement refusal
# ===========================================================================


def test_detached_copy_mutation_cannot_alter_submitted_envelope_or_fingerprint(
    runtime: Runtime, tmp_path: Any, sink_probe: _SinkProbe
):
    class _MutatingGuard:
        def __init__(self) -> None:
            self.pristine: Any = None

        def __call__(self, envelope: Any) -> None:
            self.pristine = copy.deepcopy(envelope)
            # Top-level field, nested mapping, nested list, and a nested
            # contract scalar — all through the callback's own alias.
            envelope["objective"] = "MUTATED BY CALLBACK"
            envelope["grounding"]["mastermind_sha"] = "f" * 40
            envelope["execution_contract"]["requested_authorities"][0] = "WRITE"
            envelope["execution_contract"]["attempt_limit"] = 20
            return None

    guard = _MutatingGuard()

    receipt = pr_a.run(
        ceo_ingress.handle_frame(
            _v1_frame(),
            runtime=runtime,
            grounding_provider=pr_a._FakeGrounding(),
            workspace_root=_workspace_root(tmp_path),
            **_guard_kwargs(guard),
        )
    )

    assert sink_probe.calls == 1
    submitted = sink_probe.payloads[0]
    assert submitted == guard.pristine
    assert submitted["objective"] == pr_a._research_request()["objective"]
    assert submitted["grounding"]["mastermind_sha"] == pr_a.GROUNDING_A["mastermind_sha"]
    assert submitted["execution_contract"]["requested_authorities"] == [
        "READ",
        "RESEARCH",
    ]
    assert receipt["fingerprint"] == ceo_intent.intent_fingerprint(guard.pristine)
    job = runtime.jobs.get_job(receipt["job_id"])
    assert job is not None
    assert job.objective == pr_a._research_request()["objective"]
    assert job.requested_authorities == ["READ", "RESEARCH"]


def test_replacement_mapping_return_refuses_rather_than_selecting_a_new_intent(
    runtime: Runtime, tmp_path: Any, sink_probe: _SinkProbe
):
    before = _runtime_snapshot(runtime)

    def _replacing_guard(envelope: Any) -> dict[str, Any]:
        replacement = copy.deepcopy(envelope)
        replacement["objective"] = "CALLBACK-SELECTED OBJECTIVE"
        return replacement

    with pytest.raises(ceo_ingress.CeoIngressError) as raised:
        pr_a.run(
            ceo_ingress.handle_frame(
                _v1_frame(),
                runtime=runtime,
                grounding_provider=pr_a._FakeGrounding(),
                workspace_root=_workspace_root(tmp_path),
                **_guard_kwargs(_replacing_guard),
            )
        )

    _assert_sanitized_backend_refused(raised)
    assert sink_probe.calls == 0
    assert _runtime_snapshot(runtime) == before


# ===========================================================================
# required case 7 — status/state never invoke the guard; closed public schema
# ===========================================================================


def test_status_and_state_frames_never_invoke_the_guard(
    runtime: Runtime, tmp_path: Any, sink_probe: _SinkProbe
):
    guard = _RecordingGuard()
    receipt = pr_a.run(
        ceo_ingress.handle_frame(
            _v1_frame(),
            runtime=runtime,
            grounding_provider=pr_a._FakeGrounding(),
            workspace_root=_workspace_root(tmp_path),
            **_guard_kwargs(guard),
        )
    )
    assert guard.invocations == 1
    automated = pr_a.run(
        ceo_ingress.handle_frame(
            _v2_frame(),
            runtime=runtime,
            grounding_provider=pr_a._FakeGrounding(),
            workspace_root=_workspace_root(tmp_path),
            service_state="READY",
            ceo_ingress_armed=True,
            **_guard_kwargs(guard),
        )
    )
    assert guard.invocations == 2

    status = pr_a.run(
        ceo_ingress.handle_frame(
            json.loads(
                pr_a._status_bytes(intent_id=receipt["intent_id"])
            ),
            runtime=runtime,
            grounding_provider=pr_a._FakeGrounding(),
            workspace_root=_workspace_root(tmp_path),
            **_guard_kwargs(guard),
        )
    )
    assert status["intent_id"] == receipt["intent_id"]
    assert status["job_id"] == receipt["job_id"]

    status_v2 = pr_a.run(
        ceo_ingress.handle_frame(
            json.loads(pr_a._status_v2_bytes()),
            runtime=runtime,
            grounding_provider=pr_a._FakeGrounding(),
            workspace_root=_workspace_root(tmp_path),
            service_state="READY",
            ceo_ingress_armed=True,
            **_guard_kwargs(guard),
        )
    )
    assert status_v2["intent_id"] == automated["intent_id"]

    state = pr_a.run(
        ceo_ingress.handle_frame(
            {"schema": ceo_ingress.STATE_SCHEMA},
            runtime=runtime,
            grounding_provider=pr_a._FakeGrounding(),
            workspace_root=_workspace_root(tmp_path),
            service_state="READY",
            ceo_ingress_armed=True,
            **_guard_kwargs(guard),
        )
    )
    assert state["schema"] == hot_state.HOT_STATE_SCHEMA

    assert guard.invocations == 2


def test_caller_supplied_guard_field_fails_closed_schema_before_business_effects(
    runtime: Runtime, tmp_path: Any, sink_probe: _SinkProbe
):
    grounding = pr_a._FakeGrounding()

    with pytest.raises(ceo_ingress.CeoIngressError) as raised:
        pr_a.run(
            ceo_ingress.handle_frame(
                _v1_frame(admission_guard=True),
                runtime=runtime,
                grounding_provider=grounding,
                workspace_root=_workspace_root(tmp_path),
            )
        )
    assert raised.value.code == "invalid_input"

    with pytest.raises(ceo_ingress.CeoIngressError) as raised_v2:
        pr_a.run(
            ceo_ingress.handle_frame(
                _v2_frame(admission_guard={"objective": "smuggled"}),
                runtime=runtime,
                grounding_provider=grounding,
                workspace_root=_workspace_root(tmp_path),
                service_state="READY",
                ceo_ingress_armed=True,
            )
        )
    assert raised_v2.value.code == "invalid_input"

    # Closed-schema rejection precedes every business effect.
    assert grounding.calls == 0
    assert sink_probe.calls == 0
    assert runtime.jobs.list_jobs() == []
    assert runtime.events.list_events() == []
