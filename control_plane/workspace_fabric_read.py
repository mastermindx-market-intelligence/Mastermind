"""Authenticated, bounded projection of original canonical-paid native runs.

This composes existing owners. It neither discovers arbitrary local paths nor
turns a generic Workspace login, workstream label or run ID into Fabric access.
Every remote read requires a current COO principal/root join, the immutable
Runtime original launch and the same installed paid physical owner.
"""
from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime, timezone

from common import executive_workspace_fabric_contract as wire
from common.executive_workspace_contract import canonical, digest, error, permission_stamp
from control_plane.executive_paid_fabric_composition import PaidBindingSource
from control_plane.executive_paid_fabric_adapter import PaidFabricHostBinding
from control_plane.executive_fabric_bridge_broker import start_request_sha256
from control_plane.workspace_paid_fabric_runtime import BoundedPaidFabricSnapshot, PaidFabricRootNotBound
from control_plane.workspace_owned_task import await_owned

MAX_ROOTS = 4
MAX_MEMBERSHIPS = 64
READ_SECONDS = 8


def _source_identity(snapshot):
    from control_plane.workspace_read_service import _plan_validity_identity
    return (snapshot.instance, snapshot.publication, digest(snapshot.document),
        digest(_plan_validity_identity(snapshot.validity)), digest(snapshot.currentness))


def _roots(service, frame, installed_source):
    from control_plane.workspace_read_service import _qualified, _join
    before = service.cache.snapshot()
    rows = before.document.get("autonomy", {}).get("responsibilities")
    if type(rows) is not list:
        raise ValueError("source_unavailable")
    selected = frame["selection"]
    if selected is not None:
        rows = [row for row in rows if type(row) is dict and row.get("root_job_id") == selected["root_id"]]
        if len(rows) != 1:
            raise PermissionError("access_denied")
    limited = len(rows) > MAX_MEMBERSHIPS
    admitted = []
    for row in rows[:MAX_MEMBERSHIPS]:
        if type(row) is not dict:
            raise ValueError("source_unavailable")
        selection = {"work_ref": row.get("responsibility_ref"), "root_job_id": row.get("root_job_id")}
        try:
            _join(before.document, selection)
            if not _qualified(before, selection):
                continue
            marker = service._activity_membership_marker(frame["principal"], selection,
                original_owner=installed_source.for_workspace_read_principal)
        except (PermissionError, LookupError):
            continue
        admitted.append((selection, marker))
        if len(admitted) == MAX_ROOTS:
            limited = limited or len(rows) > MAX_ROOTS
            break
    if not admitted:
        raise PermissionError("access_denied")
    return before, tuple(admitted), limited


def _runtime_snapshots(service, memberships):
    from control_plane.executive_runtime import RuntimeReadObservationReceipt
    bounded = service._bounded_runtime(service.runtime) if service._bounded_runtime else service.runtime
    result = []
    for selection, marker in memberships:
        with bounded.observe_bounded_read() as observation:
            try:
                snapshot = observation.read_paid_fabric_runs_bounded(selection["root_job_id"],
                    work_ref=selection["work_ref"], principal_binding_digest=marker[1],
                    authority_generation_digest=marker[2], mission_authority_ref=marker[3])
            except PaidFabricRootNotBound as unbound:
                # A proved ordinary CEO root is an explicit omission, never a
                # browser authority. Catch inside the bracket so physical close
                # can qualify its exact immutable creation observation below.
                snapshot = unbound
        receipt = observation.receipt
        if (type(snapshot) not in (BoundedPaidFabricSnapshot, PaidFabricRootNotBound)
                or type(receipt) is not RuntimeReadObservationReceipt
                or receipt.schema != "mastermind.runtime_read_observation.v1"
                or receipt.state != "SAME" or type(receipt.before) is not int
                or receipt.before < 0 or receipt.before != receipt.after
                or type(receipt.source_identity) is not str
                or snapshot.observation_source_identity != receipt.source_identity
                or snapshot.root_job_id != selection["root_job_id"]):
            raise ValueError("source_unavailable")
        result.append(snapshot)
    return tuple(result)


def _runtime_identity(snapshots):
    # Request-scoped observation IDs intentionally differ between the two
    # closed reads. Compare their actual bounded source/evidence digests.
    return tuple((row.root_job_id, row.snapshot_digest) for row in snapshots)


def _current(service, frame, installed_source, paid_source, permission, before, memberships):
    from control_plane.workspace_read_service import _qualified, _join
    principal = frame["principal"]
    if (service.authorize(principal) is not True
            or permission_stamp(service.authorize, principal) != permission):
        raise PermissionError("access_denied")
    after = service.cache.snapshot()
    if before.owner is not after.owner or _source_identity(after) != _source_identity(before):
        raise ValueError("source_unavailable")
    for selection, marker in memberships:
        _join(after.document, selection)
        if not _qualified(after, selection):
            raise ValueError("source_unavailable")
        if service._activity_membership_marker(principal, selection,
                original_owner=installed_source.for_workspace_read_principal) != marker:
            raise PermissionError("access_denied")
    paid_source._current()


