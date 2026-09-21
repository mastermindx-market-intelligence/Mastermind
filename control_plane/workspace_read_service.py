"""Read composition owned by the existing control service, never the public App.

The caller supplies the existing live ControlRoom ServerConfig owner and Runtime.
This module neither constructs either owner nor starts a cache refresh. The
private bracket is request scoped, and is not an installation/currentness registry.
"""
from __future__ import annotations

import asyncio
import copy
import math
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from integrations.mastermind_workspace_app.contract import (
    MAX_RESPONSE_BYTES, OBSERVATION_SCHEMA, PROGRAMS_SCHEMA, canonical, digest,
    error, validate_frame, bounded_canonical, permission_stamp,
)


@dataclass(frozen=True)
class _Snapshot:
    owner: Any
    instance: str
    publication: int
    document: dict
    validity: dict
    currentness: dict


class ExistingControlRoomCache:
    """A view of one already-running canonical ServerConfig, not a new cache.

    The resolver must return the actual owner instance, and must change when
    that owner restarts. The opaque token lives on that instance under its own
    state lock. It is never based on id(), a path, an inode or caller input.
    """

    def __init__(self, owner: Callable[[], Any], *, monotonic=time.monotonic):
        self._owner = owner
        self._monotonic = monotonic

    def snapshot(self) -> _Snapshot:
        from scripts.chairman_control_room import (
            ServerConfig, _sample_source_clock, _source_validity_snapshot,
        )
        owner = self._owner()
        if not isinstance(owner, ServerConfig):
            raise ValueError("source_unavailable")
        with owner.state_lock:
            seq = owner.state_published_seq
            doc = owner.state_cache.get("doc")
            stamp = owner.state_cache.get("composed_monotonic")
            now = self._monotonic()
            ttl = owner.state_ttl
            if (type(seq) is not int or seq <= 0 or type(doc) is not dict
                    or doc.get("schema") != "mastermind.chairman_control_room.v1"
                    or type(stamp) not in (int, float) or not math.isfinite(stamp)
                    or type(now) not in (int, float) or not math.isfinite(now)
                    or type(ttl) not in (int, float) or not math.isfinite(ttl)
                    or ttl <= 0 or not 0 <= now - stamp <= ttl
                    or owner.state_refresh_error is not None or getattr(owner, "state_stopping", False)):
                raise ValueError("source_unavailable")
            instance = getattr(owner, "_workspace_read_instance", None)
            if instance is None:
                instance = secrets.token_hex(32)
                setattr(owner, "_workspace_read_instance", instance)
            validity = _source_validity_snapshot(owner, _sample_source_clock(owner))
            snapshot = _Snapshot(owner, instance, seq, copy.deepcopy(doc),
                                 copy.deepcopy(validity), {"state": "fresh", "publication_seq": seq})
        # Neither truncation nor falling back to an empty Programs list is legal.
        bounded_canonical(snapshot.document)
        return snapshot


def _join(document, selection):
    work_ref, root = selection["work_ref"], selection["root_job_id"]
    work = document.get("work")
    autonomy = document.get("autonomy")
    responsibilities = autonomy.get("responsibilities") if type(autonomy) is dict else None
    if type(work) is not list or type(responsibilities) is not list:
        raise LookupError("selection_not_found")
    works = [r for r in work if type(r) is dict and r.get("work_ref") == work_ref]
    rows = [r for r in responsibilities if type(r) is dict and r.get("responsibility_ref") == work_ref]
    if (len(works) != 1 or len(rows) != 1 or rows[0].get("root_job_id") != root
            or rows[0].get("root_job_candidates") != [root]
            or rows[0].get("root_job_ambiguous") is not False
            or rows[0].get("runtime_root_state") != "RESOLVED"):
        raise LookupError("selection_not_found")
    return rows[0]


def _qualified(snapshot, selected=None):
    from control_plane.mission_workspace import _qualified_current
    doc = snapshot.document
    autonomy = doc.get("autonomy")
    if type(autonomy) is not dict or type(autonomy.get("responsibilities")) is not list:
        return False
    rows = [_join(doc, selected)] if selected else autonomy["responsibilities"]
    # A qualified empty publication may represent zero Programs. A missing or
    # malformed source-validity envelope may never qualify as that empty state.
    validity = snapshot.validity
    if (validity.get("schema") != "mastermind.control_room_source_validity.v1"
            or validity.get("publication_seq") != snapshot.publication
            or validity.get("profile") != "b5.darwin-chrome-paired-v1"
            or type(validity.get("cards")) is not list):
        return False
    return all(type(row) is dict and _qualified_current(
        validity=validity, cache=snapshot.currentness, responsibility=row,
        responsibility_ref=row.get("responsibility_ref"), root_job_id=row.get("root_job_id"),
        control_generated_at=doc.get("generated_at"), autonomy_generated_at=autonomy.get("generated_at"),
    ) for row in rows)


def _observation(before, after, selected, runtime):
    same = (before.owner is after.owner and before.instance == after.instance
            and before.publication == after.publication
            and digest(before.document) == digest(after.document))
    state = "SAME" if same else "CONFLICT"
    if selected is not None:
        if type(runtime) is not dict or runtime.get("state") == "UNKNOWN":
            state = "UNKNOWN" if state == "SAME" else state
        elif runtime.get("state") == "CONFLICT":
            state = "CONFLICT"
        elif runtime.get("state") != "SAME":
            state = "UNKNOWN" if state == "SAME" else state
    return {
        "schema": OBSERVATION_SCHEMA, "state": state,
        "selection": selected,
        "control_room": {
            "instance_before": before.instance, "instance_after": after.instance,
            "publication_before": before.publication, "publication_after": after.publication,
            "document_digest": digest(before.document),
            "source_validity_digest": digest(after.validity),
            "cache_currentness_digest": digest(after.currentness),
        },
        "runtime": runtime,
    }


