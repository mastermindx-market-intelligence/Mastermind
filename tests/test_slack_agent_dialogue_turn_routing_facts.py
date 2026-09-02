from __future__ import annotations

import asyncio
import dataclasses
import importlib
import inspect

import pytest

from control_plane.session_targets import RuntimeBinding, load_session_targets
from integrations.slack_agent_dialogue.turn_routing_facts import (
    TurnRoutingFactsError,
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
    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_registry(),
        current_binding_for=_binding_for,
        candidate_source=lambda: (_runtime_candidate(runtime),),
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
    turn_runtime = runtime.AgentRelayTurnRuntime(
        observer=observer,
        registry=_registry(),
        current_binding_for=lambda seat: binding_calls.append(seat),
        candidate_source=lambda: (_runtime_candidate(runtime),),
    )

    receipts = asyncio.run(turn_runtime.reconcile_once())

    assert len(receipts) == 1
    assert receipts[0].outcome is runtime.ObservationOutcome.REFUSED
    assert receipts[0].reason == "DIALOGUE_BINDING_MISMATCH"
    assert observer.calls == 0
    assert binding_calls == []
