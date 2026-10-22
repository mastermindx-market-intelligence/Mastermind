"""Workbench-bound browser action port over an owner-bound relay.

This module reuses the existing Workbench ActionArtifactStore for browser
modifying-effect receipts. It creates no browser lifecycle registry, retry
queue, or effect database. The signed browser_ref plus OS process identity and
the deterministic relay socket name are enough to address one live resource.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

from control_plane.browser_resource_contract import (
    ALLOWED_BROWSER_TOOLS,
    READ_ONLY_BROWSER_TOOLS,
)
from control_plane.codex_worker import ProcessIdentityError, ProcessInspector
from integrations.workbench_action_mcp.action_artifacts import (
    ACTION_PURPOSE_BROWSER_ACTION,
    ACTION_PURPOSE_BROWSER_RESOURCE,
    ActionArtifactBusy,
    ActionArtifactError,
    ActionArtifactIdentity,
    ActionArtifactStore,
    ActionArtifactUncertain,
    ActionHostBinding,
    acquire_store_writer,
    enumerate_action_evidence,
    claim_action,
    classify_action,
    finalize_action,
    read_action_process,
    revalidate_artifact_store,
)
from integrations.workbench_action_mcp.contracts import (
    ActionCaller,
    ProjectActionBinding,
)

from .contracts import (
    ACTION_SCHEMA,
    BrowserContractError,
    BrowserRefCodec,
    BrowserResourceRef,
    PreparedBrowserAction,
    canonical_browser_arguments,
)
from .relay import (
    RELAY_REQUEST_SCHEMA,
    RELAY_RESPONSE_SCHEMA,
    BrowserRelayError,
    relay_request,
)


from integrations.mastermind_browser_link.tool_contract import (
    LINK_TOOLS, LINK_READ_TOOLS, LINK_TOOL_SCHEMA_DIGEST, INVENTORY_TOOL,
    OWNER_RESULT_SCHEMA, OWNER_CONNECTION_SCHEMA, backend_tool_policy,
)


class BrowserPortRefused(RuntimeError):
    """Typed Workbench browser refusal with no implied external effect."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


ResolveBinding = Callable[[ActionCaller, str], ProjectActionBinding | None]
ClockMs = Callable[[], int]
RelayRequester = Callable[..., dict[str, Any]]


def _binding_key(value: ProjectActionBinding) -> tuple[object, ...]:
    scope = value.scope
    return (
        value.project_ref,
        scope.root_device,
        scope.root_inode,
        scope.context_ref,
        scope.responsibility_ref,
        scope.operation_ref,
        scope.owner_ref,
        scope.generation,
        scope.expires_at_ms,
    )


