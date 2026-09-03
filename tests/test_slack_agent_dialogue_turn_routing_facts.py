from __future__ import annotations

import asyncio
import dataclasses
import importlib
import inspect

import pytest

from control_plane.executive_runtime import (
    AttemptStatus,
    ExecutiveDialogueSource,
    WorkerStatus,
)
from control_plane.executive_terminal_return import TerminalReturnCandidate
from control_plane.session_targets import RuntimeBinding, load_session_targets
from integrations.slack_agent_dialogue.executive_terminal_return_projector import (
    ResolvedTerminalReturnBinding,
    TerminalReturnProjectionReceipt,
)
from integrations.slack_agent_dialogue.turn_routing_facts import (
    TurnRoutingFactsError,
    resolve_terminal_turn_routing_facts,
    resolve_turn_routing_facts,
)
from tests.test_company_dialogue_runtime_binding import (
    THREAD_TS,
    caller,
    identity,
    parent,
    resolve,
    runtime_binding,
    snapshot,
)


def _ceo_binding(
    *,
    generation: int = 7,
    binding_id: str = "bind-ceoruntime0001",
    alias: str = "EXECUTIVE-CEO-A",
    surface: str = "chatgpt-sol",
) -> RuntimeBinding:
    return RuntimeBinding(
        session_alias=alias,
        binding_id=binding_id,
        binding_generation=generation,
        native_handle="provider-private-ceo-thread",
        account_label="provider-private-ceo-account",
        reasoning_surface=surface,
    )


def _registry():
    registry = load_session_targets()
    coo = dataclasses.replace(
        registry.targets["EXECUTIVE-COO-A"],
        reasoning_surface="codex",
    )
    registry = dataclasses.replace(
        registry,
        targets={**registry.targets, "EXECUTIVE-COO-A": coo},
    )
    return registry.with_root_job_bindings(
        {
            "JOB-100": {
                "ceo": "EXECUTIVE-CEO-A",
                "coo": "EXECUTIVE-COO-A",
            }
        }
    )


def _binding_for(
    seat: str,
    *,
    coo: RuntimeBinding | None = None,
    ceo: RuntimeBinding | None = None,
) -> RuntimeBinding | None:
    if seat == "coo":
        return coo if coo is not None else runtime_binding()
    if seat == "ceo":
        return ceo if ceo is not None else _ceo_binding()
    return None


def _terminal_candidate() -> TerminalReturnCandidate:
    terminal_digest = "1" * 64
    return TerminalReturnCandidate(
        job_id="JOB-200",
        attempt_id="ATT-200",
        worker_id="codex-worker-01",
        root_job_id="JOB-100",
        role="work",
        operation_key=identity().operation_key,
        session_ref=identity().session_ref,
        runtime_status="COMPLETED",
        result_status="RESULT",
        result_envelope_digest="2" * 64,
        terminal_evidence_digest=terminal_digest,
        artifact_receipt_digest="3" * 64,
        validation_receipt_digest="4" * 64,
        effective_grant_digest="5" * 64,
        terminal_at="2026-09-03T08:00:00Z",
        message_key=f"asd-exec-result-{terminal_digest}",
        summary="The exact worker result completed.",
        review_verdict=None,
        dialogue_source=ExecutiveDialogueSource(
            schema_version="mastermind.executive_dialogue_source/v1",
            work_ref=parent()["work_ref"],
            commission_ref=parent()["commission_ref"],
            watch_mode=parent()["watch_mode"],
        ),
    )


def _terminal_binding() -> ResolvedTerminalReturnBinding:
    terminal = _terminal_candidate()
    attempt = {
        "kind": "worker_attempt",
        "job_id": terminal.job_id,
        "attempt_id": terminal.attempt_id,
        "worker_id": terminal.worker_id,
    }
    return ResolvedTerminalReturnBinding(
        work_ref=parent()["work_ref"],
        commission_ref=parent()["commission_ref"],
        session_ref=terminal.session_ref,
        operation_key=terminal.operation_key,
        watch_mode=parent()["watch_mode"],
        actor_ref=attempt,
        applies_to={"kind": "executive_attempt", **{k: attempt[k] for k in ("job_id", "attempt_id", "worker_id")}},
    )


