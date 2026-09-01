from __future__ import annotations

import ast
import dataclasses
import importlib
import importlib.util
import inspect
import json
from pathlib import Path

import pytest


MODULE_NAME = "control_plane.operator_continuity_projection"
ATTEMPT_1 = "ATT-" + "1" * 32
ATTEMPT_2 = "ATT-" + "2" * 32
ATTEMPT_3 = "ATT-" + "3" * 32
CAPSULE_2 = "a" * 64


def _module():
    spec = importlib.util.find_spec(MODULE_NAME)
    assert spec is not None, "operator continuity projection is not implemented"
    return importlib.import_module(MODULE_NAME)


def _current(module, **overrides):
    values = {
        "root_job_id": "JOB-001",
        "job_id": "JOB-004",
        "attempt_id": ATTEMPT_2,
        "worker_id": "claude-worker-b",
        "attempt_state": module.AttemptState.RUNNING,
        "target_seat": module.Seat.COO,
        "session_alias": "EXECUTIVE-COO-A",
        "provider": "claude",
        "account_label": "claude-pro-02",
        "host_ref": "host-opaque-b",
        "provider_session_id_present": True,
        "binding_id": "bind-runtime-b123",
        "binding_generation": 1,
        "continuation_state": module.ContinuationState.ACKNOWLEDGED,
        "capsule_id": CAPSULE_2,
        "predecessor_attempt_id": ATTEMPT_1,
    }
    values.update(overrides)
    return module.CurrentAttemptFact(**values)


def _previous(module, **overrides):
    values = {
        "root_job_id": "JOB-001",
        "job_id": "JOB-003",
        "attempt_id": ATTEMPT_1,
        "worker_id": "claude-worker-a",
        "terminal_state": module.AttemptState.RATE_LIMITED,
        "provider": "claude",
        "account_label": "claude-pro-01",
    }
    values.update(overrides)
    return module.PreviousAttemptFact(**values)


def _capacity(module, **overrides):
    values = {
        "state": module.CapacityState.AVAILABLE,
        "eligible": True,
        "evidence_age_seconds": 12,
        "stale": False,
        "reason_codes": (),
    }
    values.update(overrides)
    return module.CapacityEvidence(**values)


def _facts(module, **overrides):
    values = {
        "root_job_id": "JOB-001",
        "job_id": "JOB-004",
        "current_attempt_id": ATTEMPT_2,
        "target_seat": module.Seat.COO,
        "session_alias": "EXECUTIVE-COO-A",
        "logical_actor": "Mastermind · Fable",
        "current_join": module.CurrentJoinState.EXACT,
        "current": _current(module),
        "previous": _previous(module),
        "requeue_committed": True,
        "effect_state": module.EffectState.NONE,
        "capacity": _capacity(module),
        "transport": module.TransportEvidence(),
    }
    values.update(overrides)
    return module.OperatorContinuityFacts(**values)


def test_module_exists_before_behavior_is_exercised() -> None:
    assert _module().__name__ == MODULE_NAME


def test_acknowledged_rebound_projects_running_without_laundering_ack() -> None:
    module = _module()

    projection = module.project_operator_continuity(_facts(module))
    wire = projection.to_dict()

    assert wire["schema"] == "mastermind.operator_continuity_projection.v1"
    assert wire["status"] == "RUNNING"
    assert wire["current"]["attempt_id"] == ATTEMPT_2
    assert wire["current"]["continuation_state"] == "ACKNOWLEDGED"
    assert wire["previous"]["attempt_id"] == ATTEMPT_1
    assert wire["previous"]["terminal_status"] == "RATE_LIMITED"
    assert wire["attention"] == "none"
    assert "continuation_acknowledged" in wire["reason_codes"]


def test_claimed_attempt_without_provider_session_is_rebinding() -> None:
    module = _module()
    current = _current(
        module,
        attempt_state=module.AttemptState.CLAIMED,
        provider_session_id_present=False,
        binding_id=None,
        binding_generation=None,
        continuation_state=module.ContinuationState.NONE,
        capsule_id=None,
        predecessor_attempt_id=None,
    )
    facts = _facts(
        module,
        current=current,
        previous=None,
        requeue_committed=False,
    )

    wire = module.project_operator_continuity(facts).to_dict()

    assert wire["status"] == "REBINDING"
    assert wire["current"]["provider_session_id_present"] is False
    assert "provider_session_absent" in wire["reason_codes"]
    assert "runtime_binding_absent" in wire["reason_codes"]


