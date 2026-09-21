"""Read composition owned by the existing control service, never the public App.

The caller supplies the existing live ControlRoom ServerConfig owner and Runtime.
This module neither constructs either owner nor starts a cache refresh. The
private bracket is request scoped, and is not an installation/currentness registry.
"""
from __future__ import annotations

import asyncio
from control_plane.workspace_owned_task import await_owned
import copy
import math
import re
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
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


def _qualified_empty_programs(doc, validity):
    """An empty list needs positive canonical source evidence, not all([]).

    These fields are emitted by the existing CCR compositor from its inputs.
    They are not a new health flag or a replacement for cache publication gates.
    Missing navigation bindings remain optional and cannot decide source health.
    """
    from control_plane import chairman_control_room as ccr
    sources, autonomy, degraded = doc.get("sources"), doc.get("autonomy"), doc.get("degraded")
    if (type(sources) is not dict or type(autonomy) is not dict
            or type(degraded) is not list or not all(type(reason) is str for reason in degraded)
            or doc.get("work") != [] or validity.get("cards") != []
            or autonomy.get("schema") != "mastermind.autonomy_control_room.v1"
            or autonomy.get("generated_at") != doc.get("generated_at")
            or autonomy.get("source_failures") != []):
        return False
    counts = autonomy.get("counts")
    if (type(counts) is not dict or type(counts.get("total")) is not int
            or counts["total"] != 0 or counts.get("empty") is not True):
        return False
    core = ("boot_packet:", "executive_inbox:", "executive_runtime:",
            "agent_os_state:", "active_builds:", "autonomy:")
    if any(reason.startswith(core) for reason in degraded):
        return False
    schemas = {"executive_inbox_schema": ccr.EXECUTIVE_INBOX_SCHEMA,
               "agent_os_brief_schema": ccr.AGENT_OS_BRIEF_SCHEMA,
               "agent_os_state_schema": ccr.AGENT_OS_STATE_SCHEMA,
               "active_builds_schema": ccr.ACTIVE_BUILDS_SCHEMA}
    if any(sources.get(key) != expected for key, expected in schemas.items()):
        return False
    if sources.get("runtime_db_present") is not True:
        return False
    for key in ("mastermind_sha", "macro_sha"):
        value = sources.get(key)
        if type(value) is not str or re.fullmatch(r"[0-9a-f]{40}", value) is None:
            return False
    if type(sources.get("macro_root")) is not str or not sources["macro_root"].strip():
        return False
    for stamp in (doc.get("generated_at"), sources.get("agent_os_state_generated_at"),
                  sources.get("active_builds_collected_at")):
        try:
            if type(stamp) is not str or datetime.fromisoformat(stamp.replace("Z", "+00:00")).utcoffset() is None:
                return False
        except ValueError:
            return False
    return True


_CCR_SCHEMA = "mastermind.chairman_control_room.v1"
_AUTONOMY_SCHEMA = "mastermind.autonomy_control_room.v1"
#: Canonical freshness states the mapper may emit. Anything else on a row is a
#: malformed fact and fails closed; ``stale``/``unknown`` are the recognized
#: non-current states an explicit unqualified receipt may still serve.
_FRESHNESS_CURRENT = "current"
_FRESHNESS_NONCURRENT = ("stale", "unknown")