async def _status(paid_source, reference):
    physical = PaidFabricHostBinding(**reference.physical_binding)
    # This is the original installed source; a successor with the same display
    # labels does not acquire the old physical run, nor may HTTP select it.
    if dataclasses.asdict(paid_source(physical.host_ref, physical.worker_id)) != reference.physical_binding:
        raise ValueError("source_unavailable")
    source = paid_source.source_for(physical)
    if source != reference.launch_request["paid_source_config"]:
        raise ValueError("source_unavailable")
    payload = {"binding": reference.launch_request["binding"], "run_id": reference.run_id,
        "physical_binding_sha256": reference.physical_binding_sha256,
        "start_request_sha256": start_request_sha256(reference.launch_request),
        "process_ref_sha256": reference.process_ref_sha256,
        "parent_run_id": reference.parent_run_id}
    client = paid_source.client_for(physical, payload)
    reply = await client.request("native-fabric-status", payload, timeout_seconds=READ_SECONDS)
    # WorkerBrokerClient returns the checked result, not the wire envelope.
    if (type(reply) is not dict
            or set(reply) != {"adapter_id", "binding", "physical_binding_sha256", "request_sha256",
                "process_ref_sha256", "status"}
            or reply["adapter_id"] != "canonical-paid-fabric"
            or reply["binding"] != payload["binding"]
            or reply["physical_binding_sha256"] != payload["physical_binding_sha256"]
            or reply["request_sha256"] != payload["start_request_sha256"]
            or reply["process_ref_sha256"] != payload["process_ref_sha256"]):
        raise ValueError("source_unavailable")
    if paid_source.source_for(physical) != source:
        raise ValueError("source_unavailable")
    return wire.status_metadata(reply["status"], run_id=reference.run_id,
                                root_id=reference.root_id, parent_run_id=reference.parent_run_id)


async def handle_fabric_frame(service, frame, installed_source, paid_source):
    from ops.executive_os.coo_principal_host import CooInstalledSource
    try:
        wire.validate_frame(frame)
    except (TypeError, ValueError):
        return error("invalid_input", 400)
    if type(installed_source) is not CooInstalledSource or type(paid_source) is not PaidBindingSource:
        return error("access_denied", 403)
    try:
        authorizer = service.authorize
        if authorizer(frame["principal"]) is not True:
            raise PermissionError("access_denied")
        permission = permission_stamp(authorizer, frame["principal"])
        if permission is None:
            raise PermissionError("access_denied")
        paid_source._current()
        before, memberships, limited = _roots(service, frame, installed_source)
        snapshots = await await_owned(asyncio.create_task(asyncio.to_thread(
            _runtime_snapshots, service, memberships)))
        _current(service, frame, installed_source, paid_source, permission, before, memberships)
        references = tuple(run for snapshot in snapshots
            if type(snapshot) is BoundedPaidFabricSnapshot for run in snapshot.runs)
        if len(references) > wire.MAX_ROWS or len({r.run_id for r in references}) != len(references):
            raise ValueError("source_unavailable")
        if frame["selection"] is not None:
            references = tuple(run for run in references
                if run.root_id == frame["selection"]["root_id"] and run.run_id == frame["selection"]["run_id"])
            if len(references) != 1:
                raise PermissionError("access_denied")
        # Concurrency is bounded by original installed hosts (at most three)
        # and the total read has the existing finite Workspace transport bound.
        semaphore = asyncio.Semaphore(3)
        async def read(run):
            async with semaphore:
                _current(service, frame, installed_source, paid_source, permission, before, memberships)
                try:
                    value = await _status(paid_source, run)
                    return {"run_id": run.run_id, "controller_modified_at": None,
                            "status": value, "reason_code": None}
                except (ValueError, OSError, RuntimeError):
                    return {"run_id": run.run_id, "controller_modified_at": None,
                            "status": None, "reason_code": "STATUS_UNAVAILABLE"}
        async with asyncio.timeout(READ_SECONDS):
            items = await asyncio.gather(*(read(run) for run in references))
        after_runtime = await await_owned(asyncio.create_task(asyncio.to_thread(
            _runtime_snapshots, service, memberships)))
        if _runtime_identity(after_runtime) != _runtime_identity(snapshots):
            raise ValueError("source_unavailable")
        _current(service, frame, installed_source, paid_source, permission, before, memberships)
        if service.authorize is not authorizer:
            raise PermissionError("access_denied")
        if frame["operation"] == wire.STATUS_OPERATION:
            if items[0]["status"] is None:
                raise ValueError("source_unavailable")
            result = items[0]["status"]
        else:
            complete = all(item["status"] is not None for item in items)
            reasons = ["ROWS_OMITTED"]
            if limited or any(snapshot.truncated for snapshot in snapshots
                              if type(snapshot) is BoundedPaidFabricSnapshot):
                reasons.append("SCAN_LIMIT")
            if not complete:
                reasons.append("STATUS_PARTIAL")
            result = wire.validate_catalog({"schema": wire.CATALOG_SCHEMA, "availability": "PARTIAL",
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "source": {"owner": "ATTENDED_FABRIC", "observation_kind": "CONTROLLER_STATUS_SNAPSHOT",
                    "revision": digest({"runtime": _runtime_identity(snapshots), "items": items}),
                    "scope": "EXACT_RUN_SET", "atomic": False, "time_basis": "LOCAL_READ"},
                # These are global native counts, which this exact paid subset
                # cannot establish. Never report unbound/manual/finite as idle.
                "coverage": {"returned_count": len(items), "candidate_count": None,
                    "omitted_count": None, "scan_complete": False, "status_complete": complete},
                "items": items, "reason_codes": reasons})
        if len(canonical({"ok": True, "result": result})) + 1 > wire.ceiling(frame["operation"]):
            raise ValueError("source_unavailable")
        return {"ok": True, "result": result}
    except PermissionError:
        return error("access_denied", 403)
    except Exception:
        return error("source_unavailable", 503)
