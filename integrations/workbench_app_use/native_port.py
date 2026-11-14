"""Native primitives owned by the existing Workbench action runtime.

The port has no lifecycle, authentication, registry, routing, queue or retry
state. It borrows the existing admission resolver, action key, FD-bound artifact
store, host identity and desktop lock. Recovery reads the original receipt even
after its observation expires; it never dispatches a recovery command.
"""
from __future__ import annotations

import dataclasses
import re
import secrets
from typing import Callable, Protocol

from integrations.workbench_action_mcp.action_artifacts import (
    ACTION_PURPOSE_NATIVE_APP_ACTION, ActionArtifactError, ActionArtifactIdentity,
    ActionArtifactStore, ActionHostBinding, acquire_store_writer, claim_action,
    classify_action, finalize_action,
)
from integrations.workbench_action_mcp.contracts import (
    ActionCaller, ProjectActionBinding, validate_action_caller, validate_action_scope,
)
from .contracts import (
    SCHEMA, MAX_OBSERVATION_AGE_MS, AppUseRefused, NativeAppGrant,
    NativeDispatchUnknown, NativeRefCodec, NativeTarget, binding_fingerprint,
    canonical, command, digest, native_target, validate_grant,
)


class NativeProvider(Protocol):
    session_ref: str
    carrier: str
    qualified_actions: frozenset[str]
    def validate_session(self) -> None: ...
    def permissions(self) -> dict: ...
    def applications(self) -> dict: ...
    def windows(self, *, bundle_id: str, pid: int,
                process_start_identity_decimal: str) -> dict: ...
    def validate_target(self, target: NativeTarget) -> None: ...
    def observe(self, target: NativeTarget) -> dict: ...
    def dispatch(self, target: NativeTarget, snapshot_id: str, command: dict) -> dict:
        """Raise AppUseRefused ONLY when non-dispatch is proved; otherwise unknown."""
        ...


def existing_desktop_lock():
    # Preserve the deployed Paper lock file. A new namespace would allow both
    # old Paper callers and new native callers to drive one desktop at once.
    from integrations.paper_desktop.bridge import desktop_lock
    return desktop_lock(wait_seconds=0)


