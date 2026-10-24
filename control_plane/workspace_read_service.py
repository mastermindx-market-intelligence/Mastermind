"""Read composition owned by the existing control service, never the public App.

The caller supplies the existing live ControlRoom ServerConfig owner and Runtime.
This module neither constructs either owner nor starts a cache refresh. The
private bracket is request scoped, and is not an installation/currentness registry.
"""
from __future__ import annotations

import asyncio
from control_plane.workspace_owned_task import await_owned
import copy
import dataclasses
import math
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from common.executive_workspace_contract import (
    FABRIC_VIEW_SCHEMA_V3,
    FRAME_SCHEMA_V3, PLAN_BODY_SCHEMA, PLAN_OBSERVATION_SCHEMA,
    MAX_PLAN_RESPONSE_BYTES,
    validate_v3_frame, plan_unavailable,
    MAX_RESPONSE_BYTES,
    MAX_RESULT_RESPONSE_BYTES,
    OBSERVATION_SCHEMA,
    PROGRAMS_SCHEMA,
    PROJECTION_SCHEMA,
    QUEUE_EFFECT_EXCEPTION_REASONS,
    RESULT_BODY_SCHEMA,
    RESULT_OBSERVATION_SCHEMA,
    WORK_REFUSAL_REASON_CODES,
    WORK_SCHEMA,
    canonical,
    digest,
    error,
    validate_frame,
    validate_v2_frame,
    bounded_canonical,
    permission_stamp,
)


# Reason vocabulary exactly per the frozen v2 contract.  A v2 route emits
# one of these per non-AVAILABLE response; nothing else may be returned.
_REASON_CONTENT_OVER_BUDGET = "CONTENT_OVER_BUDGET"
_REASON_OVER_BUDGET = "OVER_BUDGET"
_REASON_SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
_REASON_SOURCE_CHANGED = "SOURCE_CHANGED"
_REASON_RESPONSE_OVER_BUDGET = "RESPONSE_OVER_BUDGET"
_VALID_REASONS = frozenset({
    _REASON_CONTENT_OVER_BUDGET,
    _REASON_OVER_BUDGET,
    _REASON_SOURCE_UNAVAILABLE,
    _REASON_SOURCE_CHANGED,
    _REASON_RESPONSE_OVER_BUDGET,
})


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
            from control_plane.workspace_control_room_lifecycle import _workspace_instance_locked
            instance = _workspace_instance_locked(owner)
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


def _program_membership(autonomy, work_refs, rows, validity):
    """Mapped cards and explicit unmapped receipts partition the Work list.

    The canonical mapper emits no card/validity receipt for an unmapped row.
    Reading that explicit absence must neither invent a seat nor hide a work
    reference. Only mapped rows participate in the paired card-validity join;
    their currentness is still checked by ``_admitted_row``.
    """
    unmapped = autonomy.get("unmapped_responsibilities", [])
    if type(unmapped) is not list:
        return False
    unmapped_refs = []
    for row in unmapped:
        if (type(row) is not dict
                or not {"responsibility_ref", "reason"} <= row.keys()
                or not row.keys() <= {"responsibility_ref", "reason", "declared_blocker"}
                or type(row["responsibility_ref"]) is not str or not row["responsibility_ref"]
                or row["reason"] not in ("owner_not_a_recognized_seat", "row_unreadable")):
            return False
        if "declared_blocker" in row:
            blocker = row["declared_blocker"]
            if (row["reason"] != "owner_not_a_recognized_seat"
                    or type(blocker) is not dict
                    or blocker.keys() != {"code", "explanation", "target_seat"}
                    or blocker["code"] != "blocked_by"
                    or type(blocker["explanation"]) is not str or not blocker["explanation"].strip()
                    or blocker["target_seat"] not in (None, "ceo")):
                return False
        unmapped_refs.append(row["responsibility_ref"])
    mapped_refs = {row["responsibility_ref"] for row in rows}
    if (len(set(unmapped_refs)) != len(unmapped_refs)
            or mapped_refs.intersection(unmapped_refs)
            or set(work_refs) != mapped_refs.union(unmapped_refs)):
        return False
    if unmapped:
        counts = autonomy.get("counts")
        if (type(counts) is not dict or type(counts.get("total")) is not int
                or counts["total"] != len(rows) or counts.get("empty") is not False):
            return False
    # Reject missing, duplicate, orphan or unmapped validity entries. This
    # is the same publication's complete mapped-card identity set, not a
    # new receipt for the unmapped rows or an all([]) currentness claim.
    pairs = []
    for entry in validity["cards"]:
        if (type(entry) is not dict
                or type(entry.get("responsibility_ref")) is not str
                or not entry["responsibility_ref"]
                or (entry.get("root_job_id") is not None
                    and (type(entry["root_job_id"]) is not str or not entry["root_job_id"]))):
            return False
        pairs.append((entry["responsibility_ref"], entry.get("root_job_id")))
    return (len(set(pairs)) == len(pairs)
            and set(pairs) == {(row["responsibility_ref"], row.get("root_job_id")) for row in rows})


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
    if selected is None and not work and not _qualified_empty_programs(doc, validity):
        return False
    if not all(type(row) is dict for row in rows) or not all(
            type(item) is dict and isinstance(item.get("work_ref"), str) and item["work_ref"]
            for item in work):
        return False
    work_refs = [item["work_ref"] for item in work]
    refs = [row.get("responsibility_ref") for row in rows]
    if (any(type(ref) is not str or not ref for ref in refs)
            or len(set(work_refs)) != len(work_refs) or len(set(refs)) != len(refs)):
        return False
    # Every responsibility must cite exactly one genuine work row. Orphan or
    # duplicated identities never read as a healthy absence of Programs.
    if any(refs.count(ref) != 1 or work_refs.count(ref) != 1 for ref in refs):
        return False
    if not all(_admitted_row(row, doc_generated_at=doc.get("generated_at"),
                             validity=validity) for row in rows):
        return False
    return selected is not None or _program_membership(autonomy, work_refs, rows, validity)


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


def _plan_validity_identity(value):
    """Compare proof identities without treating elapsed time as republication.

    Canonical remaining_ms/state age on every owner clock sample. Preserve
    every other field; the unchanged _qualified check separately refuses an
    expired or unqualified selected card after the read.
    """
    identity = copy.deepcopy(value)
    for card in identity["cards"]:
        for component in card["components"].values():
            component.pop("remaining_ms", None)
            component.pop("state", None)
    return identity