def _terminal_receipt() -> TerminalReturnProjectionReceipt:
    return TerminalReturnProjectionReceipt(
        action="POSTED",
        message_key=_terminal_candidate().message_key,
        fingerprint="6" * 64,
        message_ts="1788000000.123457",
        duplicate_timestamps=(),
        thread_ts=THREAD_TS,
        parent_author_user_id="U0RELAY001",
        parent_fingerprint=parent()["fingerprint"],
    )


def _terminal_snapshot():
    return snapshot(
        attempt_status=AttemptStatus.COMPLETED,
        worker_status=WorkerStatus.AVAILABLE,
    )


def test_terminal_routing_derives_targets_without_busy_worker_or_stale_worker_binding() -> None:
    facts = resolve_terminal_turn_routing_facts(
        delegation_identity=identity(),
        dialogue_parent=parent(),
        thread_ts=THREAD_TS,
        current_worker=_terminal_snapshot(),
        terminal_candidate=_terminal_candidate(),
        projection_receipt=_terminal_receipt(),
        resolved_binding=_terminal_binding(),
        registry=_registry(),
        current_binding_for=_binding_for,
    )

    assert facts.bound_operation_key == identity().operation_key
    assert facts.bound_commission_fingerprint == parent()["fingerprint"]
    assert facts.root_job_id == "JOB-100"
    assert facts.source_workstream == parent()["work_ref"]
    assert facts.ceo_target_bound is True
    assert facts.coo_target_bound is True


