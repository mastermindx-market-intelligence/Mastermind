"""Classify the actual ACK owner's read/physical-write boundary.

The Runtime claim and sealed completion are real. The service is constructed
without opening a socket; its actual physical worker performs the ACK event.
No arbitrary Runtime exception is treated as proof of a rolled-back write.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses

import pytest

from control_plane.executive_runtime import StateConflict
from control_plane.executive_service import ExecutiveControlService
from integrations.hermes_delegate.executive import (
    ExecutiveChildSelection, ExecutiveSelectedChild, ExecutiveSelectedChildComposition,
)
from tests.test_coo_requester_return import _fixture, _claim, _finish, _request, _events
from tests.test_executive_service import _config


@pytest.mark.parametrize("boundary,expected,physical_entries,receipt_count", [
    ("normal", "COMPLETED", 1, 1),
    ("foreign_job", "REFUSED", 0, 0),
    ("changed_digest", "REFUSED", 0, 0),
    ("closing", "REFUSED", 0, 0),
    ("guard_revoked", "REFUSED", 0, 0),
    ("status_refused", "REFUSED", 0, 0),
    ("status_unavailable", "UNAVAILABLE", 0, 0),
    ("runtime_guard_revoked", "EFFECT_UNKNOWN", 1, 0),
    ("runtime_exception", "EFFECT_UNKNOWN", 1, 0),
    ("response_lost", "EFFECT_UNKNOWN", 1, 1),
    ("post_write_currentness", "EFFECT_UNKNOWN", 1, 1),
    ("post_write_read", "EFFECT_UNKNOWN", 1, 1),
    ("post_write_malformed", "EFFECT_UNKNOWN", 1, 1),
])
def test_ack_owner_classifies_only_proven_pre_effect_failure(
    tmp_path, monkeypatch, boundary, expected, physical_entries, receipt_count,
):
    f = _fixture(tmp_path)
    _finish(f, _claim(f))
    request = _request(f)
    service = ExecutiveControlService(_config(tmp_path))
    service.runtime = f.runtime
    entered = []
    physical = service._run_physical

    async def record_physical(function, *args, **kwargs):
        entered.append(function)
        return await physical(function, *args, **kwargs)

    monkeypatch.setattr(service, "_run_physical", record_physical)
    status = service.selected_child_status

    async def checked_status(**kwargs):
        if boundary == "status_refused":
            raise StateConflict("original status refused before write")
        if boundary == "status_unavailable" or (boundary == "post_write_read" and _events(f)):
            raise OSError("original status read unavailable")
        return await status(**kwargs)

    monkeypatch.setattr(service, "selected_child_status", checked_status)

    def current():
        if (boundary == "guard_revoked"
                or (boundary == "runtime_guard_revoked" and entered)
                or (boundary == "post_write_currentness" and _events(f))):
            raise StateConflict("original authority is no longer current")

    acknowledge = f.runtime.acknowledge_coo_selected_child_result

    def runtime_ack(runtime, *args, **kwargs):
        assert runtime is f.runtime
        if boundary == "runtime_exception":
            raise StateConflict("arbitrary exception after physical Runtime entry")
        descriptor = acknowledge(*args, **kwargs)
        if boundary == "response_lost":
            raise OSError("original reply lost after event committed")
        if boundary == "post_write_malformed":
            descriptor = copy.deepcopy(descriptor)
            descriptor["terminal_evidence_digest"] = "f" * 64
        return descriptor

    monkeypatch.setattr(type(f.runtime), "acknowledge_coo_selected_child_result", runtime_ack)
    if boundary == "closing":
        service._closing = True
    elif boundary == "foreign_job":
        request["result"]["job_id"] = "JOB-999"
    elif boundary == "changed_digest":
        request["result"]["result_envelope_digest"] = "f" * 64

    async def exercise():
        selection = dataclasses.asdict(f.selection)
        selection.pop("attempt_ordinal")
        selection.pop("command_id")
        composition = ExecutiveSelectedChildComposition(
            service=service, runtime=f.runtime,
            children=(ExecutiveSelectedChild(ExecutiveChildSelection(**selection), 1),),
            loop=asyncio.get_running_loop(), context=f.context,
            capability_profile_digest=f.capability, requester_acknowledgment_guard=current,
        )
        result = await composition.acknowledge_result_async(request)
        assert result["state"] == expected, result
        assert result["command_id"] == f.command
        assert result["job_id"] == f.child.job_id
        assert len(entered) == physical_entries
        assert len(_events(f)) == receipt_count
        if expected != "COMPLETED":
            assert "requester_return" not in result
        # A lost/malformed/post-write answer is reconciled by an original
        # guarded read, never another ACK call. The completed child remains
        # the same canonical Job/Attempt throughout every refusal.
        original = f.runtime.coo_selected_child_requester_return(
            job_id=f.child.job_id, command_id=f.command, context=f.context,
            capability_profile_digest=f.capability, currentness_guard=lambda: None,
        )
        assert (original["consumption"] is not None) is bool(receipt_count)
        assert f.runtime.jobs.get_job(f.child.job_id).attempt_count == 1
        assert not service._physical_workers

    asyncio.run(exercise())
