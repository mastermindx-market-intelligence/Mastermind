from __future__ import annotations

import dataclasses
import inspect

import pytest

from control_plane.session_targets import RuntimeBinding, load_session_targets
from integrations.slack_agent_dialogue.turn_routing_facts import (
    TurnRoutingFactsError,
    resolve_turn_routing_facts,
)
from tests.test_company_dialogue_runtime_binding import (
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