def test_prepared_continuation_is_rebinding_not_acknowledged() -> None:
    module = _module()
    current = _current(
        module,
        continuation_state=module.ContinuationState.PREPARED,
        capsule_id=CAPSULE_2,
    )

    wire = module.project_operator_continuity(
        _facts(module, current=current)
    ).to_dict()

    assert wire["status"] == "REBINDING"
    assert wire["current"]["continuation_state"] == "PREPARED"
    assert "continuation_prepared" in wire["reason_codes"]
    assert "continuation_acknowledged" not in wire["reason_codes"]


def test_effect_unknown_dominates_newer_transport_context() -> None:
    module = _module()
    facts = _facts(
        module,
        effect_state=module.EffectState.EFFECT_UNKNOWN,
        transport=module.TransportEvidence(
            degraded=False,
            reason_codes=("newer_transport_message_observed",),
        ),
    )

    wire = module.project_operator_continuity(facts).to_dict()

    assert wire["status"] == "BLOCKED"
    assert wire["attention"] == "reconciliation_required"
    assert "effect_unknown" in wire["reason_codes"]


def test_terminal_without_eligible_capacity_projects_waiting_capacity() -> None:
    module = _module()
    facts = _facts(
        module,
        job_id="JOB-005",
        current_attempt_id=None,
        current_join=module.CurrentJoinState.NONE,
        current=None,
        previous=_previous(module),
        requeue_committed=False,
        capacity=_capacity(
            module,
            state=module.CapacityState.UNAVAILABLE,
            eligible=False,
            reason_codes=("all_eligible_realms_unavailable",),
        ),
    )

    wire = module.project_operator_continuity(facts).to_dict()

    assert wire["status"] == "WAITING_CAPACITY"
    assert wire["current"] is None
    assert wire["capacity"]["state"] == "unavailable"
    assert wire["capacity"]["eligible"] is False
    assert wire["attention"] == "capacity_risk"
    assert "no_eligible_capacity" in wire["reason_codes"]


def test_current_completed_attempt_projects_completed() -> None:
    module = _module()
    current = _current(
        module,
        attempt_state=module.AttemptState.COMPLETED,
        continuation_state=module.ContinuationState.ACKNOWLEDGED,
    )

    wire = module.project_operator_continuity(
        _facts(module, current=current)
    ).to_dict()

    assert wire["status"] == "COMPLETED"
    assert wire["attention"] == "none"
    assert "current_attempt_completed" in wire["reason_codes"]


@pytest.mark.parametrize(
    ("join_state", "reason"),
    [
        ("MISSING", "current_join_missing"),
        ("AMBIGUOUS", "current_join_ambiguous"),
        ("CONTRADICTORY", "current_join_contradictory"),
    ],
)
def test_non_exact_current_join_is_unknown_and_never_selects_a_winner(
    join_state: str,
    reason: str,
) -> None:
    module = _module()
    facts = _facts(
        module,
        current_attempt_id=None,
        current_join=module.CurrentJoinState[join_state],
        current=None,
        previous=None,
        requeue_committed=False,
    )

    wire = module.project_operator_continuity(facts).to_dict()

    assert wire["status"] == "UNKNOWN"
    assert wire["current"] is None
    assert wire["attention"] == "decision_required"
    assert reason in wire["reason_codes"]


def test_stale_capacity_never_defaults_to_available_or_rewrites_runtime() -> None:
    module = _module()
    facts = _facts(
        module,
        capacity=_capacity(
            module,
            state=module.CapacityState.AVAILABLE,
            eligible=True,
            evidence_age_seconds=901,
            stale=True,
            reason_codes=("provider_sample_old",),
        ),
    )

    wire = module.project_operator_continuity(facts).to_dict()

    assert wire["status"] == "RUNNING"
    assert wire["capacity"]["state"] == "unknown"
    assert wire["capacity"]["eligible"] is None
    assert wire["capacity"]["stale"] is True
    assert wire["attention"] == "capacity_risk"
    assert "capacity_evidence_stale" in wire["reason_codes"]


def test_transport_degradation_does_not_rewrite_executive_lifecycle() -> None:
    module = _module()
    facts = _facts(
        module,
        transport=module.TransportEvidence(
            degraded=True,
            reason_codes=("slack_projection_effect_unknown",),
        ),
    )

    wire = module.project_operator_continuity(facts).to_dict()

    assert wire["status"] == "RUNNING"
    assert wire["attention"] == "transport_degraded"
    assert "transport_degraded" in wire["reason_codes"]


