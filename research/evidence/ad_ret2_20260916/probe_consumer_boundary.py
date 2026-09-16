"""Opt-in capability falsifier for the READ-ONLY current supervisor.

Inject a synthetic, closed native-boundary observation and explicitly opt the
caller into the built Phase-A return. The current terminal-only supervisor still
stops the worker and abandons its epoch while the Job remains RUNNING. This probe is expected RED until the authorized consumer join is
implemented; do not alter the terminal result validator to make it pass.
"""
from dataclasses import replace
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(Path(__file__).parent))
from probe_turn_boundary import completed_turn, no_internet
from test_executive_operator_supervisor import _ActiveAdapter
from test_slack_agent_dialogue_turn_watcher import _body
from control_plane.executive_runtime import Runtime, JobStatus
from control_plane.operator_harness_contract import NormalizedEvent
from control_plane.operator_harness_orchestrator import OperatorHarnessOrchestrator


@pytest.mark.parametrize("kind", ["BLOCKED", "DECISION_REQUEST"])
def test_actual_supervisor_must_preserve_accepted_yield(tmp_path, monkeypatch, kind):
    original = OperatorHarnessOrchestrator.run_turn
    def capable(self, *args, **kwargs):
        return original(self, *args, **{**kwargs, "allow_semantic_yield": True})
    monkeypatch.setattr(OperatorHarnessOrchestrator, "run_turn", capable)
    def native_boundary(self, cursor, *, timeout_seconds):
        material = NormalizedEvent(attempt_id=cursor.attempt_id,
            session_epoch_id=cursor.session_epoch_id,
            process_generation_id=cursor.process_generation_id, turn_id=cursor.turn_id,
            kind=kind, provider_event_id="fixture-material-boundary",
            payload_redacted={"body": _body(kind), "source_event_time_ms": None,
                              "replaces_event_id": None})
        end = replace(material, kind="turn/completed", provider_event_id="fixture-end",
                      payload_redacted={"method": "turn/completed"})
        return (material, end), replace(cursor, local_sequence=2)
    monkeypatch.setattr(_ActiveAdapter, "read_events", native_boundary)
    job, adapters, error = completed_turn(tmp_path, kind)
    runtime = Runtime.at(tmp_path / "runtime")
    rows = runtime.events.list_events(job_id=job.job_id)
    yields = [e for e in rows if e.event_type == "OHF_SEMANTIC_YIELD_OBSERVED"]
    assert len(yields) == 1, "Phase A must succeed before this consumer falsifier is valid"
    assert yields[0].payload["root_job_id"]
    assert job.status in {JobStatus.RUNNING, JobStatus.CHECKPOINTED}, (
        "PHASE_B_SCOPE_REQUIRED: current supervisor terminalizes even after durable yield; "
        + str(error))
    assert sum(a.stop_calls for a in adapters) == 0