class NativeAppPort:
    def __init__(self, *, resolve_binding: Callable, resolve_grant: Callable,
                 clock_ms: Callable[[], int], action_token_key: bytes,
                 artifact_store: ActionArtifactStore, host_binding: ActionHostBinding,
                 provider: NativeProvider, resolve_recovery_binding: Callable | None = None,
                 desktop_lock: Callable = existing_desktop_lock):
        if not all(callable(value) for value in
                   (resolve_binding, resolve_grant, clock_ms, desktop_lock)):
            raise AppUseRefused("NATIVE_OWNER_SERVICES_REQUIRED")
        self._resolve = resolve_binding
        self._recover = resolve_recovery_binding or resolve_binding
        self._grants = resolve_grant
        self._clock = clock_ms
        self._codec = NativeRefCodec(action_token_key)
        self._store, self._host = artifact_store, host_binding
        self._provider = provider
        self._lock = desktop_lock

    def _binding(self, caller: ActionCaller, project_ref: str, *, recovery=False):
        validate_action_caller(caller)
        binding = (self._recover if recovery else self._resolve)(caller, project_ref)
        if (type(binding) is not ProjectActionBinding or binding.caller != caller
                or binding.project_ref != project_ref):
            raise AppUseRefused("NATIVE_ADMISSION_REFUSED")
        if not recovery:
            validate_action_scope(binding.scope, now_ms=self._clock())
        return binding

    def _live(self, caller, project_ref, body=None):
        binding = self._binding(caller, project_ref)
        grant = validate_grant(self._grants(binding), now_ms=self._clock())
        if (grant.host_id != self._host.host_id
                or grant.boot_session_id != self._host.boot_session_id
                or grant.session_ref != self._provider.session_ref):
            raise AppUseRefused("NATIVE_HOST_SESSION_MISMATCH")
        self._provider.validate_session()
        if body is not None:
            if not body["issued_at_ms"] <= self._clock() < body["expires_at_ms"]:
                raise AppUseRefused("STALE_NATIVE_OBSERVATION")
            target = native_target(body["target"])
            if (body["binding"] != binding_fingerprint(binding)
                    or body["grant"] != grant.fingerprint
                    or body["session_ref"] != self._provider.session_ref
                    or target.bundle_id not in grant.application_ids):
                raise AppUseRefused("NATIVE_AUTHORITY_CHANGED")
            if body["kind"] == "action":
                if target not in grant.targets:
                    raise AppUseRefused("NATIVE_WINDOW_NOT_GRANTED")
                action = body["command"]["action"]
                if action not in grant.actions or action not in self._provider.qualified_actions:
                    raise AppUseRefused("NATIVE_ACTION_NOT_GRANTED")
        return binding, grant

    def inventory(self, caller, *, project_ref: str) -> dict:
        _, grant = self._live(caller, project_ref)
        permissions = self._provider.permissions()
        result = self._provider.applications()
        applications = [app for app in result["applications"]
                        if app["bundle_id"] in grant.application_ids]
        if self._live(caller, project_ref)[1] != grant:
            raise AppUseRefused("NATIVE_AUTHORITY_CHANGED")
        return {"schema": SCHEMA, "carrier": self._provider.carrier,
                "session_ref": grant.session_ref, "permissions": permissions,
                "applications": applications,
                "inventory_complete": result.get("inventory_complete") is True,
                "granted_actions": sorted(set(grant.actions) & self._provider.qualified_actions),
                "input_mode": "background_exact_target",
                "physical_input_exclusion_proven": False}

    def windows(self, caller, *, project_ref: str, application: dict) -> dict:
        # Parse the same exact application identity without a caller-selected host.
        if type(application) is not dict or set(application) != {
                "bundle_id", "pid", "process_start_identity_decimal"}:
            raise AppUseRefused("EXACT_NATIVE_APPLICATION_REQUIRED")
        target = native_target({**application, "window_id": 1})
        _, grant = self._live(caller, project_ref)
        if target.bundle_id not in grant.application_ids:
            raise AppUseRefused("NATIVE_APPLICATION_NOT_GRANTED")
        result = self._provider.windows(**application)
        if self._live(caller, project_ref)[1] != grant:
            raise AppUseRefused("NATIVE_AUTHORITY_CHANGED")
        return {"schema": SCHEMA, **result, "content_trust": "untrusted_application_data"}

    def observe(self, caller, *, project_ref: str, target: dict) -> dict:
        selected = native_target(target)
        binding, grant = self._live(caller, project_ref)
        if selected.bundle_id not in grant.application_ids:
            raise AppUseRefused("NATIVE_APPLICATION_NOT_GRANTED")
        # Even AX observations share the same cooperative desktop exclusion.
        # They do not activate a window or use web-focus accessibility presses.
        with self._lock():
            binding, grant = self._live(caller, project_ref)
            issued = self._clock()
            result = self._provider.observe(selected)
            body = {
                "schema": SCHEMA, "kind": "observation",
                "binding": binding_fingerprint(binding), "grant": grant.fingerprint,
                "session_ref": self._provider.session_ref, "target": selected.wire(),
                "snapshot_id": result["snapshot_id"], "issued_at_ms": issued,
                "expires_at_ms": min(issued + MAX_OBSERVATION_AGE_MS,
                    binding.scope.expires_at_ms, grant.expires_at_ms),
            }
            self._live(caller, project_ref, body)
            if self._clock() >= body["expires_at_ms"]:
                raise AppUseRefused("NATIVE_OBSERVATION_EXPIRED_DURING_CAPTURE")
            return {"schema": SCHEMA, "observation_ref": self._codec.encode(body),
                    "target": selected.wire(), "content": result["content"],
                    "content_trust": "untrusted_application_data",
                    "expires_at_ms": body["expires_at_ms"]}

    def _identity(self, binding, body, action_id) -> ActionArtifactIdentity:
        scope = binding.scope
        return ActionArtifactIdentity(
            action_id=action_id, purpose=ACTION_PURPOSE_NATIVE_APP_ACTION,
            subject_digest=binding.caller.subject_digest,
            client_ref=binding.caller.client_ref, resource=binding.caller.resource,
            project_ref=binding.project_ref, context_ref=scope.context_ref,
            responsibility_ref=scope.responsibility_ref, operation_ref=scope.operation_ref,
            owner_ref=scope.owner_ref, generation=scope.generation,
            root_device=scope.root_device, root_inode=scope.root_inode,
            store_device=self._store.device, store_inode=self._store.inode,
            host_id=self._host.host_id, boot_session_id=self._host.boot_session_id,
            relative_path="native:" + body["target"]["bundle_id"],
            source_identity=digest({"target": body["target"], "snapshot": body["snapshot_id"],
                "command": body["command"], "grant": body["grant"]}),
        )

    def prepare(self, caller, *, project_ref: str, observation_ref: str,
                native_command: dict) -> dict:
        body = self._codec.decode(observation_ref, kind="observation", now_ms=self._clock())
        body["kind"], body["command"] = "action", command(native_command)
        binding, _ = self._live(caller, project_ref, body)
        body["action_id"] = secrets.token_hex(16)
        body["identity"] = dataclasses.asdict(self._identity(binding, body, body["action_id"]))
        return {"schema": SCHEMA, "action_ref": self._codec.encode(body),
                "action_id": body["action_id"], "effect_state": "NOT_APPLIED",
                "expires_at_ms": body["expires_at_ms"]}

    def _original(self, caller, project_ref, action_ref):
        body = self._codec.decode(action_ref, kind="action", now_ms=self._clock(), evidence=True)
        binding = self._binding(caller, project_ref, recovery=True)
        if binding_fingerprint(binding) != body["binding"]:
            raise AppUseRefused("ORIGINAL_NATIVE_OWNER_REQUIRED")
        identity = ActionArtifactIdentity(**body["identity"])
        # A current caller may inspect only its original prepared action.
        if (identity.subject_digest != caller.subject_digest
                or identity.client_ref != caller.client_ref
                or identity.resource != caller.resource
                or identity.project_ref != project_ref):
            raise AppUseRefused("ORIGINAL_NATIVE_OWNER_REQUIRED")
        return body, identity

    @staticmethod
    def _receipt(identity, classification) -> dict:
        result = classification.result
        return {"schema": SCHEMA, "action_id": identity.action_id,
                "effect_state": classification.effect_state,
                "evidence_status": classification.evidence_status,
                "details": dict(result.details) if result is not None else {},
                "business_outcome_verified": False,
                "replay_permitted": False}

    @staticmethod
    def _unknown(identity, code="NATIVE_EFFECT_UNCERTAIN") -> dict:
        return {"schema": SCHEMA, "action_id": identity.action_id,
                "effect_state": "EFFECT_UNKNOWN", "evidence_status": "uncertain",
                "details": {"code": code}, "business_outcome_verified": False,
                "replay_permitted": False}

    def reconcile(self, caller, *, project_ref: str, action_ref: str) -> dict:
        _, identity = self._original(caller, project_ref, action_ref)
        return self._receipt(identity, classify_action(self._store, identity))

    def run(self, caller, *, project_ref: str, action_ref: str) -> dict:
        body, identity = self._original(caller, project_ref, action_ref)
        writer = acquire_store_writer(self._store)
        try:
            previous = classify_action(self._store, identity)
            if not previous.claimable:
                return self._receipt(identity, previous)
            self._codec.decode(action_ref, kind="action", now_ms=self._clock())
            self._live(caller, project_ref, body)
            with self._lock():
                # Admission and target checks run AFTER contention, immediately
                # before claim/dispatch, not only when the request was enqueued.
                binding, _ = self._live(caller, project_ref, body)
                if self._identity(binding, body, body["action_id"]) != identity:
                    raise AppUseRefused("NATIVE_ACTION_BINDING_CHANGED")
                target = native_target(body["target"])
                self._provider.validate_target(target)
                self._codec.decode(action_ref, kind="action", now_ms=self._clock())
                claimed = claim_action(self._store, identity, claimed_at_ms=self._clock())
                if not claimed.created or claimed.uncertain:
                    return self._unknown(identity, "NATIVE_CLAIM_UNCERTAIN")
                try:
                    self._live(caller, project_ref, body)
                    result = self._provider.dispatch(target, body["snapshot_id"], body["command"])
                    if (type(result) is not dict or result.get("native_acknowledged") is not True
                            or result.get("carrier") != self._provider.carrier
                            or type(result.get("native_result_sha256")) is not str
                            or re.fullmatch(r"[0-9a-f]{64}", result["native_result_sha256"]) is None):
                        raise NativeDispatchUnknown("NATIVE_ACK_UNQUALIFIED")
                except AppUseRefused:
                    effect, details, observed = "NOT_APPLIED", {
                        "code": "NATIVE_PREDISPATCH_REFUSED",
                        "carrier": self._provider.carrier}, None
                except Exception:
                    effect, details, observed = "EFFECT_UNKNOWN", {
                        "code": "NATIVE_DISPATCH_UNCERTAIN",
                        "carrier": self._provider.carrier}, None
                else:
                    effect, details, observed = "APPLIED", result, result["native_result_sha256"]
                try:
                    finalize_action(self._store, identity, effect_state=effect,
                        observed_sha256=observed, completed_at_ms=self._clock(),
                        durability="durable", details=details)
                except ActionArtifactError:
                    return self._unknown(identity, "NATIVE_RECEIPT_UNCERTAIN")
                return self._receipt(identity, classify_action(self._store, identity))
        finally:
            writer.release()
