"""Trusted host-side join from a candidate continuation to the Wake ledger.

Hermetic: stdlib + pytest.  No network, no GitHub client, no Wake dispatch,
no provider transport, no new SQLite table.  The tests use a temporary
test-owned Runtime only.
"""
from __future__ import annotations

import ast
import dataclasses
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from control_plane.executive_runtime import Runtime
from control_plane.github_ci_candidate_continuation import (
    CandidateCIContinuationResult,
    wait_for_candidate_continuation,
)
from control_plane.github_ci_candidate_delivery import (
    SCHEMA as DELIVERY_SCHEMA,
    CandidateCIContinuationDeliveryDisposition,
    CandidateCIContinuationDeliveryEffectUnknown,
    CandidateCIContinuationDeliveryError,
    persist_candidate_continuation,
)
from control_plane.github_ci_candidate_observer import (
    CandidateObserverDisposition,
    observe_candidate_transition,
)
from control_plane.github_ci_candidate_waiter import (
    CandidateWaitDisposition,
    CandidateWaiterRegistry,
)
from control_plane.github_release_assessment import (
    CheckConclusion,
    CheckStatus,
)
from control_plane.wake_events import SourceKind, WakeKind, mint_obligation
from control_plane.wake_ledger import WAKE_AGGREGATE_TYPE
from control_plane.wake_persist import WakeLedgerRepository
from tests.test_github_ci_candidate_observer import observation
from tests.test_github_ci_candidate_wake import binding


ROOT = Path(__file__).resolve().parents[1]
MATERIAL_TOKEN = "m" * 24
QUIESCENT_TOKEN = "q" * 24


def _green() -> object:
    return observation(
        test_status=CheckStatus.COMPLETED,
        test_conclusion=CheckConclusion.SUCCESS,
        codeql_status=CheckStatus.COMPLETED,
        codeql_conclusion=CheckConclusion.SUCCESS,
    )


def _failed() -> object:
    """A different terminal decision: same candidate, different outcome."""

    return observation(
        test_status=CheckStatus.COMPLETED,
        test_conclusion=CheckConclusion.FAILURE,
        codeql_status=CheckStatus.COMPLETED,
        codeql_conclusion=CheckConclusion.SUCCESS,
    )


def _material_result(
    *,
    wake_binding=None,
    sample=None,
    max_samples: int = 1,
) -> CandidateCIContinuationResult:
    """One real material continuation through the existing H5 owners."""

    return wait_for_candidate_continuation(
        observation(),
        sample=sample if sample is not None else (lambda: _green()),
        wait=lambda: None,
        registry=CandidateWaiterRegistry(token_factory=lambda: MATERIAL_TOKEN),
        max_samples=max_samples,
        wake_binding=wake_binding if wake_binding is not None else binding(),
    )


def _quiescent_result() -> CandidateCIContinuationResult:
    """One real quiescent exhaustion through the existing H5 owners."""

    baseline = observation()
    return wait_for_candidate_continuation(
        baseline,
        sample=lambda: baseline,
        wait=lambda: None,
        registry=CandidateWaiterRegistry(token_factory=lambda: QUIESCENT_TOKEN),
        max_samples=1,
        wake_binding=binding(),
    )


def _wake_events(runtime: Runtime) -> list:
    return list(runtime.events.list_events(aggregate_type=WAKE_AGGREGATE_TYPE))


