"""Completed native turn != completed company responsibility.

The nonterminal JSON below is a PROPOSED fixture wire, not an accepted Runtime
schema. Current rejection is expected. The capability falsifier must not be
made GREEN by loosening the protected terminal role-result validator.
"""
from __future__ import annotations

import asyncio
import json
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests"))
from test_executive_operator_supervisor import (
    _seed_dispatchable_operator_planner, _ActiveAdapter, _PromptSource,
)
from test_slack_agent_dialogue_turn_watcher import _pending_msg
from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
from control_plane.executive_orchestration_result import canonical_bytes
from control_plane.executive_runtime import JobStatus


@pytest.fixture(autouse=True)
def no_internet(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("Network forbidden in packet05 source probe")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)


def completed_turn(tmp_path, kind):
    runtime, root, planner = _seed_dispatchable_operator_planner(tmp_path)
    adapters = []

    class BoundAdapter(_ActiveAdapter):
        def _canonical_result(self, turn):
            if kind == "RESULT":
                return super()._canonical_result(turn)
            body = _pending_msg(kind, 1)["body"]
            return canonical_bytes({
                "schema_version": "mastermind.operator_semantic_return/proposed-v1",
                "kind": kind, "body": body,
            }).decode("utf-8")

    def factory(loader):
        adapter = BoundAdapter(runtime, loader, cancel_during_collect=False)
        adapters.append(adapter)
        return adapter

    supervisor = ExecutiveOperatorSupervisor(runtime, adapter_factory=factory,
        prompt_source=_PromptSource())
    error = None
    try:
        asyncio.run(supervisor.start_cycle_job(planner.job_id,
            command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1"))
    except Exception as exc:
        error = type(exc).__name__
    job = runtime.jobs.get_job(planner.job_id)
    events = runtime.events.list_events(job_id=planner.job_id)
    print(json.dumps({"fixture_only": True, "proposed_wire": kind != "RESULT",
        "kind": kind, "job_status": job.status.value, "error": error,
        "adapter_count": len(adapters), "stop_calls": sum(a.stop_calls for a in adapters),
        "begin_turn_calls": sum(a.begin_turn_calls for a in adapters),
        "event_types": [e.event_type for e in events]}, sort_keys=True))
    return job, adapters, error


@pytest.mark.parametrize("kind", ["BLOCKED", "DECISION_REQUEST"])
def test_capability_completed_native_turn_can_yield_without_attempt_failure(tmp_path, kind):
    job, adapters, error = completed_turn(tmp_path, kind)
    assert job.status in {JobStatus.RUNNING, JobStatus.CHECKPOINTED}, (
        "NONTERMINAL_CONSUMER_NOT_BUILT: completed native turn follows failure cleanup; " + str(error))
    assert sum(a.stop_calls for a in adapters) == 0


def test_control_existing_terminal_result_is_unchanged(tmp_path):
    job, adapters, error = completed_turn(tmp_path, "RESULT")
    assert error is None
    assert job.status is JobStatus.COMPLETED
    assert len(adapters) == 1 and adapters[0].stop_calls == 1
