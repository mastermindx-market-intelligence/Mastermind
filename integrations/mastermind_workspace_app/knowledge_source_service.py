"""Project file/preference commands over existing private, Event and Git owners.

No owner here creates a Job, session, store, grant or credential mapping. GET
status is Event-only. Explicit reconciliation may observe Git and retain that
qualified observation, but never compiles, opens the private body or writes Git.
The installed factory must supply every concrete owner below.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from common import workspace_discovery_correction_contract as correction

from common.workspace_source_operation_contract import validate_lookup
from control_plane.project_source_original_input import ProjectSourceOriginalInput
from control_plane.workspace_source_operations import SourceOperationEvents, SourceOperationConflict
from control_plane.workspace_project_git_publisher import (
    FixedProjectGitPublisher, PublisherBinding, _knowledge_request_lookup,
    _validate_knowledge_lookup,
)
from integrations.mastermind_workspace_app.source_operation_context import WorkspaceSourceOperationContextFactory
from integrations.mastermind_workspace_app.source_operation_principal import source_principal_scope
from integrations.mastermind_workspace_app.knowledge_recipe_adapter import ProjectKnowledgeRecipeAdapter, _detach
from integrations.mastermind_workspace_app.knowledge_publisher_events import KnowledgePublisherEvents

_ACTIONS = frozenset({"add_project_file", "set_project_communication_preference", correction.ACTION})


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


class ProjectKnowledgeSourceOwner:
    def __init__(self, *, events, private_inputs, permission_factory, adapter,
                 publisher_events, publisher_binding, qualify_publisher, pr_owner,
                 retained_date=lambda: datetime.now(timezone.utc).date().isoformat()):
        if (type(events) is not SourceOperationEvents
                or type(private_inputs) is not ProjectSourceOriginalInput
                or private_inputs.supervisor.runtime.store is not events.store
                or type(permission_factory) is not WorkspaceSourceOperationContextFactory
                or type(adapter) is not ProjectKnowledgeRecipeAdapter
                or type(publisher_events) is not KnowledgePublisherEvents
                or type(publisher_binding) is not PublisherBinding
                or not callable(qualify_publisher) or not callable(retained_date)):
            raise TypeError("actual fixed Knowledge owners required")
        self._events, self._private = events, private_inputs
        self._permissions, self._adapter, self._publisher_events = permission_factory, adapter, publisher_events
        self._binding, self._qualifier, self._pr_owner = publisher_binding, qualify_publisher, pr_owner
        self._date = retained_date

    @staticmethod
    def _lookup(value):
        selected = validate_lookup(value)
        if selected["action"] not in _ACTIONS:
            raise SourceOperationConflict()
        return selected

    @staticmethod
    def _from_binding(binding):
        return ProjectKnowledgeSourceOwner._lookup({"schema": "mastermind.workspace_source_operation_lookup.v1",
            **{key: binding[key] for key in ("action", "request_id", "work_ref")}})

    def _permission(self, principal, lookup):
        return self._permissions.bind(principal, action=lookup["action"], work_ref=lookup["work_ref"])

    def _original(self, selected, permission):
        original = self._events.original(selected, permission.principal_scope, guard=permission.check)
        if original is None:
            raise SourceOperationConflict()
        binding = _validate_knowledge_lookup(original.get("lookup_binding"))
        if self._from_binding(binding) != selected or binding["request_sha256"] != original["request_sha256"]:
            raise SourceOperationConflict()
        return original, binding

    def prepare(self, request, principal):
        # Validated request/lookup is data only. The distinct action owner must
        # qualify the actual principal before any compiler or private custody.
        request = _detach(request)
        binding = _knowledge_request_lookup(request)
        selected = self._from_binding(binding)
        permission = self._permission(principal, selected)
        original = self._events.original(selected, permission.principal_scope, guard=permission.check)
        if original is not None:
            # A changed same-ID payload is a conflict before any source refresh.
            if (original.get("lookup_binding") != binding
                    or original["request_sha256"] != binding["request_sha256"]):
                raise SourceOperationConflict()
            prepared, original, _ = self._restore(selected, principal, permission)
        else:
            recovered = self._private.lookup_original(selected, permission.principal_scope, guard=permission.check)
            if recovered is not None:
                if recovered["request_sha256"] != binding["request_sha256"]:
                    raise SourceOperationConflict()
                if recovered["permission_binding_digest"] != permission.permission_binding_digest:
                    raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
                prepared = self._adapter.restore(private_payload=recovered["private_payload"],
                    trusted_recipe_fingerprint=recovered["recipe_fingerprint_sha256"],
                    principal=principal, permission=permission)
            else:
                prepared = self._adapter.prepare(request=request, principal=principal,
                    permission=permission, decision_date=self._date())
            recipe = self._adapter.recipe(prepared)
            # Repeating this exact private preparation completes durability for
            # an artifact-only original. No actor/day/basis is regenerated and
            # no Git operation is reserved before the real Review is returned.
            ref = self._private.prepare(selected, permission.principal_scope,
                payload=prepared.private_payload(), trusted_recipe_fingerprint=prepared.fingerprint_sha256,
                permission_binding_digest=permission.permission_binding_digest)
            if ref is None:
                raise SourceOperationConflict()
            self._events.prepare(selected, permission.principal_scope,
                request_sha256=prepared.request_sha256,
                recipe_fingerprint_sha256=prepared.fingerprint_sha256,
                original_input=ref.to_dict(), permission_binding_digest=permission.permission_binding_digest,
                guard=permission.check, lookup_binding=binding,
                publication_binding={"expected_commit": recipe["captured_commit"], "branch": "mmos/knowledge-" + hashlib.sha256(_canonical({"principal_scope": permission.principal_scope, "action": binding["action"], "request_id": binding["request_id"]})).hexdigest(),
                    "postimages": [{key: image[key] for key in ("path", "content_sha256", "expected_preimage_sha256")}
                                   for image in recipe["postimages"]]})
            original, _ = self._original(selected, permission)
        if not permission.check():
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        recipe = self._adapter.recipe(prepared)
        change = (correction.preview_change(request, permission.principal_scope)
                  if binding["action"] == correction.ACTION else
                  {"kind": "FILE_ADD", "display_name": request["file"]["display_name"],
                   "size_bytes": len(request["file"]["content_utf8"].encode("utf-8"))}
                  if binding["action"] == "add_project_file" else
                  {"kind": "COMMUNICATION_PREFERENCE", "value": request["value"]})
        return {"schema": "mastermind.workspace_source_operation_preview.v1",
            "selection": {key: selected[key] for key in ("action", "request_id", "work_ref")},
            "owner_context": {"principal_scope": permission.principal_scope},
            "request_sha256": prepared.request_sha256,
            "recipe_fingerprint_sha256": prepared.fingerprint_sha256,
            "preview_witness": {"original_input": original["original_input"],
                                "recipe_fingerprint_sha256": prepared.fingerprint_sha256},
            "preview": {"schema": "mastermind.project_knowledge_preview.v1", "state": "DRAFT_ONLY",
                "action": selected["action"], "work_ref": selected["work_ref"],
                "source_commit": recipe["captured_commit"], "change": change,
                "postimages": [{key: image[key] for key in ("path", "content_sha256", "expected_preimage_sha256")}
                               for image in recipe["postimages"]]}}

    def _inspection(self, lookup, principal):
        # Knowledge inspection carries the original seven safe fields, not a
        # caller body/current-source selector. Compare them to the actual
        # retained Event even after settlement and without any source refresh.
        binding = _validate_knowledge_lookup(lookup)
        selected = self._from_binding(binding)
        permission = self._permission(principal, selected)
        original = self._events.original(selected, permission.principal_scope, guard=permission.check)
        if original is not None and (original.get("lookup_binding") != binding
                or original.get("request_sha256") != binding["request_sha256"]):
            raise SourceOperationConflict()
        return selected, permission

    def read_status(self, lookup, principal):
        selected, permission = self._inspection(lookup, principal)
        return self._events.read_status(selected, permission.principal_scope, guard=permission.check)

    def read_original(self, lookup, principal):
        """Read only the original Event's retained note, without a compilation.

        Missing custody never proves no effect. Status/reconciliation remain
        independent and body-free when this projection cannot be opened.
        """
        from common import workspace_discovery_original_contract as original_wire
        checked = correction.validate_lookup(lookup)
        selected, permission = self._inspection(checked, principal)
        original, binding = self._original(selected, permission)
        private, events, permissions = self._private, self._events, self._permissions
        read, method = private.read, self.read_original
        def current():
            return (self._private is private and self._events is events and self._permissions is permissions
                and private.read == read and type(private).__dict__.get("read") is read.__func__
                and self.read_original == method and type(self).__dict__.get("read_original") is method.__func__
                and permission.check())
        if (binding != checked or original["permission_binding_digest"] != permission.permission_binding_digest
                or not current()):
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        payload = read(selected, permission.principal_scope,
            original_input=original["original_input"],
            trusted_recipe_fingerprint=original["recipe_fingerprint_sha256"],
            trusted_request_sha256=original["request_sha256"])
        if not current():
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        if (correction.request_lookup(payload["request"]) != checked
                or payload["action"] != correction.ACTION
                or payload["actor"] != {"principal_scope": permission.principal_scope,
                    "actor_ref": "workspace:" + permission.principal_scope,
                    "permission_binding_digest": original["permission_binding_digest"]}):
            raise SourceOperationConflict()
        snapshot = payload["initial_snapshot"]
        if (type(snapshot) is not dict
                or set(snapshot) != {"workstream_text", "discovery_text", "reference_closure", "decision_date"}
                or type(snapshot["workstream_text"]) is not str
                or len(snapshot["workstream_text"].encode("utf-8")) > 128 * 1024
                or hashlib.sha256(snapshot["workstream_text"].encode("utf-8")).hexdigest() != checked["base_revision"]):
            raise SourceOperationConflict()
        result = original_wire.validate({"schema": original_wire.SCHEMA,
            "selection": checked, "owner_context": {"principal_scope": permission.principal_scope},
            "custody": {"kind": "ORIGINAL_CORRECTION_INPUT", "original_input": original["original_input"],
                "recipe_fingerprint_sha256": original["recipe_fingerprint_sha256"]},
            "original": {"source_commit": checked["source_commit"], "discovery_ref": checked["discovery_ref"],
                "content_sha256": checked["expected_discovery_revision"], "workstream_sha256": checked["base_revision"],
                "media_type": "text/markdown", "content_utf8": snapshot["discovery_text"]}},
            lookup=checked, principal_scope=permission.principal_scope)
        if not current():
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        return result

    def _restore(self, selected, principal, permission):
        original, binding = self._original(selected, permission)
        if original["permission_binding_digest"] != permission.permission_binding_digest:
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        payload = self._private.read(selected, permission.principal_scope,
            original_input=original["original_input"],
            trusted_recipe_fingerprint=original["recipe_fingerprint_sha256"],
            trusted_request_sha256=original["request_sha256"])
        prepared = self._adapter.restore(private_payload=payload,
            trusted_recipe_fingerprint=original["recipe_fingerprint_sha256"],
            principal=principal, permission=permission)
        if _knowledge_request_lookup(payload["request"]) != binding:
            raise SourceOperationConflict()
        return prepared, original, binding

    def _publisher(self):
        def no_create(*args, **kwargs):
            raise SourceOperationConflict()
        events = self._publisher_events
        return FixedProjectGitPublisher(self._binding, no_create, lambda _: False, lambda _: "",
            self._qualifier, self._pr_owner, principal_scope=source_principal_scope,
            authorize_knowledge=events.authorize_knowledge,
            knowledge_permission_stamp=events.knowledge_permission_stamp,
            load_original_operation=events.load_original_operation,
            validate_original_claim=events.validate_original_claim)

    def _retain(self, selected, permission, original, result):
        if type(result) is not dict or result.get("selection") != original["lookup_binding"]:
            raise SourceOperationConflict()
        if result.get("recipe_fingerprint_sha256") != original["recipe_fingerprint_sha256"]:
            raise SourceOperationConflict()
        sources, proposal = [], result.get("proposal")
        if result.get("state") == "SOURCE_PUBLISHED":
            source = result.get("source")
            if (type(source) is not dict or source.get("repository") != "mastermindx-market-intelligence/macro"
                    or type(source.get("postimages")) is not list):
                raise SourceOperationConflict()
            actual = sorted((item["path"], item["content_sha256"]) for item in source["postimages"])
            expected = sorted((item["path"], item["content_sha256"]) for item in original["publication_binding"]["postimages"])
            count = 3 if selected["action"] == correction.ACTION else 2
            if actual != expected or len(actual) != count or proposal is not None:
                raise SourceOperationConflict()
            sources = [{"repository": "macro", "commit": source["commit"], **item} for item in source["postimages"]]
        elif result.get("state") != "PROPOSAL_PUBLISHED":
            return
        evidence = json.loads(_canonical({"sources": sources, "proposal": proposal}))
        self._events.retain_observation(selected, permission.principal_scope, phase="PUBLICATION",
            sources=sources, proposal=proposal, guard=permission.check,
            qualify_observation=lambda payload: permission.check()
                and payload["sources"] == evidence["sources"] and payload["proposal"] == evidence["proposal"])

    def submit(self, *, lookup, preview_witness, principal):
        selected = self._lookup(lookup)
        permission = self._permission(principal, selected)
        retained = self._events.read_status(selected, permission.principal_scope, guard=permission.check)
        # An existing attempted or settled phase is never restored/recompiled
        # or submitted again, even when current Macro source is unavailable.
        if retained["disposition"] in {"accepted", "refused"} or (retained["receipt"] is not None and retained["receipt"]["kind"] != "INTENT"):
            return retained
        original, binding = self._original(selected, permission)
        permit = self._events.claim_phase(selected, permission.principal_scope,
            permission_binding_digest=permission.permission_binding_digest,
            preview_witness=preview_witness, guard=permission.check)
        if permit is None:
            return self._events.read_status(selected, permission.principal_scope, guard=permission.check)
        publisher_invoked = False
        try:
            prepared, restored_original, restored_binding = self._restore(selected, principal, permission)
            if restored_original != original or restored_binding != binding:
                raise SourceOperationConflict()
            original_request = prepared.private_payload()["request"]
            original_recipe = self._adapter.recipe(prepared)
            publisher = self._publisher()
            with self._publisher_events.bind_claim(principal, binding, permit):
                # From this line a raised exception is uncertain. No exception
                # after the invocation may be laundered into no-effect.
                publisher_invoked = True
                result = publisher.publish_knowledge(original_request, original_recipe, principal, claim=permit)
        except Exception:
            if not publisher_invoked:
                # This private same-invocation branch follows an actual unique
                # durable permit and proves our publisher was never called.
                # Revocation can refuse this append, leaving UNKNOWN intact.
                self._events.retain_no_effect(permit, selected, permission.principal_scope,
                    qualify_no_effect=lambda: publisher_invoked is False, guard=permission.check)
            return self._events.read_status(selected, permission.principal_scope, guard=permission.check)
        if result.get("state") == "NOT_DISPATCHED":
            self._events.retain_no_effect(permit, selected, permission.principal_scope,
                qualify_no_effect=lambda: result.get("schema") == "mastermind.workspace_project_knowledge_publication.v1"
                    and result.get("state") == "NOT_DISPATCHED" and result.get("source") is None
                    and result.get("proposal") is None, guard=permission.check)
        else:
            self._retain(selected, permission, original, result)
        return self._events.read_status(selected, permission.principal_scope, guard=permission.check)

    def reconcile(self, lookup, principal):
        selected, permission = self._inspection(lookup, principal)
        retained = self._events.read_status(selected, permission.principal_scope, guard=permission.check)
        if retained["disposition"] in {"accepted", "refused"} or retained["receipt"] is None:
            return retained
        original, binding = self._original(selected, permission)
        result = self._publisher().reconcile_knowledge(binding, principal)
        self._retain(selected, permission, original, result)
        return self._events.read_status(selected, permission.principal_scope, guard=permission.check)