def test_quiescent_exhaustion_writes_nothing(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    result = _quiescent_result()
    assert result.wait_result.disposition is CandidateWaitDisposition.QUIESCENT_BUDGET_EXHAUSTED

    delivery = persist_candidate_continuation(runtime, result)

    assert delivery.disposition is CandidateCIContinuationDeliveryDisposition.QUIESCENT_NO_WRITE
    assert delivery.obligation_id is None
    assert delivery.inserted is False
    assert delivery.already_persisted is False
    assert delivery.persisted is None
    assert _wake_events(runtime) == []


def test_terminal_material_return_is_persisted_as_one_canonical_request(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    result = _material_result()
    assert result.material_return is True
    obligation = result.wake_obligation
    assert obligation is not None

    delivery = persist_candidate_continuation(runtime, result)

    assert delivery.disposition is CandidateCIContinuationDeliveryDisposition.MATERIAL_REQUESTED
    assert delivery.inserted is True
    assert delivery.already_persisted is False
    assert delivery.obligation_id == obligation.obligation_id
    assert delivery.command_id == obligation.obligation_id

    events = _wake_events(runtime)
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "WAKE_REQUESTED"
    assert event.aggregate_type == WAKE_AGGREGATE_TYPE
    assert event.aggregate_id == obligation.obligation_id
    assert event.command_id == obligation.obligation_id
    assert event.payload["obligation_id"] == obligation.obligation_id
    assert event.payload["source_ref"] == obligation.source_ref
    assert event.payload["declared_target_seat"] == "coo"
    assert event.payload["wake_kind"] == "ci_candidate_material"


def test_delivery_receipt_does_not_claim_dispatch_or_acceptance(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)

    delivery = persist_candidate_continuation(runtime, _material_result())

    assert delivery.start_issued is False
    assert delivery.wake_delivered is False
    assert delivery.worker_accepted is False
    assert delivery.parent_accepted is False
    assert delivery.schema == DELIVERY_SCHEMA


def test_duplicate_delivery_replays_the_same_canonical_request(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    result = _material_result()

    first = persist_candidate_continuation(runtime, result)
    second = persist_candidate_continuation(runtime, result)

    assert first.inserted is True
    assert second.inserted is False
    assert second.already_persisted is True
    assert second.disposition is (
        CandidateCIContinuationDeliveryDisposition.MATERIAL_ALREADY_PERSISTED
    )
    assert second.obligation_id == first.obligation_id
    assert second.command_id == first.command_id
    assert second.event_id == first.event_id
    assert len(_wake_events(runtime)) == 1


def test_same_canonical_decision_maps_to_the_same_canonical_obligation(tmp_path) -> None:
    """Two independently composed continuations of one decision are one row."""

    runtime = Runtime.at(tmp_path)
    first = _material_result()
    second = _material_result()
    assert first.wake_obligation is not None
    assert second.wake_obligation is not None
    assert first.wake_obligation.obligation_id == second.wake_obligation.obligation_id

    persist_candidate_continuation(runtime, first)
    delivery = persist_candidate_continuation(runtime, second)

    assert delivery.inserted is False
    assert delivery.obligation_id == first.wake_obligation.obligation_id
    assert len(_wake_events(runtime)) == 1


def test_reopened_runtime_reads_the_same_canonical_evidence(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    first = persist_candidate_continuation(runtime, _material_result())
    assert first.inserted is True

    reopened = Runtime.at(tmp_path)
    replay = persist_candidate_continuation(reopened, _material_result())

    assert replay.inserted is False
    assert replay.already_persisted is True
    assert replay.obligation_id == first.obligation_id
    assert replay.command_id == first.command_id
    assert replay.event_id == first.event_id
    events = _wake_events(reopened)
    assert len(events) == 1
    assert events[0].payload == first.persisted.event.payload
    assert events[0].created_at == first.persisted.event.created_at


def test_reopened_runtime_reads_the_same_row_through_the_ledger_owner(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    delivery = persist_candidate_continuation(runtime, _material_result())

    reopened = Runtime.at(tmp_path)
    found = WakeLedgerRepository(reopened).get_by_command_id(delivery.command_id)

    assert found is not None
    assert found.obligation is not None
    assert found.obligation.obligation_id == delivery.obligation_id
    assert found.event.event_id == delivery.event_id
    assert found.record.phase.value == "WAKE_REQUESTED"


def test_tampered_observer_decision_refuses_before_any_write(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    result = _material_result()
    decision = result.wait_result.decision
    assert decision is not None
    tampered = dataclasses.replace(
        result,
        wait_result=dataclasses.replace(
            result.wait_result,
            decision=dataclasses.replace(decision, canonical_digest="f" * 64),
        ),
    )

    with pytest.raises(CandidateCIContinuationDeliveryError, match="canonical digest"):
        persist_candidate_continuation(runtime, tampered)

    assert _wake_events(runtime) == []


def test_tampered_wake_obligation_refuses_before_any_write(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    result = _material_result()
    obligation = result.wake_obligation
    assert obligation is not None
    tampered = dataclasses.replace(
        result,
        wake_obligation=dataclasses.replace(
            obligation,
            declared_target_seat="ceo",
        ),
    )

    with pytest.raises(CandidateCIContinuationDeliveryError, match="COO-bound"):
        persist_candidate_continuation(runtime, tampered)

    assert _wake_events(runtime) == []


def test_obligation_projected_from_another_decision_refuses(tmp_path) -> None:
    """A well-formed obligation from a different decision is still refused."""

    runtime = Runtime.at(tmp_path)
    result = _material_result()
    foreign_result = _material_result(sample=lambda: _failed())
    obligation = result.wake_obligation
    foreign_obligation = foreign_result.wake_obligation
    assert obligation is not None
    assert foreign_obligation is not None
    assert foreign_obligation.source_ref != obligation.source_ref
    foreign = dataclasses.replace(result, wake_obligation=foreign_obligation)

    with pytest.raises(
        CandidateCIContinuationDeliveryError,
        match="not the original projection of the decision",
    ):
        persist_candidate_continuation(runtime, foreign)

    assert _wake_events(runtime) == []


def test_inconsistent_root_and_evidence_refs_refuses(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    result = _material_result()
    obligation = result.wake_obligation
    assert obligation is not None
    misrooted = dataclasses.replace(
        result,
        wake_obligation=dataclasses.replace(
            obligation,
            root_job_id="JOB-9999",
        ),
    )

    with pytest.raises(CandidateCIContinuationDeliveryError, match="evidence_refs"):
        persist_candidate_continuation(runtime, misrooted)

    assert _wake_events(runtime) == []


def test_inconsistent_quiescent_continuation_refuses(tmp_path) -> None:
    """A quiescent disposition that still carries wake evidence is refused."""

    runtime = Runtime.at(tmp_path)
    quiescent = _quiescent_result()
    material = _material_result()
    decision = material.wait_result.decision
    obligation = material.wake_obligation
    assert decision is not None
    assert obligation is not None
    inconsistent = dataclasses.replace(
        quiescent,
        wait_result=dataclasses.replace(quiescent.wait_result, decision=decision),
        wake_obligation=obligation,
    )

    with pytest.raises(
        CandidateCIContinuationDeliveryError,
        match="quiescent candidate continuation carries wake evidence",
    ):
        persist_candidate_continuation(runtime, inconsistent)

    assert _wake_events(runtime) == []


def test_quiescent_continuation_carrying_a_decision_refuses(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    material = _material_result()
    decision = material.wait_result.decision
    assert decision is not None
    quiescent = _quiescent_result()
    inconsistent = dataclasses.replace(
        quiescent,
        wait_result=dataclasses.replace(quiescent.wait_result, decision=decision),
    )

    with pytest.raises(CandidateCIContinuationDeliveryError, match="carries wake evidence"):
        persist_candidate_continuation(runtime, inconsistent)

    assert _wake_events(runtime) == []


def test_material_continuation_without_an_obligation_refuses(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    result = _material_result()
    stripped = dataclasses.replace(result, wake_obligation=None)

    with pytest.raises(CandidateCIContinuationDeliveryError, match="no exact wake obligation"):
        persist_candidate_continuation(runtime, stripped)

    assert _wake_events(runtime) == []


def test_wait_digest_that_does_not_match_the_decision_refuses(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    result = _material_result()
    mismatched = dataclasses.replace(
        result,
        wait_result=dataclasses.replace(
            result.wait_result,
            latest_observation_digest="b" * 64,
        ),
    )

    with pytest.raises(CandidateCIContinuationDeliveryError, match="latest observation digest"):
        persist_candidate_continuation(runtime, mismatched)

    assert _wake_events(runtime) == []


def test_observer_identity_that_does_not_match_the_wait_refuses(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    result = _material_result()
    mismatched = dataclasses.replace(
        result,
        wait_result=dataclasses.replace(
            result.wait_result,
            observer_id="github-ci-observer-" + "c" * 32,
        ),
    )

    with pytest.raises(CandidateCIContinuationDeliveryError, match="wait observer identity"):
        persist_candidate_continuation(runtime, mismatched)

    assert _wake_events(runtime) == []


def test_obligation_with_noncanonical_routing_case_refuses(tmp_path) -> None:
    """The canonical envelope rejects a routing value the codec would normalize."""

    runtime = Runtime.at(tmp_path)
    result = _material_result(
        wake_binding=dataclasses.replace(binding(), routing_workstream="prophet"),
    )
    obligation = result.wake_obligation
    assert obligation is not None
    assert obligation.workstream == "prophet"
    tampered = dataclasses.replace(
        result,
        wake_obligation=dataclasses.replace(obligation, workstream="PROPHET"),
    )

    with pytest.raises(
        CandidateCIContinuationDeliveryError,
        match="not the canonical projection",
    ):
        persist_candidate_continuation(runtime, tampered)

    assert _wake_events(runtime) == []


def test_non_candidate_continuation_result_refuses(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)

    with pytest.raises(
        CandidateCIContinuationDeliveryError,
        match="wrong exact type",
    ):
        persist_candidate_continuation(runtime, {"schema": "not-a-continuation"})

    assert _wake_events(runtime) == []


def test_non_canonical_result_schema_refuses(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    result = _material_result()
    tampered = dataclasses.replace(result, schema="mastermind.github_ci_candidate_continuation.v0")

    with pytest.raises(
        CandidateCIContinuationDeliveryError,
        match="result schema is not canonical",
    ):
        persist_candidate_continuation(runtime, tampered)

    assert _wake_events(runtime) == []


def test_non_canonical_wait_result_schema_refuses(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    result = _material_result()
    tampered = dataclasses.replace(
        result,
        wait_result=dataclasses.replace(
            result.wait_result,
            schema="mastermind.github_ci_candidate_waiter.v0",
        ),
    )

    with pytest.raises(
        CandidateCIContinuationDeliveryError,
        match="wait result schema is not canonical",
    ):
        persist_candidate_continuation(runtime, tampered)

    assert _wake_events(runtime) == []


def test_non_candidate_wait_result_refuses(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    result = _material_result()
    tampered = dataclasses.replace(result, wait_result="not-a-wait-result")

    with pytest.raises(
        CandidateCIContinuationDeliveryError,
        match="wait result has the wrong exact type",
    ):
        persist_candidate_continuation(runtime, tampered)

    assert _wake_events(runtime) == []


def test_material_continuation_that_does_not_wake_reasoning_refuses(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    result = _material_result()
    decision = result.wait_result.decision
    assert decision is not None
    tampered = dataclasses.replace(
        result,
        wait_result=dataclasses.replace(
            result.wait_result,
            decision=dataclasses.replace(decision, wake_reasoning=False),
        ),
    )

    with pytest.raises(
        CandidateCIContinuationDeliveryError,
        match="does not wake reasoning",
    ):
        persist_candidate_continuation(runtime, tampered)

    assert _wake_events(runtime) == []


def test_obligation_from_another_wake_source_refuses(tmp_path) -> None:
    """An inbox-sourced obligation cannot be persisted as a CI candidate wake."""

    runtime = Runtime.at(tmp_path)
    result = _material_result()
    inbox = mint_obligation(
        wake_kind=WakeKind.CI_CANDIDATE_MATERIAL,
        source_kind=SourceKind.EXECUTIVE_INBOX_ATTENTION,
        source_ref="eia-" + "a" * 12,
        declared_target_seat="coo",
        emitted_at="2026-10-05T09:00:00Z",
    )
    foreign = dataclasses.replace(result, wake_obligation=inbox)

    with pytest.raises(
        CandidateCIContinuationDeliveryError,
        match="not the candidate observation source",
    ):
        persist_candidate_continuation(runtime, foreign)

    assert _wake_events(runtime) == []


def test_obligation_with_another_wake_kind_refuses(tmp_path) -> None:
    """A CI candidate observation cannot carry an unrelated wake kind."""

    runtime = Runtime.at(tmp_path)
    result = _material_result()
    decision = result.wait_result.decision
    assert decision is not None
    other = mint_obligation(
        wake_kind=WakeKind.REVIEW_REQUIRED,
        source_kind=SourceKind.EXECUTIVE_RUNTIME_EVENT,
        source_ref="runtime:job:JOB-001:1",
        declared_target_seat="coo",
        job_id="JOB-001",
        root_job_id="JOB-001",
        emitted_at="2026-10-05T09:00:00Z",
    )
    foreign = dataclasses.replace(result, wake_obligation=other)

    with pytest.raises(
        CandidateCIContinuationDeliveryError,
        match="not the candidate material kind",
    ):
        persist_candidate_continuation(runtime, foreign)

    assert _wake_events(runtime) == []


def test_material_continuation_with_a_quiescent_decision_refuses(tmp_path) -> None:
    """A quiescent observer decision cannot be carried into a wake request."""

    runtime = Runtime.at(tmp_path)
    result = _material_result()
    decision = result.wait_result.decision
    assert decision is not None
    quiescent_decision = observe_candidate_transition(observation())
    assert quiescent_decision.disposition is CandidateObserverDisposition.QUIESCENT
    tampered = dataclasses.replace(
        result,
        wait_result=dataclasses.replace(
            result.wait_result,
            decision=quiescent_decision,
        ),
    )

    with pytest.raises(
        CandidateCIContinuationDeliveryError,
        match="quiescent observer decision cannot request a wake",
    ):
        persist_candidate_continuation(runtime, tampered)

    assert _wake_events(runtime) == []


def test_material_continuation_without_an_exact_decision_refuses(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    result = _material_result()
    tampered = dataclasses.replace(
        result,
        wait_result=dataclasses.replace(result.wait_result, decision="not-a-decision"),
    )

    with pytest.raises(
        CandidateCIContinuationDeliveryError,
        match="no exact observer decision",
    ):
        persist_candidate_continuation(runtime, tampered)

    assert _wake_events(runtime) == []


def test_non_canonical_wait_disposition_refuses(tmp_path) -> None:
    """A disposition string is not the canonical disposition member."""

    runtime = Runtime.at(tmp_path)
    result = _material_result()
    tampered = dataclasses.replace(
        result,
        wait_result=dataclasses.replace(
            result.wait_result,
            disposition="MATERIAL_RETURN",
        ),
    )

    with pytest.raises(
        CandidateCIContinuationDeliveryError,
        match="disposition is not a canonical disposition",
    ):
        persist_candidate_continuation(runtime, tampered)

    assert _wake_events(runtime) == []


def test_new_python_process_on_the_same_runtime_db_replays(tmp_path) -> None:
    """A separate interpreter on the same Runtime DB must not duplicate the row."""

    runtime = Runtime.at(tmp_path)
    first = persist_candidate_continuation(runtime, _material_result())
    assert first.inserted is True

    child = textwrap.dedent(
        f"""
        import json, sys
        sys.path.insert(0, {str(ROOT)!r})
        from control_plane.executive_runtime import Runtime
        from control_plane.github_ci_candidate_delivery import (
            persist_candidate_continuation,
        )
        from tests.test_github_ci_candidate_delivery import _material_result
        from control_plane.wake_ledger import WAKE_AGGREGATE_TYPE

        runtime = Runtime.at({str(tmp_path)!r})
        delivery = persist_candidate_continuation(runtime, _material_result())
        print(json.dumps({{
            "inserted": delivery.inserted,
            "obligation_id": delivery.obligation_id,
            "events": len(runtime.events.list_events(
                aggregate_type=WAKE_AGGREGATE_TYPE
            )),
        }}))
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", child],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(ROOT),
        timeout=300,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout.strip().splitlines()[-1])
    assert report["inserted"] is False
    assert report["obligation_id"] == first.obligation_id
    assert report["events"] == 1
    assert len(_wake_events(Runtime.at(tmp_path))) == 1


def test_unknown_write_effect_keeps_the_canonical_obligation_id(tmp_path, monkeypatch) -> None:
    """An unknown write outcome never resends under a different id."""

    runtime = Runtime.at(tmp_path)
    result = _material_result()
    obligation = result.wake_obligation
    assert obligation is not None

    def _explode(self, record, *, obligation=None, actor="wake_reconcile"):
        raise OSError("simulated indeterminate durable outcome")

    monkeypatch.setattr(WakeLedgerRepository, "append_record", _explode)

    with pytest.raises(CandidateCIContinuationDeliveryEffectUnknown) as caught:
        persist_candidate_continuation(runtime, result)

    assert caught.value.obligation_id == obligation.obligation_id
    assert _wake_events(runtime) == []


def test_delivery_module_owns_no_transport_dispatch_or_scheduler() -> None:
    module = ROOT / "control_plane" / "github_ci_candidate_delivery.py"
    tree = ast.parse(module.read_text(encoding="utf-8"))
    imported_roots = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots |= {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert imported_roots.isdisjoint(
        {
            "requests",
            "httpx",
            "urllib",
            "socket",
            "subprocess",
            "time",
            "asyncio",
            "mcp",
            "threading",
        }
    )
    source = module.read_text(encoding="utf-8")
    for forbidden in (
        "dispatch_wake(",
        "deliver(",
        "create_job(",
        "merge(",
        "deploy(",
        "rerun(",
        "urlopen(",
        "gh api",
        "CREATE TABLE",
        "create_task(",
        "Timer(",
    ):
        assert forbidden not in source


def test_delivery_module_imports_no_second_lifecycle_owner() -> None:
    """The join composes existing owners; it does not create a new one."""

    module = ROOT / "control_plane" / "github_ci_candidate_delivery.py"
    tree = ast.parse(module.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "control_plane.wake_ledger" in imported
    assert "control_plane.wake_persist" in imported
    assert "control_plane.wake_events" in imported
    for forbidden in (
        "control_plane.wake_dispatcher",
        "control_plane.wake_router",
        "control_plane.wake_transport",
        "control_plane.wake_reconcile",
        "control_plane.session_targets",
    ):
        assert forbidden not in imported


def test_delivery_test_is_in_existing_ci_gate() -> None:
    from scripts.ci_pytest import resolve_gate

    gate = resolve_gate(ROOT)
    assert "tests/test_github_ci_candidate_delivery.py" in gate["included"]


def test_pure_record_failure_is_not_an_unknown_write(tmp_path, monkeypatch) -> None:
    from control_plane import github_ci_candidate_delivery as delivery_module
    from control_plane.wake_ledger import WakeLedgerError

    runtime = Runtime.at(tmp_path)

    def refuse_record(obligation):
        raise WakeLedgerError("invalid record before persistence")

    monkeypatch.setattr(delivery_module, "requested_record", refuse_record)
    with pytest.raises(CandidateCIContinuationDeliveryError, match="before write"):
        persist_candidate_continuation(runtime, _material_result())
    assert _wake_events(runtime) == []


def test_committed_write_then_response_loss_reconciles_same_obligation(tmp_path, monkeypatch) -> None:
    runtime = Runtime.at(tmp_path)
    result = _material_result()
    obligation = result.wake_obligation
    assert obligation is not None
    original_append = WakeLedgerRepository.append_record

    def commit_then_lose_response(self, record, *, obligation=None, actor="wake_reconcile"):
        original_append(self, record, obligation=obligation, actor=actor)
        raise OSError("simulated response loss after durable commit")

    monkeypatch.setattr(WakeLedgerRepository, "append_record", commit_then_lose_response)
    with pytest.raises(CandidateCIContinuationDeliveryEffectUnknown) as caught:
        persist_candidate_continuation(runtime, result)
    assert caught.value.obligation_id == obligation.obligation_id

    # Reconcile by canonical read after reopening before any same-id replay.
    reopened = Runtime.at(tmp_path)
    evidence = WakeLedgerRepository(reopened).get_by_command_id(obligation.obligation_id)
    assert evidence is not None
    assert evidence.obligation == obligation
    assert len(_wake_events(reopened)) == 1

    monkeypatch.setattr(WakeLedgerRepository, "append_record", original_append)
    repeated = persist_candidate_continuation(reopened, result)
    assert repeated.inserted is False
    assert repeated.event_id == evidence.event.event_id
    assert len(_wake_events(Runtime.at(tmp_path))) == 1


def test_coherent_changed_correlation_conflicts_with_existing_request(tmp_path) -> None:
    original = _material_result()
    alternate = _material_result(wake_binding=dataclasses.replace(binding(), root_job_id="JOB-9999"))
    assert original.wake_obligation.obligation_id == alternate.wake_obligation.obligation_id
    runtime = Runtime.at(tmp_path / "original")
    first = persist_candidate_continuation(runtime, original)

    with pytest.raises(CandidateCIContinuationDeliveryError, match="command_id collision"):
        persist_candidate_continuation(runtime, alternate)
    records = _wake_events(runtime)
    assert len(records) == 1
    assert records[0].event_id == first.event_id
    assert records[0].payload["root_job_id"] == original.wake_obligation.root_job_id

    # A fresh ledger accepts a coherent binding from its trusted caller. This
    # demonstrates projection validation, not authentication or admission.
    alternate_delivery = persist_candidate_continuation(Runtime.at(tmp_path / "other"), alternate)
    assert alternate_delivery.inserted is True
    assert alternate_delivery.start_issued is False
    assert alternate_delivery.worker_accepted is False


def test_timestamp_replay_preserves_first_canonical_evidence(tmp_path) -> None:
    original = _material_result()
    later = _material_result(wake_binding=dataclasses.replace(
        binding(), emitted_at="2026-11-05T06:00:00Z"))
    runtime = Runtime.at(tmp_path)
    first = persist_candidate_continuation(runtime, original)
    repeated = persist_candidate_continuation(runtime, later)
    assert repeated.inserted is False
    assert repeated.event_id == first.event_id
    assert repeated.persisted.obligation.emitted_at == original.wake_obligation.emitted_at
    assert len(_wake_events(runtime)) == 1