@pytest.mark.parametrize(
    "current",
    [
        snapshot(attempt_status=AttemptStatus.COMPLETED, worker_status=WorkerStatus.BUSY),
        snapshot(attempt_status=AttemptStatus.RUNNING, worker_status=WorkerStatus.AVAILABLE),
        dataclasses.replace(_terminal_snapshot(), job_id="JOB-999"),
        dataclasses.replace(_terminal_snapshot(), root_job_id="JOB-999"),
        dataclasses.replace(_terminal_snapshot(), attempt_id="ATT-999"),
        dataclasses.replace(_terminal_snapshot(), worker_id="other-worker"),
        dataclasses.replace(_terminal_snapshot(), parent_fingerprint="f" * 64),
    ],
)
def test_terminal_routing_requires_exact_completed_available_source_snapshot(current) -> None:
    calls: list[str] = []

    with pytest.raises(TurnRoutingFactsError) as exc:
        resolve_terminal_turn_routing_facts(
            delegation_identity=identity(),
            dialogue_parent=parent(),
            thread_ts=THREAD_TS,
            current_worker=current,
            terminal_candidate=_terminal_candidate(),
            projection_receipt=_terminal_receipt(),
            resolved_binding=_terminal_binding(),
            registry=_registry(),
            current_binding_for=lambda seat: calls.append(seat),
        )

    assert exc.value.code == "TERMINAL_RESULT_BINDING_MISMATCH"
    assert calls == []


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            lambda terminal, receipt, binding: (dataclasses.replace(terminal, job_id="JOB-999"), receipt, binding),
            "TERMINAL_RESULT_BINDING_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (dataclasses.replace(terminal, root_job_id="JOB-999"), receipt, binding),
            "TERMINAL_RESULT_BINDING_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (dataclasses.replace(terminal, attempt_id="ATT-999"), receipt, binding),
            "TERMINAL_RESULT_BINDING_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (dataclasses.replace(terminal, worker_id="forged-worker"), receipt, binding),
            "TERMINAL_RESULT_BINDING_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (dataclasses.replace(terminal, operation_key="forged-operation"), receipt, binding),
            "TERMINAL_RESULT_BINDING_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (dataclasses.replace(terminal, session_ref="asd-session-forged-operation"), receipt, binding),
            "TERMINAL_RESULT_BINDING_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (dataclasses.replace(terminal, runtime_status="FAILED"), receipt, binding),
            "TERMINAL_RESULT_BINDING_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (dataclasses.replace(terminal, result_status="BLOCKED"), receipt, binding),
            "TERMINAL_RESULT_BINDING_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (dataclasses.replace(terminal, dialogue_source=None), receipt, binding),
            "TERMINAL_RESULT_BINDING_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (
                dataclasses.replace(
                    terminal,
                    dialogue_source=dataclasses.replace(
                        terminal.dialogue_source,
                        work_ref="WS:FORGED-WORK",
                    ),
                ),
                receipt,
                binding,
            ),
            "TERMINAL_RESULT_BINDING_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (
                dataclasses.replace(
                    terminal,
                    dialogue_source=dataclasses.replace(
                        terminal.dialogue_source,
                        commission_ref={
                            **parent()["commission_ref"],
                            "content_sha256": "e" * 64,
                        },
                    ),
                ),
                receipt,
                binding,
            ),
            "TERMINAL_RESULT_BINDING_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (
                dataclasses.replace(
                    terminal,
                    dialogue_source=dataclasses.replace(
                        terminal.dialogue_source,
                        watch_mode=None,
                    ),
                ),
                receipt,
                binding,
            ),
            "TERMINAL_RESULT_BINDING_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (terminal, dataclasses.replace(receipt, action="IGNORED"), binding),
            "TERMINAL_RESULT_RECEIPT_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (terminal, dataclasses.replace(receipt, message_key="asd-exec-result-" + "f" * 64), binding),
            "TERMINAL_RESULT_RECEIPT_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (terminal, dataclasses.replace(receipt, thread_ts="1788000000.123499"), binding),
            "TERMINAL_RESULT_RECEIPT_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (terminal, dataclasses.replace(receipt, parent_fingerprint="f" * 64), binding),
            "TERMINAL_RESULT_RECEIPT_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (terminal, dataclasses.replace(receipt, duplicate_timestamps=("1788000000.123458",)), binding),
            "TERMINAL_RESULT_RECEIPT_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (terminal, receipt, dataclasses.replace(binding, work_ref="WS:FORGED-WORK")),
            "TERMINAL_RESULT_BINDING_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (
                terminal,
                receipt,
                dataclasses.replace(
                    binding,
                    commission_ref={
                        **binding.commission_ref,
                        "content_sha256": "e" * 64,
                    },
                ),
            ),
            "TERMINAL_RESULT_BINDING_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (terminal, receipt, dataclasses.replace(binding, session_ref="asd-session-forged-operation")),
            "TERMINAL_RESULT_BINDING_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (terminal, receipt, dataclasses.replace(binding, operation_key="forged-operation")),
            "TERMINAL_RESULT_BINDING_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (terminal, receipt, dataclasses.replace(binding, watch_mode=None)),
            "TERMINAL_RESULT_BINDING_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (
                terminal,
                receipt,
                dataclasses.replace(
                    binding,
                    actor_ref={**binding.actor_ref, "worker_id": "forged-worker"},
                ),
            ),
            "TERMINAL_RESULT_BINDING_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (
                terminal,
                receipt,
                dataclasses.replace(
                    binding,
                    applies_to={
                        **binding.applies_to,
                        "worker_id": "forged-worker",
                    },
                ),
            ),
            "TERMINAL_RESULT_BINDING_MISMATCH",
        ),
        (
            lambda terminal, receipt, binding: (terminal, receipt, dataclasses.replace(binding, allowed_message_types=("ACK", "RESULT"))),
            "TERMINAL_RESULT_BINDING_MISMATCH",
        ),
    ],
)
def test_terminal_routing_refuses_any_identity_join_drift_before_target_lookup(
    mutation,
    expected_code: str,
) -> None:
    terminal, receipt, binding = mutation(
        _terminal_candidate(),
        _terminal_receipt(),
        _terminal_binding(),
    )
    calls: list[str] = []

    with pytest.raises(TurnRoutingFactsError) as exc:
        resolve_terminal_turn_routing_facts(
            delegation_identity=identity(),
            dialogue_parent=parent(),
            thread_ts=THREAD_TS,
            current_worker=_terminal_snapshot(),
            terminal_candidate=terminal,
            projection_receipt=receipt,
            resolved_binding=binding,
            registry=_registry(),
            current_binding_for=lambda seat: calls.append(seat),
        )

    assert exc.value.code == expected_code
    assert calls == []


