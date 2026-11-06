"""Integration adapter joining actual Runtime source-operation Events to the
reviewed fixed knowledge Git publisher seams.

This module owns no Git, HTTP, compiler, artifact body or Macro read and no
write effect of any kind. It binds the actual ``SourceOperationEvents`` owner
and the actual ``WorkspaceSourceOperationContextFactory`` so the reviewed
``FixedProjectGitPublisher`` knowledge methods can be wired to four private
seams — ``authorize_knowledge``, ``knowledge_permission_stamp``,
``load_original_operation`` and ``validate_original_claim`` — plus the actual
owner ``principal_scope`` projection. Retained publisher metadata is derived
exclusively from ``Events.original`` and ``Events.read_status`` under fresh
bound permission guards; recipes, claims and caller payloads are never
metadata authority. A ``CLAIMED`` phase exists only while one private
in-process ``_PhasePermit`` from ``Events.claim_phase`` is active inside
``bind_claim`` and ``Events.validate_permit`` still holds at every callback;
the ``PHASE_ATTEMPTED`` label alone is never claim evidence, a later
PROPOSAL/SOURCE/NOT_DISPATCHED Event revokes the live permit, and a restart
never recreates a claim. Absence of an original Event is ``None``; corrupt or
changed retained state fails closed with one constant error code. The adapter
never replaces the original permission binding with the current stamp, never
issues revision/adoption/continuation authority, never maps a Workspace
identity to a Git credential and never dispatches a generic action or path.
"""
from __future__ import annotations

import json
import re
import threading
from contextlib import contextmanager
from contextvars import ContextVar

from common.workspace_project_journal_contract import validate_selection
from common.workspace_source_operation_contract import validate_lookup
from control_plane.workspace_source_operations import SourceOperationEvents
from integrations.mastermind_workspace_app.source_operation_principal import source_principal_scope
from integrations.mastermind_workspace_app.source_operation_context import (
    WorkspaceSourceOperationContextFactory,
)

KNOWLEDGE_METADATA_SCHEMA = "mastermind.workspace_project_knowledge_operation.v1"
_EVENT_SCHEMA = "mastermind.project_source_operation_event.v1"
_LOOKUP_SCHEMA = "mastermind.workspace_source_operation_lookup.v1"
_PUBLICATION_REPOSITORY = "mastermindx-market-intelligence/macro"

_KNOWLEDGE_ACTIONS = frozenset({"add_project_file", "set_project_communication_preference"})
_LOOKUP7_KEYS = frozenset({"action", "request_id", "work_ref", "source_commit",
                           "base_revision", "request_sha256", "expected_preference_revision"})
_IDENTITY3_KEYS = ("action", "request_id", "work_ref")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_HEX40 = re.compile(r"[0-9a-f]{40}")


class KnowledgeOperationConflict(ValueError):
    """Closed adapter conflict; carries one constant code, never private text."""

    def __init__(self):
        super().__init__("KNOWLEDGE_OPERATION_CONFLICT")


def _detached(value):
    """Fresh builtin-only copy through the canonical JSON encoding."""
    return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False, allow_nan=False))


def _hex64(value):
    if type(value) is not str or _HEX64.fullmatch(value) is None:
        raise KnowledgeOperationConflict()
    return value


def _hex40(value):
    if type(value) is not str or _HEX40.fullmatch(value) is None:
        raise KnowledgeOperationConflict()
    return value


def _lookup_identity(value):
    """Validate the exact body-free seven-field knowledge selection."""
    if (type(value) is not dict or set(value) != _LOOKUP7_KEYS
            or type(value["action"]) is not str
            or value["action"] not in _KNOWLEDGE_ACTIONS):
        raise KnowledgeOperationConflict()
    try:
        validate_lookup({"schema": _LOOKUP_SCHEMA, "action": value["action"],
                         "request_id": value["request_id"], "work_ref": value["work_ref"]})
        validate_selection({"work_ref": value["work_ref"]})
    except ValueError:
        raise KnowledgeOperationConflict() from None
    _hex64(value["base_revision"])
    _hex64(value["request_sha256"])
    _hex40(value["source_commit"])
    preference = value["expected_preference_revision"]
    if preference is not None:
        _hex64(preference)
        if value["action"] == "add_project_file":
            raise KnowledgeOperationConflict()
    return {key: value[key] for key in _LOOKUP7_KEYS}


def _lookup3(identity):
    return {"schema": _LOOKUP_SCHEMA, **{key: identity[key] for key in _IDENTITY3_KEYS}}


class _ReadGuard:
    """Fresh bound permission check for one exact bound owner context."""
    __slots__ = ("_context",)

    def __init__(self, context):
        self._context = context

    def __call__(self):
        return self._context.check() is True


