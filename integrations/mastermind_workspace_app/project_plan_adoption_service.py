"""Actual two-phase ADOPT action over incumbent Events/private/Git owners.

The installed source factory supplies fixed qualified captured snapshots,
actor and reserved-boundary qualification. Their callbacks are mandatory, not
public selectors or grants. No public read/submit/status can supply a recipe,
actor, filesystem path, principal scope or publication proof.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from common.workspace_source_operation_contract import validate_lookup, validate_advance
from control_plane.project_plan_adoption_operation import PlanAdoptionRecipeAdapter, adoption_snapshot_material
from control_plane.project_source_original_input import ProjectSourceOriginalInput
from control_plane.workspace_source_operations import SourceOperationEvents, SourceOperationConflict
from control_plane.workspace_project_git_publisher import FixedProjectGitPublisher, PublisherBinding
from control_plane.project_plan_adoption_git import BINDING_SCHEMA, SCHEMA as PUBLICATION_SCHEMA, validate_adoption_request
from integrations.mastermind_workspace_app.source_operation_context import WorkspaceSourceOperationContextFactory
from integrations.mastermind_workspace_app.source_operation_principal import source_principal_scope

ACTION = "ADOPT_PLAN"


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ProjectPlanAdoptionSourceOwner:
    def __init__(self, *, events, private_inputs, permission_factory, adapter,
                 capture_snapshot, actor_for, qualify_recipe,
                 publisher_binding, qualify_publisher, pr_owner):
        from integrations.mastermind_workspace_app.installed_plan_adoption import InstalledPlanAdoptionRecipeAdapter
        if (type(events) is not SourceOperationEvents or type(private_inputs) is not ProjectSourceOriginalInput
                or private_inputs.supervisor.runtime.store is not events.store
                or type(permission_factory) is not WorkspaceSourceOperationContextFactory
                or type(adapter) not in (PlanAdoptionRecipeAdapter, InstalledPlanAdoptionRecipeAdapter)
                or type(publisher_binding) is not PublisherBinding
                or not all(callable(fn) for fn in (capture_snapshot, actor_for, qualify_recipe, qualify_publisher))):
            raise ValueError("fixed plan adoption owners required")
        self._events, self._private, self._permissions, self._adapter = events, private_inputs, permission_factory, adapter
        self._capture, self._actor, self._qualify_recipe = capture_snapshot, actor_for, qualify_recipe
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

    def _qualified(self, principal, prepared, recipe, phase, permission):
        try:
            allowed = (permission.check() is True
                and self._qualify_recipe(principal, prepared, deepcopy(recipe), phase) is True
                and permission.check() is True)
        except Exception:
            allowed = False
        if not allowed:
            raise PermissionError("SOURCE_OPERATION_RECIPE_UNQUALIFIED")

    def _snapshot(self, request, principal, phase, permission):
        if permission.check() is not True:
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        try:
            snapshot = self._capture(deepcopy(request), principal, phase)
        except Exception:
            raise ValueError("SOURCE_OPERATION_SOURCE_UNAVAILABLE") from None
        if permission.check() is not True:
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        return snapshot

    @staticmethod
    def _binding_for(recipe, *, current_snapshot=None):
        images = [{"path": e["path"], "content_sha256": e["content_sha256"],
                   "expected_preimage_sha256": e["expected_sha256"]} for e in recipe["edits"]]
        if recipe["phase"] == "CANDIDATE" and not images:
            source = recipe["candidate_source"]
            if source is None or source["path"] != recipe["candidate_path"] or source["content_sha256"] != recipe["candidate_sha256"]:
                raise SourceOperationConflict()
            images = [{"path": source["path"], "content_sha256": source["content_sha256"],
                       "expected_preimage_sha256": source["content_sha256"]}]
        if recipe["phase"] == "ADOPTION_DECISION":
            ws_path = "agentos/workstreams/" + recipe["work_ref"].replace(":", "-", 1) + ".md"
            if not any(i["path"] == ws_path for i in images):
                if current_snapshot is None:
                    raise SourceOperationConflict()
                capture = adoption_snapshot_material(current_snapshot)["workstream"]
                raw = capture["raw_bytes"]
                if (type(raw) is not bytes or capture["source"]["path"] != ws_path
                        or _sha(raw) != recipe["candidate_sha256"]
                        or capture["source"]["content_sha256"] != _sha(raw)):
                    raise SourceOperationConflict()
                images.insert(0, {"path": ws_path, "content_sha256": _sha(raw), "expected_preimage_sha256": _sha(raw)})
        return {"expected_commit": recipe["expected_commit"], "postimages": images, "branch": None}

    def prepare(self, request, principal):
        request = validate_adoption_request(request)
        selected = self._lookup(request.get("request_id"), request.get("work_ref"))
        permission = self._permission(principal, selected)
        original = self._events.original(selected, permission.principal_scope, guard=permission.check)
        retained = None
        if original is not None:
            if (original["request_sha256"] != _sha(_canonical(request))
                    or original["permission_binding_digest"] != permission.permission_binding_digest):
                raise SourceOperationConflict()
            prepared, _ = self._restore(selected, permission)
        else:
            retained = self._private.lookup_original(selected, permission.principal_scope, guard=permission.check)
            if retained is not None:
                if (retained["request_sha256"] != _sha(_canonical(request))
                        or retained["permission_binding_digest"] != permission.permission_binding_digest):
                    raise SourceOperationConflict()
                prepared = self._adapter.restore(private_payload=retained["private_payload"],
                    trusted_recipe_fingerprint=retained["recipe_fingerprint_sha256"])
            else:
                snapshot = self._snapshot(request, principal, "CANDIDATE", permission)
                try:
                    actor = self._actor(principal, deepcopy(request), deepcopy(snapshot))
                except Exception:
                    raise ValueError("SOURCE_OPERATION_ACTOR_UNAVAILABLE") from None
                prepared = self._adapter.prepare(request=request, initial_snapshot=snapshot, actor=actor)
        recipe = self._adapter.candidate_recipe(prepared)
        self._qualified(principal, prepared, recipe, "CANDIDATE", permission)
        if original is not None:
            original_input = original["original_input"]
        elif retained is not None:
            original_input = retained["original_input"]
        else:
            ref = self._private.prepare(selected, permission.principal_scope,
                payload=prepared.private_payload(), trusted_recipe_fingerprint=prepared.fingerprint_sha256,
                permission_binding_digest=permission.permission_binding_digest)
            if ref is None:
                raise SourceOperationConflict()
            original_input = ref.to_dict()
        public_sha = _sha(_canonical(request))
        self._events.prepare(selected, permission.principal_scope, request_sha256=public_sha,
            recipe_fingerprint_sha256=prepared.fingerprint_sha256, original_input=original_input,
            permission_binding_digest=permission.permission_binding_digest, guard=permission.check,
            publication_binding=self._binding_for(recipe))
        if permission.check() is not True:
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        preview = {"schema": "mastermind.project_plan_adoption_preview.v1", "work_ref": recipe["work_ref"],
            "expected_commit": recipe["expected_commit"], "expected_adoption": recipe["expected_adoption"],
            "candidate_sha256": recipe["candidate_sha256"],
            "changed_frontmatter_fields": recipe["preview"]["changed_frontmatter_fields"],
            "record_body_changed": recipe["preview"]["record_body_changed"]}
        return {"schema": "mastermind.workspace_source_operation_preview.v1",
            "selection": {k: selected[k] for k in ("action", "request_id", "work_ref")},
            "owner_context": {"principal_scope": permission.principal_scope}, "request_sha256": public_sha,
            "recipe_fingerprint_sha256": prepared.fingerprint_sha256,
            "preview_witness": {"original_input": original_input, "recipe_fingerprint_sha256": prepared.fingerprint_sha256},
            "preview": preview}

    def read_status(self, lookup, principal):
        selected = self._selection(lookup)
        permission = self._permission(principal, selected)
        return self._events.read_status(selected, permission.principal_scope, guard=permission.check)

    def _restore(self, selected, permission):
        original = self._events.original(selected, permission.principal_scope, guard=permission.check)
        if original is None:
            raise SourceOperationConflict()
        payload = self._private.read(selected, permission.principal_scope,
            original_input=original["original_input"], trusted_recipe_fingerprint=original["recipe_fingerprint_sha256"],
            trusted_request_sha256=original["request_sha256"])
        prepared = self._adapter.restore(private_payload=payload,
            trusted_recipe_fingerprint=original["recipe_fingerprint_sha256"])
        if self._lookup(payload["request"]["request_id"], payload["request"]["work_ref"]) != selected:
            raise SourceOperationConflict()
        return prepared, original

    def _publisher(self, selected, principal, permission, phase, *, prepared=None, recipe=None):
        scope = permission.principal_scope
        def authorized(who, work):
            if work != selected["work_ref"] or source_principal_scope(who) != scope or permission.check() is not True:
                return False
            # Writes recheck the actual recipe/reserved-boundary owner too.
            # Observation-only recovery deliberately needs no fresh source.
            if prepared is not None:
                try:
                    return (recipe is not None and self._qualify_recipe(who, prepared, deepcopy(recipe), phase) is True
                            and permission.check() is True)
                except Exception:
                    return False
            return True
        def load(who, lookup, selected_phase):
            if lookup != selected or selected_phase != phase or not authorized(who, lookup["work_ref"]):
                raise SourceOperationConflict()
            original = self._events.original(selected, scope, guard=permission.check)
            binding = self._events.publication_binding(selected, scope, phase=phase, guard=permission.check)
            if original is None or binding is None:
                return None
            return {"schema": BINDING_SCHEMA, "selection": deepcopy(selected), "principal_scope": scope,
                **{k: original[k] for k in ("request_sha256", "recipe_fingerprint_sha256", "permission_binding_digest")},
                "phase": phase, "publication_binding": binding}
        def validate(who, lookup, permit, metadata):
            return authorized(who, lookup["work_ref"]) and metadata["phase"] == phase and self._events.validate_permit(
                permit, selected, scope, guard=permission.check)
        def unavailable(*args):
            raise SourceOperationConflict()
        return FixedProjectGitPublisher(self._binding, unavailable, lambda _: False, unavailable,
            self._qualifier, self._pr_owner, principal_scope=source_principal_scope,
            authorize_plan_adoption=authorized,
            plan_adoption_permission_stamp=lambda who, work: permission.permission_binding_digest if authorized(who, work) else "",
            load_plan_adoption_operation=load, validate_plan_adoption_claim=validate)

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
            binding = self._events.publication_binding(selected, permission.principal_scope, phase=phase, guard=permission.check)
            expected = [{"path": i["path"], "content_sha256": i["content_sha256"]} for i in binding["postimages"]]
            if (type(source) is not dict or source.get("repository") != "mastermindx-market-intelligence/macro"
                    or source.get("postimages") != expected):
                raise SourceOperationConflict()
            # The shared public wire uses the fixed short repository name.
            sources = [{"repository": "macro", "commit": source["commit"], **image} for image in expected]
            proposal = None
        elif result.get("state") != "PROPOSAL_PUBLISHED":
            return
        evidence = deepcopy({"sources": sources, "proposal": proposal})
        self._events.retain_observation(selected, permission.principal_scope, phase=phase,
            sources=sources, proposal=proposal, guard=permission.check,
            qualify_observation=lambda payload: permission.check() is True
                and payload["sources"] == evidence["sources"] and payload["proposal"] == evidence["proposal"])

    def _finish(self, selected, permission, phase, permit, result):
        if result.get("state") == "NOT_DISPATCHED":
            if phase == "CANDIDATE":
                self._events.retain_no_effect(permit, selected, permission.principal_scope,
                    qualify_no_effect=lambda: result.get("schema") == PUBLICATION_SCHEMA
                        and result.get("source") is None and result.get("proposal") is None,
                    guard=permission.check)
            # A refused later phase cannot erase its already observed candidate.
            # Keep the existing original unresolved; never claim overall no-effect.
        else:
            self._retain(selected, permission, phase, result)
        return self._events.read_status(selected, permission.principal_scope, guard=permission.check)

    def submit(self, *, lookup, preview_witness, principal):
        selected = self._selection(lookup)
        permission = self._permission(principal, selected)
        prepared, _ = self._restore(selected, permission)
        recipe = self._adapter.candidate_recipe(prepared)
        self._qualified(principal, prepared, recipe, "CANDIDATE", permission)
        permit = self._events.claim_phase(selected, permission.principal_scope,
            permission_binding_digest=permission.permission_binding_digest, preview_witness=preview_witness, guard=permission.check)
        if permit is None:
            return self._events.read_status(selected, permission.principal_scope, guard=permission.check)
        result = self._publisher(selected, principal, permission, "CANDIDATE", prepared=prepared, recipe=recipe).publish_plan_adoption(
            prepared.private_payload()["request"], recipe, principal, phase="CANDIDATE", claim=permit)
        return self._finish(selected, permission, "CANDIDATE", permit, result)

    def reconcile(self, lookup, principal):
        """Explicit Check: observe original phase, append only qualified evidence."""
        selected = self._selection(lookup)
        permission = self._permission(principal, selected)
        retained = self._events.read_status(selected, permission.principal_scope, guard=permission.check)
        if retained["disposition"] == "accepted" or retained["reason"] == "READY_FOR_ADVANCE" or retained["receipt"] is None:
            return retained
        phase = retained["phase"]
        if phase not in ("CANDIDATE", "ADOPTION") or retained["receipt"]["kind"] == "INTENT":
            return retained
        result = self._publisher(selected, principal, permission, phase).reconcile_plan_adoption(selected, principal, phase=phase)
        self._retain(selected, permission, phase, result)
        return self._events.read_status(selected, permission.principal_scope, guard=permission.check)

    def advance(self, request, principal):
        value = validate_advance(request)
        selected = self._selection({"schema": "mastermind.workspace_source_operation_lookup.v1",
            **{k: value[k] for k in ("action", "request_id", "work_ref")}})
        permission = self._permission(principal, selected)
        retained = self._events.read_status(selected, permission.principal_scope, guard=permission.check)
        if retained["disposition"] == "accepted":
            return retained
        if retained["phase"] == "ADOPTION":
            # Actual common owner validates the original candidate witness and
            # returns NO permit for an already attempted phase. No recompile.
            permit = self._events.claim_phase(selected, permission.principal_scope,
                permission_binding_digest=permission.permission_binding_digest,
                phase_receipt_digest=value["phase_receipt_digest"], guard=permission.check)
            if permit is not None:
                raise SourceOperationConflict()
            return self._events.read_status(selected, permission.principal_scope, guard=permission.check)
        if (retained["reason"] != "READY_FOR_ADVANCE" or retained["phase"] != "CANDIDATE"
                or retained["advance"] != {"phase_receipt_digest": value["phase_receipt_digest"]}):
            raise SourceOperationConflict()
        prepared, original = self._restore(selected, permission)
        candidate = self._adapter.candidate_recipe(prepared)
        sources = retained["receipt"]["sources"]
        if (len(sources) != 1 or sources[0]["path"] != candidate["candidate_path"]
                or sources[0]["content_sha256"] != candidate["candidate_sha256"]):
            raise SourceOperationConflict()
        raw = (candidate["edits"][0]["content_utf8"].encode("utf-8") if candidate["edits"] else
               prepared.initial_snapshot()["candidate_target"]["capture"]["raw_bytes"])
        proof = {"schema": "agentos.plan_candidate_publication.v1", "state": "VERIFIED_DEFAULT",
            "request_id": selected["request_id"], "request_sha256": original["recipe_fingerprint_sha256"],
            "source": {**sources[0], "repository": "mastermindx-market-intelligence/macro"}, "raw_bytes": raw}
        current = self._snapshot(prepared.private_payload()["request"], principal, "ADOPTION", permission)
        recipe = self._adapter.decision_recipe(prepared, current_snapshot=current, prior_qualified_publication=proof)
        self._qualified(principal, prepared, recipe, "ADOPTION", permission)
        permit = self._events.claim_phase(selected, permission.principal_scope,
            permission_binding_digest=permission.permission_binding_digest,
            phase_receipt_digest=value["phase_receipt_digest"],
            phase_publication_binding=self._binding_for(recipe, current_snapshot=current), guard=permission.check)
        if permit is None:
            return self._events.read_status(selected, permission.principal_scope, guard=permission.check)
        result = self._publisher(selected, principal, permission, "ADOPTION", prepared=prepared, recipe=recipe).publish_plan_adoption(
            prepared.private_payload()["request"], recipe, principal, phase="ADOPTION", claim=permit)
        return self._finish(selected, permission, "ADOPTION", permit, result)