def test_exact_current_worker_and_registry_derive_closed_routing_facts() -> None:
    dialogue_parent = parent()
    current = snapshot()

    facts = resolve_turn_routing_facts(
        dialogue_parent=dialogue_parent,
        current_worker=current,
        binding_resolution=resolve(current=current, dialogue_parent=dialogue_parent),
        registry=_registry(),
        current_binding_for=_binding_for,
    )

    assert facts.bound_operation_key == dialogue_parent["operation_key"]
    assert facts.bound_commission_fingerprint == dialogue_parent["fingerprint"]
    assert facts.root_job_id == current.root_job_id
    assert facts.routing_workstream is None
    assert facts.source_workstream == dialogue_parent["work_ref"]
    assert facts.ceo_target_bound is True
    assert facts.coo_target_bound is True
    assert current.runtime_binding.native_handle not in repr(facts)
    assert _ceo_binding().native_handle not in repr(facts)


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda result, dialogue_parent, current: dataclasses.replace(
                result,
                binding=dataclasses.replace(
                    result.binding,
                    operation_key="forged-operation",
                ),
            ),
            "DIALOGUE_BINDING_MISMATCH",
        ),
        (
            lambda result, dialogue_parent, current: dataclasses.replace(
                result,
                binding=dataclasses.replace(
                    result.binding,
                    commission_ref={
                        **result.binding.commission_ref,
                        "content_sha256": "e" * 64,
                    },
                ),
            ),
            "DIALOGUE_BINDING_MISMATCH",
        ),
        (
            lambda result, dialogue_parent, current: dataclasses.replace(
                result,
                binding=dataclasses.replace(
                    result.binding,
                    applies_to={
                        **result.binding.applies_to,
                        "worker_id": "forged-worker",
                    },
                ),
            ),
            "DIALOGUE_BINDING_MISMATCH",
        ),
    ],
)
def test_forged_resolved_binding_is_refused_before_target_resolution(
    mutate,
    code: str,
) -> None:
    dialogue_parent = parent()
    current = snapshot()
    result = mutate(
        resolve(current=current, dialogue_parent=dialogue_parent),
        dialogue_parent,
        current,
    )
    calls: list[str] = []

    with pytest.raises(TurnRoutingFactsError) as exc:
        resolve_turn_routing_facts(
            dialogue_parent=dialogue_parent,
            current_worker=current,
            binding_resolution=result,
            registry=_registry(),
            current_binding_for=lambda seat: calls.append(seat),
        )

    assert exc.value.code == code
    assert calls == []


def test_stale_parent_fingerprint_is_refused_before_target_resolution() -> None:
    dialogue_parent = parent()
    current = snapshot(parent_fingerprint="f" * 64)
    calls: list[str] = []

    with pytest.raises(TurnRoutingFactsError) as exc:
        resolve_turn_routing_facts(
            dialogue_parent=dialogue_parent,
            current_worker=current,
            binding_resolution=resolve(dialogue_parent=dialogue_parent),
            registry=_registry(),
            current_binding_for=lambda seat: calls.append(seat),
        )

    assert exc.value.code == "DIALOGUE_BINDING_MISMATCH"
    assert calls == []