class WorkspaceReadService:
    """Fixed App-peer frame handler for an existing control-service binding.

    authorize is the existing enrolled viewer permission owner. It receives
    only the verified pseudonymous A1 principal frame, never a bearer token.
    Factories are constructed by the trusted host; HTTP cannot provide them.
    """

    def __init__(self, *, cache, runtime, authorize, armed, runtime_identity,
                 acquire=None, compose=None, bounded_runtime=None):
        self.cache = cache
        self.runtime = runtime
        self.authorize = authorize
        self.armed = armed
        self.runtime_identity = runtime_identity
        self._acquire = acquire
        self._compose = compose
        self._bounded_runtime = bounded_runtime

    def _read(self, frame):
        selected = frame["selection"]
        before = self.cache.snapshot()
        if selected is not None:
            _join(before.document, selected)
        if not _qualified(before, selected):
            raise ValueError("source_unavailable")
        fabric = None
        runtime = None
        if selected is not None:
            acquire = self._acquire
            if acquire is None:
                from control_plane.fabric_job_view import read_fabric_view_v2_from_runtime
                acquire = read_fabric_view_v2_from_runtime
            observed_runtime = self._bounded_runtime(self.runtime) if self._bounded_runtime else self.runtime
            fabric = acquire(observed_runtime, selected["root_job_id"],
                             armed=self.armed, runtime_identity=self.runtime_identity)
            acquisition = fabric.get("runtime", {}).get("acquisition", {})
            receipt = acquisition.get("generation")
            if type(receipt) is dict:
                runtime = dict(receipt, snapshot_digest=acquisition.get("snapshot_digest"))
        # Runtime acquisition is finalized (including namespace/close checks)
        # before final CCR validity sampling. SAME remains an as-of read fact.
        after = self.cache.snapshot()
        if not _qualified(after, selected):
            raise ValueError("source_unavailable")
        receipt = _observation(before, after, selected, runtime)
        if selected is None:
            if receipt["state"] != "SAME":
                raise ValueError("source_unavailable")
            result = {"schema": PROGRAMS_SCHEMA, "availability": "AVAILABLE",
                      "control_room": before.document, "source_observation": receipt, "reason_codes": []}
        else:
            compose = self._compose
            if compose is None:
                from control_plane.mission_workspace import compose_mission_workspace_v2
                compose = compose_mission_workspace_v2
            result = compose(control_room=before.document, fabric_view=fabric,
                             **selected, source_validity=after.validity,
                             cache_currentness=after.currentness, source_generation=None,
                             owner_observation=receipt)
        response = {"ok": True, "result": result}
        bounded_canonical(response, limit=MAX_RESPONSE_BYTES - 1)
        return response

    async def handle_frame(self, frame):
        try:
            validate_frame(frame)
        except (TypeError, ValueError):
            return error("invalid_input", 400)
        try:
            if self.authorize(frame["principal"]) is not True:
                return error("access_denied", 403)
        except Exception:
            return error("access_denied", 403)
        permission_before = permission_stamp(self.authorize, frame["principal"])
        task = asyncio.create_task(asyncio.to_thread(self._read, frame))
        try:
            result = await asyncio.shield(task)
            if (self.authorize(frame["principal"]) is not True
                    or permission_stamp(self.authorize, frame["principal"]) != permission_before):
                return error("access_denied", 403)
            return result
        except asyncio.CancelledError:
            # The bounded owner must finish its close boundary before this
            # request relinquishes custody; never abandon an observer thread.
            try:
                await asyncio.shield(task)
            except Exception:
                pass
            raise
        except LookupError:
            return error("selection_not_found", 404)
        except Exception:
            if frame["operation"] == "programs":
                receipt = {"schema": OBSERVATION_SCHEMA, "state": "UNKNOWN", "selection": None,
                           "control_room": None, "runtime": None}
                return {"ok": True, "result": {"schema": PROGRAMS_SCHEMA, "availability": "UNAVAILABLE",
                    "control_room": None, "source_observation": receipt, "reason_codes": ["source_unavailable"]}}
            return error("source_unavailable", 503)


def workspace_provider_factory(*, control_room, authorize, armed, runtime_identity, bounded_runtime=None):
    """Compose a sibling factory from the existing hosted owner and permissions.

    Installers pass this to CeoIngressAppBinding.workspace_read_provider_factory.
    The Executive service supplies its actual Runtime on each request. A newly
    constructed/unstarted cache, absent owner or retired owner stays unavailable.
    bounded_runtime is a trusted control-owner callback, invoked after permission
    and exact CCR selection gates. It may construct the existing readonly facade
    with the owner's qualified namespace capability. An omitted callback retains
    the ordinary Runtime and cannot manufacture a SAME receipt. The public App
    never receives this callback, a path, or namespace custody.
    """
    from control_plane.workspace_control_room_lifecycle import HostedControlRoom
    if type(control_room) is not HostedControlRoom or not callable(authorize):
        raise ValueError("workspace owner configuration refused")
    cache = ExistingControlRoomCache(control_room.current_owner)
    def provide(runtime):
        return WorkspaceReadService(cache=cache, runtime=runtime, authorize=authorize,
                                    armed=armed, runtime_identity=runtime_identity, bounded_runtime=bounded_runtime)
    return provide