class WorkspaceReadService:
    """Fixed App-peer frame handler for an existing control-service binding.

    authorize is the existing enrolled viewer permission owner. It receives
    only the verified pseudonymous A1 principal frame, never a bearer token.
    Factories are constructed by the trusted host; HTTP cannot provide them.
    """

    def __init__(self, *, cache, runtime, authorize, armed, runtime_identity,
                 acquire=None, compose=None, bounded_runtime=None,
                 result_acquire=None, result_project=None, mission_v3_acquire=None,
                 mission_v3_compose=None, work_acquire=None, work_compose=None,
                 product_acceptance_basis_reader=None, product_acceptance_owner_target=None,
                 product_acceptance_owner_guard=None, product_acceptance_read=None,
                 product_acceptance_observe=None, activity_membership=None,
                 control_room_presenter=None,
                 control_room_actions=None):
        self.cache = cache
        self.runtime = runtime
        self.authorize = authorize
        self.armed = armed
        self.runtime_identity = runtime_identity
        if control_room_presenter is not None:
            from control_plane.workspace_control_room_presenter import ExistingControlRoomPresenter
            if type(control_room_presenter) is not ExistingControlRoomPresenter:
                raise ValueError("exact existing Control Room read owner required")
        self._control_room_presenter = control_room_presenter
        if control_room_actions is not None:
            from control_plane.workspace_control_room_actions import ExistingControlRoomActions
            if type(control_room_actions) is not ExistingControlRoomActions:
                raise ValueError("exact existing Control Room action owner required")
        self._control_room_actions = control_room_actions
        self._acquire = acquire
        self._compose = compose
        self._bounded_runtime = bounded_runtime
        # Producer callables for the v2 routes.  All four are constructor
        # injected and optional; the production result path resolves the
        # canonical Runtime/Fabric and Mission owners. Missing producers fail
        # closed through typed transport refusal, never through a local DTO.
        self._result_acquire = result_acquire
        self._result_project = result_project
        self._mission_v3_acquire = mission_v3_acquire
        self._mission_v3_compose = mission_v3_compose
        # Work-queue producers — list_roots_v2_from_runtime and
        # compose_work_queue_v1 by default.  Constructor-injected so the
        # read service never reaches past the service boundary for a writer
        # or an unfrozen schema.
        self._work_acquire = work_acquire
        self._work_compose = work_compose
        from control_plane.agentos_product_acceptance_basis import AgentOsProductAcceptanceBasisReader
        if (product_acceptance_basis_reader is not None
                and type(product_acceptance_basis_reader) is not AgentOsProductAcceptanceBasisReader):
            raise ValueError("acceptance reader must be the existing source owner")
        self._product_acceptance_basis_reader = product_acceptance_basis_reader
        from control_plane.principal_ruling_target import PrincipalRulingTarget
        if product_acceptance_owner_target is not None:
            if type(product_acceptance_owner_target) is not PrincipalRulingTarget:
                raise ValueError("exact host-owned acceptance target required")
            product_acceptance_owner_target.__post_init__()
        # Only trusted host composition supplies this frozen original target.
        # No target is discovered from HTTP selectors or the latest Runtime row.
        self._product_acceptance_owner_target = product_acceptance_owner_target
        if (product_acceptance_owner_guard is not None
                and (not callable(product_acceptance_owner_guard)
                     or product_acceptance_owner_target is None)):
            raise ValueError("acceptance source guard requires a trusted fixed target")
        self._product_acceptance_owner_guard = product_acceptance_owner_guard
        # The trusted outer host supplies its existing integration readers.
        # Core must not import the transport owner; absence stays unavailable.
        if any(reader is not None and not callable(reader)
               for reader in (product_acceptance_read, product_acceptance_observe)):
            raise ValueError("acceptance read composition requires callable readers")
        self._product_acceptance_read = product_acceptance_read
        self._product_acceptance_observe = product_acceptance_observe
        # Only the installed COO source may supply principal/workstream
        # membership. General Workspace sign-in is insufficient for OHF data.
        if activity_membership is not None and not callable(activity_membership):
            raise ValueError("activity membership owner must be callable")
        self._activity_membership = activity_membership

    async def _handle_original_acceptance_frame(self, frame):
        from common.product_acceptance_acquisition_contract import mission_frame
        from control_plane.principal_ruling_target import PrincipalRulingTarget
        try:
            original_frame = mission_frame(frame)
        except (TypeError, ValueError):
            return error("invalid_input", 400)
        principal = original_frame["principal"]
        try:
            if self.authorize(principal) is not True:
                return error("access_denied", 403)
            before = permission_stamp(self.authorize, principal)
        except Exception:
            return error("access_denied", 403)
        target = self._product_acceptance_owner_target
        guard = self._product_acceptance_owner_guard
        observe = self._product_acceptance_observe
        read = self._product_acceptance_read
        def check_source():
            if (self._product_acceptance_owner_guard is not guard
                    or self._product_acceptance_observe is not observe
                    or self._product_acceptance_read is not read):
                raise ValueError("acceptance source guard changed")
            if guard is not None:
                outcome = guard()
                if outcome is not None:
                    import inspect
                    if inspect.iscoroutine(outcome):
                        outcome.close()
                    raise ValueError("acceptance source guard must settle synchronously")
        try:
            if (type(target) is not PrincipalRulingTarget
                    or not callable(observe) or not callable(read)):
                raise ValueError("source_unavailable")
            target.__post_init__()
            target_fields = (target.work_ref, target.obligation_id, target.reasoning_surface)
            if target.work_ref != original_frame["selection"]["work_ref"]:
                raise ValueError("source_unavailable")
            check_source()
        except Exception:
            return error("source_unavailable", 503)
        try:
            body = await observe(
                self, original_frame, owner_target=target)
            result = {"ok": True, "result": body}
            bounded_canonical(result, limit=MAX_RESPONSE_BYTES - 1)
        except Exception:
            result = error("source_unavailable", 503)
        # The R2 reader settles cancellation and brackets Runtime/source/owner
        # observations. This composition additionally pins its selected target
        # through the await; neither replacement nor mutation may disclose data.
        try:
            if (self.authorize(principal) is not True
                    or permission_stamp(self.authorize, principal) != before):
                return error("access_denied", 403)
            if (self._product_acceptance_owner_target is not target
                    or (target.work_ref, target.obligation_id, target.reasoning_surface) != target_fields):
                return error("source_unavailable", 503)
            check_source()
        except Exception:
            return error("source_unavailable", 503)
        return result

    def _read_mission_v4(self, frame):
        from common import product_acceptance_read_contract as contract
        from control_plane.fabric_job_view import read_fabric_view_v3_from_runtime, compose_fabric_view_v4
        from control_plane.mission_workspace import compose_mission_workspace_v4
        selected = contract.selection(frame["selection"])
        mission_selection = {k: selected[k] for k in ("work_ref", "root_job_id")}
        before = self.cache.snapshot()
        _join(before.document, mission_selection)
        if not _qualified(before, mission_selection):
            raise ValueError("source_unavailable")
        runtime = self._bounded_runtime(self.runtime) if self._bounded_runtime else self.runtime
        first = read_fabric_view_v3_from_runtime(runtime, selected["root_job_id"],
            armed=self.armed, runtime_identity=self.runtime_identity)
        read = self._product_acceptance_read
        if not callable(read):
            raise ValueError("source_unavailable")
        accepted = read(runtime, self._product_acceptance_basis_reader, selected)
        if self._product_acceptance_read is not read:
            raise ValueError("source_unavailable")
        last = read_fabric_view_v3_from_runtime(runtime, selected["root_job_id"],
            armed=self.armed, runtime_identity=self.runtime_identity)
        companion = compose_fabric_view_v4(before=first, after=last, acceptance=accepted)
        acquisition = last["fabric_view"]["runtime"]["acquisition"]
        generation = acquisition.get("generation")
        observed = (dict(generation, snapshot_digest=acquisition.get("snapshot_digest"))
                    if type(generation) is dict else None)
        after = self.cache.snapshot()
        _join(after.document, mission_selection)
        if not _qualified(after, mission_selection):
            raise ValueError("source_unavailable")
        observation = _observation(before, after, mission_selection, observed)
        result = compose_mission_workspace_v4(control_room=before.document,
            fabric_view=companion, selection=selected, source_validity=after.validity,
            cache_currentness=after.currentness, owner_observation=observation)
        if runtime.store.read_binding is not None:
            runtime.store.read_binding.validate_before_core_return()
        response = {"ok": True, "result": result}
        bounded_canonical(response, limit=MAX_RESPONSE_BYTES - 1)
        return response

    async def _handle_v4_frame(self, frame):
        from common import product_acceptance_read_contract as contract
        try:
            contract.validate_frame(frame)
        except (TypeError, ValueError):
            return error("invalid_input", 400)
        try:
            if self.authorize(frame["principal"]) is not True:
                return error("access_denied", 403)
            before = permission_stamp(self.authorize, frame["principal"])
        except Exception:
            return error("access_denied", 403)
        task = asyncio.create_task(asyncio.to_thread(self._read_mission_v4, frame))
        try:
            result = await await_owned(task)
        except LookupError:
            return error("selection_not_found", 404)
        except Exception:
            return error("source_unavailable", 503)
        try:
            if (self.authorize(frame["principal"]) is not True
                    or permission_stamp(self.authorize, frame["principal"]) != before):
                return error("access_denied", 403)
        except Exception:
            return error("access_denied", 403)
        return result

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

    def _read_work(self, frame):
        """Read the workspace work-queue projection through existing custody.

        Mirrors the programs pipeline (cache bracket → SAME → no selection),
        but inserts one bounded Runtime root-list acquisition between the
        two cache samples and threads the acquisition receipt into the
        observation.  The pure :func:`compose_work_queue_v1` compositor
        owns all per-row grouping and the queue-level effect_exception
        read; this method never re-derives them.

        B2: failures split into typed refusal classes via
        :class:`_WorkRefusal`.  CCR bracket / runtime-receipt /
        observation-state refusals raise ``_WorkRefusal("source_unavailable")``
        or ``_WorkRefusal("runtime_observation_not_same")``.

        N2: an acquire-raised exception of ANY kind (defensive — the
        production acquirer swallows its own faults and surfaces a
        degraded notes list) becomes
        ``_WorkRefusal("source_integrity_unverified")`` — the runtime
        could not return a well-formed root list.  The same
        ``Exception`` guard the cache bracket uses, so a
        ``TypeError`` / ``RuntimeError`` acquirer yields the SAME typed
        refusal body as a ``ValueError`` acquirer.  A compose-raised
        ``ValueError`` (the composer's closed-table validator or
        evidence-freshness rejection) stays
        ``_WorkRefusal("projection_refused")``.  Anything else is a
        real error envelope — never a typed UNAVAILABLE body.
        """
        # Work carries no selection (mirrors programs); the selection field
        # is None by the closed-frame validator.  Anything else is a frame
        # contract violation that should refuse 400 before reaching here.
        # N5: a raising cache yields the same typed refusal body as an
        # unqualified cache — both wire shapes are unified into
        # ``_WorkRefusal("source_unavailable")``.
        try:
            before = self.cache.snapshot()
        except Exception:
            raise _WorkRefusal("source_unavailable") from None
        if not _qualified(before, None):
            raise _WorkRefusal("source_unavailable")
        acquire = self._work_acquire
        if acquire is None:
            from control_plane.fabric_job_view import list_roots_v2_from_runtime
            acquire = list_roots_v2_from_runtime
        compose = self._work_compose
        if compose is None:
            from control_plane.work_queue_projection import compose_work_queue_v1
            compose = compose_work_queue_v1
        observed_runtime = (
            self._bounded_runtime(self.runtime)
            if self._bounded_runtime else self.runtime
        )
        try:
            root_list = acquire(
                observed_runtime,
                armed=self.armed,
                runtime_identity=self.runtime_identity,
            )
        except Exception:
            # N2: the production acquirer swallows its own faults and
            # surfaces a degraded notes list, so this branch is defensive
            # only — if any acquirer raises ANY exception, it is a
            # source-integrity event (the runtime could not return a
            # well-formed root list), NOT a projection fault.  A
            # projection fault comes from the composer below.  The same
            # ``Exception`` guard the cache bracket uses
            # (``self.cache.snapshot()`` raises ``Exception`` on failure)
            # — one rule, both sites, so a ``TypeError`` /
            # ``RuntimeError`` acquirer yields the SAME typed refusal
            # body as a ``ValueError`` acquirer.
            raise _WorkRefusal("source_integrity_unverified") from None
        acquisition = root_list.get("runtime", {}).get("acquisition", {})
        generation = acquisition.get("generation")
        runtime_receipt = (
            dict(generation, snapshot_digest=acquisition.get("snapshot_digest"))
            if isinstance(generation, dict) else None
        )
        # N3: evaluate the CCR receipt state BEFORE the runtime gate.
        # The runtime acquisition is finalized (namespace/close checks
        # complete) before the second CCR sample, so a CCR change between
        # the two samples is positively proven here.  The CCR half of the
        # receipt must finalize SAME; missing/UNKNOWN/CONFLICT all refuse
        # as ``source_unavailable`` — the runtime gate below does NOT
        # subsume this check.
        # N5: a raising cache yields the same typed refusal body as an
        # unqualified cache.
        try:
            after = self.cache.snapshot()
        except Exception:
            raise _WorkRefusal("source_unavailable") from None
        ccr_receipt = _observation(before, after, None, None)
        if ccr_receipt["state"] != "SAME":
            raise _WorkRefusal("source_unavailable")
        if not _qualified(after, None):
            raise _WorkRefusal("source_unavailable")
        receipt = _observation(before, after, None, runtime_receipt)
        # B1: runtime observation gates the work read.  The runtime half
        # of the receipt must finalize SAME; missing/UNKNOWN/CONFLICT all
        # refuse as ``runtime_observation_not_same`` so the route cannot
        # silently claim a same-as-of read over a degraded runtime.
        if not isinstance(runtime_receipt, dict) or runtime_receipt.get("state") != "SAME":
            raise _WorkRefusal("runtime_observation_not_same")
        if receipt["state"] != "SAME":
            raise _WorkRefusal("source_unavailable")
        try:
            # WQ-PROD-1: derive the typed accountability / placement /
            # effects producer inputs from the autonomy control room
            # so every row carries per-row evidence instead of
            # ``no_producer``.  A derivation ``ValueError`` is treated
            # exactly like a compose ``ValueError`` — the existing
            # closed-key-set and freshness validators pass through
            # :func:`derive_work_producers_v1`, so any malformed
            # derivation surfaces as the typed ``projection_refused``
            # refusal.  ``producer_skips`` is exposed only via the
            # module-level pure function return (the closed
            # :data:`OUTPUT_KEYS` set in
            # :mod:`control_plane.work_queue_projection` does not admit
            # a new top-level key); tests assert against the pure
            # function's return, not against the response body.
            from control_plane.work_queue_projection import (
                derive_work_producers_v1,
            )
            producers = derive_work_producers_v1(before.document)
            # NB: injected composers (test fakes) MUST accept the four
            # producer kwargs below — all in-repo fakes take ``**kwargs``.
            result = compose(
                root_list,
                control_room=before.document,
                source_observation=receipt,
                accountability=producers["accountability"],
                placement=producers["placement"],
                effects=producers["effects"],
                evidence_as_of=producers["evidence_as_of"],
            )
        except ValueError:
            raise _WorkRefusal("projection_refused") from None
        response = {"ok": True, "result": result}
        bounded_canonical(response, limit=MAX_RESPONSE_BYTES - 1)
        return response

    def _activity_membership_marker(self, principal, selected, *, original_owner=None):
        """Re-read the incumbent installed COO principal/workstream owner.

        This is NOT a native Fabric-run grant. It covers only original
        Executive Runtime Attempt evidence inside the COO-enrolled workstream
        and the exact currently selected Control Room root. No caller-supplied
        authority, machine owner, TTL or new permission registry is accepted.
        """
        from control_plane.coo_principal_mandate import AuthorityFact, PrincipalFact
        from common.executive_workspace_contract import RESOURCE, SCOPE
        owner = original_owner if original_owner is not None else self._activity_membership
        if not callable(owner):
            raise PermissionError("activity source not installed")
        try:
            value = owner(principal, selected["work_ref"])
            if type(value) is not tuple or len(value) != 3:
                raise ValueError("wrong COO source")
            row, fact, authority = value
            if (type(row) is not dict or type(fact) is not PrincipalFact
                    or type(authority) is not AuthorityFact
                    or row.get("enabled") is not True
                    or row.get("work_ref") != selected["work_ref"]
                    or authority.work_ref != selected["work_ref"]
                    or authority.live_source_or_lease_conflict is not False
                    or type(row.get("principal_binding_digest")) is not str
                    or re.fullmatch(r"[0-9a-f]{64}", row["principal_binding_digest"]) is None
                    or fact.principal_binding_digest != row["principal_binding_digest"]
                    or type(authority.authority_generation_digest) is not str
                    or re.fullmatch(r"[0-9a-f]{64}", authority.authority_generation_digest) is None):
                raise ValueError("COO source unresolved")
            expected = {
                "issuer_digest": fact.issuer_digest,
                "subject_digest": fact.subject_digest, "client_ref": fact.client_ref,
                "resource": RESOURCE, "scopes": [SCOPE],
            }
            if (type(principal) is not dict or set(principal) != set(expected) | {"policy_id"}
                    or type(principal["policy_id"]) is not str
                    or not 1 <= len(principal["policy_id"]) <= 256
                    or {k: principal[k] for k in expected} != expected):
                raise ValueError("cross-principal source")
            # The source owner's digest and the entire validated installed
            # mission row are reobserved on release; no made-up grant digest.
            return (digest(row), fact.principal_binding_digest,
                    authority.authority_generation_digest,
                    authority.mission_authority_ref)
        except Exception:
            raise PermissionError("activity source unavailable") from None

    def _read_retained_activity(self, frame):
        """One original bounded Runtime observation under the current CCR root.

        The caller first establishes the original issuer/COO principal
        membership and rechecks it after this synchronous read has closed.
        Never returns the raw typed Job, Attempt or Event source to the App.
        """
        from common import executive_workspace_activity_contract as activity
        from control_plane.executive_runtime import RuntimeRoleResultOverBudget
        from control_plane.operator_activity_projection import (
            project_retained_operator_activity, ActivityProjectionRefusal,
        )
        selected = activity.selection(frame["selection"])
        try:
            before = self.cache.snapshot()
        except Exception:
            return activity.unavailable(selected, "SOURCE_UNAVAILABLE")
        _join(before.document, selected)  # 404 before Runtime for foreign root
        try:
            if not _qualified(before, selected):
                return activity.unavailable(selected, "SOURCE_UNAVAILABLE")
            bounded = self._bounded_runtime(self.runtime) if self._bounded_runtime else self.runtime
            with bounded.observe_bounded_read() as observation:
                source = observation.read_retained_operator_activity_bounded(
                    selected["root_job_id"], selected["job_id"], selected["attempt_id"]
                )
            receipt = observation.receipt  # physical close first
            if source.root_metadata.work_ref != selected["work_ref"]:
                return activity.unavailable(selected, "SOURCE_UNAVAILABLE")
            after = self.cache.snapshot()
            if (before.owner is not after.owner
                    or before.instance != after.instance
                    or before.publication != after.publication
                    or digest(before.document) != digest(after.document)
                    or digest(_plan_validity_identity(before.validity)) !=
                       digest(_plan_validity_identity(after.validity))
                    or digest(before.currentness) != digest(after.currentness)):
                return activity.unavailable(selected, "SOURCE_CHANGED")
            if not _qualified(after, selected):
                return activity.unavailable(selected, "SOURCE_UNAVAILABLE")
            view = project_retained_operator_activity(
                source, receipt, **selected,
            )
            observation_doc = self._result_observation(before, after, selected, receipt)
            observation_doc["schema"] = activity.OBSERVATION_SCHEMA
            body = {
                "schema": activity.BODY_SCHEMA, "selection": selected,
                "availability": "AVAILABLE", "reason_codes": [],
                "source_observation": observation_doc, "activity": view,
            }
            try:
                bounded_canonical({"ok": True, "result": body},
                                  limit=activity.MAX_RESPONSE_BYTES - 1)
            except (TypeError, ValueError):
                return activity.unavailable(selected, "RESPONSE_OVER_BUDGET")
            return {"ok": True, "result": body}
        except RuntimeRoleResultOverBudget:
            return activity.unavailable(selected, "OVER_BUDGET")
        except ActivityProjectionRefusal as exc:
            if exc.code == "SOURCE_CHANGED":
                return activity.unavailable(selected, "SOURCE_CHANGED")
            return activity.unavailable(selected,
                                        "OVER_BUDGET" if exc.code == "SOURCE_OVER_BUDGET"
                                        else "SOURCE_UNAVAILABLE")
        except LookupError:
            raise
        except Exception:
            return activity.unavailable(selected, "SOURCE_UNAVAILABLE")

    async def handle_activity_from_original_coo(self, frame, installed_source):
        """Trusted COO factory supplies its original installed reader per request.

        No changes to the immutable installed launcher or a global authority.
        Ordinary standalone Workspace frames without that source remain denied.
        """
        from ops.executive_os.coo_principal_host import CooInstalledSource
        if type(installed_source) is not CooInstalledSource:
            return error("access_denied", 403)
        return await self._handle_activity_frame(
            frame, original_owner=installed_source.for_workspace_read_principal,
        )

    async def _handle_activity_frame(self, frame, *, original_owner=None):
        from common import executive_workspace_activity_contract as activity
        try:
            activity.validate_frame(frame)
        except (TypeError, ValueError):
            return error("invalid_input", 400)
        principal, selected = frame["principal"], frame["selection"]
        try:
            if self.authorize(principal) is not True:
                return error("access_denied", 403)
            stamp = permission_stamp(self.authorize, principal)
            if stamp is None:
                return error("access_denied", 403)
            source_reader = original_owner if original_owner is not None else self._activity_membership
            stored_source_reader = self._activity_membership
            before = self._activity_membership_marker(principal, selected, original_owner=source_reader)
        except Exception:
            # Missing installed COO grants do not downgrade to global viewer
            # permission or a raw Runtime read.
            return error("access_denied", 403)
        task = asyncio.create_task(asyncio.to_thread(self._read_retained_activity, frame))
        try:
            response = await await_owned(task)
        except LookupError:
            response = error("selection_not_found", 404)
        except Exception:
            response = activity.unavailable(selected, "SOURCE_UNAVAILABLE")
        try:
            if (self.authorize(principal) is not True
                    or permission_stamp(self.authorize, principal) != stamp
                    or self._activity_membership is not stored_source_reader
                    or self._activity_membership_marker(principal, selected, original_owner=source_reader) != before):
                return error("access_denied", 403)
        except Exception:
            return error("access_denied", 403)
        return response

    def _read_admitted_plan(self, frame):
        """One owner read, physical close, policy/CCR bracket, then pure display."""
        from control_plane.executive_runtime import (
            BoundedAdmittedPlanSnapshot, BoundedRoleResultRootMetadata,
            CooCyclePolicy, RuntimePlanAdmissionNotEstablished,
            RuntimePlanAdmissionConflict, RuntimeRoleResultOverBudget,
        )
        from control_plane.fabric_plan_projection import (
            project_admitted_plan, FabricPlanProjectionError,
        )
        selected = frame["selection"]
        try:
            before = self.cache.snapshot()
        except Exception:
            return plan_unavailable(selected, "SOURCE_UNAVAILABLE")
        # Preserve the existing selection 404 before any Runtime acquisition.
        _join(before.document, selected)
        try:
            if not _qualified(before, selected):
                return plan_unavailable(selected, "SOURCE_UNAVAILABLE")
            policy_before = CooCyclePolicy.load().policy_sha256
            bounded = self._bounded_runtime(self.runtime) if self._bounded_runtime else self.runtime
            with bounded.observe_bounded_read() as observation:
                snapshot = observation.read_admitted_plan_bounded(selected["root_job_id"])
            receipt = observation.receipt  # finalized only after physical close
            policy_after = CooCyclePolicy.load().policy_sha256
            if (not isinstance(snapshot, BoundedAdmittedPlanSnapshot)
                    or not isinstance(snapshot.root_metadata, BoundedRoleResultRootMetadata)
                    or snapshot.root_job_id != selected["root_job_id"]
                    or snapshot.root_metadata.work_ref not in (None, selected["work_ref"])
                    or type(policy_before) is not str or re.fullmatch(r"[0-9a-f]{64}", policy_before) is None
                    or policy_before != policy_after
                    or snapshot.admission.get("policy_sha") != policy_before):
                return plan_unavailable(selected, "SOURCE_UNAVAILABLE")
            after = self.cache.snapshot()
            if (before.owner is not after.owner or before.instance != after.instance
                    or before.publication != after.publication
                    or digest(before.document) != digest(after.document)
                    or digest(_plan_validity_identity(before.validity)) != digest(_plan_validity_identity(after.validity))
                    or digest(before.currentness) != digest(after.currentness)):
                return plan_unavailable(selected, "SOURCE_CHANGED")
            if not _qualified(after, selected):
                return plan_unavailable(selected, "SOURCE_UNAVAILABLE")
            plan = project_admitted_plan(snapshot, receipt)
            source = self._result_observation(before, after, selected, receipt)
            source["schema"] = PLAN_OBSERVATION_SCHEMA
            body = {"schema": PLAN_BODY_SCHEMA, "selection": dict(selected),
                    "availability": "AVAILABLE", "reason_codes": [],
                    "source_observation": source, "plan": plan}
            try:
                bounded_canonical({"ok": True, "result": body}, limit=MAX_PLAN_RESPONSE_BYTES - 1)
            except (TypeError, ValueError):
                return plan_unavailable(selected, "RESPONSE_OVER_BUDGET")
            return {"ok": True, "result": body}
        except RuntimePlanAdmissionNotEstablished:
            return plan_unavailable(selected, "ADMISSION_NOT_ESTABLISHED")
        except RuntimePlanAdmissionConflict:
            return plan_unavailable(selected, "ADMISSION_CONFLICT")
        except RuntimeRoleResultOverBudget:
            return plan_unavailable(selected, "OVER_BUDGET")
        except FabricPlanProjectionError as exc:
            return plan_unavailable(selected, exc.code)
        except Exception:
            return plan_unavailable(selected, "SOURCE_UNAVAILABLE")

    async def _handle_v3_frame(self, frame):
        try:
            validate_v3_frame(frame)
        except (TypeError, ValueError):
            return error("invalid_input", 400)
        try:
            if self.authorize(frame["principal"]) is not True:
                return error("access_denied", 403)
            before = permission_stamp(self.authorize, frame["principal"])
        except Exception:
            return error("access_denied", 403)
        task = asyncio.create_task(asyncio.to_thread(self._read_admitted_plan, frame))
        try:
            result = await await_owned(task)
        except LookupError:
            result = error("selection_not_found", 404)
        except Exception:
            result = plan_unavailable(frame["selection"], "SOURCE_UNAVAILABLE")
        try:
            if (self.authorize(frame["principal"]) is not True
                    or permission_stamp(self.authorize, frame["principal"]) != before):
                return error("access_denied", 403)
        except Exception:
            return error("access_denied", 403)
        return result

    def _read_result(self, frame):
        """Read one bounded role result through the actual Fabric seam.

        The selection is the frozen five-field tuple.  The bracket is exact:
        the initial CCR work/root join is 404 before Runtime, one bounded
        Runtime acquisition whose receipt finalizes only after the physical
        context close, pre-projection binding verification, the after-close
        CCR recheck, then projection through the shared Fabric owner and the
        closed budget ladder.  Acquisition ``OVER_BUDGET`` never reaches the
        projector.  Every refusal below is one typed unavailable body with
        null result, null control_room and null runtime.
        """
        selected = frame["selection"]
        try:
            before = self.cache.snapshot()
        except Exception:
            return self._result_unavailable_body(selected, _REASON_SOURCE_UNAVAILABLE)
        try:
            _join(before.document, selected)
        except LookupError:
            raise LookupError("selection_not_found") from None
        if not _qualified(before, selected):
            return self._result_unavailable_body(selected, _REASON_SOURCE_UNAVAILABLE)
        try:
            snapshot, receipt = self._bounded_result_acquire(selected)
        except _ResultOverBudget:
            return self._result_unavailable_body(selected, _REASON_OVER_BUDGET)
        except _ResultSourceUnavailable:
            return self._result_unavailable_body(selected, _REASON_SOURCE_UNAVAILABLE)
        try:
            after = self.cache.snapshot()
        except Exception:
            return self._result_unavailable_body(selected, _REASON_SOURCE_UNAVAILABLE)
        # A positive CCR change proof — owner instance, publication sequence
        # or canonical document moved between the two samples — is the only
        # SOURCE_CHANGED; every other failure below is SOURCE_UNAVAILABLE.
        if (before.owner is not after.owner or before.instance != after.instance
                or before.publication != after.publication
                or digest(before.document) != digest(after.document)):
            return self._result_unavailable_body(selected, _REASON_SOURCE_CHANGED)
        if not _qualified(after, selected):
            return self._result_unavailable_body(selected, _REASON_SOURCE_UNAVAILABLE)
        if not self._result_binding_verified(snapshot, receipt, selected):
            return self._result_unavailable_body(selected, _REASON_SOURCE_UNAVAILABLE)
        try:
            projection = self._bounded_result_project(snapshot, receipt)
        except Exception:
            return self._result_unavailable_body(selected, _REASON_SOURCE_UNAVAILABLE)
        # The shared documents are served unchanged; their embedded selector
        # must already equal the request's four fields.  It is compared,
        # never overwritten.
        shared = self._result_shared_selection(selected)
        if (type(projection.complete) is not dict
                or type(projection.content_over_budget) is not dict
                or projection.complete.get("selection") != shared
                or projection.content_over_budget.get("selection") != shared):
            return self._result_unavailable_body(selected, _REASON_SOURCE_UNAVAILABLE)
        observation = self._result_observation(before, after, selected, receipt)
        # Budget ladder over the whole canonical {ok:true,result:BODY} + LF:
        # the complete document, then the projector's own content_over_budget
        # fallback, then discard.  Only the Workspace wrapper is rebuilt; the
        # shared nested documents never are.
        body = {
            "schema": RESULT_BODY_SCHEMA,
            "selection": dict(selected),
            "availability": "AVAILABLE",
            "reason_codes": [],
            "source_observation": observation,
            "result": projection.complete,
        }
        if self._result_envelope_fits(body):
            return {"ok": True, "result": body}
        body = {
            "schema": RESULT_BODY_SCHEMA,
            "selection": dict(selected),
            "availability": "CONTENT_OVER_BUDGET",
            "reason_codes": [_REASON_CONTENT_OVER_BUDGET],
            "source_observation": observation,
            "result": projection.content_over_budget,
        }
        if self._result_envelope_fits(body):
            return {"ok": True, "result": body}
        # Neither shared document fits: discard all content.  No successful
        # source receipt is retained with the refusal.
        raise _ResultResponseOverBudget()

    def _bounded_result_acquire(self, selected):
        """One bounded role-result acquisition via the actual Runtime seam.

        Returns ``(snapshot, receipt)`` exactly once, with the receipt read
        only after the bounded observation context has physically closed —
        reading it inside the with-block is the preserved lifetime defect.
        The production path resolves the canonical ``read_role_result_bounded``
        over the existing bounded runtime facade (exactly one selection per
        observation, no ambient Runtime reopen, root scan or source fallback);
        a constructor-injected ``result_acquire`` is the interface fixture
        path and is used directly.
        """
        if self._result_acquire is not None:
            try:
                return self._result_acquire(self.runtime, selected,
                                            armed=self.armed,
                                            runtime_identity=self.runtime_identity)
            except _ResultOverBudget:
                raise
            except Exception as exc:
                raise self._result_acquire_refusal(exc) from exc
        from control_plane.executive_runtime import RuntimeRoleResultOverBudget
        bounded_runtime = (self._bounded_runtime(self.runtime)
                           if self._bounded_runtime else self.runtime)
        try:
            with bounded_runtime.observe_bounded_read() as observation:
                snapshot = observation.read_role_result_bounded(
                    selected["root_job_id"],
                    selected["job_id"],
                    expected_attempt_id=selected["attempt_id"],
                    expected_result_envelope_digest=selected["result_envelope_digest"],
                )
                # The receipt finalizes when this block physically closes; it
                # is deliberately not read here.
            receipt = observation.receipt
        except RuntimeRoleResultOverBudget as exc:
            raise _ResultOverBudget() from exc
        except Exception as exc:
            raise self._result_acquire_refusal(exc) from exc
        return snapshot, receipt

    @staticmethod
    def _result_acquire_refusal(exc):
        """Map an actual acquisition error to the service's typed refusal.

        ``RuntimeRoleResultOverBudget`` is OVER_BUDGET; every other
        StateConflict, RuntimeReadUnavailable or generic error — authority
        mismatch, missing root or Attempt, digest disagreement, unfinalized
        observation — is SOURCE_UNAVAILABLE.  None of them positively prove
        a CCR change.
        """
        from control_plane.executive_runtime import RuntimeRoleResultOverBudget
        if isinstance(exc, RuntimeRoleResultOverBudget):
            return _ResultOverBudget()
        return _ResultSourceUnavailable()

    def _bounded_result_project(self, snapshot, receipt):
        """Project one bounded snapshot through the actual shared Fabric owner."""
        if self._result_project is not None:
            return self._result_project(snapshot, receipt)
        from control_plane.fabric_result_projection import project_fabric_role_result
        return project_fabric_role_result(snapshot, receipt)

    @staticmethod
    def _result_binding_verified(snapshot, receipt, selected):
        """Pre-projection binding law over the actual Runtime material.

        Exact snapshot root/job/attempt/envelope-digest tuple, non-null
        source identity equal to the finalized receipt's identity, a final
        SAME receipt, and root metadata work_ref agreement when present.
        """
        root_metadata = getattr(snapshot, "root_metadata", None)
        work_ref = getattr(root_metadata, "work_ref", None)
        identity = getattr(snapshot, "observation_source_identity", None)
        return ((getattr(snapshot, "root_job_id", None),
                 getattr(snapshot, "job_id", None),
                 getattr(snapshot, "attempt_id", None),
                 getattr(snapshot, "result_envelope_digest", None))
                == (selected["root_job_id"], selected["job_id"],
                    selected["attempt_id"], selected["result_envelope_digest"])
                and getattr(receipt, "state", None) == "SAME"
                and type(identity) is str and bool(identity)
                and identity == getattr(receipt, "source_identity", None)
                and (work_ref is None or work_ref == selected["work_ref"]))

    def _result_observation(self, before, after, selected, receipt):
        """Assemble the closed ``mastermind.workspace_result_observation.v1``.

        The runtime field is the finalized receipt's own public dictionary;
        the control_room bracket carries the two sampled CCR digests.
        """
        generation = receipt.to_dict()
        return {
            "schema": RESULT_OBSERVATION_SCHEMA,
            "state": "SAME" if generation.get("state") == "SAME" else "UNKNOWN",
            "selection": {key: selected[key] for key in sorted(selected)},
            "control_room": {
                "instance_before": before.instance,
                "instance_after": after.instance,
                "publication_before": before.publication,
                "publication_after": after.publication,
                "document_digest": digest(before.document),
                "source_validity_digest": digest(after.validity),
                "cache_currentness_digest": digest(after.currentness),
            },
            "runtime": generation,
        }

    def _result_shared_selection(self, selected):
        """The four-field selection embedded in shared result documents."""
        return {
            "root_job_id": selected["root_job_id"],
            "job_id": selected["job_id"],
            "attempt_id": selected["attempt_id"],
            "result_envelope_digest": selected["result_envelope_digest"],
        }

    @staticmethod
    def _result_envelope_fits(body):
        """Whole ``{"ok":true,"result":BODY}`` UTF-8 + LF within 16384 bytes."""
        try:
            bounded_canonical({"ok": True, "result": body},
                              limit=MAX_RESULT_RESPONSE_BYTES - 1)
        except (TypeError, ValueError):
            return False
        return True

    def _result_unavailable_body(self, selected, reason):
        """One typed unavailable body, pinned by the frozen design fixtures.

        ``result``, ``source_observation.control_room`` and
        ``source_observation.runtime`` are all null; the observation state is
        CONFLICT only for the positively proven SOURCE_CHANGED refusal, else
        UNKNOWN.  No successful source receipt is retained.
        """
        body = {
            "schema": RESULT_BODY_SCHEMA,
            "selection": dict(selected),
            "availability": "UNAVAILABLE",
            "reason_codes": [reason],
            "source_observation": {
                "schema": RESULT_OBSERVATION_SCHEMA,
                "state": "CONFLICT" if reason == _REASON_SOURCE_CHANGED else "UNKNOWN",
                "selection": {key: selected[key] for key in sorted(selected)},
                "control_room": None,
                "runtime": None,
            },
            "result": None,
        }
        bounded_canonical({"ok": True, "result": body},
                          limit=MAX_RESULT_RESPONSE_BYTES - 1)
        return {"ok": True, "result": body}

    def _read_mission_v3(self, frame):
        """Join the canonical v3 companion and reducer through existing custody."""
        selected = frame["selection"]
        before = self.cache.snapshot()
        _join(before.document, selected)
        if not _qualified(before, selected):
            raise ValueError("source_unavailable")
        acquire, compose = self._mission_v3_acquire, self._mission_v3_compose
        if acquire is None:
            from control_plane.fabric_job_view import read_fabric_view_v3_from_runtime
            acquire = read_fabric_view_v3_from_runtime
        if compose is None:
            from control_plane.mission_workspace import compose_mission_workspace_v3
            compose = compose_mission_workspace_v3
        observed_runtime = self._bounded_runtime(self.runtime) if self._bounded_runtime else self.runtime
        companion = acquire(observed_runtime, selected["root_job_id"],
                            armed=self.armed, runtime_identity=self.runtime_identity)
        acquisition = companion.get("fabric_view", {}).get("runtime", {}).get("acquisition", {})
        generation = acquisition.get("generation")
        runtime = (dict(generation, snapshot_digest=acquisition.get("snapshot_digest"))
                   if type(generation) is dict else None)
        # The canonical Fabric owner returns only after observation physical
        # close. The cache bracket and canonical reducer retain state authority.
        after = self.cache.snapshot()
        _join(after.document, selected)
        if not _qualified(after, selected):
            raise ValueError("source_unavailable")
        observation = _observation(before, after, selected, runtime)
        result = compose(control_room=before.document, fabric_view=companion,
                         **selected, source_validity=after.validity,
                         cache_currentness=after.currentness, source_generation=None,
                         owner_observation=observation)
        response = {"ok": True, "result": result}
        bounded_canonical(response, limit=MAX_RESPONSE_BYTES - 1)
        return response

    def read_mission_for_work_ref(self, work_ref):
        """Host-internal COO consumer of the SAME Mission v3 acquisition.

        The configured App-peer provider must authorize its sealed mission first.
        This method performs no authentication, refresh, root creation or grant.
        Root selection remains the current Control Room responsibility projection.
        """
        from common.executive_workspace_contract import _check_work_ref
        if not _check_work_ref(work_ref):
            raise ValueError("invalid_input")
        snapshot = self.cache.snapshot()
        autonomy = snapshot.document.get("autonomy")
        rows = autonomy.get("responsibilities") if type(autonomy) is dict else None
        matches = [row for row in rows if type(row) is dict
                   and row.get("responsibility_ref") == work_ref] if type(rows) is list else []
        if len(matches) != 1:
            raise LookupError("selection_not_found")
        selection = {"work_ref": work_ref, "root_job_id": matches[0].get("root_job_id")}
        _join(snapshot.document, selection)
        if not _qualified(snapshot, selection):
            raise ValueError("source_unavailable")
        return self._read_mission_v3({"selection": selection})["result"]

    async def handle_frame(self, frame, *, action_host_ready=None):
        from common import workspace_control_room_action_contract as action_wire
        if type(frame) is dict and frame.get("schema") == action_wire.FRAME_SCHEMA:
            try:
                request = action_wire.validate_frame(frame)
            except (TypeError, ValueError):
                return error("invalid_input", 400)
            actions = self._control_room_actions
            if actions is None:
                return {"ok": True, "result": action_wire.refused_result(
                    request["operation"], code="source_unavailable", status=503,
                )}
            # Actions retain their own admission and effect-aware response;
            # READ post-work permission/retirement rewriting cannot apply here.
            return await actions.handle_frame(request, host_ready=action_host_ready)
        from common.workspace_control_room_read_contract import (
            FRAME_SCHEMA as CCR_READ_FRAME_SCHEMA, validate_frame as validate_ccr_read_frame,
        )
        if isinstance(frame, dict) and frame.get("schema") == CCR_READ_FRAME_SCHEMA:
            try:
                validate_ccr_read_frame(frame)
            except (TypeError, ValueError):
                return error("invalid_input", 400)
            presenter = self._control_room_presenter
            return (await presenter.read(frame["principal"], frame["operation"])
                    if presenter is not None else error("source_unavailable", 503))
        from common.product_acceptance_read_contract import FRAME_SCHEMA as ACCEPTANCE_FRAME_SCHEMA
        if isinstance(frame, dict) and frame.get("schema") == ACCEPTANCE_FRAME_SCHEMA:
            from common.product_acceptance_acquisition_contract import OPERATION as ORIGINAL_OPERATION
            if frame.get("operation") == ORIGINAL_OPERATION:
                return await self._handle_original_acceptance_frame(frame)
            return await self._handle_v4_frame(frame)
        if isinstance(frame, dict) and frame.get("schema") == FRAME_SCHEMA_V3:
            return await self._handle_v3_frame(frame)
        from common.executive_workspace_activity_contract import FRAME_SCHEMA as ACTIVITY_FRAME_SCHEMA
        if isinstance(frame, dict) and frame.get("schema") == ACTIVITY_FRAME_SCHEMA:
            return await self._handle_activity_frame(frame)
        # v2 frames take the closed v2 validation path; v1 frames keep their
        # existing envelope.  The two are mutually exclusive — never both.
        if isinstance(frame, dict) and frame.get("schema") == "mastermind.executive_workspace_read.v2":
            return await self._handle_v2_frame(frame)
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
        worker = self._read_work if frame["operation"] == "work" else self._read
        task = asyncio.create_task(asyncio.to_thread(worker, frame))
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
        except _WorkRefusal as refusal:
            # B2: typed refusal from ``_read_work`` — emits a typed UNAVAILABLE
            # body with the closed reason_code.  This branch fires BEFORE the
            # generic ``except Exception`` so a projection/validator fault is
            # never laundered into ``source_unavailable``.
            if frame["operation"] != "work":
                return error("source_unavailable", 503)
            from control_plane.work_queue_projection import (
                _GROUP_ORDER as _WQ_GROUPS, _utc_now as _wq_utc_now,
                WORK_QUEUE_SCHEMA,
                _QUEUE_EFFECT_EXCEPTION_REASON_READ_REFUSED,
            )
            receipt = {"schema": OBSERVATION_SCHEMA, "state": "UNKNOWN", "selection": None,
                       "control_room": None, "runtime": None}
            # Key-for-key shape parity with the composer's UNAVAILABLE branch
            # (only generated_at / source_observation / reason_codes /
            # lifecycle_source legitimately differ; the typed refusal carries
            # the read-service's own reason code, not the composer's
            # LIFECYCLE_UNAVAILABLE flag).
            # N4: the effect_exception.reason uses ``read_refused`` — the
            # read service is reporting that its OWN read failed (CCR
            # bracket, runtime observation, projection fault), NOT that the
            # composer's view of a missing control room document.  The
            # composer's ``control_room_missing`` is its OWN vocabulary for
            # a missing control room input; the read service must not
            # mis-attribute its own failure to the composer's vocabulary.
            # Closed-set guard: the read service's emitted ``reason`` MUST
            # be a member of the contract's effect_exception vocabulary so
            # the workspace read can never silently introduce a new reason.
            assert _QUEUE_EFFECT_EXCEPTION_REASON_READ_REFUSED in QUEUE_EFFECT_EXCEPTION_REASONS, (
                f"read-service emitted reason "
                f"{_QUEUE_EFFECT_EXCEPTION_REASON_READ_REFUSED!r} not in "
                f"QUEUE_EFFECT_EXCEPTION_REASONS="
                f"{sorted(QUEUE_EFFECT_EXCEPTION_REASONS)}"
            )
            return {"ok": True, "result": {"schema": WORK_QUEUE_SCHEMA,
                "availability": "UNAVAILABLE",
                "generated_at": _wq_utc_now(),
                "lifecycle_source": None,
                "effect_exception": {"value": "UNKNOWN", "scope": "RUNTIME_CURRENT_WORKER",
                                     "observable": False,
                                     "reason": _QUEUE_EFFECT_EXCEPTION_REASON_READ_REFUSED},
                "coverage": {"count": 0, "total": None, "truncated": False,
                             "completeness": "PARTIAL"},
                "groups": {key: [] for key in _WQ_GROUPS},
                "source_observation": receipt,
                "reason_codes": [refusal.reason_code]}}
        except Exception:
            if frame["operation"] == "programs":
                receipt = {"schema": OBSERVATION_SCHEMA, "state": "UNKNOWN", "selection": None,
                           "control_room": None, "runtime": None}
                return {"ok": True, "result": {"schema": PROGRAMS_SCHEMA, "availability": "UNAVAILABLE",
                    "control_room": None, "source_observation": receipt, "reason_codes": ["source_unavailable"]}}
            if frame["operation"] == "work":
                # B2: a non-_WorkRefusal exception on the work path is a REAL
                # error envelope — a 503 with the closed error shape.  A
                # projection/validator fault would have come through as a
                # _WorkRefusal above; reaching this branch means something
                # unexpected happened and the route must NOT silently manufacture
                # a typed UNAVAILABLE document.
                return error("source_unavailable", 503)
            return error("source_unavailable", 503)

    async def _handle_v2_frame(self, frame):
        try:
            validate_v2_frame(frame)
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
        operation = frame["operation"]
        if operation == "result":
            worker = self._read_result
        elif operation == "mission_v3":
            worker = self._read_mission_v3
        else:
            return error("invalid_input", 400)
        task = asyncio.create_task(asyncio.to_thread(worker, frame))
        try:
            result = await await_owned(task)
        except LookupError:
            return error("selection_not_found", 404)
        except _ResultResponseOverBudget:
            # Neither shared document fits the closed ceiling: discard all
            # content through the fixture-pinned minimal unavailable body.
            result = self._result_unavailable_body(
                frame["selection"], _REASON_RESPONSE_OVER_BUDGET)
        except Exception:
            if operation != "result":
                # Producer failure is a typed transport refusal; the adapter
                # never manufactures a Mission body.
                return error("source_unavailable", 503)
            result = self._result_unavailable_body(
                frame["selection"], _REASON_SOURCE_UNAVAILABLE)
        try:
            if (self.authorize(frame["principal"]) is not True
                    or permission_stamp(self.authorize, frame["principal"]) != permission_before):
                return error("access_denied", 403)
        except Exception:
            return error("access_denied", 403)
        return result