def test_exact_current_attempt_pointer_prevents_old_attempt_selection() -> None:
    module = _module()

    with pytest.raises(ValueError, match="current_attempt_id"):
        dataclasses.replace(
            _facts(module),
            current_attempt_id=ATTEMPT_3,
        )


def test_requeue_requires_exact_predecessor_and_realm_evidence() -> None:
    module = _module()

    with pytest.raises(ValueError, match="predecessor_attempt_id"):
        _facts(
            module,
            current=_current(module, predecessor_attempt_id=ATTEMPT_3),
        )

    with pytest.raises(ValueError, match="account_label"):
        _previous(module, account_label="")


def test_missing_capacity_is_unknown_not_available() -> None:
    module = _module()

    wire = module.project_operator_continuity(
        _facts(module, capacity=None)
    ).to_dict()

    assert wire["status"] == "RUNNING"
    assert wire["capacity"] == {
        "state": "unknown",
        "eligible": None,
        "evidence_age_seconds": None,
        "stale": False,
        "reason_codes": ["capacity_evidence_missing"],
    }
    assert "capacity_evidence_missing" in wire["reason_codes"]


def test_reason_code_order_is_canonical_and_input_order_independent() -> None:
    module = _module()
    first = _facts(
        module,
        capacity=_capacity(
            module,
            state=module.CapacityState.DEGRADED,
            eligible=True,
            reason_codes=("zeta", "alpha", "alpha"),
        ),
        transport=module.TransportEvidence(
            degraded=True,
            reason_codes=("two", "one", "two"),
        ),
    )
    second = _facts(
        module,
        capacity=_capacity(
            module,
            state=module.CapacityState.DEGRADED,
            eligible=True,
            reason_codes=("alpha", "zeta"),
        ),
        transport=module.TransportEvidence(
            degraded=True,
            reason_codes=("one", "two"),
        ),
    )

    first_wire = module.project_operator_continuity(first).to_dict()
    second_wire = module.project_operator_continuity(second).to_dict()

    assert first_wire == second_wire
    assert first_wire["reason_codes"] == sorted(set(first_wire["reason_codes"]))
    assert first_wire["capacity"]["reason_codes"] == ["alpha", "zeta"]
    assert first_wire["transport"]["reason_codes"] == ["one", "two"]


def test_public_wire_exposes_presence_not_native_session_identity_or_email() -> None:
    module = _module()
    wire = module.project_operator_continuity(_facts(module)).to_dict()

    assert "provider_session_id" not in wire["current"]
    assert "native_handle" not in wire["current"]
    assert wire["current"]["provider_session_id_present"] is True
    assert "@" not in json.dumps(wire, sort_keys=True)

    with pytest.raises(ValueError, match="account_label"):
        _current(module, account_label="owner@example.com")


def test_contract_has_no_title_recency_slack_or_native_session_selector() -> None:
    module = _module()
    fields = {field.name for field in dataclasses.fields(module.OperatorContinuityFacts)}
    forbidden = {
        "title",
        "newest_timestamp",
        "slack_message",
        "slack_delivered",
        "provider_session_id",
        "native_handle",
    }

    assert fields.isdisjoint(forbidden)
    values = {
        field.name: getattr(_facts(module), field.name)
        for field in dataclasses.fields(module.OperatorContinuityFacts)
    }
    with pytest.raises(TypeError):
        module.OperatorContinuityFacts(
            **values,
            slack_delivered=True,
        )


def test_projection_types_are_immutable() -> None:
    module = _module()
    projection = module.project_operator_continuity(_facts(module))

    with pytest.raises(dataclasses.FrozenInstanceError):
        projection.status = module.ContinuityStatus.UNKNOWN


def test_module_is_pure_and_imports_no_runtime_or_io_owner() -> None:
    module = _module()
    source_path = Path(inspect.getsourcefile(module) or "")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    imported_roots = set()
    called_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_roots.add((node.module or "").split(".", 1)[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_names.add(node.func.attr)

    assert imported_roots <= {"__future__", "dataclasses", "enum", "re", "typing"}
    assert called_names.isdisjoint(
        {
            "open",
            "print",
            "connect",
            "request",
            "send",
            "sleep",
            "time",
            "now",
            "utcnow",
            "uuid4",
            "run",
            "Popen",
        }
    )
    assert "control_plane" not in imported_roots
    assert "integrations" not in imported_roots
