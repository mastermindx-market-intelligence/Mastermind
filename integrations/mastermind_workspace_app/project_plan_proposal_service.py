"""Single-phase PLAN-proposal source owner over the incumbent Events/Git owners.

This is the distinct ``publish_project_plan_proposal`` action beside the
accepted ADOPT owner; the normal CREATE and ADOPT actions are unchanged.  The
installed source factory supplies fixed qualified captured basis/result, the
actor and the reserved-boundary qualification.  Their callbacks are mandatory
host composition, never public selectors or grants: no public read, submit,
status or reconcile can supply a recipe, actor, basis snapshot, filesystem
path, principal scope or publication proof.

A fresh preparation requires a live canonical PLAN basis and a live qualified
S19 planning result; both are re-checked before and after the private freeze.
The closed recipe compiler alone decides DRAFT_ONLY versus NO_PROPOSAL, so a
clarify or plain-text result never becomes a PLAN and never writes an Event,
private input or publisher call.  Restoration is only for the existing owner
after verified original-input custody and committed digest.  After the source
publication the canonical workstream has changed, so reconciliation belongs to
this original operation and never re-captures the old current source.

One bounded integration dependency is parent-owned because it is an existing
shared module: the incumbent ``workspace_source_operation_contract`` lookup
grammar must recognize this action (the same registration ``ADOPT_PLAN``
already has).  Until that registration is installed this owner fails closed on
every public method with ``invalid_source_operation`` and never writes.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from common.workspace_source_operation_contract import validate_lookup
from control_plane.project_plan_canonical_basis import CanonicalProjectPlanBasis
from control_plane.project_plan_proposal_git import (
    ACTION,
    BINDING_SCHEMA,
    SCHEMA as PUBLICATION_SCHEMA,
    validate_request,
)
from control_plane.project_plan_proposal_operation import (
    PlanProposalOperationError,
    PlanProposalRecipeAdapter,
)
from control_plane.project_plan_result_source import QualifiedPlanningResult
from control_plane.project_source_original_input import ProjectSourceOriginalInput
from control_plane.workspace_project_git_publisher import FixedProjectGitPublisher, PublisherBinding
from control_plane.workspace_source_operations import SourceOperationEvents, SourceOperationConflict
from integrations.mastermind_workspace_app.source_operation_context import WorkspaceSourceOperationContextFactory
from integrations.mastermind_workspace_app.source_operation_principal import source_principal_scope

PHASE = "PUBLICATION"


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _require_effect_outside_read():
    # A caller's enclosing capture survives our nested pure scopes. It can
    # only remove the right to mutate; it never supplies an effect grant.
    from control_plane.project_canonical_data import _CAPTURE
    if _CAPTURE.get() is not None:
        raise PermissionError("SOURCE_OPERATION_EFFECT_DURING_READ")


class ProjectPlanProposalSourceOwner:
    def __init__(self, *, events, private_inputs, permission_factory, adapter,
                 capture_basis, capture_result, actor_for, qualify_recipe,
                 publisher_binding, qualify_publisher, pr_owner):
        from integrations.mastermind_workspace_app.project_journey_recipes import InstalledProjectPlanProposalRecipeAdapter
        if (type(events) is not SourceOperationEvents or type(private_inputs) is not ProjectSourceOriginalInput
                or private_inputs.supervisor.runtime.store is not events.store
                or type(permission_factory) is not WorkspaceSourceOperationContextFactory
                or type(adapter) not in (PlanProposalRecipeAdapter, InstalledProjectPlanProposalRecipeAdapter) or adapter.action != ACTION
                or type(publisher_binding) is not PublisherBinding
                or not all(callable(fn) for fn in (capture_basis, capture_result, actor_for,
                                                   qualify_recipe, qualify_publisher))):
            raise ValueError("fixed plan proposal owners required")
        self._events, self._private, self._permissions, self._adapter = events, private_inputs, permission_factory, adapter
        self._basis, self._result, self._actor, self._qualify_recipe = capture_basis, capture_result, actor_for, qualify_recipe
        self._binding, self._qualifier, self._pr_owner = publisher_binding, qualify_publisher, pr_owner

    @staticmethod
    def _lookup(request_id, work_ref):
        return validate_lookup({"schema": "mastermind.workspace_source_operation_lookup.v1",
            "action": ACTION, "request_id": request_id, "work_ref": work_ref})

    def _selection(self, lookup):
        selected = validate_lookup(lookup)
        if selected["action"] != ACTION:
            raise SourceOperationConflict()
        return selected

    def _permission(self, principal, selected):
        return self._permissions.bind(principal, action=ACTION, work_ref=selected["work_ref"])

    def _qualified(self, principal, prepared, recipe, permission):
        try:
            allowed = (permission.check() is True
                and self._qualify_recipe(principal, prepared, deepcopy(recipe), PHASE) is True
                and permission.check() is True)
        except Exception:
            allowed = False
        if not allowed:
            raise PermissionError("SOURCE_OPERATION_RECIPE_UNQUALIFIED")

    def _captured(self, request, principal, permission):
        """Nominal live basis and result under the actual verified principal."""
        if permission.check() is not True:
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        try:
            basis = self._basis(deepcopy(request), principal)
            result = self._result(deepcopy(request), principal)
        except Exception:
            raise ValueError("SOURCE_OPERATION_SOURCE_UNAVAILABLE") from None
        if (type(basis) is not CanonicalProjectPlanBasis or type(result) is not QualifiedPlanningResult
                or permission.check() is not True):
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        return basis, result

    def _joins(self, request, selected, basis, result, *, observation=None):
        """Exact request join onto the actual basis and terminal result."""
        try:
            if observation is None:
                data, _ = result._consumed_material()
            else:
                from control_plane.project_plan_result_source import _ConsumedPlanningObservation
                if type(observation) is not _ConsumedPlanningObservation:
                    raise SourceOperationConflict()
                data = observation.material(result)
            material = basis.material()
            if (data["selection"] != request["selection"] or data["result_digest"] != request["result_digest"]
                    or material["work_ref"] != request["work_ref"]
                    or material["base_source"] != request["base_source"]
                    or material["base_adoption"] != request["expected_adoption"]
                    or material["source"]["commit"] != request["expected_commit"]):
                raise SourceOperationConflict()
        except SourceOperationConflict:
            raise
        except Exception:
            raise ValueError("SOURCE_OPERATION_SOURCE_UNAVAILABLE") from None
        return data, material

    @staticmethod
    def _proposal_snapshot(basis, request_id):
        try:
            return basis.proposal_snapshot(request_id=request_id)
        except Exception:
            raise ValueError("SOURCE_OPERATION_SOURCE_UNAVAILABLE") from None

    @staticmethod
    def _binding_for(recipe, snapshot):
        """Exact planned CAS postimages: create-only PLAN plus guarded WS.

        The compiler may omit an unchanged workstream edit; the binding must
        still guard the exact current workstream bytes it was qualified over,
        taken from the same frozen basis snapshot, never from live re-reads.
        """
        images = [{"path": edit["path"], "content_sha256": edit["content_sha256"],
                   "expected_preimage_sha256": edit["expected_sha256"]} for edit in recipe["edits"]]
        proposal = "research/project-plans/PLAN-" + recipe["work_ref"][3:] + "-" + recipe["request_id"][-40:] + ".md"
        workstream = "agentos/workstreams/WS-" + recipe["work_ref"][3:] + ".md"
        if not any(image["path"] == workstream for image in images):
            capture = snapshot["workstream"]
            raw = capture["raw_bytes"]
            if (type(raw) is not bytes or capture["source"]["path"] != workstream
                    or capture["source"]["commit"] != recipe["expected_commit"]
                    or capture["source"]["content_sha256"] != _sha(raw)):
                raise SourceOperationConflict()
            images.insert(0, {"path": workstream, "content_sha256": _sha(raw),
                              "expected_preimage_sha256": _sha(raw)})
        if len(images) != 2 or {image["path"] for image in images} != {proposal, workstream}:
            raise SourceOperationConflict()
        for image in images:
            if image["path"] == proposal:
                if image["expected_preimage_sha256"] is not None:
                    raise SourceOperationConflict()
            elif not (type(image["expected_preimage_sha256"]) is str and len(image["expected_preimage_sha256"]) == 64):
                raise SourceOperationConflict()
        return {"expected_commit": recipe["expected_commit"], "postimages": images, "branch": None}

    def prepare(self, request, principal):
        return self._prepare(request, principal)

    def prepare_qualified(self, request, principal, *, basis, result):
        """Private SAME-S19 invocation join; public source prepare never supplies this."""
        if (type(basis) is not CanonicalProjectPlanBasis or type(result) is not QualifiedPlanningResult
                or result._source.material()["publication"]["principal_scope"] != source_principal_scope(principal)):
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        return self._prepare(request, principal, qualified=(basis,result))

    def _prepare(self, request, principal, *, qualified=None):
        request = validate_request(request)
        selected = self._lookup(request.get("request_id"), request.get("work_ref"))
        permission = self._permission(principal, selected)
        original = self._events.original(selected, permission.principal_scope, guard=permission.check)
        if original is not None:
            if (original["request_sha256"] != _sha(_canonical(request))
                    or original["permission_binding_digest"] != permission.permission_binding_digest):
                raise SourceOperationConflict()
            prepared, _ = self._restore(selected, permission)
            recipe = self._adapter.recipe(prepared)
            self._qualified(principal, prepared, recipe, permission)
        else:
            basis, result = self._captured(request, principal, permission) if qualified is None else qualified
            recovered = self._private.lookup_original(selected, permission.principal_scope, guard=permission.check)
            from integrations.mastermind_workspace_app.project_journey_recipes import InstalledProjectPlanProposalRecipeAdapter
            scope = (result._consumed_observation if type(self._adapter) is InstalledProjectPlanProposalRecipeAdapter
                     else result.read_scope)
            with basis._view.capture_scope(), scope() as observation:
                self._joins(request, selected, basis, result, observation=observation)
                if recovered is not None:
                    # A committed private original can precede INTENT when its
                    # response was lost. Recover those exact bytes/stamp;
                    # never recapture the actor/clock or invent another key.
                    if (recovered["request_sha256"] != _sha(_canonical(request))
                            or recovered["permission_binding_digest"] != permission.permission_binding_digest):
                        raise SourceOperationConflict()
                    prepared = self._adapter.restore(private_payload=recovered["private_payload"],
                        trusted_recipe_fingerprint=recovered["recipe_fingerprint_sha256"])
                else:
                    snapshot = self._proposal_snapshot(basis, selected["request_id"])
                    try:
                        actor = self._actor(principal)
                    except Exception:
                        raise ValueError("SOURCE_OPERATION_ACTOR_UNAVAILABLE") from None
                    if observation is None:
                        prepared = self._adapter.prepare(request=request, initial_snapshot=snapshot,
                            actor=actor, qualified_result=result)
                    else:
                        prepared = self._adapter._prepare_observed(request=request, initial_snapshot=snapshot,
                            actor=actor, qualified_result=result, observation=observation)
                    if prepared is None:
                        # Clarify/plain results have no private original or Event.
                        raise PlanProposalOperationError("PLAN_PROPOSAL_NOT_PREPARED")
                try:
                    basis.check()
                except Exception:
                    raise ValueError("SOURCE_OPERATION_SOURCE_UNAVAILABLE") from None
                recipe = self._adapter.recipe(prepared)
                self._qualified(principal, prepared, recipe, permission)
                # Contiguous pure requalification stays inside this same
                # original basis/result bracket, in its existing check order.
                basis.check()
                result._consumed_material()
                if permission.check() is not True:
                    raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        # The private envelope carries the same exact permission binding
        # identity the Event records, so later recovery compares one stamp.
        _require_effect_outside_read()
        ref = self._private.prepare(selected, permission.principal_scope,
            payload=prepared.private_payload(), trusted_recipe_fingerprint=prepared.fingerprint_sha256,
            permission_binding_digest=permission.permission_binding_digest)
        if ref is None:
            raise SourceOperationConflict()
        if original is None:
            # A second pure fence after private retention, before INTENT.
            with basis._view.capture_scope(), result.read_scope():
                basis.check()
                result._consumed_material()
        public_sha, original_input = _sha(_canonical(request)), ref.to_dict()
        _require_effect_outside_read()
        self._events.prepare(selected, permission.principal_scope, request_sha256=public_sha,
            recipe_fingerprint_sha256=prepared.fingerprint_sha256, original_input=original_input,
            permission_binding_digest=permission.permission_binding_digest, guard=permission.check,
            publication_binding=self._binding_for(recipe, prepared.private_payload()["initial_snapshot"]["snapshot"]))
        if permission.check() is not True:
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        preview = {"schema": "mastermind.project_plan_proposal_preview.v1", "work_ref": recipe["work_ref"],
            "status": recipe["status"], "expected_commit": recipe["expected_commit"],
            "expected_adoption": recipe["base_adoption"], "proposal_id": recipe["proposal_id"],
            "proposal_path": recipe["proposal_path"], "candidate_sha256": recipe["candidate_sha256"],
            "base_source": deepcopy(recipe["base_source"]), "result_digest": request["result_digest"],
            "edited_paths": [edit["path"] for edit in recipe["edits"]]}
        return {"schema": "mastermind.workspace_source_operation_preview.v1",
            "selection": {k: selected[k] for k in ("action", "request_id", "work_ref")},
            "owner_context": {"principal_scope": permission.principal_scope}, "request_sha256": public_sha,
            "recipe_fingerprint_sha256": prepared.fingerprint_sha256,
            "preview_witness": {"original_input": original_input,
                                "recipe_fingerprint_sha256": prepared.fingerprint_sha256},
            "preview": preview}

    def read_status(self, lookup, principal):
        selected = self._selection(lookup)
        permission = self._permission(principal, selected)
        return self._events.read_status(selected, permission.principal_scope, guard=permission.check)

    def _restore(self, selected, permission):
        original = self._events.original(selected, permission.principal_scope, guard=permission.check)
        if original is None:
            raise SourceOperationConflict()
        if original.get("permission_binding_digest") != permission.permission_binding_digest:
            raise SourceOperationConflict()
        payload = self._private.read(selected, permission.principal_scope,
            original_input=original["original_input"], trusted_recipe_fingerprint=original["recipe_fingerprint_sha256"],
            trusted_request_sha256=original["request_sha256"])
        prepared = self._adapter.restore(private_payload=payload,
            trusted_recipe_fingerprint=original["recipe_fingerprint_sha256"])
        if self._lookup(payload["request"]["request_id"], payload["request"]["work_ref"]) != selected:
            raise SourceOperationConflict()
        return prepared, original

    def _publisher(self, selected, principal, permission, *, prepared=None, recipe=None):
        scope = permission.principal_scope
        def authorized(who, work):
            if work != selected["work_ref"] or source_principal_scope(who) != scope or permission.check() is not True:
                return False
            # Writes recheck the actual recipe/reserved-boundary owner too.
            # Observation-only recovery deliberately needs no fresh source.
            if prepared is not None:
                try:
                    return (recipe is not None and self._qualify_recipe(who, prepared, deepcopy(recipe), PHASE) is True
                            and permission.check() is True)
                except Exception:
                    return False
            return True
        def load(who, lookup, selected_phase):
            if lookup != selected or selected_phase != PHASE or not authorized(who, lookup["work_ref"]):
                raise SourceOperationConflict()
            original = self._events.original(selected, scope, guard=permission.check)
            binding = self._events.publication_binding(selected, scope, phase=PHASE, guard=permission.check)
            if original is None or binding is None:
                return None
            return {"schema": BINDING_SCHEMA, "selection": deepcopy(selected), "principal_scope": scope,
                **{k: original[k] for k in ("request_sha256", "recipe_fingerprint_sha256",
                                            "permission_binding_digest")},
                "phase": PHASE, "publication_binding": binding}
        def validate(who, lookup, permit, metadata):
            return authorized(who, lookup["work_ref"]) and metadata["phase"] == PHASE and self._events.validate_permit(
                permit, selected, scope, guard=permission.check)
        def unavailable(*args):
            raise SourceOperationConflict()
        return FixedProjectGitPublisher(self._binding, unavailable, lambda _: False, unavailable,
            self._qualifier, self._pr_owner, principal_scope=source_principal_scope,
            authorize_plan_proposal=authorized,
            plan_proposal_permission_stamp=lambda who, work: permission.permission_binding_digest if authorized(who, work) else "",
            load_plan_proposal_operation=load, validate_plan_proposal_claim=validate)

    def _retain(self, selected, permission, phase, result):
        if (type(result) is not dict or result.get("schema") != PUBLICATION_SCHEMA
                or result.get("selection") != selected or result.get("phase") != phase):
            raise SourceOperationConflict()
        original = self._events.original(selected, permission.principal_scope, guard=permission.check)
        if original is None or result.get("recipe_fingerprint_sha256") != original["recipe_fingerprint_sha256"]:
            raise SourceOperationConflict()
        sources, proposal = [], result.get("proposal")
        if result.get("state") == "SOURCE_PUBLISHED":
            source = result.get("source")
            binding = self._events.publication_binding(selected, permission.principal_scope, phase=phase,
                                                       guard=permission.check)
            expected = [{"path": image["path"], "content_sha256": image["content_sha256"]}
                        for image in binding["postimages"]]
            if (type(source) is not dict or source.get("repository") != "mastermindx-market-intelligence/macro"
                    or source.get("postimages") != expected):
                raise SourceOperationConflict()
            # The shared public wire uses the fixed short repository name.
            sources = [{"repository": "macro", "commit": source["commit"], **image} for image in expected]
            proposal = None
        elif result.get("state") != "PROPOSAL_PUBLISHED":
            # Unknown or refused publisher rungs stay unresolved; only genuine
            # typed publication evidence is ever retained here.
            return
        evidence = deepcopy({"sources": sources, "proposal": proposal})
        self._events.retain_observation(selected, permission.principal_scope, phase=phase,
            sources=sources, proposal=proposal, guard=permission.check,
            qualify_observation=lambda payload: permission.check() is True
                and payload["sources"] == evidence["sources"] and payload["proposal"] == evidence["proposal"])

    def _finish(self, selected, permission, permit, result):
        if result.get("state") == "NOT_DISPATCHED":
            self._events.retain_no_effect(permit, selected, permission.principal_scope,
                qualify_no_effect=lambda: result.get("schema") == PUBLICATION_SCHEMA
                    and result.get("source") is None and result.get("proposal") is None,
                guard=permission.check)
        else:
            self._retain(selected, permission, PHASE, result)
        return self._events.read_status(selected, permission.principal_scope, guard=permission.check)

    def submit(self, *, lookup, preview_witness, principal):
        selected = self._selection(lookup)
        permission = self._permission(principal, selected)
        # Retained actual Events state first, as the accepted Knowledge owner
        # reads it: once the PLAN changed the canonical source, a repeated
        # submit returns the original observed/attempted status.  It never
        # restores the frozen compiler, re-qualifies against the old basis or
        # reaches the publisher again.  Only a fresh INTENT (or no receipt
        # yet) keeps the existing grant/claim path below.
        retained = self._events.read_status(selected, permission.principal_scope, guard=permission.check)
        receipt = retained["receipt"]
        if (retained["disposition"] in ("accepted", "refused")
                or (receipt is not None and receipt["kind"] != "INTENT")):
            return retained
        prepared, _ = self._restore(selected, permission)
        recipe = self._adapter.recipe(prepared)
        self._qualified(principal, prepared, recipe, permission)
        permit = self._events.claim_phase(selected, permission.principal_scope,
            permission_binding_digest=permission.permission_binding_digest,
            preview_witness=preview_witness, guard=permission.check)
        if permit is None:
            return self._events.read_status(selected, permission.principal_scope, guard=permission.check)
        # Proven pre-publisher failure (before the publisher call) may retain
        # no effect.  Once publish_plan_proposal is invoked, any exception is
        # post-invocation and uncertain: it can never claim no effect and is
        # never retried, so only the observed owner status is returned.
        invoked = False
        try:
            request = prepared.private_payload()["request"]
            publisher = self._publisher(selected, principal, permission, prepared=prepared, recipe=recipe)
            invoked = True
            result = publisher.publish_plan_proposal(request, recipe, principal, claim=permit)
        except Exception:
            if not invoked:
                self._events.retain_no_effect(permit, selected, permission.principal_scope,
                    qualify_no_effect=lambda: not invoked,
                    guard=permission.check)
            return self._events.read_status(selected, permission.principal_scope, guard=permission.check)
        return self._finish(selected, permission, permit, result)

    def reconcile(self, lookup, principal):
        """Explicit Check: observe the original publication, append only
        qualified evidence.  Never re-captures the current source, never
        recompiles and never starts or retries an effect."""
        selected = self._selection(lookup)
        permission = self._permission(principal, selected)
        retained = self._events.read_status(selected, permission.principal_scope, guard=permission.check)
        if (retained["disposition"] == "accepted" or retained["reason"] == "READY_FOR_ADVANCE"
                or retained["receipt"] is None):
            return retained
        phase = retained["phase"]
        if phase != PHASE or retained["receipt"]["kind"] == "INTENT":
            return retained
        result = self._publisher(selected, principal, permission).reconcile_plan_proposal(selected, principal)
        self._retain(selected, permission, phase, result)
        return self._events.read_status(selected, permission.principal_scope, guard=permission.check)