class _ResultOverBudget(Exception):
    """Typed refusal for RuntimeRoleResultOverBudget inside the read service."""


class _ResultSourceUnavailable(Exception):
    """Typed refusal for any non-overbudget Runtime acquisition error."""


class _ResultResponseOverBudget(Exception):
    """Typed refusal when neither shared document fits the 16384 ceiling."""


class _WorkRefusal(Exception):
    """Typed refusal for a work-queue read failure (B2).

    ``reason_code`` must be a member of
    :data:`common.executive_workspace_contract.WORK_REFUSAL_REASON_CODES`.
    Anything else on this exception is a contract violation.  The catch
    block in :meth:`WorkspaceReadService.handle_frame` translates this
    into a typed UNAVAILABLE body — never into a 503 error envelope.
    """

    def __init__(self, reason_code):
        if reason_code not in WORK_REFUSAL_REASON_CODES:
            raise ValueError(
                f"_WorkRefusal reason_code {reason_code!r} not in "
                f"WORK_REFUSAL_REASON_CODES={sorted(WORK_REFUSAL_REASON_CODES)}"
            )
        super().__init__(reason_code)
        self.reason_code = reason_code


def workspace_provider_factory(*, control_room, authorize, armed, runtime_identity, bounded_runtime=None,
                               authorize_discovery=None, authorize_actions=None, action_now=None,
                               product_acceptance_basis_reader=None, product_acceptance_owner_target=None,
                               product_acceptance_owner_guard=None, product_acceptance_read=None,
                               product_acceptance_observe=None, activity_membership=None,
                               cross_plane_context=None, cross_plane_enrollment=None):
    """Compose a sibling factory from the existing hosted owner and permissions.

    Installers pass this to CeoIngressAppBinding.workspace_read_provider_factory.
    The Executive service supplies its actual Runtime on each request. A newly
    constructed/unstarted cache, absent owner or retired owner stays unavailable.
    bounded_runtime is a trusted control-owner callback, invoked after permission
    and exact CCR selection gates. It may construct the existing readonly facade
    with the owner's qualified namespace capability. An omitted callback retains
    the ordinary Runtime and cannot manufacture a SAME receipt. The public App
    never receives this callback, a path, or namespace custody.
    authorize_discovery is a separately selected, revocable trusted action owner;
    omission keeps Discovery refused. The READ membership callback does not
    supply this grant. authorize_actions selects all four mutation permissions
    from that same trusted enrollment owner; omission keeps mutations unavailable.
    """
    from control_plane.workspace_control_room_lifecycle import HostedControlRoom
    if type(control_room) is not HostedControlRoom or not callable(authorize):
        raise ValueError("workspace owner configuration refused")
    if cross_plane_enrollment is not None:
        # An installed host may select the same private reader through an
        # already-qualified typed enrollment; never from HTTP or control.json.
        # Preserve the existing source authority, not a second reader plane.
        if cross_plane_context is not None:
            raise ValueError("ambiguous cross-plane source selection")
        from control_plane.workspace_cross_plane_enrollment import select_installed_cross_plane
        cross_plane_context = select_installed_cross_plane(
            control_room=control_room, authorize=authorize,
            enrollment=cross_plane_enrollment,
        )
    cache = ExistingControlRoomCache(control_room.current_owner)
    # The original source+permission owner, not a new publisher or identity.
    # Discovery requires an independent callback and remains dark by default.
    from control_plane.workspace_control_room_presenter import ExistingControlRoomPresenter
    presenter = ExistingControlRoomPresenter(
        cache, authorize=authorize, authorize_discovery=authorize_discovery,
        cross_plane_context=cross_plane_context,
    )
    actions = None
    if authorize_actions is not None:
        from control_plane.workspace_control_room_actions import ExistingControlRoomActions
        actions = ExistingControlRoomActions(
            control_room, authorize=authorize, authorize_actions=authorize_actions, now=action_now,
        )
    def provide(runtime):
        return WorkspaceReadService(cache=cache, runtime=runtime, authorize=authorize,
                                    armed=armed, runtime_identity=runtime_identity,
                                    control_room_presenter=presenter, control_room_actions=actions,
                                    bounded_runtime=bounded_runtime,
                                    product_acceptance_basis_reader=product_acceptance_basis_reader,
                                    product_acceptance_owner_target=product_acceptance_owner_target,
                                    product_acceptance_owner_guard=product_acceptance_owner_guard,
                                    product_acceptance_read=product_acceptance_read,
                                    product_acceptance_observe=product_acceptance_observe,
                                    activity_membership=activity_membership)
    return provide
