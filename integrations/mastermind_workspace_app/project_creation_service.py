"""CREATE composition over the existing Event, private input and Git owners.

The installed factory must supply the qualified captured canonical compiler
adapter, fixed Git publisher binding/qualifier and actual PR owner. No public
request supplies any of those owners. This service never creates a Runtime Job,
session or send target. Canonical source publication is a separate fact from
conversation preparation and execution admission.
"""
from __future__ import annotations

import hashlib
import json

from common.workspace_source_operation_contract import validate_lookup
from control_plane.project_source_original_input import ProjectSourceOriginalInput
from control_plane.workspace_source_operations import SourceOperationEvents, SourceOperationConflict
from control_plane.workspace_project_git_publisher import FixedProjectGitPublisher, PublisherBinding
from integrations.mastermind_workspace_app.source_operation_principal import source_principal_scope
from integrations.mastermind_workspace_app.source_operation_context import WorkspaceSourceOperationContextFactory

ACTION = "publish_project_proposal"


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


class ProjectCreationSourceOwner:
    def __init__(self, *, events, private_inputs, permission_factory, adapter,
                 publisher_binding, qualify_publisher, pr_owner):
        from integrations.mastermind_workspace_app.project_creation_operation import ProjectCreationRecipeAdapter
        from integrations.mastermind_workspace_app.project_journey_recipes import InstalledProjectCreationRecipeAdapter
        if (type(events) is not SourceOperationEvents or type(private_inputs) is not ProjectSourceOriginalInput
                or private_inputs.supervisor.runtime.store is not events.store
                or type(permission_factory) is not WorkspaceSourceOperationContextFactory
                or type(adapter) not in (ProjectCreationRecipeAdapter, InstalledProjectCreationRecipeAdapter)
                or type(publisher_binding) is not PublisherBinding or not callable(qualify_publisher)):
            raise ValueError("fixed project source owners required")
        self._events, self._private = events, private_inputs
        self._permissions, self._adapter = permission_factory, adapter
        self._binding, self._qualifier, self._pr_owner = publisher_binding, qualify_publisher, pr_owner

    @staticmethod
    def _lookup(request_id, work_ref):
        return validate_lookup({"schema": "mastermind.workspace_source_operation_lookup.v1",
                                "action": ACTION, "request_id": request_id, "work_ref": work_ref})

    def _permission(self, principal, lookup=None):
        return self._permissions.bind(principal, action=ACTION,
                                      work_ref=None if lookup is None else lookup["work_ref"])

    def prepare(self, request, principal):
        permission = self._permission(principal)
        prepared = self._adapter.prepare(request=request, principal=principal)
        recipe = self._adapter.proposal_recipe(prepared)
        lookup = self._lookup(recipe["request_id"], recipe["work_ref"])
        public_sha = hashlib.sha256(_canonical(request)).hexdigest()
        # The accepted artifact owner keys by original command and actual scope.
        # Changed same-ID input cannot replace the original even before INTENT.
        ref = self._private.prepare(lookup, permission.principal_scope,
            payload=prepared.private_payload(), trusted_recipe_fingerprint=prepared.fingerprint_sha256)
        if ref is None:
            raise SourceOperationConflict()
        original_input = ref.to_dict()
        self._events.prepare(lookup, permission.principal_scope, request_sha256=public_sha,
            recipe_fingerprint_sha256=prepared.fingerprint_sha256, original_input=original_input,
            permission_binding_digest=permission.permission_binding_digest, guard=permission.check,
            publication_binding={"expected_commit": recipe["expected_commit"], "branch": None,
                "postimages": [{"path": recipe["path"], "content_sha256": recipe["content_sha256"],
                                "expected_preimage_sha256": None}]})
        if not permission.check():
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        payload = prepared.private_payload()
        record = payload["initial_snapshot"]["compiler_request"]["record"]
        preview = {"schema": "mastermind.project_creation_preview.v1", "state": "DRAFT_ONLY",
            "work_ref": recipe["work_ref"], "source_commit": recipe["expected_commit"],
            "canonical_path": recipe["path"], "content_sha256": recipe["content_sha256"],
            "goal": record["objective"], "profile": {
                "id": request["profile_id"], "revision": request["profile_sha256"],
                "title": record["title"], "owner": record["owner"], "program": record["program"],
                "repos": list(record["repos"]), "classification": record["class"],
                "blast_radius": record["blast_radius"], "ambiguity": record["ambiguity"],
                "waves": json.loads(_canonical(record["waves"])), "next_action": record["next_action"]}}
        return {"schema": "mastermind.workspace_source_operation_preview.v1",
            "selection": {key: lookup[key] for key in ("action", "request_id", "work_ref")},
            "owner_context": {"principal_scope": permission.principal_scope},
            "request_sha256": public_sha, "recipe_fingerprint_sha256": prepared.fingerprint_sha256,
            "preview_witness": {"original_input": original_input,
                                "recipe_fingerprint_sha256": prepared.fingerprint_sha256},
            "preview": preview}

    def read_status(self, lookup, principal):
        selected = validate_lookup(lookup)
        if selected["action"] != ACTION:
            raise SourceOperationConflict()
        permission = self._permission(principal, selected)
        return self._events.read_status(selected, permission.principal_scope, guard=permission.check)

    def _restore(self, lookup, principal, permission):
        original = self._events.original(lookup, permission.principal_scope, guard=permission.check)
        if original is None:
            raise SourceOperationConflict()
        payload = self._private.read(lookup, permission.principal_scope,
            original_input=original["original_input"],
            trusted_recipe_fingerprint=original["recipe_fingerprint_sha256"],
            trusted_request_sha256=original["request_sha256"])
        prepared = self._adapter.restore(private_payload=payload,
            trusted_recipe_fingerprint=original["recipe_fingerprint_sha256"], principal=principal)
        recipe = self._adapter.proposal_recipe(prepared)
        if self._lookup(recipe["request_id"], recipe["work_ref"]) != lookup:
            raise SourceOperationConflict()
        return prepared, original

    def _publisher(self, *, frozen, recipe, permission, permit=None):
        # Freeze qualified compiler output before constructing the transport.
        # Reconciliation uses the original authenticated private snapshot only;
        # no current Macro/compiler/profile read can prevent original lookup.
        frozen, recipe = json.loads(_canonical(frozen)), json.loads(_canonical(recipe))
        scope = permission.principal_scope
        lookup = self._lookup(recipe["request_id"], recipe["work_ref"])
        def compile_original(request):
            if type(request) is not dict or request != frozen:
                raise SourceOperationConflict()
            return json.loads(_canonical(recipe))
        def authorize(who):
            if not permission.check() or source_principal_scope(who) != scope:
                return False
            return permit is None or self._events.validate_permit(permit, lookup, scope, guard=permission.check)
        return FixedProjectGitPublisher(self._binding, compile_original, authorize,
            lambda who: permission.permission_binding_digest if authorize(who) else "",
            self._qualifier, self._pr_owner, principal_scope=source_principal_scope), frozen

    def _frozen_observation_material(self, lookup, permission):
        original = self._events.original(lookup, permission.principal_scope, guard=permission.check)
        if original is None:
            raise SourceOperationConflict()
        payload = self._private.read(lookup, permission.principal_scope,
            original_input=original["original_input"], trusted_recipe_fingerprint=original["recipe_fingerprint_sha256"],
            trusted_request_sha256=original["request_sha256"])
        snapshot = payload["initial_snapshot"]
        frozen, recipe = snapshot.get("compiler_request"), snapshot.get("compiled_recipe")
        expected = original["publication_binding"]
        if (payload["actor"] != {"principal_scope": permission.principal_scope}
                or type(frozen) is not dict or type(recipe) is not dict
                or set(recipe) != {"schema", "state", "request_id", "request_sha256", "expected_commit",
                                   "work_ref", "path", "content_utf8", "content_sha256"}
                or recipe["schema"] != "agentos.project_proposal.v1" or recipe["state"] != "DRAFT_ONLY"
                or recipe["request_sha256"] != original["recipe_fingerprint_sha256"]
                or hashlib.sha256(_canonical(frozen)).hexdigest() != original["recipe_fingerprint_sha256"]
                or self._lookup(recipe["request_id"], recipe["work_ref"]) != lookup
                or frozen.get("request_id") != lookup["request_id"]
                or recipe["expected_commit"] != expected["expected_commit"]
                or frozen.get("expected_commit") != expected["expected_commit"]
                or recipe["path"] != "agentos/workstreams/WS-" + lookup["work_ref"][3:] + ".md"
                or type(recipe["content_utf8"]) is not str or len(recipe["content_utf8"].encode("utf-8")) > 32768
                or hashlib.sha256(recipe["content_utf8"].encode("utf-8")).hexdigest() != recipe["content_sha256"]
                or expected["postimages"] != [{"path": recipe["path"], "content_sha256": recipe["content_sha256"],
                                               "expected_preimage_sha256": None}]):
            raise SourceOperationConflict()
        return original, frozen, recipe

    def _retain(self, lookup, permission, original, result):
        # ``result`` comes only from our fixed actual publisher invocation;
        # no HTTP caller can supply a publication dictionary to this method.
        if (type(result) is not dict or result.get("work_ref") != lookup["work_ref"]
                or result.get("request_sha256") != original["recipe_fingerprint_sha256"]):
            raise SourceOperationConflict()
        sources, proposal = [], result.get("proposal")
        if result.get("state") == "PROJECT_CREATED":
            proposal = None
            source = result["source"]
            if (source["request_sha256"] != original["recipe_fingerprint_sha256"]
                    or [{"path": source["path"], "content_sha256": source["content_sha256"],
                         "expected_preimage_sha256": None}] != original["publication_binding"]["postimages"]):
                raise SourceOperationConflict()
            sources = [{key: source[key] for key in ("repository", "commit", "path", "content_sha256")}]
        elif result.get("state") != "PROPOSAL_PUBLISHED":
            return
        evidence = {"sources": sources, "proposal": proposal}
        self._events.retain_observation(lookup, permission.principal_scope, phase="PUBLICATION",
            sources=sources, proposal=proposal, guard=permission.check,
            qualify_observation=lambda payload: permission.check()
                and payload["sources"] == evidence["sources"] and payload["proposal"] == evidence["proposal"])

    def submit(self, *, lookup, preview_witness, principal):
        selected = validate_lookup(lookup)
        if selected["action"] != ACTION:
            raise SourceOperationConflict()
        permission = self._permission(principal, selected)
        permit = self._events.claim_phase(selected, permission.principal_scope,
            permission_binding_digest=permission.permission_binding_digest,
            preview_witness=preview_witness, guard=permission.check)
        if permit is None:
            return self._events.read_status(selected, permission.principal_scope, guard=permission.check)
        # A fresh, original permit exists before private/source restoration.
        # Any failure HERE has made zero publisher invocations. Retain that
        # actual same-invocation no-effect fact while the guard is still valid;
        # never infer it from a missing receipt on a later read/restart.
        try:
            prepared, original = self._restore(selected, principal, permission)
            recipe = self._adapter.proposal_recipe(prepared)
            frozen = prepared.private_payload()["initial_snapshot"]["compiler_request"]
            publisher, request = self._publisher(frozen=frozen, recipe=recipe, permission=permission, permit=permit)
        except Exception:
            self._events.retain_no_effect(permit, selected, permission.principal_scope,
                qualify_no_effect=lambda: True, guard=permission.check)
            return self._events.read_status(selected, permission.principal_scope, guard=permission.check)
        # Exactly one external invocation for this newly issued permit.
        result = publisher.publish(request, principal)
        if result.get("state") == "NOT_DISPATCHED":
            self._events.retain_no_effect(permit, selected, permission.principal_scope,
                qualify_no_effect=lambda: result.get("schema") == "mastermind.workspace_project_publication.v1"
                    and result.get("state") == "NOT_DISPATCHED"
                    and result.get("source") is None and result.get("proposal") is None,
                guard=permission.check)
        else:
            self._retain(selected, permission, original, result)
        return self._events.read_status(selected, permission.principal_scope, guard=permission.check)

    def reconcile(self, lookup, principal):
        """Explicit Check status only: readonly Git/PR, qualified Event append."""
        selected = validate_lookup(lookup)
        if selected["action"] != ACTION:
            raise SourceOperationConflict()
        permission = self._permission(principal, selected)
        retained = self._events.read_status(selected, permission.principal_scope, guard=permission.check)
        if retained["disposition"] == "accepted" or retained["receipt"] is None:
            return retained
        original, frozen, recipe = self._frozen_observation_material(selected, permission)
        publisher, request = self._publisher(frozen=frozen, recipe=recipe, permission=permission)
        result = publisher.reconcile(request, principal)
        self._retain(selected, permission, original, result)
        return self._events.read_status(selected, permission.principal_scope, guard=permission.check)