@pytest.mark.parametrize(
    "current_coo",
    [
        None,
        runtime_binding(generation=4),
        runtime_binding(binding_id="bind-worker-runtime-0002"),
        RuntimeBinding(
            session_alias="EXECUTIVE-CEO-A",
            binding_id="bind-wrongseat0001",
            binding_generation=1,
            native_handle="private",
            account_label="private",
            reasoning_surface="chatgpt-sol",
        ),
    ],
)
def test_current_worker_runtime_drift_refuses(current_coo: RuntimeBinding | None) -> None:
    dialogue_parent = parent()
    current = snapshot()

    with pytest.raises(TurnRoutingFactsError) as exc:
        resolve_turn_routing_facts(
            dialogue_parent=dialogue_parent,
            current_worker=current,
            binding_resolution=resolve(current=current, dialogue_parent=dialogue_parent),
            registry=_registry(),
            current_binding_for=lambda seat: (
                current_coo if seat == "coo" else _ceo_binding()
            ),
        )

    assert exc.value.code == "CURRENT_WORKER_BINDING_DRIFT"


def test_target_alias_or_surface_mismatch_refuses_instead_of_injecting_bound_true() -> None:
    dialogue_parent = parent()
    current = snapshot()

    with pytest.raises(TurnRoutingFactsError) as exc:
        resolve_turn_routing_facts(
            dialogue_parent=dialogue_parent,
            current_worker=current,
            binding_resolution=resolve(current=current, dialogue_parent=dialogue_parent),
            registry=_registry(),
            current_binding_for=lambda seat: (
                current.runtime_binding
                if seat == "coo"
                else _ceo_binding(alias="EXECUTIVE-COO-A", surface="codex")
            ),
        )

    assert exc.value.code == "TARGET_BINDING_MISMATCH"
    parameters = inspect.signature(resolve_turn_routing_facts).parameters
    assert "ceo_target_bound" not in parameters
    assert "coo_target_bound" not in parameters


def test_missing_ceo_binding_derives_false_but_preserves_exact_coo_binding() -> None:
    dialogue_parent = parent()
    current = snapshot()

    facts = resolve_turn_routing_facts(
        dialogue_parent=dialogue_parent,
        current_worker=current,
        binding_resolution=resolve(current=current, dialogue_parent=dialogue_parent),
        registry=_registry(),
        current_binding_for=lambda seat: (
            current.runtime_binding if seat == "coo" else None
        ),
    )

    assert facts.ceo_target_bound is False
    assert facts.coo_target_bound is True


def test_non_resolved_wp3_result_refuses_without_target_resolution() -> None:
    dialogue_parent = parent()
    current = snapshot()
    refused = dataclasses.replace(resolve(), state=type(resolve().state).REFUSED)
    calls: list[str] = []

    with pytest.raises(TurnRoutingFactsError) as exc:
        resolve_turn_routing_facts(
            dialogue_parent=dialogue_parent,
            current_worker=current,
            binding_resolution=refused,
            registry=_registry(),
            current_binding_for=lambda seat: calls.append(seat),
        )

    assert exc.value.code == "CURRENT_WORKER_UNRESOLVED"
    assert calls == []


def _runtime_candidate(runtime):
    return runtime.RelayTurnCandidate(
        delegation_identity=identity(),
        dialogue_parent=parent(),
        thread_ts=THREAD_TS,
        current_worker=snapshot(),
        actor=caller(),
    )


def test_runtime_candidate_exposes_no_parallel_context_or_routing_authority() -> None:
    runtime = importlib.import_module("integrations.slack_agent_dialogue.runtime")

    assert set(runtime.RelayTurnCandidate.__dataclass_fields__) == {
        "delegation_identity",
        "dialogue_parent",
        "thread_ts",
        "current_worker",
        "actor",
        "terminal_candidate",
        "terminal_projection_receipt",
    }
    parameters = inspect.signature(runtime.RelayTurnCandidate).parameters
    assert "context" not in parameters
    assert "routing_workstream" not in parameters


