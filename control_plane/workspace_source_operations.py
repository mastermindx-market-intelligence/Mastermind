"""Original project-source operations in the incumbent Runtime Events owner.

This module owns jobless durable phase reservation, not authentication or Git.
The qualified integration factory supplies a fresh guard for the actual verified
principal/distinct grant. A returned in-process permit is usable only while its
exact committed phase attempt is unresolved. A restart never recreates a permit.
Read status never writes; explicit reconciliation can only retain an observation
issued by the same trusted Git publisher, never start or retry an effect.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from common.workspace_source_operation_contract import (
    unavailable, validate_lookup, validate_status, _validate_source, _validate_branch,
)
from control_plane.executive_runtime import RuntimeStore

AGGREGATE = "project_source_operation"
SCHEMA = "mastermind.project_source_operation_event.v1"
_HEX = re.compile(r"[0-9a-f]{64}")


class SourceOperationConflict(ValueError):
    def __init__(self):
        super().__init__("SOURCE_OPERATION_CONFLICT")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _hex(value):
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise SourceOperationConflict()
    return value


def _identity(lookup, principal_scope):
    selection = validate_lookup(lookup)
    return {key: selection[key] for key in ("action", "request_id", "work_ref")} | {
        "principal_scope": _hex(principal_scope)}


def _aggregate(identity):
    # Deliberately excludes action, target, payload and recipe. Changing any of
    # those under the same principal/original ID must conflict, not fork history.
    return _digest({"principal_scope": identity["principal_scope"],
                    "request_id": identity["request_id"]})


def _guard(check):
    if check() is not True:
        raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")


def _reference(value):
    keys = {"schema", "input_ref", "artifact_sha256", "payload_sha256"}
    if (type(value) is not dict or any(type(k) is not str for k in value)
            or set(value) != keys or any(type(v) is not str for v in value.values())
            or value["schema"] != "mastermind.terminal_original_input_reference.v1"
            or type(value["input_ref"]) is not str
            or re.fullmatch(r"terminal-input:[0-9a-f]{64}", value["input_ref"]) is None):
        raise SourceOperationConflict()
    _hex(value["artifact_sha256"])
    _hex(value["payload_sha256"])
    return dict(value)


def _lookup_binding(value, identity, request_sha256):
    if value is None:
        return None
    keys = {"action", "request_id", "work_ref", "source_commit", "base_revision",
            "request_sha256", "expected_preference_revision"}
    if (identity["action"] not in {"add_project_file", "set_project_communication_preference"}
            or type(value) is not dict or set(value) != keys
            or any(value[k] != identity[k] for k in ("action", "request_id", "work_ref"))
            or value["request_sha256"] != request_sha256
            or type(value["source_commit"]) is not str
            or re.fullmatch(r"[0-9a-f]{40}", value["source_commit"]) is None):
        raise SourceOperationConflict()
    _hex(value["base_revision"])
    if value["expected_preference_revision"] is not None:
        _hex(value["expected_preference_revision"])
        if identity["action"] == "add_project_file":
            raise SourceOperationConflict()
    return dict(value)


def _publication_binding(value):
    if value is None:
        return None
    if (type(value) is not dict or set(value) != {"expected_commit", "postimages", "branch"}
            or type(value["expected_commit"]) is not str
            or re.fullmatch(r"[0-9a-f]{40}", value["expected_commit"]) is None
            or type(value["postimages"]) is not list or not 1 <= len(value["postimages"]) <= 3):
        raise SourceOperationConflict()
    # Reuse the actual closed path/ref/branch contract; no path is opened here.
    paths = set()
    out = []
    for item in value["postimages"]:
        if type(item) is not dict or set(item) != {"path", "content_sha256", "expected_preimage_sha256"}:
            raise SourceOperationConflict()
        if item["path"] in paths:
            raise SourceOperationConflict()
        paths.add(item["path"])
        _hex(item["content_sha256"])
        if item["expected_preimage_sha256"] is not None:
            _hex(item["expected_preimage_sha256"])
        out.append(dict(item))
    # Reuse the exact closed source/path grammar, without constructing an
    # observation or treating these planned postimages as published evidence.
    for item in out:
        _validate_source({"repository": "macro", "commit": value["expected_commit"],
                          "path": item["path"], "content_sha256": item["content_sha256"]})
    if value["branch"] is not None:
        _validate_branch(value["branch"])
    return {"expected_commit": value["expected_commit"], "postimages": out, "branch": value["branch"]}


@dataclass(frozen=True, slots=True)
class _PhasePermit:
    owner: object
    aggregate_id: str
    event_id: int
    phase: str
    fingerprint: str


class SourceOperationEvents:
    """One source-operation event adapter over the actual RuntimeStore.

    ``guard`` is a private installed-factory seam, never a public request field.
    Every read and transaction rechecks it before and after acquisition, and a
    revoked precommit guard rolls back the event. No method inserts a Job.
    """
    def __init__(self, store: RuntimeStore):
        if type(store) is not RuntimeStore:
            raise TypeError("actual RuntimeStore required")
        self.store = store
        self._permit_owner = object()

    def _events(self, identity, connection=None):
        rows = self.store.bounded_aggregate_events(
            AGGREGATE, _aggregate(identity), connection=connection,
            max_events=16, max_total_bytes=131072)
        for row in rows:
            if (row.payload.get("schema") != SCHEMA or row.payload.get("identity") != identity
                    or row.job_id is not None or row.attempt_id is not None
                    or row.worker_id is not None):
                raise SourceOperationConflict()
        return rows

    def _append(self, connection, identity, suffix, payload):
        key = _aggregate(identity)
        command = "project-source:" + key + ":" + suffix
        existing = self.store.get_event_by_command_id(command, connection=connection)
        if existing is not None:
            if existing.payload != payload:
                raise SourceOperationConflict()
            return existing
        self.store.append_event(
            connection, aggregate_type=AGGREGATE, aggregate_id=key,
            event_type="PROJECT_SOURCE_" + payload["kind"], command_id=command,
            actor="workspace:" + identity["principal_scope"], payload=payload)
        return self.store.get_event_by_command_id(command, connection=connection)

    @staticmethod
    def _payload(identity, kind, phase, intent, **extra):
        return {"schema": SCHEMA, "identity": identity, "kind": kind, "phase": phase,
                "request_sha256": intent["request_sha256"],
                "recipe_fingerprint_sha256": intent["recipe_fingerprint_sha256"], **extra}

    def prepare(self, lookup, principal_scope, *, request_sha256,
                recipe_fingerprint_sha256, original_input, permission_binding_digest, guard,
                lookup_binding=None, publication_binding=None):
        """Commit the safe original binding before its real preview is shown.

        Private bytes must already be frozen by the incumbent artifact owner.
        Repeated identical preparation is read-only; changed original data never
        replaces an intent. The permission binding remains the reviewed binding;
        later grant changes require refusal rather than silently changing it.
        """
        identity = _identity(lookup, principal_scope)
        phase = "CANDIDATE" if identity["action"] == "ADOPT_PLAN" else "PUBLICATION"
        payload = {"schema": SCHEMA, "identity": identity, "kind": "INTENT", "phase": phase,
                   "request_sha256": _hex(request_sha256),
                   "recipe_fingerprint_sha256": _hex(recipe_fingerprint_sha256),
                   "permission_binding_digest": _hex(permission_binding_digest),
                   "original_input": _reference(original_input),
                   "lookup_binding": _lookup_binding(lookup_binding, identity, request_sha256),
                   "publication_binding": _publication_binding(publication_binding)}
        _guard(guard)
        with self.store.transaction() as connection:
            _guard(guard)
            self._events(identity, connection)
            event = self._append(connection, identity, "intent", payload)
            _guard(guard)
        return self._receipt(event)

    def original(self, lookup, principal_scope, *, guard):
        """Private factory lookup; never return this binding as a public body."""
        identity = _identity(lookup, principal_scope)
        _guard(guard)
        rows = self._events(identity)
        _guard(guard)
        return None if not rows else json.loads(_canonical(rows[0].payload))

    def read_publication(self, lookup, principal_scope, *, event_id,
                         receipt_sha256, source, guard):
        """Check an exact committed CREATE source receipt without writes.

        The caller's private guard must qualify its actual principal and read
        scope. This returns source evidence, never planning, execution, session
        or continuation authority. Supplied receipt dictionaries are not proof:
        the exact immutable Event and its original binding must exist here.
        """
        identity = _identity(lookup, principal_scope)
        if (identity["action"] != "publish_project_proposal"
                or type(event_id) is not int or event_id <= 0):
            raise SourceOperationConflict()
        _hex(receipt_sha256)
        expected_source = _validate_source(source)
        # The public validator may normalize in future; retain the exact closed
        # supplied value only after it has passed that owner contract.
        expected_source = json.loads(_canonical(source))
        expected_path = "agentos/workstreams/WS-" + identity["work_ref"][3:] + ".md"
        if expected_source["path"] != expected_path:
            raise SourceOperationConflict()
        _guard(guard)
        rows = self._events(identity)
        selected = [row for row in rows if row.event_id == event_id]
        if len(selected) != 1 or not rows or rows[0].payload["kind"] != "INTENT":
            raise SourceOperationConflict()
        event = selected[0]
        payload = event.payload
        receipt = self._receipt(event)
        planned = rows[0].payload.get("publication_binding")
        if (payload["kind"] != "SOURCE_OBSERVED" or payload["phase"] != "PUBLICATION"
                or payload.get("proposal") is not None
                or payload.get("sources") != [expected_source]
                or receipt["receipt_sha256"] != receipt_sha256
                or not any(row.event_id < event_id and row.payload["kind"] == "PHASE_ATTEMPTED"
                           and row.payload["phase"] == "PUBLICATION" for row in rows)
                or planned is None
                or planned["postimages"] != [{"path": expected_source["path"],
                    "content_sha256": expected_source["content_sha256"],
                    "expected_preimage_sha256": None}]
                or payload["request_sha256"] != rows[0].payload["request_sha256"]
                or payload["recipe_fingerprint_sha256"] != rows[0].payload["recipe_fingerprint_sha256"]):
            raise SourceOperationConflict()
        result = {"schema": "mastermind.project_source_publication_observation.v1",
                  "selection": {key: identity[key] for key in ("action", "request_id", "work_ref")},
                  "owner_context": {"principal_scope": identity["principal_scope"]},
                  "source": expected_source, "receipt": receipt,
                  "request_sha256": payload["request_sha256"],
                  "recipe_fingerprint_sha256": payload["recipe_fingerprint_sha256"]}
        _guard(guard)
        return result

    def publication_candidates(self, work_ref, principal_scope, *, guard):
        """Bounded original publication selectors for same-project reopen.

        These selectors are not publication proof. The qualified data owner
        must reread each exact original and SOURCE_OBSERVED receipt, then verify
        its source bytes against the actual canonical default. No write grant,
        private input, current compiler, client pointer or new store is used.
        """
        from common.workspace_project_journal_contract import validate_selection
        from control_plane.executive_runtime import _event_from_row
        validate_selection({"work_ref": work_ref})
        scope = _hex(principal_scope)
        _guard(guard)
        with self.store.read() as connection:
            rows = connection.execute("""
                SELECT * FROM events WHERE aggregate_type=?
                AND event_type='PROJECT_SOURCE_SOURCE_OBSERVED'
                AND json_extract(payload_json,'$.schema')=?
                AND json_extract(payload_json,'$.identity.principal_scope')=?
                AND json_extract(payload_json,'$.identity.work_ref')=?
                AND json_extract(payload_json,'$.kind')='SOURCE_OBSERVED'
                AND ((json_extract(payload_json,'$.identity.action') IN
                    ('add_project_file','set_project_communication_preference','publish_project_proposal','publish_project_plan_proposal')
                    AND json_extract(payload_json,'$.phase')='PUBLICATION')
                    OR (json_extract(payload_json,'$.identity.action')='ADOPT_PLAN'
                    AND json_extract(payload_json,'$.phase')='ADOPTION'))
                ORDER BY event_id DESC LIMIT 65
            """, (AGGREGATE, SCHEMA, scope, work_ref)).fetchall()
            _guard(guard)
            candidates = []
            for row in rows[:64]:
                event = _event_from_row(row)
                identity = event.payload.get("identity")
                if type(identity) is not dict:
                    raise SourceOperationConflict()
                lookup = validate_lookup({"schema": "mastermind.workspace_source_operation_lookup.v1",
                    **{key: identity[key] for key in ("action", "request_id", "work_ref")}})
                if _identity(lookup, scope) != identity or event not in self._events(identity, connection):
                    raise SourceOperationConflict()
                candidates.append(lookup)
            _guard(guard)
        return {"lookups": candidates, "has_more": len(rows) > 64}

    def claim_phase(self, lookup, principal_scope, *, permission_binding_digest,
                    preview_witness=None, phase_receipt_digest=None, phase_publication_binding=None, guard):
        """Reserve exactly one external phase attempt, before any external I/O.

        Existing attempt means reconciliation only: this never returns a second
        permit, including after a crash or an uncertain result.
        """
        identity = _identity(lookup, principal_scope)
        _guard(guard)
        with self.store.transaction() as connection:
            _guard(guard)
            rows = self._events(identity, connection)
            if not rows:
                raise SourceOperationConflict()
            intent = rows[0].payload
            if intent["permission_binding_digest"] != _hex(permission_binding_digest):
                raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
            phase = intent["phase"]
            if phase_receipt_digest is not None:
                digest = _hex(phase_receipt_digest)
                prior = [row for row in rows if row.payload["kind"] == "SOURCE_OBSERVED"
                         and row.payload["phase"] == "CANDIDATE"
                         and self._receipt(row)["receipt_sha256"] == digest]
                if identity["action"] != "ADOPT_PLAN" or len(prior) != 1:
                    raise SourceOperationConflict()
                # Once an attempt exists this exact original witness permits
                # only the idempotent no-permit return below. A restart never
                # recreates an external invocation capability.
                phase = "ADOPTION"
            else:
                expected = {"original_input": intent["original_input"],
                            "recipe_fingerprint_sha256": intent["recipe_fingerprint_sha256"]}
                if type(preview_witness) is not dict or preview_witness != expected:
                    raise SourceOperationConflict()
            binding = _publication_binding(phase_publication_binding)
            if binding is not None and phase != "ADOPTION":
                raise SourceOperationConflict()
            attempts = [row for row in rows if row.payload["kind"] == "PHASE_ATTEMPTED"
                        and row.payload["phase"] == phase]
            if attempts:
                if binding is not None and attempts[0].payload.get("publication_binding") != binding:
                    raise SourceOperationConflict()
                _guard(guard)
                return None
            extra = {} if binding is None else {"publication_binding": binding}
            event = self._append(connection, identity, "attempt-" + phase.lower(),
                                 self._payload(identity, "PHASE_ATTEMPTED", phase, intent, **extra))
            _guard(guard)
        return _PhasePermit(self._permit_owner, _aggregate(identity), event.event_id,
                            phase, intent["recipe_fingerprint_sha256"])

    def publication_binding(self, lookup, principal_scope, *, phase, guard):
        """Read committed planned CAS hashes, never publication proof or a permit.

        ADOPTION binds its later recipe at the unique explicit phase attempt;
        it cannot replace the original candidate basis or its immutable receipt.
        The action-specific canonical compiler and grant owner qualify recipes.
        """
        identity = _identity(lookup, principal_scope)
        if phase not in ({"CANDIDATE", "ADOPTION"} if identity["action"] == "ADOPT_PLAN"
                         else {"PUBLICATION"}):
            raise SourceOperationConflict()
        _guard(guard)
        rows = self._events(identity)
        if phase == "ADOPTION":
            matches = [row for row in rows if row.payload["kind"] == "PHASE_ATTEMPTED"
                       and row.payload["phase"] == phase]
            value = None if not matches else matches[0].payload.get("publication_binding")
        else:
            value = None if not rows else rows[0].payload.get("publication_binding")
        result = None if value is None else json.loads(_canonical(value))
        _guard(guard)
        return result

    def validate_permit(self, permit, lookup, principal_scope, *, guard):
        """Publisher pre-write fence. Never recreates a durable claim."""
        identity = _identity(lookup, principal_scope)
        if (type(permit) is not _PhasePermit or permit.owner is not self._permit_owner
                or permit.aggregate_id != _aggregate(identity)):
            return False
        _guard(guard)
        rows = self._events(identity)
        valid = bool(rows and rows[-1].event_id == permit.event_id
                     and rows[-1].payload["kind"] == "PHASE_ATTEMPTED"
                     and rows[-1].payload["phase"] == permit.phase
                     and rows[-1].payload["recipe_fingerprint_sha256"] == permit.fingerprint)
        _guard(guard)
        return valid

    def retain_observation(self, lookup, principal_scope, *, phase, sources, proposal,
                           qualify_observation: Callable, guard):
        """Explicit command ONLY: retain the trusted publisher's exact observation.

        This API is not registered on GET. The installed factory binds
        ``qualify_observation`` to original publisher/readback; public source refs
        and booleans alone are never qualification. No callback here may publish.
        Concurrent same-observation calls commit one deterministic Event.
        """
        identity = _identity(lookup, principal_scope)
        _guard(guard)
        with self.store.transaction() as connection:
            _guard(guard)
            rows = self._events(identity, connection)
            if not rows or not any(r.payload["kind"] == "PHASE_ATTEMPTED"
                                       and r.payload["phase"] == phase for r in rows):
                raise SourceOperationConflict()
            intent = rows[0].payload
            kind = "SOURCE_OBSERVED" if sources else "PROPOSAL_OBSERVED"
            payload = self._payload(identity, kind, phase, intent,
                                    sources=sources, proposal=proposal)
            # Run the public closed shape before either qualifier or serializer.
            sample = self._body(identity, intent, {
                "kind": kind, "event_id": 1, "recorded_at_ms": 0,
                "receipt_sha256": "0" * 64, "sources": sources, "proposal": proposal}, phase)
            validate_status(sample)
            payload = json.loads(_canonical(payload))
            if qualify_observation(json.loads(_canonical(payload))) is not True:
                raise SourceOperationConflict()
            # A different source for an already settled phase is a conflict,
            # never a new "latest" election after default moves.
            for previous in rows:
                p = previous.payload
                if p["phase"] == phase and p["kind"] == "SOURCE_OBSERVED" and p != payload:
                    raise SourceOperationConflict()
            # Once a later phase starts, only idempotent reads of an already
            # retained earlier receipt are allowed. Never append a late proposal
            # after its source settlement or regress a current adoption attempt.
            if rows[-1].payload["phase"] != phase and not any(r.payload == payload for r in rows):
                raise SourceOperationConflict()
            suffix = "observed-" + _digest(payload)[:32]
            event = self._append(connection, identity, suffix, payload)
            _guard(guard)
        return self._receipt(event)

    def retain_no_effect(self, permit, lookup, principal_scope, *, qualify_no_effect, guard):
        """Retain an actual same-invocation zero-publication outcome.

        A reservation alone never proves this. The fixed action owner must
        qualify its actual publisher NOT_DISPATCHED or the protected path before
        any publisher invocation, and no previous observed partial
        publication may exist. After restart there is no in-process permit, so
        absence can never be promoted to a no-effect terminal result.
        """
        identity = _identity(lookup, principal_scope)
        if (type(permit) is not _PhasePermit or permit.owner is not self._permit_owner
                or permit.aggregate_id != _aggregate(identity)):
            raise SourceOperationConflict()
        _guard(guard)
        with self.store.transaction() as connection:
            _guard(guard)
            rows = self._events(identity, connection)
            if (not rows or rows[-1].event_id != permit.event_id
                    or rows[-1].payload["kind"] != "PHASE_ATTEMPTED"
                    or any(r.payload["kind"] in {"PROPOSAL_OBSERVED", "SOURCE_OBSERVED"} for r in rows)
                    or qualify_no_effect() is not True):
                raise SourceOperationConflict()
            self._append(connection, identity, "no-effect-" + permit.phase.lower(),
                         self._payload(identity, "NOT_DISPATCHED", permit.phase, rows[0].payload))
            _guard(guard)

    @staticmethod
    def _receipt(event):
        payload = event.payload
        result = {"kind": payload["kind"], "event_id": event.event_id,
                  "recorded_at_ms": int(round(datetime.fromisoformat(event.created_at).timestamp() * 1000)),
                  "sources": payload.get("sources", []), "proposal": payload.get("proposal")}
        result["receipt_sha256"] = _digest(result)
        return result

    @staticmethod
    def _body(identity, intent, receipt, phase):
        final = receipt["kind"] == "SOURCE_OBSERVED" and phase != "CANDIDATE"
        ready = receipt["kind"] == "SOURCE_OBSERVED" and phase == "CANDIDATE"
        return {"schema": "mastermind.workspace_source_operation_status.v1",
                "selection": {k: identity[k] for k in ("action", "request_id", "work_ref")},
                "owner_context": {"principal_scope": identity["principal_scope"]},
                "disposition": "accepted" if final else "unknown",
                "reason": None if final else ("READY_FOR_ADVANCE" if ready else
                           "PHASE_ATTEMPT_UNRESOLVED" if receipt["kind"] == "PHASE_ATTEMPTED" else "IN_PROGRESS"),
                "request_sha256": intent["request_sha256"],
                "recipe_fingerprint_sha256": intent["recipe_fingerprint_sha256"],
                "phase": phase, "receipt": receipt,
                "advance": {"phase_receipt_digest": receipt["receipt_sha256"]} if ready else None}

    def _status(self, identity, rows):
        if not rows:
            return unavailable(identity["action"], identity["request_id"],
                               identity["work_ref"], identity["principal_scope"])
        if rows[-1].payload["kind"] == "NOT_DISPATCHED":
            body = unavailable(identity["action"], identity["request_id"],
                               identity["work_ref"], identity["principal_scope"])
            body.update(disposition="refused", reason="NOT_DISPATCHED")
            return validate_status(body)
        return validate_status(self._body(identity, rows[0].payload,
                                         self._receipt(rows[-1]), rows[-1].payload["phase"]))

    def read_status(self, lookup, principal_scope, *, guard):
        """Read existing Runtime Events only. No Git or artifact callback, no write."""
        identity = _identity(lookup, principal_scope)
        _guard(guard)
        result = self._status(identity, self._events(identity))
        _guard(guard)
        return result