class _ClaimLease:
    """One active in-process claim invocation; never serialized or stored.

    ``_PhasePermit`` is a frozen slots dataclass, so permit identity is tracked
    with a pinned object-identity map rather than a ``WeakSet``; no new store
    or lifecycle is introduced and nothing outlives this process.
    """
    __slots__ = ("permit", "scope", "identity", "context")

    def __init__(self, permit, scope, identity, context):
        self.permit, self.scope, self.identity, self.context = permit, scope, identity, context


class KnowledgePublisherEvents:
    """Concrete knowledge-seam adapter over the actual Events owner."""

    def __init__(self, *, events, contexts):
        if (type(events) is not SourceOperationEvents
                or type(contexts) is not WorkspaceSourceOperationContextFactory):
            raise KnowledgeOperationConflict()
        self._events = events
        self._contexts = contexts
        self._lock = threading.Lock()
        self._consumed = {}
        self._active = ContextVar("mastermind_knowledge_claim_lease", default=None)

    # -- publisher owner seams ------------------------------------------------

    def principal_scope(self, principal):
        """Actual ``workspace_owner_context`` scope for the nominal owner."""
        return source_principal_scope(principal)

    def authorize_knowledge(self, principal, action, work_ref):
        """Whether the current sealed grant authorizes this closed action."""
        try:
            return self._context(principal, action, work_ref).check() is True
        except (PermissionError, ValueError, TypeError):
            return False

    def knowledge_permission_stamp(self, principal, action, work_ref):
        """Exact current scoped permission stamp for the closed action."""
        context = self._context(principal, action, work_ref)
        return _hex64(context.permission_binding_digest)

    def load_original_operation(self, principal, lookup):
        """Derive retained publisher metadata from actual Events only.

        ``None`` means only that no original operation exists. Any corrupt or
        changed retained state raises the closed conflict instead of guessing.
        """
        identity = _lookup_identity(lookup)
        context = self._context(principal, identity["action"], identity["work_ref"])
        scope = context.principal_scope
        guard = _ReadGuard(context)
        original = self._events.original(_lookup3(identity), scope, guard=guard)
        if original is None:
            return None
        status = self._events.read_status(_lookup3(identity), scope, guard=guard)
        if self._events.original(_lookup3(identity), scope, guard=guard) != original:
            raise KnowledgeOperationConflict()
        return self._metadata(identity, scope, original, status, context)

    def validate_original_claim(self, principal, lookup, claim, metadata):
        """Whether ``claim`` is the live actual permit behind ``metadata``.

        Requires the exact seven known fields, a currently active in-process
        lease on this very permit object for this principal scope and lookup,
        a fresh ``Events.validate_permit`` fence and current permissions, and
        full equality with the freshly derived retained metadata. Booleans,
        serialized claims, other adapters and restarted-owner permits fail.
        """
        try:
            identity = _lookup_identity(lookup)
        except KnowledgeOperationConflict:
            return False
        lease = self._active.get()
        if lease is None or lease.permit is not claim or lease.identity != identity:
            return False
        try:
            # The derived snapshot must still be CLAIMED: that proves the fresh
            # Events.validate_permit fence held under the current permissions.
            return (type(metadata) is dict and metadata.get("phase") == "CLAIMED"
                    and metadata == self.load_original_operation(principal, identity))
        except (PermissionError, ValueError):
            return False

    # -- claim discipline -----------------------------------------------------

    @contextmanager
    def bind_claim(self, principal, lookup, permit):
        """Bind one actual ``claim_phase`` permit for exactly one invocation.

        The permit is validated against the actual Events owner and recorded
        consumed before the lease is yielded, so no failure path can reuse it.
        Nested, concurrent and restarted reuse of the same permit is refused.
        Exiting the block — normally or through an exception — revokes the
        active ``CLAIMED`` phase. No Event is claimed or appended here.
        """
        identity = _lookup_identity(lookup)
        context = self._context(principal, identity["action"], identity["work_ref"])
        scope = context.principal_scope
        with self._lock:
            if self._consumed.get(id(permit)) is not None or self._active.get() is not None:
                raise KnowledgeOperationConflict()
            # Consumed before yield: a later failure can never reuse the permit.
            self._consumed[id(permit)] = permit
        if not self._events.validate_permit(permit, _lookup3(identity), scope,
                                            guard=_ReadGuard(context)):
            raise KnowledgeOperationConflict()
        lease = _ClaimLease(permit, scope, identity, context)
        token = self._active.set(lease)
        try:
            yield self.load_original_operation(principal, identity)
        finally:
            self._active.reset(token)

    # -- retained metadata derivation ----------------------------------------

    def _context(self, principal, action, work_ref):
        if type(action) is not str or action not in _KNOWLEDGE_ACTIONS:
            raise KnowledgeOperationConflict()
        try:
            validate_selection({"work_ref": work_ref})
        except ValueError:
            raise KnowledgeOperationConflict() from None
        return self._contexts.bind(principal, action=action, work_ref=work_ref)

    def _metadata(self, identity, scope, original, status, context):
        self._check_original(identity, scope, original)
        planned = original["publication_binding"]
        phase, publication, proposal = self._phase(identity, planned, status, context)
        return _detached({
            "schema": KNOWLEDGE_METADATA_SCHEMA,
            "identity": dict(identity) | {"principal_scope": scope},
            "recipe_fingerprint_sha256": original["recipe_fingerprint_sha256"],
            "permission_binding_digest": original["permission_binding_digest"],
            "phase": phase,
            "expected_commit": planned["expected_commit"],
            "postimages": planned["postimages"],
            "branch": planned["branch"],
            "publication": publication,
            "proposal": proposal,
        })

    @staticmethod
    def _check_original(identity, scope, original):
        if (type(original) is not dict
                or original.get("schema") != _EVENT_SCHEMA
                or original.get("kind") != "INTENT"
                or original.get("identity")
                != {key: identity[key] for key in _IDENTITY3_KEYS} | {"principal_scope": scope}
                or original.get("request_sha256") != identity["request_sha256"]):
            raise KnowledgeOperationConflict()
        for key in ("recipe_fingerprint_sha256", "permission_binding_digest"):
            _hex64(original.get(key))
        binding = original.get("lookup_binding")
        if (type(binding) is not dict or set(binding) != _LOOKUP7_KEYS
                or any(binding[key] != identity[key] for key in _LOOKUP7_KEYS)):
            raise KnowledgeOperationConflict()
        if (type(original.get("publication_binding")) is not dict
                or set(original["publication_binding"]) != {"expected_commit", "postimages", "branch"}
                or type(original["publication_binding"].get("branch")) not in (str, type(None))):
            raise KnowledgeOperationConflict()
        _hex40(original["publication_binding"]["expected_commit"])
        if original["publication_binding"]["expected_commit"] != identity["source_commit"]:
            raise KnowledgeOperationConflict()
        images = original["publication_binding"]["postimages"]
        if (type(images) is not list or len(images) != 2
                or len({item.get("path") for item in images}) != 2):
            raise KnowledgeOperationConflict()
        for item in images:
            if (type(item) is not dict
                    or set(item) != {"path", "content_sha256", "expected_preimage_sha256"}
                    or type(item["path"]) is not str or not item["path"]):
                raise KnowledgeOperationConflict()
            _hex64(item["content_sha256"])
            if item["expected_preimage_sha256"] is not None:
                _hex64(item["expected_preimage_sha256"])

    def _phase(self, identity, planned, status, status_context):
        if status.get("disposition") == "refused":
            if status.get("reason") != "NOT_DISPATCHED" or status.get("receipt") is not None:
                raise KnowledgeOperationConflict()
            return "NOT_DISPATCHED", None, None
        receipt = status.get("receipt")
        if type(receipt) is not dict or status.get("phase") != "PUBLICATION":
            raise KnowledgeOperationConflict()
        kind = receipt.get("kind")
        if kind == "SOURCE_OBSERVED":
            return "SOURCE_PUBLISHED", self._source_proof(planned, receipt), None
        if kind == "PROPOSAL_OBSERVED":
            proposal = receipt.get("proposal")
            if (type(proposal) is not dict or planned["branch"] is None
                    or proposal.get("head_branch") != planned["branch"]):
                raise KnowledgeOperationConflict()
            return "PROPOSAL_PUBLISHED", None, _detached(proposal)
        if kind not in ("INTENT", "PHASE_ATTEMPTED"):
            raise KnowledgeOperationConflict()
        return self._claim_phase(identity, status_context), None, None

    @staticmethod
    def _source_proof(planned, receipt):
        """Both planned postimages in one actual same Macro commit, or conflict."""
        sources = receipt.get("sources")
        if (type(sources) is not list or len(sources) != 2
                or any(type(item) is not dict or item.get("repository") != "macro"
                       for item in sources)):
            raise KnowledgeOperationConflict()
        commits = {item.get("commit") for item in sources}
        if len(commits) != 1:
            raise KnowledgeOperationConflict()
        _hex40(next(iter(commits)))
        images = planned["postimages"]
        if ({(item["path"], item["content_sha256"]) for item in sources}
                != {(item["path"], item["content_sha256"]) for item in images}):
            raise KnowledgeOperationConflict()
        return {"repository": _PUBLICATION_REPOSITORY, "commit": next(iter(commits)),
                "postimages": [{"path": item["path"], "content_sha256": item["content_sha256"]}
                               for item in images]}

    def _claim_phase(self, identity, context):
        """``CLAIMED`` only under an active lease whose permit still fences.

        The fence runs under the caller's fresh bound context, so a grant
        rotated or revoked after the bind revokes the live claim immediately.
        The ``STARTED`` rung is part of the closed metadata enum but carries no
        actual Events proof this adapter can retain, so it is never derived.
        """
        lease = self._active.get()
        if lease is not None and lease.identity == identity:
            if self._events.validate_permit(lease.permit, _lookup3(identity),
                                            lease.scope, guard=_ReadGuard(context)):
                return "CLAIMED"
        return "UNKNOWN"