def test_runtime_derives_observer_context_and_routing_only_from_accepted_owners() -> None:
    runtime = importlib.import_module("integrations.slack_agent_dialogue.runtime")
    expected = resolve(dialogue_parent=parent()).binding
    assert expected is not None

    class Observer:
        def __init__(self) -> None:
            self.calls = []

        async def reconcile_once(self, *, context, routing):
            self.calls.append((context, routing))
            return runtime.ObservationReceipt(
                outcome=runtime.ObservationOutcome.NO_ACTION,
                reason="TEST",
                decision=None,
                obligation=None,
                route=None,
            )

    observer = Observer()
    from tests.test_slack_agent_dialogue_runtime import _w3c_dependencies

    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_registry(),
        current_binding_for=_binding_for,
        candidate_source=lambda: (_runtime_candidate(runtime),),
        **_w3c_dependencies(runtime),
    )

    receipts = asyncio.run(turn_runtime.reconcile_once())

    assert len(receipts) == 1
    assert receipts[0].outcome is runtime.ObservationOutcome.NO_ACTION
    assert len(observer.calls) == 1
    context, routing = observer.calls[0]
    assert context.work_ref == expected.work_ref
    assert dict(context.commission_ref) == dict(expected.commission_ref)
    assert context.session_ref == expected.session_ref
    assert context.operation_key == expected.operation_key
    assert context.watch_mode == expected.watch_mode
    assert dict(context.actor_ref) == dict(expected.actor_ref)
    assert dict(context.applies_to) == dict(expected.applies_to)
    assert routing.routing_workstream is None
    assert routing.source_workstream == parent()["work_ref"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operation_key", "forged-operation"),
        ("session_ref", "asd-session-forged-operation"),
        (
            "commission_ref",
            {
                **parent()["commission_ref"],
                "content_sha256": "e" * 64,
            },
        ),
        (
            "actor_ref",
            {
                "kind": "worker_attempt",
                "job_id": "JOB-200",
                "attempt_id": "ATT-200",
                "worker_id": "forged-worker",
            },
        ),
        (
            "applies_to",
            {
                "kind": "executive_attempt",
                "job_id": "JOB-200",
                "attempt_id": "ATT-200",
                "worker_id": "forged-worker",
            },
        ),
    ],
)
def test_runtime_refuses_forged_wp3_context_before_observer_or_binding_io(
    monkeypatch,
    field: str,
    value,
) -> None:
    runtime = importlib.import_module("integrations.slack_agent_dialogue.runtime")
    accepted = resolve(dialogue_parent=parent())
    assert accepted.binding is not None
    forged = dataclasses.replace(
        accepted,
        binding=dataclasses.replace(accepted.binding, **{field: value}),
    )
    monkeypatch.setattr(
        runtime,
        "resolve_company_dialogue_binding",
        lambda **_kwargs: forged,
    )

    class Observer:
        calls = 0

        async def reconcile_once(self, *, context, routing):
            self.calls += 1
            raise AssertionError("observer/Slack path must not run for forged identity")

    binding_calls: list[str] = []
    observer = Observer()
    from tests.test_slack_agent_dialogue_runtime import _w3c_dependencies

    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_registry(),
        current_binding_for=lambda seat: binding_calls.append(seat),
        candidate_source=lambda: (_runtime_candidate(runtime),),
        **_w3c_dependencies(runtime),
    )

    receipts = asyncio.run(turn_runtime.reconcile_once())

    assert len(receipts) == 1
    assert receipts[0].outcome is runtime.ObservationOutcome.REFUSED
    assert receipts[0].reason == "DIALOGUE_BINDING_MISMATCH"
    assert observer.calls == 0
    assert binding_calls == []
