"""Runtime-owned retained capacity acquisition and safe Workspace composition.

The fixed authenticated frame owner must qualify selected-root membership and
permission before and after this read, then require a finalized SAME receipt.
This module never acquires a host, provider, credential or live capacity source.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any


MAX_RESPONSE_BYTES = 16_384
MAX_EVENT_BYTES = 65_536


@dataclasses.dataclass(frozen=True)
class RetainedCapacitySnapshot:
    root_metadata: Any
    job: Any
    attempt: Any
    claim_event: Any
    begin_event: Any
    observation_source_identity: str = ""


def acquire_retained_capacity(acquisition, vm_guard, *, root_job_id, job_id, attempt_id):
    """Implementation of one Runtime observation selection, not an HTTP reader."""
    from control_plane.executive_runtime import (
        RuntimeReadUnavailable, RuntimeRoleResultOverBudget, _BoundedRoleResultLoader,
        _bounded_acquisition_identifier, _bounded_strict_root_metadata,
        _job_from_row, _attempt_from_row, _event_from_row,
    )
    root_id = _bounded_acquisition_identifier(root_job_id, name="root")
    job_id = _bounded_acquisition_identifier(job_id, name="job")
    attempt_id = _bounded_acquisition_identifier(attempt_id, name="attempt")
    acquisition._require_open()
    loader = _BoundedRoleResultLoader(acquisition._connection)
    vm_guard.activate()
    try:
        root = loader.execute("SELECT * FROM jobs WHERE job_id=?", (root_id,)).fetchone()
        metadata = _bounded_strict_root_metadata(loader, root, root_id)
        if metadata.work_ref is None:
            raise RuntimeReadUnavailable("retained capacity root unavailable")
        job = loader.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if (job is None or job["root_job_id"] != root_id or job["orchestration_role"] != "work"
                or job["current_attempt_id"] != attempt_id):
            raise RuntimeReadUnavailable("retained capacity Job unavailable")
        # Authenticate the entire original lineage in the same bounded snapshot.
        ancestor, seen = job, set()
        for _ in range(16):
            token = ancestor["job_id"]
            if token in seen or ancestor["root_job_id"] != root_id:
                raise RuntimeReadUnavailable("retained capacity lineage invalid")
            seen.add(token)
            if token == root_id:
                if ancestor["parent_job_id"] is not None:
                    raise RuntimeReadUnavailable("retained capacity lineage invalid")
                break
            if ancestor["parent_job_id"] is None:
                raise RuntimeReadUnavailable("retained capacity lineage invalid")
            ancestor = loader.execute("SELECT * FROM jobs WHERE job_id=?", (ancestor["parent_job_id"],)).fetchone()
            if ancestor is None:
                raise RuntimeReadUnavailable("retained capacity lineage invalid")
        else:
            raise RuntimeReadUnavailable("retained capacity lineage over budget")
        attempt = loader.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
        if (attempt is None or attempt["job_id"] != job_id
                or job["assigned_worker_id"] != attempt["worker_id"]
                or job["assigned_quota_class"] != attempt["quota_class"]
                or int(attempt["attempt_number"]) != 1):
            raise RuntimeReadUnavailable("retained capacity Attempt unavailable")
        meta = loader.execute(
            "SELECT event_id,aggregate_type,aggregate_id,command_id,worker_id,quota_class,length(CAST(payload_json AS BLOB)) AS bytes FROM events "
            "WHERE job_id=? AND attempt_id=? AND event_type='JOB_CLAIMED' ORDER BY event_id LIMIT 2",
            (job_id, attempt_id),
        ).fetchall()
        if len(meta) != 1:
            raise RuntimeReadUnavailable("retained capacity claim unavailable")
        claim_command = f"coo-cycle:{root_id}:dispatch:{job_id}:attempt:1"
        if (meta[0]["aggregate_type"] != "job" or meta[0]["aggregate_id"] != job_id
                or meta[0]["command_id"] != claim_command
                or meta[0]["worker_id"] != attempt["worker_id"] or meta[0]["quota_class"] != attempt["quota_class"]):
            raise RuntimeReadUnavailable("retained capacity claim identity invalid")
        if meta[0]["bytes"] > MAX_EVENT_BYTES:
            raise RuntimeRoleResultOverBudget()
        claim = loader.execute("SELECT * FROM events WHERE event_id=?", (meta[0]["event_id"],)).fetchone()
        payload = json.loads(claim["payload_json"])
        evidence = payload.get("capacity_evidence")
        if not isinstance(evidence, dict) or evidence.get("schema") != "mastermind.finite_initial_claim/v1":
            raise RuntimeReadUnavailable("retained capacity evidence unavailable")
        physical = evidence.get("physical_capacity")
        begin_id = physical.get("begin_event_id") if isinstance(physical, dict) else None
        if type(begin_id) is not int or begin_id < 1:
            raise RuntimeReadUnavailable("retained capacity BEGIN unavailable")
        meta = loader.execute("SELECT event_type,aggregate_type,aggregate_id,command_id,length(CAST(payload_json AS BLOB)) AS bytes FROM events WHERE event_id=?", (begin_id,)).fetchone()
        if meta is None:
            raise RuntimeReadUnavailable("retained capacity BEGIN unavailable")
        expected_aggregate = hashlib.sha256(json.dumps([physical.get("host_ref"), f"finite-initial:{job_id}"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if (meta["event_type"] != "PHYSICAL_RESOURCE_BEGIN" or meta["aggregate_type"] != "physical_resource_operation"
                or meta["aggregate_id"] != expected_aggregate or meta["command_id"] != f"physical:{claim_command}:begin"):
            raise RuntimeReadUnavailable("retained capacity BEGIN identity invalid")
        if meta["bytes"] > MAX_EVENT_BYTES:
            raise RuntimeRoleResultOverBudget()
        begin = loader.execute("SELECT * FROM events WHERE event_id=?", (begin_id,)).fetchone()
        return RetainedCapacitySnapshot(metadata, _job_from_row(job), _attempt_from_row(attempt), _event_from_row(claim), _event_from_row(begin))
    finally:
        vm_guard.deactivate()