class BrowserActionPort:
    """Read tools plus exactly-once browser action dispatch for one Workbench owner."""

    def __init__(
        self,
        *,
        resolve_binding: ResolveBinding,
        resolve_recovery_binding: ResolveBinding | None = None,
        require_resource_claim_for_fresh: bool = False,
        clock_ms: ClockMs,
        codec: BrowserRefCodec,
        artifact_store: ActionArtifactStore,
        host_binding: ActionHostBinding,
        inspector: ProcessInspector,
        relay_root: Path,
        relay_requester: RelayRequester = relay_request,
        action_ttl_ms: int = 5 * 60 * 1000,
        relay_timeout_seconds: float = 30.0,
    ) -> None:
        if not callable(resolve_binding) or not callable(clock_ms) or not callable(relay_requester):
            raise TypeError("browser port callbacks must be callable")
        if resolve_recovery_binding is not None and not callable(resolve_recovery_binding):
            raise TypeError("browser recovery binding must be callable")
        if (type(require_resource_claim_for_fresh) is not bool
                or (require_resource_claim_for_fresh and resolve_recovery_binding is None)):
            raise TypeError("fresh browser resource claim requires a recovery resolver")
        if not isinstance(codec, BrowserRefCodec):
            raise TypeError("browser codec is required")
        if not isinstance(artifact_store, ActionArtifactStore):
            raise TypeError("browser artifact store is required")
        if not isinstance(host_binding, ActionHostBinding):
            raise TypeError("browser host binding is required")
        if not hasattr(inspector, "inspect"):
            raise TypeError("browser process inspector is required")
        if not isinstance(relay_root, Path) or not relay_root.is_absolute():
            raise TypeError("browser relay root must be absolute")
        try:
            root_stat = relay_root.lstat()
        except OSError as error:
            raise TypeError("browser relay root is unavailable") from error
        if (
            stat.S_ISLNK(root_stat.st_mode)
            or not stat.S_ISDIR(root_stat.st_mode)
            or root_stat.st_uid != os.geteuid()
            or stat.S_IMODE(root_stat.st_mode) & 0o022
        ):
            raise TypeError("browser relay root is unsafe")
        if type(action_ttl_ms) is not int or not 1000 <= action_ttl_ms <= 5 * 60 * 1000:
            raise TypeError("browser action TTL is invalid")
        if not isinstance(relay_timeout_seconds, (int, float)) or not 0 < relay_timeout_seconds <= 120:
            raise TypeError("browser relay timeout is invalid")
        self._resolve_binding = resolve_binding
        self._resolve_recovery_binding = resolve_recovery_binding
        self._require_resource_claim_for_fresh = require_resource_claim_for_fresh
        self._clock_ms = clock_ms
        self._codec = codec
        self._store = artifact_store
        self._host_binding = host_binding
        self._inspector = inspector
        self._relay_root = relay_root
        self._relay_requester = relay_requester
        self._action_ttl_ms = action_ttl_ms
        self._relay_timeout = float(relay_timeout_seconds)
        self._inflight_gate = threading.RLock()
        self._inflight_actions: set[str] = set()

    @property
    def codec(self) -> BrowserRefCodec:
        return self._codec

    def _now(self) -> int:
        value = self._clock_ms()
        if type(value) is not int or not 0 <= value < 2**63:
            raise BrowserPortRefused("CLOCK_UNAVAILABLE")
        return value

    def _binding(
        self,
        caller: ActionCaller,
        browser: BrowserResourceRef,
        *,
        recovery: bool = False,
    ) -> ProjectActionBinding:
        if type(caller) is not ActionCaller:
            raise BrowserPortRefused("CALLER_INVALID")
        resolver = (
            self._resolve_recovery_binding
            if recovery and self._resolve_recovery_binding is not None
            else self._resolve_binding
        )
        value = resolver(caller, browser.project_ref)
        if type(value) is not ProjectActionBinding:
            raise BrowserPortRefused("BROWSER_BINDING_CHANGED")
        scope = value.scope
        if (
            caller.subject_digest != browser.subject_digest
            or caller.client_ref != browser.client_ref
            or caller.resource != browser.resource
            or value.project_ref != browser.project_ref
            or scope.context_ref != browser.context_ref
            or scope.responsibility_ref != browser.responsibility_ref
            or scope.operation_ref != browser.operation_ref
            or scope.owner_ref != browser.owner_ref
            or scope.generation != browser.generation
            or self._host_binding.host_id != browser.host_id
            or self._host_binding.boot_session_id != browser.boot_session_id
        ):
            raise BrowserPortRefused("BROWSER_BINDING_CHANGED")
        return value

    def _resource(
        self,
        caller: ActionCaller,
        browser_ref: object,
        *,
        require_fresh: bool = True,
    ) -> tuple[BrowserResourceRef, ProjectActionBinding, Path]:
        now_ms = self._now()
        if type(caller) is not ActionCaller or type(caller.expires_at) is not int:
            raise BrowserPortRefused("CALLER_INVALID")
        if now_ms >= caller.expires_at * 1000:
            raise BrowserPortRefused("BROWSER_BINDING_CHANGED")
        try:
            browser = self._codec.decode_resource(
                browser_ref, now_ms=now_ms, require_fresh=require_fresh
            )
        except BrowserContractError as error:
            raise BrowserPortRefused("BROWSER_REF_INVALID") from error
        binding = self._binding(caller, browser, recovery=not require_fresh)
        if (self._resolve_recovery_binding is not None
                and (not require_fresh or self._require_resource_claim_for_fresh)):
            # The signed browser ref omits the project root's device/inode.
            # For a private worker, join every resource read AND fresh mutation
            # to the same original APPLIED start/process claim. The attended
            # port retains its prior recovery-only behavior by default.
            store = revalidate_artifact_store(self._store)
            identity = ActionArtifactIdentity(
                action_id=browser.start_action_id,
                purpose=ACTION_PURPOSE_BROWSER_RESOURCE,
                subject_digest=browser.subject_digest,
                client_ref=browser.client_ref,
                resource=browser.resource,
                project_ref=browser.project_ref,
                context_ref=browser.context_ref,
                responsibility_ref=browser.responsibility_ref,
                operation_ref=browser.operation_ref,
                owner_ref=browser.owner_ref,
                generation=browser.generation,
                root_device=binding.scope.root_device,
                root_inode=binding.scope.root_inode,
                store_device=store.device,
                store_inode=store.inode,
                host_id=browser.host_id,
                boot_session_id=browser.boot_session_id,
                relative_path=f"browser:{browser.start_action_id}",
                source_identity=browser.tool_schema_digest,
            )
            classified = classify_action(self._store, identity)
            if classified.evidence_status != "qualified" or classified.effect_state != "APPLIED":
                raise BrowserPortRefused("BROWSER_RECOVERY_BINDING_CHANGED")
            try:
                process = read_action_process(self._store, identity)
            except ActionArtifactError as error:
                raise BrowserPortRefused("BROWSER_RECOVERY_BINDING_CHANGED") from error
            if (
                process is None
                or process.pid != browser.relay_pid
                or process.process_start_identity != browser.relay_start_identity
                or process.pgid != browser.relay_pgid
                or process.session_id != browser.relay_session_id
                or process.host_id != browser.host_id
                or process.boot_session_id != browser.boot_session_id
            ):
                raise BrowserPortRefused("BROWSER_RECOVERY_BINDING_CHANGED")
        try:
            observed = self._inspector.inspect(browser.relay_pid)
        except (ProcessIdentityError, OSError, ValueError) as error:
            raise BrowserPortRefused("PROCESS_IDENTITY_CHANGED") from error
        if (
            observed.start_identity != browser.relay_start_identity
            or observed.pgid != browser.relay_pgid
            or observed.session_id != browser.relay_session_id
            or observed.effective_uid != os.geteuid()
            or observed.real_uid != os.getuid()
            or observed.effective_gid != os.getegid()
            or observed.real_gid != os.getgid()
        ):
            raise BrowserPortRefused("PROCESS_IDENTITY_CHANGED")
        socket_path = self._relay_root / f"{browser.start_action_id}.sock"
        return browser, binding, socket_path

    def _relay(
        self,
        *,
        socket_path: Path,
        browser: BrowserResourceRef,
        request_id: str,
        tool: str,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        response = self._relay_requester(
            socket_path,
            {
                "schema": RELAY_REQUEST_SCHEMA,
                "kind": "tool",
                "request_id": request_id,
                "resource_id": browser.start_action_id,
                "tool": tool,
                "arguments": dict(arguments),
            },
            timeout=self._relay_timeout,
        )
        if (
            type(response) is not dict
            or response.get("schema") != RELAY_RESPONSE_SCHEMA
            or response.get("request_id") != request_id
            or response.get("resource_id") != browser.start_action_id
            or type(response.get("ok")) is not bool
        ):
            raise BrowserRelayError("relay response binding changed")
        return response

    def observe_resource(
        self,
        caller: ActionCaller,
        browser_ref: object,
    ) -> BrowserResourceRef:
        """Revalidate and project one exact live resource without browser I/O."""
        browser, _binding, _socket_path = self._resource(
            caller, browser_ref, require_fresh=True
        )
        return browser

    def observe_connection(self, caller: ActionCaller, browser_ref: object) -> Mapping[str, Any]:
        browser, _binding, socket_path = self._resource(caller, browser_ref, require_fresh=True)
        if browser.tool_schema_digest != LINK_TOOL_SCHEMA_DIGEST:
            raise BrowserPortRefused("BROWSER_BACKEND_UNSUPPORTED")
        request_id = secrets.token_hex(16)
        response = self._relay_requester(socket_path, {
            "schema": RELAY_REQUEST_SCHEMA, "kind": "status", "request_id": request_id,
            "resource_id": browser.start_action_id,
        }, timeout=min(2.0, self._relay_timeout))
        if (type(response) is not dict or response.get("schema") != RELAY_RESPONSE_SCHEMA
                or response.get("request_id") != request_id or response.get("resource_id") != browser.start_action_id
                or response.get("ok") is not True or response.get("tool_schema_digest") != LINK_TOOL_SCHEMA_DIGEST
                or response.get("child_pid") != browser.relay_pid
                or response.get("allowed_tools") != sorted(LINK_TOOLS)):
            raise BrowserPortRefused("BROWSER_CONNECTION_UNAVAILABLE")
        data = response.get("connection_status")
        from integrations.mastermind_browser_link.native_channel import record, reference, native_host_name
        try:
            record(data, {"schema", "instance_id", "connected"}, {"connection_generation"})
            native_host_name(data["instance_id"])
            if data["schema"] != OWNER_CONNECTION_SCHEMA or type(data["connected"]) is not bool:
                raise ValueError("invalid connection status")
            if data["connected"]:
                reference(data.get("connection_generation"))
            elif "connection_generation" in data:
                raise ValueError("disconnected generation")
        except (ValueError, TypeError) as exc:
            raise BrowserPortRefused("BROWSER_CONNECTION_UNAVAILABLE") from exc
        return dict(data)

    def observe_tab_group(
        self,
        caller: ActionCaller,
        browser_ref: object,
    ) -> Mapping[str, Any]:
        """Observe the owner-established tab group through one fixed list call.

        This is not a generic browser_tabs pass-through. The caller cannot select,
        create, or close tabs here; those operations remain outside the read
        projection. A relay failure is never retried.
        """
        browser, _binding, socket_path = self._resource(
            caller, browser_ref, require_fresh=True
        )
        request_id = secrets.token_hex(16)
        try:
            response = self._relay(
                socket_path=socket_path,
                browser=browser,
                request_id=request_id,
                tool=INVENTORY_TOOL if browser.tool_schema_digest == LINK_TOOL_SCHEMA_DIGEST else "browser_tabs",
                arguments={} if browser.tool_schema_digest == LINK_TOOL_SCHEMA_DIGEST else {"action": "list"},
            )
        except BrowserRelayError as error:
            raise BrowserPortRefused(
                "BROWSER_TAB_OBSERVATION_UNAVAILABLE"
            ) from error
        result = response.get("result")
        if (
            response["ok"] is not True
            or not isinstance(result, Mapping)
            or result.get("isError") is True
        ):
            raise BrowserPortRefused("BROWSER_TAB_OBSERVATION_REFUSED")
        return dict(result)

    def call_read_tool(
        self,
        caller: ActionCaller,
        browser_ref: object,
        tool: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if tool not in READ_ONLY_BROWSER_TOOLS | LINK_READ_TOOLS:
            raise BrowserPortRefused("MUTATING_TOOL_REQUIRES_ACTION_REF")
        try:
            canonical = canonical_browser_arguments(arguments)
        except BrowserContractError as error:
            raise BrowserPortRefused("BROWSER_ARGUMENTS_INVALID") from error
        # A fresh authenticated caller may inspect the exact existing carrier
        # after its resource lease ends. Process and owner binding stay pinned;
        # this path has no action claim or mutating tool.
        browser, _binding, socket_path = self._resource(
            caller, browser_ref, require_fresh=False
        )
        if tool not in backend_tool_policy(browser.tool_schema_digest)[1]:
            raise BrowserPortRefused("BROWSER_TOOL_NOT_GRANTED")
        request_id = secrets.token_hex(16)
        try:
            response = self._relay(
                socket_path=socket_path,
                browser=browser,
                request_id=request_id,
                tool=tool,
                arguments=json.loads(canonical),
            )
        except BrowserRelayError as error:
            raise BrowserPortRefused("BROWSER_READ_UNAVAILABLE") from error
        if response["ok"] is not True or type(response.get("result")) is not dict:
            raise BrowserPortRefused("BROWSER_READ_REFUSED")
        return response["result"]

    def prepare_action(
        self,
        caller: ActionCaller,
        browser_ref: object,
        tool: str,
        arguments: Mapping[str, Any],
    ) -> str:
        if tool not in ALLOWED_BROWSER_TOOLS | LINK_TOOLS:
            raise BrowserPortRefused("BROWSER_TOOL_NOT_GRANTED")
        if tool in READ_ONLY_BROWSER_TOOLS | LINK_READ_TOOLS:
            raise BrowserPortRefused("READ_ONLY_TOOL_NEEDS_NO_ACTION_REF")
        if type(browser_ref) is not str:
            raise BrowserPortRefused("BROWSER_REF_INVALID")
        browser, binding, _socket_path = self._resource(caller, browser_ref)
        if tool not in backend_tool_policy(browser.tool_schema_digest)[0]:
            raise BrowserPortRefused("BROWSER_TOOL_NOT_GRANTED")
        try:
            arguments_json = canonical_browser_arguments(arguments)
        except BrowserContractError as error:
            raise BrowserPortRefused("BROWSER_ARGUMENTS_INVALID") from error
        now_ms = self._now()
        expires_at_ms = min(
            now_ms + self._action_ttl_ms,
            browser.expires_at_ms,
            binding.scope.expires_at_ms,
            caller.expires_at * 1000,
        )
        if expires_at_ms <= now_ms:
            raise BrowserPortRefused("BROWSER_ACTION_EXPIRED")
        prepared = PreparedBrowserAction(
            schema=ACTION_SCHEMA,
            action_id=secrets.token_hex(16),
            browser_ref_sha256=hashlib.sha256(browser_ref.encode("utf-8")).hexdigest(),
            subject_digest=browser.subject_digest,
            client_ref=browser.client_ref,
            resource=browser.resource,
            project_ref=browser.project_ref,
            context_ref=browser.context_ref,
            responsibility_ref=browser.responsibility_ref,
            operation_ref=browser.operation_ref,
            owner_ref=browser.owner_ref,
            generation=browser.generation,
            host_id=browser.host_id,
            boot_session_id=browser.boot_session_id,
            tool_name=tool,
            arguments_json=arguments_json,
            issued_at_ms=now_ms,
            expires_at_ms=expires_at_ms,
        )
        return self._codec.encode_action(prepared)

    def _action_identity(
        self,
        browser: BrowserResourceRef,
        binding: ProjectActionBinding,
        prepared: PreparedBrowserAction,
    ) -> ActionArtifactIdentity:
        store = revalidate_artifact_store(self._store)
        return ActionArtifactIdentity(
            action_id=prepared.action_id,
            purpose=ACTION_PURPOSE_BROWSER_ACTION,
            subject_digest=prepared.subject_digest,
            client_ref=prepared.client_ref,
            resource=prepared.resource,
            project_ref=prepared.project_ref,
            context_ref=prepared.context_ref,
            responsibility_ref=prepared.responsibility_ref,
            operation_ref=prepared.operation_ref,
            owner_ref=prepared.owner_ref,
            generation=prepared.generation,
            root_device=binding.scope.root_device,
            root_inode=binding.scope.root_inode,
            store_device=store.device,
            store_inode=store.inode,
            host_id=prepared.host_id,
            boot_session_id=prepared.boot_session_id,
            relative_path=f"browser:{browser.start_action_id}:{prepared.tool_name}",
            source_identity=browser.tool_schema_digest,
        )

    def _decode_action(
        self,
        caller: ActionCaller,
        browser_ref: object,
        action_ref: object,
        *,
        require_live: bool = True,
    ) -> tuple[BrowserResourceRef, ProjectActionBinding, Path, PreparedBrowserAction]:
        if type(browser_ref) is not str:
            raise BrowserPortRefused("BROWSER_REF_INVALID")
        if require_live:
            browser, binding, socket_path = self._resource(caller, browser_ref)
        else:
            try:
                browser = self._codec.decode_resource(
                    browser_ref, now_ms=self._now(), require_fresh=False
                )
            except BrowserContractError as error:
                raise BrowserPortRefused("BROWSER_REF_INVALID") from error
            binding = self._binding(caller, browser)
            socket_path = self._relay_root / f"{browser.start_action_id}.sock"
        try:
            prepared = self._codec.decode_action(
                action_ref, now_ms=self._now(), require_fresh=require_live
            )
        except BrowserContractError as error:
            raise BrowserPortRefused("BROWSER_ACTION_INVALID") from error
        if (
            prepared.browser_ref_sha256
            != hashlib.sha256(browser_ref.encode("utf-8")).hexdigest()
            or prepared.subject_digest != browser.subject_digest
            or prepared.client_ref != browser.client_ref
            or prepared.resource != browser.resource
            or prepared.project_ref != browser.project_ref
            or prepared.context_ref != browser.context_ref
            or prepared.responsibility_ref != browser.responsibility_ref
            or prepared.operation_ref != browser.operation_ref
            or prepared.owner_ref != browser.owner_ref
            or prepared.generation != browser.generation
            or prepared.host_id != browser.host_id
            or prepared.boot_session_id != browser.boot_session_id
        ):
            raise BrowserPortRefused("BROWSER_ACTION_BINDING_CHANGED")
        if prepared.tool_name not in backend_tool_policy(browser.tool_schema_digest)[0]:
            raise BrowserPortRefused("BROWSER_TOOL_NOT_GRANTED")
        return browser, binding, socket_path, prepared

    @staticmethod
    def _classification_receipt(classified, *, reconciled: bool) -> dict[str, Any]:
        result = classified.result
        return {
            "status": "OK",
            "effect_state": classified.effect_state,
            "observed_sha256": result.observed_sha256 if result is not None else None,
            "reconciled": reconciled,
        }

    def reconcile_action(
        self,
        caller: ActionCaller,
        browser_ref: object,
        action_ref: object,
    ) -> dict[str, Any]:
        browser, binding, _socket_path, prepared = self._decode_action(
            caller, browser_ref, action_ref, require_live=False
        )
        identity = self._action_identity(browser, binding, prepared)
        classified = classify_action(self._store, identity)
        if classified.evidence_status == "qualified":
            return self._classification_receipt(classified, reconciled=True)
        # Absence alone is not a terminal no-effect proof: the original
        # invocation could still be waiting to acquire its durable claim.
        return {
            "status": "OK",
            "effect_state": "EFFECT_UNKNOWN",
            "observed_sha256": None,
            "reconciled": True,
        }

    @staticmethod
    def _unknown(*, reconciled: bool = False) -> dict[str, Any]:
        return {"status": "OK", "effect_state": "EFFECT_UNKNOWN",
                "observed_sha256": None, "reconciled": reconciled}

    def _action_writer(self):
        # Wait only for a short store transaction, never repeat browser I/O.
        deadline = time.monotonic() + 0.75
        while True:
            try:
                return acquire_store_writer(self._store)
            except ActionArtifactBusy:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.01)

    def _finalize_claimed(self, identity, claim, **values):
        with self._action_writer():
            classified = classify_action(self._store, identity)
            if classified.evidence_status == "qualified":
                result = classified.result
                if (result.effect_state == values["effect_state"]
                        and result.observed_sha256 == values["observed_sha256"]):
                    return result
                raise ActionArtifactUncertain("browser completion evidence conflicts")
            if classified.evidence_status != "pending" or classified.claim != claim:
                raise ActionArtifactUncertain("original browser claim changed")
            return finalize_action(self._store, identity, **values)

    @staticmethod
    def _result_effect(browser, prepared, result):
        if browser.tool_schema_digest != LINK_TOOL_SCHEMA_DIGEST:
            return "APPLIED" if result.get("isError") is False else "EFFECT_UNKNOWN"
        metadata = result.get("structuredContent")
        if (type(metadata) is not dict or not {"schema", "request_id", "effect_state", "status"} <= metadata.keys()
                or metadata.keys() - {"schema", "request_id", "effect_state", "status", "code", "document_revision"}
                or metadata.get("schema") != OWNER_RESULT_SCHEMA
                or metadata.get("request_id") != prepared.action_id
                or type(result.get("isError")) is not bool):
            return None
        combination = (metadata.get("status"), metadata.get("effect_state"), result["isError"])
        if any(type(item) is not str for item in combination[:2]):
            return None
        if combination not in {
            ("completed", "APPLIED", False),
            ("refused", "NOT_APPLIED", True),
            ("refused", "EFFECT_UNKNOWN", True),
            ("pending", "EFFECT_UNKNOWN", True),
        }:
            return None
        return metadata["effect_state"]

    def has_active_actions(self) -> bool:
        """Observe this original action owner's dispatches; caller holds the store writer."""
        with self._inflight_gate:
            return bool(self._inflight_actions)

    def _require_resolved_link_history(self, browser):
        if browser.tool_schema_digest != LINK_TOOL_SCHEMA_DIGEST:
            return
        with self._inflight_gate:
            inflight = frozenset(self._inflight_actions)
        prefix = f"browser:{browser.start_action_id}:"
        for classified in enumerate_action_evidence(self._store):
            identity = classified.claim.identity
            if identity.purpose != ACTION_PURPOSE_BROWSER_ACTION or not identity.relative_path.startswith(prefix):
                continue
            if classified.evidence_status == "pending" and identity.action_id in inflight:
                continue
            if classified.evidence_status != "qualified" or classified.effect_state == "EFFECT_UNKNOWN":
                raise BrowserPortRefused("BROWSER_EFFECT_UNRESOLVED")

    def run_action(
        self, caller: ActionCaller, browser_ref: object, action_ref: object,
    ) -> dict[str, Any]:
        browser, binding, socket_path, prepared = self._decode_action(
            caller, browser_ref, action_ref, require_live=False
        )
        identity = self._action_identity(browser, binding, prepared)
        owns_claim = False
        try:
            original_binding = _binding_key(binding)
            try:
                writer = self._action_writer()
            except (ActionArtifactBusy, ActionArtifactUncertain):
                # Another invocation could already have claimed this original ID.
                return self._unknown(reconciled=True)
            with writer:
                classified = classify_action(self._store, identity)
                if classified.evidence_status == "qualified":
                    return self._classification_receipt(classified, reconciled=True)
                if classified.evidence_status != "absent":
                    return self._unknown(reconciled=True)
                fresh_browser, fresh_binding, fresh_socket, fresh_prepared = self._decode_action(
                    caller, browser_ref, action_ref
                )
                if (fresh_browser != browser or _binding_key(fresh_binding) != original_binding
                        or fresh_socket != socket_path or fresh_prepared != prepared):
                    raise BrowserPortRefused("BROWSER_ACTION_BINDING_CHANGED")
                self._require_resolved_link_history(browser)
                outcome = claim_action(self._store, identity, claimed_at_ms=self._now())
                if not outcome.created:
                    return self._unknown(reconciled=True)
                with self._inflight_gate:
                    self._inflight_actions.add(identity.action_id)
                    owns_claim = True

            # Only this invocation created the durable claim. Release the shared
            # store lock while Chrome works; duplicates only observe the claim.
            reason = None
            try:
                current_browser, current_binding, current_socket = self._resource(caller, browser_ref)
            except BrowserPortRefused:
                reason = "binding_refused_before_dispatch"
            else:
                if (_binding_key(current_binding) != original_binding or current_browser != browser
                        or current_socket != socket_path or self._now() >= prepared.expires_at_ms):
                    reason = "binding_changed_before_dispatch"
            if reason is not None:
                self._finalize_claimed(
                    identity, outcome.claim, effect_state="NOT_APPLIED", observed_sha256=None,
                    completed_at_ms=self._now(), durability="durable", details={"reason": reason},
                )
                return {"status": "OK", "effect_state": "NOT_APPLIED",
                        "observed_sha256": None, "reconciled": False}
            try:
                response = self._relay(
                    socket_path=socket_path, browser=browser, request_id=prepared.action_id,
                    tool=prepared.tool_name, arguments=json.loads(prepared.arguments_json),
                )
            except BrowserRelayError:
                return self._unknown()

            observed_sha256 = None
            result = None
            if response["ok"] is not True:
                if response.get("error") != "REQUEST_REFUSED":
                    return self._unknown()
                effect_state = "NOT_APPLIED"
                details = {"relay_error": "REQUEST_REFUSED"}
            else:
                result = response.get("result")
                if type(result) is not dict:
                    return self._unknown()
                effect_state = self._result_effect(browser, prepared, result)
                if effect_state is None:
                    return self._unknown()
                try:
                    result_bytes = json.dumps(result, sort_keys=True, separators=(",", ":"),
                                              ensure_ascii=False, allow_nan=False).encode("utf-8")
                except (TypeError, ValueError):
                    return self._unknown()
                observed_sha256 = hashlib.sha256(result_bytes).hexdigest()
                details = {"tool": prepared.tool_name, "browser_tool_effect_only": True}
            try:
                # Persist the exact original effect even if its lease has since
                # expired. Saving evidence requires no new browser authority.
                result_record = self._finalize_claimed(
                    identity, outcome.claim, effect_state=effect_state, observed_sha256=observed_sha256,
                    completed_at_ms=self._now(), durability="durable", details=details,
                )
            except (ActionArtifactBusy, ActionArtifactUncertain, OSError):
                return self._unknown()
            receipt = {"status": "OK", "effect_state": result_record.effect_state,
                       "observed_sha256": result_record.observed_sha256, "reconciled": False}
            if result is not None and result_record.effect_state == "APPLIED":
                receipt["result"] = result
            return receipt
        finally:
            if owns_claim:
                with self._inflight_gate:
                    self._inflight_actions.discard(identity.action_id)



__all__ = [
    "BrowserActionPort",
    "BrowserPortRefused",
]