def _admitted_row(row, *, doc_generated_at, validity):
    """Only the canonical ``card`` fact gates reading this responsibility row.

    Dispatch, owed-open-age and actionability never decide admission here.
    A current row needs a live int budget/receipt pair from the real paired
    publication; a recognized non-current row is readable only as an explicit
    unqualified receipt whose budget and remaining values are null. An expired
    receipt, a current row paired with an unqualified component, unknown
    freshness or missing metadata never reads. The row is inspected in place
    and never promoted, sanitized or rewritten.
    """
    from control_plane.mission_workspace import (
        AUTONOMY_VALIDITY_POLICY, AUTONOMY_VALIDITY_SCHEMA, _HEX_64,
        _mapping, _mapping_rows, _safe_timestamp,
    )
    ref, root = row.get("responsibility_ref"), row.get("root_job_id")
    freshness = row.get("freshness")
    if (not isinstance(ref, str) or not ref
            or freshness not in (_FRESHNESS_CURRENT, *_FRESHNESS_NONCURRENT)
            or (root is not None and (not isinstance(root, str) or not root))):
        return False
    entries = [entry for entry in _mapping_rows(validity.get("cards"))
               if entry.get("responsibility_ref") == ref and entry.get("root_job_id") == root]
    if len(entries) != 1:
        return False
    receipt = _mapping(_mapping(entries[0].get("components")).get("card"))
    meta = _mapping(_mapping(row.get("validity")).get("card"))
    proof_ref, budget = meta.get("proof_ref"), meta.get("valid_for_ms")
    qualified_at = _safe_timestamp(meta.get("qualified_at"))
    if (meta.get("schema") != AUTONOMY_VALIDITY_SCHEMA
            or meta.get("policy") != AUTONOMY_VALIDITY_POLICY
            or not isinstance(proof_ref, str) or _HEX_64.fullmatch(proof_ref) is None
            or receipt.get("proof_ref") != proof_ref
            or qualified_at is None
            or qualified_at != _safe_timestamp(receipt.get("qualified_at"))
            or qualified_at != doc_generated_at):
        return False
    remaining, state = receipt.get("remaining_ms"), receipt.get("state")
    if freshness == _FRESHNESS_CURRENT:
        return (type(budget) is int and budget > 0
                and type(remaining) is int and 0 < remaining <= budget
                and state == "current")
    return budget is None and remaining is None and state == "unqualified"


def _qualified(snapshot, selected=None):
    from control_plane.mission_workspace import (
        SOURCE_VALIDITY_PROFILE, SOURCE_VALIDITY_SCHEMA,
    )
    doc = snapshot.document
    autonomy = doc.get("autonomy")
    work = doc.get("work")
    if (doc.get("schema") != _CCR_SCHEMA or type(work) is not list
            or type(autonomy) is not dict
            or autonomy.get("schema") != _AUTONOMY_SCHEMA
            or type(autonomy.get("responsibilities")) is not list
            or type(doc.get("generated_at")) is not str
            or autonomy.get("generated_at") != doc.get("generated_at")):
        return False
    try:
        if datetime.fromisoformat(doc["generated_at"].replace("Z", "+00:00")).utcoffset() is None:
            return False
    except ValueError:
        return False
    rows = [_join(doc, selected)] if selected else autonomy["responsibilities"]
    # A qualified empty publication may represent zero Programs. A missing or
    # malformed source-validity envelope may never qualify as that empty state.
    validity = snapshot.validity
    publication_seq = validity.get("publication_seq")
    if (validity.get("schema") != SOURCE_VALIDITY_SCHEMA
            or type(publication_seq) is not int or publication_seq <= 0
            or publication_seq != snapshot.publication
            or validity.get("profile") != SOURCE_VALIDITY_PROFILE
            or type(validity.get("cards")) is not list
            or snapshot.currentness.get("state") != "fresh"
            or type(snapshot.currentness.get("publication_seq")) is not int
            or snapshot.currentness.get("publication_seq") != publication_seq):
        return False
    if selected is None and not rows and not _qualified_empty_programs(doc, validity):
        return False
    if not all(type(row) is dict for row in rows) or not all(
            type(item) is dict and isinstance(item.get("work_ref"), str) and item["work_ref"]
            for item in work):
        return False
    work_refs = [item["work_ref"] for item in work]
    refs = [row.get("responsibility_ref") for row in rows]
    if len(set(work_refs)) != len(work_refs) or len(set(refs)) != len(refs):
        return False
    # Every responsibility must cite exactly one genuine work row. Orphan or
    # duplicated identities never read as a healthy absence of Programs.
    if any(refs.count(ref) != 1 or work_refs.count(ref) != 1 for ref in refs):
        return False
    if selected is None and set(work_refs) != set(refs):
        return False
    return all(_admitted_row(row, doc_generated_at=doc.get("generated_at"),
                             validity=validity) for row in rows)


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
        try:
            permission_before = permission_stamp(self.authorize, frame["principal"])
        except Exception:
            return error("access_denied", 403)
        task = asyncio.create_task(asyncio.to_thread(self._read, frame))
        try:
            result = await await_owned(task)
            try:
                if (self.authorize(frame["principal"]) is not True
                        or permission_stamp(self.authorize, frame["principal"]) != permission_before):
                    return error("access_denied", 403)
            except Exception:
                return error("access_denied", 403)
            return result
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
